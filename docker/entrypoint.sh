#!/bin/sh
set -eu

# Validate before touching persistent data or starting any network listener.
python -m license_admin.container_runtime.config
umask 077
mkdir -p /data/projects /data/config /data/cache /tmp/runtime-activo
chown -R activo:activo /data /tmp/runtime-activo
chmod 700 /data /data/projects /data/config /data/cache /tmp/runtime-activo

exec gosu activo "$@"
