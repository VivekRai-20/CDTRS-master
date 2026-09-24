# ==============================================================================
# CDTRS - Intranet / Office Mail Provider
# Standard IMAP + SMTP
#
# MAILBOX ARCHITECTURE
# --------------------
# INCOMING:
#     DS mailbox -> IMAP -> CDTRS
#
# OUTGOING:
#     CDTRS application mailbox -> SMTP -> recipients
#
# The DS mailbox and CDTRS application mailbox are independent.
#
# Supports:
#     IMAP SSL/TLS
#     IMAP STARTTLS
#     IMAP plain/internal connection
#     SMTP SSL/TLS
#     SMTP STARTTLS
#     SMTP plain/internal connection
#
# Authentication currently supports username/password.
# OAuth2 can be added later if the office requires it.
# ==============================================================================

import os
import ssl
import email
import logging
import imaplib
import smtplib

from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from datetime import datetime
from typing import List, Optional

from .base import (
    BaseMailProvider,
    EmailAttachmentDTO,
    IncomingEmailDTO,
    OutgoingEmailDTO,
)

logger = logging.getLogger("cdtrs.mail.intranet")

# Network timeout (seconds) for IMAP.  Without one, an unreachable mail
# server blocks the mailbox sync for minutes.
try:
    _IMAP_TIMEOUT = float(os.getenv("IMAP_TIMEOUT", "20"))
except ValueError:
    _IMAP_TIMEOUT = 20.0


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


def _env_security(name: str, default: str) -> str:
    value = os.getenv(name, default).strip().lower()

    aliases = {
        "tls": "starttls",
        "ssl/tls": "ssl",
        "ssl_tls": "ssl",
        "none": "plain",
        "": default,
    }

    return aliases.get(value, value)


class IntranetMailProvider(BaseMailProvider):
    """
    Standard IMAP/SMTP provider for the CDTRS office mail system.

    Incoming mail:
        DS mailbox via IMAP.

    Outgoing mail:
        CDTRS application mailbox via SMTP.

    The two accounts are intentionally independent.
    """

    def __init__(self):

        # ==================================================================
        # IMAP - DS MAILBOX
        # ==================================================================

        self.imap_host = os.getenv(
            "INTRANET_IMAP_HOST",
            ""
        ).strip()

        self.imap_port = int(
            os.getenv("INTRANET_IMAP_PORT", "993")
        )

        # Supported:
        #   ssl
        #   starttls
        #   plain
        self.imap_security = _env_security(
            "INTRANET_IMAP_SECURITY",
            "ssl"
        )

        self.imap_auth = os.getenv(
            "INTRANET_IMAP_AUTH",
            "password"
        ).strip().lower()

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

        IMAP:
            DS mailbox

        SMTP:
            CDTRS application mailbox
        """

        imap_ready = bool(
            self.imap_host
            and self.ds_mail_user
        )

        smtp_ready = bool(
            self.smtp_host
            and self.cdtrs_mail_user
            and self.sender_address
        )

        return imap_ready and smtp_ready

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
    # IMAP CONNECTION - DS MAILBOX
    # ======================================================================

    def _connect_imap(self) -> Optional[imaplib.IMAP4]:

        try:

            if self.imap_security == "ssl":

                context = self._create_ssl_context()

                client = imaplib.IMAP4_SSL(
                    self.imap_host,
                    self.imap_port,
                    ssl_context=context,
                    timeout=_IMAP_TIMEOUT,
                )

            elif self.imap_security == "starttls":

                client = imaplib.IMAP4(
                    self.imap_host,
                    self.imap_port,
                    timeout=_IMAP_TIMEOUT,
                )

                context = self._create_ssl_context()

                client.starttls(
                    ssl_context=context
                )

            elif self.imap_security == "plain":

                client = imaplib.IMAP4(
                    self.imap_host,
                    self.imap_port,
                    timeout=_IMAP_TIMEOUT,
                )

            else:

                raise ValueError(
                    f"Unsupported IMAP security mode: "
                    f"{self.imap_security}"
                )

            # --------------------------------------------------------------
            # Authentication
            # --------------------------------------------------------------

            if self.imap_auth == "password":

                if not self.ds_mail_user or not self.ds_mail_pass:
                    raise ValueError(
                        "DS mailbox username/password is not configured."
                    )

                client.login(
                    self.ds_mail_user,
                    self.ds_mail_pass,
                )

            else:

                raise ValueError(
                    f"Unsupported IMAP authentication mode: "
                    f"{self.imap_auth}"
                )

            logger.info(
                "Connected to DS mailbox via IMAP "
                f"({self.imap_host}:{self.imap_port}, "
                f"{self.imap_security})"
            )

            return client

        except Exception as ex:

            logger.error(
                "Failed to connect to DS mailbox via IMAP "
                f"({self.imap_host}:{self.imap_port}): {ex}"
            )

            return None

    # ======================================================================
    # INCOMING MAIL - DS MAILBOX
    # ======================================================================

    def fetch_incoming_emails(
        self,
        max_count: int = 50,
        unread_only: bool = True,
    ) -> List[IncomingEmailDTO]:

        if not self.is_configured():

            logger.info(
                "Intranet mail provider is not configured."
            )

            return []

        client = self._connect_imap()

        if not client:
            return []

        results: List[IncomingEmailDTO] = []

        try:

            status, _ = client.select("INBOX")

            if status != "OK":

                logger.error(
                    "Could not select DS mailbox INBOX."
                )

                return []

            search_crit = (
                "UNSEEN"
                if unread_only
                else "ALL"
            )

            status, msg_nums = client.search(
                None,
                search_crit,
            )

            if status != "OK":
                return []

            if not msg_nums or not msg_nums[0]:
                return []

            num_list = msg_nums[0].split()

            # Most recent first
            num_list = num_list[-max_count:][::-1]

            for num in num_list:

                try:

                    res, data = client.fetch(
                        num,
                        "(RFC822)",
                    )

                    if (
                        res != "OK"
                        or not data
                        or not isinstance(data[0], tuple)
                    ):
                        continue

                    raw_email = data[0][1]

                    msg = email.message_from_bytes(
                        raw_email
                    )

                    # ------------------------------------------------------
                    # Subject
                    # ------------------------------------------------------

                    subject_header = msg.get(
                        "Subject",
                        "(No Subject)"
                    )

                    subject = self._decode_header_str(
                        subject_header
                    )

                    # ------------------------------------------------------
                    # Sender
                    # ------------------------------------------------------

                    from_header = msg.get(
                        "From",
                        ""
                    )

                    sender_name, sender_email = (
                        self._parse_from_header(
                            from_header
                        )
                    )

                    # ------------------------------------------------------
                    # Message ID
                    # ------------------------------------------------------

                    msg_id = msg.get(
                        "Message-ID",
                        (
                            f"intranet-"
                            f"{num.decode('utf-8')}-"
                            f"{int(datetime.now().timestamp())}"
                        ),
                    )

                    msg_id = msg_id.strip(
                        "<>"
                    ).strip()

                    # ------------------------------------------------------
                    # Date
                    # ------------------------------------------------------

                    date_header = msg.get(
                        "Date"
                    )

                    received_at = datetime.now()

                    if date_header:

                        try:

                            parsed_date = (
                                email.utils
                                .parsedate_to_datetime(
                                    date_header
                                )
                            )

                            if parsed_date:

                                received_at = (
                                    parsed_date
                                    .replace(tzinfo=None)
                                )

                        except Exception:
                            pass

                    # ------------------------------------------------------
                    # Body and attachments
                    # ------------------------------------------------------

                    body_text = ""
                    body_html = ""

                    attachments: List[
                        EmailAttachmentDTO
                    ] = []

                    if msg.is_multipart():

                        for part in msg.walk():

                            content_type = (
                                part.get_content_type()
                            )

                            content_disposition = str(
                                part.get(
                                    "Content-Disposition",
                                    ""
                                )
                            )

                            filename = (
                                part.get_filename()
                            )

                            # --------------------------------------------------
                            # Attachment
                            # --------------------------------------------------

                            if filename:

                                filename = (
                                    self._decode_header_str(
                                        filename
                                    )
                                )

                                file_bytes = (
                                    part.get_payload(
                                        decode=True
                                    )
                                )

                                if file_bytes:

                                    attachments.append(
                                        EmailAttachmentDTO(
                                            filename=filename,
                                            content_type=(
                                                content_type
                                                or
                                                "application/octet-stream"
                                            ),
                                            size_bytes=len(
                                                file_bytes
                                            ),
                                            content_bytes=file_bytes,
                                        )
                                    )

                            elif (
                                "attachment"
                                in content_disposition
                            ):

                                file_bytes = (
                                    part.get_payload(
                                        decode=True
                                    )
                                )

                                if file_bytes:

                                    attachments.append(
                                        EmailAttachmentDTO(
                                            filename="attachment",
                                            content_type=(
                                                content_type
                                                or
                                                "application/octet-stream"
                                            ),
                                            size_bytes=len(
                                                file_bytes
                                            ),
                                            content_bytes=file_bytes,
                                        )
                                    )

                            # --------------------------------------------------
                            # Text
                            # --------------------------------------------------

                            elif (
                                content_type == "text/plain"
                                and not body_text
                            ):

                                payload = (
                                    part.get_payload(
                                        decode=True
                                    )
                                )

                                if payload:

                                    body_text = payload.decode(
                                        part.get_content_charset()
                                        or "utf-8",
                                        errors="replace",
                                    )

                            elif (
                                content_type == "text/html"
                                and not body_html
                            ):

                                payload = (
                                    part.get_payload(
                                        decode=True
                                    )
                                )

                                if payload:

                                    body_html = payload.decode(
                                        part.get_content_charset()
                                        or "utf-8",
                                        errors="replace",
                                    )

                    else:

                        content_type = (
                            msg.get_content_type()
                        )

                        payload = (
                            msg.get_payload(
                                decode=True
                            )
                        )

                        if payload:

                            decoded = payload.decode(
                                msg.get_content_charset()
                                or "utf-8",
                                errors="replace",
                            )

                            if content_type == "text/html":
                                body_html = decoded
                            else:
                                body_text = decoded

                    # ------------------------------------------------------
                    # DTO
                    # ------------------------------------------------------

                    dto = IncomingEmailDTO(
                        message_id=msg_id,
                        sender_name=(
                            sender_name
                            or "External Sender"
                        ),
                        sender_email=(
                            sender_email
                            or ""
                        ),
                        subject=subject,
                        body_text=(
                            body_text or None
                        ),
                        body_html=(
                            body_html or None
                        ),
                        received_at=received_at,
                        has_attachments=(
                            len(attachments) > 0
                        ),
                        attachments=attachments,
                    )

                    results.append(dto)

                except Exception as ex:

                    logger.warning(
                        "Error parsing IMAP message "
                        f"{num}: {ex}"
                    )

        except Exception as ex:

            logger.error(
                f"Error during DS IMAP fetch: {ex}"
            )

        finally:

            try:
                client.close()
            except Exception:
                pass

            try:
                client.logout()
            except Exception:
                pass

        return results

    # ======================================================================
    # MARK AS READ
    # ======================================================================

    def mark_as_read(
        self,
        message_id: str
    ) -> bool:

        # Current sync fetches RFC822 from UNSEEN messages.
        # IMAP normally marks them as seen when fetched.
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

        if not self.is_configured():

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