"""License-admin domain objects and signed CSV serialization."""

from __future__ import annotations

import base64
import binascii
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import io
import json
import math
from typing import Any, Iterable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from issue_license import LicenseIssueError, normalize_hwid
from license_admin.limits import (
    MAX_LICENSE_FEED_BYTES,
    MAX_LICENSE_FEED_ROWS,
    MAX_LICENSE_TOKEN_LENGTH,
)


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    FUTURE = "future"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class LicenseRecord:
    hwid: str
    token: str
    username: str = ""
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    jti: str | None = None
    parse_error: str | None = None

    def status(
        self,
        now: datetime | None = None,
        *,
        expiring_within_days: int = 30,
    ) -> LicenseStatus:
        if self.parse_error is not None or self.expires_at is None:
            return LicenseStatus.INVALID
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if self.issued_at is not None and self.issued_at > current:
            return LicenseStatus.FUTURE
        seconds_remaining = (self.expires_at - current).total_seconds()
        if seconds_remaining <= 0:
            return LicenseStatus.EXPIRED
        if seconds_remaining <= expiring_within_days * 86_400:
            return LicenseStatus.EXPIRING
        return LicenseStatus.ACTIVE

    def remaining_days(self, now: datetime | None = None) -> int | None:
        if self.expires_at is None:
            return None
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        seconds = (self.expires_at - current).total_seconds()
        return max(0, math.ceil(seconds / 86_400))


def _decode_segment(segment: str) -> bytes:
    try:
        encoded = segment.encode("ascii")
        return base64.b64decode(
            encoded + b"=" * (-len(encoded) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise LicenseIssueError("JWT payload uses invalid base64url encoding.") from exc


def _unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LicenseIssueError(f"JWT payload contains duplicate claim {key!r}.")
        result[key] = value
    return result


def _claim_timestamp(claims: dict[str, Any], name: str) -> datetime:
    raw_value = claims.get(name)
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise LicenseIssueError(f"JWT claim {name!r} must be a timestamp.")
    numeric = float(raw_value)
    if not math.isfinite(numeric):
        raise LicenseIssueError(f"JWT claim {name!r} must be finite.")
    try:
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (OSError, OverflowError, ValueError) as exc:
        raise LicenseIssueError(f"JWT claim {name!r} is out of range.") from exc


def license_key_id(token: str) -> str | None:
    """Return a well-formed JWT key ID without trusting the token."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        header = json.loads(
            _decode_segment(parts[0]).decode("utf-8"),
            object_pairs_hook=_unique_json,
        )
        if not isinstance(header, dict):
            return None
        key_id = header.get("kid")
        return key_id if isinstance(key_id, str) and key_id else None
    except (LicenseIssueError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def inspect_license(
    hwid: str,
    token: str,
    *,
    public_key_pem: bytes | None = None,
    expected_issuer: str | None = None,
    expected_audience: str | None = None,
    _verification_key: rsa.RSAPublicKey | None = None,
) -> LicenseRecord:
    """Decode display metadata while retaining malformed rows for repair/revocation."""
    normalized_hwid = hwid.strip().casefold()
    compact_token = token.strip()
    try:
        normalized_hwid = normalize_hwid(normalized_hwid)
        if len(compact_token) > MAX_LICENSE_TOKEN_LENGTH:
            raise LicenseIssueError("License token is too large.")
        parts = compact_token.split(".")
        if len(parts) != 3 or not all(parts):
            raise LicenseIssueError("License token is not a compact JWT.")
        header = json.loads(
            _decode_segment(parts[0]).decode("utf-8"),
            object_pairs_hook=_unique_json,
        )
        payload = json.loads(
            _decode_segment(parts[1]).decode("utf-8"),
            object_pairs_hook=_unique_json,
        )
        if not isinstance(header, dict) or header.get("alg") != "RS256":
            raise LicenseIssueError("JWT must use RS256.")
        if header.get("typ") not in (None, "JWT") or "crit" in header:
            raise LicenseIssueError("JWT header contains unsupported fields.")
        if not isinstance(payload, dict):
            raise LicenseIssueError("JWT payload must be an object.")
        loaded_key = _verification_key
        if loaded_key is None and public_key_pem is not None:
            candidate_key = serialization.load_pem_public_key(public_key_pem)
            loaded_key = candidate_key if isinstance(candidate_key, rsa.RSAPublicKey) else None
        if public_key_pem is not None or _verification_key is not None:
            if not isinstance(loaded_key, rsa.RSAPublicKey) or loaded_key.key_size < 2_048:
                raise LicenseIssueError("License verification key is not a strong RSA key.")
            loaded_key.verify(
                _decode_segment(parts[2]),
                f"{parts[0]}.{parts[1]}".encode("ascii"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            key_id = header.get("kid")
            if key_id is not None:
                public_der = loaded_key.public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                expected_key_id = hashlib.sha256(public_der).hexdigest()[:16]
                if key_id != expected_key_id:
                    raise LicenseIssueError("JWT was signed for a different key ID.")
        token_hwid = payload.get("hwid")
        if not isinstance(token_hwid, str) or token_hwid.casefold() != normalized_hwid:
            raise LicenseIssueError("JWT HWID does not match its Sheet row.")
        username = payload.get("username") or payload.get("sub")
        if not isinstance(username, str) or not username.strip():
            raise LicenseIssueError("JWT has no valid username.")
        jti = payload.get("jti")
        if jti is not None and (
            not isinstance(jti, str)
            or not 16 <= len(jti) <= 128
            or any(character not in "0123456789abcdefABCDEF" for character in jti)
        ):
            raise LicenseIssueError("JWT identifier is invalid.")
        if expected_issuer and payload.get("iss") != expected_issuer:
            raise LicenseIssueError("JWT issuer does not match License Admin settings.")
        audience = payload.get("aud")
        if expected_audience and not (
            audience == expected_audience
            or (isinstance(audience, list) and expected_audience in audience)
        ):
            raise LicenseIssueError("JWT audience does not match License Admin settings.")
        issued_at = _claim_timestamp(payload, "iat")
        expires_at = _claim_timestamp(payload, "exp")
        if expires_at <= issued_at:
            raise LicenseIssueError("JWT expiry is not later than its issue time.")
        return LicenseRecord(
            hwid=normalized_hwid,
            token=compact_token,
            username=username.strip(),
            issued_at=issued_at,
            expires_at=expires_at,
            jti=jti,
        )
    except (
        InvalidSignature,
        LicenseIssueError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        message = "JWT signature is invalid." if isinstance(exc, InvalidSignature) else str(exc)
        return LicenseRecord(
            hwid=normalized_hwid,
            token=compact_token,
            parse_error=message,
        )


def parse_signed_csv(csv_text: str) -> list[LicenseRecord]:
    if len(csv_text.encode("utf-8")) > MAX_LICENSE_FEED_BYTES:
        raise LicenseIssueError("The signed license CSV is too large.")
    if csv_text.lstrip("\ufeff\r\n\t ").casefold().startswith(("<!doctype", "<html")):
        raise LicenseIssueError("The license source returned HTML instead of CSV.")

    records: list[LicenseRecord] = []
    seen_hwids: set[str] = set()
    try:
        reader = csv.reader(io.StringIO(csv_text.lstrip("\ufeff"), newline=""), strict=True)
        for row_number, row in enumerate(reader, start=1):
            if row_number > MAX_LICENSE_FEED_ROWS:
                raise LicenseIssueError("The signed license CSV has too many rows.")
            if not row or all(not value.strip() for value in row):
                continue
            first = row[0].strip().casefold()
            second = row[1].strip().casefold() if len(row) > 1 else ""
            if first == "hwid" and second in {
                "token",
                "license_token",
                "jwt token",
                "jwt_token",
            }:
                continue
            if len(row) < 2 or not row[0].strip() or not row[1].strip():
                raise LicenseIssueError(
                    f"Signed row {row_number} must contain both HWID and token."
                )
            hwid = row[0].strip().casefold()
            if hwid in seen_hwids:
                raise LicenseIssueError(
                    f"The signed CSV contains duplicate HWID at row {row_number}."
                )
            seen_hwids.add(hwid)
            records.append(inspect_license(hwid, row[1]))
    except csv.Error as exc:
        raise LicenseIssueError("The signed license list is not valid CSV.") from exc
    return records


def serialize_signed_csv(records: Iterable[LicenseRecord]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("hwid", "token"))
    for record in sorted(records, key=lambda item: (item.username.casefold(), item.hwid)):
        writer.writerow((record.hwid, record.token))
    return output.getvalue()


def validate_record_signatures(
    records: Iterable[LicenseRecord],
    public_key_pem: bytes | Iterable[bytes],
    *,
    expected_issuer: str | None = None,
    expected_audience: str | None = None,
) -> list[LicenseRecord]:
    materials = (
        (public_key_pem,)
        if isinstance(public_key_pem, bytes)
        else tuple(public_key_pem)
    )
    if not materials:
        raise LicenseIssueError("No license verification public keys are configured.")
    loaded_keys: list[rsa.RSAPublicKey] = []
    keys_by_id: dict[str, rsa.RSAPublicKey] = {}
    for material in materials:
        try:
            candidate = serialization.load_pem_public_key(material)
        except (TypeError, ValueError) as exc:
            raise LicenseIssueError("License verification public key is invalid.") from exc
        if not isinstance(candidate, rsa.RSAPublicKey) or candidate.key_size < 2_048:
            raise LicenseIssueError("License verification key is not a strong RSA key.")
        public_der = candidate.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        key_id = hashlib.sha256(public_der).hexdigest()[:16]
        if key_id not in keys_by_id:
            keys_by_id[key_id] = candidate
            loaded_keys.append(candidate)

    verified: list[LicenseRecord] = []
    for record in records:
        selected: rsa.RSAPublicKey | None = None
        token_key_id = license_key_id(record.token)
        if token_key_id is not None:
            selected = keys_by_id.get(token_key_id)
        if selected is not None:
            verified.append(
                inspect_license(
                    record.hwid,
                    record.token,
                    expected_issuer=expected_issuer,
                    expected_audience=expected_audience,
                    _verification_key=selected,
                )
            )
            continue

        attempts = [
            inspect_license(
                record.hwid,
                record.token,
                expected_issuer=expected_issuer,
                expected_audience=expected_audience,
                _verification_key=key,
            )
            for key in loaded_keys
        ]
        verified.append(
            next(
                (attempt for attempt in attempts if attempt.parse_error is None),
                attempts[0],
            )
        )
    return verified


def records_digest(records: Iterable[LicenseRecord]) -> str:
    canonical = serialize_signed_csv(records).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
