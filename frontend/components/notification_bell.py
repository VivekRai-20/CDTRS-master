from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from services.notification_service import notification_service


class NotificationBellWidget(QWidget):
    """
    Global notification bell.

    Shows the combined unread count of:
        - workflow notifications
        - deadline reminders

    Clicking the bell opens the notification panel.
    """

    clicked = Signal()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.setup_ui()
        self.refresh()

        try:
            from services.event_bus import event_bus

            event_bus.notifications_updated.connect(
                self.refresh
            )

            event_bus.data_changed.connect(
                self.refresh
            )

        except Exception:
            pass

        try:
            from core.context.context_manager import context_manager

            context_manager.active_context_changed.connect(
                self.refresh
            )

        except Exception:
            pass

    # =========================================================
    # UI
    # =========================================================

    def setup_ui(self):

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.bell_button = QPushButton("🔔")

        self.bell_button.setFixedSize(38, 38)

        self.bell_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.bell_button.setStyleSheet(
            """
            QPushButton {
                background-color: transparent;
                border: 1px solid #E2E8F0;
                border-radius: 19px;
                font-size: 17px;
            }

            QPushButton:hover {
                background-color: #F1F5F9;
            }
            """
        )

        self.bell_button.clicked.connect(
            self._handle_click
        )

        self.badge = QLabel("0")

        self.badge.setFixedSize(18, 18)

        self.badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.badge.setStyleSheet(
            """
            QLabel {
                background-color: #E11D48;
                color: white;
                border-radius: 9px;
                font-size: 10px;
                font-weight: bold;
            }
            """
        )

        self.badge.setVisible(False)

        layout.addWidget(self.bell_button)
        layout.addWidget(self.badge)

    # =========================================================
    # REFRESH
    # =========================================================

    def refresh(self):

        try:
            count = notification_service.unread_alert_count()

            if count > 0:

                self.badge.setText(
                    str(count if count <= 99 else "99+")
                )

                self.badge.setVisible(True)

            else:

                self.badge.setVisible(False)

        except Exception:

            self.badge.setVisible(False)

    # =========================================================
    # CLICK
    # =========================================================

    def _handle_click(self):

        self.clicked.emit()