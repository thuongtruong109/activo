"""Run the standalone License Admin desktop application."""

from __future__ import annotations

import sys
from pathlib import Path
import json


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test-output":
        if len(sys.argv) != 3:
            return 2
        output = Path(sys.argv[2])
        try:
            from license_admin.release_smoke import run_smoke_test

            return run_smoke_test(output)
        except Exception as exc:
            # Capture DLL/import failures before Qt can initialize. No project access.
            try:
                output.write_text(json.dumps({"ok": False, "error": str(exc)}) + "\n", encoding="utf-8")
            except OSError:
                pass
            return 1
    from license_admin.application import run_application

    return run_application()


if __name__ == "__main__":
    raise SystemExit(main())
