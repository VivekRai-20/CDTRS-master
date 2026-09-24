from typing import Any, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QCursor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from api.client import api_client

class StatCard(QFrame):
    def __init__(self, title: str, note: str, icon: str, icon_color: str, icon_bg: str, parent=None):
        super().__init__(parent)
        self.setObjectName("statCard")

        # Icon on the left
        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"background: {icon_bg}; color: {icon_color}; font-size: 20px; border-radius: 12px; min-width: 40px; min-height: 40px; max-width: 40px; max-height: 40px;")

        # Text on the right
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("statTitle")

        self.value_label = QLabel("0")
        self.value_label.setObjectName("statValue")

        note_label = QLabel(note)
        note_label.setObjectName("statNote")
        note_label.setWordWrap(True)

        text_layout.addWidget(title_label)
        text_layout.addWidget(self.value_label)
        text_layout.addWidget(note_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)
        layout.addWidget(icon_lbl)
        layout.addLayout(text_layout)
        layout.addStretch()

    def set_value(self, value: Any) -> None:
        self.value_label.setText(str(value))

class AdminDashboardPage(QWidget):
    navigate_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("adminDashboardPage")

        # Top layout
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        
        title = QLabel("Administration")
        title.setObjectName("pageTitle")
        
        subtitle = QLabel("Manage users, work contexts, departments, system configuration, and the administrator audit history.")
        subtitle.setObjectName("mutedSubtitle")
        subtitle.setWordWrap(True)
        
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        right_box = QHBoxLayout()
        right_box.setSpacing(12)
        
        self.status_lbl = QLabel("Updated\nJust now")
        self.status_lbl.setObjectName("statusLabel")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        refresh = QPushButton("↻ Refresh")
        refresh.setObjectName("primaryButton")
        refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh.clicked.connect(self.load_dashboard)
        
        right_box.addWidget(self.status_lbl)
        right_box.addWidget(refresh)
        
        header.addLayout(right_box)

        # Stat cards
        self.users_card = StatCard("USERS", "Configured application accounts", "👥", "#2563eb", "#eff6ff")
        self.active_users_card = StatCard("ACTIVE USERS", "Accounts currently enabled", "👤", "#16a34a", "#f0fdf4")
        self.departments_card = StatCard("DEPARTMENTS", "Configured organisational units", "🏢", "#7c3aed", "#f3e8ff")
        self.audit_card = StatCard("ADMIN AUDIT", "Recorded administrator changes", "📄", "#ea580c", "#fff7ed")

        cards = QHBoxLayout()
        cards.setSpacing(16)
        cards.addWidget(self.users_card, 1)
        cards.addWidget(self.active_users_card, 1)
        cards.addWidget(self.departments_card, 1)
        cards.addWidget(self.audit_card, 1)

        # Recent changes title
        activity_title_layout = QHBoxLayout()
        icon_clock = QLabel("🕒")
        icon_clock.setStyleSheet("font-size: 18px; color: #2563eb;")
        activity_title = QLabel("Recent administrator changes")
        activity_title.setObjectName("sectionTitle")
        activity_title_layout.addWidget(icon_clock)
        activity_title_layout.addWidget(activity_title)
        activity_title_layout.addStretch()

        self.activity_box = QWidget()
        self.activity_layout = QVBoxLayout(self.activity_box)
        self.activity_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_layout.setSpacing(12)

        activity_scroll = QScrollArea()
        activity_scroll.setWidgetResizable(True)
        activity_scroll.setFrameShape(QFrame.Shape.NoFrame)
        activity_scroll.setWidget(self.activity_box)
        activity_scroll.setStyleSheet("background: transparent;")
        activity_scroll.setMinimumHeight(300)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(32, 32, 32, 32)
        content_layout.setSpacing(24)
        content_layout.addLayout(header)
        content_layout.addLayout(cards)
        content_layout.addLayout(activity_title_layout)
        content_layout.addWidget(activity_scroll, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(content)

        self.setStyleSheet('''
            QWidget#adminDashboardPage { background: #f8fafc; }
            QLabel#pageTitle { font-size: 22px; font-weight: 800; color: #0f172a; }
            QLabel#mutedSubtitle { color: #64748b; font-size: 14px; }
            QLabel#sectionTitle { font-size: 16px; font-weight: 750; color: #0f172a; }
            QLabel#statusLabel { color: #64748b; font-size: 11px; }
            
            QFrame#statCard { background: white; border: 1px solid #bfdbfe; border-radius: 10px; }
            QLabel#statTitle { color: #475569; font-size: 11px; font-weight: 700; }
            QLabel#statValue { color: #0f172a; font-size: 22px; font-weight: 800; }
            QLabel#statNote { color: #64748b; font-size: 11px; }
            
            QPushButton#primaryButton { background: #3b82f6; color: white; border-radius: 8px; font-weight: 600; padding: 10px 20px; font-size: 14px; }
            QPushButton#primaryButton:hover { background: #2563eb; }
            
            QFrame#activityItem { background: white; border: 1px solid #e2e8f0; border-radius: 12px; }
        ''')

        self.load_dashboard()

    @staticmethod
    def _as_list(data: Any, *keys: str) -> List[Dict[str, Any]]:
        if isinstance(data, list): return data
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, list): return value
        return []

    def load_dashboard(self) -> None:
        try:
            users = self._as_list(api_client.get("/admin/users"), "users", "items")
            departments = self._as_list(api_client.get("/admin/departments"), "departments", "items")
            audit = self._as_list(api_client.get("/admin/audit-logs"), "audit_logs", "logs", "items")

            self.users_card.set_value(len(users))
            self.active_users_card.set_value(sum(bool(u.get("is_active", True)) for u in users))
            self.departments_card.set_value(len(departments))
            self.audit_card.set_value(len(audit))

            from datetime import datetime
            now = datetime.now().strftime("%d %b %Y, %H:%M")
            self.status_lbl.setText(f"Updated\n{now}")

            self._render_activity(audit[:8])
        except Exception as exc:
            self.status_lbl.setText("Unable to load")
            self._render_activity([])
            QMessageBox.warning(self, "Admin Dashboard", f"Unable to load administrator data.\n\n{exc}")

    def _render_activity(self, rows: List[Dict[str, Any]]) -> None:
        while self.activity_layout.count():
            item = self.activity_layout.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater()

        if not rows:
            label = QLabel("No administrator changes have been recorded.")
            label.setStyleSheet("color: #64748b;")
            self.activity_layout.addWidget(label)
            self.activity_layout.addStretch(1)
            return

        for row in rows:
            card = QFrame()
            card.setObjectName("activityItem")

            action = str(row.get("action") or "ADMIN ACTION")
            actor = str(row.get("username") or row.get("user_name") or "Unknown admin")
            target_type = str(row.get('entity_type') or 'System')
            target_id = row.get('entity_id')
            if target_type.lower() == 'user': target_type = 'User Account'
            elif target_type.lower() == 'department': target_type = 'Department'
            
            target = target_type
            if target_id is not None: target += f" #{target_id}"
            
            details = str(row.get("description") or row.get("details") or "")
            timestamp_raw = str(row.get("created_at") or "")
            
            # Format timestamp roughly like mockup
            if "T" in timestamp_raw:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp_raw.split(".")[0])
                    timestamp_fmt = dt.strftime("%d %b %Y, %H:%M")
                except:
                    timestamp_fmt = timestamp_raw
            else:
                timestamp_fmt = timestamp_raw

            layout = QHBoxLayout(card)
            layout.setContentsMargins(20, 16, 20, 16)
            layout.setSpacing(12)
            
            icon_lbl = QLabel("📄")
            icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_lbl.setStyleSheet("background: #eff6ff; color: #3b82f6; font-size: 20px; border-radius: 12px; min-width: 40px; min-height: 40px; max-width: 40px; max-height: 40px; border: none;")

            text_layout = QVBoxLayout()
            text_layout.setSpacing(4)

            headline = QLabel(f"{action.upper()}  •  {actor}")
            headline.setStyleSheet("font-weight: 750; color: #0f172a; font-size: 13px; border: none;")
            
            meta = QLabel(f"{target}    {timestamp_raw}")
            meta.setStyleSheet("color: #64748b; font-size: 12px; border: none;")
            
            text_layout.addWidget(headline)
            text_layout.addWidget(meta)
            
            if details:
                body = QLabel(details)
                body.setStyleSheet("color: #64748b; font-size: 13px; border: none;")
                body.setWordWrap(True)
                text_layout.addWidget(body)

            time_lbl = QLabel(timestamp_fmt)
            time_lbl.setStyleSheet("color: #64748b; font-size: 12px; border: none;")
            time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

            layout.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
            layout.addLayout(text_layout, 1)
            layout.addWidget(time_lbl, 0, Qt.AlignmentFlag.AlignTop)

            self.activity_layout.addWidget(card)

        self.activity_layout.addStretch(1)

AdminDashboard = AdminDashboardPage
