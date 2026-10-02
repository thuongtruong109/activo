#!/bin/sh
set -eu

display="${DISPLAY:-:99}"
screen="${ACTIVO_SCREEN:-1440x900x24}"

cleanup() {
    trap - EXIT INT TERM
    for pid in "${app_pid:-}" "${web_pid:-}" "${vnc_pid:-}" \
        "${wm_pid:-}" "${xvfb_pid:-}"; do
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null || true
        fi
    done
}
trap cleanup EXIT INT TERM

Xvfb "$display" -screen 0 "$screen" -ac -nolisten tcp &
xvfb_pid=$!

attempt=0
while [ ! -S "/tmp/.X11-unix/X${display#:}" ]; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 50 ]; then
        echo "Xvfb did not become ready" >&2
        exit 1
    fi
    sleep 0.1
done

fluxbox >/tmp/fluxbox.log 2>&1 &
wm_pid=$!

if [ -n "${ACTIVO_VNC_PASSWORD:-}" ]; then
    x11vnc -storepasswd "$ACTIVO_VNC_PASSWORD" /tmp/x11vnc.pass >/dev/null
    set -- -rfbauth /tmp/x11vnc.pass
else
    set -- -nopw
fi

x11vnc -display "$display" -forever -shared -rfbport 5900 -noxdamage \
    -quiet "$@" &
vnc_pid=$!

websockify --web=/usr/share/novnc/ 6080 localhost:5900 &
web_pid=$!

python -m license_admin &
app_pid=$!
wait "$app_pid"
