"""Run the standalone License Admin desktop application."""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from license_admin.main_window import ADMIN_STYLESHEET, LicenseAdminWindow


def main() -> int:
    QCoreApplication.setOrganizationName("LicenseTools")
    QCoreApplication.setApplicationName("LicenseAdmin")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(ADMIN_STYLESHEET)
    window = LicenseAdminWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
