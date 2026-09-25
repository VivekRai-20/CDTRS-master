"""
fineTune/label_tool.py
----------------------
STEP 2 - label the line images made by prepare_dataset.py.

    python fineTune/label_tool.py

For each line image you:
  1. type the text exactly as written (start from PaddleOCR's guess), and
  2. choose Handwritten or Printed - or Skip for images that are not a
     single readable text line (stamps, signatures, cut-off lines).

Keys
  Enter            save and go to the next line
  Ctrl+H / Ctrl+P  mark Handwritten / Printed
  Ctrl+K           mark Skip (and go to the next line)
  Page Down / Up   next / previous line without saving
  Ctrl+G           copy PaddleOCR's reading into the text box

Every save is written to datasets/labels.csv immediately, so you can stop at
any time and continue later.  Uses PySide6 (already installed for CDTRS).
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QKeySequence, QPixmap, QShortcut  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QButtonGroup, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QRadioButton, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from common import (  # noqa: E402
    HANDWRITTEN, LABELS_CSV, PRINTED, SKIP, is_labelled, line_image_path, read_labels, write_labels,
)

FILTERS = ["Not labelled yet", "All lines", "Handwritten", "Printed", "Skipped", "Test split"]


class LabelTool(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CDTRS handwriting labelling")
        self.resize(1200, 620)
        self.rows = read_labels()
        self.visible: list[int] = []
        self.position = 0

        # --- top bar -----------------------------------------------------
        self.filter_box = QComboBox()
        self.filter_box.addItems(FILTERS)
        self.filter_box.currentIndexChanged.connect(self._apply_filter)
        self.jump = QSpinBox()
        self.jump.setMinimum(1)
        self.jump.valueChanged.connect(self._jump_to)
        self.progress = QLabel()
        top = QHBoxLayout()
        top.addWidget(QLabel("Show:"))
        top.addWidget(self.filter_box)
        top.addSpacing(16)
        top.addWidget(QLabel("Go to #"))
        top.addWidget(self.jump)
        top.addStretch()
        top.addWidget(self.progress)

        # --- image ---------------------------------------------------------
        self.image_label = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: white; border: 1px solid #cbd5e1;")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.image_label)
        scroll.setMinimumHeight(220)
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(25, 300)
        self.zoom.setValue(100)
        self.zoom.valueChanged.connect(self._show_image)
        self.info = QLabel()
        self.info.setStyleSheet("color: #475569;")

        # --- answer ------------------------------------------------------------
        self.ocr_label = QLabel()
        self.ocr_label.setStyleSheet("color: #64748b;")
        self.text_edit = QLineEdit()
        self.text_edit.setStyleSheet("font-size: 18px; padding: 6px;")
        self.text_edit.setPlaceholderText("Type the text exactly as written in the image")
        self.text_edit.returnPressed.connect(self._save_and_next)
        self.kind_group = QButtonGroup(self)
        self.radio_hw = QRadioButton("Handwritten (Ctrl+H)")
        self.radio_pr = QRadioButton("Printed (Ctrl+P)")
        self.radio_skip = QRadioButton("Skip - not a text line (Ctrl+K)")
        for button in (self.radio_hw, self.radio_pr, self.radio_skip):
            self.kind_group.addButton(button)
        kinds = QHBoxLayout()
        for button in (self.radio_hw, self.radio_pr, self.radio_skip):
            kinds.addWidget(button)
        kinds.addStretch()

        prev_btn = QPushButton("< Previous (PgUp)")
        prev_btn.clicked.connect(lambda: self._move(-1))
        next_btn = QPushButton("Next > (PgDn)")
        next_btn.clicked.connect(lambda: self._move(1))
        copy_btn = QPushButton("Use OCR text (Ctrl+G)")
        copy_btn.clicked.connect(self._copy_ocr)
        save_btn = QPushButton("Save && Next (Enter)")
        save_btn.setStyleSheet("background: #2563eb; color: white; font-weight: 600; padding: 6px 14px;")
        save_btn.clicked.connect(self._save_and_next)
        buttons = QHBoxLayout()
        buttons.addWidget(prev_btn)
        buttons.addWidget(next_btn)
        buttons.addStretch()
        buttons.addWidget(copy_btn)
        buttons.addWidget(save_btn)

        layout = QVBoxLayout()
        layout.addLayout(top)
        layout.addWidget(scroll, 1)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Zoom"))
        zoom_row.addWidget(self.zoom)
        zoom_row.addWidget(self.info, 1)
        layout.addLayout(zoom_row)
        layout.addWidget(self.ocr_label)
        layout.addWidget(self.text_edit)
        layout.addLayout(kinds)
        layout.addLayout(buttons)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        for keys, action in (
            ("Ctrl+H", lambda: self.radio_hw.setChecked(True)),
            ("Ctrl+P", lambda: self.radio_pr.setChecked(True)),
            ("Ctrl+K", self._skip),
            ("PgDown", lambda: self._move(1)),
            ("PgUp", lambda: self._move(-1)),
            ("Ctrl+G", self._copy_ocr),
        ):
            QShortcut(QKeySequence(keys), self, activated=action)

        self._apply_filter()

    # ------------------------------------------------------------------ #
    def _apply_filter(self) -> None:
        choice = self.filter_box.currentText()
        def keep(row: dict) -> bool:
            kind = (row.get("type") or "").upper()
            if choice == "Not labelled yet":
                return not is_labelled(row)
            if choice == "Handwritten":
                return kind == HANDWRITTEN
            if choice == "Printed":
                return kind == PRINTED
            if choice == "Skipped":
                return kind == SKIP
            if choice == "Test split":
                return row.get("split") == "test"
            return True
        self.visible = [i for i, row in enumerate(self.rows) if keep(row)]
        self.position = 0
        self.jump.blockSignals(True)
        self.jump.setMaximum(max(1, len(self.visible)))
        self.jump.setValue(1)
        self.jump.blockSignals(False)
        self._show()

    def _current(self) -> dict | None:
        if not self.visible or not (0 <= self.position < len(self.visible)):
            return None
        return self.rows[self.visible[self.position]]

    def _show(self) -> None:
        done = sum(1 for row in self.rows if is_labelled(row))
        self.progress.setText(f"Labelled {done} of {len(self.rows)}")
        row = self._current()
        if row is None:
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("Nothing to show here - all lines in this view are labelled.")
            self.ocr_label.setText("")
            self.info.setText("")
            self.text_edit.clear()
            return
        self.jump.blockSignals(True)
        self.jump.setValue(self.position + 1)
        self.jump.blockSignals(False)
        self._show_image()
        self.info.setText(
            f"#{self.position + 1} of {len(self.visible)}   {row['image']}   "
            f"(from {row.get('source', '')}, page {row.get('page', '')}, split {row.get('split', '')})"
        )
        conf = row.get("ocr_confidence") or ""
        self.ocr_label.setText(
            f"PaddleOCR read: {row.get('ocr_text', '')!r}   (confidence {conf})   "
            f"guessed type: {row.get('predicted_type') or '-'}"
        )
        self.text_edit.setText(row.get("text") or row.get("ocr_text") or "")
        self.text_edit.selectAll()
        self.text_edit.setFocus()
        kind = (row.get("type") or row.get("predicted_type") or "").upper()
        self.kind_group.setExclusive(False)
        for button in (self.radio_hw, self.radio_pr, self.radio_skip):
            button.setChecked(False)
        self.kind_group.setExclusive(True)
        {HANDWRITTEN: self.radio_hw, PRINTED: self.radio_pr, SKIP: self.radio_skip}.get(
            kind, self.radio_hw).setChecked(True)

    def _show_image(self) -> None:
        row = self._current()
        if row is None:
            return
        pixmap = QPixmap(str(line_image_path(row)))
        if pixmap.isNull():
            self.image_label.setText(f"Image not found: {line_image_path(row)}")
            return
        target_height = max(24, int(96 * self.zoom.value() / 100))
        self.image_label.setPixmap(pixmap.scaledToHeight(target_height, Qt.TransformationMode.SmoothTransformation))

    def _move(self, step: int) -> None:
        if self.visible:
            self.position = max(0, min(len(self.visible) - 1, self.position + step))
            self._show()

    def _jump_to(self, value: int) -> None:
        self.position = max(0, min(len(self.visible) - 1, value - 1))
        self._show()

    def _copy_ocr(self) -> None:
        row = self._current()
        if row is not None:
            self.text_edit.setText(row.get("ocr_text") or "")

    def _save(self, kind: str) -> bool:
        row = self._current()
        if row is None:
            return False
        text = " ".join(self.text_edit.text().split())
        if kind != SKIP and not text:
            QMessageBox.information(self, "Text missing", "Type the text of the line, or mark it Skip.")
            return False
        row["type"] = kind
        row["text"] = text if kind != SKIP else ""
        row["labelled_at"] = datetime.now().isoformat(timespec="seconds")
        try:
            write_labels(self.rows)
        except PermissionError:
            QMessageBox.warning(self, "Could not save",
                                f"{LABELS_CSV} is open in another program (Excel?). Close it and try again.")
            return False
        return True

    def _selected_kind(self) -> str:
        if self.radio_pr.isChecked():
            return PRINTED
        if self.radio_skip.isChecked():
            return SKIP
        return HANDWRITTEN

    def _advance_after_save(self) -> None:
        if self.filter_box.currentText() == "Not labelled yet":
            # the saved row leaves this view
            del self.visible[self.position]
            self.position = min(self.position, max(0, len(self.visible) - 1))
        else:
            self.position = min(self.position + 1, max(0, len(self.visible) - 1))
        self.jump.setMaximum(max(1, len(self.visible)))
        self._show()

    def _save_and_next(self) -> None:
        if self._save(self._selected_kind()):
            self._advance_after_save()

    def _skip(self) -> None:
        self.radio_skip.setChecked(True)
        if self._save(SKIP):
            self._advance_after_save()


def main() -> None:
    if not LABELS_CSV.exists():
        print(f"{LABELS_CSV} does not exist yet. Run  python fineTune/prepare_dataset.py  first.")
        sys.exit(1)
    app = QApplication(sys.argv)
    window = LabelTool()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
