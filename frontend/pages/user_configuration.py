from __future__ import annotations

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSplitter,
    QVBoxLayout, QWidget, QInputDialog
)

from api.client import api_client


CONTEXT_TYPES = ["EMPLOYEE", "HOD", "DIRECTOR", "DS", "TSO", "ADMIN"]


def _list(data: Any, *keys: str) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


class UserFormDialog(QDialog):
    """Full AdminSuite user profile editor."""

    def __init__(
        self,
        user: Optional[Dict[str, Any]] = None,
        departments: Optional[List[Dict[str, Any]]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.user = user or {}
        self.editing = bool(user)
        self.departments = departments or []
        self.result_data: Dict[str, Any] = {}

        self.setWindowTitle("Edit User" if self.editing else "Create User")
        self.setMinimumWidth(520)

        self.username = QLineEdit(str(self.user.get("username") or ""))
        self.username.setReadOnly(self.editing)

        self.full_name = QLineEdit(str(self.user.get("full_name") or ""))
        self.employee_code = QLineEdit(str(self.user.get("employee_code") or ""))
        self.designation = QLineEdit(str(self.user.get("designation") or ""))
        self.email = QLineEdit(str(self.user.get("email") or ""))
        self.outlook_email = QLineEdit(str(self.user.get("outlook_email") or ""))
        self.gov_email = QLineEdit(str(self.user.get("gov_email") or ""))

        self.role = QComboBox()
        self.role.addItems(CONTEXT_TYPES)
        current_role = str(self.user.get("role") or "EMPLOYEE").upper()
        index = self.role.findText(current_role)
        if index >= 0:
            self.role.setCurrentIndex(index)

        self.department = QComboBox()
        self.department.addItem("None", None)
        for dept in self.departments:
            self.department.addItem(
                str(dept.get("name") or dept.get("code") or ""),
                dept.get("id"),
            )
        current_id = self.user.get("department_id")
        if current_id is not None:
            index = self.department.findData(current_id)
            if index >= 0:
                self.department.setCurrentIndex(index)
        elif self.user.get("department"):
            index = self.department.findText(str(self.user["department"]))
            if index >= 0:
                self.department.setCurrentIndex(index)

        self.status = QComboBox()
        self.status.addItems(["Active", "Inactive"])
        self.status.setCurrentIndex(0 if self.user.get("is_active", True) else 1)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Initial password (new users only)")
        if self.editing:
            self.password.setEnabled(False)

        form = QFormLayout()
        form.setSpacing(10)
        form.addRow("Username *", self.username)
        form.addRow("Full Name *", self.full_name)
        form.addRow("Employee Code", self.employee_code)
        form.addRow("Designation", self.designation)
        form.addRow("Primary Email", self.email)
        form.addRow("Outlook Email", self.outlook_email)
        form.addRow("Government / NIC Email", self.gov_email)
        form.addRow("Primary Role", self.role)
        form.addRow("Primary Department", self.department)
        form.addRow("Account Status", self.status)
        form.addRow("Initial Password", self.password)

        note = QLabel(
            "Work Contexts are managed separately below. A user's contexts are "
            "the authority used by the operational UI."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self):
        username = self.username.text().strip()
        full_name = self.full_name.text().strip()
        if not username or not full_name:
            QMessageBox.warning(self, "Required", "Username and Full Name are required.")
            return

        dept_name = self.department.currentText()
        self.result_data = {
            "username": username,
            "full_name": full_name,
            "employee_code": self.employee_code.text().strip() or None,
            "designation": self.designation.text().strip() or None,
            "email": self.email.text().strip() or None,
            "outlook_email": self.outlook_email.text().strip() or None,
            "gov_email": self.gov_email.text().strip() or None,
            "role": self.role.currentText(),
            "department_id": self.department.currentData(),
            "department_name": None if dept_name == "None" else dept_name,
            "is_active": self.status.currentText() == "Active",
        }
        if not self.editing:
            self.result_data["password"] = self.password.text().strip() or "cdtrs@123"
        self.accept()


class ContextDialog(QDialog):
    def __init__(self, departments: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Work Context")
        self.setMinimumWidth(420)

        self.context_type = QComboBox()
        self.context_type.addItems(CONTEXT_TYPES)

        self.department = QComboBox()
        self.department.addItem("None", None)
        for dept in departments:
            self.department.addItem(
                str(dept.get("name") or dept.get("code") or ""),
                dept.get("id"),
            )

        self.help = QLabel()
        self.help.setObjectName("muted")
        self.help.setWordWrap(True)
        self.context_type.currentTextChanged.connect(self._update_help)
        self._update_help(self.context_type.currentText())

        form = QFormLayout()
        form.addRow("Context Type", self.context_type)
        form.addRow("Department", self.department)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Save
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)
        layout.addLayout(form)
        layout.addWidget(self.help)
        layout.addWidget(buttons)

    def _update_help(self, context: str):
        if context in ("EMPLOYEE", "HOD"):
            self.help.setText("This context is department-scoped; choose a department.")
            self.department.setEnabled(True)
        elif context == "TSO":
            self.help.setText(
                "TSO is an organisation-level DS work context. Only one active TSO "
                "membership may exist system-wide."
            )
            self.department.setCurrentIndex(0)
            self.department.setEnabled(False)
        elif context in ("DS", "DIRECTOR", "ADMIN"):
            self.help.setText("This is an organisation-level context.")
            self.department.setCurrentIndex(0)
            self.department.setEnabled(False)

    def _validate(self):
        if self.context_type.currentText() in ("EMPLOYEE", "HOD") and self.department.currentData() is None:
            QMessageBox.warning(self, "Department required", "Choose a department for this context.")
            return
        self.accept()

    def values(self) -> Dict[str, Any]:
        return {
            "context_type": self.context_type.currentText(),
            "department_id": self.department.currentData(),
            "is_active": True,
        }


class UserConfigurationPage(QWidget):
    """Complete Admin user/profile/context management workspace."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("userConfigurationPage")
        self.users: List[Dict[str, Any]] = []
        self.departments: List[Dict[str, Any]] = []
        self.selected_user: Optional[Dict[str, Any]] = None

        title = QLabel("User Configuration")
        title.setObjectName("pageTitle")
        subtitle = QLabel(
            "Create, edit, activate, deactivate and manage work contexts for every user."
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search username, name or employee code…")
        self.search.textChanged.connect(self._render_users)

        self.role_filter = QComboBox()
        self.role_filter.addItems(["All Roles"] + CONTEXT_TYPES)
        self.role_filter.currentIndexChanged.connect(self._render_users)

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Status", "Active", "Inactive"])
        self.status_filter.currentIndexChanged.connect(self._render_users)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.load_data)

        add = QPushButton("+ Add User")
        add.setObjectName("primaryButton")
        add.clicked.connect(self._add_user)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(self.role_filter)
        toolbar.addWidget(self.status_filter)
        toolbar.addWidget(refresh)
        toolbar.addWidget(add)

        self.user_box = QWidget()
        self.user_layout = QVBoxLayout(self.user_box)
        self.user_layout.setContentsMargins(0, 0, 0, 0)
        self.user_layout.setSpacing(7)

        user_scroll = QScrollArea()
        user_scroll.setWidgetResizable(True)
        user_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        user_scroll.setMinimumWidth(340)
        user_scroll.setFrameShape(QFrame.Shape.NoFrame)
        user_scroll.setWidget(self.user_box)

        self.detail = QFrame()
        self.detail.setObjectName("detailCard")
        detail_layout = QVBoxLayout(self.detail)
        detail_layout.setContentsMargins(18, 18, 18, 18)
        detail_layout.setSpacing(10)

        self.detail_title = QLabel("Select a user")
        self.detail_title.setObjectName("sectionTitle")
        self.detail_meta = QLabel("User details will appear here.")
        self.detail_meta.setObjectName("muted")

        self.edit_btn = QPushButton("Edit Profile")
        self.edit_btn.clicked.connect(self._edit_selected)
        self.reset_btn = QPushButton("Reset Password")
        self.reset_btn.clicked.connect(self._reset_password)
        self.toggle_btn = QPushButton("Activate / Deactivate")
        self.toggle_btn.clicked.connect(self._toggle_user)

        button_row = QHBoxLayout()
        button_row.addWidget(self.edit_btn)
        button_row.addWidget(self.reset_btn)
        button_row.addWidget(self.toggle_btn)
        button_row.addStretch(1)

        contexts_title = QLabel("Work Contexts")
        contexts_title.setObjectName("sectionTitle")
        self.context_box = QWidget()
        self.context_layout = QVBoxLayout(self.context_box)
        self.context_layout.setContentsMargins(0, 0, 0, 0)
        self.context_layout.setSpacing(6)

        self.add_context_btn = QPushButton("+ Add Context")
        self.add_context_btn.setObjectName("primaryButton")
        self.add_context_btn.clicked.connect(self._add_context)

        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addLayout(button_row)
        detail_layout.addWidget(contexts_title)
        detail_layout.addWidget(self.context_box)
        detail_layout.addWidget(self.add_context_btn, 0, Qt.AlignmentFlag.AlignLeft)
        detail_layout.addStretch(1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(user_scroll)
        splitter.addWidget(self.detail)
        splitter.setSizes([350, 800])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        root.addWidget(title)
        root.addWidget(subtitle)
        root.addLayout(toolbar)
        root.addWidget(splitter, 1)

        self.setStyleSheet("""
            QWidget#userConfigurationPage { background: #f6f8fb; }
            QLabel#pageTitle { font-size: 23px; font-weight: 750; color: #172033; }
            QLabel#sectionTitle { font-size: 15px; font-weight: 700; color: #172033; }
            QLabel#muted { color: #667085; }
            QLineEdit, QComboBox {
                min-height: 35px; background: white; border: 1px solid #d0d5dd;
                border-radius: 8px; padding: 0 9px;
            }
            
            
            QPushButton#primaryButton { background: #2563eb; color: white; border-color: #2563eb; font-weight: 650; }
            QFrame#userCard, QFrame#detailCard, QFrame#contextCard {
                background: white; border: 1px solid #e4e7ec; border-radius: 10px;
            }
        """)

        self._set_detail(None)
        self.load_data()

    def _set_detail(self, user: Optional[Dict[str, Any]]):
        self.selected_user = user
        enabled = user is not None
        self.edit_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)
        self.toggle_btn.setEnabled(enabled)
        self.add_context_btn.setEnabled(enabled)

        while self.context_layout.count():
            item = self.context_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not user:
            self.detail_title.setText("Select a user")
            self.detail_meta.setText("Choose a user from the list.")
            return

        name = user.get("full_name") or user.get("username") or "User"
        status = "ACTIVE" if user.get("is_active", True) else "INACTIVE"
        self.detail_title.setText(name)
        self.detail_meta.setText(
            f"{user.get('username', '—')}  •  {user.get('employee_code') or 'No employee code'}  •  {status}\n"
            f"{user.get('designation') or 'No designation'}  •  {user.get('email') or 'No primary email'}"
        )

        contexts = user.get("context_memberships") or []
        if not contexts and user.get("contexts"):
            contexts = user["contexts"]

        if not contexts:
            label = QLabel("No active work contexts are configured.")
            label.setObjectName("muted")
            self.context_layout.addWidget(label)
            return

        for context in contexts:
            card = QFrame()
            card.setObjectName("contextCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 9, 12, 9)

            ctype = str(context.get("context_type") or context.get("context") or "UNKNOWN")
            dept = str(
                context.get("department_name")
                or context.get("department_code")
                or "Organisation"
            )
            label = QLabel(f"{ctype}  •  {dept}")
            label.setStyleSheet("font-weight: 650;")

            remove = QPushButton("Remove")
            remove.setProperty("membership_id", context.get("id"))
            remove.clicked.connect(
                lambda _, c=context: self._remove_context(c)
            )

            row.addWidget(label, 1)
            row.addWidget(remove)
            self.context_layout.addWidget(card)

    def load_data(self):
        try:
            self.users = _list(api_client.get("/admin/users"), "users", "items")
            self.departments = _list(
                api_client.get("/admin/departments"), "departments", "items"
            )
            self._render_users()
            if self.selected_user:
                fresh = next(
                    (u for u in self.users if u.get("id") == self.selected_user.get("id")),
                    None,
                )
                self._set_detail(fresh)
        except Exception as exc:
            QMessageBox.warning(self, "User Configuration", f"Unable to load users.\n\n{exc}")

    def _render_users(self):
        while self.user_layout.count():
            item = self.user_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self.search.text().strip().lower()
        role = self.role_filter.currentText()
        status = self.status_filter.currentText()

        rows = []
        for user in self.users:
            haystack = " ".join([
                str(user.get("username") or ""),
                str(user.get("full_name") or ""),
                str(user.get("employee_code") or ""),
            ]).lower()
            user_role = str(user.get("role") or "").upper()
            active = bool(user.get("is_active", True))

            if query and query not in haystack:
                continue
            if role != "All Roles" and user_role != role:
                continue
            if status == "Active" and not active:
                continue
            if status == "Inactive" and active:
                continue
            rows.append(user)

        for user in rows:
            card = QFrame()
            card.setObjectName("userCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(13, 10, 13, 10)

            info = QVBoxLayout()
            name = QLabel(str(user.get("full_name") or user.get("username") or "Unnamed"))
            name.setStyleSheet("font-weight: 700; color: #172033;")
            meta = QLabel(
                f"{user.get('username', '—')}  •  {user.get('role', '—')}  •  "
                f"{user.get('employee_code') or 'No code'}"
            )
            meta.setObjectName("muted")
            info.addWidget(name)
            info.addWidget(meta)

            state = QLabel("ACTIVE" if user.get("is_active", True) else "INACTIVE")
            state.setStyleSheet(
                "font-weight: 700; padding: 4px 8px; border-radius: 6px; "
                "background: #ecfdf3; color: #067647;"
                if user.get("is_active", True)
                else
                "font-weight: 700; padding: 4px 8px; border-radius: 6px; "
                "background: #fef3f2; color: #b42318;"
            )

            select = QPushButton("Manage")
            select.clicked.connect(lambda _, u=user: self._set_detail(u))

            row.addLayout(info, 1)
            row.addWidget(state)
            row.addWidget(select)
            self.user_layout.addWidget(card)

        self.user_layout.addStretch(1)

    def _add_user(self):
        dialog = UserFormDialog(departments=self.departments, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            api_client.post("/admin/users", json=dialog.result_data)
            QMessageBox.information(self, "User Created", "User created successfully.")
            self.load_data()
        except Exception as exc:
            QMessageBox.critical(self, "Create User Failed", str(exc))

    def _edit_selected(self):
        if not self.selected_user:
            return
        dialog = UserFormDialog(self.selected_user, self.departments, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            api_client.put(
                f"/admin/users/{self.selected_user['id']}",
                json=dialog.result_data,
            )
            QMessageBox.information(self, "User Updated", "User profile updated.")
            self.load_data()
        except Exception as exc:
            QMessageBox.critical(self, "Update User Failed", str(exc))

    def _reset_password(self):
        if not self.selected_user:
            return
        username = self.selected_user.get("username", "user")
        password, ok = QInputDialog.getText(
            self, "Reset Password", f"New password for {username}:",
            QLineEdit.EchoMode.Password
        )
        if not ok or not password.strip():
            return
        try:
            api_client.post(
                f"/admin/users/{self.selected_user['id']}/reset-password",
                json={"new_password": password.strip()},
            )
            QMessageBox.information(self, "Password Reset", "Password reset successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Password Reset Failed", str(exc))

    def _toggle_user(self):
        if not self.selected_user:
            return
        active = bool(self.selected_user.get("is_active", True))
        action = "deactivate" if active else "activate"
        if QMessageBox.question(
            self, "Confirm", f"Are you sure you want to {action} this account?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            # Backend toggles the current state; no client-side state is trusted.
            api_client.post(f"/admin/users/{self.selected_user['id']}/toggle-active")
            self.load_data()
        except Exception as exc:
            QMessageBox.critical(self, "Account Status Failed", str(exc))

    def _add_context(self):
        if not self.selected_user:
            return
        dialog = ContextDialog(self.departments, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            api_client.post(
                f"/admin/users/{self.selected_user['id']}/contexts",
                json=dialog.values(),
            )
            QMessageBox.information(self, "Context Added", "Work context added.")
            self.load_data()
        except Exception as exc:
            QMessageBox.critical(self, "Add Context Failed", str(exc))

    def _remove_context(self, context: Dict[str, Any]):
        membership_id = context.get("id")
        if membership_id is None or not self.selected_user:
            return
        if QMessageBox.question(
            self, "Remove Context",
            "Deactivate this work context membership?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            api_client.delete(
                f"/admin/users/{self.selected_user['id']}/contexts/{membership_id}"
            )
            self.load_data()
        except Exception as exc:
            QMessageBox.critical(self, "Remove Context Failed", str(exc))


AdminUserConfigurationPage = UserConfigurationPage
