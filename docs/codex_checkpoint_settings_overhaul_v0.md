# Checkpoint — Settings overhaul milestone (Fase 11A)

| Campo | Valor |
|-------|-------|
| Rama fusionada | `feature/ui-phase-11a-settings-overhaul` |
| Commit de la fase | `4bdd27f` ("feat: settings overhaul — Emuwarez API section, TMDb/region/language fixes, provider priority picker, notifications") |
| Merge commit | `b6603fd` ("merge: settings overhaul milestone", `--no-ff`, sin conflictos, sobre base `69e8bcb`) |
| Tag | `emuwarez-uploadrr-settings-overhaul-v0` (apunta al merge commit) |
| Tests | 1010 passed, 0 fallos (verificado de nuevo en `master` tras el merge) |
| `npm run build` | OK |
| Push | Ninguno — no hay remote configurado en este repo |

## Resumen de la fase

Primera sub-fase (11A) de la iteración grande de UI/configuración (20
secciones) pedida por el usuario — ver plan de la sesión y roadmap completo
en `docs/codex_phase_11a_settings_overhaul_report.md` y en la memoria del
proyecto. Cubre únicamente Settings: sección Emuwarez API, fix del
placeholder engañoso de TMDb, dropdowns de región/idioma, picker de
prioridad de providers (checkboxes + drag), y nueva pestaña de
Notificaciones (Discord/Telegram).

Quedan pendientes las fases 11B (Instancias: editar + iconos + Seerr), 11C
(Onboarding), 11D (Tareas automáticas/scheduler), 11E (Biblioteca/pósters) y
11F (Dashboard) — no implementadas todavía.

## Confirmaciones de seguridad

- No se ejecutó ninguna notificación real fuera de los tests mockeados.
- Los secretos (webhook de Discord, bot token de Telegram, API key de
  Emuwarez) nunca aparecen en las respuestas de la API ni en los tests.
- Sin push en ningún momento.

## Nota operativa (2026-07-02)

A petición del usuario, se han borrado todas las imágenes Docker locales
`emuwarez-uploadrr:*` existentes (eran de pruebas de fases anteriores). No
se reconstruirá una imagen nueva hasta que termine toda la iteración de la
Fase 11 (11A–11F), momento en el que se validará todo junto con un build
Docker limpio.
