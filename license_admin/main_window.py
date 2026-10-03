"""Main desktop window for multi-project license administration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
import json
import hashlib
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
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from issue_license import LicenseIssueError, issue_license_until
from license_admin.app_identity import app_icon, app_logo_pixmap
from license_admin.dialogs import (
    LicenseEditorDialog,
    RecordDetailsDialog,
    SettingsDialog,
)
from license_admin.dashboard_widgets import (
    MetricCard,
    SidebarButton,
    SidebarMenuButton,
)
from license_admin.data_recovery import (
    ProjectDataState,
    load_project_records,
)
from license_admin.data_state_banner import DataStateBanner
from license_admin.domain import (
    LicenseRecord,
    LicenseStatus,
    license_key_id,
    parse_signed_csv,
    records_digest,
    serialize_signed_csv,
    validate_record_signatures,
)
from license_admin.google_sheets import (
    GoogleSheetsClient,
    GoogleSheetsConfig,
    RemoteRevision,
    RemoteSnapshot,
    SheetConflictError,
    download_public_records,
)
from license_admin.flag_icons import FlagIconLoader
from license_admin.icons import svg_icon
from license_admin.information_dialogs import (
    AboutDialog,
    InformationDialog,
    PolicyDialog,
    TermsOfServiceDialog,
)
from license_admin.key_import_dialog import KeyImportDialog
from license_admin.key_identity import KeyIdentityStore
from license_admin.key_store import KeyPasswordRequiredError, load_private_key_file
from license_admin.key_rotation import resign_unexpired_records
from license_admin.localization import (
    LANGUAGES,
    current_language,
    set_language,
    text,
)
from license_admin.modal_backdrop import ModalBackdrop
from license_admin.popover import PopoverSelect, RoundedMenu
from license_admin.project_config import (
    export_project_config,
    import_project_config,
)
from license_admin.project_lock import ProjectLease, ProjectLockError
from license_admin.project_selector import ProjectSelector
from license_admin.qt_models import LicenseFilterModel, LicenseTableModel
from license_admin.record_transaction import RecordTransaction
from license_admin.service_account_import_dialog import ServiceAccountImportDialog
from license_admin.settings import AdminSettings, ProjectStore, normalize_project_id
from license_admin.settings_transaction import SettingsTransaction
from license_admin.storage import LicenseRepository
from license_admin.sync_models import (
    LocalSyncContext,
    SyncDiff,
    SyncDirection,
    SyncTarget,
    SyncTargetKind,
    build_sync_diff,
)
from license_admin.toast import Toast
from license_admin.theme import apply_theme
from license_admin.theme_toggle import ThemeToggle
from license_admin.ui_metrics import CONTROL_HEIGHT
from license_admin.worker import OperationThread
from license_admin.window_chrome import (
    APP_HEADER_HEIGHT,
    DraggableFrame,
    FramelessResizeController,
    WindowControls,
    enable_frameless_window,
)
from migrate_license_csv import migrate_legacy_csv


class LicenseAdminWindow(QMainWindow):
    def __init__(
        self,
        *,
        project_store: ProjectStore | None = None,
        qsettings: QSettings | None = None,
    ) -> None:
        super().__init__()
        enable_frameless_window(self)
        self.resize(1320, 820)
        self.setMinimumSize(980, 640)
        self.setWindowIcon(app_icon())

        self._qsettings = qsettings or QSettings("LicenseTools", "LicenseAdmin")
        set_language(str(self._qsettings.value("ui/language", "en")))
        self._theme_mode = apply_theme(
            str(self._qsettings.value("ui/theme", "dark"))
        )
        self._project_store = project_store or ProjectStore()
        catalog_lease = ProjectLease.acquire(self._project_store.root)
        try:
            default_profile = self._project_store.ensure_default()
        finally:
            catalog_lease.release()
        active_project = str(
            self._qsettings.value("projects/active", default_profile.project_id)
        ).strip()
        try:
            active_project = normalize_project_id(active_project)
        except LicenseIssueError:
            active_project = default_profile.project_id
        try:
            self._settings, self._project_lease = self._acquire_project_state(
                active_project
            )
        except ProjectLockError:
            raise
        except LicenseIssueError:
            if active_project == default_profile.project_id:
                raise
            self._settings, self._project_lease = self._acquire_project_state(
                default_profile.project_id
            )
        self._qsettings.setValue("projects/active", self._settings.project_id)
        self._workers: set[OperationThread] = set()
        self._busy = False
        self._operation_continuation: Callable[[], None] | None = None
        self._local_revision = 0
        self._records: list[LicenseRecord] = []
        self._data_state = ProjectDataState.EMPTY
        self._data_state_detail = ""
        self._set_project_identity()

        self._create_actions()
        self._build_ui()
        self._frameless_resize = FramelessResizeController(self)
        self._create_menus()
        self._load_local(show_missing=False)
        self._refresh_view()

    def _acquire_project_state(
        self,
        project_id: str,
    ) -> tuple[AdminSettings, ProjectLease]:
        """Acquire the project lease before reading its mutable profile."""
        lease = ProjectLease.acquire(
            self._project_store.project_directory(project_id)
        )
        try:
            settings = self._project_store.load(project_id)
        except Exception:
            lease.release()
            raise
        return settings, lease

    def _create_actions(self) -> None:
        self.new_action = QAction(svg_icon("plus"), text("action.new_license"), self)
        self.new_action.setShortcut("Ctrl+N")
        self.new_action.triggered.connect(self._add_license)
        self.edit_action = QAction(svg_icon("edit"), text("action.edit_license"), self)
        self.edit_action.setShortcut("Ctrl+E")
        self.edit_action.triggered.connect(self._edit_license)
        self.revoke_action = QAction(svg_icon("trash"), text("action.revoke"), self)
        self.revoke_action.setShortcut("Delete")
        self.revoke_action.triggered.connect(self._revoke_license)
        self.details_action = QAction(svg_icon("eye"), text("action.details"), self)
        self.details_action.triggered.connect(self._show_details)
        self.pull_action = QAction(svg_icon("download"), text("action.pull_sheet"), self)
        self.pull_action.setShortcut("Ctrl+Shift+D")
        self.pull_action.triggered.connect(self._pull_sheet)
        self.push_action = QAction(svg_icon("upload"), text("action.push_sheet"), self)
        self.push_action.setShortcut("Ctrl+Shift+U")
        self.push_action.triggered.connect(self._push_sheet)
        self.format_action = QAction(svg_icon("format"), text("action.format_sheet"), self)
        self.format_action.triggered.connect(self._format_sheet)
        self.test_action = QAction(svg_icon("plug"), text("action.test_connection"), self)
        self.test_action.triggered.connect(self._test_connection)
        self.open_sheet_action = QAction(svg_icon("external"), text("action.open_sheet"), self)
        self.open_sheet_action.triggered.connect(self._open_sheet)
        self.settings_action = QAction(svg_icon("settings"), text("action.settings"), self)
        self.settings_action.setShortcut("Ctrl+,")
        self.settings_action.triggered.connect(self._show_settings)
        self.new_project_action = QAction(svg_icon("plus"), text("action.new_project"), self)
        self.new_project_action.triggered.connect(self._create_project)
        self.open_project_folder_action = QAction(
            svg_icon("folder"), text("action.open_project_folder"), self
        )
        self.open_project_folder_action.triggered.connect(self._open_project_folder)
        self.import_project_keys_action = QAction(
            svg_icon("key"), text("action.import_keys"), self
        )
        self.import_project_keys_action.triggered.connect(self._import_project_keys)
        self.resign_licenses_action = QAction(
            svg_icon("key"), text("action.resign_licenses"), self
        )
        self.resign_licenses_action.triggered.connect(self._resign_licenses)
        self.revoke_rotated_key_action = QAction(
            svg_icon("trash"), text("action.revoke_rotated_key"), self
        )
        self.revoke_rotated_key_action.triggered.connect(self._revoke_rotated_key)
        self.import_google_credentials_action = QAction(
            svg_icon("upload"), text("action.import_credentials"), self
        )
        self.import_google_credentials_action.triggered.connect(
            self._import_google_credentials
        )
        self.import_project_config_action = QAction(
            svg_icon("import"), text("action.import_project_config"), self
        )
        self.import_project_config_action.triggered.connect(
            self._import_project_config
        )
        self.export_project_config_action = QAction(
            svg_icon("export"), text("action.export_project_config"), self
        )
        self.export_project_config_action.triggered.connect(
            self._export_project_config
        )
        self.import_signed_action = QAction(
            svg_icon("import"), text("action.import_signed"), self
        )
        self.import_signed_action.triggered.connect(self._import_signed)
        self.import_legacy_action = QAction(
            svg_icon("migration"), text("action.import_legacy"), self
        )
        self.import_legacy_action.triggered.connect(self._import_legacy)
        self.export_action = QAction(svg_icon("export"), text("action.export_signed"), self)
        self.export_action.setShortcut("Ctrl+S")
        self.export_action.triggered.connect(self._export_signed)
        self.quit_action = QAction(svg_icon("close"), text("action.quit"), self)
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
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        self._flag_icons = FlagIconLoader(self)
        self._flag_icons.icon_loaded.connect(self._flag_icon_loaded)
        self.language_selector = PopoverSelect()
        self.language_selector.setObjectName("languageSelect")
        self.language_selector.setFixedSize(112, CONTROL_HEIGHT)
        self.language_selector.setIconSize(QSize(20, 14))
        for option in LANGUAGES:
            self.language_selector.add_item(
                option.native_name,
                option.code,
                icon=self._flag_icons.icon(option.country_code),
            )
        self.language_selector.set_current_data(current_language())
        self.language_selector.selection_changed.connect(self._language_selected)
        self.theme_toggle = ThemeToggle(self._theme_mode)
        self.theme_toggle.mode_changed.connect(self._theme_selected)

        self.sidebar_header = DraggableFrame()
        self.sidebar_header.setObjectName("sidebarHeader")
        self.sidebar_header.setFixedHeight(APP_HEADER_HEIGHT)
        self.sidebar_header_layout = QHBoxLayout(self.sidebar_header)
        self.sidebar_header_layout.setContentsMargins(12, 0, 8, 0)
        self.sidebar_header_layout.setSpacing(5)

        self.header_brand = QWidget()
        self.header_brand.setObjectName("headerBrand")
        self.header_brand.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Preferred,
        )
        self.header_brand.setFixedWidth(130)
        header_brand_layout = QHBoxLayout(self.header_brand)
        header_brand_layout.setContentsMargins(0, 0, 0, 0)
        header_brand_layout.setSpacing(6)
        self.brand_mark = QLabel()
        self.brand_mark.setObjectName("brandLogo")
        self.brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_mark.setFixedSize(24, 24)
        self.brand_mark.setPixmap(app_logo_pixmap(22))
        self.brand_name = QLabel("LICENSE ADMIN")
        self.brand_name.setObjectName("brandName")
        header_brand_layout.addWidget(self.brand_mark)
        header_brand_layout.addWidget(self.brand_name)
        self.sidebar_header_layout.addWidget(self.header_brand)
        self.sidebar_header_layout.addStretch(1)
        self.sidebar_toggle = QToolButton()
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setFixedSize(28, 28)
        self.sidebar_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_toggle.clicked.connect(self._toggle_sidebar)
        self.sidebar_header_layout.addWidget(self.sidebar_toggle)
        sidebar_layout.addWidget(self.sidebar_header)

        sidebar_content = QWidget()
        self.sidebar_content_layout = QVBoxLayout(sidebar_content)
        self.sidebar_content_layout.setContentsMargins(10, 4, 10, 12)
        self.sidebar_content_layout.setSpacing(5)

        self.overview_button = SidebarButton(text("nav.overview"), "grid", active=True)
        self.overview_button.clicked.connect(self._focus_dashboard)
        self.new_sidebar_button = SidebarButton(text("action.new_license"), "plus")
        self.new_sidebar_button.clicked.connect(self.new_action.trigger)
        self.license_sidebar_menu = SidebarMenuButton(text("nav.license"), "key")
        self.sheet_sidebar_menu = SidebarMenuButton(text("nav.sheets"), "cloud")
        self.data_sidebar_menu = SidebarMenuButton(text("nav.data"), "database")
        self.settings_sidebar_button = SidebarButton(text("action.settings"), "settings")
        self.settings_sidebar_button.clicked.connect(self.settings_action.trigger)
        for sidebar_button in (
            self.overview_button,
            self.new_sidebar_button,
            self.license_sidebar_menu,
            self.sheet_sidebar_menu,
            self.data_sidebar_menu,
            self.settings_sidebar_button,
        ):
            self.sidebar_content_layout.addWidget(sidebar_button)
        self.sidebar_content_layout.addStretch(1)

        self.project_sidebar_menu = SidebarMenuButton(
            text("nav.manage_projects"), "folder-project"
        )
        self.sidebar_content_layout.addWidget(self.project_sidebar_menu)
        sidebar_layout.addWidget(sidebar_content, 1)
        shell.addWidget(self.sidebar)

        self.main_surface = QWidget()
        self.main_surface.setObjectName("mainSurface")
        main_layout = QVBoxLayout(self.main_surface)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.top_bar = DraggableFrame()
        self.top_bar.setObjectName("topBar")
        self.top_bar.setFixedHeight(APP_HEADER_HEIGHT)
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(12, 8, 12, 8)
        top_bar_layout.setSpacing(8)
        self.project_combo = ProjectSelector()
        top_bar_layout.addWidget(self.project_combo)
        self.primary_action_button = QPushButton(text("action.new_license"))
        self.primary_action_button.setObjectName("primaryButton")
        self.primary_action_button.setFixedWidth(128)
        self.primary_action_button.setFixedHeight(CONTROL_HEIGHT)
        self.primary_action_button.setIcon(svg_icon("plus-dark"))
        self.primary_action_button.setIconSize(QSize(16, 16))
        self.primary_action_button.clicked.connect(self.new_action.trigger)
        top_bar_layout.addWidget(
            self.primary_action_button,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        top_bar_layout.addStretch(1)

        self.header_info_group = QFrame()
        self.header_info_group.setObjectName("headerInfoGroup")
        self.header_info_group.setFixedHeight(CONTROL_HEIGHT)
        header_info_layout = QHBoxLayout(self.header_info_group)
        header_info_layout.setContentsMargins(1, 1, 1, 1)
        header_info_layout.setSpacing(0)
        self.about_button = self._header_info_button(
            "about",
            "info.about",
            self._show_about,
        )
        self.policy_button = self._header_info_button(
            "shield",
            "info.policy",
            self._show_policy,
        )
        self.terms_button = self._header_info_button(
            "document",
            "info.terms",
            self._show_terms,
        )
        for index, info_button in enumerate(
            (self.about_button, self.policy_button, self.terms_button)
        ):
            if index:
                divider = QFrame()
                divider.setObjectName("headerInfoDivider")
                divider.setFixedSize(1, 16)
                header_info_layout.addWidget(
                    divider,
                    alignment=Qt.AlignmentFlag.AlignVCenter,
                )
            header_info_layout.addWidget(info_button)
        top_bar_layout.addWidget(
            self.header_info_group,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        top_bar_layout.addWidget(
            self.theme_toggle,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        top_bar_layout.addWidget(
            self.language_selector,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        self.window_controls = WindowControls(self)
        top_bar_layout.addWidget(
            self.window_controls,
            alignment=Qt.AlignmentFlag.AlignVCenter,
        )
        main_layout.addWidget(self.top_bar)

        self.content_surface = QWidget()
        self.content_surface.setObjectName("contentSurface")
        root = QVBoxLayout(self.content_surface)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(10)

        self.data_state_banner = DataStateBanner()
        self.data_state_banner.retry_requested.connect(self._retry_local_data)
        self.data_state_banner.open_folder_requested.connect(
            self._open_project_folder
        )
        root.addWidget(self.data_state_banner)

        self.metrics_layout = QHBoxLayout()
        self.metrics_layout.setSpacing(8)
        self.total_card = MetricCard(
            text("metric.total"),
            text("metric.total_note"),
            "total",
            "#25bdea",
        )
        self.active_card = MetricCard(
            text("status.active"),
            text("metric.active_note"),
            "check",
            "#32d296",
        )
        self.expiring_card = MetricCard(
            text("status.expiring"),
            text("metric.expiring_note"),
            "clock",
            "#f4bc42",
        )
        self.expired_card = MetricCard(
            text("metric.expired_error"),
            text("metric.expired_note"),
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
        self.table_header = QWidget()
        self.table_header.setObjectName("tableHeader")
        table_header_layout = QHBoxLayout(self.table_header)
        table_header_layout.setContentsMargins(10, 8, 12, 8)
        table_header_layout.setSpacing(8)

        self.table_filters = QWidget()
        self.table_filters.setObjectName("tableFilters")
        self.table_filters.setMaximumWidth(720)
        self.table_filters.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        filters = QHBoxLayout(self.table_filters)
        filters.setContentsMargins(0, 0, 0, 0)
        filters.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("dashboardSearch")
        self.search_edit.setPlaceholderText(text("dashboard.search"))
        self._search_icon_action = self.search_edit.addAction(
            svg_icon("search", 16), QLineEdit.ActionPosition.LeadingPosition
        )
        self._search_clear_action = self.search_edit.addAction(
            svg_icon("close", 16), QLineEdit.ActionPosition.TrailingPosition
        )
        self._search_clear_action.setVisible(False)
        self._search_clear_action.triggered.connect(self.search_edit.clear)
        self.search_edit.setMinimumWidth(180)
        self.search_edit.setMaximumWidth(520)
        self.search_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.status_combo = PopoverSelect()
        self.status_combo.setFixedWidth(150)
        self.status_combo.setFixedHeight(CONTROL_HEIGHT)
        self._populate_status_selector()
        filters.addWidget(self.search_edit, 1)
        filters.addWidget(self.status_combo)
        table_header_layout.addWidget(self.table_filters)
        table_header_layout.addStretch(1)

        self.visible_label = QLabel()
        self.visible_label.setObjectName("muted")
        table_header_layout.addWidget(self.visible_label)
        self._sync_badge_state = "unsynced"
        self.sync_badge = QLabel(text("sync.unsynced"))
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
        table_panel_layout.addWidget(self.table_header)

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
        horizontal_header = self.table.horizontalHeader()
        horizontal_header.setStretchLastSection(True)
        horizontal_header.setMinimumSectionSize(72)
        horizontal_header.setSectionResizeMode(
            2,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        horizontal_header.setSectionResizeMode(
            3,
            QHeaderView.ResizeMode.ResizeToContents,
        )
        self.table.verticalHeader().setVisible(True)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.verticalHeader().setMinimumWidth(42)
        self.table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setColumnWidth(0, 180)
        self.table.setColumnWidth(1, 310)
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
        self.status_combo.selection_changed.connect(self._filter_status_changed)
        self.proxy_model.rowsInserted.connect(lambda *_args: self._refresh_visible_count())
        self.proxy_model.rowsRemoved.connect(lambda *_args: self._refresh_visible_count())
        self.proxy_model.modelReset.connect(self._refresh_visible_count)
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        self.project_combo.selection_changed.connect(self._project_combo_changed)
        self._set_sidebar_collapsed(False)
        self.setCentralWidget(central)
        self.toast = Toast(self)
        self.statusBar().hide()
        self._selection_changed()

    def _header_info_button(
        self,
        icon_name: str,
        label_key: str,
        callback: Callable[[], None],
    ) -> QToolButton:
        button = QToolButton(self.header_info_group)
        button.setObjectName("headerInfoButton")
        button.setFixedSize(CONTROL_HEIGHT - 2, CONTROL_HEIGHT - 2)
        button.setIcon(svg_icon(icon_name, 16))
        button.setIconSize(QSize(16, 16))
        button.setToolTip(text(label_key))
        button.setAccessibleName(text(label_key))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def _create_menus(self) -> None:
        self.menuBar().hide()
        self.project_menu = RoundedMenu(text("nav.manage_projects"), self)
        self._rebuild_project_menu()
        self.file_menu = RoundedMenu(text("nav.data"), self)
        self.file_menu.addAction(self.import_signed_action)
        self.file_menu.addAction(self.import_legacy_action)
        self.file_menu.addAction(self.resign_licenses_action)
        self.file_menu.addAction(self.export_action)
        self.license_menu = RoundedMenu(text("nav.license"), self)
        self.license_menu.addAction(self.new_action)
        self.license_menu.addAction(self.edit_action)
        self.license_menu.addAction(self.revoke_action)
        self.license_menu.addAction(self.details_action)
        self.sheet_menu = RoundedMenu(text("nav.sheets"), self)
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

    def _populate_status_selector(self) -> None:
        selected = self.status_combo.current_data()
        self.status_combo.clear_items()
        for label_key, status in (
            ("status.all", None),
            ("status.active", LicenseStatus.ACTIVE),
            ("status.expiring", LicenseStatus.EXPIRING),
            ("status.expired", LicenseStatus.EXPIRED),
            ("status.future", LicenseStatus.FUTURE),
            ("status.invalid", LicenseStatus.INVALID),
        ):
            self.status_combo.add_item(text(label_key), status)
        self.status_combo.set_current_data(selected)

    def _language_selected(self, value: object) -> None:
        if not isinstance(value, str):
            return
        code = set_language(value)
        self._qsettings.setValue("ui/language", code)
        self._retranslate_ui()

    def _theme_selected(self, mode: str) -> None:
        self._theme_mode = apply_theme(mode)
        self._qsettings.setValue("ui/theme", self._theme_mode)
        self.theme_toggle.set_mode(self._theme_mode)

    def _flag_icon_loaded(self, country_code: str, icon: QIcon) -> None:
        option = next(
            (item for item in LANGUAGES if item.country_code == country_code),
            None,
        )
        if option is not None:
            self.language_selector.set_item_icon(option.code, icon)

    def _retranslate_ui(self) -> None:
        for action, key in (
            (self.new_action, "action.new_license"),
            (self.edit_action, "action.edit_license"),
            (self.revoke_action, "action.revoke"),
            (self.details_action, "action.details"),
            (self.pull_action, "action.pull_sheet"),
            (self.push_action, "action.push_sheet"),
            (self.format_action, "action.format_sheet"),
            (self.test_action, "action.test_connection"),
            (self.open_sheet_action, "action.open_sheet"),
            (self.settings_action, "action.settings"),
            (self.new_project_action, "action.new_project"),
            (self.open_project_folder_action, "action.open_project_folder"),
            (self.import_project_keys_action, "action.import_keys"),
            (self.resign_licenses_action, "action.resign_licenses"),
            (self.revoke_rotated_key_action, "action.revoke_rotated_key"),
            (self.import_google_credentials_action, "action.import_credentials"),
            (self.import_project_config_action, "action.import_project_config"),
            (self.export_project_config_action, "action.export_project_config"),
            (self.import_signed_action, "action.import_signed"),
            (self.import_legacy_action, "action.import_legacy"),
            (self.export_action, "action.export_signed"),
            (self.quit_action, "action.quit"),
        ):
            action.setText(text(key))
        self.window_controls.retranslate()
        self.theme_toggle.retranslate()
        for button, label_key in (
            (self.about_button, "info.about"),
            (self.policy_button, "info.policy"),
            (self.terms_button, "info.terms"),
        ):
            button.setToolTip(text(label_key))
            button.setAccessibleName(text(label_key))
        self.overview_button.set_label(text("nav.overview"))
        self.new_sidebar_button.set_label(text("action.new_license"))
        self.license_sidebar_menu.set_label(text("nav.license"))
        self.sheet_sidebar_menu.set_label(text("nav.sheets"))
        self.data_sidebar_menu.set_label(text("nav.data"))
        self.settings_sidebar_button.set_label(text("action.settings"))
        self.project_sidebar_menu.set_label(text("nav.manage_projects"))
        self._update_sidebar_toggle()
        self.search_edit.setPlaceholderText(text("dashboard.search"))
        self.primary_action_button.setText(text("action.new_license"))
        self.total_card.set_texts(text("metric.total"), text("metric.total_note"))
        self.active_card.set_texts(text("status.active"), text("metric.active_note"))
        self.expiring_card.set_texts(
            text("status.expiring"), text("metric.expiring_note")
        )
        self.expired_card.set_texts(
            text("metric.expired_error"), text("metric.expired_note")
        )
        self.project_menu.setTitle(text("nav.manage_projects"))
        self.file_menu.setTitle(text("nav.data"))
        self.license_menu.setTitle(text("nav.license"))
        self.sheet_menu.setTitle(text("nav.sheets"))
        self._populate_status_selector()
        self.table_model.retranslate()
        self._set_sync_badge(self._sync_badge_state)
        self._update_data_state_banner()
        self._refresh_visible_count()
        self._rebuild_project_menu()

    def _set_sync_badge(self, state: str) -> None:
        self._sync_badge_state = state
        key = {
            "unsynced": "sync.unsynced",
            "dirty": "sync.dirty",
            "synced": "sync.synced",
        }.get(state, "sync.unsynced")
        self.sync_badge.setText(text(key))
        self.sync_badge.setProperty("synced", state == "synced")
        self.sync_badge.style().unpolish(self.sync_badge)
        self.sync_badge.style().polish(self.sync_badge)

    def _set_project_identity(self) -> None:
        self.setWindowTitle(f"{self._settings.project_name} — License Admin")

    def _toggle_sidebar(self) -> None:
        self._set_sidebar_collapsed(not self._sidebar_collapsed)

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(72 if collapsed else 220)
        self.header_brand.setVisible(not collapsed)
        self.sidebar_header_layout.setContentsMargins(
            6 if collapsed else 12,
            0,
            4 if collapsed else 8,
            0,
        )
        self.sidebar_header_layout.setSpacing(2 if collapsed else 5)
        self.sidebar_content_layout.setContentsMargins(
            8 if collapsed else 10,
            4,
            8 if collapsed else 10,
            12,
        )
        for button in (
            self.overview_button,
            self.new_sidebar_button,
            self.license_sidebar_menu,
            self.sheet_sidebar_menu,
            self.data_sidebar_menu,
            self.settings_sidebar_button,
            self.project_sidebar_menu,
        ):
            button.set_collapsed(collapsed)
        self._update_sidebar_toggle()

    def _update_sidebar_toggle(self) -> None:
        self.sidebar_toggle.setIcon(svg_icon("sidebar-toggle", 16))
        self.sidebar_toggle.setToolTip(
            text(
                "nav.expand_sidebar"
                if self._sidebar_collapsed
                else "nav.collapse_sidebar"
            )
        )
        self.sidebar_toggle.setIconSize(QSize(16, 16))

    def _show_information_dialog(self, dialog: InformationDialog) -> None:
        with ModalBackdrop(self):
            dialog.exec()

    def _show_about(self) -> None:
        self._show_information_dialog(AboutDialog(self))

    def _show_policy(self) -> None:
        self._show_information_dialog(PolicyDialog(self))

    def _show_terms(self) -> None:
        self._show_information_dialog(TermsOfServiceDialog(self))

    def _rebuild_project_menu(self) -> None:
        self.project_menu.clear()
        scan = self._project_store.scan_profiles()
        self.project_menu.addAction(self.new_project_action)
        self.project_menu.addAction(self.import_project_keys_action)
        self.project_menu.addAction(self.revoke_rotated_key_action)
        self.project_menu.addAction(self.import_google_credentials_action)
        self.project_menu.addSeparator()
        self.project_menu.addAction(self.import_project_config_action)
        self.project_menu.addAction(self.export_project_config_action)
        self.project_menu.addSeparator()
        self.project_menu.addAction(self.open_project_folder_action)
        self.project_menu.addAction(self.settings_action)
        if scan.issues:
            self.project_menu.addSeparator()
            for issue in scan.issues:
                unavailable = self.project_menu.addAction(
                    text("project.unavailable", project=issue.project_id)
                )
                unavailable.setEnabled(False)
                unavailable.setToolTip(issue.detail)
        self.project_combo.clear_items()
        for profile in scan.profiles:
            self.project_combo.add_item(profile.project_name, profile.project_id)
        self.project_combo.set_current_data(self._settings.project_id)
        self._set_project_identity()

    def _project_combo_changed(self, project_id: object) -> None:
        if isinstance(project_id, str):
            self._switch_project(project_id)

    def _focus_dashboard(self) -> None:
        self.search_edit.setFocus()

    def _create_project(self) -> None:
        if self._busy:
            return
        project_name, accepted = QInputDialog.getText(
            self,
            text("project.add_title"),
            text("project.name_prompt"),
        )
        if not accepted or not project_name.strip():
            return
        candidate_lease: ProjectLease | None = None
        try:
            project_id = normalize_project_id(project_name)
            candidate_lease = ProjectLease.acquire(
                self._project_store.project_directory(project_id)
            )
            profile = self._project_store.create(project_name, project_id)
        except LicenseIssueError as exc:
            if candidate_lease is not None:
                candidate_lease.release()
            QMessageBox.warning(self, text("project.create_failed"), str(exc))
            return
        self._activate_project(profile, candidate_lease)
        self._notify(text("project.created", name=profile.project_name))
        self._show_settings()

    def _switch_project(self, project_id: str) -> None:
        if self._busy or project_id == self._settings.project_id:
            return
        try:
            settings, candidate_lease = self._acquire_project_state(
                project_id
            )
        except LicenseIssueError as exc:
            self.project_combo.set_current_data(self._settings.project_id)
            QMessageBox.critical(self, text("project.open_failed"), str(exc))
            return

        self._activate_project(settings, candidate_lease)

    def _activate_project(
        self,
        settings: AdminSettings,
        candidate_lease: ProjectLease,
    ) -> None:
        previous_lease = self._project_lease
        self._project_lease = candidate_lease
        self._settings = settings
        previous_lease.release()
        self._qsettings.setValue("projects/active", settings.project_id)
        self.search_edit.clear()
        self.status_combo.set_current_data(None, emit=True)
        self._set_sync_badge("unsynced")
        self._set_project_identity()
        self._load_local(show_missing=True)
        self._refresh_view()
        self._rebuild_project_menu()
        self._notify(text("project.switched", name=self._settings.project_name), tone="info")

    def _open_project_folder(self) -> None:
        directory = self._project_store.project_directory(self._settings.project_id)
        directory.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _import_project_keys(self) -> None:
        if self._busy:
            return
        project_directory = self._project_store.project_directory(
            self._settings.project_id
        )
        transaction = SettingsTransaction(project_directory)
        try:
            dialog = KeyImportDialog(
                self,
                project_name=self._settings.project_name,
                project_directory=project_directory,
                record_count=len(self._records),
                install_directory=transaction.key_staging_directory,
                display_directory=transaction.asset_directory,
                current_private_key_path=self._settings.signing_key_path,
                current_public_key_path=self._settings.public_key_path,
            )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("key.import_failed"), str(exc))
            return
        if dialog.exec() != dialog.DialogCode.Accepted:
            transaction.discard()
            return
        imported = dialog.imported_pair()
        transaction.register_key_pair(imported)
        updated = replace(
            self._settings,
            signing_key_path=transaction.private_key_path,
            public_key_path=transaction.public_key_path,
        )
        try:
            self._settings = transaction.commit(self._project_store, updated)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("project.update_failed"), str(exc))
            return
        self._load_local(show_missing=True)
        self._refresh_view()
        self._notify(
            text(
                "project.keys_imported",
                bits=imported.info.key_size,
                fingerprint=imported.info.short_fingerprint,
            )
        )

    def _import_google_credentials(self) -> None:
        if self._busy:
            return
        dialog = ServiceAccountImportDialog(
            self,
            project_name=self._settings.project_name,
            project_directory=self._project_store.project_directory(
                self._settings.project_id
            ),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        imported = dialog.imported_service_account()
        updated = replace(self._settings, service_account_path=imported.path)
        try:
            self._project_store.save(updated)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("project.update_failed"), str(exc))
            return
        self._settings = updated
        self._notify(text("project.credential_imported", email=imported.info.client_email))

    def _resign_licenses(self) -> None:
        if self._busy or not self._ensure_data_writable():
            return
        preview_time = datetime.now(timezone.utc)
        eligible = [
            record
            for record in self._records
            if record.parse_error is None
            and record.expires_at is not None
            and record.expires_at > preview_time
        ]
        skipped = len(self._records) - len(eligible)
        if not eligible:
            self._notify(text("key.resign_none"), tone="info")
            return
        answer = QMessageBox.question(
            self,
            text("key.resign_title"),
            text("key.resign_body", count=len(eligible), skipped=skipped),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        private_key = self._load_signing_key()
        if private_key is None:
            return
        try:
            result = resign_unexpired_records(
                self._records,
                private_key,
                issuer=self._settings.issuer,
                audience=self._settings.audience,
                now=datetime.now(timezone.utc),
            )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("license.sign_failed"), str(exc))
            return
        if self._commit_records(RecordTransaction.sorted_records(result.records)) is not None:
            self._notify(
                text(
                    "key.resigned",
                    count=result.resigned_count,
                    skipped=result.unchanged_count,
                )
            )

    def _revoke_rotated_key(self) -> None:
        if self._busy or not self._ensure_data_writable():
            return
        store = KeyIdentityStore(
            self._project_store.project_directory(self._settings.project_id)
        )
        try:
            ring = store.load()
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("key.revoke_failed"), str(exc))
            return
        candidates = [
            key
            for key in ring.keys
            if key.key_id != ring.active_key_id and key.revoked_at is None
        ]
        if not candidates:
            self._notify(text("key.revoke_none"), tone="info")
            return
        labels = [
            f"{key.key_id} — {key.rotated_at or key.created_at}"
            for key in candidates
        ]
        selected, accepted = QInputDialog.getItem(
            self,
            text("key.revoke_title"),
            text("key.revoke_select"),
            labels,
            0,
            False,
        )
        if not accepted:
            return
        index = labels.index(selected)
        key = candidates[index]
        affected = sum(
            license_key_id(record.token) == key.key_id for record in self._records
        )
        answer = QMessageBox.warning(
            self,
            text("key.revoke_title"),
            text("key.revoke_body", key_id=key.key_id, count=affected),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            updated_ring = store.revoke(key.key_id)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("key.revoke_failed"), str(exc))
            return
        self._settings = replace(
            self._settings,
            trusted_public_key_paths=store.trusted_public_key_paths(updated_ring),
        )
        self._load_local(show_missing=True)
        self._refresh_view()
        self._notify(text("key.revoked", key_id=key.key_id))

    def _import_project_config(self) -> None:
        if self._busy:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self,
            text("config.import_title"),
            "",
            f"JSON (*.json);;{text('common.all_files')}",
        )
        if not filename:
            return
        try:
            updated = import_project_config(Path(filename), self._settings)
        except LicenseIssueError as exc:
            QMessageBox.warning(self, text("config.invalid"), str(exc))
            return
        answer = QMessageBox.question(
            self,
            text("config.apply_title"),
            text(
                "config.apply_body",
                file=Path(filename).name,
                project=self._settings.project_name,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self._project_store.save(updated)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("config.apply_failed"), str(exc))
            return
        self._settings = updated
        self._load_local(show_missing=True)
        self._set_project_identity()
        self._rebuild_project_menu()
        self._refresh_view()
        self._notify(text("config.applied"))

    def _export_project_config(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            text("config.export_title"),
            f"{self._settings.project_id}-settings.json",
            f"JSON (*.json);;{text('common.all_files')}",
        )
        if not filename:
            return
        target = Path(filename)
        if target.resolve(strict=False) == self._project_store.profile_path(
            self._settings.project_id
        ).resolve(strict=False):
            QMessageBox.warning(
                self,
                text("config.overwrite_title"),
                text("config.overwrite_body"),
            )
            return
        try:
            exported = export_project_config(self._settings, target)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("config.export_failed"), str(exc))
            return
        self._notify(text("config.exported", file=exported.name))

    def _load_local(self, *, show_missing: bool) -> None:
        result = load_project_records(self._settings)
        self._records = list(result.records)
        self._advance_local_revision()
        self._data_state = result.state
        self._data_state_detail = result.detail
        self._update_data_state_banner()
        self._update_action_states()
        self._refresh_sync_badge_from_baseline()
        if show_missing and not result.state.allows_writes:
            QMessageBox.critical(
                self,
                text("data.open_failed"),
                f"{self._data_state_title()}\n\n{result.detail}",
            )

    def _retry_local_data(self) -> None:
        if self._busy:
            return
        self._load_local(show_missing=True)
        self._refresh_view()

    def _commit_records(
        self,
        transaction: RecordTransaction,
        *,
        allow_busy: bool = False,
    ) -> tuple[LicenseRecord, ...] | None:
        """Persist a candidate snapshot before publishing it to the UI state."""
        if self._busy and not allow_busy:
            return None
        if not self._ensure_data_writable():
            return None
        try:
            snapshot = transaction.commit(
                LicenseRepository(self._settings.local_csv_path)
            )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("data.save_failed"), str(exc))
            return None
        self._records = list(snapshot)
        self._advance_local_revision()
        self._data_state = (
            ProjectDataState.READY if self._records else ProjectDataState.EMPTY
        )
        self._data_state_detail = ""
        self._update_data_state_banner()
        self._update_action_states()
        self._set_sync_badge("dirty")
        self._refresh_view()
        return snapshot

    def _ensure_data_writable(self) -> bool:
        if self._data_state.allows_writes:
            return True
        QMessageBox.warning(
            self,
            text("data.read_only_title"),
            text("data.read_only_body", state=self._data_state_title()),
        )
        return False

    def _data_state_title(self) -> str:
        key = {
            ProjectDataState.EMPTY: "data.empty_title",
            ProjectDataState.READY: "data.ready_title",
            ProjectDataState.CORRUPTED: "data.corrupted_title",
            ProjectDataState.WRONG_KEY: "data.wrong_key_title",
            ProjectDataState.PERMISSION_DENIED: "data.permission_title",
            ProjectDataState.UNAVAILABLE: "data.unavailable_title",
        }[self._data_state]
        return text(key)

    def _update_data_state_banner(self) -> None:
        if not hasattr(self, "data_state_banner"):
            return
        if self._data_state is ProjectDataState.READY:
            self.data_state_banner.hide()
            return
        body_key = {
            ProjectDataState.EMPTY: "data.empty_body",
            ProjectDataState.CORRUPTED: "data.corrupted_body",
            ProjectDataState.WRONG_KEY: "data.wrong_key_body",
            ProjectDataState.PERMISSION_DENIED: "data.permission_body",
            ProjectDataState.UNAVAILABLE: "data.unavailable_body",
        }.get(self._data_state, "data.unavailable_body")
        recovery = not self._data_state.allows_writes
        self.data_state_banner.set_content(
            state=self._data_state.value,
            title=self._data_state_title(),
            body=text(body_key),
            retry_label=text("data.retry"),
            open_folder_label=text("action.open_project_folder"),
            recovery=recovery,
            detail=self._data_state_detail,
        )
        self.data_state_banner.show()

    def _verified_records(self, records: list[LicenseRecord]) -> list[LicenseRecord]:
        public_keys = self._verification_key_materials()
        return validate_record_signatures(
            records,
            public_keys,
            expected_issuer=self._settings.issuer,
            expected_audience=self._settings.audience,
        )

    def _verification_key_materials(self) -> tuple[bytes, ...]:
        paths = self._settings.trusted_public_key_paths or (
            self._settings.public_key_path,
        )
        try:
            return tuple(path.read_bytes() for path in paths)
        except OSError as exc:
            raise LicenseIssueError(
                f"Unable to read a trusted public key: {exc}"
            ) from exc

    def _refresh_view(self) -> None:
        self.table_model.set_records(self._records)
        statuses = [record.status() for record in self._records]
        active_count = statuses.count(LicenseStatus.ACTIVE)
        expiring_count = statuses.count(LicenseStatus.EXPIRING)
        expired_count = statuses.count(LicenseStatus.EXPIRED)
        invalid_count = statuses.count(LicenseStatus.INVALID)
        if self._data_state.allows_writes:
            self.total_card.set_value(len(self._records))
            self.active_card.set_value(active_count)
            self.expiring_card.set_value(expiring_count)
            self.expired_card.set_value(expired_count + invalid_count)
        else:
            for card in self.metric_cards:
                card.set_value("—")
        self._refresh_visible_count()
        self._selection_changed()

    def _refresh_visible_count(self) -> None:
        if not self._data_state.allows_writes:
            self.visible_label.setText(text("data.unavailable_short"))
            return
        self.visible_label.setText(
            text(
                "table.visible",
                visible=self.proxy_model.rowCount(),
                total=len(self._records),
            )
        )

    def _filter_status_changed(self, _value: object | None = None) -> None:
        status = self.status_combo.current_data()
        self.proxy_model.set_status(status if isinstance(status, LicenseStatus) else None)
        self._refresh_visible_count()

    def _selection_changed(self, _selected: QItemSelection | None = None, _deselected: QItemSelection | None = None) -> None:
        selected = self._selected_record() is not None
        self.edit_action.setEnabled(
            selected and not self._busy and self._data_state.allows_writes
        )
        self.revoke_action.setEnabled(
            selected and not self._busy and self._data_state.allows_writes
        )
        self.details_action.setEnabled(selected and not self._busy)

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
        menu = RoundedMenu(parent=self)
        menu.addAction(self.details_action)
        menu.addAction(self.edit_action)
        menu.addAction(self.revoke_action)
        menu.addSeparator()
        copy_hwid = menu.addAction(text("details.copy_hwid"))
        copy_token = menu.addAction(text("details.copy_token"))
        selected = menu.exec(self.table.viewport().mapToGlobal(position))
        if selected is copy_hwid:
            QApplication.clipboard().setText(record.hwid)
            self._notify(text("message.copied_hwid"))
        elif selected is copy_token:
            QApplication.clipboard().setText(record.token)
            self._notify(text("message.copied_token"))

    def _load_signing_key(self) -> Any | None:
        path = self._settings.signing_key_path
        if not path.exists():
            QMessageBox.warning(
                self,
                text("license.key_missing"),
                text("license.key_missing_body", path=path),
            )
            return None
        try:
            return load_private_key_file(path)
        except KeyPasswordRequiredError:
            password, accepted = QInputDialog.getText(
                self,
                text("license.unlock"),
                text("key.password"),
                QLineEdit.EchoMode.Password,
            )
            if not accepted:
                return None
            try:
                return load_private_key_file(path, password.encode("utf-8"))
            except LicenseIssueError as exc:
                QMessageBox.critical(self, text("license.key_missing"), str(exc))
                return None
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("license.key_missing"), str(exc))
            return None

    def _add_license(self) -> None:
        if self._busy:
            return
        if not self._ensure_data_writable():
            return
        dialog = LicenseEditorDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return
        self._apply_license_editor(dialog, None)

    def _edit_license(self) -> None:
        if self._busy:
            return
        if not self._ensure_data_writable():
            return
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
        if self._busy:
            return
        if not self._ensure_data_writable():
            return
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
                text("license.duplicate"),
                f"HWID: {collision.username or text('status.invalid')}",
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
                    text(
                        "license.key_mismatch",
                        project=self._settings.project_name,
                        error=new_record.parse_error,
                    )
                )
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("license.sign_failed"), str(exc))
            return
        transaction = RecordTransaction.upsert(
            self._records,
            new_record,
            original_hwid=original.hwid if original is not None else None,
        )
        if self._commit_records(transaction) is not None:
            self._notify(
                text(
                    "license.saved",
                    action=text(
                        "license.action_updated"
                        if original
                        else "license.action_created"
                    ),
                    name=username,
                )
            )

    def _revoke_license(self) -> None:
        if self._busy:
            return
        if not self._ensure_data_writable():
            return
        record = self._selected_record()
        if record is None:
            return
        answer = QMessageBox.question(
            self,
            text("license.revoke_title"),
            text("license.revoke_body", name=record.username or record.hwid),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        transaction = RecordTransaction.revoke(self._records, record.hwid)
        if self._commit_records(transaction) is not None:
            self._notify(text("license.revoked"))

    def _show_details(self) -> None:
        record = self._selected_record()
        if record is not None:
            RecordDetailsDialog(self, record).exec()

    def _merge_imported(self, imported: list[LicenseRecord], source_name: str) -> bool:
        if self._busy:
            return False
        if not self._ensure_data_writable():
            return False
        try:
            imported = self._verified_records(imported)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("import.failed"), str(exc))
            return False
        if not imported:
            self._notify(text("import.empty"), tone="info")
            return True
        box = QMessageBox(self)
        box.setWindowTitle(text("import.title"))
        box.setText(text("import.read", count=len(imported), source=source_name))
        box.setInformativeText(text("import.choice"))
        merge_button = box.addButton(
            text("import.merge"), QMessageBox.ButtonRole.AcceptRole
        )
        replace_button = box.addButton(
            text("import.replace"), QMessageBox.ButtonRole.DestructiveRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        if box.clickedButton() is merge_button:
            transaction = RecordTransaction.merge(self._records, imported)
        elif box.clickedButton() is replace_button:
            transaction = RecordTransaction.sorted_records(imported)
        else:
            return False
        if self._commit_records(transaction) is not None:
            self._notify(text("import.imported", count=len(imported)))
            return True
        return False

    def _import_signed(self) -> None:
        if self._busy:
            return
        if not self._ensure_data_writable():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, text("action.import_signed"), "", f"CSV (*.csv);;{text('common.all_files')}"
        )
        if not filename:
            return
        try:
            imported = parse_signed_csv(Path(filename).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, LicenseIssueError) as exc:
            QMessageBox.critical(self, text("import.failed"), str(exc))
            return
        self._merge_imported(imported, Path(filename).name)

    def _import_legacy(self) -> None:
        if self._busy:
            return
        if not self._ensure_data_writable():
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, text("action.import_legacy"), "", f"CSV (*.csv);;{text('common.all_files')}"
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
            QMessageBox.critical(self, text("import.legacy_failed"), str(exc))
            return
        completed = self._merge_imported(imported, Path(filename).name)
        if completed and result.skipped_expired_count:
            self._notify(
                text("import.skipped", count=result.skipped_expired_count),
                tone="info",
            )

    def _export_signed(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            text("action.export_signed"),
            "signed-licenses.csv",
            f"CSV (*.csv);;{text('common.all_files')}",
        )
        if not filename:
            return
        try:
            Path(filename).write_text(
                serialize_signed_csv(self._records), encoding="utf-8", newline=""
            )
        except OSError as exc:
            QMessageBox.critical(self, text("export.failed"), str(exc))
            return
        self._notify(text("export.done", count=len(self._records)))

    def _sheet_client(
        self,
        config: GoogleSheetsConfig | None = None,
    ) -> GoogleSheetsClient:
        return GoogleSheetsClient(config or self._settings.sheets_config())

    def _advance_local_revision(self) -> None:
        self._local_revision += 1

    def _sheet_target(self, config: GoogleSheetsConfig) -> SyncTarget:
        return SyncTarget(
            project_id=self._settings.project_id,
            spreadsheet_id=config.spreadsheet_id,
            worksheet=config.worksheet,
            kind=SyncTargetKind.GOOGLE_SHEET,
        )

    def _public_csv_target(self, url: str) -> SyncTarget:
        url_hash = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:20]
        return SyncTarget(
            project_id=self._settings.project_id,
            spreadsheet_id=f"public-{url_hash}",
            worksheet="csv",
            kind=SyncTargetKind.PUBLIC_CSV,
        )

    def _local_sync_context(self, target: SyncTarget) -> LocalSyncContext:
        return LocalSyncContext(
            target=target,
            revision=self._local_revision,
            digest=records_digest(self._records),
        )

    def _sync_context_is_current(self, context: LocalSyncContext) -> bool:
        if context.target.project_id != self._settings.project_id:
            return False
        if context.target.kind is SyncTargetKind.PUBLIC_CSV:
            target = self._public_csv_target(self._settings.public_csv_url)
        else:
            try:
                target = self._sheet_target(self._settings.sheets_config())
            except LicenseIssueError:
                return False
        return (
            target == context.target
            and self._local_revision == context.revision
            and records_digest(self._records) == context.digest
        )

    @staticmethod
    def _revision_document(revision: RemoteRevision | None) -> dict[str, object] | None:
        if revision is None:
            return None
        return {
            "generation": revision.generation,
            "digest": revision.digest,
            "sentinel_sheet_id": revision.sentinel_sheet_id,
            "target_sheet_id": revision.target_sheet_id,
            "operation_id": revision.operation_id,
        }

    def _store_remote_baseline(
        self,
        target: SyncTarget,
        snapshot: RemoteSnapshot,
    ) -> None:
        document = {
            "digest": snapshot.digest,
            "revision": self._revision_document(snapshot.revision),
        }
        self._qsettings.setValue(
            target.settings_key,
            json.dumps(document, separators=(",", ":"), sort_keys=True),
        )

    def _remote_baseline(
        self,
        target: SyncTarget,
    ) -> tuple[str, RemoteRevision | None] | None:
        raw = str(self._qsettings.value(target.settings_key, ""))
        if not raw:
            return None
        try:
            document = json.loads(raw)
            digest = document["digest"]
            revision_document = document.get("revision")
            if not isinstance(digest, str):
                return None
            if revision_document is None:
                return digest, None
            if not isinstance(revision_document, dict):
                return None
            revision = RemoteRevision(
                generation=int(revision_document["generation"]),
                digest=str(revision_document["digest"]),
                sentinel_sheet_id=int(revision_document["sentinel_sheet_id"]),
                target_sheet_id=int(revision_document["target_sheet_id"]),
                operation_id=str(revision_document.get("operation_id", "")),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        return digest, revision

    @staticmethod
    def _baseline_matches_snapshot(
        baseline: tuple[str, RemoteRevision | None] | None,
        snapshot: RemoteSnapshot,
    ) -> bool:
        return baseline == (snapshot.digest, snapshot.revision)

    def _observe_remote_preview(
        self,
        target: SyncTarget,
        snapshot: RemoteSnapshot,
    ) -> tuple[bool, bool]:
        """Record divergence as soon as a remote preview proves it exists."""
        baseline = self._remote_baseline(target)
        baseline_changed = baseline is not None and not (
            self._baseline_matches_snapshot(baseline, snapshot)
        )
        guard_mismatch = not snapshot.guard_matches_data
        if baseline_changed or guard_mismatch:
            self._set_sync_badge("dirty")
        return baseline_changed, guard_mismatch

    def _sync_diff_details(self, diff: SyncDiff) -> str:
        groups = (
            ("+", diff.added),
            ("~", diff.updated),
            ("−", diff.removed),
        )
        lines: list[str] = []
        for marker, records in groups:
            for record in records[:12]:
                identity = record.username or record.hwid
                lines.append(f"{marker} {identity} — {record.hwid}")
            if len(records) > 12:
                lines.append(f"{marker} … {len(records) - 12} more")
        return "\n".join(lines) or text("sheet.preview_no_changes")

    def _confirm_sync_preview(
        self,
        direction: SyncDirection,
        diff: SyncDiff,
        *,
        first_push: bool = False,
        baseline_changed: bool = False,
        guard_mismatch: bool = False,
    ) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning if diff.removed else QMessageBox.Icon.Question)
        box.setWindowTitle(
            text("sheet.push_title")
            if direction is SyncDirection.PUSH
            else text("sheet.pull_title")
        )
        box.setText(
            text(
                "sheet.preview_summary",
                added=len(diff.added),
                updated=len(diff.updated),
                removed=len(diff.removed),
                unchanged=len(diff.unchanged),
            )
        )
        warnings: list[str] = []
        if first_push:
            warnings.append(text("sheet.preview_first_push"))
        if baseline_changed:
            warnings.append(text("sheet.preview_remote_changed"))
        if guard_mismatch:
            warnings.append(text("sheet.preview_manual_change"))
        if warnings:
            box.setInformativeText("\n\n".join(warnings))
        box.setDetailedText(self._sync_diff_details(diff))
        confirm = box.addButton(
            text(
                "sheet.preview_publish"
                if direction is SyncDirection.PUSH
                else "sheet.preview_replace_local"
            ),
            (
                QMessageBox.ButtonRole.DestructiveRole
                if diff.removed or first_push
                else QMessageBox.ButtonRole.AcceptRole
            ),
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.exec()
        return box.clickedButton() is confirm

    def _verification_values(self) -> tuple[tuple[bytes, ...], str, str]:
        return (
            self._verification_key_materials(),
            self._settings.issuer,
            self._settings.audience,
        )

    @staticmethod
    def _verify_pulled_records(
        records: list[LicenseRecord] | tuple[LicenseRecord, ...],
        verification: tuple[tuple[bytes, ...], str, str],
    ) -> list[LicenseRecord]:
        public_keys, issuer, audience = verification
        verified = validate_record_signatures(
            list(records),
            public_keys,
            expected_issuer=issuer,
            expected_audience=audience,
        )
        invalid_count = sum(record.parse_error is not None for record in verified)
        if invalid_count:
            raise LicenseIssueError(
                f"Google Sheet contains {invalid_count} invalid or untrusted license rows."
            )
        return verified

    def _pull_sheet(self) -> None:
        if self._busy or not self._ensure_data_writable():
            return
        try:
            verification = self._verification_values()
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("sheet.sync_failed"), str(exc))
            return
        public_url = self._settings.public_csv_url.strip()
        config: GoogleSheetsConfig | None = None
        if public_url:
            target = self._public_csv_target(public_url)
        else:
            try:
                config = self._settings.sheets_config()
            except LicenseIssueError as exc:
                QMessageBox.warning(self, text("sheet.not_configured"), str(exc))
                return
            target = self._sheet_target(config)
        context = self._local_sync_context(target)
        local_snapshot = tuple(self._records)

        def operation() -> RemoteSnapshot | tuple[list[LicenseRecord], str]:
            if public_url:
                records = self._verify_pulled_records(
                    download_public_records(public_url), verification
                )
                return records, records_digest(records)
            assert config is not None
            remote = self._sheet_client(config).read_snapshot()
            verified = self._verify_pulled_records(remote.records, verification)
            return replace(remote, records=tuple(verified))

        def complete(result: Any) -> None:
            if not self._sync_context_is_current(context):
                self._set_sync_badge("dirty")
                self._notify(text("sheet.local_changed"), tone="info")
                return
            if isinstance(result, RemoteSnapshot):
                remote = result
                remote_records = remote.records
                baseline_changed, guard_mismatch = self._observe_remote_preview(
                    target, remote
                )
            else:
                records, _digest = result
                remote = None
                remote_records = tuple(records)
                baseline_changed = False
                guard_mismatch = False
            diff = build_sync_diff(remote_records, local_snapshot)
            if not self._confirm_sync_preview(
                SyncDirection.PULL,
                diff,
                baseline_changed=baseline_changed,
                guard_mismatch=guard_mismatch,
            ):
                return
            self._queue_after_operation(
                lambda: self._apply_pull_preview(
                    context=context,
                    reviewed=remote,
                    reviewed_public=(
                        (list(remote_records), records_digest(remote_records))
                        if remote is None
                        else None
                    ),
                    config=config,
                    public_url=public_url,
                    verification=verification,
                )
            )

        self._run_operation(text("sheet.pulling"), operation, complete)

    def _apply_pull_preview(
        self,
        *,
        context: LocalSyncContext,
        reviewed: RemoteSnapshot | None,
        reviewed_public: tuple[list[LicenseRecord], str] | None,
        config: GoogleSheetsConfig | None,
        public_url: str,
        verification: tuple[tuple[bytes, ...], str, str],
    ) -> None:
        if not self._sync_context_is_current(context):
            self._set_sync_badge("dirty")
            return
        self._set_sync_badge("dirty")

        def operation() -> RemoteSnapshot | tuple[list[LicenseRecord], str]:
            if public_url:
                records = self._verify_pulled_records(
                    download_public_records(public_url), verification
                )
                digest = records_digest(records)
                if reviewed_public is None or digest != reviewed_public[1]:
                    raise SheetConflictError(
                        "The public CSV changed after the sync preview."
                    )
                return records, digest
            if config is None or reviewed is None:
                raise RuntimeError("Missing authenticated Sheet preview.")
            current = self._sheet_client(config).read_snapshot()
            if (
                current.digest != reviewed.digest
                or current.revision != reviewed.revision
            ):
                raise SheetConflictError(
                    "The Google Sheet changed after the sync preview."
                )
            verified = self._verify_pulled_records(current.records, verification)
            return replace(current, records=tuple(verified))

        def complete(result: Any) -> None:
            if not self._sync_context_is_current(context):
                self._set_sync_badge("dirty")
                self._notify(text("sheet.local_changed"), tone="info")
                return
            if isinstance(result, RemoteSnapshot):
                records = list(result.records)
            else:
                records = list(result[0])
            transaction = RecordTransaction.sorted_records(records)
            committed = self._commit_records(transaction, allow_busy=True)
            if committed is None:
                return
            if isinstance(result, RemoteSnapshot):
                self._store_remote_baseline(context.target, result)
                if result.revision is not None and result.guard_matches_data:
                    self._mark_synced(text("sheet.pulled", count=len(committed)))
                else:
                    self._set_sync_badge("dirty")
                    self._notify(
                        text("sheet.pulled_unversioned", count=len(committed)),
                        tone="info",
                    )
            else:
                self._set_sync_badge("dirty")
                self._notify(text("sheet.pulled_public", count=len(committed)))

        self._run_operation(text("sheet.pulling"), operation, complete)

    def _push_sheet(self) -> None:
        if self._busy or not self._ensure_data_writable():
            return
        invalid_count = sum(
            record.status() is LicenseStatus.INVALID for record in self._records
        )
        if invalid_count:
            QMessageBox.critical(
                self,
                text("sheet.sync_failed"),
                text("sheet.invalid_rows", count=invalid_count),
            )
            return
        try:
            config = self._settings.sheets_config()
        except LicenseIssueError as exc:
            QMessageBox.warning(self, text("sheet.not_configured"), str(exc))
            self._show_settings()
            return
        if config.credentials_path is None:
            QMessageBox.warning(
                self,
                text("sheet.credentials_missing"),
                text("sheet.credentials_body"),
            )
            self._show_settings()
            return
        target = self._sheet_target(config)
        context = self._local_sync_context(target)
        local_snapshot = tuple(self._records)

        def operation() -> RemoteSnapshot:
            return self._sheet_client(config).read_snapshot()

        def complete(remote: Any) -> None:
            if not isinstance(remote, RemoteSnapshot):
                raise RuntimeError("Unexpected Sheet preview result.")
            if not self._sync_context_is_current(context):
                self._set_sync_badge("dirty")
                return
            baseline = self._remote_baseline(target)
            first_push = baseline is None and bool(remote.records)
            baseline_changed, guard_mismatch = self._observe_remote_preview(
                target, remote
            )
            diff = build_sync_diff(local_snapshot, remote.records)
            if not self._confirm_sync_preview(
                SyncDirection.PUSH,
                diff,
                first_push=first_push,
                baseline_changed=baseline_changed,
                guard_mismatch=guard_mismatch,
            ):
                return
            self._queue_after_operation(
                lambda: self._publish_push_preview(
                    context=context,
                    records=local_snapshot,
                    reviewed=remote,
                    config=config,
                )
            )

        self._run_operation(text("sheet.checking"), operation, complete)

    def _publish_push_preview(
        self,
        *,
        context: LocalSyncContext,
        records: tuple[LicenseRecord, ...],
        reviewed: RemoteSnapshot,
        config: GoogleSheetsConfig,
    ) -> None:
        if not self._sync_context_is_current(context):
            self._set_sync_badge("dirty")
            return
        self._set_sync_badge("dirty")

        def operation() -> RemoteSnapshot:
            return self._sheet_client(config).publish_records(
                records,
                expected_revision=reviewed.revision,
                expected_digest=reviewed.digest,
            )

        def complete(remote: Any) -> None:
            if not isinstance(remote, RemoteSnapshot):
                raise RuntimeError("Unexpected Sheet publish result.")
            self._store_remote_baseline(context.target, remote)
            if self._sync_context_is_current(context):
                self._mark_synced(text("sheet.synced", count=len(records)))
            else:
                self._set_sync_badge("dirty")
                self._notify(text("sheet.local_changed"), tone="info")

        self._run_operation(text("sheet.syncing"), operation, complete)

    def _format_sheet(self) -> None:
        if self._busy or not self._ensure_data_writable():
            return
        try:
            client = self._sheet_client()
        except LicenseIssueError as exc:
            QMessageBox.warning(self, text("sheet.not_configured"), str(exc))
            return
        self._run_operation(
            text("sheet.formatting"),
            lambda: client.format_worksheet(),
            lambda _result: self._notify(text("sheet.formatted")),
        )

    def _test_connection(self) -> None:
        try:
            client = self._sheet_client()
        except LicenseIssueError as exc:
            QMessageBox.warning(self, text("sheet.not_configured"), str(exc))
            return

        def complete(records: Any) -> None:
            self._notify(text("message.connection_ok", count=len(records)))

        self._run_operation(text("sheet.checking"), client.read_records, complete)

    def _open_sheet(self) -> None:
        try:
            url = self._settings.sheets_config().browser_url
        except LicenseIssueError as exc:
            QMessageBox.warning(self, text("sheet.not_configured"), str(exc))
            return
        QDesktopServices.openUrl(QUrl(url))

    def _show_settings(self) -> None:
        if self._busy:
            return
        dialog = SettingsDialog(
            self,
            self._settings,
            project_directory=self._project_store.project_directory(
                self._settings.project_id
            ),
            record_count=len(self._records),
        )
        with ModalBackdrop(self):
            result = dialog.exec()
        if result != dialog.DialogCode.Accepted:
            return
        try:
            values = dialog.commit(self._project_store)
        except LicenseIssueError as exc:
            QMessageBox.critical(self, text("settings.save_failed"), str(exc))
            return
        self._settings = values
        self._qsettings.setValue("projects/active", values.project_id)
        self._load_local(show_missing=True)
        self._set_project_identity()
        self._rebuild_project_menu()
        self._refresh_view()
        self._notify(text("message.saved_settings"))

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
                QMessageBox.critical(self, text("operation.complete_failed"), str(exc))

        def failed(error: str) -> None:
            QMessageBox.critical(self, text("message.operation_failed"), error)

        def finished() -> None:
            self._workers.discard(worker)
            worker.deleteLater()
            continuation = self._operation_continuation
            self._operation_continuation = None
            self._set_busy(False, text("message.ready"))
            if continuation is not None:
                continuation()

        worker.succeeded.connect(succeeded)
        worker.failed.connect(failed)
        worker.finished.connect(finished)
        worker.start()

    def _queue_after_operation(self, continuation: Callable[[], None]) -> None:
        if not self._busy:
            continuation()
            return
        if self._operation_continuation is not None:
            raise RuntimeError("A follow-up operation is already queued.")
        self._operation_continuation = continuation

    def _set_busy(self, busy: bool, _message: str) -> None:
        self._busy = busy
        self._update_action_states()
        self.table.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        elif QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self._selection_changed()

    def _update_action_states(self) -> None:
        if not hasattr(self, "new_action"):
            return
        idle = not self._busy
        writable = self._data_state.allows_writes
        for action in (
            self.new_action,
            self.pull_action,
            self.push_action,
            self.format_action,
            self.import_signed_action,
            self.import_legacy_action,
            self.resign_licenses_action,
            self.revoke_rotated_key_action,
        ):
            action.setEnabled(idle and writable)
        for action in (
            self.test_action,
            self.settings_action,
            self.new_project_action,
            self.import_project_keys_action,
            self.import_google_credentials_action,
            self.import_project_config_action,
            self.export_project_config_action,
            self.open_project_folder_action,
            self.open_sheet_action,
        ):
            action.setEnabled(idle)
        self.export_action.setEnabled(idle and writable)
        if hasattr(self, "project_combo"):
            self.project_combo.setEnabled(idle)
            self.primary_action_button.setEnabled(idle and writable)
            self.new_sidebar_button.setEnabled(idle and writable)
            self.settings_sidebar_button.setEnabled(idle)
            self.project_sidebar_menu.setEnabled(idle)
            self.data_state_banner.retry_button.setEnabled(idle)
            self.data_state_banner.open_folder_button.setEnabled(idle)

    def _refresh_sync_badge_from_baseline(self) -> None:
        try:
            target = self._sheet_target(self._settings.sheets_config())
        except LicenseIssueError:
            self._set_sync_badge("unsynced")
            return
        baseline = self._remote_baseline(target)
        if baseline is None:
            self._set_sync_badge("unsynced")
        elif (
            baseline[1] is not None
            and baseline[1].digest == baseline[0]
            and baseline[0] == records_digest(self._records)
        ):
            self._set_sync_badge("synced")
        else:
            self._set_sync_badge("dirty")

    def _mark_synced(self, message: str) -> None:
        self._set_sync_badge("synced")
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
                text("operation.running_title"),
                text("operation.running_body"),
            )
            event.ignore()
            return
        self._project_lease.release()
        event.accept()
