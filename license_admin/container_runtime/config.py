from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import os
import re
import sys


class ContainerConfigurationError(ValueError):
    """Invalid private-desktop configuration; messages never contain secrets."""


@dataclass(frozen=True)
class DesktopConfig:
    password: str = field(repr=False)
    display: str = ":99"
    screen: str = "1440x900x24"


def load_config(environment: Mapping[str, str] | None = None) -> DesktopConfig:
    values = os.environ if environment is None else environment
    password = values.get("ACTIVO_VNC_PASSWORD", "")
    if not password:
        raise ContainerConfigurationError(
            "Set ACTIVO_VNC_PASSWORD; refusing to start an unauthenticated desktop."
        )
    # RFB VNC authentication silently truncates to 8 bytes. Reject instead.
    if len(password) != 8 or any(not 33 <= ord(char) <= 126 for char in password):
        raise ContainerConfigurationError(
            "ACTIVO_VNC_PASSWORD must contain exactly 8 random printable ASCII "
            "characters without spaces. Use TLS and separate strong proxy authentication."
        )
    if password.lower() in {"password", "changeme", "12345678", "qwertyui"}:
        raise ContainerConfigurationError("Refusing a common default VNC credential.")
    display = values.get("DISPLAY", ":99")
    if re.fullmatch(r":[0-9]{1,3}", display) is None:
        raise ContainerConfigurationError("DISPLAY must be a local display such as :99.")
    screen = values.get("ACTIVO_SCREEN", "1440x900x24")
    match = re.fullmatch(r"([0-9]{2,4})x([0-9]{2,4})x(16|24)", screen)
    if match is None or not all(64 <= int(value) <= 8192 for value in match.groups()[:2]):
        raise ContainerConfigurationError(
            "ACTIVO_SCREEN must be WIDTHxHEIGHTxDEPTH (64..8192 pixels, depth 16 or 24)."
        )
    return DesktopConfig(password=password, display=display, screen=screen)


def main() -> int:
    try:
        load_config()
    except ContainerConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
