"""Offline packaged-runtime probe; does not open or mutate user projects."""

from __future__ import annotations

import json
from pathlib import Path
import struct

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication, QPushButton

from license_admin.app_identity import APP_ICON_PATH, app_logo_pixmap, configure_application_identity
from license_admin.version import APP_VERSION


def run_smoke_test(output: Path) -> int:
    report: dict[str, object] = {"version": APP_VERSION, "ok": False}
    try:
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            app = QApplication([])
        configure_application_identity(app)
        icon_data = APP_ICON_PATH.read_bytes()
        count = struct.unpack_from("<H", icon_data, 4)[0]
        sizes = sorted({icon_data[6 + i * 16] or 256 for i in range(count)})
        if not {16, 24, 32, 48, 64, 128, 256}.issubset(sizes):
            raise RuntimeError("Incomplete bundled Windows icon")
        for size in sizes:
            if app.windowIcon().pixmap(QSize(size, size)).isNull():
                raise RuntimeError("Unable to render bundled Windows icon")
        if app_logo_pixmap(48).isNull():
            raise RuntimeError("Bundled logo is missing")
        button = QPushButton("Offline runtime probe")
        button.resize(240, 40)
        if button.grab().isNull():
            raise RuntimeError("Qt could not render a widget")
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        payload = b"License Admin release probe"
        signature = key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
        key.public_key().verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
        report.update(ok=True, iconSizes=sizes, applicationVersion=app.applicationVersion())
    except Exception as exc:
        report["error"] = str(exc)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1
