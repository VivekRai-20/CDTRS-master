"""Dashboard for the active work context.

The counters come from the backend, which derives them from the active
context: the same person sees a different dashboard wearing their HOD hat than
wearing their Employee hat.  Nothing here is a percentage or an averaged
progress figure - the cards count things, and the table lists what needs
attention.
"""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from components.document_viewer import DocumentViewer
from core.context.context_manager import context_manager
from models.document import DocumentModel
from services.auth_service import auth_service
from services.dashboard_service import dashboard_service
from services.document_service import document_service
from components.notification_bell import (
    NotificationBellWidget
)

from components.notification_panel import (
    NotificationPanel
)
CARD_COLORS = ["#0369A1", "#1D4ED8", "#B45309", "#166534", "#7C3AED", "#B91C1C"]


class DashboardPage(QWidget):

    view_requested = Signal(object, str)
    navigate_requested = Signal(str, object)


    HEADERS = [
        "Reference", "Title / Subject", "Priority",
        "Lifecycle", "Workstreams & Stages", "Deadline",
    ]

    def __init__(self, user_role: str = "DS"):
        super().__init__()
        self.user_role = user_role
        self.documents: List[DocumentModel] = []
        self.viewer: Optional[DocumentViewer] = None
        self.notification_panel = None
        self._build()
        self._connect_events()

    def _connect_events(self) -> None:
        try:
            from services.event_bus import event_bus
            event_bus.document_updated.connect(self._on_workflow_changed)
        except Exception:
            pass
        try:
            context_manager.active_context_changed.connect(self._on_workflow_changed)
        except Exception:
            pass

    def showEvent(self, event):
        super().showEvent(event)
        self.load()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title = QLabel("Dashboard")
        self.title.setObjectName("pageTitle")
        titles.addWidget(self.title)
        self.subtitle = QLabel()
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setWordWrap(True)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)
        self.notification_bell = NotificationBellWidget()

        self.notification_bell.clicked.connect(
            self._toggle_notifications
        )

        header.addWidget(
            self.notification_bell,
            0,
            Qt.AlignmentFlag.AlignTop)

        refresh = QPushButton("Refresh")
        refresh.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        refresh.setStyleSheet(
            """
            QPushButton {
                background-color: #0F172A;
                color: white;
                font-weight: 600;
                padding: 7px 16px;
                border-radius: 4px;
            }

            QPushButton:hover {
                background-color: #1E293B;
            }

            QPushButton:pressed {
                background-color: #020617;
            }
            """
        )
        refresh.clicked.connect(self._refresh_all)
        header.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)

        self.cards_host = QWidget()
        self.cards_grid = QGridLayout(self.cards_host)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(12)
        layout.addWidget(self.cards_host)

        self.table_title = QLabel("Needs Attention")
        self.table_title.setObjectName("sectionTitle")
        self.table_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
        layout.addWidget(self.table_title)

        self.table = QTableWidget()
        self.table.setColumnCount(len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(self.open_document)

        header_view = self.table.horizontalHeader()
        for col in range(len(self.HEADERS)):
            header_view.setSectionResizeMode(
                col,
                QHeaderView.ResizeMode.Stretch if col in (1, 4)
                else QHeaderView.ResizeMode.ResizeToContents,
            )
        layout.addWidget(self.table, 1)

        self.empty_note = QLabel()
        self.empty_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_note.setStyleSheet("color: #94A3B8; font-size: 12px; padding: 16px;")
        self.empty_note.setVisible(False)
        layout.addWidget(self.empty_note)

    # ------------------------------------------------------------------

    def _card(self, label: str, value: Any, color: str) -> QFrame:
        card = QFrame()
        card.setObjectName("contentCard")
        card.setStyleSheet(
            "QFrame#contentCard { background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            f"border-left: 4px solid {color}; border-radius: 6px; }}"
        )
        inner = QVBoxLayout(card)
        inner.setContentsMargins(18, 14, 18, 14)
        inner.setSpacing(3)

        value_label = QLabel(str(value))
        value_label.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {color};")
        inner.addWidget(value_label)

        name = QLabel(label)
        name.setWordWrap(True)
        name.setStyleSheet("color: #475569; font-size: 11px; font-weight: 600;")
        inner.addWidget(name)
        return card

    def load(self) -> None:
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            # Layout items are not always widgets (spacers have none).
            if widget is not None:
                widget.hide()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        summary: Dict[str, Any] = {}
        try:
            summary = dashboard_service.get_summary() or {}
        except Exception as exc:
            QMessageBox.warning(self, "Dashboard", f"Could not load the dashboard.\n{exc}")

        context_type = summary.get("context_type") or self.user_role
        department = summary.get("department")

        user_name = ""
        try:
            user = auth_service.get_current_user()
            user_name = user.full_name if user else ""
        except Exception:
            pass

        self.title.setText(f"{context_type} Dashboard" if context_type else "Dashboard")
        self.subtitle.setText(
            (f"{user_name} - " if user_name else "")
            + f"working as {context_type}"
            + (f" ({department})" if department else "")
            + ". Switch context from the sidebar to see a different workspace."
        )

        cards = summary.get("cards") or []
        for index, card in enumerate(cards):
            color = CARD_COLORS[index % len(CARD_COLORS)]
            widget = self._card(card.get("label", ""), card.get("value", 0), color)
            self.cards_grid.addWidget(widget, index // 4, index % 4)

        raw_docs = summary.get("documents") or []
        self.documents = [
            d if isinstance(d, DocumentModel) else DocumentModel.from_dict(d) for d in raw_docs
        ]

        self.table.setRowCount(len(self.documents))
        for row, doc in enumerate(self.documents):
            self._set(row, 0, doc.reference)
            self._set(row, 1, doc.subject or doc.title)
            self._set(row, 2, str(doc.priority).title(), color=doc.priority_color, bold=True)
            self._set(row, 3, doc.lifecycle_label, color=doc.lifecycle_color, bold=True)
            self._set(row, 4, doc.branch_stage_cell, tooltip="\n".join(doc.branch_stage_lines))
            self._set(row, 5, doc.deadline_display, color=doc.deadline_color,
                      bold=doc.deadline_state in ("overdue", "due_soon"))
            lines = max(1, len(doc.branch_stage_lines))
            self.table.setRowHeight(row, 26 + (lines - 1) * 15)

        self.empty_note.setVisible(not self.documents)
        self.empty_note.setText("Nothing needs your attention in this work context right now.")

    def _set(self, row, col, text, color=None, bold=False, tooltip=None) -> None:
        cell = QTableWidgetItem(str(text or "-"))
        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
        cell.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if color:
            cell.setForeground(QBrush(QColor(color)))
        if bold:
            font = cell.font()
            font.setBold(True)
            cell.setFont(font)
        if tooltip:
            cell.setToolTip(tooltip)
        self.table.setItem(row, col, cell)

    def open_document(self) -> None:
        row = self.table.currentRow()
        if not (0 <= row < len(self.documents)):
            return
        doc = self.documents[row]
        self._show_document(doc, self.user_role)

    # Names the application shell calls.
    def refresh(self) -> None:
        self.load()

    def _show_document(self, doc, role: str) -> None:
        """Hand the document to the application shell when one is hosting this
        page; otherwise open it in its own window."""
        from services.document_service import document_service as _docs

        full = _docs.get_document(doc.id) or doc
        self.view_requested.emit(full, role)

    def _refresh_all(self) -> None:
        """Refresh dashboard data and notification state."""
        self.load()

        try:
            self.notification_bell.refresh()
        except Exception:
            pass

        try:
            if self.notification_panel is not None:
                self.notification_panel.refresh()
        except Exception:
            pass   

    def _on_workflow_changed(self, *_) -> None:
        """Bound method, not a lambda: Qt disconnects this when the
        widget is destroyed, so a stale page never reloads itself."""
        # Hidden pages reload in showEvent when they are opened; reloading
        # every page on each server event froze the window.
        if not self.isVisible():
            return
        self.load()

    def _toggle_notifications(self):

        if self.notification_panel is None:

            self.notification_panel = NotificationPanel(
                self
            )

        self.notification_panel.refresh()

        if self.notification_panel.isVisible():

            self.notification_panel.hide()

            return

        self.notification_panel.adjustSize()

        panel_width = (
            self.notification_panel.width()
        )

        x = (
            self.width()
            - panel_width
            - 28
        )

        y = 65

        self.notification_panel.move(
            x,
            y
        )

        self.notification_panel.show()
        self.notification_panel.raise_()