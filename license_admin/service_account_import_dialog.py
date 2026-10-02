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
from license_admin.service_account_store import (
    ImportedServiceAccount,
    SERVICE_ACCOUNT_FILENAME,
    import_service_account,
    inspect_service_account,
)


class ServiceAccountImportDialog(QDialog):
    """Validate and copy Google credentials into one project directory."""

    def __init__(
        self,
        parent: QWidget,
        *,
        project_name: str,
        project_directory: Path,
    ) -> None:
        super().__init__(parent)
        self._project_directory = project_directory
        self._imported: ImportedServiceAccount | None = None
        self.setWindowTitle(f"Nhập Google service account — {project_name}")
        self.setMinimumWidth(680)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Chọn JSON của Google service account. File sẽ được kiểm tra và sao chép "
            "vào project hiện tại; project khác không sử dụng credential này."
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
        self.source_edit.setPlaceholderText("Chọn service-account JSON")
        browse_button = QPushButton("Chọn…")
        browse_button.setIcon(svg_icon("folder", 16))
        browse_button.clicked.connect(self._browse)
        row.addWidget(self.source_edit, 1)
        row.addWidget(browse_button)
        form.addRow("JSON nguồn", container)
        layout.addLayout(form)

        destination = QLabel(
            f"Đích: {project_directory / SERVICE_ACCOUNT_FILENAME}"
        )
        destination.setWordWrap(True)
        destination.setObjectName("muted")
        layout.addWidget(destination)

        warning = QLabel(
            "JSON này chứa private key. Không commit, gửi qua chat hoặc đặt trong thư "
            "mục public. Khi chạy Docker, file được giữ trong volume dữ liệu riêng."
        )
        warning.setWordWrap(True)
        warning.setObjectName("warning")
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        import_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        import_button.setText("Xác minh và nhập")
        import_button.setIcon(svg_icon("upload", 16))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setIcon(
            svg_icon("close", 16)
        )
        buttons.accepted.connect(self._validate_and_import)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn Google service-account JSON",
            self.source_edit.text(),
            "JSON (*.json);;Tất cả file (*)",
        )
        if selected:
            self.source_edit.setText(selected)

    def _validate_and_import(self) -> None:
        source_text = self.source_edit.text().strip()
        if not source_text:
            QMessageBox.warning(
                self,
                "Thiếu credential",
                "Hãy chọn Google service-account JSON cần nhập.",
            )
            return
        source = Path(source_text)
        try:
            info = inspect_service_account(source)
        except LicenseIssueError as exc:
            QMessageBox.warning(self, "Credential không hợp lệ", str(exc))
            return

        target = self._project_directory / SERVICE_ACCOUNT_FILENAME
        source_is_target = (
            source.resolve(strict=False) == target.resolve(strict=False)
        )
        overwrite = target.exists() and not source_is_target
        if overwrite:
            answer = QMessageBox.warning(
                self,
                "Xác nhận thay credential",
                "Project đã có service-account JSON. Bạn có muốn thay file hiện tại "
                f"bằng credential của {info.client_email}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self._imported = import_service_account(
                source,
                self._project_directory,
                overwrite=overwrite,
            )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, "Không thể nhập credential", str(exc))
            return
        self.accept()

    def imported_service_account(self) -> ImportedServiceAccount:
        if self._imported is None:
            raise RuntimeError("No service account has been imported.")
        return self._imported
