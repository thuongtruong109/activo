"""Focused dialogs for editing licenses and application settings."""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
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
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from issue_license import LicenseIssueError, MAX_LICENSE_DAYS, normalize_hwid
from license_admin.domain import LicenseRecord
from license_admin.google_sheets import extract_spreadsheet_id
from license_admin.key_import_dialog import KeyImportDialog
from license_admin.key_store import KeyPasswordRequiredError, inspect_key_pair
from license_admin.settings import AdminSettings


class LicenseEditorDialog(QDialog):
    def __init__(self, parent: QWidget, record: LicenseRecord | None = None) -> None:
        super().__init__(parent)
        self._record = record
        self.setWindowTitle("Gia hạn / cập nhật license" if record else "Tạo license mới")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "JWT mới sẽ được ký ở máy này. Thay đổi chỉ được công khai sau khi "
            "bấm “Đồng bộ lên Sheet”."
        )
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        form = QFormLayout()
        self.username_edit = QLineEdit(record.username if record else "")
        self.username_edit.setPlaceholderText("Tên hoặc bí danh khách hàng")
        self.hwid_edit = QLineEdit(record.hwid if record else "")
        self.hwid_edit.setPlaceholderText("64 ký tự hexadecimal")
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
        form.addRow("Người dùng", self.username_edit)
        form.addRow("HWID thiết bị", self.hwid_edit)
        form.addRow("Hết hạn cuối ngày (UTC)", self.expiry_edit)
        layout.addLayout(form)

        presets = QHBoxLayout()
        presets.addWidget(QLabel("Chọn nhanh:"))
        for days, label in ((30, "30 ngày"), (90, "90 ngày"), (365, "1 năm"), (730, "2 năm")):
            button = QPushButton(label)
            button.clicked.connect(
                lambda checked=False, duration=days: self.expiry_edit.setDate(
                    utc_qdate.addDays(duration)
                )
            )
            presets.addWidget(button)
        presets.addStretch()
        layout.addLayout(presets)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Ký và lưu")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self) -> None:
        try:
            username = self.username_edit.text().strip()
            if not username or len(username) > 200:
                raise LicenseIssueError("Tên người dùng phải có từ 1 đến 200 ký tự.")
            if any(ord(character) < 32 for character in username):
                raise LicenseIssueError("Tên người dùng không được chứa ký tự điều khiển.")
            normalize_hwid(self.hwid_edit.text())
        except LicenseIssueError as exc:
            QMessageBox.warning(self, "Dữ liệu chưa hợp lệ", str(exc))
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
        self._project_directory = project_directory
        self._record_count = record_count
        self._validated_key_paths: tuple[Path, Path] | None = None
        self.setWindowTitle("Cài đặt License Admin")
        self.setMinimumSize(720, 500)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        files_tab = QWidget()
        files_form = QFormLayout(files_tab)
        self.project_name_edit = QLineEdit(values.project_name)
        self.project_id_edit = QLineEdit(values.project_id)
        self.project_id_edit.setReadOnly(True)
        files_form.addRow("Tên dự án", self.project_name_edit)
        files_form.addRow("Project ID", self.project_id_edit)
        self.local_csv_edit = self._path_field(
            files_form,
            "Dữ liệu quản trị",
            values.local_csv_path,
            "CSV (*.csv);;Tất cả file (*)",
            save=True,
        )
        self.signing_key_edit = self._path_field(
            files_form,
            "RSA private key",
            values.signing_key_path,
            "PEM (*.pem);;Tất cả file (*)",
        )
        self.public_key_edit = self._path_field(
            files_form,
            "RSA public key",
            values.public_key_path,
            "PEM (*.pem);;Tất cả file (*)",
        )
        self.import_keys_button = QPushButton("Nhập cặp key vào project…")
        self.import_keys_button.setObjectName("importProjectKeys")
        self.import_keys_button.clicked.connect(self._import_keys)
        files_form.addRow("", self.import_keys_button)
        key_warning = QLabel(
            "Mỗi project có cặp key riêng. Nút nhập sẽ xác minh rồi sao chép key vào thư "
            "mục project. Không tải private key lên Google Drive hoặc commit vào Git."
        )
        key_warning.setWordWrap(True)
        key_warning.setObjectName("warning")
        files_form.addRow("", key_warning)
        tabs.addTab(files_tab, "File & khóa ký")

        google_tab = QWidget()
        google_form = QFormLayout(google_tab)
        self.sheet_id_edit = QLineEdit(values.spreadsheet_id)
        self.sheet_id_edit.setPlaceholderText("ID hoặc URL của Google Sheet")
        self.worksheet_edit = QLineEdit(values.worksheet)
        self.public_url_edit = QLineEdit(values.public_csv_url)
        self.public_url_edit.setPlaceholderText("https://docs.google.com/.../export?format=csv")
        self.credentials_edit = self._path_field(
            google_form,
            "Service account JSON",
            values.service_account_path,
            "JSON (*.json);;Tất cả file (*)",
        )
        google_form.insertRow(0, "Spreadsheet", self.sheet_id_edit)
        google_form.insertRow(1, "Tên worksheet", self.worksheet_edit)
        google_form.insertRow(2, "Public CSV URL", self.public_url_edit)
        note = QLabel(
            "Chia sẻ Sheet cho email client_email trong service-account JSON với quyền Editor. "
            "Public CSV URL chỉ cần cho chức năng tải xuống không đăng nhập."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        google_form.addRow("", note)
        tabs.addTab(google_tab, "Google Sheets")

        claims_tab = QWidget()
        claims_form = QFormLayout(claims_tab)
        self.issuer_edit = QLineEdit(values.issuer)
        self.audience_edit = QLineEdit(values.audience)
        claims_form.addRow("Issuer", self.issuer_edit)
        claims_form.addRow("Audience", self.audience_edit)
        claims_note = QLabel(
            "Hai giá trị này phải trùng với cấu hình được nhúng trong ứng dụng khách."
        )
        claims_note.setWordWrap(True)
        claims_note.setObjectName("warning")
        claims_form.addRow("", claims_note)
        tabs.addTab(claims_tab, "JWT claims")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Lưu cài đặt")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
        button = QPushButton("Chọn…")

        def browse() -> None:
            if save:
                chosen, _ = QFileDialog.getSaveFileName(
                    self, "Chọn file", edit.text(), file_filter
                )
            else:
                chosen, _ = QFileDialog.getOpenFileName(
                    self, "Chọn file", edit.text(), file_filter
                )
            if chosen:
                edit.setText(chosen)

        button.clicked.connect(browse)
        row.addWidget(edit, 1)
        row.addWidget(button)
        form.addRow(label, container)
        return edit

    def _import_keys(self) -> None:
        dialog = KeyImportDialog(
            self,
            project_name=self.project_name_edit.text().strip() or "Project hiện tại",
            project_directory=self._project_directory,
            record_count=self._record_count,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        imported = dialog.imported_pair()
        self.signing_key_edit.setText(str(imported.private_key_path))
        self.public_key_edit.setText(str(imported.public_key_path))
        self._validated_key_paths = (
            imported.private_key_path.resolve(strict=False),
            imported.public_key_path.resolve(strict=False),
        )

    def _validate_and_accept(self) -> None:
        if not self.project_name_edit.text().strip():
            QMessageBox.warning(self, "Thiếu cấu hình", "Tên dự án không được trống.")
            return
        if not self.local_csv_edit.text().strip():
            QMessageBox.warning(self, "Thiếu cấu hình", "Hãy chọn file dữ liệu quản trị.")
            return
        if not self.signing_key_edit.text().strip():
            QMessageBox.warning(self, "Thiếu cấu hình", "Hãy chọn RSA private key.")
            return
        if not Path(self.signing_key_edit.text().strip()).is_file():
            QMessageBox.warning(self, "Khóa ký không hợp lệ", "Không tìm thấy RSA private key.")
            return
        if not self.public_key_edit.text().strip():
            QMessageBox.warning(self, "Thiếu cấu hình", "Hãy chọn RSA public key.")
            return
        if not Path(self.public_key_edit.text().strip()).is_file():
            QMessageBox.warning(self, "Public key không hợp lệ", "Không tìm thấy RSA public key.")
            return
        private_path = Path(self.signing_key_edit.text().strip())
        public_path = Path(self.public_key_edit.text().strip())
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
                    "Xác minh private key",
                    "Mật khẩu private key:",
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
                    QMessageBox.warning(self, "Cặp key không hợp lệ", str(exc))
                    return
            except LicenseIssueError as exc:
                QMessageBox.warning(self, "Cặp key không hợp lệ", str(exc))
                return
        sheet_value = self.sheet_id_edit.text().strip()
        if sheet_value:
            try:
                extract_spreadsheet_id(sheet_value)
            except LicenseIssueError as exc:
                QMessageBox.warning(self, "Google Sheet không hợp lệ", str(exc))
                return
        if not self.worksheet_edit.text().strip():
            QMessageBox.warning(self, "Thiếu cấu hình", "Tên worksheet không được trống.")
            return
        if not self.issuer_edit.text().strip() or not self.audience_edit.text().strip():
            QMessageBox.warning(self, "Thiếu cấu hình", "Issuer và audience không được trống.")
            return
        public_url = self.public_url_edit.text().strip()
        if public_url and not public_url.startswith("https://"):
            QMessageBox.warning(self, "URL không hợp lệ", "Public CSV URL phải dùng HTTPS.")
            return
        credentials = self.credentials_edit.text().strip()
        if credentials and not Path(credentials).is_file():
            QMessageBox.warning(
                self,
                "Service account không hợp lệ",
                "Không tìm thấy service-account JSON.",
            )
            return
        self.accept()

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
        self.setWindowTitle("Chi tiết license")
        self.resize(760, 520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Người dùng", QLabel(record.username or "—"))
        form.addRow("HWID", QLabel(record.hwid))
        form.addRow("JTI", QLabel(record.jti or "—"))
        if record.parse_error:
            error = QLabel(record.parse_error)
            error.setWordWrap(True)
            error.setObjectName("danger")
            form.addRow("Lỗi", error)
        layout.addLayout(form)
        token = QTextEdit(record.token)
        token.setReadOnly(True)
        layout.addWidget(QLabel("JWT token"))
        layout.addWidget(token, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_hwid = buttons.addButton(
            "Sao chép HWID", QDialogButtonBox.ButtonRole.ActionRole
        )
        copy_token = buttons.addButton(
            "Sao chép token", QDialogButtonBox.ButtonRole.ActionRole
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
