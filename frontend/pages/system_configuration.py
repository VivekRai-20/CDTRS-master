from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QTextEdit, QLineEdit, QVBoxLayout, QWidget
)

from api.client import api_client


DEFAULTS = {
    "priority_red_days": 0,
    "priority_orange_days": 3,
    "priority_yellow_days": 7,
    "reminder_email_subject": "ACTION REQUIRED: CDTRS Document Reminder - {reference}",
    "reminder_email_template": (
        "Dear {assignee_name},\n\n"
        "This is an automated reminder regarding document '{title}' "
        "(Ref: {reference}).\n"
        "Deadline: {deadline} ({days_left} remaining).\n\n"
        "Please review and take necessary action.\n\n"
        "CDTRS Automated Dispatch System"
    ),
}


class SystemConfigurationPage(QWidget):
    """AdminSuite's actual priority and reminder-email configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("systemConfigurationPage")

        title = QLabel("System Configuration")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Configure the priority countdown thresholds and automated document "
            "reminder email template used by CDTRS."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        priority_group = QGroupBox("Priority Countdown Thresholds")
        priority_form = QFormLayout(priority_group)
        priority_form.setSpacing(12)

        self.red = QSpinBox()
        self.red.setRange(-30, 30)
        self.orange = QSpinBox()
        self.orange.setRange(-30, 60)
        self.yellow = QSpinBox()
        self.yellow.setRange(-30, 120)

        priority_form.addRow("Red / Urgent — days left <=", self.red)
        priority_form.addRow("Orange / High — days left <=", self.orange)
        priority_form.addRow("Yellow / Medium — days left <=", self.yellow)

        help_text = QLabel(
            "The lower the number of days remaining, the more urgent the document. "
            "These values control the dynamic priority countdown."
        )
        help_text.setObjectName("muted")
        help_text.setWordWrap(True)

        email_group = QGroupBox("Action Reminder Email Template")
        email_form = QFormLayout(email_group)
        email_form.setSpacing(12)

        self.subject = QLineEdit()
        self.body = QTextEdit()
        self.body.setMinimumHeight(180)

        email_form.addRow("Email Subject", self.subject)
        email_form.addRow("Email Body", self.body)

        placeholders = QLabel(
            "Available placeholders:  {assignee_name}   {title}   {reference}   "
            "{deadline}   {days_left}"
        )
        placeholders.setObjectName("muted")
        placeholders.setWordWrap(True)

        reset = QPushButton("Reset Defaults")
        reset.clicked.connect(self._reset_defaults)

        save = QPushButton("Save Configuration")
        save.setObjectName("primaryButton")
        save.clicked.connect(self._save)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(reset)
        actions.addWidget(save)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(priority_group)
        layout.addWidget(help_text)
        layout.addWidget(email_group)
        layout.addWidget(placeholders)
        layout.addLayout(actions)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

        self.setStyleSheet("""
            QWidget#systemConfigurationPage { background: #f6f8fb; }
            QLabel#pageTitle { font-size: 23px; font-weight: 750; color: #172033; }
            QLabel#muted { color: #667085; }
            QGroupBox {
                background: white; border: 1px solid #e4e7ec; border-radius: 10px;
                margin-top: 10px; padding: 14px; font-weight: 700;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
            QLineEdit, QSpinBox, QTextEdit {
                background: white; border: 1px solid #d0d5dd; border-radius: 8px;
                padding: 6px;
            }
            
            
            QPushButton#primaryButton { background: #2563eb; color: white; border-color: #2563eb; font-weight: 650; }
        """)

        self._reset_defaults()
        self.load_settings()

    def _reset_defaults(self):
        self.red.setValue(DEFAULTS["priority_red_days"])
        self.orange.setValue(DEFAULTS["priority_orange_days"])
        self.yellow.setValue(DEFAULTS["priority_yellow_days"])
        self.subject.setText(DEFAULTS["reminder_email_subject"])
        self.body.setPlainText(DEFAULTS["reminder_email_template"])

    def load_settings(self):
        try:
            data = api_client.get("/admin/settings")
            if not isinstance(data, dict):
                return
            self.red.setValue(int(data.get("priority_red_days", DEFAULTS["priority_red_days"])))
            self.orange.setValue(int(data.get("priority_orange_days", DEFAULTS["priority_orange_days"])))
            self.yellow.setValue(int(data.get("priority_yellow_days", DEFAULTS["priority_yellow_days"])))
            self.subject.setText(
                str(data.get("reminder_email_subject", DEFAULTS["reminder_email_subject"]))
            )
            self.body.setPlainText(
                str(data.get("reminder_email_template", DEFAULTS["reminder_email_template"]))
            )
        except Exception as exc:
            QMessageBox.warning(self, "System Configuration", f"Unable to load settings.\n\n{exc}")

    def _save(self):
        if self.red.value() > self.orange.value() or self.orange.value() > self.yellow.value():
            QMessageBox.warning(
                self, "Invalid Thresholds",
                "Thresholds should be ordered Red <= Orange <= Yellow."
            )
            return

        payload: Dict[str, Any] = {
            "priority_red_days": str(self.red.value()),
            "priority_orange_days": str(self.orange.value()),
            "priority_yellow_days": str(self.yellow.value()),
            "reminder_email_subject": self.subject.text().strip(),
            "reminder_email_template": self.body.toPlainText().strip(),
        }

        try:
            api_client.post("/admin/settings", json=payload)
            QMessageBox.information(
                self, "Saved", "System configuration saved successfully."
            )
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))


AdminSystemConfigurationPage = SystemConfigurationPage
