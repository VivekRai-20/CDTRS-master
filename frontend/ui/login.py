from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame,
    QPushButton,
    QMessageBox
)
from PySide6.QtCore import Qt
from services.auth_service import authenticate, auth_service
from ui.main_window import MainWindow


class ResetPasswordDialog(QDialog):
    """Dialog allowing users to change their account password from the login screen with current password verification."""

    def __init__(self, default_username: str = "", parent: QWidget = None):
        super().__init__(parent)
        self.setWindowTitle("Change Password")
        # Responsive dialog: bounded rather than fixed so it remains usable
        # with Windows display scaling and different monitor sizes.
        self.setMinimumSize(360, 360)
        self.resize(420, 430)
        self.setMaximumSize(520, 520)
        self.setModal(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(10)

        title = QLabel("Change Account Password")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1E3A8A;")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Verify your current password to set a new password.")
        subtitle.setStyleSheet("color: #64748B; font-size: 12px;")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(5)

        # Username
        u_label = QLabel("Username")
        u_label.setStyleSheet("font-weight: 600; color: #334155; font-size: 12px;")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        if default_username:
            self.username_input.setText(default_username)
        layout.addWidget(u_label)
        layout.addWidget(self.username_input)

        # Current Password
        old_p_label = QLabel("Current Password")
        old_p_label.setStyleSheet("font-weight: 600; color: #334155; font-size: 12px;")
        self.old_password_input = QLineEdit()
        self.old_password_input.setPlaceholderText("Enter current password")
        self.old_password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(old_p_label)
        layout.addWidget(self.old_password_input)

        # New Password
        p_label = QLabel("New Password")
        p_label.setStyleSheet("font-weight: 600; color: #334155; font-size: 12px;")
        self.new_password_input = QLineEdit()
        self.new_password_input.setPlaceholderText("Enter new password (min 4 characters)")
        self.new_password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(p_label)
        layout.addWidget(self.new_password_input)

        # Confirm Password
        cp_label = QLabel("Confirm New Password")
        cp_label.setStyleSheet("font-weight: 600; color: #334155; font-size: 12px;")
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setPlaceholderText("Re-enter new password")
        self.confirm_password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(cp_label)
        layout.addWidget(self.confirm_password_input)

        layout.addSpacing(8)

        # Button row
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #E2E8F0;
                color: #334155;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #CBD5E1;
            }
        """)
        cancel_btn.clicked.connect(self.reject)

        self.submit_btn = QPushButton("Update Password")
        self.submit_btn.setStyleSheet("""
            QPushButton {
                background: #2563EB;
                color: white;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #1D4ED8;
            }
        """)
        self.submit_btn.clicked.connect(self._handle_reset)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(self.submit_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _handle_reset(self):
        username = self.username_input.text().strip()
        old_pwd = self.old_password_input.text()
        new_pwd = self.new_password_input.text()
        confirm_pwd = self.confirm_password_input.text()

        if not username:
            QMessageBox.warning(self, "Validation Error", "Please enter your username.")
            self.username_input.setFocus()
            return

        if not old_pwd:
            QMessageBox.warning(self, "Validation Error", "Please enter your current password.")
            self.old_password_input.setFocus()
            return

        if not new_pwd:
            QMessageBox.warning(self, "Validation Error", "Please enter a new password.")
            self.new_password_input.setFocus()
            return

        if len(new_pwd) < 4:
            QMessageBox.warning(self, "Validation Error", "New password must be at least 4 characters long.")
            self.new_password_input.setFocus()
            return

        if new_pwd == old_pwd:
            QMessageBox.warning(self, "Validation Error", "New password must be different from current password.")
            self.new_password_input.setFocus()
            return

        if new_pwd != confirm_pwd:
            QMessageBox.warning(self, "Validation Error", "New password and confirmation do not match.")
            self.confirm_password_input.setFocus()
            return

        try:
            success = auth_service.reset_password(username, old_pwd, new_pwd)
            if success:
                QMessageBox.information(
                    self,
                    "Password Updated",
                    f"Password for user '{username}' has been updated successfully.\nYou can now log in with your new password."
                )
                self.accept()
            else:
                QMessageBox.warning(
                    self,
                    "Update Failed",
                    f"Could not update password for user '{username}'. Please verify your username and current password."
                )
        except Exception as ex:
            error_msg = str(ex)
            if "Current password does not match" in error_msg or "400" in error_msg:
                QMessageBox.critical(
                    self,
                    "Authentication Failed",
                    "The current password you entered is incorrect. Please try again."
                )
                self.old_password_input.clear()
                self.old_password_input.setFocus()
            elif "404" in error_msg or "not found" in error_msg.lower():
                QMessageBox.critical(
                    self,
                    "User Not Found",
                    f"User '{username}' was not found in the database."
                )
                self.username_input.setFocus()
            else:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to update password:\n\n{error_msg}"
                )


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setMinimumSize(520, 420)
        self.resize(760, 560)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(8)
        main_layout.setAlignment(Qt.AlignCenter)

        # Login card
        card = QFrame()
        card.setObjectName("loginCard")
        # Fixed width caused excessive empty space on some screens and
        # cramped layouts on others.  Bound the card instead.
        card.setMinimumWidth(320)
        card.setMaximumWidth(460)
        card.setSizePolicy(
            __import__("PySide6.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Preferred,
            __import__("PySide6.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Maximum,
        )

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(9)

        # Title
        title = QLabel("CDTRS")
        title.setObjectName("loginTitle")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("Centralised Document Tracking and Routing System")
        subtitle.setObjectName("loginSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)

        username_label = QLabel("Username")
        username_label.setStyleSheet("font-weight: 600; color: #334155;")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")

        password_label = QLabel("Password")
        password_label.setStyleSheet("font-weight: 600; color: #334155;")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.login)

        self.login_button = QPushButton("Login")
        self.login_button.clicked.connect(self.login)

        # Change Password Link Button
        self.forgot_btn = QPushButton("Change Password")
        self.forgot_btn.setCursor(Qt.PointingHandCursor)
        self.forgot_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #2563EB;
                border: none;
                font-size: 12px;
                font-weight: 500;
                padding: 4px;
            }
            QPushButton:hover {
                color: #1D4ED8;
                text-decoration: underline;
            }
        """)
        self.forgot_btn.clicked.connect(self.open_reset_password_dialog)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addSpacing(10)

        card_layout.addWidget(username_label)
        card_layout.addWidget(self.username_input)

        card_layout.addWidget(password_label)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(6)

        card_layout.addWidget(self.login_button)
        card_layout.addWidget(self.forgot_btn, alignment=Qt.AlignCenter)
        card.setLayout(card_layout)

        main_layout.addWidget(card)
        self.setLayout(main_layout)

    def open_reset_password_dialog(self):
        current_username = self.username_input.text().strip()
        dialog = ResetPasswordDialog(default_username=current_username, parent=self)
        if dialog.exec() == QDialog.Accepted:
            # Pre-fill username and focus on password
            if dialog.username_input.text().strip():
                self.username_input.setText(dialog.username_input.text().strip())
                self.password_input.clear()
                self.password_input.setFocus()

    def login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username or not password:
            QMessageBox.warning(self, "Input Required", "Please enter both username and password.")
            return

        try:
            user = authenticate(username, password)
        except Exception as ex:
            QMessageBox.critical(
                self,
                "Connection Error",
                f"Could not connect to the backend server:\n\n{str(ex)}\n\nPlease ensure the backend server is running or check the API URL in config/settings.py."
            )
            return

        if user:
            print("Login Successful")
            print("Username:", user["username"])
            print("Role:", user["role"])

            self.main_window = MainWindow(
                user["username"],
                user["role"]
            )

            self.main_window.show()
            self.close()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password. Please try again.")
