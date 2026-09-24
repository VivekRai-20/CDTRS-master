"""My Tasks - the worker's own assignments in the active context.

Used for both Employee and TSO contexts.  The list is strictly the caller's
own work items for the hat they are currently wearing: someone who is
Employee-Product and also TSO sees two entirely separate task lists depending
on which context is active, and TSO work never mixes in with Employee work.

Each row is ONE work item: one person, one workstream, one stage, one
deadline, and that person's own latest written update.
"""

from typing import List, Optional

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
from components.routing_dialogs import ProgressDialog, StageDialog, SubmitWorkDialog
from core.context.context_manager import context_manager
from models import WorkItemModel
from services.document_service import document_service
from services.work_service import work_service


class MyTasksPage(QWidget):

    view_requested = Signal(object, str)


    HEADERS = [
        "Reference",
        "Document",
        "Workstream",
        "My Stage",
        "Latest Progress",
        "Last Update",
        "Deadline",
        "Files",
    ]

    def __init__(self, context_label: str = "Employee"):
        super().__init__()
        self.context_label = context_label
        self.items: List[WorkItemModel] = []
        self._doc_cache = {}
        self.viewer: Optional[DocumentViewer] = None
        self._build()
        self._connect_events()

    def _connect_events(self) -> None:
        try:
            from services.event_bus import event_bus
            event_bus.document_updated.connect(self._on_workflow_changed)
        except Exception:
            pass
        try:
            context_manager.active_context_changed.connect(self._on_workflow_changed)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.load_tasks()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        self.title = QLabel(f"{self.context_label} Tasks")
        self.title.setObjectName("pageTitle")
        layout.addWidget(self.title)

        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        controls = QHBoxLayout()
        controls.setSpacing(8)

        self.scope = QComboBox()
        self.scope.addItem("My open work", False)
        self.scope.addItem("Including finished work", True)
        self.scope.currentIndexChanged.connect(self.load_tasks)
        controls.addWidget(self.scope)

        controls.addStretch()

        for text, handler, primary in (
            ("Open Document", self.open_document, False),
            ("Change Stage", self.change_stage, False),
            ("Add Progress", self.add_progress, True),
            ("Submit Work", self.submit_work, False),
        ):
            btn = QPushButton(text)
            btn.setStyleSheet(
                "background-color: #0F172A; color: white; font-weight: 600; "
                "padding: 7px 15px; border-radius: 4px;"
                if primary else
                "background-color: #F8FAFC; color: #0F172A; border: 1px solid #CBD5E1; "
                "font-weight: 600; padding: 7px 15px; border-radius: 4px;"
            )
            btn.clicked.connect(handler)
            controls.addWidget(btn)

        layout.addLayout(controls)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self.open_document)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self.table, 1)

        self.empty_note = QLabel()
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setStyleSheet("color: #94A3B8; font-size: 12px; padding: 18px;")
        self.empty_note.setVisible(False)
        layout.addWidget(self.empty_note)

    # ------------------------------------------------------------------

    def load_tasks(self) -> None:
        include_finished = bool(self.scope.currentData())
        try:
            self.items = work_service.my_work_items(include_finished=include_finished)
        except Exception as exc:
            self.items = []
            QMessageBox.warning(self, "Tasks", f"Could not load your tasks.\n{exc}")

        try:
            ctype = context_manager.active_context_type() or self.context_label
            dept = context_manager.active_department_name()
            scope = f"{ctype}" + (f" - {dept}" if dept else "")
        except Exception:
            scope = self.context_label

        overdue = sum(1 for i in self.items if i.deadline_state == "overdue" and not i.is_finished)
        returned = sum(1 for i in self.items if i.was_returned)
        self.subtitle.setText(
            f"Working as: {scope}.  {len(self.items)} assignment(s)"
            + (f", {overdue} overdue" if overdue else "")
            + (f", {returned} returned to you" if returned else "")
            + ".  Progress is written in your own words - there is no percentage."
        )

        self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            doc = self._document_for(item)
            self._set(row, 0, doc.reference if doc else "-")
            self._set(row, 1, (doc.subject or doc.title) if doc else "-")
            self._set(row, 2, item.branch_label or "-",
                      tooltip=f"Team: {item.team_name}" if item.team_name else None)
            self._set(row, 3, item.stage_label,
                      color=WORK_STAGE_COLORS.get(item.stage, "#475569"), bold=True)
            self._set(row, 4, item.progress_summary,
                      tooltip=item.latest_progress_text or "No update yet")
            self._set(row, 5, item.last_update_display)
            self._set(row, 6, item.deadline_display, color=item.deadline_color,
                      bold=item.deadline_state in ("overdue", "due_soon"))
            self._set(row, 7, str(item.attachment_count) if item.attachment_count else "-")

        self.empty_note.setVisible(not self.items)
        self.empty_note.setText(
            "You have no assignments in this work context.\n"
            "Switch context if your work is under a different hat."
        )

    def _document_for(self, item: WorkItemModel):
        if item.document_id in self._doc_cache:
            return self._doc_cache[item.document_id]
        try:
            doc = document_service.get_document(item.document_id)
        except Exception:
            doc = None
        self._doc_cache[item.document_id] = doc
        return doc

    def _set(self, row, col, text, color=None, bold=False, tooltip=None) -> None:
        cell = QTableWidgetItem(str(text or "-"))
        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        cell.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if color:
            cell.setForeground(QBrush(QColor(color)))
        if bold:
            font = cell.font()
            font.setBold(True)
            cell.setFont(font)
        if tooltip:
            cell.setToolTip(tooltip)
        self.table.setItem(row, col, cell)

    # ------------------------------------------------------------------

    def selected_item(self) -> Optional[WorkItemModel]:
        row = self.table.currentRow()
        if 0 <= row < len(self.items):
            return self.items[row]
        QMessageBox.information(self, "Tasks", "Select one of your assignments first.")
        return None

    def _after_action(self) -> None:
        self._doc_cache.clear()
        self.load_tasks()
        try:
            from services.event_bus import event_bus
            event_bus.document_updated.emit(0)
        except Exception:
            pass

    def open_document(self) -> None:
        item = self.selected_item()
        if not item:
            return
        doc = self._document_for(item)
        if not doc:
            QMessageBox.warning(self, "Tasks", "Could not open that document.")
            return
        self._show_document(doc, self.context_label.upper())

    def _show_document(self, doc, role: str) -> None:
        """Hand the document to the application shell."""
        from services.document_service import document_service as _docs

        full = _docs.get_document(doc.id) or doc
        self.view_requested.emit(full, role)

    def _on_workflow_changed(self, *_) -> None:
        """Reload tasks when workflow/context changes."""
        # Hidden pages reload in showEvent when they are opened; reloading
        # every page on each server event froze the window.
        if not self.isVisible():
            return
        self.load_tasks()

    def add_progress(self) -> None:
        item = self.selected_item()
        if not item:
            return
        if item.is_finished:
            QMessageBox.information(self, "Tasks", "This assignment is already finished.")
            return
        dialog = ProgressDialog(item, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        try:
            work_service.add_progress(
                item.id, data["description"], data["new_stage"], data["file_path"]
            )
        except Exception as exc:
            QMessageBox.warning(self, "Progress", str(exc))
            return
        QMessageBox.information(self, "Progress recorded", "Your update has been saved.")
        self._after_action()

    def change_stage(self) -> None:
        item = self.selected_item()
        if not item:
            return
        if item.is_finished:
            QMessageBox.information(self, "Tasks", "This assignment is already finished.")
            return
        dialog = StageDialog(item, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        try:
            work_service.set_stage(item.id, data["stage"], data["note"])
        except Exception as exc:
            QMessageBox.warning(self, "Stage", str(exc))
            return
        self._after_action()

    def submit_work(self) -> None:
        item = self.selected_item()
        if not item:
            return
        if item.is_finished:
            QMessageBox.information(self, "Tasks", "This assignment is already finished.")
            return
        dialog = SubmitWorkDialog(item, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            work_service.submit(item.id, dialog.get_note())
        except Exception as exc:
            QMessageBox.warning(self, "Submit", str(exc))
            return
        QMessageBox.information(
            self, "Submitted",
            "Your work has gone to your HOD for validation."
            if item.requires_validation else
            "Your assignment is complete. The DS decides when the document closes.",
        )
        self._after_action()


class EmployeeTasksPage(MyTasksPage):
    def __init__(self):
        super().__init__(context_label="Employee")


class TSOTasksPage(MyTasksPage):
    def __init__(self):
        super().__init__(context_label="TSO")

