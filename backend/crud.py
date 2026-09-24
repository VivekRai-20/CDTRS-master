"""CDTRS data access: identity, contexts, intake, attachments, admin, seeding.

Document workflow does NOT live here.  Branch routing, work items, stages,
progress, reviews, Director reviews and closure are all in workflow.py, so
there is exactly one place where workflow rules are enforced.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional

import bcrypt
from jose import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import schemas
import workflow
from models import (
    AttachmentType,
    MessageProcessingStatus,
    OCRStatus,
    Priority,
    UserRole,
    WorkContextType,
)

SECRET_KEY = os.getenv("SECRET_KEY", "cdtrs-super-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "500"))


# =========================================================
# LIVE EVENT MANAGER (WebSocket broadcast)
# =========================================================

class LiveEventManager:
    def __init__(self):
        self._active_connections: List[Any] = []
        self._recent_events: List[Dict[str, Any]] = []
        self._max_recent = 100

    async def connect(self, websocket: Any):
        await websocket.accept()
        self._active_connections.append(websocket)

    def disconnect(self, websocket: Any):
        if websocket in self._active_connections:
            self._active_connections.remove(websocket)

    async def broadcast(
        self,
        event_type: str,
        document_id: Optional[int] = None,
        user_id: Optional[int] = None,
        payload: Optional[dict] = None,
    ):
        event = {
            "event_type": event_type,
            "document_id": document_id,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
            "payload": payload or {},
        }
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_recent:
            self._recent_events.pop(0)
        for connection in list(self._active_connections):
            try:
                await connection.send_json(event)
            except Exception:
                self.disconnect(connection)

    def get_recent_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._recent_events[-limit:]


event_manager = LiveEventManager()


# =========================================================
# PASSWORD & JWT
# =========================================================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None


# =========================================================
# USERS
# =========================================================

def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    db_user = models.User(
        username=user.username,
        password_hash=hash_password(user.password),
        full_name=user.full_name,
        role=user.role,
        employee_code=user.employee_code,
        designation=user.designation,
        email=user.email,
        outlook_email=user.outlook_email,
        gov_email=user.gov_email,
        department_id=user.department_id,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_username(db: Session, username: str) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    return db.query(models.User).filter(models.User.id == user_id).first()


def get_users(db: Session, include_inactive: bool = True) -> List[models.User]:
    q = db.query(models.User)
    if not include_inactive:
        q = q.filter(models.User.is_active.is_(True))
    return q.order_by(models.User.full_name).all()


def get_users_by_role(db: Session, role: UserRole) -> List[models.User]:
    return (
        db.query(models.User)
        .filter(models.User.role == role, models.User.is_active.is_(True))
        .order_by(models.User.full_name)
        .all()
    )


def get_users_by_context(
    db: Session,
    context_type: WorkContextType,
    department_id: Optional[int] = None,
) -> List[models.User]:
    """Users who hold a given work context.  This, not User.role, is what
    routing and assignment pickers should offer."""
    q = (
        db.query(models.User)
        .join(models.WorkContextMembership, models.WorkContextMembership.user_id == models.User.id)
        .filter(
            models.WorkContextMembership.context_type == context_type,
            models.WorkContextMembership.is_active.is_(True),
            models.User.is_active.is_(True),
        )
    )
    if department_id is not None:
        q = q.filter(models.WorkContextMembership.department_id == department_id)
    return q.order_by(models.User.full_name).distinct().all()


def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    user = get_user_by_username(db, username)
    if user and user.is_active and verify_password(password, user.password_hash):
        return user
    return None


def update_user_password(db: Session, user_id: int, new_password: str) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    user.password_hash = hash_password(new_password)
    db.commit()
    return True


# =========================================================
# WORK CONTEXT MEMBERSHIPS
# =========================================================

def get_user_context_memberships(db: Session, user_id: int) -> List[models.WorkContextMembership]:
    return (
        db.query(models.WorkContextMembership)
        .filter(
            models.WorkContextMembership.user_id == user_id,
            models.WorkContextMembership.is_active.is_(True),
        )
        .order_by(models.WorkContextMembership.id.asc())
        .all()
    )


def get_context_membership(db: Session, membership_id: int) -> Optional[models.WorkContextMembership]:
    return (
        db.query(models.WorkContextMembership)
        .filter(models.WorkContextMembership.id == membership_id)
        .first()
    )


def validate_user_context(db: Session, user_id: int, context_id: int) -> Optional[models.WorkContextMembership]:
    return (
        db.query(models.WorkContextMembership)
        .filter(
            models.WorkContextMembership.id == context_id,
            models.WorkContextMembership.user_id == user_id,
            models.WorkContextMembership.is_active.is_(True),
        )
        .first()
    )


def create_work_context_membership(
    db: Session, data: schemas.WorkContextCreate, performed_by_user_id: Optional[int] = None
) -> models.WorkContextMembership:
    if data.context_type in (WorkContextType.HOD, WorkContextType.EMPLOYEE) and not data.department_id:
        raise ValueError(f"A department is required for a {data.context_type.value} context.")

    if data.context_type == WorkContextType.TSO:
        # The organisation designates exactly one TSO.
        membership = workflow.set_active_tso(db, data.user_id, data.department_id)
        db.commit()
        db.refresh(membership)
        return membership

    existing = (
        db.query(models.WorkContextMembership)
        .filter(
            models.WorkContextMembership.user_id == data.user_id,
            models.WorkContextMembership.context_type == data.context_type,
            models.WorkContextMembership.department_id == data.department_id,
        )
        .first()
    )
    if existing:
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing

    membership = models.WorkContextMembership(
        user_id=data.user_id,
        context_type=data.context_type,
        department_id=data.department_id,
        is_active=True,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    log_audit_event(
        db, performed_by_user_id, "CONTEXT_CREATED", "work_context_membership", membership.id,
        f"Granted {membership.label} to user {data.user_id}",
    )
    return membership


def deactivate_work_context_membership(
    db: Session, membership_id: int, performed_by_user_id: Optional[int] = None
) -> Optional[models.WorkContextMembership]:
    membership = get_context_membership(db, membership_id)
    if not membership:
        return None

    live_work = (
        db.query(models.WorkItem)
        .filter(
            models.WorkItem.assigned_to_context_membership_id == membership_id,
            models.WorkItem.is_active.is_(True),
        )
        .count()
    )
    if live_work:
        raise ValueError(
            f"This context still has {live_work} open work item(s). "
            "Reassign or complete them before removing it."
        )

    membership.is_active = False
    db.commit()
    db.refresh(membership)
    log_audit_event(
        db, performed_by_user_id, "CONTEXT_REVOKED", "work_context_membership", membership.id,
        f"Revoked {membership.label} from user {membership.user_id}",
    )
    return membership


def get_single_active_tso(db: Session) -> Optional[models.WorkContextMembership]:
    return workflow.active_tso_context(db)


def set_active_tso(db: Session, user_id: int, performed_by_user_id: Optional[int] = None) -> models.WorkContextMembership:
    membership = workflow.set_active_tso(db, user_id)
    db.commit()
    db.refresh(membership)
    log_audit_event(
        db, performed_by_user_id, "TSO_DESIGNATED", "work_context_membership", membership.id,
        f"Designated user {user_id} as the active TSO",
    )
    return membership


# =========================================================
# DEPARTMENTS
# =========================================================

def create_department(db: Session, dept: schemas.DepartmentCreate) -> models.Department:
    db_dept = models.Department(name=dept.name, code=dept.code)
    db.add(db_dept)
    db.commit()
    db.refresh(db_dept)
    return db_dept


def get_departments(db: Session, include_inactive: bool = False) -> List[models.Department]:
    q = db.query(models.Department)
    if not include_inactive:
        q = q.filter(models.Department.is_active.is_(True))
    return q.order_by(models.Department.name).all()


def get_department_by_id(db: Session, dept_id: int) -> Optional[models.Department]:
    return db.query(models.Department).filter(models.Department.id == dept_id).first()


# =========================================================
# EMPLOYEE DIRECTORY
# =========================================================

def create_employee(db: Session, emp: schemas.EmployeeCreate) -> models.Employee:
    db_emp = models.Employee(
        employee_code=emp.employee_code,
        full_name=emp.full_name,
        department_id=emp.department_id,
        designation=emp.designation,
        email=emp.email,
        outlook_email=emp.outlook_email,
        gov_email=emp.gov_email,
    )
    db.add(db_emp)
    db.commit()
    db.refresh(db_emp)
    return db_emp


def get_employees(db: Session) -> List[models.Employee]:
    return (
        db.query(models.Employee)
        .filter(models.Employee.is_active.is_(True))
        .order_by(models.Employee.full_name)
        .all()
    )


def get_employees_by_department(db: Session, department_id: int) -> List[models.Employee]:
    return (
        db.query(models.Employee)
        .filter(
            models.Employee.department_id == department_id,
            models.Employee.is_active.is_(True),
        )
        .order_by(models.Employee.full_name)
        .all()
    )


# =========================================================
# INTAKE
# =========================================================

def create_incoming_message(
    db: Session, intake: schemas.IntakeCreate, has_attachments: bool = False
) -> models.IncomingMessage:
    if intake.external_message_id:
        existing = (
            db.query(models.IncomingMessage)
            .filter(models.IncomingMessage.external_message_id == intake.external_message_id)
            .first()
        )
        if existing:
            return existing

    msg = models.IncomingMessage(
        source_type=intake.source_type,
        external_message_id=intake.external_message_id,
        sender_name=intake.sender_name,
        sender_email=intake.sender_email,
        subject=intake.subject,
        received_at=intake.received_at or datetime.now(),
        body_reference=intake.body_reference,
        has_attachments=has_attachments,
        processing_status=MessageProcessingStatus.NEW,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_incoming_messages(db: Session) -> List[models.IncomingMessage]:
    """Intake items still awaiting DS processing.  Once converted into a
    document the message is PROCESSED and leaves this queue; the document
    itself carries on in Documents and History."""
    return (
        db.query(models.IncomingMessage)
        .filter(models.IncomingMessage.processing_status != MessageProcessingStatus.PROCESSED)
        .order_by(models.IncomingMessage.created_at.desc())
        .all()
    )


def get_incoming_message_by_id(db: Session, msg_id: int) -> Optional[models.IncomingMessage]:
    return db.query(models.IncomingMessage).filter(models.IncomingMessage.id == msg_id).first()


def get_incoming_message_by_external_id(db: Session, external_id: str) -> Optional[models.IncomingMessage]:
    return (
        db.query(models.IncomingMessage)
        .filter(models.IncomingMessage.external_message_id == external_id)
        .first()
    )


def process_intake_to_document(
    db: Session,
    msg_id: int,
    proc_req: schemas.IntakeProcessRequest,
    user: models.User,
    context_id: Optional[int] = None,
) -> Optional[models.Document]:
    """DS turns an incoming message into a registered document."""
    msg = get_incoming_message_by_id(db, msg_id)
    if not msg:
        return None

    doc_create = schemas.DocumentCreate(
        title=proc_req.title or msg.subject or f"Incoming Message #{msg.id}",
        subject=proc_req.subject or msg.subject,
        description=proc_req.description or msg.body_reference,
        received_date=proc_req.received_date
        or (msg.received_at.date() if msg.received_at else date.today()),
        deadline=proc_req.deadline,
        source=proc_req.source or msg.sender_name or msg.sender_email or "External Intake",
        sender_name=proc_req.sender_name or msg.sender_name,
        sender_reference=proc_req.sender_reference,
        mode=msg.source_type.value,
        priority=proc_req.priority,
        source_message_id=msg.id,
    )

    doc = create_document(db, doc_create, created_by=user.id, context_id=context_id)
    msg.processing_status = MessageProcessingStatus.PROCESSED

    # Attachments captured before the document existed now belong to it.
    for att in (
        db.query(models.Attachment)
        .filter(
            models.Attachment.source_message_id == msg.id,
            models.Attachment.document_id.is_(None),
        )
        .all()
    ):
        att.document_id = doc.doc_id

    db.commit()
    db.refresh(doc)
    return doc


# =========================================================
# DOCUMENTS (creation & metadata; workflow lives in workflow.py)
# =========================================================

def generate_reference_no(db: Session) -> str:
    year = datetime.now().year
    prefix = f"CDTRS-{year}-"
    refs = (
        db.query(models.Document.reference_no)
        .filter(models.Document.reference_no.like(f"{prefix}%"))
        .all()
    )
    max_num = 0
    for (ref,) in refs:
        suffix = ref[len(prefix):] if ref and ref.startswith(prefix) else ""
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    return f"{prefix}{str(max_num + 1).zfill(4)}"


#: Serialises reference-number allocation inside this server process.
_REFERENCE_LOCK = threading.Lock()


def _fit(value: Any, column) -> Any:
    """Trim text to the column's length.  OCR-derived values (a long subject
    line, a sender block) must not make the database reject the document."""
    if value is None or not isinstance(value, str):
        return value
    value = value.strip()
    length = getattr(getattr(column, "type", None), "length", None)
    if length and len(value) > length:
        value = value[: max(0, length - 1)].rstrip() + "…"
    return value


def _fit_document_fields(values: Dict[str, Any]) -> Dict[str, Any]:
    columns = models.Document.__table__.columns
    return {k: (_fit(v, columns[k]) if k in columns else v) for k, v in values.items()}


def create_document(
    db: Session,
    doc: schemas.DocumentCreate,
    created_by: int,
    context_id: Optional[int] = None,
) -> models.Document:
    values = _fit_document_fields(dict(
        title=(doc.title or "").strip() or "Untitled document",
        subject=doc.subject,
        description=doc.description,
        received_date=doc.received_date,
        deadline=doc.deadline,
        source=doc.source,
        sender_name=doc.sender_name,
        sender_reference=doc.sender_reference,
        mode=doc.mode or "MANUAL_UPLOAD",
        priority=doc.priority,
        lifecycle=models.DocumentLifecycle.RECEIVED,
        created_by=created_by,
        source_message_id=doc.source_message_id,
        ocr_status=OCRStatus.NONE,
        version=1,
    ))
    # Two registrations at the same moment could compute the same next
    # reference number; retry with a fresh number instead of failing.
    with _REFERENCE_LOCK:
        for attempt in range(5):
            db_doc = models.Document(reference_no=generate_reference_no(db), **values)
            db.add(db_doc)
            try:
                db.commit()
                break
            except IntegrityError:
                db.rollback()
                if attempt == 4:
                    raise
    db.refresh(db_doc)

    actor = get_user_by_id(db, created_by)
    context = get_context_membership(db, context_id) if context_id else None
    workflow.record_event(
        db,
        document_id=db_doc.doc_id,
        event_type="DOCUMENT_RECEIVED",
        summary=f"Document received via {doc.mode}",
        actor=actor,
        context=context,
        details=doc.description,
    )
    db.commit()
    db.refresh(db_doc)
    return db_doc


def get_document(db: Session, doc_id: int) -> Optional[models.Document]:
    return db.query(models.Document).filter(models.Document.doc_id == doc_id).first()


def update_document_metadata(
    db: Session,
    doc_id: int,
    payload: schemas.DocumentUpdate,
    actor: models.User,
    context_id: Optional[int] = None,
) -> models.Document:
    """DS corrects document metadata, including anything OCR got wrong.  Each
    correction is recorded so the change is traceable."""
    context = workflow.require_context(db, actor, context_id, WorkContextType.DS)
    doc = get_document(db, doc_id)
    if not doc:
        raise workflow.WorkflowError(f"Document {doc_id} not found.")
    if payload.expected_version is not None and doc.version != payload.expected_version:
        raise workflow.WorkflowError(
            "This document was changed by someone else. Reload it and try again."
        )

    changes: List[str] = []
    for field in (
        "title", "subject", "description", "received_date",
        "deadline", "source", "sender_name", "sender_reference", "priority",
    ):
        new_value = getattr(payload, field, None)
        if new_value is None:
            continue
        new_value = _fit(new_value, models.Document.__table__.columns[field])
        old_value = getattr(doc, field)
        if old_value != new_value:
            setattr(doc, field, new_value)
            changes.append(f"{field}: '{old_value}' -> '{new_value}'")

    if changes:
        doc.version += 1
        doc.updated_at = datetime.now()
        workflow.record_event(
            db,
            document_id=doc_id,
            event_type="METADATA_UPDATED",
            summary=f"{actor.full_name} updated document details",
            actor=actor,
            context=context,
            details="; ".join(changes),
        )
    db.commit()
    db.refresh(doc)
    return doc


# =========================================================
# ATTACHMENTS
# =========================================================

def compute_checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_attachment(
    db: Session,
    doc_id: Optional[int],
    progress_update_id: Optional[int],
    uploaded_by: int,
    file_name: str,
    storage_key: str,
    file_type: Optional[str],
    file_size: Optional[int],
    checksum: Optional[str] = None,
    attachment_type: AttachmentType = AttachmentType.ORIGINAL,
    source_message_id: Optional[int] = None,
    context_id: Optional[int] = None,
) -> models.Attachment:
    """Store a file and keep it attached to whatever it belongs to: the
    document itself, or one specific progress update (and therefore one
    person's work item)."""
    att = models.Attachment(
        document_id=doc_id,
        progress_update_id=progress_update_id,
        uploaded_by_user_id=uploaded_by,
        uploaded_by_context_membership_id=context_id,
        file_name=file_name,
        storage_key=storage_key,
        file_type=file_type,
        file_size=file_size,
        checksum=checksum,
        attachment_type=attachment_type,
        source_message_id=source_message_id,
    )
    db.add(att)
    db.flush()

    if doc_id:
        progress_record = (
            db.query(models.ProgressUpdate)
            .filter(models.ProgressUpdate.id == progress_update_id)
            .first()
            if progress_update_id
            else None
        )
        actor = get_user_by_id(db, uploaded_by)
        workflow.record_event(
            db,
            document_id=doc_id,
            branch_id=progress_record.work_item.branch_id if progress_record else None,
            work_item_id=progress_record.work_item_id if progress_record else None,
            event_type="ATTACHMENT_UPLOADED",
            summary=f"{actor.full_name if actor else 'Someone'} uploaded {file_name}",
            actor=actor,
            context=get_context_membership(db, context_id) if context_id else None,
            details=f"{file_name} ({attachment_type.value})",
        )

    db.commit()
    db.refresh(att)
    return att


def get_attachments(db: Session, doc_id: int) -> List[models.Attachment]:
    return (
        db.query(models.Attachment)
        .filter(models.Attachment.document_id == doc_id)
        .order_by(models.Attachment.created_at)
        .all()
    )


def get_attachment(db: Session, attachment_id: int) -> Optional[models.Attachment]:
    return db.query(models.Attachment).filter(models.Attachment.id == attachment_id).first()


# =========================================================
# NOTIFICATIONS
# =========================================================

def get_notifications(
    db: Session, user_id: int, context_id: Optional[int] = None, limit: int = 100
) -> List[models.Notification]:
    """Notifications for this user, narrowed to the hat they are wearing.
    Context-less notifications are always shown."""
    q = db.query(models.Notification).filter(models.Notification.user_id == user_id)
    if context_id is not None:
        q = q.filter(
            (models.Notification.context_membership_id == context_id)
            | (models.Notification.context_membership_id.is_(None))
        )
    return q.order_by(models.Notification.created_at.desc()).limit(limit).all()


def get_unread_notifications(
    db: Session, user_id: int, context_id: Optional[int] = None
) -> List[models.Notification]:
    q = db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.is_read.is_(False),
    )
    if context_id is not None:
        q = q.filter(
            (models.Notification.context_membership_id == context_id)
            | (models.Notification.context_membership_id.is_(None))
        )
    return q.order_by(models.Notification.created_at.desc()).all()


def mark_notification_read(db: Session, notification_id: int, user_id: int) -> Optional[models.Notification]:
    note = (
        db.query(models.Notification)
        .filter(models.Notification.id == notification_id, models.Notification.user_id == user_id)
        .first()
    )
    if note:
        note.is_read = True
        db.commit()
        db.refresh(note)
    return note


def mark_all_notifications_read(db: Session, user_id: int, context_id: Optional[int] = None) -> int:
    q = db.query(models.Notification).filter(
        models.Notification.user_id == user_id,
        models.Notification.is_read.is_(False),
    )
    if context_id is not None:
        q = q.filter(
            (models.Notification.context_membership_id == context_id)
            | (models.Notification.context_membership_id.is_(None))
        )
    count = q.update({"is_read": True}, synchronize_session=False)
    db.commit()
    return count


def get_reminders(db: Session, user_id: int) -> List[models.Reminder]:
    return (
        db.query(models.Reminder)
        .filter(models.Reminder.recipient_user_id == user_id)
        .order_by(models.Reminder.sent_at.desc())
        .all()
    )


def mark_reminder_read(db: Session, reminder_id: int, user_id: int) -> Optional[models.Reminder]:
    rem = (
        db.query(models.Reminder)
        .filter(models.Reminder.id == reminder_id, models.Reminder.recipient_user_id == user_id)
        .first()
    )
    if rem:
        rem.is_read = True
        db.commit()
        db.refresh(rem)
    return rem


def send_manual_reminder(
    db: Session,
    doc_id: int,
    actor: models.User,
    context_id: Optional[int] = None,
    work_item_id: Optional[int] = None,
    recipient_user_id: Optional[int] = None,
    message: Optional[str] = None,
) -> int:
    """DS or HOD nudges whoever is holding the work.  Targets one work item
    when given, otherwise everyone with live work on the document."""
    context = workflow.require_context(db, actor, context_id, WorkContextType.DS, WorkContextType.HOD)
    doc = get_document(db, doc_id)
    if not doc:
        raise workflow.WorkflowError(f"Document {doc_id} not found.")

    targets: List[models.WorkItem] = []
    if work_item_id:
        item = db.query(models.WorkItem).filter(models.WorkItem.id == work_item_id).first()
        if not item:
            raise workflow.WorkflowError("Work item not found.")
        targets = [item]
    else:
        targets = [
            w for w in doc.work_items
            if w.stage not in workflow.TERMINAL_WORK_STAGES
            and (recipient_user_id is None or w.assigned_to_user_id == recipient_user_id)
        ]

    if not targets:
        raise workflow.WorkflowError("There is no open work on this document to remind about.")

    body = message or f"Please update your work on '{doc.title}' ({doc.reference_no})."
    now = datetime.now()
    sent = 0
    for item in targets:
        key = f"manual:{item.id}:{now.isoformat()}"
        db.add(models.Reminder(
            document_id=doc_id,
            work_item_id=item.id,
            recipient_user_id=item.assigned_to_user_id,
            recipient_context_membership_id=item.assigned_to_context_membership_id,
            reason=models.ReminderReason.ACTION_REQUIRED,
            message=body,
            due_at=datetime.combine(item.deadline, datetime.min.time()) if item.deadline else None,
            deduplication_key=key,
        ))
        workflow.notify(
            db,
            user_id=item.assigned_to_user_id,
            context_membership_id=item.assigned_to_context_membership_id,
            document_id=doc_id,
            branch_id=item.branch_id,
            work_item_id=item.id,
            title=f"{doc.reference_no}: reminder",
            message=body,
        )
        sent += 1

    workflow.record_event(
        db,
        document_id=doc_id,
        event_type="REMINDER_SENT",
        summary=f"{actor.full_name} sent a reminder to {sent} person(s)",
        actor=actor,
        context=context,
        details=body,
    )
    db.commit()
    return sent


# =========================================================
# ADMIN AUDIT (configuration only)
# =========================================================

def log_audit_event(
    db: Session,
    user_id: Optional[int],
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    description: Optional[str] = None,
) -> models.AuditLog:
    entry = models.AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_audit_logs(db: Session, limit: int = 200, offset: int = 0) -> List[models.AuditLog]:
    return (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


# =========================================================
# ADMIN: USERS, DEPARTMENTS, SETTINGS
# =========================================================

def create_admin_user(db: Session, data: schemas.AdminUserCreate, performed_by_user_id: Optional[int] = None) -> models.User:
    if get_user_by_username(db, data.username):
        raise ValueError(f"Username '{data.username}' is already taken.")
    user = models.User(
        username=data.username,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
        email=data.email,
        outlook_email=data.outlook_email,
        gov_email=data.gov_email,
        employee_code=data.employee_code,
        designation=data.designation,
        department_id=data.department_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_audit_event(db, performed_by_user_id, "USER_CREATED", "user", user.id, f"Created account {user.username}")
    return user


def update_admin_user(
    db: Session, user_id: int, data: schemas.AdminUserUpdate, performed_by_user_id: Optional[int] = None
) -> Optional[models.User]:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    changes = []
    for field in (
        "full_name", "role", "email", "outlook_email", "gov_email",
        "employee_code", "designation", "department_id", "is_active",
    ):
        value = getattr(data, field, None)
        if value is None:
            continue
        if getattr(user, field) != value:
            changes.append(f"{field}={value}")
            setattr(user, field, value)
    db.commit()
    db.refresh(user)
    if changes:
        log_audit_event(
            db, performed_by_user_id, "USER_UPDATED", "user", user.id,
            f"Updated {user.username}: {', '.join(changes)}",
        )
    return user


def reset_user_password(db: Session, user_id: int, new_password: str, performed_by_user_id: Optional[int] = None) -> bool:
    ok = update_user_password(db, user_id, new_password)
    if ok:
        log_audit_event(db, performed_by_user_id, "PASSWORD_RESET", "user", user_id, "Administrative password reset")
    return ok


def toggle_user_active(db: Session, user_id: int, performed_by_user_id: Optional[int] = None) -> Optional[bool]:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    user.is_active = not user.is_active
    db.commit()
    log_audit_event(
        db, performed_by_user_id, "USER_ACTIVATION_TOGGLED", "user", user.id,
        f"{user.username} is now {'active' if user.is_active else 'inactive'}",
    )
    return user.is_active


def create_admin_department(db: Session, dept: schemas.DepartmentCreate, performed_by_user_id: Optional[int] = None) -> models.Department:
    existing = db.query(models.Department).filter(models.Department.name == dept.name).first()
    if existing:
        raise ValueError(f"Department '{dept.name}' already exists.")
    department = models.Department(name=dept.name, code=dept.code, is_active=True)
    db.add(department)
    db.commit()
    db.refresh(department)
    log_audit_event(db, performed_by_user_id, "DEPARTMENT_CREATED", "department", department.id, f"Created {department.name}")
    return department


def update_admin_department(
    db: Session, dept_id: int, data: Dict[str, Any], performed_by_user_id: Optional[int] = None
) -> Optional[models.Department]:
    dept = get_department_by_id(db, dept_id)
    if not dept:
        return None
    for field in ("name", "code", "is_active"):
        if field in data and data[field] is not None:
            setattr(dept, field, data[field])
    db.commit()
    db.refresh(dept)
    log_audit_event(db, performed_by_user_id, "DEPARTMENT_UPDATED", "department", dept.id, f"Updated {dept.name}")
    return dept


def get_system_settings(db: Session) -> Dict[str, str]:
    return {s.key: s.value for s in db.query(models.SystemSetting).all()}


def update_system_setting(
    db: Session, key: str, value: str, description: Optional[str] = None,
    performed_by_user_id: Optional[int] = None,
) -> models.SystemSetting:
    setting = db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first()
    if setting:
        setting.value = value
        if description:
            setting.description = description
    else:
        setting = models.SystemSetting(key=key, value=value, description=description)
        db.add(setting)
    db.commit()
    db.refresh(setting)
    log_audit_event(db, performed_by_user_id, "SETTING_UPDATED", "system_setting", setting.id, f"{key} = {value}")
    return setting


DEFAULT_SETTINGS = {
    "mail.notifications_enabled": ("true", "Send workflow notifications by email"),
    "mail.reminder_enabled": ("true", "Send deadline reminder emails"),
    "mail.reminder_lead_days": ("2", "Days before a deadline to start reminding"),
    "mail.from_address": ("cdtrs@novacore.example", "Sender address for outgoing notifications"),
    "mail.template.assignment": (
        "You have been assigned work on {reference_no}: {title}.",
        "Template for new assignment notifications",
    ),
    "mail.template.reminder": (
        "Reminder: your work on {reference_no} is due on {deadline}.",
        "Template for deadline reminders",
    ),
    "workflow.default_deadline_days": ("7", "Default deadline when none is given"),
}


def ensure_default_settings(db: Session) -> None:
    for key, (value, description) in DEFAULT_SETTINGS.items():
        if not db.query(models.SystemSetting).filter(models.SystemSetting.key == key).first():
            db.add(models.SystemSetting(key=key, value=value, description=description))
    db.commit()


# =========================================================
# SEEDING
# =========================================================

def _resolve_department(db: Session, token: Optional[str]) -> Optional[models.Department]:
    """Seed files refer to departments by code OR name; accept both."""
    if not token:
        return None
    return (
        db.query(models.Department)
        .filter((models.Department.code == token) | (models.Department.name == token))
        .first()
    )


def seed_data(db: Session) -> None:
    """Create departments, accounts and work contexts from
    backend/data/seed_data.json."""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "seed_data.json")
    payload: Dict[str, Any] = {}
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

    # --- departments ---
    for d in payload.get("departments", []):
        if not db.query(models.Department).filter(models.Department.name == d["name"]).first():
            db.add(models.Department(name=d["name"], code=d.get("code"), is_active=True))
    db.commit()

    # --- employee directory ---
    for emp in payload.get("employees", []):
        code = emp.get("employee_code")
        dept = _resolve_department(db, emp.get("department"))
        if not dept:
            raise ValueError(f"Unknown department '{emp.get('department')}' for employee {code}.")
        record = db.query(models.Employee).filter(models.Employee.employee_code == code).first()
        if not record:
            record = models.Employee(
                employee_code=code,
                full_name=emp.get("full_name"),
                department_id=dept.id,
                designation=emp.get("designation") or "Staff",
                email=emp.get("email"),
                outlook_email=emp.get("outlook_email"),
                gov_email=emp.get("gov_email"),
            )
            db.add(record)
        else:
            record.department_id = dept.id
            record.email = emp.get("email") or record.email
    db.commit()

    # --- accounts ---
    definitions: List[Dict[str, Any]] = []
    for su in payload.get("system_users", []):
        definitions.append({**su, "_role": UserRole(su["role"])})
    for emp in payload.get("employees", []):
        definitions.append({**emp, "_role": UserRole.EMPLOYEE})

    for spec in definitions:
        username = spec.get("username")
        if not username:
            continue
        dept = _resolve_department(db, spec.get("department"))
        user = get_user_by_username(db, username)
        if not user:
            user = models.User(
                username=username,
                password_hash=hash_password(spec.get("default_password") or "cdtrs@123"),
                full_name=spec.get("full_name"),
                role=spec["_role"],
                employee_code=spec.get("employee_code"),
                designation=spec.get("designation") or "Staff",
                email=spec.get("email"),
                outlook_email=spec.get("outlook_email"),
                gov_email=spec.get("gov_email"),
                department_id=dept.id if dept else None,
                is_active=True,
            )
            db.add(user)
            db.flush()
        else:
            user.full_name = spec.get("full_name") or user.full_name
            user.role = spec["_role"]
            user.designation = spec.get("designation") or user.designation
            user.employee_code = spec.get("employee_code") or user.employee_code
            if dept:
                user.department_id = dept.id

        # link the HR directory record to the account
        if spec.get("employee_code"):
            record = (
                db.query(models.Employee)
                .filter(models.Employee.employee_code == spec["employee_code"])
                .first()
            )
            if record and not record.user_id:
                record.user_id = user.id
    db.commit()

    # --- work contexts ---
    default_contexts = {
        UserRole.ADMIN: [{"context": "ADMIN"}],
        UserRole.DS: [{"context": "DS"}],
        UserRole.DIRECTOR: [{"context": "DIRECTOR"}],
        UserRole.HOD: [{"context": "HOD", "from_user_department": True}],
        UserRole.EMPLOYEE: [{"context": "EMPLOYEE", "from_user_department": True}],
        UserRole.TSO: [{"context": "TSO"}],
    }

    tso_seeded = False
    for spec in definitions:
        user = get_user_by_username(db, spec.get("username", ""))
        if not user:
            continue
        context_defs = spec.get("contexts") or default_contexts.get(spec["_role"], [])
        for cdef in context_defs:
            try:
                ctype = WorkContextType(cdef.get("context") or cdef.get("context_type"))
            except ValueError:
                continue

            department_id = None
            token = cdef.get("department_code") or cdef.get("department")
            if token:
                dept = _resolve_department(db, token)
                if not dept:
                    raise ValueError(
                        f"Unknown department '{token}' for {ctype.value} context of {user.username}."
                    )
                department_id = dept.id
            elif cdef.get("from_user_department"):
                department_id = user.department_id

            if ctype == WorkContextType.TSO:
                # Exactly one TSO organisation-wide.
                if not tso_seeded:
                    workflow.set_active_tso(db, user.id, department_id)
                    tso_seeded = True
                continue

            existing = (
                db.query(models.WorkContextMembership)
                .filter(
                    models.WorkContextMembership.user_id == user.id,
                    models.WorkContextMembership.context_type == ctype,
                    models.WorkContextMembership.department_id == department_id,
                )
                .first()
            )
            if existing:
                existing.is_active = True
            else:
                db.add(models.WorkContextMembership(
                    user_id=user.id,
                    context_type=ctype,
                    department_id=department_id,
                    is_active=True,
                ))
    db.commit()

    ensure_default_settings(db)

    dept_count = db.query(models.Department).count()
    user_count = db.query(models.User).count()
    ctx_count = db.query(models.WorkContextMembership).filter(
        models.WorkContextMembership.is_active.is_(True)
    ).count()
    print(
        f"[CDTRS SEED] {dept_count} departments, {user_count} accounts, {ctx_count} work contexts.",
        flush=True,
    )
