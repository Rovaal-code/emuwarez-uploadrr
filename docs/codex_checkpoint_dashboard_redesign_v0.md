# Checkpoint — Dashboard redesign milestone (Fase 11F)

| Campo | Valor |
|-------|-------|
| Rama fusionada | `feature/ui-phase-11f-dashboard-redesign` |
| Commit de la fase | `4428c90` ("feat: dashboard redesign — remove ARR health/queue panels, real upload activity") |
| Merge commit | `9de49c2` ("merge: dashboard redesign milestone", `--no-ff`, sin conflictos, sobre base `595fac3`) |
| Tag | `emuwarez-uploadrr-dashboard-redesign-v0` (apunta al merge commit) |
| Tests | 1109 passed, 0 fallos (verificado de nuevo en `master` tras el merge) |
| `npm run build` | OK |
| Push | Ninguno — no hay remote configurado en este repo |

## Resumen de la fase

Sexta y última sub-fase (11F) de la iteración grande de UI/configuración
(Fase 11). Elimina "Salud Radarr/Sonarr" y "Qué hacer ahora" del Dashboard,
reposiciona "Peticiones accionables" bajo el botón de sincronización, y
repurpuesta "Actividad reciente" para mostrar elementos de biblioteca
priorizados por si satisfacen una petición eMuwarez (nuevo endpoint
`GET /api/dashboard/library-activity`) — el historial de tareas que antes
ocupaba ese lugar se movió, sin tocar su endpoint, a una nueva sección
honestamente etiquetada "Últimas tareas ejecutadas".

Sustituye los contadores estáticos "Subidas Uploadrr" por un panel real
"Actividad de subida" con tarjetas por trabajo en curso (reutiliza
`GET /uploads?status=running`, sin cambios de backend), con tiempo
transcurrido real y una barra de progreso por etapas discretas — sin
velocidad, transferencia o ETA inventadas, porque Uploadrr-EMU nunca
reporta esos datos.

Verificado con capturas reales en navegador (incluida una fila de
`upload_jobs` insertada manualmente para probar visualmente el panel de
actividad de subida, eliminada después de verificar).

Detalle completo: `docs/codex_phase_11f_dashboard_redesign_report.md`.

## Fase 11 completa

Con esta sub-fase se cierran las 6 sub-fases de la Fase 11:
11A (Settings) → 11B (Instancias/Seerr) → 11C (Onboarding) → 11D (Tareas
automáticas/scheduler) → 11E (Biblioteca/pósters) → 11F (Dashboard).

## Confirmaciones de seguridad

- El endpoint preexistente `/dashboard/activity` no se modificó — su test
  (`test_dashboard_activity_shows_sync`) sigue pasando sin cambios.
- No se fabricó ningún dato de velocidad/ETA/porcentaje de subida.
- Sin push en ningún momento.
