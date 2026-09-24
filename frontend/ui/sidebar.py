from __future__ import annotations

from typing import Any, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from models.enums import RoleEnum
from core.context.context_manager import context_manager
from core.navigation.navigation_registry import NavigationRegistry


class Sidebar(QFrame):
    """
    CDTRS context-aware sidebar.

    The selected WorkContextMembership is the user's active operational
    context. Changing it must change the API request context, the sidebar
    navigation, and the landing dashboard.

    This sidebar intentionally does NOT treat the user's permanent UserRole
    as the active workspace. A user may, for example, have Employee and HOD
    memberships and switch between them.
    """

    page_requested = Signal(str)
    logout_requested = Signal()
    context_switch_requested = Signal(int)

    # Existing compatibility signals used by older MainWindow/page code.
    department_context_changed = Signal(str)
    role_context_changed = Signal(str)

    def __init__(self, role: str = "", username: str = ""):
        super().__init__()

        self.username = username
        self._fallback_role = RoleEnum.normalize(role) or RoleEnum.EMPLOYEE.value
        self._context_switching = False
        self._active_context: Optional[Any] = None

        # Prefer ContextManager state, but do not fail when it has not yet
        # been populated after login.
        active = self._safe_active_context()
        self.role = self._context_role(active) if active is not None else self._fallback_role
        self._active_context = active

        self.setObjectName("sidebar")
        # Keep the sidebar compact on small laptop screens while allowing it
        # to breathe slightly on larger office monitors.  Do not use a fixed
        # width: the main content area must remain responsive.
        self.setMinimumWidth(200)
        self.setMaximumWidth(280)

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(12, 14, 12, 14)
        self.layout.setSpacing(5)

        title = QLabel("CDTRS")
        title.setObjectName("sidebarTitle")
        self.layout.addWidget(title)

        self.user_label = QLabel()
        self.user_label.setObjectName("sidebarUser")
        self.user_label.setWordWrap(True)
        self.layout.addWidget(self.user_label)
        self.layout.addSpacing(5)

        # Always show the workspace selector. Previously it was only created
        # when ContextManager happened to contain >1 contexts at construction.
        self.context_label = QLabel("🔐 Active Workspace")
        self.context_label.setObjectName("contextLabel")
        self.context_label.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #94A3B8; padding-top: 2px;"
        )
        self.layout.addWidget(self.context_label)

        self.context_selector = QComboBox()
        self.context_selector.setObjectName("contextSelector")
        self.context_selector.setMinimumHeight(34)
        self.context_selector.setSizeAdjustPolicy(
            QComboBox.AdjustToContentsOnFirstShow
        )
        self.context_selector.setToolTip(
            "Select your active work context. Navigation, dashboard and API data scope follow this selection."
        )
        self.context_selector.setStyleSheet(
            """
            QComboBox {
                background-color: #1E293B;
                color: #38BDF8;
                border: 1px solid #334155;
                padding: 7px 9px;
                border-radius: 5px;
                font-size: 11px;
                font-weight: 600;
            }
            QComboBox:hover { border: 1px solid #38BDF8; }
            QComboBox:focus { border: 1px solid #38BDF8; }
            QComboBox::drop-down { border: none; width: 26px; }
            QComboBox QAbstractItemView {
                background-color: #1E293B;
                color: #FFFFFF;
                selection-background-color: #334155;
                selection-color: #38BDF8;
            }
            """
        )
        self.context_selector.currentIndexChanged.connect(self._handle_context_changed)
        self.layout.addWidget(self.context_selector)
        self.layout.addSpacing(5)

        self.buttons = {}
        self._navigation_anchor = None

        # Navigation is inserted before this stretch item.
        self.layout.addStretch()

        self.logout_button = QPushButton("Logout")
        self.logout_button.setObjectName("logoutButton")
        self.logout_button.clicked.connect(self.logout_requested.emit)
        self.layout.addWidget(self.logout_button)

        self.setLayout(self.layout)
        self._build_menu()

        try:
            context_manager.active_context_changed.connect(self._handle_active_context_changed)
        except Exception:
            pass

        # Populate from the authoritative /auth/contexts endpoint when the
        # ContextManager was constructed before login/context loading.
        self.refresh_contexts()

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _context_id(context: Any) -> Optional[int]:
        value = context.get("id") if isinstance(context, dict) else getattr(context, "id", None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _context_value(context: Any, key: str, default: Any = None) -> Any:
        if isinstance(context, dict):
            return context.get(key, default)
        return getattr(context, key, default)

    def _context_role(self, context: Any) -> str:
        raw = self._context_value(context, "context_type", None)
        return RoleEnum.normalize(raw or self._fallback_role) or RoleEnum.EMPLOYEE.value

    def _context_department(self, context: Any) -> str:
        return str(
            self._context_value(context, "department_name", None)
            or self._context_value(context, "department", None)
            or ""
        ).strip()

    def _context_label(self, context: Any) -> str:
        display = self._context_value(context, "display_label", None)
        if display:
            return str(display)

        context_type = str(self._context_value(context, "context_type", "Workspace") or "Workspace")
        department = self._context_department(context)
        if department:
            return f"{context_type} • {department}"
        return context_type

    def _safe_contexts(self):
        """Return contexts from the single frontend context authority.

        ContextManager is responsible for loading/switching work contexts.
        Sidebar must not reach into a repository directly, because doing so
        can create a second context state that disagrees with MainWindow.
        """
        try:
            return list(context_manager.contexts() or [])
        except Exception:
            return []

    def _safe_active_context(self):
        try:
            context = context_manager.active_context()
            if context is not None:
                return context
        except Exception:
            pass

        contexts = self._safe_contexts()
        try:
            active_id = context_manager.active_membership_id()
        except Exception:
            active_id = None

        if active_id is not None:
            for context in contexts:
                if self._context_id(context) == int(active_id):
                    return context

        for context in contexts:
            if bool(self._context_value(context, "is_active", False)) or bool(self._context_value(context, "active", False)):
                return context
        return contexts[0] if contexts else None

    def refresh_contexts(self) -> None:
        """Reload all memberships and keep the current selection visible."""
        contexts = self._safe_contexts()

        self.context_selector.blockSignals(True)
        try:
            self.context_selector.clear()
            for context in contexts:
                context_id = self._context_id(context)
                if context_id is None:
                    continue
                self.context_selector.addItem(self._context_label(context), context_id)

            active = self._safe_active_context()
            active_id = self._context_id(active) if active is not None else None
            if active_id is not None:
                index = self.context_selector.findData(active_id)
                if index >= 0:
                    self.context_selector.setCurrentIndex(index)

            # A single context remains visible but is disabled because there
            # is nothing to switch to. Multiple contexts remain fully active.
            self.context_selector.setEnabled(len(contexts) > 1)
            if not contexts:
                self.context_selector.addItem("No work context loaded", None)
                self.context_selector.setEnabled(False)
            elif len(contexts) == 1:
                self.context_selector.setToolTip("Only one active work context is available.")
            else:
                self.context_selector.setToolTip("Select a work context to change dashboard, navigation and data scope.")
        finally:
            self.context_selector.blockSignals(False)

        active = self._safe_active_context()
        if active is not None:
            self._active_context = active
            self.role = self._context_role(active)
        self._refresh_context_display()
        self._build_menu()

    # ------------------------------------------------------------------
    # Context switching
    # ------------------------------------------------------------------

    def _handle_context_changed(self, index: int) -> None:
        """Request a context switch; MainWindow/ContextManager performs it."""
        if self._context_switching or index < 0:
            return

        context_id = self.context_selector.itemData(index)
        if context_id is None:
            return
        try:
            context_id = int(context_id)
        except (TypeError, ValueError):
            return

        current_id = self._context_id(self._active_context)
        if current_id == context_id:
            return

        # ContextManager is the single authority for switching. MainWindow
        # listens to this signal and calls context_manager.switch_context(),
        # which changes X-Work-Context-Id and emits active_context_changed.
        self._context_switching = True
        try:
            self.context_switch_requested.emit(context_id)
        finally:
            self._context_switching = False

    def _sync_context_objects(self, selected_id: int) -> None:
        """Deprecated compatibility hook; ContextManager owns active state."""
        return None

    def apply_context(self, context) -> None:
        """Apply a context already confirmed by ContextManager."""
        old_role = self.role
        self._active_context = context
        self.role = self._context_role(context)

        # Contexts may have been loaded after Sidebar construction.
        self.refresh_contexts()
        self._refresh_context_display()

        department = self._context_department(context)
        if department:
            self.department_context_changed.emit(department)
        if old_role != self.role:
            self.role_context_changed.emit(self.role)

    def _handle_active_context_changed(self, context=None) -> None:
        """Follow a context change confirmed by ContextManager."""
        active = context or self._safe_active_context()
        if active is not None:
            self.apply_context(active)
        else:
            self.refresh_contexts()

    def _sync_context_selector(self) -> None:
        if self.context_selector.count() == 0:
            return
        active_id = self._context_id(self._active_context)
        if active_id is None:
            return
        index = self.context_selector.findData(active_id)
        if index >= 0 and index != self.context_selector.currentIndex():
            self.context_selector.blockSignals(True)
            try:
                self.context_selector.setCurrentIndex(index)
            finally:
                self.context_selector.blockSignals(False)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        """Rebuild navigation strictly from the active context."""
        for button in list(self.buttons.values()):
            self.layout.removeWidget(button)
            button.deleteLater()
        self.buttons.clear()

        context_type = self._context_role(self._active_context)
        try:
            items = NavigationRegistry.get_menu(context_type)
        except Exception:
            items = []

        for page_key in items:
            button = QPushButton(str(page_key))
            button.setObjectName("sidebarButton")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, key=str(page_key):
                    self.page_requested.emit(key)
            )
            self.buttons[str(page_key)] = button

            # The stretch and Logout button are always the last two layout
            # items, so navigation is inserted immediately before them.
            self.layout.insertWidget(
                max(0, self.layout.count() - 2),
                button,
            )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _refresh_context_display(self) -> None:
        context = self._active_context or self._safe_active_context()
        display_role = self.role

        if context is not None:
            context_type = str(self._context_value(context, "context_type", None) or display_role)
            department = self._context_department(context)
            display_role = f"{context_type} • {department}" if department else context_type

        if self.username:
            self.user_label.setText(f"{self.username}\n{display_role}")
        else:
            self.user_label.setText(display_role)

    def _show_switch_error(self, message: str) -> None:
        # Keep Sidebar free of QMessageBox/UI policy. MainWindow receives the
        # role/context signal and can surface errors centrally if desired.
        self.context_label.setText(f"🔐 Active Workspace  •  {message}")

    def set_active(self, active_item: str) -> None:
        for item, button in self.buttons.items():
            if item == active_item:
                button.setStyleSheet(
                    """
                    background-color: #1E293B;
                    color: #FFFFFF;
                    font-weight: 600;
                    border-radius: 5px;
                    padding: 7px 10px;
                    """
                )
            else:
                button.setStyleSheet("")

    def get_menu_items(self, role: str):
        """Return canonical navigation labels for a context type."""
        normalized = RoleEnum.normalize(role) or self._fallback_role
        return NavigationRegistry.get_menu(normalized)
