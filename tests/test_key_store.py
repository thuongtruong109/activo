from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError
from license_admin.key_store import (
    MAX_KEY_FILE_BYTES,
    KeyPasswordRequiredError,
    import_key_pair,
    inspect_key_pair,
)
from workspace_temp import workspace_temp_dir


def write_key_pair(
    directory: Path,
    stem: str,
    *,
    password: bytes | None = None,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65_537, key_size=2_048)
    private_path = directory / f"{stem}-private.pem"
    public_path = directory / f"{stem}-public.pem"
    encryption: serialization.KeySerializationEncryption = (
        serialization.BestAvailableEncryption(password)
        if password is not None
        else serialization.NoEncryption()
    )
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            encryption,
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


class KeyStoreTests(unittest.TestCase):
    def test_oversized_key_file_is_rejected_before_parsing(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            private_path = root / "too-large.pem"
            private_path.write_bytes(b"x" * (MAX_KEY_FILE_BYTES + 1))
            _, public_path = write_key_pair(root, "valid")

            with self.assertRaisesRegex(LicenseIssueError, "between 1"):
                inspect_key_pair(private_path, public_path)

    def test_import_validates_and_copies_pair_into_project(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            private_path, public_path = write_key_pair(root / "source", "alpha")

            imported = import_key_pair(
                private_path,
                public_path,
                root / "projects" / "alpha",
            )

            self.assertEqual(imported.private_key_path.name, "private.pem")
            self.assertEqual(imported.public_key_path.name, "public.pem")
            self.assertEqual(imported.private_key_path.read_bytes(), private_path.read_bytes())
            self.assertEqual(imported.public_key_path.read_bytes(), public_path.read_bytes())
            self.assertEqual(imported.info.key_size, 2_048)
            self.assertEqual(len(imported.info.fingerprint), 64)

    def test_mismatched_pair_is_rejected_without_creating_project_files(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            private_path, _ = write_key_pair(root / "source", "alpha")
            _, other_public = write_key_pair(root / "source", "beta")
            destination = root / "projects" / "alpha"

            with self.assertRaisesRegex(LicenseIssueError, "matching pair"):
                import_key_pair(private_path, other_public, destination)

            self.assertFalse((destination / "private.pem").exists())
            self.assertFalse((destination / "public.pem").exists())

    def test_encrypted_private_key_requires_and_accepts_password(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            private_path, public_path = write_key_pair(
                root / "source",
                "encrypted",
                password=b"correct horse battery staple",
            )

            with self.assertRaises(KeyPasswordRequiredError):
                inspect_key_pair(private_path, public_path)
            with self.assertRaises(LicenseIssueError):
                inspect_key_pair(private_path, public_path, password=b"wrong")

            info = inspect_key_pair(
                private_path,
                public_path,
                password=b"correct horse battery staple",
            )
            self.assertTrue(info.private_key_encrypted)

    def test_existing_pair_requires_explicit_overwrite(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            first = write_key_pair(root / "source", "first")
            second = write_key_pair(root / "source", "second")
            destination = root / "projects" / "alpha"
            original = import_key_pair(*first, destination)

            with self.assertRaisesRegex(LicenseIssueError, "Confirm replacement"):
                import_key_pair(*second, destination)

            self.assertEqual(
                original.public_key_path.read_bytes(),
                first[1].read_bytes(),
            )
            replacement = import_key_pair(*second, destination, overwrite=True)
            self.assertEqual(replacement.public_key_path.read_bytes(), second[1].read_bytes())

    def test_failed_second_install_restores_previous_pair(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            first = write_key_pair(root / "source", "first")
            second = write_key_pair(root / "source", "second")
            destination = root / "projects" / "alpha"
            imported = import_key_pair(*first, destination)
            old_private = imported.private_key_path.read_bytes()
            old_public = imported.public_key_path.read_bytes()
            real_replace = os.replace

            def replace_with_public_failure(source: str | Path, target: str | Path) -> None:
                source_path = Path(source)
                target_path = Path(target)
                if (
                    source_path.name.startswith(".public.pem.")
                    and target_path.name == "public.pem"
                ):
                    raise OSError("simulated public-key install failure")
                real_replace(source, target)

            with (
                patch("license_admin.key_store.os.replace", replace_with_public_failure),
                self.assertRaisesRegex(LicenseIssueError, "Unable to import"),
            ):
                import_key_pair(*second, destination, overwrite=True)

            self.assertEqual(imported.private_key_path.read_bytes(), old_private)
            self.assertEqual(imported.public_key_path.read_bytes(), old_public)

    def test_imports_are_isolated_between_project_directories(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            alpha_pair = write_key_pair(root / "source", "alpha")
            beta_pair = write_key_pair(root / "source", "beta")

            alpha = import_key_pair(*alpha_pair, root / "projects" / "alpha")
            beta = import_key_pair(*beta_pair, root / "projects" / "beta")

            self.assertNotEqual(alpha.info.fingerprint, beta.info.fingerprint)
            self.assertNotEqual(
                alpha.public_key_path.read_bytes(),
                beta.public_key_path.read_bytes(),
            )


if __name__ == "__main__":
    unittest.main()
