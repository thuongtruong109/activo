"""Project profiles and non-secret settings for the standalone admin app."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from typing import Any

from issue_license import LicenseIssueError
from license_admin.google_sheets import GoogleSheetsConfig, extract_spreadsheet_id


APPLICATION_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)
PROJECTS_ROOT = Path(
    os.environ.get("ACTIVO_PROJECTS_ROOT") or APPLICATION_ROOT / "projects"
).expanduser()
PROFILE_FILENAME = "project.json"
PROFILE_SCHEMA_VERSION = 1
_PROJECT_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")


def normalize_project_id(value: str) -> str:
    """Return a filesystem-safe, stable identifier for a project profile."""
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    ).replace("đ", "d")
    project_id = re.sub(r"[^a-z0-9_-]+", "-", ascii_value).strip("-_")
    if not _PROJECT_ID_PATTERN.fullmatch(project_id):
        raise LicenseIssueError(
            "Project ID must use 1-64 lowercase letters, numbers, hyphens or underscores."
        )
    return project_id


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LicenseIssueError(f"Project profile field {key!r} is required.")
    return value.strip()


def _optional_text(document: dict[str, Any], key: str, default: str = "") -> str:
    value = document.get(key, default)
    if not isinstance(value, str):
        raise LicenseIssueError(f"Project profile field {key!r} must be text.")
    return value.strip()


def _resolve_profile_path(profile_directory: Path, value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else profile_directory / candidate


def _stored_profile_path(profile_directory: Path, value: Path) -> str:
    resolved_directory = profile_directory.resolve(strict=False)
    resolved_value = value.resolve(strict=False)
    try:
        return resolved_value.relative_to(resolved_directory).as_posix()
    except ValueError:
        return str(resolved_value)


@dataclass(frozen=True, slots=True)
class AdminSettings:
    project_id: str
    project_name: str
    local_csv_path: Path
    signing_key_path: Path
    public_key_path: Path
    service_account_path: Path | None
    spreadsheet_id: str
    worksheet: str
    public_csv_url: str
    issuer: str
    audience: str

    def sheets_config(self) -> GoogleSheetsConfig:
        return GoogleSheetsConfig(
            spreadsheet_id=extract_spreadsheet_id(self.spreadsheet_id),
            worksheet=self.worksheet,
            credentials_path=self.service_account_path,
            public_csv_url=self.public_csv_url,
        )


class ProjectStore:
    """Persist independent publisher settings for multiple products."""

    def __init__(self, root: Path = PROJECTS_ROOT) -> None:
        self.root = root

    def profile_path(self, project_id: str) -> Path:
        normalized = normalize_project_id(project_id)
        return self.root / normalized / PROFILE_FILENAME

    def project_directory(self, project_id: str) -> Path:
        return self.profile_path(project_id).parent

    def list_profiles(self) -> list[AdminSettings]:
        if not self.root.exists():
            return []
        profiles = [
            self._load_path(path)
            for path in self.root.glob(f"*/{PROFILE_FILENAME}")
            if path.is_file()
        ]
        return sorted(profiles, key=lambda profile: profile.project_name.casefold())

    def load(self, project_id: str) -> AdminSettings:
        path = self.profile_path(project_id)
        if not path.is_file():
            raise LicenseIssueError(f"Project profile does not exist: {project_id}")
        return self._load_path(path)

    def ensure_default(self) -> AdminSettings:
        profiles = self.list_profiles()
        if profiles:
            return profiles[0]
        profile = self._new_settings("Default Project", "default")
        self.save(profile)
        return profile

    def create(self, project_name: str, project_id: str | None = None) -> AdminSettings:
        display_name = project_name.strip()
        if not display_name:
            raise LicenseIssueError("Project name must not be empty.")
        normalized = normalize_project_id(project_id or display_name)
        if self.profile_path(normalized).exists():
            raise LicenseIssueError(f"Project profile already exists: {normalized}")
        profile = self._new_settings(display_name, normalized)
        self.save(profile)
        return profile

    def save(self, settings: AdminSettings) -> None:
        project_id = normalize_project_id(settings.project_id)
        profile_directory = self.root / project_id
        profile_directory.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": PROFILE_SCHEMA_VERSION,
            "id": project_id,
            "name": settings.project_name.strip(),
            "local_csv": _stored_profile_path(
                profile_directory, settings.local_csv_path
            ),
            "private_key": _stored_profile_path(
                profile_directory, settings.signing_key_path
            ),
            "public_key": _stored_profile_path(
                profile_directory, settings.public_key_path
            ),
            "service_account": (
                _stored_profile_path(profile_directory, settings.service_account_path)
                if settings.service_account_path
                else ""
            ),
            "spreadsheet_id": settings.spreadsheet_id.strip(),
            "worksheet": settings.worksheet.strip() or "Signed",
            "public_csv_url": settings.public_csv_url.strip(),
            "issuer": settings.issuer.strip(),
            "audience": settings.audience.strip(),
        }
        if not document["name"] or not document["issuer"] or not document["audience"]:
            raise LicenseIssueError(
                "Project name, issuer and audience must not be empty."
            )
        target = profile_directory / PROFILE_FILENAME
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{PROFILE_FILENAME}.",
            suffix=".tmp",
            dir=str(profile_directory),
            text=True,
        )
        os.close(descriptor)
        temporary_path = Path(temporary_name)
        try:
            temporary_path.write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, target)
        except OSError as exc:
            raise LicenseIssueError(f"Unable to save project profile: {exc}") from exc
        finally:
            temporary_path.unlink(missing_ok=True)

    def _new_settings(self, project_name: str, project_id: str) -> AdminSettings:
        profile_directory = self.root / project_id
        return AdminSettings(
            project_id=project_id,
            project_name=project_name,
            local_csv_path=profile_directory / "license_admin_data.csv",
            signing_key_path=profile_directory / "private.pem",
            public_key_path=profile_directory / "public.pem",
            service_account_path=None,
            spreadsheet_id="",
            worksheet="Signed",
            public_csv_url="",
            issuer=f"{project_id}-license-server",
            audience=f"{project_id}-desktop",
        )

    def _load_path(self, path: Path) -> AdminSettings:
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise LicenseIssueError(f"Unable to read project profile {path}: {exc}") from exc
        if not isinstance(document, dict):
            raise LicenseIssueError(f"Project profile must contain a JSON object: {path}")
        schema_version = document.get("schema_version", PROFILE_SCHEMA_VERSION)
        if (
            isinstance(schema_version, bool)
            or not isinstance(schema_version, int)
            or schema_version != PROFILE_SCHEMA_VERSION
        ):
            raise LicenseIssueError(
                f"Unsupported project profile schema version: {schema_version!r}."
            )
        project_id = normalize_project_id(_required_text(document, "id"))
        if project_id != path.parent.name:
            raise LicenseIssueError(
                f"Project ID {project_id!r} must match directory {path.parent.name!r}."
            )
        profile_directory = path.parent
        credentials = _optional_text(document, "service_account")
        return AdminSettings(
            project_id=project_id,
            project_name=_required_text(document, "name"),
            local_csv_path=_resolve_profile_path(
                profile_directory,
                _optional_text(document, "local_csv", "license_admin_data.csv"),
            ),
            signing_key_path=_resolve_profile_path(
                profile_directory,
                _optional_text(document, "private_key", "private.pem"),
            ),
            public_key_path=_resolve_profile_path(
                profile_directory,
                _optional_text(document, "public_key", "public.pem"),
            ),
            service_account_path=(
                _resolve_profile_path(profile_directory, credentials)
                if credentials
                else None
            ),
            spreadsheet_id=_optional_text(document, "spreadsheet_id"),
            worksheet=_optional_text(document, "worksheet", "Signed") or "Signed",
            public_csv_url=_optional_text(document, "public_csv_url"),
            issuer=_required_text(document, "issuer"),
            audience=_required_text(document, "audience"),
        )
