"""Durable atomic text writes with a versioned pre-replacement backup."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4


BACKUP_DIRECTORY_NAME = ".backups"


def backup_directory(path: Path) -> Path:
    """Return the private backup directory associated with *path*."""
    return path.parent / BACKUP_DIRECTORY_NAME / path.name


def create_versioned_backup(path: Path) -> Path | None:
    """Copy an existing file to a unique, timestamped backup atomically."""
    try:
        path.stat()
    except FileNotFoundError:
        return None

    destination_directory = backup_directory(path)
    destination_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = destination_directory / (
        f"{timestamp}-{uuid4().hex[:8]}-{path.name}.bak"
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".backup-",
        suffix=".tmp",
        dir=str(destination_directory),
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as target, path.open("rb") as source:
            shutil.copyfileobj(source, target)
            target.flush()
            os.fsync(target.fileno())
        shutil.copystat(path, temporary_path)
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return destination


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    create_backup: bool = True,
) -> Path | None:
    """Atomically replace *path*, backing up its previous bytes first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    temporary_path = Path(temporary_name)
    backup: Path | None = None
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if create_backup:
            backup = create_versioned_backup(path)
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    return backup
