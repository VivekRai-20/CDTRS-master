"""Live API repository.

The only place in the frontend that knows about HTTP.  Method names follow the
workflow vocabulary, so a reader can map any call straight onto a rule in the
spec: route_document opens branches, assign_work creates one work item per
person, close_document is DS-only, and so on.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.client import APIClient, api_client
from api.endpoints import Endpoints
from models import (
    AttachmentModel,
    BranchModel,
    DepartmentModel,
    DirectorReviewModel,
    DocumentModel,
    ProgressModel,
    RemarkModel,
    UserModel,
    WorkItemModel,
    WorkflowEventModel,
)
from models.user import ContextMembershipModel
from repositories.base import BaseRepository
from models.notification import NotificationModel, ReminderModel

#: Calls where the server runs OCR / model inference (seconds).  The default
#: request timeout is far too short for a multi-page scan.
OCR_TIMEOUT = 600.0
#: Mail synchronisation and other slow server work (seconds).
LONG_TIMEOUT = 180.0


class APIRepository(BaseRepository):
    def __init__(self, client: Optional[APIClient] = None):
        # Share the module-level client: auth token and active work context are
        # session state, and AuthService sets them on that same instance.  A
        # private client here would silently send requests without the
        # X-Work-Context-Id header.
        self.client = client or api_client
        self._current_user: Optional[UserModel] = None
        self._contexts: List[ContextMembershipModel] = []

    # =========================================================
    # AUTHENTICATION & CONTEXT
    # =========================================================

    def authenticate(self, username: str, password: str) -> Optional[UserModel]:
        data = self.client.post(Endpoints.AUTH_LOGIN, json={"username": username, "password": password})
        if not data:
            return None
        self.client.set_auth_token(data.get("access_token"))
        self._current_user = UserModel.from_dict(data.get("user") or {})
        self._contexts = [ContextMembershipModel.from_dict(c) for c in (data.get("contexts") or [])]
        active = data.get("active_context")
        if active:
            self.client.set_active_context_id(active.get("id"))
        return self._current_user

    def get_current_user(self) -> Optional[UserModel]:
        if self._current_user is None:
            data = self.client.get(Endpoints.AUTH_ME)
            if data:
                self._current_user = UserModel.from_dict(data)
        return self._current_user

    def logout(self) -> None:
        self.client.clear_auth_token()
        self.client.set_active_context_id(None)
        self._current_user = None
        self._contexts = []

    def reset_password(self, username: str, old_password: str, new_password: str) -> bool:
        result = self.client.post(
            Endpoints.AUTH_CHANGE_PASSWORD,
            json={"current_password": old_password, "new_password": new_password},
        )
        return bool(result)

    def get_user_contexts(self) -> List[ContextMembershipModel]:
        """Every hat this user can wear."""
        data = self.client.get(Endpoints.AUTH_CONTEXTS) or []
        self._contexts = [ContextMembershipModel.from_dict(c) for c in data]
        return self._contexts

    def switch_context(self, context_membership_id: int) -> Optional[ContextMembershipModel]:
        """Switching context changes what the whole application shows and
        allows; every later request carries the new context header."""
        data = self.client.post(
            Endpoints.AUTH_SWITCH_CONTEXT, json={"context_membership_id": context_membership_id}
        )
        if not data:
            return None
        self.client.set_active_context_id(data.get("id"))
        return ContextMembershipModel.from_dict(data)

    # =========================================================
    # REFERENCE DATA
    # =========================================================

    def get_users(
        self,
        context_type: Optional[str] = None,
        department_id: Optional[int] = None,
    ) -> List[UserModel]:
        """Filter by context_type ('EMPLOYEE', 'HOD', 'TSO', 'DIRECTOR') to get
        the people who can actually receive that kind of work."""
        params: Dict[str, Any] = {}
        if context_type:
            params["context_type"] = context_type
        if department_id is not None:
            params["department_id"] = department_id
        data = self.client.get(Endpoints.USERS_LIST, params=params or None) or []
        return [UserModel.from_dict(u) for u in data]

    def get_department_employees(self, department_id: int) -> List[UserModel]:
        data = self.client.get(Endpoints.DEPARTMENT_EMPLOYEES(department_id)) or []
        return [UserModel.from_dict(u) for u in data]

    def get_departments(self) -> List[DepartmentModel]:
        data = self.client.get(Endpoints.DEPARTMENTS_LIST) or []
        return [DepartmentModel.from_dict(d) for d in data]

    def get_workflow_vocabulary(self) -> Dict[str, Any]:
        """Stage names and labels, so the UI never hardcodes them."""
        return self.client.get(Endpoints.WORKFLOW_VOCABULARY) or {}

    # =========================================================
    # INTAKE
    # =========================================================

    def get_intake_items(self) -> List[Dict[str, Any]]:
        return self.client.get(Endpoints.INTAKE_LIST) or []

    # Legacy alias used by the inbox page.
    def get_incoming_messages(self) -> List[Dict[str, Any]]:
        return self.get_intake_items()

    def sync_outlook(self) -> Dict[str, Any]:
        return self.client.post(Endpoints.INTAKE_SYNC_OUTLOOK, timeout=LONG_TIMEOUT) or {}

    def process_intake(self, intake_id: int, payload: Dict[str, Any]) -> Optional[DocumentModel]:
        # The server OCRs the e-mail attachment while registering it.
        data = self.client.post(Endpoints.INTAKE_PROCESS(intake_id), json=payload, timeout=OCR_TIMEOUT)
        return DocumentModel.from_dict(data) if data else None

    def manual_upload(self, fields: Dict[str, Any], file_path: str) -> Optional[DocumentModel]:
        data = self.client.upload(
            Endpoints.INTAKE_MANUAL_UPLOAD, file_path=file_path, extra_data=fields, timeout=OCR_TIMEOUT
        )
        return DocumentModel.from_dict(data) if data else None

    def analyze_intake_file(self, file_path: str, body: str = "") -> Dict[str, Any]:
        """OCR + routing suggestion for a file that is not registered yet."""
        extra = {"body": body} if body else None
        return self.client.upload(
            Endpoints.INTELLIGENCE_ANALYZE, file_path=file_path, extra_data=extra, timeout=OCR_TIMEOUT
        ) or {}

    def analyze_intake_text(self, text: str) -> Dict[str, Any]:
        """Field extraction + routing suggestion for text only (e-mail body)."""
        return self.client.post(
            Endpoints.INTELLIGENCE_ANALYZE_TEXT, json={"text": text}, timeout=LONG_TIMEOUT
        ) or {}

    # =========================================================
    # DOCUMENTS
    # =========================================================

    def get_documents(self, **_filters: Any) -> List[DocumentModel]:
        """Everything the active context is allowed to see."""
        data = self.client.get(Endpoints.DOCUMENTS_LIST) or []
        return [DocumentModel.from_dict(d) for d in data]

    def get_inbox(self) -> List[DocumentModel]:
        """Only what the active context has to act on now."""
        data = self.client.get(Endpoints.DOCUMENTS_INBOX) or []
        return [DocumentModel.from_dict(d) for d in data]

    def get_document(self, doc_id: int) -> Optional[DocumentModel]:
        data = self.client.get(Endpoints.DOCUMENT_DETAIL(doc_id))
        return DocumentModel.from_dict(data) if data else None

    def create_document(self, payload: Dict[str, Any]) -> Optional[DocumentModel]:
        data = self.client.post(Endpoints.DOCUMENT_CREATE, json=payload)
        return DocumentModel.from_dict(data) if data else None

    def update_document(self, doc_id: int, payload: Dict[str, Any]) -> Optional[DocumentModel]:
        """DS corrects document details, including anything OCR mis-read."""
        data = self.client.patch(Endpoints.DOCUMENT_UPDATE(doc_id), json=payload)
        return DocumentModel.from_dict(data) if data else None

    def register_document(self, doc_id: int) -> Optional[DocumentModel]:
        data = self.client.post(Endpoints.DOCUMENT_REGISTER(doc_id))
        return DocumentModel.from_dict(data) if data else None

    def close_document(
        self, doc_id: int, remark: Optional[str] = None,
        force: bool = False, expected_version: Optional[int] = None,
    ) -> Optional[DocumentModel]:
        """DS closure - the only way a document closes."""
        data = self.client.post(
            Endpoints.DOCUMENT_CLOSE(doc_id),
            json={"remark": remark, "force": force, "expected_version": expected_version},
        )
        return DocumentModel.from_dict(data) if data else None

    def reopen_document(self, doc_id: int, reason: Optional[str] = None) -> Optional[DocumentModel]:
        data = self.client.post(Endpoints.DOCUMENT_REOPEN(doc_id), json={"reason": reason})
        return DocumentModel.from_dict(data) if data else None

    # =========================================================
    # BRANCHES (routing)
    # =========================================================

    def get_document_branches(self, doc_id: int) -> List[BranchModel]:
        data = self.client.get(Endpoints.DOCUMENT_BRANCHES(doc_id)) or []
        return [BranchModel.from_dict(b) for b in data]

    def route_document(
        self, doc_id: int, branches: List[Dict[str, Any]], expected_version: Optional[int] = None
    ) -> List[BranchModel]:
        """Open one or several workstreams in a single action.

        Each entry is {branch_type, department_id?, target_user_id?,
        instructions?, requires_hod_validation?, deadline?}.  They all coexist:
        an HOD branch, a direct employee and TSO can be created together and
        then progress at completely different rates.
        """
        data = self.client.post(
            Endpoints.DOCUMENT_BRANCHES(doc_id),
            json={"branches": branches, "expected_version": expected_version},
        ) or []
        return [BranchModel.from_dict(b) for b in data]

    def assign_work(
        self,
        branch_id: int,
        assignee_user_ids: List[int],
        instructions: Optional[str] = None,
        deadline: Optional[str] = None,
        requires_validation: bool = False,
        team_name: Optional[str] = None,
    ) -> List[WorkItemModel]:
        """Assign people to a workstream.  One work item is created per person;
        a team name only groups them for display."""
        data = self.client.post(
            Endpoints.BRANCH_ASSIGN(branch_id),
            json={
                "assignee_user_ids": assignee_user_ids,
                "instructions": instructions,
                "deadline": deadline,
                "requires_validation": requires_validation,
                "team_name": team_name,
            },
        ) or []
        return [WorkItemModel.from_dict(w) for w in data]

    def add_branch_remark(self, branch_id: int, remark_text: str) -> Optional[RemarkModel]:
        data = self.client.post(Endpoints.BRANCH_REMARK(branch_id), json={"remark_text": remark_text})
        return RemarkModel.from_dict(data) if data else None

    def close_branch(self, branch_id: int, reason: Optional[str] = None) -> Optional[BranchModel]:
        data = self.client.post(Endpoints.BRANCH_CLOSE(branch_id), json={"reason": reason})
        return BranchModel.from_dict(data) if data else None

    # =========================================================
    # DIRECTOR REVIEW
    # =========================================================

    def start_director_review(self, branch_id: int) -> Optional[BranchModel]:
        data = self.client.post(Endpoints.DIRECTOR_REVIEW_START(branch_id))
        return BranchModel.from_dict(data) if data else None

    def submit_director_review(
        self, branch_id: int, remark_text: str, expected_version: Optional[int] = None
    ) -> Optional[DirectorReviewModel]:
        """The Director remarks and hands back to the DS.  There is no decision
        to make here: the Director does not close documents."""
        data = self.client.post(
            Endpoints.DIRECTOR_REVIEW_SUBMIT(branch_id),
            json={"remark_text": remark_text, "expected_version": expected_version},
        )
        return DirectorReviewModel.from_dict(data) if data else None

    def get_director_reviews(self, doc_id: int) -> List[DirectorReviewModel]:
        data = self.client.get(Endpoints.DIRECTOR_REVIEWS(doc_id)) or []
        return [DirectorReviewModel.from_dict(r) for r in data]

    # =========================================================
    # WORK ITEMS
    # =========================================================

    def get_my_work_items(self, include_finished: bool = False) -> List[WorkItemModel]:
        data = self.client.get(
            Endpoints.WORK_ITEMS_MINE, params={"include_finished": include_finished}
        ) or []
        return [WorkItemModel.from_dict(w) for w in data]

    def get_department_work_items(self) -> List[WorkItemModel]:
        """HOD view: every individual's work across their department."""
        data = self.client.get(Endpoints.WORK_ITEMS_DEPARTMENT) or []
        return [WorkItemModel.from_dict(w) for w in data]

    def get_document_work_items(self, doc_id: int) -> List[WorkItemModel]:
        data = self.client.get(Endpoints.DOCUMENT_WORK_ITEMS(doc_id)) or []
        return [WorkItemModel.from_dict(w) for w in data]

    def get_work_item(self, work_item_id: int) -> Optional[WorkItemModel]:
        data = self.client.get(Endpoints.WORK_ITEM_DETAIL(work_item_id))
        return WorkItemModel.from_dict(data) if data else None

    def set_work_stage(
        self, work_item_id: int, stage: str, note: Optional[str] = None
    ) -> Optional[WorkItemModel]:
        data = self.client.patch(
            Endpoints.WORK_ITEM_STAGE(work_item_id), json={"stage": stage, "note": note}
        )
        return WorkItemModel.from_dict(data) if data else None

    def submit_progress(
        self, work_item_id: int, description: str, new_stage: Optional[str] = None
    ) -> Optional[ProgressModel]:
        """Free-text progress.  Stored exactly as written - there is no
        percentage anywhere in this system."""
        data = self.client.post(
            Endpoints.WORK_ITEM_PROGRESS(work_item_id),
            json={"description": description, "new_stage": new_stage},
        )
        return ProgressModel.from_dict(data) if data else None

    def submit_progress_with_file(
        self,
        work_item_id: int,
        description: str,
        file_path: Optional[str] = None,
        new_stage: Optional[str] = None,
    ) -> Optional[ProgressModel]:
        """Progress plus a supporting document, so the file stays attached to
        the update it belongs to."""
        if not file_path:
            return self.submit_progress(work_item_id, description, new_stage)
        fields: Dict[str, Any] = {"description": description}
        if new_stage:
            fields["new_stage"] = new_stage
        data = self.client.upload(
            Endpoints.WORK_ITEM_PROGRESS_FILE(work_item_id), file_path=file_path, extra_data=fields,
            timeout=LONG_TIMEOUT,
        )
        return ProgressModel.from_dict(data) if data else None

    def submit_work(self, work_item_id: int, note: Optional[str] = None) -> Optional[WorkItemModel]:
        data = self.client.post(Endpoints.WORK_ITEM_SUBMIT(work_item_id), json={"note": note})
        return WorkItemModel.from_dict(data) if data else None

    def review_work_item(
        self, work_item_id: int, outcome: str, note: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """HOD accepts or returns ONE person's work.  Never closes the
        document."""
        return self.client.post(
            Endpoints.WORK_ITEM_REVIEW(work_item_id), json={"outcome": outcome, "note": note}
        )

    # =========================================================
    # ATTACHMENTS
    # =========================================================

    def get_attachments(self, doc_id: int) -> List[AttachmentModel]:
        data = self.client.get(Endpoints.ATTACHMENT_LIST(doc_id)) or []
        return [AttachmentModel.from_dict(a) for a in data]

    def upload_attachment(
        self,
        doc_id: int,
        file_path: str,
        attachment_type: str = "SUPPORTING_DOCUMENT",
        progress_update_id: Optional[int] = None,
    ) -> Optional[AttachmentModel]:
        fields: Dict[str, Any] = {"attachment_type": attachment_type}
        if progress_update_id:
            fields["progress_update_id"] = progress_update_id
        data = self.client.upload(
            Endpoints.ATTACHMENT_UPLOAD(doc_id), file_path=file_path, extra_data=fields, timeout=LONG_TIMEOUT
        )
        return AttachmentModel.from_dict(data) if data else None

    def download_attachment(self, attachment_id: int, dest_path: str) -> Optional[str]:
        return self.client.download(Endpoints.ATTACHMENT_DOWNLOAD(attachment_id), dest_path, timeout=LONG_TIMEOUT)

    # =========================================================
    # HISTORY & REMARKS
    # =========================================================

    def get_workflow_history(self, doc_id: int) -> List[WorkflowEventModel]:
        data = self.client.get(Endpoints.DOCUMENT_HISTORY(doc_id)) or []
        return [WorkflowEventModel.from_dict(e) for e in data]

    def get_all_audit_history(self, limit: int = 500) -> List[WorkflowEventModel]:
        data = self.client.get(Endpoints.HISTORY_ALL, params={"limit": limit}) or []
        return [WorkflowEventModel.from_dict(e) for e in data]

    def get_remarks(self, doc_id: int) -> List[RemarkModel]:
        data = self.client.get(Endpoints.DOCUMENT_REMARKS(doc_id)) or []
        return [RemarkModel.from_dict(r) for r in data]

    # =========================================================
    # OCR & ROUTING INTELLIGENCE (assistive)
    # =========================================================

    def get_ocr_result(self, doc_id: int) -> Dict[str, Any]:
        return self.client.get(Endpoints.OCR_GET(doc_id)) or {}

    def trigger_ocr(self, doc_id: int) -> Dict[str, Any]:
        return self.client.post(Endpoints.OCR_RUN(doc_id), timeout=OCR_TIMEOUT) or {}

    def verify_field(self, doc_id: int, field_name: str, verified_value: str) -> Dict[str, Any]:
        return self.client.post(
            Endpoints.OCR_VERIFY(doc_id),
            json={"field_name": field_name, "verified_value": verified_value},
        ) or {}

    def get_routing_suggestion(self, doc_id: int) -> Optional[Dict[str, Any]]:
        return self.client.get(Endpoints.ROUTING_SUGGESTION(doc_id))

    def analyze_routing(self, doc_id: int) -> Optional[Dict[str, Any]]:
        return self.client.post(
            Endpoints.ROUTING_ANALYZE(doc_id), json={"include_director_remark": True}
        )

    # =========================================================
    # NOTIFICATIONS & REMINDERS
    # =========================================================

    def get_notifications(
        self,
        unread_only: bool = False
    ) -> List[NotificationModel]:
        endpoint = (
            Endpoints.NOTIFICATIONS_UNREAD
            if unread_only
            else Endpoints.NOTIFICATIONS_LIST
        )

        data = self.client.get(endpoint) or []

        return [
            NotificationModel.from_dict(item)
            for item in data
        ]


    def mark_notification_read(
        self,
        notification_id: int
    ) -> bool:
        try:
            self.client.patch(
                Endpoints.NOTIFICATION_MARK_READ(notification_id)
            )
            return True
        except Exception:
            return False


    def mark_all_notifications_read(self) -> int:
        try:
            result = self.client.patch(
                Endpoints.NOTIFICATIONS_MARK_ALL_READ
            ) or {}

            return int(result.get("updated", 0))

        except Exception:
            return 0

    def get_reminders(self) -> List[ReminderModel]:
        data = self.client.get(Endpoints.REMINDERS_LIST) or []
        return [ReminderModel.from_dict(r) for r in data]


    def mark_reminder_read(self, reminder_id: int) -> bool:
        return bool(
            self.client.patch(
                Endpoints.REMINDER_MARK_READ(reminder_id)
            )
        )


    def check_reminders(self) -> Dict[str, Any]:
        return self.client.post(Endpoints.REMINDERS_CHECK) or {}

    def send_document_reminder(
        self,
        doc_id: int,
        work_item_id: Optional[int] = None,
        recipient_user_id: Optional[int] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:

        return self.client.post(
            Endpoints.DOCUMENT_REMIND(doc_id),
            json={
                "work_item_id": work_item_id,
                "recipient_user_id": recipient_user_id,
                "message": message,
            },
        ) or {}

    # =========================================================
    # DASHBOARD
    # =========================================================

    def get_dashboard_summary(self) -> Dict[str, Any]:
        return self.client.get(Endpoints.DASHBOARD) or {}

    # =========================================================
    # ADMINISTRATION
    # =========================================================

    def admin_get_users(self) -> List[UserModel]:
        data = self.client.get(Endpoints.ADMIN_USERS) or []
        return [UserModel.from_dict(u) for u in data]

    def admin_create_user(self, payload: Dict[str, Any]) -> Optional[UserModel]:
        data = self.client.post(Endpoints.ADMIN_USERS, json=payload)
        return UserModel.from_dict(data) if data else None

    def admin_update_user(self, user_id: int, payload: Dict[str, Any]) -> Optional[UserModel]:
        data = self.client.put(Endpoints.ADMIN_USER_DETAIL(user_id), json=payload)
        return UserModel.from_dict(data) if data else None

    def admin_reset_password(self, user_id: int, new_password: str) -> bool:
        return bool(self.client.post(
            Endpoints.ADMIN_USER_RESET_PASSWORD(user_id), json={"new_password": new_password}
        ))

    def admin_toggle_user(self, user_id: int) -> Optional[bool]:
        result = self.client.post(Endpoints.ADMIN_USER_TOGGLE(user_id))
        return result.get("is_active") if result else None

    def admin_get_user_contexts(self, user_id: int) -> List[ContextMembershipModel]:
        data = self.client.get(Endpoints.ADMIN_USER_CONTEXTS(user_id)) or []
        return [ContextMembershipModel.from_dict(c) for c in data]

    def admin_grant_context(
        self, user_id: int, context_type: str, department_id: Optional[int] = None
    ) -> Optional[ContextMembershipModel]:
        data = self.client.post(
            Endpoints.ADMIN_USER_CONTEXTS(user_id),
            json={"user_id": user_id, "context_type": context_type, "department_id": department_id},
        )
        return ContextMembershipModel.from_dict(data) if data else None

    def admin_revoke_context(self, user_id: int, context_id: int) -> bool:
        return bool(self.client.delete(Endpoints.ADMIN_USER_CONTEXT_DELETE(user_id, context_id)))

    def admin_get_tso(self) -> Optional[ContextMembershipModel]:
        data = self.client.get(Endpoints.ADMIN_TSO)
        return ContextMembershipModel.from_dict(data) if data else None

    def admin_set_tso(self, user_id: int) -> Optional[ContextMembershipModel]:
        data = self.client.post(Endpoints.ADMIN_ACTIVATE_TSO(user_id))
        return ContextMembershipModel.from_dict(data) if data else None

    def admin_get_departments(self) -> List[DepartmentModel]:
        data = self.client.get(Endpoints.ADMIN_DEPARTMENTS) or []
        return [DepartmentModel.from_dict(d) for d in data]

    def admin_create_department(
        self,
        name: str,
        code: Optional[str] = None,
        description: Optional[str] = None,
        keywords: Optional[str] = None,
    ) -> Optional[DepartmentModel]:
        data = self.client.post(
            Endpoints.ADMIN_DEPARTMENTS,
            json={"name": name, "code": code, "description": description, "keywords": keywords},
        )
        return DepartmentModel.from_dict(data) if data else None

    def admin_update_department(self, dept_id: int, payload: Dict[str, Any]) -> Optional[DepartmentModel]:
        data = self.client.put(Endpoints.ADMIN_DEPARTMENT_DETAIL(dept_id), json=payload)
        return DepartmentModel.from_dict(data) if data else None

    def admin_get_settings(self) -> Dict[str, Any]:
        return self.client.get(Endpoints.ADMIN_SETTINGS) or {}

    def admin_update_setting(
        self, key: str, value: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        return self.client.post(
            Endpoints.ADMIN_SETTINGS,
            json={"key": key, "value": value, "description": description},
        ) or {}

    def admin_get_audit_logs(self, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        return self.client.get(
            Endpoints.ADMIN_AUDIT_LOGS, params={"limit": limit, "offset": offset}
        ) or []
