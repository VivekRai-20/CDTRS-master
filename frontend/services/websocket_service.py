import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtWebSockets import QWebSocket

from config.settings import settings

logger = logging.getLogger("cdtrs.websocket")


class WebSocketService(QObject):
    """
    Real-time WebSocket client synchronization service for CDTRS.

    The backend remains authoritative. This service only receives events and
    tells the local event bus which UI/data domains need refreshing.
    """

    connection_state_changed = Signal(bool, str)
    event_received = Signal(dict)

    # Backend workflow events that require the document/inbox/notification
    # views to refresh. Team-specific events are included alongside the
    # existing assignment events.
    DOCUMENT_REFRESH_EVENTS = frozenset({
        "DOCUMENT_ROUTED",
        "REMARK_UPDATED",
        "ASSIGNMENT_CREATED",
        "ASSIGNMENT_UPDATED",
        "DS_TEAM_ASSIGNED",
        "HOD_TEAM_ASSIGNED",
        "HOD_WORK_ASSIGNED",
        "HOD_ASSIGNMENT_UPDATED",
        "HOD_TEAM_CREATED",
        "HOD_ASSIGNMENT_COMPLETED",
        "PROGRESS_SUBMITTED",
        "DOCUMENT_CLOSED",
        "OCR_COMPLETED",
        "ATTACHMENT_ADDED",
        # Event names the backend actually broadcasts (backend/main.py).
        "DIRECTOR_REVIEW_REQUESTED",
        "DIRECTOR_REMARK",
        "WORK_ASSIGNED",
        "WORK_STAGE_CHANGED",
        "PROGRESS_UPDATED",
        "WORK_SUBMITTED",
        "WORK_REVIEWED",
    })

    def __init__(self):
        super().__init__()

        self._ws: Optional[QWebSocket] = None
        self._is_connected = False
        self._should_reconnect = False

        self._reconnect_delay = 2.0
        self._max_reconnect_delay = 30.0

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_reconnect)

        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(25000)
        self._heartbeat_timer.timeout.connect(self._send_heartbeat)

    # =========================================================
    # CONNECTION
    # =========================================================

    def _build_ws_url(self) -> str:
        """Derive the WebSocket endpoint from the configured API URL."""
        base_api = settings.api_url.rstrip("/")
        parsed = urlparse(base_api)

        scheme = "wss" if parsed.scheme == "https" else "ws"
        netloc = parsed.netloc
        path = parsed.path

        ws_path = path if path.endswith("/ws") else f"{path}/ws"
        return f"{scheme}://{netloc}{ws_path}"

    def connect_client(self) -> None:
        """Establish a WebSocket connection when API mode is enabled."""
        if not settings.is_api_mode:
            return

        if self._ws is not None:
            self.disconnect_client()

        self._should_reconnect = True
        self._ws = QWebSocket()

        self._ws.connected.connect(self._on_connected)
        self._ws.textMessageReceived.connect(self._on_text_message)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.errorOccurred.connect(self._on_error)

        ws_url = self._build_ws_url()
        logger.info("Connecting to WebSocket: %s", ws_url)

        self.connection_state_changed.emit(False, "Connecting...")
        self._ws.open(QUrl(ws_url))

    def disconnect_client(self) -> None:
        """Cleanly terminate the connection and disable reconnects."""
        self._should_reconnect = False
        self._reconnect_timer.stop()
        self._heartbeat_timer.stop()
        self._reconnect_delay = 2.0

        if self._ws is not None:
            try:
                self._ws.connected.disconnect(self._on_connected)
                self._ws.textMessageReceived.disconnect(self._on_text_message)
                self._ws.disconnected.disconnect(self._on_disconnected)
                self._ws.errorOccurred.disconnect(self._on_error)
            except Exception:
                pass

            self._ws.close()
            self._ws.deleteLater()
            self._ws = None

        self._is_connected = False
        self.connection_state_changed.emit(False, "Disconnected")

    def is_connected(self) -> bool:
        return self._is_connected

    # =========================================================
    # SOCKET HANDLERS
    # =========================================================

    def _on_connected(self) -> None:
        logger.info("WebSocket connected successfully.")

        self._is_connected = True
        self._reconnect_delay = 2.0
        self._heartbeat_timer.start()

        self.connection_state_changed.emit(True, "Live Connected")

    def _on_disconnected(self) -> None:
        logger.info("WebSocket disconnected.")

        self._is_connected = False
        self._heartbeat_timer.stop()
        self.connection_state_changed.emit(False, "Disconnected")

        if self._should_reconnect and settings.is_api_mode:
            logger.info(
                "Scheduling reconnect in %.1fs...",
                self._reconnect_delay,
            )
            self._reconnect_timer.start(
                int(self._reconnect_delay * 1000)
            )
            self._reconnect_delay = min(
                self._reconnect_delay * 1.5,
                self._max_reconnect_delay,
            )

    def _on_error(self, error_code: Any) -> None:
        err_msg = self._ws.errorString() if self._ws else str(error_code)
        logger.warning("WebSocket error: %s", err_msg)
        # The connection is re-established automatically (see
        # _on_disconnected); tell the user that instead of a raw socket error.
        if self._should_reconnect:
            status = "Live updates reconnecting..."
        else:
            status = f"Live updates unavailable: {err_msg}"
        self.connection_state_changed.emit(False, status)

    def _send_heartbeat(self) -> None:
        if self._ws and self._is_connected:
            try:
                self._ws.sendTextMessage(json.dumps({"type": "ping"}))
            except Exception:
                pass

    def _do_reconnect(self) -> None:
        if self._should_reconnect and settings.is_api_mode:
            self.connect_client()

    # =========================================================
    # EVENT DISPATCH
    # =========================================================

    def _on_text_message(self, message_text: str) -> None:
        try:
            data = json.loads(message_text)
        except Exception:
            logger.warning("Ignoring invalid WebSocket JSON message.")
            return

        if not isinstance(data, dict):
            return

        self.event_received.emit(data)
        self._dispatch_event_to_bus(data)

    def _dispatch_event_to_bus(self, data: Dict[str, Any]) -> None:
        """
        Translate backend events into lightweight local refresh signals.

        No workflow mutation happens here. Team events are handled exactly
        like other assignment/workflow events.
        """
        event_type = str(data.get("event_type", "")).upper()
        doc_id = data.get("document_id")

        if not event_type or event_type in ("PING", "PONG", "HEARTBEAT"):
            return

        from services.event_bus import event_bus

        if event_type in ("DOCUMENT_CREATED", "INTAKE_REGISTERED"):
            event_bus.notify_inbox_updated()
            event_bus.notify_data_changed()
            return

        if event_type in self.DOCUMENT_REFRESH_EVENTS:
            # Views reload the document themselves (only the visible ones);
            # fetching it here too would block the window once per event.
            if doc_id:
                event_bus.notify_workflow_updated(doc_id)
            else:
                event_bus.notify_data_changed()

            event_bus.notify_inbox_updated()
            event_bus.notify_notifications_updated()
            event_bus.notify_data_changed()
            return

        if event_type in ("NOTIFICATION", "REMINDER"):
            event_bus.notify_notifications_updated()
            event_bus.notify_data_changed()
            return

        # Unknown/new backend events still cause a safe generic refresh.
        event_bus.notify_data_changed()


# Global singleton instance
websocket_service = WebSocketService()
