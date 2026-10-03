"""Atomic local persistence for license-admin drafts."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Iterable

from issue_license import LicenseIssueError
from license_admin.atomic_file import atomic_write_text, backup_directory
from license_admin.domain import (
    LicenseRecord,
    parse_signed_csv,
    serialize_signed_csv,
)


class LicenseDataFailure(str, Enum):
    CORRUPTED = "corrupted"
    PERMISSION_DENIED = "permission_denied"
    UNAVAILABLE = "unavailable"


class LicenseDataLoadError(LicenseIssueError):
    """A local-data read failure with a stable recovery category."""

    def __init__(self, failure: LicenseDataFailure, message: str) -> None:
        super().__init__(message)
        self.failure = failure


class LicenseRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[LicenseRecord]:
        try:
            self.path.stat()
        except FileNotFoundError:
            return []
        except PermissionError as exc:
            raise LicenseDataLoadError(
                LicenseDataFailure.PERMISSION_DENIED,
                f"Permission denied while checking {self.path}: {exc}",
            ) from exc
        except OSError as exc:
            raise LicenseDataLoadError(
                LicenseDataFailure.UNAVAILABLE,
                f"Unable to check {self.path}: {exc}",
            ) from exc
        try:
            if not self.path.is_file():
                raise OSError("The configured data path is not a file.")
            content = self.path.read_text(encoding="utf-8-sig")
        except FileNotFoundError as exc:
            raise LicenseDataLoadError(
                LicenseDataFailure.UNAVAILABLE,
                f"The data file disappeared while opening {self.path}: {exc}",
            ) from exc
        except PermissionError as exc:
            raise LicenseDataLoadError(
                LicenseDataFailure.PERMISSION_DENIED,
                f"Permission denied while reading {self.path}: {exc}",
            ) from exc
        except OSError as exc:
            raise LicenseDataLoadError(
                LicenseDataFailure.UNAVAILABLE,
                f"Unable to read {self.path}: {exc}",
            ) from exc
        except UnicodeError as exc:
            raise LicenseDataLoadError(
                LicenseDataFailure.CORRUPTED,
                f"The data file is not valid UTF-8: {self.path}: {exc}",
            ) from exc
        try:
            return parse_signed_csv(content)
        except LicenseIssueError as exc:
            raise LicenseDataLoadError(
                LicenseDataFailure.CORRUPTED,
                f"The data file is corrupted: {self.path}: {exc}",
            ) from exc

    def save(self, records: Iterable[LicenseRecord]) -> None:
        content = serialize_signed_csv(records)
        try:
            atomic_write_text(self.path, content)
        except OSError as exc:
            raise LicenseIssueError(f"Unable to save {self.path}: {exc}") from exc

    @property
    def backup_directory(self) -> Path:
        return backup_directory(self.path)
