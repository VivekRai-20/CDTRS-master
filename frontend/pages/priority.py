"""Deadlines & Priority monitor.

Shows what is overdue or due soon, at BOTH levels: the document's own
deadline, and each person's work-item deadline - because a document due next
month can still contain an assignment that was due yesterday.
"""

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from components.branch_panel import WORK_STAGE_COLORS
from components.document_viewer import DocumentViewer
from models import WorkItemModel
from models.document import DocumentModel
from services.document_service import document_service
from services.notification_service import notification_service


class PriorityPage(QWidget):

    HEADERS = [
        "Reference", "Document", "Priority", "Workstream",
        "Who", "Stage", "Deadline", "Status", "Last Update",
    ]

    view_requested = Signal(object, str)

    def __init__(self):
        super().__init__()
        self.documents: List[DocumentModel] = []
        self.rows: List[Tuple[DocumentModel, Optional[WorkItemModel]]] = []
        self.viewer: Optional[DocumentViewer] = None
        self._build()
        try:
            from services.event_bus import event_bus
            event_bus.document_updated.connect(self._on_workflow_changed)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.load_documents()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        title = QLabel("Deadlines & Priority")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.scope = QComboBox()
        self.scope.addItem("Overdue and due soon", "urgent")
        self.scope.addItem("Overdue only", "overdue")
        self.scope.addItem("All open work", "all")
        self.scope.currentIndexChanged.connect(self.apply_filters)
        controls.addWidget(self.scope)

        self.priority_filter = QComboBox()
        self.priority_filter.addItem("All priorities", None)
        for value in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            self.priority_filter.addItem(value.title(), value)
        self.priority_filter.currentIndexChanged.connect(self.apply_filters)
        controls.addWidget(self.priority_filter)

        controls.addStretch()

        open_btn = QPushButton("Open Document")
        open_btn.setStyleSheet(
            "background-color: #F8FAFC; color: #0F172A; border: 1px solid #CBD5E1; "
            "font-weight: 600; padding: 7px 15px; border-radius: 4px;"
        )
        open_btn.clicked.connect(self.open_document)
        controls.addWidget(open_btn)

        remind_btn = QPushButton("Send Reminder")
        remind_btn.setStyleSheet(
            "background-color: #0F172A; color: white; font-weight: 600; "
            "padding: 7px 15px; border-radius: 4px;"
        )
        remind_btn.clicked.connect(self.send_reminder)
        controls.addWidget(remind_btn)
        layout.addLayout(controls)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self.open_document)

        header = self.table.horizontalHeader()
        for col in range(len(self.HEADERS)):
            header.setSectionResizeMode(
                col,
                QHeaderView.ResizeMode.Stretch if col in (1, 3)
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        layout.addWidget(self.table, 1)

        self.empty_note = QLabel()
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setStyleSheet("color: #94A3B8; font-size: 12px; padding: 18px;")
        self.empty_note.setVisible(False)
        layout.addWidget(self.empty_note)

    # ------------------------------------------------------------------

    def load_documents(self) -> None:
        try:
            self.documents = document_service.get_documents()
        except Exception as exc:
            self.documents = []
            QMessageBox.warning(self, "Deadlines", f"Could not load documents.\n{exc}")
        self.apply_filters()

    def apply_filters(self) -> None:
        scope = self.scope.currentData()
        priority = self.priority_filter.currentData()

        self.rows = []
        for doc in self.documents:
            if doc.is_closed:
                continue
            if priority and str(doc.priority).upper() != priority:
                continue

            open_items = [w for w in doc.all_work_items if not w.is_finished]
            if open_items:
                for item in open_items:
                    if scope == "overdue" and item.deadline_state != "overdue":
                        continue
                    if scope == "urgent" and item.deadline_state not in ("overdue", "due_soon"):
                        continue
                    self.rows.append((doc, item))
            else:
                # Not yet routed: judge the document's own deadline instead.
                if scope == "overdue" and doc.deadline_state != "overdue":
                    continue
                if scope == "urgent" and doc.deadline_state not in ("overdue", "due_soon"):
                    continue
                self.rows.append((doc, None))

        overdue = sum(
            1 for d, i in self.rows
            if (i.deadline_state if i else d.deadline_state) == "overdue"
        )
        self.subtitle.setText(
            f"{len(self.rows)} item(s), {overdue} overdue. "
            "Each row is one person's deadline where work has been assigned, "
            "otherwise the document's own deadline."
        )

        self.table.setRowCount(len(self.rows))
        for row, (doc, item) in enumerate(self.rows):
            state = item.deadline_state if item else doc.deadline_state
            color = item.deadline_color if item else doc.deadline_color
            label = {
                "overdue": "Overdue", "due_soon": "Due soon",
                "on_track": "On track", "none": "No deadline",
            }.get(state, "")

            self._set(row, 0, doc.reference)
            self._set(row, 1, doc.subject or doc.title)
            self._set(row, 2, str(doc.priority).title(), color=doc.priority_color, bold=True)
            self._set(row, 3, (item.branch_label if item else None) or "Not routed")
            self._set(row, 4, (item.assignee_name if item else None) or "-")
            if item:
                self._set(row, 5, item.stage_label,
                          color=WORK_STAGE_COLORS.get(item.stage, "#475569"), bold=True)
            else:
                self._set(row, 5, doc.lifecycle_label, color=doc.lifecycle_color, bold=True)
            self._set(row, 6, item.deadline_display if item else doc.deadline_display,
                      color=color, bold=state in ("overdue", "due_soon"))
            self._set(row, 7, label, color=color, bold=state == "overdue")
            self._set(row, 8, item.last_update_display if item else doc.updated_display)

        self.empty_note.setVisible(not self.rows)
        self.empty_note.setText("Nothing is overdue or due soon.")

    def _set(self, row, col, text, color=None, bold=False) -> None:
        cell = QTableWidgetItem(str(text or "-"))
        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        cell.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if color:
            cell.setForeground(QBrush(QColor(color)))
        if bold:
            font = cell.font()
            font.setBold(True)
            cell.setFont(font)
        self.table.setItem(row, col, cell)

    # ------------------------------------------------------------------

    def _selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.rows):
            return self.rows[row]
        QMessageBox.information(self, "Deadlines", "Select a row first.")
        return None, None

    def open_document(self) -> None:
        doc, _ = self._selected()
        if doc is None:
            return
        full = document_service.get_document(doc.id) or doc
        self.viewer = DocumentViewer(full)
        self.viewer.setWindowTitle(f"{full.reference} - {full.title}")
        self.viewer.resize(1180, 820)
        self.viewer.document_changed.connect(lambda *_: self.load_documents())
        self.viewer.show()

    def send_reminder(self) -> None:
        doc, item = self._selected()
        if doc is None:
            return
        if item is None:
            QMessageBox.information(
                self, "Send Reminder",
                "This document has no assigned work yet, so there is nobody to remind. "
                "Route it first.",
            )
            return
        try:
            notification_service.send_reminder(doc.id, work_item_id=item.id)
        except Exception as exc:
            QMessageBox.warning(self, "Send Reminder", str(exc))
            return
        QMessageBox.information(
            self, "Reminder sent", f"{item.assignee_name} has been reminded."
        )

    def _on_workflow_changed(self, *_) -> None:
        """Bound method, not a lambda: Qt disconnects this when the
        widget is destroyed, so a stale page never reloads itself."""
        self.load_documents()
