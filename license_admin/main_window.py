"""Main desktop window for multi-project license administration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import QItemSelection, QSettings, QSize, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QIcon,
    QResizeEvent,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from issue_license import LicenseIssueError, issue_license_until, load_private_key
from license_admin.dialogs import (
    LicenseEditorDialog,
    RecordDetailsDialog,
    SettingsDialog,
)
from license_admin.dashboard_widgets import (
    MetricCard,
    ProjectIdentityCard,
    SidebarButton,
    SidebarMenuButton,
)
from license_admin.domain import (
    LicenseRecord,
    LicenseStatus,
    parse_signed_csv,
    records_digest,
    serialize_signed_csv,
    validate_record_signatures,
)
from license_admin.google_sheets import GoogleSheetsClient, download_public_records
from license_admin.icons import icon_pixmap, svg_icon
from license_admin.key_import_dialog import KeyImportDialog
from license_admin.qt_models import LicenseFilterModel, LicenseTableModel
from license_admin.settings import APPLICATION_ROOT, AdminSettings, ProjectStore
from license_admin.storage import LicenseRepository
from license_admin.toast import Toast
from license_admin.theme import ADMIN_STYLESHEET
from license_admin.worker import OperationThread
from migrate_license_csv import migrate_legacy_csv


class LicenseAdminWindow(QMainWindow):
    def __init__(
        self,
        *,
        project_store: ProjectStore | None = None,
        qsettings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.resize(1320, 820)
        self.setMinimumSize(980, 640)
        icon_path = APPLICATION_ROOT / "app.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._qsettings = qsettings or QSettings("LicenseTools", "LicenseAdmin")
        self._project_store = project_store or ProjectStore()
        default_profile = self._project_store.ensure_default()
        active_project = str(
            self._qsettings.value("projects/active", default_profile.project_id)
        ).strip()
        try:
            self._settings = self._project_store.load(active_project)
        except LicenseIssueError:
            self._settings = default_profile
        self._qsettings.setValue("projects/active", self._settings.project_id)
        self._workers: set[OperationThread] = set()
        self._busy = False
        self._records: list[LicenseRecord] = []
        self._set_project_identity()

        self._create_actions()
        self._build_ui()
        self._create_menus()
        self._load_local(show_missing=False)
        self._refresh_view()

    def _create_actions(self) -> None:
        self.new_action = QAction(svg_icon("plus"), "Tạo license", self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.triggered.connect(self._add_license)
        self.edit_action = QAction(svg_icon("edit"), "Gia hạn / sửa", self)
        self.edit_action.setShortcut("Ctrl+E")
        self.edit_action.triggered.connect(self._edit_license)
        self.revoke_action = QAction(svg_icon("trash"), "Thu hồi", self)
        self.revoke_action.setShortcut("Delete")
        self.revoke_action.triggered.connect(self._revoke_license)
        self.details_action = QAction(svg_icon("eye"), "Xem chi tiết", self)
        self.details_action.triggered.connect(self._show_details)
        self.pull_action = QAction(svg_icon("download"), "Tải từ Sheet", self)
        self.pull_action.setShortcut("Ctrl+Shift+D")
        self.pull_action.triggered.connect(self._pull_sheet)
        self.push_action = QAction(svg_icon("upload"), "Đồng bộ lên Sheet", self)
        self.push_action.setShortcut("Ctrl+Shift+U")
        self.push_action.triggered.connect(self._push_sheet)
        self.format_action = QAction(svg_icon("format"), "Format Sheet", self)
        self.format_action.triggered.connect(self._format_sheet)
        self.test_action = QAction(svg_icon("plug"), "Kiểm tra kết nối", self)
        self.test_action.triggered.connect(self._test_connection)
        self.open_sheet_action = QAction(svg_icon("external"), "Mở Google Sheet", self)
        self.open_sheet_action.triggered.connect(self._open_sheet)
        self.settings_action = QAction(svg_icon("settings"), "Cài đặt", self)
        self.settings_action.setShortcut("Ctrl+,")
        self.settings_action.triggered.connect(self._show_settings)
        self.new_project_action = QAction(svg_icon("plus"), "Thêm dự án…", self)
        self.new_project_action.triggered.connect(self._create_project)
        self.open_project_folder_action = QAction(
            svg_icon("folder"), "Mở thư mục dự án", self
        )
        self.open_project_folder_action.triggered.connect(self._open_project_folder)
        self.import_project_keys_action = QAction(
            svg_icon("key"), "Nhập cặp key…", self
        )
        self.import_project_keys_action.triggered.connect(self._import_project_keys)
        self.import_signed_action = QAction(
            svg_icon("import"), "Nhập signed CSV…", self
        )
        self.import_signed_action.triggered.connect(self._import_signed)
        self.import_legacy_action = QAction(
            svg_icon("migration"), "Nhập legacy CSV…", self
        )
        self.import_legacy_action.triggered.connect(self._import_legacy)
        self.export_action = QAction(svg_icon("export"), "Xuất signed CSV…", self)
        self.export_action.setShortcut("Ctrl+S")
        self.export_action.triggered.connect(self._export_signed)
        self.quit_action = QAction(svg_icon("close"), "Thoát", self)
        self.quit_action.setShortcut("Ctrl+Q")
        self.quit_action.triggered.connect(self.close)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("appShell")
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 0, 10, 12)
        sidebar_layout.setSpacing(5)

        brand = QFrame()
        brand.setObjectName("brandBlock")
        brand.setFixedHeight(72)
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(2, 12, 2, 12)
        brand_layout.setSpacing(10)
        brand_mark = QLabel("L")
        brand_mark.setObjectName("brandMark")
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_mark.setFixedSize(40, 40)
        brand_copy = QVBoxLayout()
        brand_copy.setSpacing(1)
        brand_name = QLabel("LICENSE ADMIN")
        brand_name.setObjectName("brandName")
        brand_subtitle = QLabel("MULTI-PROJECT CONSOLE")
        brand_subtitle.setObjectName("brandSubtitle")
        brand_copy.addWidget(brand_name)
        brand_copy.addWidget(brand_subtitle)
        brand_layout.addWidget(brand_mark)
        brand_layout.addLayout(brand_copy, 1)
        sidebar_layout.addWidget(brand)

        nav_label = QLabel("ĐIỀU HƯỚNG")
        nav_label.setObjectName("navSection")
        sidebar_layout.addWidget(nav_label)
        self.overview_button = SidebarButton("Tổng quan", "grid", active=True)
        self.overview_button.clicked.connect(self._focus_dashboard)
        self.new_sidebar_button = SidebarButton("Tạo license", "plus")
        self.new_sidebar_button.clicked.connect(self.new_action.trigger)
        self.license_sidebar_menu = SidebarMenuButton("License", "key")
        self.sheet_sidebar_menu = SidebarMenuButton("Google Sheets", "cloud")
        self.data_sidebar_menu = SidebarMenuButton("Dữ liệu", "database")
        self.settings_sidebar_button = SidebarButton("Cài đặt", "settings")
        self.settings_sidebar_button.clicked.connect(self.settings_action.trigger)
        for button in (
            self.overview_button,
            self.new_sidebar_button,
            self.license_sidebar_menu,
            self.sheet_sidebar_menu,
            self.data_sidebar_menu,
            self.settings_sidebar_button,
        ):
            sidebar_layout.addWidget(button)
        sidebar_layout.addStretch(1)

        project_label = QLabel("PROJECT HIỆN TẠI")
        project_label.setObjectName("navSection")
        sidebar_layout.addWidget(project_label)
        self.project_identity = ProjectIdentityCard()
        self.project_identity.set_project(
            self._settings.project_name,
            self._settings.project_id,
        )
        sidebar_layout.addWidget(self.project_identity)
        self.project_sidebar_menu = SidebarMenuButton(
            "Quản lý project", "folder-project"
        )
        sidebar_layout.addWidget(self.project_sidebar_menu)
        shell.addWidget(self.sidebar)

        self.main_surface = QWidget()
        self.main_surface.setObjectName("mainSurface")
        main_layout = QVBoxLayout(self.main_surface)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.top_bar = QFrame()
        self.top_bar.setObjectName("topBar")
        self.top_bar.setFixedHeight(58)
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(20, 9, 18, 9)
        top_bar_layout.setSpacing(12)
        top_bar_icon = QLabel()
        top_bar_icon.setPixmap(icon_pixmap("grid", 17))
        top_bar_icon.setFixedSize(17, 17)
        top_bar_layout.addWidget(top_bar_icon)
        top_bar_title = QLabel("Dashboard")
        top_bar_title.setObjectName("topBarTitle")
        top_bar_layout.addWidget(top_bar_title)
        top_bar_layout.addSpacing(10)

        self.top_controls = QWidget()
        self.top_controls.setObjectName("topControls")
        self.top_controls.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        filters = QHBoxLayout(self.top_controls)
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setSpacing(10)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("dashboardSearch")
        self.search_edit.setPlaceholderText("Tìm theo người dùng, HWID, JTI hoặc token…")
        self._search_icon_action = self.search_edit.addAction(
            svg_icon("search", 16), QLineEdit.ActionPosition.LeadingPosition
        )
        self._search_clear_action = self.search_edit.addAction(
            svg_icon("close", 16), QLineEdit.ActionPosition.TrailingPosition
        )
        self._search_clear_action.setVisible(False)
        self._search_clear_action.triggered.connect(self.search_edit.clear)
        self.search_edit.setMinimumWidth(160)
        self.search_edit.setMaximumWidth(520)
        self.search_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.status_combo = QComboBox()
        self.status_combo.setMinimumWidth(124)
        self.status_combo.addItem("Tất cả trạng thái", None)
        self.status_combo.addItem("Đang hoạt động", LicenseStatus.ACTIVE)
        self.status_combo.addItem("Sắp hết hạn", LicenseStatus.EXPIRING)
        self.status_combo.addItem("Đã hết hạn", LicenseStatus.EXPIRED)
        self.status_combo.addItem("Chưa hiệu lực", LicenseStatus.FUTURE)
        self.status_combo.addItem("Dữ liệu lỗi", LicenseStatus.INVALID)
        self.project_combo = QComboBox()
        self.project_combo.setObjectName("projectCombo")
        self.project_combo.setMinimumWidth(130)
        self.project_combo.setMaximumWidth(190)
        filters.addWidget(self.search_edit, 1)
        filters.addWidget(self.status_combo)
        filters.addWidget(self.project_combo)
        top_bar_layout.addWidget(self.top_controls, 1)
        self.primary_action_button = QPushButton("Tạo license")
        self.primary_action_button.setObjectName("primaryButton")
        self.primary_action_button.setFixedWidth(128)
        self.primary_action_button.setIcon(svg_icon("plus-dark"))
        self.primary_action_button.setIconSize(QSize(16, 16))
        self.primary_action_button.clicked.connect(self.new_action.trigger)
        top_bar_layout.addWidget(
            self.primary_action_button,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        main_layout.addWidget(self.top_bar)

        self.content_surface = QWidget()
        self.content_surface.setObjectName("contentSurface")
        root = QVBoxLayout(self.content_surface)
        root.setContentsMargins(18, 14, 18, 18)
        root.setSpacing(12)

        self.metrics_layout = QHBoxLayout()
        self.metrics_layout.setSpacing(10)
        self.total_card = MetricCard(
            "Tổng license",
            "Trong profile hiện tại",
            "total",
            "#25bdea",
        )
        self.active_card = MetricCard(
            "Đang hoạt động",
            "License còn hiệu lực",
            "check",
            "#32d296",
        )
        self.expiring_card = MetricCard(
            "Sắp hết hạn",
            "Còn tối đa 30 ngày",
            "clock",
            "#f4bc42",
        )
        self.expired_card = MetricCard(
            "Hết hạn / lỗi",
            "Cần kiểm tra hoặc cấp lại",
            "alert",
            "#f05d6c",
        )
        self.metric_cards = (
            self.total_card,
            self.active_card,
            self.expiring_card,
            self.expired_card,
        )
        for card in self.metric_cards:
            self.metrics_layout.addWidget(card, 1)
        root.addLayout(self.metrics_layout)

        self.table_panel = QFrame()
        self.table_panel.setObjectName("tablePanel")
        table_panel_layout = QVBoxLayout(self.table_panel)
        table_panel_layout.setContentsMargins(1, 0, 1, 1)
        table_panel_layout.setSpacing(0)
        table_header = QWidget()
        table_header_layout = QHBoxLayout(table_header)
        table_header_layout.setContentsMargins(14, 10, 12, 10)
        table_header_layout.setSpacing(9)
        table_icon = QLabel()
        table_icon.setPixmap(icon_pixmap("table", 17))
        table_icon.setFixedSize(17, 17)
        table_header_layout.addWidget(
            table_icon,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        table_copy = QVBoxLayout()
        table_copy.setSpacing(1)
        table_title = QLabel("Danh sách license")
        table_title.setObjectName("panelTitle")
        table_subtitle = QLabel("Double-click một dòng để gia hạn hoặc chỉnh sửa")
        table_subtitle.setObjectName("panelSubtitle")
        table_copy.addWidget(table_title)
        table_copy.addWidget(table_subtitle)
        table_header_layout.addLayout(table_copy)
        table_header_layout.addStretch(1)
        self.visible_label = QLabel()
        self.visible_label.setObjectName("muted")
        table_header_layout.addWidget(self.visible_label)
        self.sync_badge = QLabel("Chưa đồng bộ")
        self.sync_badge.setObjectName("syncBadge")
        self.sync_badge.setMinimumWidth(96)
        self.sync_badge.setMaximumWidth(126)
        self.sync_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sync_badge.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        table_header_layout.addWidget(
            self.sync_badge,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        table_panel_layout.addWidget(table_header)

        self.table_model = LicenseTableModel()
        self.proxy_model = LicenseFilterModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(lambda _index: self._edit_license())
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setMinimumSectionSize(80)
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setMinimumWidth(42)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 310)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 145)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 145)
        self.table.setColumnWidth(6, 240)
        table_panel_layout.addWidget(self.table, 1)
        root.addWidget(self.table_panel, 1)
        main_layout.addWidget(self.content_surface, 1)
        shell.addWidget(self.main_surface, 1)

        self.search_edit.textChanged.connect(self.proxy_model.set_query)
        self.search_edit.textChanged.connect(
            lambda text: self._search_clear_action.setVisible(bool(text))
        )
        self.search_edit.textChanged.connect(lambda _text: self._refresh_visible_count())
        self.status_combo.currentIndexChanged.connect(self._filter_status_changed)
        self.proxy_model.rowsInserted.connect(lambda *_args: self._refresh_visible_count())
        self.proxy_model.rowsRemoved.connect(lambda *_args: self._refresh_visible_count())
        self.proxy_model.modelReset.connect(self._refresh_visible_count)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.project_combo.currentIndexChanged.connect(self._project_combo_changed)
        self.setCentralWidget(central)
        self.toast = Toast(self)
        self.statusBar().hide()
        self._selection_changed()

    def _create_menus(self) -> None:
        self.menuBar().hide()
        self.project_menu = QMenu("Dự án", self)
        self._rebuild_project_menu()
        self.file_menu = QMenu("Dữ liệu", self)
        self.file_menu.addAction(self.import_signed_action)
        self.file_menu.addAction(self.import_legacy_action)
        self.file_menu.addAction(self.export_action)
        self.license_menu = QMenu("License", self)
        self.license_menu.addAction(self.new_action)
        self.license_menu.addAction(self.edit_action)
        self.license_menu.addAction(self.revoke_action)
        self.license_menu.addAction(self.details_action)
        self.sheet_menu = QMenu("Google Sheets", self)
        self.sheet_menu.addAction(self.pull_action)
        self.sheet_menu.addAction(self.push_action)
        self.sheet_menu.addAction(self.format_action)
        self.sheet_menu.addAction(self.test_action)
        self.sheet_menu.addSeparator()
        self.sheet_menu.addAction(self.open_sheet_action)
        self.project_sidebar_menu.setMenu(self.project_menu)
        self.data_sidebar_menu.setMenu(self.file_menu)
        self.license_sidebar_menu.setMenu(self.license_menu)
        self.sheet_sidebar_menu.setMenu(self.sheet_menu)
        self.addActions(
            (
                self.new_action,
                self.edit_action,
                self.revoke_action,
                self.pull_action,
                self.push_action,
                self.export_action,
                self.settings_action,
                self.quit_action,
            )
        )

    def _set_project_identity(self) -> None:
        self.setWindowTitle(f"{self._settings.project_name} — License Admin")
        if hasattr(self, "project_identity"):
            self.project_identity.set_project(
                self._settings.project_name,
                self._settings.project_id,
            )

    def _rebuild_project_menu(self) -> None:
        self.project_menu.clear()
        profiles = self._project_store.list_profiles()
        for profile in profiles:
            action = self.project_menu.addAction(profile.project_name)
            action.setIcon(
                svg_icon(
                    "check"
                    if profile.project_id == self._settings.project_id
                    else "folder-project"
                )
            )
            action.setData(profile.project_id)
            action.triggered.connect(
                lambda _checked=False, project_id=profile.project_id: (
                    self._switch_project(project_id)
                )
            )
        self.project_menu.addSeparator()
        self.project_menu.addAction(self.new_project_action)
        self.project_menu.addAction(self.import_project_keys_action)
        self.project_menu.addAction(self.open_project_folder_action)
        self.project_menu.addAction(self.settings_action)
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        active_index = 0
        for index, profile in enumerate(profiles):
            self.project_combo.addItem(profile.project_name, profile.project_id)
            if profile.project_id == self._settings.project_id:
                active_index = index
        self.project_combo.setCurrentIndex(active_index)
        self.project_combo.blockSignals(False)
        self._set_project_identity()

    def _project_combo_changed(self, index: int) -> None:
        project_id = self.project_combo.itemData(index)
        if isinstance(project_id, str):
            self._switch_project(project_id)

    def _focus_dashboard(self) -> None:
        self.search_edit.setFocus()

    def _create_project(self) -> None:
        project_name, accepted = QInputDialog.getText(
            self,
            "Thêm dự án",
            "Tên dự án:",
        )
        if not accepted or not project_name.strip():
            return
        try:
            profile = self._project_store.create(project_name)
        except LicenseIssueError as exc:
            QMessageBox.warning(self, "Không thể tạo dự án", str(exc))
            return
        self._switch_project(profile.project_id)
        self._notify(f"Đã tạo profile {profile.project_name}")
        self._show_settings()

    def _switch_project(self, project_id: str) -> None:
        if self._busy or project_id == self._settings.project_id:
            return
        try:
            self._settings = self._project_store.load(project_id)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, "Không thể mở dự án", str(exc))
            return
        self._qsettings.setValue("projects/active", project_id)
        self.search_edit.clear()
        self.status_combo.setCurrentIndex(0)
        self.sync_badge.setText("Chưa đồng bộ")
        self.sync_badge.setProperty("synced", False)
        self.sync_badge.style().unpolish(self.sync_badge)
        self.sync_badge.style().polish(self.sync_badge)
        self._set_project_identity()
        self._load_local(show_missing=True)
        self._refresh_view()
        self._rebuild_project_menu()
        self._notify(f"Đã chuyển sang {self._settings.project_name}", tone="info")

    def _open_project_folder(self) -> None:
        directory = self._project_store.project_directory(self._settings.project_id)
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _import_project_keys(self) -> None:
        dialog = KeyImportDialog(
            self,
            project_name=self._settings.project_name,
            project_directory=self._project_store.project_directory(
                self._settings.project_id
            ),
            record_count=len(self._records),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        imported = dialog.imported_pair()
        updated = replace(
            self._settings,
            signing_key_path=imported.private_key_path,
            public_key_path=imported.public_key_path,
        )
        try:
            self._project_store.save(updated)
            self._settings = updated
            self._records = self._verified_records(self._records)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, "Không thể cập nhật project", str(exc))
            return
        self._refresh_view()
        self._notify(
            "Đã nhập cặp key RSA "
            f"{imported.info.key_size} bit (SHA-256 {imported.info.short_fingerprint}…)"
        )

    def _load_local(self, *, show_missing: bool) -> None:
        try:
            self._records = self._verified_records(
                LicenseRepository(self._settings.local_csv_path).load()
            )
        except LicenseIssueError as exc:
            if show_missing:
                QMessageBox.critical(self, "Không thể mở dữ liệu", str(exc))
            self._records = []

    def _save_local(self) -> bool:
        try:
            LicenseRepository(self._settings.local_csv_path).save(self._records)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, "Không thể lưu dữ liệu", str(exc))
            return False
        self.sync_badge.setText("Chưa đẩy Sheet")
        self.sync_badge.setProperty("synced", False)
        self.sync_badge.style().unpolish(self.sync_badge)
        self.sync_badge.style().polish(self.sync_badge)
        return True

    def _verified_records(self, records: list[LicenseRecord]) -> list[LicenseRecord]:
        try:
            public_key = self._settings.public_key_path.read_bytes()
        except OSError as exc:
            raise LicenseIssueError(
                f"Không thể đọc public key {self._settings.public_key_path}: {exc}"
            ) from exc
        return validate_record_signatures(
            records,
            public_key,
            expected_issuer=self._settings.issuer,
            expected_audience=self._settings.audience,
        )

    def _refresh_view(self) -> None:
        self.table_model.set_records(self._records)
        statuses = [record.status() for record in self._records]
        active_count = statuses.count(LicenseStatus.ACTIVE)
        expiring_count = statuses.count(LicenseStatus.EXPIRING)
        expired_count = statuses.count(LicenseStatus.EXPIRED)
        invalid_count = statuses.count(LicenseStatus.INVALID)
        self.total_card.set_value(len(self._records))
        self.active_card.set_value(active_count)
        self.expiring_card.set_value(expiring_count)
        self.expired_card.set_value(expired_count + invalid_count)
        self._refresh_visible_count()
        self._selection_changed()

    def _refresh_visible_count(self) -> None:
        self.visible_label.setText(
            f"Hiển thị {self.proxy_model.rowCount()} / {len(self._records)}"
        )

    def _filter_status_changed(self) -> None:
        status = self.status_combo.currentData()
        self.proxy_model.set_status(status if isinstance(status, LicenseStatus) else None)
        self._refresh_visible_count()

    def _selection_changed(self, _selected: QItemSelection | None = None, _deselected: QItemSelection | None = None) -> None:
        enabled = self._selected_record() is not None and not self._busy
        self.edit_action.setEnabled(enabled)
        self.revoke_action.setEnabled(enabled)
        self.details_action.setEnabled(enabled)

    def _selected_record(self) -> LicenseRecord | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        source_index = self.proxy_model.mapToSource(rows[0])
        return self.table_model.record_at(source_index.row())

    def _show_context_menu(self, position: Any) -> None:
        record = self._selected_record()
        if record is None:
            return
        menu = QMenu(self)
        menu.addAction(self.details_action)
        menu.addAction(self.edit_action)
        menu.addAction(self.revoke_action)
        menu.addSeparator()
        copy_hwid = menu.addAction("Sao chép HWID")
        copy_token = menu.addAction("Sao chép token")
        selected = menu.exec(self.table.viewport().mapToGlobal(position))
        if selected is copy_hwid:
            QApplication.clipboard().setText(record.hwid)
            self._notify("Đã sao chép HWID")
        elif selected is copy_token:
            QApplication.clipboard().setText(record.token)
            self._notify("Đã sao chép token")

    def _load_signing_key(self) -> Any | None:
        path = self._settings.signing_key_path
        if not path.exists():
            QMessageBox.warning(
                self,
                "Không tìm thấy khóa ký",
                f"Không tìm thấy private key:\n{path}\n\nHãy chọn lại trong Cài đặt.",
            )
            return None
        try:
            return load_private_key(path, None)
        except LicenseIssueError:
            password, accepted = QInputDialog.getText(
                self,
                "Mở khóa private key",
                "Mật khẩu private key:",
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return None
            try:
                return load_private_key(path, password.encode("utf-8"))
            except LicenseIssueError as exc:
                QMessageBox.critical(self, "Không thể mở khóa ký", str(exc))
                return None

    def _add_license(self) -> None:
        dialog = LicenseEditorDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._apply_license_editor(dialog, None)

    def _edit_license(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        dialog = LicenseEditorDialog(self, record)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._apply_license_editor(dialog, record)

    def _apply_license_editor(
        self,
        dialog: LicenseEditorDialog,
        original: LicenseRecord | None,
    ) -> None:
        username, hwid, expires_at = dialog.values()
        collision = next(
            (
                item
                for item in self._records
                if item.hwid == hwid and (original is None or item.hwid != original.hwid)
            ),
            None,
        )
        if collision is not None:
            QMessageBox.warning(
                self,
                "HWID đã tồn tại",
                f"HWID này đang thuộc về {collision.username or 'một dòng dữ liệu lỗi'}.",
            )
            return
        private_key = self._load_signing_key()
        if private_key is None:
            return
        try:
            token = issue_license_until(
                private_key,
                username=username,
                hwid=hwid,
                expires_at=expires_at,
                issuer=self._settings.issuer,
                audience=self._settings.audience,
            )
            new_record = self._verified_records(
                parse_signed_csv(f"hwid,token\n{hwid},{token}\n")
            )[0]
            if new_record.parse_error:
                raise LicenseIssueError(
                    f"Private key không khớp public key của {self._settings.project_name}: "
                    f"{new_record.parse_error}"
                )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, "Không thể ký license", str(exc))
            return
        if original is not None:
            self._records = [item for item in self._records if item.hwid != original.hwid]
        self._records.append(new_record)
        self._records.sort(key=lambda item: (item.username.casefold(), item.hwid))
        if self._save_local():
            self._refresh_view()
            self._notify(
                f"Đã {'cập nhật' if original else 'tạo'} license cho {username}"
            )

    def _revoke_license(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        answer = QMessageBox.question(
            self,
            "Thu hồi license",
            f"Xóa license của “{record.username or record.hwid}” khỏi dữ liệu cục bộ?\n\n"
            "Thiết bị chỉ bị thu hồi sau khi bạn đồng bộ lên Google Sheet.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._records = [item for item in self._records if item.hwid != record.hwid]
        if self._save_local():
            self._refresh_view()
            self._notify("Đã thu hồi license trong bản cục bộ")

    def _show_details(self) -> None:
        record = self._selected_record()
        if record is not None:
            RecordDetailsDialog(self, record).exec()

    def _merge_imported(self, imported: list[LicenseRecord], source_name: str) -> None:
        imported = self._verified_records(imported)
        if not imported:
            self._notify("File không chứa license nào.", tone="info")
            return
        box = QMessageBox(self)
        box.setWindowTitle("Nhập dữ liệu")
        box.setText(f"Đã đọc {len(imported)} license từ {source_name}.")
        box.setInformativeText("Bạn muốn gộp theo HWID hay thay toàn bộ dữ liệu cục bộ?")
        merge_button = box.addButton(
            "Gộp / cập nhật", QMessageBox.ButtonRole.AcceptRole
        )
        replace_button = box.addButton(
            "Thay toàn bộ", QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is merge_button:
            merged = {record.hwid: record for record in self._records}
            merged.update({record.hwid: record for record in imported})
            self._records = list(merged.values())
        elif box.clickedButton() is replace_button:
            self._records = list(imported)
        else:
            return
        self._records.sort(key=lambda item: (item.username.casefold(), item.hwid))
        if self._save_local():
            self._refresh_view()
            self._notify(f"Đã nhập {len(imported)} license")

    def _import_signed(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Nhập signed CSV", "", "CSV (*.csv);;Tất cả file (*)"
        )
        if not filename:
            return
        try:
            imported = parse_signed_csv(Path(filename).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, LicenseIssueError) as exc:
            QMessageBox.critical(self, "Không thể nhập CSV", str(exc))
            return
        self._merge_imported(imported, Path(filename).name)

    def _import_legacy(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Nhập legacy CSV", "", "CSV (*.csv);;Tất cả file (*)"
        )
        if not filename:
            return
        private_key = self._load_signing_key()
        if private_key is None:
            return
        try:
            result = migrate_legacy_csv(
                Path(filename).read_text(encoding="utf-8-sig"),
                private_key,
                issuer=self._settings.issuer,
                audience=self._settings.audience,
            )
            imported = parse_signed_csv(result.csv_text)
        except (OSError, UnicodeError, LicenseIssueError) as exc:
            QMessageBox.critical(self, "Không thể chuyển đổi legacy CSV", str(exc))
            return
        self._merge_imported(imported, Path(filename).name)
        if result.skipped_expired_count:
            self._notify(
                f"Đã bỏ qua {result.skipped_expired_count} license hết hạn.",
                tone="info",
            )

    def _export_signed(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Xuất signed CSV",
            "signed-licenses.csv",
            "CSV (*.csv);;Tất cả file (*)",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(
                serialize_signed_csv(self._records), encoding="utf-8", newline=""
            )
        except OSError as exc:
            QMessageBox.critical(self, "Không thể xuất CSV", str(exc))
            return
        self._notify(f"Đã xuất {len(self._records)} license")

    def _sheet_client(self) -> GoogleSheetsClient:
        return GoogleSheetsClient(self._settings.sheets_config())

    def _pull_sheet(self) -> None:
        if self._records:
            answer = QMessageBox.question(
                self,
                "Tải dữ liệu từ Sheet",
                "Thao tác này sẽ thay bản cục bộ bằng dữ liệu đang công khai trên Sheet. Tiếp tục?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        def operation() -> list[LicenseRecord]:
            if self._settings.public_csv_url:
                records = download_public_records(self._settings.public_csv_url)
            else:
                records = self._sheet_client().read_records()
            return self._verified_records(records)

        def complete(records: Any) -> None:
            if not isinstance(records, list):
                raise RuntimeError("Unexpected Sheet result.")
            self._records = records
            if self._save_local():
                self._refresh_view()
                self._set_remote_digest(records)
                self._mark_synced(f"Đã tải {len(records)} license từ Sheet")

        self._run_operation("Đang tải dữ liệu từ Google Sheet…", operation, complete)

    def _push_sheet(self, *, force: bool = False) -> None:
        invalid_count = sum(
            record.status() is LicenseStatus.INVALID for record in self._records
        )
        if invalid_count:
            QMessageBox.critical(
                self,
                "Không thể đồng bộ",
                f"Có {invalid_count} license sai định dạng hoặc chữ ký. Hãy sửa hoặc thu hồi "
                "các dòng lỗi trước khi đẩy lên Sheet.",
            )
            return
        try:
            self._settings.sheets_config()
        except LicenseIssueError as exc:
            QMessageBox.warning(self, "Chưa cấu hình Google Sheet", str(exc))
            self._show_settings()
            return
        if self._settings.service_account_path is None:
            QMessageBox.warning(
                self,
                "Thiếu service account",
                "Đồng bộ ghi cần service-account JSON. Hãy chọn file trong Cài đặt.",
            )
            self._show_settings()
            return
        if not force:
            answer = QMessageBox.question(
                self,
                "Đồng bộ lên Google Sheet",
                f"Xuất bản {len(self._records)} license và xóa các dòng dư trên worksheet "
                f"“{self._settings.worksheet}”?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        snapshot = list(self._records)
        expected_digest = self._remote_digest()

        def operation() -> tuple[str, str]:
            client = self._sheet_client()
            current = client.read_records()
            current_digest = records_digest(current)
            if not force and expected_digest and current_digest != expected_digest:
                return "conflict", current_digest
            client.replace_records(snapshot, existing_records=current)
            return "ok", records_digest(snapshot)

        def complete(result: Any) -> None:
            status, digest = result
            if status == "conflict":
                answer = QMessageBox.warning(
                    self,
                    "Sheet đã thay đổi",
                    "Google Sheet đã được sửa từ lần đồng bộ gần nhất. Đẩy cưỡng bức sẽ ghi đè "
                    "những thay đổi đó. Bạn có muốn tiếp tục?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self._push_sheet(force=True)
                return
            self._qsettings.setValue(self._digest_key(), digest)
            self._mark_synced(f"Đã đồng bộ {len(snapshot)} license lên Sheet")

        self._run_operation("Đang đồng bộ lên Google Sheet…", operation, complete)

    def _format_sheet(self) -> None:
        try:
            client = self._sheet_client()
        except LicenseIssueError as exc:
            QMessageBox.warning(self, "Chưa cấu hình Google Sheet", str(exc))
            return
        self._run_operation(
            "Đang format Google Sheet…",
            lambda: client.format_worksheet(),
            lambda _result: self._notify("Đã format header, cột, bộ lọc và freeze hàng đầu."),
        )

    def _test_connection(self) -> None:
        try:
            client = self._sheet_client()
        except LicenseIssueError as exc:
            QMessageBox.warning(self, "Chưa cấu hình Google Sheet", str(exc))
            return

        def complete(records: Any) -> None:
            self._notify(f"Kết nối thành công. Đọc được {len(records)} license.")

        self._run_operation("Đang kiểm tra kết nối…", client.read_records, complete)

    def _open_sheet(self) -> None:
        try:
            url = self._settings.sheets_config().browser_url
        except LicenseIssueError as exc:
            QMessageBox.warning(self, "Chưa cấu hình Google Sheet", str(exc))
            return
        QDesktopServices.openUrl(QUrl(url))

    def _show_settings(self) -> None:
        previous_path = self._settings.local_csv_path
        dialog = SettingsDialog(
            self,
            self._settings,
            project_directory=self._project_store.project_directory(
                self._settings.project_id
            ),
            record_count=len(self._records),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        values = dialog.values()
        try:
            self._project_store.save(values)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, "Không thể lưu cài đặt", str(exc))
            return
        self._settings = values
        self._qsettings.setValue("projects/active", values.project_id)
        if self._settings.local_csv_path != previous_path:
            self._load_local(show_missing=True)
        else:
            try:
                self._records = self._verified_records(self._records)
            except LicenseIssueError as exc:
                QMessageBox.critical(self, "Không thể kiểm tra license", str(exc))
                self._records = []
        self._set_project_identity()
        self._rebuild_project_menu()
        self._refresh_view()
        self._notify("Đã lưu cài đặt")

    def _run_operation(
        self,
        message: str,
        operation: Callable[[], Any],
        on_success: Callable[[Any], None],
    ) -> None:
        if self._busy:
            return
        self._set_busy(True, message)
        worker = OperationThread(operation)
        self._workers.add(worker)

        def succeeded(result: Any) -> None:
            try:
                on_success(result)
            except Exception as exc:
                QMessageBox.critical(self, "Không thể hoàn tất thao tác", str(exc))

        def failed(error: str) -> None:
            QMessageBox.critical(self, "Thao tác thất bại", error)

        def finished() -> None:
            self._workers.discard(worker)
            worker.deleteLater()
            self._set_busy(False, "Sẵn sàng")

        worker.succeeded.connect(succeeded)
        worker.failed.connect(failed)
        worker.finished.connect(finished)
        worker.start()

    def _set_busy(self, busy: bool, _message: str) -> None:
        self._busy = busy
        for action in (
            self.new_action,
            self.pull_action,
            self.push_action,
            self.format_action,
            self.test_action,
            self.settings_action,
            self.new_project_action,
            self.import_project_keys_action,
        ):
            action.setEnabled(not busy)
        self.project_combo.setEnabled(not busy)
        self.primary_action_button.setEnabled(not busy)
        self.table.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        elif QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self._selection_changed()

    def _digest_key(self) -> str:
        return (
            f"sync/{self._settings.project_id}/{self._settings.spreadsheet_id}/"
            f"{self._settings.worksheet}/digest"
        )

    def _remote_digest(self) -> str:
        return str(self._qsettings.value(self._digest_key(), ""))

    def _set_remote_digest(self, records: list[LicenseRecord]) -> None:
        self._qsettings.setValue(self._digest_key(), records_digest(records))

    def _mark_synced(self, message: str) -> None:
        self.sync_badge.setText("Đã đồng bộ")
        self.sync_badge.setProperty("synced", True)
        self.sync_badge.style().unpolish(self.sync_badge)
        self.sync_badge.style().polish(self.sync_badge)
        self._notify(message)

    def _notify(self, message: str, *, tone: str = "success") -> None:
        self.toast.show_message(message, tone=tone)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast.reposition()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._workers:
            QMessageBox.information(
                self,
                "Đang có thao tác chạy",
                "Một thao tác mạng vẫn đang chạy. Vui lòng chờ thao tác hoàn tất rồi đóng "
                "ứng dụng để tránh làm gián đoạn đồng bộ.",
            )
            event.ignore()
            return
        event.accept()
