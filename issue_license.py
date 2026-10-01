"""Issue an RS256 device-bound license without running a license server."""

from __future__ import annotations

import argparse
import base64
import csv
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


MAX_LICENSE_DAYS = 3_650


class LicenseIssueError(ValueError):
    """Raised when publisher input or key material is invalid."""


def _as_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LicenseIssueError(f"{label} must include a timezone.")
    return value.astimezone(timezone.utc)


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def normalize_hwid(value: str) -> str:
    hwid = value.strip().casefold()
    if len(hwid) != 64 or any(character not in "0123456789abcdef" for character in hwid):
        raise LicenseIssueError("HWID must contain exactly 64 hexadecimal characters.")
    return hwid


def _validate_username(value: str) -> str:
    username = value.strip()
    if not username or len(username) > 200:
        raise LicenseIssueError("Username must contain between 1 and 200 characters.")
    if any(ord(character) < 32 for character in username):
        raise LicenseIssueError("Username must not contain control characters.")
    return username


def load_private_key(path: Path, password: bytes | None) -> rsa.RSAPrivateKey:
    try:
        loaded_key = serialization.load_pem_private_key(
            path.read_bytes(),
            password=password,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise LicenseIssueError(f"Unable to load the private key: {exc}") from exc
    if not isinstance(loaded_key, rsa.RSAPrivateKey):
        raise LicenseIssueError("The signing key must be an RSA private key.")
    if loaded_key.key_size < 2_048:
        raise LicenseIssueError("The RSA private key must be at least 2048 bits.")
    return loaded_key


def issue_license(
    private_key: rsa.RSAPrivateKey,
    *,
    username: str,
    hwid: str,
    days: int,
    issuer: str,
    audience: str,
    now: datetime | None = None,
) -> str:
    """Create a compact, device-bound RS256 JWT for publication."""
    if not 1 <= days <= MAX_LICENSE_DAYS:
        raise LicenseIssueError(
            f"License duration must be between 1 and {MAX_LICENSE_DAYS} days."
        )
    issued_at = _as_utc(now or datetime.now(timezone.utc), "Issue time")
    return issue_license_until(
        private_key,
        username=username,
        hwid=hwid,
        expires_at=issued_at + timedelta(days=days),
        issuer=issuer,
        audience=audience,
        now=issued_at,
    )


def issue_license_until(
    private_key: rsa.RSAPrivateKey,
    *,
    username: str,
    hwid: str,
    expires_at: datetime,
    issuer: str,
    audience: str,
    now: datetime | None = None,
) -> str:
    """Create a compact RS256 JWT with an exact expiration timestamp."""
    if private_key.key_size < 2_048:
        raise LicenseIssueError("The RSA private key must be at least 2048 bits.")
    normalized_hwid = normalize_hwid(hwid)
    normalized_username = _validate_username(username)
    if not issuer.strip() or not audience.strip():
        raise LicenseIssueError("Issuer and audience must not be empty.")

    issued_at = _as_utc(now or datetime.now(timezone.utc), "Issue time")
    expiration = _as_utc(expires_at, "License expiry")
    if expiration <= issued_at:
        raise LicenseIssueError("License expiry must be later than its issue time.")
    if expiration > issued_at + timedelta(days=MAX_LICENSE_DAYS):
        raise LicenseIssueError(
            f"License expiry must be within {MAX_LICENSE_DAYS} days."
        )
    public_der = private_key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    header = {
        "alg": "RS256",
        "kid": hashlib.sha256(public_der).hexdigest()[:16],
        "typ": "JWT",
    }
    payload = {
        "aud": audience.strip(),
        "exp": int(expiration.timestamp()),
        "hwid": normalized_hwid,
        "iat": int(issued_at.timestamp()),
        "iss": issuer.strip(),
        "jti": secrets.token_hex(16),
        "username": normalized_username,
    }
    encoded_header = _b64url(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _b64url(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = private_key.sign(
        signing_input,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return f"{encoded_header}.{encoded_payload}.{_b64url(signature)}"


def password_from_environment(variable_name: str | None) -> bytes | None:
    if not variable_name:
        return None
    value = os.getenv(variable_name)
    if value is None:
        raise LicenseIssueError(
            f"Private-key password environment variable {variable_name!r} is not set."
        )
    return value.encode("utf-8")


def resolve_private_key_password(
    variable_name: str | None,
    ask_password: bool,
) -> bytes | None:
    if variable_name and ask_password:
        raise LicenseIssueError(
            "Use either --password-env or --ask-password, not both."
        )
    if ask_password:
        password = getpass.getpass("Private-key password: ")
        if not password:
            raise LicenseIssueError("Private-key password must not be empty.")
        return password.encode("utf-8")
    return password_from_environment(variable_name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Issue a signed license for Google Sheets/Drive.",
    )
    key_default = os.getenv("LICENSE_PRIVATE_KEY")
    issuer_default = os.getenv("LICENSE_ISSUER")
    audience_default = os.getenv("LICENSE_AUDIENCE")
    parser.add_argument(
        "--key",
        type=Path,
        default=Path(key_default) if key_default else None,
        required=key_default is None,
        help="RSA private key PEM; alternatively set LICENSE_PRIVATE_KEY",
    )
    parser.add_argument("--username", required=True)
    parser.add_argument("--hwid", required=True)
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument(
        "--issuer",
        default=issuer_default,
        required=issuer_default is None,
    )
    parser.add_argument(
        "--audience",
        default=audience_default,
        required=audience_default is None,
    )
    parser.add_argument(
        "--password-env",
        help="name of an environment variable containing the PEM password",
    )
    parser.add_argument(
        "--ask-password",
        action="store_true",
        help="prompt for the encrypted PEM password without echo",
    )
    parser.add_argument(
        "--format",
        choices=("token", "csv"),
        default="token",
        help="print only the token or a complete hwid,token CSV row",
    )
    args = parser.parse_args()

    try:
        normalized_hwid = normalize_hwid(args.hwid)
        private_key = load_private_key(
            args.key,
            resolve_private_key_password(
                args.password_env,
                args.ask_password,
            ),
        )
        token = issue_license(
            private_key,
            username=args.username,
            hwid=normalized_hwid,
            days=args.days,
            issuer=args.issuer,
            audience=args.audience,
        )
    except LicenseIssueError as exc:
        parser.error(str(exc))

    if args.format == "csv":
        csv.writer(sys.stdout, lineterminator="\n").writerow(
            (normalized_hwid, token)
        )
    else:
        print(token)


if __name__ == "__main__":
    main()
