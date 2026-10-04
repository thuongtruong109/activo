from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import FrameType

from .config import ContainerConfigurationError, load_config


def signal_process_group(process: subprocess.Popen[bytes], *, force: bool = False) -> None:
    # Docker runs on Linux; the fallback keeps configuration tests importable on Windows.
    if sys.platform == "win32":
        if process.poll() is None:
            if force:
                process.kill()
            else:
                process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass


def stop_processes(processes: list[subprocess.Popen[bytes]]) -> None:
    """Stop whole sessions, including children, before removing the auth file."""
    for process in reversed(processes):
        signal_process_group(process)
    deadline = time.monotonic() + 5
    for process in reversed(processes):
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            signal_process_group(process, force=True)
            process.wait(timeout=2)


def run_desktop() -> int:
    config = load_config()  # Must precede filesystem changes and ALL listeners.
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp/runtime-activo"))
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    descriptor, filename = tempfile.mkstemp(prefix="vnc-", suffix=".auth", dir=runtime)
    os.close(descriptor)
    auth_file = Path(filename)
    processes: list[subprocess.Popen[bytes]] = []
    stopped = False

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        nonlocal stopped
        stopped = True

    previous_handlers = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    child_environment = dict(os.environ)
    child_environment.pop("ACTIVO_VNC_PASSWORD", None)
    child_environment["DISPLAY"] = config.display

    def start(command: list[str]) -> subprocess.Popen[bytes]:
        process = subprocess.Popen(command, env=child_environment, start_new_session=True)
        processes.append(process)
        return process

    try:
        # Suppress x11vnc's output and never format exceptions containing its argv.
        result = subprocess.run(
            ["x11vnc", "-storepasswd", config.password, filename],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=child_environment,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("Unable to create the VNC authentication file.")
        auth_file.chmod(0o600)
        server = start([
            "Xvfb", config.display, "-screen", "0", config.screen, "-ac", "-nolisten", "tcp"
        ])
        socket_path = Path(f"/tmp/.X11-unix/X{config.display[1:]}")
        deadline = time.monotonic() + 5
        while not socket_path.is_socket():
            if stopped or server.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Xvfb did not become ready.")
            time.sleep(0.1)
        start(["fluxbox"])
        start([
            "x11vnc", "-display", config.display, "-forever", "-shared",
            "-listen", "127.0.0.1", "-localhost", "-rfbport", "5900",
            "-noxdamage", "-quiet", "-safer", "-rfbauth", filename,
        ])
        # 6080 must be reachable through Docker's loopback-only host mapping.
        start(["websockify", "--web=/usr/share/novnc/", "0.0.0.0:6080", "127.0.0.1:5900"])
        application = start([sys.executable, "-m", "license_admin"])
        while not stopped:
            for process in processes:
                status = process.poll()
                if status is not None:
                    if process is application:
                        return max(0, status) if status >= 0 else 1
                    raise RuntimeError("A desktop service exited; stopping the entire session.")
            time.sleep(0.25)
        return 0
    finally:
        try:
            stop_processes(processes)
        finally:
            auth_file.unlink(missing_ok=True)
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def main() -> int:
    try:
        return run_desktop()
    except ContainerConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 78
    except Exception:
        # Avoid leaking passwords from subprocess argv in tracebacks/logs.
        print("Desktop startup or supervision failed; session stopped.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
