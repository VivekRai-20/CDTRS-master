from typing import Any, Dict, Optional, Set

from PySide6.QtCore import QObject, QTimer, Signal


class WorkflowEventBus(QObject):
    """
    Centralized reactive PySide6 EventBus for CDTRS V2.
    Broadcasts state mutations across the application without requiring polling or manual refresh buttons.

    Notifications are coalesced: a burst of server events (one workflow action
    usually produces several) triggers ONE refresh of each view shortly after
    the burst, instead of a reload per event.  Every reload is an HTTP call on
    the GUI thread, so reloading many times in a row froze the window.
    """

    # Granular domain signals
    document_created = Signal(object)      # Emits DocumentModel
    document_updated = Signal(object)      # Emits DocumentModel or a document id
    inbox_updated = Signal()               # Emits when raw intake / inbox changes
    workflow_updated = Signal(int)         # Emits document_id
    notifications_updated = Signal()       # Emits when notification state changes

    # Universal state change signal
    data_changed = Signal()                # Emits on any repository mutation

    #: Quiet period (ms) before a coalesced refresh is delivered.
    COALESCE_MS = 250

    def __init__(self):
        super().__init__()
        self._pending_documents: Dict[int, Any] = {}
        self._pending_workflow: Set[int] = set()
        self._pending_inbox = False
        self._pending_notifications = False
        self._pending_data = False

        self._flush_timer = QTimer(self)
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(self.COALESCE_MS)
        self._flush_timer.timeout.connect(self._flush)

    # ------------------------------------------------------------------
    # Coalescing
    # ------------------------------------------------------------------

    def _schedule(self) -> None:
        self._pending_data = True
        self._flush_timer.start()  # restarts the quiet period

    def _flush(self) -> None:
        documents = self._pending_documents
        workflow_ids = self._pending_workflow
        inbox = self._pending_inbox
        notifications = self._pending_notifications
        data = self._pending_data

        self._pending_documents = {}
        self._pending_workflow = set()
        self._pending_inbox = False
        self._pending_notifications = False
        self._pending_data = False

        for doc_id in sorted(workflow_ids | {k for k in documents if k > 0}):
            self.workflow_updated.emit(doc_id)
        if documents or workflow_ids:
            # Views reload their whole list, so one signal covers every document.
            last_key = next(reversed(documents), None) if documents else None
            payload: Optional[Any] = documents.get(last_key) if last_key is not None else None
            self.document_updated.emit(payload if payload is not None else next(iter(workflow_ids), 0))
        if inbox:
            self.inbox_updated.emit()
        if notifications:
            self.notifications_updated.emit()
        if data:
            self.data_changed.emit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def notify_document_created(self, document: Any) -> None:
        """Broadcasts document registration."""
        self.document_created.emit(document)
        self._schedule()

    def notify_document_updated(self, document: Any) -> None:
        """Broadcasts updates to a canonical document."""
        doc_id = getattr(document, "id", None)
        key = doc_id if isinstance(doc_id, int) else -1
        self._pending_documents[key] = document
        self._schedule()

    def notify_inbox_updated(self) -> None:
        """Broadcasts incoming dispatch / intake changes."""
        self._pending_inbox = True
        self._schedule()

    def notify_workflow_updated(self, document_id: int) -> None:
        """Broadcasts workflow stage / remark / assignment change."""
        try:
            self._pending_workflow.add(int(document_id))
        except (TypeError, ValueError):
            pass
        self._schedule()

    def notify_notifications_updated(self) -> None:
        """Broadcasts new or read notifications."""
        self._pending_notifications = True
        self._schedule()

    def notify_data_changed(self) -> None:
        """Broadcasts universal data invalidation."""
        self._schedule()


# Global singleton event bus instance
event_bus = WorkflowEventBus()
