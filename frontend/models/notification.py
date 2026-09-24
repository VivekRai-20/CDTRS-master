from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class NotificationModel:
    """
    Frontend domain model representing an in-app workflow notification.
    """

    id: Optional[int] = None
    user_id: int = 0
    document_id: Optional[int] = None
    document_reference: Optional[str] = None
    title: str = ""
    message: str = ""
    is_read: bool = False
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NotificationModel":
        return cls(
            id=data.get("id"),
            user_id=data.get("user_id", 0),
            document_id=data.get("document_id"),
            document_reference=(
                data.get("document_reference")
                or data.get("reference")
            ),
            title=data.get("title", ""),
            message=data.get("message", ""),
            is_read=data.get("is_read", False),
            created_at=data.get("created_at"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "document_id": self.document_id,
            "document_reference": self.document_reference,
            "title": self.title,
            "message": self.message,
            "is_read": self.is_read,
            "created_at": self.created_at,
        }


@dataclass
class ReminderModel:
    """
    Frontend domain model representing a deadline/action reminder.
    """

    id: Optional[int] = None
    document_id: Optional[int] = None
    work_item_id: Optional[int] = None
    recipient_user_id: Optional[int] = None

    reason: str = ""
    message: str = ""

    due_at: Optional[str] = None
    is_read: bool = False
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReminderModel":
        return cls(
            id=data.get("id"),
            document_id=data.get("document_id"),
            work_item_id=data.get("work_item_id"),
            recipient_user_id=data.get("recipient_user_id"),
            reason=data.get("reason", ""),
            message=(
                data.get("message")
                or data.get("description")
                or data.get("title")
                or ""
            ),
            due_at=data.get("due_at"),
            is_read=data.get("is_read", False),
            created_at=data.get("created_at"),
        )

    @property
    def title(self) -> str:
        if self.reason:
            return self.reason.replace("_", " ").title()

        return "Deadline Reminder"

    @property
    def document_reference(self) -> Optional[str]:
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "work_item_id": self.work_item_id,
            "recipient_user_id": self.recipient_user_id,
            "reason": self.reason,
            "message": self.message,
            "due_at": self.due_at,
            "is_read": self.is_read,
            "created_at": self.created_at,
        }