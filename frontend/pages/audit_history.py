from __future__ import annotations

from typing import Any, Dict, List

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget
)

from api.client import api_client


class AuditHistoryPage(QWidget):
    """
    Single administrator audit page.

    It records important changes made by Admin to users, contexts,
    departments and system configuration. It is read-only.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("auditHistoryPage")
        self.rows: List[Dict[str, Any]] = []

        title = QLabel("Audit History")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Read-only history of important changes performed by administrators "
            "to the CDTRS system."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search admin, action, target or details…")
        self.search.textChanged.connect(self._render)

        self.action_filter = QComboBox()
        self.action_filter.addItem("All Actions", "")
        self.action_filter.currentIndexChanged.connect(self._render)

        self.from_date = QDateEdit()
        self.from_date.setCalendarPopup(True)
        self.from_date.setDisplayFormat("dd MMM yyyy")
        self.from_date.setDate(QDate.currentDate().addDays(-30))
        self.from_date.dateChanged.connect(self._render)

        self.to_date = QDateEdit()
        self.to_date.setCalendarPopup(True)
        self.to_date.setDisplayFormat("dd MMM yyyy")
        self.to_date.setDate(QDate.currentDate())
        self.to_date.dateChanged.connect(self._render)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.load_history)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.action_filter)
        toolbar.addWidget(QLabel("From"))
        toolbar.addWidget(self.from_date)
        toolbar.addWidget(QLabel("To"))
        toolbar.addWidget(self.to_date)
        toolbar.addWidget(refresh)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Time", "Administrator", "Action", "Target", "Details"]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 165)
        self.table.setColumnWidth(1, 145)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 180)

        card = QFrame()
        card.setObjectName("tableCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 10, 10, 10)
        card_layout.addWidget(self.table)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(11)
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addLayout(toolbar)
        root.addWidget(card, 1)

        self.setStyleSheet("""
            QWidget#auditHistoryPage { background: #f6f8fb; }
            QLabel#pageTitle { font-size: 23px; font-weight: 750; color: #172033; }
            QLabel#muted { color: #667085; }
            QLineEdit, QComboBox, QDateEdit {
                min-height: 35px; background: white; border: 1px solid #d0d5dd;
                border-radius: 8px; padding: 0 8px;
            }
            
            
            QFrame#tableCard {
                background: white; border: 1px solid #e4e7ec; border-radius: 10px;
            }
            QTableWidget {
                background: white; border: none; gridline-color: #eaecf0;
            }
            QHeaderView::section {
                background: #f8fafc; border: none; border-bottom: 1px solid #e4e7ec;
                padding: 8px; font-weight: 700;
            }
        """)

        self.load_history()

    def load_history(self):
        try:
            data = api_client.get("/admin/audit-logs")
            if isinstance(data, list):
                self.rows = data
            elif isinstance(data, dict):
                self.rows = (
                    data.get("audit_logs")
                    or data.get("logs")
                    or data.get("items")
                    or []
                )
            else:
                self.rows = []

            self._populate_action_filter()
            self._render()
        except Exception as exc:
            self.rows = []
            self._render()
            QMessageBox.warning(
                self, "Audit History",
                f"Unable to load administrator audit history.\n\n{exc}"
            )

    def _populate_action_filter(self):
        current = self.action_filter.currentData()
        values = sorted({
            str(row.get("action") or "")
            for row in self.rows
            if row.get("action")
        })

        self.action_filter.blockSignals(True)
        self.action_filter.clear()
        self.action_filter.addItem("All Actions", "")
        for value in values:
            self.action_filter.addItem(value, value)
        idx = self.action_filter.findData(current)
        if idx >= 0:
            self.action_filter.setCurrentIndex(idx)
        self.action_filter.blockSignals(False)

    def _render(self):
        query = self.search.text().strip().lower()
        action = self.action_filter.currentData() or ""
        
        from_date_py = self.from_date.date().toString("yyyy-MM-dd")
        to_date_py = self.to_date.date().toString("yyyy-MM-dd")

        rows = []
        for row in self.rows:
            created_at = str(row.get("created_at") or "")
            if created_at:
                date_part = created_at.split("T")[0].split(" ")[0]
                if date_part < from_date_py or date_part > to_date_py:
                    continue
                    
            actor = str(row.get("username") or row.get("user_name") or "").lower()
            action_value = str(row.get("action") or "")
            target = (
                f"{row.get('entity_type') or ''} "
                f"{row.get('entity_id') or ''}"
            ).lower()
            details = str(row.get("description") or row.get("details") or "").lower()

            if query and query not in " ".join([actor, action_value.lower(), target, details]):
                continue
            if action and action_value != action:
                continue

            rows.append(row)

        self.table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            timestamp = str(row.get("created_at") or "—")
            actor = str(row.get("username") or row.get("user_name") or "Unknown admin")
            action_value = str(row.get("action") or "—")
            target_type = str(row.get('entity_type') or 'System')
            target_id = row.get('entity_id')
            if target_type.lower() == 'user':
                target_type = 'User Account'
            elif target_type.lower() == 'department':
                target_type = 'Department'
            
            target = target_type
            if target_id is not None:
                target += f" #{target_id}"
            details = str(row.get("description") or row.get("details") or "—")

            values = [timestamp, actor, action_value, target, details]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(r, c, item)

        self.table.resizeRowsToContents()


AdminAuditHistoryPage = AuditHistoryPage
