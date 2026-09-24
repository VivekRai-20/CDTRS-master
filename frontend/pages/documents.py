"""Documents page - redesigned document/workstream overview.

The page keeps the existing CDTRS visual language but replaces the dense
multi-column table with expandable document cards.  Each document shows its
lifecycle, priority, workstream count, deadline and last update at a glance.
Expanding a document reveals branch-specific stages, individual people/work
items, written progress updates and supporting attachments.

There is deliberately no percentage/combined-progress display.
"""

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.context.context_manager import context_manager
from models.document import DocumentModel
from services.auth_service import auth_service
from services.document_service import document_service


class DocumentsPage(QWidget):
    view_requested = Signal(object, str)

    def __init__(self, user_role: str = "DS"):
        super().__init__()
        self.user_role = user_role
        self.documents: List[DocumentModel] = []
        self._expanded_ids = set()
        self._build()
        self._connect_events()

    # ------------------------------------------------------------------

    def _connect_events(self) -> None:
        try:
            from services.event_bus import event_bus
            event_bus.document_updated.connect(self._on_workflow_changed)
        except Exception:
            pass

        try:
            context_manager.active_context_changed.connect(
                self._on_workflow_changed
            )
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.load_documents()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.setObjectName("documentsPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        self.title = QLabel("Documents")
        self.title.setObjectName("pageTitle")
        layout.addWidget(self.title)

        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        # Summary cards
        self.summary_row = QHBoxLayout()
        self.summary_row.setSpacing(10)
        layout.addLayout(self.summary_row)

        # Search / filters
        filters = QHBoxLayout()
        filters.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search documents, reference, sender or people..."
        )
        self.search.setMinimumHeight(38)
        self.search.textChanged.connect(self.apply_filters)
        filters.addWidget(self.search, 3)

        self.lifecycle_filter = QComboBox()
        self.lifecycle_filter.addItem("All lifecycles", None)
        for value, label in (
            ("RECEIVED", "Received"),
            ("REGISTERED", "Registered"),
            ("IN_REVIEW", "Under Director Review"),
            ("IN_WORK", "In Work"),
            ("WITH_DS", "With DS"),
            ("CLOSED", "Closed"),
        ):
            self.lifecycle_filter.addItem(label, value)
        self.lifecycle_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.lifecycle_filter, 1)

        self.priority_filter = QComboBox()
        self.priority_filter.addItem("All priorities", None)
        for value in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            self.priority_filter.addItem(value.title(), value)
        self.priority_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.priority_filter, 1)

        self.deadline_filter = QComboBox()
        self.deadline_filter.addItem("Any deadline", None)
        self.deadline_filter.addItem("Overdue", "overdue")
        self.deadline_filter.addItem("Due soon", "due_soon")
        self.deadline_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.deadline_filter, 1)

        self.mine_only = QComboBox()
        self.mine_only.addItem("All documents", False)
        self.mine_only.addItem("Only where I have open work", True)
        self.mine_only.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.mine_only, 1)

        clear = QPushButton("Clear")
        clear.setMinimumHeight(38)
        clear.clicked.connect(self.clear_filters)
        filters.addWidget(clear)

        refresh = QPushButton("Refresh")
        refresh.setMinimumHeight(38)
        refresh.setStyleSheet(
            "QPushButton { background-color: #0F172A; color: white; "
            "font-weight: 600; padding: 6px 16px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #1E293B; }"
        )
        refresh.clicked.connect(self.load_documents)
        filters.addWidget(refresh)

        layout.addLayout(filters)

        # Result count / sorting row
        result_row = QHBoxLayout()
        result_row.setContentsMargins(2, 2, 2, 0)

        self.result_count = QLabel("0 documents")
        self.result_count.setStyleSheet(
            "color: #475569; font-size: 12px; font-weight: 600;"
        )
        result_row.addWidget(self.result_count)
        result_row.addStretch()

        sort_label = QLabel("Sort by:")
        sort_label.setStyleSheet("color: #64748B; font-size: 11px;")
        result_row.addWidget(sort_label)

        self.sort_filter = QComboBox()
        self.sort_filter.addItem("Last Updated", "updated")
        self.sort_filter.addItem("Deadline", "deadline")
        self.sort_filter.addItem("Priority", "priority")
        self.sort_filter.addItem("Reference", "reference")
        self.sort_filter.setMinimumWidth(130)
        self.sort_filter.currentIndexChanged.connect(self.apply_filters)
        result_row.addWidget(self.sort_filter)

        layout.addLayout(result_row)

        # Scrollable document cards
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.card_container = QWidget()
        self.card_layout = QVBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(0, 0, 6, 0)
        self.card_layout.setSpacing(10)
        self.card_layout.addStretch()

        self.scroll.setWidget(self.card_container)
        layout.addWidget(self.scroll, 1)

        self.empty_note = QLabel()
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setStyleSheet(
            "color: #94A3B8; font-size: 12px; padding: 22px;"
        )
        self.empty_note.setVisible(False)
        layout.addWidget(self.empty_note, 1)

        hint = QLabel("Click a document to expand its workstreams, or use Open.")
        hint.setStyleSheet("color: #94A3B8; font-size: 10px;")
        layout.addWidget(hint)

    # ------------------------------------------------------------------

    def _summary_card(
        self, label: str, value: str, hint: str, color: str
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("summaryCard")
        card.setMaximumHeight(90)
        card.setStyleSheet(
            "QFrame#summaryCard { background: #FFFFFF; "
            "border: 1px solid #E2E8F0; border-radius: 9px; }"
        )

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 10, 14, 10)
        inner.setSpacing(2)

        value_label = QLabel(value)
        value_label.setStyleSheet(
            f"font-size: 20px; font-weight: 700; color: {color};"
        )
        inner.addWidget(value_label)

        name = QLabel(label)
        name.setStyleSheet(
            "color: #0F172A; font-size: 11px; font-weight: 700;"
        )
        inner.addWidget(name)

        sub = QLabel(hint)
        sub.setStyleSheet("color: #94A3B8; font-size: 9px;")
        inner.addWidget(sub)

        return card

    def _refresh_summary(self, documents: List[DocumentModel]) -> None:
        while self.summary_row.count():
            item = self.summary_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        open_docs = [d for d in documents if not d.is_closed]
        open_streams = sum(d.active_branch_count for d in documents)
        open_items = sum(d.open_work_item_count for d in documents)
        overdue = sum(
            1 for d in open_docs if d.deadline_state == "overdue"
        )

        cards = [
            ("Open Documents", str(len(open_docs)), "not yet closed", "#0369A1"),
            ("Open Workstreams", str(open_streams), "across all documents", "#1D4ED8"),
            ("Open Work Items", str(open_items), "individual assignments", "#B45309"),
            ("Overdue", str(overdue), "past their deadline", "#B91C1C"),
            ("Closed", str(len(documents) - len(open_docs)), "closed by DS", "#166534"),
        ]

        for label, value, hint, color in cards:
            self.summary_row.addWidget(
                self._summary_card(label, value, hint, color)
            )

        self.summary_row.addStretch()

    # ------------------------------------------------------------------
    # Document cards
    # ------------------------------------------------------------------

    @staticmethod
    def _badge(
        text: str,
        background: str,
        foreground: str = "#0F172A",
        border: Optional[str] = None,
    ) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "QLabel { "
            f"background: {background}; color: {foreground}; "
            "padding: 5px 10px; border-radius: 11px; "
            f"border: 1px solid {border or background}; "
            "font-size: 10px; font-weight: 700; }"
        )
        return label

    def _priority_badge(self, doc: DocumentModel) -> QLabel:
        priority = str(doc.priority or "MEDIUM").upper()
        styles = {
            "CRITICAL": ("#FEE2E2", "#B91C1C", "#FECACA"),
            "HIGH": ("#FFEDD5", "#C2410C", "#FED7AA"),
            "MEDIUM": ("#FEF3C7", "#B45309", "#FDE68A"),
            "LOW": ("#DCFCE7", "#166534", "#BBF7D0"),
        }
        bg, fg, border = styles.get(
            priority, ("#F1F5F9", "#475569", "#E2E8F0")
        )
        return self._badge(priority.title(), bg, fg, border)

    def _lifecycle_badge(self, doc: DocumentModel) -> QLabel:
        lifecycle = str(doc.lifecycle or "RECEIVED").upper()
        styles = {
            "RECEIVED": ("#F1F5F9", "#475569"),
            "REGISTERED": ("#CCFBF1", "#0F766E"),
            "IN_REVIEW": ("#EDE9FE", "#6D28D9"),
            "IN_WORK": ("#DBEAFE", "#1D4ED8"),
            "WITH_DS": ("#FEF3C7", "#B45309"),
            "CLOSED": ("#DCFCE7", "#166534"),
        }
        bg, fg = styles.get(lifecycle, ("#F1F5F9", "#475569"))
        return self._badge(doc.lifecycle_label or lifecycle.title(), bg, fg)

    def _stage_badge(self, stage: str, active: bool = True) -> QLabel:
        value = (stage or "Not specified").strip()
        lower = value.lower()

        if "complete" in lower or "closed" in lower:
            bg, fg = "#DCFCE7", "#166534"
        elif "return" in lower or "waiting" in lower or "overdue" in lower:
            bg, fg = "#FEF3C7", "#92400E"
        elif "review" in lower:
            bg, fg = "#EDE9FE", "#6D28D9"
        elif "progress" in lower or "work" in lower:
            bg, fg = "#DBEAFE", "#1D4ED8"
        elif not active:
            bg, fg = "#F1F5F9", "#64748B"
        else:
            bg, fg = "#F1F5F9", "#475569"

        return self._badge(value, bg, fg)

    def _small_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            "color: #64748B; font-size: 10px; font-weight: 600;"
        )
        return label

    def _value_label(self, text: str, bold: bool = False) -> QLabel:
        label = QLabel(text or "—")
        label.setWordWrap(True)
        label.setStyleSheet(
            "color: #0F172A; "
            f"font-size: 11px; font-weight: {'700' if bold else '500'};"
        )
        return label

    def _document_card(self, doc: DocumentModel) -> QFrame:
        expanded = doc.id in self._expanded_ids

        card = QFrame()
        card.setObjectName("documentCard")
        card.setStyleSheet(
            "QFrame#documentCard { background: #FFFFFF; "
            "border: 1px solid #DCE5F0; border-radius: 10px; }"
            "QFrame#documentCard:hover { border: 1px solid #93C5FD; }"
        )

        outer = QVBoxLayout(card)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(9)

        # Header row
        header = QHBoxLayout()
        header.setSpacing(10)

        expand = QToolButton()
        expand.setText("⌄" if expanded else "›")
        expand.setCheckable(True)
        expand.setChecked(expanded)
        expand.setFixedSize(28, 28)
        expand.setStyleSheet(
            "QToolButton { border: none; color: #1D4ED8; "
            "font-size: 22px; font-weight: 700; }"
            "QToolButton:hover { background: #EFF6FF; border-radius: 14px; }"
        )
        expand.clicked.connect(
            lambda checked, d=doc: self._toggle_document(d)
        )
        header.addWidget(expand)

        icon = QLabel("▤")
        icon.setFixedWidth(24)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            "color: #2563EB; font-size: 21px; font-weight: 700;"
        )
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)

        ref = QLabel(doc.reference)
        ref.setStyleSheet(
            "color: #334155; font-size: 10px; font-weight: 700;"
        )
        title_box.addWidget(ref)

        title = QLabel(doc.subject or doc.title or "Untitled document")
        title.setWordWrap(True)
        title.setStyleSheet(
            "color: #0F172A; font-size: 13px; font-weight: 700;"
        )
        title_box.addWidget(title)

        meta_parts = []
        if doc.source:
            meta_parts.append(f"From: {doc.source}")
        if doc.received_display:
            meta_parts.append(f"Received: {doc.received_display}")

        if meta_parts:
            meta = QLabel("  •  ".join(meta_parts))
            meta.setStyleSheet("color: #64748B; font-size: 9px;")
            title_box.addWidget(meta)

        header.addLayout(title_box, 4)

        header.addWidget(self._priority_badge(doc))
        header.addWidget(self._lifecycle_badge(doc))

        stream_box = QVBoxLayout()
        stream_box.setSpacing(0)
        stream_count = QLabel(str(len(doc.branch_summaries)))
        stream_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stream_count.setStyleSheet(
            "color: #1D4ED8; font-size: 15px; font-weight: 700;"
        )
        stream_box.addWidget(stream_count)

        stream_label = QLabel(
            "Workstream" if len(doc.branch_summaries) == 1 else "Workstreams"
        )
        stream_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stream_label.setStyleSheet("color: #64748B; font-size: 9px;")
        stream_box.addWidget(stream_label)

        stream_widget = QWidget()
        stream_widget.setLayout(stream_box)
        header.addWidget(stream_widget)

        deadline_box = QVBoxLayout()
        deadline_box.setSpacing(1)

        deadline_title = QLabel(
            "Deadline" if doc.deadline else "Deadline"
        )
        deadline_title.setStyleSheet(
            "color: #64748B; font-size: 9px; font-weight: 600;"
        )
        deadline_box.addWidget(deadline_title)

        deadline = QLabel(doc.deadline_display if doc.deadline else "—")
        deadline.setStyleSheet(
            f"color: {doc.deadline_color if doc.deadline else '#475569'}; "
            "font-size: 10px; font-weight: 700;"
        )
        deadline_box.addWidget(deadline)

        if doc.deadline_label:
            state = QLabel(doc.deadline_label)
            state.setStyleSheet(
                f"color: {doc.deadline_color}; font-size: 8px;"
            )
            deadline_box.addWidget(state)

        deadline_widget = QWidget()
        deadline_widget.setLayout(deadline_box)
        header.addWidget(deadline_widget)

        updated_box = QVBoxLayout()
        updated_box.setSpacing(1)

        updated_label = QLabel("Last updated")
        updated_label.setStyleSheet(
            "color: #64748B; font-size: 9px; font-weight: 600;"
        )
        updated_box.addWidget(updated_label)

        updated = QLabel(doc.updated_display or "—")
        updated.setStyleSheet(
            "color: #334155; font-size: 9px; font-weight: 600;"
        )
        updated_box.addWidget(updated)

        updated_widget = QWidget()
        updated_widget.setLayout(updated_box)
        header.addWidget(updated_widget)

        open_btn = QPushButton("Open")
        open_btn.setFixedHeight(34)
        open_btn.setMinimumWidth(76)
        open_btn.setStyleSheet(
            "QPushButton { background: #2563EB; color: white; "
            "border: none; border-radius: 6px; padding: 5px 14px; "
            "font-weight: 700; font-size: 10px; }"
            "QPushButton:hover { background: #1D4ED8; }"
        )
        open_btn.clicked.connect(lambda _, d=doc: self.open_document(d))
        header.addWidget(open_btn)

        outer.addLayout(header)

        if expanded:
            outer.addWidget(self._expanded_document_content(doc))

        return card

    def _section_card(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("innerCard")
        frame.setStyleSheet(
            "QFrame#innerCard { background: #F8FAFC; "
            "border: 1px solid #E2E8F0; border-radius: 8px; }"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        heading = QLabel(title)
        heading.setStyleSheet(
            "color: #0F172A; font-size: 11px; font-weight: 700;"
        )
        layout.addWidget(heading)

        return frame

    def _expanded_document_content(self, doc: DocumentModel) -> QWidget:
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(8, 2, 8, 2)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        
        # Use proportional sizing instead of arbitrary fixed widths
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        # Document details
        details = self._section_card("Document Details")
        dl = details.layout()

        detail_rows = [
            ("Reference", doc.reference),
            ("Title / Subject", doc.subject or doc.title),
            ("Source", doc.source or "—"),
            ("Sender", doc.sender_name or "—"),
            ("Received", doc.received_display or "—"),
            ("Priority", str(doc.priority or "—").title()),
            ("Lifecycle", doc.lifecycle_label or doc.lifecycle),
            ("Deadline", doc.deadline_display if doc.deadline else "—"),
            ("Last update", doc.updated_display or "—"),
        ]

        for name, value in detail_rows:
            row = QHBoxLayout()
            row.setSpacing(8)
            lab = QLabel(name)
            lab.setMinimumWidth(90)
            lab.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
            lab.setStyleSheet("color: #64748B; font-size: 9px;")
            val = self._value_label(value, bold=True)
            row.addWidget(lab)
            row.addWidget(val, 1)
            dl.addLayout(row)

        dl.addStretch()
        grid.addWidget(details, 0, 0)

        # Workstreams
        workstreams = self._section_card("Workstreams & Current Stage")
        wl = workstreams.layout()

        branches = list(doc.branch_summaries or [])
        if not branches:
            note = QLabel("No workstreams have been created yet.")
            note.setStyleSheet("color: #94A3B8; font-size: 10px;")
            wl.addWidget(note)
        else:
            for summary in branches:
                branch_frame = QFrame()
                branch_frame.setStyleSheet(
                    "QFrame { background: white; border: 1px solid #E2E8F0; "
                    "border-radius: 7px; }"
                )
                bl = QVBoxLayout(branch_frame)
                bl.setContentsMargins(9, 8, 9, 8)
                bl.setSpacing(4)

                top = QHBoxLayout()
                branch_name = QLabel(
                    summary.label or summary.branch_type or "Workstream"
                )
                branch_name.setStyleSheet(
                    "color: #0F172A; font-size: 10px; font-weight: 700;"
                )
                top.addWidget(branch_name)
                top.addStretch()
                top.addWidget(
                    self._stage_badge(
                        summary.stage_label or summary.stage,
                        summary.is_active,
                    )
                )
                bl.addLayout(top)

                people = ", ".join(summary.people or [])
                if people:
                    p = QLabel(f"People: {people}")
                    p.setWordWrap(True)
                    p.setStyleSheet("color: #64748B; font-size: 9px;")
                    bl.addWidget(p)

                if summary.open_items or summary.total_items:
                    count = QLabel(
                        f"{summary.open_items} open work item"
                        f"{'' if summary.open_items == 1 else 's'}"
                        f"  •  {summary.total_items} total"
                    )
                    count.setStyleSheet(
                        "color: #64748B; font-size: 8px;"
                    )
                    bl.addWidget(count)

                wl.addWidget(branch_frame)

        wl.addStretch()
        grid.addWidget(workstreams, 0, 1)

        # People / individual work
        people_card = self._section_card("People & Individual Work")
        pl = people_card.layout()

        work_items = list(doc.all_work_items or [])
        if not work_items:
            people = list(doc.people_involved or [])
            if people:
                for person in people:
                    p = QLabel(f"• {person}")
                    p.setStyleSheet(
                        "color: #334155; font-size: 10px;"
                    )
                    pl.addWidget(p)
            else:
                note = QLabel("No individual work items yet.")
                note.setStyleSheet(
                    "color: #94A3B8; font-size: 10px;"
                )
                pl.addWidget(note)
        else:
            for item in work_items:
                person_frame = QFrame()
                person_frame.setStyleSheet(
                    "QFrame { background: white; border: 1px solid #E2E8F0; "
                    "border-radius: 7px; }"
                )
                il = QVBoxLayout(person_frame)
                il.setContentsMargins(9, 8, 9, 8)
                il.setSpacing(4)

                top = QHBoxLayout()

                person_name = QLabel(
                    item.assignee_name or "Unassigned"
                )
                person_name.setStyleSheet(
                    "color: #0F172A; font-size: 10px; font-weight: 700;"
                )
                top.addWidget(person_name)
                top.addStretch()
                top.addWidget(
                    self._stage_badge(
                        item.stage_label or item.stage,
                        item.is_active,
                    )
                )
                il.addLayout(top)

                role_parts = [
                    x for x in (
                        item.context_type,
                        item.department_name,
                        item.team_name,
                    ) if x
                ]
                if role_parts:
                    role = QLabel(" • ".join(role_parts))
                    role.setWordWrap(True)
                    role.setStyleSheet(
                        "color: #64748B; font-size: 8px;"
                    )
                    il.addWidget(role)

                if item.instructions:
                    instructions = QLabel(
                        f"Assignment: {item.instructions}"
                    )
                    instructions.setWordWrap(True)
                    instructions.setStyleSheet(
                        "color: #475569; font-size: 9px;"
                    )
                    il.addWidget(instructions)

                if item.latest_progress_text:
                    progress = QLabel(
                        f"Latest progress: {item.latest_progress_text}"
                    )
                    progress.setWordWrap(True)
                    progress.setStyleSheet(
                        "color: #334155; font-size: 9px;"
                    )
                    il.addWidget(progress)

                attachment_text = ""
                if item.attachment_count:
                    attachment_text = (
                        f"Attachments: {item.attachment_count}"
                    )

                if attachment_text:
                    attach = QLabel(f"📎 {attachment_text}")
                    attach.setStyleSheet(
                        "color: #1D4ED8; font-size: 8px; font-weight: 600;"
                    )
                    il.addWidget(attach)

                if item.last_update_at:
                    update = QLabel(
                        f"Updated: {item.last_update_at}"
                    )
                    update.setStyleSheet(
                        "color: #94A3B8; font-size: 8px;"
                    )
                    il.addWidget(update)

                pl.addWidget(person_frame)

        pl.addStretch()
        grid.addWidget(people_card, 0, 2)

        # Recent Director remark / workflow information
        bottom = QHBoxLayout()
        bottom.setSpacing(10)

        if doc.latest_director_remark:
            remark = self._section_card("Latest Director Remark")
            rl = remark.layout()

            rtext = QLabel(doc.latest_director_remark)
            rtext.setWordWrap(True)
            rtext.setStyleSheet(
                "color: #334155; font-size: 9px; line-height: 1.4;"
            )
            rl.addWidget(rtext)
            bottom.addWidget(remark, 2)

        history = self._section_card("Workflow Snapshot")
        hl = history.layout()

        history_items = list(doc.history or [])
        if history_items:
            for event in history_items[-4:][::-1]:
                line = QFrame()
                ll = QHBoxLayout(line)
                ll.setContentsMargins(0, 2, 0, 2)
                ll.setSpacing(6)

                dot = QLabel("●")
                dot.setStyleSheet("color: #2563EB; font-size: 7px;")
                ll.addWidget(dot)

                text = QLabel(
                    f"{event.summary or event.event_type}  "
                    f"— {event.actor_name or 'System'}"
                )
                text.setWordWrap(True)
                text.setStyleSheet(
                    "color: #475569; font-size: 8px;"
                )
                ll.addWidget(text, 1)
                hl.addWidget(line)
        else:
            note = QLabel("No workflow history available.")
            note.setStyleSheet("color: #94A3B8; font-size: 9px;")
            hl.addWidget(note)

        bottom.addWidget(history, 3)

        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom)
        grid.addWidget(bottom_widget, 1, 0, 1, 3)

        # Action row
        actions = QHBoxLayout()
        actions.addStretch()

        open_full = QPushButton("Open Full Document")
        open_full.setMinimumHeight(34)
        open_full.setStyleSheet(
            "QPushButton { background: #0F172A; color: white; "
            "border: none; border-radius: 6px; padding: 6px 15px; "
            "font-weight: 700; font-size: 10px; }"
            "QPushButton:hover { background: #1E293B; }"
        )
        open_full.clicked.connect(lambda _, d=doc: self.open_document(d))
        actions.addWidget(open_full)

        workflow_btn = QPushButton("View Workflow")
        workflow_btn.setMinimumHeight(34)
        workflow_btn.setStyleSheet(
            "QPushButton { background: #EFF6FF; color: #1D4ED8; "
            "border: 1px solid #BFDBFE; border-radius: 6px; "
            "padding: 6px 15px; font-weight: 700; font-size: 10px; }"
            "QPushButton:hover { background: #DBEAFE; }"
        )
        workflow_btn.clicked.connect(
            lambda _, d=doc: self.open_document(d)
        )
        actions.addWidget(workflow_btn)

        grid.addLayout(actions, 2, 0, 1, 3)

        return content

    def _toggle_document(self, doc: DocumentModel) -> None:
        if doc.id in self._expanded_ids:
            self._expanded_ids.remove(doc.id)
        else:
            self._expanded_ids.add(doc.id)
        self.apply_filters()

    # ------------------------------------------------------------------
    # Loading / filtering
    # ------------------------------------------------------------------

    def load_documents(self) -> None:
        try:
            self.documents = document_service.get_documents()
        except Exception as exc:
            self.documents = []
            QMessageBox.warning(
                self, "Documents", f"Could not load documents.\n{exc}"
            )

        context_label = ""
        try:
            ctype = context_manager.active_context_type(self.user_role)
            dept = context_manager.active_department_name()
            context_label = f"{ctype}" + (f" - {dept}" if dept else "")
        except Exception:
            pass

        self.subtitle.setText(
            f"Working as: {context_label}. "
            "Each document can contain multiple workstreams, with each "
            "branch and individual work item at its own stage."
            if context_label
            else
            "Each document can contain multiple workstreams, with each "
            "branch and individual work item at its own stage."
        )

        self._refresh_summary(self.documents)
        self.apply_filters()

    def _sort_documents(
        self, documents: List[DocumentModel]
    ) -> List[DocumentModel]:
        mode = self.sort_filter.currentData()

        if mode == "deadline":
            return sorted(
                documents,
                key=lambda d: (
                    d.deadline is None,
                    d.deadline or "9999-12-31",
                ),
            )

        if mode == "priority":
            order = {
                "CRITICAL": 0,
                "HIGH": 1,
                "MEDIUM": 2,
                "LOW": 3,
            }
            return sorted(
                documents,
                key=lambda d: order.get(
                    str(d.priority).upper(), 9
                ),
            )

        if mode == "reference":
            return sorted(
                documents,
                key=lambda d: d.reference.lower()
            )

        return sorted(
            documents,
            key=lambda d: d.updated_at or "",
            reverse=True,
        )

    def apply_filters(self) -> None:
        text = self.search.text().strip().lower()
        lifecycle = self.lifecycle_filter.currentData()
        priority = self.priority_filter.currentData()
        deadline = self.deadline_filter.currentData()
        mine_only = bool(self.mine_only.currentData())

        user = None
        try:
            user = auth_service.get_current_user()
        except Exception:
            pass

        user_id = user.id if user else None
        context_id = None

        try:
            context_id = context_manager.active_membership_id()
        except Exception:
            pass

        results: List[DocumentModel] = []

        for doc in self.documents:
            if lifecycle and doc.lifecycle != lifecycle:
                continue

            if priority and str(doc.priority).upper() != priority:
                continue

            if deadline and doc.deadline_state != deadline:
                continue

            if mine_only:
                mine = [
                    w
                    for w in doc.work_items_for_user(
                        user_id, context_id
                    )
                    if not w.is_finished
                ]
                if not mine and not doc.my_work_items:
                    continue

            if text:
                haystack = " ".join(
                    filter(
                        None,
                        [
                            doc.reference,
                            doc.title,
                            doc.subject,
                            doc.sender_name,
                            doc.source,
                            " ".join(doc.people_involved),
                            " ".join(doc.branch_stage_lines),
                            " ".join(
                                w.latest_progress_text or ""
                                for w in doc.all_work_items
                            ),
                        ],
                    )
                ).lower()

                if text not in haystack:
                    continue

            results.append(doc)

        results = self._sort_documents(results)

        # Rebuild cards.
        while self.card_layout.count():
            item = self.card_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        for doc in results:
            self.card_layout.addWidget(self._document_card(doc))

        self.card_layout.addStretch()

        self.result_count.setText(
            f"{len(results)} document{'s' if len(results) != 1 else ''} found"
        )

        self.empty_note.setVisible(not results)
        self.scroll.setVisible(bool(results))

        self.empty_note.setText(
            "No documents match these filters."
            if self.documents
            else
            "No documents are visible in this work context yet."
        )

    def clear_filters(self) -> None:
        self.search.clear()
        self.lifecycle_filter.setCurrentIndex(0)
        self.priority_filter.setCurrentIndex(0)
        self.deadline_filter.setCurrentIndex(0)
        self.mine_only.setCurrentIndex(0)
        self.sort_filter.setCurrentIndex(0)
        self.apply_filters()

    def set_filters(self, **filters) -> None:
        """Compatibility helper used by MainWindow navigation."""
        mapping = {
            "lifecycle": self.lifecycle_filter,
            "priority": self.priority_filter,
            "deadline": self.deadline_filter,
        }

        if "search" in filters:
            self.search.setText(str(filters["search"] or ""))

        for key, combo in mapping.items():
            if key not in filters:
                continue
            wanted = filters[key]
            for index in range(combo.count()):
                if combo.itemData(index) == wanted:
                    combo.setCurrentIndex(index)
                    break

        self.apply_filters()

    # ------------------------------------------------------------------
    # Open document
    # ------------------------------------------------------------------

    def open_document(self, document: Optional[DocumentModel] = None) -> None:
        doc = document

        if doc is None:
            QMessageBox.information(
                self,
                "Documents",
                "Select or open a document first.",
            )
            return

        self._show_document(doc, self.user_role)

    def view_document(self, *args) -> None:
        self.open_document()

    def on_document_selected(self, *args) -> None:
        pass

    def _show_document(self, doc, role: str) -> None:
        """Hand the document to the application shell."""
        from services.document_service import document_service as _docs

        full = _docs.get_document(doc.id) or doc
        self.view_requested.emit(full, role)

    def _on_workflow_changed(self, *_) -> None:
        self.load_documents()
