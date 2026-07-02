# Fase 11F — Rediseño del Dashboard

Sexta y última sub-fase de la iteración grande de UI/configuración (Fase
11). Referencia visual: `references/interfaz_de_gestión_de_subidas_emu.png`
(no trackeada en git, no borrar).

## Estado del repo

| Campo | Valor |
|-------|-------|
| Rama base | `master` (incluye 11A-11E ya mergeadas) |
| Rama de esta fase | `feature/ui-phase-11f-dashboard-redesign` |
| Tests previos | 1105 passed |
| Tests tras esta fase | 1109 passed, 0 fallos (1105 + 4 nuevos) |

## Qué se implementó

1. **Eliminada la sección "Salud Radarr/Sonarr"** (Fase 8A) del Dashboard.
2. **Eliminada la sección "Qué hacer ahora"** (cola operativa, Fase 8C) del
   Dashboard, junto con su estado (`queueTop`, `queueRefreshing`) y el
   `handleQueueRefresh()` asociado. La página "Cola" (`QueuePage.tsx`) sigue
   intacta y usa la misma API (`listQueue`/`refreshQueue`) — no se tocó.
3. **"Peticiones accionables" reposicionada** justo debajo de la barra de
   sincronización (antes vivía en la tercera posición de la columna
   derecha).
4. **"Actividad reciente" repurpuesta**: antes mostraba el historial de
   `task_runs` (sincronizaciones/tareas); ahora muestra elementos de la
   biblioteca priorizados por si satisfacen una petición eMuwarez:
   `Llena` (satisfecha) → `Compatible`/`Parcial` → el resto, con empate roto
   por `updated_at DESC` (interpretación honesta de "aleatorios": reordenar
   de verdad en cada carga sería solo ruido, no más útil; "más reciente
   primero" es un desempate determinista y significativo). Incluye botón
   "Subir" por fila que abre el modal de preflight ya existente
   (`UploadPreflightModal`, reutilizado tal cual de `LibraryPage.tsx`).
   - Nuevo endpoint `GET /api/dashboard/library-activity?limit=N`
     (`web/api/dashboard.py`), nueva función de servicio
     `services/library.py::get_dashboard_library_activity()`.
   - El endpoint `GET /api/dashboard/activity` (task_runs) **no se tocó** —
     sigue existiendo tal cual, para no romper el test preexistente
     `test_dashboard_activity_shows_sync`. Esos mismos datos ahora se
     muestran en una nueva sección al final de la página, renombrada
     honestamente **"Últimas tareas ejecutadas"**.
5. **Panel "Actividad de subida" real** (sustituye los 4 contadores
   estáticos "Subidas Uploadrr"): una tarjeta por cada trabajo de subida
   con `status=running` (reutiliza `GET /api/uploads?status=running&limit=5`,
   endpoint ya existente, sin cambios de backend), mostrando:
   - Título y tiempo transcurrido real (`started_at` → ahora, actualizado
     cada segundo en el cliente).
   - Barra de progreso **por etapas discretas** (`preflight` →
     `config_staging` → `running` → `finalizing`, 4 pasos fijos), nunca un
     porcentaje inventado — el backend (`compute_progress_phase()`, Fase
     10F) documenta explícitamente que Uploadrr-EMU no reporta progreso
     numérico.
   - "Última actividad" con el timestamp real `last_log_at`.
   - **Ningún campo de velocidad, transferencia en bytes o ETA** — no
     existen en el backend (confirmado por grep exhaustivo antes de
     implementar) y no se han fabricado.
6. Limpieza de tipos: `frontend/src/types/api.ts` — añadidos los campos
   Phase 8B reales a `DashboardSummaryResponse` (usados por "Peticiones
   accionables", antes accedidos vía `(s as any)`), y eliminada la
   interfaz `DashboardSummaryResponseV2` (duplicado sin ningún uso en todo
   el frontend, confirmado por grep).

## Qué NO se implementó de la imagen de referencia (y por qué)

- **Velocidad/transferencia/ETA por subida**: el backend no expone esos
  datos (Uploadrr-EMU no reporta progreso estructurado). Fabricarlos
  contradice el mandato explícito de esta fase.
- **Widget "Sistema operativo: Saludable / Versión / Uptime"** en el pie
  del sidebar: "Versión" sí existe (`/api/health`), pero **"Uptime" no —
  no hay ningún registro de la hora de arranque del proceso en todo el
  backend** (confirmado por grep). Añadir esa instrumentación es un cambio
  de infraestructura nuevo, no pedido explícitamente por el encargo de esta
  fase (que solo hablaba de eliminar/reposicionar/repropósito secciones
  concretas) — se dejó fuera para no inventar una métrica falsa ni
  expandir el alcance sin pedirlo.
- **Paginación con selector de tamaño de página en "Actividad reciente"**:
  el widget del dashboard es una vista acotada (top 10) con propósito de
  "vistazo rápido"; la Biblioteca (Fase 11E) ya ofrece la vista completa
  paginada/filtrable con más detalle. Añadir paginación completa aquí
  habría duplicado esa funcionalidad sin necesidad.
- **"Últimos eventos"** (panel separado de "Últimas tareas ejecutadas"):
  no existe ningún feed de eventos distinto de `task_runs` en el backend;
  crear uno sería inventar una fuente de datos nueva no solicitada
  explícitamente. Se mantuvo solo "Últimas tareas ejecutadas".
- El topbar (toggle claro/oscuro, etc.) — decisión ya tomada en el plan
  inicial de la Fase 11, no se ha tocado en ninguna sub-fase.

## Tests

- `tests/test_dashboard_library_api.py` — 4 tests nuevos: auth requerida,
  lista vacía, priorización correcta (`Llena` > `Compatible` > sin
  petición, verificado con 3 películas reales sincronizadas y
  `update_request_status()`), respeto del parámetro `limit`.
- Test preexistente `test_dashboard_activity_shows_sync` (endpoint
  `/dashboard/activity`, sin tocar) sigue pasando sin modificar.

**`pytest -q`**: `1109 passed, 0 failed`.
**`npm run build`**: OK, sin errores de tipos.

## Verificación manual (servidor demo real)

- Confirmado que "Actividad reciente" muestra un elemento con petición
  `Compatible` antes que el resto (`Sin petición`), con botón "Subir" por
  fila.
- Confirmado que "Peticiones accionables" aparece justo bajo el botón de
  sincronización.
- Confirmado que "Últimas tareas ejecutadas" muestra el historial real de
  `task_runs` (incluyendo ejecuciones automáticas del scheduler de la Fase
  11D) al final de la página.
- Insertado manualmente un `upload_jobs` con `status=running,
  stage=config_staging` para verificar el panel "Actividad de subida": se
  renderizó correctamente con tiempo transcurrido real ("2m 37s"), barra de
  progreso en el paso 2/4 ("Preparando configuración"), y "Última
  actividad" con el `last_log_at` real. Fila de prueba eliminada tras la
  verificación.
- Confirmado que las secciones "Salud Radarr/Sonarr" y "Qué hacer ahora"
  ya no aparecen en ningún punto de la página.

## Gaps / limitaciones conocidas

- El desempate "aleatorios" en "Actividad reciente" se implementó como
  "más recientemente actualizado", no como orden verdaderamente aleatorio
  — documentado como decisión deliberada más arriba.
- El widget de "Uptime" del sidebar de la imagen de referencia no se
  implementó (requeriría instrumentación nueva de arranque del proceso,
  fuera de alcance).
