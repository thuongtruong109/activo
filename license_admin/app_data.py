"""Per-user application-data paths and one-time legacy migration."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
from uuid import uuid4

from issue_license import LicenseIssueError
from license_admin.windows_security import (
    restrict_to_current_user,
    restrict_tree_to_current_user,
)


VENDOR_NAME = "Activo"
APPLICATION_NAME = "LicenseAdmin"


def application_data_root() -> Path:
    """Return a non-roaming, per-user directory for mutable application data."""
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if not local_app_data:
            raise LicenseIssueError("Windows LOCALAPPDATA is unavailable.")
        base = Path(local_app_data)
    else:
        configured = os.environ.get("XDG_DATA_HOME", "").strip()
        base = Path(configured) if configured else Path.home() / ".local" / "share"
    return base / VENDOR_NAME / APPLICATION_NAME


def migrate_legacy_projects(legacy_root: Path, destination_root: Path) -> bool:
    """Copy legacy projects into LocalAppData after securing both copies."""
    legacy = legacy_root.resolve(strict=False)
    destination = destination_root.resolve(strict=False)
    if legacy == destination:
        return False
    try:
        legacy_profiles = tuple(legacy.glob("*/project.json"))
    except OSError as exc:
        raise LicenseIssueError(f"Unable to inspect legacy projects {legacy}: {exc}") from exc
    if not legacy_profiles:
        return False

    if destination.exists():
        # A previous successful migration is intentionally left in place. Still
        # re-apply the private ACL so later permission inheritance changes do not
        # expose either the active copy or the retained rollback copy.
        restrict_tree_to_current_user(legacy)
        restrict_tree_to_current_user(destination)
        try:
            destination_profiles = tuple(destination.glob("*/project.json"))
        except OSError as exc:
            raise LicenseIssueError(
                f"Unable to inspect migrated projects {destination}: {exc}"
            ) from exc
        if destination_profiles:
            return False
        raise LicenseIssueError(
            f"Project migration destination exists but contains no profiles: "
            f"{destination}. Move or remove that empty directory, then retry."
        )

    # The legacy copy is retained as rollback data, but it must no longer expose
    # publisher secrets through inherited Everyone/Users read permissions.
    restrict_tree_to_current_user(legacy)
    temporary: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        restrict_to_current_user(destination.parent)
        temporary = destination.parent / f".projects-migration-{uuid4().hex}"
        shutil.copytree(legacy, temporary)
        restrict_tree_to_current_user(temporary)
        copied_profiles = tuple(temporary.glob("*/project.json"))
        if len(copied_profiles) != len(legacy_profiles):
            raise LicenseIssueError("Legacy project migration verification failed.")
        os.replace(temporary, destination)
    except (OSError, LicenseIssueError) as exc:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
        if isinstance(exc, LicenseIssueError):
            raise
        raise LicenseIssueError(f"Unable to migrate legacy project data: {exc}") from exc
    return True

