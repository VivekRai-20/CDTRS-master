"""
Notification and reminder service for the active work context.

Notifications:
    Workflow/activity events.

Reminders:
    Deadline/action reminders.

Both are displayed through the notification bell, but remain
separate backend concepts.
"""

from typing import List, Dict, Any, Optional

from models.notification import (
    NotificationModel,
    ReminderModel,
)

from repositories.provider import get_repository


class NotificationService:

    # =========================================================
    # NOTIFICATIONS
    # =========================================================

    def get_notifications(
        self,
        unread_only: bool = False,
    ) -> List[NotificationModel]:

        return get_repository().get_notifications(
            unread_only=unread_only
        )

    def get_unread(self) -> List[NotificationModel]:

        return self.get_notifications(
            unread_only=True
        )

    def unread_count(self) -> int:

        try:
            return len(self.get_unread())
        except Exception:
            return 0

    def mark_as_read(
        self,
        notification_id: int,
    ) -> bool:

        return get_repository().mark_notification_read(
            notification_id
        )

    def mark_all_read(self) -> int:

        return get_repository().mark_all_notifications_read()

    # =========================================================
    # REMINDERS
    # =========================================================

    def get_reminders(
        self,
    ) -> List[ReminderModel]:

        return get_repository().get_reminders()

    def get_unread_reminders(
        self,
    ) -> List[ReminderModel]:

        return [
            reminder
            for reminder in self.get_reminders()
            if not reminder.is_read
        ]

    def unread_reminder_count(self) -> int:

        try:
            return len(self.get_unread_reminders())
        except Exception:
            return 0

    def mark_reminder_as_read(
        self,
        reminder_id: int,
    ) -> bool:

        return get_repository().mark_reminder_read(
            reminder_id
        )

    # =========================================================
    # COMBINED ALERT COUNT
    # =========================================================

    def unread_alert_count(self) -> int:

        return (
            self.unread_count()
            + self.unread_reminder_count()
        )

    # =========================================================
    # DEADLINE CHECK
    # =========================================================

    def check_deadlines(
        self,
    ) -> Dict[str, Any]:

        return get_repository().check_reminders()

    # =========================================================
    # MANUAL REMINDER
    # =========================================================

    def send_reminder(
        self,
        document_id: int,
        work_item_id: Optional[int] = None,
        recipient_user_id: Optional[int] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:

        return get_repository().send_document_reminder(
            document_id,
            work_item_id,
            recipient_user_id,
            message,
        )


notification_service = NotificationService()