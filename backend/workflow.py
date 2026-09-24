"""
CDTRS workflow engine.

Everything that moves a document through the organisation lives here.  The
rules it enforces:

*   The DS is the only actor who opens branches and the only actor who closes
    a document.
*   The Director reviews and remarks.  The Director never closes anything.
*   Branches are independent.  Nothing in this module ever collapses several
    branch stages into one value, and nothing lets one branch overwrite
    another.
*   A WorkItem belongs to exactly one person.  Teams group work items; they
    never replace them.
*   Progress is free text.  There is no percentage and no roll-up.
*   History is append-only.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

import models
from models import (
    BranchStage,
    BranchType,
    DocumentLifecycle,
    RemarkType,
    ReminderReason,
    ReviewOutcome,
    UserRole,
    WorkContextType,
    WorkStage,
)


class WorkflowError(Exception):
    """A workflow rule was violated.  Surfaces to the API as HTTP 400."""


class PermissionDenied(WorkflowError):
    """The active context is not allowed to perform this action."""


# =========================================================
# STAGE VOCABULARY
# =========================================================

#: Which branch stages are legal for each branch type.
BRANCH_STAGES: Dict[BranchType, List[BranchStage]] = {
    BranchType.DIRECTOR: [
        BranchStage.REVIEW_REQUESTED,
        BranchStage.UNDER_DIRECTOR_REVIEW,
        BranchStage.REMARK_ADDED,
        BranchStage.RETURNED_TO_DS,
        BranchStage.CANCELLED,
    ],
    BranchType.DEPARTMENT: [
        BranchStage.HOD_REVIEW,
        BranchStage.EMPLOYEE_ASSIGNMENT,
        BranchStage.EMPLOYEE_WORK,
        BranchStage.HOD_VALIDATION,
        BranchStage.FURTHER_WORK,
        BranchStage.COMPLETED,
        BranchStage.CANCELLED,
    ],
    BranchType.EMPLOYEE: [
        BranchStage.ASSIGNED,
        BranchStage.IN_PROGRESS,
        BranchStage.SUBMITTED,
        BranchStage.FURTHER_WORK,
        BranchStage.COMPLETED,
        BranchStage.CANCELLED,
    ],
    BranchType.TSO: [
        BranchStage.ASSIGNED,
        BranchStage.IN_PROGRESS,
        BranchStage.SUBMITTED,
        BranchStage.FURTHER_WORK,
        BranchStage.COMPLETED,
        BranchStage.CANCELLED,
    ],
}

#: Stage a branch starts in when it is opened.
INITIAL_BRANCH_STAGE: Dict[BranchType, BranchStage] = {
    BranchType.DIRECTOR: BranchStage.REVIEW_REQUESTED,
    BranchType.DEPARTMENT: BranchStage.HOD_REVIEW,
    BranchType.EMPLOYEE: BranchStage.ASSIGNED,
    BranchType.TSO: BranchStage.ASSIGNED,
}

#: Stages a worker is allowed to move their own work item into.
WORKER_SELECTABLE_STAGES: List[WorkStage] = [
    WorkStage.UNDER_WORK,
    WorkStage.WAITING,
    WorkStage.SUBMITTED,
]

TERMINAL_WORK_STAGES = (WorkStage.COMPLETED, WorkStage.CANCELLED)

#: Human labels used in history text and in the UI.
BRANCH_STAGE_LABELS: Dict[str, str] = {
    BranchStage.REVIEW_REQUESTED.value: "Review Requested",
    BranchStage.UNDER_DIRECTOR_REVIEW.value: "Under Director Review",
    BranchStage.REMARK_ADDED.value: "Director Remark Added",
    BranchStage.RETURNED_TO_DS.value: "Returned to DS",
    BranchStage.HOD_REVIEW.value: "HOD Review",
    BranchStage.EMPLOYEE_ASSIGNMENT.value: "Employee Assignment",
    BranchStage.EMPLOYEE_WORK.value: "Employee Work",
    BranchStage.HOD_VALIDATION.value: "HOD Validation",
    BranchStage.ASSIGNED.value: "Assigned",
    BranchStage.IN_PROGRESS.value: "In Progress",
    BranchStage.SUBMITTED.value: "Submitted",
    BranchStage.FURTHER_WORK.value: "Further Work",
    BranchStage.COMPLETED.value: "Completed",
    BranchStage.CANCELLED.value: "Cancelled",
}

WORK_STAGE_LABELS: Dict[str, str] = {
    WorkStage.ASSIGNED.value: "Assigned",
    WorkStage.UNDER_WORK.value: "Under Work",
    WorkStage.WAITING.value: "Waiting",
    WorkStage.SUBMITTED.value: "Submitted",
    WorkStage.UNDER_REVIEW.value: "Under Review",
    WorkStage.RETURNED.value: "Returned",
    WorkStage.COMPLETED.value: "Completed",
    WorkStage.CANCELLED.value: "Cancelled",
}

LIFECYCLE_LABELS: Dict[str, str] = {
    DocumentLifecycle.RECEIVED.value: "Received",
    DocumentLifecycle.REGISTERED.value: "Registered",
    DocumentLifecycle.IN_REVIEW.value: "Under Director Review",
    DocumentLifecycle.IN_WORK.value: "In Work",
    DocumentLifecycle.WITH_DS.value: "With DS",
    DocumentLifecycle.CLOSED.value: "Closed",
}


def branch_stage_label(stage: Any) -> str:
    value = stage.value if hasattr(stage, "value") else str(stage or "")
    return BRANCH_STAGE_LABELS.get(value, value.replace("_", " ").title())


def work_stage_label(stage: Any) -> str:
    value = stage.value if hasattr(stage, "value") else str(stage or "")
    return WORK_STAGE_LABELS.get(value, value.replace("_", " ").title())


def lifecycle_label(value: Any) -> str:
    raw = value.value if hasattr(value, "value") else str(value or "")
    return LIFECYCLE_LABELS.get(raw, raw.replace("_", " ").title())


# =========================================================
# CONTEXT RESOLUTION & AUTHORIZATION
# =========================================================

def resolve_context(
    db: Session,
    user: models.User,
    context_id: Optional[int] = None,
) -> Optional[models.WorkContextMembership]:
    """Return the caller's active work context.

    An explicit context_id must belong to the caller.  With no explicit id we
    fall back to the membership matching the account's primary role, and
    finally to any active membership.
    """
    if context_id is not None:
        membership = (
            db.query(models.WorkContextMembership)
            .filter(
                models.WorkContextMembership.id == context_id,
                models.WorkContextMembership.user_id == user.id,
                models.WorkContextMembership.is_active.is_(True),
            )
            .first()
        )
        if membership is None:
            raise PermissionDenied("The selected work context does not belong to this user.")
        return membership

    memberships = (
        db.query(models.WorkContextMembership)
        .filter(
            models.WorkContextMembership.user_id == user.id,
            models.WorkContextMembership.is_active.is_(True),
        )
        .order_by(models.WorkContextMembership.id.asc())
        .all()
    )
    if not memberships:
        return None

    try:
        preferred = WorkContextType(user.role.value)
    except ValueError:
        preferred = None
    if preferred is not None:
        for m in memberships:
            if m.context_type == preferred:
                return m
    return memberships[0]


def require_context(
    db: Session,
    user: models.User,
    context_id: Optional[int],
    *allowed: WorkContextType,
) -> models.WorkContextMembership:
    """Resolve the active context and assert it is one of `allowed`."""
    context = resolve_context(db, user, context_id)
    if context is None:
        raise PermissionDenied("No active work context is available for this user.")
    if allowed and context.context_type not in allowed:
        names = ", ".join(c.value for c in allowed)
        raise PermissionDenied(
            f"This action requires a {names} work context; "
            f"the active context is {context.context_type.value}."
        )
    return context


def get_context_for(
    db: Session,
    user_id: int,
    context_type: WorkContextType,
    department_id: Optional[int] = None,
) -> Optional[models.WorkContextMembership]:
    """Find a user's active membership of a given type, optionally scoped to a
    department.  Department-scoped lookup falls back to an unscoped membership
    of the same type."""
    q = db.query(models.WorkContextMembership).filter(
        models.WorkContextMembership.user_id == user_id,
        models.WorkContextMembership.context_type == context_type,
        models.WorkContextMembership.is_active.is_(True),
    )
    if department_id is not None:
        scoped = q.filter(models.WorkContextMembership.department_id == department_id).first()
        if scoped:
            return scoped
    return q.order_by(models.WorkContextMembership.id.asc()).first()


def department_hod_contexts(db: Session, department_id: int) -> List[models.WorkContextMembership]:
    """Every active HOD context for a department.  A department may legitimately
    have more than one HOD, and one person may be HOD of several departments."""
    return (
        db.query(models.WorkContextMembership)
        .join(models.User, models.User.id == models.WorkContextMembership.user_id)
        .filter(
            models.WorkContextMembership.context_type == WorkContextType.HOD,
            models.WorkContextMembership.department_id == department_id,
            models.WorkContextMembership.is_active.is_(True),
            models.User.is_active.is_(True),
        )
        .all()
    )


def active_tso_context(db: Session) -> Optional[models.WorkContextMembership]:
    """The single designated TSO for the organisation."""
    return (
        db.query(models.WorkContextMembership)
        .join(models.User, models.User.id == models.WorkContextMembership.user_id)
        .filter(
            models.WorkContextMembership.context_type == WorkContextType.TSO,
            models.WorkContextMembership.is_active.is_(True),
            models.User.is_active.is_(True),
        )
        .order_by(models.WorkContextMembership.id.asc())
        .first()
    )


def set_active_tso(db: Session, user_id: int, department_id: Optional[int] = None) -> models.WorkContextMembership:
    """Designate one user as THE TSO, deactivating any previous TSO context."""
    user = db.query(models.User).filter(models.User.id == user_id, models.User.is_active.is_(True)).first()
    if not user:
        raise WorkflowError("Cannot designate an inactive or unknown user as TSO.")

    existing = (
        db.query(models.WorkContextMembership)
        .filter(models.WorkContextMembership.context_type == WorkContextType.TSO)
        .all()
    )
    target: Optional[models.WorkContextMembership] = None
    for membership in existing:
        if membership.user_id == user_id:
            target = membership
        elif membership.is_active:
            membership.is_active = False

    if target is None:
        target = models.WorkContextMembership(
            user_id=user_id,
            context_type=WorkContextType.TSO,
            department_id=department_id,
            is_active=True,
        )
        db.add(target)
    else:
        target.is_active = True
    db.flush()
    return target


def director_contexts(db: Session) -> List[models.WorkContextMembership]:
    return (
        db.query(models.WorkContextMembership)
        .join(models.User, models.User.id == models.WorkContextMembership.user_id)
        .filter(
            models.WorkContextMembership.context_type == WorkContextType.DIRECTOR,
            models.WorkContextMembership.is_active.is_(True),
            models.User.is_active.is_(True),
        )
        .all()
    )


def ds_contexts(db: Session) -> List[models.WorkContextMembership]:
    return (
        db.query(models.WorkContextMembership)
        .join(models.User, models.User.id == models.WorkContextMembership.user_id)
        .filter(
            models.WorkContextMembership.context_type == WorkContextType.DS,
            models.WorkContextMembership.is_active.is_(True),
            models.User.is_active.is_(True),
        )
        .all()
    )


# =========================================================
# HISTORY & NOTIFICATIONS
# =========================================================

def record_event(
    db: Session,
    *,
    document_id: int,
    event_type: str,
    summary: str,
    actor: Optional[models.User] = None,
    context: Optional[models.WorkContextMembership] = None,
    branch_id: Optional[int] = None,
    work_item_id: Optional[int] = None,
    details: Optional[str] = None,
) -> models.WorkflowEvent:
    """Append one immutable entry to the document's history."""
    event = models.WorkflowEvent(
        document_id=document_id,
        branch_id=branch_id,
        work_item_id=work_item_id,
        event_type=event_type,
        actor_user_id=actor.id if actor else None,
        actor_context_membership_id=context.id if context else None,
        actor_context_type=context.context_type.value if context else None,
        summary=summary[:300],
        details=details,
        created_at=datetime.now(),
    )
    db.add(event)
    db.flush()
    return event


def _setting(db: Session, key: str, default: str = "") -> str:
    row = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    return row.value if row else default


def _email_enabled(db: Session) -> bool:
    return _setting(db, "mail.notifications_enabled", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )


#: Outgoing mail runs off the request thread.  A slow or unreachable mail
#: provider must never hold up routing, assignment or a progress update.
_MAIL_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cdtrs-mail")


def _send_email_async(
    user_id: int,
    document_id: int,
    title: str,
    message: str,
    work_item_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    include_progress_attachments: bool = False,
) -> None:
    """Runs on a worker thread with its own session; SQLAlchemy sessions are
    not shareable across threads."""
    try:
        from database import SessionLocal
        from mail.service import mail_service

        db = SessionLocal()
        try:
            mail_service.send_workflow_notification(
            db=db,
            doc_id=document_id,
            recipient_user_id=user_id,
            title=title,
            message=message,
            work_item_id=work_item_id,
            branch_id=branch_id,
            include_progress_attachments=include_progress_attachments,
        )
        finally:
            db.close()
    except Exception:
        pass


def _dispatch_email(
    db: Session,
    user_id: int,
    document_id: Optional[int],
    title: str,
    message: str,
    work_item_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    include_progress_attachments: bool = False,
) -> None:
    """Best effort outgoing mail.  Notifications must never fail or delay a
    workflow action, so this is queued and every problem is swallowed - the
    in-app notification has already been recorded either way."""
    if document_id is None or not _email_enabled(db):
        return
    try:
        from mail.service import mail_service
        if not mail_service.is_configured():
            return
        _MAIL_POOL.submit(
            _send_email_async,
            user_id,
            document_id,
            title,
            message,
            work_item_id,
            branch_id,
            include_progress_attachments,
        )
    except Exception:
        pass


def notify(
    db: Session,
    *,
    user_id: int,
    title: str,
    message: str,
    context_membership_id: Optional[int] = None,
    document_id: Optional[int] = None,
    branch_id: Optional[int] = None,
    work_item_id: Optional[int] = None,
    event_id: Optional[int] = None,
    email: bool = True,
    include_progress_attachments: bool = False,
) -> models.Notification:
    """Raise an in-app notification addressed at one specific work context, and
    mirror it by email when mail notifications are switched on."""
    note = models.Notification(
        user_id=user_id,
        context_membership_id=context_membership_id,
        document_id=document_id,
        branch_id=branch_id,
        work_item_id=work_item_id,
        event_id=event_id,
        title=title[:200],
        message=message,
        is_read=False,
        created_at=datetime.now(),
    )
    db.add(note)
    if email:
        _dispatch_email(
            db,
            user_id,
            document_id,
            title,
            message,
            work_item_id=work_item_id,
            branch_id=branch_id,
            include_progress_attachments=include_progress_attachments,
        )
    return note


def add_remark(
    db: Session,
    *,
    document_id: int,
    author: models.User,
    context: Optional[models.WorkContextMembership],
    remark_text: str,
    remark_type: RemarkType,
    branch_id: Optional[int] = None,
    work_item_id: Optional[int] = None,
    provenance: str = "MANUAL",
) -> models.DocumentRemark:
    """Append a remark.  Remarks are never edited and never replaced."""
    remark = models.DocumentRemark(
        document_id=document_id,
        branch_id=branch_id,
        work_item_id=work_item_id,
        author_user_id=author.id,
        author_context_membership_id=context.id if context else None,
        remark_type=remark_type,
        remark_text=remark_text,
        provenance=provenance,
        created_at=datetime.now(),
    )
    db.add(remark)
    db.flush()
    return remark


# =========================================================
# STATE RECOMPUTATION
# =========================================================

def recompute_branch_stage(db: Session, branch: models.DocumentBranch) -> None:
    """Derive a branch's stage from its own work items.

    Only ever looks at this branch.  Never reads, and never writes, any other
    branch."""
    if branch.branch_type == BranchType.DIRECTOR:
        return  # driven explicitly by the Director review actions
    if branch.stage in (BranchStage.CANCELLED,) or not branch.is_active:
        return

    # Query directly to avoid stale relationships after db.flush()
    items = db.query(models.WorkItem).filter(models.WorkItem.branch_id == branch.id).all()
    live = [w for w in items if w.stage not in TERMINAL_WORK_STAGES]

    if not items:
        branch.stage = (
            BranchStage.HOD_REVIEW
            if branch.branch_type == BranchType.DEPARTMENT
            else BranchStage.ASSIGNED
        )
        return

    if not live:
        # Every person on this branch has finished.  The branch is done; other
        # branches on the same document are untouched.
        branch.stage = BranchStage.COMPLETED
        if branch.is_active:
            branch.is_active = False
            branch.closed_at = datetime.now()
        return

    if branch.branch_type == BranchType.DEPARTMENT:
        if any(w.stage == WorkStage.UNDER_REVIEW for w in live):
            branch.stage = BranchStage.HOD_VALIDATION
        elif all(w.stage == WorkStage.ASSIGNED for w in live):
            branch.stage = BranchStage.EMPLOYEE_ASSIGNMENT
        else:
            branch.stage = BranchStage.EMPLOYEE_WORK
    else:
        if all(w.stage == WorkStage.SUBMITTED for w in live):
            branch.stage = BranchStage.SUBMITTED
        elif all(w.stage == WorkStage.ASSIGNED for w in live):
            branch.stage = BranchStage.ASSIGNED
        else:
            branch.stage = BranchStage.IN_PROGRESS

    branch.version += 1


def recompute_lifecycle(db: Session, doc: models.Document) -> None:
    """Derive the DOCUMENT lifecycle.

    This is deliberately coarse and never attempts to describe the work: a
    document sits in IN_WORK whether one branch or five branches are running,
    and whatever stages those branches are individually at."""
    if doc.closed_at is not None:
        doc.lifecycle = DocumentLifecycle.CLOSED
        return

    branches = list(doc.branches)
    active = [b for b in branches if b.is_active]
    active_work = [b for b in active if b.branch_type != BranchType.DIRECTOR]
    active_review = [b for b in active if b.branch_type == BranchType.DIRECTOR]

    if active_work:
        doc.lifecycle = DocumentLifecycle.IN_WORK
    elif active_review:
        doc.lifecycle = DocumentLifecycle.IN_REVIEW
    elif branches:
        doc.lifecycle = DocumentLifecycle.WITH_DS
    elif doc.registered_at is not None:
        doc.lifecycle = DocumentLifecycle.REGISTERED
    else:
        doc.lifecycle = DocumentLifecycle.RECEIVED

    doc.updated_at = datetime.now()


def _touch(doc: models.Document) -> None:
    doc.version += 1
    doc.updated_at = datetime.now()


def _get_document(db: Session, document_id: int) -> models.Document:
    doc = db.query(models.Document).filter(models.Document.doc_id == document_id).first()
    if not doc:
        raise WorkflowError(f"Document {document_id} not found.")
    return doc


def _check_version(doc: models.Document, expected_version: Optional[int]) -> None:
    if expected_version is not None and doc.version != expected_version:
        raise WorkflowError(
            "This document was changed by someone else while you were working on it. "
            "Reload it and try again."
        )


def _assert_open(doc: models.Document) -> None:
    if doc.lifecycle == DocumentLifecycle.CLOSED:
        raise WorkflowError("This document is closed. Reopen it before making further changes.")


# =========================================================
# ROUTING - OPENING BRANCHES (DS only)
# =========================================================

def _find_open_branch(
    db: Session,
    document_id: int,
    branch_type: BranchType,
    department_id: Optional[int],
    target_user_id: Optional[int],
) -> Optional[models.DocumentBranch]:
    q = db.query(models.DocumentBranch).filter(
        models.DocumentBranch.document_id == document_id,
        models.DocumentBranch.branch_type == branch_type,
        models.DocumentBranch.is_active.is_(True),
    )
    if branch_type == BranchType.DEPARTMENT:
        q = q.filter(models.DocumentBranch.department_id == department_id)
    elif branch_type == BranchType.DIRECTOR:
        pass  # only one Director review may be open at a time
    else:
        q = q.filter(models.DocumentBranch.target_user_id == target_user_id)
    return q.first()


def _resolve_branch_target(
    db: Session,
    branch_type: BranchType,
    *,
    department_id: Optional[int],
    target_user_id: Optional[int],
) -> Dict[str, Any]:
    """Validate a routing request and resolve the concrete target context."""

    if branch_type == BranchType.DEPARTMENT:
        if not department_id:
            raise WorkflowError("A department is required to route to an HOD.")
        dept = (
            db.query(models.Department)
            .filter(models.Department.id == department_id, models.Department.is_active.is_(True))
            .first()
        )
        if not dept:
            raise WorkflowError(f"Department {department_id} is not an active department.")
        hods = department_hod_contexts(db, department_id)
        if not hods:
            raise WorkflowError(f"No active HOD is configured for {dept.name}.")
        return {
            "department_id": department_id,
            "target_user_id": None,
            "target_context_membership_id": None,
            "label": f"{dept.name} HOD",
            "notify_contexts": hods,
        }

    if branch_type == BranchType.DIRECTOR:
        directors = director_contexts(db)
        if not directors:
            raise WorkflowError("No active Director is configured in the system.")
        chosen = None
        if target_user_id:
            chosen = next((c for c in directors if c.user_id == target_user_id), None)
            if chosen is None:
                raise WorkflowError("The selected user does not hold an active Director context.")
        else:
            chosen = directors[0]
        return {
            "department_id": None,
            "target_user_id": chosen.user_id,
            "target_context_membership_id": chosen.id,
            "label": "Director Review",
            "notify_contexts": [chosen],
        }

    if branch_type == BranchType.TSO:
        tso = active_tso_context(db)
        if not tso:
            raise WorkflowError(
                "No active TSO is designated. An administrator must designate one before routing to TSO."
            )
        if target_user_id and target_user_id != tso.user_id:
            raise WorkflowError("Only the currently designated TSO can receive TSO work.")
        return {
            "department_id": tso.department_id,
            "target_user_id": tso.user_id,
            "target_context_membership_id": tso.id,
            "label": "TSO",
            "notify_contexts": [tso],
        }

    # BranchType.EMPLOYEE - direct DS to employee, no HOD involved
    if not target_user_id:
        raise WorkflowError("An employee must be selected for a direct assignment.")
    target = (
        db.query(models.User)
        .filter(models.User.id == target_user_id, models.User.is_active.is_(True))
        .first()
    )
    if not target:
        raise WorkflowError("The selected employee is not an active user.")
    emp_context = get_context_for(db, target.id, WorkContextType.EMPLOYEE, target.department_id)
    if not emp_context:
        raise WorkflowError(f"{target.full_name} does not hold an active Employee work context.")
    return {
        "department_id": emp_context.department_id,
        "target_user_id": target.id,
        "target_context_membership_id": emp_context.id,
        "label": target.full_name,
        "notify_contexts": [emp_context],
    }

def _ocr_prior_director_review_detected(
    db: Session,
    doc: models.Document,
) -> bool:
    """
    Return True when the OCR pipeline has explicitly confirmed that
    the document already contains a prior Director review/instruction.

    The OCR system is responsible for detecting and interpreting the
    handwritten Director content. The workflow engine only consumes
    the final confirmation.
    """
    field = (
        db.query(models.DocumentExtractedField)
        .filter(
            models.DocumentExtractedField.document_id == doc.doc_id,
            models.DocumentExtractedField.field_name == "PRIOR_DIRECTOR_REVIEW_DETECTED",
        )
        .first()
    )

    if not field:
        return False

    value = field.verified_value

    return str(value).strip().lower() in {
        "true",
        "1",
        "yes",
        "detected",
        "confirmed",
    }
def _director_review_satisfied(
    db: Session,
    doc: models.Document,
) -> bool:
    """
    Director review is satisfied when either:

    1. A Director has already completed a review, or
    2. OCR has explicitly confirmed a prior Director review.
    """

    completed_review = (
        db.query(models.DirectorReview.id)
        .filter(
            models.DirectorReview.document_id == doc.doc_id,
        )
        .first()
        is not None
    )

    return completed_review or _ocr_prior_director_review_detected(db, doc)

def _assert_director_review_before_work_routing(
    db: Session,
    doc: models.Document,
    requests: Sequence[Dict[str, Any]],
) -> None:
    """
    Prevent DS from routing to HOD, Employee or TSO before the
    mandatory Director review is satisfied.

    Routing to Director itself is allowed because that is the
    mandatory first step.

    Director + work recipients cannot be sent in the same routing
    action.
    """

    branch_types = set()

    for request in requests:
        branch_type = request.get("branch_type")

        if not isinstance(branch_type, BranchType):
            branch_type = BranchType(str(branch_type))

        branch_types.add(branch_type)

    # Sending to Director is the mandatory first step.
    if branch_types == {BranchType.DIRECTOR}:
        return

    # Do not allow DS to combine Director + work routing.
    if BranchType.DIRECTOR in branch_types:
        raise WorkflowError(
            "Director review must be completed before routing the document "
            "to an HOD, employee or TSO."
        )

    # HOD / Employee / TSO routing requires a satisfied Director gate.
    if not _director_review_satisfied(db, doc):
        raise WorkflowError(
            "This document must undergo Director review before it can be "
            "routed to an HOD, employee or TSO."
        )
    
def open_branches(
    db: Session,
    *,
    document_id: int,
    requests: Sequence[Dict[str, Any]],
    actor: models.User,
    context_id: Optional[int] = None,
    expected_version: Optional[int] = None,
) -> List[models.DocumentBranch]:
    """DS routes a document to one or more targets at once.

    Every request in `requests` becomes its own branch and they all coexist.
    Routing to a target that already has an open branch extends that branch
    with a new round rather than duplicating it, so nothing that already
    happened on it is lost.

    Each request is a dict with:
        branch_type, department_id, target_user_id, instructions,
        requires_hod_validation, deadline, assignee_user_ids, team_name
    """
    context = require_context(db, actor, context_id, WorkContextType.DS)
    doc = _get_document(db, document_id)
    _check_version(doc, expected_version)
    _assert_open(doc)

    if not requests:
        raise WorkflowError("Select at least one recipient before routing.")

    _assert_director_review_before_work_routing(
    db,
    doc,
    requests,
    )

    created: List[models.DocumentBranch] = []
    now = datetime.now()

    for req in requests:
        branch_type = req["branch_type"]
        if not isinstance(branch_type, BranchType):
            branch_type = BranchType(str(branch_type))

        resolved = _resolve_branch_target(
            db,
            branch_type,
            department_id=req.get("department_id"),
            target_user_id=req.get("target_user_id"),
        )
        instructions = (req.get("instructions") or "").strip() or None
        deadline = req.get("deadline") or doc.deadline
        requires_validation = bool(req.get("requires_hod_validation"))

        existing = _find_open_branch(
            db, document_id, branch_type,
            resolved["department_id"], resolved["target_user_id"],
        )

        if existing is not None:
            # Further work down a workstream that is already running.
            branch = existing
            branch.round_no += 1
            branch.stage = BranchStage.FURTHER_WORK
            if instructions:
                branch.instructions = instructions
            if deadline:
                branch.deadline = deadline
            branch.version += 1
            event = record_event(
                db,
                document_id=document_id,
                branch_id=branch.id,
                event_type="BRANCH_FURTHER_WORK",
                summary=f"DS sent further work to {resolved['label']} (round {branch.round_no})",
                actor=actor,
                context=context,
                details=instructions,
            )
        else:
            round_no = 1

            if branch_type == BranchType.DIRECTOR:
                last_director_round = (
                    db.query(models.DocumentBranch.round_no)
                    .filter(
                        models.DocumentBranch.document_id == document_id,
                        models.DocumentBranch.branch_type == BranchType.DIRECTOR,
                    )
                    .order_by(
                        models.DocumentBranch.round_no.desc()
                    )
                    .first()
                )

                last_director_round = (
                    last_director_round[0]
                    if last_director_round is not None
                    else 0
                )

                round_no = last_director_round + 1

            branch = models.DocumentBranch(
                document_id=document_id,
                branch_type=branch_type,
                stage=INITIAL_BRANCH_STAGE[branch_type],
                department_id=resolved["department_id"],
                target_user_id=resolved["target_user_id"],
                target_context_membership_id=resolved["target_context_membership_id"],
                opened_by_user_id=actor.id,
                opened_by_context_membership_id=context.id,
                instructions=instructions,
                requires_hod_validation=requires_validation,
                deadline=deadline,
                round_no=round_no,
                is_active=True,
                opened_at=now,
            )
            db.add(branch)
            db.flush()
            event = record_event(
                db,
                document_id=document_id,
                branch_id=branch.id,
                event_type=f"BRANCH_OPENED_{branch_type.value}",
                summary=f"DS routed the document to {resolved['label']}",
                actor=actor,
                context=context,
                details=instructions,
            )

        created.append(branch)

        # A DIRECTOR branch carries no work items: the Director reviews and
        # remarks, they do not perform assigned work.
        if branch_type in (BranchType.EMPLOYEE, BranchType.TSO):
            assign_work_items(
                db,
                branch=branch,
                assignee_user_ids=[resolved["target_user_id"]],
                actor=actor,
                context=context,
                instructions=instructions,
                deadline=deadline,
                requires_validation=(
                    requires_validation if branch_type == BranchType.EMPLOYEE else False
                ),
                team_name=None,
                _skip_authorization=True,
            )
        elif branch_type == BranchType.DEPARTMENT and req.get("assignee_user_ids"):
            # DS may pre-assign staff inside a department branch; the HOD still
            # sees the branch and keeps full control of it afterwards.
            assign_work_items(
                db,
                branch=branch,
                assignee_user_ids=list(req["assignee_user_ids"]),
                actor=actor,
                context=context,
                instructions=instructions,
                deadline=deadline,
                requires_validation=requires_validation,
                team_name=req.get("team_name"),
                _skip_authorization=True,
            )

        for target_ctx in resolved["notify_contexts"]:
            notify(
                db,
                user_id=target_ctx.user_id,
                context_membership_id=target_ctx.id,
                document_id=document_id,
                branch_id=branch.id,
                event_id=event.id,
                title=f"{doc.reference_no}: routed to you",
                message=(
                    f"'{doc.title}' has been routed to you as {resolved['label']}."
                    + (f" Instructions: {instructions}" if instructions else "")
                ),
            )

        recompute_branch_stage(db, branch)

    recompute_lifecycle(db, doc)
    _touch(doc)
    db.commit()
    for b in created:
        db.refresh(b)
    return created


# =========================================================
# WORK ITEM ASSIGNMENT (DS or HOD)
# =========================================================

def _authorize_branch_assignment(
    db: Session,
    branch: models.DocumentBranch,
    context: models.WorkContextMembership,
) -> None:
    if context.context_type == WorkContextType.DS:
        return
    if context.context_type == WorkContextType.HOD:
        if branch.branch_type != BranchType.DEPARTMENT:
            raise PermissionDenied("An HOD can assign staff only on a department workstream.")
        if branch.department_id != context.department_id:
            raise PermissionDenied(
                "This workstream belongs to another department. Switch to the matching HOD context."
            )
        return
    raise PermissionDenied("Only DS and HOD contexts can assign work.")


def assign_work_items(
    db: Session,
    *,
    branch: models.DocumentBranch,
    assignee_user_ids: Sequence[int],
    actor: models.User,
    context: models.WorkContextMembership,
    instructions: Optional[str] = None,
    deadline: Optional[date] = None,
    requires_validation: bool = False,
    team_name: Optional[str] = None,
    per_item_deadlines: Optional[Dict[int, date]] = None,
    _skip_authorization: bool = False,
    _commit: bool = False,
) -> List[models.WorkItem]:
    """Create ONE WorkItem per person.

    Assigning three people produces three work items, each with its own stage,
    deadline, progress history and attachments.  `team_name` only groups them
    for display; it never merges their records.
    """
    if not _skip_authorization:
        _authorize_branch_assignment(db, branch, context)

    ids = [int(u) for u in dict.fromkeys(assignee_user_ids) if u]
    if not ids:
        raise WorkflowError("Select at least one person to assign.")
    if not branch.is_active:
        raise WorkflowError("This workstream is closed. DS must send further work to reopen it.")

    doc = branch.document
    now = datetime.now()

    team: Optional[models.WorkTeam] = None
    if team_name and team_name.strip():
        team = models.WorkTeam(
            branch_id=branch.id,
            name=team_name.strip(),
            created_by_user_id=actor.id,
            created_at=now,
        )
        db.add(team)
        db.flush()

    created: List[models.WorkItem] = []
    for user_id in ids:
        target = (
            db.query(models.User)
            .filter(models.User.id == user_id, models.User.is_active.is_(True))
            .first()
        )
        if not target:
            raise WorkflowError(f"User {user_id} is not an active account.")

        # Which hat does this person wear for this branch?
        if branch.branch_type == BranchType.TSO:
            target_context = get_context_for(db, user_id, WorkContextType.TSO)
            if not target_context:
                raise WorkflowError(f"{target.full_name} does not hold an active TSO context.")
        elif branch.branch_type == BranchType.DEPARTMENT:
            target_context = get_context_for(db, user_id, WorkContextType.EMPLOYEE, branch.department_id)
            if not target_context:
                raise WorkflowError(
                    f"{target.full_name} does not hold an active Employee context "
                    f"in {branch.department_name or 'this department'}."
                )
            if target_context.department_id != branch.department_id:
                raise WorkflowError(
                    f"{target.full_name} is not an employee of {branch.department_name}."
                )
        else:
            target_context = get_context_for(db, user_id, WorkContextType.EMPLOYEE, target.department_id)
            if not target_context:
                raise WorkflowError(f"{target.full_name} does not hold an active Employee context.")

        # A person already working this branch in this round is not duplicated;
        # their existing item is reused so their history stays in one place.
        existing = next(
            (
                w for w in branch.work_items
                if w.assigned_to_user_id == user_id
                and w.is_active
                and w.stage not in TERMINAL_WORK_STAGES
            ),
            None,
        )
        if existing is not None:
            if instructions:
                existing.instructions = instructions
            if team is not None:
                existing.team_id = team.id
            existing.round_no = branch.round_no
            if existing.stage in (WorkStage.RETURNED, WorkStage.SUBMITTED, WorkStage.UNDER_REVIEW):
                _set_stage(db, existing, WorkStage.ASSIGNED, actor, note="Further work assigned")
            created.append(existing)
            continue

        previous = (
            db.query(models.WorkItem)
            .filter(
                models.WorkItem.branch_id == branch.id,
                models.WorkItem.assigned_to_user_id == user_id,
            )
            .order_by(models.WorkItem.id.desc())
            .first()
        )

        item_deadline = (per_item_deadlines or {}).get(user_id) or deadline or branch.deadline
        item = models.WorkItem(
            document_id=branch.document_id,
            branch_id=branch.id,
            team_id=team.id if team else None,
            assigned_to_user_id=user_id,
            assigned_to_context_membership_id=target_context.id,
            assigned_by_user_id=actor.id,
            assigned_by_context_membership_id=context.id if context else None,
            instructions=instructions or branch.instructions,
            deadline=item_deadline,
            stage=WorkStage.ASSIGNED,
            requires_validation=bool(requires_validation or branch.requires_hod_validation),
            round_no=branch.round_no,
            continues_item_id=previous.id if previous else None,
            is_active=True,
            assigned_at=now,
        )
        db.add(item)
        db.flush()
        created.append(item)

        event = record_event(
            db,
            document_id=branch.document_id,
            branch_id=branch.id,
            work_item_id=item.id,
            event_type="WORK_ASSIGNED",
            summary=(
                f"{actor.full_name} assigned {target.full_name} on {branch.label}"
                + (f" (team {team.name})" if team else "")
            ),
            actor=actor,
            context=context,
            details=instructions,
        )
        notify(
            db,
            user_id=user_id,
            context_membership_id=target_context.id,
            document_id=branch.document_id,
            branch_id=branch.id,
            work_item_id=item.id,
            event_id=event.id,
            title=f"{doc.reference_no}: new assignment",
            message=(
                f"You have been assigned work on '{doc.title}'."
                + (f" Instructions: {instructions}" if instructions else "")
                + (f" Due {item_deadline.isoformat()}." if item_deadline else "")
            ),
        )

    recompute_branch_stage(db, branch)
    recompute_lifecycle(db, doc)
    _touch(doc)

    if _commit:
        db.commit()
        for item in created:
            db.refresh(item)
    return created


def assign_branch_work(
    db: Session,
    *,
    branch_id: int,
    assignee_user_ids: Sequence[int],
    actor: models.User,
    context_id: Optional[int] = None,
    instructions: Optional[str] = None,
    deadline: Optional[date] = None,
    requires_validation: bool = False,
    team_name: Optional[str] = None,
) -> List[models.WorkItem]:
    """API entry point for DS/HOD assigning people to a branch."""
    context = require_context(db, actor, context_id, WorkContextType.DS, WorkContextType.HOD)
    branch = db.query(models.DocumentBranch).filter(models.DocumentBranch.id == branch_id).first()
    if not branch:
        raise WorkflowError(f"Workstream {branch_id} not found.")
    _assert_open(branch.document)
    return assign_work_items(
        db,
        branch=branch,
        assignee_user_ids=assignee_user_ids,
        actor=actor,
        context=context,
        instructions=instructions,
        deadline=deadline,
        requires_validation=requires_validation,
        team_name=team_name,
        _commit=True,
    )


# =========================================================
# WORKER ACTIONS (Employee / TSO / HOD working an item)
# =========================================================

def _load_own_work_item(
    db: Session,
    work_item_id: int,
    user: models.User,
    context: models.WorkContextMembership,
) -> models.WorkItem:
    item = db.query(models.WorkItem).filter(models.WorkItem.id == work_item_id).first()
    if not item:
        raise WorkflowError(f"Work item {work_item_id} not found.")
    if item.assigned_to_user_id != user.id:
        raise PermissionDenied("This work item belongs to someone else.")
    if item.assigned_to_context_membership_id and item.assigned_to_context_membership_id != context.id:
        raise PermissionDenied(
            "This work item belongs to a different work context. "
            "Switch context to work on it."
        )
    return item


def _set_stage(
    db: Session,
    item: models.WorkItem,
    new_stage: WorkStage,
    actor: models.User,
    note: Optional[str] = None,
) -> None:
    """Move one work item's stage and record the change.  Never touches any
    other person's work item."""
    if item.stage == new_stage:
        return
    previous = item.stage
    item.stage = new_stage
    item.version += 1

    now = datetime.now()
    if new_stage == WorkStage.UNDER_WORK and item.started_at is None:
        item.started_at = now
    if new_stage == WorkStage.SUBMITTED:
        item.submitted_at = now
    if new_stage in TERMINAL_WORK_STAGES:
        item.completed_at = now
        item.is_active = False
    else:
        item.is_active = True
        item.completed_at = None

    db.add(models.WorkStageChange(
        work_item_id=item.id,
        from_stage=previous,
        to_stage=new_stage,
        changed_by_user_id=actor.id,
        note=note,
        created_at=now,
    ))


def update_work_stage(
    db: Session,
    *,
    work_item_id: int,
    new_stage: WorkStage,
    actor: models.User,
    context_id: Optional[int] = None,
    note: Optional[str] = None,
) -> models.WorkItem:
    """The worker moves their own work through its stages."""
    context = require_context(
        db, actor, context_id,
        WorkContextType.EMPLOYEE, WorkContextType.TSO, WorkContextType.HOD,
    )
    item = _load_own_work_item(db, work_item_id, actor, context)
    _assert_open(item.document)

    if not isinstance(new_stage, WorkStage):
        new_stage = WorkStage(str(new_stage))
    if new_stage not in WORKER_SELECTABLE_STAGES:
        allowed = ", ".join(work_stage_label(s) for s in WORKER_SELECTABLE_STAGES)
        raise WorkflowError(
            f"You can set your work to: {allowed}. "
            "Use Submit or Complete to finish the assignment."
        )
    if item.stage in TERMINAL_WORK_STAGES:
        raise WorkflowError("This assignment is already finished.")

    previous = item.stage
    _set_stage(db, item, new_stage, actor, note=note)

    record_event(
        db,
        document_id=item.document_id,
        branch_id=item.branch_id,
        work_item_id=item.id,
        event_type="WORK_STAGE_CHANGED",
        summary=(
            f"{actor.full_name} moved their work from "
            f"{work_stage_label(previous)} to {work_stage_label(new_stage)}"
        ),
        actor=actor,
        context=context,
        details=note,
    )

    recompute_branch_stage(db, item.branch)
    recompute_lifecycle(db, item.document)
    db.commit()
    db.refresh(item)
    return item


def submit_progress(
    db: Session,
    *,
    work_item_id: int,
    description: str,
    actor: models.User,
    context_id: Optional[int] = None,
    new_stage: Optional[WorkStage] = None,
) -> models.ProgressUpdate:
    """Append a free-text progress update to one person's work item.

    The text is whatever the worker wrote.  It is never parsed into a number,
    never averaged and never combined with anyone else's update.
    """
    context = require_context(
        db, actor, context_id,
        WorkContextType.EMPLOYEE, WorkContextType.TSO, WorkContextType.HOD,
    )
    item = _load_own_work_item(db, work_item_id, actor, context)
    _assert_open(item.document)

    text = (description or "").strip()
    if not text:
        raise WorkflowError("Write what you have done before submitting an update.")
    if item.stage in TERMINAL_WORK_STAGES:
        raise WorkflowError("This assignment is finished; no further updates can be added.")

    # An update implies work has started, unless the worker chose a stage.
    if new_stage is not None:
        if not isinstance(new_stage, WorkStage):
            new_stage = WorkStage(str(new_stage))
        if new_stage in WORKER_SELECTABLE_STAGES:
            _set_stage(db, item, new_stage, actor, note="Set with progress update")
    elif item.stage in (WorkStage.ASSIGNED, WorkStage.RETURNED):
        _set_stage(db, item, WorkStage.UNDER_WORK, actor, note="First progress update")

    update = models.ProgressUpdate(
        document_id=item.document_id,
        work_item_id=item.id,
        author_user_id=actor.id,
        author_context_membership_id=context.id,
        description=text,
        stage_at_time=item.stage,
        created_at=datetime.now(),
    )
    db.add(update)
    db.flush()

    doc = item.document
    branch = item.branch
    event = record_event(
        db,
        document_id=item.document_id,
        branch_id=item.branch_id,
        work_item_id=item.id,
        event_type="PROGRESS_UPDATED",
        summary=f"{actor.full_name} added a progress update on {branch.label}",
        actor=actor,
        context=context,
        details=text,
    )

    # Tell whoever is waiting on this person.
    if branch.branch_type == BranchType.DEPARTMENT and branch.department_id:
        for hod in department_hod_contexts(db, branch.department_id):
            notify(
                db,
                user_id=hod.user_id,
                context_membership_id=hod.id,
                document_id=doc.doc_id,
                branch_id=branch.id,
                work_item_id=item.id,
                event_id=event.id,
                title=f"{doc.reference_no}: progress update",
                message=f"{actor.full_name} updated their work on '{doc.title}'.",
                include_progress_attachments=True,
            )
    else:
        for ds in ds_contexts(db):
            notify(
                db,
                user_id=ds.user_id,
                context_membership_id=ds.id,
                document_id=doc.doc_id,
                branch_id=branch.id,
                work_item_id=item.id,
                event_id=event.id,
                title=f"{doc.reference_no}: progress update",
                message=f"{actor.full_name} updated their work on '{doc.title}'.",
                include_progress_attachments=True,
            )

    recompute_branch_stage(db, branch)
    recompute_lifecycle(db, doc)
    db.commit()
    db.refresh(update)
    return update


def submit_work(
    db: Session,
    *,
    work_item_id: int,
    actor: models.User,
    context_id: Optional[int] = None,
    note: Optional[str] = None,
) -> models.WorkItem:
    """The worker hands their work in.

    If the work needs HOD validation it goes to UNDER_REVIEW and waits for the
    HOD.  Otherwise it completes.  Neither outcome closes the document: only
    the DS closes documents.
    """
    context = require_context(
        db, actor, context_id,
        WorkContextType.EMPLOYEE, WorkContextType.TSO, WorkContextType.HOD,
    )
    item = _load_own_work_item(db, work_item_id, actor, context)
    _assert_open(item.document)
    if item.stage in TERMINAL_WORK_STAGES:
        raise WorkflowError("This assignment is already finished.")

    if note and note.strip():
        db.add(models.ProgressUpdate(
            document_id=item.document_id,
            work_item_id=item.id,
            author_user_id=actor.id,
            author_context_membership_id=context.id,
            description=note.strip(),
            stage_at_time=WorkStage.SUBMITTED,
            created_at=datetime.now(),
        ))

    branch = item.branch
    doc = item.document
    needs_review = bool(item.requires_validation) and branch.branch_type == BranchType.DEPARTMENT

    _set_stage(
        db, item,
        WorkStage.UNDER_REVIEW if needs_review else WorkStage.COMPLETED,
        actor, note=note,
    )

    event = record_event(
        db,
        document_id=item.document_id,
        branch_id=branch.id,
        work_item_id=item.id,
        event_type="WORK_SUBMITTED" if needs_review else "WORK_COMPLETED",
        summary=(
            f"{actor.full_name} submitted their work for HOD validation on {branch.label}"
            if needs_review else
            f"{actor.full_name} completed their work on {branch.label}"
        ),
        actor=actor,
        context=context,
        details=note,
    )

    if needs_review and branch.department_id:
        for hod in department_hod_contexts(db, branch.department_id):
            notify(
                db,
                user_id=hod.user_id,
                context_membership_id=hod.id,
                document_id=doc.doc_id,
                branch_id=branch.id,
                work_item_id=item.id,
                event_id=event.id,
                title=f"{doc.reference_no}: work awaiting your validation",
                message=f"{actor.full_name} submitted work on '{doc.title}' for your review.",
                include_progress_attachments=True,
            )
    else:
        for ds in ds_contexts(db):
            notify(
                db,
                user_id=ds.user_id,
                context_membership_id=ds.id,
                document_id=doc.doc_id,
                branch_id=branch.id,
                work_item_id=item.id,
                event_id=event.id,
                title=f"{doc.reference_no}: work completed",
                message=f"{actor.full_name} completed their work on '{doc.title}'.",
                include_progress_attachments=True,
            )

    recompute_branch_stage(db, branch)
    recompute_lifecycle(db, doc)
    _touch(doc)
    db.commit()
    db.refresh(item)
    return item


# =========================================================
# HOD VALIDATION OF ONE PERSON'S WORK
# =========================================================

def review_work_item(
    db: Session,
    *,
    work_item_id: int,
    outcome: ReviewOutcome,
    actor: models.User,
    context_id: Optional[int] = None,
    note: Optional[str] = None,
) -> models.WorkItemReview:
    """An HOD accepts or returns ONE person's work.

    Accepting completes that person's work item only.  It does not complete
    the branch unless everyone on it has finished, and it never closes the
    document."""
    context = require_context(db, actor, context_id, WorkContextType.HOD, WorkContextType.DS)
    item = db.query(models.WorkItem).filter(models.WorkItem.id == work_item_id).first()
    if not item:
        raise WorkflowError(f"Work item {work_item_id} not found.")
    _assert_open(item.document)

    branch = item.branch
    if context.context_type == WorkContextType.HOD:
        if branch.branch_type != BranchType.DEPARTMENT or branch.department_id != context.department_id:
            raise PermissionDenied("You can only validate work on your own department's workstream.")

    if not isinstance(outcome, ReviewOutcome):
        outcome = ReviewOutcome(str(outcome))
    if item.stage not in (WorkStage.SUBMITTED, WorkStage.UNDER_REVIEW):
        raise WorkflowError("Only submitted work can be validated.")

    review = models.WorkItemReview(
        work_item_id=item.id,
        reviewer_user_id=actor.id,
        reviewer_context_membership_id=context.id,
        outcome=outcome,
        note=note,
        created_at=datetime.now(),
    )
    db.add(review)
    db.flush()

    if outcome == ReviewOutcome.ACCEPTED:
        _set_stage(db, item, WorkStage.COMPLETED, actor, note=note)
        summary = f"{actor.full_name} validated {item.assignee_name}'s work"
        message = f"Your work on '{item.document.title}' was accepted."
    else:
        _set_stage(db, item, WorkStage.RETURNED, actor, note=note)
        summary = f"{actor.full_name} returned {item.assignee_name}'s work for rework"
        message = f"Your work on '{item.document.title}' was returned for rework."

    if note:
        add_remark(
            db,
            document_id=item.document_id,
            author=actor,
            context=context,
            remark_text=note,
            remark_type=RemarkType.HOD if context.context_type == WorkContextType.HOD else RemarkType.DS,
            branch_id=branch.id,
            work_item_id=item.id,
            provenance="WORK_REVIEW",
        )

    event = record_event(
        db,
        document_id=item.document_id,
        branch_id=branch.id,
        work_item_id=item.id,
        event_type=f"WORK_{outcome.value}",
        summary=summary,
        actor=actor,
        context=context,
        details=note,
    )
    notify(
        db,
        user_id=item.assigned_to_user_id,
        context_membership_id=item.assigned_to_context_membership_id,
        document_id=item.document_id,
        branch_id=branch.id,
        work_item_id=item.id,
        event_id=event.id,
        title=f"{item.document.reference_no}: work {outcome.value.lower()}",
        message=message + (f" Note: {note}" if note else ""),
    )

    recompute_branch_stage(db, branch)
    recompute_lifecycle(db, item.document)
    db.commit()
    db.refresh(review)
    return review


# =========================================================
# DIRECTOR REVIEW (repeatable; remark only)
# =========================================================

def start_director_review(
    db: Session,
    *,
    branch_id: int,
    actor: models.User,
    context_id: Optional[int] = None,
) -> models.DocumentBranch:
    """Mark that the Director has opened the document.  Idempotent."""
    context = require_context(db, actor, context_id, WorkContextType.DIRECTOR)
    branch = db.query(models.DocumentBranch).filter(models.DocumentBranch.id == branch_id).first()
    if not branch or branch.branch_type != BranchType.DIRECTOR:
        raise WorkflowError("Director review workstream not found.")
    if branch.target_user_id and branch.target_user_id != actor.id:
        raise PermissionDenied("This review was requested from another Director.")
    if branch.stage == BranchStage.REVIEW_REQUESTED:
        branch.stage = BranchStage.UNDER_DIRECTOR_REVIEW
        branch.version += 1
        record_event(
            db,
            document_id=branch.document_id,
            branch_id=branch.id,
            event_type="DIRECTOR_REVIEW_STARTED",
            summary=f"{actor.full_name} opened the document for review",
            actor=actor,
            context=context,
        )
        db.commit()
        db.refresh(branch)
    return branch


def submit_director_review(
    db: Session,
    *,
    branch_id: int,
    remark_text: str,
    actor: models.User,
    context_id: Optional[int] = None,
    expected_version: Optional[int] = None,
) -> models.DirectorReview:
    """The Director records a remark and hands the document back to the DS.

    The Director does not decide anything about closure and does not stop or
    change work happening on other branches.  Every review is kept: none
    replaces an earlier one.
    """
    context = require_context(db, actor, context_id, WorkContextType.DIRECTOR)
    branch = db.query(models.DocumentBranch).filter(models.DocumentBranch.id == branch_id).first()
    if not branch or branch.branch_type != BranchType.DIRECTOR:
        raise WorkflowError("Director review workstream not found.")
    if not branch.is_active:
        raise WorkflowError("This review has already been returned to the DS.")
    if branch.target_user_id and branch.target_user_id != actor.id:
        raise PermissionDenied("This review was requested from another Director.")

    doc = branch.document
    _check_version(doc, expected_version)
    _assert_open(doc)

    text = (remark_text or "").strip()
    if not text:
        raise WorkflowError("A Director review must carry a remark.")

    review_no = db.query(models.DirectorReview).filter(
        models.DirectorReview.document_id == doc.doc_id
    ).count() + 1

    review = models.DirectorReview(
        document_id=doc.doc_id,
        branch_id=branch.id,
        director_user_id=actor.id,
        director_context_membership_id=context.id,
        remark_text=text,
        review_no=review_no,
        document_version=doc.version,
        requested_at=branch.opened_at,
        created_at=datetime.now(),
    )
    db.add(review)

    add_remark(
        db,
        document_id=doc.doc_id,
        author=actor,
        context=context,
        remark_text=text,
        remark_type=RemarkType.DIRECTOR,
        branch_id=branch.id,
        provenance="DIRECTOR_REVIEW",
    )

    branch.stage = BranchStage.RETURNED_TO_DS
    branch.is_active = False
    branch.closed_at = datetime.now()
    branch.version += 1

    event = record_event(
        db,
        document_id=doc.doc_id,
        branch_id=branch.id,
        event_type="DIRECTOR_REMARK_ADDED",
        summary=f"Director review #{review_no} completed and returned to DS",
        actor=actor,
        context=context,
        details=text,
    )

    for ds in ds_contexts(db):
        notify(
            db,
            user_id=ds.user_id,
            context_membership_id=ds.id,
            document_id=doc.doc_id,
            branch_id=branch.id,
            event_id=event.id,
            title=f"{doc.reference_no}: returned by Director",
            message=f"Director review #{review_no} on '{doc.title}' is complete. Remark: {text}",
        )

    recompute_lifecycle(db, doc)
    _touch(doc)
    db.commit()
    db.refresh(review)
    return review


# =========================================================
# BRANCH REMARKS (HOD / DS)
# =========================================================

def add_branch_remark(
    db: Session,
    *,
    branch_id: int,
    remark_text: str,
    actor: models.User,
    context_id: Optional[int] = None,
) -> models.DocumentRemark:
    """HOD or DS writes a remark against one workstream."""
    context = require_context(
        db, actor, context_id,
        WorkContextType.HOD, WorkContextType.DS, WorkContextType.TSO, WorkContextType.EMPLOYEE,
    )
    branch = db.query(models.DocumentBranch).filter(models.DocumentBranch.id == branch_id).first()
    if not branch:
        raise WorkflowError(f"Workstream {branch_id} not found.")
    _assert_open(branch.document)

    text = (remark_text or "").strip()
    if not text:
        raise WorkflowError("A remark cannot be empty.")

    if context.context_type == WorkContextType.HOD:
        if branch.branch_type != BranchType.DEPARTMENT or branch.department_id != context.department_id:
            raise PermissionDenied("You can only remark on your own department's workstream.")

    remark_type = {
        WorkContextType.HOD: RemarkType.HOD,
        WorkContextType.DS: RemarkType.DS,
        WorkContextType.TSO: RemarkType.TSO,
        WorkContextType.EMPLOYEE: RemarkType.EMPLOYEE,
    }[context.context_type]

    remark = add_remark(
        db,
        document_id=branch.document_id,
        author=actor,
        context=context,
        remark_text=text,
        remark_type=remark_type,
        branch_id=branch.id,
    )
    record_event(
        db,
        document_id=branch.document_id,
        branch_id=branch.id,
        event_type=f"{remark_type.value}_REMARK",
        summary=f"{actor.full_name} added a {remark_type.value.title()} remark on {branch.label}",
        actor=actor,
        context=context,
        details=text,
    )
    db.commit()
    db.refresh(remark)
    return remark


# =========================================================
# DS DECISIONS
# =========================================================

def close_branch(
    db: Session,
    *,
    branch_id: int,
    actor: models.User,
    context_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> models.DocumentBranch:
    """DS ends one workstream without closing the document.  Other branches
    keep running."""
    context = require_context(db, actor, context_id, WorkContextType.DS)
    branch = db.query(models.DocumentBranch).filter(models.DocumentBranch.id == branch_id).first()
    if not branch:
        raise WorkflowError(f"Workstream {branch_id} not found.")
    if not branch.is_active:
        raise WorkflowError("This workstream is already closed.")

    now = datetime.now()
    for item in branch.work_items:
        if item.stage not in TERMINAL_WORK_STAGES:
            _set_stage(db, item, WorkStage.CANCELLED, actor, note=reason or "Workstream closed by DS")

    branch.stage = BranchStage.COMPLETED
    branch.is_active = False
    branch.closed_at = now
    branch.version += 1

    record_event(
        db,
        document_id=branch.document_id,
        branch_id=branch.id,
        event_type="BRANCH_CLOSED",
        summary=f"DS closed the {branch.label} workstream",
        actor=actor,
        context=context,
        details=reason,
    )
    recompute_lifecycle(db, branch.document)
    _touch(branch.document)
    db.commit()
    db.refresh(branch)
    return branch


def close_document(
    db: Session,
    *,
    document_id: int,
    actor: models.User,
    context_id: Optional[int] = None,
    remark: Optional[str] = None,
    force: bool = False,
    expected_version: Optional[int] = None,
) -> models.Document:
    """Only the DS closes a document, and only when the DS decides the work is
    finished.

    No Director approval is required.  If workstreams are still running the
    caller must pass force=True, which cancels them explicitly and records
    that in history rather than pretending they finished.
    """
    context = require_context(db, actor, context_id, WorkContextType.DS)
    doc = _get_document(db, document_id)
    _check_version(doc, expected_version)

    if doc.lifecycle == DocumentLifecycle.CLOSED:
        raise WorkflowError("This document is already closed.")

    open_branches_list = [b for b in doc.branches if b.is_active]
    if open_branches_list and not force:
        labels = ", ".join(b.label for b in open_branches_list)
        raise WorkflowError(
            f"{len(open_branches_list)} workstream(s) are still open: {labels}. "
            "Confirm closure to cancel them, or wait for them to finish."
        )

    now = datetime.now()
    for branch in open_branches_list:
        for item in branch.work_items:
            if item.stage not in TERMINAL_WORK_STAGES:
                _set_stage(db, item, WorkStage.CANCELLED, actor, note="Document closed by DS")
        branch.stage = BranchStage.CANCELLED
        branch.is_active = False
        branch.closed_at = now
        branch.version += 1
        record_event(
            db,
            document_id=document_id,
            branch_id=branch.id,
            event_type="BRANCH_CANCELLED_ON_CLOSE",
            summary=f"{branch.label} was cancelled because the DS closed the document",
            actor=actor,
            context=context,
        )

    doc.lifecycle = DocumentLifecycle.CLOSED
    doc.closed_at = now
    doc.closed_by_user_id = actor.id
    doc.closure_remark = remark
    _touch(doc)

    if remark:
        add_remark(
            db,
            document_id=document_id,
            author=actor,
            context=context,
            remark_text=remark,
            remark_type=RemarkType.DS,
            provenance="CLOSURE",
        )

    event = record_event(
        db,
        document_id=document_id,
        event_type="DOCUMENT_CLOSED",
        summary=f"{actor.full_name} closed the document",
        actor=actor,
        context=context,
        details=remark,
    )

    # Tell everyone who worked on it.
    told = set()
    for item in doc.work_items:
        key = (item.assigned_to_user_id, item.assigned_to_context_membership_id)
        if key in told:
            continue
        told.add(key)
        notify(
            db,
            user_id=item.assigned_to_user_id,
            context_membership_id=item.assigned_to_context_membership_id,
            document_id=document_id,
            event_id=event.id,
            title=f"{doc.reference_no}: closed",
            message=f"'{doc.title}' has been closed by the DS.",
        )

    db.commit()
    db.refresh(doc)
    return doc


def reopen_document(
    db: Session,
    *,
    document_id: int,
    actor: models.User,
    context_id: Optional[int] = None,
    reason: Optional[str] = None,
) -> models.Document:
    """DS reopens a closed document so further work can be routed."""
    context = require_context(db, actor, context_id, WorkContextType.DS)
    doc = _get_document(db, document_id)
    if doc.lifecycle != DocumentLifecycle.CLOSED:
        raise WorkflowError("This document is not closed.")

    doc.closed_at = None
    doc.closed_by_user_id = None
    doc.closure_remark = None
    recompute_lifecycle(db, doc)
    _touch(doc)
    record_event(
        db,
        document_id=document_id,
        event_type="DOCUMENT_REOPENED",
        summary=f"{actor.full_name} reopened the document",
        actor=actor,
        context=context,
        details=reason,
    )
    db.commit()
    db.refresh(doc)
    return doc


def register_document(
    db: Session,
    *,
    document_id: int,
    actor: models.User,
    context_id: Optional[int] = None,
) -> models.Document:
    """DS confirms the (possibly OCR-extracted) metadata is correct."""
    context = require_context(db, actor, context_id, WorkContextType.DS)
    doc = _get_document(db, document_id)
    if doc.registered_at is None:
        doc.registered_at = datetime.now()
        record_event(
            db,
            document_id=document_id,
            event_type="DOCUMENT_REGISTERED",
            summary=f"{actor.full_name} registered the document",
            actor=actor,
            context=context,
        )
        # Only a real change bumps the version, so re-registering an already
        # registered document never invalidates a caller's expected_version.
        recompute_lifecycle(db, doc)
        _touch(doc)
        db.commit()
    db.refresh(doc)
    return doc

def send_to_director(
    db: Session,
    *,
    document_id: int,
    actor: models.User,
    context_id: Optional[int] = None,
    expected_version: Optional[int] = None,
) -> models.DocumentBranch:
    """
    DS explicitly sends a registered document to the Director for review.

    This is a separate action from document registration.
    The Director reviews and remarks; the Director does not close the
    document or decide its final routing.
    """
    context = require_context(db, actor, context_id, WorkContextType.DS)
    doc = _get_document(db, document_id)

    _check_version(doc, expected_version)
    _assert_open(doc)

    if doc.registered_at is None:
        raise WorkflowError(
            "The document must be registered before it can be sent "
            "to the Director for review."
        )

    # Do not create another Director review while one is already open.
    existing = _find_open_branch(
        db,
        document_id,
        BranchType.DIRECTOR,
        None,
        None,
    )

    if existing is not None:
        raise WorkflowError(
            "This document is already awaiting Director review."
        )

    resolved = _resolve_branch_target(
        db,
        BranchType.DIRECTOR,
        department_id=None,
        target_user_id=None,
    )

    now = datetime.now()
    round_no = (
    db.query(models.DocumentBranch.round_no)
            .filter(
                models.DocumentBranch.document_id == document_id,
                models.DocumentBranch.branch_type == BranchType.DIRECTOR,
            )
            .order_by(models.DocumentBranch.round_no.desc())
            .scalar()
            or 0
        ) + 1
    branch = models.DocumentBranch(
        document_id=document_id,
        branch_type=BranchType.DIRECTOR,
        stage=BranchStage.REVIEW_REQUESTED,
        department_id=None,
        target_user_id=resolved["target_user_id"],
        target_context_membership_id=resolved["target_context_membership_id"],
        opened_by_user_id=actor.id,
        opened_by_context_membership_id=context.id,
        instructions=None,
        requires_hod_validation=False,
        deadline=doc.deadline,
        round_no=round_no,
        version=1,
        is_active=True,
        opened_at=now,
    )

    db.add(branch)
    db.flush()

    event = record_event(
        db,
        document_id=document_id,
        branch_id=branch.id,
        event_type="DIRECTOR_REVIEW_REQUESTED",
        summary=f"{actor.full_name} sent the document to the Director for review",
        actor=actor,
        context=context,
    )

    for target_ctx in resolved["notify_contexts"]:
        notify(
            db,
            user_id=target_ctx.user_id,
            context_membership_id=target_ctx.id,
            document_id=document_id,
            branch_id=branch.id,
            event_id=event.id,
            title=f"{doc.reference_no}: Director review requested",
            message=(
                f"'{doc.title}' has been sent to you for Director review."
            ),
        )

    recompute_branch_stage(db, branch)
    recompute_lifecycle(db, doc)
    _touch(doc)

    db.commit()
    db.refresh(branch)

    return branch


# =========================================================
# VISIBILITY & QUERIES
# =========================================================

def _participation_filter(user: models.User, context: models.WorkContextMembership):
    """Documents this context has legitimately taken part in."""
    clauses = [
        models.Document.created_by == user.id,
        models.Document.branches.any(models.DocumentBranch.opened_by_user_id == user.id),
        models.Document.branches.any(models.DocumentBranch.target_user_id == user.id),
        models.Document.work_items.any(models.WorkItem.assigned_to_user_id == user.id),
        models.Document.work_items.any(models.WorkItem.assigned_by_user_id == user.id),
        models.Document.remarks.any(models.DocumentRemark.author_user_id == user.id),
        models.Document.director_reviews.any(models.DirectorReview.director_user_id == user.id),
    ]
    if context.context_type == WorkContextType.HOD and context.department_id is not None:
        clauses.append(
            models.Document.branches.any(
                and_(
                    models.DocumentBranch.branch_type == BranchType.DEPARTMENT,
                    models.DocumentBranch.department_id == context.department_id,
                )
            )
        )
    return or_(*clauses)


def documents_for_context(
    db: Session,
    user: models.User,
    context_id: Optional[int] = None,
) -> List[models.Document]:
    """Every document the active context may open.  DS and Director see the
    whole register; everyone else sees what they took part in."""
    context = resolve_context(db, user, context_id)
    if context is None or context.context_type == WorkContextType.ADMIN:
        return []

    q = db.query(models.Document)
    if context.context_type not in (WorkContextType.DS, WorkContextType.DIRECTOR):
        q = q.filter(_participation_filter(user, context))
    return q.order_by(models.Document.updated_at.desc()).all()


def can_access_document(
    db: Session,
    doc: models.Document,
    user: models.User,
    context_id: Optional[int] = None,
) -> bool:
    context = resolve_context(db, user, context_id)
    if context is None or context.context_type == WorkContextType.ADMIN:
        return False
    if context.context_type in (WorkContextType.DS, WorkContextType.DIRECTOR):
        return True
    return (
        db.query(models.Document)
        .filter(models.Document.doc_id == doc.doc_id, _participation_filter(user, context))
        .first()
        is not None
    )


def inbox_for_context(
    db: Session,
    user: models.User,
    context_id: Optional[int] = None,
) -> List[models.Document]:
    """What this context has to act on right now.  Strictly the action queue:
    finished work drops out of it and lives on in Documents and History."""
    context = resolve_context(db, user, context_id)
    if context is None:
        return []
    ct = context.context_type

    if ct == WorkContextType.ADMIN:
        return []

    if ct == WorkContextType.DS:
        # Anything not closed and not currently out with someone else.
        docs = (
            db.query(models.Document)
            .filter(models.Document.lifecycle != DocumentLifecycle.CLOSED)
            .order_by(models.Document.updated_at.desc())
            .all()
        )
        return [
            d for d in docs
            if d.lifecycle in (
                DocumentLifecycle.RECEIVED,
                DocumentLifecycle.REGISTERED,
                DocumentLifecycle.WITH_DS,
            )
            or any(
                b.is_active and b.stage in (BranchStage.COMPLETED, BranchStage.SUBMITTED)
                for b in d.branches
            )
            or any(not b.is_active and b.branch_type == BranchType.DIRECTOR for b in d.branches)
        ]

    if ct == WorkContextType.DIRECTOR:
        return (
            db.query(models.Document)
            .filter(
                models.Document.branches.any(
                    and_(
                        models.DocumentBranch.branch_type == BranchType.DIRECTOR,
                        models.DocumentBranch.is_active.is_(True),
                        or_(
                            models.DocumentBranch.target_user_id == user.id,
                            models.DocumentBranch.target_user_id.is_(None),
                        ),
                    )
                )
            )
            .order_by(models.Document.updated_at.desc())
            .all()
        )

    if ct == WorkContextType.HOD and context.department_id is not None:
        return (
            db.query(models.Document)
            .filter(
                models.Document.branches.any(
                    and_(
                        models.DocumentBranch.branch_type == BranchType.DEPARTMENT,
                        models.DocumentBranch.department_id == context.department_id,
                        models.DocumentBranch.is_active.is_(True),
                    )
                )
            )
            .order_by(models.Document.updated_at.desc())
            .all()
        )

    if ct in (WorkContextType.EMPLOYEE, WorkContextType.TSO):
        return (
            db.query(models.Document)
            .filter(
                models.Document.work_items.any(
                    and_(
                        models.WorkItem.assigned_to_user_id == user.id,
                        models.WorkItem.assigned_to_context_membership_id == context.id,
                        models.WorkItem.is_active.is_(True),
                    )
                )
            )
            .order_by(models.Document.updated_at.desc())
            .all()
        )

    return []


def work_items_for_context(
    db: Session,
    user: models.User,
    context_id: Optional[int] = None,
    include_finished: bool = False,
) -> List[models.WorkItem]:
    """This person's own task list, scoped to the hat they are wearing."""
    context = resolve_context(db, user, context_id)
    if context is None:
        return []
    q = db.query(models.WorkItem).filter(
        models.WorkItem.assigned_to_user_id == user.id,
        models.WorkItem.assigned_to_context_membership_id == context.id,
    )
    if not include_finished:
        q = q.filter(models.WorkItem.stage.notin_(TERMINAL_WORK_STAGES))
    return q.order_by(models.WorkItem.assigned_at.desc()).all()


def branch_work_items_for_context(
    db: Session,
    user: models.User,
    context_id: Optional[int] = None,
) -> List[models.WorkItem]:
    """For an HOD: every person's work item across their department's
    workstreams, so individual contributions stay visible."""
    context = resolve_context(db, user, context_id)
    if context is None or context.context_type != WorkContextType.HOD:
        return []
    return (
        db.query(models.WorkItem)
        .join(models.DocumentBranch, models.DocumentBranch.id == models.WorkItem.branch_id)
        .filter(
            models.DocumentBranch.branch_type == BranchType.DEPARTMENT,
            models.DocumentBranch.department_id == context.department_id,
        )
        .order_by(models.WorkItem.assigned_at.desc())
        .all()
    )


def document_history(db: Session, document_id: int) -> List[models.WorkflowEvent]:
    return (
        db.query(models.WorkflowEvent)
        .filter(models.WorkflowEvent.document_id == document_id)
        .order_by(models.WorkflowEvent.created_at.asc(), models.WorkflowEvent.id.asc())
        .all()
    )


def visible_history(
    db: Session,
    user: models.User,
    context_id: Optional[int] = None,
    limit: int = 500,
) -> List[models.WorkflowEvent]:
    """History across every document the active context can see."""
    docs = documents_for_context(db, user, context_id)
    if not docs:
        return []
    ids = [d.doc_id for d in docs]
    return (
        db.query(models.WorkflowEvent)
        .filter(models.WorkflowEvent.document_id.in_(ids))
        .order_by(models.WorkflowEvent.created_at.desc())
        .limit(limit)
        .all()
    )


# =========================================================
# DEADLINES & REMINDERS
# =========================================================

def overdue_state(deadline: Optional[date], reference: Optional[date] = None) -> str:
    """'overdue' | 'due_soon' | 'on_track' | 'none' for one deadline."""
    if not deadline:
        return "none"
    today = reference or date.today()
    days = (deadline - today).days
    if days < 0:
        return "overdue"
    if days <= 2:
        return "due_soon"
    return "on_track"


def generate_deadline_reminders(db: Session) -> List[models.Reminder]:
    """Raise a reminder for each live work item that is due soon or overdue.

    Reminders are per work item, so each person is told about their own
    deadline rather than the document's."""
    today = date.today()
    created: List[models.Reminder] = []

    items = (
        db.query(models.WorkItem)
        .filter(
            models.WorkItem.is_active.is_(True),
            models.WorkItem.stage.notin_(TERMINAL_WORK_STAGES),
            models.WorkItem.deadline.isnot(None),
        )
        .all()
    )
    for item in items:
        state = overdue_state(item.deadline, today)
        if state not in ("overdue", "due_soon"):
            continue
        reason = ReminderReason.OVERDUE if state == "overdue" else ReminderReason.DUE_SOON
        key = f"workitem:{item.id}:{reason.value}:{today.isoformat()}"
        if db.query(models.Reminder).filter(models.Reminder.deduplication_key == key).first():
            continue

        doc = item.document
        message = (
            f"Your work on '{doc.title}' ({doc.reference_no}) "
            + ("is overdue" if state == "overdue" else "is due shortly")
            + f" - deadline {item.deadline.isoformat()}."
        )
        reminder = models.Reminder(
            document_id=item.document_id,
            work_item_id=item.id,
            recipient_user_id=item.assigned_to_user_id,
            recipient_context_membership_id=item.assigned_to_context_membership_id,
            reason=reason,
            message=message,
            due_at=datetime.combine(item.deadline, datetime.min.time()),
            deduplication_key=key,
        )
        db.add(reminder)
        notify(
            db,
            user_id=item.assigned_to_user_id,
            context_membership_id=item.assigned_to_context_membership_id,
            document_id=item.document_id,
            branch_id=item.branch_id,
            work_item_id=item.id,
            title=f"{doc.reference_no}: {'overdue' if state == 'overdue' else 'due soon'}",
            message=message,
        )
        created.append(reminder)

    db.commit()
    return created


# =========================================================
# DASHBOARD
# =========================================================

def dashboard_for_context(
    db: Session,
    user: models.User,
    context_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Counters that mean something for the hat the user is wearing.  No
    percentages, no averaged progress."""
    context = resolve_context(db, user, context_id)
    if context is None:
        return {"context_type": None, "cards": [], "documents": []}

    ct = context.context_type
    docs = documents_for_context(db, user, context_id)
    inbox = inbox_for_context(db, user, context_id)
    cards: List[Dict[str, Any]] = []

    if ct == WorkContextType.ADMIN:
        cards = [
            {"key": "users", "label": "Users",
             "value": db.query(models.User).filter(models.User.is_active.is_(True)).count()},
            {"key": "departments", "label": "Departments",
             "value": db.query(models.Department).filter(models.Department.is_active.is_(True)).count()},
            {"key": "contexts", "label": "Work Contexts",
             "value": db.query(models.WorkContextMembership).filter(
                 models.WorkContextMembership.is_active.is_(True)).count()},
            {"key": "audit", "label": "Audit Entries",
             "value": db.query(models.AuditLog).count()},
        ]
        return {"context_type": ct.value, "cards": cards, "documents": []}

    if ct == WorkContextType.DS:
        open_docs = [d for d in docs if d.lifecycle != DocumentLifecycle.CLOSED]
        with_director = sum(1 for d in open_docs if d.open_director_review is not None)
        cards = [
            {"key": "awaiting_ds", "label": "Awaiting Your Decision", "value": len(inbox)},
            {"key": "in_work", "label": "In Work",
             "value": sum(1 for d in open_docs if d.lifecycle == DocumentLifecycle.IN_WORK)},
            {"key": "with_director", "label": "With Director", "value": with_director},
            {"key": "closed", "label": "Closed",
             "value": sum(1 for d in docs if d.lifecycle == DocumentLifecycle.CLOSED)},
        ]
    elif ct == WorkContextType.DIRECTOR:
        cards = [
            {"key": "to_review", "label": "Awaiting Your Review", "value": len(inbox)},
            {"key": "reviewed", "label": "Reviews You Completed",
             "value": db.query(models.DirectorReview).filter(
                 models.DirectorReview.director_user_id == user.id).count()},
            {"key": "in_work", "label": "Documents In Work",
             "value": sum(1 for d in docs if d.lifecycle == DocumentLifecycle.IN_WORK)},
        ]
    elif ct == WorkContextType.HOD:
        items = branch_work_items_for_context(db, user, context_id)
        live = [w for w in items if w.stage not in TERMINAL_WORK_STAGES]
        cards = [
            {"key": "branches", "label": "Department Workstreams", "value": len(inbox)},
            {"key": "assigned", "label": "Staff Working", "value": len(live)},
            {"key": "to_validate", "label": "Awaiting Your Validation",
             "value": sum(1 for w in items if w.stage == WorkStage.UNDER_REVIEW)},
            {"key": "overdue", "label": "Overdue",
             "value": sum(1 for w in live if overdue_state(w.deadline) == "overdue")},
        ]
    else:  # EMPLOYEE / TSO
        items = work_items_for_context(db, user, context_id, include_finished=True)
        live = [w for w in items if w.stage not in TERMINAL_WORK_STAGES]
        cards = [
            {"key": "assigned", "label": "My Assignments", "value": len(live)},
            {"key": "under_work", "label": "Under Work",
             "value": sum(1 for w in live if w.stage == WorkStage.UNDER_WORK)},
            {"key": "returned", "label": "Returned to Me",
             "value": sum(1 for w in live if w.stage == WorkStage.RETURNED)},
            {"key": "overdue", "label": "Overdue",
             "value": sum(1 for w in live if overdue_state(w.deadline) == "overdue")},
        ]

    return {
        "context_type": ct.value,
        "department": context.department_name,
        "cards": cards,
        "documents": inbox[:25],
    }
