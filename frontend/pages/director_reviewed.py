"""Reviews the Director has already written.

Every review is listed separately, including several on the same document:
a document that came back three times shows three rows, because none of those
remarks replaced an earlier one.
"""

from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
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
from models import DirectorReviewModel
from models.document import DocumentModel
from services.document_service import document_service


class DirectorReviewedPage(QWidget):

    view_requested = Signal(object, str)


    HEADERS = ["Reference", "Document", "Review", "Remark", "Written", "Document Now"]

    def __init__(self):
        super().__init__()
        self.rows: List[Tuple[DocumentModel, DirectorReviewModel]] = []
        self.viewer: Optional[DocumentViewer] = None
        self._build()
        try:
            from services.event_bus import event_bus
            event_bus.document_updated.connect(self._on_workflow_changed)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.load()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        title = QLabel("My Reviews")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        controls = QHBoxLayout()
        controls.addStretch()
        open_btn = QPushButton("Open Document")
        open_btn.setStyleSheet(
            "background-color: #F8FAFC; color: #0F172A; border: 1px solid #CBD5E1; "
            "font-weight: 600; padding: 7px 15px; border-radius: 4px;"
        )
        open_btn.clicked.connect(self.open_document)
        controls.addWidget(open_btn)
        layout.addLayout(controls)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
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
                QHeaderView.ResizeMode.Stretch if col in (1, 3)
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        layout.addWidget(self.table, 1)

    def load(self) -> None:
        self.rows = []
        try:
            for doc in document_service.get_documents():
                full = doc
                if not doc.director_reviews and doc.id:
                    try:
                        full = document_service.get_document(doc.id) or doc
                    except Exception:
                        full = doc
                for review in full.director_reviews:
                    self.rows.append((full, review))
        except Exception as exc:
            QMessageBox.warning(self, "My Reviews", f"Could not load reviews.\n{exc}")

        self.rows.sort(key=lambda pair: pair[1].created_at or "", reverse=True)
        self.subtitle.setText(
            f"{len(self.rows)} review(s) written. Every one is kept - a document reviewed "
            "three times shows three entries here."
        )

        self.table.setRowCount(len(self.rows))
        for row, (doc, review) in enumerate(self.rows):
            self._set(row, 0, doc.reference)
            self._set(row, 1, doc.subject or doc.title)
            self._set(row, 2, f"#{review.review_no}", color="#7C3AED", bold=True)
            self._set(row, 3, review.remark_text, tooltip=review.remark_text)
            self._set(row, 4, review.created_at or "-")
            self._set(row, 5, doc.lifecycle_label, color=doc.lifecycle_color, bold=True)

    def _set(self, row, col, text, color=None, bold=False, tooltip=None) -> None:
        from PySide6.QtGui import QBrush, QColor
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

    def open_document(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self.rows)):
            QMessageBox.information(self, "My Reviews", "Select a review first.")
            return
        doc = self.rows[row][0]
        self._show_document(doc, "DIRECTOR")

    def load_documents(self) -> None:
        self.load()

    def _show_document(self, doc, role: str) -> None:
        """Hand the document to the application shell when one is hosting this
        page; otherwise open it in its own window."""
        from services.document_service import document_service as _docs

        full = _docs.get_document(doc.id) or doc
        if self.receivers(self.view_requested) > 0:
            self.view_requested.emit(full, role)
            return

        from components.document_viewer import DocumentViewer
        self.viewer = DocumentViewer(full, role=role)
        self.viewer.setWindowTitle(f"{full.reference} - {full.title}")
        self.viewer.resize(1180, 820)
        self.viewer.close_requested.connect(self.viewer.close)
        self.viewer.show()

    def _on_workflow_changed(self, *_) -> None:
        """Bound method, not a lambda: Qt disconnects this when the
        widget is destroyed, so a stale page never reloads itself."""
        self.load()
