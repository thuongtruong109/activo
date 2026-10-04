"""Normal desktop startup, separate from the Qt-free release probe dispatcher."""

from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from issue_license import LicenseIssueError
from license_admin.app_identity import configure_application_identity, configure_process_identity
from license_admin.main_window import LicenseAdminWindow
from license_admin.theme import ADMIN_STYLESHEET
from license_admin.widget_style import configure_widget_style


def run_application() -> int:
    configure_process_identity()
    QCoreApplication.setOrganizationName("LicenseTools")
    QCoreApplication.setApplicationName("LicenseAdmin")
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv)
    configure_application_identity(app)
    configure_widget_style(app)
    app.setStyleSheet(ADMIN_STYLESHEET)
    try:
        window = LicenseAdminWindow()
    except LicenseIssueError as exc:
        QMessageBox.critical(None, "Unable to open License Admin", str(exc))
        return 1
    window.show()
    return app.exec()
