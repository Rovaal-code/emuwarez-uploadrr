# Fase 11D — Tareas automáticas (scheduler)

Cuarta sub-fase de la iteración grande de UI/configuración. Pieza de mayor
riesgo arquitectónico de todo el encargo: no existía ningún scheduler en el
proyecto (ni APScheduler, ni cron, ni un loop propio) — las "tareas" eran
solo historial (`task_runs`) ejecutado bajo demanda.

## Estado del repo

| Campo | Valor |
|-------|-------|
| Rama base | `master` (incluye 11A+11B+11C ya mergeadas) |
| Rama de esta fase | `feature/ui-phase-11d-automatic-tasks-scheduler` |
| Tests previos | 1054 passed |
| Tests tras esta fase | 1090 passed, 0 fallos (1054 + 36 nuevos) |

## Arquitectura del scheduler

Sin dependencias nuevas (no APScheduler). Mecanismo ligero de tres capas:

1. **`scheduled_tasks`** (tabla nueva, `database.py`): bookkeeping puro
   (intervalo, mínimo permitido, si admite ejecución manual, última/próxima
   ejecución, último estado/resumen). Sembrada de forma idempotente con 3
   tareas fijas.
2. **`emuwarez_uploadrr/services/scheduler.py`** (nuevo, sin dependencia de
   asyncio — 100% síncrono y testeable): `claim_due_tasks()` marca como
   "reclamadas" (empuja `next_run_at` una ventana de gracia de 5 min) las
   tareas vencidas antes de ejecutarlas, para que un tick concurrente no las
   vuelva a disparar mientras siguen en curso; `run_scheduled_task()`
   ejecuta una tarea y actualiza su bookkeeping; `tick_due_tasks()` junta
   ambas cosas abriendo su propia conexión SQLite.
3. **`web/app.py`**: hook de lifespan de FastAPI que lanza
   `asyncio.create_task` con un loop que llama a
   `asyncio.to_thread(tick_due_tasks)` cada 60 segundos — así una
   sincronización lenta (red bloqueante) nunca bloquea el event loop de la
   API. Verificado explícitamente que **no se activa durante los tests**
   (`TestClient(app)` sin `with` no dispara eventos de lifespan — confirmado
   con una prueba aislada antes de implementar), así que los 1090 tests no
   arrancan ningún scheduler real. Variable de entorno
   `EMUWAREZ_DISABLE_SCHEDULER=1` como válvula de escape adicional para
   scripts de smoke/E2E.

## Reutilización de infraestructura existente (en vez de duplicarla)

- **Sincronización de bibliotecas**: reutiliza `services/library.py::sync_all()`
  tal cual — esta función YA registraba sus propias ejecuciones en
  `task_runs` bajo el nombre `"sync-library"`. El scheduler usa ese mismo
  nombre como `task_key`, así que el historial de "Ver logs" incluye
  automáticamente sincronizaciones manuales previas hechas desde el
  Dashboard, antes de que existiera esta fase (visto en la verificación
  manual: 2 ejecuciones antiguas + la nueva automática, todas en la misma
  tabla de logs).
- **Sincronización de peticiones eMuwarez**: reutiliza
  `services/requests.py::sync_emu_requests()` **tal cual**, que YA
  implementaba el límite de 1 hora (`MIN_SYNC_SECONDS = 3600`,
  `can_sync_requests()`) — por eso esta tarea tiene `min_interval_minutes=60`
  y `manual_allowed=False` codificados de forma consistente con esa
  constante preexistente.
- **Peticiones Seerr**: no existe ninguna función de sincronización real
  (la sincronización de peticiones Seerr sigue fuera de alcance, ver 11B/
  11C). El ejecutor de esta tarea es honesto al respecto: cuenta instancias
  Seerr configuradas y reporta `"skipped"` con el mensaje "Seerr
  configurado, pero la sincronización de peticiones todavía no está
  implementada" (o "Sin instancias Seerr configuradas" si no hay ninguna) —
  nunca finge sincronizar algo que no existe. Un test (`test_run_seerr_sync_never_calls_real_network`)
  garantiza explícitamente que este ejecutor jamás intenta ninguna llamada
  de red.

## Backend — endpoints nuevos

- `GET /api/tasks/scheduled` — lista las 3 tareas con su bookkeeping.
- `PUT /api/tasks/scheduled/{task_key}` — cambia el intervalo (rechaza con
  422 si está por debajo del mínimo de esa tarea).
- `POST /api/tasks/scheduled/{task_key}/run` — ejecuta ahora (400 si la
  tarea no admite ejecución manual, ej. eMuwarez).
- `GET /api/tasks/scheduled/{task_key}/logs` — historial de ejecuciones
  (reutiliza `task_runs` vía nueva `services/tasks.py::list_tasks_by_name()`).

## Frontend

- `api/scheduledTasks.ts` (nuevo): tipos + llamadas a los 4 endpoints.
- `pages/TasksPage.tsx` (reescrito): una tarjeta por tarea con selector de
  intervalo (opciones filtradas por el mínimo de cada tarea), última/próxima
  ejecución (cuenta atrás en vivo, actualizada cada segundo), estado con
  color (verde/rojo/ámbar), resumen de la última ejecución, botón "Ejecutar
  ahora" (oculto para la tarea de eMuwarez, sustituido por el texto
  explicativo + cuenta atrás), y botón "Ver logs" que abre un modal con el
  historial reciente. La página hace polling ligero cada 30s para reflejar
  ejecuciones automáticas que ocurran en segundo plano mientras está abierta.

## Tests

- `tests/test_scheduler_service.py` (21): defaults sembrados correctamente,
  validación de intervalo mínimo por tarea, ejecución de cada tipo de tarea
  (mockeando la función subyacente, nunca red real), fallo registrado sin
  relanzar la excepción, bloqueo de ejecución manual para eMuwarez,
  `claim_due_tasks` (todo vencido al principio, no se re-reclama
  inmediatamente, respeta `enabled=0`), `tick_due_tasks` end-to-end.
- `tests/test_scheduled_tasks_api.py` (15): auth requerida en los 4
  endpoints, contenido de la lista, validación de intervalo (200/422/404),
  bloqueo manual de eMuwarez (400), logs (200/404), y una prueba explícita
  de que la respuesta de "ejecutar ahora" no filtra secretos.

**`pytest -q`**: `1090 passed, 0 failed`.
**`npm run build`**: OK, sin errores de tipos.

## Verificación manual (servidor real, no mockeado)

Arrancado el servidor demo persistente (con instancias Radarr/Sonarr reales
de la demo ya configuradas desde fases anteriores) y confirmado que:

- El scheduler se disparó solo, automáticamente, a los ~60s de arrancar el
  proceso — **sin ninguna acción manual** — sincronizando de verdad 362
  elementos desde las instancias Radarr/Sonarr configuradas.
- La tarea de Seerr se marcó como omitida (sin instancias Seerr en esta
  demo).
- La tarea de eMuwarez falló limpiamente con "No hay API key EMU
  configurada" (correcto, esta demo no tiene key eMuwarez) y programó su
  próxima ejecución a 1 hora vista.
- La vista "Tareas" del frontend renderiza las 3 tarjetas con los datos
  reales, cuenta atrás en vivo, y la tarea de eMuwarez sin botón de
  ejecución manual.
- El modal "Ver logs" de la sincronización de bibliotecas mostró **el
  historial real**, incluyendo dos ejecuciones manuales hechas en fases
  anteriores a través del botón "Sincronizar biblioteca" del Dashboard,
  antes de que existiera esta fase — confirma que la reutilización de
  `task_runs`/`"sync-library"` funciona correctamente con datos reales
  preexistentes, no solo con datos nuevos.

## Gaps / limitaciones conocidas

- La sincronización automática de peticiones Seerr solo cuenta instancias
  configuradas; no sincroniza peticiones de verdad (la función no existe
  todavía, ver 11B/11C). El scheduler está preparado para activarla el día
  que se implemente — solo haría falta sustituir el cuerpo de
  `_run_seerr_sync()`.
- El scheduler es de un solo proceso (no hay coordinación multi-proceso);
  esto es correcto para el modelo de despliegue actual (`web serve` como
  proceso único), documentado explícitamente en el docstring del módulo.
- Quedan las fases 11E (Biblioteca/pósters) y 11F (Dashboard).
