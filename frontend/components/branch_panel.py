"""Workstream and work-item cards.

This is where the core rule becomes visible to users: a document is shown as
a LIST of workstreams, each with its own stage, and every person inside a
workstream gets their own card with their own stage, deadline, written
progress and attachments.  Nothing is summed, averaged or merged.
"""

import os
import tempfile
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices

from PySide6.QtWidgets import (
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from models import BranchModel, WorkItemModel
from services.attachment_service import attachment_service

# ---------------------------------------------------------------------------
# Stage colours.  Branch stages and work stages have separate palettes on
# purpose: they are different concepts and must not be read as one scale.
# ---------------------------------------------------------------------------

BRANCH_STAGE_COLORS = {
    "REVIEW_REQUESTED": "#7C3AED",
    "UNDER_DIRECTOR_REVIEW": "#6D28D9",
    "REMARK_ADDED": "#5B21B6",
    "RETURNED_TO_DS": "#4C1D95",
    "HOD_REVIEW": "#0F172A",
    "EMPLOYEE_ASSIGNMENT": "#1D4ED8",
    "EMPLOYEE_WORK": "#0369A1",
    "HOD_VALIDATION": "#B45309",
    "ASSIGNED": "#1D4ED8",
    "IN_PROGRESS": "#0369A1",
    "SUBMITTED": "#B45309",
    "FURTHER_WORK": "#C2410C",
    "COMPLETED": "#166534",
    "CANCELLED": "#6B7280",
}

WORK_STAGE_COLORS = {
    "ASSIGNED": "#1D4ED8",
    "UNDER_WORK": "#0369A1",
    "WAITING": "#92400E",
    "SUBMITTED": "#B45309",
    "UNDER_REVIEW": "#7C3AED",
    "RETURNED": "#B91C1C",
    "COMPLETED": "#166534",
    "CANCELLED": "#6B7280",
}


def badge(text: str, color: str, bold: bool = True) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"background-color: {color}; color: white; padding: 2px 8px; "
        f"border-radius: 3px; font-size: 10px; font-weight: {'700' if bold else '500'};"
    )
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
    return label


def outline_badge(text: str, color: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(
        f"color: {color}; border: 1px solid {color}; padding: 1px 7px; "
        f"border-radius: 3px; font-size: 10px; font-weight: 600;"
    )
    label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
    return label


def small_button(text: str, primary: bool = False) -> QPushButton:
    btn = QPushButton(text)
    if primary:
        btn.setStyleSheet(
            "background-color: #0F172A; color: white; font-weight: 600; "
            "padding: 5px 12px; border-radius: 4px; font-size: 11px;"
        )
    else:
        btn.setStyleSheet(
            "background-color: #F8FAFC; color: #0F172A; border: 1px solid #CBD5E1; "
            "font-weight: 600; padding: 5px 12px; border-radius: 4px; font-size: 11px;"
        )
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


# ===========================================================================
# WORK ITEM CARD - one person
# ===========================================================================

class WorkItemCard(QFrame):
    """One person's work on one workstream.

    Shows what was assigned, their own stage, their own deadline, what they
    wrote, and what they attached.  Two people on the same team render as two
    of these, never as one row.
    """

    progress_requested = Signal(int)     # work_item_id
    stage_requested = Signal(int)        # work_item_id
    submit_requested = Signal(int)       # work_item_id
    accept_requested = Signal(int)       # work_item_id
    return_requested = Signal(int)       # work_item_id
    remind_requested = Signal(int)       # work_item_id

    def __init__(
        self,
        item: WorkItemModel,
        *,
        can_work: bool = False,
        can_validate: bool = False,
        can_remind: bool = False,
        show_full_progress: bool = True,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.item = item
        self.can_work = can_work
        self.can_validate = can_validate
        self.can_remind = can_remind
        self.show_full_progress = show_full_progress
        self.setObjectName("workItemCard")
        self._build()

    def _build(self) -> None:
        item = self.item
        stage_color = WORK_STAGE_COLORS.get(item.stage, "#475569")
        self.setStyleSheet(
            "QFrame#workItemCard { background-color: #FFFFFF; border: 1px solid #E2E8F0; "
            f"border-left: 3px solid {stage_color}; border-radius: 5px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # --- who + stage + deadline ---
        head = QHBoxLayout()
        head.setSpacing(8)

        who = QLabel(item.assignee_name or "Unassigned")
        who.setStyleSheet("font-weight: 700; color: #0F172A; font-size: 12px;")
        head.addWidget(who)

        if item.team_name:
            head.addWidget(outline_badge(f"Team: {item.team_name}", "#475569"))
        if item.context_type == "TSO":
            head.addWidget(outline_badge("TSO", "#B45309"))
        elif item.department_name:
            head.addWidget(outline_badge(item.department_name, "#64748B"))
        if item.round_no > 1:
            head.addWidget(outline_badge(f"Round {item.round_no}", "#C2410C"))

        head.addStretch()
        head.addWidget(badge(item.stage_label, stage_color))
        layout.addLayout(head)

        # --- assignment metadata ---
        meta_bits: List[str] = []
        if item.assigner_name:
            meta_bits.append(f"Assigned by {item.assigner_name}")
        if item.deadline and item.deadline != "-":
            meta_bits.append(f"Due {item.deadline_display}")
        if item.requires_validation:
            meta_bits.append("HOD validation required")
        if meta_bits:
            meta = QLabel("  •  ".join(meta_bits))
            meta.setStyleSheet(f"color: {item.deadline_color}; font-size: 10px;")
            layout.addWidget(meta)

        if item.instructions:
            instr = QLabel(f"Instructions: {item.instructions}")
            instr.setWordWrap(True)
            instr.setStyleSheet("color: #475569; font-size: 11px; font-style: italic;")
            layout.addWidget(instr)

        # --- written progress, exactly as the worker typed it ---
        if self.show_full_progress and item.progress_updates:
            for update in item.progress_updates:
                layout.addWidget(self._progress_block(update))
        elif item.latest_progress_text:
            latest = QLabel(item.progress_summary)
            latest.setWordWrap(True)
            latest.setStyleSheet("color: #1E293B; font-size: 11px;")
            layout.addWidget(latest)
        else:
            empty = QLabel("No progress update yet.")
            empty.setStyleSheet("color: #94A3B8; font-size: 11px; font-style: italic;")
            layout.addWidget(empty)

        # --- validation outcomes ---
        for review in item.reviews:
            color = "#166534" if review.outcome == "ACCEPTED" else "#B91C1C"
            rev = QLabel(review.label + (f" - {review.note}" if review.note else ""))
            rev.setWordWrap(True)
            rev.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 600;")
            layout.addWidget(rev)

        # --- actions available to the viewer ---
        actions = self._action_row()
        if actions is not None:
            layout.addWidget(actions)

    def _progress_block(self, update) -> QWidget:
        block = QFrame()
        block.setStyleSheet(
            "background-color: #F8FAFC; border-left: 2px solid #CBD5E1; border-radius: 3px;"
        )
        inner = QVBoxLayout(block)
        inner.setContentsMargins(10, 7, 10, 7)
        inner.setSpacing(3)

        header = QLabel(update.header)
        header.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 600;")
        inner.addWidget(header)

        body = QLabel(update.description)
        body.setWordWrap(True)
        body.setStyleSheet("color: #1E293B; font-size: 11px;")
        inner.addWidget(body)

        for att in update.attachments:
            row_holder = QWidget()
            row = QHBoxLayout(row_holder)
            row.setContentsMargins(0, 2, 0, 0)
            row.setSpacing(6)

            file_label = QLabel(
                f"  📎 {att.file_name}  ({att.size_label})  -  {att.uploaded_label}"
            )
            file_label.setWordWrap(True)
            file_label.setStyleSheet("color: #0369A1; font-size: 10px;")
            row.addWidget(file_label, 1)

            view_btn = small_button("View")
            view_btn.clicked.connect(
                lambda checked=False, a=att: self._view_attachment(a)
            )
            row.addWidget(view_btn)

            download_btn = small_button("Download")
            download_btn.clicked.connect(
                lambda checked=False, a=att: self._download_attachment(a)
            )
            row.addWidget(download_btn)

            inner.addWidget(row_holder)

        return block

    def _view_attachment(self, attachment) -> None:
        """Download an attachment to a temporary cache and open it locally."""
        attachment_id = getattr(attachment, "id", None)
        file_name = getattr(attachment, "file_name", None) or "attachment"

        if not attachment_id:
            QMessageBox.warning(
                self,
                "View Attachment",
                "This attachment does not have a valid attachment ID.",
            )
            return

        try:
            cache_dir = os.path.join(
                tempfile.gettempdir(),
                "cdtrs_attachment_preview",
            )
            os.makedirs(cache_dir, exist_ok=True)

            safe_name = os.path.basename(file_name)
            cached_path = os.path.join(
                cache_dir,
                f"{attachment_id}_{safe_name}",
            )

            downloaded = attachment_service.download(
                attachment_id,
                cached_path,
            )
            final_path = downloaded or cached_path

            if not final_path or not os.path.exists(final_path):
                raise RuntimeError(
                    "The attachment could not be downloaded from the server."
                )

            if not QDesktopServices.openUrl(
                QUrl.fromLocalFile(os.path.abspath(final_path))
            ):
                raise RuntimeError(
                    "Windows could not open the downloaded attachment."
                )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "View Attachment",
                f"Could not open '{file_name}'.\n\n{exc}",
            )

    def _download_attachment(self, attachment) -> None:
        """Let the current authorized user save the attachment locally."""
        attachment_id = getattr(attachment, "id", None)
        file_name = getattr(attachment, "file_name", None) or "attachment"

        if not attachment_id:
            QMessageBox.warning(
                self,
                "Download Attachment",
                "This attachment does not have a valid attachment ID.",
            )
            return

        target_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Attachment",
            file_name,
            "All Files (*)",
        )

        if not target_path:
            return

        try:
            downloaded = attachment_service.download(
                attachment_id,
                target_path,
            )
            final_path = downloaded or target_path

            if not final_path or not os.path.exists(final_path):
                raise RuntimeError(
                    "The attachment could not be downloaded from the server."
                )

            QMessageBox.information(
                self,
                "Download Complete",
                f"Attachment saved to:\n{final_path}",
            )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Download Attachment",
                f"Could not download '{file_name}'.\n\n{exc}",
            )

    def _action_row(self) -> Optional[QWidget]:
        buttons: List[QPushButton] = []
        item = self.item

        if self.can_work and not item.is_finished:
            b = small_button("Add Progress", primary=True)
            b.clicked.connect(lambda: self.progress_requested.emit(item.id))
            buttons.append(b)

            b = small_button("Change Stage")
            b.clicked.connect(lambda: self.stage_requested.emit(item.id))
            buttons.append(b)

            if item.stage != "UNDER_REVIEW":
                b = small_button("Submit Work")
                b.clicked.connect(lambda: self.submit_requested.emit(item.id))
                buttons.append(b)

        if self.can_validate and item.awaiting_validation:
            b = small_button("Accept", primary=True)
            b.clicked.connect(lambda: self.accept_requested.emit(item.id))
            buttons.append(b)

            b = small_button("Return for Rework")
            b.clicked.connect(lambda: self.return_requested.emit(item.id))
            buttons.append(b)

        if self.can_remind and not item.is_finished:
            b = small_button("Remind")
            b.clicked.connect(lambda: self.remind_requested.emit(item.id))
            buttons.append(b)

        if not buttons:
            return None

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(6)
        for b in buttons:
            row.addWidget(b)
        row.addStretch()
        return holder


# ===========================================================================
# BRANCH CARD - one workstream
# ===========================================================================

class BranchCard(QFrame):
    """One independent workstream, with its own stage and its own people.

    Several of these sit side by side on a document at different stages;
    that is the normal case, not an error state.
    """

    assign_requested = Signal(int)       # branch_id
    remark_requested = Signal(int)       # branch_id
    close_requested = Signal(int)        # branch_id
    further_work_requested = Signal(int)  # branch_id
    review_requested = Signal(int)       # branch_id (Director)
    remind_requested = Signal(int)       # branch_id

    work_action = Signal(str, int)       # action name, work_item_id

    def __init__(
        self,
        branch: BranchModel,
        *,
        current_user_id: Optional[int] = None,
        current_context_id: Optional[int] = None,
        context_type: str = "",
        context_department_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.branch = branch
        self.current_user_id = current_user_id
        self.current_context_id = current_context_id
        self.context_type = (context_type or "").upper()
        self.context_department_id = context_department_id
        self.setObjectName("branchCard")
        self._build()

    # -- permission helpers ------------------------------------------------

    @property
    def _is_ds(self) -> bool:
        return self.context_type == "DS"

    @property
    def _is_director(self) -> bool:
        return self.context_type == "DIRECTOR"

    @property
    def _is_owning_hod(self) -> bool:
        return (
            self.context_type == "HOD"
            and self.branch.branch_type == "DEPARTMENT"
            and self.branch.department_id == self.context_department_id
        )

    def _is_my_work(self, item: WorkItemModel) -> bool:
        """True only when this work item belongs to the person AND the hat
        they are currently wearing."""
        return (
            item.assigned_to_user_id == self.current_user_id
            and (
                self.current_context_id is None
                or item.assigned_to_context_membership_id == self.current_context_id
            )
        )

    # -- rendering ---------------------------------------------------------

    def _build(self) -> None:
        branch = self.branch
        accent = branch.accent_color if branch.is_active else "#94A3B8"
        self.setStyleSheet(
            "QFrame#branchCard { background-color: #FFFFFF; border: 1px solid #CBD5E1; "
            f"border-left: 4px solid {accent}; border-radius: 6px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(9)

        # --- header: label, type, its OWN stage ---
        head = QHBoxLayout()
        head.setSpacing(8)

        title = QLabel(branch.label)
        title.setStyleSheet("font-weight: 700; color: #0F172A; font-size: 13px;")
        head.addWidget(title)
        head.addWidget(outline_badge(branch.type_label, "#64748B"))
        if branch.round_no > 1:
            head.addWidget(outline_badge(f"Round {branch.round_no}", "#C2410C"))
        head.addStretch()

        if not branch.is_active:
            head.addWidget(outline_badge("Closed", "#94A3B8"))
        head.addWidget(badge(branch.stage_label, BRANCH_STAGE_COLORS.get(branch.stage, "#475569")))
        layout.addLayout(head)

        if branch.instructions:
            instr = QLabel(f"Instructions: {branch.instructions}")
            instr.setWordWrap(True)
            instr.setStyleSheet("color: #475569; font-size: 11px; font-style: italic;")
            layout.addWidget(instr)

        if branch.deadline and branch.deadline_state != "none":
            dl = QLabel(f"Workstream deadline: {branch.deadline}")
            dl.setStyleSheet("color: #64748B; font-size: 10px;")
            layout.addWidget(dl)

        # --- the people ---
        if branch.branch_type == "DIRECTOR":
            note = QLabel(
                "The Director reviews and records a remark. "
                "Closure is decided by the DS."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #64748B; font-size: 11px;")
            layout.addWidget(note)
        elif not branch.work_items:
            empty = QLabel("Nobody has been assigned to this workstream yet.")
            empty.setStyleSheet("color: #94A3B8; font-size: 11px; font-style: italic;")
            layout.addWidget(empty)
        else:
            for item in branch.work_items:
                card = WorkItemCard(
                    item,
                    can_work=self._is_my_work(item),
                    can_validate=self._is_owning_hod or self._is_ds,
                    can_remind=self._is_ds or self._is_owning_hod,
                )
                card.progress_requested.connect(lambda i: self.work_action.emit("progress", i))
                card.stage_requested.connect(lambda i: self.work_action.emit("stage", i))
                card.submit_requested.connect(lambda i: self.work_action.emit("submit", i))
                card.accept_requested.connect(lambda i: self.work_action.emit("accept", i))
                card.return_requested.connect(lambda i: self.work_action.emit("return", i))
                card.remind_requested.connect(lambda i: self.work_action.emit("remind", i))
                layout.addWidget(card)

        # --- branch-level actions ---
        actions = self._action_row()
        if actions is not None:
            layout.addWidget(actions)

    def _action_row(self) -> Optional[QWidget]:
        branch = self.branch
        buttons: List[QPushButton] = []

        if self._is_owning_hod and branch.is_active:
            b = small_button("Assign Staff", primary=True)
            b.clicked.connect(lambda: self.assign_requested.emit(branch.id))
            buttons.append(b)

            b = small_button("Add HOD Remark")
            b.clicked.connect(lambda: self.remark_requested.emit(branch.id))
            buttons.append(b)

        if self._is_director and branch.branch_type == "DIRECTOR" and branch.is_active:
            b = small_button("Write Review Remark", primary=True)
            b.clicked.connect(lambda: self.review_requested.emit(branch.id))
            buttons.append(b)

        if self._is_ds:
            if branch.is_active:
                if branch.branch_type != "DIRECTOR":
                    b = small_button("Close Workstream")
                    b.clicked.connect(lambda: self.close_requested.emit(branch.id))
                    buttons.append(b)

                b = small_button("Remind")
                b.clicked.connect(lambda: self.remind_requested.emit(branch.id))
                buttons.append(b)

                b = small_button("Add Remark")
                b.clicked.connect(lambda: self.remark_requested.emit(branch.id))
                buttons.append(b)
            elif not branch.is_active and branch.branch_type != "DIRECTOR":
                b = small_button("Send Further Work")
                b.clicked.connect(lambda: self.further_work_requested.emit(branch.id))
                buttons.append(b)

        if not buttons:
            return None

        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(6)
        for b in buttons:
            row.addWidget(b)
        row.addStretch()
        return holder
