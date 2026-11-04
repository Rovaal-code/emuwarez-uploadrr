# Plan de implementación: «Subida por lotes»

Documento autosuficiente para quien lo ejecute. Hecho leyendo el código de `master` en `b934813` (04/11/2026), sin ejecutar
nada ni modificar ficheros. Los números de línea son aproximados (≈). Pendiente de que Gabriel responda las preguntas de §8;
la recomendación va en cada una. Al terminar cada PR, actualiza `docs/PLAN.md` (ver «Cómo se trabaja» allí).

---

## 0. Lo que hay hoy (hallazgos que condicionan el diseño)

1. **No existe selección múltiple en Biblioteca ni en Peticiones.** `LibraryPage.tsx` solo tiene `selected` (una ficha abierta) y
   `wizardItem` (un elemento). `RequestsPage.tsx` abre el asistente con un `libraryItemId` (`openUpload`, ≈ línea 645). El Panel
   tiene un botón «Subir» por fila (`CarrilListo.tsx`). Lo único «múltiple» es **dentro del asistente**: marcar temporadas de una
   serie (`PasoSeleccion`, `multiSelected`) o capítulos de una temporada (`episodeSelected`). La selección con casillas de
   Biblioteca y Panel hay que construirla desde cero.
2. **Una «tanda» del asistente no es una entidad.** `useAsistente.ts` (`uploadAllSeasons` ≈ 908, `uploadAllEpisodes` ≈ 960) hace un
   bucle **en el navegador**: por cada elemento llama a `queueUpload()` → `POST /library/{id}/upload/queue` y salta el que falle.
   El servidor no sabe que son una tanda. Cada una es un `upload_jobs` independiente. `Seleccion` (`utils/seleccionSubida.ts`)
   admite una sola cola homogénea («Nunca dos colas a la vez»): temporadas **o** capítulos.
3. **La cola ya es «un hilo por trabajo + puerta».** `upload_queue._insert_and_start_queued_job` (≈ 93-208) inserta la fila
   `queued` bajo `BEGIN IMMEDIATE`, publica `subida-estado` y llama a `_lanzar_trabajo` (≈ 211): un `threading.Thread` por trabajo
   que corre `_run_queued_job` (≈ 1375). Ese hilo toma plaza en `_upload_concurrency_gate`
   (`upload_execution/concurrencia.py`, clase `_UploadConcurrencyGate`) **antes** de comprobar/renombrar/preparar, y la traspasa al
   subproceso de Uploadrr-EMU (`puerta_traspasada`). La puerta admite por **id ascendente** (`min(self._waiting - retirados)`),
   relee el límite («Subidas en paralelo», `uploads.max_concurrent`, defecto 1, 0..10) en cada vuelta y despierta cada ≤3 s.
4. **Ciclo de vida por trabajo** (`upload_execution/ciclo_de_vida.py`): `cancel_upload_job` (distingue `queued` → `escribir_estado`
   + `retirar_de_la_cola`; `preparing` → solo marca; `running` → SIGTERM al grupo), `queue_retry_for_job` (crea fila nueva con
   `retry_of_job_id`, reanuda desde el paso que falló), `delete_upload_job` (borra la cadena entera de intentos). Un reintento
   hereda petición, propuesta de nomenclatura, overrides y snapshots.
5. **Cadenas de reintento**: `queue_upload_for_item` encadena cada «Subir» sobre el último trabajo del elemento
   (`_find_latest_job_for_item`), y `UploadsPage` solo enseña la punta de cada cadena (`hasNewerRetry`).
6. **Comprobaciones previas** ya divididas para tandas: `services/upload_checks.py::run_upload_checks(scope=...)` con
   `CONTENT_CHECK_IDS` (accesible, season_pack, capitulos_accesibles, carpeta_subida, renameable, spanish) por elemento y
   `ENVIRONMENT_CHECK_IDS` (output, qbittorrent, imghosts, emuwarez) una vez por tanda. En el cliente las orquesta
   `useComprobacionesTanda` (`asistente/useComprobaciones.ts`), que es **genérico sobre una lista de ids** (`batchQueue: number[]`)
   y reutilizable tal cual.
7. **Comprobaciones del servidor al correr el trabajo** (fallan el trabajo, no el lote): `_paso_comprobar` (integridad,
   `allowed_roots`, claves, `uploadrr.path`, nomenclatura bloqueada vía `_check_generic_upload_preconditions`), `_paso_nombre`
   (`build_nomenclature_apply_plan` / `build_season_pack_plan` no `ready`), `_populate_ready` (`validate_upload_preconditions`),
   `start_upload_job` (`validate_upload_job_start`). Duplicados: no hay bloqueo en la app; el Resumen compara contra el catálogo
   local (`getEmuComparison`, SQL local, sin red) y existe `conclusionDuplicados` (`utils/resumenSubida.ts`: niveles
   `duplicado | trump | mixto | peor | sin-comparar`). Uploadrr-EMU hace además su propia fase `duplicates` al ejecutarse; si
   aborta, la app solo ve un exit code distinto de 0 (no hay parseo específico de duplicado en `upload_result_parser.py`).
8. **Límite de eMuwarez (~28/min compartido)** (`integrations/emu_limitador.py`): la app solo pasa por él en la comprobación de
   entorno (`test_emuwarez_connection`, 1 llamada por pasada), el seeding por subida (`emu_torrent_stats`, solo al abrir un
   detalle) y las sincronizaciones. **El subproceso Uploadrr-EMU llama al tracker por su cuenta con la misma clave y NO pasa por
   ese limitador.** La única válvula real es «Subidas en paralelo».
9. **Notificaciones**: `_notify_upload_completed/_failed` (`upload_execution/estado.py`) emiten una notificación (campana +
   Discord/Telegram según ajustes) **por trabajo**.
10. **Panel**: «En curso» (`CarrilEnCurso.tsx`) pinta **todas** las subidas vivas, cada una con su `useTicker` (un `setInterval`
    por fila; permitido porque `utils/uploadStatus.ts` está en `RELOJES`). Un lote de 40 lo inundaría.
11. **Biblioteca virtualizada** (`FilasVirtuales`, `RejillaVirtual`, 3 vistas: pósters, pósters grandes, lista): las filas fuera
    de pantalla no existen en el DOM, así que la selección tiene que vivir en estado de `LibraryPage`, no en el DOM. La rejilla ya
    tuvo un bug de oscilación de medida (PLAN.md, «vista de pósters en negro»): cualquier adorno en la tarjeta no puede cambiar su
    alto.
12. **Rediseño pendiente P2 (Biblioteca) y P3 (Peticiones)** en PLAN.md: lo que toque esas pantallas choca con él.

---

## 1. Alcance, no-alcance y decisiones

### Alcance (v1)

- Elegir con casillas en **Biblioteca** (películas, series y temporadas) y en el **Panel** («Listo para subir»: peticiones,
  contenido único y mejoras) y subirlas **de un solo golpe** desde un modal nuevo de dos pasos: «Contenido» y «Resumen».
- Tipos de elemento del lote: **película**, **temporada (pack)** y, solo desde el Panel cuando la petición es de un capítulo,
  **capítulo suelto**. Una serie marcada se **expande a sus temporadas aptas para pack**.
- Un lote queda **agrupado en Subidas** (chip «Lote · N», filtro por lote, barra con contadores y acciones «Cancelar pendientes» /
  «Reintentar fallidas»).
- Cancelar, reintentar y fallos por elemento sin tumbar al resto.

### No-alcance (v1) y por qué

- **Sin edición por elemento** (Source/Proveedor/Tag/Título, pistas, idioma de pistas): se usan los nombres que propone la
  aplicación y el Resumen los **lista** (hoy una tanda no enseña el nombre de cada torrent; es un pendiente de PLAN.md). Quien
  quiera editar uno lo sube suelto. Editar 40 elementos en un modal no escala y duplicaría el hook de 1053 líneas.
- **Sin capítulos sueltos de varias series** desde Biblioteca (solo packs de temporada). Las temporadas no aptas para pack
  (incompletas, incoherentes, sin castellano en algún capítulo) salen **saltadas con su motivo**.
- **Sin selección en Peticiones** (la página); es el mismo modal con otro productor, queda para un PR opcional posterior.
- **Sin cambiar la concurrencia ni la puerta**: un lote no sube «más rápido»; solo evita el clic repetido. No hay prioridades ni
  «lote en serie» propios.
- **Sin entidad «lote» con tabla, nombre, política ni estado propios.**
- **Sin eventos nuevos, sin `setInterval` nuevos, sin estados nuevos de subida** (así no se tocan
  `test_copias_frontend.py::test_el_vocabulario_de_estados_coincide` ni los avisos).
- **Notificación agregada y unificar las tandas actuales con el nuevo endpoint**: opcionales, PR final (ver §6).

### Decisiones

| # | Decisión | Por qué |
|---|---|---|
| D1 | **Un lote es solo una etiqueta**: columna `upload_jobs.lote_id TEXT` (12 hex), sin tabla. | Cada elemento ya es un trabajo con su cadena de reintentos, su hilo, su cancelación y su borrado. Una tabla `upload_batches` obligaría a mantener estado (¿cancelado? ¿terminado?) que ya se deduce de las filas, y a decidir qué pasa al borrar. Todo lo que el lote necesita (contadores, cancelar pendientes, reintentar fallidas) se calcula con `GROUP BY lote_id` sobre las **puntas de cadena**. Si más adelante hace falta nombre o política, se añade la tabla y se rellena a partir de `lote_id` sin perder datos. |
| D2 | **El id lo asigna el servidor** en el nuevo endpoint (`secrets.token_hex(6)`); las tandas actuales del asistente mandan un id generado en el cliente (mismo formato, validado con regex) en su `queueUpload` de siempre. | Permite agrupar lo que ya existe sin reescribir los ~6 tests que verifican llamadas sueltas a `queueUpload`. |
| D3 | **Cada elemento sigue siendo un trabajo independiente**; no hay trabajo «padre». | No hay que reescribir `_run_queued_job`, `cancel_upload_job` ni `queue_retry_for_job`. |
| D4 | **Subidas no agrupa filas en acordeón**: chip «Lote · N» en la fila + filtro `lote_id` + barra de resumen cuando hay filtro. | La tabla ya anida cadenas de reintento y pagina por trabajos (100, «Cargar más»); un segundo nivel de anidado rompería ordenación, paginación y el recuento «N de M». |
| D5 | **Pertenencia al lote = punta de cadena con ese `lote_id`.** Un reintento (`queue_retry_for_job`) hereda el `lote_id` del original. Si después subes ese mismo elemento suelto (`queue_upload_for_item` sin lote) la fila vieja deja de ser punta y el lote «pierde» ese miembro. | Coherente con cómo ya se ven las cadenas. Se acepta y se documenta. |
| D6 | **Un fallo no detiene al resto** (igual que la tanda actual). | Es el comportamiento vigente y lo esperado; lo sistémico se mitiga en §5.5. |
| D7 | **Duplicado y trump avisan, no bloquean** (igual que el Resumen actual): los niveles `duplicado` y `peor` llegan **desmarcados** y avisados; el usuario puede marcarlos. | Evita subir 30 duplicados por un clic de más, sin impedir un re-subir legítimo. A confirmar (pregunta 3). |
| D8 | **Tope de 50 elementos por lote** (`MAX_ELEMENTOS_LOTE`, copia vigilada en el frontend). | Cada elemento = 1 hilo esperando en la puerta (ver §5.1); 50 es holgado y acotado. A confirmar (pregunta 2). |
| D9 | La **petición se enlaza solo desde el Panel** (`rec_request_id` por fila). Desde Biblioteca no se enlaza (igual que hoy). | Paridad con el asistente actual. A confirmar (pregunta 6). |

---

## 2. Modelo de datos y migración

**Esquema 51 → 52** en `emuwarez_uploadrr/database.py`:

- `SCHEMA_VERSION = 52` (línea ≈ 21).
- Nueva función `_migrate_upload_jobs_lote(conn)` copiando el patrón de `_migrate_upload_jobs_pasos_uploadrr` (≈ 1282): leer
  `PRAGMA table_info(upload_jobs)`; si falta `lote_id`, `ALTER TABLE upload_jobs ADD COLUMN lote_id TEXT` con el mismo
  `try/except sqlite3.OperationalError` que solo calla si la columna ya existe; después
  `CREATE INDEX IF NOT EXISTS idx_upload_jobs_lote ON upload_jobs(lote_id)`.
- Llamarla **al final de la cascada** de `init_db`, justo después de `_migrate_upload_jobs_pasos_uploadrr(conn)` (≈ línea 1881),
  antes de `set_state(conn, "schema_version", ...)`.
- Nullable, sin relleno: los trabajos viejos y los sueltos tienen `lote_id IS NULL` (la interfaz no pinta chip).
- No hace falta tocar `backup_service`, `maintenance_service`, `borrar_biblioteca` ni `demo_seed` (columna nueva anulable, no hay
  FK).

Definición de **punta de cadena** (la misma que `_find_latest_job_for_item`):

```sql
id NOT IN (SELECT retry_of_job_id FROM upload_jobs WHERE retry_of_job_id IS NOT NULL)
```

---

## 3. Backend por fichero

### `emuwarez_uploadrr/services/lotes.py` (NUEVO; `services/` no puede importar de `web/`)

Constantes y utilidades:
- `MAX_ELEMENTOS_LOTE = 50`
- `TIPOS_DE_LOTE = ("movie", "season", "episode")`
- `nuevo_lote_id() -> str` (`secrets.token_hex(6)`) y `lote_id_valido(valor) -> bool` (regex `^[0-9a-f]{12}$`).

Consultas (todo el SQL del lote vive aquí, por `test_web_no_habla_sql.py`):
- `_puntas(conn, lote_id) -> list[dict]`: filas del lote que son punta de cadena, orden `id ASC`.
- `resumen_de_lote(conn, lote_id) -> dict | None`: `{lote_id, total, en_cola, en_marcha (staging+preparing+running), completadas,
  fallidas, canceladas, creado, terminado (no queda nada activo), puede_cancelar, puede_reintentar}`. `None` si no hay filas. Solo
  BD: **nunca** llama a eMuwarez ni a qBittorrent.
- `contar_por_lote(conn, lote_ids) -> dict[str, int]`: una sola consulta `GROUP BY` para los `lote_id` de una página de la lista
  (alimenta el chip «Lote · N»).

Acciones (reutilizan lo que ya hay, así heredan todas sus carreras ya resueltas):
- `encolar_lote(conn, elementos) -> dict`: ver §3.2.
- `cancelar_lote(conn, lote_id, *, solo_pendientes=True) -> dict`: **primero** todos los `queued` (llamando a
  `upload_execution.cancel_upload_job` por id, que ya hace `escribir_estado(desde={"queued"})` + `retirar_de_la_cola`);
  **después**, solo si `solo_pendientes=False`, los `preparing` y `running`. El orden importa: si se cancelara antes un `running`,
  se liberaría plaza y un `queued` podría arrancar entre medias. Devuelve contadores `{canceladas, intactas}`.
- `reintentar_fallidas(conn, lote_id, *, desde_el_principio=False) -> dict`: para cada punta `failed|cancelled` en orden de id
  llama a `upload_queue.queue_retry_for_job(id, conn=conn, desde_el_principio=...)`; si devuelve `blocked` (p. ej.
  `trabajo_activo`) lo cuenta como saltado con su mensaje. El reintento hereda `lote_id` (§3.1), así que el lote sigue siendo el
  mismo y conserva el orden FIFO. Tras un reinicio de la aplicación (`reconcile_interrupted_jobs` marca como fallidos todos los
  activos) esto reanuda todo con un clic.

### 3.1 `services/upload_queue.py`

- `_insert_and_start_queued_job(...)` (≈ 93-208): parámetro nuevo `lote_id: str | None = None`; añadir `lote_id` a la lista de
  columnas del `INSERT` y **un `?` más** a los marcadores (hoy son 20; ojo al contarlos) y el valor a la tupla (≈ 163-189).
- `queue_upload_for_item(...)` (≈ 255-313): parámetro `lote_id: str | None = None`, pasado a `_insert_and_start_queued_job`. No
  hereda del último trabajo del elemento (decisión D5).
- `queue_retry_for_job(...)` (≈ 357-373): pasar `lote_id=original.get("lote_id")`.
- `upload_execution/ciclo_de_vida.py::retry_upload_job` (camino heredado `/uploads/{id}/retry`, INSERT ≈ 110-133): copiar también
  `lote_id` del original (una línea) para que ese camino no saque al elemento del lote.
- No se toca `_run_queued_job`, `PASOS`, la puerta ni `reconcile_interrupted_jobs`.

### 3.2 `encolar_lote` (en `services/lotes.py`)

Entrada: lista de elementos `{item_id, request_item_id?, checks?, campos?, provider?}` en el orden que el usuario quiera que se
suban (el orden de inserción es el orden de id, que es el de la puerta).

Algoritmo:
1. Validar `1 <= len(elementos) <= MAX_ELEMENTOS_LOTE` (si no, lanzar `ValueError`; el endpoint lo traduce a 422/400).
2. `lote_id = nuevo_lote_id()`. Para cada elemento, **dentro de un `try/except Exception` por elemento** (un fallo inesperado se
   apunta con `logger.exception` y se devuelve como `blocked`, nunca aborta el resto):
   - Repetido en el cuerpo → `blocked: "Repetido en el lote."`.
   - Elemento inexistente → `blocked` (lo da `queue_upload_for_item`).
   - `item_type` fuera de `TIPOS_DE_LOTE` (una serie) → `blocked: "Elige sus temporadas."`.
   - Si trae `campos` (solo película/capítulo, y solo cuando la interfaz sugirió proveedor): guardarlos igual que
     `POST /library/{id}/nomenclature/save-fields`: `source_assistant.update_nomenclature_fields_preview(item_id, campos,
     conn=conn)` + `nomenclature.save_manual_nomenclature_fields(item_id, campos, preview, conn=conn)`. Así el trabajo fija esa
     propuesta (paridad con el asistente suelto, que siempre guarda).
   - `queue_upload_for_item(item_id, request_item_id=..., checks=..., provider_override=el.provider, lote_id=lote_id, conn=conn)`.
     Si devuelve `status == "blocked"` (p. ej. «Ya hay una subida en curso para este contenido.») se anota y se sigue.
3. Si no se encoló ninguno, `lote_id` de la respuesta es `None` (no queda lote fantasma).
4. Devuelve `{lote_id, encolados, saltados, resultados: [{item_id, status: "queued"|"blocked", job_id, errors}]}`.

No hace falta `eventos.publicar` aquí: cada alta pasa por `_insert_and_start_queued_job` (que ya publica `subida-estado`) y cada
cambio por `escribir_estado` (regla de CLAUDE.md: se publica desde el único sitio que escribe). El doble clic en «Subir» queda
protegido por `trabajo_activo`: la segunda llamada saltará todos los elementos.

No re-ejecuta las comprobaciones de contenido en el servidor: `_paso_comprobar` / `_populate_ready` ya las rehacen al correr cada
trabajo (y repetir `build_season_pack_plan` en la petición sería caro).

### 3.3 `services/upload_execution/consultas.py`

- `_upload_jobs_where(filters)` (≈ 38): añadir `lote_id = ?` cuando `filters.get("lote_id")`. `count_upload_jobs` lo hereda.
- Nada más (`list_upload_jobs` no cambia).

### 3.4 `web/schemas.py`

- `UploadQueueBody` (≈ 1415-1444): `lote_id: Optional[str] = None` con patrón `^[0-9a-f]{12}$` (para las tandas actuales del
  asistente).
- `UploadJobDetail` (≈ 1173-1243): `lote_id: Optional[str] = None`, `lote_total: Optional[int] = None`.
- Nuevos modelos: `UploadLoteElemento` (`item_id: int`, `request_item_id: Optional[int]`, `checks: Optional[UploadChecksSnapshot]`,
  `campos: Optional[Dict[str, Any]]`, `provider: Optional[str]`), `UploadLoteBody` (`elementos: list[UploadLoteElemento]` con
  `min_length=1`, `max_length=50`), `UploadLoteResultado`, `UploadLoteResponse`, `LoteResumen`, `LoteAccionBody`
  (`solo_pendientes: bool = True`, `desde_el_principio: bool = False`).

### 3.5 `web/api/uploads.py` (sin SQL: guardia `test_web_no_habla_sql`)

- `queue_upload` (≈ 291): pasar `lote_id=body.lote_id` a `queue_upload_for_item` (validado con `lote_id_valido`; 422 si no
  cumple).
- `_job_to_detail` / `_con_ficha` (≈ 114-206): nuevos kwargs `lote_id`, `lote_total` hacia `UploadJobDetail`.
- `get_uploads` (≈ 330): query param `lote_id: str | None = Query(None, pattern=...)` en `filters`; tras `exec_list_jobs`, **una**
  llamada `lotes.contar_por_lote(conn, {j["lote_id"] for j in jobs if j.get("lote_id")})` y pasar `lote_total` a cada
  `_con_ficha`. `count_uploads` (≈ 367): mismo filtro.
- `get_upload` (≈ 388): rellenar `lote_total` de ese trabajo.
- Rutas nuevas, declaradas **antes** de `/uploads/{job_id}` (mismo motivo que el comentario de `/uploads/count`):
  - `POST /uploads/lote` → `lotes.encolar_lote`.
  - `GET /uploads/lotes/{lote_id}` → `lotes.resumen_de_lote` (404 si `None`).
  - `POST /uploads/lotes/{lote_id}/cancelar` (`solo_pendientes`).
  - `POST /uploads/lotes/{lote_id}/reintentar` (`desde_el_principio`).
- Todas con `Depends(require_auth)` y `_get_conn()` como el resto.

---

## 4. Frontend por fichero

### Utilidades, API y tipos
- `src/utils/lote.ts` (NUEVO): `MAX_ELEMENTOS_LOTE = 50` (copia del backend, vigilada), `nuevoLoteId()` (12 hex con
  `crypto.getRandomValues`, con respaldo para jsdom), tipos `ElementoDeLote`, `FilaLote`, y funciones puras:
  `expandirSeleccion(...)` (serie → temporadas aptas, usando `isSeasonReady` / `seasonNotReadyReason`), `razonNoSubible(item)`
  (película/capítulo: reutilizar la lógica de `episodeNotReadyReason` de `utils/libraryItem.ts`, que mira `local_status` y
  `has_spanish_ok`; renombrarla o añadir un alias `archivoNoListoRazon` sin romper sus usos), `marcadaPorDefecto(nivelDuplicado)`
  (desmarca `duplicado` y `peor`), `duplicadoEnElLote(filas)` (misma `tmdb_id` y resolución dos veces: dos instancias con la misma
  película acabarían con el mismo nombre y el segundo trabajo fallaría con «es de la subida #N»).
- `src/api/uploads.ts`: `queueUpload(...)` recibe un **7.º parámetro** opcional `loteId` (los 6 actuales no se mueven: los tests
  miran `mock.calls[0][4]` y `[5]`); nuevas `queueLote`, `getLote`, `cancelarLote`, `reintentarLote`; `UploadsQuery.lote_id` y su
  serialización en `uploadsQueryString`.
- `src/types/api.ts`: `UploadJob.lote_id?`, `lote_total?`; tipos de las respuestas del lote.

### Selección
- `src/hooks/useSeleccionLote.ts` (NUEVO): `Map<number, LibraryItemResponse>` (se guarda el objeto, no solo el id, porque una fila
  filtrada o recargada puede desaparecer de la lista), `alternar`, `limpiar`, `tiene`, tope `MAX_ELEMENTOS_LOTE`.
- `src/components/lote/BarraLote.tsx` (NUEVO): barra fija inferior «N seleccionados · Subir por lotes · Limpiar». Reutilizable
  por Biblioteca y Panel.
- `src/components/lote/CasillaLote.tsx` (NUEVO): `<input type="checkbox">` con `aria-label="Seleccionar «Título»"`;
  `stopPropagation` para que no abra la ficha.

### Modal
- `src/components/lote/SubidaPorLotesModal.tsx` + `useLote.ts` + `PasoContenidoLote.tsx` + `PasoResumenLote.tsx` (NUEVOS).
  Stepper de dos pasos con las clases `asist-paso*` ya existentes («1 · Contenido», «2 · Resumen»).
  - **Entrada**: `elementos: { item: LibraryItemResponse; requestId?: number; alcance?: { season?: number | null; episode?:
    number | null } }[]`, `onClose`, `onDone`, `onNavigate`.
  - **Paso 1 «Contenido»**: expande cada serie con `getLibrary({ parent_id, type: 'season', limit: 500 })` (como `useAsistente`
    ≈ 257; si trae `alcance.season`, solo esa temporada). Lista de filas con casilla, tipo, motivo si no es subible (desmarcada y
    deshabilitada, con la razón de arriba), aviso de repetido, total y el tope de 50. «Continuar (N)».
  - **Paso 2 «Resumen»**:
    - Reutiliza `useComprobacionesTanda({ step: 2, batchQueue: idsDelPaso1, batchPhase, proveedorElegido: new Map() })` para el
      entorno (una vez) y el contenido (uno a uno, con «Comprobando 7 de 40…»). Pasar la cola completa del paso 1 y manejar
      marcar/desmarcar localmente: si la longitud de `batchQueue` cambiara se relanzaría el efecto (aunque `sigueValiendo`
      conserva lo ya comprobado).
    - Efecto propio, secuencial por elemento: `getNomenclatureFields(id)` solo en película/capítulo (nombre del torrent y
      `blocked`; si WEB-DL sin proveedor, `suggestProvider(id)` y se guardan los `campos` para enviarlos), y
      `getEmuComparison(id)` → `resumirComparaciones([c])` → `conclusionDuplicados(filas)` para el veredicto por elemento. Para
      temporadas, el nombre sale del `season_pack` del check de contenido; si no hay nombre, se pone «Pack de temporada» (mejora
      opcional: devolver `nombre` desde `run_upload_checks`, compatible hacia atrás).
    - Tabla por elemento: título, tipo, nombre del torrent, comprobación (✓/✗ + mensaje), «En eMuwarez» (frase de
      `conclusionDuplicados`), casilla «Incluir». Falla comprobación de contenido, nomenclatura bloqueada o sin castellano →
      desmarcada, deshabilitada y con su motivo («Se saltará»). Entorno fallido → no se puede subir (igual que `PasoSubidaTanda`).
    - Texto fijo: «Se subirán de N en N según “Subidas en paralelo” (ahora: X)». X sale de
      `fetchSettings().upload_max_concurrent` (ya lo usa `useAsistente`).
    - «Subir N»: `queueLote({ elementos })` con, por elemento, `request_item_id`, `checks: mergedChecksFor(id)`, `campos` si
      procede y `provider` si lo sugirió. Resultado: «N de M encolados» + lista de saltados con su motivo + «Ver el lote en
      Subidas» (handoff por `sessionStorage` `emuwarez_open_lote`, el mismo patrón que `emuwarez_open_upload`, y
      `onNavigate('uploads')`).
  - Cierre: se bloquea mientras la petición está en vuelo (como `ocupado` en el asistente).
- `src/styles/lote.css` (NUEVO, importado en `main.tsx` junto a `asistente.css`/`subidas.css`): clases `lote-*`. Sin estilos en
  línea (el repo los lleva a clases).

### Pantallas
- `src/pages/LibraryPage.tsx`: `useSeleccionLote()` en el componente; `<BarraLote>`; `<SubidaPorLotesModal>` dentro de `modals`
  (≈ 532). Limpiar la selección en `useAlSalir` (≈ 386) y en `onDone`. **Lo seleccionable**: películas, series y temporadas (no
  capítulos).
  - Lista: `LibraryTreeRow.tsx` — la casilla va **dentro de la celda Título**, no como columna nueva (`LIST_COLUMNS = 13` se usa
    en el esqueleto, `FilaVacia` y `FilasVirtuales`; añadir una columna obliga a tocar los tres).
  - Pósters y pósters grandes: `PosterCard` (en el propio `LibraryPage.tsx`, ≈ 70, memoizado) y `LargePosterCard.tsx` reciben
    `seleccionado` y `onToggle` estables. La casilla va en `position: absolute` dentro del marco del póster y **no puede cambiar
    el alto de la tarjeta** (la rejilla mide la primera tarjeta; ver PLAN.md «vista de pósters en negro»).
- `src/pages/DashboardPage.tsx` + `components/hoy/CarrilListo.tsx`: casilla en cada `Fila` de peticiones, contenido único y
  mejoras (no en faltantes). Estado `Map<clave, DashboardRecommendationItem>` con clave
  `${rec_request_id ?? 'u'}-${library_target_id ?? id}`. Barra «Subir seleccionadas (N)» al pie del carril. Al abrir:
  `getLibraryItem(item.library_target_id ?? item.id)` por fila, con `requestId = item.rec_request_id` y
  `alcance = { season, episode }` como hace `abrir()` (≈ 218-236).
- `components/hoy/CarrilEnCurso.tsx`: tope de filas vivas visibles (p. ej. 6: las que están subiendo/preparando y las primeras en
  cola) más una línea «+N en cola · Ver todas las subidas». `notaEnCurso` ya resume «N subiendo · M en cola».
- `src/pages/UploadsPage.tsx`:
  - Chip «Lote · N» en `JobRow` (junto al título, ≈ 186-203) cuando `job.lote_id`; al pulsarlo fija `loteFiltro`.
  - `load()` (≈ 355) pasa `lote_id` a `getUploads`/`countUploads`; `loteFiltro` se reinicia en `quitarFiltros` y `useAlSalir`.
  - Con `loteFiltro`, banner sobre la tabla alimentado por `getLote`: contadores (en cola, en marcha, completadas, fallidas,
    canceladas), «Cancelar pendientes», «Reintentar fallidas», «Quitar filtro». La recarga del resumen va dentro del `load` que
    ya dispara `useRefrescoPorAvisos(AVISOS_SUBIDA, ...)`: **ningún sondeo nuevo**.
  - Modal de confirmación de cancelar, con casilla «Parar también las que ya se están preparando o subiendo» (reutiliza el texto
    del modal de cancelar en preparación).
  - Recoger `emuwarez_open_lote` del `sessionStorage` en el mismo efecto que recoge `emuwarez_open_upload` (≈ 390-397).
- `src/components/UploadJobDetailPage.tsx`: línea «Parte de un lote de N · Ver el lote» (usa el mismo handoff).
- `src/components/asistente/useAsistente.ts` (solo PR 1): `uploadAllSeasons` (≈ 908) y `uploadAllEpisodes` (≈ 960) generan **un**
  `nuevoLoteId()` al empezar y lo pasan como 7.º argumento de cada `queueUpload`, **solo si la tanda tiene más de un elemento**
  (siempre lo es en esas dos rutas, porque `esTanda` exige ids > 1).

---

## 5. Interacción con concurrencia, cancelación, reintentos y comprobaciones

### 5.1 Concurrencia y la puerta

- Un lote de N crea **N filas `queued` y N hilos** que esperan en `_UploadConcurrencyGate.acquire`. Con «Subidas en paralelo» = 1
  (defecto) suben de uno en uno, **en el orden del lote** (ids consecutivos). No se toca ese comportamiento.
- Coste a vigilar: cada hilo que espera llama a `_limite_de_subidas()` (abre una conexión SQLite, lee `uploads.max_concurrent`) en
  cada vuelta, y cada `release`/`retirar`/salida de un hilo hace `notify_all`, que despierta a **todos**. Con 50 hilos son decenas
  de lecturas por evento, aceptable en SQLite local pero no gratis. Por eso el tope de 50. Si en la práctica molesta, la mejora
  (opcional, PR 7) es cachear la lectura del límite ~1 s dentro de la puerta (conserva la semántica «el cambio de ajuste se nota
  al momento» a un segundo de resolución). **No** conviene un despachador que lance hilos de uno en uno: `retirar_de_la_cola` y
  `trabajo_activo` dependen de que el hilo exista en `_EN_CURSO`.
- Un lote no cambia el límite ni lo sugiere. La interfaz solo lo **dice** («Se subirán de N en N según “Subidas en paralelo”»).
- **Justicia**: la puerta es FIFO por id, así que una subida suelta lanzada después de un lote de 40 espera a que terminen o se
  cancelen las pendientes. Se acepta en v1 (pregunta 2).
- Recursos compartidos que ya soportan trabajos en paralelo y no cambian: `ENLACES` (candado de enlaces), el `config.yaml`
  compartido de Uploadrr-EMU (`_acquire_staged_config`, cubierto por `test_parallel_config_staging.py`).

### 5.2 Cancelación

- `cancelar_lote` cancela **primero los `queued`** (salen de la puerta al instante vía `retirar_de_la_cola`) y, solo si el usuario
  lo pide, después `preparing` y `running`. Cancelar un `running` primero liberaría una plaza que un `queued` podría tomar antes de
  ser cancelado.
- Cada cancelación pasa por `cancel_upload_job`, así que heredan sus guardas (`escribir_estado(desde={"queued"})`, recursión si el
  estado cambió entre lectura y escritura, SIGTERM al grupo, `preparing` que se detiene en el siguiente punto limpio).
- Cancelar un solo elemento desde su fila sigue funcionando igual y no afecta al lote.

### 5.3 Reintentos

- «Reintentar fallidas» recorre las puntas `failed|cancelled` por id y reencola con `queue_retry_for_job` (reanuda desde el paso
  que falló si se puede). Cada reintento hereda el `lote_id`, la petición y la nomenclatura fijada.
- Tras un reinicio de la app, `reconcile_interrupted_jobs` marca como fallidos **todos** los activos (también los `queued` que
  nunca empezaron); «Reintentar fallidas» es entonces la forma natural de retomar el lote.
- Un elemento con trabajo activo no se reintenta (`trabajo_activo` → `blocked`, se cuenta como saltado).

### 5.4 Comprobaciones previas y qué hace el lote cuando un elemento no pasa

| Comprobación | Dónde | Efecto en el lote |
|---|---|---|
| Contenido accesible, carpeta de subida, pack posible, sin castellano (`run_upload_checks` scope `content`) | Paso 2, por elemento | Fila desmarcada, deshabilitada y con motivo; **se salta**, el resto sigue. |
| Entorno (directorio de salida, qBittorrent, hosts de imágenes, eMuwarez; scope `environment`) | Paso 2, **una vez** | Si falla, no se puede subir nada (igual que `PasoSubidaTanda`); «Volver a comprobar». |
| Nomenclatura bloqueada | Paso 2 (`getNomenclatureFields(...).blocked` en película/capítulo; pack: el plan del check `season_pack`) y de nuevo al correr el trabajo (`_check_generic_upload_preconditions`, `_paso_nombre`) | Salto en el paso 2; si aun así llega al servidor, ese trabajo falla con su motivo y los demás siguen. |
| Duplicado / trump contra el catálogo local | Paso 2 (`getEmuComparison` → `conclusionDuplicados`; SQL local, sin red) | Aviso por elemento; `duplicado` y `peor` llegan desmarcados; nunca bloquea. |
| Trabajo activo del mismo contenido | `queue_upload_for_item` (`trabajo_activo`) | Elemento saltado en la respuesta («Ya hay una subida en curso»). |
| Mismo contenido dos veces en el lote (dos instancias) | Paso 1 (`duplicadoEnElLote`) y servidor («Repetido en el lote.») | Aviso y/o salto. |
| Claves, `uploadrr.path`, `allowed_roots`, integridad | Servidor, al correr cada trabajo | Ese trabajo falla (`failed` con motivo); no afecta a los demás. |
| Duplicado detectado por el propio Uploadrr-EMU | Al ejecutar | Sale como fallo genérico con el resumen de error; no hay parseo específico hoy. |

### 5.5 Qué hace el lote cuando un elemento falla

Sigue con los demás (D6). Un fallo **sistémico** (eMuwarez caído, qBittorrent mal, clave inválida) haría fallar los N seguidos y
generaría N notificaciones; la mitigación de v1 es la comprobación de **entorno una vez antes de subir** y que «Reintentar
fallidas» recupere todo. Un freno automático («parar tras X fallos seguidos con el mismo motivo») y la notificación agregada
quedan como decisión de Gabriel (preguntas 4 y 5).

### 5.6 Límite de ~28/min a eMuwarez

- La app añade como mucho **1 llamada por lote** (el entorno), por el limitador compartido.
- `getEmuComparison`, `resumen_de_lote`, `contar_por_lote` y la lista de Subidas **solo leen BD local**. Prohibido pedir
  `tracker-stats` por fila en la vista del lote (es una llamada a eMuwarez por subida; el PLAN la limita a abrir un detalle).
- Las llamadas de Uploadrr-EMU (búsqueda de duplicados, subida, descarga del torrent) **no pasan por el limitador**. Con «Subidas
  en paralelo» = 1 no hay problema; con 5-10 y un lote de películas cortas se multiplican contra una clave que comparten Sonarr,
  Radarr y qui. **El lote no sube el límite ni lo recomienda.**
- La sugerencia de proveedor por TMDb (`suggestProvider`) es TMDb, no eMuwarez, y solo se pide para WEB-DL sin proveedor en el
  nombre.

---

## 6. Estrategia de PRs (orden, el más barato primero; cada uno verde por separado)

Rama `feat/lotes-N-…`, PR no borrador (CodeRabbit). Cada PR actualiza `docs/PLAN.md` («Hecho» y tachar «subida por lotes» solo en
el último) y no sube la versión. Los PR de solo `frontend/`/`docs/` en CI ejecutan los tests cuyo nombre de fichero contiene
`frontend`: cualquier test nuevo que lea ficheros del frontend debe llevar esa palabra en su nombre.

### PR 1 — «Las tandas del asistente quedan agrupadas como lote en Subidas» (backend + frontend, pequeño)
- Migración 52, `lote_id` en `_insert_and_start_queued_job` / `queue_upload_for_item` / `queue_retry_for_job` /
  `retry_upload_job`, filtro `lote_id` en `_upload_jobs_where`, `UploadQueueBody.lote_id`, `UploadJobDetail.lote_id/lote_total`,
  `services/lotes.py` con `nuevo_lote_id`, `lote_id_valido`, `contar_por_lote`, `resumen_de_lote`; `GET /uploads/lotes/{id}`.
- Frontend: `utils/lote.ts` (`nuevoLoteId`), 7.º parámetro de `queueUpload`, las dos tandas de `useAsistente`, chip y filtro en
  `UploadsPage`, banner de contadores (sin acciones).
- **Aceptación**: (a) subir 2 temporadas o 3 capítulos desde el asistente crea trabajos con el mismo `lote_id`; (b) Subidas
  enseña «Lote · N» y al pulsarlo filtra y muestra contadores; (c) una subida suelta no lleva chip; (d) migrar una BD de esquema
  51 conserva todo; (e) los tests actuales del asistente siguen en verde sin cambiar sus asserts (`mock.calls[0][4]`/`[5]`);
  (f) un reintento conserva el lote.

### PR 2 — «Cancelar pendientes y reintentar fallidas de un lote» (backend + frontend)
- `cancelar_lote`, `reintentar_fallidas`, rutas `POST /uploads/lotes/{id}/cancelar|reintentar`; botones y modal de confirmación
  en el banner de `UploadsPage`.
- **Aceptación**: con la puerta a 1 y un lote de 3 (uno `running`), «Cancelar pendientes» deja el `running` intacto y cancela los
  otros dos sin que ninguno arranque; con la casilla «también lo que ya está en marcha» cancela los tres en ese orden;
  «Reintentar fallidas» crea trabajos nuevos con el mismo `lote_id`, en orden de id, saltando los que tengan trabajo activo; tras
  `reconcile_interrupted_jobs` recupera todo.

### PR 3 — Endpoint `POST /uploads/lote` (solo backend)
- `encolar_lote`, modelos de `schemas.py`, ruta. Sin interfaz.
- **Aceptación**: devuelve `lote_id` + resultados por elemento en el orden dado; un elemento inexistente, repetido, de tipo serie
  o con trabajo activo sale `blocked` sin tumbar los demás; más de 50 → 422; ninguno encolado → `lote_id: null`; cada elemento
  lleva `request_item_id`, `checks` y `provider` a su trabajo; con `campos` guarda la propuesta manual como `save-fields`.

### PR 4 — Biblioteca: selección de **películas** + modal «Subir por lotes» (frontend)
- `useSeleccionLote`, `BarraLote`, `CasillaLote`, `SubidaPorLotesModal` (paso 1 + paso 2 con películas), `queueLote`,
  integración en `LibraryPage`, `LibraryTreeRow`, `PosterCard`, `LargePosterCard`, `lote.css`, tope de filas en `CarrilEnCurso`.
- **Aceptación**: marcar películas en las tres vistas (lista, pósters, pósters grandes); la selección sobrevive a cambiar de
  filtro y de vista y se limpia al salir de Biblioteca; el Resumen lista nombre y veredicto por película; una película sin
  castellano o con nomenclatura bloqueada sale saltada con motivo; «Subir» crea el lote y lleva a Subidas filtrado por él; el
  Panel no se llena (tope «+N en cola»); la rejilla no vuelve a oscilar (comprobar a mano con 200 selecciones).

### PR 5 — Series y temporadas en el lote (frontend, quizá un cambio pequeño en backend)
- Expansión de series a temporadas en el paso 1, packs en el paso 2 (progreso por temporada, motivos de `seasonNotReadyReason` y
  del check `season_pack`), opcionalmente `nombre` en la respuesta de `run_upload_checks`.
- **Aceptación**: marcar 2 series con 3 y 2 temporadas aptas → el paso 1 muestra 5 filas marcadas y las no aptas desmarcadas con
  su motivo; un lote mixto película + temporada funciona; el tope de 50 cuenta tras expandir.

### PR 6 — Panel: selección en «Listo para subir» (frontend)
- Casillas en `CarrilListo` y barra «Subir seleccionadas (N)»; petición enlazada por fila (`rec_request_id`), capítulos sueltos
  cuando la petición lo es.
- **Aceptación**: los trabajos creados llevan su `request_item_id` y Subidas enseña la petición de cada uno; una petición de
  capítulo sube ese capítulo; «Otras ideas» entra sin petición.

### PR 7 (opcional, cada punto por separado y solo si Gabriel lo quiere)
- Notificación agregada del lote (`upload_batch_done`, silenciar el envío externo de los trabajos de un lote): toca
  `notification_center.EVENT_TYPES`, ajustes de notificaciones y sus tests.
- Unificar las tandas del asistente con `POST /uploads/lote` (obliga a reescribir los asserts de `UploadWizardModal.test.tsx`
  líneas ≈ 387-456 y ≈ 595-720).
- Selección en la página de Peticiones.
- Caché de ~1 s de la lectura del límite en la puerta.

---

## 7. Tests a añadir y guardas que hay que vigilar

### Backend (pytest; usar el fixture `db_conn`, `isolated_db`, `client`, `auth_headers`, y para hilos reales `subidas_reales` + el fixture `puerta` de `tests/test_subida_sin_espera.py`; el `_subidas_sin_hilo` autouse de `conftest.py` desactiva `_lanzar_trabajo` salvo que se pida `subidas_reales`)
- `tests/test_lotes.py` (NUEVO):
  - Migración: columna e índice presentes; BD de esquema 51 migra; la columna sobrevive al cortocircuito de esquema (patrones de
    `test_subida_pasos_uploadrr.py` líneas ≈ 112-122 y
    `test_upload_queue.py::test_season_overrides_column_survives_schema_version_short_circuit`).
  - `queue_upload_for_item(lote_id=…)` persiste; sin lote queda `NULL`; `queue_retry_for_job` y `retry_upload_job` heredan.
  - `resumen_de_lote` cuenta solo **puntas de cadena** (un reintento no duplica el elemento); `contar_por_lote` agrupa; lote
    inexistente → `None`.
  - `encolar_lote`: orden de ids = orden de la lista; elemento inexistente / repetido / serie / con trabajo activo / excepción
    inesperada simulada → `blocked` sin abortar; >50 → error; ninguno encolado → `lote_id None`; `campos` guarda la propuesta;
    segunda llamada idéntica (doble clic) salta todos.
  - `cancelar_lote`: con la puerta a 1, el `queued` sale de la cola antes de tocar al `running`; `solo_pendientes=False` cancela
    todos y en ese orden; ningún `queued` arranca durante la cancelación.
  - `reintentar_fallidas`: orden por id, hereda lote, salta activos, reanuda tras `reconcile_interrupted_jobs`.
  - Filtro `lote_id` en `list_upload_jobs` y `count_upload_jobs`.
- `tests/test_lotes_api.py` (NUEVO): 401 sin token; 422 con `lote_id` mal formado; `POST /uploads/lote` y las rutas de
  resumen/cancelar/reintentar; la ruta `/uploads/lotes/...` no la captura `/uploads/{job_id}`; `GET /uploads?lote_id=…` y
  `lote_total` en la lista.
- Ajustar sin romper: `tests/test_upload_queue.py` (la firma de `_insert_and_start_queued_job` gana un parámetro opcional) y
  `tests/test_marca_registro_y_listado_de_subidas.py` (la lista gana campos).
- Cobertura: `codecov/patch` ≥ 70 % sobre las líneas cambiadas de `emuwarez_uploadrr/` (los PR 1-3 son casi todo backend, así que
  hay que cubrir `lotes.py` entero).

### Frontend (vitest; usar `components/__tests__/dom.ts`)
- `utils/__tests__/lote.test.ts`: `expandirSeleccion`, `razonNoSubible`, `marcadaPorDefecto`, `duplicadoEnElLote`, `nuevoLoteId`
  (formato).
- `components/__tests__/SubidaPorLotesModal.test.tsx`: película marcada/no apta; paso 2 con comprobaciones y entorno una vez
  (`runUploadChecks` llamado con `'environment'` una sola vez); nomenclatura bloqueada → saltada; `conclusionDuplicados` por fila;
  «Subir» llama a `queueLote` con el orden y los `checks`; resultado parcial lista los saltados; «Ver el lote» navega a Subidas.
- `components/__tests__/UploadWizardModal.test.tsx`: añadir que las dos tandas pasan el mismo `lote_id` (7.º argumento) y que una
  subida suelta no lo pasa.
- Selección: `useSeleccionLote` (tope, persistencia entre filtros) y que la casilla de la lista no abre la ficha.
- `pages/__tests__/` (UploadsPage no tiene test hoy): chip, filtro por lote y banner (nuevo `UploadsPage.test.tsx`).

### Guardas de CLAUDE.md que se pueden romper
- `test_web_no_habla_sql.py`: ningún `SELECT/INSERT/UPDATE/DELETE` en `web/api/uploads.py`; todo en `services/lotes.py` y
  `consultas.py`.
- `test_una_sola_puerta_a_settings.py`: `lotes.py` no consulta la tabla `settings`; el límite de paralelo se lee solo con
  `get_upload_max_concurrent` (y el frontend por `fetchSettings`).
- `services/` nunca importa de `web/`: los modelos Pydantic viven en `web/schemas.py`, `lotes.py` trabaja con diccionarios.
- `test_copias_frontend.py`: añadir un caso que compare `MAX_ELEMENTOS_LOTE` de `utils/lote.ts` con `services/lotes.py` (patrón
  `_texto("utils/lote.ts")` + regex). **No se añade ningún estado ni fase nuevos**, así que los casos de vocabulario de estados y
  fases no cambian.
- `test_eventos_fases_3_y_4.py::test_no_han_aparecido_sondeos_nuevos`: no escribir `setInterval` en ficheros nuevos; el refresco
  del lote usa `useRefrescoPorAvisos(AVISOS_SUBIDA, …)`. No se añaden tipos de evento (`test_eventos*.py` quedan igual).
- Migración: subir `SCHEMA_VERSION` y llamar a `_migrate_upload_jobs_lote` al final de la cascada (`preparar_base` hace la copia
  previa); `test_base_al_arrancar.py` usa `SCHEMA_VERSION - 1` y no necesita cambios.
- `ruff --select E9,F`: sin imports ni variables sin usar; `npm run lint` vigila lo equivalente en TS (cuidado al renombrar o
  poner alias a `episodeNotReadyReason`).
- Texto de interfaz en español; sin estilos en línea (clases en `lote.css`); sin `console.log`.
- `test_iconos_frontend.py`: si se añaden iconos, que salgan de `Iconos.tsx`/`DetailCard.tsx` como el resto.

---

## 8. Riesgos y preguntas abiertas para Gabriel (por impacto)

### Preguntas (solo él puede decidir)

1. **¿Vale un lote sin edición por elemento?** (nombres automáticos; solo se sugiere proveedor a los WEB-DL sin proveedor; editar
   = subir suelto). Es la decisión que más condiciona el coste y la calidad de los nombres. Recomendación: sí en v1, con el
   Resumen listando el nombre de cada torrent. Si la respuesta es no, hay que generalizar `useAsistente` (colas heterogéneas,
   `sharedTitle` por serie, etc.), que es un proyecto aparte.
2. **Concurrencia y justicia**: ¿el lote respeta «Subidas en paralelo» tal cual (recomendado) o quieres un «lote de baja
   prioridad» para que una subida suelta lanzada después no espere a las 40 del lote? Y, ¿50 es buen tope?
3. **Duplicados y trumps**: ¿llegan desmarcados `duplicado` y `peor` (propuesto), o todos marcados y solo avisados?
4. **Fallo sistémico**: ¿seguir siempre con el resto (propuesto) o parar el lote tras X fallos seguidos con el mismo motivo? Hoy
   40 fallos seguidos son 40 notificaciones.
5. **Notificaciones**: ¿una sola por lote (campana y Discord/Telegram) en lugar de una por subida? Requiere un tipo de evento
   nuevo (`upload_batch_done`) y tocar Ajustes → Notificaciones.
6. **Petición desde Biblioteca**: hoy una subida desde Biblioteca nunca enlaza petición. ¿En un lote, enlazar la petición abierta
   de cada elemento si existe?
7. **Biblioteca y el rediseño P2**: ¿el lote antes o después de P2? Si es antes, las casillas se hacen en componentes sueltos
   (`CasillaLote`, `BarraLote`) para que P2 las recoloque; ¿casillas siempre visibles o un modo «Seleccionar»?
8. **Alcance de las series**: ¿vale «solo packs de temporada aptos» y mandar a subir suelto lo demás, o quieres capítulos sueltos
   de las temporadas no aptas dentro del lote?
9. **Peticiones**: ¿añadir la selección también a la página de Peticiones (un PR más pequeño sobre el mismo modal)?
10. **Ciclo de vida del lote**: ¿«Borrar lote» desde Subidas (borrar todas las cadenas terminadas)? Hoy se borra de una en una.
11. **Unificar las tandas actuales** con el endpoint nuevo: mejora la coherencia pero obliga a reescribir ~6 tests del asistente.

### Riesgos técnicos

- **Hilos y lecturas de BD en espera**: 50 hilos esperando, cada uno leyendo el ajuste cada ≤3 s y con `notify_all` frecuentes
  (ver §5.1). Aceptable con el tope; medir con 50 trabajos falsos antes de subir el tope.
- **Reinicio a mitad de lote**: `reconcile_interrupted_jobs` deja todo `failed` («Interrumpido…»); «Reintentar fallidas» lo cura,
  pero el usuario ve de golpe N fallidas y N notificaciones.
- **Subidas muy largas encadenadas**: un lote de 40 con paralelo 1 puede tardar horas; no hay barra de progreso global (solo
  contadores). Fuera de alcance.
- **Disco**: cada trabajo prepara enlaces duros o copias por reflink en la carpeta de subidas; con paralelo > 1 y remux activo hay
  varias copias/escrituras a la vez. Conviene probarlo en el NAS.
- **Limitador de eMuwarez no cubre a Uploadrr-EMU** (ver §5.6). El riesgo real es subir «Subidas en paralelo» con lotes grandes.
- **La rejilla de pósters**: la casilla no puede alterar la medida de la tarjeta (bug previo de React 185). Comprobar en `:edge`
  con 200 selecciones.
- **Selección obsoleta**: una sincronización puede borrar un elemento mientras el modal está abierto; el servidor devuelve ese
  elemento como `blocked` y el lote sigue.
- **Dos instancias con la misma película** (4K y 1080p en Radarr distintos) acaban con el mismo nombre y el segundo trabajo falla
  con «es de la subida #N» (`_paso_preparar`). Se avisa en el paso 1; el servidor no lo impide.
- **`useComprobacionesTanda` reutilizado**: su efecto depende de `batchQueue.length`; hay que pasarle la cola estable del paso 1 y
  manejar las casillas del paso 2 por separado, o relanzará la pasada (barata gracias a `sigueValiendo`, pero inesperada).
- **No verificado**: no se ejecutó la suite ni se abrió la interfaz; el comportamiento de Uploadrr-EMU ante un duplicado real y el
  coste de 50 hilos en el NAS requieren una prueba manual antes de dar el lote por bueno.

---

### Ficheros críticos para la implementación
- `emuwarez_uploadrr/services/upload_queue.py`
- `emuwarez_uploadrr/web/api/uploads.py`
- `emuwarez_uploadrr/database.py`
- `frontend/src/components/asistente/useAsistente.ts`
- `frontend/src/pages/UploadsPage.tsx`
