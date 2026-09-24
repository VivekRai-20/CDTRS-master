"""Documents table.

The Workstreams column is a multi-line cell listing EVERY branch with its own
stage, e.g.

    Engineering HOD: Employee Work
    Anil Kumar: Completed
    TSO: Technical Work

That is the point: a document being worked on by three groups at three
different stages reads as exactly that, instead of being flattened into one
misleading status.
"""

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from models.document import DocumentModel


class DocumentTable(QTableWidget):

    document_activated = Signal(object)

    HEADERS = [
        "Reference",
        "Title / Subject",
        "Priority",
        "Lifecycle",
        "Workstreams & Stages",
        "People Involved",
        "Deadline",
        "Last Update",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.documents: List[DocumentModel] = []

        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)

        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        self.doubleClicked.connect(self._emit_activated)

    # ------------------------------------------------------------------

    def load_documents(self, documents: List[DocumentModel]) -> None:
        self.documents = list(documents or [])
        self.setRowCount(len(self.documents))

        for row, doc in enumerate(self.documents):
            self._set(row, 0, doc.reference)
            self._set(row, 1, doc.subject or doc.title)
            self._set(row, 2, str(doc.priority).title(), color=doc.priority_color, bold=True)
            self._set(row, 3, doc.lifecycle_label, color=doc.lifecycle_color, bold=True)

            # One line per workstream, each with its own stage.
            self._set(
                row, 4,
                doc.branch_stage_cell,
                tooltip="\n".join(doc.branch_stage_lines) or "Not routed",
            )

            self._set(row, 5, doc.people_cell, tooltip=", ".join(doc.people_involved))
            self._set(
                row, 6,
                doc.deadline_display if doc.deadline else "-",
                color=doc.deadline_color,
                bold=doc.deadline_state in ("overdue", "due_soon"),
                tooltip=doc.deadline_label,
            )
            self._set(row, 7, doc.updated_display)

            # Give multi-branch rows enough height to show every line.
            lines = max(1, len(doc.branch_stage_lines))
            self.setRowHeight(row, 26 + (lines - 1) * 15)

        self.resizeColumnsToContents()
        header = self.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

    def _set(
        self,
        row: int,
        col: int,
        text: str,
        color: Optional[str] = None,
        bold: bool = False,
        tooltip: Optional[str] = None,
    ) -> None:
        item = QTableWidgetItem(str(text or "-"))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if color:
            item.setForeground(QBrush(QColor(color)))
        if bold:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        if tooltip:
            item.setToolTip(tooltip)
        self.setItem(row, col, item)

    # ------------------------------------------------------------------

    def selected_document(self) -> Optional[DocumentModel]:
        row = self.currentRow()
        if 0 <= row < len(self.documents):
            return self.documents[row]
        return None

    def _emit_activated(self) -> None:
        doc = self.selected_document()
        if doc is not None:
            self.document_activated.emit(doc)
