from typing import Any, Dict, List
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QFont, QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QFrame,
    QHeaderView,
    QScrollArea
)
from api.client import api_client

class DepartmentDialog(QDialog):
    def __init__(self, department: Dict[str, Any] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Department" if department else "Add Department")
        self.setMinimumWidth(400)
        self.department = department or {}

        layout = QFormLayout(self)
        self.name_input = QLineEdit(self.department.get("name", ""))
        self.code_input = QLineEdit(self.department.get("code", ""))
        
        self.name_input.setStyleSheet("padding: 8px; border: 1px solid #d0d5dd; border-radius: 6px;")
        self.code_input.setStyleSheet("padding: 8px; border: 1px solid #d0d5dd; border-radius: 6px;")

        layout.addRow("Name:", self.name_input)
        layout.addRow("Code:", self.code_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return {
            "name": self.name_input.text().strip(),
            "code": self.code_input.text().strip(),
        }

class DepartmentConfigurationPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("departmentConfigurationPage")
        self.departments: List[Dict[str, Any]] = []

        # Top layout: Breadcrumb, Title, Add Button
        top_bar = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        
        breadcrumb = QLabel("Admin  >  Department Configuration")
        breadcrumb.setStyleSheet("color: #2563eb; font-size: 11px; font-weight: 500;")
        
        header_row = QHBoxLayout()
        icon_label = QLabel("👥")
        icon_label.setStyleSheet("background: #eff6ff; color: #2563eb; font-size: 20px; padding: 10px; border-radius: 12px;")
        
        title_text_layout = QVBoxLayout()
        title = QLabel("Department Configuration")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #111827;")
        subtitle = QLabel("Manage organizational departments and their details. Add, edit or deactivate departments as needed.")
        subtitle.setStyleSheet("color: #6b7280; font-size: 14px;")
        title_text_layout.addWidget(title)
        title_text_layout.addWidget(subtitle)
        
        header_row.addWidget(icon_label)
        header_row.addLayout(title_text_layout)
        header_row.addStretch()
        
        title_layout.addWidget(breadcrumb)
        title_layout.addLayout(header_row)

        add_btn = QPushButton("+ Add Department")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet("background: #2563eb; color: white; border-radius: 6px; padding: 10px 16px; font-weight: 600; font-size: 14px;")
        add_btn.clicked.connect(self._add)

        top_bar.addLayout(title_layout)
        top_bar.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Stat cards
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)
        
        self.total_card = self._create_stat_card("Total Departments", "0", "🏢", "#eff6ff", "#2563eb")
        self.active_card = self._create_stat_card("Active Departments", "0", "✅", "#f0fdf4", "#16a34a")
        self.inactive_card = self._create_stat_card("Inactive Departments", "0", "❌", "#fef2f2", "#dc2626")
        
        stats_layout.addWidget(self.total_card)
        stats_layout.addWidget(self.active_card)
        stats_layout.addWidget(self.inactive_card)

        # Filters and Table Container
        main_card = QFrame()
        main_card.setStyleSheet("background: white; border-radius: 12px; border: 1px solid #bfdbfe;")
        main_layout = QVBoxLayout(main_card)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(16)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(12)
        
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Search departments by name or code...")
        self.search.setStyleSheet("padding: 10px; border: 1px solid #d1d5db; border-radius: 8px; font-size: 14px; background: #f9fafb;")
        self.search.textChanged.connect(self._render)

        status_layout = QVBoxLayout()
        status_layout.setSpacing(4)
        status_label = QLabel("Status")
        status_label.setStyleSheet("color: #6b7280; font-size: 12px; font-weight: 600; border: none;")
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Active", "Inactive"])
        self.status_filter.setStyleSheet("padding: 8px; border: 1px solid #d1d5db; border-radius: 8px; background: white;")
        self.status_filter.currentIndexChanged.connect(self._render)
        status_layout.addWidget(status_label)
        status_layout.addWidget(self.status_filter)
        
        sort_layout = QVBoxLayout()
        sort_layout.setSpacing(4)
        sort_label = QLabel("Sort by")
        sort_label.setStyleSheet("color: #6b7280; font-size: 12px; font-weight: 600; border: none;")
        self.sort_filter = QComboBox()
        self.sort_filter.addItems(["Department Name", "Code"])
        self.sort_filter.setStyleSheet("padding: 8px; border: 1px solid #d1d5db; border-radius: 8px; background: white;")
        self.sort_filter.currentIndexChanged.connect(self._render)
        sort_layout.addWidget(sort_label)
        sort_layout.addWidget(self.sort_filter)

        clear_btn = QPushButton("Clear Filters")
        clear_btn.setStyleSheet("background: #f3f4f6; color: #374151; padding: 10px 16px; border-radius: 8px; font-weight: 600; border: none;")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_filters)

        toolbar.addWidget(self.search, 1)
        toolbar.addLayout(status_layout)
        toolbar.addLayout(sort_layout)
        toolbar.addWidget(clear_btn, 0, Qt.AlignmentFlag.AlignBottom)

        self.table = QTableWidget(0, 5)
        self.table.setShowGrid(False)
        self.table.setHorizontalHeaderLabels(["#", "Department Name", "Code", "Status", "Actions"])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 280)
        
        self.table.setStyleSheet('''
            QTableWidget {
                border: none;
                background: white;
                gridline-color: transparent;
            }
            QHeaderView::section {
                background-color: #f9fafb;
                color: #374151;
                font-weight: 700;
                font-size: 11px;
                border: none;
                border-bottom: 1px solid #e5e7eb;
                padding: 12px 8px;
                text-align: left;
            }
            QTableWidget::item {
                border-bottom: 1px solid #f3f4f6;
                padding: 12px 8px;
                color: #111827;
                font-size: 14px;
            }
            QTableWidget::item:alternate {
                background-color: #fafafa;
            }
        ''')

        main_layout.addLayout(toolbar)
        main_layout.addWidget(self.table, 1)
        
        # Pagination footer
        footer_layout = QHBoxLayout()
        self.pagination_label = QLabel("Showing 0 departments")
        self.pagination_label.setStyleSheet("color: #6b7280; font-size: 11px; border: none;")
        
        page_controls = QHBoxLayout()
        page_controls.setSpacing(4)
        prev_btn = QPushButton("<")
        prev_btn.setFixedSize(32, 32)
        prev_btn.setStyleSheet("border: 1px solid #bfdbfe; border-radius: 6px; background: white; color: #6b7280;")
        page_1 = QPushButton("1")
        page_1.setFixedSize(32, 32)
        page_1.setStyleSheet("border: none; border-radius: 6px; background: #2563eb; color: white; font-weight: bold;")
        next_btn = QPushButton(">")
        next_btn.setFixedSize(32, 32)
        next_btn.setStyleSheet("border: 1px solid #bfdbfe; border-radius: 6px; background: white; color: #6b7280;")
        
        page_controls.addWidget(prev_btn)
        page_controls.addWidget(page_1)
        page_controls.addWidget(next_btn)
        
        footer_layout.addWidget(self.pagination_label)
        footer_layout.addStretch()
        footer_layout.addLayout(page_controls)
        
        main_layout.addLayout(footer_layout)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)
        root.addLayout(top_bar)
        root.addLayout(stats_layout)
        root.addWidget(main_card, 1)

        self.setStyleSheet("QWidget#departmentConfigurationPage { background: #f3f4f6; }")

        self.load_departments()

    def _create_stat_card(self, title, value, icon, bg_color, icon_color):
        card = QFrame()
        card.setStyleSheet(f"background: white; border-radius: 12px; border: 1px solid #bfdbfe;")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"background: {bg_color}; color: {icon_color}; font-size: 20px; padding: 10px; border-radius: 12px; border: none;")
        
        text_layout = QVBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #6b7280; font-size: 11px; font-weight: 500; border: none;")
        val_lbl = QLabel(value)
        val_lbl.setObjectName("statValue")
        val_lbl.setStyleSheet("color: #111827; font-size: 22px; font-weight: 700; border: none;")
        
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(val_lbl)
        
        layout.addWidget(icon_lbl)
        layout.addSpacing(12)
        layout.addLayout(text_layout)
        layout.addStretch()
        return card

    def _update_stat_card(self, card, value):
        lbl = card.findChild(QLabel, "statValue")
        if lbl:
            lbl.setText(str(value))

    def _clear_filters(self):
        self.search.clear()
        self.status_filter.setCurrentIndex(0)
        self.sort_filter.setCurrentIndex(0)

    def load_departments(self):
        try:
            response = api_client.get("/admin/departments")
            self.departments = response if isinstance(response, list) else response.get("departments", {}).get("items", [])
            self._render()
        except Exception as exc:
            QMessageBox.warning(self, "Departments", f"Unable to load departments.\n\n{exc}")

    def _render(self):
        query = self.search.text().strip().lower()
        filter_value = self.status_filter.currentText()
        sort_val = self.sort_filter.currentText()

        rows = []
        active_count = 0
        for dept in self.departments:
            active = bool(dept.get("is_active", True))
            if active: active_count += 1
            
            text = f"{dept.get('name', '')} {dept.get('code', '')}".lower()

            if query and query not in text:
                continue
            if filter_value == "Active" and not active:
                continue
            if filter_value == "Inactive" and active:
                continue
            rows.append(dept)

        if sort_val == "Department Name":
            rows.sort(key=lambda x: str(x.get("name", "")).lower())
        else:
            rows.sort(key=lambda x: str(x.get("code", "")).lower())

        self._update_stat_card(self.total_card, len(self.departments))
        self._update_stat_card(self.active_card, active_count)
        self._update_stat_card(self.inactive_card, len(self.departments) - active_count)

        self.pagination_label.setText(f"Showing 1-{len(rows)} of {len(self.departments)} departments")

        self.table.setRowCount(len(rows))
        for r, dept in enumerate(rows):
            name = str(dept.get("name") or "Unnamed Department")
            code = str(dept.get("code") or "—")
            active = bool(dept.get("is_active", True))

            # #
            num_item = QTableWidgetItem(str(r + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 0, num_item)
            
            # Name
            name_item = QTableWidgetItem(name)
            name_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
            self.table.setItem(r, 1, name_item)
            
            # Code
            self.table.setItem(r, 2, QTableWidgetItem(code))
            
            # Status Pill
            status_widget = QWidget()
            status_layout = QHBoxLayout(status_widget)
            status_layout.setContentsMargins(0, 0, 0, 0)
            status_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            
            pill = QLabel(f"{'●' if active else '●'} {'Active' if active else 'Inactive'}")
            if active:
                pill.setStyleSheet("background: #dcfce7; color: #166534; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 12px;")
            else:
                pill.setStyleSheet("background: #fee2e2; color: #991b1b; padding: 4px 10px; border-radius: 12px; font-weight: 600; font-size: 12px;")
            status_layout.addWidget(pill)
            self.table.setCellWidget(r, 3, status_widget)
            
            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(0, 0, 0, 0)
            actions_layout.setSpacing(8)
            actions_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            
            edit_btn = QPushButton("✏️ Edit")
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setStyleSheet("background: transparent; color: #2563eb; font-weight: 600; border: 1px solid #bfdbfe; border-radius: 6px; padding: 4px 12px;")
            edit_btn.clicked.connect(lambda _, d=dept: self._action("edit", d))
            
            toggle_text = "🚫 Deactivate" if active else "✅ Activate"
            toggle_color = "#dc2626" if active else "#16a34a"
            toggle_border = "#fecaca" if active else "#bbf7d0"
            dots_btn = QPushButton(toggle_text)
            dots_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            dots_btn.setStyleSheet(f"background: transparent; color: {toggle_color}; font-weight: 600; border: 1px solid {toggle_border}; border-radius: 6px; padding: 4px 12px;")
            dots_btn.clicked.connect(lambda _, d=dept: self._action("toggle", d))
            
            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(dots_btn)
            self.table.setCellWidget(r, 4, actions_widget)
        
        self.table.verticalHeader().setDefaultSectionSize(54)

    def _add(self):
        dialog = DepartmentDialog(parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            api_client.post("/admin/departments", json=dialog.values())
            self.load_departments()
        except Exception as exc:
            QMessageBox.critical(self, "Add Department Failed", str(exc))

    def _action(self, action: str, dept: Dict[str, Any]):
        dept_id = dept.get("id")
        if dept_id is None:
            return

        if action == "edit":
            dialog = DepartmentDialog(dept, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            payload = dialog.values()
        else:
            active = bool(dept.get("is_active", True))
            target = "deactivate" if active else "activate"
            name = dept.get("name") or "this department"
            result = QMessageBox.question(self, "Confirm", f"Are you sure you want to {target} {name}?")
            if result != QMessageBox.StandardButton.Yes:
                return
            payload = {"is_active": not active}

        try:
            api_client.put(f"/admin/departments/{dept_id}", json=payload)
            self.load_departments()
        except Exception as exc:
            QMessageBox.critical(self, "Update Failed", str(exc))

AdminDepartmentConfigurationPage = DepartmentConfigurationPage
