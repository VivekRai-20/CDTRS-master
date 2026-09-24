"""CDTRS frontend active-context manager."""

from typing import Any, List, Optional

from PySide6.QtCore import QObject, Signal

from models.enums import RoleEnum
from services.auth_service import auth_service


class ContextManager(QObject):
    """Single frontend authority for the active operational context."""

    active_context_changed = Signal(object)
    context_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_context = None

    # ------------------------------------------------------------------
    # Loading / refreshing
    # ------------------------------------------------------------------

    def refresh(self, fallback_role: Optional[str] = None):
        """Refresh available contexts and publish the active one."""
        try:
            contexts = list(auth_service.get_contexts() or [])
        except Exception:
            contexts = []

        context = None
        try:
            context = auth_service.get_active_context()
        except Exception:
            context = None

        if context is None and contexts:
            context = next(
                (item for item in contexts if self._context_is_active(item)),
                None,
            )

        # If the backend/auth layer has not marked one active, choose the
        # first authenticated membership as the local default.  This never
        # creates a membership or bypasses backend authorization.
        if context is None and contexts:
            context = contexts[0]
            context_id = self._context_id(context)
            if context_id is not None:
                try:
                    auth_service.set_active_context(context_id)
                    context = auth_service.get_active_context() or context
                except Exception:
                    pass

        self._active_context = context

        if context is None:
            if fallback_role:
                return None
            self.context_cleared.emit()
            return None

        self.active_context_changed.emit(context)
        return context

    # ------------------------------------------------------------------
    # Context collection
    # ------------------------------------------------------------------

    def contexts(self) -> List[Any]:
        """Return all contexts available to the authenticated user."""
        try:
            return list(auth_service.get_contexts() or [])
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Active context
    # ------------------------------------------------------------------

    def active_context(self):
        """Return the confirmed active context, if one exists."""
        if self._active_context is not None:
            return self._active_context

        try:
            self._active_context = auth_service.get_active_context()
        except Exception:
            self._active_context = None

        # If AuthService has memberships but has not materialized an active
        # object yet, resolve it from the available collection.
        if self._active_context is None:
            contexts = self.contexts()

            active_id = None
            try:
                getter = getattr(auth_service, "get_active_context_membership_id", None)
                if callable(getter):
                    active_id = getter()
            except Exception:
                pass

            if active_id is not None:
                for context in contexts:
                    if self._context_id(context) == int(active_id):
                        self._active_context = context
                        break

            if self._active_context is None:
                self._active_context = next(
                    (
                        context
                        for context in contexts
                        if self._context_is_active(context)
                    ),
                    None,
                )

        return self._active_context

    def active_membership_id(self) -> Optional[int]:
        context = self.active_context()
        return self._context_id(context)

    def active_context_type(self, fallback_role: Optional[str] = None) -> str:
        """Return active context type; otherwise use the authenticated role."""
        context = self.active_context()

        if context is not None:
            value = self._context_value(context, "context_type", None)
            if value:
                return RoleEnum.normalize(value)

        if fallback_role:
            return RoleEnum.normalize(fallback_role)

        return RoleEnum.EMPLOYEE.value

    def active_department_id(self):
        context = self.active_context()
        return (
            self._context_value(context, "department_id", None)
            if context
            else None
        )

    def active_department_name(self) -> str:
        context = self.active_context()
        if not context:
            return ""

        return str(
            self._context_value(context, "department_name", None)
            or self._context_value(context, "department", None)
            or ""
        )

    # ------------------------------------------------------------------
    # Switching
    # ------------------------------------------------------------------

    def switch_context(self, membership_id: int) -> bool:
        """Validate/switch context through AuthService and publish it."""
        try:
            selected_id = int(membership_id)
        except (TypeError, ValueError):
            return False

        try:
            if not auth_service.switch_context(selected_id):
                return False
        except Exception:
            return False

        context = auth_service.get_active_context()
        if context is None or self._context_id(context) != selected_id:
            # Do not silently display a different context than the one that
            # was requested and successfully validated.
            for item in self.contexts():
                if self._context_id(item) == selected_id:
                    context = item
                    break

        if context is None:
            self.context_cleared.emit()
            return False

        self._active_context = context
        self.active_context_changed.emit(context)
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _context_value(context: Any, key: str, default: Any = None) -> Any:
        if isinstance(context, dict):
            return context.get(key, default)
        return getattr(context, key, default)

    @classmethod
    def _context_id(cls, context: Any) -> Optional[int]:
        if context is None:
            return None

        value = cls._context_value(context, "id", None)
        if value is None:
            value = cls._context_value(context, "membership_id", None)
        if value is None:
            value = cls._context_value(
                context,
                "context_membership_id",
                None,
            )

        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _context_is_active(cls, context: Any) -> bool:
        return bool(
            cls._context_value(context, "is_active", False)
            or cls._context_value(context, "active", False)
        )

    # ------------------------------------------------------------------
    # Logout
    # ------------------------------------------------------------------

    def clear(self):
        """Clear local state during logout."""
        self._active_context = None
        self.context_cleared.emit()


context_manager = ContextManager()
