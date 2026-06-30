#!/usr/bin/env bash
# scripts/docker-e2e-demo.sh
# E2E controlado en Docker con datos simulados — Phase 9B
#
# Uso:
#   bash scripts/docker-e2e-demo.sh
#   KEEP_CONTAINER=1 bash scripts/docker-e2e-demo.sh
#   PORT=9595 bash scripts/docker-e2e-demo.sh
#
# Variables opcionales:
#   IMAGE_NAME=emuwarez-uploadrr:e2e  imagen a construir
#   PORT=9494                          puerto local
#   KEEP_CONTAINER=0                   si 1, mantiene el contenedor y el tmpdir al salir
#
# Garantías de aislamiento:
#   - Todo escribe en un TMPDIR temporal creado con mktemp -d
#   - No usa Radarr/Sonarr reales
#   - No usa eMuwarez real
#   - No ejecuta Uploadrr real
#   - No sube contenido real
#   - No modifica Uploadrr/
#   - No expone API keys reales

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-emuwarez-uploadrr:e2e}"
PORT="${PORT:-9494}"
KEEP_CONTAINER="${KEEP_CONTAINER:-0}"
CONTAINER_NAME="emuwarez-e2e-$$"
TIMEOUT=90

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}✓${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $*"; }
log_fail() { echo -e "${RED}✗${NC} $*"; }
log_step() { echo -e "\n── $* ──────────────────────────────────"; }

# Temporary directory — all data goes here, nothing touches real user paths
E2E_TMPDIR=$(mktemp -d)
mkdir -p \
    "$E2E_TMPDIR/config" \
    "$E2E_TMPDIR/data/media/movies/Demo Movie (2024)" \
    "$E2E_TMPDIR/data/uploads/emu" \
    "$E2E_TMPDIR/uploadrr-mount"

# Fake .mkv file — text content, .mkv extension (verifiers check existence/extension/size)
echo "FAKE MKV DEMO — eMuwarez Uploadrr E2E test fixture" \
    > "$E2E_TMPDIR/data/media/movies/Demo Movie (2024)/Demo Movie (2024) WEBDL-1080p.mkv"

cleanup() {
    if [ "${KEEP_CONTAINER:-0}" = "0" ]; then
        docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
        rm -rf "$E2E_TMPDIR"
    else
        log_warn "KEEP_CONTAINER=1: contenedor '$CONTAINER_NAME' mantenido"
        log_warn "Directorio temporal: $E2E_TMPDIR"
    fi
}
trap cleanup EXIT

BASE_URL="http://127.0.0.1:${PORT}"

http_get_code() {
    local url="$1"
    if command -v curl &>/dev/null; then
        curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$url" 2>/dev/null || echo "000"
    else
        python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('$url', timeout=8)
    print(r.status)
except Exception:
    print('000')
" 2>/dev/null
    fi
}

http_body() {
    local url="$1"
    if command -v curl &>/dev/null; then
        curl -s --max-time 8 "$url" 2>/dev/null || true
    else
        python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('$url', timeout=8)
    print(r.read().decode())
except Exception:
    print('')
" 2>/dev/null
    fi
}

PASS=0
FAIL=0

check_ok() {
    local label="$1"
    shift
    if "$@"; then
        log_ok "$label"
        PASS=$((PASS + 1))
    else
        log_fail "$label"
        FAIL=$((FAIL + 1))
    fi
}

check_http() {
    local label="$1"
    local url="$2"
    local expected="${3:-200}"
    local code
    code=$(http_get_code "$url")
    if [ "$code" = "$expected" ]; then
        log_ok "$label → HTTP $code"
        PASS=$((PASS + 1))
    else
        log_fail "$label → HTTP $code (esperado $expected)"
        FAIL=$((FAIL + 1))
    fi
}

exec_in_container() {
    local label="$1"
    shift
    if docker exec "$CONTAINER_NAME" "$@"; then
        log_ok "$label"
        PASS=$((PASS + 1))
    else
        log_fail "$label"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "eMuwarez Uploadrr — E2E Demo Controlado (Phase 9B)"
echo "==================================================="
echo "  Imagen:     $IMAGE_NAME"
echo "  Puerto:     $PORT"
echo "  Contenedor: $CONTAINER_NAME"
echo "  Tmpdir:     $E2E_TMPDIR"
echo ""

# ── 1. Build image ────────────────────────────────────────────────────────────
log_step "1. Build imagen Docker"
if docker build -t "$IMAGE_NAME" . -q; then
    log_ok "Imagen construida: $IMAGE_NAME"
else
    log_fail "Error construyendo imagen"
    exit 1
fi

# ── 2. Start container ────────────────────────────────────────────────────────
log_step "2. Arrancar contenedor"
docker run -d \
    --name "$CONTAINER_NAME" \
    -e CONFIG_DIR=/config \
    -e TZ=Europe/Madrid \
    -p "${PORT}:9494" \
    -v "${E2E_TMPDIR}/config:/config" \
    -v "${E2E_TMPDIR}/data:/data" \
    -v "${E2E_TMPDIR}/uploadrr-mount:/opt/Uploadrr:ro" \
    "$IMAGE_NAME" >/dev/null

log_ok "Contenedor arrancado: $CONTAINER_NAME"

# ── 3. Wait for health ────────────────────────────────────────────────────────
log_step "3. Esperar /api/health"
ELAPSED=0
while true; do
    CODE=$(http_get_code "${BASE_URL}/api/health")
    if [ "$CODE" = "200" ]; then
        log_ok "App respondiendo tras ${ELAPSED}s"
        break
    fi
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        log_fail "Timeout esperando /api/health (último código: $CODE)"
        echo ""
        echo "Logs del contenedor:"
        docker logs "$CONTAINER_NAME" 2>&1 | tail -30
        exit 1
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

# ── 4. CLI: db init ───────────────────────────────────────────────────────────
log_step "4. CLI — db init"
exec_in_container "db init" \
    python3 emuwarez_uploader.py db init

# ── 5. Demo seed ──────────────────────────────────────────────────────────────
log_step "5. CLI — demo seed"
exec_in_container "demo seed" \
    python3 emuwarez_uploader.py demo seed \
        --media-root /data/media \
        --prepared-root /data/uploads/emu \
        --confirm DEMO_SEED

# ── 6. Library verification ───────────────────────────────────────────────────
log_step "6. CLI — library verify-files"
exec_in_container "library verify-files" \
    python3 emuwarez_uploader.py library verify-files

exec_in_container "library recommendations" \
    python3 emuwarez_uploader.py library recommendations

exec_in_container "library verify-file 1" \
    python3 emuwarez_uploader.py library verify-file 1

# ── 7. Request readiness ──────────────────────────────────────────────────────
log_step "7. CLI — requests readiness"
exec_in_container "requests readiness-refresh" \
    python3 emuwarez_uploader.py requests readiness-refresh

exec_in_container "requests prioritized" \
    python3 emuwarez_uploader.py requests prioritized

# ── 8. Queue ──────────────────────────────────────────────────────────────────
log_step "8. CLI — queue"
exec_in_container "queue refresh" \
    python3 emuwarez_uploader.py queue refresh

exec_in_container "queue summary" \
    python3 emuwarez_uploader.py queue summary

exec_in_container "queue list" \
    python3 emuwarez_uploader.py queue list

# ── 9. Action plan ────────────────────────────────────────────────────────────
log_step "9. CLI — queue action-plan"
exec_in_container "queue action-plan 1" \
    python3 emuwarez_uploader.py queue action-plan 1

exec_in_container "queue execute-safe 1 --action view_plan" \
    python3 emuwarez_uploader.py queue execute-safe 1 --action view_plan

exec_in_container "queue events 1" \
    python3 emuwarez_uploader.py queue events 1

# ── 10. Nomenclature preview ──────────────────────────────────────────────────
log_step "10. CLI — nomenclature preview"
exec_in_container "nomenclature preview 1" \
    python3 emuwarez_uploader.py nomenclature preview 1

# ── 11. Upload preflight ──────────────────────────────────────────────────────
log_step "11. CLI — upload preflight (dry-run)"
exec_in_container "upload preflight 1" \
    python3 emuwarez_uploader.py upload preflight 1

# ── 12. Frontend HTTP checks ──────────────────────────────────────────────────
log_step "12. Frontend HTTP checks"
check_http "GET /api/health"       "${BASE_URL}/api/health"
check_http "GET /api/setup/status" "${BASE_URL}/api/setup/status"

ROOT_BODY=$(http_body "${BASE_URL}/")
ROOT_CODE=$(http_get_code "${BASE_URL}/")
if [ "$ROOT_CODE" = "200" ] && echo "$ROOT_BODY" | grep -qi "html"; then
    log_ok "GET / → HTML (HTTP $ROOT_CODE)"
    PASS=$((PASS + 1))
else
    log_warn "GET / → HTTP $ROOT_CODE (frontend puede no estar disponible)"
fi

DASH_CODE=$(http_get_code "${BASE_URL}/dashboard")
if [ "$DASH_CODE" = "200" ]; then
    log_ok "GET /dashboard → HTTP $DASH_CODE (SPA fallback OK)"
    PASS=$((PASS + 1))
else
    log_warn "GET /dashboard → HTTP $DASH_CODE"
fi

QUEUE_CODE=$(http_get_code "${BASE_URL}/queue")
if [ "$QUEUE_CODE" = "200" ]; then
    log_ok "GET /queue → HTTP $QUEUE_CODE (SPA fallback OK)"
    PASS=$((PASS + 1))
else
    log_warn "GET /queue → HTTP $QUEUE_CODE"
fi

# ── 13. Phase 10A — Nomenclature sources/providers API ───────────────────────
log_step "13. Phase 10A — Sources y Providers API"
SOURCES_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "http://localhost:${HOST_PORT}/api/nomenclature/sources")
if [ "$SOURCES_CODE" = "200" ]; then
    log_ok "GET /nomenclature/sources → 200"
    PASS=$((PASS + 1))
else
    log_warn "GET /nomenclature/sources → HTTP $SOURCES_CODE"
fi

PROVIDERS_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "http://localhost:${HOST_PORT}/api/nomenclature/providers")
if [ "$PROVIDERS_CODE" = "200" ]; then
    log_ok "GET /nomenclature/providers → 200"
    PASS=$((PASS + 1))
else
    log_warn "GET /nomenclature/providers → HTTP $PROVIDERS_CODE"
fi

# Verify sources includes WEB-DL
SOURCES_BODY=$(curl -s -H "Authorization: Bearer $TOKEN" \
    "http://localhost:${HOST_PORT}/api/nomenclature/sources")
if echo "$SOURCES_BODY" | grep -q "WEB-DL"; then
    log_ok "Sources contiene WEB-DL"
    PASS=$((PASS + 1))
else
    log_warn "Sources no contiene WEB-DL"
fi

# MKV title preview for demo item (expects blocked since no prepared_path in fresh demo)
MKV_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $TOKEN" \
    "http://localhost:${HOST_PORT}/api/library/1/mkv-title/preview")
if [ "$MKV_CODE" = "200" ]; then
    log_ok "GET /library/1/mkv-title/preview → 200"
    PASS=$((PASS + 1))
else
    log_warn "GET /library/1/mkv-title/preview → HTTP $MKV_CODE"
fi

# ── 14. Security check: Uploadrr not in image ─────────────────────────────────
log_step "14. Seguridad"
if docker exec "$CONTAINER_NAME" test -d /app/Uploadrr 2>/dev/null; then
    log_fail "Uploadrr/ encontrado DENTRO de la imagen — NO debe estar"
    FAIL=$((FAIL + 1))
else
    log_ok "Uploadrr/ no está dentro de la imagen"
    PASS=$((PASS + 1))
fi

# ── Resumen ───────────────────────────────────────────────────────────────────
echo ""
echo "==================================================="
echo "Resultado E2E: ${PASS} OK, ${FAIL} FAIL"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    log_fail "E2E DEMO FALLIDO"
    echo ""
    echo "Logs del contenedor (últimas 30 líneas):"
    docker logs "$CONTAINER_NAME" 2>&1 | tail -30
    exit 1
fi

echo ""
log_ok "E2E DEMO PASSED"
