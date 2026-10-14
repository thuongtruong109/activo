"""Visible next steps for local changes awaiting publication."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from license_admin.icons import svg_icon
from license_admin.localization import text
from license_admin.responsive import wrap_label


class PublicationPanel(QFrame):
    publish_requested = Signal()
    review_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("publicationPanel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        self.title = QLabel()
        self.title.setObjectName("publicationTitle")
        wrap_label(self.title)
        self.body = QLabel()
        self.body.setObjectName("publicationBody")
        wrap_label(self.body)
        layout.addWidget(self.title)
        layout.addWidget(self.body)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.publish_button = QPushButton()
        self.publish_button.setObjectName("primaryButton")
        self.publish_button.setIcon(svg_icon("upload", 16, "#02131c"))
        self.publish_button.clicked.connect(self.publish_requested)
        self.review_button = QPushButton()
        self.review_button.clicked.connect(self.review_requested)
        actions.addWidget(self.publish_button)
        actions.addWidget(self.review_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.hide()

    def update_state(
        self, *, state: str, has_data: bool, pending_revocations: int,
        revocation_count: int, writable: bool, busy: bool, sheet_configured: bool,
    ) -> None:
        pending = state in {"dirty", "revocation_pending", "revoked_pending"} or (
            state == "unsynced" and has_data
        )
        self.setVisible(pending and writable)
        self.title.setText(text("publication.pending"))
        if pending_revocations:
            self.body.setText(text("publication.revocations", count=pending_revocations))
        else:
            self.body.setText(text("publication.body"))
        if not sheet_configured:
            self.body.setText(self.body.text() + " " + text("publication.setup"))
        self.publish_button.setText(text("publication.publish"))
        self.publish_button.setEnabled(writable and not busy)
        self.review_button.setText(text("publication.review"))
        self.review_button.setVisible(revocation_count > 0)
        self.review_button.setEnabled(not busy)
