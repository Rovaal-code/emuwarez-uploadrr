# Fase 11 — Informe final combinado

Resumen de las 6 sub-fases (11A-11F) en que se dividió la iteración grande
de UI/configuración pedida originalmente en un único encargo de 20
secciones. Se implementó por fases con checkpoints (rama →
implementación → tests → verificación manual → commit → merge `--no-ff` →
tag → checkpoint), siguiendo el mismo patrón que el resto del proyecto
(Fases 0-10F).

## 1. Resumen

| Sub-fase | Alcance | Tag |
|---|---|---|
| 11A | Settings: Emuwarez API, fix TMDb, dropdowns región/idioma, prioridad de providers (checkboxes+drag), Notificaciones (Discord/Telegram) | `emuwarez-uploadrr-settings-overhaul-v0` |
| 11B | Instancias: editar (PUT ya existente, solo cableado), iconos Radarr/Sonarr rediseñados + Seerr, primera migración de rebuild de tabla del proyecto | `emuwarez-uploadrr-instances-edit-icons-seerr-v0` |
| 11C | Onboarding: paso Bienvenida, reordenado admin→base→emu→instancias→seerr→tmdb→uploadrr→nomenclatura→completar, paso Seerr opcional, paso nomenclatura/hardlinks con confirmación, fix de bug real en `setupInstances()` | `emuwarez-uploadrr-onboarding-wizard-v0` |
| 11D | Tareas automáticas: primer scheduler en background del proyecto (sin dependencias nuevas), reutiliza sync existentes | `emuwarez-uploadrr-automatic-tasks-scheduler-v0` |
| 11E | Biblioteca: extracción de `poster_url` desde Radarr/Sonarr, vista de pósters por defecto + toggle a lista (persistido en localStorage) | `emuwarez-uploadrr-library-poster-grid-v0` |
| 11F | Dashboard: elimina Salud ARR/"Qué hacer ahora", reposiciona Peticiones accionables, repurpuesta Actividad reciente (prioriza peticiones satisfechas), panel real de Actividad de subida | `emuwarez-uploadrr-dashboard-redesign-v0` |

Todas las sub-fases están **mergeadas a `master`** con `--no-ff`, tag y
commit de checkpoint. Reportes individuales en
`docs/codex_phase_11{a,b,c,d,e,f}_*.md`, checkpoints en
`docs/codex_checkpoint_*.md`.

Secciones del encargo original ya satisfechas sin necesitar una sub-fase
dedicada (verificado por grep antes de empezar, documentado en el plan
inicial):
- **Quitar "priority" de Subidas**: no existía ningún campo así en todo el
  proyecto (ni backend ni frontend) — nada que quitar.
- **Limpieza de modo demo**: `demo seed` ya requería confirmación explícita
  por CLI y `App.tsx` ya fuerza el wizard de setup si falta admin/init —
  sin cambios de código necesarios.

## 2. Archivos cambiados (resumen agregado por área)

- **Backend — nuevo**: `services/scheduler.py`, `services/notifications.py`,
  `integrations/seerr.py`, `web/api/scheduled_tasks.py`,
  `web/api/notifications.py`.
- **Backend — modificado en varias sub-fases**: `database.py` (3
  migraciones nuevas: Seerr rebuild-de-tabla, `scheduled_tasks`,
  `poster_url`; `SCHEMA_VERSION` 12→16), `models.py`, `web/schemas.py`,
  `web/api/router.py`, `web/api/dashboard.py`, `web/api/library.py`,
  `web/api/setup.py`, `web/api/instances.py`, `web/services/setup_service.py`,
  `services/library.py`, `services/instances.py`, `services/tasks.py`,
  `integrations/base.py`, `integrations/radarr.py`, `integrations/sonarr.py`.
- **Frontend — nuevo**: `components/ProviderPriorityPicker.tsx`,
  `constants/regionLanguage.ts`, `api/scheduledTasks.ts`,
  `api/notifications.ts`, `pages/TasksPage.tsx` (reescrita).
- **Frontend — modificado/reescrito**: `pages/SettingsPage.tsx`,
  `pages/InstancesPage.tsx`, `pages/SetupWizard.tsx` (reescrita),
  `pages/LibraryPage.tsx`, `pages/DashboardPage.tsx` (reescrita),
  `components/ServiceIcon.tsx` (reescrito), `types/api.ts`,
  `types/domain.ts`, `api/setup.ts`, `api/instances.ts`, `api/library.ts`,
  `api/dashboard.ts`, `api/integrationTests.ts`.
- **Tests nuevos**: 14 ficheros nuevos de test a lo largo de las 6
  sub-fases (ver detalle por fase en cada report individual).
- **Docs**: 6 reports de sub-fase + 6 checkpoints + este informe final.

Detalle línea a línea de cada cambio: ver el report individual de cada
sub-fase (contienen citas de archivo:línea).

## 3. Tests / validación

| Momento | Tests |
|---|---|
| Antes de la Fase 11 (tras 10F) | 975 passed |
| Tras 11A | 1010 passed (+35) |
| Tras 11B | 1039 passed (+29) |
| Tras 11C | 1054 passed (+15) |
| Tras 11D | 1090 passed (+36) |
| Tras 11E | 1105 passed (+15) |
| Tras 11F | **1109 passed (+4)** |

**Total: +134 tests nuevos a lo largo de la Fase 11. `pytest -q` en
`master` tras el último merge: 1109 passed, 0 fallos.**

`npm run build` (`tsc && vite build`) verificado sin errores tras cada
sub-fase individualmente y en el estado final de `master`.

No existe tooling de tests de frontend (ni vitest ni jest) en este
proyecto — la validación de frontend fue siempre tipos (`tsc`) + build
(`vite build`), consistente con todas las fases anteriores del proyecto.

**Verificación manual real** (no solo tests automatizados) en cada
sub-fase: servidor demo real (`~/.config/emuwarez-uploadrr-demo`, puerto
9494) recorrido con Playwright controlando Google Chrome real, incluyendo
un recorrido end-to-end completo del wizard de onboarding desde una base
de datos limpia (11C), confirmación de que el scheduler automático se
dispara solo en un servidor real sin intervención manual (11D), pósters
reales renderizados en el grid de Biblioteca (11E), y el panel de
Actividad de subida con un trabajo de subida real insertado
manualmente (11F). Todas las capturas y datos de prueba manuales se
limpiaron de la base de datos demo tras cada verificación.

## 4. Limitaciones conocidas (agregado, ver cada report para detalle)

- **Seerr**: solo modelo de datos + UI + test de conexión. La
  sincronización real de peticiones desde Overseerr/Jellyseerr **no está
  implementada** — deliberadamente fuera de alcance en 11B, honrado
  consistentemente en 11C (paso opcional del wizard) y 11D (la tarea
  programada reporta esto explícitamente en vez de fingir sincronizar).
- **eMuwarez**: sin endpoint conocido de detección de usuario ("whoami") —
  el test de conexión solo confirma validez de la API key, sin mostrar
  nombre de usuario.
- **Nomenclatura sin hardlinks**: solo se implementó el almacenamiento de
  la preferencia (`nomenclature.use_hardlinks`); no se implementó ningún
  motor alternativo que renombre el archivo original de la biblioteca en
  su sitio — habría contradicho una invariante de seguridad usada en todo
  el proyecto ("nunca modificar el archivo original").
- **Extracción de pósters**: solo usa `remoteUrl` de Radarr/Sonarr, nunca
  la URL relativa `url` (evita filtrar la API key de la instancia en una
  imagen visible en el cliente). Si una instancia solo expone `url`, el
  póster queda vacío (icono de marcador de posición).
- **Dashboard — Actividad de subida**: sin velocidad/transferencia/ETA
  (el backend nunca los expone, Uploadrr-EMU no reporta progreso
  estructurado) — se usa tiempo transcurrido real + etapas discretas en
  su lugar.
- **Dashboard — widget de Uptime** de la imagen de referencia: no
  implementado (no hay tracking de arranque de proceso en el backend, y
  no se pidió instrumentarlo explícitamente).
- El topbar (toggle claro/oscuro) de la imagen de referencia no se tocó
  en ninguna sub-fase — decisión tomada en el plan inicial de la Fase 11.

## 5. Capturas de pantalla

Todas las capturas de verificación manual se generaron en el servidor demo
real durante la implementación (no se adjuntan como archivos en el repo,
ya que son artefactos de verificación de sesión, no documentación
permanente del proyecto) — descritas en detalle en la sección
"Verificación manual" de cada report individual de sub-fase
(`docs/codex_phase_11{a,b,c,d,e,f}_*.md`).

## Próximo paso (pendiente de confirmación del usuario)

Por instrucción explícita anterior del usuario, **no se ha construido
ninguna imagen Docker nueva** durante la Fase 11 (todas las de prueba se
borraron al empezar 11A, con la instrucción de esperar "al final de todas
las fases" para construir una nueva y probar todo end-to-end). Con las 6
sub-fases ya mergeadas a `master`, ese momento ha llegado — pendiente de
que el usuario confirme si quiere que se construya y valide ahora
(`docker build` + `docker compose config` + `scripts/docker-smoke-test.sh`
+ `scripts/docker-e2e-demo.sh`, el mismo proceso usado en fases anteriores
como 10F).
