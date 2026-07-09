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
# Uploadrr-EMU (mediainfo also by our own nomenclature); git is used to fetch
# the Uploadrr-EMU fork at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
    mediainfo ffmpeg mktorrent git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bundle Uploadrr-EMU (the user's fork) as an internal dependency — like
# mediainfo/ffmpeg, the user configures nothing. Installed under /opt (NOT
# /app, or setuptools' flat-layout discovery would clash with our own package).
# uploadrr.path defaults to /opt/Uploadrr (services/uploadrr_contract.py).
# setuptools is pinned <80 because pyrobase's setup.py still imports the
# pkg_resources module that newer setuptools dropped.
RUN git clone --depth 1 https://codeberg.org/ccx94/Uploadrr-EMU.git /opt/Uploadrr \
    && pip install --no-cache-dir "setuptools<80" wheel \
    && pip install --no-cache-dir --no-build-isolation -r /opt/Uploadrr/requirements.txt \
    && pip install --no-cache-dir tmdbsimple \
    && rm -rf /opt/Uploadrr/.git

# Install Python dependencies first (better layer caching)
COPY pyproject.toml ./
COPY emuwarez_uploader.py ./
COPY emuwarez_uploadrr/ ./emuwarez_uploadrr/

RUN pip install --no-cache-dir -e ".[web]"

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

CMD ["python3", "emuwarez_uploader.py", "web", "serve", "--host", "0.0.0.0", "--port", "9494"]
