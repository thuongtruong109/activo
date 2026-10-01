"""Double-click entry point for the standalone License Admin."""

from __future__ import annotations

from pathlib import Path
import sys


repository_root = str(Path(__file__).resolve().parent)
if repository_root not in sys.path:
    sys.path.insert(0, repository_root)

from license_admin.__main__ import main


raise SystemExit(main())
