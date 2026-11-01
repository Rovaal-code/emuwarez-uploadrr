"""Controlled Uploadrr execution service.

SAFETY CONTRACT:
- Never executes Uploadrr without explicit confirmation INICIAR_UPLOADRR.
- Never uses shell=True.
- Never stores API keys in logs or database.
- Never modifies Uploadrr/.
- Never executes mkvpropedit.
- Never creates eMuwarez requests automatically.
- dry_run=True always by default; always takes precedence over start=True.
"""
from __future__ import annotations

# El servicio se parte en módulos por responsabilidad (ver docs/PLAN.md); este paquete
# re-exporta sus nombres para que `from ...services.upload_execution import X` siga igual.
# Ojo con parchear en tests: un parche sobre este paquete NO alcanza al código de los
# submódulos, que importan los nombres directamente; hay que parchear el módulo que lo usa.
from .comun import (  # noqa: F401
    logger,
    CONFIRMATION_TOKEN,
    DELETE_CONFIRMATION_TOKEN,
    QBIT_AÑADIDO,
    PROGRESS_PHASES,
    ETAPA_ESPERANDO_TURNO,
    compute_progress_phase,
    _SECRET_PATTERNS,
    redact_secrets,
    _get_db_conn,
    _now,
    _get_setting,
    _collect_secrets,
)
from .consultas import (  # noqa: F401
    VIDEO_EXTENSIONS,
    get_upload_job,
    _upload_jobs_where,
    list_upload_jobs,
    count_upload_jobs,
    validate_upload_job_start,
    build_uploadrr_execution_command,
)
from .registro import (  # noqa: F401
    _avisar_de_log,
    _ficha_del_torrent,
    _marca_torrent_subido,
    append_upload_log,
    get_upload_job_logs,
    create_upload_artifact,
    get_upload_job_artifacts,
)
from .estado import (  # noqa: F401
    _update_job_status,
    _avanzar_job,
    _finalize_job_status,
    _check_trailer_and_log,
    _job_poster_url,
    _notify_upload_completed,
    _notify_upload_failed,
    _esta_cancelado,
)
from .config import (  # noqa: F401
    ConfigNoPreparada,
    _stage_uploadrr_config,
    _restore_uploadrr_config,
    _config_stage_lock,
    _config_stage_refcount,
    _acquire_staged_config,
    restaurar_config_interrumpida,
    _release_staged_config,
)
from .concurrencia import (  # noqa: F401
    get_upload_max_concurrent,
    _limite_de_subidas,
    _UploadConcurrencyGate,
    _upload_concurrency_gate,
    _sin_fallos,
)
from .progreso import (  # noqa: F401
    _read_progress_state,
    _write_progress_json,
    mark_phase_started,
    mark_phase_done,
    mark_phase_failed,
    update_phase_progress,
    advance_running_phase,
)
from .procesos import (  # noqa: F401
    _PROCESOS,
    _PROCESOS_LOCK,
    _GRACIA_SIGKILL,
    _senalar_grupo,
    _detener_proceso,
    detener_procesos_en_marcha,
    _pid_es_de_este_job,
    _terminar_y_esperar,
)
from .ejecucion import (  # noqa: F401
    _GRACIA_LECTORES,
    _run_uploadrr_subprocess,
    _run_uploadrr_subprocess_body,
    start_upload_job,
)
from .ciclo_de_vida import (  # noqa: F401
    retry_upload_job,
    cancel_upload_job,
    retry_chain_ids,
    delete_upload_job,
)

__all__ = [
    "CONFIRMATION_TOKEN",
    "DELETE_CONFIRMATION_TOKEN",
    "PROGRESS_PHASES",
    "compute_progress_phase",
    "redact_secrets",
    "get_upload_job",
    "list_upload_jobs",
    "count_upload_jobs",
    "validate_upload_job_start",
    "build_uploadrr_execution_command",
    "start_upload_job",
    "retry_upload_job",
    "append_upload_log",
    "get_upload_job_logs",
    "create_upload_artifact",
    "get_upload_job_artifacts",
    "cancel_upload_job",
    "delete_upload_job",
    "mark_phase_started",
    "mark_phase_done",
    "update_phase_progress",
    "advance_running_phase",
]
