"""Document viewer.

The screen where the workflow becomes legible:

    Document header      lifecycle, priority, deadline
    Preview + details    the file, and the metadata the DS can correct
    Director reviews     every review, kept separately, newest last
    Workstreams          one card per branch, each at its OWN stage,
                         each containing one card per PERSON
    Remarks              append-only, scoped to the workstream they belong to
    History              the complete chronological record

Actions are decided by the active work context, not by the account's nominal
role: the same person sees HOD controls in their HOD context and worker
controls in their Employee context.
"""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from components.branch_panel import BranchCard, badge, outline_badge
from components.document_info import DocumentInfo
from components.document_preview import DocumentPreview
from components.routing_dialogs import (
    AssignWorkDialog,
    CloseDocumentDialog,
    DirectorReviewDialog,
    EditDocumentDialog,
    ProgressDialog,
    RemarkDialog,
    ReminderDialog,
    ReminderDialog as _ReminderDialog,
    RoutingDialog,
    StageDialog,
    SubmitWorkDialog,
    WorkReviewDialog,
)
from core.context.context_manager import context_manager
from models import DocumentModel, WorkItemModel
from services.auth_service import auth_service
from services.document_service import document_service
from services.routing_service import routing_service
from services.work_service import work_service


def _section_title(text: str, hint: str = "") -> QWidget:
    holder = QWidget()
    layout = QVBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    title = QLabel(text)
    title.setObjectName("sectionTitle")
    title.setStyleSheet("font-size: 13px; font-weight: 700; color: #0F172A;")
    layout.addWidget(title)

    if hint:
        sub = QLabel(hint)
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #64748B; font-size: 10px;")
        layout.addWidget(sub)
    return holder


class DocumentViewer(QWidget):
    """Full view of one document for the active work context."""

    close_requested = Signal()
    document_updated = Signal(object)
    # Kept so callers that open the viewer as a window can listen too.
    document_changed = Signal(int)

    def __init__(
        self,
        document: Optional[DocumentModel] = None,
        role: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.document = document or DocumentModel()
        self._context_type = ""
        self._context_id: Optional[int] = None
        self._context_department_id: Optional[int] = None
        self._user_id: Optional[int] = None

        self._sync_context(role)
        self._build()
        if self.document and self.document.id:
            self.refresh()

    # ==================================================================
    # CONTEXT
    # ==================================================================

    def _sync_context(self, fallback_role: Optional[str] = None) -> None:
        """Read the active hat.  Everything this screen offers follows from it."""
        try:
            self._context_type = context_manager.active_context_type(fallback_role) or ""
            self._context_id = context_manager.active_membership_id()
            self._context_department_id = context_manager.active_department_id()
        except Exception:
            self._context_type = (fallback_role or "").upper()
            self._context_id = None
            self._context_department_id = None
        try:
            user = auth_service.get_current_user()
            self._user_id = user.id if user else None
        except Exception:
            self._user_id = None

    @property
    def is_ds(self) -> bool:
        return self._context_type == "DS"

    @property
    def is_director(self) -> bool:
        return self._context_type == "DIRECTOR"

    @property
    def is_hod(self) -> bool:
        return self._context_type == "HOD"

    @property
    def is_worker(self) -> bool:
        return self._context_type in ("EMPLOYEE", "TSO")

    # ==================================================================
    # LAYOUT
    # ==================================================================

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(12)

        # ---- header ----
        header = QHBoxLayout()
        header.setSpacing(12)

        self.back_btn = QPushButton("← Back")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.setStyleSheet(
            "background-color: transparent; color: #0F172A; border: none; "
            "font-weight: 600; font-size: 12px; padding: 4px 6px;"
        )
        self.back_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(self.back_btn, 0, Qt.AlignmentFlag.AlignTop)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("pageTitle")
        self.title_label.setWordWrap(True)
        self.ref_label = QLabel()
        self.ref_label.setObjectName("pageSubtitle")
        titles.addWidget(self.title_label)
        titles.addWidget(self.ref_label)
        header.addLayout(titles, 1)

        self.badge_row = QWidget()
        self.badge_layout = QHBoxLayout(self.badge_row)
        self.badge_layout.setContentsMargins(0, 0, 0, 0)
        self.badge_layout.setSpacing(6)
        self.badge_layout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.badge_row)
        root.addLayout(header)

        # ---- scrollable body ----
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 4, 4, 10)
        self.body_layout.setSpacing(14)

        self.top_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.setHandleWidth(8)
        self.preview = DocumentPreview(self.document)
        self.info = DocumentInfo(self.document)
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.info.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.top_splitter.addWidget(self.preview)
        self.top_splitter.addWidget(self.info)
        self.top_splitter.setStretchFactor(0, 1)
        self.top_splitter.setStretchFactor(1, 1)
        self.body_layout.addWidget(self.top_splitter)

        # Sections rebuilt on every refresh.
        self.ocr_review_section = self._make_section()
        self.body_layout.addWidget(self.ocr_review_section["frame"])
        self.director_section = self._make_section()
        self.branches_section = self._make_section()
        self.remarks_section = self._make_section()
        self.history_section = self._make_section()
        for section in (
            self.director_section, self.branches_section,
            self.remarks_section, self.history_section,
        ):
            self.body_layout.addWidget(section["frame"])

        self.body_layout.addStretch()
        self.scroll.setWidget(self.body)
        root.addWidget(self.scroll, 1)

        # ---- action bar ----
        self.action_bar = QWidget()
        self.action_layout = QHBoxLayout(self.action_bar)
        self.action_layout.setContentsMargins(0, 6, 0, 0)
        self.action_layout.setSpacing(8)
        root.addWidget(self.action_bar)

    def _make_section(self) -> Dict[str, Any]:
        frame = QFrame()
        frame.setObjectName("contentCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        return {"frame": frame, "layout": layout}

    @staticmethod
    def _clear(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
            elif item.layout() is not None:
                DocumentViewer._clear(item.layout())

    # ==================================================================
    # DATA
    # ==================================================================

    def set_document(self, document: DocumentModel) -> None:
        self.document = document
        self.refresh()

    def refresh(self, reload_from_server: bool = True) -> None:
        """Re-read the document and redraw every section."""
        self._sync_context()
        if reload_from_server and self.document and self.document.id:
            try:
                fresh = document_service.get_document(self.document.id)
                if fresh:
                    self.document = fresh
            except Exception as exc:
                QMessageBox.warning(self, "Document", f"Could not reload the document.\n{exc}")

        self._render_header()
        try:
            self.preview.set_document(self.document)
        except Exception:
            pass
        try:
            self.info.update_document(self.document)
        except Exception:
            pass
        self._render_ocr_verification()
        self._render_director_reviews()
        self._render_branches()
        self._render_remarks()
        self._render_history()
        self._render_actions()

    # ==================================================================
    # RENDERING
    # ==================================================================

    def _render_header(self) -> None:
        doc = self.document
        self.title_label.setText(doc.title or "Untitled Document")
        bits = [doc.reference]
        if doc.sender_name:
            bits.append(doc.sender_name)
        bits.append(f"Received {doc.received_display}")
        self.ref_label.setText("   •   ".join(bits))

        self._clear(self.badge_layout)
        self.badge_layout.addWidget(badge(doc.lifecycle_label, doc.lifecycle_color))
        self.badge_layout.addWidget(outline_badge(str(doc.priority).title(), doc.priority_color))
        if doc.deadline and doc.deadline_state != "none":
            self.badge_layout.addWidget(
                outline_badge(f"Due {doc.deadline_display}", doc.deadline_color)
            )
        if doc.active_branch_count:
            self.badge_layout.addWidget(
                outline_badge(f"{doc.active_branch_count} open workstream(s)", "#0369A1")
            )

    # ---- OCR: prior Director review (DS verification) ----

    _PRIOR_REVIEW_FIELD = "PRIOR_DIRECTOR_REVIEW_DETECTED"
    _DIRECTOR_REMARK_FIELD = "DIRECTOR_HANDWRITTEN_REMARK"

    @staticmethod
    def _is_true(value: Any) -> bool:
        return str(value or "").strip().lower() in {"true", "1", "yes", "detected", "confirmed"}

    def _render_ocr_verification(self) -> None:
        """Let the DS confirm (or reject) a Director instruction that OCR found
        on the document.  Only the DS-verified value lets the workflow skip the
        Director review step; the raw OCR detection never does."""
        section = self.ocr_review_section
        layout = section["layout"]
        self._clear(layout)
        section["frame"].setVisible(False)

        doc = self.document
        if not self.is_ds or not doc or not doc.id or doc.is_closed:
            return
        try:
            ocr = document_service.get_ocr_result(doc.id) or {}
        except Exception:
            return
        fields = {
            str(f.get("field_name", "")).upper(): f
            for f in (ocr.get("fields") or [])
            if isinstance(f, dict)
        }
        flag = fields.get(self._PRIOR_REVIEW_FIELD)
        remark = fields.get(self._DIRECTOR_REMARK_FIELD)
        if not flag and not remark:
            return
        section["frame"].setVisible(True)

        layout.addWidget(_section_title(
            "OCR: Director Instruction Found on the Document",
            "OCR found what looks like a Director instruction already written on this document. "
            "OCR can misread, so it is only used once you confirm it here.",
        ))

        verified = flag is not None and flag.get("verified_value") is not None
        if verified:
            confirmed = self._is_true(flag.get("verified_value"))
            when = str(flag.get("verified_at") or "")[:16].replace("T", " ")
            status_text = (
                f"Confirmed by the DS{(' on ' + when) if when else ''}: the Director has already reviewed this document."
                if confirmed else
                f"Checked by the DS{(' on ' + when) if when else ''}: not a prior Director review."
            )
            status_color = "#166534" if confirmed else "#475569"
        else:
            confirmed = False
            status_text = "Detected by OCR - not yet confirmed. The Director review step still applies."
            status_color = "#92400E"
        status = QLabel(status_text)
        status.setWordWrap(True)
        status.setStyleSheet(f"color: {status_color}; font-size: 11px; font-weight: 600;")
        layout.addWidget(status)

        remark_value = ""
        if remark:
            remark_value = remark.get("verified_value") or remark.get("extracted_value") or ""
        remark_edit = QTextEdit()
        remark_edit.setPlainText(str(remark_value))
        remark_edit.setPlaceholderText("Director's instruction as written on the document (correct any OCR mistakes)")
        remark_edit.setFixedHeight(64)
        layout.addWidget(remark_edit)

        confirm = QCheckBox(
            "The Director has already reviewed this document - the Director review step is not needed"
        )
        confirm.setChecked(confirmed)
        layout.addWidget(confirm)

        buttons = QHBoxLayout()
        buttons.addStretch()
        save_btn = QPushButton("Verify && Save")
        save_btn.setStyleSheet(
            "background-color: #0F172A; color: white; font-weight: 600; padding: 6px 16px; border-radius: 4px;"
        )
        save_btn.clicked.connect(lambda: self._save_ocr_verification(remark_edit, confirm))
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

    def _save_ocr_verification(self, remark_edit: QTextEdit, confirm: QCheckBox) -> None:
        doc_id = self.document.id
        remark_text = remark_edit.toPlainText().strip()
        confirmed = confirm.isChecked()

        def act():
            if remark_text:
                document_service.verify_ocr_field(doc_id, self._DIRECTOR_REMARK_FIELD, remark_text)
            document_service.verify_ocr_field(
                doc_id, self._PRIOR_REVIEW_FIELD, "true" if confirmed else "false"
            )

        self._guard(
            act,
            "OCR Verification",
            "Saved. The document can now be routed without a new Director review."
            if confirmed else
            "Saved. This document still goes through the Director review step.",
        )

    def _render_director_reviews(self) -> None:
        layout = self.director_section["layout"]
        self._clear(layout)
        doc = self.document

        if not doc.director_reviews and not doc.open_director_branch:
            self.director_section["frame"].setVisible(False)
            return
        self.director_section["frame"].setVisible(True)

        layout.addWidget(_section_title(
            "Director Review",
            "Every review is kept separately. The Director remarks; the DS decides what happens next.",
        ))

        open_branch = doc.open_director_branch
        if open_branch:
            pending = QLabel(
                f"Awaiting Director review - requested {open_branch.opened_at or ''}"
                + (f"\nInstructions: {open_branch.instructions}" if open_branch.instructions else "")
            )
            pending.setWordWrap(True)
            pending.setStyleSheet(
                "background-color: #F5F3FF; border-left: 3px solid #7C3AED; padding: 9px 11px; "
                "color: #4C1D95; font-size: 11px; border-radius: 3px;"
            )
            layout.addWidget(pending)

        for review in doc.director_reviews:
            block = QFrame()
            block.setStyleSheet(
                "background-color: #FAFAFA; border-left: 3px solid #7C3AED; border-radius: 3px;"
            )
            inner = QVBoxLayout(block)
            inner.setContentsMargins(11, 8, 11, 8)
            inner.setSpacing(3)

            head = QLabel(review.header)
            head.setStyleSheet("color: #4C1D95; font-size: 10px; font-weight: 700;")
            inner.addWidget(head)

            text = QLabel(review.remark_text)
            text.setWordWrap(True)
            text.setStyleSheet("color: #1E293B; font-size: 11px;")
            inner.addWidget(text)
            layout.addWidget(block)

    def _render_branches(self) -> None:
        layout = self.branches_section["layout"]
        self._clear(layout)
        doc = self.document

        layout.addWidget(_section_title(
            "Workstreams",
            "Each workstream has its own stage and moves at its own pace. "
            "Inside one, every person has their own work record.",
        ))

        work_branches = doc.work_branches
        if not work_branches:
            empty = QLabel(
                "This document has not been routed yet."
                + (" Use Route Document below to send it out." if self.is_ds else "")
            )
            empty.setWordWrap(True)
            empty.setStyleSheet("color: #94A3B8; font-size: 11px; font-style: italic;")
            layout.addWidget(empty)
            return

        for branch in work_branches:
            card = BranchCard(
                branch,
                current_user_id=self._user_id,
                current_context_id=self._context_id,
                context_type=self._context_type,
                context_department_id=self._context_department_id,
            )
            card.assign_requested.connect(self._assign_staff)
            card.remark_requested.connect(self._add_branch_remark)
            card.close_requested.connect(self._close_branch)
            card.further_work_requested.connect(self._send_further_work)
            card.review_requested.connect(lambda _bid: self._director_review())
            card.work_action.connect(self._handle_work_action)
            layout.addWidget(card)

    def _render_remarks(self) -> None:
        layout = self.remarks_section["layout"]
        self._clear(layout)
        doc = self.document

        remarks = [r for r in doc.remarks if r.provenance != "DIRECTOR_REVIEW"]
        if not remarks:
            self.remarks_section["frame"].setVisible(False)
            return
        self.remarks_section["frame"].setVisible(True)

        layout.addWidget(_section_title(
            "Remarks",
            "Append-only. Nothing here is ever overwritten or replaced.",
        ))
        for remark in remarks:
            block = QFrame()
            block.setStyleSheet(
                "background-color: #F8FAFC; border-left: 3px solid #CBD5E1; border-radius: 3px;"
            )
            inner = QVBoxLayout(block)
            inner.setContentsMargins(11, 7, 11, 7)
            inner.setSpacing(2)
            head = QLabel(remark.header)
            head.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 600;")
            inner.addWidget(head)
            text = QLabel(remark.remark_text)
            text.setWordWrap(True)
            text.setStyleSheet("color: #1E293B; font-size: 11px;")
            inner.addWidget(text)
            layout.addWidget(block)

    def _render_history(self) -> None:
        layout = self.history_section["layout"]
        self._clear(layout)
        doc = self.document

        if not doc.history:
            self.history_section["frame"].setVisible(False)
            return
        self.history_section["frame"].setVisible(True)

        layout.addWidget(_section_title(
            "Workflow History",
            "The complete chronological record of everything that happened to this document.",
        ))
        for event in doc.history:
            row = QLabel(
                f"{event.when}   •   [{event.scope}]   {event.summary}"
                + (f"\n        {event.details}" if event.details else "")
            )
            row.setWordWrap(True)
            row.setStyleSheet("color: #334155; font-size: 10px; padding: 2px 0px;")
            layout.addWidget(row)

    # ==================================================================
    # ACTION BAR
    # ==================================================================

    def _render_actions(self) -> None:
        self._clear(self.action_layout)
        doc = self.document
        buttons: List[QPushButton] = []

        def make(text: str, handler, primary: bool = False) -> QPushButton:
            btn = QPushButton(text)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "background-color: #0F172A; color: white; font-weight: 600; padding: 8px 16px; "
                "border-radius: 4px; font-size: 12px;"
                if primary else
                "background-color: #F8FAFC; color: #0F172A; border: 1px solid #CBD5E1; "
                "font-weight: 600; padding: 8px 16px; border-radius: 4px; font-size: 12px;"
            )
            btn.clicked.connect(handler)
            return btn

        if self.is_ds:
            if doc.is_closed:
                buttons.append(make("Reopen Document", self._reopen_document, primary=True))
            else:
                buttons.append(make("Route Document", self._route_document, primary=True))
                buttons.append(make("Edit Details", self._edit_details))
                buttons.append(make("Send Reminder", self._send_reminder))
                buttons.append(make("Close Document", self._close_document))

        elif self.is_director:
            if doc.open_director_branch:
                buttons.append(make("Write Review Remark", self._director_review, primary=True))
            else:
                note = QLabel("No review is currently requested from you on this document.")
                note.setStyleSheet("color: #64748B; font-size: 11px; font-style: italic;")
                self.action_layout.addWidget(note)

        elif self.is_hod:
            my_branches = doc.branches_for_department(self._context_department_id)
            active = [b for b in my_branches if b.is_active]
            if active:
                buttons.append(make(
                    "Assign Staff", lambda: self._assign_staff(active[0].id), primary=True
                ))
                buttons.append(make(
                    "Add HOD Remark", lambda: self._add_branch_remark(active[0].id)
                ))
            else:
                note = QLabel("This document is not currently routed to your department.")
                note.setStyleSheet("color: #64748B; font-size: 11px; font-style: italic;")
                self.action_layout.addWidget(note)

        elif self.is_worker:
            mine = [
                w for w in doc.work_items_for_user(self._user_id, self._context_id)
                if not w.is_finished
            ]
            if mine:
                item = mine[0]
                buttons.append(make(
                    "Add Progress", lambda: self._work_progress(item.id), primary=True
                ))
                buttons.append(make("Change Stage", lambda: self._work_stage(item.id)))
                buttons.append(make("Submit Work", lambda: self._work_submit(item.id)))
            else:
                note = QLabel("You have no open assignment on this document in this context.")
                note.setStyleSheet("color: #64748B; font-size: 11px; font-style: italic;")
                self.action_layout.addWidget(note)

        for btn in buttons:
            self.action_layout.addWidget(btn)
        self.action_layout.addStretch()

    # ==================================================================
    # ACTION HANDLERS
    # ==================================================================

    def _notify_change(self) -> None:
        if self.document and self.document.id:
            self.document_changed.emit(self.document.id)
        self.document_updated.emit(self.document)
        try:
            from services.event_bus import event_bus
            event_bus.document_updated.emit(self.document.id)
        except Exception:
            pass

    def _guard(self, action, success_title: str, success_message: str) -> bool:
        """Run a workflow call and report the outcome faithfully."""
        try:
            action()
        except Exception as exc:
            QMessageBox.warning(self, "Action failed", str(exc))
            return False
        QMessageBox.information(self, success_title, success_message)
        self.refresh()
        self._notify_change()
        return True

    # ---- DS ----

    def _route_document(self) -> None:
        dialog = RoutingDialog(self.document, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        branches = dialog.get_branches()
        self._guard(
            lambda: routing_service.route(self.document.id, branches, self.document.version),
            "Routed",
            f"Opened {len(branches)} workstream(s). They now run independently.",
        )

    def _send_further_work(self, branch_id: int) -> None:
        branch = self.document.branch_by_id(branch_id)
        if not branch:
            return
        dialog = RemarkDialog(
            f"Send Further Work - {branch.label}",
            "This reopens the workstream with a new round. Everything already done on it "
            "stays in the record.",
            self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        entry: Dict[str, Any] = {
            "branch_type": branch.branch_type,
            "instructions": dialog.get_text(),
        }
        if branch.branch_type == "DEPARTMENT":
            entry["department_id"] = branch.department_id
        elif branch.branch_type in ("EMPLOYEE", "TSO"):
            entry["target_user_id"] = branch.target_user_id

        self._guard(
            lambda: routing_service.route(self.document.id, [entry]),
            "Further work sent",
            f"{branch.label} has been reopened for further work.",
        )

    def _close_branch(self, branch_id: int) -> None:
        branch = self.document.branch_by_id(branch_id)
        if not branch:
            return
        confirm = QMessageBox.question(
            self, "Close Workstream",
            f"Close the {branch.label} workstream?\n\n"
            "Outstanding work on it is cancelled. Other workstreams and the document itself "
            "are not affected.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._guard(
            lambda: routing_service.close_branch(branch_id, "Closed by DS"),
            "Workstream closed",
            f"{branch.label} is closed. The document remains open.",
        )

    def _close_document(self) -> None:
        dialog = CloseDocumentDialog(self.document, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        self._guard(
            lambda: document_service.close_document(
                self.document.id,
                remark=data["remark"],
                force=data["force"],
                expected_version=self.document.version,
            ),
            "Document closed",
            f"{self.document.reference} has been closed.",
        )

    def _reopen_document(self) -> None:
        dialog = RemarkDialog(
            "Reopen Document", "Why is this document being reopened?", self
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._guard(
            lambda: document_service.reopen_document(self.document.id, dialog.get_text()),
            "Reopened",
            "The document is open again and can be routed for further work.",
        )

    def _edit_details(self) -> None:
        dialog = EditDocumentDialog(self.document, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._guard(
            lambda: document_service.update_document(self.document.id, dialog.get_data()),
            "Details updated",
            "The changes are recorded in the document history.",
        )

    def _remind_branch(self, branch_id: int) -> None:
        self._send_reminder()

    def _send_reminder(self) -> None:
        dialog = ReminderDialog(self.document, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        self._guard(
            lambda: document_service.send_reminder(
                self.document.id, data["work_item_id"], None, data["message"]
            ),
            "Reminder sent",
            "The people holding open work have been notified.",
        )

    # ---- Director ----

    def _director_review(self) -> None:
        branch = self.document.open_director_branch
        if not branch:
            QMessageBox.information(
                self, "Director Review", "No review is currently requested on this document."
            )
            return
        try:
            routing_service.start_director_review(branch.id)
        except Exception:
            pass

        dialog = DirectorReviewDialog(self.document, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._guard(
            lambda: routing_service.submit_director_review(
                branch.id, dialog.get_text(), self.document.version
            ),
            "Review recorded",
            "Your remark is saved and the document has returned to the DS.",
        )

    # ---- HOD / DS assignment ----

    def _assign_staff(self, branch_id: int) -> None:
        branch = self.document.branch_by_id(branch_id)
        if not branch:
            return
        dialog = AssignWorkDialog(branch, self._context_department_id, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        count = len(data["assignee_user_ids"])
        self._guard(
            lambda: routing_service.assign(
                branch_id,
                data["assignee_user_ids"],
                instructions=data["instructions"],
                deadline=data["deadline"],
                requires_validation=data["requires_validation"],
                team_name=data["team_name"],
            ),
            "Staff assigned",
            f"Created {count} individual work record(s) - one per person.",
        )

    def _add_branch_remark(self, branch_id: int) -> None:
        branch = self.document.branch_by_id(branch_id)
        label = branch.label if branch else "this workstream"
        dialog = RemarkDialog(
            f"Add Remark - {label}",
            "Remarks are appended to the record. Earlier remarks are never replaced.",
            self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._guard(
            lambda: routing_service.add_remark(branch_id, dialog.get_text()),
            "Remark saved",
            "Your remark has been added to the workstream.",
        )

    # ---- work item actions ----

    def _find_item(self, work_item_id: int) -> Optional[WorkItemModel]:
        return next((w for w in self.document.all_work_items if w.id == work_item_id), None)

    def _handle_work_action(self, action: str, work_item_id: int) -> None:
        handlers = {
            "progress": self._work_progress,
            "stage": self._work_stage,
            "submit": self._work_submit,
            "accept": self._work_accept,
            "return": self._work_return,
            "remind": self._work_remind,
        }
        handler = handlers.get(action)
        if handler:
            handler(work_item_id)

    def _work_progress(self, work_item_id: int) -> None:
        item = self._find_item(work_item_id)
        if not item:
            return
        dialog = ProgressDialog(item, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        self._guard(
            lambda: work_service.add_progress(
                work_item_id, data["description"], data["new_stage"], data["file_path"]
            ),
            "Progress recorded",
            "Your update has been added to your work record.",
        )

    def _work_stage(self, work_item_id: int) -> None:
        item = self._find_item(work_item_id)
        if not item:
            return
        dialog = StageDialog(item, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        data = dialog.get_data()
        self._guard(
            lambda: work_service.set_stage(work_item_id, data["stage"], data["note"]),
            "Stage updated",
            "Only your own work stage changed.",
        )

    def _work_submit(self, work_item_id: int) -> None:
        item = self._find_item(work_item_id)
        if not item:
            return
        dialog = SubmitWorkDialog(item, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        
        data = dialog.get_data()
        def do_submit():
            if data["file_path"]:
                work_service.add_progress(
                    work_item_id, 
                    description=data["note"] or "Attached final work submission file.", 
                    file_path=data["file_path"]
                )
            return work_service.submit(work_item_id, data["note"])

        self._guard(
            do_submit,
            "Work submitted",
            (
                "Your work has gone to your HOD for validation."
                if item.requires_validation else
                "Your assignment is complete. The DS decides when the document closes."
            ),
        )

    def _work_accept(self, work_item_id: int) -> None:
        item = self._find_item(work_item_id)
        if not item:
            return
        dialog = WorkReviewDialog(item, accept_mode=True, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._guard(
            lambda: work_service.accept(work_item_id, dialog.get_note()),
            "Work accepted",
            f"{item.assignee_name}'s work is validated. The document stays open until the DS closes it.",
        )

    def _work_return(self, work_item_id: int) -> None:
        item = self._find_item(work_item_id)
        if not item:
            return
        dialog = WorkReviewDialog(item, accept_mode=False, parent=self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._guard(
            lambda: work_service.return_for_rework(work_item_id, dialog.get_note()),
            "Work returned",
            f"{item.assignee_name} has been asked to rework this. Their earlier progress is kept.",
        )

    def _work_remind(self, work_item_id: int) -> None:
        item = self._find_item(work_item_id)
        if not item:
            return
        self._guard(
            lambda: document_service.send_reminder(self.document.id, work_item_id),
            "Reminder sent",
            f"{item.assignee_name} has been reminded.",
        )

    def cleanup(self) -> None:
        """Release listeners before the shell removes this widget."""
        try:
            self.preview.cleanup()
        except Exception:
            pass
