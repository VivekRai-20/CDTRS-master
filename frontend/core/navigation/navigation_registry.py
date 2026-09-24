from __future__ import annotations

from typing import Dict, List

from models.enums import RoleEnum


class NavigationRegistry:
    """
    Canonical navigation available for each active work-context type.

    The active WorkContextMembership is the source of truth.

    IMPORTANT:
        HOD does NOT have Employee Tasks.
        Employee Tasks belong only to EMPLOYEE context.
        TSO Tasks belong only to TSO context.
    """

    ADMIN = [
        "Dashboard",
        "User Configuration",
        "Department Configuration",
        "System Configuration",
        "Audit History",
    ]

    DIRECTOR = [
        "Dashboard",
        "Inbox",
        "Documents",
        "History / Audit",
    ]

    DS = [
        "Dashboard",
        "Document Intake",
        "Inbox",
        "Documents",
        "Workflow History",
    ]

    HOD = [
        "Dashboard",
        "HOD Inbox",
        "Documents",
        "Workflow History",
    ]

    EMPLOYEE = [
        "Dashboard",
        "Employee Tasks",
        "Documents",
        "Workflow History",
    ]

    TSO = [
        "Dashboard",
        "TSO Tasks",
        "Documents",
        "Workflow History",
    ]

    _MENUS: Dict[str, List[str]] = {
        RoleEnum.ADMIN.value: ADMIN,
        RoleEnum.DIRECTOR.value: DIRECTOR,
        RoleEnum.DS.value: DS,
        RoleEnum.HOD.value: HOD,
        RoleEnum.EMPLOYEE.value: EMPLOYEE,
        RoleEnum.TSO.value: TSO,
    }

    @classmethod
    def get_menu(cls, context_type: str) -> List[str]:
        """
        Return the navigation menu for the active context.

        No role fallback is used here. If the context is unknown,
        an empty menu is returned.
        """

        normalized = str(context_type or "").strip().upper()

        # Accept enum-like values such as:
        # RoleEnum.HOD
        if normalized.startswith("ROLEENUM."):
            normalized = normalized.split(".", 1)[1]

        return list(
            cls._MENUS.get(
                normalized,
                [],
            )
        )

    @classmethod
    def is_allowed(
        cls,
        context_type: str,
        page_name: str,
    ) -> bool:
        """
        Return whether a page belongs to the active context's menu.
        """

        return page_name in cls.get_menu(
            context_type
        )

    @classmethod
    def default_page(
        cls,
        context_type: str,
    ) -> str | None:
        """
        Return the first page available to a context.
        """

        menu = cls.get_menu(
            context_type
        )

        return menu[0] if menu else None

    @classmethod
    def all_pages(cls) -> List[str]:
        """
        Return all registered page names without duplicates.
        """

        pages: List[str] = []

        for menu in cls._MENUS.values():
            for page in menu:
                if page not in pages:
                    pages.append(page)

        return pages

    @classmethod
    def all_contexts(cls) -> List[str]:
        """
        Return all supported context types.
        """

        return list(
            cls._MENUS.keys()
        )


# ----------------------------------------------------------------------
# Module-level compatibility helpers
# ----------------------------------------------------------------------

def get_navigation(
    context_type: str,
) -> List[str]:
    return NavigationRegistry.get_menu(
        context_type
    )


def is_page_allowed(
    context_type: str,
    page_name: str,
) -> bool:
    return NavigationRegistry.is_allowed(
        context_type,
        page_name,
    )