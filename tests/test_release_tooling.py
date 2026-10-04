from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file
from tests.workspace_temp import workspace_temp_dir
from license_admin.app_identity import APP_ICON_PATH
from license_admin.release_smoke import run_smoke_test
from license_admin.__main__ import main
from license_admin.version import APP_COMPANY_NAME, APP_DISPLAY_NAME, APP_VERSION
from tools.release.artifacts import checksums, inspect_native_binaries
from tools.release.inventory import generate, runtime_dependencies
from tools.release.lock import export_requirements, read_lock
from tools.release.metadata import version_resource, windows_version
from tools.release.native import isolate_build_path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseToolingTests(unittest.TestCase):
    def test_windows_version_is_numeric_and_bounded(self) -> None:
        self.assertEqual(windows_version("1.2.3"), (1, 2, 3, 0))
        self.assertEqual(windows_version("1.2.3.4"), (1, 2, 3, 4))
        for invalid in ("1.2", "v1.2.3", "1.2.3-rc1", "1.2.3.65536", "-1.2.3", "1.2.3.4.5"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                windows_version(invalid)

    def test_resource_contains_shared_branding_and_version(self) -> None:
        with workspace_temp_dir() as directory:
            path = Path(directory) / "version-info.txt"
            path.write_text(version_resource(), encoding="utf-8")
            resource = load_version_info_from_text_file(str(path))
            major, minor, patch_version, build = windows_version(APP_VERSION)
            self.assertEqual(resource.ffi.fileVersionMS, (major << 16) | minor)
            self.assertEqual(resource.ffi.fileVersionLS, (patch_version << 16) | build)
            fields = {item.name: item.val for item in resource.kids[0].kids[0].kids}
            self.assertEqual(fields["ProductName"], APP_DISPLAY_NAME)
            self.assertEqual(fields["CompanyName"], APP_COMPANY_NAME)
            self.assertEqual(fields["FileVersion"], APP_VERSION)
            self.assertEqual(fields["ProductVersion"], APP_VERSION)
            self.assertTrue(fields["LegalCopyright"])

    def test_local_icon_has_all_windows_resolutions(self) -> None:
        data = APP_ICON_PATH.read_bytes()
        self.assertEqual(struct.unpack_from("<HH", data), (0, 1))
        count = struct.unpack_from("<H", data, 4)[0]
        sizes = set()
        for index in range(count):
            width, height, _, _, _, _, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + index * 16)
            self.assertEqual(width, height)
            self.assertLessEqual(offset + size, len(data))
            sizes.add(width or 256)
        self.assertEqual(sizes, {16, 24, 32, 48, 64, 128, 256})

    def test_committed_pip_export_matches_pylock(self) -> None:
        packages = read_lock(ROOT / "pylock.windows.toml")
        self.assertEqual(export_requirements(packages), (ROOT / "requirements-build.windows.txt").read_text(encoding="utf-8"))
        for package in packages:
            self.assertTrue(all(wheel["url"].startswith("https://files.pythonhosted.org/") for wheel in package["wheels"]))

    def test_bad_or_missing_lock_hash_is_rejected(self) -> None:
        with workspace_temp_dir() as directory:
            path = Path(directory) / "pylock.toml"
            for digest in ("", "123", "g" * 64):
                path.write_text('lock-version = "1.0"\n[[packages]]\nname = "requests"\nversion = "2.34.2"\nwheels = [{hashes = {sha256 = "' + digest + '"}}]\n', encoding="utf-8")
                with self.subTest(digest=digest), self.assertRaises(ValueError):
                    read_lock(path)

    def test_checksums_reflect_final_bytes_and_never_hash_themselves(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            artifact = root / "signed.exe"
            artifact.write_bytes(b"unsigned")
            checksums(root)
            original = (root / "SHA256SUMS.txt").read_text()
            artifact.write_bytes(b"signed-and-timestamped")
            checksums(root)
            result = (root / "SHA256SUMS.txt").read_text()
            self.assertNotEqual(original, result)
            self.assertEqual(result, hashlib.sha256(artifact.read_bytes()).hexdigest() + "  signed.exe\n")

    def test_native_inventory_rejects_ambient_path_dlls(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            approved = root / "venv"
            approved.mkdir()
            toc = root / "Analysis-00.toc"
            toc.write_text(repr([("icuuc.dll", str(root / "unrelated-tool/icuuc.dll"), "BINARY")]), encoding="utf-8")
            with patch("sys.prefix", str(approved)), patch("sys.base_prefix", str(approved)):
                with self.assertRaisesRegex(RuntimeError, "Unapproved native binary"):
                    inspect_native_binaries(toc)

    def test_native_inventory_hashes_only_approved_binaries(self) -> None:
        with workspace_temp_dir() as directory:
            root = Path(directory)
            binary = root / "QtCore.pyd"
            binary.write_bytes(b"locked-wheel-binary")
            toc = root / "Analysis-00.toc"
            toc.write_text(repr(([], [("PySide6/QtCore.pyd", str(binary), "BINARY")], [("asset", "irrelevant", "DATA")])), encoding="utf-8")
            with patch("sys.prefix", directory), patch("sys.base_prefix", directory):
                report = inspect_native_binaries(toc)
            self.assertEqual(len(report), 1)
            self.assertEqual(report[0]["source"], "locked-environment/QtCore.pyd")
            self.assertEqual(report[0]["sha256"], hashlib.sha256(binary.read_bytes()).hexdigest())

    def test_probe_dispatcher_records_import_failure_before_qt_starts(self) -> None:
        with workspace_temp_dir() as directory:
            output = Path(directory) / "probe.json"
            with patch("sys.argv", ["LicenseAdmin.exe", "--self-test-output", str(output)]), patch.dict("sys.modules", {"license_admin.release_smoke": None}):
                self.assertEqual(main(), 1)
            result = json.loads(output.read_text())
            self.assertFalse(result["ok"])
            self.assertIn("license_admin.release_smoke", result["error"])

    def test_invalid_probe_arguments_never_start_normal_application(self) -> None:
        with patch("sys.argv", ["LicenseAdmin.exe", "--self-test-output"]), patch.dict("sys.modules", {"license_admin.application": None}):
            self.assertEqual(main(), 2)

    def test_normal_entry_point_dispatches_to_application(self) -> None:
        with patch("sys.argv", ["LicenseAdmin.exe"]), patch("license_admin.application.run_application", return_value=7) as start:
            self.assertEqual(main(), 7)
            start.assert_called_once_with()

    def test_native_build_path_does_not_inherit_ambient_tools(self) -> None:
        with patch("sys.platform", "win32"), patch.dict(os.environ, {"PATH": "unrelated/poppler;unrelated/libheif"}):
            isolate_build_path()
            self.assertNotIn("poppler", os.environ["PATH"])
            self.assertNotIn("libheif", os.environ["PATH"])
            self.assertIn(str(Path(os.environ["SystemRoot"]) / "System32"), os.environ["PATH"])

    def test_offline_smoke_checks_qt_crypto_icon_and_application_version(self) -> None:
        with workspace_temp_dir() as directory:
            path = Path(directory) / "probe.json"
            self.assertEqual(run_smoke_test(path), 0)
            result = json.loads(path.read_text())
            self.assertTrue(result["ok"])
            self.assertEqual(result["applicationVersion"], APP_VERSION)
            self.assertEqual(result["iconSizes"], [16, 24, 32, 48, 64, 128, 256])

    def test_missing_bundled_icon_fails_smoke(self) -> None:
        with workspace_temp_dir() as directory:
            path = Path(directory) / "probe.json"
            with patch("license_admin.release_smoke.APP_ICON_PATH", Path(directory) / "missing.ico"):
                self.assertEqual(run_smoke_test(path), 1)
            self.assertFalse(json.loads(path.read_text())["ok"])

    def test_inventory_has_hashes_notices_and_runtime_scope(self) -> None:
        with workspace_temp_dir() as directory:
            output = Path(directory)
            # This test also runs in developer environments; production always checks
            # exact environment equality without patching.
            with patch("tools.release.inventory.check_environment"):
                generate(output, ROOT / "pylock.windows.toml")
            sbom = json.loads((output / "sbom.cdx.json").read_text(encoding="utf-8"))
            self.assertEqual(sbom["bomFormat"], "CycloneDX")
            self.assertEqual(sbom["specVersion"], "1.6")
            self.assertEqual(sbom["metadata"]["component"]["version"], APP_VERSION)
            components = {item["name"]: item for item in sbom["components"]}
            self.assertEqual(components["pyinstaller"]["scope"], "excluded")
            self.assertEqual(components["pyside6"]["scope"], "required")
            expected = {package["name"]: package["version"] for package in read_lock(ROOT / "pylock.windows.toml")}
            self.assertEqual(components["requests"]["version"], expected["requests"])
            for item in components.values():
                for ref in item.get("externalReferences", []):
                    self.assertEqual(ref["hashes"][0]["alg"], "SHA-256")
            notices = (output / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
            for term in ("GNU LESSER GENERAL PUBLIC LICENSE", "GNU GENERAL PUBLIC LICENSE", "Apache License", "PYTHON SOFTWARE FOUNDATION", "Icons8"):
                self.assertIn(term, notices)
            runtime = runtime_dependencies()
            self.assertTrue({"requests", "pyside6", "cryptography", "shiboken6", "urllib3"}.issubset(runtime))


if __name__ == "__main__":
    unittest.main()
