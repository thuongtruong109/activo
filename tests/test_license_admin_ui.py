from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QToolBar, QToolButton

from license_admin.dialogs import SettingsDialog
from license_admin.domain import LicenseRecord
from license_admin.main_window import LicenseAdminWindow
from license_admin.qt_models import LicenseFilterModel, LicenseTableModel
from license_admin.settings import ProjectStore
from workspace_temp import workspace_temp_dir


class LicenseAdminUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        existing = QApplication.instance()
        cls.app = existing if isinstance(existing, QApplication) else QApplication([])
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
            self.assertEqual(window.findChildren(QToolBar), [])
            self.assertFalse(window.table.verticalHeader().isHidden())
            self.assertTrue(window.statusBar().isHidden())
            self.assertIs(
                window.menuBar().cornerWidget(Qt.Corner.TopRightCorner),
                window.top_controls,
            )
        finally:
            window.close()

    def test_project_menu_exposes_key_import_and_settings_dialog_reuses_it(self) -> None:
        window = self.create_window()
        try:
            self.assertIn(window.import_project_keys_action, window.project_menu.actions())
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
            finally:
                settings.close()
        finally:
            window.close()

    def test_top_controls_fit_and_clear_button_is_centered(self) -> None:
        window = self.create_window()
        try:
            window.resize(980, 640)
            window.show()
            window.search_edit.setText("de")
            self.app.processEvents()

            self.assertLessEqual(
                window.sync_badge.geometry().right(),
                window.top_controls.rect().right(),
            )
            clear_buttons = window.search_edit.findChildren(QToolButton)
            self.assertEqual(len(clear_buttons), 1)
            clear_center = clear_buttons[0].mapTo(
                window.search_edit,
                clear_buttons[0].rect().center(),
            )
            self.assertLessEqual(
                abs(clear_center.y() - window.search_edit.rect().center().y()),
                1,
            )
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
            checked = [
                action.text()
                for action in window.project_menu.actions()
                if action.isCheckable() and action.isChecked()
            ]
            self.assertEqual(checked, ["Second App"])
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
