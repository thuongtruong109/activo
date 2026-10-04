"""Isolate PyInstaller's DLL lookup from unrelated tools on the builder's PATH."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def isolate_build_path() -> None:
    if sys.platform != "win32":
        return
    windows = Path(os.environ["SystemRoot"])
    directories = (windows / "System32", windows, Path(sys.base_prefix),
                   Path(sys.base_prefix) / "DLLs", Path(sys.executable).parent)
    os.environ["PATH"] = os.pathsep.join(str(path) for path in directories)
