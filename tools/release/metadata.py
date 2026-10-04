"""Qt-free release metadata and PyInstaller Windows resources."""

from __future__ import annotations

import argparse
from pathlib import Path
import re

from license_admin.version import (
    APP_COMPANY_NAME,
    APP_COPYRIGHT,
    APP_DISPLAY_NAME,
    APP_EXECUTABLE,
    APP_VERSION,
)


def windows_version(version: str) -> tuple[int, int, int, int]:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:\.\d+)?", version):
        raise ValueError("Windows release versions must contain 3 or 4 numeric parts.")
    parts = tuple(int(part) for part in version.split("."))
    if any(part > 65535 for part in parts):
        raise ValueError("Windows version components must be at most 65535.")
    return (parts[0], parts[1], parts[2], parts[3] if len(parts) == 4 else 0)


def version_resource(version: str = APP_VERSION) -> str:
    numeric = windows_version(version)
    values = {
        "CompanyName": APP_COMPANY_NAME,
        "FileDescription": APP_DISPLAY_NAME,
        "FileVersion": version,
        "InternalName": "LicenseAdmin",
        "LegalCopyright": APP_COPYRIGHT,
        "OriginalFilename": APP_EXECUTABLE,
        "ProductName": APP_DISPLAY_NAME,
        "ProductVersion": version,
    }
    entries = ",\n".join(
        f"StringStruct({key!r}, {value!r})" for key, value in values.items()
    )
    return (
        "VSVersionInfo(\n"
        f"ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r}, "
        "mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),\n"
        f"kids=[StringFileInfo([StringTable('040904B0', [{entries}])]),\n"
        "VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version-resource", type=Path)
    args = parser.parse_args()
    if args.version_resource:
        args.version_resource.parent.mkdir(parents=True, exist_ok=True)
        args.version_resource.write_text(version_resource(), encoding="utf-8")
    else:
        print(APP_VERSION)


if __name__ == "__main__":
    main()
