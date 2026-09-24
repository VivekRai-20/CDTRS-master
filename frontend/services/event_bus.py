from typing import Any, Optional
from PySide6.QtCore import QObject, Signal


class WorkflowEventBus(QObject):
    """
    Centralized reactive PySide6 EventBus for CDTRS V2.
    Broadcasts state mutations across the application without requiring polling or manual refresh buttons.
    """

    # Granular domain signals
    document_created = Signal(object)      # Emits DocumentModel
    document_updated = Signal(object)      # Emits DocumentModel
    inbox_updated = Signal()               # Emits when raw intake / inbox changes
    workflow_updated = Signal(int)         # Emits document_id
    notifications_updated = Signal()       # Emits when notification state changes

    # Universal state change signal
    data_changed = Signal()                # Emits on any repository mutation

    def __init__(self):
        super().__init__()

    def notify_document_created(self, document: Any) -> None:
        """Broadcasts document registration."""
        self.document_created.emit(document)
        self.data_changed.emit()

    def notify_document_updated(self, document: Any) -> None:
        """Broadcasts updates to a canonical document."""
        self.document_updated.emit(document)
        if hasattr(document, "id") and document.id:
            self.workflow_updated.emit(document.id)
        self.data_changed.emit()

    def notify_inbox_updated(self) -> None:
        """Broadcasts incoming dispatch / intake changes."""
        self.inbox_updated.emit()
        self.data_changed.emit()

    def notify_workflow_updated(self, document_id: int) -> None:
        """Broadcasts workflow stage / remark / assignment change."""
        self.workflow_updated.emit(document_id)
        self.data_changed.emit()

    def notify_notifications_updated(self) -> None:
        """Broadcasts new or read notifications."""
        self.notifications_updated.emit()
        self.data_changed.emit()

    def notify_data_changed(self) -> None:
        """Broadcasts universal data invalidation."""
        self.data_changed.emit()


# Global singleton event bus instance
event_bus = WorkflowEventBus()
