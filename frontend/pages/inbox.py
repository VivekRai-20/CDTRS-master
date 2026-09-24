"""
CDTRS — Director Secretary Incoming Communications Inbox.

This page represents the DS incoming communication queue.

Flow:

External / Outlook communication
        ↓
     DS Inbox
        ↓
Process Communication
        ↓
Automatic document processing / OCR
        ↓
Document Intake / Workflow

Manual uploads and already registered workflow documents
do NOT belong in this Inbox.
"""

from typing import Any, Dict, List
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from repositories.provider import get_repository


class InboxPage(QWidget):
    """
    Director Secretary incoming communications page.

    The page contains:

        Header
        Summary cards
        Search/filter bar
        Incoming communication list
        Selected communication preview
        Process Communication action

    OCR is NOT manually triggered from this page.
    Document processing/OCR happens automatically after processing.
    """

    process_requested = Signal(object)

    def __init__(self):
        super().__init__()

        self.documents: List[Any] = []
        self._displayed_docs: List[Any] = []
        self._selected_index = -1

        self.setup_ui()

        # ------------------------------------------------------------
        # EVENT BUS
        # ------------------------------------------------------------

        try:
            from services.event_bus import event_bus

            try:
                event_bus.inbox_updated.connect(
                    self.load_documents
                )
            except Exception:
                pass

            try:
                event_bus.data_changed.connect(
                    self.load_documents
                )
            except Exception:
                pass

        except Exception:
            pass

    # ================================================================
    # SHOW EVENT
    # ================================================================

    def showEvent(self, event):
        super().showEvent(event)
        self.load_documents()

    # ================================================================
    # MAIN UI
    # ================================================================

    def setup_ui(self):

        main_layout = QVBoxLayout(self)

        main_layout.setContentsMargins(
            28,
            22,
            28,
            24,
        )

        main_layout.setSpacing(12)

        # ============================================================
        # HEADER
        # ============================================================

        header = QHBoxLayout()
        header.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)

        title = QLabel(
            "Incoming Communications"
        )

        title.setObjectName(
            "pageTitle"
        )

        title_box.addWidget(title)

        subtitle = QLabel(
            "External mail and dispatches waiting for "
            "Director Secretary processing"
        )

        subtitle.setObjectName(
            "pageSubtitle"
        )

        subtitle.setWordWrap(True)

        title_box.addWidget(
            subtitle
        )

        header.addLayout(
            title_box,
            1,
        )

        # ------------------------------------------------------------
        # READY BADGE
        # ------------------------------------------------------------

        self.sync_badge = QLabel(
            "● Ready"
        )

        self.sync_badge.setObjectName(
            "statusBadge"
        )

        self.sync_badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.sync_badge.setMinimumWidth(
            150
        )

        self.sync_badge.setMinimumHeight(
            42
        )

        self._set_ready_badge()

        header.addWidget(
            self.sync_badge
        )

        # ------------------------------------------------------------
        # SYNC BUTTON
        # ------------------------------------------------------------

        self.sync_outlook_btn = QPushButton(
            "↻  Sync Now"
        )

        self.sync_outlook_btn.setMinimumHeight(
            42
        )

        self.sync_outlook_btn.setMinimumWidth(
            130
        )

        self.sync_outlook_btn.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.sync_outlook_btn.setStyleSheet(
            """
            QPushButton {
                background: #0F172A;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 8px 15px;
                font-weight: 600;
            }

            QPushButton:hover {
                background: #1E293B;
            }

            QPushButton:disabled {
                background: #94A3B8;
            }
            """
        )

        self.sync_outlook_btn.clicked.connect(
            self._sync_outlook
        )

        header.addWidget(
            self.sync_outlook_btn
        )

        main_layout.addLayout(
            header
        )

        # ============================================================
        # SUMMARY CARDS
        # ============================================================

        stats = QHBoxLayout()
        stats.setSpacing(12)

        self.new_count = self._stat_card(
            "0",
            "Waiting to Process",
            "#2563EB",
        )

        self.attachment_count = self._stat_card(
            "0",
            "With Attachments",
            "#D97706",
        )

        self.today_count = self._stat_card(
            "0",
            "Received Today",
            "#059669",
        )

        stats.addWidget(
            self.new_count,
            1,
        )

        stats.addWidget(
            self.attachment_count,
            1,
        )

        stats.addWidget(
            self.today_count,
            1,
        )

        # Keep the cards compact and prevent them
        # from stretching across the entire window.
        stats.addStretch(
            2
        )

        main_layout.addLayout(
            stats
        )

        # ============================================================
        # FILTER BAR
        # ============================================================

        filter_bar = QFrame()

        filter_bar.setObjectName(
            "inboxFilterBar"
        )

        filter_bar.setMinimumHeight(
            62
        )

        filter_bar.setStyleSheet(
            """
            QFrame#inboxFilterBar {
                background: #FFFFFF;
                border: 1px solid #DCE5F0;
                border-radius: 8px;
            }
            """
        )

        filter_layout = QHBoxLayout(
            filter_bar
        )

        filter_layout.setContentsMargins(
            12,
            9,
            12,
            9,
        )

        filter_layout.setSpacing(
            10
        )

        # ------------------------------------------------------------
        # SEARCH
        # ------------------------------------------------------------

        self.search_input = QLineEdit()

        self.search_input.setPlaceholderText(
            "Search sender, subject, source or communication..."
        )

        self.search_input.setMinimumHeight(
            38
        )

        self.search_input.textChanged.connect(
            self.apply_filters
        )

        filter_layout.addWidget(
            self.search_input,
            4,
        )

        # ------------------------------------------------------------
        # FILTER
        # ------------------------------------------------------------

        self.filter_combo = QComboBox()

        self.filter_combo.addItems(
            [
                "All Incoming",
                "With Attached Files",
                "Email Body / No Attachment",
            ]
        )

        self.filter_combo.setMinimumHeight(
            38
        )

        self.filter_combo.setMinimumWidth(
            190
        )

        self.filter_combo.currentIndexChanged.connect(
            self.apply_filters
        )

        filter_layout.addWidget(
            self.filter_combo,
            1,
        )

        # ------------------------------------------------------------
        # CLEAR
        # ------------------------------------------------------------

        clear_btn = QPushButton(
            "Clear"
        )

        clear_btn.setMinimumHeight(
            38
        )

        clear_btn.setMinimumWidth(
            70
        )

        clear_btn.clicked.connect(
            self._clear_filters
        )

        filter_layout.addWidget(
            clear_btn
        )

        main_layout.addWidget(
            filter_bar
        )

        # ============================================================
        # MAIN WORKSPACE
        # ============================================================

        workspace = QFrame()

        workspace.setObjectName(
            "inboxWorkspace"
        )

        workspace.setStyleSheet(
            """
            QFrame#inboxWorkspace {
                background: #FFFFFF;
                border: 1px solid #DCE5F0;
                border-radius: 10px;
            }
            """
        )

        workspace_layout = QHBoxLayout(
            workspace
        )

        workspace_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        workspace_layout.setSpacing(
            0
        )

        # ============================================================
        # LEFT — INCOMING LIST
        # ============================================================

        left = QFrame()

        left.setObjectName(
            "inboxListPane"
        )

        # IMPORTANT:
        # Do not allow this pane to become excessively wide.
        left.setMinimumWidth(
            330
        )

        left.setMaximumWidth(
            440
        )

        left.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        left.setStyleSheet(
            """
            QFrame#inboxListPane {
                background: #F8FAFC;
                border-right: 1px solid #E2E8F0;
            }
            """
        )

        left_layout = QVBoxLayout(
            left
        )

        left_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        left_layout.setSpacing(
            0
        )

        # ------------------------------------------------------------
        # LIST HEADER
        # ------------------------------------------------------------

        list_header = QHBoxLayout()

        list_header.setContentsMargins(
            14,
            12,
            14,
            10,
        )

        list_title = QLabel(
            "INCOMING"
        )

        list_title.setStyleSheet(
            """
            color: #475569;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1px;
            """
        )

        list_header.addWidget(
            list_title
        )

        list_header.addStretch()

        self.result_label = QLabel(
            "0 messages"
        )

        self.result_label.setStyleSheet(
            """
            color: #64748B;
            font-size: 9px;
            font-weight: 600;
            """
        )

        list_header.addWidget(
            self.result_label
        )

        left_layout.addLayout(
            list_header
        )

        # ------------------------------------------------------------
        # SCROLL AREA
        # ------------------------------------------------------------

        self.list_scroll = QScrollArea()

        self.list_scroll.setWidgetResizable(
            True
        )

        self.list_scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.list_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.list_container = QWidget()

        self.list_layout = QVBoxLayout(
            self.list_container
        )

        self.list_layout.setContentsMargins(
            8,
            4,
            8,
            8,
        )

        self.list_layout.setSpacing(
            7
        )

        self.list_layout.addStretch()

        self.list_scroll.setWidget(
            self.list_container
        )

        left_layout.addWidget(
            self.list_scroll,
            1,
        )

        # ============================================================
        # RIGHT — DETAIL
        # ============================================================

        self.detail_stack = QStackedWidget()

        self.detail_stack.setObjectName(
            "inboxDetailStack"
        )

        self.detail_stack.setMinimumWidth(
            500
        )

        # ------------------------------------------------------------
        # EMPTY DETAIL
        # ------------------------------------------------------------

        self.detail_empty = (
            self._build_detail_empty()
        )

        self.detail_stack.addWidget(
            self.detail_empty
        )

        # ------------------------------------------------------------
        # DETAIL SCROLL
        # ------------------------------------------------------------

        self.detail_scroll = QScrollArea()

        self.detail_scroll.setWidgetResizable(
            True
        )

        self.detail_scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.detail_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.detail_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.detail_container = QWidget()

        self.detail_layout = QVBoxLayout(
            self.detail_container
        )

        self.detail_layout.setContentsMargins(
            24,
            18,
            24,
            18,
        )

        self.detail_layout.setSpacing(
            12
        )

        self.detail_scroll.setWidget(
            self.detail_container
        )

        self.detail_stack.addWidget(
            self.detail_scroll
        )

        # ------------------------------------------------------------
        # PROPORTION
        #
        # Approximately 37% list / 63% detail.
        # ------------------------------------------------------------

        workspace_layout.addWidget(
            left,
            3,
        )

        workspace_layout.addWidget(
            self.detail_stack,
            5,
        )

        main_layout.addWidget(
            workspace,
            1,
        )

        # ============================================================
        # BOTTOM ACTION BAR
        # ============================================================

        action_bar = QHBoxLayout()

        action_bar.setContentsMargins(
            0,
            2,
            0,
            0,
        )

        self.selection_hint = QLabel(
            "Select an incoming communication to review it."
        )

        self.selection_hint.setStyleSheet(
            """
            color: #64748B;
            font-size: 10px;
            """
        )

        action_bar.addWidget(
            self.selection_hint
        )

        action_bar.addStretch()

        self.process_button = QPushButton(
            "Process Communication"
        )

        self.process_button.setEnabled(
            False
        )

        self.process_button.setMinimumHeight(
            42
        )

        self.process_button.setMinimumWidth(
            205
        )

        self.process_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.process_button.setStyleSheet(
            """
            QPushButton {
                background: #2563EB;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 8px 17px;
                font-weight: 700;
            }

            QPushButton:hover {
                background: #1D4ED8;
            }

            QPushButton:disabled {
                background: #CBD5E1;
                color: #64748B;
            }
            """
        )

        self.process_button.clicked.connect(
            self.process_selected
        )

        action_bar.addWidget(
            self.process_button
        )

        main_layout.addLayout(
            action_bar
        )

    # ================================================================
    # BADGE
    # ================================================================

    def _set_ready_badge(
        self,
    ):

        self.sync_badge.setText(
            "● Ready"
        )

        self.sync_badge.setStyleSheet(
            """
            QLabel#statusBadge {
                background: #ECFDF5;
                color: #047857;
                border: 1px solid #A7F3D0;
                border-radius: 14px;
                padding: 7px 14px;
                font-size: 9px;
                font-weight: 700;
            }
            """
        )

    # ================================================================
    # STAT CARD
    # ================================================================

    def _stat_card(
        self,
        value: str,
        label: str,
        accent: str,
    ) -> QFrame:

        card = QFrame()

        card.setFixedHeight(
            74
        )

        card.setMinimumWidth(
            220
        )

        card.setMaximumWidth(
            300
        )

        card.setStyleSheet(
            f"""
            QFrame {{
                background: #FFFFFF;
                border: 1px solid #DCE5F0;
                border-left: 4px solid {accent};
                border-radius: 8px;
            }}
            """
        )

        layout = QVBoxLayout(
            card
        )

        layout.setContentsMargins(
            12,
            9,
            12,
            8,
        )

        layout.setSpacing(
            1
        )

        value_label = QLabel(
            value
        )

        value_label.setStyleSheet(
            f"""
            color: {accent};
            font-size: 21px;
            font-weight: 800;
            """
        )

        layout.addWidget(
            value_label
        )

        text_label = QLabel(
            label
        )

        text_label.setStyleSheet(
            """
            color: #334155;
            font-size: 9px;
            font-weight: 700;
            """
        )

        layout.addWidget(
            text_label
        )

        card.value_label = value_label

        return card

    # ================================================================
    # GENERIC VALUE
    # ================================================================

    @staticmethod
    def _value(
        doc: Any,
        key: str,
        default="",
    ):

        if isinstance(
            doc,
            dict,
        ):
            return doc.get(
                key,
                default,
            )

        return getattr(
            doc,
            key,
            default,
        )

    # ================================================================
    # EMPTY DETAIL
    # ================================================================

    def _build_detail_empty(
        self,
    ) -> QWidget:

        frame = QFrame()

        frame.setStyleSheet(
            """
            background: #FFFFFF;
            """
        )

        layout = QVBoxLayout(
            frame
        )

        layout.setContentsMargins(
            50,
            70,
            50,
            70,
        )

        icon = QLabel(
            "✉"
        )

        icon.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        icon.setStyleSheet(
            """
            color: #CBD5E1;
            font-size: 42px;
            font-weight: 700;
            """
        )

        layout.addWidget(
            icon
        )

        title = QLabel(
            "Select a communication"
        )

        title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        title.setStyleSheet(
            """
            color: #334155;
            font-size: 15px;
            font-weight: 700;
            """
        )

        layout.addWidget(
            title
        )

        text = QLabel(
            "Choose an incoming message from the list "
            "to review its sender, subject, content and attachments."
        )

        text.setWordWrap(
            True
        )

        text.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        text.setStyleSheet(
            """
            color: #94A3B8;
            font-size: 10px;
            """
        )

        layout.addWidget(
            text
        )

        return frame

    # ================================================================
    # MAIL CARD
    # ================================================================

    def _build_mail_card(
        self,
        index: int,
        doc: Any,
    ) -> QFrame:

        selected = (
            index == self._selected_index
        )

        card = QFrame()

        card.setObjectName(
            "mailCard"
        )

        # ------------------------------------------------------------
        # IMPORTANT FIX:
        # Previously cards were too short and long subjects were
        # vertically clipped.
        # ------------------------------------------------------------

        card.setMinimumHeight(
            86
        )

        card.setMaximumHeight(
            104
        )

        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        if selected:

            card.setStyleSheet(
                """
                QFrame#mailCard {
                    background: #EFF6FF;
                    border: 1px solid #60A5FA;
                    border-left: 4px solid #2563EB;
                    border-radius: 8px;
                }
                """
            )

        else:

            card.setStyleSheet(
                """
                QFrame#mailCard {
                    background: #FFFFFF;
                    border: 1px solid #E2E8F0;
                    border-radius: 8px;
                }

                QFrame#mailCard:hover {
                    border: 1px solid #93C5FD;
                    background: #F8FBFF;
                }
                """
            )

        outer = QVBoxLayout(
            card
        )

        outer.setContentsMargins(
            11,
            9,
            11,
            9,
        )

        outer.setSpacing(
            0
        )

        button = QPushButton()

        button.setFlat(
            True
        )

        button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        button.setStyleSheet(
            """
            QPushButton {
                border: none;
                text-align: left;
                padding: 0;
                background: transparent;
            }
            """
        )

        content = QWidget()

        content_layout = QVBoxLayout(
            content
        )

        content_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        content_layout.setSpacing(
            4
        )

        # ============================================================
        # TOP LINE — SENDER + DATE
        # ============================================================

        top = QHBoxLayout()

        top.setSpacing(
            6
        )

        sender = str(
            self._value(
                doc,
                "sender_name",
            )
            or self._value(
                doc,
                "sender_email",
            )
            or self._value(
                doc,
                "source",
            )
            or "External sender"
        )

        sender_label = QLabel(
            sender
        )

        sender_label.setMinimumHeight(
            18
        )

        sender_label.setMaximumHeight(
            20
        )

        sender_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        sender_label.setStyleSheet(
            """
            color: #0F172A;
            font-size: 10px;
            font-weight: 700;
            """
        )

        top.addWidget(
            sender_label,
            1,
        )

        received = str(
            self._value(
                doc,
                "date",
            )
            or self._value(
                doc,
                "received_at",
            )
            or "Today"
        )

        received = (
            received
            .replace(
                "T",
                " ",
            )
            .replace(
                "Z",
                "",
            )
        )

        # Keep date short in the list.
        if len(received) > 16:
            received = received[:16]

        time_label = QLabel(
            received
        )

        time_label.setMinimumWidth(
            92
        )

        time_label.setMaximumWidth(
            115
        )

        time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTop
        )

        time_label.setStyleSheet(
            """
            color: #64748B;
            font-size: 7px;
            font-weight: 600;
            """
        )

        top.addWidget(
            time_label
        )

        content_layout.addLayout(
            top
        )

        # ============================================================
        # SUBJECT
        # ============================================================

        subject = str(
            self._value(
                doc,
                "subject",
            )
            or self._value(
                doc,
                "title",
            )
            or "No subject"
        )

        subject_label = QLabel(
            subject
        )

        # IMPORTANT:
        # Long subject gets two lines rather than being clipped.
        subject_label.setWordWrap(
            True
        )

        subject_label.setMinimumHeight(
            24
        )

        subject_label.setMaximumHeight(
            34
        )

        subject_label.setStyleSheet(
            """
            color: #1E293B;
            font-size: 9px;
            font-weight: 600;
            """
        )

        content_layout.addWidget(
            subject_label
        )

        # ============================================================
        # META
        # ============================================================

        mode = str(
            self._value(
                doc,
                "mode",
            )
            or self._value(
                doc,
                "source_type",
            )
            or "External Mail"
        )

        att_count = int(
            self._value(
                doc,
                "attachment_count",
                0,
            )
            or 0
        )

        meta_text = mode

        if att_count:

            meta_text += (
                f"   •   📎 {att_count} attachment"
                f"{'' if att_count == 1 else 's'}"
            )

        meta = QLabel(
            meta_text
        )

        meta.setMinimumHeight(
            14
        )

        meta.setMaximumHeight(
            16
        )

        meta.setStyleSheet(
            """
            color: #64748B;
            font-size: 7px;
            """
        )

        content_layout.addWidget(
            meta
        )

        button_layout = QVBoxLayout(
            button
        )

        button_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        button_layout.addWidget(
            content
        )

        button.clicked.connect(
            lambda checked=False, i=index:
            self._select_item(i)
        )

        outer.addWidget(
            button
        )

        return card

    # ================================================================
    # SELECT ITEM
    # ================================================================

    def _select_item(
        self,
        index: int,
    ):

        if (
            index < 0
            or index >= len(
                self._displayed_docs
            )
        ):
            return

        self._selected_index = index

        self.process_button.setEnabled(
            True
        )

        self.selection_hint.setText(
            "Communication selected. Review it and continue processing."
        )

        self._render_list()

        self._render_detail(
            self._displayed_docs[index]
        )

    # ================================================================
    # LOAD DOCUMENTS
    # ================================================================

    def load_documents(
        self,
    ):

        try:

            repo = get_repository()

            intake_items = (
                repo.get_intake_items()
            )

        except Exception:

            self.documents = []
            self._displayed_docs = []
            self._selected_index = -1

            self.sync_badge.setText(
                "● Backend unavailable"
            )

            self.sync_badge.setStyleSheet(
                """
                QLabel#statusBadge {
                    background: #FEF2F2;
                    color: #B91C1C;
                    border: 1px solid #FECACA;
                    border-radius: 14px;
                    padding: 7px 14px;
                    font-size: 9px;
                    font-weight: 700;
                }
                """
            )

            self.apply_filters()

            return

        normalized: List[
            Dict[str, Any]
        ] = []

        for item in (
            intake_items or []
        ):

            if not isinstance(
                item,
                dict,
            ):
                continue

            source_type = str(
                item.get(
                    "source_type"
                )
                or item.get(
                    "mode"
                )
                or ""
            ).upper()

            # --------------------------------------------------------
            # MANUAL UPLOADS DO NOT BELONG IN INBOX
            # --------------------------------------------------------

            if source_type in (
                "MANUAL_UPLOAD",
                "MANUAL",
                "MANUAL UPLOAD",
            ):
                continue

            processing_status = str(
                item.get(
                    "processing_status"
                )
                or item.get(
                    "status"
                )
                or "NEW"
            )

            # --------------------------------------------------------
            # PROCESSED ITEMS LEAVE INBOX
            # --------------------------------------------------------

            if (
                processing_status.upper()
                == "PROCESSED"
            ):
                continue

            received_at = (
                item.get(
                    "received_at"
                )
                or item.get(
                    "created_at"
                )
                or ""
            )

            sender_name = (
                item.get(
                    "sender_name"
                )
                or item.get(
                    "sender_email"
                )
                or "External sender"
            )

            subject = (
                item.get(
                    "subject"
                )
                or
                f"Incoming Message #{item.get('id', '')}"
            )

            normalized.append(
                {
                    "id": item.get(
                        "id"
                    ),

                    "title": subject,

                    "source": sender_name,

                    "created_by": (
                        item.get(
                            "sender_email"
                        )
                        or item.get(
                            "sender_name"
                        )
                        or "External"
                    ),

                    "mode": (
                        item.get(
                            "source_type"
                        )
                        or "External Mail"
                    ),

                    "format": "Email",

                    "file_type": "Email",

                    "attachment_count": (
                        1
                        if item.get(
                            "has_attachments"
                        )
                        else 0
                    ),

                    "date": str(
                        received_at
                    ),

                    "status": processing_status,

                    "sender_name": item.get(
                        "sender_name"
                    ),

                    "sender_email": item.get(
                        "sender_email"
                    ),

                    "subject": item.get(
                        "subject"
                    ),

                    "body": (
                        item.get(
                            "body"
                        )
                        or ""
                    ),

                    "body_reference": item.get(
                        "body_reference"
                    ),

                    "external_message_id": item.get(
                        "external_message_id"
                    ),

                    "received_at": item.get(
                        "received_at"
                    ),

                    "has_attachments": bool(
                        item.get(
                            "has_attachments"
                        )
                    ),

                    "processing_status": processing_status,

                    "created_at": item.get(
                        "created_at"
                    ),

                    "file_path": "",
                }
            )

        self.documents = normalized

        self._set_ready_badge()

        self.apply_filters()

    # ================================================================
    # FILTERS
    # ================================================================

    def apply_filters(
        self,
    ):

        search_query = (
            self.search_input
            .text()
            .strip()
            .lower()
        )

        filter_type = (
            self.filter_combo
            .currentText()
        )

        filtered: List[Any] = []

        for doc in self.documents:

            source = str(
                self._value(
                    doc,
                    "source",
                )
                or ""
            ).lower()

            sender = str(
                self._value(
                    doc,
                    "created_by",
                )
                or self._value(
                    doc,
                    "sender_email",
                )
                or ""
            ).lower()

            sender_name = str(
                self._value(
                    doc,
                    "sender_name",
                )
                or ""
            ).lower()

            title = str(
                self._value(
                    doc,
                    "title",
                )
                or self._value(
                    doc,
                    "subject",
                )
                or ""
            ).lower()

            mode = str(
                self._value(
                    doc,
                    "mode",
                )
                or ""
            ).lower()

            att_count = int(
                self._value(
                    doc,
                    "attachment_count",
                    0,
                )
                or 0
            )

            # --------------------------------------------------------
            # ATTACHMENT FILTER
            # --------------------------------------------------------

            if (
                filter_type
                == "With Attached Files"
                and att_count < 1
            ):
                continue

            if (
                filter_type
                == "Email Body / No Attachment"
                and att_count > 0
            ):
                continue

            # --------------------------------------------------------
            # SEARCH
            # --------------------------------------------------------

            if search_query:

                match = (
                    search_query in source
                    or search_query in sender
                    or search_query in sender_name
                    or search_query in title
                    or search_query in mode
                )

                if not match:
                    continue

            filtered.append(
                doc
            )

        self._displayed_docs = filtered

        if not filtered:

            self._selected_index = -1

        elif (
            self._selected_index
            >= len(filtered)
        ):

            self._selected_index = 0

        self._update_stats()

        self._render_list()

        self.result_label.setText(
            f"{len(filtered)} message"
            f"{'' if len(filtered) == 1 else 's'}"
        )

        if self._selected_index >= 0:

            self.process_button.setEnabled(
                True
            )

            self.selection_hint.setText(
                "Communication selected. Review it and continue processing."
            )

            self._render_detail(
                filtered[
                    self._selected_index
                ]
            )

        else:

            self.process_button.setEnabled(
                False
            )

            self.selection_hint.setText(
                "Select an incoming communication to review it."
            )

            self.detail_stack.setCurrentWidget(
                self.detail_empty
            )

    # ================================================================
    # UPDATE SUMMARY CARDS
    # ================================================================

    def _update_stats(
        self,
    ):

        total = len(
            self.documents
        )

        attachments = sum(
            int(
                self._value(
                    doc,
                    "attachment_count",
                    0,
                )
                or 0
            )
            for doc in self.documents
        )

        today = 0

        current_date = (
            datetime.now()
            .strftime("%Y-%m-%d")
        )

        for doc in self.documents:

            value = str(
                self._value(
                    doc,
                    "received_at",
                )
                or self._value(
                    doc,
                    "date",
                )
                or ""
            )

            if not value:
                continue

            try:

                date_part = (
                    value
                    .replace(
                        "Z",
                        "",
                    )
                    .split(
                        "T",
                        1,
                    )[0]
                )

                if date_part == current_date:

                    today += 1

            except Exception:
                pass

        self.new_count.value_label.setText(
            str(total)
        )

        self.attachment_count.value_label.setText(
            str(attachments)
        )

        self.today_count.value_label.setText(
            str(today)
        )

    # ================================================================
    # CLEAR FILTERS
    # ================================================================

    def _clear_filters(
        self,
    ):

        self.search_input.clear()

        self.filter_combo.setCurrentIndex(
            0
        )

    # ================================================================
    # CLEAR LAYOUT
    # ================================================================

    def _clear_layout(
        self,
        layout,
    ):

        while layout.count():

            item = layout.takeAt(
                0
            )

            widget = item.widget()

            if widget is not None:

                widget.setParent(
                    None
                )

                widget.deleteLater()

    # ================================================================
    # RENDER LIST
    # ================================================================

    def _render_list(
        self,
    ):

        self._clear_layout(
            self.list_layout
        )

        if not self._displayed_docs:

            empty = QLabel(
                "No incoming communications"
            )

            empty.setAlignment(
                Qt.AlignmentFlag.AlignCenter
            )

            empty.setWordWrap(
                True
            )

            empty.setStyleSheet(
                """
                color: #94A3B8;
                font-size: 10px;
                padding: 30px;
                """
            )

            self.list_layout.addWidget(
                empty
            )

            self.list_layout.addStretch()

            return

        for index, doc in enumerate(
            self._displayed_docs
        ):

            self.list_layout.addWidget(
                self._build_mail_card(
                    index,
                    doc,
                )
            )

        self.list_layout.addStretch()

    # ================================================================
    # RENDER DETAIL
    # ================================================================

    def _render_detail(
        self,
        doc: Any,
    ):

        self._clear_layout(
            self.detail_layout
        )

        # ============================================================
        # SUBJECT HEADER
        # ============================================================

        header = QFrame()

        header.setStyleSheet(
            """
            QFrame {
                background: #FFFFFF;
                border-bottom: 1px solid #E2E8F0;
            }
            """
        )

        header_layout = QVBoxLayout(
            header
        )

        header_layout.setContentsMargins(
            0,
            0,
            0,
            10,
        )

        header_layout.setSpacing(
            5
        )

        subject = str(
            self._value(
                doc,
                "subject",
            )
            or self._value(
                doc,
                "title",
            )
            or "No subject"
        )

        subject_label = QLabel(
            subject
        )

        subject_label.setWordWrap(
            True
        )

        subject_label.setStyleSheet(
            """
            color: #0F172A;
            font-size: 18px;
            font-weight: 750;
            """
        )

        header_layout.addWidget(
            subject_label
        )

        ref = self._value(
            doc,
            "id",
        )

        mode = str(
            self._value(
                doc,
                "mode",
            )
            or "External Mail"
        )

        if ref is not None:

            reference_text = (
                f"Incoming communication #{ref}"
            )

        else:

            reference_text = (
                "Incoming communication"
            )

        ref_label = QLabel(
            f"{reference_text}   •   {mode}"
        )

        ref_label.setStyleSheet(
            """
            color: #64748B;
            font-size: 9px;
            """
        )

        header_layout.addWidget(
            ref_label
        )

        self.detail_layout.addWidget(
            header
        )

        # ============================================================
        # SENDER INFORMATION
        # ============================================================

        sender_card = QFrame()

        sender_card.setStyleSheet(
            """
            QFrame {
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            """
        )

        sender_layout = QVBoxLayout(
            sender_card
        )

        sender_layout.setContentsMargins(
            13,
            10,
            13,
            10,
        )

        sender_layout.setSpacing(
            4
        )

        sender_name = str(
            self._value(
                doc,
                "sender_name",
            )
            or self._value(
                doc,
                "source",
            )
            or "External sender"
        )

        sender_email = str(
            self._value(
                doc,
                "sender_email",
            )
            or self._value(
                doc,
                "created_by",
            )
            or ""
        )

        received = str(
            self._value(
                doc,
                "received_at",
            )
            or self._value(
                doc,
                "date",
            )
            or "—"
        )

        received = (
            received
            .replace(
                "T",
                " ",
            )
            .replace(
                "Z",
                "",
            )
        )

        sender_line = QLabel(
            f"<b>From:</b> {sender_name}"
            + (
                f"  &lt;{sender_email}&gt;"
                if sender_email
                else ""
            )
        )

        sender_line.setTextFormat(
            Qt.TextFormat.RichText
        )

        sender_line.setWordWrap(
            True
        )

        sender_line.setStyleSheet(
            """
            color: #334155;
            font-size: 10px;
            """
        )

        sender_layout.addWidget(
            sender_line
        )

        received_label = QLabel(
            f"<b>Received:</b> {received[:30]}"
        )

        received_label.setTextFormat(
            Qt.TextFormat.RichText
        )

        received_label.setStyleSheet(
            """
            color: #64748B;
            font-size: 9px;
            """
        )

        sender_layout.addWidget(
            received_label
        )

        self.detail_layout.addWidget(
            sender_card
        )

        # ============================================================
        # MESSAGE BODY
        # ============================================================

        body_card = QFrame()

        body_card.setStyleSheet(
            """
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            """
        )

        body_layout = QVBoxLayout(
            body_card
        )

        body_layout.setContentsMargins(
            14,
            12,
            14,
            14,
        )

        body_layout.setSpacing(
            8
        )

        body_title = QLabel(
            "MESSAGE"
        )

        body_title.setStyleSheet(
            """
            color: #64748B;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 1px;
            """
        )

        body_layout.addWidget(
            body_title
        )

        body = str(
            self._value(
                doc,
                "body",
            )
            or
            "No message body is available for this communication."
        )

        body_label = QLabel(
            body
        )

        body_label.setWordWrap(
            True
        )

        body_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        body_label.setStyleSheet(
            """
            color: #334155;
            font-size: 10px;
            padding: 4px 0;
            """
        )

        body_layout.addWidget(
            body_label
        )

        self.detail_layout.addWidget(
            body_card
        )

        # ============================================================
        # ATTACHMENTS
        # ============================================================

        att_count = int(
            self._value(
                doc,
                "attachment_count",
                0,
            )
            or 0
        )

        attachments = QFrame()

        attachments.setStyleSheet(
            """
            QFrame {
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
            }
            """
        )

        att_layout = QVBoxLayout(
            attachments
        )

        att_layout.setContentsMargins(
            14,
            11,
            14,
            11,
        )

        att_layout.setSpacing(
            5
        )

        att_title = QLabel(
            "ATTACHMENTS"
        )

        att_title.setStyleSheet(
            """
            color: #64748B;
            font-size: 9px;
            font-weight: 800;
            letter-spacing: 1px;
            """
        )

        att_layout.addWidget(
            att_title
        )

        if att_count:

            att_label = QLabel(
                f"📎 {att_count} attachment"
                f"{'' if att_count == 1 else 's'} "
                "received with this communication."
            )

        else:

            att_label = QLabel(
                "No attachments received."
            )

        att_label.setWordWrap(
            True
        )

        att_label.setStyleSheet(
            """
            color: #334155;
            font-size: 10px;
            """
        )

        att_layout.addWidget(
            att_label
        )

        self.detail_layout.addWidget(
            attachments
        )

        # ============================================================
        # PROCESSING NOTE
        # ============================================================

        note = QFrame()

        note.setStyleSheet(
            """
            QFrame {
                background: #EFF6FF;
                border: 1px solid #BFDBFE;
                border-radius: 8px;
            }
            """
        )

        note_layout = QHBoxLayout(
            note
        )

        note_layout.setContentsMargins(
            12,
            10,
            12,
            10,
        )

        note_layout.setSpacing(
            8
        )

        note_icon = QLabel(
            "ℹ"
        )

        note_icon.setStyleSheet(
            """
            color: #2563EB;
            font-size: 15px;
            font-weight: 800;
            """
        )

        note_layout.addWidget(
            note_icon
        )

        note_text = QLabel(
            "Select Process Communication to move this "
            "incoming item into document processing. "
            "OCR and document processing run automatically "
            "as part of that flow."
        )

        note_text.setWordWrap(
            True
        )

        note_text.setStyleSheet(
            """
            color: #1E40AF;
            font-size: 9px;
            """
        )

        note_layout.addWidget(
            note_text,
            1,
        )

        self.detail_layout.addWidget(
            note
        )

        self.detail_layout.addStretch()

        self.detail_stack.setCurrentWidget(
            self.detail_scroll
        )

    # ================================================================
    # PROCESS SELECTED
    # ================================================================

    def process_selected(
        self,
    ):

        index = self._selected_index

        if (
            index < 0
            or index >= len(
                self._displayed_docs
            )
        ):

            QMessageBox.information(
                self,
                "No Communication Selected",
                "Please select an incoming communication to process.",
            )

            return

        selected_item = (
            self._displayed_docs[index]
        )

        self.process_requested.emit(
            selected_item
        )

    # ================================================================
    # OUTLOOK SYNC
    # ================================================================

    def _sync_outlook(
        self,
    ):

        self.sync_outlook_btn.setEnabled(
            False
        )

        self.sync_outlook_btn.setText(
            "⏳  Syncing..."
        )

        try:

            repo = get_repository()

            result = repo.sync_outlook()

            if not isinstance(
                result,
                dict,
            ):
                result = {
                    "status": "success",
                    "message": str(result),
                    "synced_count": 0,
                }

            status = result.get(
                "status"
            )

            message = result.get(
                "message",
                "Mailbox synchronization complete.",
            )

            now_str = (
                datetime.now()
                .strftime("%H:%M:%S")
            )

            if status == "success":

                synced_count = result.get(
                    "synced_count",
                    0,
                )

                self.sync_badge.setText(
                    f"● Synced ({now_str})"
                )

                QMessageBox.information(
                    self,
                    "Outlook Synchronized",
                    (
                        f"{message}\n\n"
                        f"New communications: {synced_count}"
                    ),
                )

            elif status == "not_configured":

                self.sync_badge.setText(
                    "○ Standby"
                )

                QMessageBox.information(
                    self,
                    "Outlook Notice",
                    (
                        f"{message}\n\n"
                        "Existing external intake items remain accessible."
                    ),
                )

            else:

                QMessageBox.warning(
                    self,
                    "Sync Issue",
                    message,
                )

            self.load_documents()

        except Exception as ex:

            QMessageBox.warning(
                self,
                "Sync Error",
                f"Could not complete Outlook sync:\n{ex}",
            )

        finally:

            self.sync_outlook_btn.setEnabled(
                True
            )

            self.sync_outlook_btn.setText(
                "↻  Sync Now"
            )

    # ================================================================
    # OPTIONAL BACKGROUND AUTO-SYNC
    # ================================================================

    def _background_autosync(
        self,
    ):

        try:

            repo = get_repository()

            result = repo.sync_outlook()

            if not isinstance(
                result,
                dict,
            ):
                return

            status = result.get(
                "status"
            )

            now_str = (
                datetime.now()
                .strftime("%H:%M:%S")
            )

            if status == "success":

                synced_count = result.get(
                    "synced_count",
                    0,
                )

                if synced_count > 0:

                    self.sync_badge.setText(
                        f"● Auto-Synced ({now_str})"
                    )

                    self.load_documents()

                else:

                    self.sync_badge.setText(
                        f"● Synced ({now_str})"
                    )

            elif status == "not_configured":

                self.sync_badge.setText(
                    "○ Standby"
                )

        except Exception:
            # Background sync must never break the Inbox UI.
            pass

    # ================================================================
    # COMPATIBILITY
    # ================================================================

    def load(
        self,
    ):
        """
        Compatibility alias.

        Some existing navigation/event code may call inbox.load().
        """
        self.load_documents()