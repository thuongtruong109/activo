#!/bin/sh
set -eu

# The supervisor also validates direct invocation, without the root entrypoint.
exec python -m license_admin.container_runtime.desktop
