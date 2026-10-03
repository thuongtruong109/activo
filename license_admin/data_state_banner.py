"""Persistent dashboard status for empty and recovery-mode project data."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout


class DataStateBanner(QFrame):
    retry_requested = Signal()
    open_folder_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dataStateBanner")
        self.setProperty("state", "empty")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 10, 10)
        layout.setSpacing(12)
        copy = QVBoxLayout()
        copy.setSpacing(2)
        self.title_label = QLabel()
        self.title_label.setObjectName("dataStateTitle")
        self.body_label = QLabel()
        self.body_label.setObjectName("dataStateBody")
        self.body_label.setWordWrap(True)
        copy.addWidget(self.title_label)
        copy.addWidget(self.body_label)
        layout.addLayout(copy, 1)

        self.retry_button = QPushButton()
        self.retry_button.setObjectName("dataStateAction")
        self.retry_button.clicked.connect(self.retry_requested)
        layout.addWidget(self.retry_button)
        self.open_folder_button = QPushButton()
        self.open_folder_button.setObjectName("dataStateAction")
        self.open_folder_button.clicked.connect(self.open_folder_requested)
        layout.addWidget(self.open_folder_button)

    def set_content(
        self,
        *,
        state: str,
        title: str,
        body: str,
        retry_label: str,
        open_folder_label: str,
        recovery: bool,
        detail: str = "",
    ) -> None:
        self.setProperty("state", state)
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.setToolTip(detail)
        self.retry_button.setText(retry_label)
        self.open_folder_button.setText(open_folder_label)
        self.retry_button.setVisible(recovery)
        self.open_folder_button.setVisible(recovery)
        self.style().unpolish(self)
        self.style().polish(self)
