"""Classify project data health before the UI is allowed to mutate it."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from issue_license import LicenseIssueError
from license_admin.domain import LicenseRecord, validate_record_signatures
from license_admin.settings import AdminSettings
from license_admin.storage import (
    LicenseDataFailure,
    LicenseDataLoadError,
    LicenseRepository,
)


class ProjectDataState(str, Enum):
    EMPTY = "empty"
    READY = "ready"
    CORRUPTED = "corrupted"
    WRONG_KEY = "wrong_key"
    PERMISSION_DENIED = "permission_denied"
    UNAVAILABLE = "unavailable"

    @property
    def allows_writes(self) -> bool:
        return self in {ProjectDataState.EMPTY, ProjectDataState.READY}


@dataclass(frozen=True, slots=True)
class ProjectDataLoadResult:
    state: ProjectDataState
    records: tuple[LicenseRecord, ...] = ()
    detail: str = ""


_KEY_MISMATCH_ERRORS = frozenset(
    {
        "JWT signature is invalid.",
        "JWT was signed for a different key ID.",
    }
)


def load_project_records(settings: AdminSettings) -> ProjectDataLoadResult:
    """Load and verify data without collapsing failures into an empty project."""
    try:
        raw_records = LicenseRepository(settings.local_csv_path).load()
    except LicenseDataLoadError as exc:
        state = {
            LicenseDataFailure.CORRUPTED: ProjectDataState.CORRUPTED,
            LicenseDataFailure.PERMISSION_DENIED: ProjectDataState.PERMISSION_DENIED,
            LicenseDataFailure.UNAVAILABLE: ProjectDataState.UNAVAILABLE,
        }[exc.failure]
        return ProjectDataLoadResult(state=state, detail=str(exc))

    if not raw_records:
        return ProjectDataLoadResult(state=ProjectDataState.EMPTY)

    try:
        public_key = settings.public_key_path.read_bytes()
    except PermissionError as exc:
        return ProjectDataLoadResult(
            state=ProjectDataState.PERMISSION_DENIED,
            detail=f"Permission denied while reading {settings.public_key_path}: {exc}",
        )
    except OSError as exc:
        return ProjectDataLoadResult(
            state=ProjectDataState.WRONG_KEY,
            detail=f"Unable to read verification key {settings.public_key_path}: {exc}",
        )

    try:
        verified = validate_record_signatures(
            raw_records,
            public_key,
            expected_issuer=settings.issuer,
            expected_audience=settings.audience,
        )
    except LicenseIssueError as exc:
        return ProjectDataLoadResult(
            state=ProjectDataState.WRONG_KEY,
            detail=str(exc),
        )

    if all(record.parse_error is None for record in raw_records) and all(
        record.parse_error in _KEY_MISMATCH_ERRORS for record in verified
    ):
        return ProjectDataLoadResult(
            state=ProjectDataState.WRONG_KEY,
            records=tuple(verified),
            detail="Every license was rejected by the configured public key.",
        )

    return ProjectDataLoadResult(
        state=ProjectDataState.READY,
        records=tuple(verified),
    )
