"""
ocr_splash_dialog.py — Modern Animated Splash Dialog for OCR Processing.
Provides clear visual feedback while PaddleOCR extracts text, analyzes
handwriting, and infers departmental routing.
"""

from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor, QFont

from services.ocr_service import ocr_service


class _OCRWorker(QThread):
    """Background worker running PaddleOCR off the main GUI thread."""
    result_ready = Signal(dict)
    failed = Signal(str)

    def __init__(self, file_path: str, incoming_item: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.file_path = file_path
        self.incoming_item = incoming_item

    def run(self):
        try:
            res = ocr_service.process_incoming_document(
                file_path=self.file_path,
                incoming_item=self.incoming_item,
            )
            self.result_ready.emit(res)
        except Exception as ex:
            self.failed.emit(str(ex))


class OCRSplashDialog(QDialog):
    """
    Sleek frameless splash screen displaying live OCR progress,
    animation, and step indicators while document intelligence runs.
    """

    def __init__(
        self,
        file_path: str,
        incoming_item: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.file_path = file_path
        self.incoming_item = incoming_item
        self.result: Dict[str, Any] = {}

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumSize(360, 220)
        self.setMaximumSize(640, 360)
        self.resize(480, 260)

        self._step_index = 0
        self._steps = [
            "📄 Pre-processing document pages & normalizing image...",
            "🔍 Running PaddleOCR text & handwriting recognition...",
            "🧠 Scoring department keywords & extracting structured fields...",
            "✨ Finalizing document intelligence & routing suggestions...",
        ]

        self._setup_ui()
        self._start_worker()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # Card container with dark blue header & subtle border
        self.card = QFrame()
        self.card.setObjectName("splashCard")
        self.card.setStyleSheet("""
            QFrame#splashCard {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 12px;
            }
        """)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(15, 23, 42, 60))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(12)

        # Header Row (Icon + Title)
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel("🧠")
        icon_lbl.setStyleSheet("font-size: 28px;")

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)

        title_lbl = QLabel("Document Intelligence & OCR")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #0F172A;")

        subtitle_lbl = QLabel("Analyzing document content, handwriting & routing...")
        subtitle_lbl.setStyleSheet("font-size: 12px; color: #64748B;")

        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(subtitle_lbl)
        header_row.addWidget(icon_lbl)
        header_row.addLayout(title_vbox, 1)
        card_layout.addLayout(header_row)

        card_layout.addSpacing(6)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate pulsing mode
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #E2E8F0;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284C7, stop:0.5 #0D9488, stop:1 #2563EB);
                border-radius: 3px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        # Step Status Label
        self.status_lbl = QLabel(self._steps[0])
        self.status_lbl.setStyleSheet("font-size: 12px; font-weight: 500; color: #334155; padding-top: 4px;")
        self.status_lbl.setWordWrap(True)
        card_layout.addWidget(self.status_lbl)

        # File name indicator
        fname = ""
        if self.file_path:
            import os
            fname = os.path.basename(self.file_path)
        elif self.incoming_item and self.incoming_item.get("title"):
            fname = self.incoming_item.get("title")

        if fname:
            file_badge = QLabel(f"Processing: {fname}")
            file_badge.setStyleSheet("font-size: 11px; color: #64748B; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; padding: 4px 8px;")
            card_layout.addWidget(file_badge)

        main_layout.addWidget(self.card, 1)

        # Step rotation timer for animated text feedback
        self._step_timer = QTimer(self)
        self._step_timer.timeout.connect(self._advance_step)
        self._step_timer.start(800)

    def _advance_step(self):
        self._step_index = (self._step_index + 1) % len(self._steps)
        self.status_lbl.setText(self._steps[self._step_index])

    def _start_worker(self):
        self._worker = _OCRWorker(self.file_path, self.incoming_item)
        self._worker.result_ready.connect(self._on_success)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_success(self, result: Dict[str, Any]):
        self._step_timer.stop()
        self.result = result
        # Small delay for smooth visual conclusion
        QTimer.singleShot(250, self.accept)

    def _on_failed(self, error_msg: str):
        self._step_timer.stop()
        # Create safe fallback result on failure
        title = (self.incoming_item.get("title") if self.incoming_item else "") or "Document"
        self.result = {
            "title": title,
            "extracted_text": "",
            "ocr_error": error_msg or "OCR failed",
            "confidence": 0,
            "suggested_department": None,
            "suggested_employee": None,
            "priority": "Medium",
            "deadline": "",
            "is_handwritten": False,
            "ocr_fields": {},
            "file_path": self.file_path,
        }
        QTimer.singleShot(250, self.accept)

    @classmethod
    def execute_ocr(
        cls,
        file_path: str,
        incoming_item: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ) -> Dict[str, Any]:
        """
        Convenience static helper: shows the OCR splash dialog, executes
        PaddleOCR in the background, and returns the result dictionary.
        """
        dialog = cls(file_path=file_path, incoming_item=incoming_item, parent=parent)
        dialog.exec()
        return dialog.result
