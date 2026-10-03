"""Pure record migration helpers used after signing-key rotation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError, issue_license_until
from license_admin.domain import LicenseRecord, inspect_license


@dataclass(frozen=True, slots=True)
class ResignResult:
    records: tuple[LicenseRecord, ...]
    resigned_count: int
    unchanged_count: int


def resign_unexpired_records(
    records: Iterable[LicenseRecord],
    private_key: rsa.RSAPrivateKey,
    *,
    issuer: str,
    audience: str,
    now: datetime | None = None,
) -> ResignResult:
    """Re-sign valid, unexpired records while retaining expired/invalid history."""
    issued_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    migrated: list[LicenseRecord] = []
    resigned_count = 0
    for record in records:
        if (
            record.parse_error is not None
            or record.expires_at is None
            or record.expires_at <= issued_at
        ):
            migrated.append(record)
            continue
        token = issue_license_until(
            private_key,
            username=record.username,
            hwid=record.hwid,
            expires_at=record.expires_at,
            issuer=issuer,
            audience=audience,
            now=issued_at,
        )
        resigned = inspect_license(
            record.hwid,
            token,
            public_key_pem=public_pem,
            expected_issuer=issuer,
            expected_audience=audience,
        )
        if resigned.parse_error is not None:
            raise LicenseIssueError(
                f"Re-signed license verification failed: {resigned.parse_error}"
            )
        migrated.append(resigned)
        resigned_count += 1
    return ResignResult(
        records=tuple(migrated),
        resigned_count=resigned_count,
        unchanged_count=len(migrated) - resigned_count,
    )

