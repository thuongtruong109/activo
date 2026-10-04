"""Focused dialogs for editing licenses and application settings."""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from issue_license import LicenseIssueError, MAX_LICENSE_DAYS, normalize_hwid
from license_admin.domain import LicenseRecord
from license_admin.google_sheets import extract_spreadsheet_id
from license_admin.icons import svg_icon
from license_admin.key_import_dialog import KeyImportDialog
from license_admin.key_store import KeyPasswordRequiredError, inspect_key_pair
from license_admin.localization import text
from license_admin.responsive import fit_window_to_screen, responsive_form, scroll_container
from license_admin.service_account_import_dialog import ServiceAccountImportDialog
from license_admin.service_account_store import inspect_service_account
from license_admin.settings import AdminSettings, ProjectStore
from license_admin.settings_transaction import SettingsTransaction
from license_admin.window_chrome import (
    FramelessResizeController,
    FramelessTabHeader,
    enable_frameless_window,
)


class LicenseEditorDialog(QDialog):
    def __init__(self, parent: QWidget, record: LicenseRecord | None = None) -> None:
        super().__init__(parent)
        self._record = record
        self.setWindowTitle(
            text("editor.edit_title") if record else text("editor.new_title")
        )
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        intro = QLabel(
            text("editor.intro")
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        form = QFormLayout()
        self.username_edit = QLineEdit(record.username if record else "")
        self.username_edit.setPlaceholderText(text("editor.username_placeholder"))
        self.hwid_edit = QLineEdit(record.hwid if record else "")
        self.hwid_edit.setPlaceholderText(text("editor.hwid_placeholder"))
        self.hwid_edit.setMaxLength(64)
        self.expiry_edit = QDateEdit()
        self.expiry_edit.setCalendarPopup(True)
        self.expiry_edit.setDisplayFormat("dd/MM/yyyy")
        utc_today = datetime.now(timezone.utc).date()
        utc_qdate = QDate(utc_today.year, utc_today.month, utc_today.day)
        self.expiry_edit.setMinimumDate(utc_qdate.addDays(1))
        self.expiry_edit.setMaximumDate(utc_qdate.addDays(MAX_LICENSE_DAYS - 1))
        default_expiry = utc_qdate.addDays(365)
        if record and record.expires_at:
            existing = QDate(
                record.expires_at.year,
                record.expires_at.month,
                record.expires_at.day,
            )
            if existing >= self.expiry_edit.minimumDate():
                default_expiry = min(existing, self.expiry_edit.maximumDate())
        self.expiry_edit.setDate(default_expiry)
        form.addRow(text("editor.username"), self.username_edit)
        form.addRow(text("editor.hwid"), self.hwid_edit)
        form.addRow(text("editor.expiry"), self.expiry_edit)

        self.quick_select_row = QWidget()
        presets = QHBoxLayout(self.quick_select_row)
        presets.setContentsMargins(0, 0, 0, 0)
        presets.setSpacing(6)
        self.quick_select_buttons: list[QPushButton] = []
        for days, label in (
            (30, text("editor.30_days")),
            (90, text("editor.90_days")),
            (365, text("editor.1_year")),
            (730, text("editor.2_years")),
        ):
            button = QPushButton(label)
            button.setIcon(svg_icon("clock", 16))
            button.clicked.connect(
                lambda checked=False, duration=days: self.expiry_edit.setDate(
                    utc_qdate.addDays(duration)
                )
            )
            self.quick_select_buttons.append(button)
            presets.addWidget(button, 1)
        form.addRow(text("editor.quick"), self.quick_select_row)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText(text("editor.sign_save"))
        save_button.setIcon(svg_icon("check", 16))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setIcon(
            svg_icon("close", 16)
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            text("common.cancel")
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        try:
            username = self.username_edit.text().strip()
            if not username or len(username) > 200:
                raise LicenseIssueError(text("validation.username_length"))
            if any(ord(character) < 32 for character in username):
                raise LicenseIssueError(text("validation.username_control"))
            normalize_hwid(self.hwid_edit.text())
        except LicenseIssueError as exc:
            QMessageBox.warning(self, text("message.invalid_data"), str(exc))
            return
        self.accept()

    def values(self) -> tuple[str, str, datetime]:
        selected = self.expiry_edit.date()
        expiry = datetime.combine(
            datetime(selected.year(), selected.month(), selected.day()).date(),
            time(23, 59, 59),
            tzinfo=timezone.utc,
        )
        return (
            self.username_edit.text().strip(),
            normalize_hwid(self.hwid_edit.text()),
            expiry,
        )


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        values: AdminSettings,
        *,
        project_directory: Path,
        record_count: int,
    ) -> None:
        super().__init__(parent)
        enable_frameless_window(self)
        self.setObjectName("settingsDialog")
        self._project_directory = project_directory
        self._record_count = record_count
        self._initial_settings = values
        self._transaction = SettingsTransaction(project_directory)
        self._validated_key_paths: tuple[Path, Path] | None = None
        self.setWindowTitle(text("settings.title"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self.settings_tab_header = FramelessTabHeader(self)
        layout.addWidget(self.settings_tab_header)
        body = QWidget()
        body.setObjectName("settingsBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 8, 10, 10)
        body_layout.setSpacing(8)
        self.settings_pages = QStackedWidget()
        self.settings_pages.setObjectName("settingsPages")
        self.settings_tab_header.current_changed.connect(
            self.settings_pages.setCurrentIndex
        )
        body_layout.addWidget(self.settings_pages, 1)
        layout.addWidget(body, 1)

        files_tab = QWidget()
        files_form = QFormLayout(files_tab)
        self.project_name_edit = QLineEdit(values.project_name)
        self.project_id_edit = QLineEdit(values.project_id)
        self.project_id_edit.setReadOnly(True)
        files_form.addRow(text("settings.project_name"), self.project_name_edit)
        files_form.addRow(text("settings.project_id"), self.project_id_edit)
        self.local_csv_edit = self._path_field(
            files_form,
            text("settings.admin_data"),
            values.local_csv_path,
            f"CSV (*.csv);;{text('common.all_files')}",
            save=True,
        )
        self.signing_key_edit = self._path_field(
            files_form,
            text("settings.private_key"),
            values.signing_key_path,
            f"PEM (*.pem);;{text('common.all_files')}",
        )
        self.public_key_edit = self._path_field(
            files_form,
            text("settings.public_key"),
            values.public_key_path,
            f"PEM (*.pem);;{text('common.all_files')}",
        )
        self.import_keys_button = QPushButton(text("settings.import_keys"))
        self.import_keys_button.setObjectName("importProjectKeys")
        self.import_keys_button.setIcon(svg_icon("key", 16))
        self.import_keys_button.clicked.connect(self._import_keys)
        files_form.addRow("", self.import_keys_button)
        key_warning = QLabel(
            text("settings.key_note")
        )
        key_warning.setWordWrap(True)
        key_warning.setObjectName("warning")
        files_form.addRow("", key_warning)
        responsive_form(files_form)
        self.settings_pages.addWidget(scroll_container(files_tab))
        self.settings_tab_header.add_tab(text("settings.tab_files"))

        google_tab = QWidget()
        google_form = QFormLayout(google_tab)
        self.sheet_id_edit = QLineEdit(values.spreadsheet_id)
        self.sheet_id_edit.setPlaceholderText(
            text("settings.spreadsheet_placeholder")
        )
        self.worksheet_edit = QLineEdit(values.worksheet)
        self.public_url_edit = QLineEdit(values.public_csv_url)
        self.public_url_edit.setPlaceholderText("https://docs.google.com/.../export?format=csv")
        self.credentials_edit = self._path_field(
            google_form,
            text("settings.service_json"),
            values.service_account_path,
            f"JSON (*.json);;{text('common.all_files')}",
        )
        self.import_credentials_button = QPushButton(text("settings.import_json"))
        self.import_credentials_button.setObjectName("importProjectCredentials")
        self.import_credentials_button.setIcon(svg_icon("upload", 16))
        self.import_credentials_button.clicked.connect(self._import_credentials)
        google_form.addRow("", self.import_credentials_button)
        google_form.insertRow(0, text("settings.spreadsheet"), self.sheet_id_edit)
        google_form.insertRow(1, text("settings.worksheet"), self.worksheet_edit)
        google_form.insertRow(2, text("settings.public_url"), self.public_url_edit)
        note = QLabel(
            text("settings.google_note")
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        google_form.addRow("", note)
        responsive_form(google_form)
        self.settings_pages.addWidget(scroll_container(google_tab))
        self.settings_tab_header.add_tab(text("settings.tab_sheets"))

        claims_tab = QWidget()
        claims_form = QFormLayout(claims_tab)
        self.issuer_edit = QLineEdit(values.issuer)
        self.audience_edit = QLineEdit(values.audience)
        claims_form.addRow(text("settings.issuer"), self.issuer_edit)
        claims_form.addRow(text("settings.audience"), self.audience_edit)
        claims_note = QLabel(
            text("settings.claims_note")
        )
        claims_note.setWordWrap(True)
        claims_note.setObjectName("warning")
        claims_form.addRow("", claims_note)
        responsive_form(claims_form)
        self.settings_pages.addWidget(scroll_container(claims_tab))
        self.settings_tab_header.add_tab(text("settings.tab_claims"))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
        save_button.setText(text("settings.save"))
        save_button.setIcon(svg_icon("check", 16))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setIcon(
            svg_icon("close", 16)
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            text("common.cancel")
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        body_layout.addWidget(buttons)
        fit_window_to_screen(self, QSize(720, 500))
        self._frameless_resize = FramelessResizeController(self, corner_radius=11)

    def _path_field(
        self,
        form: QFormLayout,
        label: str,
        value: Path | None,
        file_filter: str,
        *,
        save: bool = False,
    ) -> QLineEdit:
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(str(value) if value else "")
        button = QPushButton(text("common.choose"))
        button.setIcon(svg_icon("folder", 16))
        button.setAccessibleName(f"{text('common.choose')} {label}")
        button.setToolTip(label)

        def browse() -> None:
            if save:
                chosen, _ = QFileDialog.getSaveFileName(
                    self, text("common.choose"), edit.text(), file_filter
                )
            else:
                chosen, _ = QFileDialog.getOpenFileName(
                    self, text("common.choose"), edit.text(), file_filter
                )
            if chosen:
                edit.setText(chosen)

        button.clicked.connect(browse)
        row.addWidget(edit, 1)
        row.addWidget(button)
        form.addRow(label, container)
        return edit

    def _import_keys(self) -> None:
        try:
            dialog = KeyImportDialog(
                self,
                project_name=(
                    self.project_name_edit.text().strip()
                    or text("nav.current_project")
                ),
                project_directory=self._project_directory,
                record_count=self._record_count,
                install_directory=self._transaction.key_staging_directory,
                display_directory=self._transaction.asset_directory,
                current_private_key_path=self._initial_settings.signing_key_path,
                current_public_key_path=self._initial_settings.public_key_path,
            )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("key.import_failed"), str(exc))
            return
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        imported = dialog.imported_pair()
        self._transaction.register_key_pair(imported)
        self.signing_key_edit.setText(str(self._transaction.private_key_path))
        self.public_key_edit.setText(str(self._transaction.public_key_path))
        self._validated_key_paths = (
            self._transaction.private_key_path.resolve(strict=False),
            self._transaction.public_key_path.resolve(strict=False),
        )

    def _import_credentials(self) -> None:
        try:
            dialog = ServiceAccountImportDialog(
                self,
                project_name=(
                    self.project_name_edit.text().strip()
                    or text("nav.current_project")
                ),
                project_directory=self._project_directory,
                install_directory=self._transaction.credential_staging_directory,
                display_directory=self._transaction.asset_directory,
            )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("credential.import_failed"), str(exc))
            return
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        imported = dialog.imported_service_account()
        self._transaction.register_service_account(imported)
        self.credentials_edit.setText(str(self._transaction.service_account_path))

    def _validate_and_accept(self) -> None:
        if not self.project_name_edit.text().strip():
            QMessageBox.warning(
                self,
                text("message.missing_configuration"),
                text("settings.project_name"),
            )
            return
        if not self.local_csv_edit.text().strip():
            QMessageBox.warning(
                self,
                text("message.missing_configuration"),
                text("validation.required", field=text("settings.admin_data")),
            )
            return
        if not self.signing_key_edit.text().strip():
            QMessageBox.warning(
                self,
                text("message.missing_configuration"),
                text(
                    "validation.required",
                    field=text("settings.private_key"),
                ),
            )
            return
        private_path = Path(self.signing_key_edit.text().strip())
        public_text = self.public_key_edit.text().strip()
        public_path = Path(public_text) if public_text else Path()
        staged_keys_selected = (
            bool(public_text)
            and self._transaction.uses_staged_key_paths(
                private_path,
                public_path,
            )
        )
        if not staged_keys_selected and not private_path.is_file():
            QMessageBox.warning(
                self,
                text("message.invalid_data"),
                text(
                    "validation.not_found",
                    field=text("settings.private_key"),
                ),
            )
            return
        if not public_text:
            QMessageBox.warning(
                self,
                text("message.missing_configuration"),
                text(
                    "validation.required",
                    field=text("settings.public_key"),
                ),
            )
            return
        if not staged_keys_selected and not public_path.is_file():
            QMessageBox.warning(
                self,
                text("message.invalid_data"),
                text(
                    "validation.not_found",
                    field=text("settings.public_key"),
                ),
            )
            return
        selected_paths = (
            private_path.resolve(strict=False),
            public_path.resolve(strict=False),
        )
        if selected_paths != self._validated_key_paths:
            try:
                inspect_key_pair(private_path, public_path)
            except KeyPasswordRequiredError:
                password, accepted = QInputDialog.getText(
                    self,
                    text("key.password_required"),
                    text("key.password"),
                    QLineEdit.EchoMode.Password,
                )
                if not accepted:
                    return
                try:
                    inspect_key_pair(
                        private_path,
                        public_path,
                        password=password.encode("utf-8"),
                    )
                except LicenseIssueError as exc:
                    QMessageBox.warning(self, text("key.invalid_pair"), str(exc))
                    return
            except LicenseIssueError as exc:
                QMessageBox.warning(self, text("key.invalid_pair"), str(exc))
                return
        sheet_value = self.sheet_id_edit.text().strip()
        if sheet_value:
            try:
                extract_spreadsheet_id(sheet_value)
            except LicenseIssueError as exc:
                QMessageBox.warning(self, text("message.invalid_data"), str(exc))
                return
        if not self.worksheet_edit.text().strip():
            QMessageBox.warning(
                self,
                text("message.missing_configuration"),
                text(
                    "validation.required",
                    field=text("settings.worksheet"),
                ),
            )
            return
        if not self.issuer_edit.text().strip() or not self.audience_edit.text().strip():
            fields = f"{text('settings.issuer')} / {text('settings.audience')}"
            QMessageBox.warning(
                self,
                text("message.missing_configuration"),
                text("validation.required", field=fields),
            )
            return
        public_url = self.public_url_edit.text().strip()
        if public_url and not public_url.startswith("https://"):
            QMessageBox.warning(self, text("message.invalid_data"), text("validation.https"))
            return
        credentials = self.credentials_edit.text().strip()
        if credentials:
            credential_path = Path(credentials)
            try:
                if not self._transaction.uses_staged_service_account(
                    credential_path
                ):
                    inspect_service_account(credential_path)
            except LicenseIssueError as exc:
                QMessageBox.warning(
                    self,
                    text("credential.invalid"),
                    str(exc),
                )
                return
        self.accept()

    def reject(self) -> None:
        try:
            self._transaction.discard()
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("settings.save_failed"), str(exc))
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.result() != self.DialogCode.Accepted:
            try:
                self._transaction.discard()
            except LicenseIssueError as exc:
                QMessageBox.critical(self, text("settings.save_failed"), str(exc))
                event.ignore()
                return
        super().closeEvent(event)

    def commit(self, project_store: ProjectStore) -> AdminSettings:
        """Commit the accepted settings and any staged imports together."""
        if self.result() != self.DialogCode.Accepted:
            raise LicenseIssueError("Settings must be accepted before commit.")
        return self._transaction.commit(project_store, self.values())

    def values(self) -> AdminSettings:
        sheet_value = self.sheet_id_edit.text().strip()
        spreadsheet_id = extract_spreadsheet_id(sheet_value) if sheet_value else ""
        credentials = self.credentials_edit.text().strip()
        return AdminSettings(
            project_id=self.project_id_edit.text().strip(),
            project_name=self.project_name_edit.text().strip(),
            local_csv_path=Path(self.local_csv_edit.text().strip()),
            signing_key_path=Path(self.signing_key_edit.text().strip()),
            public_key_path=Path(self.public_key_edit.text().strip()),
            service_account_path=Path(credentials) if credentials else None,
            spreadsheet_id=spreadsheet_id,
            worksheet=self.worksheet_edit.text().strip(),
            public_csv_url=self.public_url_edit.text().strip(),
            issuer=self.issuer_edit.text().strip(),
            audience=self.audience_edit.text().strip(),
        )


class RecordDetailsDialog(QDialog):
    def __init__(self, parent: QWidget, record: LicenseRecord) -> None:
        super().__init__(parent)
        self.setWindowTitle(text("details.title"))
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow(text("editor.username"), QLabel(record.username or "—"))
        form.addRow("HWID", QLabel(record.hwid))
        form.addRow("JTI", QLabel(record.jti or "—"))
        if record.parse_error:
            error = QLabel(record.parse_error)
            error.setWordWrap(True)
            error.setObjectName("danger")
            form.addRow(text("details.error"), error)
        layout.addLayout(form)
        token = QTextEdit(record.token)
        token.setReadOnly(True)
        layout.addWidget(QLabel(text("details.token")))
        layout.addWidget(token, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_hwid = buttons.addButton(
            text("details.copy_hwid"), QDialogButtonBox.ButtonRole.ActionRole
        )
        copy_token = buttons.addButton(
            text("details.copy_token"), QDialogButtonBox.ButtonRole.ActionRole
        )
        copy_hwid.setIcon(svg_icon("copy", 16))
        copy_token.setIcon(svg_icon("copy", 16))
        buttons.button(QDialogButtonBox.StandardButton.Close).setIcon(
            svg_icon("close", 16)
        )
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(
            text("common.close")
        )
        copy_hwid.clicked.connect(
            lambda: self._copy(record.hwid)
        )
        copy_token.clicked.connect(
            lambda: self._copy(record.token)
        )
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _copy(self, value: str) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(value)
