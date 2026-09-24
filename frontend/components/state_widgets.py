from typing import Callable, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LoadingSpinnerWidget(QFrame):
    """
    Reusable loading indicator widget for asynchronous data operations.
    Can be placed inside any container or stacked widget.
    """

    def __init__(self, message: str = "Loading data, please wait...", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("loadingWidget")

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 22, 16, 22)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate mode
        self.progress_bar.setMinimumWidth(120)
        self.progress_bar.setMaximumWidth(320)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)

        self.label = QLabel(message)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("color: #64748B; font-size: 13px; font-weight: 500;")

        layout.addWidget(self.progress_bar, 0, Qt.AlignCenter)
        layout.addWidget(self.label, 0, Qt.AlignCenter)

        self.setLayout(layout)

    def set_message(self, message: str) -> None:
        """Updates the displayed loading message."""
        self.label.setText(message)


class ErrorStateWidget(QFrame):
    """
    Reusable error state widget for displaying API or network failures.
    Provides an optional 'Retry' button connected to a retry callback.
    """

    def __init__(
        self,
        message: str = "An error occurred while loading data.",
        on_retry: Optional[Callable[[], None]] = None,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.setObjectName("errorWidget")
        self._on_retry = on_retry

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 22, 16, 22)

        # Error Icon / Badge
        self.icon_label = QLabel("⚠️")
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 28px;")

        # Title
        self.title_label = QLabel("Unable to Load Data")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #E11D48; font-size: 15px; font-weight: 600;")

        # Detail Message
        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("color: #64748B; font-size: 13px;")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)

        # Retry Action Button
        if on_retry:
            btn_layout = QHBoxLayout()
            btn_layout.setAlignment(Qt.AlignCenter)

            self.retry_button = QPushButton("Retry")
            self.retry_button.setMinimumWidth(100)
            self.retry_button.setMaximumWidth(160)
            self.retry_button.setMinimumHeight(32)
            self.retry_button.setMaximumHeight(38)
            self.retry_button.setStyleSheet("""
                QPushButton {
                    background-color: #0F172A;
                    color: white;
                    border-radius: 6px;
                    font-weight: 600;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #1E293B;
                }
            """)
            self.retry_button.clicked.connect(self._handle_retry)
            btn_layout.addWidget(self.retry_button)
            layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _handle_retry(self) -> None:
        if self._on_retry:
            self._on_retry()

    def set_error(self, message: str) -> None:
        """Updates the displayed error description."""
        self.message_label.setText(message)


class EmptyStateWidget(QFrame):
    """
    Reusable empty state widget for displaying zero-result lists, queues, or search results.
    """

    def __init__(
        self,
        title: str = "No Documents Found",
        message: str = "There are no records matching your current filter criteria.",
        icon: str = "📄",
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.setObjectName("emptyWidget")

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 26, 16, 26)

        self.icon_label = QLabel(icon)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 32px;")

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #334155; font-size: 15px; font-weight: 600;")

        self.message_label = QLabel(message)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("color: #94A3B8; font-size: 13px;")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)

        self.setLayout(layout)

    def set_content(self, title: str, message: str) -> None:
        """Updates empty state title and message."""
        self.title_label.setText(title)
        self.message_label.setText(message)
