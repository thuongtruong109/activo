"""Validation and project-local storage for Google service-account files."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Any, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from issue_license import LicenseIssueError
from license_admin.windows_security import restrict_to_current_user


MAX_SERVICE_ACCOUNT_FILE_BYTES = 1024 * 1024
SERVICE_ACCOUNT_FILENAME = "service-account.json"


@dataclass(frozen=True, slots=True)
class ServiceAccountInfo:
    """Safe metadata extracted from a service-account credential."""

    client_email: str
    project_id: str


@dataclass(frozen=True, slots=True)
class ImportedServiceAccount:
    """Result of copying a credential into a project directory."""

    path: Path
    info: ServiceAccountInfo


def _read_document(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LicenseIssueError(f"Unable to read service-account JSON: {exc}") from exc
    if size < 1 or size > MAX_SERVICE_ACCOUNT_FILE_BYTES:
        raise LicenseIssueError(
            "Service-account JSON must be between 1 byte and 1 MiB."
        )
    try:
        raw = path.read_bytes()
        parsed: Any = json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LicenseIssueError(f"Unable to read service-account JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LicenseIssueError("Service-account JSON must contain an object.")
    return raw, cast(dict[str, Any], parsed)


def load_service_account(path: Path) -> dict[str, Any]:
    """Load and fully validate a Google service-account document."""
    _raw, document = _read_document(path)
    account_type = document.get("type")
    if account_type != "service_account":
        raise LicenseIssueError(
            "Google credential must have type 'service_account'."
        )
    for field in ("client_email", "private_key"):
        value = document.get(field)
        if not isinstance(value, str) or not value.strip():
            raise LicenseIssueError(
                f"Service-account JSON is missing {field!r}."
            )
    token_uri = document.get("token_uri", "https://oauth2.googleapis.com/token")
    if not isinstance(token_uri, str) or not token_uri.startswith("https://"):
        raise LicenseIssueError("Service-account token_uri must use HTTPS.")
    try:
        private_key = serialization.load_pem_private_key(
            cast(str, document["private_key"]).encode("utf-8"),
            password=None,
        )
    except (TypeError, ValueError) as exc:
        raise LicenseIssueError("Service-account private key is invalid.") from exc
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise LicenseIssueError("Service-account private key must be RSA.")
    return document


def inspect_service_account(path: Path) -> ServiceAccountInfo:
    """Return non-secret metadata after validating a credential file."""
    document = load_service_account(path)
    project_id = document.get("project_id", "")
    return ServiceAccountInfo(
        client_email=cast(str, document["client_email"]).strip(),
        project_id=project_id.strip() if isinstance(project_id, str) else "",
    )


def import_service_account(
    source: Path,
    project_directory: Path,
    *,
    overwrite: bool = False,
) -> ImportedServiceAccount:
    """Validate and atomically copy a credential into one project."""
    info = inspect_service_account(source)
    raw, _document = _read_document(source)
    target = project_directory / SERVICE_ACCOUNT_FILENAME
    if source.resolve(strict=False) == target.resolve(strict=False):
        restrict_to_current_user(project_directory)
        restrict_to_current_user(target)
        return ImportedServiceAccount(path=target, info=info)
    if target.exists() and not overwrite:
        raise LicenseIssueError(
            "This project already has a service-account JSON. Confirm replacement first."
        )

    try:
        project_directory.mkdir(parents=True, exist_ok=True)
        restrict_to_current_user(project_directory)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{SERVICE_ACCOUNT_FILENAME}.",
            suffix=".tmp",
            dir=str(project_directory),
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(raw)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            restrict_to_current_user(temporary_path)
            inspect_service_account(temporary_path)
            os.replace(temporary_path, target)
        finally:
            temporary_path.unlink(missing_ok=True)
    except (OSError, LicenseIssueError) as exc:
        raise LicenseIssueError(f"Unable to import service-account JSON: {exc}") from exc
    return ImportedServiceAccount(path=target, info=info)
