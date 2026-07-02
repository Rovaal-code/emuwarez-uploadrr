# Fase 11A — Settings overhaul (Emuwarez API, TMDb, dropdowns, prioridad de providers, notificaciones)

Primera sub-fase de la iteración grande de UI/configuración pedida por el
usuario (20 secciones — ver plan en `.claude/plans/whimsical-dancing-orbit.md`
de la sesión). Se decidió abordarla por fases con checkpoints, igual que el
resto del proyecto (10A–10F). Esta fase cubre únicamente Settings.

## Estado del repo

| Campo | Valor |
|-------|-------|
| Ruta | `~/Descargas/emuwarez_uploadrr/emuwarez_uploadrr_cli_ready_v2` |
| Rama base | `master` (limpia, incluye Fase 10F ya mergeada — commit `69e8bcb`) |
| Rama de esta fase | `feature/ui-phase-11a-settings-overhaul` |
| Tests previos | 975 passed |
| Tests tras esta fase | 1010 passed, 0 fallos (975 + 35 nuevos) |

## Qué se implementó

1. **Sección Emuwarez API en Settings** (antes solo existía en el setup
   wizard): tarjeta "Emuwarez" en la pestaña Configuración — API key/token,
   estado configurada/no configurada (enmascarada), botón "Probar conexión"
   (reutiliza `test_emuwarez_connection` ya existente de la Fase 10C). **No
   muestra usuario/cuenta detectado** — se confirmó que la API de eMuwarez
   integrada en este proyecto (`emuwarez_uploadrr/integrations/emu.py`) no
   tiene ningún endpoint de perfil/cuenta propia ya usado (solo
   torrents/peticiones); limitación documentada explícitamente en la propia
   UI, no un olvido.
2. **Fix campo TMDb**: quitado el placeholder `sk-…` (sugería formato de
   OpenAI) → placeholder neutro "API key de TMDb".
3. **Dropdowns región/idioma**: sustituidos los `<input>` de texto libre por
   `<select>` con listas fijas (`frontend/src/constants/regionLanguage.ts`,
   20 regiones / 16 idiomas, con ES/es-ES por defecto). Siguen escribiendo
   los mismos campos `tmdb_watch_region`/`tmdb_language` que ya existían —
   sin cambios de backend.
4. **Prioridad de providers**: nuevo componente
   `frontend/src/components/ProviderPriorityPicker.tsx` — checkboxes para
   activar/desactivar providers + reordenar por drag-and-drop nativo (HTML5
   `draggable`, sin añadir ninguna librería nueva). Sustituye el `<input>`
   CSV. Sigue guardando `provider_priority_order: string[]` en el mismo
   campo de siempre.
5. **Sección Notificaciones** (nueva pestaña en Settings, junto a
   Configuración/Diagnóstico/Backup/Mantenimiento):
   - Discord: activar/desactivar, webhook URL (enmascarada al guardar),
     botón "Probar notificación" que envía un mensaje de prueba real.
   - Telegram: activar/desactivar, bot token (enmascarado), chat ID, botón
     "Probar notificación".
   - Nuevo servicio `emuwarez_uploadrr/services/notifications.py`
     (`send_discord_test`/`send_telegram_test`) y nuevo endpoint
     `emuwarez_uploadrr/web/api/notifications.py`
     (`POST /api/notifications/test/discord|telegram`).

## Backend — detalle

- `web/services/settings_service.py`: `notify.discord.webhook_url` y
  `notify.telegram.bot_token` añadidos a `_SECRET_KEYS` (se enmascaran igual
  que `tmdb.api_key`/`emu.api_key`).
- `web/api/settings.py`: `SettingsResponse`/`SettingsUpdateRequest`
  ampliados con `emu_api_key_*` y `notify_discord_*`/`notify_telegram_*`.
  Deshabilitar una notificación (`enabled=false`) **no borra** el
  webhook/token guardado — solo cambia el flag, igual que el patrón
  existente de "guardar key aparte de activar/desactivar".
- `web/schemas.py`: `TestDiscordRequest`/`TestTelegramRequest` (reutiliza
  `IntegrationTestResult` ya existente para la respuesta, mismo shape que
  TMDb/eMuwarez/Arr).
- `web/api/router.py`: nuevo `notifications_router` registrado.

## Tests

- `tests/test_notifications_service.py` (17): mockea todas las llamadas
  HTTP salientes (discord/telegram) — nunca red real. Incluye guard
  explícito de "nunca se llama sin mock" y de que el bot token/webhook
  nunca aparece en el resultado.
- `tests/test_notifications_api.py` (9): auth guard, uso de valor del
  body vs valor guardado, nunca expone el secreto completo en la
  respuesta.
- `tests/test_settings_emu_notify_api.py` (9): guardar/leer `emu.api_key`
  desde Settings (no solo setup wizard), guardar/leer notificaciones,
  enmascarado, que desactivar no borra el secreto, y que
  `provider_priority_order` sigue funcionando como lista.

**`pytest -q`**: `1010 passed, 0 failed`.
**`npm run build`** (`tsc && vite build`): OK, sin errores de tipos.

## Verificación manual

Arrancada la app (mismo flujo de `CONFIG_DIR` + setup ya usado en la
sesión) y capturadas 4 pantallas: Configuración (TMDb sin pista SK +
dropdowns región/idioma + tarjeta Emuwarez), prioridad de providers
(picker con drag), selector expandido de providers disponibles, y pestaña
Notificaciones completa (Discord + Telegram). Todo coherente con el estilo
visual existente (mismas clases `placeholder-card`/`form-group`/`form-hint`).

## Gaps / limitaciones conocidas

- Usuario/cuenta de eMuwarez detectado: no implementado (sin endpoint
  conocido — ver punto 1 arriba). Si el usuario identifica el endpoint real
  en el futuro, es una extensión pequeña y aislada de
  `services/integration_tests.py::test_emuwarez_connection`.
- El resto de la iteración de 20 secciones (Instancias/Seerr, Onboarding,
  Tareas automáticas, Biblioteca/pósters, Dashboard) queda en fases
  posteriores (11B–11F), no implementadas todavía — ver plan.
