"""Workflow history table.

Every event carries the workstream it belongs to, so the same table answers
"what happened to this document" and "what happened on the Engineering
branch" without needing a second view.
"""

from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from models import WorkflowEventModel


class HistoryTable(QTableWidget):

    HEADERS = ["When", "Workstream", "Who", "Context", "What Happened", "Detail"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.history: List[WorkflowEventModel] = []

        self.setColumnCount(len(self.HEADERS))
        self.setHorizontalHeaderLabels(self.HEADERS)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setWordWrap(True)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)

        header = self.horizontalHeader()
        for col in range(4):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

    def load_history(self, events: List[WorkflowEventModel]) -> None:
        self.history = list(events or [])
        self.setRowCount(len(self.history))
        for row, event in enumerate(self.history):
            self._set(row, 0, event.when)
            self._set(row, 1, event.scope)
            self._set(row, 2, event.actor_name)
            self._set(row, 3, event.actor_context_type or "-")
            self._set(row, 4, event.summary)
            self._set(row, 5, event.details or "-")

    def _set(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(str(text or "-"))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, col, item)
