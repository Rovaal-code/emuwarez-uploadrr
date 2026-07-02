# Checkpoint — Onboarding wizard milestone (Fase 11C)

| Campo | Valor |
|-------|-------|
| Rama fusionada | `feature/ui-phase-11c-onboarding-wizard` |
| Commit de la fase | `e472a98` ("feat: onboarding wizard — welcome step, Seerr step, hardlink strategy, skip warnings") |
| Merge commit | `82b0847` ("merge: onboarding wizard milestone", `--no-ff`, sin conflictos, sobre base `9ecd05b`) |
| Tag | `emuwarez-uploadrr-onboarding-wizard-v0` (apunta al merge commit) |
| Tests | 1054 passed, 0 fallos (verificado de nuevo en `master` tras el merge) |
| `npm run build` | OK |
| Push | Ninguno — no hay remote configurado en este repo |

## Resumen de la fase

Tercera sub-fase (11C) de la iteración grande de UI/configuración. Amplía
el wizard de setup ya existente (no lo reconstruye): nuevo paso
"Bienvenida", reordenación completa (admin→base→emu→instancias→
seerr→tmdb→uploadrr→nomenclatura→completar), nuevo paso Seerr opcional,
nuevo paso de nomenclatura/hardlinks (con checkbox de "no usar hardlinks"
protegido por confirmación exacta `DESACTIVAR_HARDLINKS`), advertencia
explícita al intentar omitir la verificación de la key de eMuwarez, y
dropdowns de región/idioma en el paso TMDb. Se corrigió además un bug real
preexistente en `setupInstances()` que habría hecho fallar con 422 la
adición de instancias Radarr/Sonarr desde el wizard en producción.

Verificado con un recorrido end-to-end real en navegador (Playwright)
sobre una base de datos completamente nueva, desde "Bienvenida" hasta
aterrizar en el Dashboard.

Detalle completo: `docs/codex_phase_11c_onboarding_wizard_report.md`.

Quedan pendientes las fases 11D (Tareas automáticas/scheduler), 11E
(Biblioteca/pósters) y 11F (Dashboard).

## Confirmaciones de seguridad

- El modo "no usar hardlinks" solo persiste una preferencia — no se
  implementó ningún motor que module archivos originales de la biblioteca.
- La confirmación `DESACTIVAR_HARDLINKS` se valida en el backend, no solo
  en el frontend.
- Sin push en ningún momento.
