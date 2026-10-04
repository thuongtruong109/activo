"""Inspect PE metadata/icons and produce checksums after signing finishes."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys
from collections.abc import Iterator

import pefile  # type: ignore[import-untyped]

from license_admin.version import APP_COMPANY_NAME, APP_DISPLAY_NAME, APP_VERSION


def inspect_native_binaries(analysis: Path) -> list[dict[str, object]]:
    """Reject accidental bundling from ambient PATH (e.g. an incompatible ICU)."""
    def entries(value: object) -> Iterator[tuple[str, str, str]]:
        if isinstance(value, (list, tuple)):
            if len(value) == 3 and all(isinstance(item, str) for item in value):
                yield value[0], value[1], value[2]
            else:
                for child in value:
                    yield from entries(child)

    roots = ((Path(sys.prefix).resolve(), "locked-environment"),
             (Path(sys.base_prefix).resolve(), "cpython"))
    report: list[dict[str, object]] = []
    for name, source, kind in entries(ast.literal_eval(analysis.read_text(encoding="utf-8"))):
        if kind != "BINARY":
            continue
        path = Path(source).resolve()
        owner = next(((label, path.relative_to(root)) for root, label in roots if path.is_relative_to(root)), None)
        if owner is None:
            raise RuntimeError(f"Unapproved native binary source: {name}: {path}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        report.append({"name": name, "source": f"{owner[0]}/{owner[1].as_posix()}", "sha256": digest})
    if not report:
        raise RuntimeError("PyInstaller analysis contained no native binaries")
    return sorted(report, key=lambda item: str(item["name"]))


def inspect_executable(path: Path) -> dict[str, object]:
    with pefile.PE(str(path)) as pe:
        values = {}
        for info_group in getattr(pe, "FileInfo", []):
            for info in info_group:
                for table in getattr(info, "StringTable", []):
                    values.update({k.decode(): v.decode("utf-8").strip("\x00 ") for k, v in table.entries.items()})
        expected = {"ProductName": APP_DISPLAY_NAME, "CompanyName": APP_COMPANY_NAME,
            "FileVersion": APP_VERSION, "ProductVersion": APP_VERSION}
        if any(values.get(key) != value for key, value in expected.items()) or not values.get("LegalCopyright"):
            raise RuntimeError(f"Incorrect PE VersionInfo: {values}")
        resolutions: set[int] = set()
        for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if entry.id == pefile.RESOURCE_TYPE["RT_GROUP_ICON"]:
                for group in entry.directory.entries:
                    for language in group.directory.entries:
                        data = language.data.struct
                        payload = pe.get_data(data.OffsetToData, data.Size)
                        for index in range(struct.unpack_from("<H", payload, 4)[0]):
                            width = payload[6 + index * 14]
                            resolutions.add(width or 256)
    if not {16, 24, 32, 48, 64, 128, 256}.issubset(resolutions):
        raise RuntimeError(f"Missing multi-resolution PE icon: {resolutions}")
    return {"versionInfo": values, "iconSizes": sorted(resolutions)}


def checksums(directory: Path) -> None:
    files = sorted(path for path in directory.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt")
    lines = []
    for path in files:
        with path.open("rb") as stream:
            lines.append(f"{hashlib.file_digest(stream, 'sha256').hexdigest()}  {path.name}")
    (directory / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--checksums", type=Path)
    parser.add_argument("--analysis", type=Path)
    parser.add_argument("--native-report", type=Path)
    args = parser.parse_args()
    if args.analysis:
        native = inspect_native_binaries(args.analysis)
        if not args.native_report:
            parser.error("--native-report is required with --analysis")
        args.native_report.write_text(json.dumps(native, indent=2) + "\n", encoding="utf-8")
    if args.exe:
        report = inspect_executable(args.exe)
        if args.report:
            args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        else:
            print(json.dumps(report, indent=2))
    if args.checksums:
        checksums(args.checksums)
