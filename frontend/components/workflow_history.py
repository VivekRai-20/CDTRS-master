"""Workflow history card wrapper."""

from typing import List, Optional

from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

from components.history_table import HistoryTable
from models import WorkflowEventModel


class WorkflowHistory(QFrame):
    """The document's complete chronological record, workstream-tagged."""

    def __init__(self, history: Optional[List[WorkflowEventModel]] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("contentCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)

        title = QLabel("Workflow History")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        hint = QLabel(
            "Every routing decision, assignment, progress update, remark, validation "
            "and stage change, in order."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748B; font-size: 10px;")
        layout.addWidget(hint)

        self.table = HistoryTable()
        layout.addWidget(self.table)

        self.load_history(history or [])

    def load_history(self, history: List[WorkflowEventModel]) -> None:
        self.table.load_history(history)

    # Alias kept for older callers.
    def update_history(self, history: List[WorkflowEventModel]) -> None:
        self.load_history(history)
