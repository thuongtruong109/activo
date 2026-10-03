"""Independent key identity and lifecycle metadata for one project."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from issue_license import LicenseIssueError
from license_admin.atomic_file import atomic_write_text
from license_admin.key_store import public_key_fingerprint


KEYRING_FILENAME = "keyring.json"
KEYRING_SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class KeyIdentity:
    key_id: str
    fingerprint: str
    public_key_path: Path
    created_at: str
    rotated_at: str | None
    revoked_at: str | None


@dataclass(frozen=True, slots=True)
class KeyRing:
    active_key_id: str | None
    keys: tuple[KeyIdentity, ...]

    @property
    def active(self) -> KeyIdentity | None:
        return next(
            (key for key in self.keys if key.key_id == self.active_key_id),
            None,
        )


class KeyIdentityStore:
    """Persist non-secret identity, rotation and revocation history."""

    def __init__(self, project_directory: Path) -> None:
        self.project_directory = project_directory.resolve(strict=False)
        self.path = self.project_directory / KEYRING_FILENAME

    def load(self) -> KeyRing:
        if not self.path.exists():
            return KeyRing(None, ())
        try:
            document = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LicenseIssueError(f"Unable to read key identity metadata: {exc}") from exc
        if not isinstance(document, dict) or document.get("schema_version") != 1:
            raise LicenseIssueError("Key identity metadata has an unsupported schema.")
        active = document.get("active_key_id")
        if active is not None and not isinstance(active, str):
            raise LicenseIssueError("Key identity active_key_id must be text or null.")
        raw_keys = document.get("keys")
        if not isinstance(raw_keys, list):
            raise LicenseIssueError("Key identity metadata must contain a keys list.")
        keys: list[KeyIdentity] = []
        seen: set[str] = set()
        for raw in raw_keys:
            if not isinstance(raw, dict):
                raise LicenseIssueError("Key identity entry must be an object.")
            key = self._parse_identity(raw)
            if key.key_id in seen:
                raise LicenseIssueError("Key identity metadata contains duplicate key IDs.")
            seen.add(key.key_id)
            keys.append(key)
        ring = KeyRing(active, tuple(keys))
        if active is not None and ring.active is None:
            raise LicenseIssueError("Active key identity is missing from the keyring.")
        if ring.active is not None and ring.active.revoked_at is not None:
            raise LicenseIssueError("The active signing key is revoked.")
        return ring

    def snapshot(self) -> str | None:
        """Capture the exact keyring document for transaction rollback."""
        if not self.path.exists():
            return None
        try:
            return self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise LicenseIssueError(
                f"Unable to snapshot key identity metadata: {exc}"
            ) from exc

    def restore(self, snapshot: str | None) -> None:
        """Restore a prior keyring snapshot after a related write fails."""
        try:
            if snapshot is None:
                self.path.unlink(missing_ok=True)
            else:
                atomic_write_text(
                    self.path,
                    snapshot,
                    encoding="utf-8",
                    create_backup=False,
                )
        except OSError as exc:
            raise LicenseIssueError(
                f"Unable to restore key identity metadata: {exc}"
            ) from exc

    def reconcile_active(self, public_key_path: Path) -> KeyRing:
        """Make the selected public key active and record a rotation if needed."""
        if not public_key_path.is_file():
            return self.load()
        fingerprint = public_key_fingerprint(public_key_path)
        key_id = fingerprint[:16]
        ring = self.load()
        if ring.active_key_id == key_id:
            return ring
        now = _utc_now()
        updated: list[KeyIdentity] = []
        found = False
        for key in ring.keys:
            if key.key_id == key_id:
                if key.revoked_at is not None:
                    raise LicenseIssueError(
                        f"Signing key {key_id} was revoked at {key.revoked_at}."
                    )
                updated.append(
                    KeyIdentity(
                        key_id=key.key_id,
                        fingerprint=key.fingerprint,
                        public_key_path=public_key_path.resolve(strict=False),
                        created_at=key.created_at,
                        rotated_at=None,
                        revoked_at=None,
                    )
                )
                found = True
            elif key.key_id == ring.active_key_id and key.rotated_at is None:
                updated.append(
                    KeyIdentity(
                        key_id=key.key_id,
                        fingerprint=key.fingerprint,
                        public_key_path=key.public_key_path,
                        created_at=key.created_at,
                        rotated_at=now,
                        revoked_at=key.revoked_at,
                    )
                )
            else:
                updated.append(key)
        if not found:
            try:
                created_at = datetime.fromtimestamp(
                    public_key_path.stat().st_mtime,
                    tz=timezone.utc,
                ).isoformat().replace("+00:00", "Z")
            except OSError:
                created_at = now
            updated.append(
                KeyIdentity(
                    key_id=key_id,
                    fingerprint=fingerprint,
                    public_key_path=public_key_path.resolve(strict=False),
                    created_at=created_at,
                    rotated_at=None,
                    revoked_at=None,
                )
            )
        reconciled = KeyRing(key_id, tuple(updated))
        self._save(reconciled)
        return reconciled

    def revoke(self, key_id: str) -> KeyRing:
        ring = self.load()
        if key_id == ring.active_key_id:
            raise LicenseIssueError("Rotate away from a key before revoking it.")
        found = False
        now = _utc_now()
        keys: list[KeyIdentity] = []
        for key in ring.keys:
            if key.key_id == key_id:
                found = True
                keys.append(
                    KeyIdentity(
                        key_id=key.key_id,
                        fingerprint=key.fingerprint,
                        public_key_path=key.public_key_path,
                        created_at=key.created_at,
                        rotated_at=key.rotated_at,
                        revoked_at=key.revoked_at or now,
                    )
                )
            else:
                keys.append(key)
        if not found:
            raise LicenseIssueError(f"Unknown key ID: {key_id}")
        updated = KeyRing(ring.active_key_id, tuple(keys))
        self._save(updated)
        return updated

    def trusted_public_key_paths(
        self,
        ring: KeyRing | None = None,
    ) -> tuple[Path, ...]:
        ring = ring or self.load()
        active = ring.active
        candidates = (
            ([active] if active is not None else [])
            + [key for key in ring.keys if key is not active]
        )
        return tuple(
            key.public_key_path
            for key in candidates
            if key.revoked_at is None and key.public_key_path.is_file()
        )

    def _save(self, ring: KeyRing) -> None:
        document = {
            "schema_version": KEYRING_SCHEMA_VERSION,
            "active_key_id": ring.active_key_id,
            "keys": [self._identity_document(key) for key in ring.keys],
        }
        try:
            atomic_write_text(
                self.path,
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise LicenseIssueError(f"Unable to save key identity metadata: {exc}") from exc

    def _stored_path(self, path: Path) -> str:
        try:
            return path.resolve(strict=False).relative_to(self.project_directory).as_posix()
        except ValueError:
            return str(path.resolve(strict=False))

    def _resolved_path(self, value: str) -> Path:
        candidate = Path(value)
        return candidate if candidate.is_absolute() else self.project_directory / candidate

    def _identity_document(self, key: KeyIdentity) -> dict[str, str | None]:
        return {
            "key_id": key.key_id,
            "fingerprint": key.fingerprint,
            "public_key": self._stored_path(key.public_key_path),
            "created_at": key.created_at,
            "rotated_at": key.rotated_at,
            "revoked_at": key.revoked_at,
        }

    def _parse_identity(self, raw: dict[str, Any]) -> KeyIdentity:
        required = ("key_id", "fingerprint", "public_key", "created_at")
        if any(not isinstance(raw.get(field), str) or not raw[field] for field in required):
            raise LicenseIssueError("Key identity entry is incomplete.")
        rotated = raw.get("rotated_at")
        revoked = raw.get("revoked_at")
        if rotated is not None and not isinstance(rotated, str):
            raise LicenseIssueError("Key rotated_at must be text or null.")
        if revoked is not None and not isinstance(revoked, str):
            raise LicenseIssueError("Key revoked_at must be text or null.")
        fingerprint = str(raw["fingerprint"])
        key_id = str(raw["key_id"])
        if len(fingerprint) != 64 or key_id != fingerprint[:16]:
            raise LicenseIssueError("Key identity fingerprint or key ID is invalid.")
        return KeyIdentity(
            key_id=key_id,
            fingerprint=fingerprint,
            public_key_path=self._resolved_path(str(raw["public_key"])),
            created_at=str(raw["created_at"]),
            rotated_at=rotated,
            revoked_at=revoked,
        )

