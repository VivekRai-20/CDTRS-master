"""
busy_dialog.py — run a slow call without freezing the window.

    result = BusyDialog.run(parent, "Registering document", "Uploading...", fn)

The call runs on a worker thread while a small modal "working" card is shown,
so Windows never marks the application as "Not Responding" and the live
WebSocket connection keeps answering the server's keep-alive pings.  Any
exception raised by *fn* is re-raised in the caller, so existing error
handling keeps working unchanged.
"""

from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class _Worker(QThread):
    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.succeeded.emit(self._fn())
        except Exception as exc:  # re-raised on the GUI thread by BusyDialog.run
            self.failed.emit(exc)


class BusyDialog(QDialog):
    def __init__(
        self,
        title: str,
        message: str,
        fn: Callable[[], Any],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._result: Any = None
        self._error: Optional[BaseException] = None
        self._running = True

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        root.setContentsMargins(15, 15, 15, 15)

        card = QFrame()
        card.setObjectName("busyCard")
        card.setStyleSheet(
            "QFrame#busyCard { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 12px; }"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(15, 23, 42, 60))
        shadow.setOffset(0, 8)
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A; border: none;")
        layout.addWidget(heading)

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("font-size: 12px; color: #475569; border: none;")
        layout.addWidget(self.message_label)

        bar = QProgressBar()
        bar.setRange(0, 0)  # indeterminate
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            "QProgressBar { background-color: #E2E8F0; border: none; border-radius: 3px; }"
            "QProgressBar::chunk { background-color: #0284C7; border-radius: 3px; }"
        )
        layout.addWidget(bar)
        root.addWidget(card)

        self._worker = _Worker(fn)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_success(self, result: Any) -> None:
        self._result = result
        self._finish()

    def _on_failure(self, error: BaseException) -> None:
        self._error = error
        self._finish()

    def _finish(self) -> None:
        self._running = False
        self._worker.wait()
        self.accept()

    def reject(self) -> None:
        # Esc must not abandon a call that is still running.
        if not self._running:
            super().reject()

    @classmethod
    def run(
        cls,
        parent: Optional[QWidget],
        title: str,
        message: str,
        fn: Callable[[], Any],
    ) -> Any:
        dialog = cls(title, message, fn, parent)
        dialog.exec()
        if dialog._error is not None:
            raise dialog._error
        return dialog._result
