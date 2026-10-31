# syntax=docker/dockerfile:1
# ── Stage 1: Build frontend ──────────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="eMuwarez Uploadrr"
LABEL org.opencontainers.image.description="Upload manager for eMuwarez with Radarr/Sonarr integration"

# System dependencies. mediainfo/ffmpeg/mktorrent are needed by the bundled
# Uploadrr-EMU (mediainfo also by our own nomenclature); mkvtoolnix (mkvmerge)
# is what our own nomenclature uses to reorder/rename tracks; git is used to
# fetch the Uploadrr-EMU fork at build time. These same three (mediainfo,
# ffmpeg's ffprobe, mkvtoolnix's mkvmerge) are also the whole toolset behind
# services/source_engine (see docs/source_engine.md) — no extra package
# needed for it.
# mesa-vulkan-drivers: Vulkan por CPU para el libplacebo de ffmpeg, con el que Uploadrr-EMU saca las capturas de
# un Dolby Vision perfil 5.
RUN apt-get update && apt-get install -y --no-install-recommends \
    mediainfo ffmpeg mktorrent mkvtoolnix git mesa-vulkan-drivers \
    && rm -rf /var/lib/apt/lists/*

# mkbrr: Uploadrr-EMU crea el .torrent con él si está en el PATH (si no, con torf).
# Versión y checksums fijados: al subir MKBRR_VERSION hay que cambiar los dos sha256
# (mkbrr_<versión>_checksums.txt de la release).
ARG TARGETARCH
ARG MKBRR_VERSION=1.27.0
RUN set -eu; \
    case "${TARGETARCH:-amd64}" in \
      amd64) arch=x86_64; sum=962323dd30083154fd6f5e1a46a5951a49db726ad93510c3e3c5f74a33d6912f ;; \
      arm64) arch=arm64; sum=63529e28c05e2d29c9d1327bbc43ef84f9e2ab4c25f2dd853ecf0f0a35c5a675 ;; \
      *) echo "mkbrr no tiene binario para ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    python3 -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/tmp/mkbrr.tar.gz')" \
      "https://github.com/autobrr/mkbrr/releases/download/v${MKBRR_VERSION}/mkbrr_${MKBRR_VERSION}_linux_${arch}.tar.gz"; \
    echo "${sum}  /tmp/mkbrr.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/mkbrr.tar.gz -C /usr/local/bin mkbrr; \
    rm /tmp/mkbrr.tar.gz; \
    mkbrr version

WORKDIR /app

# Dependencias web antes que el código: un cambio en emuwarez_uploadrr/ no las reinstala.
# Salen del extra `web` de pyproject.toml, con las versiones fijadas en constraints.txt.
COPY pyproject.toml constraints.txt ./
RUN python -c "import tomllib; print(*tomllib.load(open('pyproject.toml', 'rb'))['project']['optional-dependencies']['web'], sep='\n')" > /tmp/web.txt \
    && pip install --no-cache-dir -c constraints.txt -r /tmp/web.txt \
    && rm /tmp/web.txt

# Bundle Uploadrr-EMU as an internal dependency — like mediainfo/ffmpeg, the
# user configures nothing, and it is NEVER an external bind mount. Installed
# under /opt (NOT /app, or setuptools' flat-layout discovery would clash with
# our own package). uploadrr.path defaults to /opt/Uploadrr
# (services/uploadrr_contract.py). What Uploadrr-EMU writes and must survive a
# rebuild/recreate (config.yaml, its .bak, cookies/ and tmp/) is symlinked into
# /config/Uploadrr below, so the user mounts nothing beyond the /config volume
# they already have. The rest of data/ (services.json, tags.json, templates...)
# stays real in the image: a new image updates it.
#
# Cloned from our own fork (Kisnov/Uploadrr-EMU on GitHub, not the public
# codeberg.org/ccx94/Uploadrr-EMU upstream) so the image ships our local
# patches — Spanish trailer preference, trailer on TV/anime too, and our own
# signature instead of Uploadrr's default branding — instead of a clean
# upstream checkout that silently drops all of that on a fresh deploy. The
# fork is public, so the build needs no token.
#
# Cache-busting: Docker's layer cache keys a RUN step on its literal command
# text, not on what the command actually fetches from the network — a plain
# `git clone` here would silently keep reusing a stale checkout on every
# rebuild forever, even after new commits land on the fork's main branch
# (confirmed happened across several previous deploys in this project: the
# clone step showed CACHED and shipped stale Uploadrr-EMU code despite fresh
# fixes already pushed to the fork). Passing the fork's current commit SHA as
# a build arg makes THIS layer's cache key include it, so it only re-clones
# when the fork actually has new commits — pass
# `--build-arg UPLOADRR_COMMIT=$(git ls-remote https://github.com/Kisnov/Uploadrr-EMU.git main | cut -f1)`
# at build time. If omitted it stays "unknown", which can reuse a cached
# clone: pass a current UPLOADRR_COMMIT or build with `--no-cache`.
# Uploadrr-EMU no versiona data/config.yaml: el entrypoint lo crea en /config desde su ejemplo la primera vez.
ARG UPLOADRR_COMMIT=unknown
RUN echo "Uploadrr-EMU @ ${UPLOADRR_COMMIT}" \
    && git clone --depth 1 https://github.com/Kisnov/Uploadrr-EMU.git /opt/Uploadrr \
    && if [ "${UPLOADRR_COMMIT}" != unknown ]; then \
         git -C /opt/Uploadrr fetch -q --depth 1 origin "${UPLOADRR_COMMIT}" && git -C /opt/Uploadrr checkout -q FETCH_HEAD; fi \
    && pip install --no-cache-dir -r /opt/Uploadrr/requirements.txt \
    && rm -rf /opt/Uploadrr/.git /opt/Uploadrr/data/cookies /opt/Uploadrr/tmp \
    && ln -sf /config/Uploadrr/data/config.yaml /opt/Uploadrr/data/config.yaml \
    && ln -sf /config/Uploadrr/data/config.yaml.bak /opt/Uploadrr/data/config.yaml.bak \
    && ln -s /config/Uploadrr/data/cookies /opt/Uploadrr/data/cookies \
    && ln -s /config/Uploadrr/tmp /opt/Uploadrr/tmp \
    && chmod -R a+rX /opt/Uploadrr \
    && chmod 1777 /opt/Uploadrr/data
# Solo data/ admite escritura (el índice de torrents que deja Uploadrr-EMU): el UID
# del contenedor (PUID/PGID, `user:` del compose) no se conoce al construir, y con
# el bit sticky no puede borrar ni sustituir lo que trae la imagen. El código es de
# solo lectura. Los destinos de los enlaces los crea docker-entrypoint.sh.

# El código de la app, después de lo que casi no cambia.
COPY emuwarez_uploader.py ./
COPY emuwarez_uploadrr/ ./emuwarez_uploadrr/

RUN pip install --no-cache-dir --no-deps -e .

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy built frontend — app.py resolves frontend/dist relative to its own
# location: Path(__file__).parent.parent.parent / "frontend" / "dist"
# With WORKDIR=/app and app.py at /app/emuwarez_uploadrr/web/app.py,
# _REPO_ROOT = /app, so frontend/dist must be at /app/frontend/dist.
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Runtime environment
# Sello de versión: lo lee services/version_info.py para la tarjeta de
# Diagnóstico y para saber si hay una imagen más nueva publicada. Se pasan con
# --build-arg al construir; sin ellos vale "unknown" y la comprobación se
# desactiva sola, diciéndolo, en vez de inventarse un estado.
ARG APP_COMMIT=unknown
ARG APP_BUILD_DATE=unknown
ENV APP_COMMIT=${APP_COMMIT}
ENV APP_BUILD_DATE=${APP_BUILD_DATE}
LABEL org.opencontainers.image.revision=${APP_COMMIT}
LABEL org.opencontainers.image.created=${APP_BUILD_DATE}

ENV CONFIG_DIR=/config
ENV TZ=Europe/Madrid
ENV PYTHONUNBUFFERED=1

# Config directory — mount a persistent volume here
VOLUME ["/config"]

EXPOSE 9494

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9494/api/health', timeout=5).read()" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python3", "emuwarez_uploader.py", "web", "serve", "--host", "0.0.0.0", "--port", "9494"]
