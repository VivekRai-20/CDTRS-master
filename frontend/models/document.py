"""Frontend domain model for a CDTRS document.

A document carries a LIFECYCLE and a list of BRANCHES.  It deliberately has
no single "current owner", "current department" or "current stage": those
concepts stop meaning anything the moment a document is being worked on by
an HOD, a direct employee and the TSO at the same time, which is the normal
case here.

    Document (lifecycle: In Work)
      |
      +-- Engineering HOD      stage: Employee Work
      |     +-- Rahul   Under Work
      |     +-- Sneha   Waiting
      |
      +-- Anil (direct)        stage: Completed
      |
      +-- TSO                  stage: Technical Work
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from models.workflow import (
    DEADLINE_COLORS,
    DEADLINE_LABELS,
    AttachmentModel,
    BranchModel,
    BranchSummaryModel,
    DirectorReviewModel,
    ProgressModel,
    RemarkModel,
    WorkItemModel,
    WorkflowEventModel,
    _fmt_date,
    _fmt_datetime,
    _get,
)

LIFECYCLE_COLORS = {
    "RECEIVED": "#475569",
    "REGISTERED": "#0F766E",
    "IN_REVIEW": "#7C3AED",
    "IN_WORK": "#0369A1",
    "WITH_DS": "#B45309",
    "CLOSED": "#166534",
}

PRIORITY_COLORS = {
    "CRITICAL": "#B91C1C",
    "HIGH": "#C2410C",
    "MEDIUM": "#B45309",
    "LOW": "#166534",
}


@dataclass
class DocumentModel:
    # --- identity ---
    id: Optional[int] = None
    reference_no: Optional[str] = None
    title: str = ""
    subject: Optional[str] = None
    description: Optional[str] = None

    received_date: Optional[str] = None
    deadline: Optional[str] = None
    deadline_state: str = "none"
    source: Optional[str] = None
    sender_name: Optional[str] = None
    sender_reference: Optional[str] = None
    mode: str = "MANUAL_UPLOAD"
    priority: str = "MEDIUM"

    # --- document lifecycle (NOT the state of the work) ---
    lifecycle: str = "RECEIVED"
    lifecycle_label: str = "Received"
    version: int = 1
    ocr_status: Optional[str] = None

    created_by: Optional[int] = None
    source_message_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    registered_at: Optional[str] = None
    closed_at: Optional[str] = None
    closed_by_user_id: Optional[int] = None
    closure_remark: Optional[str] = None

    # --- the work (each branch keeps its own stage) ---
    branch_summaries: List[BranchSummaryModel] = field(default_factory=list)
    branches: List[BranchModel] = field(default_factory=list)
    people_involved: List[str] = field(default_factory=list)
    active_branch_count: int = 0
    open_work_item_count: int = 0
    my_work_items: List[WorkItemModel] = field(default_factory=list)

    # --- review & history ---
    latest_director_remark: Optional[str] = None
    has_open_director_review: bool = False
    director_reviews: List[DirectorReviewModel] = field(default_factory=list)
    remarks: List[RemarkModel] = field(default_factory=list)
    attachments: List[AttachmentModel] = field(default_factory=list)
    history: List[WorkflowEventModel] = field(default_factory=list)

    # --- advisory routing intelligence (suggestions only) ---
    suggested_department_id: Optional[int] = None
    suggested_department_name: Optional[str] = None
    suggested_employee_id: Optional[int] = None
    suggested_employee_name: Optional[str] = None
    routing_confidence: Optional[float] = None
    routing_reason: Optional[str] = None
    is_director_instruction: bool = False
    # Every department scored against the OCR text, best first:
    # [{"department": name, "department_id": id, "score": float}, ...]
    ranked_departments: List[Dict[str, Any]] = field(default_factory=list)

    # ================================================================
    # CONSTRUCTION
    # ================================================================

    @classmethod
    def from_dict(cls, data: Any) -> "DocumentModel":
        if data is None:
            return cls()
        if isinstance(data, cls):
            return data
        return cls(
            id=_get(data, "doc_id") or _get(data, "id"),
            reference_no=_get(data, "reference_no"),
            title=_get(data, "title") or "",
            subject=_get(data, "subject"),
            description=_get(data, "description"),
            received_date=_get(data, "received_date"),
            deadline=_get(data, "deadline"),
            deadline_state=_get(data, "deadline_state") or "none",
            source=_get(data, "source"),
            sender_name=_get(data, "sender_name"),
            sender_reference=_get(data, "sender_reference"),
            mode=_get(data, "mode") or "MANUAL_UPLOAD",
            priority=_get(data, "priority") or "MEDIUM",
            lifecycle=_get(data, "lifecycle") or "RECEIVED",
            lifecycle_label=_get(data, "lifecycle_label") or "Received",
            version=_get(data, "version") or 1,
            ocr_status=_get(data, "ocr_status"),
            created_by=_get(data, "created_by"),
            source_message_id=_get(data, "source_message_id"),
            created_at=_get(data, "created_at"),
            updated_at=_get(data, "updated_at"),
            registered_at=_get(data, "registered_at"),
            closed_at=_get(data, "closed_at"),
            closed_by_user_id=_get(data, "closed_by_user_id"),
            closure_remark=_get(data, "closure_remark"),
            branch_summaries=[
                BranchSummaryModel.from_dict(b) for b in (_get(data, "branch_summaries") or [])
            ],
            branches=[BranchModel.from_dict(b) for b in (_get(data, "branches") or [])],
            people_involved=list(_get(data, "people_involved") or []),
            active_branch_count=_get(data, "active_branch_count") or 0,
            open_work_item_count=_get(data, "open_work_item_count") or 0,
            my_work_items=[WorkItemModel.from_dict(w) for w in (_get(data, "my_work_items") or [])],
            latest_director_remark=_get(data, "latest_director_remark"),
            has_open_director_review=bool(_get(data, "has_open_director_review")),
            director_reviews=[
                DirectorReviewModel.from_dict(r) for r in (_get(data, "director_reviews") or [])
            ],
            remarks=[RemarkModel.from_dict(r) for r in (_get(data, "remarks") or [])],
            attachments=[AttachmentModel.from_dict(a) for a in (_get(data, "attachments") or [])],
            history=[WorkflowEventModel.from_dict(e) for e in (_get(data, "history") or [])],
            suggested_department_id=_get(data, "suggested_department_id"),
            suggested_department_name=_get(data, "suggested_department_name"),
            suggested_employee_id=_get(data, "suggested_employee_id"),
            suggested_employee_name=_get(data, "suggested_employee_name"),
            routing_confidence=_get(data, "routing_confidence"),
            routing_reason=_get(data, "routing_reason"),
            is_director_instruction=bool(_get(data, "is_director_instruction")),
            ranked_departments=[
                r for r in (_get(data, "ranked_departments") or []) if isinstance(r, dict)
            ],
        )

    # ================================================================
    # DISPLAY
    # ================================================================

    @property
    def reference(self) -> str:
        return self.reference_no or (f"DOC-{self.id}" if self.id else "-")

    @property
    def received_display(self) -> str:
        return _fmt_date(self.received_date)

    @property
    def deadline_display(self) -> str:
        return _fmt_date(self.deadline)

    @property
    def deadline_color(self) -> str:
        return DEADLINE_COLORS.get(self.deadline_state, DEADLINE_COLORS["none"])

    @property
    def deadline_label(self) -> str:
        return DEADLINE_LABELS.get(self.deadline_state, "")

    @property
    def updated_display(self) -> str:
        return _fmt_datetime(self.updated_at)

    @property
    def lifecycle_color(self) -> str:
        return LIFECYCLE_COLORS.get(self.lifecycle, "#475569")

    @property
    def priority_color(self) -> str:
        return PRIORITY_COLORS.get(str(self.priority).upper(), "#475569")

    @property
    def is_closed(self) -> bool:
        return self.lifecycle == "CLOSED"

    # ================================================================
    # BRANCH / WORK PROJECTIONS
    # ================================================================

    @property
    def active_branches(self) -> List[BranchModel]:
        return [b for b in self.branches if b.is_active]

    @property
    def work_branches(self) -> List[BranchModel]:
        """Everything except Director review - the branches where work happens."""
        return [b for b in self.branches if b.branch_type != "DIRECTOR"]

    @property
    def director_branches(self) -> List[BranchModel]:
        return [b for b in self.branches if b.branch_type == "DIRECTOR"]

    @property
    def open_director_branch(self) -> Optional[BranchModel]:
        for b in self.branches:
            if b.branch_type == "DIRECTOR" and b.is_active:
                return b
        return None

    @property
    def all_work_items(self) -> List[WorkItemModel]:
        items: List[WorkItemModel] = []
        for b in self.branches:
            items.extend(b.work_items)
        return items

    def branch_by_id(self, branch_id: Optional[int]) -> Optional[BranchModel]:
        if branch_id is None:
            return None
        return next((b for b in self.branches if b.id == branch_id), None)

    def work_items_for_user(self, user_id: Optional[int], context_id: Optional[int] = None) -> List[WorkItemModel]:
        """This person's own work on this document, scoped to one context when
        given.  A user wearing two hats keeps two separate sets of work."""
        if user_id is None:
            return []
        return [
            w for w in self.all_work_items
            if w.assigned_to_user_id == user_id
            and (context_id is None or w.assigned_to_context_membership_id == context_id)
        ]

    def branches_for_department(self, department_id: Optional[int]) -> List[BranchModel]:
        if department_id is None:
            return []
        return [
            b for b in self.branches
            if b.branch_type == "DEPARTMENT" and b.department_id == department_id
        ]

    # ================================================================
    # TABLE CELL HELPERS
    # ================================================================

    @property
    def branch_stage_lines(self) -> List[str]:
        """One line per branch, e.g. ['Engineering HOD: Employee Work',
        'Anil Kumar: Completed'].  Deliberately a LIST: a document with
        branches at different stages must read as exactly that."""
        return [s.cell_text for s in self.branch_summaries]

    @property
    def branch_stage_cell(self) -> str:
        if not self.branch_summaries:
            return "Not routed"
        return "\n".join(self.branch_stage_lines)

    @property
    def people_cell(self) -> str:
        if not self.people_involved:
            return "-"
        if len(self.people_involved) <= 3:
            return ", ".join(self.people_involved)
        return f"{', '.join(self.people_involved[:3])} +{len(self.people_involved) - 3} more"

    @property
    def workstream_summary(self) -> str:
        if not self.branch_summaries:
            return "Not routed"
        active = self.active_branch_count
        total = len(self.branch_summaries)
        return f"{active} open / {total} total"

    @property
    def latest_progress_line(self) -> str:
        """Most recent update across every person on the document."""
        latest: Optional[ProgressModel] = None
        for item in self.all_work_items:
            for p in item.progress_updates:
                if latest is None or (p.created_at or "") > (latest.created_at or ""):
                    latest = p
        if latest is None:
            return "No updates yet"
        text = " ".join(latest.description.split())
        if len(text) > 80:
            text = text[:77] + "..."
        return f"{latest.author_name}: {text}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.id,
            "reference_no": self.reference_no,
            "title": self.title,
            "subject": self.subject,
            "lifecycle": self.lifecycle,
            "priority": self.priority,
            "deadline": self.deadline,
            "version": self.version,
        }

    def __repr__(self) -> str:
        return (
            f"DocumentModel({self.reference}, lifecycle={self.lifecycle}, "
            f"branches={len(self.branches)}, work_items={len(self.all_work_items)})"
        )
