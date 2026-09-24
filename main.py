import os
import sys

# Ensure frontend directory is at the beginning of sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")
if FRONTEND_DIR not in sys.path:
    sys.path.insert(0, FRONTEND_DIR)

from PySide6.QtWidgets import QApplication
from ui.login import LoginWindow

app = QApplication(sys.argv)

theme_path = os.path.join(FRONTEND_DIR, "styles", "theme.qss")
if not os.path.exists(theme_path):
    theme_path = os.path.join(ROOT_DIR, "styles", "theme.qss")

if os.path.exists(theme_path):
    with open(theme_path, "r", encoding="utf-8") as file:
        app.setStyleSheet(file.read())

window = LoginWindow()
window.show()
sys.exit(app.exec())
