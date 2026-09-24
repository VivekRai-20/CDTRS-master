"""Director inbox.

Documents where a review has been requested from the Director.  The Director
reads the document, the work done so far and every earlier remark, then writes
a remark and the document returns to the DS.

The Director does not close documents and does not approve them: closure is
the DS's decision, and a document can come back here as many times as the DS
needs.
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
    QVBoxLayout,
    QWidget,
)

from components.document_viewer import DocumentViewer
from components.routing_dialogs import DirectorReviewDialog
from core.context.context_manager import context_manager
from models.document import DocumentModel
from services.document_service import document_service
from services.routing_service import routing_service


class DirectorInboxPage(QWidget):

    view_requested = Signal(object, str)


    HEADERS = [
        "Reference", "Title / Subject", "Priority", "Review Round",
        "Work So Far", "Requested", "Deadline",
    ]

    def __init__(self):
        super().__init__()
        self.documents: List[DocumentModel] = []
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

        title = QLabel("Director Review")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        controls = QHBoxLayout()
        controls.addStretch()

        open_btn = QPushButton("Open & Read")
        open_btn.setStyleSheet(
            "background-color: #F8FAFC; color: #0F172A; border: 1px solid #CBD5E1; "
            "font-weight: 600; padding: 7px 15px; border-radius: 4px;"
        )
        open_btn.clicked.connect(self.open_document)
        controls.addWidget(open_btn)

        review_btn = QPushButton("Write Review Remark")
        review_btn.setStyleSheet(
            "background-color: #7C3AED; color: white; font-weight: 600; "
            "padding: 7px 15px; border-radius: 4px;"
        )
        review_btn.clicked.connect(self.write_review)
        controls.addWidget(review_btn)
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
        for col in range(len(self.HEADERS)):
            header.setSectionResizeMode(
                col,
                QHeaderView.ResizeMode.Stretch if col in (1, 4)
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        layout.addWidget(self.table, 1)

        self.empty_note = QLabel()
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setStyleSheet("color: #94A3B8; font-size: 12px; padding: 18px;")
        self.empty_note.setVisible(False)
        layout.addWidget(self.empty_note)

    # ------------------------------------------------------------------

    def load(self) -> None:
        try:
            self.documents = document_service.get_inbox()
        except Exception as exc:
            self.documents = []
            QMessageBox.warning(self, "Director Review", f"Could not load documents.\n{exc}")

        self.subtitle.setText(
            f"{len(self.documents)} document(s) awaiting your review. "
            "Read the work done so far, then record a remark - the document returns to the DS, "
            "who decides whether more work is needed or it can be closed."
        )

        self.table.setRowCount(len(self.documents))
        for row, doc in enumerate(self.documents):
            branch = doc.open_director_branch
            round_no = len(doc.director_reviews) + 1
            work_summary = (
                "; ".join(s.cell_text for s in doc.branch_summaries
                          if s.branch_type != "DIRECTOR")
                or "No work routed yet"
            )
            self._set(row, 0, doc.reference)
            self._set(row, 1, doc.subject or doc.title)
            self._set(row, 2, str(doc.priority).title(), color=doc.priority_color, bold=True)
            self._set(row, 3, f"Review #{round_no}", color="#7C3AED", bold=True)
            self._set(row, 4, work_summary, tooltip=work_summary)
            self._set(row, 5, branch.opened_at if branch else "-")
            self._set(row, 6, doc.deadline_display, color=doc.deadline_color,
                      bold=doc.deadline_state in ("overdue", "due_soon"))

        self.empty_note.setVisible(not self.documents)
        self.empty_note.setText("No documents are currently awaiting your review.")

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

    def selected_document(self) -> Optional[DocumentModel]:
        row = self.table.currentRow()
        if 0 <= row < len(self.documents):
            return self.documents[row]
        QMessageBox.information(self, "Director Review", "Select a document first.")
        return None

    def open_document(self) -> None:
        doc = self.selected_document()
        if not doc:
            return
        full = document_service.get_document(doc.id) or doc
        branch = full.open_director_branch
        if branch:
            try:
                routing_service.start_director_review(branch.id)
            except Exception:
                pass
        self._show_document(full, "DIRECTOR")

    def write_review(self) -> None:
        doc = self.selected_document()
        if not doc:
            return
        full = document_service.get_document(doc.id) or doc
        branch = full.open_director_branch
        if not branch:
            QMessageBox.information(
                self, "Director Review",
                "No review is currently requested from you on this document.",
            )
            return
        try:
            routing_service.start_director_review(branch.id)
        except Exception:
            pass

        dialog = DirectorReviewDialog(full, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        try:
            routing_service.submit_director_review(branch.id, dialog.get_text(), full.version)
        except Exception as exc:
            QMessageBox.warning(self, "Director Review", str(exc))
            return
        QMessageBox.information(
            self, "Review recorded",
            "Your remark is saved and the document has returned to the DS. "
            "It can come back to you again later if the DS requests another review.",
        )
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
