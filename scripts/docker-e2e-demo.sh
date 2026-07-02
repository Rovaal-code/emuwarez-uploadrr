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
    "$E2E_TMPDIR/uploadrr-mount" \
    "$E2E_TMPDIR/uploadrr-data" \
    "$E2E_TMPDIR/uploadrr-tmp"

# Fake .mkv file — text content, .mkv extension (verifiers check existence/extension/size)
echo "FAKE MKV DEMO — eMuwarez Uploadrr E2E test fixture" \
    > "$E2E_TMPDIR/data/media/movies/Demo Movie (2024)/Demo Movie (2024) WEBDL-1080p.mkv"

# Phase 10F — fake Uploadrr-EMU: never the real fork, never touches eMuwarez.
# Code (upload.py) goes in the :ro mount; data/config.yaml goes in the
# separate rw mount, mirroring the documented Docker mount strategy.
#
# The empty data/ and tmp/ mountpoint directories must already exist INSIDE
# uploadrr-mount (the :ro source) before Docker starts — nested bind mounts
# under a read-only parent fail with "Read-only file system" if the target
# directory doesn't already exist, since the container can't mkdir it at
# mount time. A real Uploadrr-EMU checkout already ships these directories;
# this fake fixture has to create them explicitly.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$E2E_TMPDIR/uploadrr-mount/data" "$E2E_TMPDIR/uploadrr-mount/tmp"
cp "$REPO_ROOT/tests/fixtures/fake_uploadrr_emu.py" "$E2E_TMPDIR/uploadrr-mount/upload.py"
cat > "$E2E_TMPDIR/uploadrr-data/config.yaml" <<'YAML'
DEFAULT:
  tmdb: PLACEHOLDER_TMDB_KEY
  default_torrent_client: qbit

TRACKERS:
  EMU:
    api_key: PLACEHOLDER_EMU_SECRET
    anon: false
YAML

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
    -v "${E2E_TMPDIR}/uploadrr-data:/opt/Uploadrr/data:rw" \
    -v "${E2E_TMPDIR}/uploadrr-tmp:/opt/Uploadrr/tmp:rw" \
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

# ── 13. Phase 10A — Nomenclature sources/providers (CLI + auth guard) ────────
log_step "13. Phase 10A — Sources, Providers y MKV title"

# CLI: nomenclature sources must list WEB-DL
SOURCES_OUT=$(docker exec "$CONTAINER_NAME" python3 emuwarez_uploader.py nomenclature sources 2>&1)
if echo "$SOURCES_OUT" | grep -q "WEB-DL"; then
    log_ok "nomenclature sources — WEB-DL presente"
    PASS=$((PASS + 1))
else
    log_fail "nomenclature sources — WEB-DL NO encontrado"
    FAIL=$((FAIL + 1))
fi

# CLI: nomenclature providers must list AMZN
PROVIDERS_OUT=$(docker exec "$CONTAINER_NAME" python3 emuwarez_uploader.py nomenclature providers 2>&1)
if echo "$PROVIDERS_OUT" | grep -q "AMZN"; then
    log_ok "nomenclature providers — AMZN presente"
    PASS=$((PASS + 1))
else
    log_fail "nomenclature providers — AMZN NO encontrado"
    FAIL=$((FAIL + 1))
fi

# API auth guard: sources endpoint must return 401 without token
SOURCES_NO_AUTH=$(curl -s -o /dev/null -w "%{http_code}" \
    "${BASE_URL}/api/nomenclature/sources")
if [ "$SOURCES_NO_AUTH" = "401" ]; then
    log_ok "GET /nomenclature/sources sin token → 401 (auth guard OK)"
    PASS=$((PASS + 1))
else
    log_warn "GET /nomenclature/sources sin token → HTTP $SOURCES_NO_AUTH (esperado 401)"
fi

# CLI: mkv-title preview for demo item (expects blocked — no prepared_path in fresh demo)
# Uses || true because mkv-title preview exits 1 when blocked (expected in demo)
MKV_OUT=$(docker exec "$CONTAINER_NAME" python3 emuwarez_uploader.py mkv-title preview 1 2>&1 || true)
if echo "$MKV_OUT" | grep -qE "blocked|Status"; then
    log_ok "mkv-title preview — responde correctamente (blocked sin prepared_path)"
    PASS=$((PASS + 1))
else
    log_warn "mkv-title preview — respuesta inesperada"
fi

# ── 14. Phase 10F — controlled Uploadrr-EMU execution (fake runner only) ────
log_step "14. Phase 10F — Ejecución controlada Uploadrr-EMU (fake runner)"

# Configure Uploadrr runtime settings pointing at the fake runner mounted
# above, then run a real preflight + apply cycle. Never touches a real
# Uploadrr-EMU installation or eMuwarez.
E2E_FAKE_RUN_OUT=$(docker exec -i "$CONTAINER_NAME" python3 - <<'PYEOF' 2>&1
import time
from emuwarez_uploadrr.database import connect, init_db, db_path
from emuwarez_uploadrr.web.services.settings_service import set_setting
from emuwarez_uploadrr.services.upload_preflight import build_upload_preflight
from emuwarez_uploadrr.services.upload_execution import (
    start_upload_job, get_upload_job, CONFIRMATION_TOKEN,
)

conn = connect(db_path())
init_db(conn)
set_setting(conn, "uploadrr.path", "/opt/Uploadrr")
set_setting(conn, "uploadrr.python_path", "/usr/local/bin/python")
set_setting(conn, "uploadrr.runtime_type", "uploadrr_emu")
set_setting(conn, "tmdb.api_key", "e2e_fake_tmdb_key")
set_setting(conn, "emu.api_key", "e2e_fake_emu_key")
conn.commit()

result = build_upload_preflight(1, conn=conn)
job = result.get("job")
print(f"PREFLIGHT_STATUS={result.get('status')}")
cmd_preview = (result.get("command_preview") or {}).get("command_preview")
print(f"COMMAND_PREVIEW={cmd_preview}")
if not job:
    print("RESULT=no_job")
    raise SystemExit(0)

job_id = job["id"]
start = start_upload_job(job_id, dry_run=False, start=True, confirmation=CONFIRMATION_TOKEN, conn=conn)
print(f"START_ACTION={start.get('action')}")
print(f"START_ERROR={start.get('error')}")

deadline = time.monotonic() + 15
final = None
while time.monotonic() < deadline:
    final = get_upload_job(job_id, conn=conn)
    if final["status"] in ("completed", "failed", "cancelled"):
        break
    time.sleep(0.2)
time.sleep(0.3)
print(f"FINAL_STATUS={final['status'] if final else 'unknown'}")
print(f"FINAL_EXIT_CODE={final.get('exit_code') if final else None}")
print(f"FINAL_RESULT_URL={final.get('result_url') if final else None}")
PYEOF
)
echo "$E2E_FAKE_RUN_OUT"

check_ok "Fase 10F — settings runtime Uploadrr configuradas" \
    grep -q 'PREFLIGHT_STATUS=ready' <<< "$E2E_FAKE_RUN_OUT"
check_ok "Fase 10F — command_preview usa flags reales (-tk/-mt/-ua)" \
    grep -E 'COMMAND_PREVIEW=.*-tk.*-mt.*-ua' <<< "$E2E_FAKE_RUN_OUT"
check_ok "Fase 10F — job fake arranca (action=started)" \
    grep -q 'START_ACTION=started' <<< "$E2E_FAKE_RUN_OUT"
check_ok "Fase 10F — job fake termina en completed" \
    grep -q 'FINAL_STATUS=completed' <<< "$E2E_FAKE_RUN_OUT"
check_ok "Fase 10F — exit_code 0" \
    grep -q 'FINAL_EXIT_CODE=0' <<< "$E2E_FAKE_RUN_OUT"
check_ok "Fase 10F — URL fake capturada como resultado" \
    grep -q 'FINAL_RESULT_URL=https://fake-emu.invalid.test' <<< "$E2E_FAKE_RUN_OUT"

# Logs must show the fake runner's deterministic output, never a real eMuwarez call.
FAKE_JOB_LOGS=$(docker exec "$CONTAINER_NAME" python3 -c "
from emuwarez_uploadrr.database import connect, init_db, db_path
from emuwarez_uploadrr.services.upload_execution import list_upload_jobs, get_upload_job_logs
conn = connect(db_path()); init_db(conn)
jobs = list_upload_jobs(conn=conn)
if jobs:
    logs = get_upload_job_logs(jobs[0]['id'], conn=conn)
    for entry in logs['logs']:
        print(entry['message'])
" 2>&1)
check_ok "Fase 10F — logs capturados del fake runner" \
    grep -q 'Torrent creado correctamente' <<< "$FAKE_JOB_LOGS"
# config.yaml is staged with the fake tmdb/emu keys during execution and
# must be restored back to its original placeholder content afterwards.
check_ok "Fase 10F — config.yaml restaurado al placeholder original" \
    grep -q 'PLACEHOLDER_TMDB_KEY' "${E2E_TMPDIR}/uploadrr-data/config.yaml"

# ── 15. Security check: Uploadrr not in image ─────────────────────────────────
log_step "15. Seguridad"
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
