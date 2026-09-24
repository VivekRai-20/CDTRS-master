from typing import Any, Dict, Optional, List

from models.user import UserModel
from repositories.provider import get_repository


class AuthService:
    """Authentication and active WorkContextMembership session management."""

    def __init__(self):
        self._repository = get_repository()
        self._active_context_id: Optional[int] = None

    def login(self, username: str, password: str) -> Optional[UserModel]:
        repo = get_repository()

        user = repo.authenticate(username, password)
        if not user:
            return None

        # ---------------------------------------------------------
        # 1. Preserve the active context returned during login.
        # ---------------------------------------------------------
        self._active_context_id = user.active_context_id

        # ---------------------------------------------------------
        # 2. ALWAYS load the complete context membership list.
        #
        # Do not assume that authenticate() returned every context.
        # The user may have:
        #   DS + HOD
        #   DS + Employee
        #   Director + HOD
        #   HOD + Employee
        #   etc.
        # ---------------------------------------------------------
        try:
            raw_contexts = repo.get_user_contexts()

            if raw_contexts:
                user.set_contexts(raw_contexts)

        except Exception:
            # Keep contexts already returned by authenticate().
            raw_contexts = None

        # ---------------------------------------------------------
        # 3. If the repository did not return contexts, preserve
        #    whatever was already loaded by UserModel.from_dict().
        # ---------------------------------------------------------
        contexts = user.get_contexts()

        # ---------------------------------------------------------
        # 4. Resolve active context.
        #
        # Prefer the active context returned by authentication.
        # If it does not exist in the loaded memberships, fall back
        # to UserModel's active-context resolution.
        # ---------------------------------------------------------
        if self._active_context_id is not None:
            if not user.set_active_context(self._active_context_id):
                self._active_context_id = user.active_context_id

        if self._active_context_id is None:
            active_context = user.active_context

            if active_context:
                self._active_context_id = active_context.id
                user.set_active_context(active_context.id)

            elif contexts:
                self._active_context_id = contexts[0].id
                user.set_active_context(self._active_context_id)

        # ---------------------------------------------------------
        # 5. Tell the API client which context is active.
        #
        # This is what causes subsequent API requests to carry the
        # correct X-Work-Context-Id header.
        # ---------------------------------------------------------
        if self._active_context_id is not None:
            try:
                from api.client import api_client
                api_client.set_active_context_id(self._active_context_id)
            except Exception:
                pass

        # ---------------------------------------------------------
        # 6. Start websocket connection in API mode.
        # ---------------------------------------------------------
        from config.settings import settings

        if settings.is_api_mode:
            try:
                from services.websocket_service import websocket_service
                websocket_service.connect_client()
            except Exception:
                pass

        return user

    def logout(self) -> None:
        self._active_context_id = None

        try:
            from api.client import api_client
            api_client.set_active_context_id(None)
        except Exception:
            pass

        try:
            from services.websocket_service import websocket_service
            websocket_service.disconnect_client()
        except Exception:
            pass

        get_repository().logout()

    def get_current_user(self) -> Optional[UserModel]:
        return get_repository().get_current_user()

    def is_authenticated(self) -> bool:
        return self.get_current_user() is not None

    # -------------------------------------------------------------
    # Context management
    # -------------------------------------------------------------

    def get_contexts(self) -> List[Any]:
        """
        Return all WorkContextMembership records available to the
        authenticated user.

        The repository is queried when the current UserModel has
        no loaded memberships.
        """
        user = self.get_current_user()

        if not user:
            return []

        contexts = user.get_contexts()

        if contexts:
            return contexts

        try:
            raw_contexts = get_repository().get_user_contexts()

            if raw_contexts:
                user.set_contexts(raw_contexts)

        except Exception:
            return contexts

        return user.get_contexts()

    def get_active_context(self):
        user = self.get_current_user()

        if not user:
            return None

        if self._active_context_id is not None:
            if not user.set_active_context(self._active_context_id):
                self._active_context_id = user.active_context_id

        return user.active_context

    def get_active_context_id(self) -> Optional[int]:
        context = self.get_active_context()

        if context:
            return context.id

        return self._active_context_id

    def set_active_context(self, context_membership_id: int) -> bool:
        """Set the local active context and propagate it to the API client.

        This is intentionally a local/session operation.  Use
        ``switch_context()`` when the backend must validate the switch.
        """
        try:
            context_id = int(context_membership_id)
        except (TypeError, ValueError):
            return False

        user = self.get_current_user()
        if not user:
            return False

        contexts = user.get_contexts()
        if not any(getattr(context, "id", None) == context_id for context in contexts):
            return False

        if not user.set_active_context(context_id):
            return False

        self._active_context_id = context_id

        try:
            from api.client import api_client
            api_client.set_active_context_id(context_id)
        except Exception:
            pass

        return True

    def switch_context(self, context_membership_id: int) -> bool:
        """Validate and switch to one of the authenticated user's contexts."""
        try:
            context_id = int(context_membership_id)
        except (TypeError, ValueError):
            return False

        try:
            result = get_repository().switch_context(context_id)
        except Exception:
            return False

        if not result:
            return False

        selected_id = context_id
        if isinstance(result, dict):
            selected_id = result.get("id") or result.get(
                "context_membership_id"
            ) or context_id

        try:
            selected_id = int(selected_id)
        except (TypeError, ValueError):
            selected_id = context_id

        user = self.get_current_user()
        if not user:
            return False

        # Refresh membership state so the UI always reflects the backend
        # membership set after a successful switch.
        try:
            raw_contexts = get_repository().get_user_contexts()
            if raw_contexts:
                user.set_contexts(raw_contexts)
        except Exception:
            pass

        return self.set_active_context(selected_id)

    def reset_password(
        self,
        username: str,
        old_password: str,
        new_password: str,
    ) -> bool:
        return get_repository().reset_password(
            username,
            old_password,
            new_password,
        )


auth_service = AuthService()


def authenticate(
    username: str,
    password: str,
) -> Optional[Dict[str, Any]]:
    user = auth_service.login(username, password)

    if not user:
        return None

    context = user.active_context

    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": context.context_type if context else user.role,
        "department_id": (
            context.department_id
            if context
            else user.department_id
        ),
        "department": (
            context.department_name
            if context
            else user.department_name
        ),
        "contexts": [
            c.to_dict()
            for c in user.get_contexts()
        ],
        "active_context_id": user.active_context_id,
        "active_context_membership_id": user.active_context_id,
    }