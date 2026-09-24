"""Frontend enums.

These mirror the backend vocabulary exactly.  Three distinct concepts, kept
apart on purpose:

    DocumentLifecycleEnum   the state of the DOCUMENT
    BranchStageEnum         the state of ONE workstream
    WorkStageEnum           the state of ONE person's work

Confusing these is what the redesign set out to fix, so nothing here maps one
onto another.
"""

from enum import Enum


class RoleEnum(str, Enum):
    """A work context type.  This, not a nominal job title, decides what a
    user sees and may do."""

    ADMIN = "ADMIN"
    DS = "DS"
    DIRECTOR = "DIRECTOR"
    HOD = "HOD"
    EMPLOYEE = "EMPLOYEE"
    TSO = "TSO"

    @classmethod
    def normalize(cls, value) -> str:
        if value is None:
            return ""
        text = str(value).strip().upper()
        if text.startswith("ROLEENUM.") or text.startswith("WORKCONTEXTTYPE."):
            text = text.split(".", 1)[1]
        aliases = {
            "ADMINISTRATOR": cls.ADMIN.value,
            "MASTER": cls.ADMIN.value,
            "DIRECTOR_SECRETARY": cls.DS.value,
            "DIRECTOR SECRETARY": cls.DS.value,
            "SECRETARY": cls.DS.value,
            "HEAD OF DEPARTMENT": cls.HOD.value,
            "HEAD_OF_DEPARTMENT": cls.HOD.value,
            "TECHNICAL SUPPORT OFFICER": cls.TSO.value,
            "TECHNICAL_SUPPORT_OFFICER": cls.TSO.value,
        }
        return aliases.get(text, text)


class DocumentLifecycleEnum(str, Enum):
    """The DOCUMENT's own state.  It never describes the work inside."""

    RECEIVED = "RECEIVED"
    REGISTERED = "REGISTERED"
    IN_REVIEW = "IN_REVIEW"
    IN_WORK = "IN_WORK"
    WITH_DS = "WITH_DS"
    CLOSED = "CLOSED"

    @classmethod
    def label(cls, value) -> str:
        return {
            "RECEIVED": "Received",
            "REGISTERED": "Registered",
            "IN_REVIEW": "Under Director Review",
            "IN_WORK": "In Work",
            "WITH_DS": "With DS",
            "CLOSED": "Closed",
        }.get(str(value or "").upper(), str(value or ""))


class BranchTypeEnum(str, Enum):
    """The kind of workstream a branch is."""

    DIRECTOR = "DIRECTOR"
    DEPARTMENT = "DEPARTMENT"
    EMPLOYEE = "EMPLOYEE"
    TSO = "TSO"

    @classmethod
    def label(cls, value) -> str:
        return {
            "DIRECTOR": "Director Review",
            "DEPARTMENT": "Department / HOD",
            "EMPLOYEE": "Direct Employee",
            "TSO": "TSO",
        }.get(str(value or "").upper(), str(value or ""))


class BranchStageEnum(str, Enum):
    """The stage of ONE branch.  Branches of the same document routinely sit
    at different values of this at the same time."""

    # Director branch
    REVIEW_REQUESTED = "REVIEW_REQUESTED"
    UNDER_DIRECTOR_REVIEW = "UNDER_DIRECTOR_REVIEW"
    REMARK_ADDED = "REMARK_ADDED"
    RETURNED_TO_DS = "RETURNED_TO_DS"
    # Department / HOD branch
    HOD_REVIEW = "HOD_REVIEW"
    EMPLOYEE_ASSIGNMENT = "EMPLOYEE_ASSIGNMENT"
    EMPLOYEE_WORK = "EMPLOYEE_WORK"
    HOD_VALIDATION = "HOD_VALIDATION"
    # Direct employee / TSO branch
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    SUBMITTED = "SUBMITTED"
    # Shared
    FURTHER_WORK = "FURTHER_WORK"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class WorkStageEnum(str, Enum):
    """The stage of ONE person's work item."""

    ASSIGNED = "ASSIGNED"
    UNDER_WORK = "UNDER_WORK"
    WAITING = "WAITING"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    RETURNED = "RETURNED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

    @classmethod
    def label(cls, value) -> str:
        return {
            "ASSIGNED": "Assigned",
            "UNDER_WORK": "Under Work",
            "WAITING": "Waiting",
            "SUBMITTED": "Submitted",
            "UNDER_REVIEW": "Under Review",
            "RETURNED": "Returned",
            "COMPLETED": "Completed",
            "CANCELLED": "Cancelled",
        }.get(str(value or "").upper(), str(value or ""))

    @classmethod
    def worker_selectable(cls):
        """Stages a worker may set on their own work.  Finishing goes through
        Submit, and only an HOD/DS can return or cancel work."""
        return [cls.UNDER_WORK, cls.WAITING, cls.SUBMITTED]


class ReviewOutcomeEnum(str, Enum):
    ACCEPTED = "ACCEPTED"
    RETURNED = "RETURNED"


class RemarkTypeEnum(str, Enum):
    DIRECTOR = "DIRECTOR"
    HOD = "HOD"
    DS = "DS"
    TSO = "TSO"
    EMPLOYEE = "EMPLOYEE"
    OTHER = "OTHER"


class PriorityEnum(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

    @classmethod
    def normalize(cls, value) -> str:
        if value is None:
            return cls.MEDIUM.value
        text = str(value).strip().upper()
        aliases = {
            "URGENT": cls.CRITICAL.value,
            "RED": cls.CRITICAL.value,
            "NORMAL": cls.MEDIUM.value,
            "ORANGE": cls.MEDIUM.value,
            "YELLOW": cls.MEDIUM.value,
            "GREEN": cls.LOW.value,
        }
        return aliases.get(text, text)

    @classmethod
    def label(cls, value) -> str:
        return cls.normalize(value).title()


class IngestionModeEnum(str, Enum):
    GOVERNMENT_MAIL = "GOVERNMENT_MAIL"
    OUTLOOK = "OUTLOOK"
    MANUAL_UPLOAD = "MANUAL_UPLOAD"
    OTHER_APPROVED_SOURCE = "OTHER_APPROVED_SOURCE"

    @classmethod
    def normalize(cls, value) -> str:
        if value is None:
            return ""
        text = str(value).strip().upper().replace(" ", "_")
        aliases = {
            "GOVT_MAIL": cls.GOVERNMENT_MAIL.value,
            "OUTLOOK_MAIL": cls.OUTLOOK.value,
            "OUTLOOK_EMAIL": cls.OUTLOOK.value,
            "MANUAL": cls.MANUAL_UPLOAD.value,
        }
        return aliases.get(text, text)

    @classmethod
    def label(cls, value) -> str:
        return {
            "GOVERNMENT_MAIL": "Government Mail",
            "OUTLOOK": "Outlook",
            "MANUAL_UPLOAD": "Manual Upload",
            "OTHER_APPROVED_SOURCE": "Other Approved Source",
        }.get(cls.normalize(value), str(value or ""))


class OCRStatusEnum(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
