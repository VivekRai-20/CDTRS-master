"""Workflow dialogs.

Routing is multi-target by design: one dialog, as many recipients as the DS
needs, all opened as independent workstreams in a single action.  Assignment
always produces one work item per person.  Progress is free text - there is
no percentage field anywhere in this file, and none should be added.
"""

from datetime import date
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from models import BranchModel, DocumentModel, WorkItemModel
from models.enums import WorkStageEnum
from repositories.provider import get_repository


# ===========================================================================
# SHARED CHROME
# ===========================================================================

class _BaseDialog(QDialog):
    def __init__(self, title: str, subtitle: str = "", parent: Optional[QWidget] = None, width: int = 620):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.setModal(True)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(22, 18, 22, 18)
        self._root.setSpacing(12)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 15px; font-weight: 700; color: #0F172A;")
        self._root.addWidget(heading)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setWordWrap(True)
            sub.setStyleSheet("color: #64748B; font-size: 11px;")
            self._root.addWidget(sub)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #E2E8F0;")
        self._root.addWidget(line)

    def add_buttons(self, ok_text: str = "Confirm") -> QDialogButtonBox:
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        box.button(QDialogButtonBox.StandardButton.Ok).setText(ok_text)
        box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            "background-color: #0F172A; color: white; font-weight: 600; padding: 7px 18px; border-radius: 4px;"
        )
        box.accepted.connect(self._on_accept)
        box.rejected.connect(self.reject)
        self._root.addWidget(box)
        self._button_box = box
        return box

    def _on_accept(self) -> None:
        self.accept()

    @staticmethod
    def warn(parent, title: str, message: str) -> None:
        QMessageBox.warning(parent, title, message)


def _date_edit(initial: Optional[str] = None) -> QDateEdit:
    widget = QDateEdit()
    widget.setCalendarPopup(True)
    widget.setDisplayFormat("yyyy-MM-dd")
    widget.setDate(QDate.currentDate().addDays(7))
    if initial:
        parsed = QDate.fromString(str(initial)[:10], "yyyy-MM-dd")
        if parsed.isValid():
            widget.setDate(parsed)
    return widget


# ===========================================================================
# ROUTING - open one or many workstreams at once
# ===========================================================================

class RoutingDialog(_BaseDialog):
    """DS routing.

    Add a row per recipient.  An HOD, a direct employee and the TSO can all be
    added in one go; they become separate workstreams that then progress
    independently and can sit at completely different stages.
    """

    BRANCH_CHOICES = [
        ("Director - review & remark", "DIRECTOR"),
        ("Department HOD", "DEPARTMENT"),
        ("Employee (direct, no HOD)", "EMPLOYEE"),
        ("TSO", "TSO"),
    ]

    def __init__(self, document: DocumentModel, parent: Optional[QWidget] = None):
        super().__init__(
            "Route Document",
            "Add every recipient this document needs. Each becomes its own workstream "
            "and they run independently - one can finish while another is still in progress.",
            parent,
            width=760,
        )
        self.document = document
        self.rows: List[Dict[str, Any]] = []
        
        if getattr(self.document, 'is_director_instruction', False) and not self.document.director_reviews:
            self.BRANCH_CHOICES = [
                ("Director - review & remark", "DIRECTOR"),
            ]
        else:
            self.BRANCH_CHOICES = [
                ("Director - review & remark", "DIRECTOR"),
                ("Department HOD", "DEPARTMENT"),
                ("Employee (direct, no HOD)", "EMPLOYEE"),
                ("TSO", "TSO"),
            ]

        self._departments = []
        self._employees_by_dept: Dict[int, List[Any]] = {}
        self._directors = []
        try:
            repo = get_repository()
            self._departments = repo.get_departments()
            self._directors = repo.get_users(context_type="DIRECTOR")
        except Exception:
            pass

        self._build()

    def _build(self) -> None:
        if self.document.latest_director_remark:
            hint = QLabel(f"Latest Director remark: “{self.document.latest_director_remark}”")
            hint.setWordWrap(True)
            hint.setStyleSheet(
                "background-color: #F5F3FF; border-left: 3px solid #7C3AED; padding: 8px 10px; "
                "color: #4C1D95; font-size: 11px; border-radius: 3px;"
            )
            self._root.addWidget(hint)

        if self.document.suggested_department_name:
            confidence = int((self.document.routing_confidence or 0) * 100)
            sugg = QLabel(
                f"Suggestion ({confidence}% confidence): {self.document.suggested_department_name}"
                + (f" - {self.document.routing_reason}" if self.document.routing_reason else "")
            )
            sugg.setWordWrap(True)
            sugg.setStyleSheet("color: #475569; font-size: 11px; font-style: italic;")
            self._root.addWidget(sugg)

        self._build_ranked_departments()

        self.rows_area = QScrollArea()
        self.rows_area.setWidgetResizable(True)
        self.rows_area.setFrameShape(QFrame.Shape.NoFrame)
        self.rows_area.setMinimumHeight(240)

        self.rows_host = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(8)
        self.rows_layout.addStretch()
        self.rows_area.setWidget(self.rows_host)
        self._root.addWidget(self.rows_area)

        add_row = QHBoxLayout()
        add_btn = QPushButton("+ Add recipient")
        add_btn.setStyleSheet(
            "background-color: #F8FAFC; color: #0F172A; border: 1px dashed #94A3B8; "
            "font-weight: 600; padding: 7px 14px; border-radius: 4px;"
        )
        add_btn.clicked.connect(lambda: self._add_row())
        add_row.addWidget(add_btn)
        add_row.addStretch()
        self._root.addLayout(add_row)

        self.add_buttons("Route Document")
        self._add_row(prefill=True)

    # ---- OCR department ranking (advisory) ----

    def _ranked_choices(self) -> List[Dict[str, Any]]:
        """Departments ranked by how well they match the document text."""
        names_by_id = {d.id: d.name for d in self._departments}
        ids_by_name = {d.name: d.id for d in self._departments}
        choices: List[Dict[str, Any]] = []
        seen = set()
        for item in getattr(self.document, "ranked_departments", None) or []:
            dept_id = item.get("department_id") or ids_by_name.get(item.get("department"))
            if dept_id not in names_by_id or dept_id in seen:
                continue
            try:
                score = float(item.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            seen.add(dept_id)
            choices.append({"id": dept_id, "name": names_by_id[dept_id], "score": score})
        choices.sort(key=lambda c: c["score"], reverse=True)
        return choices

    def _build_ranked_departments(self) -> None:
        if not any(value == "DEPARTMENT" for _, value in self.BRANCH_CHOICES):
            return
        choices = self._ranked_choices()[:5]
        if not choices:
            return

        box = QFrame()
        box.setStyleSheet(
            "QFrame { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 5px; }"
        )
        layout = QVBoxLayout(box)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)
        caption = QLabel("Best matching departments (from the document text) - click one to send it there:")
        caption.setWordWrap(True)
        caption.setStyleSheet("color: #475569; font-size: 11px; border: none;")
        layout.addWidget(caption)

        chips = QGridLayout()
        chips.setHorizontalSpacing(6)
        chips.setVerticalSpacing(6)
        for i, choice in enumerate(choices):
            pct = max(0, min(100, round(choice["score"] * 100)))
            # "&" would be read as a keyboard mnemonic in button text.
            chip = QPushButton(f"{choice['name'].replace('&', '&&')}   {pct}%")
            chip.setToolTip("Semantic match score from OCR. Advisory only.")
            chip.setMinimumHeight(28)
            chip.setStyleSheet(
                "QPushButton { background-color: #FFFFFF; color: #0F172A; border: 1px solid #CBD5E1; "
                "border-radius: 12px; padding: 4px 12px; font-size: 11px; text-align: left; } "
                "QPushButton:hover { border-color: #0369A1; color: #0369A1; }"
            )
            chip.clicked.connect(
                lambda _checked=False, dept_id=choice["id"]: self._apply_ranked_department(dept_id)
            )
            chips.addWidget(chip, i // 2, i % 2)
        layout.addLayout(chips)
        self._root.addWidget(box)

    def _apply_ranked_department(self, dept_id: int) -> None:
        """Point a Department row at the chosen department."""
        row = next((r for r in self.rows if r["type"].currentData() == "DEPARTMENT"), None)
        if row is None:
            # A single row is switched to this department; with several rows
            # the DS already chose, add a new one instead of overwriting.
            if len(self.rows) == 1:
                row = self.rows[0]
            else:
                self._add_row()
                row = self.rows[-1]
            type_idx = row["type"].findData("DEPARTMENT")
            if type_idx < 0:
                return
            row["type"].setCurrentIndex(type_idx)
        target_idx = row["target"].findData(dept_id)
        if target_idx >= 0:
            row["target"].setCurrentIndex(target_idx)

    def _add_row(self, prefill: bool = False) -> None:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 5px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)

        top = QHBoxLayout()
        type_combo = QComboBox()
        for label, value in self.BRANCH_CHOICES:
            type_combo.addItem(label, value)
        top.addWidget(QLabel("Send to:"))
        top.addWidget(type_combo, 1)

        remove_btn = QPushButton("Remove")
        remove_btn.setStyleSheet("color: #B91C1C; border: none; font-size: 11px;")
        top.addWidget(remove_btn)
        layout.addLayout(top)

        target_combo = QComboBox()
        target_label = QLabel("Recipient:")
        target_row = QHBoxLayout()
        target_row.addWidget(target_label)
        target_row.addWidget(target_combo, 1)
        layout.addLayout(target_row)

        instructions = QLineEdit()
        instructions.setPlaceholderText("Instructions for this recipient (optional)")
        layout.addWidget(instructions)

        options = QHBoxLayout()
        validation = QCheckBox("Require HOD validation of submitted work")
        options.addWidget(validation)
        options.addStretch()
        options.addWidget(QLabel("Deadline:"))
        deadline = _date_edit(self.document.deadline)
        options.addWidget(deadline)
        layout.addLayout(options)

        entry = {
            "widget": card,
            "type": type_combo,
            "target": target_combo,
            "target_label": target_label,
            "instructions": instructions,
            "validation": validation,
            "deadline": deadline,
        }

        def refresh_targets() -> None:
            branch_type = type_combo.currentData()
            target_combo.clear()
            if branch_type == "DEPARTMENT":
                target_label.setText("Department:")
                target_label.setVisible(True)
                target_combo.setVisible(True)
                for dept in self._departments:
                    target_combo.addItem(dept.name, dept.id)
                if self.document.suggested_department_id:
                    idx = target_combo.findData(self.document.suggested_department_id)
                    if idx >= 0:
                        target_combo.setCurrentIndex(idx)
                validation.setVisible(True)
                validation.setChecked(True)
            elif branch_type == "EMPLOYEE":
                target_label.setText("Employee:")
                target_label.setVisible(True)
                target_combo.setVisible(True)
                try:
                    for user in get_repository().get_users(context_type="EMPLOYEE"):
                        dept = f" ({user.department_name})" if user.department_name else ""
                        target_combo.addItem(f"{user.full_name}{dept}", user.id)
                except Exception:
                    pass
                if self.document.suggested_employee_id:
                    idx = target_combo.findData(self.document.suggested_employee_id)
                    if idx >= 0:
                        target_combo.setCurrentIndex(idx)
                validation.setVisible(True)
                validation.setChecked(False)
            elif branch_type == "DIRECTOR":
                target_label.setText("Director:")
                target_label.setVisible(bool(self._directors))
                target_combo.setVisible(bool(self._directors))
                for user in self._directors:
                    target_combo.addItem(user.full_name, user.id)
                validation.setVisible(False)
                validation.setChecked(False)
            else:  # TSO - exactly one designated TSO, so nothing to pick
                target_label.setVisible(False)
                target_combo.setVisible(False)
                validation.setVisible(False)
                validation.setChecked(False)

        type_combo.currentIndexChanged.connect(refresh_targets)

        def remove_row() -> None:
            if len(self.rows) <= 1:
                self.warn(self, "Routing", "At least one recipient is required.")
                return
            self.rows.remove(entry)
            card.hide()
            card.setParent(None)
            card.deleteLater()

        remove_btn.clicked.connect(remove_row)

        if prefill and self.document.suggested_department_id:
            type_combo.setCurrentIndex(1)
        refresh_targets()

        self.rows_layout.insertWidget(self.rows_layout.count() - 1, card)
        self.rows.append(entry)

    def _on_accept(self) -> None:
        if not self.get_branches():
            self.warn(self, "Routing", "Add at least one recipient before routing.")
            return
        self.accept()

    def get_branches(self) -> List[Dict[str, Any]]:
        """The routing payload: one entry per workstream to open."""
        payload: List[Dict[str, Any]] = []
        for row in self.rows:
            branch_type = row["type"].currentData()
            entry: Dict[str, Any] = {
                "branch_type": branch_type,
                "instructions": row["instructions"].text().strip() or None,
                "requires_hod_validation": row["validation"].isChecked(),
                "deadline": row["deadline"].date().toString("yyyy-MM-dd"),
            }
            if branch_type == "DEPARTMENT":
                if row["target"].currentData() is None:
                    continue
                entry["department_id"] = row["target"].currentData()
            elif branch_type in ("EMPLOYEE", "DIRECTOR"):
                if row["target"].currentData() is None:
                    continue
                entry["target_user_id"] = row["target"].currentData()
            payload.append(entry)
        return payload


# ===========================================================================
# ASSIGNMENT - one work item per person
# ===========================================================================

class AssignWorkDialog(_BaseDialog):
    """Assign people to a workstream.

    Selecting three people creates three separate work items.  A team name is
    only a label for the group: each person still has their own stage,
    deadline, progress and attachments.
    """

    def __init__(
        self,
        branch: BranchModel,
        department_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(
            f"Assign Staff - {branch.label}",
            "Each person selected gets their own work record: their own stage, deadline, "
            "written progress and attachments. A team name only groups them for display.",
            parent,
            width=600,
        )
        self.branch = branch
        self.department_id = department_id or branch.department_id
        self._build()

    def _build(self) -> None:
        self.people = QListWidget()
        self.people.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.people.setMinimumHeight(190)

        already = {w.assigned_to_user_id for w in self.branch.work_items if not w.is_finished}
        try:
            repo = get_repository()
            if self.branch.branch_type == "DEPARTMENT" and self.department_id:
                candidates = repo.get_department_employees(self.department_id)
            elif self.branch.branch_type == "TSO":
                candidates = repo.get_users(context_type="TSO")
            else:
                candidates = repo.get_users(context_type="EMPLOYEE")
        except Exception:
            candidates = []

        for user in candidates:
            item = QListWidgetItem(
                f"{user.full_name}"
                + (f"  -  {user.designation}" if getattr(user, "designation", None) else "")
                + ("   [already assigned]" if user.id in already else "")
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, user.id)
            self.people.addItem(item)

        if not candidates:
            note = QLabel(
                "Nobody holds an Employee work context in this department. "
                "An administrator can grant one from User Configuration."
            )
            note.setWordWrap(True)
            note.setStyleSheet("color: #B91C1C; font-size: 11px;")
            self._root.addWidget(note)

        self._root.addWidget(QLabel("Select the people to assign:"))
        self._root.addWidget(self.people)

        form = QFormLayout()
        form.setSpacing(8)

        self.team_name = QLineEdit()
        self.team_name.setPlaceholderText("Optional - e.g. 'Infrastructure Review Team'")
        form.addRow("Team name:", self.team_name)

        self.instructions = QTextEdit()
        self.instructions.setPlaceholderText("What should they do?")
        self.instructions.setMaximumHeight(72)
        if self.branch.instructions:
            self.instructions.setPlainText(self.branch.instructions)
        form.addRow("Instructions:", self.instructions)

        self.deadline = _date_edit(self.branch.deadline)
        form.addRow("Deadline:", self.deadline)

        self.validation = QCheckBox("Their submitted work needs my validation before it counts as done")
        self.validation.setChecked(bool(self.branch.requires_hod_validation))
        form.addRow("", self.validation)

        self._root.addLayout(form)
        self.add_buttons("Assign")

    def _on_accept(self) -> None:
        if not self.selected_user_ids():
            self.warn(self, "Assign Staff", "Select at least one person.")
            return
        self.accept()

    def selected_user_ids(self) -> List[int]:
        return [
            self.people.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.people.count())
            if self.people.item(i).checkState() == Qt.CheckState.Checked
        ]

    def get_data(self) -> Dict[str, Any]:
        return {
            "assignee_user_ids": self.selected_user_ids(),
            "team_name": self.team_name.text().strip() or None,
            "instructions": self.instructions.toPlainText().strip() or None,
            "deadline": self.deadline.date().toString("yyyy-MM-dd"),
            "requires_validation": self.validation.isChecked(),
        }


# ===========================================================================
# PROGRESS - free text, optional attachment
# ===========================================================================

class ProgressDialog(_BaseDialog):
    """Write a progress update.

    Describe what you did or what is happening.  This is stored exactly as
    written; the system never turns it into a number or a completion figure.
    """

    def __init__(self, item: WorkItemModel, parent: Optional[QWidget] = None):
        super().__init__(
            "Progress Update",
            f"{item.branch_label or 'Your work'} - describe what you have done or what is "
            "currently happening. Attach supporting files if they belong with this update.",
            parent,
            width=600,
        )
        self.item = item
        self._file_path: Optional[str] = None
        self._build()

    def _build(self) -> None:
        if self.item.instructions:
            instr = QLabel(f"Assigned: {self.item.instructions}")
            instr.setWordWrap(True)
            instr.setStyleSheet(
                "background-color: #F8FAFC; border-left: 3px solid #CBD5E1; padding: 8px 10px; "
                "color: #334155; font-size: 11px; border-radius: 3px;"
            )
            self._root.addWidget(instr)

        self._root.addWidget(QLabel("What has happened?"))
        self.description = QTextEdit()
        self.description.setPlaceholderText(
            "e.g. Reviewed the submitted documents and identified three issues in the existing "
            "configuration. I have prepared the required analysis and am currently working on "
            "the proposed changes."
        )
        self.description.setMinimumHeight(140)
        self._root.addWidget(self.description)

        stage_row = QHBoxLayout()
        stage_row.addWidget(QLabel("Set my stage to:"))
        self.stage = QComboBox()
        self.stage.addItem("Leave unchanged", None)
        for stage in WorkStageEnum.worker_selectable():
            self.stage.addItem(WorkStageEnum.label(stage.value), stage.value)
        stage_row.addWidget(self.stage, 1)
        self._root.addLayout(stage_row)

        file_row = QHBoxLayout()
        self.file_label = QLabel("No file attached")
        self.file_label.setStyleSheet("color: #64748B; font-size: 11px;")
        attach = QPushButton("Attach supporting file")
        attach.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #CBD5E1; padding: 6px 12px; "
            "border-radius: 4px; font-size: 11px; font-weight: 600;"
        )
        attach.clicked.connect(self._pick_file)
        clear = QPushButton("Clear")
        clear.setStyleSheet("color: #B91C1C; border: none; font-size: 11px;")
        clear.clicked.connect(self._clear_file)
        file_row.addWidget(attach)
        file_row.addWidget(clear)
        file_row.addWidget(self.file_label, 1)
        self._root.addLayout(file_row)

        self.add_buttons("Submit Update")

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach supporting document", "",
            "Documents (*.pdf *.docx *.doc *.xlsx *.xls *.png *.jpg *.jpeg *.txt *.csv *.zip)",
        )
        if path:
            self._file_path = path
            self.file_label.setText(path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])

    def _clear_file(self) -> None:
        self._file_path = None
        self.file_label.setText("No file attached")

    def _on_accept(self) -> None:
        if not self.description.toPlainText().strip():
            self.warn(self, "Progress Update", "Describe what you have done before submitting.")
            return
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return {
            "description": self.description.toPlainText().strip(),
            "new_stage": self.stage.currentData(),
            "file_path": self._file_path,
        }


# ===========================================================================
# STAGE CHANGE
# ===========================================================================

class StageDialog(_BaseDialog):
    """Move your own work to a different stage."""

    def __init__(self, item: WorkItemModel, parent: Optional[QWidget] = None):
        super().__init__(
            "Change Work Stage",
            f"Currently: {item.stage_label}. This changes only your own work - "
            "nobody else on this document is affected.",
            parent,
            width=480,
        )
        self.item = item

        self.stage = QComboBox()
        for stage in WorkStageEnum.worker_selectable():
            self.stage.addItem(WorkStageEnum.label(stage.value), stage.value)
        form = QFormLayout()
        form.addRow("New stage:", self.stage)

        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional note, e.g. why you are waiting")
        form.addRow("Note:", self.note)
        self._root.addLayout(form)

        self.add_buttons("Update Stage")

    def get_data(self) -> Dict[str, Any]:
        return {"stage": self.stage.currentData(), "note": self.note.text().strip() or None}


# ===========================================================================
# SUBMIT WORK
# ===========================================================================

class SubmitWorkDialog(_BaseDialog):
    def __init__(self, item: WorkItemModel, parent: Optional[QWidget] = None):
        needs_review = item.requires_validation
        super().__init__(
            "Submit Work",
            (
                "Your work will go to your HOD for validation."
                if needs_review else
                "Your assignment will be marked complete."
            )
            + " This does not close the document - the DS decides that.",
            parent,
            width=520,
        )
        self._file_path: Optional[str] = None
        self.note = QTextEdit()
        self.note.setPlaceholderText("Closing note (optional) - recorded as a final progress update")
        self.note.setMaximumHeight(100)
        self._root.addWidget(self.note)
        
        file_row = QHBoxLayout()
        self.file_label = QLabel("No file attached")
        self.file_label.setStyleSheet("color: #64748B; font-size: 11px;")
        attach = QPushButton("Attach final file")
        attach.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #CBD5E1; padding: 6px 12px; "
            "border-radius: 4px; font-size: 11px; font-weight: 600;"
        )
        attach.clicked.connect(self._pick_file)
        clear = QPushButton("Clear")
        clear.setStyleSheet("color: #B91C1C; border: none; font-size: 11px;")
        clear.clicked.connect(self._clear_file)
        file_row.addWidget(attach)
        file_row.addWidget(clear)
        file_row.addWidget(self.file_label, 1)
        self._root.addLayout(file_row)

        self.add_buttons("Submit")

    def _pick_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach final document", "",
            "All Files (*);;PDF Documents (*.pdf);;Images (*.png *.jpg *.jpeg)"
        )
        if path:
            self._file_path = path
            import os
            self.file_label.setText(f"Attached: {os.path.basename(path)}")

    def _clear_file(self) -> None:
        self._file_path = None
        self.file_label.setText("No file attached")

    def get_data(self) -> Dict[str, Any]:
        return {
            "note": self.note.toPlainText().strip() or None,
            "file_path": self._file_path
        }


# ===========================================================================
# REMARK
# ===========================================================================

class RemarkDialog(_BaseDialog):
    def __init__(self, title: str, subtitle: str, parent: Optional[QWidget] = None, prefill: str = ""):
        super().__init__(title, subtitle, parent, width=580)
        self.text = QTextEdit()
        self.text.setMinimumHeight(140)
        if prefill:
            self.text.setPlainText(prefill)
        self._root.addWidget(self.text)
        self.add_buttons("Save Remark")

    def _on_accept(self) -> None:
        if not self.text.toPlainText().strip():
            self.warn(self, "Remark", "A remark cannot be empty.")
            return
        self.accept()

    def get_text(self) -> str:
        return self.text.toPlainText().strip()


class DirectorReviewDialog(RemarkDialog):
    """The Director records a remark and hands the document back to the DS.

    There is deliberately no approve/reject/close control here: the Director
    reviews and remarks; the DS decides whether more work is needed or the
    document can be closed.
    """

    def __init__(self, document: DocumentModel, parent: Optional[QWidget] = None):
        super().__init__(
            "Director Review",
            "Record your remark. The document returns to the DS, who decides whether further "
            "work is needed or it can be closed. Every review you write is kept separately.",
            parent,
        )
        if document.director_reviews:
            previous = QLabel(
                "Previous reviews:\n"
                + "\n".join(f"  #{r.review_no}: {r.remark_text}" for r in document.director_reviews)
            )
            previous.setWordWrap(True)
            previous.setStyleSheet(
                "background-color: #F5F3FF; border-left: 3px solid #7C3AED; padding: 8px 10px; "
                "color: #4C1D95; font-size: 11px; border-radius: 3px;"
            )
            self._root.insertWidget(3, previous)


class WorkReviewDialog(_BaseDialog):
    """Accept or return ONE person's work."""

    def __init__(self, item: WorkItemModel, accept_mode: bool, parent: Optional[QWidget] = None):
        super().__init__(
            ("Accept Work" if accept_mode else "Return Work for Rework"),
            (
                f"{item.assignee_name}'s work only. Accepting completes their assignment; "
                "it does not close the workstream unless everyone else has finished, and it "
                "never closes the document."
                if accept_mode else
                f"{item.assignee_name}'s work goes back to them. Their earlier progress and "
                "attachments are kept."
            ),
            parent,
            width=560,
        )
        self.accept_mode = accept_mode

        if item.latest_progress_text:
            latest = QLabel(f"Their latest update:\n{item.latest_progress_text}")
            latest.setWordWrap(True)
            latest.setStyleSheet(
                "background-color: #F8FAFC; border-left: 3px solid #CBD5E1; padding: 8px 10px; "
                "color: #334155; font-size: 11px; border-radius: 3px;"
            )
            self._root.addWidget(latest)

        self.note = QTextEdit()
        self.note.setPlaceholderText(
            "Validation note (optional)" if accept_mode else "Explain what needs reworking"
        )
        self.note.setMaximumHeight(110)
        self._root.addWidget(self.note)
        self.add_buttons("Accept" if accept_mode else "Return")

    def _on_accept(self) -> None:
        if not self.accept_mode and not self.note.toPlainText().strip():
            self.warn(self, "Return Work", "Explain what needs reworking.")
            return
        self.accept()

    def get_note(self) -> Optional[str]:
        return self.note.toPlainText().strip() or None


# ===========================================================================
# CLOSURE (DS only)
# ===========================================================================

class CloseDocumentDialog(_BaseDialog):
    """DS closure.

    Closure is the DS's decision alone.  No Director approval is required.
    If workstreams are still running they must be cancelled explicitly - the
    dialog says so rather than quietly marking them finished.
    """

    def __init__(self, document: DocumentModel, parent: Optional[QWidget] = None):
        open_branches = [b for b in document.branches if b.is_active]
        super().__init__(
            f"Close {document.reference}",
            "Closing is your decision as DS. The Director's remarks are advisory and no "
            "Director approval is required.",
            parent,
            width=600,
        )
        self.document = document
        self.open_branches = open_branches

        if document.branch_summaries:
            summary = QLabel(
                "Workstreams:\n"
                + "\n".join(
                    f"  • {s.label}: {s.stage_label}" + ("" if s.is_active else "  (closed)")
                    for s in document.branch_summaries
                )
            )
            summary.setWordWrap(True)
            summary.setStyleSheet(
                "background-color: #F8FAFC; border-left: 3px solid #CBD5E1; padding: 8px 10px; "
                "color: #334155; font-size: 11px; border-radius: 3px;"
            )
            self._root.addWidget(summary)

        self.force = QCheckBox()
        if open_branches:
            labels = ", ".join(b.label for b in open_branches)
            warning = QLabel(
                f"{len(open_branches)} workstream(s) are still open: {labels}. "
                "Closing now cancels their outstanding work, and that is recorded in the history."
            )
            warning.setWordWrap(True)
            warning.setStyleSheet(
                "background-color: #FEF2F2; border-left: 3px solid #B91C1C; padding: 8px 10px; "
                "color: #7F1D1D; font-size: 11px; border-radius: 3px;"
            )
            self._root.addWidget(warning)
            self.force.setText("I understand - cancel the outstanding work and close")
            self._root.addWidget(self.force)

        self._root.addWidget(QLabel("Closure remark:"))
        self.remark = QTextEdit()
        self.remark.setPlaceholderText("Why is this document being closed?")
        self.remark.setMaximumHeight(110)
        self._root.addWidget(self.remark)

        self.add_buttons("Close Document")

    def _on_accept(self) -> None:
        if self.open_branches and not self.force.isChecked():
            self.warn(
                self, "Close Document",
                "Workstreams are still open. Tick the confirmation to cancel them and close, "
                "or wait for them to finish.",
            )
            return
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return {
            "remark": self.remark.toPlainText().strip() or None,
            "force": bool(self.open_branches and self.force.isChecked()),
        }


# ===========================================================================
# REMINDER
# ===========================================================================

class ReminderDialog(_BaseDialog):
    """Nudge whoever is actually holding the work."""

    def __init__(self, document: DocumentModel, parent: Optional[QWidget] = None):
        super().__init__(
            f"Send Reminder - {document.reference}",
            "Reminders go to the people holding live work items, with their own deadline.",
            parent,
            width=560,
        )
        self.document = document

        open_items = [w for w in document.all_work_items if not w.is_finished]

        self.target = QComboBox()
        self.target.addItem("Everyone with open work", None)
        for item in open_items:
            self.target.addItem(
                f"{item.assignee_name} - {item.branch_label} "
                f"({item.stage_label}, due {item.deadline_display})",
                item.id,
            )
        form = QFormLayout()
        form.addRow("Remind:", self.target)
        self._root.addLayout(form)

        if not open_items:
            note = QLabel("There is no open work on this document to remind about.")
            note.setStyleSheet("color: #B91C1C; font-size: 11px;")
            self._root.addWidget(note)

        self._root.addWidget(QLabel("Message:"))
        self.message = QTextEdit()
        self.message.setPlaceholderText("Optional - a default message is sent if left blank")
        self.message.setMaximumHeight(90)
        self._root.addWidget(self.message)

        self.add_buttons("Send Reminder")

    def get_data(self) -> Dict[str, Any]:
        return {
            "work_item_id": self.target.currentData(),
            "message": self.message.toPlainText().strip() or None,
        }


# ===========================================================================
# DOCUMENT DETAILS (DS correcting extracted metadata)
# ===========================================================================

class EditDocumentDialog(_BaseDialog):
    """DS corrects document details.

    OCR fills these in to save typing; it never has the final word.  Every
    correction is recorded in the document's history.
    """

    def __init__(self, document: DocumentModel, parent: Optional[QWidget] = None):
        super().__init__(
            f"Edit Details - {document.reference}",
            "Correct anything the extraction got wrong. Changes are recorded in the history.",
            parent,
            width=620,
        )
        self.document = document

        form = QFormLayout()
        form.setSpacing(8)

        self.title = QLineEdit(document.title or "")
        form.addRow("Title:", self.title)

        self.subject = QLineEdit(document.subject or "")
        form.addRow("Subject:", self.subject)

        self.sender = QLineEdit(document.sender_name or "")
        form.addRow("Sender:", self.sender)

        self.sender_ref = QLineEdit(document.sender_reference or "")
        form.addRow("Sender reference:", self.sender_ref)

        self.source = QLineEdit(document.source or "")
        form.addRow("Source:", self.source)

        self.priority = QComboBox()
        for value in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
            self.priority.addItem(value.title(), value)
        idx = self.priority.findData(str(document.priority).upper())
        if idx >= 0:
            self.priority.setCurrentIndex(idx)
        form.addRow("Priority:", self.priority)

        self.deadline = _date_edit(document.deadline)
        form.addRow("Deadline:", self.deadline)

        self.description = QTextEdit(document.description or "")
        self.description.setMaximumHeight(90)
        form.addRow("Description:", self.description)

        self._root.addLayout(form)
        self.add_buttons("Save Changes")

    def _on_accept(self) -> None:
        if not self.title.text().strip():
            self.warn(self, "Edit Details", "A title is required.")
            return
        self.accept()

    def get_data(self) -> Dict[str, Any]:
        return {
            "title": self.title.text().strip(),
            "subject": self.subject.text().strip() or None,
            "sender_name": self.sender.text().strip() or None,
            "sender_reference": self.sender_ref.text().strip() or None,
            "source": self.source.text().strip() or None,
            "priority": self.priority.currentData(),
            "deadline": self.deadline.date().toString("yyyy-MM-dd"),
            "description": self.description.toPlainText().strip() or None,
            "expected_version": self.document.version,
        }
