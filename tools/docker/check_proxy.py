from __future__ import annotations

import base64
import hashlib
import http.client
import json
from pathlib import Path
import socket
import ssl
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.docker.check_runtime import DockerChecks

ORIGIN = "https://license-admin.example.invalid:8443"
PROXY_SECRET = "disposable-proxy-test-credential-not-for-deployment"

# Use the runtime's already-locked cryptography, not an extra host dependency.
# Self-signed certificates and SHA1 htpasswd here are TEST FIXTURES ONLY.
CERTIFICATE_FIXTURE = r'''
import datetime, json
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
    .public_key(key.public_key()).serial_number(x509.random_serial_number())
    .not_valid_before(now-datetime.timedelta(minutes=5)).not_valid_after(now+datetime.timedelta(hours=1))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost')]), critical=False)
    .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    .sign(key, hashes.SHA256()))
print(json.dumps({'cert': cert.public_bytes(serialization.Encoding.PEM).decode(),
    'key': key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()).decode()}))
'''


def websocket_status(context: ssl.SSLContext, port: int, *, authorized: bool, origin: str | None, path: str = "/websockify") -> tuple[int, bytes]:
    with socket.create_connection(("127.0.0.1", port), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname="localhost") as connection:
            headers = [
                f"GET {path} HTTP/1.1", "Host: license-admin.example.invalid:8443",
                "Upgrade: websocket", "Connection: Upgrade", "Sec-WebSocket-Version: 13",
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==", "Sec-WebSocket-Protocol: binary",
            ]
            if origin is not None:
                headers.append(f"Origin: {origin}")
            if authorized:
                credential = base64.b64encode(f"operator:{PROXY_SECRET}".encode()).decode()
                headers.append(f"Authorization: Basic {credential}")
            connection.sendall(("\r\n".join(headers) + "\r\n\r\n").encode())
            response = bytearray()
            while b"\r\n\r\n" not in response:
                chunk = connection.recv(4096)
                if not chunk:
                    raise RuntimeError("Incomplete WebSocket handshake.")
                response.extend(chunk)
            header, payload = bytes(response).split(b"\r\n\r\n", 1)
            status = int(header.split(b" ", 2)[1])
            if status == 101:
                while b"RFB 003.008\n" not in payload and len(payload) < 4096:
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    payload += chunk
            return status, payload


def check_proxy(checks: DockerChecks, desktop: str, directory: Path, image: str) -> None:
    if "@sha256:" not in image:
        raise ValueError("The integration proxy image must be pinned by digest.")
    tls = directory / "tls"
    tls.mkdir()
    fixture = json.loads(checks.require("exec", desktop, "python", "-c", CERTIFICATE_FIXTURE))
    (tls / "tls.fullchain.pem").write_text(fixture["cert"], encoding="ascii")
    (tls / "tls.key").write_text(fixture["key"], encoding="ascii")
    password_hash = base64.b64encode(hashlib.sha1(PROXY_SECRET.encode()).digest()).decode()
    (tls / "proxy.htpasswd").write_text(f"operator:{{SHA}}{password_hash}\n", encoding="ascii")
    # The production example runs on the HOST. Only this disposable shared-network
    # container listens on all container interfaces, behind loopback host mappings.
    root = Path(__file__).resolve().parents[2]
    example = (root / "docker" / "reverse-proxy" / "nginx.conf.example").read_text(encoding="utf-8")
    assert example.count("listen 127.0.0.1:8443 ssl;") == 1
    example = example.replace("listen 127.0.0.1:8443 ssl;", "listen 0.0.0.0:8443 ssl;")
    configuration = directory / "nginx.conf"
    configuration.write_text("events {}\nhttp {\n" + example + "\n}\n", encoding="utf-8")
    checks.require("pull", image, timeout=180)
    proxy = checks.create(
        "--network", f"container:{desktop}", "--entrypoint", "nginx",
        "--mount", f"type=bind,source={configuration.resolve()},target=/etc/nginx/nginx.conf,readonly",
        "--mount", f"type=bind,source={tls.resolve()},target=/etc/nginx/activo,readonly",
        image, "-g", "daemon off;",
    )
    checks.require("start", proxy)
    bindings = json.loads(checks.require("inspect", "--format", "{{json .NetworkSettings.Ports}}", desktop))
    port = int(bindings["8443/tcp"][0]["HostPort"])
    context = ssl.create_default_context(cafile=str(tls / "tls.fullchain.pem"))
    deadline = time.monotonic() + 15
    while True:
        connection = http.client.HTTPSConnection("localhost", port, context=context, timeout=2)
        try:
            connection.request("GET", "/vnc.html")
            assert connection.getresponse().status == 401
            break
        except (ConnectionError, OSError):
            if time.monotonic() >= deadline:
                raise RuntimeError("TLS proxy did not become ready: " + checks.require("logs", proxy))
            time.sleep(0.25)
        finally:
            connection.close()
    credential = base64.b64encode(f"operator:{PROXY_SECRET}".encode()).decode()
    connection = http.client.HTTPSConnection("localhost", port, context=context, timeout=5)
    try:
        connection.request("GET", "/vnc.html", headers={"Authorization": f"Basic {credential}"})
        assert connection.getresponse().status == 200
    finally:
        connection.close()
    assert websocket_status(context, port, authorized=False, origin=ORIGIN)[0] == 401
    for origin in (None, "https://attacker.invalid", "null"):
        assert websocket_status(context, port, authorized=True, origin=origin)[0] == 403
    status, payload = websocket_status(context, port, authorized=True, origin=ORIGIN)
    assert status == 101 and b"RFB 003.008\n" in payload
    assert websocket_status(context, port, authorized=True, origin="https://attacker.invalid", path="/other-path")[0] != 101
    checks.require("exec", proxy, "nginx", "-t")
    # Stop the proxy before fixture removal and before stopping its network owner.
    checks.require("stop", "--time", "5", proxy)
    print("PASS TLS proxy: trusted test certificate, HTTP/WS auth, Origin rejection, valid WSS carries RFB, no path bypass.", flush=True)
