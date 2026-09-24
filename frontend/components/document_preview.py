# ==============================================================================
# PZ_26/08 - Hardware-Accelerated In-App Document Previewer (QPdfView / QPdfDocument)
# Renders PDF documents, scanned images, and intake email dispatches with zoom & fit controls
# ==============================================================================

import os
from typing import Any, Dict, Optional, Union

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap, QImage, QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView

    HAS_QT_PDF = True
except ImportError:
    HAS_QT_PDF = False

from models.document import DocumentModel
from services.attachment_service import attachment_service


class DocumentPreview(QFrame):
    """
    Production In-App Document Preview Widget for CDTRS.

    Supports:
    - PDF documents
    - Scanned images
    - Text files
    - Intake/email dispatch bodies
    - On-demand attachment download
    - Local preview caching
    - PDF zoom controls
    """

    def __init__(
        self,
        document: Optional[
            Union[DocumentModel, Dict[str, Any]]
        ] = None,
    ):
        super().__init__()

        self.document = document or {}

        self.setObjectName("contentCard")

        self._current_resolved_path: Optional[str] = None
        self._pdf_doc: Optional[Any] = None
        self._image_pixmap: Optional[QPixmap] = None

        if HAS_QT_PDF:
            self._pdf_doc = QPdfDocument(self)

        self.setup_ui()
        self.update_preview()

    # ==========================================================================
    # UI
    # ==========================================================================

    def setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(18, 14, 18, 14)
        root_layout.setSpacing(10)

        # ----------------------------------------------------------------------
        # Header
        # ----------------------------------------------------------------------

        hdr_layout = QHBoxLayout()
        hdr_layout.setSpacing(8)

        title = QLabel("Document Preview")
        title.setObjectName("sectionTitle")
        title.setStyleSheet(
            "font-size: 13px; "
            "font-weight: 700; "
            "color: #0F172A;"
        )
        hdr_layout.addWidget(title)

        self.format_badge = QLabel("PDF")
        self.format_badge.setStyleSheet(
            "background-color: #0F172A; "
            "color: white; "
            "padding: 2px 8px; "
            "border-radius: 3px; "
            "font-weight: 600; "
            "font-size: 10px;"
        )
        hdr_layout.addWidget(self.format_badge)

        hdr_layout.addStretch()

        # ----------------------------------------------------------------------
        # PDF Control Toolbar
        # ----------------------------------------------------------------------

        self.pdf_toolbar = QWidget()

        tb_layout = QHBoxLayout(self.pdf_toolbar)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(4)

        self.fit_btn = QPushButton("Fit")
        self.fit_btn.setStyleSheet(
            "background: #F1F5F9; "
            "border: 1px solid #CBD5E1; "
            "font-size: 11px; "
            "padding: 2px 8px; "
            "border-radius: 3px;"
        )
        self.fit_btn.clicked.connect(self._fit_width)
        tb_layout.addWidget(self.fit_btn)

        self.zoom_in_btn = QPushButton("+")
        self.zoom_in_btn.setStyleSheet(
            "background: #F1F5F9; "
            "border: 1px solid #CBD5E1; "
            "font-weight: bold; "
            "font-size: 11px; "
            "padding: 2px 8px; "
            "border-radius: 3px;"
        )
        self.zoom_in_btn.clicked.connect(self._zoom_in)
        tb_layout.addWidget(self.zoom_in_btn)

        self.zoom_out_btn = QPushButton("-")
        self.zoom_out_btn.setStyleSheet(
            "background: #F1F5F9; "
            "border: 1px solid #CBD5E1; "
            "font-weight: bold; "
            "font-size: 11px; "
            "padding: 2px 8px; "
            "border-radius: 3px;"
        )
        self.zoom_out_btn.clicked.connect(self._zoom_out)
        tb_layout.addWidget(self.zoom_out_btn)

        self.page_info_lbl = QLabel("1 / 1")
        self.page_info_lbl.setStyleSheet(
            "font-size: 11px; "
            "color: #64748B; "
            "font-weight: 600; "
            "padding: 0 4px;"
        )
        tb_layout.addWidget(self.page_info_lbl)

        hdr_layout.addWidget(self.pdf_toolbar)

        root_layout.addLayout(hdr_layout)

        # ----------------------------------------------------------------------
        # Content Stack
        # ----------------------------------------------------------------------

        self.stack = QStackedWidget()

        # ======================================================================
        # Page 0 - PDF Viewer
        # ======================================================================

        if HAS_QT_PDF:
            self.pdf_view = QPdfView()

            self.pdf_view.setDocument(self._pdf_doc)

            self.pdf_view.setPageMode(
                QPdfView.PageMode.MultiPage
            )

            self.pdf_view.setZoomMode(
                QPdfView.ZoomMode.FitToWidth
            )

            self.pdf_view.setStyleSheet(
                "background-color: #525659; "
                "border: 1px solid #CBD5E1; "
                "border-radius: 4px;"
            )

            self.stack.addWidget(self.pdf_view)

        else:
            self.pdf_fallback_lbl = QLabel(
                "PDF engine initializing..."
            )

            self.stack.addWidget(
                self.pdf_fallback_lbl
            )

        # ======================================================================
        # Page 1 - Image Viewer
        # ======================================================================

        self.image_scroll = QScrollArea()

        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setAlignment(Qt.AlignCenter)

        self.image_scroll.setStyleSheet(
            "background-color: #F8FAFC; "
            "border: 1px solid #CBD5E1; "
            "border-radius: 4px;"
        )

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)

        self.image_scroll.setWidget(
            self.image_label
        )

        self.stack.addWidget(
            self.image_scroll
        )

        # ======================================================================
        # Page 2 - Text / Dispatch Browser
        # ======================================================================

        self.text_browser = QTextBrowser()

        self.text_browser.setOpenExternalLinks(False)

        self.text_browser.setStyleSheet(
            "background-color: #F8FAFC; "
            "border: 1px solid #CBD5E1; "
            "border-radius: 4px; "
            "padding: 12px; "
            "font-size: 12px; "
            "color: #1E293B;"
        )

        self.stack.addWidget(
            self.text_browser
        )

        # ======================================================================
        # Page 3 - Metadata / Info Fallback
        # ======================================================================

        self.fallback_frame = QFrame()

        self.fallback_frame.setStyleSheet(
            "background-color: #F8FAFC; "
            "border: 1px dashed #CBD5E1; "
            "border-radius: 6px; "
            "padding: 16px;"
        )

        fb_layout = QVBoxLayout(
            self.fallback_frame
        )

        fb_layout.setAlignment(
            Qt.AlignCenter
        )

        fb_layout.setSpacing(8)

        self.fallback_text = QLabel()

        self.fallback_text.setAlignment(
            Qt.AlignCenter
        )

        self.fallback_text.setStyleSheet(
            "color: #475569; "
            "font-size: 12px;"
        )

        self.fallback_text.setWordWrap(True)

        fb_layout.addWidget(
            self.fallback_text
        )

        self.stack.addWidget(
            self.fallback_frame
        )

        self.stack.setMinimumHeight(220)

        root_layout.addWidget(
            self.stack,
            1,
        )

    # ==========================================================================
    # Resolve document file
    # ==========================================================================

    def _resolve_document_file_path(
        self,
    ) -> Optional[str]:
        """
        Resolve the document file for in-app preview.

        Priority:

        1. Existing local file_path, if available.
        2. ORIGINAL attachment from the server.
        3. First available attachment.

        Attachments are downloaded on-demand into the local
        CDTRS preview cache.
        """

        # ----------------------------------------------------------------------
        # 1. Existing local file path
        # ----------------------------------------------------------------------

        if (
            hasattr(self.document, "file_path")
            and self.document.file_path
        ):
            if os.path.exists(
                self.document.file_path
            ):
                return self.document.file_path

        if isinstance(self.document, dict):
            file_path = self.document.get(
                "file_path"
            )

            if (
                file_path
                and os.path.exists(file_path)
            ):
                return file_path

        # ----------------------------------------------------------------------
        # 2. Get document ID
        # ----------------------------------------------------------------------

        doc_id = (
            getattr(
                self.document,
                "id",
                None,
            )
            or getattr(
                self.document,
                "doc_id",
                None,
            )
            or (
                self.document.get("id")
                if isinstance(
                    self.document,
                    dict,
                )
                else None
            )
            or (
                self.document.get("doc_id")
                if isinstance(
                    self.document,
                    dict,
                )
                else None
            )
        )

        if not doc_id:
            return None

        # ----------------------------------------------------------------------
        # 3. Get document attachments
        # ----------------------------------------------------------------------

        try:
            attachments = (
                attachment_service
                .get_document_attachments(
                    doc_id
                )
                or []
            )

            if not attachments:
                return None

            # --------------------------------------------------------------
            # Prefer ORIGINAL attachment
            # --------------------------------------------------------------

            original = next(
                (
                    attachment
                    for attachment in attachments
                    if str(
                        getattr(
                            attachment,
                            "attachment_type",
                            "",
                        )
                    ).upper()
                    == "ORIGINAL"
                ),
                None,
            )

            attachment = (
                original
                or attachments[0]
            )

            # --------------------------------------------------------------
            # Attachment ID
            # --------------------------------------------------------------

            attachment_id = getattr(
                attachment,
                "id",
                None,
            )

            if not attachment_id:
                return None

            # --------------------------------------------------------------
            # File name
            # --------------------------------------------------------------

            file_name = (
                getattr(
                    attachment,
                    "file_name",
                    None,
                )
                or f"attachment_{attachment_id}"
            )

            safe_name = os.path.basename(
                file_name
            )

            # --------------------------------------------------------------
            # Local preview cache
            # --------------------------------------------------------------

            cache_dir = os.path.join(
                os.path.expanduser("~"),
                ".cdtrs",
                "preview_cache",
            )

            os.makedirs(
                cache_dir,
                exist_ok=True,
            )

            cached_path = os.path.join(
                cache_dir,
                f"{attachment_id}_{safe_name}",
            )

            # --------------------------------------------------------------
            # Already downloaded
            # --------------------------------------------------------------

            if os.path.exists(
                cached_path
            ):
                return cached_path

            # --------------------------------------------------------------
            # Download from backend
            # --------------------------------------------------------------

            downloaded = (
                attachment_service.download(
                    attachment_id,
                    cached_path,
                )
            )

            if (
                downloaded
                and os.path.exists(downloaded)
            ):
                return downloaded

            # Some repository implementations may
            # return None while still writing the file.

            if os.path.exists(
                cached_path
            ):
                return cached_path

        except Exception as exc:
            print(
                "[DocumentPreview] "
                f"Failed to resolve attachment: {exc}"
            )

        return None

    # ==========================================================================
    # Image resizing
    # ==========================================================================

    def _rescale_image(self):
        if (
            self._image_pixmap is None
            or self._image_pixmap.isNull()
        ):
            return

        viewport = (
            self.image_scroll
            .viewport()
            .size()
        )

        # QMargins has no topLeft()/bottomRight(); subtract each side.
        margins = self.image_scroll.contentsMargins()

        width = max(
            120,
            viewport.width() - margins.left() - margins.right() - 12,
        )

        height = max(
            120,
            viewport.height() - margins.top() - margins.bottom() - 12,
        )

        self.image_label.setPixmap(
            self._image_pixmap.scaled(
                width,
                height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    # ==========================================================================
    # Resize event
    # ==========================================================================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rescale_image()

    # ==========================================================================
    # Update preview
    # ==========================================================================

    def update_preview(self):
        """
        Update the preview area according to the current document.
        """

        file_path = (
            self._resolve_document_file_path()
        )

        self._current_resolved_path = (
            file_path
        )

        # ----------------------------------------------------------------------
        # Document metadata
        # ----------------------------------------------------------------------

        ref = (
            getattr(
                self.document,
                "reference_no",
                None,
            )
            or getattr(
                self.document,
                "reference",
                None,
            )
            or (
                self.document.get(
                    "reference"
                )
                if isinstance(
                    self.document,
                    dict,
                )
                else "Document"
            )
        )

        title = (
            getattr(
                self.document,
                "title",
                None,
            )
            or getattr(
                self.document,
                "subject",
                None,
            )
            or (
                self.document.get(
                    "title"
                )
                if isinstance(
                    self.document,
                    dict,
                )
                else "Untitled"
            )
        )

        mode = (
            getattr(
                self.document,
                "mode",
                None,
            )
            or (
                self.document.get(
                    "mode"
                )
                if isinstance(
                    self.document,
                    dict,
                )
                else "Outlook"
            )
        )

        desc = (
            getattr(
                self.document,
                "description",
                None,
            )
            or getattr(
                self.document,
                "ocr_text",
                None,
            )
            or (
                self.document.get(
                    "description"
                )
                if isinstance(
                    self.document,
                    dict,
                )
                else ""
            )
        )

        # ======================================================================
        # Actual document file exists
        # ======================================================================

        if (
            file_path
            and os.path.exists(file_path)
        ):

            ext = os.path.splitext(
                file_path
            )[1].lower()

            self.format_badge.setText(
                ext.replace(
                    ".",
                    "",
                ).upper()
                or "FILE"
            )

            # ------------------------------------------------------------------
            # PDF
            # ------------------------------------------------------------------

            if (
                ext == ".pdf"
                and HAS_QT_PDF
            ):

                self.pdf_toolbar.setVisible(
                    True
                )

                self.stack.setCurrentIndex(
                    0
                )

                self._pdf_doc.load(
                    file_path
                )

                page_count = (
                    self._pdf_doc.pageCount()
                )

                self.page_info_lbl.setText(
                    (
                        f"1 / {page_count}"
                        if page_count > 0
                        else "1 / 1"
                    )
                )

                self.pdf_view.setZoomMode(
                    QPdfView.ZoomMode.FitToWidth
                )

                return

            # ------------------------------------------------------------------
            # Image
            # ------------------------------------------------------------------

            elif ext in (
                ".png",
                ".jpg",
                ".jpeg",
                ".bmp",
            ):

                self.pdf_toolbar.setVisible(
                    False
                )

                self.stack.setCurrentIndex(
                    1
                )

                pixmap = QPixmap(
                    file_path
                )

                self._image_pixmap = (
                    pixmap
                )

                self._rescale_image()

                return

            # ------------------------------------------------------------------
            # Text
            # ------------------------------------------------------------------

            elif ext in (
                ".txt",
                ".log",
                ".csv",
                ".json",
            ):

                self.pdf_toolbar.setVisible(
                    False
                )

                self.stack.setCurrentIndex(
                    2
                )

                try:
                    with open(
                        file_path,
                        "r",
                        encoding="utf-8",
                        errors="ignore",
                    ) as fh:
                        content = fh.read()

                    self.text_browser.setPlainText(
                        content
                    )

                except Exception:
                    self.text_browser.setPlainText(
                        desc
                        or "Unable to read text file."
                    )

                return

        # ======================================================================
        # No previewable file
        # ======================================================================

        self.pdf_toolbar.setVisible(
            False
        )

        self.stack.setCurrentIndex(
            3
        )

        self.format_badge.setText(
            "INFO"
        )

        self.fallback_text.setText(
            f"Document Ref: {ref}\n\n"
            f"Title: {title}\n"
            f"Ingestion Mode: {mode}\n\n"
            f"{desc or '(Document file is not available for preview.)'}"
        )

    # ==========================================================================
    # PDF controls
    # ==========================================================================

    def _fit_width(self):
        if (
            HAS_QT_PDF
            and hasattr(
                self,
                "pdf_view",
            )
        ):
            self.pdf_view.setZoomMode(
                QPdfView.ZoomMode.FitToWidth
            )

    def _zoom_in(self):
        if (
            HAS_QT_PDF
            and hasattr(
                self,
                "pdf_view",
            )
        ):
            self.pdf_view.setZoomMode(
                QPdfView.ZoomMode.Custom
            )

            self.pdf_view.setZoomFactor(
                self.pdf_view.zoomFactor()
                * 1.2
            )

    def _zoom_out(self):
        if (
            HAS_QT_PDF
            and hasattr(
                self,
                "pdf_view",
            )
        ):
            self.pdf_view.setZoomMode(
                QPdfView.ZoomMode.Custom
            )

            self.pdf_view.setZoomFactor(
                max(
                    0.2,
                    self.pdf_view.zoomFactor()
                    / 1.2,
                )
            )

    # ==========================================================================
    # Change document
    # ==========================================================================

    def set_document(
        self,
        document: Optional[
            Union[
                DocumentModel,
                Dict[str, Any],
            ]
        ],
    ):
        self.document = document or {}
        self.update_preview()