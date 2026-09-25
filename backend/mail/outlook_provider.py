# ==============================================================================
# PZ_26/08 - Dual-Mode Microsoft Graph API Mail Provider
# Supports Personal Consumer Testing (Device Code / Refresh Token) and
# Enterprise Organizational Deployment (Entra ID Client Credentials Grant)
# ==============================================================================

import os
import json
import base64
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import requests

from .base import BaseMailProvider, EmailAttachmentDTO, IncomingEmailDTO, OutgoingEmailDTO

logger = logging.getLogger("cdtrs.mail.outlook")


class OutlookGraphProvider(BaseMailProvider):
    """
    Dual-Mode Microsoft Graph API Mail Provider for CDTRS.
    Supports:
    1. Personal / Consumer Mode: Delegated OAuth2 Device Code / Refresh Token for @outlook.com / @hotmail.com
    2. Organizational Mode: OAuth2 Client Credentials Grant for Microsoft 365 / Azure Entra ID
    """

    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
    LOGIN_BASE_URL = "https://login.microsoftonline.com"
    DEFAULT_PUBLIC_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"

    def __init__(self):
        self.auth_mode = os.getenv("OUTLOOK_AUTH_MODE", "").lower()
        self.tenant_id = os.getenv("OUTLOOK_TENANT_ID", "").strip()
        self.client_id = os.getenv("OUTLOOK_CLIENT_ID", "").strip() or self.DEFAULT_PUBLIC_CLIENT_ID
        self.client_secret = os.getenv("OUTLOOK_CLIENT_SECRET", "").strip()
        self.mailbox = os.getenv("OUTLOOK_MAILBOX", "").strip()
        self.folder = os.getenv("OUTLOOK_FOLDER", "Inbox").strip()
        self.token_file = Path(__file__).parent / ".token_cache.json"

        self._cached_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def is_configured(self) -> bool:
        # Configured if personal token cache exists OR organizational credentials provided
        if self.token_file.exists():
            return True
        if self.tenant_id and self.client_id and self.client_secret and self.mailbox:
            return True
        return False

    def _get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        # 1. Return in-memory cached token if valid (with 5-minute safety buffer).
        #    When force_refresh=True, deliberately skip all cached access tokens.
        now_dt = datetime.utcnow()
        if not force_refresh and self._cached_token and self._token_expires_at:
            if now_dt < (self._token_expires_at - timedelta(minutes=5)):
                return self._cached_token

        # 2. Try Personal Token Cache (Refresh Token Flow)
        if self.token_file.exists():
            try:
                with open(self.token_file, "r", encoding="utf-8") as fh:
                    tok_data = json.load(fh)
                
                # Check if file cached access_token is still valid before calling network.
                # When force_refresh=True, skip the cached access token and redeem the
                # refresh token instead.
                cached_file_tok = tok_data.get("access_token")
                cached_exp_str = tok_data.get("expires_at")
                if not force_refresh and cached_file_tok and cached_exp_str:
                    try:
                        exp_dt = datetime.fromisoformat(cached_exp_str)
                        if now_dt < (exp_dt - timedelta(minutes=5)):
                            self._cached_token = cached_file_tok
                            self._token_expires_at = exp_dt
                            return self._cached_token
                    except Exception:
                        pass

                refresh_token = tok_data.get("refresh_token")
                client_id = tok_data.get("client_id") or self.client_id or self.DEFAULT_PUBLIC_CLIENT_ID

                if refresh_token:
                    token_url = f"{self.LOGIN_BASE_URL}/common/oauth2/v2.0/token"
                    payload = {
                        "client_id": client_id,
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                    }
                    resp = requests.post(token_url, data=payload, timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        self._cached_token = data.get("access_token")
                        expires_in = data.get("expires_in", 3600)
                        self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

                        # Update cache
                        tok_data["access_token"] = self._cached_token
                        tok_data["expires_at"] = self._token_expires_at.isoformat()
                        if "refresh_token" in data:
                            tok_data["refresh_token"] = data["refresh_token"]
                        with open(self.token_file, "w", encoding="utf-8") as fw:
                            json.dump(tok_data, fw, indent=2)
                        return self._cached_token
                    else:
                        logger.error(f"Personal token refresh HTTP {resp.status_code}: {resp.text}")
            except Exception as ex:
                logger.error(f"Personal token refresh error: {ex}")

        # 3. Try Organizational Client Credentials Flow
        if self.tenant_id and self.client_id and self.client_secret:
            token_url = f"{self.LOGIN_BASE_URL}/{self.tenant_id}/oauth2/v2.0/token"
            payload = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials"
            }
            try:
                resp = requests.post(token_url, data=payload, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    self._cached_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                    return self._cached_token
            except Exception as ex:
                logger.error(f"OAuth2 client credentials error: {ex}")

        return None

    def fetch_incoming_emails(
        self,
        max_count: int = 50,
        unread_only: bool = True
    ) -> List[IncomingEmailDTO]:
        if not self.is_configured():
            return []

        token = self._get_access_token()
        if not token:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }

        # Determine target endpoint: /me or /users/{mailbox}
        if self.token_file.exists() and not (self.tenant_id and self.client_secret):
            url = f"{self.GRAPH_BASE_URL}/me/mailFolders/{self.folder}/messages"
        else:
            box = self.mailbox or "me"
            url = f"{self.GRAPH_BASE_URL}/users/{box}/mailFolders/{self.folder}/messages"

        # Microsoft Graph OData query options.  Graph only accepts $orderby
        # together with $filter when the ordered property is also filtered
        # first, hence the (always true) receivedDateTime condition.
        params: Dict[str, Any] = {
            "$top": max_count,
            "$expand": "attachments",
            "$select": "id,subject,bodyPreview,body,from,receivedDateTime,hasAttachments,isRead",
            "$orderby": "receivedDateTime desc",
        }
        if unread_only:
            params["$filter"] = "receivedDateTime ge 1900-01-01T00:00:00Z and isRead eq false"

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=25)

            # If Graph rejects the cached bearer token, force one refresh and retry once.
            # This handles a stale/revoked access token even when the local expires_at
            # value still says the token is valid.
            if resp.status_code == 401 and self.token_file.exists():
                refreshed_token = self._get_access_token(force_refresh=True)
                if refreshed_token:
                    headers["Authorization"] = f"Bearer {refreshed_token}"
                    resp = requests.get(url, headers=headers, params=params, timeout=25)

            # Fallback to /me if /users/{mailbox} failed on personal accounts
            if resp.status_code == 404 and "/users/" in url:
                url = f"{self.GRAPH_BASE_URL}/me/mailFolders/{self.folder}/messages"
                resp = requests.get(url, headers=headers, params=params, timeout=25)

            if resp.status_code != 200:
                logger.error(f"Graph API fetch messages failed: {resp.status_code} - {resp.text}")
                return []

            data = resp.json()
            raw_messages = data.get("value", [])
            results: List[IncomingEmailDTO] = []

            for msg in raw_messages:
                msg_id = msg.get("id", "")
                subject = msg.get("subject") or "Untitled Email Dispatch"
                body_obj = msg.get("body") or {}
                body_text = body_obj.get("content") or msg.get("bodyPreview") or ""
                body_html = body_obj.get("content") if body_obj.get("contentType", "").lower() == "html" else None

                from_dict = msg.get("from") or {}
                email_addr_obj = from_dict.get("emailAddress") or {}
                sender_name = email_addr_obj.get("name")
                sender_email = email_addr_obj.get("address")

                received_str = msg.get("receivedDateTime")
                try:
                    received_at = datetime.fromisoformat(received_str.replace("Z", "+00:00")) if received_str else datetime.utcnow()
                except Exception:
                    received_at = datetime.utcnow()

                has_att = bool(msg.get("hasAttachments", False))
                attachments_list: List[EmailAttachmentDTO] = []

                if has_att and "attachments" in msg:
                    for att in msg.get("attachments", []):
                        if att.get("@odata.type") == "#microsoft.graph.fileAttachment":
                            att_name = att.get("name", "attachment.pdf")
                            att_type = att.get("contentType", "application/octet-stream")
                            att_size = att.get("size", 0)
                            raw_b64 = att.get("contentBytes", "")
                            try:
                                att_bytes = base64.b64decode(raw_b64) if raw_b64 else b""
                            except Exception:
                                att_bytes = b""

                            attachments_list.append(EmailAttachmentDTO(
                                filename=att_name,
                                content_type=att_type,
                                size_bytes=att_size or len(att_bytes),
                                content_bytes=att_bytes
                            ))

                dto = IncomingEmailDTO(
                    message_id=msg_id,
                    sender_name=sender_name,
                    sender_email=sender_email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    received_at=received_at,
                    has_attachments=bool(attachments_list),
                    attachments=attachments_list
                )
                results.append(dto)

            return results

        except Exception as ex:
            logger.error(f"Error fetching Outlook emails: {ex}")
            return []

    def send_email(self, email: OutgoingEmailDTO) -> bool:
        if not self.is_configured():
            return False

        token = self._get_access_token()
        if not token:
            return False

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        if self.token_file.exists() and not (self.tenant_id and self.client_secret):
            url = f"{self.GRAPH_BASE_URL}/me/sendMail"
        else:
            box = self.mailbox or "me"
            url = f"{self.GRAPH_BASE_URL}/users/{box}/sendMail"

        message_payload: Dict[str, Any] = {
            "subject": email.subject,
            "body": {
                "contentType": "HTML" if email.body_html else "Text",
                "content": email.body_html or email.body_text
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "name": email.recipient_name,
                        "address": email.recipient_email
                    }
                }
            ]
        }

        if email.attachments:
            att_payloads = []
            for a in email.attachments:
                att_payloads.append({
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": a.filename,
                    "contentType": a.content_type,
                    "contentBytes": base64.b64encode(a.content_bytes).decode("utf-8")
                })
            message_payload["attachments"] = att_payloads

        send_payload = {
            "message": message_payload,
            "saveToSentItems": True
        }

        try:
            resp = requests.post(url, headers=headers, json=send_payload, timeout=20)

            # Retry once with a freshly redeemed access token if the cached token
            # is rejected by Microsoft Graph.
            if resp.status_code == 401 and self.token_file.exists():
                refreshed_token = self._get_access_token(force_refresh=True)
                if refreshed_token:
                    headers["Authorization"] = f"Bearer {refreshed_token}"
                    resp = requests.post(
                        url,
                        headers=headers,
                        json=send_payload,
                        timeout=20,
                    )

            if resp.status_code == 404 and "/users/" in url:
                url = f"{self.GRAPH_BASE_URL}/me/sendMail"
                resp = requests.post(url, headers=headers, json=send_payload, timeout=20)

            if resp.status_code in (200, 202):
                return True
            else:
                logger.error(f"Graph API sendMail failed: {resp.status_code} - {resp.text}")
                return False
        except Exception as ex:
            logger.error(f"Error sending Outlook email: {ex}")
            return False

    def mark_as_read(self, message_id: str) -> bool:
        if not self.is_configured() or not message_id:
            return False

        token = self._get_access_token()
        if not token:
            return False

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        if self.token_file.exists() and not (self.tenant_id and self.client_secret):
            url = f"{self.GRAPH_BASE_URL}/me/messages/{message_id}"
        else:
            box = self.mailbox or "me"
            url = f"{self.GRAPH_BASE_URL}/users/{box}/messages/{message_id}"

        try:
            resp = requests.patch(url, headers=headers, json={"isRead": True}, timeout=15)

            # Retry once with a freshly redeemed access token if Graph rejects
            # the cached bearer token.
            if resp.status_code == 401 and self.token_file.exists():
                refreshed_token = self._get_access_token(force_refresh=True)
                if refreshed_token:
                    headers["Authorization"] = f"Bearer {refreshed_token}"
                    resp = requests.patch(
                        url,
                        headers=headers,
                        json={"isRead": True},
                        timeout=15,
                    )

            if resp.status_code == 404 and "/users/" in url:
                url = f"{self.GRAPH_BASE_URL}/me/messages/{message_id}"
                resp = requests.patch(
                    url,
                    headers=headers,
                    json={"isRead": True},
                    timeout=15,
                )

            return resp.status_code == 200
        except Exception:
            return False
