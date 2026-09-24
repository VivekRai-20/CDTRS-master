from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel
)


class BasePage(QWidget):

    def __init__(self, title, subtitle=""):
        super().__init__()

        layout = QVBoxLayout()
        layout.setContentsMargins(30, 25, 30, 30)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")

        layout.addWidget(title_label)

        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("pageSubtitle")
            layout.addWidget(subtitle_label)

        layout.addStretch()

        self.setLayout(layout)