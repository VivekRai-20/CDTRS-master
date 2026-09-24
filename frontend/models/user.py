from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextMembershipModel:
    """
    A user's membership in a specific work context.

    Context type determines the role for that context.
    department_id is populated only when the context is department-specific.

    Examples:
        HOD • PSTD
        HOD • ESFS
        EMPLOYEE • FCTD
        TSO • DS
        DS • DS
    """

    id: Optional[int] = None
    user_id: Optional[int] = None

    context_type: str = ""
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    department_code: Optional[str] = None

    is_active: bool = True

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def context_label(self) -> str:
        """Human-readable context label."""
        context = self.context_type.upper()

        if self.department_code:
            return f"{context} • {self.department_code}"

        if self.department_name:
            return f"{context} • {self.department_name}"

        return context

    @classmethod
    def from_dict(
        cls,
        data: Optional[Dict[str, Any]],
    ) -> "ContextMembershipModel":
        if not data:
            return cls()

        return cls(
            id=data.get("id"),
            user_id=data.get("user_id"),
            context_type=str(
                data.get("context_type")
                or data.get("role")
                or ""
            ).upper(),
            department_id=data.get("department_id"),
            department_name=data.get("department_name"),
            department_code=data.get("department_code"),
            is_active=bool(data.get("is_active", True)),
            created_at=(
                str(data["created_at"])
                if data.get("created_at") is not None
                else None
            ),
            updated_at=(
                str(data["updated_at"])
                if data.get("updated_at") is not None
                else None
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "context_type": self.context_type,
            "department_id": self.department_id,
            "department_name": self.department_name,
            "department_code": self.department_code,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class UserModel:
    """
    Frontend representation of a backend user.

    The active context is authoritative for the user's current permissions,
    role and department-specific behavior.

    The role and department fields are retained as profile/backend fields,
    but application workflow decisions must use active_context.
    """

    id: Optional[int] = None

    username: str = ""
    email: str = ""
    full_name: str = ""

    # Backend/profile role.
    # Do not use this as the active workflow context.
    role: Optional[str] = None

    employee_id: Optional[str] = None

    # Profile/default department information.
    # Context-specific operations must use active_context.department_id.
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    department_code: Optional[str] = None

    is_active: bool = True

    context_memberships: List[ContextMembershipModel] = field(
        default_factory=list
    )

    active_context_id: Optional[int] = None

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def active_context(self) -> Optional[ContextMembershipModel]:
        """
        Return the currently selected context.

        Only an active membership belonging to this user can be returned.
        """
        if self.active_context_id is not None:
            for membership in self.context_memberships:
                if (
                    membership.id == self.active_context_id
                    and membership.is_active
                ):
                    return membership

        # Fallback only for a newly loaded model where the backend marked
        # one membership as active but active_context_id was not populated.
        for membership in self.context_memberships:
            if membership.is_active and getattr(
                membership,
                "is_selected",
                False,
            ):
                return membership

        return None

    @property
    def active_role(self) -> Optional[str]:
        """Role of the currently selected work context."""
        context = self.active_context

        if context is not None:
            return context.context_type

        return None

    @property
    def active_department_id(self) -> Optional[int]:
        """Department belonging to the currently selected context."""
        context = self.active_context

        if context is not None:
            return context.department_id

        return None

    @property
    def active_department_name(self) -> Optional[str]:
        """Department name belonging to the current context."""
        context = self.active_context

        if context is not None:
            return context.department_name

        return None

    @property
    def active_department_code(self) -> Optional[str]:
        """Department code belonging to the current context."""
        context = self.active_context

        if context is not None:
            return context.department_code

        return None

    @property
    def active_context_label(self) -> str:
        """Display label for the current context."""
        context = self.active_context

        if context is None:
            return ""

        return context.context_label

    def has_context(
        self,
        context_type: str,
        department_id: Optional[int] = None,
    ) -> bool:
        """
        Check whether the user has an active membership matching a context.
        """
        requested_type = str(context_type).upper()

        for membership in self.context_memberships:
            if not membership.is_active:
                continue

            if membership.context_type.upper() != requested_type:
                continue

            if (
                department_id is not None
                and membership.department_id != department_id
            ):
                continue

            return True

        return False

    def set_active_context(
        self,
        context_id: Optional[int],
    ) -> bool:
        """
        Select an existing active context membership.

        Returns True when the context was selected successfully.
        """
        if context_id is None:
            self.active_context_id = None
            return True

        for membership in self.context_memberships:
            if (
                membership.id == context_id
                and membership.is_active
            ):
                self.active_context_id = membership.id
                return True

        return False

    def get_contexts(self) -> List[ContextMembershipModel]:
        """Return all context memberships belonging to this user."""
        return list(self.context_memberships)

    def set_contexts(self, contexts: List[Any]) -> None:
        """
        Replace the user's context memberships with backend-provided data.

        Existing active context is preserved when possible. Otherwise, an
        explicitly selected/active membership is used when available.
        """
        memberships: List[ContextMembershipModel] = []

        for item in contexts or []:
            if isinstance(item, ContextMembershipModel):
                memberships.append(item)
            elif isinstance(item, dict):
                memberships.append(ContextMembershipModel.from_dict(item))

        self.context_memberships = memberships

        # Preserve the currently selected context if it still exists.
        if self.active_context_id is not None:
            if self.set_active_context(self.active_context_id):
                return

        # Otherwise prefer a backend-selected membership.
        selected = next(
            (
                membership
                for membership in self.context_memberships
                if getattr(membership, "is_selected", False)
            ),
            None,
        )

        if selected is None:
            selected = next(
                (
                    membership
                    for membership in self.context_memberships
                    if membership.is_active
                ),
                None,
            )

        if selected is not None:
            self.active_context_id = selected.id

    def clear_active_context(self) -> None:
        """Clear the currently selected context."""
        self.active_context_id = None

    @classmethod
    def from_dict(
        cls,
        data: Optional[Dict[str, Any]],
    ) -> "UserModel":
        if not data:
            return cls()

        raw_memberships = (
            data.get("context_memberships")
            or data.get("contexts")
            or []
        )

        memberships = [
            ContextMembershipModel.from_dict(item)
            for item in raw_memberships
            if isinstance(item, dict)
        ]

        active_context_id = data.get("active_context_id")

        # Some backend responses may mark the selected membership.
        if active_context_id is None:
            for membership_data in raw_memberships:
                if not isinstance(membership_data, dict):
                    continue

                if membership_data.get("is_selected") is True:
                    active_context_id = membership_data.get("id")
                    break

        return cls(
            id=data.get("id"),
            username=data.get("username") or "",
            email=data.get("email") or "",
            full_name=(
                data.get("full_name")
                or data.get("name")
                or ""
            ),
            role=(
                str(data["role"]).upper()
                if data.get("role") is not None
                else None
            ),
            employee_id=data.get("employee_id"),
            department_id=data.get("department_id"),
            # The API serialises the home department name as "department".
            department_name=data.get("department_name") or data.get("department"),
            department_code=data.get("department_code"),
            is_active=bool(data.get("is_active", True)),
            context_memberships=memberships,
            active_context_id=active_context_id,
            created_at=(
                str(data["created_at"])
                if data.get("created_at") is not None
                else None
            ),
            updated_at=(
                str(data["updated_at"])
                if data.get("updated_at") is not None
                else None
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the user and all available context memberships."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "employee_id": self.employee_id,
            "department_id": self.department_id,
            "department_name": self.department_name,
            "department_code": self.department_code,
            "is_active": self.is_active,
            "context_memberships": [
                membership.to_dict()
                for membership in self.context_memberships
            ],
            "active_context_id": self.active_context_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def __repr__(self) -> str:
        return (
            "UserModel("
            f"id={self.id}, "
            f"username={self.username!r}, "
            f"active_context_id={self.active_context_id}, "
            f"active_role={self.active_role!r})"
        )