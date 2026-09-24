# ==============================================================================
# PZ_26/08 - Base Mail Provider Interface & Typed Data Transfer Objects (DTOs)
# Pluggable email abstraction layer supporting Outlook, Government Mail (NIC), etc.
# ==============================================================================

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class EmailAttachmentDTO:
    filename: str
    content_type: str
    size_bytes: int
    content_bytes: bytes


@dataclass
class IncomingEmailDTO:
    message_id: str
    sender_name: Optional[str]
    sender_email: Optional[str]
    subject: str
    body_text: Optional[str]
    body_html: Optional[str]
    received_at: datetime
    has_attachments: bool = False
    attachments: List[EmailAttachmentDTO] = field(default_factory=list)


@dataclass
class OutgoingEmailDTO:
    recipient_email: str
    recipient_name: str
    subject: str
    body_text: str
    body_html: Optional[str] = None
    attachments: Optional[List[EmailAttachmentDTO]] = None


class BaseMailProvider(ABC):
    """
    Abstract Base Class for mail providers in CDTRS.
    Enables pluggable mail providers (Outlook / Microsoft Graph, Government NIC Mail, SMTP/IMAP).
    """

    @abstractmethod
    def is_configured(self) -> bool:
        """Returns True if required credentials and endpoints are configured in environment."""
        pass

    @abstractmethod
    def fetch_incoming_emails(
        self,
        max_count: int = 50,
        unread_only: bool = True
    ) -> List[IncomingEmailDTO]:
        """Fetches incoming emails with attachments from the designated inbox."""
        pass

    @abstractmethod
    def send_email(self, email: OutgoingEmailDTO) -> bool:
        """Dispatches an outgoing email."""
        pass

    @abstractmethod
    def mark_as_read(self, message_id: str) -> bool:
        """Marks an incoming message as read in the mailbox."""
        pass
