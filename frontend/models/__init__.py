"""CDTRS frontend domain models."""

from models.enums import (
    BranchStageEnum,
    BranchTypeEnum,
    DocumentLifecycleEnum,
    IngestionModeEnum,
    OCRStatusEnum,
    PriorityEnum,
    RemarkTypeEnum,
    ReviewOutcomeEnum,
    RoleEnum,
    WorkStageEnum,
)

from models.user import UserModel, ContextMembershipModel
from models.department import DepartmentModel
from models.document import DocumentModel
from models.notification import NotificationModel

from models.workflow import (
    AttachmentModel,
    BranchModel,
    BranchSummaryModel,
    DirectorReviewModel,
    ProgressModel,
    RemarkModel,
    WorkItemModel,
    WorkReviewModel,
    WorkflowEventModel,
)

__all__ = [
    # Vocabulary
    "RoleEnum",
    "DocumentLifecycleEnum",
    "BranchTypeEnum",
    "BranchStageEnum",
    "WorkStageEnum",
    "ReviewOutcomeEnum",
    "RemarkTypeEnum",
    "PriorityEnum",
    "IngestionModeEnum",
    "OCRStatusEnum",
    # Identity
    "UserModel",
    "ContextMembershipModel",
    "DepartmentModel",
    # Document
    "DocumentModel",
    # Workflow
    "BranchModel",
    "BranchSummaryModel",
    "WorkItemModel",
    "ProgressModel",
    "WorkReviewModel",
    "RemarkModel",
    "DirectorReviewModel",
    "WorkflowEventModel",
    "AttachmentModel",
    "NotificationModel",
]
