"""Signed, freshness-bound license feed manifests and tombstones."""

from __future__ import annotations

import base64
import binascii
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
from typing import Any, Iterable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from issue_license import LicenseIssueError, normalize_hwid
from license_admin.atomic_file import atomic_write_text
from license_admin.domain import LicenseRecord, parse_signed_csv, records_digest
from license_admin.limits import MAX_LICENSE_FEED_BYTES, MAX_LICENSE_FEED_ROWS


FEED_SCHEMA = "activo-license-feed-v2"
MANIFEST_TYPE = "ACTIVO-FEED-MANIFEST"
FEED_COLUMNS = ("entry_type", "hwid", "token", "jti", "revoked_at")
DEFAULT_FRESHNESS = timedelta(days=7)
MAX_FRESHNESS = timedelta(days=31)
MAX_CLOCK_SKEW = timedelta(minutes=5)


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LicenseIssueError(f"{label} must include a timezone.")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> int:
    return int(_as_utc(value, "Manifest time").timestamp())


def _timestamp_claim(value: Any, name: str) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LicenseIssueError(f"Feed manifest {name} must be an integer timestamp.")
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OSError, OverflowError, ValueError) as exc:
        raise LicenseIssueError(f"Feed manifest {name} is out of range.") from exc


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_b64url(value: str) -> bytes:
    try:
        encoded = value.encode("ascii")
        return base64.b64decode(
            encoded + b"=" * (-len(encoded) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise LicenseIssueError("Feed manifest uses invalid base64url encoding.") from exc


def _json_object(value: bytes, label: str) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise LicenseIssueError(
                    f"Feed manifest {label} contains duplicate field {key!r}."
                )
            result[key] = item
        return result

    try:
        decoded = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LicenseIssueError(f"Feed manifest {label} is invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise LicenseIssueError(f"Feed manifest {label} must be an object.")
    return decoded


@dataclass(frozen=True, slots=True)
class FeedTombstone:
    hwid: str
    jti: str | None
    revoked_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.hwid, str):
            raise LicenseIssueError("A revocation HWID must be text.")
        if not isinstance(self.revoked_at, datetime):
            raise LicenseIssueError("A revocation timestamp must be a datetime.")
        object.__setattr__(self, "hwid", normalize_hwid(self.hwid))
        object.__setattr__(self, "revoked_at", _as_utc(self.revoked_at, "revoked_at"))
        if self.jti is not None and (
            not 16 <= len(self.jti) <= 128
            or any(character not in "0123456789abcdefABCDEF" for character in self.jti)
        ):
            raise LicenseIssueError("A revocation JTI must contain 16-128 hexadecimal characters.")
        if self.jti is not None:
            object.__setattr__(self, "jti", self.jti.casefold())


@dataclass(frozen=True, slots=True)
class FeedManifest:
    revision: int
    generated_at: datetime
    expires_at: datetime
    issuer: str
    audience: str
    key_id: str
    active_digest: str
    revoked_digest: str
    active_count: int
    revoked_count: int
    token: str


@dataclass(frozen=True, slots=True)
class FeedDocument:
    records: tuple[LicenseRecord, ...]
    tombstones: tuple[FeedTombstone, ...]
    manifest_token: str = ""
    manifest: FeedManifest | None = None

    def is_revoked(self, *, hwid: str, jti: str | None = None) -> bool:
        normalized_hwid = normalize_hwid(hwid)
        normalized_jti = jti.casefold() if jti is not None else None
        return any(
            item.hwid == normalized_hwid
            or (
                normalized_jti is not None
                and item.jti is not None
                and item.jti.casefold() == normalized_jti
            )
            for item in self.tombstones
        )


def tombstones_digest(tombstones: Iterable[FeedTombstone]) -> str:
    canonical = [
        {
            "hwid": item.hwid,
            "jti": item.jti,
            "revoked_at": _timestamp(item.revoked_at),
        }
        for item in sorted(tombstones, key=lambda item: (item.hwid, item.jti or ""))
    ]
    encoded = json.dumps(
        canonical,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def publication_content_digest(
    records: Iterable[LicenseRecord],
    tombstones: Iterable[FeedTombstone],
) -> str:
    active_digest = records_digest(records)
    revoked_digest = tombstones_digest(tombstones)
    return hashlib.sha256(
        f"{active_digest}:{revoked_digest}".encode("ascii")
    ).hexdigest()


def _public_key_id(key: rsa.RSAPublicKey) -> str:
    material = key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(material).hexdigest()[:16]


def sign_feed(
    records: Iterable[LicenseRecord],
    tombstones: Iterable[FeedTombstone],
    private_key: rsa.RSAPrivateKey,
    *,
    revision: int,
    issuer: str,
    audience: str,
    generated_at: datetime | None = None,
    freshness: timedelta = DEFAULT_FRESHNESS,
) -> FeedDocument:
    """Return an immutable feed whose manifest signs all publishable content."""
    if not isinstance(private_key, rsa.RSAPrivateKey) or private_key.key_size < 2_048:
        raise LicenseIssueError("Feed signing requires a strong RSA private key.")
    if revision < 1:
        raise LicenseIssueError("Feed manifest revision must be positive.")
    if not issuer.strip() or not audience.strip():
        raise LicenseIssueError("Feed manifest issuer and audience are required.")
    if freshness <= timedelta(0) or freshness > MAX_FRESHNESS:
        raise LicenseIssueError("Feed freshness must be between 1 second and 31 days.")
    ordered_records = tuple(
        sorted(records, key=lambda item: (item.username.casefold(), item.hwid))
    )
    ordered_tombstones = tuple(
        sorted(tombstones, key=lambda item: (item.hwid, item.jti or ""))
    )
    _validate_disjoint(ordered_records, ordered_tombstones)
    now = _as_utc(generated_at or datetime.now(timezone.utc), "generated_at")
    expires_at = now + freshness
    public_key = private_key.public_key()
    key_id = _public_key_id(public_key)
    header = {
        "alg": "RS256",
        "kid": key_id,
        "typ": MANIFEST_TYPE,
    }
    payload = {
        "active_count": len(ordered_records),
        "active_sha256": records_digest(ordered_records),
        "aud": audience.strip(),
        "exp": _timestamp(expires_at),
        "generated_at": _timestamp(now),
        "iss": issuer.strip(),
        "revision": revision,
        "revoked_count": len(ordered_tombstones),
        "revoked_sha256": tombstones_digest(ordered_tombstones),
        "schema": FEED_SCHEMA,
    }
    encoded_header = _b64url(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _b64url(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    token = f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"
    manifest = FeedManifest(
        revision=revision,
        generated_at=now,
        expires_at=expires_at,
        issuer=issuer.strip(),
        audience=audience.strip(),
        key_id=key_id,
        active_digest=str(payload["active_sha256"]),
        revoked_digest=str(payload["revoked_sha256"]),
        active_count=len(ordered_records),
        revoked_count=len(ordered_tombstones),
        token=token,
    )
    return FeedDocument(ordered_records, ordered_tombstones, token, manifest)


def _load_verification_keys(
    public_key_pem: bytes | Iterable[bytes],
) -> dict[str, rsa.RSAPublicKey]:
    materials = (public_key_pem,) if isinstance(public_key_pem, bytes) else tuple(public_key_pem)
    keys: dict[str, rsa.RSAPublicKey] = {}
    for material in materials:
        try:
            candidate = serialization.load_pem_public_key(material)
        except (TypeError, ValueError) as exc:
            raise LicenseIssueError("Feed verification public key is invalid.") from exc
        if not isinstance(candidate, rsa.RSAPublicKey) or candidate.key_size < 2_048:
            raise LicenseIssueError("Feed verification key is not a strong RSA key.")
        keys[_public_key_id(candidate)] = candidate
    if not keys:
        raise LicenseIssueError("No feed verification public keys are configured.")
    return keys


def verify_feed(
    document: FeedDocument,
    public_key_pem: bytes | Iterable[bytes],
    *,
    expected_issuer: str,
    expected_audience: str,
    minimum_revision: int = 0,
    now: datetime | None = None,
    require_fresh: bool = True,
) -> FeedDocument:
    """Verify signature, freshness, content digests, and rollback floor."""
    token = document.manifest_token.strip()
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise LicenseIssueError("The license feed has no valid signed manifest.")
    header = _json_object(_decode_b64url(parts[0]), "header")
    payload = _json_object(_decode_b64url(parts[1]), "payload")
    if (
        header.get("alg") != "RS256"
        or header.get("typ") != MANIFEST_TYPE
        or "crit" in header
    ):
        raise LicenseIssueError("The feed manifest must use RS256 and the expected type.")
    key_id = header.get("kid")
    if not isinstance(key_id, str) or not key_id:
        raise LicenseIssueError("The feed manifest has no key ID.")
    if len(key_id) != 16 or any(character not in "0123456789abcdef" for character in key_id):
        raise LicenseIssueError("The feed manifest key ID is invalid.")
    key = _load_verification_keys(public_key_pem).get(key_id)
    if key is None:
        raise LicenseIssueError("The feed manifest was signed by an untrusted key.")
    try:
        key.verify(
            _decode_b64url(parts[2]),
            f"{parts[0]}.{parts[1]}".encode("ascii"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except InvalidSignature as exc:
        raise LicenseIssueError("The feed manifest signature is invalid.") from exc

    revision = payload.get("revision")
    active_count = payload.get("active_count")
    revoked_count = payload.get("revoked_count")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (revision, active_count, revoked_count)
    ):
        raise LicenseIssueError("The feed manifest contains invalid counters.")
    assert isinstance(revision, int)
    assert isinstance(active_count, int)
    assert isinstance(revoked_count, int)
    if revision < 1 or active_count < 0 or revoked_count < 0:
        raise LicenseIssueError("The feed manifest contains negative or zero metadata.")
    if revision < minimum_revision:
        raise LicenseIssueError(
            f"Feed rollback rejected: revision {revision} is older than {minimum_revision}."
        )
    generated_at = _timestamp_claim(payload.get("generated_at"), "generated_at")
    expires_at = _timestamp_claim(payload.get("exp"), "exp")
    current = _as_utc(now or datetime.now(timezone.utc), "now")
    if generated_at > current + MAX_CLOCK_SKEW:
        raise LicenseIssueError("The feed manifest was generated too far in the future.")
    if expires_at <= generated_at or expires_at - generated_at > MAX_FRESHNESS:
        raise LicenseIssueError("The feed manifest freshness window is invalid.")
    if require_fresh and current >= expires_at:
        raise LicenseIssueError("The license feed manifest is stale.")
    if payload.get("schema") != FEED_SCHEMA:
        raise LicenseIssueError("The license feed manifest schema is unsupported.")
    if payload.get("iss") != expected_issuer or payload.get("aud") != expected_audience:
        raise LicenseIssueError("The feed manifest issuer or audience does not match.")

    _validate_disjoint(document.records, document.tombstones)
    active_digest = records_digest(document.records)
    revoked_digest = tombstones_digest(document.tombstones)
    if (
        payload.get("active_sha256") != active_digest
        or payload.get("revoked_sha256") != revoked_digest
        or active_count != len(document.records)
        or revoked_count != len(document.tombstones)
    ):
        raise LicenseIssueError("The feed content does not match its signed manifest.")
    manifest = FeedManifest(
        revision=revision,
        generated_at=generated_at,
        expires_at=expires_at,
        issuer=expected_issuer,
        audience=expected_audience,
        key_id=key_id,
        active_digest=active_digest,
        revoked_digest=revoked_digest,
        active_count=active_count,
        revoked_count=revoked_count,
        token=token,
    )
    return FeedDocument(document.records, document.tombstones, token, manifest)


def _validate_disjoint(
    records: Iterable[LicenseRecord],
    tombstones: Iterable[FeedTombstone],
) -> None:
    active_hwids: set[str] = set()
    active_jtis: set[str] = set()
    for record in records:
        if not isinstance(record, LicenseRecord):
            raise LicenseIssueError("The feed contains an invalid active record.")
        hwid = record.hwid.casefold()
        if hwid in active_hwids:
            raise LicenseIssueError(f"The feed contains duplicate active HWID {hwid!r}.")
        active_hwids.add(hwid)
        if record.jti is not None:
            folded_jti = record.jti.casefold()
            if folded_jti in active_jtis:
                raise LicenseIssueError("The feed contains duplicate active JTI values.")
            active_jtis.add(folded_jti)
    revoked_hwids: set[str] = set()
    revoked_jtis: set[str] = set()
    for tombstone in tombstones:
        hwid = tombstone.hwid.casefold()
        if hwid in revoked_hwids:
            raise LicenseIssueError(f"The feed contains duplicate tombstone HWID {hwid!r}.")
        revoked_hwids.add(hwid)
        if tombstone.jti is not None:
            folded_jti = tombstone.jti.casefold()
            if folded_jti in revoked_jtis:
                raise LicenseIssueError("The feed contains duplicate tombstone JTI values.")
            revoked_jtis.add(folded_jti)
    overlap = active_hwids & revoked_hwids
    if overlap:
        raise LicenseIssueError(
            f"An HWID cannot be both active and revoked: {sorted(overlap)[0]!r}."
        )
    if active_jtis & revoked_jtis:
        raise LicenseIssueError("An active JTI cannot also appear in a tombstone.")


def serialize_feed_csv(document: FeedDocument) -> str:
    if not document.manifest_token:
        raise LicenseIssueError("A published feed requires a signed manifest.")
    _validate_disjoint(document.records, document.tombstones)
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FEED_COLUMNS)
    writer.writerow(("manifest", "", document.manifest_token, "", ""))
    for record in sorted(
        document.records, key=lambda item: (item.username.casefold(), item.hwid)
    ):
        writer.writerow(("active", record.hwid, record.token, record.jti or "", ""))
    for tombstone in sorted(
        document.tombstones, key=lambda item: (item.hwid, item.jti or "")
    ):
        writer.writerow(
            (
                "revoked",
                tombstone.hwid,
                "",
                tombstone.jti or "",
                tombstone.revoked_at.isoformat().replace("+00:00", "Z"),
            )
        )
    return output.getvalue()


def parse_feed_csv(csv_text: str, *, allow_legacy: bool = False) -> FeedDocument:
    if len(csv_text.encode("utf-8")) > MAX_LICENSE_FEED_BYTES:
        raise LicenseIssueError("The signed license feed is too large.")
    if csv_text.lstrip("\ufeff\r\n\t ").casefold().startswith(("<!doctype", "<html")):
        raise LicenseIssueError("The license source returned HTML instead of CSV.")
    try:
        rows = list(csv.reader(io.StringIO(csv_text.lstrip("\ufeff"), newline=""), strict=True))
    except csv.Error as exc:
        raise LicenseIssueError("The signed license feed is not valid CSV.") from exc
    if len(rows) > MAX_LICENSE_FEED_ROWS:
        raise LicenseIssueError("The signed license feed has too many rows.")
    if not rows or tuple(rows[0]) != FEED_COLUMNS:
        if allow_legacy:
            return FeedDocument(tuple(parse_signed_csv(csv_text)), ())
        raise LicenseIssueError("The license feed is missing the v2 header.")
    records: list[LicenseRecord] = []
    tombstones: list[FeedTombstone] = []
    manifest_token = ""
    for row_number, row in enumerate(rows[1:], start=2):
        padded = row + [""] * (len(FEED_COLUMNS) - len(row))
        if len(row) > len(FEED_COLUMNS):
            raise LicenseIssueError(f"Feed row {row_number} has too many columns.")
        entry_type, hwid, token, jti, revoked_at = (
            value.strip() for value in padded
        )
        if not any(padded):
            continue
        if entry_type == "manifest":
            if manifest_token or not token or any((hwid, jti, revoked_at)):
                raise LicenseIssueError("The feed manifest row is invalid or duplicated.")
            manifest_token = token
        elif entry_type == "active":
            if not hwid or not token or revoked_at:
                raise LicenseIssueError(f"Active feed row {row_number} is incomplete.")
            record = parse_signed_csv(f"hwid,token\n{hwid},{token}\n")[0]
            expected_jti = record.jti.casefold() if record.jti is not None else ""
            if jti.casefold() != expected_jti:
                raise LicenseIssueError(f"Active feed row {row_number} has a mismatched JTI.")
            records.append(record)
        elif entry_type == "revoked":
            if not hwid or token or not revoked_at:
                raise LicenseIssueError(f"Revoked feed row {row_number} is incomplete.")
            try:
                parsed_time = datetime.fromisoformat(revoked_at.replace("Z", "+00:00"))
            except ValueError as exc:
                raise LicenseIssueError(
                    f"Revoked feed row {row_number} has an invalid timestamp."
                ) from exc
            tombstones.append(FeedTombstone(hwid, jti or None, parsed_time))
        else:
            raise LicenseIssueError(f"Feed row {row_number} has an unknown entry type.")
    if not manifest_token:
        raise LicenseIssueError("The license feed has no signed manifest row.")
    _validate_disjoint(records, tombstones)
    return FeedDocument(tuple(records), tuple(tombstones), manifest_token)


def feed_digest(document: FeedDocument) -> str:
    return hashlib.sha256(serialize_feed_csv(document).encode("utf-8")).hexdigest()


class ManifestRevisionStore:
    """Durably remember the highest accepted manifest revision per issuer/audience."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _identity(issuer: str, audience: str) -> str:
        return hashlib.sha256(f"{issuer}\0{audience}".encode("utf-8")).hexdigest()

    def minimum_revision(self, issuer: str, audience: str) -> int:
        document = self._load()
        value = document.get(self._identity(issuer, audience), 0)
        if isinstance(value, dict):
            value = value.get("revision", 0)
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    def accept(self, manifest: FeedManifest, content_digest: str) -> None:
        document = self._load()
        identity = self._identity(manifest.issuer, manifest.audience)
        raw_previous = document.get(identity, 0)
        if isinstance(raw_previous, dict):
            previous = raw_previous.get("revision")
            previous_digest = raw_previous.get("content_digest")
        else:
            previous = raw_previous
            previous_digest = None
        if isinstance(previous, bool) or not isinstance(previous, int):
            raise LicenseIssueError("The manifest rollback state is corrupted.")
        if manifest.revision < previous:
            raise LicenseIssueError(
                f"Feed rollback rejected: revision {manifest.revision} is older than {previous}."
            )
        if manifest.revision == previous:
            if previous_digest not in (None, content_digest):
                raise LicenseIssueError(
                    "Feed equivocation rejected: the accepted revision has different content."
                )
            if previous_digest == content_digest:
                return
        document[identity] = {
            "revision": manifest.revision,
            "content_digest": content_digest,
        }
        try:
            atomic_write_text(
                self.path,
                json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n",
                create_backup=False,
            )
        except OSError as exc:
            raise LicenseIssueError(f"Unable to persist manifest revision: {exc}") from exc

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LicenseIssueError(f"Unable to read manifest revision state: {exc}") from exc
        if not isinstance(value, dict):
            raise LicenseIssueError("Manifest revision state must be a JSON object.")
        return value


def parse_verify_and_accept_feed(
    csv_text: str,
    public_key_pem: bytes | Iterable[bytes],
    *,
    issuer: str,
    audience: str,
    revision_store: ManifestRevisionStore,
    now: datetime | None = None,
) -> FeedDocument:
    """Client entry point that rejects stale and rolled-back signed feeds."""
    document = parse_feed_csv(csv_text)
    verified = verify_feed(
        document,
        public_key_pem,
        expected_issuer=issuer,
        expected_audience=audience,
        minimum_revision=revision_store.minimum_revision(issuer, audience),
        now=now,
    )
    assert verified.manifest is not None
    revision_store.accept(
        verified.manifest,
        publication_content_digest(verified.records, verified.tombstones),
    )
    return verified
