"""Allowlisted support diagnostics, independent of project data and secrets."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

from PySide6 import __version__ as pyside_version
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QWidget

from license_admin.localization import current_language
from license_admin.version import APP_COMPANY_NAME, APP_DISPLAY_NAME, APP_VERSION


def build_channel() -> str:
    # No stable/beta metadata is supplied by the release pipeline yet.
    return "packaged" if getattr(sys, "frozen", False) else "source"


def third_party_notices_path() -> Path | None:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    candidates = (
        root / "release" / "THIRD_PARTY_NOTICES.txt",
        Path(sys.executable).parent / "THIRD_PARTY_NOTICES.txt",
        root / "build" / "release-metadata" / "THIRD_PARTY_NOTICES.txt",
    )
    return next((path for path in candidates if path.is_file()), None)


def diagnostics_text(window: QWidget) -> str:
    screen = window.screen()
    available = screen.availableGeometry() if screen is not None else None
    data = {
        "application": APP_DISPLAY_NAME,
        "version": APP_VERSION,
        "build_channel": build_channel(),
        "publisher": APP_COMPANY_NAME,
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "qt": qVersion(),
        "pyside": pyside_version,
        "language": current_language(),
        "theme": window.property("themeMode"),
        "window_size": [window.width(), window.height()],
        "screen_available_size": (
            [available.width(), available.height()] if available is not None else None
        ),
        "device_pixel_ratio": window.devicePixelRatioF(),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)
