"""Piezas compartidas del servicio de subidas: constantes, fases de progreso, redacción de secretos y acceso a la base."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from ...database import connect, get_setting_canonical, init_db


logger = logging.getLogger("emuwarez.upload")
CONFIRMATION_TOKEN = "INICIAR_UPLOADRR"
DELETE_CONFIRMATION_TOKEN = "BORRAR_SUBIDA"
# Queda en los logs del job; al escribirla, append_upload_log marca `torrent_subido` para no borrar lo que siembra qBittorrent.
QBIT_AÑADIDO = "qBittorrent: torrent añadido correctamente."
# Phase 10F: approximate progress phases surfaced to the UI (string label
# only). Numeric per-phase percentages are tracked separately in
# upload_jobs.progress_json — see mark_phase_done/update_phase_progress below
# and uploadrr_progress.py's PHASES table.
PROGRESS_PHASES = (
    "staging", "queued", "verificacion_presubida", "nomenclature", "remux",
    "config_staging", "running", "finalizing", "succeeded", "failed",
    "cancelled", "timeout",
)
# Fase de un trabajo 'ready' lanzado directamente (CLI, reintento con
# confirmación) mientras espera plaza en "Subidas en paralelo".
ETAPA_ESPERANDO_TURNO = "queued"


def compute_progress_phase(status: str, stage: str | None) -> str:
    """Map (status, stage) to one of PROGRESS_PHASES for display purposes only."""
    stage = stage or ""
    if status == "cancelled":
        return "cancelled"
    if status == "failed" and stage == "timeout":
        return "timeout"
    if status == "failed":
        return "failed"
    if status == "completed":
        return "succeeded"
    if status == "staging":
        return "staging"
    if status == "preparing":
        # Server-side prep queued jobs go through before the real Uploadrr
        # subprocess: verificación presubida (integrity + generic preconditions)
        # -> nomenclature rename -> track remux -> final preflight, all
        # against the SAME job row the user is watching.
        if stage in ("verificacion_presubida", "nomenclature", "remux"):
            return stage
        return "verificacion_presubida"
    if status == "running":
        if stage == "config_staging":
            return "config_staging"
        if stage == "finalizing":
            return "finalizing"
        return "running"
    if status == "ready":
        return "queued" if stage == ETAPA_ESPERANDO_TURNO else "verificacion_presubida"
    if status in ("draft", "preflight"):
        return "verificacion_presubida"
    return "queued"


_SECRET_PATTERNS = [
    re.compile(r"(api[_-]?token\s*=\s*)\S+", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*=\s*)\S+", re.IGNORECASE),
    re.compile(r"(token\s*=\s*)\S+", re.IGNORECASE),
    re.compile(r"(key\s*=\s*)\S+", re.IGNORECASE),
]


def redact_secrets(value: str, secrets: list[str]) -> str:
    """Replace known secret values and common secret patterns with ***REDACTED***."""
    result = value
    for secret in secrets:
        if secret and len(secret) > 3:
            result = result.replace(secret, "***REDACTED***")
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(r"\1***REDACTED***", result)
    return result


def _get_db_conn():
    conn = connect()
    init_db(conn)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_setting(conn, key: str, default=None):
    try:
        from ..settings import get_setting_canonical
        valor = get_setting_canonical(conn, key)
        if valor:
            return valor
    except Exception:
        pass
    try:
        from ...database import get_state
        return get_state(conn, key, default)
    except Exception:
        return default


def _collect_secrets(conn) -> list[str]:
    secrets = []
    # Los dos de qBittorrent también: un error de conexión de Uploadrr-EMU escribe la URL de qui, clave incluida.
    for key in ("emu.api_key", "tmdb.api_key", "qbit.password", "qbit.qui_proxy_url"):
        val = get_setting_canonical(conn, key)
        if val:
            secrets.append(val)
    # urllib3 escribe la ruta sin el host ("url: /proxy/<clave>/api/v2/..."): la clave de qui, sola.
    qui = (get_setting_canonical(conn, "qbit.qui_proxy_url") or "").strip().rstrip("/")
    if "/proxy/" in qui:
        secrets.append(qui.rsplit("/", 1)[-1])
    # Las de los hosts de imágenes también se stagean en el config.yaml del hijo.
    from ..settings import all_settings
    secrets += [v for k, v in all_settings(conn).items() if k.startswith("imghost.key.") and v]
    return secrets
