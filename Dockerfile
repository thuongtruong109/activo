FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
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

COPY requirements.txt pyproject.toml ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.txt

COPY . .
RUN chmod +x /app/docker/entrypoint.sh /app/docker/start-desktop.sh

EXPOSE 6080
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6080/vnc.html', timeout=3)" || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["/app/docker/start-desktop.sh"]
