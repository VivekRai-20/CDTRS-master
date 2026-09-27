from datetime import datetime
from typing import Any, Dict, Optional, Union
import json
import os

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from models.document import DocumentModel
from models.enums import IngestionModeEnum, PriorityEnum
from repositories.provider import get_repository
from services.document_service import document_service
from services.ocr_service import ocr_service
from services.routing_service import routing_service
from components.ocr_splash_dialog import OCRSplashDialog
from components.busy_dialog import BusyDialog
from components.document_preview import DocumentPreview
from services.date_utils import parse_date


class DocumentIntakePage(QWidget):
    """
    Document Intake & Processing Page for Director Secretary.
    Captures incoming documents, metadata, OCR text, and routes initial intake
    directly to the Director for review or directly to HOD/Staff if a prior Director directive exists.
    Allows DS to edit suggested routing before confirmation.
    """

    document_processed = Signal(object)  # Emits newly created & routed DocumentModel

    def __init__(self):
        super().__init__()
        self.selected_file: Optional[str] = None
        self.current_inbox_item_id: Optional[int] = None
        self.extracted_ocr_text: str = ""
        self.extracted_ocr_fields: Dict[str, Any] = {}
        self.has_prior_director_remark: bool = False
        self.prior_director_remark_text: str = ""
        self._dept_id_map: Dict[str, int] = {}  # name -> id, populated from backend
        self.setup_ui()

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(30, 25, 30, 30)
        main_layout.setSpacing(15)

        # --------------------------------
        # PAGE HEADER
        # --------------------------------
        header_layout = QHBoxLayout()
        vbox = QVBoxLayout()
        vbox.setSpacing(2)

        title = QLabel("Document Intake & Processing Verification")
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "Verify extracted metadata and routing intelligence from incoming dispatches before committing to CDTRS workflow."
        )
        subtitle.setObjectName("pageSubtitle")

        vbox.addWidget(title)
        vbox.addWidget(subtitle)
        header_layout.addLayout(vbox)
        header_layout.addStretch()

        # Manual File Upload Button
        manual_btn = QPushButton("📁 Manual Intake / Upload File")
        manual_btn.setStyleSheet("background-color: #F8FAFC; color: #0F172A; border: 1px solid #CBD5E1; font-weight: 600; padding: 7px 16px; border-radius: 5px;")
        manual_btn.clicked.connect(self.select_document)
        header_layout.addWidget(manual_btn)

        main_layout.addLayout(header_layout)

        # --------------------------------
        # MAIN 2-COLUMN CONTENT
        # --------------------------------
        content_layout = QHBoxLayout()
        content_layout.setSpacing(18)

        # LEFT - DOCUMENT SOURCE & PREVIEW CARD
        preview_card = QFrame()
        preview_card.setObjectName("contentCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        preview_layout.setSpacing(12)

        preview_title = QLabel("Document Source & Dispatch File")
        preview_title.setObjectName("sectionTitle")
        preview_layout.addWidget(preview_title)

        self.preview_label = QLabel("No document loaded\n\nSelect an incoming item from Inbox or click 'Manual Intake / Upload File' to process a document.")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(260, 220)
        self.preview_label.setStyleSheet("background-color: #F8FAFC; border: 2px dashed #CBD5E1; border-radius: 8px; color: #64748B; padding: 18px; font-size: 12px;")
        self.preview_label.setWordWrap(True)

        # The document itself (PDF pages, scan image, or the e-mail / text)
        # so the DS can check the extracted details against it.
        self.document_preview = DocumentPreview({})
        self.document_preview.setMinimumHeight(360)
        self.preview_file_lbl = QLabel()
        self.preview_file_lbl.setWordWrap(True)
        self.preview_file_lbl.setStyleSheet("color: #64748B; font-size: 11px;")

        preview_page = QWidget()
        pp_layout = QVBoxLayout(preview_page)
        pp_layout.setContentsMargins(0, 0, 0, 0)
        pp_layout.setSpacing(4)
        pp_layout.addWidget(self.preview_file_lbl)
        pp_layout.addWidget(self.document_preview, 1)

        self.preview_stack = QStackedWidget()
        self.preview_stack.addWidget(self.preview_label)   # 0 - nothing loaded
        self.preview_stack.addWidget(preview_page)         # 1 - document preview
        preview_layout.addWidget(self.preview_stack, 1)

        # Compact OCR Status Badge (Clean Neutral)
        self.ocr_status_frame = QFrame()
        self.ocr_status_frame.setStyleSheet(
            "background-color: #F8FAFC; border: 1px solid #E2E8F0;"
            " border-radius: 5px; padding: 8px;"
        )
        ocr_hlayout = QHBoxLayout(self.ocr_status_frame)
        ocr_hlayout.setContentsMargins(10, 6, 10, 6)
        ocr_hlayout.setSpacing(8)

        self.ocr_status_lbl = QLabel("✓ OCR Processed")
        self.ocr_status_lbl.setStyleSheet("color: #334155; font-weight: 600; font-size: 12px;")
        self.ocr_hw_badge = QLabel()
        self.ocr_hw_badge.setStyleSheet(
            "background: #F1F5F9; color: #475569; border: 1px solid #E2E8F0; font-size: 10px; font-weight: 600;"
            " border-radius: 3px; padding: 2px 6px;"
        )
        self.ocr_hw_badge.setVisible(False)
        ocr_hlayout.addWidget(self.ocr_status_lbl)
        ocr_hlayout.addWidget(self.ocr_hw_badge)
        ocr_hlayout.addStretch()
        self.ocr_status_frame.setVisible(False)
        preview_layout.addWidget(self.ocr_status_frame)


        # Collapsible OCR Fields panel
        self.ocr_fields_frame = QFrame()
        self.ocr_fields_frame.setStyleSheet(
            "background: #F8FAFC; border: 1px solid #E2E8F0;"
            " border-radius: 5px; padding: 4px;"
        )
        ocr_f_layout = QVBoxLayout(self.ocr_fields_frame)
        ocr_f_layout.setContentsMargins(8, 6, 8, 6)
        ocr_f_layout.setSpacing(3)
        ocr_fields_hdr = QLabel("📋 OCR Extracted Fields")
        ocr_fields_hdr.setStyleSheet("font-weight: 600; font-size: 11px; color: #475569;")
        ocr_f_layout.addWidget(ocr_fields_hdr)
        self.ocr_fields_text = QLabel()
        self.ocr_fields_text.setWordWrap(True)
        self.ocr_fields_text.setStyleSheet("font-size: 11px; color: #334155; font-family: monospace;")
        ocr_f_layout.addWidget(self.ocr_fields_text)
        self.ocr_fields_frame.setVisible(False)
        preview_layout.addWidget(self.ocr_fields_frame)

        content_layout.addWidget(preview_card, 1)

        # RIGHT - DOCUMENT INFORMATION FORM
        info_card = QFrame()
        info_card.setObjectName("contentCard")
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(18, 18, 18, 18)
        info_layout.setSpacing(10)

        info_title = QLabel("Extracted Document Information")
        info_title.setObjectName("sectionTitle")
        info_layout.addWidget(info_title)

        form = QFormLayout()
        form.setSpacing(8)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Enter document title / subject")
        self.title_input.setMaxLength(255)  # database column size

        self.ref_input = QLineEdit()
        self.ref_input.setPlaceholderText("Auto-generated reference number")

        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("YYYY-MM-DD")

        self.mode_input = QComboBox()
        self.mode_input.addItems([
            IngestionModeEnum.GOVERNMENT_MAIL.value,
            IngestionModeEnum.OUTLOOK.value,
            IngestionModeEnum.MANUAL_UPLOAD.value,
        ])

        self.source_input = QLineEdit()
        self.source_input.setPlaceholderText("e.g. Finance Department, Cabinet Secretariat")

        self.format_input = QComboBox()
        self.format_input.addItems([
            "PDF", "DOCX", "Image (PNG/JPG)", "Scanned PDF", "Email Body", "Other"
        ])

        self.priority_input = QComboBox()
        self.priority_input.addItems([
            PriorityEnum.CRITICAL.value,
            PriorityEnum.HIGH.value,
            PriorityEnum.MEDIUM.value,
            PriorityEnum.LOW.value
        ])
        self.priority_input.setCurrentText(PriorityEnum.MEDIUM.value)

        self.deadline_input = QLineEdit()
        self.deadline_input.setPlaceholderText("YYYY-MM-DD (optional)")

        form.addRow("Title / Subject:", self.title_input)
        form.addRow("Reference No:", self.ref_input)
        form.addRow("Received Date:", self.date_input)
        form.addRow("Ingestion Mode:", self.mode_input)
        form.addRow("Sender / Source:", self.source_input)
        form.addRow("Document Format:", self.format_input)
        form.addRow("Priority:", self.priority_input)
        form.addRow("Target Deadline:", self.deadline_input)

        info_layout.addLayout(form)
        content_layout.addWidget(info_card, 2)
        main_layout.addLayout(content_layout)

        # --------------------------------
        # ROUTING INTELLIGENCE & DIRECTOR REMARK CARD
        # --------------------------------
        bottom_cards_layout = QHBoxLayout()
        bottom_cards_layout.setSpacing(18)

        # 1. Routing Intelligence Card (Editable by DS)
        routing_card = QFrame()
        routing_card.setObjectName("contentCard")
        r_layout = QVBoxLayout(routing_card)
        r_layout.setContentsMargins(16, 14, 16, 14)
        r_layout.setSpacing(8)

        r_title = QLabel("Routing Intelligence")
        r_title.setObjectName("sectionTitle")
        r_layout.addWidget(r_title)

        r_form = QFormLayout()
        r_form.setSpacing(6)

        self.dept_combo = QComboBox()
        self.dept_combo.addItem("Not Specified", None)

        self.emp_combo = QComboBox()
        self._load_departments_from_backend()
        self._load_employees_from_backend()

        self.dept_combo.currentIndexChanged.connect(self._on_dept_changed)

        self.confidence_label = QLabel("Confidence: — • Source: Document / OCR")
        self.confidence_label.setStyleSheet("color: #059669; font-weight: 600; font-size: 11px;")

        r_form.addRow("Suggested Dept:", self.dept_combo)
        r_form.addRow("Suggested Staff:", self.emp_combo)
        r_layout.addLayout(r_form)
        r_layout.addWidget(self.confidence_label)

        bottom_cards_layout.addWidget(routing_card, 1)

        # 2. Pre-existing Director Remark Card
        self.director_remark_card = QFrame()
        self.director_remark_card.setObjectName("contentCard")
        self.director_remark_card.setStyleSheet("QFrame#contentCard { background-color: #FEF3C7; border: 1px solid #FCD34D; border-radius: 6px; }")
        
        dr_layout = QVBoxLayout(self.director_remark_card)
        dr_layout.setContentsMargins(16, 14, 16, 14)
        dr_layout.setSpacing(6)

        dr_title = QLabel("Prior Director Directive Detected in Source")
        dr_title.setStyleSheet("font-weight: 700; color: #92400E; font-size: 13px;")
        dr_layout.addWidget(dr_title)

        self.prior_remark_lbl = QLabel("OCR found what looks like a Director instruction on the document:")
        self.prior_remark_lbl.setStyleSheet("color: #78350F; font-size: 12px; font-style: italic;")
        self.prior_remark_lbl.setWordWrap(True)
        dr_layout.addWidget(self.prior_remark_lbl)

        # The instruction as read by OCR, correctable by the DS.
        self.prior_remark_edit = QTextEdit()
        self.prior_remark_edit.setPlaceholderText(
            "Director's instruction as written on the document (correct any OCR mistakes)"
        )
        self.prior_remark_edit.setFixedHeight(58)
        self.prior_remark_edit.setStyleSheet(
            "background: #FFFBEB; border: 1px solid #FCD34D; border-radius: 4px; color: #78350F; font-size: 12px;"
        )
        dr_layout.addWidget(self.prior_remark_edit)

        # When the Director has already written the instruction on the
        # document, the separate Director review step is not needed: the DS
        # confirms it here and routes straight to departments.
        self.prior_review_check = QCheckBox(
            "The Director has already reviewed this document - skip the Director review "
            "step and route it directly"
        )
        self.prior_review_check.setStyleSheet("color: #78350F; font-size: 11px; font-weight: 600;")
        self.prior_review_check.toggled.connect(lambda _c: self._update_director_flow_note())
        dr_layout.addWidget(self.prior_review_check)

        self.director_flow_note = QLabel()
        self.director_flow_note.setWordWrap(True)
        self.director_flow_note.setStyleSheet(
            "color: #92400E; font-size: 11px;"
        )
        dr_layout.addWidget(self.director_flow_note)

        self.director_remark_card.setVisible(False)
        bottom_cards_layout.addWidget(self.director_remark_card, 1)

        main_layout.addLayout(bottom_cards_layout)

        # --------------------------------
        # CONFIRMATION ACTION BAR
        # --------------------------------
        action_bar = QHBoxLayout()
        action_bar.addStretch()

        self.clear_btn = QPushButton("Clear Form")
        self.clear_btn.setStyleSheet("background-color: #F1F5F9; color: #0F172A; border: 1px solid #CBD5E1; font-weight: 600; padding: 8px 16px; border-radius: 5px;")
        self.clear_btn.clicked.connect(self.clear_form)
        action_bar.addWidget(self.clear_btn)

        self.submit_btn = QPushButton("Confirm & Send for Director Review")
        self.submit_btn.setStyleSheet("background-color: #0F172A; color: white; font-size: 13px; font-weight: 600; padding: 9px 24px; border-radius: 6px;")
        self.submit_btn.clicked.connect(self.save_and_confirm_routing)
        action_bar.addWidget(self.submit_btn)

        main_layout.addLayout(action_bar)
        self.setLayout(main_layout)

    # ====================================
    # ACTIONS & DEBUG LOGGING
    # ====================================

    def _load_departments_from_backend(self):
        self.dept_combo.blockSignals(True)
        current_dept_id = self.dept_combo.currentData()
        self.dept_combo.clear()
        self.dept_combo.addItem("Not Specified", None)
        self._dept_id_map = {}
        try:
            repo = get_repository()
            departments = repo.get_departments()
            for dept in departments:
                self.dept_combo.addItem(dept.name, dept.id)
                self._dept_id_map[dept.name] = dept.id
        except Exception as e:
            self.dept_combo.addItem("⚠ Could not load departments", None)
        if current_dept_id is not None:
            for i in range(self.dept_combo.count()):
                if self.dept_combo.itemData(i) == current_dept_id:
                    self.dept_combo.setCurrentIndex(i)
                    break
        self.dept_combo.blockSignals(False)

    def _load_employees_from_backend(self, department_id: Optional[int] = None):
        self.emp_combo.blockSignals(True)
        self.emp_combo.clear()
        self.emp_combo.addItem("Not Assigned", None)
        try:
            repo = get_repository()
            # Fetch all staff: HODs, TSO, and Employees
            all_staff = repo.get_users(department_id=department_id)
            for staff in all_staff:
                role_str = staff.role or "Staff"
                dept_label = staff.department_name or "General"
                self.emp_combo.addItem(f"{staff.full_name} ({role_str} - {dept_label})", staff.id)
        except Exception as e:
            self.emp_combo.addItem("⚠ Could not load staff", None)
        self.emp_combo.blockSignals(False)


    def _on_dept_changed(self):
        dept_id = self.dept_combo.currentData()
        self._load_employees_from_backend(department_id=dept_id)

    def select_document(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Intake Document",
            "",
            "Documents (*.pdf *.docx *.png *.jpg *.jpeg *.tif *.tiff *.bmp *.txt);;All Files (*)"
        )
        if not file_path:
            return

        self.selected_file = file_path
        fname = os.path.basename(file_path)
        self.incoming_attachments_list = [fname]
        self.incoming_attachment_count = 1
        self.preview_label.setText(f"Manual File Loaded:\n{fname}\n\nPath: {file_path}")

        res = OCRSplashDialog.execute_ocr(
            file_path=file_path,
            incoming_item={"title": fname, "source": "Manual Upload", "mode": IngestionModeEnum.MANUAL_UPLOAD.value},
            parent=self
        )
        self._populate_extracted_data(res, file_path=file_path)

    def load_document(self, doc_dict_or_model: Union[DocumentModel, Dict[str, Any]]):
        if isinstance(doc_dict_or_model, DocumentModel):
            doc = doc_dict_or_model
            self.current_inbox_item_id = doc.id
            self.incoming_attachments_list = doc.attachments_list or []
            self.incoming_attachment_count = doc.attachment_count if doc.attachment_count is not None else len(self.incoming_attachments_list)
            raw_data = {
                "title": doc.title,
                "date": doc.date,
                "mode": doc.mode,
                "source": doc.source,
                "priority": doc.priority,
                "deadline": doc.deadline,
                "file_path": doc.file_path,
                "format": doc.format or doc.file_type,
                "has_prior_director_remark": doc.has_prior_director_remark,
                "director_remark": doc.director_remark,
                "attachments_list": self.incoming_attachments_list,
                "attachment_count": self.incoming_attachment_count
            }
        else:
            raw_data = dict(doc_dict_or_model)
            self.current_inbox_item_id = raw_data.get("id")
            # Lets the OCR step fetch and read the mail's attachment.
            raw_data["intake_message_id"] = raw_data.get("id")
            self.incoming_attachments_list = raw_data.get("attachments_list", [])
            self.incoming_attachment_count = raw_data.get("attachment_count", len(self.incoming_attachments_list))

        raw_file_path = raw_data.get("file_path", "")
        
        ocr_result = OCRSplashDialog.execute_ocr(
            file_path=raw_file_path,
            incoming_item=raw_data,
            parent=self
        )
        self._populate_extracted_data(ocr_result, file_path=raw_file_path)

    def _populate_extracted_data(self, ocr_result: Dict[str, Any], file_path: Optional[str] = None):
        self.extracted_ocr_text = ocr_result.get("extracted_text", "")
        self.extracted_ocr_fields = dict(ocr_result.get("ocr_fields") or {})
        raw_conf = ocr_result.get("confidence", 0.0)
        try:
            c = float(raw_conf)
            self.extracted_ocr_confidence = (c / 100.0) if c > 1.0 else c
        except (ValueError, TypeError):
            self.extracted_ocr_confidence = 0.0
        
        # DEBUG PRINT FOR TRACING OCR TEXT CAPTURE
        print(f"\n--- [DEBUG OCR POPULATE] ---")
        print(f"Extracted Text Length: {len(self.extracted_ocr_text)} characters")
        print(f"Extracted OCR Confidence: {self.extracted_ocr_confidence:.4f} ({round(self.extracted_ocr_confidence * 100)}%)")
        print(f"Sample Extracted Text Preview: {repr(self.extracted_ocr_text[:150])}")
        print(f"OCR Result Keys Returned: {list(ocr_result.keys())}")
        print(f"----------------------------\n")

        self.title_input.setText(ocr_result.get("title", ""))
        self.ref_input.clear()
        self.date_input.setText(ocr_result.get("date", datetime.now().strftime("%Y-%m-%d")))

        raw_mode = ocr_result.get("mode") or IngestionModeEnum.MANUAL_UPLOAD.value
        mode_val = IngestionModeEnum.normalize(raw_mode)
        idx = self.mode_input.findText(mode_val)
        if idx >= 0:
            self.mode_input.setCurrentIndex(idx)
        else:
            self.mode_input.setCurrentText(mode_val)

        self.source_input.setText(ocr_result.get("source", ""))

        fmt_val = ocr_result.get("format", "PDF")
        f_idx = self.format_input.findText(fmt_val)
        if f_idx >= 0:
            self.format_input.setCurrentIndex(f_idx)
        else:
            self.format_input.setCurrentText(fmt_val)

        priority_val = PriorityEnum.normalize(ocr_result.get("priority", "Medium"))
        self.priority_input.setCurrentText(priority_val)

        self.deadline_input.setText(ocr_result.get("deadline", ""))

        dept = ocr_result.get("suggested_department", "")
        emp = ocr_result.get("suggested_employee") or ""

        d_idx = -1
        dept_id = ocr_result.get("suggested_department_id")
        if dept_id is not None:
            d_idx = self.dept_combo.findData(dept_id)
        if d_idx < 0 and dept and dept not in ("Not Specified", "None", ""):
            d_idx = self.dept_combo.findText(dept, Qt.MatchFixedString)
            if d_idx < 0:
                alias_map = {
                    "human resources": "hr",
                    "it": "technical",
                    "information technology": "technical",
                    "systems": "technical",
                    "operations": "administration",
                    "legal": "administration",
                }
                target_name = alias_map.get(dept.lower(), dept).lower()
                for i in range(self.dept_combo.count()):
                    item_txt = self.dept_combo.itemText(i).lower()
                    if target_name == item_txt or target_name in item_txt or item_txt in target_name:
                        d_idx = i
                        break

        if d_idx >= 0:
            self.dept_combo.setCurrentIndex(d_idx)
            selected_dept_id = self.dept_combo.itemData(d_idx)
            self._load_employees_from_backend(department_id=selected_dept_id)

        e_idx = -1
        emp_id = ocr_result.get("suggested_employee_id")
        if emp_id is not None:
            e_idx = self.emp_combo.findData(emp_id)
        if e_idx < 0 and emp and emp not in ("Not Assigned", "None", ""):
            for i in range(self.emp_combo.count()):
                if emp.lower() in self.emp_combo.itemText(i).lower():
                    e_idx = i
                    break
        if e_idx >= 0:
            self.emp_combo.setCurrentIndex(e_idx)
        else:
            self.emp_combo.setCurrentIndex(0)

        # Two different numbers: how well the text was read, and how well the
        # suggested department matches it.
        ocr_part = (
            f"OCR confidence: {round(self.extracted_ocr_confidence * 100)}%"
            if self.extracted_ocr_confidence > 0 else "OCR confidence: —"
        )
        match = ocr_result.get("department_match")
        if d_idx > 0 and match is not None:
            try:
                dept_part = f"Department match: {round(float(match) * 100)}%"
            except (TypeError, ValueError):
                dept_part = "Department suggested from the document"
        elif d_idx > 0:
            dept_part = "Department suggested from the document"
        else:
            dept_part = "No department match found - please choose one"
        self.confidence_label.setText(f"{ocr_part} • {dept_part}")

        pages = ocr_result.get("pages_extracted", 1)
        is_hw = ocr_result.get("is_handwritten", False)
        pages_label = f"{pages} page(s)"
        ocr_error = ocr_result.get("ocr_error")
        if ocr_error and not self.extracted_ocr_text:
            self.ocr_status_lbl.setText(
                "⚠ OCR could not read this file - please fill in the details manually. "
                "The server will try again after registration."
            )
            self.ocr_status_lbl.setToolTip(str(ocr_error))
        else:
            self.ocr_status_lbl.setText(f"✓ OCR Processed • {pages_label} extracted")
            self.ocr_status_lbl.setToolTip("")
        if is_hw:
            self.ocr_hw_badge.setText("✍ Handwritten")
            self.ocr_hw_badge.setVisible(True)
        else:
            self.ocr_hw_badge.setVisible(False)
        self.ocr_status_frame.setVisible(True)

        ocr_fields = ocr_result.get("ocr_fields", {})
        if ocr_fields:
            lines = []
            field_labels = {
                "subject": "Subject",
                "reference_no": "Ref No",
                "date": "Date",
                "deadline": "Deadline",
                "priority": "Priority",
                "amount": "Amount",
                "sender": "Sender",
                "recipient": "Recipient",
                "employee": "Employee",
                "department": "Department",
            }
            for key, label in field_labels.items():
                val = ocr_fields.get(key)
                if val:
                    if isinstance(val, list):
                        val = ", ".join(str(v) for v in val)
                    lines.append(f"{label}: {val}")
            if lines:
                self.ocr_fields_text.setText("\n".join(lines))
                self.ocr_fields_frame.setVisible(True)
            else:
                self.ocr_fields_frame.setVisible(False)
        else:
            self.ocr_fields_frame.setVisible(False)

        has_remark = ocr_result.get("has_prior_director_remark", False)
        remark_text = ocr_result.get("director_remark", "")

        if has_remark and remark_text:
            self.has_prior_director_remark = True
            self.prior_director_remark_text = str(remark_text)
            self.prior_remark_edit.setPlainText(str(remark_text))
            self.prior_review_check.setChecked(True)
            self.director_remark_card.setVisible(True)
        else:
            self.has_prior_director_remark = False
            self.prior_director_remark_text = ""
            self.prior_remark_edit.clear()
            self.prior_review_check.setChecked(False)
            self.director_remark_card.setVisible(False)
        self._update_director_flow_note()

        self._set_submit_button_text()

        if file_path and os.path.exists(file_path):
            self.selected_file = file_path
        elif ocr_result.get("file_path") and os.path.exists(ocr_result.get("file_path")):
            self.selected_file = ocr_result.get("file_path")
        elif self.selected_file and os.path.exists(self.selected_file):
            pass 
        else:
            self.selected_file = ocr_result.get("file_path") or f"data/incoming/{self.title_input.text()}"

        self._show_preview(ocr_result, mode_val, fmt_val)

    def _show_preview(self, ocr_result: Dict[str, Any], mode_val: str, fmt_val: str) -> None:
        """Show the document itself next to the extracted details."""
        local_file = self.selected_file if (self.selected_file and os.path.exists(self.selected_file)) else ""
        body = str(ocr_result.get("body") or "").strip()
        preview_text = ""
        if not local_file:
            preview_text = body or self.extracted_ocr_text
        elif os.path.splitext(local_file)[1].lower() not in (
            ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif", ".txt"
        ):
            # e.g. DOCX: cannot be drawn here, show the text that was read.
            preview_text = self.extracted_ocr_text or body

        names = [n for n in (ocr_result.get("attachment_names") or []) if n]
        display_name = os.path.basename(local_file) if local_file else (self.title_input.text() or "E-mail")
        info = f"{display_name}  •  {mode_val}  •  {fmt_val}"
        if names:
            info += f"  •  {len(names)} attachment(s): {', '.join(names[:4])}"
            if not local_file:
                info += " (none of them can be previewed)"
        self.preview_file_lbl.setText(info)

        self.document_preview.set_document({
            "file_path": local_file,
            "title": self.title_input.text(),
            "reference": "New intake",
            "mode": mode_val,
            "description": body,
            "preview_text": preview_text,
        })
        self.preview_stack.setCurrentIndex(1)

    def _update_director_flow_note(self) -> None:
        if self.prior_review_check.isChecked():
            self.director_flow_note.setText(
                "After registering, you can route this document straight to HODs, employees "
                "or the TSO. Your confirmation is recorded in the document history."
            )
        else:
            self.director_flow_note.setText(
                "Not confirmed: the document will go to the Director for review first."
            )

    @staticmethod
    def _valid_date(text: str) -> Optional[str]:
        """YYYY-MM-DD for a real calendar date, else None."""
        parsed = parse_date(text)
        return parsed.isoformat() if parsed else None

    def save_and_confirm_routing(self):
        title = self.title_input.text().strip()
        if not title:
            QMessageBox.warning(self, "Validation Error", "Please provide a document Title / Subject.")
            return

        # Dates: only real calendar dates.  OCR may have put a reference
        # number such as 44/88/2026 here; the DS must correct it first.
        received_raw = self.date_input.text().strip()
        received = self._valid_date(received_raw) if received_raw else datetime.now().strftime("%Y-%m-%d")
        if not received:
            QMessageBox.warning(
                self, "Validation Error",
                f"Received Date \"{received_raw}\" is not a valid date.\n\n"
                "Enter it as YYYY-MM-DD (for example 2026-09-27).",
            )
            self.date_input.setFocus()
            return
        deadline_raw = self.deadline_input.text().strip()
        deadline = self._valid_date(deadline_raw) if deadline_raw else None
        if deadline_raw and not deadline:
            QMessageBox.warning(
                self, "Validation Error",
                f"Target Deadline \"{deadline_raw}\" is not a valid date.\n\n"
                "Enter it as YYYY-MM-DD, or leave it empty.",
            )
            self.deadline_input.setFocus()
            return
        if deadline and deadline < received:
            QMessageBox.warning(
                self, "Validation Error",
                f"The deadline ({deadline}) is before the received date ({received}). "
                "Please correct one of them.",
            )
            self.deadline_input.setFocus()
            return
        self.date_input.setText(received)
        if deadline:
            self.deadline_input.setText(deadline)

        dept_text = self.dept_combo.currentText()
        if dept_text in ("Not Specified", ""):
            dept_text = None

        emp_raw = self.emp_combo.currentText()
        emp_text = emp_raw.split(" (")[0] if emp_raw != "Not Assigned" else None

        target_dept_id = self.dept_combo.currentData() if dept_text else None
        emp_id = self.emp_combo.currentData()
        actual_upload_path = self.selected_file if (self.selected_file and os.path.exists(self.selected_file)) else None
        ref_no = self.ref_input.text().strip() or "Auto-Generated"

        # A Director instruction already written on the document (found by
        # OCR and confirmed here by the DS) satisfies the Director review
        # step; otherwise the document goes to the Director first.
        prior_detected = self.has_prior_director_remark and self.director_remark_card.isVisible()
        prior_confirmed = prior_detected and self.prior_review_check.isChecked()
        prior_text = self.prior_remark_edit.toPlainText().strip() if prior_detected else ""
        if prior_confirmed and not prior_text:
            QMessageBox.warning(
                self, "Validation Error",
                "Enter the Director's instruction as written on the document, or untick "
                "\"The Director has already reviewed this document\".",
            )
            self.prior_remark_edit.setFocus()
            return

        if prior_confirmed:
            next_step = (
                "You confirmed the Director has already reviewed it (instruction on the "
                "document), so after registering you can route it directly to HODs, "
                "employees or the TSO."
            )
        else:
            next_step = (
                "After registering, send it to the Director for review. Once the Director "
                "has remarked, you can route it to HODs, employees or the TSO."
            )
        confirm_msg = (
            f"Register this document?\n\n"
            f"Reference: {ref_no}\n"
            f"Title: {title}\n\n"
            f"{next_step}\n\n"
            "Proceed?"
        )
        reply = QMessageBox.question(
            self,
            "Register Document",
            confirm_msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return

        inbox_item_id = self.current_inbox_item_id
        if inbox_item_id:
            # Arrived by mail: convert the intake record into a document.
            intake_payload = {
                "title": title,
                "subject": title,
                "priority": PriorityEnum.normalize(self.priority_input.currentText()),
                "source": self.source_input.text().strip() or None,
                "sender_name": self.source_input.text().strip() or None,
                "sender_reference": self.ref_input.text().strip() or None,
                "received_date": received,
                "deadline": deadline,
            }
            # What was read from the mail attachment on this screen, so the
            # server does not OCR it again, and the DS's routing choice.
            if self.extracted_ocr_text:
                intake_payload["ocr_text"] = self.extracted_ocr_text
                intake_payload["ocr_confidence"] = float(getattr(self, "extracted_ocr_confidence", 0.0) or 0.0)
                intake_fields = self._intake_ocr_fields()
                if intake_fields:
                    intake_payload["ocr_fields"] = json.loads(json.dumps(intake_fields, default=str))
            if target_dept_id:
                intake_payload["suggested_department_id"] = int(target_dept_id)
            if emp_id:
                intake_payload["suggested_employee_id"] = int(emp_id)
        else:
            if not actual_upload_path:
                QMessageBox.warning(
                    self,
                    "Register Document",
                    "Attach the document file before registering.",
                )
                return
            fields = {
                "title": title,
                "subject": title,
                "received_date": received,
                "mode": IngestionModeEnum.normalize(self.mode_input.currentText())
                or "MANUAL_UPLOAD",
                "priority": PriorityEnum.normalize(self.priority_input.currentText()),
                "source": self.source_input.text().strip() or "External",
                "sender_name": self.source_input.text().strip() or "",
                "sender_reference": self.ref_input.text().strip() or "",
                "ocr_text": self.extracted_ocr_text or "",
                "confidence": str(getattr(self, "extracted_ocr_confidence", 0.0) or 0.0),
            }
            intake_fields = self._intake_ocr_fields()
            if intake_fields:
                fields["ocr_fields"] = json.dumps(intake_fields, default=str)
            if deadline:
                fields["deadline"] = deadline
            if target_dept_id:
                fields["suggested_department_id"] = str(target_dept_id)
            if emp_id:
                fields["suggested_employee_id"] = str(emp_id)

        def register():
            """Runs on a worker thread: upload, OCR on the server, register."""
            if inbox_item_id:
                doc = document_service.process_intake(inbox_item_id, intake_payload)
            else:
                doc = document_service.manual_upload(fields, actual_upload_path)
            if not doc:
                raise RuntimeError("The server did not return the new document.")
            try:
                document_service.register_document(doc.id)
            except Exception as exc:
                # Saved but not registered: report it instead of letting the
                # DS upload the same file again (which would duplicate it).
                return doc, exc
            if prior_detected:
                # Record the DS's decision on the OCR-detected instruction.
                # A confirmation opens routing without a new Director review.
                try:
                    if prior_text:
                        document_service.verify_ocr_field(
                            doc.id, "DIRECTOR_HANDWRITTEN_REMARK", prior_text
                        )
                    document_service.verify_ocr_field(
                        doc.id, "PRIOR_DIRECTOR_REVIEW_DETECTED",
                        "true" if prior_confirmed else "false",
                    )
                except Exception as exc:
                    return (document_service.get_document(doc.id) or doc), RuntimeError(
                        "the document is registered, but confirming the Director instruction "
                        f"failed ({exc}). Confirm it from the document screen."
                    )
            return (document_service.get_document(doc.id) or doc), None

        try:
            created_doc, register_error = BusyDialog.run(
                self,
                "Registering Document",
                "Uploading the document and reading it on the server. "
                "A large scanned document can take a minute.",
                register,
            )
        except Exception as ex:
            QMessageBox.critical(
                self, "Intake Error", f"Could not register the document.\n{ex}"
            )
            return

        self.current_inbox_item_id = None
        if register_error is not None:
            QMessageBox.warning(
                self,
                "Register Document",
                f"{created_doc.reference} was saved, but registering it failed:\n"
                f"{register_error}\n\nOpen it from the Documents page to finish.",
            )
            self.clear_form()
            self.document_processed.emit(created_doc)
            return

        QMessageBox.information(
            self,
            "Document Registered",
            f"{created_doc.reference} registered.\n\n"
            + (
                "Director review confirmed from the document - choose the departments / staff."
                if getattr(created_doc, "director_review_satisfied", False)
                else "Send it to the Director for review."
            ),
        )

        # Offer routing immediately, with every destination available.
        try:
            from components.routing_dialogs import RoutingDialog

            dialog = RoutingDialog(created_doc, self)
            if dialog.exec() == dialog.DialogCode.Accepted:
                branches = dialog.get_branches()
                BusyDialog.run(
                    self, "Routing Document", "Opening the workstreams...",
                    lambda: routing_service.route(created_doc.id, branches, created_doc.version),
                )
                QMessageBox.information(
                    self,
                    "Routed",
                    f"Opened {len(branches)} workstream(s). "
                    "They now run independently of each other.",
                )
                created_doc = document_service.get_document(created_doc.id) or created_doc
        except Exception as ex:
            QMessageBox.warning(
                self,
                "Routing",
                f"The document is registered, but routing failed.\n{ex}\n\n"
                "You can route it from the Documents page.",
            )

        self.clear_form()
        self.document_processed.emit(created_doc)

    def _intake_ocr_fields(self) -> Dict[str, Any]:
        """OCR_new fields to store with the document (all unverified).

        A Director remark found at intake is sent as a detection only; the DS
        confirms it later from the document screen before the workflow uses it.
        """
        if not self.extracted_ocr_text:
            return {}
        fields: Dict[str, Any] = {}
        for key, value in (self.extracted_ocr_fields or {}).items():
            if value in (None, "", [], {}):
                continue
            fields[str(key)] = value if isinstance(value, (str, int, float, list)) else str(value)
        if self.has_prior_director_remark and self.prior_director_remark_text:
            fields.setdefault("prior_director_review_detected", "true")
            fields.setdefault(
                "director_handwritten_remark",
                self.prior_remark_edit.toPlainText().strip() or self.prior_director_remark_text,
            )
        return fields

    def clear_form(self):
        self.title_input.clear()
        self.ref_input.clear()
        self.date_input.clear()
        self.source_input.clear()
        self.deadline_input.clear()
        self.extracted_ocr_text = ""
        self.extracted_ocr_fields = {}
        self.selected_file = None
        self.current_inbox_item_id = None
        self.has_prior_director_remark = False
        self.prior_director_remark_text = ""
        self.prior_remark_edit.clear()
        self.prior_review_check.setChecked(False)
        self.ocr_status_frame.setVisible(False)
        self.ocr_fields_frame.setVisible(False)
        self.director_remark_card.setVisible(False)

        self.preview_label.setText("No document loaded\n\nSelect an incoming item from Inbox or click 'Manual Intake / Upload File' to process a document.")
        self.preview_stack.setCurrentIndex(0)
        self.document_preview.set_document({})
        self.dept_combo.setCurrentIndex(0)
        self.emp_combo.setCurrentIndex(0)
        self.confidence_label.setText("Confidence: — • Source: Document / OCR")
        self._set_submit_button_text()

    def _set_submit_button_text(self):
        """Keep the intake action label consistent with the mandatory
          flow."""
        self.submit_btn.setText("Register Document")