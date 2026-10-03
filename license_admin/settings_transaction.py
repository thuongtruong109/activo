"""All-or-nothing staging and commit for Settings changes."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
from uuid import uuid4

from issue_license import LicenseIssueError
from license_admin.key_store import (
    PRIVATE_KEY_FILENAME,
    PUBLIC_KEY_FILENAME,
    ImportedKeyPair,
    public_key_fingerprint,
)
from license_admin.windows_security import restrict_to_current_user
from license_admin.service_account_store import (
    ImportedServiceAccount,
    inspect_service_account,
)
from license_admin.settings import AdminSettings, ProjectStore


SETTINGS_ASSET_DIRECTORY = ".settings-assets"


class SettingsTransaction:
    """Keep imported secrets isolated until one atomic profile-pointer switch."""

    def __init__(self, project_directory: Path) -> None:
        self._project_directory = project_directory
        self._transaction_id = uuid4().hex
        self._staging_root: Path | None = None
        self._staged_key_pair: ImportedKeyPair | None = None
        self._staged_key_digests: tuple[str, str] | None = None
        self._staged_service_account: ImportedServiceAccount | None = None
        self._staged_service_account_digest: str | None = None
        self._closed = False

    @property
    def key_staging_directory(self) -> Path:
        return self._ensure_staging_root() / "keys"

    @property
    def credential_staging_directory(self) -> Path:
        return self._ensure_staging_root() / "credentials"

    @property
    def asset_directory(self) -> Path:
        return (
            self._project_directory
            / SETTINGS_ASSET_DIRECTORY
            / self._transaction_id
        )

    @property
    def private_key_path(self) -> Path:
        return self.asset_directory / PRIVATE_KEY_FILENAME

    @property
    def public_key_path(self) -> Path:
        return self.asset_directory / PUBLIC_KEY_FILENAME

    @property
    def service_account_path(self) -> Path:
        return self.asset_directory / "service-account.json"

    def register_key_pair(self, imported: ImportedKeyPair) -> None:
        self._ensure_open()
        expected = self.key_staging_directory.resolve(strict=False)
        if (
            imported.private_key_path.parent.resolve(strict=False) != expected
            or imported.public_key_path.parent.resolve(strict=False) != expected
        ):
            raise LicenseIssueError("The key pair is outside this settings staging area.")
        digests = (
            self._file_digest(imported.private_key_path),
            self._file_digest(imported.public_key_path),
        )
        self._staged_key_pair = imported
        self._staged_key_digests = digests

    def register_service_account(self, imported: ImportedServiceAccount) -> None:
        self._ensure_open()
        if imported.path.parent.resolve(
            strict=False
        ) != self.credential_staging_directory.resolve(strict=False):
            raise LicenseIssueError(
                "The service account is outside this settings staging area."
            )
        digest = self._file_digest(imported.path)
        self._staged_service_account = imported
        self._staged_service_account_digest = digest

    def uses_staged_key_paths(self, private_path: Path, public_path: Path) -> bool:
        return self._staged_key_pair is not None and (
            private_path.resolve(strict=False),
            public_path.resolve(strict=False),
        ) == (
            self.private_key_path.resolve(strict=False),
            self.public_key_path.resolve(strict=False),
        )

    def uses_staged_service_account(self, path: Path) -> bool:
        return self._staged_service_account is not None and path.resolve(
            strict=False
        ) == self.service_account_path.resolve(strict=False)

    def commit(
        self,
        project_store: ProjectStore,
        values: AdminSettings,
    ) -> AdminSettings:
        """Publish staged assets, then atomically switch project.json to them."""
        self._ensure_open()
        expected_project_directory = project_store.project_directory(
            values.project_id
        ).resolve(strict=False)
        if expected_project_directory != self._project_directory.resolve(strict=False):
            raise LicenseIssueError(
                "The settings transaction does not belong to this project."
            )
        use_keys = self.uses_staged_key_paths(
            values.signing_key_path,
            values.public_key_path,
        )
        use_credentials = (
            values.service_account_path is not None
            and self.uses_staged_service_account(values.service_account_path)
        )
        asset_directory = self.asset_directory.resolve(strict=False)
        key_points_to_transaction = (
            values.signing_key_path.parent.resolve(strict=False) == asset_directory
            or values.public_key_path.parent.resolve(strict=False) == asset_directory
        )
        credential_points_to_transaction = (
            values.service_account_path is not None
            and values.service_account_path.parent.resolve(strict=False)
            == asset_directory
        )
        if key_points_to_transaction and not use_keys:
            raise LicenseIssueError("The staged key pair is incomplete or unavailable.")
        if credential_points_to_transaction and not use_credentials:
            raise LicenseIssueError(
                "The staged service account is incomplete or unavailable."
            )
        pending_directory: Path | None = None
        published_directory = False
        try:
            committed = values
            if use_keys or use_credentials:
                assets_root = self.asset_directory.parent
                assets_root.mkdir(parents=True, exist_ok=True)
                restrict_to_current_user(assets_root)
                pending_directory = assets_root / f".pending-{self._transaction_id}"
                if pending_directory.exists() or self.asset_directory.exists():
                    raise LicenseIssueError(
                        "The settings transaction destination already exists."
                    )
                pending_directory.mkdir()
                restrict_to_current_user(pending_directory)

                if use_keys:
                    if (
                        self._staged_key_pair is None
                        or self._staged_key_digests is None
                    ):
                        raise LicenseIssueError("The staged key pair is unavailable.")
                    self._copy_durable(
                        self._staged_key_pair.private_key_path,
                        pending_directory / PRIVATE_KEY_FILENAME,
                        private=True,
                        expected_digest=self._staged_key_digests[0],
                    )
                    self._copy_durable(
                        self._staged_key_pair.public_key_path,
                        pending_directory / PUBLIC_KEY_FILENAME,
                        expected_digest=self._staged_key_digests[1],
                    )
                    if public_key_fingerprint(
                        pending_directory / PUBLIC_KEY_FILENAME
                    ) != self._staged_key_pair.info.fingerprint:
                        raise LicenseIssueError(
                            "The staged public key changed during commit."
                        )
                    committed = replace(
                        committed,
                        signing_key_path=self.private_key_path,
                        public_key_path=self.public_key_path,
                    )

                if use_credentials:
                    if (
                        self._staged_service_account is None
                        or self._staged_service_account_digest is None
                    ):
                        raise LicenseIssueError(
                            "The staged service account is unavailable."
                        )
                    self._copy_durable(
                        self._staged_service_account.path,
                        pending_directory / "service-account.json",
                        private=True,
                        expected_digest=self._staged_service_account_digest,
                    )
                    inspected = inspect_service_account(
                        pending_directory / "service-account.json"
                    )
                    if inspected != self._staged_service_account.info:
                        raise LicenseIssueError(
                            "The staged service account changed during commit."
                        )
                    committed = replace(
                        committed,
                        service_account_path=self.service_account_path,
                    )

                os.replace(pending_directory, self.asset_directory)
                pending_directory = None
                published_directory = True

            self._cleanup_staging()
            project_store.save(committed)
        except (OSError, LicenseIssueError) as exc:
            cleanup_errors: list[str] = []
            published = self.asset_directory if published_directory else None
            for directory in (pending_directory, published):
                if directory is None:
                    continue
                try:
                    shutil.rmtree(directory)
                except OSError as cleanup_exc:
                    cleanup_errors.append(str(cleanup_exc))
            try:
                self.discard()
            except LicenseIssueError as cleanup_exc:
                cleanup_errors.append(str(cleanup_exc))
            detail = (
                f" Cleanup also failed: {'; '.join(cleanup_errors)}"
                if cleanup_errors
                else ""
            )
            if isinstance(exc, LicenseIssueError) and not detail:
                raise
            raise LicenseIssueError(
                f"Unable to commit settings transaction: {exc}.{detail}"
            ) from exc
        self.discard()
        return project_store.load(committed.project_id)

    def discard(self) -> None:
        if self._closed:
            return
        self._cleanup_staging()
        self._closed = True

    def __del__(self) -> None:
        try:
            self.discard()
        except Exception:
            pass

    def _ensure_open(self) -> None:
        if self._closed:
            raise LicenseIssueError("The settings transaction is already closed.")

    def _cleanup_staging(self) -> None:
        if self._staging_root is None:
            return
        try:
            shutil.rmtree(self._staging_root)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise LicenseIssueError(
                f"Unable to discard staged settings files: {exc}"
            ) from exc
        self._staging_root = None

    def _ensure_staging_root(self) -> Path:
        self._ensure_open()
        if self._staging_root is None:
            staging_root: Path | None = None
            try:
                self._project_directory.mkdir(parents=True, exist_ok=True)
                restrict_to_current_user(self._project_directory)
                staging_root = (
                    self._project_directory
                    / f".settings-staging-{self._transaction_id}"
                )
                staging_root.mkdir()
                restrict_to_current_user(staging_root)
                self._staging_root = staging_root
            except (OSError, LicenseIssueError) as exc:
                if staging_root is not None:
                    shutil.rmtree(staging_root, ignore_errors=True)
                raise LicenseIssueError(
                    f"Unable to create settings staging directory: {exc}"
                ) from exc
        return self._staging_root

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        try:
            with path.open("rb") as source:
                while chunk := source.read(128 * 1024):
                    digest.update(chunk)
        except OSError as exc:
            raise LicenseIssueError(
                f"Unable to fingerprint staged file {path.name}: {exc}"
            ) from exc
        return digest.hexdigest()

    @staticmethod
    def _copy_durable(
        source: Path,
        destination: Path,
        *,
        private: bool = False,
        expected_digest: str,
    ) -> None:
        try:
            digest = hashlib.sha256()
            with source.open("rb") as source_stream, destination.open("xb") as target:
                while chunk := source_stream.read(128 * 1024):
                    target.write(chunk)
                    digest.update(chunk)
                target.flush()
                os.fsync(target.fileno())
            if private:
                restrict_to_current_user(destination)
            if digest.hexdigest() != expected_digest:
                raise LicenseIssueError(
                    f"Staged file changed after validation: {source.name}."
                )
        except LicenseIssueError:
            raise
        except OSError as exc:
            raise LicenseIssueError(
                f"Unable to stage {destination.name}: {exc}"
            ) from exc
