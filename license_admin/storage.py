"""Atomic local persistence for license-admin drafts."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
from typing import Iterable

from issue_license import LicenseIssueError
from license_admin.domain import (
    LicenseRecord,
    parse_signed_csv,
    serialize_signed_csv,
)


class LicenseRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[LicenseRecord]:
        if not self.path.exists():
            return []
        try:
            return parse_signed_csv(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError) as exc:
            raise LicenseIssueError(f"Unable to read {self.path}: {exc}") from exc

    def save(self, records: Iterable[LicenseRecord]) -> None:
        content = serialize_signed_csv(records)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=str(self.path.parent),
                text=True,
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            try:
                temporary_path.write_text(content, encoding="utf-8", newline="")
                os.replace(temporary_path, self.path)
            finally:
                temporary_path.unlink(missing_ok=True)
        except OSError as exc:
            raise LicenseIssueError(f"Unable to save {self.path}: {exc}") from exc
