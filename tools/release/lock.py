"""Validate pylock inputs and export pip's hash-checked compatibility format."""

from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path
import re
import sys
import tomllib
from typing import cast, NotRequired, TypedDict


class WheelHashes(TypedDict):
    sha256: str


class LockedWheel(TypedDict):
    url: str
    hashes: WheelHashes


class LockedPackage(TypedDict):
    name: str
    version: str
    wheels: list[LockedWheel]
    marker: NotRequired[str]


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def read_lock(path: Path) -> list[LockedPackage]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    if document.get("lock-version") != "1.0":
        raise ValueError("Unsupported pylock format")
    packages = cast(list[LockedPackage], document["packages"])
    if not isinstance(packages, list) or not packages:
        raise ValueError("The lock must contain pinned packages")
    seen: set[str] = set()
    for package in packages:
        name = normalized(package["name"])
        if not name or name in seen:
            raise ValueError(f"Invalid/duplicate locked package: {name}")
        seen.add(name)
        if not package.get("version") or not package.get("wheels"):
            raise ValueError(f"Unpinned or non-wheel dependency: {package['name']}")
        for wheel in package["wheels"]:
            if not re.fullmatch(r"[a-f0-9]{64}", wheel["hashes"].get("sha256", "")):
                raise ValueError(f"Missing wheel hash: {package['name']}")
    return packages


def export_requirements(packages: list[LockedPackage]) -> str:
    lines = ["# Generated from pylock.windows.toml; do not edit.", "--only-binary=:all:"]
    for package in packages:
        marker = f" ; {package['marker']}" if package.get("marker") else ""
        hashes = sorted({wheel["hashes"]["sha256"] for wheel in package["wheels"]})
        lines.append(f"{package['name']}=={package['version']}{marker} \\")
        lines.append(" \\\n".join(f"    --hash=sha256:{digest}" for digest in hashes))
    return "\n".join(lines) + "\n"


def check_environment(packages: list[LockedPackage]) -> None:
    if sys.platform != "win32" or sys.maxsize <= 2**32 or sys.version_info[:3] != (3, 12, 10):
        raise RuntimeError("The release lock targets Windows x64 / CPython 3.12.10.")
    expected = {normalized(p["name"]): p["version"] for p in packages}
    actual = {normalized(d.metadata["Name"]): d.version for d in importlib.metadata.distributions()}
    # pip can be present in a pip-created venv; all build/runtime packages must match.
    actual.pop("pip", None)
    if expected != actual:
        changed = sorted(
            name for name in expected.keys() | actual.keys()
            if expected.get(name) != actual.get(name)
        )
        raise RuntimeError(f"Release environment does not match the lock: {changed}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=Path("pylock.windows.toml"))
    parser.add_argument("--export", type=Path)
    parser.add_argument("--check-environment", action="store_true")
    args = parser.parse_args()
    packages = read_lock(args.lock)
    if args.export:
        args.export.write_text(export_requirements(packages), encoding="utf-8")
    if args.check_environment:
        check_environment(packages)


if __name__ == "__main__":
    main()
