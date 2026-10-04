"""Create a CycloneDX inventory and collect actual bundled license texts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import distribution
import json
from pathlib import Path
import platform
import sys

from packaging.requirements import Requirement
from PySide6.QtCore import qVersion
from cryptography.hazmat.backends.openssl.backend import backend

from license_admin.version import APP_COMPANY_NAME, APP_DISPLAY_NAME, APP_VERSION
from tools.release.lock import check_environment, normalized, read_lock

RUNTIME_ROOTS = ("PySide6", "cryptography", "requests")


def runtime_dependencies() -> set[str]:
    found: set[str] = set()
    pending = list(RUNTIME_ROOTS)
    while pending:
        name = normalized(pending.pop())
        if name in found:
            continue
        found.add(name)
        for value in distribution(name).requires or []:
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return found


def generate(output: Path, lock: Path) -> None:
    packages = read_lock(lock)
    check_environment(packages)
    output.mkdir(parents=True, exist_ok=True)
    runtime = runtime_dependencies()
    components = []
    notices = [
        f"{APP_DISPLAY_NAME} {APP_VERSION} — third-party notices\n",
        "This inventory includes runtime libraries and build tools (scope: excluded).",
        "Qt/PySide is dynamically linked; LGPL/GPL/commercial obligations must be reviewed",
        "before distribution. The inventory is not a license grant for this application.",
        "Application icon: Icons8 https://icons8.com/icon/nAYITb36Rm9S/key",
        "Bundled local icon; review the Icons8 asset license/attribution before release.\n",
    ]
    for package in packages:
        name, version = package["name"], package["version"]
        dist = distribution(name)
        purl = f"pkg:pypi/{normalized(name)}@{version}"
        license_name = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "Unspecified"
        component = {
            "type": "library",
            "bom-ref": purl,
            "name": name,
            "version": version,
            "purl": purl,
            "scope": "required" if normalized(name) in runtime else "excluded",
            "licenses": [{"license": {"name": license_name}}],
            "externalReferences": [{"type": "distribution", "url": w["url"],
                "hashes": [{"alg": "SHA-256", "content": w["hashes"]["sha256"]}]} for w in package["wheels"]],
        }
        components.append(component)
        if normalized(name) not in runtime and normalized(name) != "pyinstaller":
            continue
        notices.append(f"\n{'=' * 72}\n{name} {version}\nDeclared license: {license_name}\n")
        for file in sorted(dist.files or [], key=str):
            if any(term in str(file).lower() for term in ("license", "copying", "notice")):
                path = Path(str(dist.locate_file(file)))
                if path.is_file() and path.stat().st_size < 2_000_000:
                    notices.append(f"\n--- {file} ---\n")
                    notices.append(path.read_text(encoding="utf-8", errors="replace"))

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError("CPython license text is missing from the build interpreter")
    notices.extend(["\n--- CPython and bundled library license notices ---\n", python_license.read_text(encoding="utf-8")])
    legal_root = Path(__file__).resolve().parents[2] / "third_party"
    for name in ("LGPL-3.0.txt", "GPL-3.0.txt", "OpenSSL-LICENSE.txt"):
        path = legal_root / name
        if not path.is_file():
            raise RuntimeError(f"Required third-party notice is missing: {path}")
        notices.extend([f"\n--- {name} ---\n", path.read_text(encoding="utf-8")])
    for name, version, license_name in (
        ("CPython", platform.python_version(), "PSF-2.0"),
        ("Qt", qVersion(), "LGPL-3.0-only OR GPL-3.0-only OR commercial"),
        ("OpenSSL (cryptography wheel)", backend.openssl_version_text(), "Apache-2.0"),
    ):
        components.append({"type": "library", "bom-ref": name, "name": name, "version": version,
            "licenses": [{"license": {"name": license_name}}]})
    root_ref = f"pkg:generic/activo/license-admin@{APP_VERSION}"
    sbom = {
        "$schema": "http://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "component": {"type": "application", "bom-ref": root_ref, "name": APP_DISPLAY_NAME,
                "version": APP_VERSION, "supplier": {"name": APP_COMPANY_NAME}},
            "properties": [{"name": "activo:lock-sha256", "value": hashlib.sha256(lock.read_bytes()).hexdigest()},
                {"name": "activo:inventory-scope", "value": "Locked wheels, runtime dependency closure, CPython, Qt and wheel OpenSSL; not a complete native transitive scan"}],
        },
        "components": components,
        "dependencies": [{"ref": root_ref, "dependsOn": [c["bom-ref"] for c in components if c.get("scope") != "excluded"]}],
    }
    (output / "sbom.cdx.json").write_text(json.dumps(sbom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "THIRD_PARTY_NOTICES.txt").write_text("\n".join(notices), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("build/release-metadata"))
    parser.add_argument("--lock", type=Path, default=Path("pylock.windows.toml"))
    arguments = parser.parse_args()
    generate(arguments.output, arguments.lock)
