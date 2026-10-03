from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError
from license_admin.key_store import import_key_pair
from license_admin.service_account_store import import_service_account
from license_admin.settings import AdminSettings, ProjectStore
from license_admin.settings_transaction import SettingsTransaction
from workspace_temp import workspace_temp_dir


def _write_key_pair(directory: Path, stem: str) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    private_path = directory / f"{stem}-private.pem"
    public_path = directory / f"{stem}-public.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


def _write_service_account(path: Path, email: str) -> Path:
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "type": "service_account",
                "project_id": "transaction-test",
                "private_key": private_key.private_bytes(
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


class SettingsTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        patches = (
            patch("license_admin.key_store.restrict_to_current_user"),
            patch("license_admin.settings_transaction.restrict_to_current_user"),
            patch("license_admin.service_account_store.restrict_to_current_user"),
        )
        for acl in patches:
            acl.start()
            self.addCleanup(acl.stop)

    def _configured_project(
        self,
        root: Path,
    ) -> tuple[ProjectStore, AdminSettings, bytes, bytes, bytes]:
        store = ProjectStore(root / "projects")
        profile = store.ensure_default()
        old_pair = _write_key_pair(root / "sources", "old")
        old_keys = import_key_pair(*old_pair, profile.signing_key_path.parent)
        old_credential_source = _write_service_account(
            root / "sources" / "old-service.json",
            "old@example.test",
        )
        old_credential = import_service_account(
            old_credential_source,
            profile.signing_key_path.parent,
        )
        configured = replace(
            profile,
            signing_key_path=old_keys.private_key_path,
            public_key_path=old_keys.public_key_path,
            service_account_path=old_credential.path,
        )
        store.save(configured)
        return (
            store,
            configured,
            old_keys.private_key_path.read_bytes(),
            old_keys.public_key_path.read_bytes(),
            old_credential.path.read_bytes(),
        )

    def _stage_replacements(
        self,
        root: Path,
        transaction: SettingsTransaction,
    ) -> tuple[Path, Path]:
        new_pair = _write_key_pair(root / "sources", "new")
        staged_keys = import_key_pair(
            *new_pair,
            transaction.key_staging_directory,
        )
        transaction.register_key_pair(staged_keys)
        new_credential = _write_service_account(
            root / "sources" / "new-service.json",
            "new@example.test",
        )
        staged_credential = import_service_account(
            new_credential,
            transaction.credential_staging_directory,
        )
        transaction.register_service_account(staged_credential)
        return staged_keys.private_key_path, staged_credential.path

    def test_discard_removes_staging_without_touching_project_files(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store, configured, old_private, old_public, old_credential = (
                self._configured_project(root)
            )
            transaction = SettingsTransaction(
                store.project_directory(configured.project_id)
            )
            staged_key, staged_credential = self._stage_replacements(
                root,
                transaction,
            )
            staging_root = staged_key.parent.parent

            transaction.discard()

            self.assertFalse(staging_root.exists())
            self.assertFalse(staged_credential.exists())
            self.assertEqual(configured.signing_key_path.read_bytes(), old_private)
            self.assertEqual(configured.public_key_path.read_bytes(), old_public)
            self.assertIsNotNone(configured.service_account_path)
            assert configured.service_account_path is not None
            self.assertEqual(
                configured.service_account_path.read_bytes(), old_credential
            )

    def test_commit_switches_profile_only_after_all_assets_are_ready(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store, configured, old_private, old_public, old_credential = (
                self._configured_project(root)
            )
            transaction = SettingsTransaction(
                store.project_directory(configured.project_id)
            )
            staged_key, _staged_credential = self._stage_replacements(
                root,
                transaction,
            )
            staging_root = staged_key.parent.parent
            requested = replace(
                configured,
                project_name="Committed Project",
                signing_key_path=transaction.private_key_path,
                public_key_path=transaction.public_key_path,
                service_account_path=transaction.service_account_path,
            )

            committed = transaction.commit(store, requested)
            loaded = store.load(committed.project_id)

            self.assertFalse(staging_root.exists())
            self.assertEqual(loaded, committed)
            self.assertTrue(committed.signing_key_path.is_file())
            self.assertTrue(committed.public_key_path.is_file())
            self.assertIsNotNone(committed.service_account_path)
            assert committed.service_account_path is not None
            self.assertTrue(committed.service_account_path.is_file())
            self.assertNotEqual(committed.signing_key_path.read_bytes(), old_private)
            self.assertNotEqual(committed.public_key_path.read_bytes(), old_public)
            self.assertNotEqual(
                committed.service_account_path.read_bytes(), old_credential
            )
            self.assertEqual(configured.signing_key_path.read_bytes(), old_private)
            self.assertEqual(configured.public_key_path.read_bytes(), old_public)
            self.assertIsNotNone(configured.service_account_path)
            assert configured.service_account_path is not None
            self.assertEqual(
                configured.service_account_path.read_bytes(), old_credential
            )

    def test_profile_save_failure_rolls_back_published_asset_generation(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store, configured, old_private, old_public, old_credential = (
                self._configured_project(root)
            )
            original_profile = store.profile_path(
                configured.project_id
            ).read_bytes()
            transaction = SettingsTransaction(
                store.project_directory(configured.project_id)
            )
            staged_key, _staged_credential = self._stage_replacements(
                root,
                transaction,
            )
            staging_root = staged_key.parent.parent
            asset_directory = transaction.asset_directory
            requested = replace(
                configured,
                signing_key_path=transaction.private_key_path,
                public_key_path=transaction.public_key_path,
                service_account_path=transaction.service_account_path,
            )

            with (
                patch.object(
                    store,
                    "save",
                    side_effect=LicenseIssueError("simulated profile failure"),
                ),
                self.assertRaisesRegex(LicenseIssueError, "simulated profile failure"),
            ):
                transaction.commit(store, requested)

            self.assertFalse(staging_root.exists())
            self.assertFalse(asset_directory.exists())
            self.assertEqual(
                store.profile_path(configured.project_id).read_bytes(),
                original_profile,
            )
            self.assertEqual(configured.signing_key_path.read_bytes(), old_private)
            self.assertEqual(configured.public_key_path.read_bytes(), old_public)
            self.assertIsNotNone(configured.service_account_path)
            assert configured.service_account_path is not None
            self.assertEqual(
                configured.service_account_path.read_bytes(), old_credential
            )

    def test_asset_copy_failure_never_switches_project_profile(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store, configured, old_private, old_public, old_credential = (
                self._configured_project(root)
            )
            original_profile = store.profile_path(
                configured.project_id
            ).read_bytes()
            transaction = SettingsTransaction(
                store.project_directory(configured.project_id)
            )
            self._stage_replacements(root, transaction)
            asset_directory = transaction.asset_directory
            requested = replace(
                configured,
                signing_key_path=transaction.private_key_path,
                public_key_path=transaction.public_key_path,
                service_account_path=transaction.service_account_path,
            )
            real_copy = SettingsTransaction._copy_durable

            def fail_public_copy(
                source: Path,
                destination: Path,
                *,
                private: bool = False,
                expected_digest: str,
            ) -> None:
                if destination.name == "public.pem":
                    raise LicenseIssueError("simulated asset copy failure")
                real_copy(
                    source,
                    destination,
                    private=private,
                    expected_digest=expected_digest,
                )

            with (
                patch.object(
                    transaction,
                    "_copy_durable",
                    side_effect=fail_public_copy,
                ),
                self.assertRaisesRegex(
                    LicenseIssueError,
                    "simulated asset copy failure",
                ),
            ):
                transaction.commit(store, requested)

            self.assertFalse(asset_directory.exists())
            self.assertEqual(
                store.profile_path(configured.project_id).read_bytes(),
                original_profile,
            )
            self.assertEqual(configured.signing_key_path.read_bytes(), old_private)
            self.assertEqual(configured.public_key_path.read_bytes(), old_public)
            self.assertIsNotNone(configured.service_account_path)
            assert configured.service_account_path is not None
            self.assertEqual(
                configured.service_account_path.read_bytes(), old_credential
            )

    def test_modified_staged_key_is_rejected_before_profile_switch(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store, configured, old_private, old_public, old_credential = (
                self._configured_project(root)
            )
            original_profile = store.profile_path(
                configured.project_id
            ).read_bytes()
            transaction = SettingsTransaction(
                store.project_directory(configured.project_id)
            )
            staged_private, _staged_credential = self._stage_replacements(
                root,
                transaction,
            )
            requested = replace(
                configured,
                signing_key_path=transaction.private_key_path,
                public_key_path=transaction.public_key_path,
                service_account_path=transaction.service_account_path,
            )
            staged_private.write_bytes(b"tampered after validation")

            with self.assertRaisesRegex(
                LicenseIssueError,
                "changed after validation",
            ):
                transaction.commit(store, requested)

            self.assertFalse(transaction.asset_directory.exists())
            self.assertEqual(
                store.profile_path(configured.project_id).read_bytes(),
                original_profile,
            )
            self.assertEqual(configured.signing_key_path.read_bytes(), old_private)
            self.assertEqual(configured.public_key_path.read_bytes(), old_public)
            self.assertIsNotNone(configured.service_account_path)
            assert configured.service_account_path is not None
            self.assertEqual(
                configured.service_account_path.read_bytes(), old_credential
            )

    def test_modified_staged_credential_is_rejected_before_profile_switch(
        self,
    ) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            store, configured, old_private, old_public, old_credential = (
                self._configured_project(root)
            )
            original_profile = store.profile_path(
                configured.project_id
            ).read_bytes()
            transaction = SettingsTransaction(
                store.project_directory(configured.project_id)
            )
            _staged_private, staged_credential = self._stage_replacements(
                root,
                transaction,
            )
            requested = replace(
                configured,
                signing_key_path=transaction.private_key_path,
                public_key_path=transaction.public_key_path,
                service_account_path=transaction.service_account_path,
            )
            staged_credential.write_bytes(b"tampered after validation")

            with self.assertRaisesRegex(
                LicenseIssueError,
                "changed after validation",
            ):
                transaction.commit(store, requested)

            self.assertFalse(transaction.asset_directory.exists())
            self.assertEqual(
                store.profile_path(configured.project_id).read_bytes(),
                original_profile,
            )
            self.assertEqual(configured.signing_key_path.read_bytes(), old_private)
            self.assertEqual(configured.public_key_path.read_bytes(), old_public)
            self.assertIsNotNone(configured.service_account_path)
            assert configured.service_account_path is not None
            self.assertEqual(
                configured.service_account_path.read_bytes(), old_credential
            )


if __name__ == "__main__":
    unittest.main()
