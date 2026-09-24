"""Document-wise Workflow History page.

Shows workflow history grouped by document instead of one large global table.
The left side lists documents; selecting a document shows its chronological
workflow timeline on the right.

Administrative/configuration audit activity remains outside this page.
"""

from collections import OrderedDict
from typing import List, Optional, Any

from PySide6.QtCore import Qt
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
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.context.context_manager import context_manager
from models import WorkflowEventModel
from services.document_service import document_service


class HistoryPage(QWidget):

    def __init__(self):
        super().__init__()
        self.events: List[WorkflowEventModel] = []
        self.document_groups = OrderedDict()
        self.selected_document_key = None
        self._build()

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
        self.load()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.setObjectName("historyPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(12)

        title = QLabel("Workflow History")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        self.subtitle = QLabel(
            "View the complete workflow history document by document."
        )
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        # Search/filter toolbar
        filters = QHBoxLayout()
        filters.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Search reference, title, person, workstream or event..."
        )
        self.search.setMinimumHeight(38)
        self.search.textChanged.connect(self.apply_filters)
        filters.addWidget(self.search, 3)

        self.event_filter = QComboBox()
        self.event_filter.addItem("All activity", None)
        for value, label in (
            ("BRANCH", "Routing"),
            ("WORK_ASSIGNED", "Assignments"),
            ("PROGRESS_UPDATED", "Progress updates"),
            ("WORK_", "Work activity"),
            ("DIRECTOR", "Director review"),
            ("REMARK", "Remarks"),
            ("ATTACHMENT", "Attachments"),
            ("DOCUMENT_", "Document lifecycle"),
        ):
            self.event_filter.addItem(label, value)
        self.event_filter.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.event_filter, 1)

        refresh = QPushButton("Refresh")
        refresh.setMinimumHeight(38)
        refresh.setStyleSheet(
            "QPushButton { background-color: #0F172A; color: white; "
            "font-weight: 600; padding: 6px 16px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #1E293B; }"
        )
        refresh.clicked.connect(self.load)
        filters.addWidget(refresh)

        layout.addLayout(filters)

        self.result_count = QLabel("0 documents")
        self.result_count.setStyleSheet(
            "color: #475569; font-size: 11px; font-weight: 600;"
        )
        layout.addWidget(self.result_count)

        # Main split: document list + selected document timeline
        main = QHBoxLayout()
        main.setSpacing(12)

        # Left document list
        self.document_scroll = QScrollArea()
        self.document_scroll.setWidgetResizable(True)
        self.document_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.document_scroll.setMinimumWidth(330)
        self.document_scroll.setMaximumWidth(420)
        self.document_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.document_container = QWidget()
        self.document_layout = QVBoxLayout(self.document_container)
        self.document_layout.setContentsMargins(0, 0, 5, 0)
        self.document_layout.setSpacing(8)
        self.document_layout.addStretch()

        self.document_scroll.setWidget(self.document_container)
        main.addWidget(self.document_scroll, 1)

        # Right history panel
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.detail_container = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_container)
        self.detail_layout.setContentsMargins(0, 0, 4, 0)
        self.detail_layout.setSpacing(10)

        self.detail_scroll.setWidget(self.detail_container)
        main.addWidget(self.detail_scroll, 3)

        layout.addLayout(main, 1)

    # ------------------------------------------------------------------
    # Safe model access
    # ------------------------------------------------------------------

    @staticmethod
    def _get(obj: Any, *names: str, default=None):
        for name in names:
            try:
                value = getattr(obj, name, None)
                if value is not None and value != "":
                    return value
            except Exception:
                pass
        return default

    def _document_key(self, event: WorkflowEventModel):
        """Get a stable document identifier from whatever the current model exposes."""
        return self._get(
            event,
            "document_id",
            "doc_id",
            "document_reference",
            "reference",
            default=None,
        )

    def _document_reference(self, event) -> str:
        return str(
            self._get(
                event,
                "document_reference",
                "reference",
                "document_ref",
                "document_id",
                "doc_id",
                default="Document",
            )
        )

    def _document_title(self, event) -> str:
        return str(
            self._get(
                event,
                "document_title",
                "title",
                "subject",
                "document_subject",
                default="Workflow history",
            )
        )

    def _event_time(self, event) -> str:
        value = self._get(
            event,
            "created_at",
            "timestamp",
            "event_time",
            "occurred_at",
            "created_on",
            default="",
        )
        if value is None:
            return ""
        return str(value)

    # ------------------------------------------------------------------
    # Loading/grouping
    # ------------------------------------------------------------------

    def load(self) -> None:
        try:
            self.events = document_service.get_all_history(limit=800)
        except Exception as exc:
            self.events = []
            QMessageBox.warning(
                self, "History", f"Could not load history.\n{exc}"
            )
            self._clear_document_views()
            return

        self.subtitle.setText(
            f"{len(self.events)} workflow event(s) across the documents "
            "you can see. Select a document to view its complete timeline."
        )

        self._group_events()
        self.apply_filters()

    def _group_events(self) -> None:
        groups = OrderedDict()

        for event in self.events:
            key = self._document_key(event)

            # If a model only exposes a document reference, that is still
            # sufficient to group the history correctly.
            if key is None:
                key = self._document_reference(event)

            if key not in groups:
                groups[key] = {
                    "key": key,
                    "reference": self._document_reference(event),
                    "title": self._document_title(event),
                    "events": [],
                }

            groups[key]["events"].append(event)

        # Newest document activity first.
        for group in groups.values():
            group["events"].sort(
                key=lambda e: self._event_time(e),
                reverse=True,
            )

        self.document_groups = groups

        if self.selected_document_key not in self.document_groups:
            self.selected_document_key = (
                next(iter(self.document_groups), None)
            )

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def apply_filters(self) -> None:
        text = self.search.text().strip().lower()
        prefix = self.event_filter.currentData()

        filtered = OrderedDict()

        for key, group in self.document_groups.items():
            matching_events = []

            for event in group["events"]:
                if prefix and prefix not in str(
                    self._get(event, "event_type", default="")
                ):
                    continue

                if text:
                    haystack = " ".join(
                        filter(
                            None,
                            [
                                group["reference"],
                                group["title"],
                                self._get(event, "summary", default=""),
                                self._get(event, "details", default=""),
                                self._get(event, "actor_name", default=""),
                                self._get(event, "branch_label", default=""),
                                self._get(event, "event_type", default=""),
                            ],
                        )
                    ).lower()

                    if text not in haystack:
                        continue

                matching_events.append(event)

            if matching_events:
                filtered[key] = {
                    **group,
                    "events": matching_events,
                }

        self._render_document_list(filtered)

        self.result_count.setText(
            f"{len(filtered)} document"
            f"{'' if len(filtered) == 1 else 's'}"
        )

        if not filtered:
            self._show_empty_detail(
                "No workflow history matches the current filters."
            )
            return

        if self.selected_document_key not in filtered:
            self.selected_document_key = next(iter(filtered))

        self._render_document_detail(
            filtered[self.selected_document_key]
        )

    # ------------------------------------------------------------------
    # Document list
    # ------------------------------------------------------------------

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _render_document_list(self, groups) -> None:
        self._clear_layout(self.document_layout)

        heading = QLabel("DOCUMENTS")
        heading.setStyleSheet(
            "color: #64748B; font-size: 10px; font-weight: 700; "
            "padding: 4px 6px;"
        )
        self.document_layout.addWidget(heading)

        for key, group in groups.items():
            self.document_layout.addWidget(
                self._document_list_card(group)
            )

        self.document_layout.addStretch()

    def _document_list_card(self, group) -> QFrame:
        selected = group["key"] == self.selected_document_key
        events = group["events"]

        card = QFrame()
        card.setObjectName("historyDocumentCard")
        card.setStyleSheet(
            "QFrame#historyDocumentCard { "
            "background: #FFFFFF; "
            "border: 1px solid #DCE5F0; "
            "border-radius: 9px; }"
            "QFrame#historyDocumentCard:hover { "
            "border: 1px solid #93C5FD; }"
        )

        outer = QVBoxLayout(card)
        outer.setContentsMargins(12, 11, 12, 11)
        outer.setSpacing(6)

        button = QToolButton()
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        button.setText("")
        button.setStyleSheet(
            "QToolButton { border: none; text-align: left; }"
        )

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)

        ref = QLabel(group["reference"])
        ref.setStyleSheet(
            "color: #1D4ED8; font-size: 10px; font-weight: 700;"
        )
        cl.addWidget(ref)

        title = QLabel(group["title"])
        title.setWordWrap(True)
        title.setStyleSheet(
            "color: #0F172A; font-size: 12px; font-weight: 700;"
        )
        cl.addWidget(title)

        meta = QLabel(
            f"{len(events)} event"
            f"{'' if len(events) == 1 else 's'}"
            f"  •  Latest: {self._event_time(events[0]) or '—'}"
        )
        meta.setStyleSheet(
            "color: #64748B; font-size: 9px;"
        )
        cl.addWidget(meta)

        button.setLayout(QVBoxLayout())
        button.layout().setContentsMargins(0, 0, 0, 0)
        button.layout().addWidget(content)

        if selected:
            card.setStyleSheet(
                "QFrame#historyDocumentCard { "
                "background: #EFF6FF; "
                "border: 1px solid #60A5FA; "
                "border-left: 4px solid #2563EB; "
                "border-radius: 9px; }"
            )

        button.clicked.connect(
            lambda _, k=group["key"]: self._select_document(k)
        )

        outer.addWidget(button)

        return card

    def _select_document(self, key) -> None:
        self.selected_document_key = key
        self.apply_filters()

    # ------------------------------------------------------------------
    # Detail / timeline
    # ------------------------------------------------------------------

    def _render_document_detail(self, group) -> None:
        self._clear_layout(self.detail_layout)

        header = QFrame()
        header.setObjectName("historyHeader")
        header.setStyleSheet(
            "QFrame#historyHeader { background: #FFFFFF; "
            "border: 1px solid #DCE5F0; border-radius: 10px; }"
        )

        hl = QVBoxLayout(header)
        hl.setContentsMargins(18, 15, 18, 15)
        hl.setSpacing(5)

        top = QHBoxLayout()

        icon = QLabel("▤")
        icon.setStyleSheet(
            "color: #2563EB; font-size: 25px; font-weight: 700;"
        )
        top.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)

        ref = QLabel(group["reference"])
        ref.setStyleSheet(
            "color: #334155; font-size: 10px; font-weight: 700;"
        )
        title_box.addWidget(ref)

        title = QLabel(group["title"])
        title.setWordWrap(True)
        title.setStyleSheet(
            "color: #0F172A; font-size: 16px; font-weight: 700;"
        )
        title_box.addWidget(title)

        top.addLayout(title_box, 1)

        count = QLabel(
            f"{len(group['events'])} events"
        )
        count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count.setStyleSheet(
            "background: #DBEAFE; color: #1D4ED8; "
            "padding: 6px 10px; border-radius: 12px; "
            "font-size: 9px; font-weight: 700;"
        )
        top.addWidget(count)

        hl.addLayout(top)

        sub = QLabel(
            "Complete document workflow history — newest activity first."
        )
        sub.setStyleSheet(
            "color: #64748B; font-size: 10px;"
        )
        hl.addWidget(sub)

        self.detail_layout.addWidget(header)

        timeline = QFrame()
        timeline.setStyleSheet("QFrame { background: transparent; }")
        tl = QVBoxLayout(timeline)
        tl.setContentsMargins(12, 6, 12, 12)
        tl.setSpacing(0)

        events = group["events"]

        for index, event in enumerate(events):
            tl.addWidget(
                self._timeline_event(
                    event,
                    first=(index == 0),
                    last=(index == len(events) - 1),
                )
            )

        self.detail_layout.addWidget(timeline)
        self.detail_layout.addStretch()

    def _event_style(self, event):
        event_type = str(
            self._get(event, "event_type", default="")
        ).upper()

        if "DIRECTOR" in event_type or "REVIEW" in event_type:
            return "#8B5CF6", "#EDE9FE"
        if "REMARK" in event_type:
            return "#EC4899", "#FCE7F3"
        if "PROGRESS" in event_type:
            return "#2563EB", "#DBEAFE"
        if "ATTACHMENT" in event_type:
            return "#059669", "#D1FAE5"
        if "ASSIGN" in event_type or "WORK_" in event_type:
            return "#F59E0B", "#FEF3C7"
        if "BRANCH" in event_type or "ROUT" in event_type:
            return "#0EA5E9", "#E0F2FE"
        return "#64748B", "#F1F5F9"

    def _event_icon(self, event) -> str:
        event_type = str(
            self._get(event, "event_type", default="")
        ).upper()

        if "ATTACHMENT" in event_type:
            return "📎"
        if "PROGRESS" in event_type:
            return "✎"
        if "REMARK" in event_type:
            return "▱"
        if "ASSIGN" in event_type:
            return "●"
        if "DIRECTOR" in event_type or "REVIEW" in event_type:
            return "◉"
        if "BRANCH" in event_type or "ROUT" in event_type:
            return "↗"
        return "▤"

    def _timeline_event(
        self,
        event,
        first: bool = False,
        last: bool = False,
    ) -> QWidget:
        wrapper = QWidget()
        row = QHBoxLayout(wrapper)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        # Timestamp
        time_box = QVBoxLayout()
        time_box.setContentsMargins(0, 7, 0, 0)
        time_box.setSpacing(1)

        when = self._event_time(event)
        when_label = QLabel(when or "—")
        when_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        when_label.setWordWrap(True)
        when_label.setFixedWidth(118)
        when_label.setStyleSheet(
            "color: #64748B; font-size: 9px; font-weight: 600;"
        )
        time_box.addWidget(when_label)
        time_box.addStretch()

        time_widget = QWidget()
        time_widget.setLayout(time_box)
        row.addWidget(time_widget)

        # Timeline marker
        color, light = self._event_style(event)

        marker_box = QVBoxLayout()
        marker_box.setContentsMargins(0, 0, 0, 0)
        marker_box.setSpacing(0)

        marker = QLabel(self._event_icon(event))
        marker.setFixedSize(34, 34)
        marker.setAlignment(Qt.AlignmentFlag.AlignCenter)
        marker.setStyleSheet(
            f"background: {light}; color: {color}; "
            "border: 1px solid #FFFFFF; border-radius: 17px; "
            "font-size: 13px; font-weight: 700;"
        )
        marker_box.addWidget(marker, 0, Qt.AlignmentFlag.AlignHCenter)

        if not last:
            line = QFrame()
            line.setFixedWidth(2)
            line.setSizePolicy(
                QSizePolicy.Policy.Fixed,
                QSizePolicy.Policy.Expanding,
            )
            line.setStyleSheet("background: #DCE5F0; border: none;")
            marker_box.addWidget(line, 1, Qt.AlignmentFlag.AlignHCenter)

        marker_widget = QWidget()
        marker_widget.setLayout(marker_box)
        marker_widget.setFixedWidth(42)
        row.addWidget(marker_widget)

        # Event card
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #FFFFFF; "
            "border: 1px solid #E2E8F0; border-radius: 8px; }"
        )

        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 9, 12, 9)
        cl.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(7)

        summary = str(
            self._get(event, "summary", default="Workflow activity")
        )
        summary_label = QLabel(summary)
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet(
            "color: #0F172A; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(summary_label, 1)

        branch = self._get(event, "branch_label", default="")
        if branch:
            branch_label = QLabel(str(branch))
            branch_label.setStyleSheet(
                f"background: {light}; color: {color}; "
                "padding: 4px 8px; border-radius: 10px; "
                "font-size: 8px; font-weight: 700;"
            )
            top.addWidget(branch_label)

        cl.addLayout(top)

        details = self._get(event, "details", default="")
        if details:
            detail_label = QLabel(str(details))
            detail_label.setWordWrap(True)
            detail_label.setStyleSheet(
                "color: #475569; font-size: 9px;"
            )
            cl.addWidget(detail_label)

        actor = self._get(event, "actor_name", default="")
        context = self._get(event, "context_type", "role", default="")
        actor_text = str(actor or "System")
        if context:
            actor_text += f"  •  {context}"

        actor_label = QLabel(actor_text)
        actor_label.setStyleSheet(
            "color: #64748B; font-size: 8px; font-weight: 600;"
        )
        cl.addWidget(actor_label)

        row.addWidget(card, 1)

        return wrapper

    def _show_empty_detail(self, text: str) -> None:
        self._clear_layout(self.detail_layout)

        frame = QFrame()
        frame.setStyleSheet(
            "QFrame { background: #FFFFFF; border: 1px solid #E2E8F0; "
            "border-radius: 10px; }"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(30, 40, 30, 40)

        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "color: #94A3B8; font-size: 12px;"
        )
        layout.addWidget(label)

        self.detail_layout.addWidget(frame)
        self.detail_layout.addStretch()

    def _clear_document_views(self) -> None:
        self._clear_layout(self.document_layout)
        self._clear_layout(self.detail_layout)

    # ------------------------------------------------------------------

    def load_history(self) -> None:
        self.load()

    def _on_workflow_changed(self, *_) -> None:
        # Hidden pages reload in showEvent when they are opened; reloading
        # every page on each server event froze the window.
        if not self.isVisible():
            return
        self.load()
