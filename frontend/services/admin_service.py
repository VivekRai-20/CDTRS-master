"""Administration: accounts, work contexts, departments, TSO designation,
mail/notification settings and the configuration audit trail.

Administrative activity is audited separately from document workflow.  A
document's own history stays in the document; this audit covers configuration
changes only.
"""

from typing import Any, Dict, List, Optional

from models import DepartmentModel, UserModel
from models.user import ContextMembershipModel
from repositories.provider import get_repository


class AdminService:

    # =========================================================
    # USERS
    # =========================================================

    def get_users(self) -> List[UserModel]:
        return get_repository().admin_get_users()

    def create_user(self, payload: Dict[str, Any]) -> Optional[UserModel]:
        return get_repository().admin_create_user(payload)

    def update_user(self, user_id: int, payload: Dict[str, Any]) -> Optional[UserModel]:
        return get_repository().admin_update_user(user_id, payload)

    def reset_password(self, user_id: int, new_password: str) -> bool:
        return get_repository().admin_reset_password(user_id, new_password)

    def toggle_active(self, user_id: int) -> Optional[bool]:
        return get_repository().admin_toggle_user(user_id)

    # =========================================================
    # WORK CONTEXTS (a user may hold several)
    # =========================================================

    def get_user_contexts(self, user_id: int) -> List[ContextMembershipModel]:
        return get_repository().admin_get_user_contexts(user_id)

    def grant_context(
        self, user_id: int, context_type: str, department_id: Optional[int] = None
    ) -> Optional[ContextMembershipModel]:
        """Give a user another hat, e.g. HOD-Engineering on top of
        Employee-Product.  HOD and Employee contexts require a department."""
        return get_repository().admin_grant_context(user_id, context_type, department_id)

    def revoke_context(self, user_id: int, context_id: int) -> bool:
        """Refused by the backend while that context still has open work, so
        nobody's live assignments are orphaned."""
        return get_repository().admin_revoke_context(user_id, context_id)

    # =========================================================
    # TSO (exactly one at a time, organisation-wide)
    # =========================================================

    def get_tso(self) -> Optional[ContextMembershipModel]:
        return get_repository().admin_get_tso()

    def set_tso(self, user_id: int) -> Optional[ContextMembershipModel]:
        """Designating a new TSO stands the previous one down."""
        return get_repository().admin_set_tso(user_id)

    # =========================================================
    # DEPARTMENTS
    # =========================================================

    def get_departments(self) -> List[DepartmentModel]:
        return get_repository().admin_get_departments()

    def create_department(
        self,
        name: str,
        code: Optional[str] = None,
        description: Optional[str] = None,
        keywords: Optional[str] = None,
    ) -> Optional[DepartmentModel]:
        return get_repository().admin_create_department(name, code, description, keywords)

    def update_department(self, dept_id: int, payload: Dict[str, Any]) -> Optional[DepartmentModel]:
        return get_repository().admin_update_department(dept_id, payload)

    # =========================================================
    # SETTINGS (mail, notifications, reminders, templates)
    # =========================================================

    def get_settings(self) -> Dict[str, Any]:
        return get_repository().admin_get_settings()

    def update_setting(
        self, key: str, value: str, description: Optional[str] = None
    ) -> Dict[str, Any]:
        return get_repository().admin_update_setting(key, value, description)

    # =========================================================
    # CONFIGURATION AUDIT
    # =========================================================

    def get_audit_logs(self, limit: int = 200, offset: int = 0) -> List[Dict[str, Any]]:
        return get_repository().admin_get_audit_logs(limit, offset)


admin_service = AdminService()
