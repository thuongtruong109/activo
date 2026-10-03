"""Durable local revocation journal and explicit publication lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable

from issue_license import LicenseIssueError, normalize_hwid
from license_admin.atomic_file import atomic_write_bytes, atomic_write_text
from license_admin.domain import LicenseRecord
from license_admin.feed_manifest import FeedTombstone


REVOCATION_SCHEMA_VERSION = 1


class RevocationPhase(str, Enum):
    PENDING = "pending"
    REVOKED = "revoked"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class RevocationEntry:
    hwid: str
    jti: str | None
    username: str
    revoked_at: datetime
    phase: RevocationPhase
    published_at: datetime | None = None
    published_revision: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.hwid, str):
            raise LicenseIssueError("Revocation HWID must be text.")
        if not isinstance(self.username, str):
            raise LicenseIssueError("Revocation username must be text.")
        if not isinstance(self.phase, RevocationPhase):
            raise LicenseIssueError("Revocation phase is invalid.")
        if not isinstance(self.revoked_at, datetime):
            raise LicenseIssueError("Revocation revoked_at must be a datetime.")
        if self.jti is not None and (
            not isinstance(self.jti, str)
            or not 16 <= len(self.jti) <= 128
            or any(
                character not in "0123456789abcdefABCDEF"
                for character in self.jti
            )
        ):
            raise LicenseIssueError(
                "Revocation JTI must contain 16-128 hexadecimal characters."
            )
        if self.published_at is not None and not isinstance(
            self.published_at, datetime
        ):
            raise LicenseIssueError("Revocation published_at must be a datetime.")
        if self.published_revision is not None and (
            isinstance(self.published_revision, bool)
            or not isinstance(self.published_revision, int)
        ):
            raise LicenseIssueError("Revocation publication revision must be an integer.")
        object.__setattr__(self, "hwid", normalize_hwid(self.hwid))
        if self.jti is not None:
            object.__setattr__(self, "jti", self.jti.casefold())
        object.__setattr__(
            self,
            "revoked_at",
            _as_utc(self.revoked_at, "revoked_at"),
        )
        if self.published_at is not None:
            object.__setattr__(
                self,
                "published_at",
                _as_utc(self.published_at, "published_at"),
            )
        if self.phase is RevocationPhase.PUBLISHED:
            if self.published_at is None or self.published_revision is None:
                raise LicenseIssueError(
                    "A published revocation requires publication time and revision."
                )
        elif self.published_at is not None or self.published_revision is not None:
            raise LicenseIssueError(
                "An unpublished revocation cannot contain publication metadata."
            )
        if self.published_revision is not None and self.published_revision < 1:
            raise LicenseIssueError("Published revocation revision must be positive.")

    def tombstone(self) -> FeedTombstone:
        return FeedTombstone(self.hwid, self.jti, self.revoked_at)


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LicenseIssueError(f"Revocation {label} must include a timezone.")
    return value.astimezone(timezone.utc)


def request_revocation(
    entries: Iterable[RevocationEntry],
    record: LicenseRecord,
    *,
    now: datetime | None = None,
) -> tuple[RevocationEntry, ...]:
    existing = {entry.hwid: entry for entry in entries}
    if record.hwid in existing:
        raise LicenseIssueError("This license already has a revocation entry.")
    existing[record.hwid] = RevocationEntry(
        hwid=record.hwid,
        jti=record.jti,
        username=record.username,
        revoked_at=_as_utc(now or datetime.now(timezone.utc), "revoked_at"),
        phase=RevocationPhase.PENDING,
    )
    return tuple(sorted(existing.values(), key=lambda item: item.hwid))


def mark_revoked(
    entries: Iterable[RevocationEntry],
) -> tuple[RevocationEntry, ...]:
    return tuple(
        replace(entry, phase=RevocationPhase.REVOKED)
        if entry.phase is RevocationPhase.PENDING
        else entry
        for entry in entries
    )


def mark_published(
    entries: Iterable[RevocationEntry],
    *,
    revision: int,
    published_at: datetime,
) -> tuple[RevocationEntry, ...]:
    timestamp = _as_utc(published_at, "published_at")
    return tuple(
        replace(
            entry,
            phase=RevocationPhase.PUBLISHED,
            published_at=timestamp,
            published_revision=revision,
        )
        if entry.phase is RevocationPhase.REVOKED
        else entry
        for entry in entries
    )


def merge_published_tombstones(
    entries: Iterable[RevocationEntry],
    tombstones: Iterable[FeedTombstone],
    *,
    revision: int,
    published_at: datetime,
) -> tuple[RevocationEntry, ...]:
    """Merge remote tombstones without discarding newer local pending intent."""
    merged = {entry.hwid: entry for entry in entries}
    timestamp = _as_utc(published_at, "published_at")
    for tombstone in tombstones:
        current = merged.get(tombstone.hwid)
        if current is not None and current.phase is not RevocationPhase.PUBLISHED:
            continue
        merged[tombstone.hwid] = RevocationEntry(
            hwid=tombstone.hwid,
            jti=tombstone.jti,
            username=current.username if current is not None else "",
            revoked_at=tombstone.revoked_at,
            phase=RevocationPhase.PUBLISHED,
            published_at=timestamp,
            published_revision=revision,
        )
    return tuple(sorted(merged.values(), key=lambda item: item.hwid))


class RevocationRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def beside(cls, license_csv_path: Path) -> RevocationRepository:
        return cls(license_csv_path.with_name(f"{license_csv_path.stem}.revocations.json"))

    def load(self) -> tuple[RevocationEntry, ...]:
        if not self.path.exists():
            return ()
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LicenseIssueError(f"Unable to read revocation journal: {exc}") from exc
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise LicenseIssueError("Revocation journal schema is unsupported.")
        raw_entries = document.get("revocations")
        if not isinstance(raw_entries, list):
            raise LicenseIssueError("Revocation journal must contain a list.")
        entries = tuple(self._parse_entry(value) for value in raw_entries)
        self._validate(entries)
        return entries

    def save(self, entries: Iterable[RevocationEntry]) -> tuple[RevocationEntry, ...]:
        snapshot = tuple(sorted(entries, key=lambda item: item.hwid))
        self._validate(snapshot)
        document = {
            "schema_version": REVOCATION_SCHEMA_VERSION,
            "revocations": [self._entry_document(entry) for entry in snapshot],
        }
        try:
            atomic_write_text(
                self.path,
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise LicenseIssueError(f"Unable to save revocation journal: {exc}") from exc
        return snapshot

    def snapshot_bytes(self) -> bytes | None:
        try:
            return self.path.read_bytes() if self.path.exists() else None
        except OSError as exc:
            raise LicenseIssueError(f"Unable to snapshot revocation journal: {exc}") from exc

    def restore_bytes(self, snapshot: bytes | None) -> None:
        try:
            if snapshot is None:
                self.path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(
                    self.path,
                    snapshot,
                    create_backup=False,
                )
        except OSError as exc:
            raise LicenseIssueError(f"Unable to restore revocation journal: {exc}") from exc

    @staticmethod
    def _validate(entries: tuple[RevocationEntry, ...]) -> None:
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, RevocationEntry):
                raise LicenseIssueError("Revocation journal contains an invalid entry.")
            if entry.hwid in seen:
                raise LicenseIssueError(
                    f"Revocation journal contains duplicate HWID {entry.hwid!r}."
                )
            seen.add(entry.hwid)

    @staticmethod
    def _entry_document(entry: RevocationEntry) -> dict[str, Any]:
        return {
            "hwid": entry.hwid,
            "jti": entry.jti,
            "username": entry.username,
            "revoked_at": entry.revoked_at.isoformat().replace("+00:00", "Z"),
            "phase": entry.phase.value,
            "published_at": (
                entry.published_at.isoformat().replace("+00:00", "Z")
                if entry.published_at is not None
                else None
            ),
            "published_revision": entry.published_revision,
        }

    @staticmethod
    def _parse_entry(raw: Any) -> RevocationEntry:
        if not isinstance(raw, dict):
            raise LicenseIssueError("Revocation entry must be an object.")
        revoked_raw = raw.get("revoked_at")
        published_raw = raw.get("published_at")
        phase_raw = raw.get("phase")
        hwid_raw = raw.get("hwid")
        if not isinstance(revoked_raw, str) or not isinstance(hwid_raw, str):
            raise LicenseIssueError("Revocation entry is incomplete or invalid.")
        if published_raw is not None and not isinstance(published_raw, str):
            raise LicenseIssueError("Revocation publication time must be text or null.")
        if not isinstance(phase_raw, str):
            raise LicenseIssueError("Revocation phase must be text.")
        try:
            revoked_at = datetime.fromisoformat(revoked_raw.replace("Z", "+00:00"))
            published_at = (
                datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                if published_raw is not None
                else None
            )
            phase = RevocationPhase(phase_raw)
        except ValueError as exc:
            raise LicenseIssueError("Revocation entry is incomplete or invalid.") from exc
        jti = raw.get("jti")
        username = raw.get("username", "")
        published_revision = raw.get("published_revision")
        if jti is not None and not isinstance(jti, str):
            raise LicenseIssueError("Revocation JTI must be text or null.")
        return RevocationEntry(
            hwid=hwid_raw,
            jti=jti,
            username=username,
            revoked_at=revoked_at,
            phase=phase,
            published_at=published_at,
            published_revision=published_revision,
        )
