FROM python:3.12.15-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS dependencies

WORKDIR /dependencies
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt

FROM python:3.12.15-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS runtime

LABEL org.opencontainers.image.description="Single trusted-operator desktop. Not a public or multi-user backend."

ENV PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    QT_QPA_PLATFORM=xcb \
    QT_X11_NO_MITSHM=1 \
    DISPLAY=:99 \
    HOME=/home/activo \
    XDG_RUNTIME_DIR=/tmp/runtime-activo \
    XDG_CONFIG_HOME=/data/config \
    XDG_CACHE_HOME=/data/cache \
    ACTIVO_PROJECTS_ROOT=/data/projects

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        fluxbox \
        fonts-dejavu-core \
        gosu \
        libdbus-1-3 \
        libegl1 \
        libfontconfig1 \
        libgl1 \
        libxi6 \
        libxkbcommon-x11-0 \
        libxrender1 \
        libxtst6 \
        libxcb-cursor0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-randr0 \
        libxcb-render-util0 \
        libxcb-shape0 \
        libxcb-sync1 \
        libxcb-xfixes0 \
        libxcb-xinerama0 \
        novnc \
        websockify \
        x11vnc \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 activo \
    && useradd --uid 10001 --gid activo --create-home --shell /bin/sh activo \
    && mkdir -p /app /data/projects /data/config /data/cache /tmp/runtime-activo \
    && chown -R activo:activo /data /tmp/runtime-activo

WORKDIR /app

COPY --from=dependencies /opt/venv /opt/venv
# Deliberate allowlist: no build/test tools, project secrets or mutable host data.
COPY license_admin/ ./license_admin/
COPY issue_license.py migrate_license_csv.py ./
COPY docker/entrypoint.sh docker/start-desktop.sh ./docker/
RUN chmod +x /app/docker/entrypoint.sh /app/docker/start-desktop.sh

EXPOSE 6080
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -m license_admin.container_runtime.healthcheck

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["/app/docker/start-desktop.sh"]
