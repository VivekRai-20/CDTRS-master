"""ORM -> API serialization.

Kept separate from the workflow engine so the transport shape can change
without touching workflow rules.  The one invariant enforced here: a document
is described by a LIST of branch states, never by a single rolled-up status.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

import models
import schemas
import workflow
from models import BranchType, WorkStage


# =========================================================
# LEAVES
# =========================================================

def attachment(a: models.Attachment) -> schemas.AttachmentResponse:
    return schemas.AttachmentResponse(
        id=a.id,
        document_id=a.document_id,
        progress_update_id=a.progress_update_id,
        work_item_id=a.work_item_id,
        file_name=a.file_name,
        file_type=a.file_type,
        file_size=a.file_size,
        attachment_type=a.attachment_type,
        uploaded_by_user_id=a.uploaded_by_user_id,
        uploaded_by_name=a.uploaded_by_name,
        created_at=a.created_at,
    )


def progress(p: models.ProgressUpdate) -> schemas.ProgressResponse:
    return schemas.ProgressResponse(
        id=p.id,
        document_id=p.document_id,
        work_item_id=p.work_item_id,
        author_user_id=p.author_user_id,
        author_name=p.author_name,
        description=p.description,
        stage_at_time=p.stage_at_time,
        created_at=p.created_at,
        attachments=[attachment(a) for a in p.attachments],
    )


def work_review(r: models.WorkItemReview) -> schemas.WorkReviewResponse:
    return schemas.WorkReviewResponse(
        id=r.id,
        work_item_id=r.work_item_id,
        reviewer_user_id=r.reviewer_user_id,
        reviewer_name=r.reviewer_name,
        outcome=r.outcome,
        note=r.note,
        created_at=r.created_at,
    )


def remark(r: models.DocumentRemark) -> schemas.RemarkResponse:
    return schemas.RemarkResponse(
        id=r.id,
        document_id=r.document_id,
        branch_id=r.branch_id,
        branch_label=r.branch_label,
        work_item_id=r.work_item_id,
        author_user_id=r.author_user_id,
        author_name=r.author_name,
        remark_type=r.remark_type,
        remark_text=r.remark_text,
        provenance=r.provenance,
        created_at=r.created_at,
    )


def director_review(r: models.DirectorReview) -> schemas.DirectorReviewResponse:
    return schemas.DirectorReviewResponse(
        id=r.id,
        document_id=r.document_id,
        branch_id=r.branch_id,
        director_user_id=r.director_user_id,
        director_name=r.director_name,
        remark_text=r.remark_text,
        review_no=r.review_no,
        requested_at=r.requested_at,
        created_at=r.created_at,
    )


def event(e: models.WorkflowEvent) -> schemas.WorkflowEventResponse:
    return schemas.WorkflowEventResponse(
        id=e.id,
        document_id=e.document_id,
        branch_id=e.branch_id,
        branch_label=e.branch_label,
        work_item_id=e.work_item_id,
        event_type=e.event_type,
        actor_user_id=e.actor_user_id,
        actor_name=e.actor_name,
        actor_context_type=e.actor_context_type,
        summary=e.summary,
        details=e.details,
        created_at=e.created_at,
    )


def context(c: models.WorkContextMembership) -> schemas.WorkContextResponse:
    return schemas.WorkContextResponse(
        id=c.id,
        user_id=c.user_id,
        context_type=c.context_type,
        department_id=c.department_id,
        department_name=c.department_name,
        label=c.label,
        is_active=c.is_active,
    )


def user(u: models.User, contexts: Optional[List[models.WorkContextMembership]] = None) -> schemas.UserResponse:
    memberships = contexts if contexts is not None else [
        m for m in u.context_memberships if m.is_active
    ]
    return schemas.UserResponse(
        id=u.id,
        username=u.username,
        full_name=u.full_name,
        role=u.role,
        employee_code=u.employee_code,
        designation=u.designation,
        email=u.email,
        outlook_email=u.outlook_email,
        gov_email=u.gov_email,
        department_id=u.department_id,
        department=u.department,
        is_active=u.is_active,
        contexts=[context(m) for m in memberships],
    )


# =========================================================
# WORK ITEMS & BRANCHES
# =========================================================

def work_item(w: models.WorkItem, include_progress: bool = True) -> schemas.WorkItemResponse:
    return schemas.WorkItemResponse(
        id=w.id,
        document_id=w.document_id,
        branch_id=w.branch_id,
        branch_label=w.branch_label,
        team_id=w.team_id,
        team_name=w.team_name,
        assigned_to_user_id=w.assigned_to_user_id,
        assignee_name=w.assignee_name,
        assigned_to_context_membership_id=w.assigned_to_context_membership_id,
        context_type=w.context_type,
        department_name=w.department_name,
        assigned_by_user_id=w.assigned_by_user_id,
        assigner_name=w.assigner_name,
        instructions=w.instructions,
        deadline=w.deadline,
        deadline_state=workflow.overdue_state(w.deadline),
        stage=w.stage,
        stage_label=workflow.work_stage_label(w.stage),
        requires_validation=w.requires_validation,
        round_no=w.round_no,
        is_active=w.is_active,
        latest_progress_text=w.latest_progress_text,
        last_update_at=w.last_update_at,
        attachment_count=w.attachment_count,
        assigned_at=w.assigned_at,
        started_at=w.started_at,
        submitted_at=w.submitted_at,
        completed_at=w.completed_at,
        version=w.version,
        progress_updates=[progress(p) for p in w.progress_updates] if include_progress else [],
        reviews=[work_review(r) for r in w.reviews] if include_progress else [],
    )


def branch(b: models.DocumentBranch, include_progress: bool = True) -> schemas.BranchResponse:
    return schemas.BranchResponse(
        id=b.id,
        document_id=b.document_id,
        branch_type=b.branch_type,
        label=b.label,
        stage=b.stage,
        stage_label=workflow.branch_stage_label(b.stage),
        department_id=b.department_id,
        department_name=b.department_name,
        target_user_id=b.target_user_id,
        target_user_name=b.target_user_name,
        target_context_membership_id=b.target_context_membership_id,
        opened_by_user_id=b.opened_by_user_id,
        instructions=b.instructions,
        requires_hod_validation=b.requires_hod_validation,
        deadline=b.deadline,
        deadline_state=workflow.overdue_state(b.deadline),
        round_no=b.round_no,
        is_active=b.is_active,
        opened_at=b.opened_at,
        closed_at=b.closed_at,
        version=b.version,
        work_items=[work_item(w, include_progress) for w in b.work_items],
    )


def branch_summary(b: models.DocumentBranch) -> schemas.BranchSummary:
    items = list(b.work_items)
    return schemas.BranchSummary(
        branch_id=b.id,
        branch_type=b.branch_type,
        label=b.label,
        stage=b.stage,
        stage_label=workflow.branch_stage_label(b.stage),
        is_active=b.is_active,
        people=[w.assignee_name for w in items if w.assignee_name],
        open_items=sum(1 for w in items if w.stage not in workflow.TERMINAL_WORK_STAGES),
        total_items=len(items),
    )


# =========================================================
# DOCUMENTS
# =========================================================

def _base_document_fields(d: models.Document) -> Dict[str, Any]:
    open_items = sum(
        1 for w in d.work_items if w.stage not in workflow.TERMINAL_WORK_STAGES
    )
    return dict(
        doc_id=d.doc_id,
        reference_no=d.reference_no,
        title=d.title,
        subject=d.subject,
        description=d.description,
        source=d.source,
        sender_name=d.sender_name,
        priority=d.priority,
        lifecycle=d.lifecycle,
        lifecycle_label=workflow.lifecycle_label(d.lifecycle),
        received_date=d.received_date,
        deadline=d.deadline,
        deadline_state=workflow.overdue_state(d.deadline),
        ocr_status=d.ocr_status,
        version=d.version,
        branch_summaries=[branch_summary(b) for b in d.branches],
        people_involved=d.people_involved,
        active_branch_count=len(d.active_branches),
        open_work_item_count=open_items,
        latest_director_remark=d.latest_director_remark,
        has_open_director_review=d.open_director_review is not None,
        created_at=d.created_at,
        updated_at=d.updated_at,
        closed_at=d.closed_at,
    )


def document_list(
    d: models.Document,
    my_work_items: Optional[List[models.WorkItem]] = None,
) -> schemas.DocumentListResponse:
    fields = _base_document_fields(d)
    fields["my_work_items"] = [
        work_item(w, include_progress=False) for w in (my_work_items or [])
    ]
    return schemas.DocumentListResponse(**fields)


def document_detail(
    db: Session,
    d: models.Document,
    include_history: bool = True,
) -> schemas.DocumentDetailResponse:
    fields = _base_document_fields(d)
    suggestion = d.routing_suggestion
    fields.update(
        mode=d.mode,
        created_by=d.created_by,
        source_message_id=d.source_message_id,
        registered_at=d.registered_at,
        closed_by_user_id=d.closed_by_user_id,
        closure_remark=d.closure_remark,
        branches=[branch(b) for b in d.branches],
        remarks=[remark(r) for r in d.remarks],
        director_reviews=[director_review(r) for r in d.director_reviews],
        attachments=[attachment(a) for a in d.attachments],
        history=[event(e) for e in workflow.document_history(db, d.doc_id)] if include_history else [],
        suggested_department_id=suggestion.suggested_department_id if suggestion else None,
        suggested_department_name=suggestion.suggested_department_name if suggestion else None,
        suggested_employee_id=suggestion.suggested_employee_id if suggestion else None,
        suggested_employee_name=suggestion.suggested_employee_name if suggestion else None,
        routing_confidence=suggestion.routing_confidence if suggestion else None,
        routing_reason=suggestion.routing_reason if suggestion else None,
        is_director_instruction=bool(suggestion.is_director_instruction) if suggestion else False,
        ranked_departments=(suggestion.ranked_departments or []) if suggestion else [],
    )
    return schemas.DocumentDetailResponse(**fields)


def documents_with_my_work(
    db: Session,
    docs: List[models.Document],
    user_id: Optional[int],
    context_membership_id: Optional[int],
) -> List[schemas.DocumentListResponse]:
    """List view that also carries the caller's own work items, so task pages
    can show stage / latest progress / deadline per row."""
    out: List[schemas.DocumentListResponse] = []
    for d in docs:
        mine = [
            w for w in d.work_items
            if user_id is not None
            and w.assigned_to_user_id == user_id
            and (
                context_membership_id is None
                or w.assigned_to_context_membership_id == context_membership_id
            )
        ]
        out.append(document_list(d, mine))
    return out


# =========================================================
# MISC
# =========================================================

def notification(n: models.Notification) -> schemas.NotificationResponse:
    return schemas.NotificationResponse(
        id=n.id,
        user_id=n.user_id,
        context_membership_id=n.context_membership_id,
        document_id=n.document_id,
        branch_id=n.branch_id,
        work_item_id=n.work_item_id,
        title=n.title,
        message=n.message,
        is_read=n.is_read,
        created_at=n.created_at,
    )


def reminder(r: models.Reminder) -> schemas.ReminderResponse:
    return schemas.ReminderResponse(
        id=r.id,
        document_id=r.document_id,
        work_item_id=r.work_item_id,
        recipient_user_id=r.recipient_user_id,
        reason=r.reason,
        message=r.message,
        due_at=r.due_at,
        sent_at=r.sent_at,
        is_read=r.is_read,
    )


def dashboard(db: Session, data: Dict[str, Any]) -> schemas.DashboardResponse:
    return schemas.DashboardResponse(
        context_type=data.get("context_type"),
        department=data.get("department"),
        cards=[schemas.DashboardCard(**c) for c in data.get("cards", [])],
        documents=[document_list(d) for d in data.get("documents", [])],
    )
