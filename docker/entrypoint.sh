#!/bin/sh
set -eu

mkdir -p /data/projects /data/config /data/cache /tmp/runtime-activo
chown -R activo:activo /data /tmp/runtime-activo
chmod 700 /tmp/runtime-activo

exec gosu activo "$@"
