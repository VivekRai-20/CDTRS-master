from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QWidget,
    QSizePolicy,
)

from components.document_viewer import DocumentViewer
from models.enums import RoleEnum

from pages.dashboard import DashboardPage
from pages.director_inbox import DirectorInboxPage
from pages.director_reviewed import DirectorReviewedPage
from pages.document_intake import DocumentIntakePage
from pages.documents import DocumentsPage
from pages.employee_tasks import EmployeeTasksPage
from pages.history import HistoryPage
from pages.hod_inbox import HODInboxPage
from pages.inbox import InboxPage
from pages.tso_tasks import TSOTasksPage

from ui.sidebar import Sidebar

from core.context.context_manager import context_manager
from core.navigation.navigation_registry import NavigationRegistry


class MainWindow(QMainWindow):
    """
    Main CDTRS application shell.

    Navigation is controlled exclusively by the currently active
    WorkContextMembership/context.

    Important:
        - Role/context determines the sidebar.
        - Role/context determines the landing page.
        - Admin pages are created only for ADMIN context.
        - Workflow History is document-specific, not user activity history.
        - No Security Trail/Admin Suite navigation exists here.
    """

    def __init__(self, username: str, role: str):
        super().__init__()

        self.username = username
        self.role = RoleEnum.normalize(role)

        self.previous_page = None
        self.document_viewer = None

        # --------------------------------------------------------------
        # Admin pages
        # --------------------------------------------------------------
        #
        # Created lazily ONLY when an ADMIN context is active.
        #
        self.admin_dashboard_page = None
        self.user_configuration_page = None
        self.department_configuration_page = None
        self.system_configuration_page = None
        self.audit_history_page = None

        self._admin_pages_initialized = False

        # --------------------------------------------------------------
        # Window
        # --------------------------------------------------------------

        self.setWindowTitle(
            f"CDTRS - {self.role} ({self.username})"
        )

        self.resize(1180, 760)
        self.setMinimumSize(900, 560)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --------------------------------------------------------------
        # Sidebar
        # --------------------------------------------------------------

        self.sidebar = Sidebar(
            self.role,
            username=self.username,
        )

        self.sidebar.page_requested.connect(
            self._handle_page_requested
        )

        self.sidebar.logout_requested.connect(
            self.logout
        )

        self.sidebar.context_switch_requested.connect(
            self._handle_context_switch
        )

        # --------------------------------------------------------------
        # Page stack
        # --------------------------------------------------------------

        self.stack = QStackedWidget()

        # ==============================================================
        # COMMON / OPERATIONAL PAGES
        # ==============================================================

        # --------------------------------------------------------------
        # Generic role dashboard
        # --------------------------------------------------------------

        self.dashboard_page = DashboardPage(self.role)

        self.dashboard_page.view_requested.connect(
            self.open_document_viewer
        )

        self.dashboard_page.navigate_requested.connect(
            self._handle_dashboard_navigate
        )

        self.stack.addWidget(self.dashboard_page)

        # --------------------------------------------------------------
        # DS Inbox
        #
        # This page represents automatically synchronized incoming
        # Outlook/mail documents waiting for DS processing.
        # --------------------------------------------------------------

        self.inbox_page = InboxPage()

        self.inbox_page.process_requested.connect(
            self.open_document_from_inbox
        )

        self.stack.addWidget(self.inbox_page)

        # --------------------------------------------------------------
        # DS Document Intake
        # --------------------------------------------------------------

        self.document_intake_page = DocumentIntakePage()

        self.document_intake_page.document_processed.connect(
            self.on_document_processed
        )

        self.stack.addWidget(self.document_intake_page)

        # --------------------------------------------------------------
        # Documents
        # --------------------------------------------------------------

        self.documents_page = DocumentsPage(
            user_role=self.role
        )

        self.documents_page.view_requested.connect(
            self.open_document_viewer
        )

        self.stack.addWidget(self.documents_page)

        # --------------------------------------------------------------
        # Document-specific Workflow History
        # --------------------------------------------------------------

        self.history_page = HistoryPage()

        self.stack.addWidget(self.history_page)

        # --------------------------------------------------------------
        # Director Inbox
        # --------------------------------------------------------------

        self.director_inbox_page = DirectorInboxPage()

        self.director_inbox_page.view_requested.connect(
            self.open_document_viewer
        )

        self.stack.addWidget(self.director_inbox_page)

        # --------------------------------------------------------------
        # Director reviewed documents
        #
        # Kept as an internal operational page because dashboard/filter
        # navigation may still use it. It is NOT a sidebar item.
        # --------------------------------------------------------------

        self.director_reviewed_page = DirectorReviewedPage()

        self.director_reviewed_page.view_requested.connect(
            self.open_document_viewer
        )

        self.stack.addWidget(self.director_reviewed_page)

        # --------------------------------------------------------------
        # HOD Inbox
        # --------------------------------------------------------------

        self.hod_inbox_page = HODInboxPage()

        self.hod_inbox_page.view_requested.connect(
            self.open_document_viewer
        )

        self.stack.addWidget(self.hod_inbox_page)

        # --------------------------------------------------------------
        # Employee Tasks
        # --------------------------------------------------------------

        self.employee_tasks_page = EmployeeTasksPage()

        self.employee_tasks_page.view_requested.connect(
            self.open_document_viewer
        )

        self.stack.addWidget(self.employee_tasks_page)

        # --------------------------------------------------------------
        # TSO Tasks
        # --------------------------------------------------------------

        self.tso_tasks_page = TSOTasksPage()

        self.tso_tasks_page.view_requested.connect(
            self.open_document_viewer
        )

        self.stack.addWidget(self.tso_tasks_page)

        # ==============================================================
        # MAIN WINDOW LAYOUT
        # ==============================================================

        main_layout.addWidget(self.sidebar)

        stack_container = QWidget()
        stack_container.setObjectName("mainContentContainer")
        stack_container.setStyleSheet("#mainContentContainer { background: transparent; }")
        stack_layout = QHBoxLayout(stack_container)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(0)
        
        stack_layout.addStretch(1)
        self.stack.setMaximumWidth(1400)
        
        # Using size policy to allow it to expand up to max width
        self.stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        stack_layout.addWidget(self.stack, 10)
        stack_layout.addStretch(1)

        main_layout.addWidget(stack_container, 1)

        central_widget.setLayout(main_layout)

        # ==============================================================
        # CONTEXT EVENTS
        # ==============================================================

        context_manager.active_context_changed.connect(
            self._handle_active_context_changed
        )

        context_manager.context_cleared.connect(
            self._handle_context_cleared
        )

        # ==============================================================
        # APPLY INITIAL CONTEXT
        # ==============================================================

        context = context_manager.active_context()

        if context is not None:
            self._apply_context(context)
        else:
            self._navigate_to_first_allowed_page()

    # ==================================================================
    # ADMIN PAGE INITIALIZATION
    # ==================================================================

    def _ensure_admin_pages(self) -> None:
        """
        Lazily create administrator-only pages.

        These pages must never be constructed for non-admin contexts
        because their constructors may call /admin/* endpoints.
        """

        if self._admin_pages_initialized:
            return

        self._admin_pages_initialized = True

        from pages.admin_dashboard import AdminDashboardPage
        from pages.user_configuration import UserConfigurationPage
        from pages.department_configuration import (
            DepartmentConfigurationPage,
        )
        from pages.system_configuration import SystemConfigurationPage
        from pages.audit_history import AuditHistoryPage

        self.admin_dashboard_page = AdminDashboardPage()
        self.admin_dashboard_page.navigate_requested.connect(self._handle_dashboard_navigate)

        self.user_configuration_page = UserConfigurationPage()

        self.department_configuration_page = (
            DepartmentConfigurationPage()
        )

        self.system_configuration_page = SystemConfigurationPage()

        self.audit_history_page = AuditHistoryPage()

        self.stack.addWidget(
            self.admin_dashboard_page
        )

        self.stack.addWidget(
            self.user_configuration_page
        )

        self.stack.addWidget(
            self.department_configuration_page
        )

        self.stack.addWidget(
            self.system_configuration_page
        )

        self.stack.addWidget(
            self.audit_history_page
        )

    # ==================================================================
    # CONTEXT HANDLING
    # ==================================================================

    def _handle_context_switch(self, membership_id: int):
        """
        Switch the active WorkContextMembership.

        The context manager is the source of truth. Once it emits
        active_context_changed, _apply_context() rebuilds the visible
        navigation and chooses the correct landing page.
        """

        current_id = context_manager.active_membership_id()

        if current_id == membership_id:
            return

        if not context_manager.switch_context(membership_id):
            self._sync_sidebar_selector()

    def _handle_active_context_changed(self, context):
        self._apply_context(context)
        self._sync_sidebar_selector()

    def _handle_context_cleared(self):
        """
        Context clearing normally occurs during logout.
        """

        self.document_viewer = None

    def _apply_context(self, context):
        """
        Apply a newly active work context.

        This is the central point where context changes affect:
            1. Current role/context.
            2. Window title.
            3. Sidebar navigation.
            4. Admin page availability.
            5. Landing page.
        """

        context_type = (
            getattr(context, "context_type", None)
            or self.role
        )

        self.role = RoleEnum.normalize(context_type)

        self.setWindowTitle(
            f"CDTRS - {self.role} ({self.username})"
        )

        # Sidebar rebuilds itself from NavigationRegistry using
        # the active context. Therefore old-role tabs disappear.
        self.sidebar.apply_context(context)

        # Admin pages exist only if ADMIN is the active context.
        if self.role == RoleEnum.ADMIN.value:
            self._ensure_admin_pages()

        # Do not keep a document viewer open across context switches.
        if self.document_viewer is not None:
            self._cleanup_existing_viewer()

        # Keep role-dependent pages aware of the new context where
        # supported by the page implementation.
        if hasattr(self.documents_page, "user_role"):
            self.documents_page.user_role = self.role

        if hasattr(self.dashboard_page, "role"):
            self.dashboard_page.role = self.role

        # Always land on the first page belonging to the NEW context.
        self._navigate_to_first_allowed_page()

        self.centralWidget().updateGeometry()

    def _sync_sidebar_selector(self):
        selector = self.sidebar.context_selector

        if selector is None:
            return

        active_id = context_manager.active_membership_id()

        if active_id is None:
            return

        self.sidebar._context_switching = True

        try:
            index = selector.findData(active_id)

            if index >= 0:
                selector.setCurrentIndex(index)

        finally:
            self.sidebar._context_switching = False

    # ==================================================================
    # NAVIGATION
    # ==================================================================

    def _handle_page_requested(self, page_key: str):
        """
        Navigate only to a page exposed by the active context.

        NavigationRegistry is the final navigation authority.
        """

        if not self._page_allowed_for_current_context(page_key):
            return

        # --------------------------------------------------------------
        # Dashboard
        #
        # IMPORTANT:
        # Admin's Dashboard is AdminDashboardPage.
        # Every other context uses DashboardPage.
        # --------------------------------------------------------------

        if page_key == "Dashboard":

            if self.role == RoleEnum.ADMIN.value:
                self._ensure_admin_pages()

                if self.admin_dashboard_page is not None:
                    self._navigate_to(
                        self.admin_dashboard_page,
                        "Dashboard",
                    )

            else:
                self._navigate_to(
                    self.dashboard_page,
                    "Dashboard",
                )

        # --------------------------------------------------------------
        # DS Inbox
        # --------------------------------------------------------------

        elif page_key == "Inbox":

            if self.role == RoleEnum.DIRECTOR.value:
                self._navigate_to(
                    self.director_inbox_page,
                    "Inbox",
                )

            elif self.role == RoleEnum.HOD.value:
                self._navigate_to(
                    self.hod_inbox_page,
                    "HOD Inbox",
                )

            elif self.role == RoleEnum.EMPLOYEE.value:
                self._navigate_to(
                    self.employee_tasks_page,
                    "Employee Tasks",
                )

            elif self.role == RoleEnum.TSO.value:
                self._navigate_to(
                    self.tso_tasks_page,
                    "TSO Tasks",
                )

            elif self.role == RoleEnum.DS.value:
                self._navigate_to(
                    self.inbox_page,
                    "Inbox",
                )

        # --------------------------------------------------------------
        # Director Inbox / Review Queue
        # --------------------------------------------------------------

        elif page_key == "Review Queue":

            self._navigate_to(
                self.director_inbox_page,
                "Review Queue",
            )

        # --------------------------------------------------------------
        # HOD Inbox
        # --------------------------------------------------------------

        elif page_key == "HOD Inbox":

            self._navigate_to(
                self.hod_inbox_page,
                "HOD Inbox",
            )

        # --------------------------------------------------------------
        # Employee Tasks
        # --------------------------------------------------------------

        elif page_key == "Employee Tasks":

            self._navigate_to(
                self.employee_tasks_page,
                "Employee Tasks",
            )

        # --------------------------------------------------------------
        # TSO Tasks
        # --------------------------------------------------------------

        elif page_key == "TSO Tasks":

            self._navigate_to(
                self.tso_tasks_page,
                "TSO Tasks",
            )

        # --------------------------------------------------------------
        # Legacy internal task keys
        #
        # These are retained only so older dashboard signals do not
        # break. They are NOT exposed in the new sidebar.
        # --------------------------------------------------------------

        elif page_key == "My Tasks":

            if self.role == RoleEnum.TSO.value:
                self._navigate_to(
                    self.tso_tasks_page,
                    "TSO Tasks",
                )

            elif self.role == RoleEnum.EMPLOYEE.value:
                self._navigate_to(
                    self.employee_tasks_page,
                    "Employee Tasks",
                )

        elif page_key == "Department Tasks":

            if self.role == RoleEnum.HOD.value:
                self._navigate_to(
                    self.hod_inbox_page,
                    "HOD Inbox",
                )

        # --------------------------------------------------------------
        # DS Document Intake
        # --------------------------------------------------------------

        elif page_key in (
            "Document Intake",
            "Document Processing",
        ):

            self._navigate_to(
                self.document_intake_page,
                "Document Intake",
            )

        # --------------------------------------------------------------
        # Documents
        # --------------------------------------------------------------

        elif page_key in (
            "Documents",
            "All Documents",
        ):

            self._navigate_to(
                self.documents_page,
                "Documents",
            )

        # --------------------------------------------------------------
        # Document Workflow History
        #
        # This page is document-specific. It is NOT a personal
        # activity/history page.
        # --------------------------------------------------------------

        elif page_key in (
            "Workflow History",
            "History / Audit",
            "History",
        ):

            self._navigate_to(
                self.history_page,
                page_key,
            )

        # --------------------------------------------------------------
        # Admin User Configuration
        # --------------------------------------------------------------

        elif page_key == "User Configuration":

            if self.role != RoleEnum.ADMIN.value:
                return

            self._ensure_admin_pages()

            if self.user_configuration_page is not None:
                self._navigate_to(
                    self.user_configuration_page,
                    page_key,
                )

        # --------------------------------------------------------------
        # Admin Department Configuration
        # --------------------------------------------------------------

        elif page_key == "Department Configuration":

            if self.role != RoleEnum.ADMIN.value:
                return

            self._ensure_admin_pages()

            if self.department_configuration_page is not None:
                self._navigate_to(
                    self.department_configuration_page,
                    page_key,
                )

        # --------------------------------------------------------------
        # Admin System Configuration
        # --------------------------------------------------------------

        elif page_key == "System Configuration":

            if self.role != RoleEnum.ADMIN.value:
                return

            self._ensure_admin_pages()

            if self.system_configuration_page is not None:
                self._navigate_to(
                    self.system_configuration_page,
                    page_key,
                )

        # --------------------------------------------------------------
        # Admin Audit History
        # --------------------------------------------------------------

        elif page_key == "Audit History":

            if self.role != RoleEnum.ADMIN.value:
                return

            self._ensure_admin_pages()

            if self.audit_history_page is not None:
                self._navigate_to(
                    self.audit_history_page,
                    page_key,
                )

    def _open_inbox_for_role(self, menu_key: str):
        """
        Internal compatibility helper.

        New sidebar labels are handled directly by
        _handle_page_requested(), but this method is retained for
        dashboard/internal navigation.
        """

        if self.role == RoleEnum.DIRECTOR.value:
            self._navigate_to(
                self.director_inbox_page,
                menu_key,
            )

        elif self.role == RoleEnum.HOD.value:
            self._navigate_to(
                self.hod_inbox_page,
                "HOD Inbox",
            )

        elif self.role == RoleEnum.TSO.value:
            self._navigate_to(
                self.tso_tasks_page,
                "TSO Tasks",
            )

        elif self.role == RoleEnum.EMPLOYEE.value:
            self._navigate_to(
                self.employee_tasks_page,
                "Employee Tasks",
            )

        elif self.role == RoleEnum.DS.value:
            self._navigate_to(
                self.inbox_page,
                "Inbox",
            )

    def _navigate_to_first_allowed_page(self):
        """
        Navigate to the first page exposed by the active context.

        Because every NavigationRegistry menu starts with Dashboard,
        this also guarantees that switching context lands on the
        correct context-specific dashboard.
        """

        context_type = context_manager.active_context_type(
            fallback_role=self.role
        )

        if not context_type:
            context_type = self.role

        if context_type == RoleEnum.ADMIN.value:
            self._ensure_admin_pages()

        menu = NavigationRegistry.get_menu(context_type)

        if not menu:
            return

        self._handle_page_requested(menu[0])

    def _page_allowed_for_current_context(
        self,
        page_key: str,
    ) -> bool:
        """
        Validate navigation against the active context only.
        """

        context_type = context_manager.active_context_type(
            fallback_role=self.role
        )

        if not context_type:
            context_type = self.role

        return NavigationRegistry.is_allowed(
            context_type,
            page_key,
        )

    def setup_navigation(self):
        """
        Compatibility method retained for older callers.

        Navigation is now managed by Sidebar + NavigationRegistry.
        """

        return None

    # ==================================================================
    # DASHBOARD NAVIGATION
    # ==================================================================

    def _handle_dashboard_navigate(
        self,
        target_page_name: str,
        filters: Optional[dict] = None,
    ):
        """
        Handle navigation requests originating from a dashboard.

        Dashboard buttons must still obey the active context's
        NavigationRegistry permissions.
        """

        if not self._page_allowed_for_current_context(
            target_page_name
        ):
            return

        # --------------------------------------------------------------
        # Dashboard
        # --------------------------------------------------------------

        if target_page_name == "Dashboard":

            self._handle_page_requested("Dashboard")
            return

        # --------------------------------------------------------------
        # Admin pages
        # --------------------------------------------------------------

        if target_page_name == "User Configuration":
            self._handle_page_requested(
                "User Configuration"
            )
            return

        if target_page_name == "Department Configuration":
            self._handle_page_requested(
                "Department Configuration"
            )
            return

        if target_page_name == "System Configuration":
            self._handle_page_requested(
                "System Configuration"
            )
            return

        if target_page_name == "Audit History":
            self._handle_page_requested(
                "Audit History"
            )
            return

        # --------------------------------------------------------------
        # Inbox
        # --------------------------------------------------------------

        if target_page_name == "Inbox":

            if self.role == RoleEnum.DIRECTOR.value:

                self._navigate_to(
                    self.director_inbox_page,
                    "Inbox",
                    skip_reload=bool(filters),
                )

                if (
                    filters
                    and hasattr(
                        self.director_inbox_page,
                        "set_filters",
                    )
                ):
                    self.director_inbox_page.set_filters(
                        **filters
                    )

                return

            if self.role == RoleEnum.HOD.value:

                self._navigate_to(
                    self.hod_inbox_page,
                    "HOD Inbox",
                    skip_reload=bool(filters),
                )

                if (
                    filters
                    and hasattr(
                        self.hod_inbox_page,
                        "set_filters",
                    )
                ):
                    self.hod_inbox_page.set_filters(
                        **filters
                    )

                return

            if self.role == RoleEnum.TSO.value:

                self._navigate_to(
                    self.tso_tasks_page,
                    "TSO Tasks",
                    skip_reload=bool(filters),
                )

                return

            if self.role == RoleEnum.EMPLOYEE.value:

                self._navigate_to(
                    self.employee_tasks_page,
                    "Employee Tasks",
                    skip_reload=bool(filters),
                )

                return

            if self.role == RoleEnum.DS.value:

                self._navigate_to(
                    self.inbox_page,
                    "Inbox",
                    skip_reload=bool(filters),
                )

                return

        # --------------------------------------------------------------
        # Director reviewed documents
        # --------------------------------------------------------------

        elif target_page_name in (
            "Reviewed Documents",
            "Reviewed",
        ):

            if self.role == RoleEnum.DIRECTOR.value:

                self._navigate_to(
                    self.director_inbox_page,
                    "Inbox",
                    skip_reload=True,
                )

                if hasattr(
                    self.director_inbox_page,
                    "set_filters",
                ):
                    self.director_inbox_page.set_filters(
                        category="Reviewed & Returned to DS"
                    )

            else:

                self._navigate_to(
                    self.director_reviewed_page,
                    "Reviewed Documents",
                )

        # --------------------------------------------------------------
        # Documents
        # --------------------------------------------------------------

        elif target_page_name in (
            "Documents",
            "All Documents",
        ):

            self._navigate_to(
                self.documents_page,
                "Documents",
                skip_reload=bool(filters),
            )

            if (
                filters
                and hasattr(
                    self.documents_page,
                    "set_filters",
                )
            ):
                self.documents_page.set_filters(
                    **filters
                )

    # ==================================================================
    # PAGE NAVIGATION HELPER
    # ==================================================================

    def _navigate_to(
        self,
        target_widget: QWidget,
        menu_key: str,
        skip_reload: bool = False,
    ):
        """
        Display a page and refresh only that page.

        The page itself uses the active context through APIClient's
        X-Work-Context-Id header.
        """

        if target_widget is None:
            return

        if self.document_viewer is not None:
            self._cleanup_existing_viewer()

        if not skip_reload:

            if hasattr(target_widget, "refresh"):
                target_widget.refresh()

            elif hasattr(target_widget, "load_inbox"):
                target_widget.load_inbox()

            elif hasattr(target_widget, "load_tasks"):
                target_widget.load_tasks()

            elif hasattr(target_widget, "load_documents"):
                target_widget.load_documents()

            elif hasattr(target_widget, "load_history"):
                target_widget.load_history()

        self.sidebar.set_active(menu_key)

        self.stack.setCurrentWidget(
            target_widget
        )

    # ==================================================================
    # DOCUMENT PROCESSING
    # ==================================================================

    def open_document_from_inbox(self, document):
        """
        Open a synchronized incoming document in the DS Document Intake
        workspace.
        """

        if self.document_viewer is not None:
            self._cleanup_existing_viewer()

        self.document_intake_page.load_document(
            document
        )

        # New navigation label.
        active_key = (
            "Document Intake"
            if "Document Intake" in self.sidebar.buttons
            else "Document Processing"
        )

        self.sidebar.set_active(active_key)

        self.stack.setCurrentWidget(
            self.document_intake_page
        )

    def on_document_processed(self, routed_document):
        """
        Refresh only pages relevant to the currently active context
        after DS document processing/routing.
        """

        # Generic dashboard
        if hasattr(self.dashboard_page, "refresh"):
            self.dashboard_page.refresh()

        # Admin dashboard, if it exists
        if (
            self.role == RoleEnum.ADMIN.value
            and self.admin_dashboard_page is not None
            and hasattr(
                self.admin_dashboard_page,
                "refresh",
            )
        ):
            self.admin_dashboard_page.refresh()

        # Refresh the context-specific operational area.
        if self.role == RoleEnum.DS.value:

            self.inbox_page.load_documents()
            self.documents_page.load_documents()

        elif self.role == RoleEnum.DIRECTOR.value:

            self.director_inbox_page.load_inbox()
            self.documents_page.load_documents()

        elif self.role == RoleEnum.HOD.value:

            self.hod_inbox_page.load_inbox()
            self.documents_page.load_documents()

        elif self.role == RoleEnum.EMPLOYEE.value:

            self.employee_tasks_page.load_tasks()
            self.documents_page.load_documents()

        elif self.role == RoleEnum.TSO.value:

            self.tso_tasks_page.load_tasks()
            self.documents_page.load_documents()

        elif self.role == RoleEnum.ADMIN.value:

            self.documents_page.load_documents()

        self._navigate_to_first_allowed_page()

    # ==================================================================
    # DOCUMENT VIEWER
    # ==================================================================

    def _cleanup_existing_viewer(self):
        if self.document_viewer is None:
            return

        viewer = self.document_viewer
        self.document_viewer = None

        try:
            viewer.close_requested.disconnect()
        except Exception:
            pass

        try:
            viewer.document_updated.disconnect()
        except Exception:
            pass

        if hasattr(viewer, "cleanup"):
            viewer.cleanup()

        self.stack.removeWidget(viewer)
        viewer.deleteLater()

    def open_document_viewer(
        self,
        document,
        role: Optional[str] = None,
    ):
        """
        Open the document-specific viewer.

        The viewer receives the current active context role unless
        explicitly overridden by the caller.
        """

        self._cleanup_existing_viewer()

        self.previous_page = self.stack.currentWidget()

        self.document_viewer = DocumentViewer(
            document,
            role=role or self.role,
        )

        self.document_viewer.close_requested.connect(
            self.close_document_viewer
        )

        self.document_viewer.document_updated.connect(
            self.on_document_updated
        )

        self.stack.addWidget(
            self.document_viewer
        )

        self.stack.setCurrentWidget(
            self.document_viewer
        )

    def on_document_updated(self, updated_document):
        """
        Refresh only the pages relevant to the active context.

        This avoids making API calls for unrelated role-specific pages.
        """

        # --------------------------------------------------------------
        # Current context dashboard
        # --------------------------------------------------------------

        if hasattr(
            self.dashboard_page,
            "refresh",
        ):
            self.dashboard_page.refresh()

        # --------------------------------------------------------------
        # Active context-specific page
        # --------------------------------------------------------------

        if self.role == RoleEnum.ADMIN.value:

            if (
                self.admin_dashboard_page is not None
                and hasattr(
                    self.admin_dashboard_page,
                    "refresh",
                )
            ):
                self.admin_dashboard_page.refresh()

            return

        if self.role == RoleEnum.DS.value:

            self.inbox_page.load_documents()

        elif self.role == RoleEnum.DIRECTOR.value:

            self.director_inbox_page.load_inbox()

            if hasattr(
                self.director_reviewed_page,
                "load_documents",
            ):
                self.director_reviewed_page.load_documents()

        elif self.role == RoleEnum.HOD.value:

            self.hod_inbox_page.load_inbox()

        elif self.role == RoleEnum.EMPLOYEE.value:

            self.employee_tasks_page.load_tasks()

        elif self.role == RoleEnum.TSO.value:

            self.tso_tasks_page.load_tasks()

        # --------------------------------------------------------------
        # Documents is shared across operational contexts.
        # --------------------------------------------------------------

        if hasattr(
            self.documents_page,
            "status_filter",
        ):
            self.documents_page.status_filter.setCurrentIndex(
                0
            )

        self.documents_page.load_documents()

        # --------------------------------------------------------------
        # Workflow History is document-specific.
        # Refresh it only if the current page supports it.
        # --------------------------------------------------------------

        if (
            self.stack.currentWidget()
            is self.history_page
            and hasattr(
                self.history_page,
                "load_history",
            )
        ):
            self.history_page.load_history()

    def close_document_viewer(self):
        if self.previous_page is not None:
            previous = self.previous_page
            self.stack.setCurrentWidget(previous)
            if hasattr(previous, "refresh"):
                previous.refresh()
            elif hasattr(
                previous,
                "load_inbox",
            ):
                previous.load_inbox()

            elif hasattr(
                previous,
                "load_tasks",
            ):
                previous.load_tasks()

            elif hasattr(
                previous,
                "load_documents",
            ):
                previous.load_documents()

        self._cleanup_existing_viewer()

    # ==================================================================
    # LOGOUT
    # ==================================================================

    def logout(self):
        self._cleanup_existing_viewer()

        try:
            from services.auth_service import auth_service

            auth_service.logout()

        except Exception:
            pass

        context_manager.clear()

        from ui.login import LoginWindow

        self.login_window = LoginWindow()
        self.login_window.show()

        self.close()

    # ==================================================================
    # WINDOW CLOSE
    # ==================================================================

    def closeEvent(self, event):

        try:
            from services.websocket_service import websocket_service

            websocket_service.disconnect_client()

        except Exception:
            pass

        self._cleanup_existing_viewer()

        super().closeEvent(event)