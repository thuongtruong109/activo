from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QTextEdit

from license_admin.main_window import LicenseAdminWindow
from license_admin.domain import LicenseStatus
from license_admin.localization import LANGUAGES, set_language, text
from license_admin.revocation_dialog import RevocationDialog
from license_admin.revocations import RevocationPhase, RevocationRepository
from license_admin.settings import ProjectStore
from license_admin.storage import LicenseRepository
from license_admin.widget_style import configure_widget_style
from test_legacy_publication import LegacyProtocolClient
from ui_test_support import load_test_fonts
from workspace_temp import workspace_temp_dir


class PublicationWorkflowUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        load_test_fonts()
        configure_widget_style(cls.app)
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.tmp = workspace_temp_dir()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        store = ProjectStore(root / "projects")
        profile = store.ensure_default()
        profile.signing_key_path.write_bytes(self.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        profile.public_key_path.write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.window = LicenseAdminWindow(project_store=store,
                                        qsettings=QSettings(str(root / "ui.ini"), QSettings.IniFormat))
        self.window._settings = replace(self.window._settings, spreadsheet_id="a" * 30,
                                        service_account_path=Path("unused.json"))
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.assertFalse(self.window._workers)
        self.window.close()
        set_language("en")

    def create_license(self):
        dialog = SimpleNamespace(values=lambda: ("Khách hàng", "a" * 64,
                                                datetime.now(timezone.utc) + timedelta(days=365)))
        self.window._apply_license_editor(dialog, None)
        self.assertEqual(len(self.window._records), 1)
        self.window.table.selectRow(0)
        self.app.processEvents()
        return self.window._records[0]

    def finish_operation(self):
        for _ in range(600):
            self.app.processEvents()
            if not self.window._workers and not self.window._busy:
                return
            QTest.qWait(5)
        self.fail("Publication worker did not finish")

    def publish(self, client):
        with patch.object(self.window, "_sheet_client", return_value=client), \
             patch.object(self.window, "_confirm_sync_preview", return_value=True), \
             patch.object(QMessageBox, "critical") as error:
            self.window.publish_button.click()
            self.finish_operation()
            error.assert_not_called()

    def test_revoke_is_visible_searchable_and_published_from_the_dashboard(self):
        record = self.create_license()
        self.assertFalse(self.window.publication_panel.isHidden())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window._revoke_license()
        self.assertEqual(self.window._records, [])
        self.assertEqual(self.window.table_model.rowCount(), 1)
        revoked = self.window.table_model.record_at(0)
        self.assertEqual((revoked.hwid, revoked.username, revoked.jti),
                         (record.hwid, record.username, record.jti))
        self.assertEqual(revoked.token, "")
        self.assertIsNone(revoked.parse_error)
        self.assertEqual(self.window.table_model.data(self.window.table_model.index(0, 2)),
                         text("status.revoked_pending"))
        self.assertIs(self.window.table_stack.currentWidget(), self.window.table)
        self.assertTrue(self.window.data_state_banner.isHidden())
        self.assertEqual(self.window.total_card.value_label.text(), "1")
        self.assertEqual(self.window.expired_card.value_label.text(), "0")
        self.window.search_edit.setText("khach hang")
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.search_edit.setText(record.hwid)
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.window.search_edit.setText("unknown device")
        self.assertEqual(self.window.proxy_model.rowCount(), 0)
        self.assertEqual(self.window.table_state_panel.property("state"), "no_results")
        self.window.search_edit.clear()
        self.window.status_combo.set_current_data(LicenseStatus.INVALID, emit=True)
        self.assertEqual(self.window.proxy_model.rowCount(), 0)
        self.window.status_combo.set_current_data(LicenseStatus.REVOKED, emit=True)
        self.assertEqual(self.window.proxy_model.rowCount(), 1)
        self.assertIn("1", self.window.publication_panel.body.text())
        self.assertFalse(self.window.publication_panel.review_button.isHidden())
        self.assertIs(self.window._revocations[0].phase, RevocationPhase.PENDING)
        dialog = RevocationDialog(self.window, self.window._revocations, can_publish=True)
        try:
            dialog.search.setText("khach hang")
            self.assertFalse(dialog.table.isRowHidden(0))
            dialog.search.setText("not this device")
            self.assertTrue(dialog.table.isRowHidden(0))
            self.assertTrue(dialog.publish_button.isEnabled())
        finally:
            dialog.close()
        client = LegacyProtocolClient((record,))
        self.publish(client)
        self.assertEqual(client.current.disabled_hwids, (record.hwid,))
        self.assertEqual(self.window._sync_badge_state, "synced")
        self.assertTrue(self.window.publication_panel.isHidden())
        self.assertIs(self.window._revocations[0].phase, RevocationPhase.PUBLISHED)
        self.assertEqual(self.window.table_model.rowCount(), 1)
        self.assertEqual(self.window.table_model.record_at(0).token, "")
        self.assertEqual(self.window.table_model.data(self.window.table_model.index(0, 2)),
                         text("status.revoked"))
        self.assertEqual(LicenseRepository(self.window._settings.local_csv_path).load(), [])
        store, settings = self.window._project_store, self.window._qsettings
        self.window.close()
        self.window = LicenseAdminWindow(project_store=store, qsettings=settings)
        self.assertEqual(self.window.table_model.rowCount(), 1)
        self.assertEqual(self.window.table_model.record_at(0).token, "")
        self.assertEqual(self.window.table_model.data(self.window.table_model.index(0, 2)),
                         text("status.revoked"))

    def test_revoked_device_actions_and_details_do_not_reissue_or_copy_a_token(self):
        self.create_license()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window._revoke_license()
        self.window.table.selectRow(0)
        self.app.processEvents()
        self.assertFalse(self.window.edit_action.isEnabled())
        self.assertFalse(self.window.revoke_action.isEnabled())
        self.assertTrue(self.window.remove_action.isEnabled())
        self.assertTrue(self.window.details_action.isEnabled())
        with patch("license_admin.main_window.LicenseEditorDialog") as editor, \
             patch.object(QMessageBox, "question") as confirmation, \
             patch.object(self.window, "_show_details") as details:
            self.window._edit_license()
            self.window._revoke_license()
            self.window._open_selected_device()
            editor.assert_not_called()
            confirmation.assert_not_called()
            details.assert_called_once()
        from license_admin.dialogs import RecordDetailsDialog
        dialog = RecordDetailsDialog(self.window, self.window._selected_record())
        try:
            self.assertEqual(dialog.findChild(QTextEdit).toPlainText(), "")
            buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
            self.assertFalse(buttons[text("details.copy_token")].isEnabled())
            self.assertTrue(buttons[text("details.copy_hwid")].isEnabled())
        finally:
            dialog.close()

    def test_remove_from_a_published_revoked_row_hides_only_that_device(self):
        record = self.create_license()
        other_dialog = SimpleNamespace(values=lambda: ("Other customer", "b" * 64,
                                                      datetime.now(timezone.utc) + timedelta(days=365)))
        self.window._apply_license_editor(other_dialog, None)
        other = next(item for item in self.window._records if item.hwid == "b" * 64)
        self.window.table.selectRow(0)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window._revoke_license()
        client = LegacyProtocolClient((record, other))
        self.publish(client)
        self.window.status_combo.set_current_data(LicenseStatus.REVOKED, emit=True)
        self.window.table.selectRow(0)
        self.app.processEvents()
        self.assertTrue(self.window.remove_action.isEnabled())
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.remove_action.trigger()
        self.assertEqual(self.window.table_model.rowCount(), 1)
        self.assertEqual(self.window.table_model.record_at(0), other)
        self.assertEqual(self.window._records, [other])
        self.assertEqual(self.window.total_card.value_label.text(), "1")
        self.assertEqual(len(self.window._revocations), 1)
        self.assertTrue(self.window._revocations[0].remove_device)
        self.publish(client)
        self.assertEqual(client.current.disabled_hwids, ())
        self.assertEqual(client.current.records, (other,))
        self.assertEqual(self.window.table_model.rowCount(), 1)
        self.assertIs(self.window._revocations[0].phase, RevocationPhase.PUBLISHED)

    def test_pulling_blank_token_sheet_rows_retains_the_device_in_the_main_table(self):
        from license_admin.feed_manifest import FeedDocument
        from license_admin.feed_format import publication_digest
        from license_admin.google_sheets import RemoteRevision
        client = LegacyProtocolClient()
        feed = FeedDocument((), (), disabled_hwids=("b" * 64,))
        digest = publication_digest(feed)
        client.current = replace(client.current, disabled_hwids=feed.disabled_hwids,
                                 digest=digest, content_digest=digest,
                                 revision=RemoteRevision(1, digest, 99, client.current.target_sheet_id))
        context = self.window._local_sync_context(self.window._sheet_target(client.config))
        with patch.object(self.window, "_sheet_client", return_value=client), \
             patch.object(QMessageBox, "critical") as error:
            self.window._apply_pull_preview(context=context, reviewed=client.current,
                                            reviewed_public=None, config=client.config,
                                            public_url="", verification=self.window._verification_values())
            self.finish_operation()
            error.assert_not_called()
        self.assertEqual(self.window._records, [])
        self.assertEqual(self.window.table_model.rowCount(), 1)
        self.assertEqual(self.window.table_model.record_at(0).hwid, "b" * 64)
        self.assertEqual(self.window.table_model.record_at(0).token, "")
        self.assertEqual(self.window.table_model.data(self.window.table_model.index(0, 2)),
                         text("status.revoked"))
        self.assertIs(self.window.table_stack.currentWidget(), self.window.table)

    def test_remove_deletes_the_published_row_and_keeps_a_local_audit(self):
        record = self.create_license()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window._remove_license()
        self.assertTrue(self.window._revocations[0].remove_device)
        self.assertEqual(LicenseRepository(self.window._settings.local_csv_path).load(), [])
        self.assertTrue(RevocationRepository.beside(self.window._settings.local_csv_path).load()[0].remove_device)
        client = LegacyProtocolClient((record,))
        self.publish(client)
        self.assertEqual(client.current.records, ())
        self.assertEqual(client.current.disabled_hwids, ())
        self.assertEqual(self.window._sync_badge_state, "synced")

    def test_failed_publication_keeps_the_prompt_and_blocks_duplicate_busy_clicks(self):
        self.create_license()
        client = LegacyProtocolClient()
        with patch.object(self.window, "_sheet_client", return_value=client), \
             patch.object(client, "read_snapshot", side_effect=RuntimeError("Network unavailable")), \
             patch.object(QMessageBox, "critical"):
            self.window.publication_panel.publish_button.click()
            self.finish_operation()
        self.assertFalse(self.window.publication_panel.isHidden())
        self.assertNotEqual(self.window._sync_badge_state, "synced")
        self.window._set_busy(True, "Publishing")
        try:
            self.assertFalse(self.window.publish_button.isEnabled())
            self.assertFalse(self.window.publication_panel.publish_button.isEnabled())
            self.assertFalse(self.window.remove_action.isEnabled())
        finally:
            self.window._set_busy(False, "Ready")

    def test_pending_revocation_returns_after_restart_and_settings_preserve_the_format(self):
        self.create_license()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window._revoke_license()
        store = self.window._project_store
        settings = self.window._qsettings
        self.window.close()
        self.window = LicenseAdminWindow(project_store=store, qsettings=settings)
        self.assertEqual(self.window._settings.feed_format, "legacy")
        self.assertFalse(self.window.publication_panel.isHidden())
        self.assertEqual(self.window._sync_badge_state, "revocation_pending")
        self.assertEqual(self.window.table_model.rowCount(), 1)
        self.assertEqual(self.window.table_model.record_at(0).token, "")
        self.assertEqual(self.window.table_model.data(self.window.table_model.index(0, 2)),
                         text("status.revoked_pending"))
        self.assertIs(self.window.table_stack.currentWidget(), self.window.table)
        from license_admin.dialogs import SettingsDialog
        dialog = SettingsDialog(self.window, self.window._settings,
                                project_directory=self.window._settings.local_csv_path.parent,
                                record_count=0)
        try:
            self.assertEqual(dialog.values().feed_format, "legacy")
            dialog.feed_format_combo.setCurrentIndex(1)
            self.assertEqual(dialog.values().feed_format, "signed-v2")
        finally:
            dialog.close()

    def test_pending_publication_panel_fits_small_windows_in_every_locale(self):
        self.create_license()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window._revoke_license()
        for language in LANGUAGES:
            self.window.language_selector.set_current_data(language.code, emit=True)
            for width in (683, 512, 460):
                with self.subTest(language=language.code, width=width):
                    self.window.resize(width, 344)
                    self.app.processEvents()
                    self.assertEqual(self.window.content_scroll.horizontalScrollBar().maximum(), 0)
                    panel = self.window.publication_panel
                    for button in (panel.publish_button, panel.review_button):
                        self.assertLessEqual(button.geometry().right(), panel.rect().right())

    def test_missing_v2_manifest_is_rejected_when_v2_is_selected(self):
        self.window._settings = replace(self.window._settings, feed_format="signed-v2")
        client = LegacyProtocolClient()
        with self.assertRaisesRegex(ValueError, "no signed v2"):
            self.window._verify_remote_feed(client.current, self.window._verification_values(),
                                           self.window._sheet_target(client.config),
                                           minimum_revision=0, require_manifest=True)

    def test_old_pending_removal_is_shown_before_recent_published_history(self):
        from license_admin.revocations import RevocationEntry
        older = datetime(2026, 1, 1, tzinfo=timezone.utc)
        recent = datetime(2026, 10, 14, tzinfo=timezone.utc)
        entries = (
            RevocationEntry("b" * 64, None, "Published", recent, RevocationPhase.PUBLISHED,
                            published_at=recent, published_revision=1),
            RevocationEntry("a" * 64, None, "Pending removal", older, RevocationPhase.PENDING,
                            remove_device=True),
        )
        dialog = RevocationDialog(self.window, entries, can_publish=True)
        try:
            self.assertEqual(dialog.table.item(0, 0).text(), "Pending removal")
            self.assertTrue(dialog.table.item(0, 2).font().bold())
        finally:
            dialog.close()
