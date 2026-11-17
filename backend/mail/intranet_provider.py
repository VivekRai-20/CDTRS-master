# ==============================================================================
# CDTRS - Intranet / Office Mail Provider
# Standard POP3 + SMTP
#
# MAILBOX ARCHITECTURE
# --------------------
# INCOMING:
#     DS mailbox -> POP3 -> CDTRS
#
# OUTGOING:
#     CDTRS application mailbox -> SMTP -> recipients
#
# The DS mailbox and CDTRS application mailbox are independent.
#
# Supports:
#     POP3 SSL/TLS        (POP3S, usually port 995)
#     POP3 STARTTLS (STLS, usually port 110)
#     POP3 plain/internal connection (usually port 110)
#     SMTP SSL/TLS
#     SMTP STARTTLS
#     SMTP plain/internal connection
#
# POP3 has no server-side "seen" flag, so CDTRS remembers which messages it
# has already imported by their POP3 UIDL (unique id) in a small JSON state
# file.  Messages are left on the server; nothing is deleted.
#
# Authentication currently supports username/password.
# OAuth2 can be added later if the office requires it.
# ==============================================================================

import os
import ssl
import json
import email
import email.utils
import logging
import poplib
import smtplib
import tempfile
import threading

from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .base import (
    BaseMailProvider,
    EmailAttachmentDTO,
    IncomingEmailDTO,
    OutgoingEmailDTO,
)

logger = logging.getLogger("cdtrs.mail.intranet")

# Network timeout (seconds) for POP3.  Without one, an unreachable mail
# server blocks the mailbox sync for minutes.  IMAP_TIMEOUT is still honoured
# so existing .env files keep working.
try:
    _POP3_TIMEOUT = float(
        os.getenv("POP3_TIMEOUT") or os.getenv("IMAP_TIMEOUT") or "20"
    )
except ValueError:
    _POP3_TIMEOUT = 20.0

# Long mail lines (big HTML bodies, base64 without wrapping) can exceed
# poplib's default 2048-byte line limit and abort the download.
poplib._MAXLINE = max(getattr(poplib, "_MAXLINE", 2048), 1024 * 1024)

# A message handed to the sync service but never confirmed through
# mark_as_read() is usually one the service skipped as a duplicate (it is
# already in the database).  It is offered again this many more times, in
# case the import failed, and is then treated as already imported.
_UNCONFIRMED_RETRIES = 3

# Default location of the UIDL state file: backend/uploads/.mail_state/
_DEFAULT_STATE_FILE = (
    Path(__file__).resolve().parent.parent
    / "uploads"
    / ".mail_state"
    / "pop3_uidl_state.json"
)

# Several syncs (timer + on-demand) can run at once in the same process.
_STATE_LOCK = threading.Lock()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "true",
        "1",
        "yes",
        "y",
        "on",
    }


def _env_first(*names: str, default: str = "") -> str:
    """Returns the first non-empty environment variable among *names*."""
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _normalize_security(value: str, default: str) -> str:
    value = (value or "").strip().lower()

    aliases = {
        "tls": "starttls",
        "stls": "starttls",
        "ssl/tls": "ssl",
        "ssl_tls": "ssl",
        "pop3s": "ssl",
        "none": "plain",
        "": default,
    }

    return aliases.get(value, value)


def _env_security(name: str, default: str) -> str:
    return _normalize_security(os.getenv(name, default), default)


def _friendly_pop3_error(ex: Exception) -> str:
    """A short message for the Inbox screen.  Never includes the password."""
    if isinstance(ex, poplib.error_proto):
        return "The mail server refused the login. Check the e-mail ID and password."
    if isinstance(ex, (TimeoutError, ConnectionError, OSError)):
        return f"Could not reach the mail server: {ex}"
    return str(ex)


class IntranetMailProvider(BaseMailProvider):
    """
    Standard POP3/SMTP provider for the CDTRS office mail system.

    Incoming mail:
        DS mailbox via POP3.

    Outgoing mail:
        CDTRS application mailbox via SMTP.

    The two accounts are intentionally independent.
    """

    def __init__(self):

        # ==================================================================
        # POP3 - DS MAILBOX
        # ==================================================================
        # INTRANET_POP3_* settings are preferred.  The old INTRANET_IMAP_*
        # host/security/auth settings are used as a fallback so an existing
        # .env keeps working; the IMAP port is NOT reused (993 is IMAP-only).

        self.pop3_host = _env_first(
            "INTRANET_POP3_HOST",
            "INTRANET_IMAP_HOST",
        )

        # Supported:
        #   ssl       (POP3S, default port 995)
        #   starttls  (STLS,  default port 110)
        #   plain     (       default port 110)
        self.pop3_security = _normalize_security(
            _env_first(
                "INTRANET_POP3_SECURITY",
                "INTRANET_IMAP_SECURITY",
                default="ssl",
            ),
            "ssl",
        )

        default_port = "995" if self.pop3_security == "ssl" else "110"

        try:
            self.pop3_port = int(
                _env_first("INTRANET_POP3_PORT", default=default_port)
            )
        except ValueError:
            self.pop3_port = int(default_port)

        self.pop3_auth = _env_first(
            "INTRANET_POP3_AUTH",
            "INTRANET_IMAP_AUTH",
            default="password",
        ).lower()

        # Where the already-imported UIDLs are remembered.
        self.pop3_state_file = Path(
            _env_first(
                "INTRANET_POP3_STATE_FILE",
                default=str(_DEFAULT_STATE_FILE),
            )
        )

        # Backwards-compatible names (diagnostic scripts print these).
        self.imap_host = self.pop3_host
        self.imap_port = self.pop3_port
        self.imap_security = self.pop3_security
        self.imap_auth = self.pop3_auth

        # message_id -> UIDL for messages returned by the latest fetch,
        # used by mark_as_read() to confirm the import.
        self._fetched_uidls: Dict[str, str] = {}
        self.last_connect_error = ""

        # DS mailbox credentials
        self.ds_mail_user = os.getenv(
            "DS_MAIL_USER",
            ""
        ).strip()

        self.ds_mail_pass = os.getenv(
            "DS_MAIL_PASS",
            ""
        ).strip()

        # ==================================================================
        # SMTP - CDTRS APPLICATION MAILBOX
        # ==================================================================

        self.smtp_host = os.getenv(
            "INTRANET_SMTP_HOST",
            ""
        ).strip()

        self.smtp_port = int(
            os.getenv("INTRANET_SMTP_PORT", "587")
        )

        # Supported:
        #   ssl
        #   starttls
        #   plain
        self.smtp_security = _env_security(
            "INTRANET_SMTP_SECURITY",
            "starttls"
        )

        self.smtp_auth = os.getenv(
            "INTRANET_SMTP_AUTH",
            "password"
        ).strip().lower()

        # CDTRS application mailbox credentials
        self.cdtrs_mail_user = os.getenv(
            "CDTRS_MAIL_USER",
            ""
        ).strip()

        self.cdtrs_mail_pass = os.getenv(
            "CDTRS_MAIL_PASS",
            ""
        ).strip()

        # Sender identity of the CDTRS application mailbox
        self.sender_address = os.getenv(
            "CDTRS_SENDER_EMAIL",
            self.cdtrs_mail_user
        ).strip()

        self.sender_name = os.getenv(
            "CDTRS_SENDER_NAME",
            "CDTRS"
        ).strip()

        # ==================================================================
        # TLS
        # ==================================================================

        self.allow_selfsigned = _env_bool(
            "INTRANET_ALLOW_SELFSIGNED",
            False
        )

    # ======================================================================
    # CONFIGURATION
    # ======================================================================

    def is_configured(self) -> bool:
        """
        Returns True only when both sides of the office-mail integration
        have the required basic configuration.

        POP3:
            DS mailbox

        SMTP:
            CDTRS application mailbox
        """

        pop3_ready = bool(
            self.pop3_host
            and self.ds_mail_user
        )

        smtp_ready = bool(
            self.smtp_host
            and self.cdtrs_mail_user
            and self.sender_address
        )

        return pop3_ready and smtp_ready

    def is_receive_configured(self) -> bool:
        """POP3 side only: a server and a mailbox login to read."""
        return bool(self.pop3_host and self.ds_mail_user and self.ds_mail_pass)

    def is_send_configured(self) -> bool:
        """SMTP side only.  Outgoing notifications do not depend on the
        mailbox that is read, so they keep working when the mailbox login
        comes from the Inbox screen instead of .env."""
        return bool(self.smtp_host and self.cdtrs_mail_user and self.sender_address)

    def with_mailbox_login(self, username: str, password: str) -> "IntranetMailProvider":
        """A copy of this provider that reads the given mailbox instead of
        DS_MAIL_USER / DS_MAIL_PASS.  Server settings still come from .env.
        The password is only held on the copy for the duration of one sync;
        it is never written anywhere."""
        import copy
        import hashlib

        clone = copy.copy(self)
        clone._fetched_uidls = {}
        clone.ds_mail_user = (username or "").strip()
        clone.ds_mail_pass = password or ""
        # Each mailbox remembers its own imported messages.
        if clone.ds_mail_user.lower() != (self.ds_mail_user or "").lower():
            tag = hashlib.sha1(clone.ds_mail_user.lower().encode("utf-8")).hexdigest()[:12]
            clone.pop3_state_file = self.pop3_state_file.with_name(
                f"pop3_uidl_state_{tag}.json"
            )
        return clone

    # ======================================================================
    # TLS CONTEXT
    # ======================================================================

    def _create_ssl_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context()

        if self.allow_selfsigned:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        return context

    # ======================================================================
    # POP3 CONNECTION - DS MAILBOX
    # ======================================================================

    def _connect_pop3(self) -> Optional[poplib.POP3]:

        client = None
        self.last_connect_error = ""

        try:

            if self.pop3_security == "ssl":

                client = poplib.POP3_SSL(
                    self.pop3_host,
                    self.pop3_port,
                    timeout=_POP3_TIMEOUT,
                    context=self._create_ssl_context(),
                )

            elif self.pop3_security == "starttls":

                client = poplib.POP3(
                    self.pop3_host,
                    self.pop3_port,
                    timeout=_POP3_TIMEOUT,
                )

                client.stls(
                    context=self._create_ssl_context()
                )

            elif self.pop3_security == "plain":

                client = poplib.POP3(
                    self.pop3_host,
                    self.pop3_port,
                    timeout=_POP3_TIMEOUT,
                )

            else:

                raise ValueError(
                    f"Unsupported POP3 security mode: "
                    f"{self.pop3_security}"
                )

            # --------------------------------------------------------------
            # Authentication
            # --------------------------------------------------------------

            if self.pop3_auth == "password":

                if not self.ds_mail_user or not self.ds_mail_pass:
                    raise ValueError(
                        "DS mailbox username/password is not configured."
                    )

                client.user(self.ds_mail_user)
                client.pass_(self.ds_mail_pass)

            else:

                raise ValueError(
                    f"Unsupported POP3 authentication mode: "
                    f"{self.pop3_auth}"
                )

            logger.info(
                "Connected to DS mailbox via POP3 "
                f"({self.pop3_host}:{self.pop3_port}, "
                f"{self.pop3_security})"
            )

            return client

        except Exception as ex:

            self.last_connect_error = _friendly_pop3_error(ex)

            logger.error(
                "Failed to connect to DS mailbox via POP3 "
                f"({self.pop3_host}:{self.pop3_port}): {ex}"
            )

            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

            return None

    # ======================================================================
    # UIDL STATE (which messages were already imported)
    # ======================================================================

    def _load_state(self) -> dict:
        """
        State file layout:
            {
              "seen":    ["<uidl>", ...],      # imported (or given up on)
              "pending": {"<uidl>": <count>}   # handed out, not confirmed
            }
        """

        try:
            with open(self.pop3_state_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            return {
                "seen": set(data.get("seen", [])),
                "pending": dict(data.get("pending", {})),
            }

        except FileNotFoundError:
            return {"seen": set(), "pending": {}}

        except Exception as ex:
            logger.warning(
                f"Could not read POP3 state file "
                f"{self.pop3_state_file}: {ex}. Starting fresh; "
                "duplicates are still filtered by Message-ID."
            )
            return {"seen": set(), "pending": {}}

    def _save_state(self, state: dict) -> None:

        try:
            self.pop3_state_file.parent.mkdir(parents=True, exist_ok=True)

            payload = {
                "seen": sorted(state["seen"]),
                "pending": state["pending"],
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }

            # Write atomically so a crash never leaves a half-written file.
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.pop3_state_file.parent),
                prefix=".pop3_state_",
                suffix=".tmp",
            )

            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=1)

            os.replace(tmp_path, self.pop3_state_file)

        except Exception as ex:
            logger.error(
                f"Could not write POP3 state file "
                f"{self.pop3_state_file}: {ex}"
            )

    @staticmethod
    def _parse_uidl_listing(lines: List[bytes]) -> List[Tuple[int, str]]:
        """Parses UIDL lines such as b'1 000001a2b3' into (num, uidl)."""

        result: List[Tuple[int, str]] = []

        for line in lines or []:

            try:
                text = line.decode("ascii", errors="replace").strip()
                num_str, uidl = text.split(None, 1)
                result.append((int(num_str), uidl.strip()))
            except Exception:
                continue

        return result

    # ======================================================================
    # INCOMING MAIL - DS MAILBOX
    # ======================================================================

    def fetch_incoming_emails(
        self,
        max_count: int = 50,
        unread_only: bool = True,
    ) -> List[IncomingEmailDTO]:
        """
        Downloads messages from the DS mailbox via POP3.

        unread_only=True returns only messages whose UIDL has not been
        imported before ("new" mail).  unread_only=False returns the most
        recent messages regardless of state.  Messages stay on the server.
        """

        if not self.is_receive_configured():

            logger.info(
                "Intranet mail provider is not configured."
            )

            return []

        client = self._connect_pop3()

        if not client:
            # Let the sync report the real reason (wrong password, server
            # unreachable) instead of "0 new e-mails".
            raise RuntimeError(
                self.last_connect_error
                or "Could not connect to the mailbox."
            )

        results: List[IncomingEmailDTO] = []
        self._fetched_uidls = {}

        try:

            # --------------------------------------------------------------
            # Message list with unique ids
            # --------------------------------------------------------------

            try:
                _, uidl_lines, _ = client.uidl()
                listing = self._parse_uidl_listing(uidl_lines)
                uidl_supported = True

            except poplib.error_proto as ex:
                # Very old servers may not support UIDL.  Fall back to
                # message numbers; Message-ID still prevents duplicates.
                logger.warning(
                    f"POP3 server does not support UIDL ({ex}); "
                    "falling back to message numbers."
                )
                count, _ = client.stat()
                listing = [(n, "") for n in range(1, count + 1)]
                uidl_supported = False

            if not listing:
                return []

            with _STATE_LOCK:

                state = self._load_state()

                if uidl_supported:

                    on_server = {uidl for _, uidl in listing}

                    # Forget messages that were removed from the server so
                    # the state file does not grow forever.
                    state["seen"] &= on_server
                    state["pending"] = {
                        u: c
                        for u, c in state["pending"].items()
                        if u in on_server
                    }

                    # Unconfirmed messages: retry a few times, then give up
                    # (the service most likely skipped them as duplicates).
                    for uidl, attempts in list(state["pending"].items()):
                        if attempts > _UNCONFIRMED_RETRIES:
                            state["seen"].add(uidl)
                            del state["pending"][uidl]

                if unread_only and uidl_supported:
                    candidates = [
                        (num, uidl)
                        for num, uidl in listing
                        if uidl not in state["seen"]
                    ]
                else:
                    candidates = list(listing)

                # POP3 numbers messages oldest first; most recent first.
                candidates = candidates[-max_count:][::-1]

                if uidl_supported and unread_only:
                    for _, uidl in candidates:
                        state["pending"][uidl] = (
                            state["pending"].get(uidl, 0) + 1
                        )
                    self._save_state(state)

            # --------------------------------------------------------------
            # Download and parse
            # --------------------------------------------------------------

            for num, uidl in candidates:

                try:

                    _, lines, _ = client.retr(num)

                    raw_email = b"\r\n".join(lines) + b"\r\n"

                    dto = self._parse_message(
                        raw_email,
                        uidl or str(num),
                    )

                    if uidl:
                        self._fetched_uidls[dto.message_id] = uidl

                    results.append(dto)

                except Exception as ex:

                    logger.warning(
                        "Error reading POP3 message "
                        f"{num} ({uidl}): {ex}"
                    )

        except Exception as ex:

            logger.error(
                f"Error during DS POP3 fetch: {ex}"
            )

        finally:

            # QUIT ends the session.  No DELE commands are ever sent, so
            # nothing is removed from the mailbox.
            try:
                client.quit()
            except Exception:
                try:
                    client.close()
                except Exception:
                    pass

        return results

    # ======================================================================
    # MESSAGE PARSING
    # ======================================================================

    def _parse_message(
        self,
        raw_email: bytes,
        fallback_id: str,
    ) -> IncomingEmailDTO:

        msg = email.message_from_bytes(
            raw_email
        )

        # ------------------------------------------------------------------
        # Subject
        # ------------------------------------------------------------------

        subject = self._decode_header_str(
            msg.get("Subject", "(No Subject)")
        )

        # ------------------------------------------------------------------
        # Sender
        # ------------------------------------------------------------------

        sender_name, sender_email = self._parse_from_header(
            msg.get("From", "")
        )

        # ------------------------------------------------------------------
        # Message ID (stable fallback: the POP3 UIDL)
        # ------------------------------------------------------------------

        msg_id = str(
            msg.get("Message-ID", "") or ""
        ).strip().strip("<>").strip()

        if not msg_id:
            msg_id = f"intranet-pop3-{fallback_id}"

        # ------------------------------------------------------------------
        # Date
        # ------------------------------------------------------------------

        received_at = datetime.now()
        date_header = msg.get("Date")

        if date_header:

            try:

                parsed_date = email.utils.parsedate_to_datetime(
                    date_header
                )

                if parsed_date:
                    received_at = parsed_date.replace(tzinfo=None)

            except Exception:
                pass

        # ------------------------------------------------------------------
        # Body and attachments
        # ------------------------------------------------------------------

        body_text = ""
        body_html = ""

        attachments: List[EmailAttachmentDTO] = []

        if msg.is_multipart():

            for part in msg.walk():

                content_type = part.get_content_type()

                content_disposition = str(
                    part.get("Content-Disposition", "")
                )

                filename = part.get_filename()

                # ----------------------------------------------------------
                # Attachment
                # ----------------------------------------------------------

                if filename or "attachment" in content_disposition:

                    file_bytes = part.get_payload(decode=True)

                    if file_bytes:

                        attachments.append(
                            EmailAttachmentDTO(
                                filename=(
                                    self._decode_header_str(filename)
                                    if filename
                                    else "attachment"
                                ),
                                content_type=(
                                    content_type
                                    or "application/octet-stream"
                                ),
                                size_bytes=len(file_bytes),
                                content_bytes=file_bytes,
                            )
                        )

                # ----------------------------------------------------------
                # Text
                # ----------------------------------------------------------

                elif content_type == "text/plain" and not body_text:

                    payload = part.get_payload(decode=True)

                    if payload:
                        body_text = payload.decode(
                            part.get_content_charset() or "utf-8",
                            errors="replace",
                        )

                elif content_type == "text/html" and not body_html:

                    payload = part.get_payload(decode=True)

                    if payload:
                        body_html = payload.decode(
                            part.get_content_charset() or "utf-8",
                            errors="replace",
                        )

        else:

            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)

            if payload:

                decoded = payload.decode(
                    msg.get_content_charset() or "utf-8",
                    errors="replace",
                )

                if content_type == "text/html":
                    body_html = decoded
                else:
                    body_text = decoded

        # ------------------------------------------------------------------
        # DTO
        # ------------------------------------------------------------------

        return IncomingEmailDTO(
            message_id=msg_id,
            sender_name=sender_name or "External Sender",
            sender_email=sender_email or "",
            subject=subject,
            body_text=body_text or None,
            body_html=body_html or None,
            received_at=received_at,
            has_attachments=len(attachments) > 0,
            attachments=attachments,
        )

    # ======================================================================
    # MARK AS READ
    # ======================================================================

    def mark_as_read(
        self,
        message_id: str
    ) -> bool:
        """
        POP3 has no read flag.  Called by the sync service after a message
        was stored in CDTRS: records its UIDL as imported so it is not
        downloaded again.
        """

        uidl = self._fetched_uidls.pop(message_id, None)

        if not uidl:
            return True

        with _STATE_LOCK:
            state = self._load_state()
            state["seen"].add(uidl)
            state["pending"].pop(uidl, None)
            self._save_state(state)

        return True

    # ======================================================================
    # SMTP CONNECTION - CDTRS MAILBOX
    # ======================================================================

    def _connect_smtp(self):

        if self.smtp_security == "ssl":

            context = self._create_ssl_context()

            server = smtplib.SMTP_SSL(
                self.smtp_host,
                self.smtp_port,
                context=context,
                timeout=15,
            )

        elif self.smtp_security == "starttls":

            server = smtplib.SMTP(
                self.smtp_host,
                self.smtp_port,
                timeout=15,
            )

            context = self._create_ssl_context()

            server.starttls(
                context=context
            )

        elif self.smtp_security == "plain":

            server = smtplib.SMTP(
                self.smtp_host,
                self.smtp_port,
                timeout=15,
            )

        else:

            raise ValueError(
                f"Unsupported SMTP security mode: "
                f"{self.smtp_security}"
            )

        # --------------------------------------------------------------
        # Authentication
        # --------------------------------------------------------------

        if self.smtp_auth == "password":

            if (
                not self.cdtrs_mail_user
                or not self.cdtrs_mail_pass
            ):
                raise ValueError(
                    "CDTRS mailbox username/password "
                    "is not configured."
                )

            server.login(
                self.cdtrs_mail_user,
                self.cdtrs_mail_pass,
            )

        else:

            raise ValueError(
                f"Unsupported SMTP authentication mode: "
                f"{self.smtp_auth}"
            )

        return server

    # ======================================================================
    # OUTGOING MAIL - CDTRS MAILBOX
    # ======================================================================

    def send_email(
        self,
        email_dto: OutgoingEmailDTO
    ) -> bool:

        if not self.is_send_configured():

            logger.warning(
                "Intranet SMTP is not configured. "
                "Email dispatch skipped."
            )

            return False

        server = None

        try:

            msg = MIMEMultipart(
                "mixed"
            )

            msg["From"] = (
                f"{self.sender_name} "
                f"<{self.sender_address}>"
            )

            msg["To"] = (
                f"{email_dto.recipient_name} "
                f"<{email_dto.recipient_email}>"
            )

            msg["Subject"] = email_dto.subject

            msg["Date"] = (
                email.utils.formatdate(
                    localtime=True
                )
            )

            # ----------------------------------------------------------
            # Text / HTML
            # ----------------------------------------------------------

            alt_part = MIMEMultipart(
                "alternative"
            )

            if email_dto.body_text:

                alt_part.attach(
                    MIMEText(
                        email_dto.body_text,
                        "plain",
                        "utf-8",
                    )
                )

            if email_dto.body_html:

                alt_part.attach(
                    MIMEText(
                        email_dto.body_html,
                        "html",
                        "utf-8",
                    )
                )

            msg.attach(
                alt_part
            )

            # ----------------------------------------------------------
            # Attachments
            # ----------------------------------------------------------

            if email_dto.attachments:

                for att in email_dto.attachments:

                    part = MIMEApplication(
                        att.content_bytes,
                        Name=att.filename,
                    )

                    part[
                        "Content-Disposition"
                    ] = (
                        f'attachment; '
                        f'filename="{att.filename}"'
                    )

                    msg.attach(part)

            # ----------------------------------------------------------
            # SMTP
            # ----------------------------------------------------------

            server = self._connect_smtp()

            server.sendmail(
                self.sender_address,
                [email_dto.recipient_email],
                msg.as_string(),
            )

            logger.info(
                "Email successfully sent from CDTRS "
                f"mailbox {self.sender_address} "
                f"to {email_dto.recipient_email} "
                f"via {self.smtp_host}:{self.smtp_port}"
            )

            return True

        except Exception as ex:

            logger.error(
                "Failed to send email via CDTRS SMTP "
                f"({self.smtp_host}:{self.smtp_port}): {ex}"
            )

            return False

        finally:

            if server is not None:

                try:
                    server.quit()
                except Exception:
                    pass

    # ======================================================================
    # HELPERS
    # ======================================================================

    @staticmethod
    def _decode_header_str(
        header_str: str
    ) -> str:

        if not header_str:
            return ""

        decoded_fragments = (
            decode_header(header_str)
        )

        text_parts = []

        for text, encoding in decoded_fragments:

            if isinstance(text, bytes):

                try:

                    text_parts.append(
                        text.decode(
                            encoding
                            or "utf-8",
                            errors="replace",
                        )
                    )

                except Exception:

                    text_parts.append(
                        text.decode(
                            "latin1",
                            errors="replace",
                        )
                    )

            else:

                text_parts.append(
                    str(text)
                )

        return "".join(text_parts)

    @staticmethod
    def _parse_from_header(
        from_header: str
    ) -> tuple:

        if not from_header:
            return ("", "")

        name, addr = (
            email.utils.parseaddr(
                from_header
            )
        )

        return (
            name,
            addr,
        )