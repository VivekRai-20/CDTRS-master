"""Repository protocol.

Defines the data operations the UI is allowed to perform.  The vocabulary is
the workflow vocabulary: branches are opened, work items are assigned to one
person each, progress is free text, and only the DS closes a document.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from models import (
    AttachmentModel,
    BranchModel,
    DepartmentModel,
    DirectorReviewModel,
    DocumentModel,
    NotificationModel,
    ProgressModel,
    RemarkModel,
    UserModel,
    WorkItemModel,
    WorkflowEventModel,
)
from models.user import ContextMembershipModel


class BaseRepository(ABC):

    # =========================================================
    # AUTHENTICATION & WORK CONTEXT
    # =========================================================

    @abstractmethod
    def authenticate(self, username: str, password: str) -> Optional[UserModel]:
        """Sign in and establish the session."""

    @abstractmethod
    def get_current_user(self) -> Optional[UserModel]:
        """The signed-in account."""

    @abstractmethod
    def logout(self) -> None:
        """Clear the session and the active context."""

    @abstractmethod
    def get_user_contexts(self) -> List[ContextMembershipModel]:
        """Every hat this user can wear, e.g. HOD-Engineering plus
        Employee-Product plus TSO."""

    @abstractmethod
    def switch_context(self, context_membership_id: int) -> Optional[ContextMembershipModel]:
        """Change the active hat.  Everything the user sees and may do changes
        with it."""

    # =========================================================
    # REFERENCE DATA
    # =========================================================

    @abstractmethod
    def get_users(
        self, context_type: Optional[str] = None, department_id: Optional[int] = None
    ) -> List[UserModel]:
        """People, filtered by the work context they hold."""

    @abstractmethod
    def get_departments(self) -> List[DepartmentModel]:
        """Active departments."""

    # =========================================================
    # DOCUMENTS
    # =========================================================

    @abstractmethod
    def get_documents(self, **filters: Any) -> List[DocumentModel]:
        """Everything the active context may open."""

    @abstractmethod
    def get_inbox(self) -> List[DocumentModel]:
        """Only what the active context must act on now."""

    @abstractmethod
    def get_document(self, doc_id: int) -> Optional[DocumentModel]:
        """One document with its branches, work items, remarks and history."""

    @abstractmethod
    def create_document(self, payload: Dict[str, Any]) -> Optional[DocumentModel]:
        """Register a new document (DS)."""

    @abstractmethod
    def update_document(self, doc_id: int, payload: Dict[str, Any]) -> Optional[DocumentModel]:
        """Correct document metadata, including anything OCR mis-read (DS)."""

    @abstractmethod
    def close_document(
        self, doc_id: int, remark: Optional[str] = None,
        force: bool = False, expected_version: Optional[int] = None,
    ) -> Optional[DocumentModel]:
        """DS closure.  The only way a document closes."""

    # =========================================================
    # BRANCHES (independent workstreams)
    # =========================================================

    @abstractmethod
    def get_document_branches(self, doc_id: int) -> List[BranchModel]:
        """Every workstream on the document, each with its own stage."""

    @abstractmethod
    def route_document(
        self, doc_id: int, branches: List[Dict[str, Any]], expected_version: Optional[int] = None
    ) -> List[BranchModel]:
        """Open one or several workstreams at once.  They coexist."""

    @abstractmethod
    def assign_work(
        self,
        branch_id: int,
        assignee_user_ids: List[int],
        instructions: Optional[str] = None,
        deadline: Optional[str] = None,
        requires_validation: bool = False,
        team_name: Optional[str] = None,
    ) -> List[WorkItemModel]:
        """One work item per person.  A team name groups them, never merges
        them."""

    @abstractmethod
    def add_branch_remark(self, branch_id: int, remark_text: str) -> Optional[RemarkModel]:
        """Append a remark to a workstream.  Remarks are never overwritten."""

    @abstractmethod
    def close_branch(self, branch_id: int, reason: Optional[str] = None) -> Optional[BranchModel]:
        """End one workstream; the document and other branches carry on."""

    # =========================================================
    # DIRECTOR REVIEW
    # =========================================================

    @abstractmethod
    def submit_director_review(
        self, branch_id: int, remark_text: str, expected_version: Optional[int] = None
    ) -> Optional[DirectorReviewModel]:
        """Record a Director remark and hand back to the DS."""

    @abstractmethod
    def get_director_reviews(self, doc_id: int) -> List[DirectorReviewModel]:
        """Every review ever made on the document.  None replaces another."""

    # =========================================================
    # WORK ITEMS (one person's work)
    # =========================================================

    @abstractmethod
    def get_my_work_items(self, include_finished: bool = False) -> List[WorkItemModel]:
        """The caller's own tasks in the active context."""

    @abstractmethod
    def get_department_work_items(self) -> List[WorkItemModel]:
        """HOD view: every individual's work across their department."""

    @abstractmethod
    def get_document_work_items(self, doc_id: int) -> List[WorkItemModel]:
        """Everyone's work on one document."""

    @abstractmethod
    def set_work_stage(
        self, work_item_id: int, stage: str, note: Optional[str] = None
    ) -> Optional[WorkItemModel]:
        """The worker moves their own work through its stages."""

    @abstractmethod
    def submit_progress(
        self, work_item_id: int, description: str, new_stage: Optional[str] = None
    ) -> Optional[ProgressModel]:
        """Free-text progress.  Never a percentage."""

    @abstractmethod
    def submit_work(self, work_item_id: int, note: Optional[str] = None) -> Optional[WorkItemModel]:
        """Hand the work in for validation or completion."""

    @abstractmethod
    def review_work_item(
        self, work_item_id: int, outcome: str, note: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """HOD accepts or returns ONE person's work."""

    # =========================================================
    # ATTACHMENTS, HISTORY, NOTIFICATIONS
    # =========================================================

    @abstractmethod
    def get_attachments(self, doc_id: int) -> List[AttachmentModel]:
        """Files on the document, including those attached to progress."""

    @abstractmethod
    def upload_attachment(
        self, doc_id: int, file_path: str,
        attachment_type: str = "SUPPORTING_DOCUMENT",
        progress_update_id: Optional[int] = None,
    ) -> Optional[AttachmentModel]:
        """Attach a supporting document, optionally to a specific update."""

    @abstractmethod
    def get_workflow_history(self, doc_id: int) -> List[WorkflowEventModel]:
        """The document's complete chronological history."""

    @abstractmethod
    def get_notifications(self, unread_only: bool = False) -> List[NotificationModel]:
        """Notifications for the active context."""

    @abstractmethod
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Counters that mean something for the active context."""
