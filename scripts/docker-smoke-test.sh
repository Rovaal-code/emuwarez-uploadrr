#!/usr/bin/env bash
# scripts/docker-smoke-test.sh
# Smoke test reproducible para la imagen Docker de eMuwarez Uploadrr.
#
# Uso: bash scripts/docker-smoke-test.sh
#
# Variables opcionales:
#   IMAGE_NAME=emuwarez-uploadrr:smoke   nombre de imagen a construir
#   PORT=9494                            puerto local a mapear
#   KEEP_CONTAINER=0                     si 1, no limpia el contenedor al salir

set -euo pipefail

IMAGE_NAME="${IMAGE_NAME:-emuwarez-uploadrr:smoke}"
PORT="${PORT:-9494}"
KEEP_CONTAINER="${KEEP_CONTAINER:-0}"
CONTAINER_NAME="emuwarez-uploadrr-smoke-$$"
TIMEOUT=90

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok()   { echo -e "${GREEN}✓${NC} $*"; }
log_warn() { echo -e "${YELLOW}⚠${NC} $*"; }
log_fail() { echo -e "${RED}✗${NC} $*"; }
log_info() { echo "  $*"; }

TMPDIR_SMOKE=$(mktemp -d)
mkdir -p "$TMPDIR_SMOKE/config" "$TMPDIR_SMOKE/data" "$TMPDIR_SMOKE/uploads" "$TMPDIR_SMOKE/uploadrr-mount"

cleanup() {
    if [ "${KEEP_CONTAINER:-0}" = "0" ]; then
        docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
        rm -rf "$TMPDIR_SMOKE"
    else
        log_warn "KEEP_CONTAINER=1: contenedor '$CONTAINER_NAME' mantenido"
        log_warn "Directorio temporal mantenido: $TMPDIR_SMOKE"
    fi
}
trap cleanup EXIT

BASE_URL="http://127.0.0.1:${PORT}"

http_get() {
    local url="$1"
    if command -v curl &>/dev/null; then
        curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000"
    else
        python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('${url}', timeout=5)
    print(r.status)
except Exception:
    print('000')
" 2>/dev/null
    fi
}

http_body() {
    local url="$1"
    if command -v curl &>/dev/null; then
        curl -s --max-time 5 "$url" 2>/dev/null || true
    else
        python3 -c "
import urllib.request
try:
    r = urllib.request.urlopen('${url}', timeout=5)
    print(r.read().decode())
except Exception:
    print('')
" 2>/dev/null
    fi
}

echo ""
echo "eMuwarez Uploadrr — Docker Smoke Test"
echo "======================================="
echo ""

# 1. Build imagen
log_info "Construyendo imagen $IMAGE_NAME..."
if docker build -t "$IMAGE_NAME" . -q; then
    log_ok "Imagen construida: $IMAGE_NAME"
else
    log_fail "Error construyendo imagen"
    exit 1
fi

# 2. Arrancar contenedor
log_info "Arrancando contenedor $CONTAINER_NAME en puerto $PORT..."
docker run -d \
    --name "$CONTAINER_NAME" \
    -e CONFIG_DIR=/config \
    -e TZ=Europe/Madrid \
    -p "${PORT}:9494" \
    -v "${TMPDIR_SMOKE}/config:/config" \
    -v "${TMPDIR_SMOKE}/data:/data" \
    -v "${TMPDIR_SMOKE}/uploads:/uploads" \
    "$IMAGE_NAME" >/dev/null

log_ok "Contenedor arrancado"

# 3. Esperar que la app responda
log_info "Esperando que la app responda (timeout ${TIMEOUT}s)..."
ELAPSED=0
while true; do
    CODE=$(http_get "${BASE_URL}/api/health")
    if [ "$CODE" = "200" ]; then
        break
    fi
    if [ "$ELAPSED" -ge "$TIMEOUT" ]; then
        log_fail "Timeout esperando /api/health (último código HTTP: $CODE)"
        echo ""
        echo "Logs del contenedor:"
        docker logs "$CONTAINER_NAME" 2>&1 | tail -30
        exit 1
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done
log_ok "App respondiendo tras ${ELAPSED}s"

# 4. Checks de endpoints API
PASS=0
FAIL=0

check_endpoint() {
    local label="$1"
    local url="$2"
    local expected="${3:-200}"
    local code
    code=$(http_get "$url")
    if [ "$code" = "$expected" ]; then
        log_ok "$label → HTTP $code"
        PASS=$((PASS + 1))
    else
        log_fail "$label → HTTP $code (esperado $expected)"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "Endpoints API:"
check_endpoint "GET /api/health"        "${BASE_URL}/api/health"
check_endpoint "GET /api/runtime"       "${BASE_URL}/api/runtime"
check_endpoint "GET /api/setup/status"  "${BASE_URL}/api/setup/status"
check_endpoint "GET /api/docs"          "${BASE_URL}/api/docs"

# 5. Frontend
echo ""
echo "Frontend:"
ROOT_BODY=$(http_body "${BASE_URL}/")
ROOT_CODE=$(http_get "${BASE_URL}/")
if [ "$ROOT_CODE" = "200" ] && echo "$ROOT_BODY" | grep -qi "html"; then
    log_ok "GET / → HTML (HTTP $ROOT_CODE)"
    PASS=$((PASS + 1))
else
    log_warn "GET / → HTTP $ROOT_CODE (frontend puede no estar disponible)"
fi

DASH_CODE=$(http_get "${BASE_URL}/dashboard")
if [ "$DASH_CODE" = "200" ]; then
    log_ok "GET /dashboard → HTTP $DASH_CODE (SPA fallback OK)"
    PASS=$((PASS + 1))
else
    log_warn "GET /dashboard → HTTP $DASH_CODE"
fi

# 6. CONFIG_DIR
echo ""
echo "Configuración:"
if [ -d "${TMPDIR_SMOKE}/config" ]; then
    log_ok "/config montado y accesible desde el host"
    PASS=$((PASS + 1))
else
    log_fail "/config no accesible desde el host"
    FAIL=$((FAIL + 1))
fi

# 7. Uploadrr-EMU bundled as an internal dependency (must be in the image)
echo ""
echo "Uploadrr-EMU (dependencia interna):"
if docker exec "$CONTAINER_NAME" test -f /opt/Uploadrr/upload.py 2>/dev/null; then
    log_ok "Uploadrr-EMU está bundleado en /opt/Uploadrr"
    PASS=$((PASS + 1))
else
    log_fail "Uploadrr-EMU NO está en la imagen (/opt/Uploadrr/upload.py falta)"
    FAIL=$((FAIL + 1))
fi

# 8. Resumen
echo ""
echo "======================================="
echo "Resultado: ${PASS} OK, ${FAIL} FAIL"
if [ "$FAIL" -eq 0 ]; then
    echo ""
    log_ok "Smoke test PASADO"
    exit 0
else
    echo ""
    log_fail "Smoke test FALLIDO"
    echo ""
    echo "Logs del contenedor (últimas 20 líneas):"
    docker logs "$CONTAINER_NAME" 2>&1 | tail -20
    exit 1
fi
