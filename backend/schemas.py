"""CDTRS API contracts.

Response shapes follow the model: a document carries a lifecycle, branches
carry their own stages, and work items carry one person's stage, deadline and
progress.  Nothing here rolls several people's work into one figure.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional
from datetime import date, datetime

from models import (
    AttachmentType,
    BranchStage,
    BranchType,
    DocumentLifecycle,
    MessageProcessingStatus,
    OCRStatus,
    Priority,
    RemarkType,
    ReminderReason,
    ReviewOutcome,
    RoutingSource,
    SourceType,
    UserRole,
    WorkContextType,
    WorkStage,
)


# =========================================================
# DEPARTMENTS
# =========================================================

class DepartmentCreate(BaseModel):
    name: str
    code: Optional[str] = None


class DepartmentResponse(BaseModel):
    id: int
    name: str
    code: Optional[str] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# EMPLOYEE DIRECTORY
# =========================================================

class EmployeeCreate(BaseModel):
    employee_code: str
    full_name: str
    department_id: int
    designation: str
    email: Optional[str] = None
    outlook_email: Optional[str] = None
    gov_email: Optional[str] = None


class EmployeeResponse(BaseModel):
    id: int
    employee_code: str
    full_name: str
    department_id: int
    designation: str
    email: Optional[str] = None
    outlook_email: Optional[str] = None
    gov_email: Optional[str] = None
    user_id: Optional[int] = None
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# WORK CONTEXTS
# =========================================================

class WorkContextResponse(BaseModel):
    id: int
    user_id: int
    context_type: WorkContextType
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    label: str
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class WorkContextCreate(BaseModel):
    user_id: int
    context_type: WorkContextType
    department_id: Optional[int] = None


class WorkContextSwitchRequest(BaseModel):
    context_membership_id: int


# =========================================================
# USERS & AUTH
# =========================================================

class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: UserRole
    employee_code: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    outlook_email: Optional[str] = None
    gov_email: Optional[str] = None
    department_id: Optional[int] = None


class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    role: UserRole
    employee_code: Optional[str] = None
    designation: Optional[str] = None
    email: Optional[str] = None
    outlook_email: Optional[str] = None
    gov_email: Optional[str] = None
    department_id: Optional[int] = None
    department: Optional[str] = None
    is_active: bool = True
    contexts: List[WorkContextResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    contexts: List[WorkContextResponse] = Field(default_factory=list)
    active_context: Optional[WorkContextResponse] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    username: str
    new_password: str


class AdminPasswordResetRequest(BaseModel):
    new_password: str


# =========================================================
# INTAKE
# =========================================================

class IntakeCreate(BaseModel):
    source_type: SourceType = SourceType.MANUAL_UPLOAD
    external_message_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    subject: Optional[str] = None
    body_reference: Optional[str] = None
    received_at: Optional[datetime] = None


class IntakeProcessRequest(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    received_date: Optional[date] = None
    deadline: Optional[date] = None
    priority: Priority = Priority.MEDIUM
    source: Optional[str] = None
    sender_name: Optional[str] = None
    sender_reference: Optional[str] = None


class IntakeResponse(BaseModel):
    id: int
    source_type: SourceType
    external_message_id: Optional[str] = None
    sender_name: Optional[str] = None
    sender_email: Optional[str] = None
    subject: Optional[str] = None
    received_at: datetime
    body_reference: Optional[str] = None
    has_attachments: bool = False
    processing_status: MessageProcessingStatus

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# ATTACHMENTS
# =========================================================

class AttachmentResponse(BaseModel):
    id: int
    document_id: Optional[int] = None
    progress_update_id: Optional[int] = None
    work_item_id: Optional[int] = None
    file_name: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    attachment_type: AttachmentType
    uploaded_by_user_id: int
    uploaded_by_name: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# PROGRESS (free text - never a percentage)
# =========================================================

class ProgressCreate(BaseModel):
    """What the worker wrote.  `description` is free text and is stored as
    written."""
    description: str
    new_stage: Optional[WorkStage] = None


class ProgressResponse(BaseModel):
    id: int
    document_id: int
    work_item_id: int
    author_user_id: int
    author_name: Optional[str] = None
    description: str
    stage_at_time: Optional[WorkStage] = None
    created_at: datetime
    attachments: List[AttachmentResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# WORK ITEM REVIEW / STAGE HISTORY
# =========================================================

class WorkReviewResponse(BaseModel):
    id: int
    work_item_id: int
    reviewer_user_id: int
    reviewer_name: Optional[str] = None
    outcome: ReviewOutcome
    note: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkReviewRequest(BaseModel):
    outcome: ReviewOutcome
    note: Optional[str] = None


class StageChangeResponse(BaseModel):
    id: int
    work_item_id: int
    from_stage: Optional[WorkStage] = None
    to_stage: WorkStage
    changed_by_user_id: int
    note: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# WORK ITEMS (one person's work)
# =========================================================

class WorkItemResponse(BaseModel):
    id: int
    document_id: int
    branch_id: int
    branch_label: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None

    assigned_to_user_id: int
    assignee_name: Optional[str] = None
    assigned_to_context_membership_id: Optional[int] = None
    context_type: Optional[str] = None
    department_name: Optional[str] = None
    assigned_by_user_id: int
    assigner_name: Optional[str] = None

    instructions: Optional[str] = None
    deadline: Optional[date] = None
    deadline_state: str = "none"

    stage: WorkStage
    stage_label: str = ""
    requires_validation: bool = False
    round_no: int = 1
    is_active: bool = True

    latest_progress_text: Optional[str] = None
    last_update_at: Optional[datetime] = None
    attachment_count: int = 0

    assigned_at: datetime
    started_at: Optional[datetime] = None
    submitted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    version: int = 1

    progress_updates: List[ProgressResponse] = Field(default_factory=list)
    reviews: List[WorkReviewResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class WorkStageUpdateRequest(BaseModel):
    stage: WorkStage
    note: Optional[str] = None


class WorkSubmitRequest(BaseModel):
    note: Optional[str] = None


# =========================================================
# BRANCHES (independent workstreams)
# =========================================================

class BranchCreate(BaseModel):
    """One routing target.  Several of these may be sent at once and they all
    become independent, coexisting workstreams."""
    branch_type: BranchType
    department_id: Optional[int] = None
    target_user_id: Optional[int] = None
    instructions: Optional[str] = None
    requires_hod_validation: bool = False
    deadline: Optional[date] = None
    # Optional: DS may pre-assign people inside a DEPARTMENT branch.
    assignee_user_ids: List[int] = Field(default_factory=list)
    team_name: Optional[str] = None


class RouteRequest(BaseModel):
    branches: List[BranchCreate]
    expected_version: Optional[int] = None

class SendToDirectorRequest(BaseModel):
    expected_version: Optional[int] = None
    
class BranchResponse(BaseModel):
    id: int
    document_id: int
    branch_type: BranchType
    label: str
    stage: BranchStage
    stage_label: str = ""

    department_id: Optional[int] = None
    department_name: Optional[str] = None
    target_user_id: Optional[int] = None
    target_user_name: Optional[str] = None
    target_context_membership_id: Optional[int] = None

    opened_by_user_id: int
    instructions: Optional[str] = None
    requires_hod_validation: bool = False
    deadline: Optional[date] = None
    deadline_state: str = "none"
    round_no: int = 1

    is_active: bool = True
    opened_at: datetime
    closed_at: Optional[datetime] = None
    version: int = 1

    work_items: List[WorkItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class BranchAssignRequest(BaseModel):
    """DS or HOD assigns people to a workstream.  One work item is created per
    person; a team name only groups them."""
    assignee_user_ids: List[int]
    instructions: Optional[str] = None
    deadline: Optional[date] = None
    requires_validation: bool = False
    team_name: Optional[str] = None


class BranchRemarkRequest(BaseModel):
    remark_text: str


class BranchCloseRequest(BaseModel):
    reason: Optional[str] = None


# =========================================================
# REMARKS / DIRECTOR REVIEWS
# =========================================================

class RemarkResponse(BaseModel):
    id: int
    document_id: int
    branch_id: Optional[int] = None
    branch_label: Optional[str] = None
    work_item_id: Optional[int] = None
    author_user_id: int
    author_name: Optional[str] = None
    remark_type: RemarkType
    remark_text: str
    provenance: str = "MANUAL"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DirectorReviewRequest(BaseModel):
    """The Director remarks and hands back to DS.  There is deliberately no
    decision field: the Director does not close documents."""
    remark_text: str
    expected_version: Optional[int] = None


class DirectorReviewResponse(BaseModel):
    id: int
    document_id: int
    branch_id: Optional[int] = None
    director_user_id: int
    director_name: Optional[str] = None
    remark_text: str
    review_no: int = 1
    requested_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# WORKFLOW HISTORY
# =========================================================

class WorkflowEventResponse(BaseModel):
    id: int
    document_id: int
    branch_id: Optional[int] = None
    branch_label: Optional[str] = None
    work_item_id: Optional[int] = None
    event_type: str
    actor_user_id: Optional[int] = None
    actor_name: str = "System"
    actor_context_type: Optional[str] = None
    summary: str
    details: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# DOCUMENTS
# =========================================================

class DocumentCreate(BaseModel):
    title: str
    subject: Optional[str] = None
    description: Optional[str] = None
    received_date: date
    deadline: Optional[date] = None
    source: Optional[str] = None
    sender_name: Optional[str] = None
    sender_reference: Optional[str] = None
    mode: str = "MANUAL_UPLOAD"
    priority: Priority = Priority.MEDIUM
    source_message_id: Optional[int] = None


class DocumentUpdate(BaseModel):
    """DS corrects extracted or entered metadata."""
    title: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    received_date: Optional[date] = None
    deadline: Optional[date] = None
    source: Optional[str] = None
    sender_name: Optional[str] = None
    sender_reference: Optional[str] = None
    priority: Optional[Priority] = None
    expected_version: Optional[int] = None


class BranchSummary(BaseModel):
    """Compact per-branch state for list views.  Kept as a LIST so a document
    with branches at different stages is displayed as such, never averaged
    into one status."""
    branch_id: int
    branch_type: BranchType
    label: str
    stage: BranchStage
    stage_label: str
    is_active: bool
    people: List[str] = Field(default_factory=list)
    open_items: int = 0
    total_items: int = 0


class DocumentListResponse(BaseModel):
    doc_id: int
    reference_no: str
    title: str
    subject: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None
    sender_name: Optional[str] = None
    priority: Priority
    lifecycle: DocumentLifecycle
    lifecycle_label: str = ""
    received_date: date
    deadline: Optional[date] = None
    deadline_state: str = "none"
    ocr_status: OCRStatus
    version: int

    branch_summaries: List[BranchSummary] = Field(default_factory=list)
    people_involved: List[str] = Field(default_factory=list)
    active_branch_count: int = 0
    open_work_item_count: int = 0
    latest_director_remark: Optional[str] = None
    has_open_director_review: bool = False

    # Only populated on "my tasks" style listings.
    my_work_items: List[WorkItemResponse] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime
    closed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DocumentDetailResponse(DocumentListResponse):
    mode: str
    created_by: int
    source_message_id: Optional[int] = None
    registered_at: Optional[datetime] = None
    closed_by_user_id: Optional[int] = None
    closure_remark: Optional[str] = None

    branches: List[BranchResponse] = Field(default_factory=list)
    remarks: List[RemarkResponse] = Field(default_factory=list)
    director_reviews: List[DirectorReviewResponse] = Field(default_factory=list)
    attachments: List[AttachmentResponse] = Field(default_factory=list)
    history: List[WorkflowEventResponse] = Field(default_factory=list)

    suggested_department_id: Optional[int] = None
    suggested_department_name: Optional[str] = None
    suggested_employee_id: Optional[int] = None
    suggested_employee_name: Optional[str] = None
    routing_confidence: Optional[float] = None
    routing_reason: Optional[str] = None
    is_director_instruction: bool = False
    ranked_departments: Optional[List[Dict[str, Any]]] = None


class CloseRequest(BaseModel):
    remark: Optional[str] = None
    force: bool = False
    expected_version: Optional[int] = None


class ReopenRequest(BaseModel):
    reason: Optional[str] = None


# =========================================================
# OCR & EXTRACTION
# =========================================================

class ExtractedFieldResponse(BaseModel):
    id: int
    document_id: int
    field_name: str
    extracted_value: Optional[str] = None
    verified_value: Optional[str] = None
    effective_value: Optional[str] = None
    confidence: Optional[float] = None
    source_page: Optional[int] = 1
    verified_by: Optional[int] = None
    verified_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class FieldVerifyRequest(BaseModel):
    field_name: str
    verified_value: str


class OCRResponse(BaseModel):
    id: Optional[int] = None
    document_id: int
    extracted_text: Optional[str] = None
    ocr_status: OCRStatus
    ocr_engine: Optional[str] = None
    confidence: Optional[float] = None
    processed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    fields: List[ExtractedFieldResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RoutingSuggestionResponse(BaseModel):
    id: int
    document_id: int
    suggested_department_id: Optional[int] = None
    suggested_department_name: Optional[str] = None
    suggested_employee_id: Optional[int] = None
    suggested_employee_name: Optional[str] = None
    routing_confidence: float
    routing_reason: str
    routing_source: RoutingSource
    is_director_instruction: bool = False
    ranked_departments: Optional[List[Dict[str, Any]]] = None
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoutingAnalyzeRequest(BaseModel):
    include_director_remark: bool = True


# =========================================================
# NOTIFICATIONS & REMINDERS
# =========================================================

class NotificationResponse(BaseModel):
    id: int
    user_id: int
    context_membership_id: Optional[int] = None
    document_id: Optional[int] = None
    branch_id: Optional[int] = None
    work_item_id: Optional[int] = None
    title: str
    message: str
    is_read: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReminderResponse(BaseModel):
    id: int
    document_id: int
    work_item_id: Optional[int] = None
    recipient_user_id: int
    reason: ReminderReason
    message: Optional[str] = None
    due_at: Optional[datetime] = None
    sent_at: datetime
    is_read: bool = False

    model_config = ConfigDict(from_attributes=True)


class ReminderCheckResponse(BaseModel):
    generated: int
    reminders: List[ReminderResponse] = Field(default_factory=list)


class ReminderSendRequest(BaseModel):
    work_item_id: Optional[int] = None
    recipient_user_id: Optional[int] = None
    message: Optional[str] = None


class ReminderSendResponse(BaseModel):
    sent: int
    channel: str = "in-app"
    detail: Optional[str] = None


class OutlookSyncResponse(BaseModel):
    """Result of pulling the DS mailbox."""
    status: str
    synced_count: int = 0
    ignored_duplicates: int = 0
    message: Optional[str] = None
    details: List[Dict[str, Any]] = Field(default_factory=list)


# =========================================================
# DASHBOARD
# =========================================================

class DashboardCard(BaseModel):
    key: str
    label: str
    value: int


class DashboardResponse(BaseModel):
    context_type: Optional[str] = None
    department: Optional[str] = None
    cards: List[DashboardCard] = Field(default_factory=list)
    documents: List[DocumentListResponse] = Field(default_factory=list)


# =========================================================
# ADMIN
# =========================================================

class AdminUserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: UserRole
    email: Optional[str] = None
    outlook_email: Optional[str] = None
    gov_email: Optional[str] = None
    employee_code: Optional[str] = None
    designation: Optional[str] = None
    department_id: Optional[int] = None


class AdminUserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    email: Optional[str] = None
    outlook_email: Optional[str] = None
    gov_email: Optional[str] = None
    employee_code: Optional[str] = None
    designation: Optional[str] = None
    department_id: Optional[int] = None
    is_active: Optional[bool] = None


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    description: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SystemSettingUpdate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None


# =========================================================
# LIVE EVENTS (websocket)
# =========================================================

class LiveEventMessage(BaseModel):
    event: str
    document_id: Optional[int] = None
    branch_id: Optional[int] = None
    work_item_id: Optional[int] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)
