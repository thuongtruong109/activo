from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHeaderView,
    QMessageBox,
    QInputDialog,
    QPushButton,
    QToolBar,
    QToolButton,
    QWidget,
)

from issue_license import LicenseIssueError
from license_admin.app_identity import (
    APP_ICON_PATH,
    APP_LOGO_PATH,
    SUPPORT_EMAIL,
    app_icon,
    configure_application_identity,
)
from license_admin.dialogs import (
    LicenseEditorDialog,
    RecordDetailsDialog,
    SettingsDialog,
)
from license_admin.data_recovery import ProjectDataState
from license_admin.domain import LicenseRecord, records_digest
from license_admin.flag_icons import FLAG_CDN_TEMPLATE, FlagIconLoader
from license_admin.google_sheets import (
    GoogleSheetsConfig,
    RemoteRevision,
    RemoteSnapshot,
)
from license_admin.key_import_dialog import KeyImportDialog
from license_admin.key_store import import_key_pair
from license_admin.main_window import LicenseAdminWindow
from license_admin.icons import ICON_SPRITE_PATH, svg_icon
from license_admin.information_dialogs import (
    AboutDialog,
    InformationDialog,
    PolicyDialog,
    TermsOfServiceDialog,
)
from license_admin.localization import DEFAULT_LANGUAGE, LANGUAGES, set_language
from license_admin.modal_backdrop import ModalBackdrop
from license_admin.popover import RoundedMenu
from license_admin.project_lock import ProjectLease
from license_admin.qt_models import LicenseFilterModel, LicenseTableModel
from license_admin.record_transaction import RecordTransaction
from license_admin.service_account_import_dialog import ServiceAccountImportDialog
from license_admin.service_account_store import import_service_account
from license_admin.settings import ProjectStore
from license_admin.storage import LicenseRepository
from license_admin.sync_models import build_sync_diff
from license_admin.theme import ADMIN_STYLESHEET, stylesheet_for
from license_admin.ui_metrics import CONTROL_HEIGHT
from license_admin.window_chrome import DraggableFrame
from workspace_temp import workspace_temp_dir


class LicenseAdminUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        existing = QApplication.instance()
        cls.app = existing if isinstance(existing, QApplication) else QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(ADMIN_STYLESHEET)
        cls.temporary_directory = workspace_temp_dir()
        root = Path(cls.temporary_directory.name)
        cls.project_store = ProjectStore(root / "projects")
        profile = cls.project_store.ensure_default()
        cls.private_key = rsa.generate_private_key(
            public_exponent=65_537,
            key_size=2_048,
        )
        profile.signing_key_path.write_bytes(
            cls.private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        profile.public_key_path.write_bytes(
            cls.private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        cls.qsettings = QSettings(
            str(root / "settings.ini"),
            QSettings.Format.IniFormat,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.qsettings.clear()
        cls.qsettings.sync()
        cls.temporary_directory.cleanup()

    def create_window(self) -> LicenseAdminWindow:
        return LicenseAdminWindow(
            project_store=self.project_store,
            qsettings=self.qsettings,
        )

    def test_vertical_header_displays_row_numbers(self) -> None:
        model = LicenseTableModel()

        self.assertEqual(
            model.headerData(
                0,
                Qt.Orientation.Vertical,
                int(Qt.ItemDataRole.DisplayRole),
            ),
            1,
        )
        self.assertEqual(
            model.headerData(
                11,
                Qt.Orientation.Vertical,
                int(Qt.ItemDataRole.DisplayRole),
            ),
            12,
        )

    def test_search_uses_accent_insensitive_contains_matching(self) -> None:
        model = LicenseTableModel()
        model.set_records(
            [LicenseRecord(hwid="abc12345", token="token", username="Hải Đệ")]
        )
        proxy = LicenseFilterModel()
        proxy.setSourceModel(model)

        proxy.set_query("de")
        self.assertEqual(proxy.rowCount(), 1)

        proxy.set_query("ai d")
        self.assertEqual(proxy.rowCount(), 1)

        proxy.set_query("khong co")
        self.assertEqual(proxy.rowCount(), 0)

    def test_success_notification_uses_toast_without_modal(self) -> None:
        window = self.create_window()
        try:
            with (
                patch.object(window.toast, "show_message") as show_toast,
                patch.object(QMessageBox, "information") as show_modal,
            ):
                window._notify("Đã tải dữ liệu")

            show_toast.assert_called_once_with("Đã tải dữ liệu", tone="success")
            show_modal.assert_not_called()
        finally:
            window.close()

    def test_compact_layout_has_no_action_toolbar(self) -> None:
        window = self.create_window()
        try:
            window.resize(980, 640)
            window.show()
            self.app.processEvents()
            self.assertEqual(window.findChildren(QToolBar), [])
            self.assertFalse(window.table.verticalHeader().isHidden())
            self.assertTrue(window.statusBar().isHidden())
            self.assertTrue(window.menuBar().isHidden())
            self.assertTrue(
                bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
            )
            self.assertFalse(window.mask().isEmpty())
            self.assertFalse(window.mask().contains(QPoint(0, 0)))
            self.assertTrue(
                window.mask().contains(window.rect().center())
            )
            window.showMaximized()
            self.app.processEvents()
            self.assertTrue(window.mask().isEmpty())
            window.showNormal()
            window.resize(980, 640)
            self.app.processEvents()
            self.assertFalse(window.mask().isEmpty())
            self.assertEqual(window.sidebar.width(), 220)
            self.assertEqual(window.top_bar.height(), 58)
            self.assertEqual(window.sidebar_header.height(), window.top_bar.height())
            self.assertIs(window.sidebar_header.parentWidget(), window.sidebar)
            self.assertIs(window.window_controls.parentWidget(), window.top_bar)
            self.assertEqual(window.window_controls.close_button.objectName(), "trafficClose")
            self.assertEqual(
                window.window_controls.minimize_button.objectName(),
                "trafficMinimize",
            )
            self.assertEqual(
                window.window_controls.maximize_button.objectName(),
                "trafficMaximize",
            )
            self.assertLess(
                window.window_controls.minimize_button.geometry().left(),
                window.window_controls.maximize_button.geometry().left(),
            )
            self.assertLess(
                window.window_controls.maximize_button.geometry().left(),
                window.window_controls.close_button.geometry().left(),
            )
            content_margins = window.content_surface.layout().contentsMargins()
            self.assertEqual(
                (
                    content_margins.left(),
                    content_margins.top(),
                    content_margins.right(),
                    content_margins.bottom(),
                ),
                (12, 10, 12, 12),
            )
            self.assertIs(window.project_combo.parentWidget(), window.top_bar)
            self.assertIs(window.language_selector.parentWidget(), window.top_bar)
            self.assertIs(window.header_brand.parentWidget(), window.sidebar_header)
            self.assertIs(window.sidebar_toggle.parentWidget(), window.sidebar_header)
            self.assertGreater(
                window.sidebar_toggle.geometry().left()
                - window.header_brand.geometry().right(),
                20,
            )
            self.assertIs(window.table_filters.parentWidget(), window.table_header)
            self.assertIs(window.search_edit.parentWidget(), window.table_filters)
            self.assertIs(window.status_combo.parentWidget(), window.table_filters)
            self.assertIs(window.primary_action_button.parentWidget(), window.top_bar)
            self.assertEqual(window.primary_action_button.width(), 128)
            self.assertEqual(
                {
                    window.project_combo.height(),
                    window.primary_action_button.height(),
                    window.language_selector.height(),
                    window.search_edit.height(),
                    window.status_combo.height(),
                    window.theme_toggle.height(),
                },
                {CONTROL_HEIGHT},
            )
            self.assertFalse(hasattr(window, "project_label"))
            self.assertFalse(hasattr(window, "project_identity"))
            self.assertFalse(hasattr(window, "nav_label"))
            self.assertEqual(window.brand_mark.size().width(), 24)
            self.assertFalse(window.brand_mark.pixmap().isNull())
            self.assertIsNone(window.findChild(QPushButton, "quitButton"))
            self.assertFalse(hasattr(window, "page_title"))
            self.assertFalse(hasattr(window, "page_description"))
            self.assertFalse(hasattr(window, "status_panel"))
            self.assertFalse(hasattr(window, "top_bar_title"))
            self.assertFalse(hasattr(window, "table_title"))
            self.assertFalse(hasattr(window, "table_subtitle"))
            self.assertEqual(
                window.table.horizontalHeader().sectionResizeMode(2),
                QHeaderView.ResizeMode.ResizeToContents,
            )
            self.assertEqual(
                window.table.horizontalHeader().sectionResizeMode(3),
                QHeaderView.ResizeMode.ResizeToContents,
            )

            sidebar_buttons = (
                window.overview_button,
                window.new_sidebar_button,
                window.license_sidebar_menu,
                window.sheet_sidebar_menu,
                window.data_sidebar_menu,
                window.settings_sidebar_button,
                window.project_sidebar_menu,
            )
            self.assertEqual({button.height() for button in sidebar_buttons}, {42})
            self.assertTrue(window.overview_button._active_indicator.isVisible())
            self.assertEqual(
                window.overview_button._active_indicator.geometry().getRect(),
                (0, 12, 3, 18),
            )

            window.sidebar_toggle.click()
            self.app.processEvents()
            self.assertEqual(window.sidebar.width(), 72)
            self.assertTrue(window.header_brand.isHidden())
            self.assertFalse(window.brand_mark.isVisible())
            self.assertEqual(window.overview_button.text(), "")
            self.assertEqual(window.project_sidebar_menu.text(), "")
            self.assertTrue(window.project_sidebar_menu._chevron.isHidden())
            self.assertEqual(
                window.project_sidebar_menu.toolButtonStyle(),
                Qt.ToolButtonStyle.ToolButtonIconOnly,
            )

            window.sidebar_toggle.click()
            self.app.processEvents()
            self.assertEqual(window.sidebar.width(), 220)
            self.assertFalse(window.header_brand.isHidden())
            self.assertTrue(window.brand_mark.isVisible())
            self.assertEqual(window.overview_button.text(), "Overview")
            self.assertEqual(window.project_sidebar_menu.text(), "Manage projects")
        finally:
            window.close()

    def test_header_information_buttons_open_user_facing_documents(self) -> None:
        window = self.create_window()
        try:
            for button, tooltip in (
                (window.about_button, "About"),
                (window.policy_button, "Policy"),
                (window.terms_button, "Terms of service"),
            ):
                self.assertIs(button.parentWidget(), window.header_info_group)
                self.assertEqual(button.size().height(), CONTROL_HEIGHT - 2)
                self.assertEqual(button.toolTip(), tooltip)
                self.assertFalse(button.icon().isNull())
            self.assertIs(window.header_info_group.parentWidget(), window.top_bar)

            about = AboutDialog(window)
            policy = PolicyDialog(window)
            terms = TermsOfServiceDialog(window)
            for dialog in (about, policy, terms):
                self.assertEqual(dialog.objectName(), "informationDialog")
                self.assertIsNotNone(dialog.findChild(QFrame, "informationSurface"))
            self.assertIsNotNone(about.contact_link)
            assert about.contact_link is not None
            self.assertIn(SUPPORT_EMAIL, about.contact_link.text())
            self.assertTrue(about.contact_link.openExternalLinks())
            self.assertIsNone(policy.contact_link)
            self.assertIsNone(terms.contact_link)

            about_copy = " ".join(
                label.text() for label in about.section_bodies
            ).casefold()
            for implementation_detail in (
                "python",
                "pyside",
                "qt",
                "cryptography",
                "technology stack",
            ):
                self.assertNotIn(implementation_detail, about_copy)

            self.assertGreaterEqual(len(policy.section_titles), 5)
            self.assertGreaterEqual(len(terms.section_titles), 5)

            with patch.object(InformationDialog, "exec", return_value=0) as show:
                window.about_button.click()
                window.policy_button.click()
                window.terms_button.click()
            self.assertEqual(show.call_count, 3)
            about.close()
            policy.close()
            terms.close()
        finally:
            window.close()

    def test_project_menu_exposes_key_import_and_settings_dialog_reuses_it(self) -> None:
        window = self.create_window()
        try:
            project_ids = {
                profile.project_id for profile in self.project_store.list_profiles()
            }
            self.assertFalse(
                any(
                    action.data() in project_ids
                    for action in window.project_menu.actions()
                )
            )
            self.assertIs(window.project_menu.actions()[0], window.new_project_action)
            self.assertIn(window.import_project_keys_action, window.project_menu.actions())
            self.assertIn(
                window.import_google_credentials_action,
                window.project_menu.actions(),
            )
            self.assertIn(
                window.import_project_config_action,
                window.project_menu.actions(),
            )
            self.assertIn(
                window.export_project_config_action,
                window.project_menu.actions(),
            )
            settings = SettingsDialog(
                window,
                window._settings,
                project_directory=self.project_store.project_directory(
                    window._settings.project_id
                ),
                record_count=0,
            )
            try:
                self.assertEqual(
                    settings.import_keys_button.objectName(),
                    "importProjectKeys",
                )
                self.assertEqual(
                    settings.import_credentials_button.objectName(),
                    "importProjectCredentials",
                )
                self.assertTrue(
                    bool(
                        settings.windowFlags()
                        & Qt.WindowType.FramelessWindowHint
                    )
                )
                self.assertEqual(settings.settings_tab_header.tab_bar.count(), 3)
                self.assertEqual(settings.settings_pages.count(), 3)
                self.assertEqual(
                    settings.settings_tab_header.close_button.objectName(),
                    "modalCloseButton",
                )
                self.assertNotIsInstance(
                    settings.settings_tab_header,
                    DraggableFrame,
                )
                settings.show()
                self.app.processEvents()
                self.assertEqual(
                    {
                        settings.project_name_edit.height(),
                        settings.project_id_edit.height(),
                        settings.local_csv_edit.height(),
                        settings.signing_key_edit.height(),
                        settings.public_key_edit.height(),
                        settings.import_keys_button.height(),
                        settings.import_credentials_button.height(),
                    },
                    {CONTROL_HEIGHT},
                )
                self.assertFalse(settings.mask().isEmpty())
                self.assertFalse(settings.mask().contains(QPoint(0, 0)))
                self.assertTrue(
                    settings.mask().contains(settings.rect().center())
                )
                settings.settings_tab_header.tab_bar.setCurrentIndex(2)
                self.assertEqual(settings.settings_pages.currentIndex(), 2)
            finally:
                settings.close()
        finally:
            window.close()

    def test_cancel_settings_discards_key_and_credential_imports(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store = ProjectStore(root / "projects")
            profile = store.ensure_default()
            project_directory = store.project_directory(profile.project_id)

            def write_pair(stem: str) -> tuple[Path, Path]:
                key = rsa.generate_private_key(
                    public_exponent=65_537,
                    key_size=2_048,
                )
                private_path = root / f"{stem}-private.pem"
                public_path = root / f"{stem}-public.pem"
                private_path.write_bytes(
                    key.private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                )
                public_path.write_bytes(
                    key.public_key().public_bytes(
                        serialization.Encoding.PEM,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                )
                return private_path, public_path

            def write_credential(name: str, email: str) -> Path:
                key = rsa.generate_private_key(
                    public_exponent=65_537,
                    key_size=2_048,
                )
                path = root / name
                path.write_text(
                    json.dumps(
                        {
                            "type": "service_account",
                            "project_id": "ui-transaction-test",
                            "private_key": key.private_bytes(
                                serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption(),
                            ).decode("ascii"),
                            "client_email": email,
                            "token_uri": "https://oauth2.googleapis.com/token",
                        }
                    ),
                    encoding="utf-8",
                )
                return path

            old_pair = import_key_pair(*write_pair("old"), project_directory)
            old_credential = import_service_account(
                write_credential("old-service.json", "old@example.test"),
                project_directory,
            )
            profile = replace(
                profile,
                signing_key_path=old_pair.private_key_path,
                public_key_path=old_pair.public_key_path,
                service_account_path=old_credential.path,
            )
            store.save(profile)
            original_profile = store.profile_path(profile.project_id).read_bytes()
            original_private = old_pair.private_key_path.read_bytes()
            original_public = old_pair.public_key_path.read_bytes()
            original_credential = old_credential.path.read_bytes()
            new_private, new_public = write_pair("new")
            new_credential = write_credential(
                "new-service.json",
                "new@example.test",
            )
            parent = QWidget()
            dialog = SettingsDialog(
                parent,
                profile,
                project_directory=project_directory,
                record_count=4,
            )

            def run_key_import(key_dialog: KeyImportDialog) -> int:
                key_dialog.private_key_edit.setText(str(new_private))
                key_dialog.public_key_edit.setText(str(new_public))
                with patch.object(
                    QMessageBox,
                    "warning",
                    return_value=QMessageBox.StandardButton.Yes,
                ):
                    key_dialog._validate_and_import()
                return key_dialog.result()

            def run_credential_import(
                credential_dialog: ServiceAccountImportDialog,
            ) -> int:
                credential_dialog.source_edit.setText(str(new_credential))
                with patch.object(
                    QMessageBox,
                    "warning",
                    return_value=QMessageBox.StandardButton.Yes,
                ):
                    credential_dialog._validate_and_import()
                return credential_dialog.result()

            try:
                with patch.object(KeyImportDialog, "exec", run_key_import):
                    dialog._import_keys()
                with patch.object(
                    ServiceAccountImportDialog,
                    "exec",
                    run_credential_import,
                ):
                    dialog._import_credentials()

                staging_directories = list(
                    project_directory.glob(".settings-staging-*")
                )
                self.assertEqual(len(staging_directories), 1)
                self.assertIn(
                    ".settings-assets",
                    dialog.signing_key_edit.text(),
                )
                self.assertIn(
                    ".settings-assets",
                    dialog.credentials_edit.text(),
                )
                self.assertEqual(old_pair.private_key_path.read_bytes(), original_private)
                self.assertEqual(old_pair.public_key_path.read_bytes(), original_public)
                self.assertEqual(old_credential.path.read_bytes(), original_credential)
                self.assertFalse((project_directory / ".settings-assets").exists())

                dialog.reject()

                self.assertFalse(staging_directories[0].exists())
                self.assertEqual(
                    store.profile_path(profile.project_id).read_bytes(),
                    original_profile,
                )
                self.assertEqual(old_pair.private_key_path.read_bytes(), original_private)
                self.assertEqual(old_pair.public_key_path.read_bytes(), original_public)
                self.assertEqual(old_credential.path.read_bytes(), original_credential)
                self.assertFalse((project_directory / ".settings-assets").exists())
            finally:
                dialog.close()
                parent.close()

    def test_corrupted_data_opens_in_recovery_mode_without_overwrite(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store = ProjectStore(root / "projects")
            profile = store.ensure_default()
            corrupted = "hwid,token\nmissing-token\n"
            profile.local_csv_path.write_text(corrupted, encoding="utf-8")
            qsettings = QSettings(
                str(root / "recovery-settings.ini"),
                QSettings.Format.IniFormat,
            )
            window = LicenseAdminWindow(project_store=store, qsettings=qsettings)
            try:
                self.assertEqual(window._data_state, ProjectDataState.CORRUPTED)
                self.assertFalse(window.data_state_banner.isHidden())
                self.assertIn("Recovery", window.data_state_banner.title_label.text())
                self.assertEqual(window.total_card.value_label.text(), "—")
                self.assertFalse(window.new_action.isEnabled())
                self.assertFalse(window.import_signed_action.isEnabled())
                self.assertFalse(window.pull_action.isEnabled())
                self.assertFalse(window.push_action.isEnabled())
                self.assertTrue(window.settings_action.isEnabled())
                with patch.object(QMessageBox, "warning") as warning:
                    self.assertIsNone(
                        window._commit_records(
                            RecordTransaction.from_records(window._records)
                        )
                    )
                warning.assert_called_once()
                self.assertEqual(
                    profile.local_csv_path.read_text(encoding="utf-8"),
                    corrupted,
                )
                profile.local_csv_path.write_text("hwid,token\n", encoding="utf-8")
                window._retry_local_data()
                self.assertEqual(window._data_state, ProjectDataState.EMPTY)
                self.assertTrue(window.new_action.isEnabled())
                self.assertTrue(window.import_signed_action.isEnabled())
            finally:
                window.close()
                qsettings.clear()

    def test_failed_record_commit_preserves_memory_table_and_sync_state(self) -> None:
        window = self.create_window()
        try:
            original = [
                LicenseRecord(
                    hwid="original-hwid",
                    token="original-token",
                    username="Original",
                )
            ]
            candidate = [
                LicenseRecord(
                    hwid="candidate-hwid",
                    token="candidate-token",
                    username="Candidate",
                )
            ]
            window._records = original
            window._data_state = ProjectDataState.READY
            window._data_state_detail = "unchanged detail"
            window._set_sync_badge("synced")
            window._refresh_view()
            revision_before = window._local_revision
            data_path = window._settings.local_csv_path
            existed_before = data_path.exists()
            bytes_before = data_path.read_bytes() if existed_before else None

            def fail_save(
                _repository: object,
                records: Iterable[LicenseRecord],
            ) -> None:
                self.assertIs(window._records, original)
                self.assertEqual(window.table_model.records, original)
                self.assertEqual(tuple(records), tuple(candidate))
                self.assertEqual(window._sync_badge_state, "synced")
                raise LicenseIssueError("simulated write failure")

            with (
                patch.object(
                    LicenseRepository,
                    "save",
                    autospec=True,
                    side_effect=fail_save,
                ),
                patch.object(QMessageBox, "critical") as critical,
                patch.object(window.toast, "show_message") as toast,
            ):
                committed = window._commit_records(
                    RecordTransaction.from_records(candidate)
                )

            self.assertIsNone(committed)
            self.assertIs(window._records, original)
            self.assertEqual(window.table_model.records, original)
            self.assertEqual(window._data_state, ProjectDataState.READY)
            self.assertEqual(window._data_state_detail, "unchanged detail")
            self.assertEqual(window._sync_badge_state, "synced")
            self.assertEqual(window._local_revision, revision_before)
            self.assertEqual(data_path.exists(), existed_before)
            if existed_before:
                self.assertEqual(data_path.read_bytes(), bytes_before)
            critical.assert_called_once()
            toast.assert_not_called()
        finally:
            window.close()

    def test_successful_record_commit_swaps_state_only_after_persistence(self) -> None:
        window = self.create_window()
        try:
            original = [
                LicenseRecord(
                    hwid="original-hwid",
                    token="original-token",
                    username="Original",
                )
            ]
            candidate = [
                LicenseRecord(
                    hwid="candidate-hwid",
                    token="candidate-token",
                    username="Candidate",
                )
            ]
            window._records = original
            window._data_state = ProjectDataState.READY
            window._set_sync_badge("synced")
            window._refresh_view()
            revision_before = window._local_revision

            def save(
                _repository: object,
                records: Iterable[LicenseRecord],
            ) -> None:
                self.assertIs(window._records, original)
                self.assertEqual(window.table_model.records, original)
                self.assertEqual(tuple(records), tuple(candidate))
                self.assertEqual(window._sync_badge_state, "synced")

            with patch.object(
                LicenseRepository,
                "save",
                autospec=True,
                side_effect=save,
            ) as persist:
                committed = window._commit_records(
                    RecordTransaction.from_records(candidate)
                )

            self.assertEqual(committed, tuple(candidate))
            persist.assert_called_once()
            self.assertIsNot(window._records, candidate)
            self.assertEqual(window._records, candidate)
            self.assertEqual(window.table_model.records, candidate)
            self.assertEqual(window._data_state, ProjectDataState.READY)
            self.assertEqual(window._sync_badge_state, "dirty")
            self.assertEqual(window._local_revision, revision_before + 1)
        finally:
            window.close()

    def test_busy_state_disables_every_mutating_entry_point(self) -> None:
        window = self.create_window()
        try:
            window._set_busy(True, "syncing")

            for action in (
                window.new_action,
                window.edit_action,
                window.revoke_action,
                window.pull_action,
                window.push_action,
                window.format_action,
                window.import_signed_action,
                window.import_legacy_action,
                window.import_project_keys_action,
                window.import_google_credentials_action,
                window.import_project_config_action,
                window.settings_action,
                window.new_project_action,
            ):
                self.assertFalse(action.isEnabled())
            self.assertFalse(window.project_combo.isEnabled())
            self.assertFalse(window.settings_sidebar_button.isEnabled())
            self.assertFalse(window.project_sidebar_menu.isEnabled())
            self.assertFalse(window.table.isEnabled())

            with (
                patch.object(QInputDialog, "getText") as project_prompt,
                patch.object(QFileDialog, "getOpenFileName") as file_prompt,
                patch.object(LicenseEditorDialog, "exec") as editor,
                patch.object(window, "_run_operation") as run_operation,
            ):
                window._create_project()
                window._import_project_config()
                window._import_signed()
                window._import_legacy()
                window._add_license()
                window._pull_sheet()
                window._push_sheet()
                window._format_sheet()

            project_prompt.assert_not_called()
            file_prompt.assert_not_called()
            editor.assert_not_called()
            run_operation.assert_not_called()
        finally:
            window._set_busy(False, "ready")
            window.close()

    def test_sync_diff_preview_never_exposes_license_tokens(self) -> None:
        window = self.create_window()
        try:
            secret_token = "secret.header.payload.signature"
            local = LicenseRecord(
                hwid="preview-hwid",
                token=secret_token,
                username="Preview User",
            )
            diff = build_sync_diff([local], [])

            details = window._sync_diff_details(diff)

            self.assertIn("Preview User", details)
            self.assertIn("preview-hwid", details)
            self.assertNotIn(secret_token, details)
        finally:
            window.close()

    def test_second_window_for_same_project_fails_closed(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store = ProjectStore(root / "projects")
            store.ensure_default()
            first_settings = QSettings(
                str(root / "first.ini"),
                QSettings.Format.IniFormat,
            )
            second_settings = QSettings(
                str(root / "second.ini"),
                QSettings.Format.IniFormat,
            )
            first = LicenseAdminWindow(
                project_store=store,
                qsettings=first_settings,
            )
            try:
                with self.assertRaisesRegex(LicenseIssueError, "already open"):
                    LicenseAdminWindow(
                        project_store=store,
                        qsettings=second_settings,
                    )
            finally:
                first.close()

            replacement = LicenseAdminWindow(
                project_store=store,
                qsettings=second_settings,
            )
            replacement.close()
            first_settings.clear()
            first_settings.sync()
            second_settings.clear()
            second_settings.sync()

    def test_stale_push_completion_never_marks_newer_local_state_synced(self) -> None:
        window = self.create_window()
        try:
            config = GoogleSheetsConfig(
                spreadsheet_id="a" * 30,
                worksheet="Signed",
                credentials_path=window._settings.service_account_path,
            )
            window._settings = replace(
                window._settings,
                spreadsheet_id=config.spreadsheet_id,
                worksheet=config.worksheet,
            )
            target = window._sheet_target(config)
            context = window._local_sync_context(target)
            records = tuple(window._records)
            digest = records_digest(records)
            remote = RemoteSnapshot(
                records=records,
                digest=digest,
                revision=RemoteRevision(1, digest, 91, 42, "operation"),
                target_sheet_id=42,
                target_row_count=1_000,
            )

            def finish_with_newer_local_revision(
                _message: str,
                _operation: object,
                on_success: object,
            ) -> None:
                window._advance_local_revision()
                on_success(remote)  # type: ignore[operator]

            with (
                patch.object(
                    window,
                    "_run_operation",
                    side_effect=finish_with_newer_local_revision,
                ),
                patch.object(window, "_mark_synced") as mark_synced,
                patch.object(window, "_notify") as notify,
            ):
                window._publish_push_preview(
                    context=context,
                    records=records,
                    reviewed=remote,
                    config=config,
                )

            mark_synced.assert_not_called()
            self.assertEqual(window._sync_badge_state, "dirty")
            notify.assert_called_once()
        finally:
            window.close()

    def test_unchanged_push_still_uses_revision_guarded_publish(self) -> None:
        window = self.create_window()
        try:
            config = GoogleSheetsConfig(
                spreadsheet_id="a" * 30,
                worksheet="Signed",
                credentials_path=Path("service-account.json"),
            )
            window._settings = replace(
                window._settings,
                spreadsheet_id=config.spreadsheet_id,
                worksheet=config.worksheet,
                service_account_path=config.credentials_path,
            )
            digest = records_digest(window._records)
            remote = RemoteSnapshot(
                records=tuple(window._records),
                digest=digest,
                revision=RemoteRevision(1, digest, 91, 42, "reviewed"),
                target_sheet_id=42,
                target_row_count=1_000,
            )

            with (
                patch.object(window, "_run_operation") as run_operation,
                patch.object(
                    window,
                    "_confirm_sync_preview",
                    return_value=True,
                ),
                patch.object(window, "_queue_after_operation") as queue,
                patch.object(window, "_mark_synced") as mark_synced,
            ):
                window._push_sheet()
                preview_complete = run_operation.call_args.args[2]
                preview_complete(remote)

            queue.assert_called_once()
            mark_synced.assert_not_called()
        finally:
            window.close()

    def test_cancelled_preview_keeps_observed_remote_divergence_dirty(self) -> None:
        window = self.create_window()
        try:
            config = GoogleSheetsConfig(
                spreadsheet_id="a" * 30,
                worksheet="Signed",
                credentials_path=Path("service-account.json"),
            )
            window._settings = replace(
                window._settings,
                spreadsheet_id=config.spreadsheet_id,
                worksheet=config.worksheet,
                service_account_path=config.credentials_path,
            )
            target = window._sheet_target(config)
            baseline_digest = records_digest(window._records)
            baseline = RemoteSnapshot(
                records=tuple(window._records),
                digest=baseline_digest,
                revision=RemoteRevision(1, baseline_digest, 91, 42, "baseline"),
                target_sheet_id=42,
                target_row_count=1_000,
            )
            changed_record = LicenseRecord("remote-change", "remote-token")
            changed_digest = records_digest([changed_record])
            changed = RemoteSnapshot(
                records=(changed_record,),
                digest=changed_digest,
                revision=RemoteRevision(2, changed_digest, 92, 42, "changed"),
                target_sheet_id=42,
                target_row_count=1_000,
            )
            window._store_remote_baseline(target, baseline)
            window._set_sync_badge("synced")

            with (
                patch.object(window, "_run_operation") as run_operation,
                patch.object(
                    window,
                    "_confirm_sync_preview",
                    return_value=False,
                ),
                patch.object(window, "_queue_after_operation") as queue,
            ):
                window._push_sheet()
                preview_complete = run_operation.call_args.args[2]
                preview_complete(changed)

            self.assertEqual(window._sync_badge_state, "dirty")
            queue.assert_not_called()
        finally:
            window.close()

    def test_google_sheet_id_with_public_prefix_is_not_misclassified(self) -> None:
        window = self.create_window()
        try:
            config = GoogleSheetsConfig(
                spreadsheet_id="public-" + "a" * 24,
                worksheet="Signed",
                credentials_path=Path("service-account.json"),
            )
            window._settings = replace(
                window._settings,
                spreadsheet_id=config.spreadsheet_id,
                worksheet=config.worksheet,
                service_account_path=config.credentials_path,
                public_csv_url="https://example.invalid/licenses.csv",
            )
            context = window._local_sync_context(window._sheet_target(config))

            self.assertTrue(window._sync_context_is_current(context))
        finally:
            window.close()

    def test_project_switch_keeps_current_lease_when_destination_is_locked(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store = ProjectStore(root / "projects")
            first_profile = store.ensure_default()
            second_profile = store.create("Locked Destination")
            settings = QSettings(
                str(root / "settings.ini"),
                QSettings.Format.IniFormat,
            )
            settings.setValue("projects/active", first_profile.project_id)
            destination_lease = ProjectLease.acquire(
                store.project_directory(second_profile.project_id)
            )
            window = LicenseAdminWindow(project_store=store, qsettings=settings)
            try:
                window.project_combo.set_current_data(second_profile.project_id)
                with patch.object(QMessageBox, "critical") as critical:
                    window._switch_project(second_profile.project_id)
                critical.assert_called_once()
                self.assertEqual(window._settings.project_id, first_profile.project_id)
                self.assertEqual(
                    window.project_combo.currentData(),
                    first_profile.project_id,
                )
                self.assertTrue(window._project_lease.held)

                destination_lease.release()
                window._switch_project(second_profile.project_id)
                self.assertEqual(window._settings.project_id, second_profile.project_id)

                released_source = ProjectLease.acquire(
                    store.project_directory(first_profile.project_id)
                )
                released_source.release()
            finally:
                destination_lease.release()
                window.close()
                settings.clear()
                settings.sync()

    def test_table_filters_fit_and_clear_button_is_centered(self) -> None:
        window = self.create_window()
        try:
            window.resize(980, 640)
            window.show()
            window.search_edit.setText("de")
            self.app.processEvents()

            self.assertLessEqual(
                window.project_combo.geometry().right(),
                window.top_bar.rect().right(),
            )
            self.assertLessEqual(
                window.status_combo.geometry().right(),
                window.table_filters.rect().right(),
            )
            self.assertLessEqual(
                window.primary_action_button.geometry().right(),
                window.top_bar.rect().right(),
            )
            self.assertGreater(window.search_edit.width(), window.status_combo.width())
            self.assertLess(
                window.project_combo.geometry().left(),
                window.primary_action_button.geometry().left(),
            )
            self.assertLess(
                window.primary_action_button.geometry().right(),
                window.language_selector.geometry().left(),
            )
            self.assertLess(
                window.search_edit.mapTo(
                    window.table_header,
                    QPoint(0, 0),
                ).x(),
                window.visible_label.mapTo(
                    window.table_header,
                    QPoint(0, 0),
                ).x(),
            )
            search_action_buttons = window.search_edit.findChildren(QToolButton)
            self.assertEqual(len(search_action_buttons), 2)
            for action_button in search_action_buttons:
                action_center = action_button.mapTo(
                    window.search_edit,
                    action_button.rect().center(),
                )
                self.assertLessEqual(
                    abs(action_center.y() - window.search_edit.rect().center().y()),
                    1,
                )
        finally:
            window.close()

    def test_theme_tabs_switch_and_persist_the_application_theme(self) -> None:
        self.qsettings.setValue("ui/theme", "dark")
        window = self.create_window()
        try:
            self.assertEqual(window.theme_toggle.mode, "dark")
            self.assertTrue(window.theme_toggle.dark_button.isChecked())
            self.assertFalse(window.theme_toggle.light_button.isChecked())

            window.theme_toggle.set_mode("light", emit=True)
            self.app.processEvents()

            self.assertEqual(window.theme_toggle.mode, "light")
            self.assertEqual(self.qsettings.value("ui/theme"), "light")
            self.assertEqual(self.app.styleSheet(), stylesheet_for("light"))
            self.assertTrue(window.theme_toggle.light_button.isChecked())
            self.assertFalse(window.theme_toggle.dark_button.isChecked())
        finally:
            window.theme_toggle.set_mode("dark", emit=True)
            window.close()

    def test_editor_quick_select_aligns_with_form_fields(self) -> None:
        window = self.create_window()
        editor = LicenseEditorDialog(window)
        try:
            editor.show()
            self.app.processEvents()
            username_left = editor.username_edit.mapTo(editor, QPoint(0, 0)).x()
            quick_select_left = editor.quick_select_row.mapTo(
                editor,
                QPoint(0, 0),
            ).x()
            self.assertEqual(quick_select_left, username_left)
            self.assertEqual(
                {
                    editor.username_edit.height(),
                    editor.hwid_edit.height(),
                    editor.expiry_edit.height(),
                    *(button.height() for button in editor.quick_select_buttons),
                },
                {CONTROL_HEIGHT},
            )
            quick_widths = [
                button.width() for button in editor.quick_select_buttons
            ]
            self.assertLessEqual(
                max(quick_widths) - min(quick_widths),
                1,
            )
        finally:
            editor.close()
            window.close()

    def test_every_dialog_action_button_uses_shared_control_height(self) -> None:
        window = self.create_window()
        project_directory = self.project_store.project_directory(
            window._settings.project_id
        )
        dialogs = (
            LicenseEditorDialog(window),
            SettingsDialog(
                window,
                window._settings,
                project_directory=project_directory,
                record_count=0,
            ),
            KeyImportDialog(
                window,
                project_name=window._settings.project_name,
                project_directory=project_directory,
                record_count=0,
            ),
            ServiceAccountImportDialog(
                window,
                project_name=window._settings.project_name,
                project_directory=project_directory,
            ),
            RecordDetailsDialog(
                window,
                LicenseRecord(
                    username="Test user",
                    hwid="abc12345",
                    token="header.payload.signature",
                ),
            ),
        )
        try:
            for dialog in dialogs:
                dialog.show()
                self.app.processEvents()
                action_buttons = dialog.findChildren(QPushButton)
                self.assertTrue(action_buttons, type(dialog).__name__)
                self.assertEqual(
                    {button.height() for button in action_buttons},
                    {CONTROL_HEIGHT},
                    type(dialog).__name__,
                )
                dialog.hide()
        finally:
            for dialog in dialogs:
                dialog.close()
            window.close()

    def test_modal_backdrop_blurs_and_dims_the_main_window(self) -> None:
        window = self.create_window()
        try:
            window.show()
            self.app.processEvents()
            with ModalBackdrop(window):
                backdrop = window.findChild(QFrame, "modalBackdrop")
                self.assertIsNotNone(backdrop)
                self.assertTrue(backdrop.isVisible())
                self.assertIsNotNone(window.centralWidget().graphicsEffect())
        finally:
            window.close()

    def test_rounded_popovers_and_live_language_switching(self) -> None:
        set_language(DEFAULT_LANGUAGE)
        self.qsettings.setValue("ui/language", DEFAULT_LANGUAGE)
        window = self.create_window()
        try:
            self.assertIs(
                window.language_selector.parentWidget(),
                window.top_bar,
            )
            self.assertEqual(window.language_selector.currentData(), "en")
            self.assertEqual(
                FLAG_CDN_TEMPLATE,
                "https://flagcdn.io/flags/4x3/{country_code}.svg",
            )
            self.assertFalse(
                FlagIconLoader(window)._render_svg(
                    b'<svg xmlns="http://www.w3.org/2000/svg" '
                    b'viewBox="0 0 4 3"><path fill="#fff" d="M0 0h4v3H0z"/>'
                    b"</svg>"
                ).isNull()
            )
            self.assertEqual(
                len(window.language_selector.actions()),
                len(LANGUAGES),
            )
            self.assertTrue(
                all(
                    not action.icon().isNull()
                    for action in window.language_selector.actions()
                )
            )
            for menu in (
                window.project_menu,
                window.file_menu,
                window.license_menu,
                window.sheet_menu,
                window.status_combo.menu(),
                window.project_combo.menu(),
                window.language_selector.menu(),
            ):
                self.assertIsInstance(menu, RoundedMenu)
                self.assertEqual(menu.objectName(), "roundedPopover")
                self.assertTrue(
                    menu.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                )

            self.assertTrue(
                window.language_selector.set_current_data("vi", emit=True)
            )
            self.assertEqual(window.new_action.text(), "Tạo license")
            self.assertEqual(window.status_combo.actions()[0].text(), "Tất cả trạng thái")
            self.assertEqual(window.table_model.headerData(0, Qt.Orientation.Horizontal), "Người dùng")
            self.assertEqual(window.theme_toggle.light_button.text(), "Sáng")
            self.assertEqual(window.theme_toggle.dark_button.text(), "Tối")

            self.assertTrue(
                window.language_selector.set_current_data("es", emit=True)
            )
            self.assertEqual(window.new_action.text(), "Crear licencia")
            self.assertEqual(self.qsettings.value("ui/language"), "es")
        finally:
            window.language_selector.set_current_data("en", emit=True)
            window.close()

    def test_dashboard_cards_are_pixel_aligned_at_reference_size(self) -> None:
        window = self.create_window()
        try:
            window.resize(1600, 900)
            window.show()
            self.app.processEvents()

            metric_widths = [card.width() for card in window.metric_cards]
            self.assertLessEqual(max(metric_widths) - min(metric_widths), 1)
            self.assertEqual(window.sidebar.height(), window.centralWidget().height())
            self.assertLessEqual(
                window.table_panel.geometry().right(),
                window.content_surface.rect().right(),
            )
            self.assertGreater(window.table.viewport().height(), 400)
        finally:
            window.close()

    def test_switching_project_updates_identity_and_menu(self) -> None:
        second = self.project_store.create("Second App")
        second.signing_key_path.write_bytes(
            self.private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        second.public_key_path.write_bytes(
            self.private_key.public_key().public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )
        window = self.create_window()
        try:
            window._switch_project(second.project_id)

            self.assertEqual(window._settings.project_id, "second-app")
            self.assertEqual(window.windowTitle(), "Second App — License Admin")
            self.assertEqual(window.project_combo.name_label.text(), "Second App")
            self.assertEqual(window.project_combo.id_label.text(), "second-app")
            self.assertEqual(window.project_combo.avatar_label.text(), "S")
            self.assertEqual(window.project_combo.currentData(), "second-app")
            active_actions = [
                action
                for action in window.project_combo.actions()
                if action.data() == "second-app"
            ]
            self.assertEqual([action.text() for action in active_actions], ["Second App"])
            self.assertTrue(active_actions[0].isChecked())
        finally:
            window.close()

    def test_svg_icon_system_and_disabled_menu_state(self) -> None:
        window = self.create_window()
        try:
            self.assertTrue(ICON_SPRITE_PATH.is_file())
            self.assertTrue(APP_LOGO_PATH.is_file())
            self.assertTrue(APP_ICON_PATH.is_file())
            self.assertFalse(app_icon().isNull())
            configure_application_identity(self.app)
            self.assertFalse(self.app.windowIcon().isNull())
            self.assertFalse(window.windowIcon().isNull())
            editor = LicenseEditorDialog(window)
            message_box = QMessageBox(window)
            self.assertFalse(editor.windowIcon().isNull())
            self.assertFalse(message_box.windowIcon().isNull())
            editor.close()
            message_box.close()
            check_asset = (ICON_SPRITE_PATH.parent / "menu-check.svg").read_text(
                encoding="utf-8"
            )
            light_check_asset = (
                ICON_SPRITE_PATH.parent / "menu-check-light.svg"
            ).read_text(encoding="utf-8")
            self.assertIn("#32d296", check_asset)
            self.assertIn("#159a68", light_check_asset)
            for icon_name in (
                "grid",
                "plus",
                "key",
                "cloud",
                "database",
                "settings",
                "folder-project",
                "search",
                "close",
                "total",
                "check",
                "clock",
                "alert",
                "edit",
                "trash",
                "eye",
                "download",
                "upload",
                "format",
                "plug",
                "external",
                "folder",
                "import",
                "migration",
                "export",
                "copy",
                "toast-success",
                "toast-info",
                "table",
                "sidebar-toggle",
                "about",
                "shield",
                "document",
            ):
                self.assertFalse(svg_icon(icon_name).isNull(), icon_name)

            actions = (
                window.new_action,
                window.edit_action,
                window.revoke_action,
                window.details_action,
                window.pull_action,
                window.push_action,
                window.format_action,
                window.test_action,
                window.open_sheet_action,
                window.settings_action,
                window.new_project_action,
                window.open_project_folder_action,
                window.import_project_keys_action,
                window.import_google_credentials_action,
                window.import_project_config_action,
                window.export_project_config_action,
                window.import_signed_action,
                window.import_legacy_action,
                window.export_action,
            )
            self.assertTrue(all(not action.icon().isNull() for action in actions))
            self.assertFalse(window.edit_action.isEnabled())
            self.assertFalse(window.revoke_action.isEnabled())
            self.assertFalse(window.details_action.isEnabled())
            self.assertIn("QMenu::item:disabled", ADMIN_STYLESHEET)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
