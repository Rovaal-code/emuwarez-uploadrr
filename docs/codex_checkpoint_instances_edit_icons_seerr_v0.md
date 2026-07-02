# Checkpoint — Instances edit, icons, and Seerr support milestone (Fase 11B)

| Campo | Valor |
|-------|-------|
| Rama fusionada | `feature/ui-phase-11b-instances-edit-icons-seerr` |
| Commit de la fase | `c22c972` ("feat: instances edit, redesigned icons, and Seerr support") |
| Merge commit | `c8bcb72` ("merge: instances edit, icons, and Seerr support milestone", `--no-ff`, sin conflictos, sobre base `1454f1d`) |
| Tag | `emuwarez-uploadrr-instances-edit-icons-seerr-v0` (apunta al merge commit) |
| Tests | 1039 passed, 0 fallos (verificado de nuevo en `master` tras el merge) |
| `npm run build` | OK |
| Push | Ninguno — no hay remote configurado en este repo |

## Resumen de la fase

Segunda sub-fase (11B) de la iteración grande de UI/configuración. Cubre
Instancias: nuevo endpoint `PUT /api/instances/{id}` (cablea el
`update_instance()` ya existente), iconos Radarr/Sonarr rediseñados +
nuevo icono Seerr, y soporte completo para instancias Seerr
(Overseerr/Jellyseerr-compatible): primera migración de rebuild de tabla
del proyecto (`instances.type` CHECK ampliado), cliente de integración de
solo lectura, y alta/edición/test desde la UI. Sincronización de
peticiones desde Seerr queda fuera de alcance (400 explícito), según lo
acordado — solo se preparó la UI/modelo de datos.

Detalle completo: `docs/codex_phase_11b_instances_edit_icons_seerr_report.md`.

Quedan pendientes las fases 11C (Onboarding), 11D (Tareas
automáticas/scheduler), 11E (Biblioteca/pósters) y 11F (Dashboard).

## Confirmaciones de seguridad

- Todas las llamadas de red a Seerr/Radarr/Sonarr en tests están mockeadas.
- Los secretos (API keys) nunca aparecen en las respuestas de la API.
- La migración de BD se verificó idempotente y preserva filas/IDs
  existentes (probado tanto en tests como manualmente sobre la BD de demo
  ya poblada de fases anteriores).
- Sin push en ningún momento.
