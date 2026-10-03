"""Cross-process leases that keep one writer attached to each project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QLockFile

from issue_license import LicenseIssueError


LOCK_FILENAME = ".activo-project.lock"


class ProjectLockError(LicenseIssueError):
    """A project lease could not be acquired safely."""


@dataclass(slots=True)
class ProjectLease:
    """Hold a fail-closed QLockFile lease for one project directory."""

    project_directory: Path
    _lock: QLockFile
    _held: bool = True

    @classmethod
    def acquire(cls, project_directory: Path) -> ProjectLease:
        directory = project_directory.resolve(strict=False)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProjectLockError(
                f"Unable to prepare project directory {directory}: {exc}"
            ) from exc

        lock = QLockFile(str(directory / LOCK_FILENAME))
        # A zero timeout disables age-only stale detection. QLockFile still removes a
        # lock automatically when it can prove that its owning local process died.
        lock.setStaleLockTime(0)
        if lock.tryLock(0):
            return cls(directory, lock)

        error = lock.error()
        if error is QLockFile.LockError.PermissionError:
            raise ProjectLockError(
                f"Permission denied while locking project {directory.name!r}."
            )
        if error is QLockFile.LockError.UnknownError:
            raise ProjectLockError(
                f"Unable to lock project {directory.name!r} because of an unknown "
                "filesystem error."
            )
        process_id, hostname, application = lock.getLockInfo()
        owner = ""
        if process_id > 0 or hostname or application:
            owner = (
                f" The lock is held by PID {process_id or '?'}"
                f" on {hostname or 'an unknown host'}"
                f" ({application or 'unknown application'})."
            )
        raise ProjectLockError(
            f"Project {directory.name!r} is already open in another process or its "
            f"lock file is unavailable.{owner} Close the other instance and try again."
        )

    @property
    def held(self) -> bool:
        return self._held

    def release(self) -> None:
        if not self._held:
            return
        self._lock.unlock()
        self._held = False

    def __enter__(self) -> ProjectLease:
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()

