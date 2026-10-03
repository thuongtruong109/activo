"""User interface for importing one project's Google service account."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from issue_license import LicenseIssueError
from license_admin.icons import svg_icon
from license_admin.localization import text
from license_admin.service_account_store import (
    ImportedServiceAccount,
    SERVICE_ACCOUNT_FILENAME,
    import_service_account,
    inspect_service_account,
)


class ServiceAccountImportDialog(QDialog):
    """Validate and copy Google credentials into a target or staging area."""

    def __init__(
        self,
        parent: QWidget,
        *,
        project_name: str,
        project_directory: Path,
        install_directory: Path | None = None,
        display_directory: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_directory = project_directory
        self._install_directory = install_directory or project_directory
        self._display_directory = display_directory or project_directory
        self._imported: ImportedServiceAccount | None = None
        self.setWindowTitle(text("credential.title", project=project_name))
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)
        intro = QLabel(
            text("credential.intro")
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        form = QFormLayout()
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        self.source_edit = QLineEdit()
        self.source_edit.setObjectName("importServiceAccount")
        self.source_edit.setPlaceholderText(text("credential.placeholder"))
        self.browse_button = QPushButton(text("common.choose"))
        self.browse_button.setIcon(svg_icon("folder", 16))
        self.browse_button.setAccessibleName(
            f"{text('common.choose')} {text('credential.source')}"
        )
        self.browse_button.setToolTip(text("credential.source"))
        self.browse_button.clicked.connect(self._browse)
        row.addWidget(self.source_edit, 1)
        row.addWidget(self.browse_button)
        form.addRow(text("credential.source"), container)
        layout.addLayout(form)

        destination = QLabel(
            text(
                "credential.destination",
                path=self._display_directory / SERVICE_ACCOUNT_FILENAME,
            )
        )
        destination.setWordWrap(True)
        destination.setObjectName("muted")
        layout.addWidget(destination)

        warning = QLabel(
            text("credential.warning")
        )
        warning.setWordWrap(True)
        warning.setObjectName("warning")
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        import_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        import_button.setText(text("credential.verify_import"))
        import_button.setIcon(svg_icon("upload", 16))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setIcon(
            svg_icon("close", 16)
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            text("common.cancel")
        )
        buttons.accepted.connect(self._validate_and_import)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            text("credential.title", project=""),
            self.source_edit.text(),
            f"JSON (*.json);;{text('common.all_files')}",
        )
        if selected:
            self.source_edit.setText(selected)

    def _validate_and_import(self) -> None:
        source_text = self.source_edit.text().strip()
        if not source_text:
            QMessageBox.warning(
                self,
                text("message.missing_configuration"),
                text("credential.missing"),
            )
            return
        source = Path(source_text)
        try:
            info = inspect_service_account(source)
        except LicenseIssueError as exc:
            QMessageBox.warning(self, text("credential.invalid"), str(exc))
            return

        target = self._project_directory / SERVICE_ACCOUNT_FILENAME
        install_target = self._install_directory / SERVICE_ACCOUNT_FILENAME
        source_is_target = (
            source.resolve(strict=False) == target.resolve(strict=False)
        )
        replaces_existing = (
            target.exists() or install_target.exists()
        ) and not source_is_target
        if replaces_existing:
            answer = QMessageBox.warning(
                self,
                text("credential.replace_title"),
                text("credential.replace_body", email=info.client_email),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self._imported = import_service_account(
                source,
                self._install_directory,
                overwrite=install_target.exists(),
            )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("credential.import_failed"), str(exc))
            return
        self.accept()

    def imported_service_account(self) -> ImportedServiceAccount:
        if self._imported is None:
            raise RuntimeError("No service account has been imported.")
        return self._imported
