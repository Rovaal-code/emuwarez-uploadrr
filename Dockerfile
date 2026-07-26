# syntax=docker/dockerfile:1
# ── Stage 1: Build frontend ──────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

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
RUN apt-get update && apt-get install -y --no-install-recommends \
    mediainfo ffmpeg mktorrent mkvtoolnix git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bundle Uploadrr-EMU as an internal dependency — like mediainfo/ffmpeg, the
# user configures nothing, and it is NEVER an external bind mount. Installed
# under /opt (NOT /app, or setuptools' flat-layout discovery would clash with
# our own package). uploadrr.path defaults to /opt/Uploadrr
# (services/uploadrr_contract.py). Its data/ and tmp/ subdirs are replaced at
# container start (docker-entrypoint.sh) with symlinks into /config/Uploadrr,
# so what Uploadrr-EMU writes there survives a rebuild/recreate without the
# user mounting anything beyond the /config volume they already have.
#
# Cloned from our own private fork (Rovaal-code/Uploadrr-EMU on GitHub, not
# the public codeberg.org/ccx94/Uploadrr-EMU upstream) so the image ships
# our local patches — Spanish trailer preference, trailer on TV/anime too,
# and our own signature instead of Uploadrr's default branding — instead of
# a clean upstream checkout that silently drops all of that on a fresh
# deploy. Private repo needs a token, passed as a BuildKit secret so it
# never ends up baked into an image layer: `docker build --secret
# id=github_token,env=GITHUB_TOKEN ...` (or `,src=<file>`).
#
# setuptools is pinned <80 because pyrobase's setup.py still imports the
# pkg_resources module that newer setuptools dropped.
RUN --mount=type=secret,id=github_token \
    git clone --depth 1 "https://x-access-token:$(cat /run/secrets/github_token)@github.com/Rovaal-code/Uploadrr-EMU.git" /opt/Uploadrr \
    && pip install --no-cache-dir "setuptools<80" wheel \
    && pip install --no-cache-dir --no-build-isolation -r /opt/Uploadrr/requirements.txt \
    && pip install --no-cache-dir tmdbsimple \
    && rm -rf /opt/Uploadrr/.git \
    && chmod -R a+rwX /opt/Uploadrr
# world-writable: the container's runtime UID (PUID/PGID, docker-compose's
# `user:`) isn't known at build time, but docker-entrypoint.sh still needs to
# replace /opt/Uploadrr/{data,tmp} with symlinks under whatever UID it runs as.

# Install Python dependencies first (better layer caching)
COPY pyproject.toml ./
COPY emuwarez_uploader.py ./
COPY emuwarez_uploadrr/ ./emuwarez_uploadrr/

RUN pip install --no-cache-dir -e ".[web]"

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Copy built frontend — app.py resolves frontend/dist relative to its own
# location: Path(__file__).parent.parent.parent / "frontend" / "dist"
# With WORKDIR=/app and app.py at /app/emuwarez_uploadrr/web/app.py,
# _REPO_ROOT = /app, so frontend/dist must be at /app/frontend/dist.
COPY --from=frontend-builder /build/frontend/dist ./frontend/dist

# Runtime environment
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
