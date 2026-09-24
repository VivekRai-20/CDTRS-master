"""Frontend domain models for the workflow: branches, work items, progress,
remarks and history events.

These mirror the backend exactly, including the rule the whole redesign turns
on: a document is described by a LIST of branch states, and each person's work
is its own record with its own stage.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional


def _get(data: Any, key: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        return data.get(key, default)
    return getattr(data, key, default)


def _fmt_date(value: Any) -> str:
    """Render a date/datetime/ISO string as dd Mon yyyy, or '-' when absent."""
    if not value:
        return "-"
    if isinstance(value, (datetime, date)):
        return value.strftime("%d %b %Y")
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.split("+")[0], fmt).strftime("%d %b %Y")
        except ValueError:
            continue
    return text


def _fmt_datetime(value: Any) -> str:
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y, %H:%M")
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.split("+")[0], fmt).strftime("%d %b %Y, %H:%M")
        except ValueError:
            continue
    return text


#: Colours for deadline urgency, shared by every table and card.
DEADLINE_COLORS = {
    "overdue": "#B91C1C",
    "due_soon": "#B45309",
    "on_track": "#166534",
    "none": "#64748B",
}

DEADLINE_LABELS = {
    "overdue": "Overdue",
    "due_soon": "Due soon",
    "on_track": "On track",
    "none": "No deadline",
}


# =========================================================
# ATTACHMENT
# =========================================================

@dataclass
class AttachmentModel:
    id: Optional[int] = None
    document_id: Optional[int] = None
    progress_update_id: Optional[int] = None
    work_item_id: Optional[int] = None
    file_name: str = ""
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    attachment_type: str = "ORIGINAL"
    uploaded_by_user_id: Optional[int] = None
    uploaded_by_name: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Any) -> "AttachmentModel":
        return cls(
            id=_get(data, "id"),
            document_id=_get(data, "document_id"),
            progress_update_id=_get(data, "progress_update_id"),
            work_item_id=_get(data, "work_item_id"),
            file_name=_get(data, "file_name") or "",
            file_type=_get(data, "file_type"),
            file_size=_get(data, "file_size"),
            attachment_type=_get(data, "attachment_type") or "ORIGINAL",
            uploaded_by_user_id=_get(data, "uploaded_by_user_id"),
            uploaded_by_name=_get(data, "uploaded_by_name"),
            created_at=_get(data, "created_at"),
        )

    @property
    def size_label(self) -> str:
        if not self.file_size:
            return ""
        size = float(self.file_size)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024
        return ""

    @property
    def uploaded_label(self) -> str:
        who = self.uploaded_by_name or "Unknown"
        return f"{who} - {_fmt_datetime(self.created_at)}"


# =========================================================
# PROGRESS UPDATE (free text, never a percentage)
# =========================================================

@dataclass
class ProgressModel:
    """One free-text update written by the person doing the work."""

    id: Optional[int] = None
    document_id: Optional[int] = None
    work_item_id: Optional[int] = None
    author_user_id: Optional[int] = None
    author_name: Optional[str] = None
    description: str = ""
    stage_at_time: Optional[str] = None
    created_at: Optional[str] = None
    attachments: List[AttachmentModel] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "ProgressModel":
        return cls(
            id=_get(data, "id"),
            document_id=_get(data, "document_id"),
            work_item_id=_get(data, "work_item_id"),
            author_user_id=_get(data, "author_user_id"),
            author_name=_get(data, "author_name"),
            description=_get(data, "description") or "",
            stage_at_time=_get(data, "stage_at_time"),
            created_at=_get(data, "created_at"),
            attachments=[AttachmentModel.from_dict(a) for a in (_get(data, "attachments") or [])],
        )

    @property
    def when(self) -> str:
        return _fmt_datetime(self.created_at)

    @property
    def header(self) -> str:
        return f"{self.author_name or 'Unknown'} - {self.when}"


# =========================================================
# WORK ITEM REVIEW
# =========================================================

@dataclass
class WorkReviewModel:
    id: Optional[int] = None
    work_item_id: Optional[int] = None
    reviewer_user_id: Optional[int] = None
    reviewer_name: Optional[str] = None
    outcome: str = "ACCEPTED"
    note: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Any) -> "WorkReviewModel":
        return cls(
            id=_get(data, "id"),
            work_item_id=_get(data, "work_item_id"),
            reviewer_user_id=_get(data, "reviewer_user_id"),
            reviewer_name=_get(data, "reviewer_name"),
            outcome=_get(data, "outcome") or "ACCEPTED",
            note=_get(data, "note"),
            created_at=_get(data, "created_at"),
        )

    @property
    def label(self) -> str:
        verb = "accepted" if self.outcome == "ACCEPTED" else "returned"
        return f"{self.reviewer_name or 'Reviewer'} {verb} this work - {_fmt_datetime(self.created_at)}"


# =========================================================
# WORK ITEM (one person's work)
# =========================================================

@dataclass
class WorkItemModel:
    """Exactly one person's work on one branch.

    Never merged with anyone else's: this is the record the Documents page,
    the HOD view and the worker's own task list all read from.
    """

    id: Optional[int] = None
    document_id: Optional[int] = None
    branch_id: Optional[int] = None
    branch_label: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None

    assigned_to_user_id: Optional[int] = None
    assignee_name: Optional[str] = None
    assigned_to_context_membership_id: Optional[int] = None
    context_type: Optional[str] = None
    department_name: Optional[str] = None
    assigned_by_user_id: Optional[int] = None
    assigner_name: Optional[str] = None

    instructions: Optional[str] = None
    deadline: Optional[str] = None
    deadline_state: str = "none"

    stage: str = "ASSIGNED"
    stage_label: str = "Assigned"
    requires_validation: bool = False
    round_no: int = 1
    is_active: bool = True

    latest_progress_text: Optional[str] = None
    last_update_at: Optional[str] = None
    attachment_count: int = 0

    assigned_at: Optional[str] = None
    started_at: Optional[str] = None
    submitted_at: Optional[str] = None
    completed_at: Optional[str] = None
    version: int = 1

    progress_updates: List[ProgressModel] = field(default_factory=list)
    reviews: List[WorkReviewModel] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "WorkItemModel":
        return cls(
            id=_get(data, "id"),
            document_id=_get(data, "document_id"),
            branch_id=_get(data, "branch_id"),
            branch_label=_get(data, "branch_label"),
            team_id=_get(data, "team_id"),
            team_name=_get(data, "team_name"),
            assigned_to_user_id=_get(data, "assigned_to_user_id"),
            assignee_name=_get(data, "assignee_name"),
            assigned_to_context_membership_id=_get(data, "assigned_to_context_membership_id"),
            context_type=_get(data, "context_type"),
            department_name=_get(data, "department_name"),
            assigned_by_user_id=_get(data, "assigned_by_user_id"),
            assigner_name=_get(data, "assigner_name"),
            instructions=_get(data, "instructions"),
            deadline=_get(data, "deadline"),
            deadline_state=_get(data, "deadline_state") or "none",
            stage=_get(data, "stage") or "ASSIGNED",
            stage_label=_get(data, "stage_label") or "Assigned",
            requires_validation=bool(_get(data, "requires_validation")),
            round_no=_get(data, "round_no") or 1,
            is_active=bool(_get(data, "is_active", True)),
            latest_progress_text=_get(data, "latest_progress_text"),
            last_update_at=_get(data, "last_update_at"),
            attachment_count=_get(data, "attachment_count") or 0,
            assigned_at=_get(data, "assigned_at"),
            started_at=_get(data, "started_at"),
            submitted_at=_get(data, "submitted_at"),
            completed_at=_get(data, "completed_at"),
            version=_get(data, "version") or 1,
            progress_updates=[ProgressModel.from_dict(p) for p in (_get(data, "progress_updates") or [])],
            reviews=[WorkReviewModel.from_dict(r) for r in (_get(data, "reviews") or [])],
        )

    # -- display helpers used by tables and cards ------------------

    @property
    def deadline_display(self) -> str:
        return _fmt_date(self.deadline)

    @property
    def deadline_color(self) -> str:
        return DEADLINE_COLORS.get(self.deadline_state, DEADLINE_COLORS["none"])

    @property
    def last_update_display(self) -> str:
        return _fmt_datetime(self.last_update_at)

    @property
    def progress_summary(self) -> str:
        """First line of the latest update, for a table cell."""
        if not self.latest_progress_text:
            return "No update yet"
        text = " ".join(self.latest_progress_text.split())
        return text if len(text) <= 90 else text[:87] + "..."

    @property
    def is_finished(self) -> bool:
        return self.stage in ("COMPLETED", "CANCELLED")

    @property
    def awaiting_validation(self) -> bool:
        return self.stage == "UNDER_REVIEW"

    @property
    def was_returned(self) -> bool:
        return self.stage == "RETURNED"

    @property
    def who_label(self) -> str:
        parts = [self.assignee_name or "Unassigned"]
        if self.department_name:
            parts.append(self.department_name)
        if self.context_type == "TSO":
            parts.append("TSO")
        return " - ".join(parts)


# =========================================================
# BRANCH (independent workstream)
# =========================================================

@dataclass
class BranchModel:
    """One workstream on a document, with its OWN stage.

    Several branches coexist on one document, at different stages.  Nothing
    here collapses them together.
    """

    id: Optional[int] = None
    document_id: Optional[int] = None
    branch_type: str = "DEPARTMENT"
    label: str = ""
    stage: str = ""
    stage_label: str = ""

    department_id: Optional[int] = None
    department_name: Optional[str] = None
    target_user_id: Optional[int] = None
    target_user_name: Optional[str] = None
    target_context_membership_id: Optional[int] = None

    opened_by_user_id: Optional[int] = None
    instructions: Optional[str] = None
    requires_hod_validation: bool = False
    deadline: Optional[str] = None
    deadline_state: str = "none"
    round_no: int = 1

    is_active: bool = True
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
    version: int = 1

    work_items: List[WorkItemModel] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Any) -> "BranchModel":
        return cls(
            id=_get(data, "id"),
            document_id=_get(data, "document_id"),
            branch_type=_get(data, "branch_type") or "DEPARTMENT",
            label=_get(data, "label") or "",
            stage=_get(data, "stage") or "",
            stage_label=_get(data, "stage_label") or "",
            department_id=_get(data, "department_id"),
            department_name=_get(data, "department_name"),
            target_user_id=_get(data, "target_user_id"),
            target_user_name=_get(data, "target_user_name"),
            target_context_membership_id=_get(data, "target_context_membership_id"),
            opened_by_user_id=_get(data, "opened_by_user_id"),
            instructions=_get(data, "instructions"),
            requires_hod_validation=bool(_get(data, "requires_hod_validation")),
            deadline=_get(data, "deadline"),
            deadline_state=_get(data, "deadline_state") or "none",
            round_no=_get(data, "round_no") or 1,
            is_active=bool(_get(data, "is_active", True)),
            opened_at=_get(data, "opened_at"),
            closed_at=_get(data, "closed_at"),
            version=_get(data, "version") or 1,
            work_items=[WorkItemModel.from_dict(w) for w in (_get(data, "work_items") or [])],
        )

    @property
    def type_label(self) -> str:
        return {
            "DIRECTOR": "Director Review",
            "DEPARTMENT": "Department / HOD",
            "EMPLOYEE": "Direct Employee",
            "TSO": "TSO",
        }.get(self.branch_type, self.branch_type)

    @property
    def open_items(self) -> List[WorkItemModel]:
        return [w for w in self.work_items if not w.is_finished]

    @property
    def people(self) -> List[str]:
        return [w.assignee_name for w in self.work_items if w.assignee_name]

    @property
    def status_line(self) -> str:
        state = "Open" if self.is_active else "Closed"
        suffix = f" - round {self.round_no}" if self.round_no > 1 else ""
        return f"{state} - {self.stage_label}{suffix}"

    @property
    def accent_color(self) -> str:
        """Left-border accent so branch types are distinguishable at a glance."""
        return {
            "DIRECTOR": "#7C3AED",
            "DEPARTMENT": "#0F172A",
            "EMPLOYEE": "#0369A1",
            "TSO": "#B45309",
        }.get(self.branch_type, "#0F172A")


# =========================================================
# BRANCH SUMMARY (compact, for list views)
# =========================================================

@dataclass
class BranchSummaryModel:
    branch_id: Optional[int] = None
    branch_type: str = ""
    label: str = ""
    stage: str = ""
    stage_label: str = ""
    is_active: bool = True
    people: List[str] = field(default_factory=list)
    open_items: int = 0
    total_items: int = 0

    @classmethod
    def from_dict(cls, data: Any) -> "BranchSummaryModel":
        return cls(
            branch_id=_get(data, "branch_id"),
            branch_type=_get(data, "branch_type") or "",
            label=_get(data, "label") or "",
            stage=_get(data, "stage") or "",
            stage_label=_get(data, "stage_label") or "",
            is_active=bool(_get(data, "is_active", True)),
            people=list(_get(data, "people") or []),
            open_items=_get(data, "open_items") or 0,
            total_items=_get(data, "total_items") or 0,
        )

    @property
    def cell_text(self) -> str:
        """'Engineering HOD: Employee Work' - one line per branch in a table."""
        return f"{self.label}: {self.stage_label}"


# =========================================================
# REMARK
# =========================================================

@dataclass
class RemarkModel:
    id: Optional[int] = None
    document_id: Optional[int] = None
    branch_id: Optional[int] = None
    branch_label: Optional[str] = None
    work_item_id: Optional[int] = None
    author_user_id: Optional[int] = None
    author_name: Optional[str] = None
    remark_type: str = "OTHER"
    remark_text: str = ""
    provenance: str = "MANUAL"
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Any) -> "RemarkModel":
        return cls(
            id=_get(data, "id"),
            document_id=_get(data, "document_id"),
            branch_id=_get(data, "branch_id"),
            branch_label=_get(data, "branch_label"),
            work_item_id=_get(data, "work_item_id"),
            author_user_id=_get(data, "author_user_id"),
            author_name=_get(data, "author_name"),
            remark_type=_get(data, "remark_type") or "OTHER",
            remark_text=_get(data, "remark_text") or "",
            provenance=_get(data, "provenance") or "MANUAL",
            created_at=_get(data, "created_at"),
        )

    @property
    def header(self) -> str:
        scope = f" on {self.branch_label}" if self.branch_label else ""
        return f"{self.remark_type.title()} - {self.author_name or 'Unknown'}{scope} - {_fmt_datetime(self.created_at)}"


# =========================================================
# DIRECTOR REVIEW
# =========================================================

@dataclass
class DirectorReviewModel:
    """One completed Director review.  A document accumulates many; none
    replaces an earlier one."""

    id: Optional[int] = None
    document_id: Optional[int] = None
    branch_id: Optional[int] = None
    director_user_id: Optional[int] = None
    director_name: Optional[str] = None
    remark_text: str = ""
    review_no: int = 1
    requested_at: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Any) -> "DirectorReviewModel":
        return cls(
            id=_get(data, "id"),
            document_id=_get(data, "document_id"),
            branch_id=_get(data, "branch_id"),
            director_user_id=_get(data, "director_user_id"),
            director_name=_get(data, "director_name"),
            remark_text=_get(data, "remark_text") or "",
            review_no=_get(data, "review_no") or 1,
            requested_at=_get(data, "requested_at"),
            created_at=_get(data, "created_at"),
        )

    @property
    def header(self) -> str:
        return (
            f"Director Review #{self.review_no} - "
            f"{self.director_name or 'Director'} - {_fmt_datetime(self.created_at)}"
        )


# =========================================================
# WORKFLOW EVENT (history)
# =========================================================

@dataclass
class WorkflowEventModel:
    id: Optional[int] = None
    document_id: Optional[int] = None
    branch_id: Optional[int] = None
    branch_label: Optional[str] = None
    work_item_id: Optional[int] = None
    event_type: str = ""
    actor_user_id: Optional[int] = None
    actor_name: str = "System"
    actor_context_type: Optional[str] = None
    summary: str = ""
    details: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Any) -> "WorkflowEventModel":
        return cls(
            id=_get(data, "id"),
            document_id=_get(data, "document_id"),
            branch_id=_get(data, "branch_id"),
            branch_label=_get(data, "branch_label"),
            work_item_id=_get(data, "work_item_id"),
            event_type=_get(data, "event_type") or "",
            actor_user_id=_get(data, "actor_user_id"),
            actor_name=_get(data, "actor_name") or "System",
            actor_context_type=_get(data, "actor_context_type"),
            summary=_get(data, "summary") or "",
            details=_get(data, "details"),
            created_at=_get(data, "created_at"),
        )

    @property
    def when(self) -> str:
        return _fmt_datetime(self.created_at)

    @property
    def scope(self) -> str:
        return self.branch_label or "Document"
