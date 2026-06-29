# Checkpoint: Uploadrr Lifecycle Results — emuwarez-uploadrr-lifecycle-results-v0

**Tag:** `emuwarez-uploadrr-lifecycle-results-v0`
**Branch merged:** `feature/ui-phase-06d-upload-lifecycle-results` → `master`
**Tests:** 422 passed, 0 failed
**Date:** 2026-06-29

---

## Qué incluye esta fase (6D)

### Backend

| Archivo | Cambio |
|---------|--------|
| `emuwarez_uploadrr/services/upload_result_parser.py` | Nuevo módulo: extracción de URLs/torrent IDs de stdout, `classify_upload_result`, `build_error_summary` |
| `emuwarez_uploadrr/services/upload_execution.py` | `_run_uploadrr_subprocess` rellena `result_url`, `result_torrent_id`, `duration_seconds`, `last_success_at`/`last_error_at`, `safe_command_json`; crea `upload_artifacts`; `list_upload_jobs` con filtros; `create_upload_artifact`; `get_upload_job_artifacts`; `retry_upload_job` |
| `emuwarez_uploadrr/database.py` | Schema v7: nuevas columnas en `upload_jobs`, nueva tabla `upload_artifacts`, columna `sequence` en `upload_job_logs` |
| `emuwarez_uploadrr/web/api/uploads.py` | `GET /api/uploads` con filtros; `GET /api/uploads/{id}/artifacts`; `POST /api/uploads/{id}/retry` |
| `emuwarez_uploadrr/web/api/dashboard.py` | Contadores de subidas por estado (`uploads_ready/running/completed/failed`) |
| `emuwarez_uploadrr/web/schemas.py` | `UploadArtifact`, `UploadArtifactsResponse`, `UploadRetryRequest`, campos Phase 6D en `UploadJobDetail` |
| `emuwarez_uploadrr/cli.py` | `upload artifacts <id>`, `upload retry <id>`, filtro `--status` en `upload jobs` |

### Frontend

| Archivo | Cambio |
|---------|--------|
| `frontend/src/types/api.ts` | `UploadArtifact`, `UploadArtifactsResponse`, `UploadRetryRequest`, campos extendidos en `UploadJob` |
| `frontend/src/api/uploads.ts` | `getUploadJobArtifacts`, `retryUploadJob`, filtros en `getUploads` |
| `frontend/src/pages/UploadsPage.tsx` | Filtro de estado, `ArtifactsPanel` modal, `RetryModal` con token `INICIAR_UPLOADRR` |
| `frontend/src/pages/DashboardPage.tsx` | Panel derecho con contadores Ready/En curso/Completados/Fallidos |

### Tests (nuevos)

| Archivo | Tests |
|---------|-------|
| `tests/test_upload_result_parser.py` | 20 tests — funciones puras del parser |
| `tests/test_upload_lifecycle.py` | 19 tests — duración, timestamps, artifacts, retry |
| `tests/test_upload_retry_api.py` | 13 tests — endpoints artifacts/retry, filtros, dashboard |

**Total acumulado:** 422 tests (372 anteriores + 50 nuevos)

---

## Reglas de seguridad mantenidas

- `INICIAR_UPLOADRR` requerido para toda ejecución real y retry
- `shell=True` nunca usado en subprocess
- `safe_command_json` redacta todos los secretos antes de persistir
- `upload_artifacts` nunca incluye valores de API keys
- `retry_upload_job` crea job NUEVO — el original nunca se muta
- No se ha tocado nada dentro de `Uploadrr/`
- Sin push al remoto

---

## No implementado todavía (fuera de alcance)

- Creación automática de peticiones eMuwarez
- mkvpropedit real
- Modificación de título interno MKV
- Copia/reflink cross-device
- Docker final
