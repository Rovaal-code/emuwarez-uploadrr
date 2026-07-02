# Checkpoint — Automatic tasks scheduler milestone (Fase 11D)

| Campo | Valor |
|-------|-------|
| Rama fusionada | `feature/ui-phase-11d-automatic-tasks-scheduler` |
| Commit de la fase | `25802fc` ("feat: automatic tasks scheduler for library/eMuwarez/Seerr sync") |
| Merge commit | `50090c4` ("merge: automatic tasks scheduler milestone", `--no-ff`, sin conflictos, sobre base `50a9860`) |
| Tag | `emuwarez-uploadrr-automatic-tasks-scheduler-v0` (apunta al merge commit) |
| Tests | 1090 passed, 0 fallos (verificado de nuevo en `master` tras el merge) |
| `npm run build` | OK |
| Push | Ninguno — no hay remote configurado en este repo |

## Resumen de la fase

Cuarta sub-fase (11D) de la iteración grande de UI/configuración — la de
mayor riesgo arquitectónico: primer scheduler en background del proyecto
(sin dependencias nuevas). Nueva tabla `scheduled_tasks` +
`services/scheduler.py` (100% síncrono, testeable sin asyncio) + hook de
lifespan de FastAPI en `web/app.py` que hace tick cada 60s vía
`asyncio.to_thread`. Reutiliza `services/library.py::sync_all()` y
`services/requests.py::sync_emu_requests()` tal cual (incluyendo el límite
de 1 hora ya existente para eMuwarez), en vez de duplicar lógica. La
sincronización de peticiones Seerr reporta honestamente que no está
implementada todavía, sin fingir hacer nada.

Nuevos endpoints `GET/PUT/POST /api/tasks/scheduled...` y `TasksPage.tsx`
reescrita con tarjetas por tarea (intervalo, cuenta atrás, ejecutar ahora,
ver logs).

Verificado con un servidor demo real: el scheduler se disparó solo a los
~60s de arrancar, sincronizando de verdad 362 elementos de Radarr/Sonarr sin
ninguna acción manual, y el modal de logs mostró historial real
preexistente de fases anteriores.

Detalle completo: `docs/codex_phase_11d_automatic_tasks_scheduler_report.md`.

Quedan pendientes las fases 11E (Biblioteca/pósters) y 11F (Dashboard).

## Confirmaciones de seguridad

- El scheduler está confirmado inactivo durante los tests (`TestClient`
  sin `with` no dispara lifespan) — verificado explícitamente antes de
  implementar, no supuesto.
- Escape hatch `EMUWAREZ_DISABLE_SCHEDULER=1` para scripts de smoke/E2E.
- Sin push en ningún momento.
