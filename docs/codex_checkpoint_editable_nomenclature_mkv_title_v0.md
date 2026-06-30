# Checkpoint — Nomenclatura editable, Source Assistant y MKV title v0

## Identificadores

- **Rama mergeada:** `feature/ui-phase-10a-editable-nomenclature-source-mkv-title`
- **Commit de Fase 10A:** `34d85ac feat: add editable nomenclature source assistant and MKV title control`
- **Commit merge:** `b24a5e4 merge: editable nomenclature source assistant MKV title milestone`
- **Tag:** `emuwarez-uploadrr-editable-nomenclature-mkv-title-v0`

---

## Validaciones ejecutadas

### py_compile
- `python3 -m py_compile emuwarez_uploader.py` — OK
- `find emuwarez_uploadrr -name "*.py" | xargs -0 python3 -m py_compile` — OK

### JSON schema
- `python3 -m json.tool docs/ui_backend_contract.json` — OK

### CLI validaciones
- `nomenclature sources` — OK (7 fuentes, WEB-DL presente)
- `nomenclature providers` — OK (25 providers, AMZN/NF/DSNP presentes)
- `nomenclature fields 1` — OK (blocked: sin item de demo en BD sin seed)
- `mkv-title preview 1` — OK (blocked: sin prepared_path, respuesta controlada)
- `web info` / `web setup-status` / `web doctor` — OK
- `maintenance status` — OK
- `queue summary` / `queue refresh` / `queue list` — OK
- `demo seed` / `demo reset` — OK
- `instances list` / `library list` / `missing list` / `requests list` / `upload jobs` — OK

### pytest
- **783 passed, 0 failed** (1 warning de httpx deprecation, no bloqueante)

### npm run build
- **OK** — `dist/index.html` + assets generados correctamente
- Warning existente de fase anterior (import dinámico/estático en RequestsPage.tsx) — no bloqueante

### docker build
- **OK** — `emuwarez-uploadrr:checkpoint-10a` construida

### docker compose config
- **OK** — configuración válida

### docker smoke-test
- **8/8 OK** — health, runtime, setup/status, docs, frontend SPA, /config montado, Uploadrr/ no en imagen

### docker E2E demo
- **25/25 OK** — db init, demo seed, library verify-files, library recommendations,
  verify-file, requests readiness-refresh, requests prioritized, queue refresh/summary/list,
  queue action-plan, queue execute-safe, queue events, nomenclature preview,
  upload preflight, frontend HTTP checks, Phase 10A CLI sources/providers/auth-guard/mkv-title,
  seguridad Uploadrr/

---

## Funcionalidades incluidas en este milestone

- **SCHEMA_VERSION = 12**
- `source_assistant.py` — catálogo EMU de fuentes (7) y providers (25)
- Mapping TMDb Watch Providers → código EMU
- `provider_priority_order` — prioridad configurable de providers
- `tmdb_watch_region` — región de TMDb configurable (default: ES)
- `default_release_tag` — tag de release configurable (default: EMUWAREZ)
- Campos editables de nomenclatura: title, complement, season_episode, year, resolution, source, provider, dynamic_range, video_codec, audio_summary, subs, tag
- Fórmula EMU: `WEB-DL` coloca provider antes → `AMZN WEB-DL`, `NF WEB-DL`, `DSNP WEB-DL`
- Provider dropdown con código + nombre real (`AMZN (Amazon)`)
- Badge `[Disponible en TMDB]` para providers confirmados por TMDb
- Tag configurable respetado por encima del default
- `internal_mkv_title` derivado de torrent_name (espacios → puntos)
- `mkv_title.py` — check de mkvpropedit, preview y apply controlado
- Confirmación `APLICAR_TITULO_MKV` obligatoria para ejecución real
- Bloqueo sobre `source_path` original — solo actúa sobre `prepared_path`/`applied_path`
- 7 endpoints API nuevos protegidos con Bearer token
- CLI: `nomenclature sources/providers/fields/preview-fields`
- CLI: `mkv-title preview/apply`
- `NomenclatureFieldsModal.tsx` — modal con campos editables, dropdown de fuente/provider, sección MKV
- Funciones API Phase 10A en `frontend/src/api/nomenclature.ts`
- Todos los ejemplos eMuwarez de la especificación cubiertos por tests
- E2E demo actualizado con checks Phase 10A (CLI + auth guard)

---

## Funcionalidades bloqueadas todavía

- Creación automática de peticiones eMuwarez
- Jellyfin
- Seerr
- Subida automática sin confirmación
- Ejecución real de Uploadrr fuera de flujo confirmado
- Modificación de `source_path` original
- Copia/reflink cross-device

---

## Confirmaciones de seguridad

- `Uploadrr/` no fue modificado en ningún momento
- No se ejecutó ninguna subida real de contenido
- Jellyfin no fue implementado
- Seerr no fue implementado
- No se creó ninguna petición automática en eMuwarez
- `source_path` original queda protegido — mkvpropedit solo actúa sobre `prepared_path`/`applied_path`
- `mkvpropedit` requiere confirmación explícita `APLICAR_TITULO_MKV` y `shell=False`
- No se hizo push al repositorio remoto
- Todos los endpoints nuevos requieren Bearer token (401 sin autenticación)
