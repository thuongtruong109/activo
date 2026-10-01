from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from types import TracebackType


def workspace_temp_root() -> Path:
    root = Path(__file__).resolve().parents[1] / "tmp" / "tests"
    root.mkdir(parents=True, exist_ok=True)
    return root


class WorkspaceTempDirectory:
    def __init__(self) -> None:
        self.path = workspace_temp_root() / f"test-{uuid.uuid4().hex}"
        self.path.mkdir(parents=True, exist_ok=False)
        self.name = str(self.path)

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self) -> str:
        return self.name

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.cleanup()


def workspace_temp_dir() -> WorkspaceTempDirectory:
    return WorkspaceTempDirectory()
