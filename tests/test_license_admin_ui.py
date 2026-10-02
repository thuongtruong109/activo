from __future__ import annotations

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
    QFrame,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QToolBar,
    QToolButton,
)

from license_admin.dialogs import (
    LicenseEditorDialog,
    RecordDetailsDialog,
    SettingsDialog,
)
from license_admin.domain import LicenseRecord
from license_admin.flag_icons import FLAG_CDN_TEMPLATE, FlagIconLoader
from license_admin.key_import_dialog import KeyImportDialog
from license_admin.main_window import LicenseAdminWindow
from license_admin.icons import ICON_SPRITE_PATH, svg_icon
from license_admin.localization import DEFAULT_LANGUAGE, LANGUAGES, set_language
from license_admin.modal_backdrop import ModalBackdrop
from license_admin.popover import RoundedMenu
from license_admin.qt_models import LicenseFilterModel, LicenseTableModel
from license_admin.service_account_import_dialog import ServiceAccountImportDialog
from license_admin.settings import ProjectStore
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
            self.assertEqual(
                window.window_chrome.height(),
                window.top_bar.height(),
            )
            self.assertIs(window.window_chrome.parentWidget(), window.sidebar)
            self.assertEqual(window.window_chrome.close_button.objectName(), "trafficClose")
            self.assertEqual(
                window.window_chrome.minimize_button.objectName(),
                "trafficMinimize",
            )
            self.assertEqual(
                window.window_chrome.maximize_button.objectName(),
                "trafficMaximize",
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
            self.assertIs(window.header_brand.parentWidget(), window.window_chrome)
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
        finally:
            window.close()

    def test_project_menu_exposes_key_import_and_settings_dialog_reuses_it(self) -> None:
        window = self.create_window()
        try:
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
            self.assertEqual(window.project_identity.name_label.text(), "Second App")
            self.assertEqual(window.project_combo.currentData(), "second-app")
            active_actions = [
                action
                for action in window.project_menu.actions()
                if action.data() == "second-app"
            ]
            self.assertEqual([action.text() for action in active_actions], ["Second App"])
            self.assertFalse(active_actions[0].icon().isNull())
        finally:
            window.close()

    def test_svg_icon_system_and_disabled_menu_state(self) -> None:
        window = self.create_window()
        try:
            self.assertTrue(ICON_SPRITE_PATH.is_file())
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
