"""User interface for safely importing one project's RSA key pair."""

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
from license_admin.key_store import (
    ImportedKeyPair,
    KeyPasswordRequiredError,
    import_key_pair,
    inspect_key_pair,
    public_key_fingerprint,
)
from license_admin.icons import svg_icon
from license_admin.localization import text


class KeyImportDialog(QDialog):
    """Collect, validate and copy a key pair into one project directory."""

    def __init__(
        self,
        parent: QWidget,
        *,
        project_name: str,
        project_directory: Path,
        record_count: int,
    ) -> None:
        super().__init__(parent)
        self._project_directory = project_directory
        self._record_count = record_count
        self._imported_pair: ImportedKeyPair | None = None
        self.setWindowTitle(text("key.title", project=project_name))
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)
        intro = QLabel(
            text("key.intro")
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        form = QFormLayout()
        self.private_key_edit = self._path_field(
            form,
            text("key.private_source"),
            text("key.private_source"),
        )
        self.private_key_edit.setObjectName("importPrivateKey")
        self.public_key_edit = self._path_field(
            form,
            text("key.public_source"),
            text("key.public_source"),
        )
        self.public_key_edit.setObjectName("importPublicKey")
        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("importKeyPassword")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText(text("key.password_placeholder"))
        form.addRow(text("key.password"), self.password_edit)
        layout.addLayout(form)

        destination = QLabel(
            text(
                "key.destination",
                path=(
                    f"{project_directory / 'private.pem'}\n"
                    f"{project_directory / 'public.pem'}"
                ),
            )
        )
        destination.setWordWrap(True)
        destination.setObjectName("muted")
        layout.addWidget(destination)

        warning = QLabel(
            text("key.warning")
        )
        warning.setWordWrap(True)
        warning.setObjectName("warning")
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        import_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        import_button.setText(text("key.verify_import"))
        import_button.setIcon(svg_icon("key", 16))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setIcon(
            svg_icon("close", 16)
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            text("common.cancel")
        )
        buttons.accepted.connect(self._validate_and_import)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _path_field(
        self,
        form: QFormLayout,
        label: str,
        title: str,
    ) -> QLineEdit:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        button = QPushButton(text("common.choose"))
        button.setIcon(svg_icon("folder", 16))

        def browse() -> None:
            selected, _ = QFileDialog.getOpenFileName(
                self,
                title,
                edit.text(),
                f"PEM (*.pem);;{text('common.all_files')}",
            )
            if selected:
                edit.setText(selected)

        button.clicked.connect(browse)
        row.addWidget(edit, 1)
        row.addWidget(button)
        form.addRow(label, container)
        return edit

    def _validate_and_import(self) -> None:
        private_text = self.private_key_edit.text().strip()
        public_text = self.public_key_edit.text().strip()
        if not private_text or not public_text:
            QMessageBox.warning(
                self,
                text("message.missing_configuration"),
                text("key.missing"),
            )
            return

        private_path = Path(private_text)
        public_path = Path(public_text)
        password_text = self.password_edit.text()
        password = password_text.encode("utf-8") if password_text else None
        try:
            info = inspect_key_pair(private_path, public_path, password=password)
        except KeyPasswordRequiredError:
            QMessageBox.warning(
                self,
                text("key.password_required"),
                text("key.password_body"),
            )
            self.password_edit.setFocus()
            return
        except LicenseIssueError as exc:
            QMessageBox.warning(self, text("key.invalid_pair"), str(exc))
            return

        private_target = self._project_directory / "private.pem"
        public_target = self._project_directory / "public.pem"
        source_is_target = (
            private_path.resolve(strict=False) == private_target.resolve(strict=False)
            and public_path.resolve(strict=False) == public_target.resolve(strict=False)
        )
        targets_exist = private_target.exists() or public_target.exists()
        if targets_exist and not source_is_target:
            changed_public_key = True
            if public_target.is_file():
                try:
                    changed_public_key = (
                        public_key_fingerprint(public_target) != info.fingerprint
                    )
                except LicenseIssueError:
                    changed_public_key = True
            if changed_public_key and self._record_count:
                message = text("key.replace_licenses", count=self._record_count)
            else:
                message = text("key.replace_existing")
            answer = QMessageBox.warning(
                self,
                text("key.replace_title"),
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        try:
            self._imported_pair = import_key_pair(
                private_path,
                public_path,
                self._project_directory,
                password=password,
                overwrite=targets_exist,
            )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("key.import_failed"), str(exc))
            return
        self.password_edit.clear()
        self.accept()

    def imported_pair(self) -> ImportedKeyPair:
        if self._imported_pair is None:
            raise RuntimeError("No key pair has been imported.")
        return self._imported_pair
