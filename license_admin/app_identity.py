"""Shared application branding for windows, dialogs, and packaged builds."""

from __future__ import annotations

import ctypes
from pathlib import Path
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication


APP_DISPLAY_NAME = "License Admin"
APP_VERSION = "1.0.0"
SUPPORT_EMAIL = "thuongtruongofficial@gmail.com"
WINDOWS_APP_USER_MODEL_ID = "LicenseTools.LicenseAdmin"
ASSET_DIRECTORY = Path(__file__).with_name("assets")
APP_LOGO_PATH = ASSET_DIRECTORY / "app-logo.png"
APP_ICON_PATH = ASSET_DIRECTORY / "app.ico"


def app_icon() -> QIcon:
    """Return the common icon used by every application window."""
    icon_path = APP_ICON_PATH if APP_ICON_PATH.is_file() else APP_LOGO_PATH
    return QIcon(str(icon_path))


def app_logo_pixmap(size: int) -> QPixmap:
    """Render the bundled logo at a crisp, aspect-preserving size."""
    pixmap = QPixmap(str(APP_LOGO_PATH))
    return pixmap.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def configure_process_identity() -> None:
    """Give Windows a stable identity for taskbar grouping and shortcuts."""
    if sys.platform != "win32":
        return
    try:
        setter = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        setter.argtypes = [ctypes.c_wchar_p]
        setter.restype = ctypes.c_long
        setter(WINDOWS_APP_USER_MODEL_ID)
    except (AttributeError, OSError, TypeError):
        pass


def configure_application_identity(app: QApplication) -> None:
    """Apply the shared display name and icon before any windows are created."""
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setWindowIcon(app_icon())
