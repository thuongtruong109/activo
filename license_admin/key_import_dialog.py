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
    PRIVATE_KEY_FILENAME,
    PUBLIC_KEY_FILENAME,
    ImportedKeyPair,
    KeyPasswordRequiredError,
    import_key_pair,
    inspect_key_pair,
    public_key_fingerprint,
)
from license_admin.icons import svg_icon
from license_admin.localization import text


class KeyImportDialog(QDialog):
    """Collect, validate and copy a key pair into a target or staging area."""

    def __init__(
        self,
        parent: QWidget,
        *,
        project_name: str,
        project_directory: Path,
        record_count: int,
        install_directory: Path | None = None,
        display_directory: Path | None = None,
        current_private_key_path: Path | None = None,
        current_public_key_path: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_directory = project_directory
        self._install_directory = install_directory or project_directory
        self._display_directory = display_directory or project_directory
        self._record_count = record_count
        self._current_private_key_path = current_private_key_path
        self._current_public_key_path = current_public_key_path
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
                    f"{self._display_directory / PRIVATE_KEY_FILENAME}\n"
                    f"{self._display_directory / PUBLIC_KEY_FILENAME}"
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
        button.setAccessibleName(f"{text('common.choose')} {label}")
        button.setToolTip(label)

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

        private_target = self._project_directory / PRIVATE_KEY_FILENAME
        public_target = self._project_directory / PUBLIC_KEY_FILENAME
        install_private = self._install_directory / PRIVATE_KEY_FILENAME
        install_public = self._install_directory / PUBLIC_KEY_FILENAME
        source_is_target = (
            self._current_private_key_path is not None
            and self._current_public_key_path is not None
            and private_path.resolve(strict=False)
            == self._current_private_key_path.resolve(strict=False)
            and public_path.resolve(strict=False)
            == self._current_public_key_path.resolve(strict=False)
        )
        targets_exist = any(
            path.exists()
            for path in (
                private_target,
                public_target,
                install_private,
                install_public,
                self._current_private_key_path,
                self._current_public_key_path,
            )
            if path is not None
        )
        if targets_exist and not source_is_target:
            changed_public_key = True
            comparison_key = (
                install_public
                if install_public.is_file()
                else (
                    self._current_public_key_path
                    if self._current_public_key_path is not None
                    else public_target
                )
            )
            if comparison_key.is_file():
                try:
                    changed_public_key = (
                        public_key_fingerprint(comparison_key) != info.fingerprint
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
                self._install_directory,
                password=password,
                overwrite=install_private.exists() or install_public.exists(),
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
