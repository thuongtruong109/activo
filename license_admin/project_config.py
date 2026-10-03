"""Portable import/export of non-secret settings for one project."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from typing import Any, cast

from issue_license import LicenseIssueError
from license_admin.google_sheets import extract_spreadsheet_id
from license_admin.settings import AdminSettings


PORTABLE_CONFIG_SCHEMA_VERSION = 1
MAX_PROJECT_CONFIG_BYTES = 256 * 1024


def _settings_document(settings: AdminSettings) -> dict[str, Any]:
    return {
        "schema_version": PORTABLE_CONFIG_SCHEMA_VERSION,
        "project": {
            "name": settings.project_name,
            "spreadsheet_id": settings.spreadsheet_id,
            "worksheet": settings.worksheet,
            "public_csv_url": settings.public_csv_url,
            "issuer": settings.issuer,
            "audience": settings.audience,
        },
    }


def export_project_config(settings: AdminSettings, target: Path) -> Path:
    """Atomically export portable settings without key or credential contents."""
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=str(target.parent),
            text=True,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            temporary_path.write_text(
                json.dumps(
                    _settings_document(settings),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, target)
        finally:
            temporary_path.unlink(missing_ok=True)
    except OSError as exc:
        raise LicenseIssueError(f"Unable to export project settings: {exc}") from exc
    return target


def _read_config(path: Path) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise LicenseIssueError(f"Unable to read project settings: {exc}") from exc
    if size < 1 or size > MAX_PROJECT_CONFIG_BYTES:
        raise LicenseIssueError(
            "Project settings JSON must be between 1 byte and 256 KiB."
        )
    try:
        parsed: Any = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LicenseIssueError(f"Unable to read project settings: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LicenseIssueError("Project settings JSON must contain an object.")
    document = cast(dict[str, Any], parsed)
    schema_version = document.get("schema_version", PORTABLE_CONFIG_SCHEMA_VERSION)
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in {PORTABLE_CONFIG_SCHEMA_VERSION, 2}
    ):
        raise LicenseIssueError(
            f"Unsupported project settings schema version: {schema_version!r}."
        )
    project = document.get("project", document)
    if not isinstance(project, dict):
        raise LicenseIssueError("Project settings field 'project' must be an object.")
    return cast(dict[str, Any], project)


def _text(
    document: dict[str, Any],
    key: str,
    *,
    required: bool = False,
    default: str = "",
) -> str:
    value = document.get(key, default)
    if not isinstance(value, str):
        raise LicenseIssueError(f"Project settings field {key!r} must be text.")
    normalized = value.strip()
    if required and not normalized:
        raise LicenseIssueError(f"Project settings field {key!r} is required.")
    return normalized


def import_project_config(path: Path, current: AdminSettings) -> AdminSettings:
    """Merge portable settings into the active project without crossing asset paths."""
    document = _read_config(path)
    name = _text(document, "name", required=True)
    spreadsheet_id = _text(document, "spreadsheet_id")
    if spreadsheet_id:
        spreadsheet_id = extract_spreadsheet_id(spreadsheet_id)
    worksheet = _text(document, "worksheet", default="Signed") or "Signed"
    public_csv_url = _text(document, "public_csv_url")
    if public_csv_url and not public_csv_url.startswith("https://"):
        raise LicenseIssueError("Public CSV URL must use HTTPS.")
    return replace(
        current,
        project_name=name,
        spreadsheet_id=spreadsheet_id,
        worksheet=worksheet,
        public_csv_url=public_csv_url,
        issuer=_text(document, "issuer", required=True),
        audience=_text(document, "audience", required=True),
    )
