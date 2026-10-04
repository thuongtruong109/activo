from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.request import ProxyHandler, build_opener
import uuid

ROOT = Path(__file__).resolve().parents[2]
TEST_PASSWORD = "q9#Vs7!B"  # Disposable test credential, never a deployment default.


class DockerChecks:
    def __init__(self, image: str) -> None:
        self.image = image
        self.executable = shutil.which("docker") or "docker"
        self.containers: list[str] = []
        self.label = f"activo.security-check={uuid.uuid4().hex}"

    def command(self, *arguments: str, timeout: float = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.executable, *arguments], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout, check=False,
        )

    def require(self, *arguments: str, timeout: float = 60) -> str:
        result = self.command(*arguments, timeout=timeout)
        if result.returncode:
            raise RuntimeError(f"Docker check failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def create(self, *arguments: str) -> str:
        identifier = self.require("create", "--label", self.label, *arguments)
        if len(identifier) != 64 or any(char not in "0123456789abcdef" for char in identifier):
            raise RuntimeError("Unexpected container identity.")
        self.containers.append(identifier)
        return identifier

    def cleanup(self) -> None:
        failures: list[str] = []
        for identifier in reversed(self.containers):
            # Exact IDs created by this instance only. -v removes their anonymous volumes.
            try:
                result = self.command("rm", "--force", "--volumes", identifier)
                if result.returncode:
                    failures.append(f"{identifier}: {result.stderr.strip()}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                failures.append(f"{identifier}: {type(exc).__name__}")
        if failures:
            raise RuntimeError("Unable to remove test containers: " + "; ".join(failures))

    def health(self, identifier: str, timeout: float = 45) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = json.loads(self.require("inspect", "--format", "{{json .State}}", identifier))
            if not state["Running"]:
                raise RuntimeError("Test desktop exited: " + self.require("logs", identifier))
            if self.command("exec", identifier, "python", "-m", "license_admin.container_runtime.healthcheck").returncode == 0:
                return
            time.sleep(0.5)
        raise RuntimeError("Test desktop never became healthy.")


def check_compose(checks: DockerChecks, directory: Path) -> None:
    env_file = directory / "test.env"
    env_file.write_text("", encoding="utf-8")
    environment = dict(os.environ)
    for key in ("ACTIVO_VNC_PASSWORD", "ACTIVO_PORT", "ACTIVO_SCREEN", "COMPOSE_FILE", "COMPOSE_PROFILES", "COMPOSE_ENV_FILES"):
        environment.pop(key, None)
    command = [checks.executable, "compose", "--env-file", str(env_file), "-f", str(ROOT / "docker-compose.yml"), "config", "--format", "json"]
    for value in (None, ""):
        if value is not None:
            environment["ACTIVO_VNC_PASSWORD"] = value
        result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=30, check=False)
        assert result.returncode != 0, "Compose must reject missing/empty passwords."
    environment["ACTIVO_VNC_PASSWORD"] = TEST_PASSWORD
    result = subprocess.run(command, env=environment, capture_output=True, text=True, timeout=30, check=True)
    service = json.loads(result.stdout)["services"]["license-admin"]
    assert len(service["ports"]) == 1
    port = service["ports"][0]
    assert port["host_ip"] == "127.0.0.1" and port["target"] == 6080
    assert str(port["published"]) == "6080" and port["protocol"] == "tcp"
    assert service["init"] is True
    assert "no-new-privileges:true" in service["security_opt"]
    print("PASS Compose: missing/empty secrets rejected, host port loopback only.", flush=True)


def check_fail_closed(checks: DockerChecks) -> None:
    for value in (None, "", "old-long-password", "password"):
        arguments = [] if value is None else ["--env", f"ACTIVO_VNC_PASSWORD={value}"]
        identifier = checks.create("--network", "none", *arguments, checks.image)
        checks.require("start", identifier)
        assert checks.require("wait", identifier) == "78"
        logs = checks.require("logs", identifier)
        assert "WebSocket server" not in logs and "PORT=" not in logs
    # Direct supervisor invocation must not rely on entrypoint validation.
    identifier = checks.create("--network", "none", "--entrypoint", "/app/docker/start-desktop.sh", checks.image)
    checks.require("start", identifier)
    assert checks.require("wait", identifier) == "78"
    print("PASS image: invalid secrets and direct startup fail closed (exit 78).", flush=True)


def check_desktop(checks: DockerChecks) -> str:
    identifier = checks.create(
        "--init", "--memory", "1g", "--pids-limit", "128",
        "--security-opt", "no-new-privileges:true", "--shm-size", "256m",
        "--tmpfs", "/tmp:rw,nosuid,nodev,size=128m,mode=1777",
        "--publish", "127.0.0.1::6080", "--publish", "127.0.0.1::8443",
        "--env", f"ACTIVO_VNC_PASSWORD={TEST_PASSWORD}", checks.image,
    )
    checks.require("start", identifier)
    checks.health(identifier)
    bindings = json.loads(checks.require("inspect", "--format", "{{json .NetworkSettings.Ports}}", identifier))
    assert all(item["HostIp"] == "127.0.0.1" for entries in bindings.values() if entries for item in entries)
    port = bindings["6080/tcp"][0]["HostPort"]
    with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}/vnc.html", timeout=5) as response:
        assert response.status == 200
    inspection = r'''
import importlib.util, os, pathlib, stat
for name in ('pytest', 'mypy', 'PyInstaller'):
    assert importlib.util.find_spec(name) is None, name
for name in ('tools', 'tests', '.git', 'projects', 'requirements-build.in'):
    assert not pathlib.Path('/app', name).exists(), name
listeners = [line.split()[1] for line in pathlib.Path('/proc/net/tcp').read_text().splitlines()[1:] if line.split()[3] == '0A']
assert '0100007F:170C' in listeners, listeners  # VNC 5900 on loopback only
assert all(address.startswith('0100007F:') for address in listeners if address.endswith(':170C')), listeners
assert not any(address.endswith(':17D3') for address in listeners), listeners  # X :99 TCP 6099
found = set()
for path in pathlib.Path('/proc').iterdir():
    if not path.name.isdecimal(): continue
    try:
        command = (path/'cmdline').read_bytes().split(b'\0')
        status = (path/'status').read_text()
        environment = (path/'environ').read_bytes()
    except (PermissionError, FileNotFoundError, ProcessLookupError): continue
    if not command: continue
    name = pathlib.Path(os.fsdecode(command[0])).name
    if any(pathlib.Path(os.fsdecode(part)).name == 'websockify' for part in command[:2]):
        name = 'websockify'
    if name in ('Xvfb', 'fluxbox', 'x11vnc', 'websockify') or command[1:3] == [b'-m', b'license_admin']:
        uid = next(line for line in status.splitlines() if line.startswith('Uid:')).split()[1:]
        assert set(uid) == {'10001'}, (name, uid)
        assert b'ACTIVO_VNC_PASSWORD=' not in environment, name
        found.add(name if name != 'python' else 'application')
assert {'Xvfb', 'fluxbox', 'x11vnc', 'websockify', 'application'} <= found, found
files = list(pathlib.Path('/tmp/runtime-activo').glob('vnc-*.auth'))
assert len(files) == 1
assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
assert stat.S_IMODE(files[0].parent.stat().st_mode) == 0o700
'''
    checks.require("exec", "--user", "10001", identifier, "python", "-c", inspection)
    authentication = r'''
import socket, struct
from cryptography.hazmat.primitives.ciphers import Cipher, modes
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from license_admin.container_runtime.healthcheck import receive_exact
# VNC's DES uses bit-reversed password bytes. TripleDES with the same key in
# all three positions is equivalent to DES; ONLY for this protocol test.
key = bytes(int(f'{value:08b}'[::-1], 2) for value in b'q9#Vs7!B')
for valid in (False, True):
    with socket.create_connection(('127.0.0.1', 5900), timeout=5) as connection:
        assert receive_exact(connection, 12) == b'RFB 003.008\n'
        connection.sendall(b'RFB 003.008\n')
        count = receive_exact(connection, 1)[0]
        assert receive_exact(connection, count) == b'\x02'
        connection.sendall(b'\x02')
        challenge = receive_exact(connection, 16)
        encryptor = Cipher(TripleDES(key*3), modes.ECB()).encryptor()
        response = encryptor.update(challenge) + encryptor.finalize() if valid else bytes(16)
        connection.sendall(response)
        result = struct.unpack('>I', receive_exact(connection, 4))[0]
        assert result == (0 if valid else 1), (valid, result)
        if valid:
            connection.sendall(b'\x01')
            initialization = receive_exact(connection, 24)
            assert struct.unpack('>HH', initialization[:4]) == (1440, 900)
'''
    checks.require("exec", "--user", "10001", identifier, "python", "-c", authentication)
    logs = checks.require("logs", identifier)
    assert TEST_PASSWORD not in logs
    print("PASS desktop: wrong VNC password denied, correct password accepted, HTTP, loopback VNC, UID 10001, private auth file, no dev tooling.", flush=True)
    return identifier


def check_restart(checks: DockerChecks, identifier: str) -> None:
    checks.require("stop", "--time", "10", identifier)
    assert checks.require("inspect", "--format", "{{.State.ExitCode}}", identifier) == "0"
    checks.require("start", identifier)
    checks.health(identifier)
    print("PASS lifecycle: graceful shutdown and restart with fresh tmpfs.", flush=True)


def check_service_failure(checks: DockerChecks, identifier: str) -> None:
    kill = r'''
import os, pathlib, signal
for path in pathlib.Path('/proc').iterdir():
    if not path.name.isdecimal(): continue
    try: command = (path/'cmdline').read_bytes().split(b'\0')
    except (PermissionError, FileNotFoundError, ProcessLookupError): continue
    if command and command[0] == b'x11vnc':
        os.kill(int(path.name), signal.SIGTERM)
        break
else: raise RuntimeError('VNC not found')
'''
    checks.require("exec", "--user", "10001", identifier, "python", "-c", kill)
    assert checks.require("wait", identifier, timeout=20) != "0"
    print("PASS supervisor: VNC failure stops the entire container.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Isolated private-desktop checks; never reads operator .env/data.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--proxy-image", help="Optional official Nginx image, pinned by digest, for TLS/WS integration.")
    arguments = parser.parse_args()
    checks = DockerChecks(arguments.image)
    base = ROOT / "build" / "docker-check"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="check-", dir=base) as temporary:
        try:
            check_compose(checks, Path(temporary))
            check_fail_closed(checks)
            identifier = check_desktop(checks)
            if arguments.proxy_image:
                # Lazy import keeps the runtime-only test stdlib-only.
                from tools.docker.check_proxy import check_proxy
                check_proxy(checks, identifier, Path(temporary), arguments.proxy_image)
            check_restart(checks, identifier)
            check_service_failure(checks, identifier)
        finally:
            # Release bind mounts BEFORE removing their fixtures, also on Windows.
            checks.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
