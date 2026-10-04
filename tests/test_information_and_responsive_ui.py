from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect, QSettings, QSize
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea, QWidget

from license_admin.diagnostics import diagnostics_text
from license_admin.data_recovery import ProjectDataState
from license_admin.dialogs import SettingsDialog
from license_admin.information_dialogs import AboutDialog, PolicyDialog, TermsOfServiceDialog
from license_admin.key_import_dialog import KeyImportDialog
from license_admin.localization import LANGUAGES, set_language, text
from license_admin.main_window import LicenseAdminWindow
from license_admin.responsive import fit_window_to_screen
from license_admin.service_account_import_dialog import ServiceAccountImportDialog
from license_admin.settings import ProjectStore
from license_admin.theme import apply_theme
from license_admin.widget_style import configure_widget_style
from ui_test_support import load_test_fonts
from workspace_temp import workspace_temp_dir


class InformationAndResponsiveUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        load_test_fonts()
        configure_widget_style(cls.app)

    def setUp(self) -> None:
        self.temporary = workspace_temp_dir()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.window = LicenseAdminWindow(
            project_store=ProjectStore(root / "private-project-name"),
            qsettings=QSettings(str(root / "ui.ini"), QSettings.Format.IniFormat),
        )

    def tearDown(self) -> None:
        self.assertFalse(self.window._workers, "A worker was left running")
        if self.window._busy:
            self.window._set_busy(False, "Ready")
        self.window.close()
        set_language("en")

    def wait_for_operation(self) -> None:
        for _ in range(600):
            self.app.processEvents()
            if not self.window._workers:
                return
            QTest.qWait(5)
        self.fail("Operation did not finish")

    def assert_contained(self, widget: QWidget, parent: QWidget) -> None:
        bounds = QRect(widget.mapTo(parent, QPoint()), widget.size())
        self.assertTrue(parent.rect().contains(bounds), (widget.objectName(), bounds, parent.rect()))

    def test_dashboard_reflows_at_small_logical_sizes_in_every_locale(self) -> None:
        window = self.window
        window.show()
        for option in LANGUAGES:
            window.language_selector.set_current_data(option.code, emit=True)
            for width, height in ((1024, 768), (683, 480), (512, 344), (460, 300)):
                with self.subTest(language=option.code, width=width):
                    window.resize(width, height)
                    self.app.processEvents()
                    self.assertEqual(window.size(), QSize(width, height))
                    self.assertEqual(window.sidebar.width(), 72)
                    self.assertLessEqual(abs(window.sidebar_toggle.geometry().center().x()
                                             - window.sidebar_header.rect().center().x()), 1)
                    self.assertEqual(window.content_scroll.horizontalScrollBar().maximum(), 0)
                    for control in (window.project_combo, window.primary_action_button, window.info_button,
                                    window.theme_toggle, window.language_selector, window.window_controls):
                        self.assert_contained(control, window.top_bar)
                    self.assertFalse(window.project_combo.geometry().intersects(window.primary_action_button.geometry()))
                    self.assertFalse(window.theme_toggle.geometry().intersects(window.language_selector.geometry()))
                    self.assertLessEqual(window.table_panel.geometry().right(), window.content_surface.rect().right())
                    body = window.table_state_panel.body_label
                    self.assertGreaterEqual(body.height(), body.heightForWidth(body.width()))
                    self.assertGreater(window.content_scroll.verticalScrollBar().maximum(), 0 if width <= 683 else -1)
        window.resize(1320, 820)
        self.app.processEvents()
        self.assertEqual(window.sidebar.width(), 220)
        body = window.table_state_panel.body_label
        self.assertGreaterEqual(body.height(), body.heightForWidth(body.width()))
        window.sidebar_toggle.click()
        window.resize(512, 344)
        self.app.processEvents()
        window.resize(1320, 820)
        self.app.processEvents()
        self.assertEqual(window.sidebar.width(), 72)

    def test_document_language_is_explicit_and_metadata_is_available(self) -> None:
        for option in LANGUAGES:
            set_language(option.code)
            for dialog_type in (AboutDialog, PolicyDialog, TermsOfServiceDialog):
                with self.subTest(language=option.code, dialog=dialog_type.__name__):
                    dialog = dialog_type(self.window)
                    self.assertEqual(dialog.language_notice.isHidden(), option.code in {"en", "vi"})
                    self.assertEqual(dialog.language_notice.text(), text("info.english_notice"))
                    if dialog_type is AboutDialog:
                        self.assertIn(text("info.publisher"), [label.text() for label in dialog.section_titles])
                        self.assertIn(text("info.channel"), [label.text() for label in dialog.section_titles])
                        self.assertIsNotNone(dialog.contact_link)
                        self.assertIsNotNone(dialog.copy_diagnostics_button)
                    else:
                        self.assertIsNone(dialog.contact_link)
                        self.assertIsNone(dialog.copy_diagnostics_button)
                    dialog.close()

    def test_recovery_and_network_errors_remain_usable_in_a_narrow_window(self) -> None:
        window = self.window
        window.resize(512, 344)
        window.show()
        for option in LANGUAGES:
            window.language_selector.set_current_data(option.code, emit=True)
            window._data_state = ProjectDataState.CORRUPTED
            window._update_data_state_banner()
            window._refresh_table_state()
            self.app.processEvents()
            self.assertEqual(window.content_scroll.horizontalScrollBar().maximum(), 0, option.code)
            window._show_operation_error("Timeout: https://example.invalid/" + "a" * 500, Mock())
            self.app.processEvents()
            self.assertEqual(window.width(), 512)
            self.assertEqual(window.content_scroll.horizontalScrollBar().maximum(), 0, option.code)
            self.assert_contained(window.operation_bar.retry_button, window.operation_bar)
            window._dismiss_operation_error()
        window._load_local(show_missing=False)
        self.assertTrue(window.operation_bar.isHidden())

    def test_copy_diagnostics_is_allowlisted_and_uses_current_theme(self) -> None:
        self.window._theme_selected("light")
        dialog = AboutDialog(self.window)
        try:
            dialog.copy_diagnostics_button.click()
            copied = QApplication.clipboard().text()
            data = json.loads(copied)
            self.assertEqual(data, json.loads(diagnostics_text(self.window)))
            self.assertEqual(data["theme"], "light")
            self.assertEqual(data["build_channel"], "source")
            self.assertEqual(set(data), {
                "application", "version", "build_channel", "publisher", "os", "os_release",
                "architecture", "python", "qt", "pyside", "language", "theme", "window_size",
                "screen_available_size", "device_pixel_ratio",
            })
            self.assertNotIn(self.temporary.name, copied)
            self.assertNotIn("private-project-name", copied)
        finally:
            QApplication.clipboard().clear()
            dialog.close()

    def test_privacy_scroll_reaches_the_last_paragraph_without_an_empty_tail(self) -> None:
        for mode in ("dark", "light"):
            apply_theme(mode)
            for language in ("en", "vi"):
                set_language(language)
                dialog = PolicyDialog(self.window)
                try:
                    for width, height in ((670, 570), (488, 304)):
                        with self.subTest(theme=mode, language=language, width=width):
                            dialog.resize(width, height)
                            dialog.show()
                            QTest.qWait(1)
                            scroll = dialog.findChild(QScrollArea, "informationScroll")
                            self.assertIsNotNone(scroll)
                            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
                            self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
                            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                            self.app.processEvents()
                            self.assert_contained(dialog.section_bodies[-1], scroll.viewport())
                            for label in dialog.section_bodies:
                                self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
                finally:
                    dialog.close()

    def test_information_settings_and_imports_fit_and_scroll_on_small_screens(self) -> None:
        profile = self.window._settings
        directory = profile.local_csv_path.parent
        screen = SimpleNamespace(availableGeometry=lambda: QRect(0, 0, 512, 344))
        for option in LANGUAGES:
            set_language(option.code)
            with patch.object(QWidget, "screen", return_value=screen):
                dialogs = [
                    AboutDialog(self.window), PolicyDialog(self.window), TermsOfServiceDialog(self.window),
                    SettingsDialog(self.window, profile, project_directory=directory, record_count=0),
                    KeyImportDialog(self.window, project_name="Example", project_directory=directory, record_count=0),
                    ServiceAccountImportDialog(self.window, project_name="Example", project_directory=directory),
                ]
            for dialog in dialogs:
                with self.subTest(language=option.code, dialog=type(dialog).__name__):
                    dialog.show()
                    self.app.processEvents()
                    self.assertLessEqual(dialog.width(), 488)
                    self.assertLessEqual(dialog.height(), 304)
                    scrolls = dialog.findChildren(QScrollArea)
                    self.assertTrue(scrolls)
                    for scroll in scrolls:
                        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0,
                                         (option.code, type(dialog).__name__, scroll.objectName()))
                    if isinstance(dialog, PolicyDialog):
                        for label in dialog.section_bodies:
                            self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()),
                                                    (option.code, label.text()))
                        scrolls[0].verticalScrollBar().setValue(scrolls[0].verticalScrollBar().maximum())
                        self.app.processEvents()
                        last_section = dialog.section_bodies[-1]
                        self.assertLess(last_section.mapTo(scrolls[0].viewport(), QPoint()).y(),
                                        scrolls[0].viewport().height())
                    dialog.close()
        widget = QWidget()
        with patch.object(QWidget, "screen", return_value=screen):
            fit_window_to_screen(widget, QSize(1320, 820), QSize(460, 300))
        self.assertEqual(widget.size(), QSize(488, 304))
        widget.close()

    def test_elapsed_time_and_failure_retry_persist_after_worker_finishes(self) -> None:
        window = self.window
        with patch("license_admin.operation_bar.monotonic", return_value=100.0) as clock:
            window._set_busy(True, "Reading", step="Checking data")
            clock.return_value = 163.0
            window.operation_bar._update_elapsed()
            self.assertEqual(window.operation_bar.elapsed_label.text(), "01:03")
            window._set_busy(False, "Ready")
        fail = True
        results: list[object] = []

        def operation() -> int:
            if fail:
                raise RuntimeError("Network unavailable")
            return 42

        def retry() -> None:
            window._run_operation("Reading", operation, results.append, retry=retry)

        with patch.object(QMessageBox, "critical"):
            retry()
            self.wait_for_operation()
            self.assertFalse(window.operation_bar.isHidden())
            self.assertFalse(window.operation_bar.retry_button.isHidden())
            self.assertIsNotNone(window._last_operation_retry)
            fail = False
            window.operation_bar.retry_button.click()
            self.wait_for_operation()
            self.assertEqual(results, [42])
            self.assertTrue(window.operation_bar.isHidden())
            self.assertIsNone(window._last_operation_retry)

    def test_safe_cancellation_discards_results_and_restores_controls(self) -> None:
        for raises in (False, True):
            started, release = Event(), Event()
            callback = Mock()

            def operation() -> int:
                started.set()
                release.wait(3)
                if raises:
                    raise RuntimeError("Late failure after cancellation")
                return 42

            with patch.object(QMessageBox, "critical") as error:
                self.window._run_operation("Reading", operation, callback, retry=Mock(), cancellable=True)
                try:
                    self.assertTrue(started.wait(1))
                    self.window.operation_bar.cancel_button.click()
                    self.assertTrue(self.window._busy)
                    self.assertFalse(self.window.operation_bar.cancel_button.isEnabled())
                finally:
                    release.set()
                    self.wait_for_operation()
                callback.assert_not_called()
                error.assert_not_called()
                self.assertFalse(self.window._busy)
                self.assertTrue(self.window.project_combo.isEnabled())
                self.assertTrue(self.window.operation_bar.isHidden())

    def test_writes_cannot_be_cancelled_and_completion_errors_allow_retry(self) -> None:
        started, release = Event(), Event()
        callback = Mock(side_effect=RuntimeError("Local completion failed"))

        def operation() -> int:
            started.set()
            release.wait(3)
            return 42

        with patch.object(QMessageBox, "critical"):
            self.window._run_operation("Publishing", operation, callback, retry=Mock())
            try:
                self.assertTrue(started.wait(1))
                self.assertTrue(self.window.operation_bar.cancel_button.isHidden())
                self.window._cancel_operation()
                self.assertFalse(self.window._operation_cancelled)
            finally:
                release.set()
                self.wait_for_operation()
            callback.assert_called_once_with(42)
            self.assertFalse(self.window.operation_bar.retry_button.isHidden())
            self.window.operation_bar.dismiss_button.click()
            self.assertTrue(self.window.operation_bar.isHidden())
            self.assertIsNone(self.window._last_operation_retry)
