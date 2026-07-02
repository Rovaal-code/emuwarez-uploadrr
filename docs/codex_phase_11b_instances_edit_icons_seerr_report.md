# Fase 11B — Instancias: editar, iconos rediseñados y soporte Seerr

Segunda sub-fase de la iteración grande de UI/configuración (ver
`docs/codex_phase_11a_settings_overhaul_report.md` para el contexto y el
roadmap completo). Cubre únicamente Instancias.

## Estado del repo

| Campo | Valor |
|-------|-------|
| Rama base | `master` (limpia, incluye Fase 11A ya mergeada) |
| Rama de esta fase | `feature/ui-phase-11b-instances-edit-icons-seerr` |
| Tests previos | 1010 passed |
| Tests tras esta fase | 1039 passed, 0 fallos (1010 + 29 nuevos) |

## Qué se implementó

1. **Editar instancia**: nuevo botón "Editar" por instancia. El servicio
   `update_instance()` ya existía (`services/instances.py`) pero sin ruta
   API — solo hizo falta cablear `PUT /api/instances/{id}` (nuevo
   `UpdateInstanceRequest` en `schemas.py`). Preserva el ID, permite dejar la
   API key en blanco para mantener la actual (mismo convenio que Settings),
   y tras guardar se puede volver a probar la conexión sin recrear la
   instancia.
2. **Iconos rediseñados**: `components/ServiceIcon.tsx` — Radarr pasa de un
   "radar naranja genérico" a una insignia circular ámbar con sweep +
   blips (más parecida al color/forma real de Radarr); Sonarr mantiene el
   tema de ondas pero con una insignia de "pantalla" redondeada; se añade
   un icono nuevo para Seerr (insignia índigo con forma de ojo/lente,
   coherente con el color de marca de Overseerr/Jellyseerr). No son trazas
   exactas de los logos con copyright (sin acceso a red/imágenes en esta
   sesión) — están pensados para ser reconocibles por color/forma; si el
   usuario tiene assets SVG oficiales, se pueden sustituir en ese mismo
   fichero.
3. **Soporte Seerr completo** (Overseerr/Jellyseerr, mismo tipo de
   instancia genérico — misma API):
   - `instances.type` amplía su `CHECK` para incluir `'seerr'`. Primera
     migración de "rebuild de tabla" del proyecto
     (`database.py::_migrate_instances_widen_type_check`, idempotente,
     preserva IDs/filas existentes) — SQLite no permite `ALTER` un `CHECK`
     directamente.
   - Nuevo cliente `emuwarez_uploadrr/integrations/seerr.py` — solo
     lectura, prueba `/api/v1/auth/me` (confirma la key y expone el
     usuario detectado: `displayName`/`username`/`email`) y
     `/api/v1/status` (versión, best-effort). Mismo header `X-Api-Key` que
     Radarr/Sonarr, reutiliza `arr_base.arr_request`.
   - Alta/edición/test de instancias Seerr desde la UI de Instancias
     (sin checkboxes 4K/Anime, irrelevantes para este tipo).
   - `POST /api/instances/{id}/sync` devuelve `400` explícito para
     instancias Seerr (sincronización de peticiones no implementada
     todavía — fuera de alcance de esta fase, según lo acordado).
   - Nuevo endpoint `POST /api/integrations/test/seerr` (instancia
     guardada o credenciales sin guardar, igual que el de Arr).

## Backend — detalle

- `models.py`: `InstanceType.SEERR = "seerr"`.
- `database.py`: `SCHEMA_VERSION` 13→14, nueva migración de rebuild descrita
  arriba, registrada en `init_db()` justo después de `_migrate_instances`.
- `services/instances.py`: `add_instance()` acepta `seerr`; `test_instance_safe()`
  añade el branch Seerr.
- `web/schemas.py`: `UpdateInstanceRequest`, `TestSeerrRequest`,
  `InstanceTestResponse.username` (nuevo campo — Seerr sí expone cuenta
  detectada, a diferencia de eMuwarez en la Fase 11A).
- `web/api/instances.py`: `PUT /{instance_id}`; `sync` bloquea seerr con 400.
- `web/api/integration_tests.py`: `POST /test/seerr`.

## Frontend — detalle

- `pages/InstancesPage.tsx`: formulario de alta con selector de tipo
  ampliado (radarr/sonarr/seerr), formulario de edición inline por tarjeta
  (nombre/URL/API key/4K/Anime/activada + probar + guardar/cancelar).
- `components/ServiceIcon.tsx`: iconos rediseñados + nuevo tipo `seerr`.
- `api/instances.ts`: `updateInstance()`; `api/integrationTests.ts`:
  `testSeerrConnection()`.

## Tests

- `tests/test_seerr_integration.py` (6): cliente Seerr — éxito con
  usuario/versión, fallback de campos de usuario, error de auth/conexión,
  nunca llama a red sin mock, key nunca en el resultado.
- `tests/test_seerr_test_endpoint_api.py` (6): endpoint
  `/integrations/test/seerr` — auth guard, credenciales sin guardar,
  instancia guardada, 404→`not_configured`, secreto nunca en la respuesta.
- `tests/test_instances_api.py` (17): auth guards, alta seerr/radarr/sonarr,
  tipo inválido→422, `PUT` edita nombre/URL/key/enabled/4K/anime
  preservando el ID, key en blanco mantiene la actual, tras editar se
  puede volver a probar, test de instancia Seerr devuelve `username`,
  `sync` en seerr→400, migración idempotente y preserva filas/IDs
  existentes.

**`pytest -q`**: `1039 passed, 0 failed`.
**`npm run build`**: OK, sin errores de tipos.

## Verificación manual

Reiniciado el servidor de demo (con datos ya existentes de fases previas,
incluyendo 2 instancias Radarr reales) para confirmar que la migración
corre limpia sobre una BD ya poblada (verificado: mismos IDs, sin
pérdida de filas). Capturas de: lista de instancias con el nuevo icono de
Radarr, formulario de alta con "Seerr (Overseerr/Jellyseerr)" seleccionado,
y formulario de edición inline abierto y prellenado. Editado de verdad el
nombre de una instancia real vía `PUT` y confirmado que persiste (y
revertido tras la prueba).

## Gaps / limitaciones conocidas

- Sincronización de peticiones desde Seerr: no implementada (fuera de
  alcance de esta fase, según el encargo original — "no necesita sync
  completo, pero la UI/modelo deben estar listos"). El modelo de datos y
  la UI ya están preparados para cuando se implemente.
- Iconos: mejorados en forma/color de marca, pero no son trazas exactas de
  los logos oficiales con copyright (sin acceso a red/imágenes). Sustituir
  por SVGs oficiales es un cambio aislado en `ServiceIcon.tsx` si el
  usuario los aporta.
- Quedan las fases 11C (Onboarding), 11D (Tareas automáticas/scheduler),
  11E (Biblioteca/pósters) y 11F (Dashboard) — no implementadas todavía.
