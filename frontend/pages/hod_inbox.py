"""HOD workspace.

Two views of the same department, because an HOD needs both:

  Workstreams   the department branches routed to them, each with its stage
  Staff Work    every individual's work item, so one person's progress is
                never hidden behind a team or a branch summary

The department shown is the one belonging to the active HOD context.  An HOD
of two departments switches context to switch department; the two never mix.
"""

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from components.branch_panel import BRANCH_STAGE_COLORS, WORK_STAGE_COLORS
from components.document_viewer import DocumentViewer
from components.routing_dialogs import AssignWorkDialog, RemarkDialog, WorkReviewDialog
from core.context.context_manager import context_manager
from models import DocumentModel, WorkItemModel
from services.document_service import document_service
from services.routing_service import routing_service
from services.work_service import work_service


class HODInboxPage(QWidget):

    view_requested = Signal(object, str)


    BRANCH_HEADERS = [
        "Reference", "Document", "Priority", "Workstream Stage",
        "Staff Assigned", "Awaiting Validation", "Deadline",
    ]
    STAFF_HEADERS = [
        "Staff", "Reference", "Document", "Team", "Stage",
        "Latest Progress", "Last Update", "Deadline", "Files",
    ]

    def __init__(self):
        super().__init__()
        self.documents: List[DocumentModel] = []
        self.branch_rows: List[tuple] = []          # (document, branch)
        self.staff_items: List[WorkItemModel] = []
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
        self.load()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        self.title = QLabel("HOD Workspace")
        self.title.setObjectName("pageTitle")
        layout.addWidget(self.title)

        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        controls = QHBoxLayout()
        controls.addStretch()
        for text, handler, primary in (
            ("Open Document", self.open_document, False),
            ("Add HOD Remark", self.add_remark, False),
            ("Assign Staff", self.assign_staff, True),
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

        self.tabs = QTabWidget()

        self.branch_table = self._make_table(self.BRANCH_HEADERS, stretch_cols=(1, 3, 4))
        self.branch_table.doubleClicked.connect(self.open_document)
        self.tabs.addTab(self.branch_table, "Workstreams")

        self.staff_table = self._make_table(self.STAFF_HEADERS, stretch_cols=(2, 5))
        self.staff_table.doubleClicked.connect(self.open_document)
        self.tabs.addTab(self.staff_table, "Staff Work")

        layout.addWidget(self.tabs, 1)

        validation_row = QHBoxLayout()
        validation_row.addStretch()
        self.accept_btn = QPushButton("Accept Selected Staff Work")
        self.accept_btn.setStyleSheet(
            "background-color: #166534; color: white; font-weight: 600; "
            "padding: 7px 15px; border-radius: 4px;"
        )
        self.accept_btn.clicked.connect(lambda: self.validate(accept=True))
        validation_row.addWidget(self.accept_btn)

        self.return_btn = QPushButton("Return for Rework")
        self.return_btn.setStyleSheet(
            "background-color: #F8FAFC; color: #B91C1C; border: 1px solid #FCA5A5; "
            "font-weight: 600; padding: 7px 15px; border-radius: 4px;"
        )
        self.return_btn.clicked.connect(lambda: self.validate(accept=False))
        validation_row.addWidget(self.return_btn)
        layout.addLayout(validation_row)

    def _make_table(self, headers, stretch_cols=()) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setWordWrap(True)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        header = table.horizontalHeader()
        for col in range(len(headers)):
            header.setSectionResizeMode(
                col,
                QHeaderView.ResizeMode.Stretch if col in stretch_cols
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        return table

    # ------------------------------------------------------------------

    def load(self) -> None:
        department_id = None
        department_name = ""
        try:
            if (context_manager.active_context_type() or "").upper() != "HOD":
                self.subtitle.setText(
                    "Switch to an HOD work context to see department workstreams."
                )
                self.branch_table.setRowCount(0)
                self.staff_table.setRowCount(0)
                return
            department_id = context_manager.active_department_id()
            department_name = context_manager.active_department_name()
        except Exception:
            pass

        try:
            self.documents = document_service.get_inbox()
        except Exception as exc:
            self.documents = []
            QMessageBox.warning(self, "HOD Workspace", f"Could not load documents.\n{exc}")

        try:
            self.staff_items = work_service.department_work_items()
        except Exception:
            self.staff_items = []

        # ---- workstreams tab ----
        self.branch_rows = []
        for doc in self.documents:
            for branch in doc.branches_for_department(department_id):
                self.branch_rows.append((doc, branch))

        self.branch_table.setRowCount(len(self.branch_rows))
        for row, (doc, branch) in enumerate(self.branch_rows):
            awaiting = sum(1 for w in branch.work_items if w.awaiting_validation)
            self._set(self.branch_table, row, 0, doc.reference)
            self._set(self.branch_table, row, 1, doc.subject or doc.title)
            self._set(self.branch_table, row, 2, str(doc.priority).title(),
                      color=doc.priority_color, bold=True)
            self._set(self.branch_table, row, 3, branch.stage_label,
                      color=BRANCH_STAGE_COLORS.get(branch.stage, "#475569"), bold=True)
            self._set(self.branch_table, row, 4,
                      ", ".join(branch.people) if branch.people else "Nobody assigned yet")
            self._set(self.branch_table, row, 5, str(awaiting) if awaiting else "-",
                      color="#7C3AED" if awaiting else None, bold=bool(awaiting))
            self._set(self.branch_table, row, 6,
                      branch.deadline or doc.deadline_display, color=doc.deadline_color)

        # ---- staff work tab: one row per PERSON ----
        live_items = [w for w in self.staff_items if not w.is_finished] or self.staff_items
        self._staff_rows = live_items
        self.staff_table.setRowCount(len(live_items))
        for row, item in enumerate(live_items):
            doc = self._document_for(item)
            self._set(self.staff_table, row, 0, item.assignee_name or "-", bold=True)
            self._set(self.staff_table, row, 1, doc.reference if doc else "-")
            self._set(self.staff_table, row, 2, (doc.subject or doc.title) if doc else "-")
            self._set(self.staff_table, row, 3, item.team_name or "-")
            self._set(self.staff_table, row, 4, item.stage_label,
                      color=WORK_STAGE_COLORS.get(item.stage, "#475569"), bold=True)
            self._set(self.staff_table, row, 5, item.progress_summary,
                      tooltip=item.latest_progress_text or "No update yet")
            self._set(self.staff_table, row, 6, item.last_update_display)
            self._set(self.staff_table, row, 7, item.deadline_display,
                      color=item.deadline_color,
                      bold=item.deadline_state in ("overdue", "due_soon"))
            self._set(self.staff_table, row, 8,
                      str(item.attachment_count) if item.attachment_count else "-")

        awaiting_total = sum(1 for w in self.staff_items if w.awaiting_validation)
        self.subtitle.setText(
            f"Department: {department_name or 'not set'}.  "
            f"{len(self.branch_rows)} workstream(s), {len(live_items)} staff work record(s)"
            + (f", {awaiting_total} awaiting your validation" if awaiting_total else "")
            + ".  Each member's work is tracked separately, even inside a team."
        )

    def _document_for(self, item: WorkItemModel):
        if item.document_id in self._doc_cache:
            return self._doc_cache[item.document_id]
        doc = next((d for d in self.documents if d.id == item.document_id), None)
        if doc is None:
            try:
                doc = document_service.get_document(item.document_id)
            except Exception:
                doc = None
        self._doc_cache[item.document_id] = doc
        return doc

    def _set(self, table, row, col, text, color=None, bold=False, tooltip=None) -> None:
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
        table.setItem(row, col, cell)

    # ------------------------------------------------------------------

    def _selected_branch(self):
        row = self.branch_table.currentRow()
        if 0 <= row < len(self.branch_rows):
            return self.branch_rows[row]
        return None, None

    def _selected_staff_item(self) -> Optional[WorkItemModel]:
        row = self.staff_table.currentRow()
        rows = getattr(self, "_staff_rows", [])
        if 0 <= row < len(rows):
            return rows[row]
        return None

    def open_document(self) -> None:
        doc = None
        if self.tabs.currentIndex() == 0:
            doc, _ = self._selected_branch()
        else:
            item = self._selected_staff_item()
            if item:
                doc = self._document_for(item)
        if doc is None:
            QMessageBox.information(self, "HOD Workspace", "Select a row first.")
            return
        self._show_document(doc, "HOD")

    def assign_staff(self) -> None:
        self.tabs.setCurrentIndex(0)
        doc, branch = self._selected_branch()
        if branch is None:
            QMessageBox.information(self, "Assign Staff", "Select a workstream first.")
            return
        dialog = AssignWorkDialog(branch, branch.department_id, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        try:
            routing_service.assign(
                branch.id,
                data["assignee_user_ids"],
                instructions=data["instructions"],
                deadline=data["deadline"],
                requires_validation=data["requires_validation"],
                team_name=data["team_name"],
            )
        except Exception as exc:
            QMessageBox.warning(self, "Assign Staff", str(exc))
            return
        QMessageBox.information(
            self, "Staff assigned",
            f"Created {len(data['assignee_user_ids'])} individual work record(s) - one per person.",
        )
        self.load()

    def add_remark(self) -> None:
        self.tabs.setCurrentIndex(0)
        doc, branch = self._selected_branch()
        if branch is None:
            QMessageBox.information(self, "HOD Remark", "Select a workstream first.")
            return
        dialog = RemarkDialog(
            f"HOD Remark - {branch.label}",
            "Your remark is appended to this workstream's record and kept permanently.",
            self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            routing_service.add_remark(branch.id, dialog.get_text())
        except Exception as exc:
            QMessageBox.warning(self, "HOD Remark", str(exc))
            return
        self.load()

    def validate(self, accept: bool) -> None:
        self.tabs.setCurrentIndex(1)
        item = self._selected_staff_item()
        if item is None:
            QMessageBox.information(self, "Validation", "Select a staff work record first.")
            return
        if not item.awaiting_validation:
            QMessageBox.information(
                self, "Validation",
                f"{item.assignee_name}'s work is not awaiting validation "
                f"(currently: {item.stage_label}).",
            )
            return
        dialog = WorkReviewDialog(item, accept_mode=accept, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            if accept:
                work_service.accept(item.id, dialog.get_note())
            else:
                work_service.return_for_rework(item.id, dialog.get_note())
        except Exception as exc:
            QMessageBox.warning(self, "Validation", str(exc))
            return
        QMessageBox.information(
            self, "Done",
            f"{item.assignee_name}'s work was "
            + ("accepted. The document stays open until the DS closes it."
               if accept else "returned for rework. Their earlier progress is kept."),
        )
        self._doc_cache.clear()
        self.load()

    def load_inbox(self) -> None:
        self.load()

    def load_documents(self) -> None:
        self.load()

    def _show_document(self, doc, role: str) -> None:
        """Hand the document to the application shell when one is hosting this
        page; otherwise open it in its own window."""
        from services.document_service import document_service as _docs

        full = _docs.get_document(doc.id) or doc
        self.view_requested.emit(full, role)

    def _on_workflow_changed(self, *_) -> None:
        """Bound method, not a lambda: Qt disconnects this when the
        widget is destroyed, so a stale page never reloads itself."""
        self.load()
