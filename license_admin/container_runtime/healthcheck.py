from __future__ import annotations

import socket
from urllib.request import ProxyHandler, build_opener


def receive_exact(connection: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = connection.recv(count - len(data))
        if not chunk:
            raise RuntimeError("Incomplete RFB response.")
        data.extend(chunk)
    return bytes(data)


def require_vnc_authentication() -> None:
    """HTTP alone is not healthy: require VNC auth and reject anonymous RFB."""
    with socket.create_connection(("127.0.0.1", 5900), timeout=2) as connection:
        if receive_exact(connection, 12) != b"RFB 003.008\n":
            raise RuntimeError("Unexpected RFB protocol version.")
        connection.sendall(b"RFB 003.008\n")
        count = receive_exact(connection, 1)[0]
        security_types = receive_exact(connection, count)
        if 1 in security_types or 2 not in security_types:
            raise RuntimeError("VNC must require authentication.")


def main() -> int:
    try:
        require_vnc_authentication()
        # Ignore ambient HTTP proxy settings for this loopback-only probe.
        with build_opener(ProxyHandler({})).open("http://127.0.0.1:6080/vnc.html", timeout=2) as response:
            if response.status != 200:
                return 1
    except Exception:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
