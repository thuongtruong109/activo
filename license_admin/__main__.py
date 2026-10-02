"""Run the standalone License Admin desktop application."""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from license_admin.app_identity import (
    configure_application_identity,
    configure_process_identity,
)
from license_admin.main_window import LicenseAdminWindow
from license_admin.theme import ADMIN_STYLESHEET


def main() -> int:
    configure_process_identity()
    QCoreApplication.setOrganizationName("LicenseTools")
    QCoreApplication.setApplicationName("LicenseAdmin")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    configure_application_identity(app)
    app.setStyle("Fusion")
    app.setStyleSheet(ADMIN_STYLESHEET)
    window = LicenseAdminWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
