"""Document details panel.

Shows what the document IS, not what is happening to it.  Who is working on
it, at what stage, lives in the Workstreams section, because a document with
three branches at three different stages cannot be described by one field
here.
"""

from typing import Optional

from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

from models.document import DocumentModel
from models.enums import IngestionModeEnum


class DocumentInfo(QFrame):
    def __init__(self, document: Optional[DocumentModel] = None):
        super().__init__()
        self.document = document or DocumentModel()
        self.setObjectName("contentCard")
        self._value_labels = {}
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel("Document Details")
        title.setObjectName("sectionTitle")
        title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        layout.addWidget(title)

        self.form = QFormLayout()
        self.form.setSpacing(6)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(self.form)

        for key, label in (
            ("reference", "Reference"),
            ("subject", "Subject"),
            ("sender", "Sender"),
            ("sender_reference", "Sender Reference"),
            ("source", "Source"),
            ("mode", "Received Via"),
            ("received", "Received"),
            ("deadline", "Deadline"),
            ("priority", "Priority"),
            ("lifecycle", "Lifecycle"),
            ("workstreams", "Workstreams"),
            ("people", "People Involved"),
            ("ocr", "Extraction"),
        ):
            value = QLabel("-")
            value.setWordWrap(True)
            value.setStyleSheet("color: #1E293B; font-size: 11px;")
            self._value_labels[key] = value
            self.form.addRow(self._field_label(label), value)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self.update_document(self.document)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 600;")
        return label

    def update_document(self, document: Optional[DocumentModel]) -> None:
        doc = document or DocumentModel()
        self.document = doc

        values = {
            "reference": doc.reference,
            "subject": doc.subject or doc.title or "-",
            "sender": doc.sender_name or "-",
            "sender_reference": doc.sender_reference or "-",
            "source": doc.source or "-",
            "mode": IngestionModeEnum.label(doc.mode),
            "received": doc.received_display,
            "deadline": (
                f"{doc.deadline_display}  ({doc.deadline_label})"
                if doc.deadline else "Not set"
            ),
            "priority": str(doc.priority).title(),
            "lifecycle": doc.lifecycle_label,
            "workstreams": doc.workstream_summary,
            "people": doc.people_cell,
            "ocr": (doc.ocr_status or "NONE").title(),
        }

        for key, text in values.items():
            label = self._value_labels.get(key)
            if label is None:
                continue
            label.setText(str(text))

        # Colour the two fields where urgency matters.
        self._value_labels["deadline"].setStyleSheet(
            f"color: {doc.deadline_color}; font-size: 11px; font-weight: 600;"
        )
        self._value_labels["lifecycle"].setStyleSheet(
            f"color: {doc.lifecycle_color}; font-size: 11px; font-weight: 700;"
        )
        self._value_labels["priority"].setStyleSheet(
            f"color: {doc.priority_color}; font-size: 11px; font-weight: 600;"
        )

    # Backwards-compatible alias used by some callers.
    def set_document(self, document: Optional[DocumentModel]) -> None:
        self.update_document(document)
