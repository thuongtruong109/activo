# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


project_root = Path(SPECPATH)
sys.path.insert(0, str(project_root))
from tools.release.metadata import version_resource
from tools.release.native import isolate_build_path
from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file

isolate_build_path()

asset_directory = project_root / "license_admin" / "assets"
release_directory = project_root / "build" / "release-metadata"
release_directory.mkdir(parents=True, exist_ok=True)
version_path = release_directory / "version-info.txt"
version_path.write_text(version_resource(), encoding="utf-8")
version_info = load_version_info_from_text_file(str(version_path))
release_data = []
for name in ("THIRD_PARTY_NOTICES.txt", "sbom.cdx.json"):
    path = release_directory / name
    if path.is_file():
        release_data.append((str(path), "release"))

analysis = Analysis(
    [str(project_root / "license_admin_gui.pyw")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[(str(asset_directory), "license_admin/assets"), *release_data],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="LicenseAdmin",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(asset_directory / "app.ico"),
    version=version_info,
)
