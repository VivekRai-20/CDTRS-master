"""
CDTRS canonical data model.

Design rules enforced by this schema
------------------------------------
1.  A Document has exactly one *lifecycle*.  It never describes the state of
    the work happening inside it.
2.  A DocumentBranch is an independent workstream on a document.  It carries
    its own stage.  Branches of the same document are free to sit at
    completely different stages at the same time.
3.  A WorkItem is the record of ONE PERSON's work on ONE branch.  It is the
    atomic unit of responsibility, stage, deadline, progress and traceability.
    A team is a grouping of WorkItems, never a replacement for them.
4.  Progress is free text written by the person doing the work.  There is no
    percentage anywhere in this schema, and none may be added.
5.  Nothing that has happened is ever overwritten.  Remarks, reviews, progress
    updates, stage changes and attachments are append-only.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    Boolean,
    Float,
    BigInteger,
    ForeignKey,
    UniqueConstraint,
    Index,
    JSON,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import List, Optional
import enum

from database import Base


# =========================================================
# IDENTITY & CONTEXT ENUMS
# =========================================================

class UserRole(str, enum.Enum):
    """Primary designation of an account.  Authorization is driven by the
    active WorkContextMembership, not by this field."""
    ADMIN    = "ADMIN"
    DS       = "DS"
    DIRECTOR = "DIRECTOR"
    TSO      = "TSO"
    HOD      = "HOD"
    EMPLOYEE = "EMPLOYEE"


class WorkContextType(str, enum.Enum):
    """The hat a user is currently wearing.  This is the authorization unit."""
    EMPLOYEE = "EMPLOYEE"
    HOD      = "HOD"
    DIRECTOR = "DIRECTOR"
    DS       = "DS"
    TSO      = "TSO"
    ADMIN    = "ADMIN"


# =========================================================
# WORKFLOW ENUMS
# =========================================================

class DocumentLifecycle(str, enum.Enum):
    """Overall state of the document.  Deliberately coarse: detail lives on
    branches and work items."""
    RECEIVED   = "RECEIVED"      # captured from mail/upload, not yet registered
    REGISTERED = "REGISTERED"    # DS verified metadata; no routing yet
    IN_REVIEW  = "IN_REVIEW"     # a Director review branch is open
    IN_WORK    = "IN_WORK"       # at least one work branch is active
    WITH_DS    = "WITH_DS"       # nothing active; awaiting a DS decision
    CLOSED     = "CLOSED"        # closed by DS


class BranchType(str, enum.Enum):
    DIRECTOR   = "DIRECTOR"      # DS -> Director, review & remark
    DEPARTMENT = "DEPARTMENT"    # DS -> HOD of a department
    EMPLOYEE   = "EMPLOYEE"      # DS -> employee directly (no HOD)
    TSO        = "TSO"           # DS -> TSO


class BranchStage(str, enum.Enum):
    """Stage of ONE branch.  Which values are legal depends on branch_type;
    see workflow.BRANCH_STAGES."""

    # --- DIRECTOR branch ---
    REVIEW_REQUESTED      = "REVIEW_REQUESTED"
    UNDER_DIRECTOR_REVIEW = "UNDER_DIRECTOR_REVIEW"
    REMARK_ADDED          = "REMARK_ADDED"
    RETURNED_TO_DS        = "RETURNED_TO_DS"

    # --- DEPARTMENT (HOD) branch ---
    HOD_REVIEW            = "HOD_REVIEW"
    EMPLOYEE_ASSIGNMENT   = "EMPLOYEE_ASSIGNMENT"
    EMPLOYEE_WORK         = "EMPLOYEE_WORK"
    HOD_VALIDATION        = "HOD_VALIDATION"

    # --- EMPLOYEE / TSO direct branch ---
    ASSIGNED              = "ASSIGNED"
    IN_PROGRESS           = "IN_PROGRESS"
    SUBMITTED             = "SUBMITTED"

    # --- shared terminal / rework states ---
    FURTHER_WORK          = "FURTHER_WORK"   # DS sent it back for more work
    COMPLETED             = "COMPLETED"
    CANCELLED             = "CANCELLED"


class WorkStage(str, enum.Enum):
    """Stage of ONE person's work item.  Set by the worker (or by the
    HOD/DS through review and rework actions)."""
    ASSIGNED     = "ASSIGNED"
    UNDER_WORK   = "UNDER_WORK"
    WAITING      = "WAITING"       # blocked on someone else
    SUBMITTED    = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"  # with the HOD
    RETURNED     = "RETURNED"      # HOD/DS sent it back to the worker
    COMPLETED    = "COMPLETED"
    CANCELLED    = "CANCELLED"


class ReviewOutcome(str, enum.Enum):
    ACCEPTED = "ACCEPTED"
    RETURNED = "RETURNED"


class RemarkType(str, enum.Enum):
    DIRECTOR = "DIRECTOR"
    HOD      = "HOD"
    DS       = "DS"
    TSO      = "TSO"
    EMPLOYEE = "EMPLOYEE"
    OTHER    = "OTHER"


class Priority(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH     = "HIGH"
    MEDIUM   = "MEDIUM"
    LOW      = "LOW"


# =========================================================
# INTAKE / PROCESSING ENUMS
# =========================================================

class SourceType(str, enum.Enum):
    OUTLOOK               = "OUTLOOK"
    GOVERNMENT_MAIL       = "GOVERNMENT_MAIL"
    MANUAL_UPLOAD         = "MANUAL_UPLOAD"
    OTHER_APPROVED_SOURCE = "OTHER_APPROVED_SOURCE"
    MANUAL                = "MANUAL"


class MessageProcessingStatus(str, enum.Enum):
    NEW        = "NEW"
    PROCESSING = "PROCESSING"
    PROCESSED  = "PROCESSED"
    FAILED     = "FAILED"
    IGNORED    = "IGNORED"


class AttachmentType(str, enum.Enum):
    ORIGINAL            = "ORIGINAL"
    EMAIL_ATTACHMENT    = "EMAIL_ATTACHMENT"
    SUPPORTING_DOCUMENT = "SUPPORTING_DOCUMENT"
    PROGRESS_ATTACHMENT = "PROGRESS_ATTACHMENT"


class OCRStatus(str, enum.Enum):
    NONE       = "NONE"
    PENDING    = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"


class RoutingSource(str, enum.Enum):
    DOCUMENT_CONTENT = "DOCUMENT_CONTENT"
    DIRECTOR_REMARK  = "DIRECTOR_REMARK"
    SOURCE_METADATA  = "SOURCE_METADATA"
    MANUAL           = "MANUAL"


class ReminderReason(str, enum.Enum):
    DUE_SOON        = "DUE_SOON"
    OVERDUE         = "OVERDUE"
    ACTION_REQUIRED = "ACTION_REQUIRED"


# =========================================================
# DEPARTMENT
# =========================================================

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, nullable=True)
    # What the department handles, in plain words, and the words / phrases that
    # identify its documents.  Both are used by the routing suggestion.
    description = Column(Text, nullable=True)
    keywords = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    users     = relationship("User", back_populates="department_rel", foreign_keys="User.department_id")
    employees = relationship("Employee", back_populates="department")


# =========================================================
# EMPLOYEE DIRECTORY (HR reference data, not a workflow actor)
# =========================================================

class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    designation = Column(String(100), nullable=False)
    email = Column(String(255), nullable=True)
    outlook_email = Column(String(255), nullable=True)
    gov_email = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    department = relationship("Department", back_populates="employees")
    user       = relationship("User", foreign_keys=[user_id], back_populates="employee_record")


# =========================================================
# USER
# =========================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(SAEnum(UserRole, name="user_role"), nullable=False)
    employee_code = Column(String(50), nullable=True)
    designation = Column(String(100), nullable=True)

    email = Column(String(255), unique=True, nullable=True, index=True)
    outlook_email = Column(String(255), nullable=True)
    gov_email = Column(String(255), nullable=True)
    preferred_mail_channel = Column(String(50), default="outlook", nullable=False)

    # Home department.  Operational department comes from the active context.
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    department_rel  = relationship("Department", back_populates="users", foreign_keys=[department_id])
    employee_record = relationship(
        "Employee", foreign_keys="Employee.user_id", back_populates="user", uselist=False
    )
    notifications = relationship(
        "Notification", back_populates="user",
        foreign_keys="Notification.user_id", cascade="all, delete-orphan",
    )
    context_memberships = relationship(
        "WorkContextMembership", back_populates="user",
        foreign_keys="WorkContextMembership.user_id", cascade="all, delete-orphan",
    )

    @property
    def department(self) -> Optional[str]:
        return self.department_rel.name if self.department_rel else None


# =========================================================
# WORK CONTEXT MEMBERSHIP
# =========================================================

class WorkContextMembership(Base):
    """One hat a user can wear.  A user may hold several, e.g. HOD-Engineering
    plus Employee-Product plus TSO.  The active membership decides what the
    user sees and what they are allowed to do."""

    __tablename__ = "work_context_memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "context_type", "department_id", name="uq_context_identity"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    context_type = Column(SAEnum(WorkContextType, name="work_context_type"), nullable=False, index=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user       = relationship("User", back_populates="context_memberships", foreign_keys=[user_id])
    department = relationship("Department", foreign_keys=[department_id])

    @property
    def department_name(self) -> Optional[str]:
        return self.department.name if self.department else None

    @property
    def user_name(self) -> Optional[str]:
        return self.user.full_name if self.user else None

    @property
    def label(self) -> str:
        if self.department:
            return f"{self.context_type.value} - {self.department.name}"
        return self.context_type.value


# =========================================================
# INCOMING MESSAGES (intake provenance)
# =========================================================

class IncomingMessage(Base):
    __tablename__ = "incoming_messages"

    id = Column(Integer, primary_key=True, index=True)
    source_type = Column(SAEnum(SourceType, name="source_type_enum"), default=SourceType.MANUAL_UPLOAD, nullable=False)
    external_message_id = Column(String(255), unique=True, nullable=True, index=True)
    sender_name = Column(String(150), nullable=True)
    sender_email = Column(String(255), nullable=True)
    subject = Column(String(500), nullable=True)
    received_at = Column(DateTime, default=datetime.now)
    body_reference = Column(Text, nullable=True)
    has_attachments = Column(Boolean, default=False)
    processing_status = Column(SAEnum(MessageProcessingStatus, name="msg_status_enum"), default=MessageProcessingStatus.NEW, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    documents   = relationship("Document", back_populates="source_message")
    attachments = relationship("Attachment", back_populates="source_message")


# =========================================================
# DOCUMENT
# =========================================================

class Document(Base):
    """The document itself.  `lifecycle` describes the DOCUMENT, never the
    work.  Work state lives on branches and work items and is never collapsed
    into a single value here."""

    __tablename__ = "documents"

    doc_id = Column(Integer, primary_key=True, index=True)
    reference_no = Column(String(50), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    received_date = Column(Date, nullable=False)
    deadline = Column(Date, nullable=True)
    source = Column(String(255), nullable=True)
    sender_name = Column(String(150), nullable=True)
    sender_reference = Column(String(120), nullable=True)
    mode = Column(String(50), nullable=False)
    priority = Column(SAEnum(Priority, name="priority_enum"), default=Priority.MEDIUM, nullable=False)

    lifecycle = Column(
        SAEnum(DocumentLifecycle, name="document_lifecycle"),
        default=DocumentLifecycle.RECEIVED, nullable=False, index=True,
    )

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_message_id = Column(Integer, ForeignKey("incoming_messages.id"), nullable=True)
    ocr_status = Column(SAEnum(OCRStatus, name="ocr_status_enum"), default=OCRStatus.NONE, nullable=False)

    version = Column(Integer, default=1, nullable=False)

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    registered_at = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    closed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    closure_remark = Column(Text, nullable=True)

    creator   = relationship("User", foreign_keys=[created_by])
    closed_by = relationship("User", foreign_keys=[closed_by_user_id])
    source_message = relationship("IncomingMessage", back_populates="documents")

    branches = relationship(
        "DocumentBranch", back_populates="document",
        cascade="all, delete-orphan", order_by="DocumentBranch.opened_at",
    )
    work_items = relationship(
        "WorkItem", back_populates="document",
        cascade="all, delete-orphan", order_by="WorkItem.assigned_at",
    )
    progress_updates = relationship("ProgressUpdate", back_populates="document", cascade="all, delete-orphan")
    attachments      = relationship("Attachment", back_populates="document", cascade="all, delete-orphan")
    events           = relationship(
        "WorkflowEvent", back_populates="document",
        cascade="all, delete-orphan", order_by="WorkflowEvent.created_at",
    )
    notifications    = relationship("Notification", back_populates="document", cascade="all, delete-orphan")
    ocr_record       = relationship("DocumentOCR", back_populates="document", uselist=False, cascade="all, delete-orphan")
    extracted_fields = relationship("DocumentExtractedField", back_populates="document", cascade="all, delete-orphan")
    routing_suggestion = relationship("RoutingSuggestion", back_populates="document", uselist=False, cascade="all, delete-orphan")
    remarks          = relationship(
        "DocumentRemark", back_populates="document",
        cascade="all, delete-orphan", order_by="DocumentRemark.created_at",
    )
    director_reviews = relationship(
        "DirectorReview", back_populates="document",
        cascade="all, delete-orphan", order_by="DirectorReview.created_at",
    )
    reminders = relationship("Reminder", back_populates="document", cascade="all, delete-orphan")

    # ---- convenience projections (read-only; never persisted) ----

    @property
    def active_branches(self) -> List["DocumentBranch"]:
        return [b for b in self.branches if b.is_active]

    @property
    def open_director_review(self) -> Optional["DocumentBranch"]:
        for b in self.branches:
            if b.is_active and b.branch_type == BranchType.DIRECTOR:
                return b
        return None

    @property
    def latest_director_remark(self) -> Optional[str]:
        reviews = [r for r in self.director_reviews if r.remark_text]
        return reviews[-1].remark_text if reviews else None

    @property
    def people_involved(self) -> List[str]:
        names: List[str] = []
        for wi in self.work_items:
            if wi.assignee and wi.assignee.full_name not in names:
                names.append(wi.assignee.full_name)
        return names

    @property
    def is_closed(self) -> bool:
        return self.lifecycle == DocumentLifecycle.CLOSED


# =========================================================
# DOCUMENT BRANCH (independent workstream)
# =========================================================

class DocumentBranch(Base):
    """One independent workstream on a document.

    Branch identity is (document, branch_type, department_id | target_user_id).
    Re-routing to a target that already has an OPEN branch extends that branch
    with a new round instead of creating a duplicate; re-routing to a target
    whose branch is CLOSED opens a fresh branch, so the earlier one stays in
    history untouched."""

    __tablename__ = "document_branches"
    __table_args__ = (
        Index("ix_branch_doc_active", "document_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=False, index=True)
    branch_type = Column(SAEnum(BranchType, name="branch_type"), nullable=False, index=True)
    stage = Column(SAEnum(BranchStage, name="branch_stage"), nullable=False, index=True)

    # Target: department for DEPARTMENT branches, a user for the rest.
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    target_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)

    opened_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    opened_by_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)

    instructions = Column(Text, nullable=True)
    requires_hod_validation = Column(Boolean, default=False, nullable=False)
    deadline = Column(Date, nullable=True)

    # Incremented each time DS sends further work down this same branch.
    round_no = Column(Integer, default=1, nullable=False)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    opened_at = Column(DateTime, default=datetime.now)
    closed_at = Column(DateTime, nullable=True)
    version = Column(Integer, default=1, nullable=False)

    document       = relationship("Document", back_populates="branches")
    department     = relationship("Department", foreign_keys=[department_id])
    target_user    = relationship("User", foreign_keys=[target_user_id])
    target_context = relationship("WorkContextMembership", foreign_keys=[target_context_membership_id])
    opened_by      = relationship("User", foreign_keys=[opened_by_user_id])
    opened_by_context = relationship("WorkContextMembership", foreign_keys=[opened_by_context_membership_id])

    work_items = relationship(
        "WorkItem", back_populates="branch",
        cascade="all, delete-orphan", order_by="WorkItem.assigned_at",
    )
    teams   = relationship("WorkTeam", back_populates="branch", cascade="all, delete-orphan")
    remarks = relationship("DocumentRemark", back_populates="branch", order_by="DocumentRemark.created_at")
    events  = relationship("WorkflowEvent", back_populates="branch")

    @property
    def department_name(self) -> Optional[str]:
        return self.department.name if self.department else None

    @property
    def target_user_name(self) -> Optional[str]:
        return self.target_user.full_name if self.target_user else None

    @property
    def label(self) -> str:
        """Human name for this workstream, e.g. 'Engineering HOD'."""
        if self.branch_type == BranchType.DEPARTMENT:
            return f"{self.department_name or 'Department'} HOD"
        if self.branch_type == BranchType.DIRECTOR:
            return "Director Review"
        if self.branch_type == BranchType.TSO:
            return f"TSO - {self.target_user_name}" if self.target_user_name else "TSO"
        return self.target_user_name or "Direct Assignment"

    @property
    def active_work_items(self) -> List["WorkItem"]:
        return [w for w in self.work_items if w.is_active]


# =========================================================
# WORK TEAM (grouping only - never a substitute for WorkItems)
# =========================================================

class WorkTeam(Base):
    """A named group of WorkItems inside one branch.  Purely a label: every
    member still owns an individual WorkItem with its own stage and progress."""

    __tablename__ = "work_teams"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(Integer, ForeignKey("document_branches.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    branch     = relationship("DocumentBranch", back_populates="teams")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    work_items = relationship("WorkItem", back_populates="team")


# =========================================================
# WORK ITEM (one person's work - the unit of traceability)
# =========================================================

class WorkItem(Base):
    """Exactly one person's work on exactly one branch.

    Every employee, HOD-as-worker or TSO who touches a document owns a
    WorkItem.  It carries their own stage, their own deadline, their own
    progress updates and their own attachments, and it is never merged with
    anybody else's."""

    __tablename__ = "work_items"
    __table_args__ = (
        Index("ix_workitem_assignee_active", "assigned_to_user_id", "is_active"),
        Index("ix_workitem_context_active", "assigned_to_context_membership_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("document_branches.id"), nullable=False, index=True)
    team_id = Column(Integer, ForeignKey("work_teams.id"), nullable=True)

    assigned_to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    assigned_to_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_by_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)

    instructions = Column(Text, nullable=True)
    deadline = Column(Date, nullable=True)

    stage = Column(SAEnum(WorkStage, name="work_stage"), default=WorkStage.ASSIGNED, nullable=False, index=True)
    requires_validation = Column(Boolean, default=False, nullable=False)

    # Which DS/HOD round of work this item belongs to on its branch.
    round_no = Column(Integer, default=1, nullable=False)
    # Set when DS or the HOD sends further work: links back to the earlier item.
    continues_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False, index=True)
    assigned_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    version = Column(Integer, default=1, nullable=False)

    document  = relationship("Document", back_populates="work_items")
    branch    = relationship("DocumentBranch", back_populates="work_items")
    team      = relationship("WorkTeam", back_populates="work_items")
    assignee  = relationship("User", foreign_keys=[assigned_to_user_id])
    assigner  = relationship("User", foreign_keys=[assigned_by_user_id])
    assignee_context = relationship("WorkContextMembership", foreign_keys=[assigned_to_context_membership_id])
    assigner_context = relationship("WorkContextMembership", foreign_keys=[assigned_by_context_membership_id])
    continues = relationship("WorkItem", remote_side=[id], foreign_keys=[continues_item_id])

    progress_updates = relationship(
        "ProgressUpdate", back_populates="work_item",
        cascade="all, delete-orphan", order_by="ProgressUpdate.created_at",
    )
    reviews = relationship(
        "WorkItemReview", back_populates="work_item",
        cascade="all, delete-orphan", order_by="WorkItemReview.created_at",
    )
    stage_changes = relationship(
        "WorkStageChange", back_populates="work_item",
        cascade="all, delete-orphan", order_by="WorkStageChange.created_at",
    )
    reminders = relationship("Reminder", back_populates="work_item")
    events    = relationship("WorkflowEvent", back_populates="work_item")

    @property
    def assignee_name(self) -> Optional[str]:
        return self.assignee.full_name if self.assignee else None

    @property
    def assigner_name(self) -> Optional[str]:
        return self.assigner.full_name if self.assigner else None

    @property
    def team_name(self) -> Optional[str]:
        return self.team.name if self.team else None

    @property
    def context_type(self) -> Optional[str]:
        if self.assignee_context:
            return self.assignee_context.context_type.value
        return None

    @property
    def department_name(self) -> Optional[str]:
        if self.assignee_context and self.assignee_context.department:
            return self.assignee_context.department.name
        return None

    @property
    def latest_progress(self) -> Optional["ProgressUpdate"]:
        return self.progress_updates[-1] if self.progress_updates else None

    @property
    def latest_progress_text(self) -> Optional[str]:
        latest = self.latest_progress
        return latest.description if latest else None

    @property
    def last_update_at(self) -> Optional[datetime]:
        latest = self.latest_progress
        return latest.created_at if latest else self.assigned_at

    @property
    def attachment_count(self) -> int:
        return sum(len(p.attachments) for p in self.progress_updates)

    @property
    def branch_label(self) -> Optional[str]:
        return self.branch.label if self.branch else None


# =========================================================
# PROGRESS UPDATE (free text, append-only, never a percentage)
# =========================================================

class ProgressUpdate(Base):
    """What the worker wrote.  Free text only.  Never numeric, never averaged,
    never rolled up."""

    __tablename__ = "progress_updates"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=False, index=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False, index=True)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    author_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)

    description = Column(Text, nullable=False)
    # The worker's stage at the moment they wrote this, for readable history.
    stage_at_time = Column(SAEnum(WorkStage, name="progress_stage"), nullable=True)

    created_at = Column(DateTime, default=datetime.now)

    document    = relationship("Document", back_populates="progress_updates")
    work_item   = relationship("WorkItem", back_populates="progress_updates")
    author      = relationship("User", foreign_keys=[author_user_id])
    author_context = relationship("WorkContextMembership", foreign_keys=[author_context_membership_id])
    attachments = relationship("Attachment", back_populates="progress_update")

    @property
    def author_name(self) -> Optional[str]:
        return self.author.full_name if self.author else None


# =========================================================
# WORK ITEM REVIEW (HOD validation of one person's work)
# =========================================================

class WorkItemReview(Base):
    """An HOD (or DS) accepting or returning one person's work.  Accepting
    never closes the document: only DS closes documents."""

    __tablename__ = "work_item_reviews"

    id = Column(Integer, primary_key=True, index=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False, index=True)
    reviewer_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reviewer_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)
    outcome = Column(SAEnum(ReviewOutcome, name="review_outcome"), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    work_item = relationship("WorkItem", back_populates="reviews")
    reviewer  = relationship("User", foreign_keys=[reviewer_user_id])

    @property
    def reviewer_name(self) -> Optional[str]:
        return self.reviewer.full_name if self.reviewer else None


# =========================================================
# WORK STAGE CHANGE (per-person stage audit)
# =========================================================

class WorkStageChange(Base):
    __tablename__ = "work_stage_changes"

    id = Column(Integer, primary_key=True, index=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=False, index=True)
    from_stage = Column(SAEnum(WorkStage, name="stage_change_from"), nullable=True)
    to_stage = Column(SAEnum(WorkStage, name="stage_change_to"), nullable=False)
    changed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    work_item  = relationship("WorkItem", back_populates="stage_changes")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])


# =========================================================
# ATTACHMENTS
# =========================================================

class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=True, index=True)
    progress_update_id = Column(Integer, ForeignKey("progress_updates.id"), nullable=True, index=True)
    uploaded_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_by_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)
    file_name = Column(String(255), nullable=False)
    storage_key = Column(String(500), nullable=False)
    file_type = Column(String(100), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    checksum = Column(String(64), nullable=True)
    attachment_type = Column(SAEnum(AttachmentType, name="att_type_enum"), default=AttachmentType.ORIGINAL, nullable=False)
    source_message_id = Column(Integer, ForeignKey("incoming_messages.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    document        = relationship("Document", back_populates="attachments")
    progress_update = relationship("ProgressUpdate", back_populates="attachments")
    uploaded_by     = relationship("User", foreign_keys=[uploaded_by_user_id])
    source_message  = relationship("IncomingMessage", back_populates="attachments")

    @property
    def uploaded_by_name(self) -> Optional[str]:
        return self.uploaded_by.full_name if self.uploaded_by else None

    @property
    def work_item_id(self) -> Optional[int]:
        return self.progress_update.work_item_id if self.progress_update else None


# =========================================================
# DIRECTOR REVIEW (repeatable; remark only, never a closure)
# =========================================================

class DirectorReview(Base):
    """One completed Director review.  A document may accumulate many.  Each
    is preserved separately; none replaces an earlier one, and none closes the
    document."""

    __tablename__ = "director_reviews"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("document_branches.id"), nullable=True, index=True)
    director_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    director_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)
    remark_text = Column(Text, nullable=False)
    review_no = Column(Integer, default=1, nullable=False)
    document_version = Column(Integer, default=1, nullable=False)
    requested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    document = relationship("Document", back_populates="director_reviews")
    branch   = relationship("DocumentBranch", foreign_keys=[branch_id])
    director = relationship("User", foreign_keys=[director_user_id])

    @property
    def director_name(self) -> Optional[str]:
        return self.director.full_name if self.director else None


# =========================================================
# DOCUMENT REMARKS (append-only; nothing is ever overwritten)
# =========================================================

class DocumentRemark(Base):
    __tablename__ = "document_remarks"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=False, index=True)
    # Null means the remark is about the document as a whole.
    branch_id = Column(Integer, ForeignKey("document_branches.id"), nullable=True, index=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=True)
    author_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    author_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)
    remark_type = Column(SAEnum(RemarkType, name="remark_type_enum"), nullable=False)
    remark_text = Column(Text, nullable=False)
    provenance = Column(String(50), default="MANUAL", nullable=False)
    created_at = Column(DateTime, default=datetime.now)

    document = relationship("Document", back_populates="remarks")
    branch   = relationship("DocumentBranch", back_populates="remarks")
    author   = relationship("User", foreign_keys=[author_user_id])
    author_context = relationship("WorkContextMembership", foreign_keys=[author_context_membership_id])

    @property
    def author_name(self) -> Optional[str]:
        return self.author.full_name if self.author else None

    @property
    def branch_label(self) -> Optional[str]:
        return self.branch.label if self.branch else None


# =========================================================
# OCR & EXTRACTION
# =========================================================

class DocumentOCR(Base):
    __tablename__ = "document_ocr"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), unique=True, nullable=False)
    extracted_text = Column(Text, nullable=True)
    ocr_status = Column(SAEnum(OCRStatus, name="ocr_record_status_enum"), default=OCRStatus.PENDING, nullable=False)
    ocr_engine = Column(String(100), default="PaddleOCR", nullable=False)
    confidence = Column(Float, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    document = relationship("Document", back_populates="ocr_record")


class DocumentExtractedField(Base):
    """OCR output is advisory.  `verified_value` is what the DS confirmed and
    is what the rest of the system trusts."""

    __tablename__ = "document_extracted_fields"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=False, index=True)
    field_name = Column(String(100), nullable=False)
    extracted_value = Column(Text, nullable=True)
    confidence = Column(Float, nullable=True)
    source_page = Column(Integer, default=1, nullable=True)
    source_text = Column(Text, nullable=True)
    verified_value = Column(Text, nullable=True)
    verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)

    document      = relationship("Document", back_populates="extracted_fields")
    verifier_user = relationship("User", foreign_keys=[verified_by])

    @property
    def effective_value(self) -> Optional[str]:
        return self.verified_value if self.verified_value is not None else self.extracted_value


class RoutingSuggestion(Base):
    """Advisory only.  Never routes anything by itself; the DS decides."""

    __tablename__ = "routing_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), unique=True, nullable=False)
    suggested_department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    suggested_employee_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    routing_confidence = Column(Float, nullable=False)
    routing_reason = Column(Text, nullable=False)
    routing_source = Column(SAEnum(RoutingSource, name="routing_source_enum"), default=RoutingSource.DOCUMENT_CONTENT, nullable=False)
    is_director_instruction = Column(Boolean, default=False)
    ranked_departments = Column(JSON, nullable=True)
    generated_at = Column(DateTime, default=datetime.now)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    document             = relationship("Document", back_populates="routing_suggestion")
    suggested_department = relationship("Department", foreign_keys=[suggested_department_id])
    suggested_employee   = relationship("User", foreign_keys=[suggested_employee_id])
    confirmer            = relationship("User", foreign_keys=[confirmed_by])

    @property
    def suggested_department_name(self) -> Optional[str]:
        return self.suggested_department.name if self.suggested_department else None

    @property
    def suggested_employee_name(self) -> Optional[str]:
        return self.suggested_employee.full_name if self.suggested_employee else None


# =========================================================
# REMINDERS (document- or work-item-scoped)
# =========================================================

class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=False, index=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=True, index=True)
    recipient_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recipient_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)
    reason = Column(SAEnum(ReminderReason, name="reminder_reason_enum"), nullable=False)
    message = Column(Text, nullable=True)
    due_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, default=datetime.now)
    is_read = Column(Boolean, default=False)
    deduplication_key = Column(String(200), unique=True, nullable=False, index=True)

    document       = relationship("Document", back_populates="reminders")
    work_item      = relationship("WorkItem", back_populates="reminders")
    recipient_user = relationship("User", foreign_keys=[recipient_user_id])


# =========================================================
# WORKFLOW EVENTS (the complete chronological document history)
# =========================================================

class WorkflowEvent(Base):
    """Immutable chronological history of everything that happened to a
    document.  Branch- and work-item-scoped events carry those ids so the
    history can be read per workstream or per person."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        Index("ix_event_doc_time", "document_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("document_branches.id"), nullable=True, index=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=True, index=True)

    event_type = Column(String(60), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    actor_context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True)
    actor_context_type = Column(String(30), nullable=True)

    summary = Column(String(300), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    document  = relationship("Document", back_populates="events")
    branch    = relationship("DocumentBranch", back_populates="events")
    work_item = relationship("WorkItem", back_populates="events")
    actor     = relationship("User", foreign_keys=[actor_user_id])

    @property
    def actor_name(self) -> str:
        return self.actor.full_name if self.actor else "System"

    @property
    def branch_label(self) -> Optional[str]:
        return self.branch.label if self.branch else None


# =========================================================
# ADMIN AUDIT (configuration changes only - never workflow)
# =========================================================

class AuditLog(Base):
    """Administrative and security actions.  Document workflow activity belongs
    in WorkflowEvent, not here."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", foreign_keys=[user_id], lazy="joined")


# =========================================================
# NOTIFICATIONS (context-aware)
# =========================================================

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Which hat this notification is for.  Null means "any context".
    context_membership_id = Column(Integer, ForeignKey("work_context_memberships.id"), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.doc_id"), nullable=True)
    branch_id = Column(Integer, ForeignKey("document_branches.id"), nullable=True)
    work_item_id = Column(Integer, ForeignKey("work_items.id"), nullable=True)
    event_id = Column(Integer, ForeignKey("workflow_events.id"), nullable=True)

    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])
    document = relationship("Document", back_populates="notifications")
    context_membership = relationship("WorkContextMembership", foreign_keys=[context_membership_id])


# =========================================================
# SYSTEM SETTINGS
# =========================================================

class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
