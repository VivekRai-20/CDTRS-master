from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.notification_service import notification_service


class NotificationPanel(QFrame):
    """
    Popup panel displaying unread workflow notifications
    and deadline reminders.
    """

    closed = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.setObjectName("NotificationPanel")
        self.setFixedWidth(390)
        self.setMaximumHeight(520)

        self.setStyleSheet(
            """
            QFrame#NotificationPanel {
                background-color: white;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
            }

            QLabel#PanelTitle {
                color: #0F172A;
                font-size: 15px;
                font-weight: 700;
            }

            QLabel#SectionTitle {
                color: #475569;
                font-size: 11px;
                font-weight: 700;
            }

            QLabel#EmptyLabel {
                color: #64748B;
                font-size: 12px;
                padding: 20px;
            }

            QFrame#NotificationItem {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 7px;
            }

            QPushButton {
                border: none;
                background: transparent;
                color: #2563EB;
                font-size: 11px;
            }

            QPushButton:hover {
                color: #1D4ED8;
            }
            """
        )

        self.setup_ui()
        self.refresh()

    # =========================================================
    # UI
    # =========================================================

    def setup_ui(self):

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(10)

        # -----------------------------------------------------
        # Header
        # -----------------------------------------------------

        header = QHBoxLayout()

        title = QLabel("Notifications")
        title.setObjectName("PanelTitle")

        header.addWidget(title)
        header.addStretch()

        self.mark_all_button = QPushButton("Mark all read")
        self.mark_all_button.clicked.connect(
            self.mark_all_read
        )

        header.addWidget(self.mark_all_button)

        close_button = QPushButton("✕")
        close_button.setFixedWidth(24)
        close_button.clicked.connect(self.close)

        header.addWidget(close_button)

        outer.addLayout(header)

        # -----------------------------------------------------
        # Scroll area
        # -----------------------------------------------------

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.content = QWidget()

        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(2, 2, 2, 2)
        self.content_layout.setSpacing(8)

        self.scroll.setWidget(self.content)

        outer.addWidget(self.scroll, 1)

    # =========================================================
    # REFRESH
    # =========================================================

    def refresh(self):

        while self.content_layout.count():

            item = self.content_layout.takeAt(0)

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        notifications = []

        reminders = []

        try:
            notifications = (
                notification_service.get_unread()
            )
        except Exception:
            notifications = []

        try:
            reminders = (
                notification_service.get_unread_reminders()
            )
        except Exception:
            reminders = []

        # -----------------------------------------------------
        # Workflow notifications
        # -----------------------------------------------------

        if notifications:

            section = QLabel("WORKFLOW NOTIFICATIONS")
            section.setObjectName("SectionTitle")

            self.content_layout.addWidget(section)

            for notification in notifications:

                self._add_notification(
                    notification
                )

        # -----------------------------------------------------
        # Reminders
        # -----------------------------------------------------

        if reminders:

            section = QLabel("REMINDERS")
            section.setObjectName("SectionTitle")

            self.content_layout.addWidget(section)

            for reminder in reminders:

                self._add_reminder(
                    reminder
                )

        # -----------------------------------------------------
        # Empty state
        # -----------------------------------------------------

        if not notifications and not reminders:

            empty = QLabel(
                "You're all caught up."
            )

            empty.setObjectName("EmptyLabel")
            empty.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            self.content_layout.addWidget(empty)

        self.content_layout.addStretch()

    # =========================================================
    # NOTIFICATION ITEM
    # =========================================================

    def _add_notification(
        self,
        notification,
    ):

        card = QFrame()
        card.setObjectName("NotificationItem")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title = QLabel(
            notification.title or "Notification"
        )

        title.setStyleSheet(
            "font-weight: 700; color: #0F172A;"
        )

        layout.addWidget(title)

        message = QLabel(
            notification.message or ""
        )

        message.setWordWrap(True)
        message.setStyleSheet(
            "color: #475569; font-size: 11px;"
        )

        layout.addWidget(message)

        if notification.document_reference:

            reference = QLabel(
                f"Document: "
                f"{notification.document_reference}"
            )

            reference.setStyleSheet(
                "color: #64748B; font-size: 10px;"
            )

            layout.addWidget(reference)

        mark_button = QPushButton("Mark read")

        mark_button.clicked.connect(
            lambda checked=False,
            notification_id=notification.id:
                self._mark_notification_read(
                    notification_id
                )
        )

        layout.addWidget(
            mark_button,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        self.content_layout.addWidget(card)

    # =========================================================
    # REMINDER ITEM
    # =========================================================

    def _add_reminder(
        self,
        reminder,
    ):

        card = QFrame()
        card.setObjectName("NotificationItem")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title = QLabel(
            reminder.title
        )

        title.setStyleSheet(
            "font-weight: 700; color: #0F172A;"
        )

        layout.addWidget(title)

        message = QLabel(
            reminder.message or
            "You have a pending deadline."
        )

        message.setWordWrap(True)
        message.setStyleSheet(
            "color: #475569; font-size: 11px;"
        )

        layout.addWidget(message)

        if reminder.due_at:

            due = QLabel(
                f"Due: {reminder.due_at}"
            )

            due.setStyleSheet(
                "color: #DC2626; font-size: 10px;"
            )

            layout.addWidget(due)

        mark_button = QPushButton("Mark read")

        mark_button.clicked.connect(
            lambda checked=False,
            reminder_id=reminder.id:
                self._mark_reminder_read(
                    reminder_id
                )
        )

        layout.addWidget(
            mark_button,
            alignment=Qt.AlignmentFlag.AlignRight,
        )

        self.content_layout.addWidget(card)

    # =========================================================
    # MARK READ
    # =========================================================

    def _mark_notification_read(
        self,
        notification_id: int,
    ):

        try:
            notification_service.mark_as_read(
                notification_id
            )
        except Exception:
            pass

        self.refresh()

    def _mark_reminder_read(
        self,
        reminder_id: int,
    ):

        try:
            notification_service.mark_reminder_as_read(
                reminder_id
            )
        except Exception:
            pass

        self.refresh()

    def mark_all_read(self):

        try:
            notification_service.mark_all_read()
        except Exception:
            pass

        try:
            reminders = (
                notification_service.get_unread_reminders()
            )

            for reminder in reminders:

                if reminder.id is not None:

                    notification_service.mark_reminder_as_read(
                        reminder.id
                    )

        except Exception:
            pass

        self.refresh()