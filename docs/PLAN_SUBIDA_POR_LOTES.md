# Plan de implementación: «Subida por lotes»

Documento autosuficiente para quien lo ejecute. Primera versión hecha leyendo `master` en `b934813` (04/11/2026), sin
ejecutar nada. **Revisado el mismo día contra `adef702`** (después de #207 y #208, que cambiaron Biblioteca y Peticiones) con
cinco revisiones en paralelo (cola y BD, endpoint y comprobaciones, Biblioteca y Panel, modal y Subidas, tests y CI); lo que
cambió está en §9. Los números de línea son aproximados (≈). Pendiente de que Gabriel responda las preguntas de §8; la
recomendación va en cada una. Al terminar cada PR, actualiza `docs/PLAN.md` (ver «Cómo se trabaja» allí).

---

## 0. Lo que hay hoy (hallazgos que condicionan el diseño)

1. **No existe selección múltiple en Biblioteca ni en Peticiones.** `LibraryPage.tsx` solo tiene `selected` (una ficha abierta) y
   `wizardItem` (un elemento). `RequestsPage.tsx` abre el asistente con un `libraryItemId` (`openUpload(libraryItemId, preselect,
   requestId)`, ≈ 652). El Panel tiene un botón «Subir» por fila (`CarrilListo.tsx`). Lo único «múltiple» es **dentro del
   asistente**: marcar temporadas de una serie (`PasoSeleccion`, `multiSelected`) o capítulos de una temporada
   (`episodeSelected`). No hay ningún componente de casilla reutilizable (sí la clase `.checkbox-label`, `components.css` ≈ 596).
2. **Una «tanda» del asistente no es una entidad.** `useAsistente.ts` (`uploadAllSeasons` ≈ 902, `uploadAllEpisodes` ≈ 950) hace un
   bucle **en el navegador**: por cada elemento llama a `queueUpload()` → `POST /library/{id}/upload/queue` y salta el que falle.
   El servidor no sabe que son una tanda. Cada una es un `upload_jobs` independiente. `Seleccion` (`utils/seleccionSubida.ts`)
   admite una sola cola homogénea («Nunca dos colas a la vez»): temporadas **o** capítulos.
3. **La cola ya es «un hilo por trabajo + puerta».** `upload_queue._insert_and_start_queued_job` (≈ 93-208) inserta la fila
   `queued` bajo `BEGIN IMMEDIATE` (pone `isolation_level = None`, así que cualquier transacción abierta de la conexión se
   confirma antes), publica `subida-estado` y llama a `_lanzar_trabajo` (≈ 211): un `threading.Thread` por trabajo que corre
   `_run_queued_job` (≈ 1375). Ese hilo toma plaza en `_upload_concurrency_gate` (`upload_execution/concurrencia.py`,
   `_UploadConcurrencyGate`) **antes** de comprobar/renombrar/preparar, y la traspasa al subproceso de Uploadrr-EMU
   (`puerta_traspasada`). La puerta admite por **id ascendente** (`min(self._waiting - retirados)`), relee el límite («Subidas en
   paralelo», `uploads.max_concurrent`, defecto 1, valores 0..10, **0 = sin límite**) en cada vuelta y despierta cada ≤3 s. Un hilo
   en espera no tiene conexión abierta (`connect()` va después de `acquire`), pero cada lectura del límite abre una conexión nueva
   (`connect` con sus PRAGMA + `init_db` + SELECT).
4. **Ciclo de vida por trabajo** (`upload_execution/ciclo_de_vida.py`): `cancel_upload_job` (`queued` → `escribir_estado(desde=
   {"queued"})` + `retirar_de_la_cola`, y **si la fila ya avanzó se llama a sí misma y la cancela como lo que sea ahora**;
   `ready` esperando turno → igual con `retirar_si_espera`; `preparing` → solo marca; `running` → SIGTERM al grupo; en `running` y
   `preparing` escribe `cancelled` sin condición), `queue_retry_for_job(job_id, conn=None, *, desde_el_principio)` (fila nueva con
   `retry_of_job_id`, comprueba `trabajo_activo` bajo `BEGIN IMMEDIATE`, reanuda desde el paso que falló), `delete_upload_job`
   (borra la cadena entera de intentos, `retry_chain_ids`). Un reintento hereda petición, propuesta de nomenclatura, overrides y
   snapshots. Cancelar no notifica.
5. **Cadenas de reintento**: `queue_upload_for_item` encadena cada «Subir» sobre la punta anterior del elemento
   (`_find_latest_job_for_item`, ≈ 270), **sea del estado que sea** (también una `completed` o de otro lote). `UploadsPage` solo
   enseña la punta de cada cadena, pero lo calcula **en el navegador** (`hasNewerRetry`, ≈ 515-525) sobre las filas cargadas;
   `/uploads` pagina y cuenta intentos, no puntas.
6. **Comprobaciones previas** ya divididas para tandas: `services/upload_checks.py::run_upload_checks(scope=...)` con
   `CONTENT_CHECK_IDS` (accesible, season_pack, capitulos_accesibles, carpeta_subida, renameable, spanish) por elemento y
   `ENVIRONMENT_CHECK_IDS` (output, qbittorrent, imghosts, emuwarez) una vez por tanda. Devuelve solo `{checks, ready}`; el mensaje
   del check `season_pack` dice `Pack listo: N episodio(s) → {pack_folder}`, que es la **carpeta común de los capítulos, no el
   nombre del torrent**. En el cliente las orquesta `useComprobacionesTanda` (`asistente/useComprobaciones.ts`), genérico sobre
   una lista de ids **pero con dos condiciones del asistente**: no hace nada si `batchQueue.length <= 1`, y solo corre con
   `step === 2` y `batchPhase === 'idle'`; se relanza con `[step, batchQueue.length, batchPhase, intento]`.
7. **Comprobaciones del servidor al correr el trabajo** (fallan el trabajo, no el lote): `_paso_comprobar` (integridad,
   `allowed_roots`, claves, `uploadrr.path`, nomenclatura bloqueada vía `_check_generic_upload_preconditions`), `_paso_nombre`
   (`build_nomenclature_apply_plan` / `build_season_pack_plan` no `ready`), `_populate_ready` (`validate_upload_preconditions`),
   `start_upload_job` (`validate_upload_job_start`). **El castellano no se vuelve a comprobar en el servidor para películas ni
   capítulos** (solo los packs, con `_spanish_errors` de `season_pack.py`): hoy la ruta suelta confía en el cliente.
   Duplicados: no hay bloqueo en la app; el Resumen compara contra el catálogo local (`getEmuComparison(id, tuya?)`, SQL local, sin
   red) y existe `conclusionDuplicados` (`utils/resumenSubida.ts`: niveles `duplicado | trump | mixto | peor | sin-comparar`, y
   `null` si no hay torrents con los que comparar). Uploadrr-EMU hace su propia fase `duplicates` («Searching for existing
   torrents» / «No dupes found»); si aborta, la app solo ve un exit code distinto de 0 (no hay parseo específico de duplicado).
8. **Límite de eMuwarez (~28/min compartido)** (`integrations/emu_limitador.py`): la app solo pasa por él en la comprobación de
   entorno (`test_emuwarez_connection`, 1 llamada por pasada), el seeding por subida (`emu_torrent_stats`, solo al abrir un
   detalle) y las sincronizaciones. **El subproceso Uploadrr-EMU llama al tracker por su cuenta con la misma clave y NO pasa por
   ese limitador.** La única válvula real es «Subidas en paralelo». Además, **la sincronización de peticiones no corre mientras
   haya cualquier trabajo activo, también `queued`** (`requests._motivo_ocupado`, ≈ 168): un lote largo la para entera.
9. **Notificaciones**: `_notify_upload_completed/_failed` (`upload_execution/estado.py` ≈ 156-191) emiten una notificación
   (campana + Discord/Telegram según ajustes) **por trabajo**, de forma síncrona en el hilo del trabajo. `reconcile_interrupted_jobs`
   **no** notifica. `notification_center.emit(..., dispatch=False)` ya existe para no enviar fuera.
10. **Panel**: «En curso» (`CarrilEnCurso.tsx`) pinta **todas** las subidas vivas, cada una con su `useTicker` (un `setInterval`
    por fila; permitido porque `utils/uploadStatus.ts` está en `RELOJES`). Un lote de 40 lo inundaría, y hoy el asistente ya puede
    hacerlo con una tanda. El Panel pide `getUploads({hide_preparatory, limit: 100})` por `created_at DESC`
    (`DashboardPage.tsx` ≈ 126): con más de 100 trabajos vivos el más viejo, que es el que está subiendo, se cae de la lista.
11. **Biblioteca virtualizada** (`FilasVirtuales`, `RejillaVirtual`, 3 vistas: pósters, pósters grandes, lista): las filas fuera
    de pantalla no existen en el DOM, así que la selección tiene que vivir en estado de `LibraryPage`, no en el DOM. La rejilla mide
    la primera tarjeta y ya tuvo un bug de oscilación de medida (PLAN.md, «vista de pósters en negro»): cualquier adorno en la
    tarjeta no puede cambiar su alto, y la aparición de una barra no puede cambiar el ancho de la barra de scroll (el número de
    columnas sale del ancho). En la lista, **las temporadas son `LibraryTreeRow` hijas renderizadas recursivamente** (≈ 276-287), un
    clic en la fila de una serie o temporada la despliega (`<tr onClick={toggle}>`, ≈ 171) y solo el enlace del título abre la
    ficha (≈ 219). `LibraryChildrenSection.tsx` (ficha) reutiliza la misma fila. **Con cualquier filtro de columna Biblioteca
    carga todos los niveles en plano** (`filtrosBiblioteca.ts`): salen capítulos como filas/tarjetas, y una serie y sus temporadas
    pueden aparecer a la vez; sin filtro, las vistas de pósters no enseñan temporadas. Con una ficha abierta la lista entera se
    sustituye (`if (selected)`, ≈ 581-595).
12. **Rediseño P2 (Biblioteca) y P3 (Peticiones)** siguen pendientes en PLAN.md, pero #207 y #208 ya cambiaron esas pantallas:
    línea de calidad y grupo bajo el título, vistas guardadas (`VistasGuardadas`, `utils/vistasBiblioteca.ts`, en `localStorage`,
    solo filtros y orden), columna del título con ancho mínimo (`biblioteca.css` ≈ 131) y `LIST_COLUMNS = 7` (antes 13).
    `LibraryTreeRow.test.tsx` (≈ 87) exige 7 `td`. Lo que se toque ahí choca con P2.

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
  quiera editar uno lo sube suelto. Editar 40 elementos en un modal no escala y duplicaría el hook de ~1050 líneas.
- **Sin capítulos sueltos de varias series** desde Biblioteca (solo packs de temporada). Las temporadas no aptas para pack
  (incompletas, incoherentes, sin castellano en algún capítulo) salen **saltadas con su motivo**.
- **Sin selección en Peticiones** (la página); es el mismo modal con otro productor, queda para un PR opcional posterior.
- **Sin «seleccionar todo» ni rangos con Mayús**: v1 marca de una en una (el tope es 50).
- **Sin cambiar la concurrencia ni la puerta**: un lote no sube «más rápido»; solo evita el clic repetido. No hay prioridades ni
  «lote en serie» propios.
- **Sin entidad «lote» con tabla, nombre, política ni estado propios.**
- **Sin eventos nuevos en el bus (`eventos.publicar`), sin `setInterval` nuevos, sin estados nuevos de subida** (así no se tocan
  `test_copias_frontend.py::test_el_vocabulario_de_estados_coincide` ni los avisos). La notificación agregada de PR 7 sería un
  tipo nuevo de `notification_center.EVENT_TYPES`, no un evento del bus.
- **Notificación agregada y unificar las tandas actuales con el nuevo endpoint**: opcionales, PR final (ver §6).

### Decisiones

| # | Decisión | Por qué |
|---|---|---|
| D1 | **Un lote es solo una etiqueta**: columna `upload_jobs.lote_id TEXT` (12 hex), sin tabla. | Cada elemento ya es un trabajo con su cadena de reintentos, su hilo, su cancelación y su borrado. Una tabla `upload_batches` obligaría a mantener estado (¿cancelado? ¿terminado?) que ya se deduce de las filas, y a decidir qué pasa al borrar. Todo lo que el lote necesita (contadores, cancelar pendientes, reintentar fallidas) se calcula sobre las **puntas de cadena**. Si más adelante hace falta nombre o política, se añade la tabla y se rellena a partir de `lote_id` sin perder datos. |
| D2 | **El id lo asigna el servidor** en el nuevo endpoint (`secrets.token_hex(6)`); las tandas actuales del asistente mandan un id generado en el cliente (mismo formato) en su `queueUpload` de siempre. `MAX_ELEMENTOS_LOTE` y `PATRON_LOTE_ID` viven **una sola vez** en `services/lotes.py`; `web/schemas.py` y `web/api/uploads.py` los importan (web → services está permitido). | Permite agrupar lo que ya existe sin reescribir los 3 tests de tanda que verifican llamadas sueltas a `queueUpload`. Sin literales repetidos. |
| D3 | **Cada elemento sigue siendo un trabajo independiente**; no hay trabajo «padre». | No hay que reescribir `_run_queued_job`, `cancel_upload_job` ni `queue_retry_for_job`. |
| D4 | **Subidas no agrupa filas en acordeón**: chip «Lote · N» en la fila + filtro `lote_id` + barra de resumen cuando hay filtro. Con `lote_id` el **servidor** devuelve y cuenta solo puntas de cadena. | La tabla ya anida cadenas de reintento y pagina por trabajos (100, «Cargar más»); un segundo nivel rompería ordenación, paginación y el recuento «N de M». Filtrar puntas en el servidor hace que filas, «N de M» y contadores del banner digan lo mismo. |
| D5 | **Pertenencia al lote = punta de cadena con ese `lote_id`**, con la punta calculada sobre **toda la tabla** (no solo dentro del lote). `queue_retry_for_job` hereda el `lote_id` del original; el camino heredado `retry_upload_job` **no** (ver §3.1). Si después subes ese elemento suelto o en otro lote, la fila vieja deja de ser punta y el lote «pierde» ese miembro; y «Borrar» en una fila del lote borra la cadena entera del elemento, **también intentos de otros lotes o sueltos**. | Coherente con cómo ya se ven y se borran las cadenas. Se acepta y se documenta. |
| D6 | **Un fallo no detiene al resto** (igual que la tanda actual). | Es el comportamiento vigente y lo esperado; lo sistémico se mitiga en §5.5 (precondiciones una vez antes de encolar). |
| D7 | **Duplicado y «peor» avisan, no bloquean** (igual que el Resumen actual): los niveles `duplicado` y `peor` llegan **desmarcados** y avisados; el usuario puede marcarlos. `null` (nada con qué comparar) y `sin-comparar` llegan marcados. | Evita subir 30 duplicados por un clic de más, sin impedir un re-subir legítimo. A confirmar (pregunta 3). |
| D8 | **Tope de 50 elementos por lote** (`MAX_ELEMENTOS_LOTE`, copia vigilada en el frontend). | Cada elemento = 1 hilo esperando en la puerta (ver §5.1); 50 es holgado y acotado. A confirmar (pregunta 2). |
| D9 | La **petición se enlaza solo desde el Panel** (`rec_request_id` por fila). Desde Biblioteca no se enlaza (igual que hoy). | Paridad con el asistente actual. A confirmar (pregunta 6). |
| D10 | **El proveedor solo viaja por elemento en temporadas** (`provider` → `provider_override`, que `queue_upload_for_item` solo aplica a `season`). En película/capítulo el proveedor sugerido va dentro de `campos` (el juego **completo** de campos de `getNomenclatureFields(id).fields` + el proveedor), como hace `save-fields`. | `provider_override` se descarta en silencio fuera de las temporadas, y `save-fields` reconstruye la propuesta entera con lo que recibe: mandar solo `{provider}` vaciaría el resto. |
| D11 | **El servidor no se fía del cliente para el contenido**: `encolar_lote` salta un elemento cuyo `checks.ready` sea falso y, en película/capítulo, repite `run_upload_checks(scope="content")` (barato: abrir, probar un enlace, leer columnas). Los packs ya los revisa `_paso_nombre`. | Hoy nadie comprueba el castellano de una película en el servidor; un lote sería una segunda puerta de entrada sin esa comprobación. |

---

## 2. Modelo de datos y migración

**Esquema 51 → 52** en `emuwarez_uploadrr/database.py`:

- `SCHEMA_VERSION = 52` (línea ≈ 21).
- Nueva función `_migrate_upload_jobs_lote(conn)` copiando el patrón de `_migrate_upload_jobs_pasos_uploadrr` (≈ 1282): leer
  `PRAGMA table_info(upload_jobs)`; si falta `lote_id`, `ALTER TABLE upload_jobs ADD COLUMN lote_id TEXT` con el mismo
  `try/except sqlite3.OperationalError` que solo calla si la columna ya existe; después
  `CREATE INDEX IF NOT EXISTS idx_upload_jobs_lote ON upload_jobs(lote_id)`.
- Llamarla **al final de la cascada** de `init_db`, justo después de `_migrate_upload_jobs_pasos_uploadrr(conn)` (≈ 1881), antes
  de `set_state(conn, "schema_version", ...)` (≈ 1882).
- Nullable, sin relleno: los trabajos viejos y los sueltos tienen `lote_id IS NULL` (la interfaz no pinta chip).
- No hace falta tocar `backup_service`, `maintenance_service`, `borrar_biblioteca` ni `demo_seed` (columna nueva anulable, no hay
  FK; `get_upload_job` y `list_upload_jobs` usan `SELECT *`, así que la columna llega sola).
- Ojo con las publicaciones automáticas (§6): en cuanto PR 1 entre en una versión, una imagen anterior rechazará la BD
  (`BaseMasNuevaError`); volver atrás exige restaurar `backups/pre-migracion-*.db`.

Definición de **punta de cadena** (la misma que `_find_latest_job_for_item`), siempre sobre toda la tabla:

```sql
id NOT IN (SELECT retry_of_job_id FROM upload_jobs WHERE retry_of_job_id IS NOT NULL)
```

---

## 3. Backend por fichero

### `emuwarez_uploadrr/services/lotes.py` (NUEVO; `services/` no puede importar de `web/`)

Constantes y utilidades:
- `MAX_ELEMENTOS_LOTE = 50`, `PATRON_LOTE_ID = r"^[0-9a-f]{12}$"`
- `TIPOS_DE_LOTE = ("movie", "season", "episode")`
- `nuevo_lote_id() -> str` (`secrets.token_hex(6)`).

Consultas (todo el SQL del lote vive aquí o en `consultas.py`, por `test_web_no_habla_sql.py`):
- `_puntas(conn, lote_id) -> list[dict]`: filas con ese `lote_id` que son punta de cadena (punta calculada sobre toda la tabla),
  orden `id ASC`.
- `resumen_de_lote(conn, lote_id) -> dict | None`: `{lote_id, total, en_cola, en_marcha (staging+preparing+running y el resto de
  `ACTIVE_JOB_STATUSES` salvo queued), completadas, fallidas, canceladas, creado, terminado (no queda nada activo),
  puede_cancelar, puede_reintentar}`. `None` si no hay filas. Solo BD: **nunca** llama a eMuwarez ni a qBittorrent.
- `contar_por_lote(conn, lote_ids) -> dict[str, int]`: una sola consulta `GROUP BY` sobre puntas para los `lote_id` de una página
  de la lista (alimenta el chip «Lote · N»).

Acciones:
- `encolar_lote(conn, elementos) -> dict`: ver §3.2.
- `cancelar_lote(conn, lote_id, *, solo_pendientes=True) -> dict`: **no** llama a `cancel_upload_job` para los pendientes, porque
  si la fila avanzó entre lectura y escritura esa función se llama a sí misma y la cancela como lo que sea ahora (también
  `preparing`), rompiendo «solo pendientes». En su lugar:
  1. Para cada punta `queued`: `escribir_estado(id, desde={"queued"}, status="cancelled", stage="cancelled", finished_at=…)`.
     Si devuelve `False`, ya arrancó: se cuenta como «intacta (ya había empezado)». Todas las escrituras primero.
  2. Después, `retirar_de_la_cola(id)` y la línea de log de cada cancelado (el hilo que justo tomara plaza ve el `cancelled` en
     `_cargar_trabajo`/`_mark` y la suelta sin tocar ficheros).
  3. Solo si `solo_pendientes=False`: `cancel_upload_job` sobre los `preparing`/`running`, **releyendo el estado justo antes** de
     cada uno (si en medio pasó a `completed`, no se toca: hoy `cancel_upload_job` escribe `cancelled` sin condición en esos
     estados y marcaría como cancelada una subida que sí se hizo).
  Devuelve `{canceladas, intactas}`. Alternativa equivalente: un kwarg `solo_si_en_cola=True` en `cancel_upload_job`.
- `reintentar_fallidas(conn, lote_id, *, desde_el_principio=False) -> dict`: para cada punta `failed|cancelled` en orden de id
  llama a `upload_queue.queue_retry_for_job(id, conn=conn, desde_el_principio=...)`; si devuelve `blocked` (p. ej.
  `trabajo_activo`) lo cuenta como saltado con su mensaje. El reintento hereda `lote_id` (§3.1), así que el lote sigue siendo el
  mismo y conserva el orden FIFO. Tras un reinicio (`reconcile_interrupted_jobs` marca como fallidos todos los activos, sin
  notificar) esto reanuda todo con un clic.

### 3.1 `services/upload_queue.py`

- `_insert_and_start_queued_job(...)` (≈ 93-208): parámetro nuevo `lote_id: str | None = None` (keyword, al final: el único
  llamador directo en tests, `test_eventos_subidas.py` ≈ 155, pasa `(conn, item)` posicional). El `INSERT` (≈ 165-190) tiene hoy
  **20 columnas y 18 `?`** (`'queued','queued'` son literales): con `lote_id`, 21 columnas y 19 `?`, y el valor en la tupla.
- `queue_upload_for_item(...)` (≈ 255-313): parámetro `lote_id: str | None = None`, pasado a `_insert_and_start_queued_job`. No
  hereda del último trabajo del elemento (D5).
- `queue_retry_for_job(...)` (≈ 357-373): pasar `lote_id=original.get("lote_id")`.
- `upload_execution/ciclo_de_vida.py::retry_upload_job` (camino heredado `/uploads/{id}/retry`, que hoy solo usa el CLI,
  `comandos/subida.py` ≈ 173): **no** propaga `lote_id`. Crea una fila `ready` que espera en la puerta con etapa «esperando
  turno», y `ready` no está en `ACTIVE_JOB_STATUSES`: `trabajo_activo` no la ve, `reconcile_interrupted_jobs` no la recoge y la
  interfaz la oculta como preparatoria. Dentro de un lote, el lote nunca acabaría y «Reintentar fallidas» podría lanzar un
  duplicado.
- No se toca `_run_queued_job`, `PASOS`, la puerta ni `reconcile_interrupted_jobs`.

### 3.2 `encolar_lote` (en `services/lotes.py`)

Entrada: lista de elementos `{item_id, request_item_id?, checks, campos?, provider?}` en el orden en que el usuario quiera que se
suban (el orden de inserción es el orden de id, que es el de la puerta). `item_id` es la fila real que se sube (desde el Panel,
`library_target_id ?? id`, ver §4).

Algoritmo:
1. Validar `1 <= len(elementos) <= MAX_ELEMENTOS_LOTE` (Pydantic ya lo hace en la ruta → 422; la función lanza `ValueError` por
   si se llama desde otro sitio).
2. **Precondiciones generales una sola vez**, antes de insertar nada: las de `_season_upload_preconditions` (`uploadrr.path`
   existe, `emu.api_key`, `tmdb.api_key`; conviene renombrarla, no es solo de temporadas). Si falla, se rechaza el lote entero
   (409 con los motivos). La comprobación de entorno del cliente no cubre estas claves; sin esto, cada trabajo fallaría en
   `_paso_comprobar` a los pocos segundos y enviaría una notificación por elemento.
3. `lote_id = nuevo_lote_id()`. Para cada elemento, **dentro de un `try/except Exception` por elemento** (un fallo inesperado se
   apunta con `logger.exception`, `conn.rollback()` y se devuelve como `blocked`; si va bien, `conn.commit()`): las escrituras de
   un elemento a medias no pueden quedar confirmadas por el siguiente (`_insert_and_start_queued_job` confirma lo que hubiera
   abierto). En este orden, **todo lo que puede saltar antes de escribir nada**:
   - Repetido en el cuerpo → `blocked: "Repetido en el lote."`.
   - Elemento inexistente → `blocked`.
   - `item_type` (de la fila real, no el del Panel) fuera de `TIPOS_DE_LOTE` (una serie) → `blocked: "Elige sus temporadas."`.
   - Capítulo cuya temporada (`parent_id`) va en el mismo lote → `blocked: "Su temporada ya va en el lote."` (son
     `library_item_id` distintos: ni «Repetido» ni `trabajo_activo` lo verían, y se subirían los dos).
   - `checks.ready` falso, o en película/capítulo `run_upload_checks(item_id, scope="content")` no `ready` → `blocked` con el
     primer motivo (D11).
   - Trabajo activo del elemento (`trabajo_activo`) → `blocked: "Ya hay una subida en curso para este contenido."`.
   - Solo entonces, si trae `campos` (película/capítulo; se ignoran en temporadas): guardarlos igual que
     `POST /library/{id}/nomenclature/save-fields`: `source_assistant.update_nomenclature_fields_preview(item_id, campos,
     conn=conn)` + `nomenclature.save_manual_nomenclature_fields(item_id, campos, preview, conn=conn)`. Va al final porque
     `save_manual_nomenclature_fields` caduca la propuesta vigente y `_populate_ready` lee la más nueva no caducada: guardarla
     para un elemento que luego se salta cambiaría el nombre de la subida que ya está en marcha.
   - `queue_upload_for_item(item_id, request_item_id=..., checks=..., provider_override=el.provider if season else None,
     lote_id=lote_id, conn=conn)`. Si aun así devuelve `status == "blocked"` (carrera con `trabajo_activo`), se anota y se sigue.
4. Si no se encoló ninguno, `lote_id` de la respuesta es `None` (no queda lote fantasma).
5. Devuelve `{lote_id, encolados, saltados, resultados: [{item_id, status: "queued"|"blocked", job_id, errors}]}`.

No hace falta `eventos.publicar` aquí: cada alta pasa por `_insert_and_start_queued_job` (que ya publica `subida-estado`; el
frontend agrupa ráfagas con `useRefrescoPorAvisos`) y cada cambio por `escribir_estado`. El doble clic en «Subir» queda
protegido por `trabajo_activo`: la segunda llamada saltará todos los elementos.

Coste: la ruta es `def` (hilo del threadpool, no bloquea el bucle), pero por elemento `_propuesta_vigente` reconstruye una
propuesta automática caducada (MediaInfo si no está en caché, título de TMDb). Tras una versión que cambie reglas, 50 elementos
pueden tardar decenas de segundos, mientras los hilos de los ya encolados compiten por el cerrojo de escritura (`busy_timeout`
5 s). El modal enseña «Encolando…» y no se puede cerrar mientras tanto.

### 3.3 `services/upload_execution/consultas.py`

- `_upload_jobs_where(filters)` (≈ 38): con `filters.get("lote_id")`, añadir `lote_id = ?` **y la condición de punta de cadena**
  (D4). `count_upload_jobs` lo hereda, así que «N de M» cuenta elementos del lote.
- Nada más (`list_upload_jobs` no cambia).

### 3.4 `web/schemas.py`

- `UploadQueueBody` (≈ 1417-1446): `lote_id: Optional[str] = Field(None, pattern=PATRON_LOTE_ID)` (para las tandas actuales del
  asistente). Pydantic ya da el 422; no hace falta repetir la validación en la ruta.
- `UploadJobDetail` (≈ 1173-1243): `lote_id: Optional[str] = None`, `lote_total: Optional[int] = None`.
- Nuevos modelos: `UploadLoteElemento` (`item_id: int`, `request_item_id: Optional[int]`, `checks: UploadChecksSnapshot`
  (≈ 1412), `campos: Optional[Dict[str, Any]]`, `provider: Optional[str]` — `None` = no elegido, `""` = «Sin proveedor» a mano),
  `UploadLoteBody` (`elementos` con `min_length=1`, `max_length=MAX_ELEMENTOS_LOTE`), `UploadLoteResultado`,
  `UploadLoteResponse`, `LoteResumen`, `LoteAccionBody` (`solo_pendientes: bool = True`, `desde_el_principio: bool = False`).

### 3.5 `web/api/uploads.py` (sin SQL: guardia `test_web_no_habla_sql`)

- `queue_upload` (≈ 291): pasar `lote_id=body.lote_id` a `queue_upload_for_item`. La ruta suelta no hace nada más (sin eventos,
  auditoría ni marcas en la petición), así que la paridad es sencilla.
- `_job_to_detail` / `_con_ficha` (≈ 114-206): nuevos kwargs `lote_id`, `lote_total` hacia `UploadJobDetail`.
- `get_uploads` (≈ 330): query param `lote_id: str | None = Query(None, pattern=PATRON_LOTE_ID)` en `filters`; tras
  `exec_list_jobs`, **una** llamada `lotes.contar_por_lote(conn, {j["lote_id"] for j in jobs if j.get("lote_id")})` y pasar
  `lote_total` a cada `_con_ficha`. `count_uploads` (≈ 367): mismo filtro.
- `get_upload` (≈ 388): rellenar `lote_total` de ese trabajo.
- Rutas nuevas (el orden de declaración no importa: no chocan con `/uploads/{job_id}` ni con sus subrutas; declararlas antes
  tampoco molesta):
  - `POST /uploads/lote` → `lotes.encolar_lote`.
  - `GET /uploads/lotes/{lote_id}` → `lotes.resumen_de_lote` (404 si `None`).
  - `POST /uploads/lotes/{lote_id}/cancelar` (`solo_pendientes`).
  - `POST /uploads/lotes/{lote_id}/reintentar` (`desde_el_principio`).
- Todas con `Depends(require_auth)`. Las rutas nuevas abren la BD con `db()` (CLAUDE.md), no con el `_get_conn()` heredado del
  fichero (que solo confirma con `with`, no cierra).

---

## 4. Frontend por fichero

### Utilidades, API y tipos
- `src/utils/lote.ts` (NUEVO): `MAX_ELEMENTOS_LOTE = 50` (copia del backend, vigilada), `nuevoLoteId()` (12 hex con
  `crypto.getRandomValues`, con respaldo para jsdom), tipos `ElementoDeLote`, `FilaLote`, y funciones puras:
  - `expandirSeleccion(...)`: serie → temporadas aptas (`isSeasonReady` / `seasonNotReadyReason`), y quita una temporada que ya
    venga por su serie marcada (con filtros, serie y temporada pueden marcarse a la vez).
  - `razonNoSubible(item)`: película/capítulo con la lógica de `episodeNotReadyReason` (`utils/libraryItem.ts`: mira
    `local_status` y `has_spanish_ok`, y admite `Subido`), **pero con su propio texto**: los mensajes de esa función dicen «el
    capítulo». Mejor un parámetro de tipo o una función nueva que un alias.
  - `marcadaPorDefecto(nivel: NivelDuplicado | null)`: desmarca `duplicado` y `peor`; `null` y el resto, marcadas.
  - `repetidoEnElLote(filas)`: en el paso 1 solo **avisa** con misma `tmdb_id` + `item_type` + `season_number` (dos instancias
    de Radarr/Sonarr, `instance_id`); el bloqueo real va en el paso 2 por **nombre final del torrent** repetido (el nombre sale de
    `getNomenclatureFields` o del `nombre` del pack). Dos copias 4K y 1080p no chocan (nombres distintos); dos copias con el mismo
    nombre sí: el segundo trabajo fallaría con «es de la subida #N» (`upload_queue.py` ≈ 1186-1195 compara `destino_uploadrr`).
- `src/api/uploads.ts`: `queueUpload(itemId, remuxOverrides, checks, remuxSnapshot, seasonOverrides, requestItemId)` recibe un
  **7.º parámetro** opcional `loteId`. Los asserts de subida suelta (`UploadWizardModal.test.tsx` ≈ 169 y 302) usan
  `toHaveBeenCalledWith` con exactamente 6 argumentos: una subida suelta **no** puede pasar el 7.º ni como `undefined` (construir
  la llamada con o sin él). Nuevas `queueLote`, `getLote`, `cancelarLote`, `reintentarLote`; `UploadsQuery.lote_id` y su
  serialización en `uploadsQueryString`.
- `src/types/api.ts`: `UploadJob.lote_id?`, `lote_total?`; tipos de las respuestas del lote.

### Selección
- `src/hooks/useSeleccionLote.ts` (NUEVO): `Map<number, LibraryItemResponse>` (se guarda el objeto, no solo el id, porque una
  fila filtrada o recargada puede desaparecer de la lista), `alternar`, `limpiar`, `tiene`, tope `MAX_ELEMENTOS_LOTE`. Expone
  callbacks **estables**: las filas y tarjetas reciben `seleccionado: boolean` + `alternar`, nunca el `Map` (pasarlo rompería el
  `memo` y cada clic repintaría todas las filas).
- `src/components/lote/BarraLote.tsx` (NUEVO): «N seleccionados (M ocultos por el filtro) · Subir por lotes · Limpiar».
  Reutilizable por Biblioteca y Panel. **No `position: fixed`**: taparía el pie del sidebar (CPU/RAM/disco) y el body tiene zoom
  (`utils/uiScale`). Va en el flujo, como pie de alto fijo dentro de `.bib-pagina` (columna flex con scroller interior
  `.bib-scroll`); al aparecer cambia el alto del contenedor de `RejillaVirtual`/`FilasVirtuales`, que lo toleran, pero no puede
  hacer aparecer/desaparecer la barra de scroll vertical (cambiaría el número de columnas).
- `src/components/lote/CasillaLote.tsx` (NUEVO): `<input type="checkbox">` con `aria-label="Seleccionar «Título»"` y la clase
  `.checkbox-label`; `stopPropagation` para que no **despliegue la fila** (serie/temporada en la lista) ni abra la ficha. No se
  pinta en capítulos.

### Modal
- `src/components/lote/SubidaPorLotesModal.tsx` + `useLote.ts` + `PasoContenidoLote.tsx` + `PasoResumenLote.tsx` (NUEVOS), sobre
  `components/Modal.tsx` (regla de `.coderabbit.yaml`: Escape, clic fuera, foco atrapado y devuelto). Stepper de dos pasos con las
  clases `asist-paso*` ya existentes («1 · Contenido», «2 · Resumen»); el foco al cambiar de paso vive en `UploadWizardModal.tsx`
  y `pasosDelAsistente` no se exporta: extraerlo o copiarlo.
  - **Entrada**: `elementos: { item: LibraryItemResponse; requestId?: number; alcance?: { season?: number | null; episode?:
    number | null } }[]` como **copia** tomada al abrir (salir de Biblioteca limpia la selección de origen), `onClose`, `onDone`,
    `onNavigate`.
  - **Paso 1 «Contenido»**: expande cada serie con `getLibrary({ parent_id, type: 'season', limit: 500 })` (como `useAsistente`
    ≈ 257; si trae `alcance.season`, solo esa temporada; si es una petición de serie entera, cada temporada lleva su
    `request_item_id`). Lista de filas con casilla, tipo, motivo si no es subible (desmarcada y deshabilitada), aviso de repetido,
    total y el tope de 50. «Continuar (N)».
  - **Paso 2 «Resumen»**:
    - `useComprobacionesTanda` necesita dos cambios para reutilizarse: un parámetro `minimo` (defecto 2; el modal pasa 1), porque
      hoy no hace nada con un solo elemento y un lote de una película nunca habilitaría «Subir»; y el modal le pasa
      `step: paso === 'resumen' ? 2 : 1` (un `2` fijo comprobaría ya en el paso 1), llama a `olvidar()` cuando cambia la selección
      del paso 1 (cambiar una película por otra no cambia la longitud y no relanzaría el efecto) y mueve `batchPhase`
      `'processing'`/`'done'` alrededor de `queueLote`. Pasarle la cola completa del paso 1 y manejar las casillas del paso 2 por
      separado. `proveedorElegido` lleva el proveedor de cada temporada cuando se manda `provider` (D10), para que el check
      `season_pack` y el trabajo usen el mismo.
    - Efecto propio, secuencial por elemento:
      - Película/capítulo: `getNomenclatureFields(id)` → nombre del torrent, `blocked` y los avisos `audio_warning` (una pista sin
        idioma queda fuera del nombre), `source_mismatch_warning` y `title_warning`, que el asistente deja corregir y el lote no:
        se enseñan por fila y con `audio_warning` la fila llega desmarcada («Súbela suelta para elegir el idioma»). Si es WEB-DL
        sin proveedor, `suggestProvider(id)` y se guardan los `campos` completos (D10).
      - `getEmuComparison(id, { resolution, source })` (la segunda parte sale de los campos, como en `ResumenSubida.tsx`) →
        `resumirComparaciones([c])` (puede dar `estado: 'error' | 'sin-catalogo'`) → `conclusionDuplicados(filas)` (o `null`).
        Opcional: la hora de la última sincronización del catálogo (`getEmuSyncStatus`), como `useResumen`.
      - Temporadas: el nombre del torrent sale del `nombre` nuevo de `run_upload_checks` (PR 5, obligatorio; ver §0.6).
    - Tabla por elemento: título, tipo, nombre del torrent, avisos, comprobación (✓/✗ + mensaje), «En eMuwarez» (frase de
      `conclusionDuplicados`), casilla «Incluir». Falla comprobación de contenido, nomenclatura bloqueada, sin castellano o nombre
      repetido en el lote → desmarcada, deshabilitada y con su motivo («Se saltará»).
    - **Regla para habilitar «Subir»** (la de `PasoSubidaTanda.tsx` ≈ 105, #139/#147/#155): deshabilitado mientras
      `batchChecksLoading || batchChecksError || !completas || !envReady || ninguna fila incluida`, y mientras el efecto propio
      (nombres, comparaciones) siga corriendo; «↻ Volver a comprobar» (`repetir`). Una comprobación vieja o fallida no habilita.
    - Texto fijo: «Se subirán de N en N según “Subidas en paralelo” (ahora: X)». X sale de `fetchSettings().upload_max_concurrent`
      (el campo existe en `api/settings.ts` ≈ 51; `useAsistente` no lo lee hoy). **Con X = 0** («sin límite») el texto es un aviso:
      «Sin límite: se lanzarán las N a la vez contra eMuwarez» (pregunta 12).
    - «Subir N»: `queueLote({ elementos })` con, por elemento, `request_item_id`, `checks: mergedChecksFor(id)`, `campos` si
      procede y `provider` solo en temporadas. Resultado: «N de M encolados» + lista de saltados con su motivo + «Ver el lote en
      Subidas» (handoff por `sessionStorage` `emuwarez_open_lote`, el mismo patrón que `emuwarez_open_upload`, y
      `onNavigate('uploads')`). `onDone` (limpia la selección) se llama **en cuanto vuelve `queueLote`**, no al pulsar «Ver el
      lote»: Escape en la pantalla de resultado no pasa por ese botón.
  - Cierre: se bloquea mientras la petición está en vuelo (como `ocupado`/`cerrarModal` en el asistente).
- `src/styles/lote.css` (NUEVO, importado en `main.tsx` junto a `asistente.css`/`subidas.css`): clases `lote-*`. Sin estilos en
  línea ni `console.log` (convenciones que vigila CodeRabbit, no un test ni ESLint).

### Pantallas
- `src/pages/LibraryPage.tsx`: `useSeleccionLote()` en el componente; `<BarraLote>`; `<SubidaPorLotesModal>` dentro de `modals`
  (≈ 554). Limpiar la selección en `useAlSalir` (≈ 415) y en `onDone`. **Lo seleccionable**: películas, series y temporadas (no
  capítulos, que con filtros salen como filas/tarjetas). Con una ficha abierta (`if (selected)`) la barra no se ve; la selección se
  conserva y vuelve al cerrar la ficha. Las vistas guardadas solo guardan filtros y orden: la selección sobrevive a aplicar una
  vista y no se guarda en ella.
  - Lista: `LibraryTreeRow.tsx` — la casilla va **dentro de la celda Título**, no como columna nueva (`LIST_COLUMNS = 7` se usa
    en el esqueleto ≈ 127, `FilaVacia` ≈ 799 y `FilasVirtuales` ≈ 805, y `LibraryTreeRow` ≈ 167 tiene `colSpan = compact ? 6 : 7`
    escrito a mano; `LibraryTreeRow.test.tsx` ≈ 87 exige 7 `td`). La celda ya lleva dos líneas (título y línea de calidad) con
    ancho mínimo: la casilla no puede romperlo (choca con P2). Las props de selección bajan por la recursión de hijas y son
    **opcionales** (la ficha, `LibraryChildrenSection`, reutiliza la fila sin selección).
  - Pósters y pósters grandes: `PosterCard` (en el propio `LibraryPage.tsx`, ≈ 74, memoizado) y `LargePosterCard.tsx` reciben
    `seleccionado` y `onToggle` estables. La casilla va en `position: absolute` **arriba a la izquierda** del póster (arriba a la
    derecha ya está el icono de estado, `.bib-tarjeta-estado` / `.poster-grande-estado`) y **no puede cambiar el alto de la
    tarjeta**. Las temporadas solo salen en pósters con algún filtro activo.
- `src/pages/DashboardPage.tsx` + `components/hoy/CarrilListo.tsx`: casilla en cada `Fila` de peticiones, contenido único y
  mejoras (no en faltantes, que solo tienen «Pedir»). «Contenido único» y «Mejoras» están dentro del `<details>` plegado «Otras
  ideas» (≈ 105-131). Estado `Map<clave, DashboardRecommendationItem>` con clave
  `${rec_request_id ?? 'u'}-${library_target_id ?? id}`. Barra «Subir seleccionadas (N)» al pie del carril; limpiar en
  `useAlSalir` y `onDone` (la sección se queda montada y se recarga cada 15 s). Al abrir, por fila, como hace `abrir()`
  (≈ 220-237): `item_id = library_target_id ?? id` (`id` suele ser la serie; `library_target_id` solo se usa como petición),
  `requestId = rec_request_id` y `alcance = { season: item.season_number, episode: item.item_type === 'episode' ?
  item.episode_number : null }` (los campos se llaman `season_number`/`episode_number`, `api/dashboard.ts` ≈ 18). El tipo que se
  comprueba es el de la fila real (`getLibraryItem`), no el `item_type` de la petición: si falta la fila de la temporada,
  `_scoped_library_id` cae en la serie. **Dos peticiones pueden apuntar al mismo `library_target_id`** (el grupo 1 hace una fila
  por petición, `panel.py` ≈ 384-430): el modal las une por elemento y deja elegir qué petición se enlaza; si no, el servidor
  saltaría la segunda como «Repetido».
- `components/hoy/CarrilEnCurso.tsx` (PR 1, no PR 4: la tanda del asistente ya lo inunda hoy): tope de filas **vivas** visibles
  (p. ej. 6: las que están subiendo/preparando y las primeras en cola; las que se están despidiendo no cuentan) más una línea
  «+N en cola · Ver todas las subidas». `notaEnCurso` ya resume «N subiendo · M en cola». Para que con >100 trabajos vivos no se
  pierda el que sube, el Panel pide los vivos aparte o los ordena con los activos primero (y `notaEnCurso` deja de contar de
  menos).
- `src/pages/UploadsPage.tsx`:
  - Chip «Lote · N» en `JobRow` (junto al título, ≈ 186-203) cuando `job.lote_id` y `lote_total > 1` (un lote que se quedó en uno
    no merece chip); al pulsarlo fija `loteFiltro`.
  - `load()` (≈ 355) mete `lote_id` en el objeto `filtros` (donde ya van estado y `hide_preparatory`) hacia
    `getUploads`/`countUploads`, y `loteFiltro` entra en sus dependencias; `loteFiltro` se reinicia en `quitarFiltros` y
    `useAlSalir`, y cuenta en `filtrando` (≈ 410-413) para que el estado vacío ofrezca «Quitar filtros». Con el filtro, los
    intentos viejos sin `lote_id` no llegan (`ancestorsOf` no los encontrará): se acepta.
  - Con `loteFiltro`, banner sobre la tabla alimentado por `getLote`: contadores (en cola, en marcha, completadas, fallidas,
    canceladas), «Cancelar pendientes», «Reintentar fallidas», «Quitar filtro». La recarga del resumen va dentro del `load` que
    ya dispara `useRefrescoPorAvisos(AVISOS_SUBIDA, ...)`: **ningún sondeo nuevo**.
  - Modal de confirmación de cancelar (sobre `Modal.tsx`), con casilla «Parar también las que ya se están preparando o subiendo»
    (reutiliza el texto del modal de cancelar en preparación).
  - Recoger `emuwarez_open_lote` del `sessionStorage` en el mismo efecto que recoge `emuwarez_open_upload` (≈ 393-401); al
    recogerlo, cerrar el detalle abierto si lo hay.
- `src/components/UploadJobDetailPage.tsx`: línea «Parte de un lote de N · Ver el lote». **No** por `sessionStorage`: el detalle se
  pinta dentro de `UploadsPage` (≈ 640) y el efecto de recogida solo corre con `[cargado, subidasALaVista]`, que no cambian. Prop
  `onVerLote(loteId)` que hace `closeUpload()` y fija `loteFiltro` (o un `CustomEvent` como `emuwarez:open-upload`, ≈ 450-457).
- `src/components/asistente/useAsistente.ts` (solo PR 1): `uploadAllSeasons` (≈ 902) y `uploadAllEpisodes` (≈ 950) generan **un**
  `nuevoLoteId()` al empezar y lo pasan como 7.º argumento de cada `queueUpload` (siempre son más de un elemento: `esTanda` exige
  ids > 1).
- Documentación de usuario: la línea «Subidas» del `README.md` (≈ 22) en PR 4, y el tour (`tour/steps.ts`: paso de Biblioteca y
  `dashboard-ready`, «“Subir” abre el asistente») en PR 4 y PR 6.

---

## 5. Interacción con concurrencia, cancelación, reintentos y comprobaciones

### 5.1 Concurrencia y la puerta

- Un lote de N crea **N filas `queued` y N hilos** que esperan en `_UploadConcurrencyGate.acquire`. Con «Subidas en paralelo» = 1
  (defecto) suben de uno en uno, **en el orden del lote** (ids consecutivos). No se toca ese comportamiento.
- **Con «Subidas en paralelo» = 0 (sin límite)** un lote de 50 lanza 50 preparaciones y 50 Uploadrr-EMU a la vez contra eMuwarez,
  fuera del limitador. El modal lo avisa; si el servidor debe negarse o capar, es la pregunta 12.
- Coste a vigilar, mayor de lo que parece: cada lectura del límite es una conexión nueva (PRAGMAs + `init_db` + SELECT). Con 50
  hilos en espera son ~17 conexiones por segundo **constantes durante horas**, solo por el despertar de 3 s; y cada `release`,
  `retirar` o salida de un hilo hace `notify_all`, así que «Cancelar pendientes» de 49 son del orden de 49² ≈ 2.500 conexiones en
  ráfaga. Cada hilo además escribe una línea de log y publica un evento al empezar a esperar, que compite con el `BEGIN IMMEDIATE`
  de `encolar_lote`. Por eso: tope de 50 y **caché de ~1 s de la lectura del límite dentro de la puerta en PR 2** (antes era
  opcional en PR 7; conserva «el cambio de ajuste se nota al momento» a un segundo de resolución). **No** conviene un despachador
  que lance hilos de uno en uno: `retirar_de_la_cola` depende de que el hilo exista en `_EN_CURSO`, y la posición en la cola que
  enseña la interfaz (`get_queue_positions` / `posiciones()`) sale de `_waiting` de la puerta (`trabajo_activo` detecta los
  `queued` por estado; solo mira `_EN_CURSO` para los cancelados con hilo vivo).
- Un lote no cambia el límite ni lo sugiere. La interfaz solo lo **dice** («Se subirán de N en N según “Subidas en paralelo”»).
- **Justicia**: la puerta es FIFO por id, así que una subida suelta lanzada después de un lote de 40 espera a que terminen o se
  cancelen las pendientes. Se acepta en v1 (pregunta 2).
- **Sincronización de peticiones parada**: mientras quede un trabajo del lote, incluso solo en cola, `_motivo_ocupado` no deja
  sincronizar las peticiones (programada ni manual). Un lote de 40 con paralelo 1 son horas sin peticiones nuevas (pregunta 13).
- Recursos compartidos que ya soportan trabajos en paralelo y no cambian: `ENLACES` (candado de enlaces), el `config.yaml`
  compartido de Uploadrr-EMU (`_acquire_staged_config`, cubierto por `test_parallel_config_staging.py`).

### 5.2 Cancelación

- `cancelar_lote` cancela **primero los `queued`**, con escritura condicionada a que sigan en cola (ver §3), y solo si el usuario
  lo pide, después `preparing` y `running`. Cancelar un `running` primero liberaría una plaza que un `queued` podría tomar antes de
  ser cancelado.
- Lo que se garantiza es que **ningún pendiente cancelado toca ficheros**: si un trabajo de fuera del lote libera plaza a mitad
  del bucle, un `queued` puede llegar a tomarla, pero ve el `cancelled` al cargar y la suelta. Uno que ya hubiera pasado a
  `preparing` antes de la escritura se cuenta como «intacto (ya había empezado)».
- Los `preparing`/`running` pasan por `cancel_upload_job` (SIGTERM al grupo, `preparing` que se detiene en el siguiente punto
  limpio), releyendo el estado antes para no marcar como cancelada una subida que acaba de completarse.
- Cancelar un solo elemento desde su fila sigue funcionando igual y no afecta al lote.

### 5.3 Reintentos

- «Reintentar fallidas» recorre las puntas `failed|cancelled` por id y reencola con `queue_retry_for_job` (reanuda desde el paso
  que falló si se puede). Cada reintento hereda el `lote_id`, la petición y la nomenclatura fijada.
- Tras un reinicio de la app, `reconcile_interrupted_jobs` marca como fallidos **todos** los activos (también los `queued` que
  nunca empezaron), sin notificar; «Reintentar fallidas» es entonces la forma natural de retomar el lote.
- Un elemento con trabajo activo no se reintenta (`trabajo_activo` → `blocked`, se cuenta como saltado).

### 5.4 Comprobaciones previas y qué hace el lote cuando un elemento no pasa

| Comprobación | Dónde | Efecto en el lote |
|---|---|---|
| Contenido accesible, carpeta de subida, pack posible, sin castellano (`run_upload_checks` scope `content`) | Paso 2, por elemento; y en el servidor (`encolar_lote`: `checks.ready` y, en película/capítulo, otra pasada de contenido) | Fila desmarcada, deshabilitada y con motivo; **se salta**, el resto sigue. |
| Entorno (directorio de salida, qBittorrent, hosts de imágenes, eMuwarez; scope `environment`) | Paso 2, **una vez** | Si falla, no se puede subir nada (igual que `PasoSubidaTanda`); «Volver a comprobar». |
| Claves de eMuwarez y TMDb, `uploadrr.path` | `encolar_lote`, **una vez antes de insertar** | Se rechaza el lote entero (409) con los motivos. |
| Nomenclatura bloqueada | Paso 2 (`getNomenclatureFields(...).blocked` en película/capítulo; pack: el check `season_pack`) y de nuevo al correr el trabajo (`_check_generic_upload_preconditions`, `_paso_nombre`) | Salto en el paso 2; si aun así llega al servidor, ese trabajo falla con su motivo y los demás siguen. |
| Avisos de nombre (`audio_warning`, `source_mismatch_warning`, `title_warning`) | Paso 2 | Se enseñan; con `audio_warning` la fila llega desmarcada. |
| Duplicado / trump contra el catálogo local | Paso 2 (`getEmuComparison` → `conclusionDuplicados`; SQL local, sin red) | Aviso por elemento; `duplicado` y `peor` llegan desmarcados; nunca bloquea. |
| Trabajo activo del mismo contenido | `encolar_lote` antes de escribir, y `queue_upload_for_item` (`trabajo_activo`) | Elemento saltado («Ya hay una subida en curso»). |
| Mismo contenido dos veces en el lote | Paso 1 (aviso por `tmdb_id`+tipo+temporada), paso 2 (nombre repetido) y servidor («Repetido en el lote.») | Aviso y/o salto. |
| Capítulo y su temporada en el mismo lote | Servidor («Su temporada ya va en el lote.») | Se salta el capítulo. |
| `allowed_roots`, integridad | Servidor, al correr cada trabajo | Ese trabajo falla (`failed` con motivo); no afecta a los demás. |
| Duplicado detectado por el propio Uploadrr-EMU | Al ejecutar | Sale como fallo genérico con el resumen de error; no hay parseo específico hoy. |

### 5.5 Qué hace el lote cuando un elemento falla

Sigue con los demás (D6). Un fallo **sistémico** (eMuwarez caído, qBittorrent mal, clave inválida) haría fallar los N seguidos y
generaría N notificaciones (síncronas, desde el hilo de cada trabajo; los webhooks de Discord limitan ráfagas). Mitigación de v1:
la comprobación de **entorno una vez antes de subir**, las **precondiciones de claves una vez en el servidor** (cubren el caso
más tonto: falta una clave y todo falla en segundos) y que «Reintentar fallidas» recupere todo. Un freno automático («parar tras
X fallos seguidos con el mismo motivo») y la notificación agregada quedan como decisión de Gabriel (preguntas 4 y 5).

### 5.6 Límite de ~28/min a eMuwarez

- La app añade como mucho **1 llamada por lote** (el entorno), por el limitador compartido.
- `getEmuComparison`, `resumen_de_lote`, `contar_por_lote` y la lista de Subidas **solo leen BD local**. Prohibido pedir
  `tracker-stats` por fila en la vista del lote (es una llamada a eMuwarez por subida; el PLAN la limita a abrir un detalle).
- Las llamadas de Uploadrr-EMU (búsqueda de duplicados, subida, descarga del torrent) **no pasan por el limitador**. Con «Subidas
  en paralelo» = 1 no hay problema; con 5-10, y sobre todo con 0 (sin límite), y un lote de películas cortas se multiplican contra
  una clave que comparten Sonarr, Radarr y qui. **El lote no sube el límite ni lo recomienda.**
- La sugerencia de proveedor por TMDb (`suggestProvider`) es TMDb, no eMuwarez, y solo se pide para WEB-DL sin proveedor en el
  nombre. Las temporadas ya lo deciden en el servidor (`_decidir_proveedor_pack`).

---

## 6. Estrategia de PRs (orden, el más barato primero; cada uno verde por separado)

Rama `feat/lotes-N-…`, PR no borrador (CodeRabbit). Cada PR actualiza `docs/PLAN.md` («Hecho»; tachar «subida por lotes» en
**PR 6**, porque PR 7 es opcional) y no sube la versión. En los PR de solo `frontend/`/`docs/`/`.md`, CI ejecuta los tests cuyo
**contenido** nombra `frontend` (`grep -l frontend tests/test_*.py`; basta con decirlo en el docstring): cualquier test nuevo que
lea ficheros del frontend debe nombrarlo.

**Dependencias**: 2 ← 1; 3 ← 1; 4 ← 3 (y 1 para el handoff a Subidas); 5 ← 4; 6 ← 5 (las peticiones de temporada o serie del
Panel necesitan los packs de PR 5).

**Publicaciones automáticas**: `publicar.yml` publica sola en días impares cuando hay 3+ PR de `feat/` desde la última versión.
PR 1-3 bastan para que salga una versión con el esquema 52 y un endpoint sin interfaz (una imagen anterior ya no abrirá esa BD).
Gabriel decide (pregunta 14): o lo acepta, o se agrupan, o se publica a mano.

### PR 1 — «Las tandas del asistente quedan agrupadas como lote en Subidas» (backend + frontend)
- Migración 52, `lote_id` en `_insert_and_start_queued_job` / `queue_upload_for_item` / `queue_retry_for_job` (no en
  `retry_upload_job`), filtro `lote_id` con puntas en `_upload_jobs_where`, `UploadQueueBody.lote_id`,
  `UploadJobDetail.lote_id/lote_total`, `services/lotes.py` con constantes, `nuevo_lote_id` y `contar_por_lote`.
- Frontend: `utils/lote.ts` (`nuevoLoteId`, `MAX_ELEMENTOS_LOTE`), 7.º parámetro de `queueUpload`, las dos tandas de
  `useAsistente`, chip y filtro en `UploadsPage`; tope de filas vivas en `CarrilEnCurso`.
- **Aceptación**: (a) subir 2 temporadas o 3 capítulos desde el asistente crea trabajos con el mismo `lote_id`; (b) Subidas
  enseña «Lote · N» y al pulsarlo filtra, con «N de M» contando elementos; (c) una subida suelta no lleva chip ni pasa 7.º
  argumento (los asserts de 6 argumentos de `UploadWizardModal.test.tsx` ≈ 169 y 302 siguen igual); (d) migrar una BD de esquema
  51 conserva todo; (e) los tests de tanda (≈ 387, 427, 636) siguen en verde sin cambiar sus asserts `mock.calls[0][4]`/`[5]`;
  (f) un reintento conserva el lote; (g) «En curso» del Panel no pasa de 6 filas vivas con una tanda de 10.

### PR 2 — «Resumen, cancelar pendientes y reintentar fallidas de un lote» (backend + frontend)
- `resumen_de_lote`, `GET /uploads/lotes/{id}`, `cancelar_lote`, `reintentar_fallidas`, rutas
  `POST /uploads/lotes/{id}/cancelar|reintentar`; banner con contadores, botones y modal de confirmación en `UploadsPage`;
  «Parte de un lote» en `UploadJobDetailPage`; caché de ~1 s del límite en la puerta.
- Añadido en la revisión de #212: `queue_retry_for_job` solo acepta la punta de la cadena (reintentar un intento anterior
  abría una segunda punta y el lote contaba un elemento de más) y «Reintentar» queda apagado en los intentos anteriores.
- **Aceptación**: con la puerta a 1 y un lote de 3 (uno `running`), «Cancelar pendientes» deja el `running` intacto y cancela los
  otros dos sin que toquen ficheros; uno que pasó a `preparing` entre medias sale como «intacto»; con la casilla «también lo que
  ya está en marcha» cancela los tres en ese orden; «Reintentar fallidas» crea trabajos nuevos con el mismo `lote_id`, en orden
  de id, saltando los que tengan trabajo activo; tras `reconcile_interrupted_jobs` recupera todo; los contadores del banner
  coinciden con las filas filtradas.

### PR 3 — Endpoint `POST /uploads/lote` (solo backend)
- `encolar_lote`, modelos de `schemas.py`, ruta. Sin interfaz.
- **Aceptación**: devuelve `lote_id` + resultados por elemento en el orden dado; un elemento inexistente, repetido, de tipo
  serie, con `checks.ready` falso, sin castellano (película), capítulo con su temporada en el lote o con trabajo activo sale
  `blocked` sin tumbar los demás **y sin cambiar su propuesta de nomenclatura**; sin clave de TMDb → 409 y nada encolado; más de
  50 → 422; ninguno encolado → `lote_id: null`; cada elemento lleva `request_item_id` y `checks` a su trabajo, y `provider` solo
  en temporadas; con `campos` (película) guarda la propuesta manual como `save-fields`.

### PR 4 — Biblioteca: selección de **películas** + modal «Subir por lotes» (frontend)
- `useSeleccionLote`, `BarraLote`, `CasillaLote`, `SubidaPorLotesModal` (paso 1 + paso 2 con películas), `queueLote`, cambio
  `minimo` de `useComprobacionesTanda`, integración en `LibraryPage`, `LibraryTreeRow`, `PosterCard`, `LargePosterCard`,
  `lote.css`, README.
- **Aceptación**: marcar películas en las tres vistas (lista, pósters, pósters grandes); la selección sobrevive a cambiar de
  filtro, de vista y a aplicar una vista guardada, y se limpia al salir de Biblioteca; un lote de **una** película funciona; el
  Resumen lista nombre, avisos y veredicto por película; una película sin castellano, con nomenclatura bloqueada o con
  `audio_warning` sale saltada o desmarcada con motivo; «Subir» no se habilita con una comprobación vieja o fallida; «Subir» crea
  el lote y lleva a Subidas filtrado por él; la rejilla no vuelve a oscilar (comprobar a mano con 200 selecciones) y la lista sigue
  con 7 columnas.

### PR 5 — Series y temporadas en el lote (frontend + `nombre` en `run_upload_checks`)
- Expansión de series a temporadas en el paso 1, packs en el paso 2 (progreso por temporada, motivos de `seasonNotReadyReason` y
  del check `season_pack`), y `nombre` (`season_pack_title`) en la respuesta de `run_upload_checks` (compatible hacia atrás). Así
  se cierra también el pendiente de PLAN.md «en una tanda el Resumen no lista el nombre de cada torrent».
- **Aceptación**: marcar 2 series con 3 y 2 temporadas aptas → el paso 1 muestra 5 filas marcadas y las no aptas desmarcadas con
  su motivo; serie y una de sus temporadas marcadas a la vez no duplican; el Resumen enseña el nombre de cada pack; un lote mixto
  película + temporada funciona; el tope de 50 cuenta tras expandir.

### PR 6 — Panel: selección en «Listo para subir» (frontend)
- Casillas en `CarrilListo` y barra «Subir seleccionadas (N)»; petición enlazada por fila (`rec_request_id`), capítulos sueltos
  cuando la petición lo es; tour.
- **Aceptación**: los trabajos creados llevan su `request_item_id` y Subidas enseña la petición de cada uno; una petición de
  capítulo sube ese capítulo; una de serie entera expande a temporadas con la misma petición; dos peticiones sobre el mismo
  elemento salen como una fila con elección de petición; «Otras ideas» entra sin petición. Tests en `DashboardPage.test.tsx`.

### PR 7 (opcional, cada punto por separado y solo si Gabriel lo quiere)
- Notificación agregada del lote (`upload_batch_done`): tipo nuevo en `notification_center.EVENT_TYPES` y sus iconos en
  `NotificationBell.tsx` (comentario ≈ 30-33 de `notification_center.py`), `emit(..., dispatch=False)` para los trabajos del lote,
  y un gancho en `_finalize_job_status`/`_fail` que detecte el último del lote; ajustes de notificaciones y sus tests (pregunta 5).
- Freno tras X fallos seguidos con el mismo motivo (pregunta 4).
- Enlazar la petición abierta desde Biblioteca (pregunta 6).
- Capítulos sueltos de temporadas no aptas dentro del lote (pregunta 8).
- Selección en la página de Peticiones (pregunta 9).
- «Borrar lote» desde Subidas (pregunta 10).
- Unificar las tandas del asistente con `POST /uploads/lote` (reescribir los 3 tests de tanda de `UploadWizardModal.test.tsx`,
  ≈ 387-456 y ≈ 595-720) (pregunta 11).
- Que la sincronización de peticiones no cuente los `queued` como ocupados (pregunta 13).
- Salió al implementar (sin pregunta): en `encolar_lote`, guardar los `campos` y crear el trabajo en la misma transacción
  (hoy, si encolar falla justo después de guardarlos, la propuesta queda cambiada aunque el elemento salga saltado; ver
  #215); y elegir el proveedor de un pack cuyos capítulos traen proveedores distintos (hoy se salta: «Súbela suelta»). Los
  avisos propios de cada pack ya se enseñan (después del PR 6, ver PLAN.md).

---

## 7. Tests a añadir y guardas que hay que vigilar

### Backend (pytest)
Fixtures: `isolated_db` (autouse), `client`, `auth_headers`, `subidas_reales` y el autouse `_subidas_sin_hilo` de `conftest.py`
(desactiva `_lanzar_trabajo` salvo con `subidas_reales`). **`db_conn` y `puerta` no son compartidos**: `db_conn` se define en cada
fichero (p. ej. `test_upload_queue.py` ≈ 23) y `puerta` es local de `test_subida_sin_espera.py` (≈ 38-47); copiarlos o mover
`puerta` a `conftest.py`. Sin `subidas_reales`, `_EN_CURSO` está vacío y `retirar_de_la_cola` no hace nada: los tests de orden de
cancelación necesitan `subidas_reales` + `puerta`.
- `tests/test_lotes.py` (NUEVO):
  - Migración: columna e índice presentes; BD de esquema 51 migra; la columna sobrevive al cortocircuito de esquema (patrones de
    `test_subida_pasos_uploadrr.py` ≈ 110-122 y `test_upload_queue.py::test_season_overrides_column_survives_schema_version_short_circuit`
    ≈ 536). Ese patrón hace `DROP COLUMN`: con `idx_upload_jobs_lote` creado, SQLite falla («error in index … after drop
    column»), así que el test hace `DROP INDEX` antes.
  - `queue_upload_for_item(lote_id=…)` persiste; sin lote queda `NULL`; `queue_retry_for_job` hereda; `retry_upload_job` no.
  - `resumen_de_lote` cuenta solo **puntas de cadena** (un reintento no duplica el elemento; una subida suelta posterior del mismo
    elemento lo saca del lote); `contar_por_lote` agrupa; lote inexistente → `None`.
  - `encolar_lote`: orden de ids = orden de la lista; elemento inexistente / repetido / serie / `checks.ready` falso / película
    sin castellano / capítulo con su temporada / con trabajo activo / excepción inesperada simulada → `blocked` sin abortar y sin
    escrituras a medias; un elemento saltado con `campos` no caduca su propuesta; falta una clave → error y nada insertado; >50 →
    error; ninguno encolado → `lote_id None`; `campos` guarda la propuesta; `provider` solo llega a temporadas; segunda llamada
    idéntica (doble clic) salta todos.
  - `cancelar_lote`: con la puerta a 1, el `queued` sale de la cola antes de tocar al `running`; un `queued` que pasa a
    `preparing` entre lectura y escritura no se cancela con `solo_pendientes=True`; `solo_pendientes=False` cancela todos y en ese
    orden; un `running` que se completa entre medias no queda `cancelled`.
  - `reintentar_fallidas`: orden por id, hereda lote, salta activos, reanuda tras `reconcile_interrupted_jobs`.
  - Filtro `lote_id` en `list_upload_jobs` y `count_upload_jobs` (solo puntas).
- `tests/test_lotes_api.py` (NUEVO): 401 sin token; 422 con `lote_id` mal formado; `POST /uploads/lote` y las rutas de
  resumen/cancelar/reintentar; `GET /uploads?lote_id=…` y `lote_total` en la lista.
- No hace falta tocar `test_upload_queue.py` (no llama a `_insert_and_start_queued_job`) ni
  `test_marca_registro_y_listado_de_subidas.py` (no compara claves exactas); `test_eventos_subidas.py` ≈ 155 llama posicional y el
  kwarg nuevo no le afecta.
- Cobertura: `codecov/patch` ≥ 70 % sobre las líneas cambiadas de `emuwarez_uploadrr/` (los PR 1-3 son casi todo backend, así que
  hay que cubrir `lotes.py` entero).

### Frontend (vitest; usar `components/__tests__/dom.ts`)
- `utils/__tests__/lote.test.ts`: `expandirSeleccion` (también serie + su temporada), `razonNoSubible` (texto de película),
  `marcadaPorDefecto` (también `null`), `repetidoEnElLote`, `nuevoLoteId` (formato).
- `components/__tests__/SubidaPorLotesModal.test.tsx`: lote de una película; película marcada/no apta; paso 2 con comprobaciones y
  entorno una vez (`runUploadChecks` llamado con `'environment'` una sola vez) y nada comprobado mientras se está en el paso 1;
  volver al paso 1 y cambiar una película por otra recomprueba; nomenclatura bloqueada → saltada; `audio_warning` → desmarcada;
  `conclusionDuplicados` por fila; «Subir» deshabilitado con comprobación incompleta o fallida; «Subir» llama a `queueLote` con el
  orden, los `checks` y `campos` completos; resultado parcial lista los saltados; «Ver el lote» navega a Subidas; Escape tras
  subir limpia la selección.
- `components/__tests__/UploadWizardModal.test.tsx`: añadir que las dos tandas pasan el mismo `lote_id` (7.º argumento) y que una
  subida suelta no lo pasa.
- Selección: `useSeleccionLote` (tope, persistencia entre filtros y vistas guardadas), que la casilla de la lista no despliega la
  fila ni abre la ficha, y que `LibraryTreeRow` sigue con 7 `td`.
- `api/__tests__/uploads.test.ts`: la query string con `lote_id` (compara cadenas exactas) y el 7.º argumento de `queueUpload`.
- `pages/__tests__/UploadsPage.test.tsx` (NUEVO; UploadsPage no tiene test hoy): chip (y sin chip con `lote_total` 1), filtro por
  lote, «Quitar filtros», banner.
- `pages/__tests__/DashboardPage.test.tsx` (ya cubre «En curso» ≈ 89-116 y «Subir» en «Listo» ≈ 379-397): tope de filas vivas
  (PR 1) y selección del Panel (PR 6).
- `DetalleSubida.test.tsx`: «Parte de un lote · Ver el lote».

### Guardas de CLAUDE.md que se pueden romper
- `test_web_no_habla_sql.py` (mira todo `web/api/*.py` que llame a `.execute(`): ningún SQL en `web/api/uploads.py`; todo en
  `services/lotes.py` y `consultas.py`.
- `test_una_sola_puerta_a_settings.py`: `lotes.py` no consulta la tabla `settings`; el límite de paralelo se lee solo con
  `get_upload_max_concurrent` (y el frontend por `fetchSettings`); las precondiciones con `get_setting_canonical`, como hoy.
- `services/` nunca importa de `web/`: los modelos Pydantic viven en `web/schemas.py`, `lotes.py` trabaja con diccionarios.
- `test_copias_frontend.py`: añadir un caso que compare `MAX_ELEMENTOS_LOTE` de `utils/lote.ts` con `services/lotes.py` (patrón
  `_texto("utils/lote.ts")` + regex). **No se añade ningún estado ni fase nuevos**, así que los casos de vocabulario no cambian.
- `test_eventos_fases_3_y_4.py::test_no_han_aparecido_sondeos_nuevos`: no escribir `setInterval` en ficheros nuevos; el refresco
  del lote usa `useRefrescoPorAvisos(AVISOS_SUBIDA, …)`. No se añaden tipos de evento del bus (`test_eventos*.py` quedan igual).
- Migración: subir `SCHEMA_VERSION` y llamar a `_migrate_upload_jobs_lote` al final de la cascada (`preparar_base` hace la copia
  previa); `test_base_al_arrancar.py` usa `SCHEMA_VERSION - 1` y no necesita cambios.
- `ruff --select E9,F`: sin imports ni variables sin usar; `npm run lint` (ESLint solo con las reglas de react-hooks) y `tsc`
  vigilan lo suyo en TS.
- Reglas de CodeRabbit (`.coderabbit.yaml` ≈ 75), no tests: diálogos con `components/Modal.tsx`; colores y tamaños con tokens;
  texto de interfaz en español; sin estilos en línea (clases en `lote.css`); sin `console.log`.
- No hay OpenAPI generado ni instantánea de rutas (`test_openapi_schema` solo mira el título): las rutas nuevas no tocan nada más.

---

## 8. Riesgos y preguntas abiertas para Gabriel (por impacto)

### Preguntas (solo él puede decidir)

1. **¿Vale un lote sin edición por elemento?** (nombres automáticos; solo se sugiere proveedor a los WEB-DL sin proveedor; las
   filas con avisos de nombre llegan desmarcadas; editar = subir suelto). Es la decisión que más condiciona el coste y la calidad
   de los nombres. Recomendación: sí en v1, con el Resumen listando el nombre y los avisos de cada torrent. Si la respuesta es no,
   hay que generalizar `useAsistente` (colas heterogéneas, `sharedTitle` por serie, etc.), que es un proyecto aparte.
2. **Concurrencia y justicia**: ¿el lote respeta «Subidas en paralelo» tal cual (recomendado) o quieres un «lote de baja
   prioridad» para que una subida suelta lanzada después no espere a las 40 del lote? Y, ¿50 es buen tope?
3. **Duplicados y trumps**: ¿llegan desmarcados `duplicado` y `peor` (propuesto), o todos marcados y solo avisados?
4. **Fallo sistémico**: ¿seguir siempre con el resto (propuesto, con las claves comprobadas antes de encolar) o parar el lote tras
   X fallos seguidos con el mismo motivo? Hoy 40 fallos seguidos son 40 notificaciones.
5. **Notificaciones**: ¿una sola por lote (campana y Discord/Telegram) en lugar de una por subida? Requiere un tipo de notificación
   nuevo (`upload_batch_done`) y tocar Ajustes → Notificaciones.
6. **Petición desde Biblioteca**: hoy una subida desde Biblioteca nunca enlaza petición. ¿En un lote, enlazar la petición abierta
   de cada elemento si existe?
7. **Biblioteca y el rediseño P2**: #208 ya cambió la lista (línea de calidad, vistas guardadas, 7 columnas). ¿El lote antes o
   después de P2? Si es antes, las casillas se hacen en componentes sueltos (`CasillaLote`, `BarraLote`) para que P2 las
   recoloque; ¿casillas siempre visibles o un modo «Seleccionar»?
8. **Alcance de las series**: ¿vale «solo packs de temporada aptos» y mandar a subir suelto lo demás, o quieres capítulos sueltos
   de las temporadas no aptas dentro del lote?
9. **Peticiones**: ¿añadir la selección también a la página de Peticiones (un PR más pequeño sobre el mismo modal)?
10. **Ciclo de vida del lote**: ¿«Borrar lote» desde Subidas (borrar todas las cadenas terminadas)? Hoy se borra de una en una, y
    borrar una fila del lote borra también los intentos de ese elemento en otros lotes (D5).
11. **Unificar las tandas actuales** con el endpoint nuevo: mejora la coherencia pero obliga a reescribir los 3 tests de tanda del
    asistente.
12. **«Subidas en paralelo» = 0 (sin límite)**: ¿el lote solo avisa (propuesto), el servidor lo rechaza, o lo trata como 1?
13. **Sincronización de peticiones durante un lote**: hoy se para mientras haya cualquier trabajo activo, también en cola. ¿Se deja
    (un lote de 40 son horas sin peticiones nuevas) o se cambia `_motivo_ocupado` para no contar los `queued`, que no gastan
    llamadas? Recomendación: no contarlos, en un PR aparte.
14. **Publicaciones durante la serie de PRs**: tras PR 1-3 la publicación automática puede sacar el esquema 52 sin interfaz. ¿Se
    acepta, o se publica a mano hasta PR 4?

### Riesgos técnicos

- **Hilos y conexiones en espera**: 50 hilos esperando son ~17 conexiones/s constantes y ráfagas de miles al cancelar (§5.1). La
  caché de 1 s de PR 2 lo resuelve; medir con 50 trabajos falsos antes de subir el tope.
- **Reinicio a mitad de lote**: `reconcile_interrupted_jobs` deja todo `failed` («Interrumpido…»), sin notificaciones;
  «Reintentar fallidas» lo cura, pero el usuario ve de golpe N fallidas en Subidas.
- **Subidas muy largas encadenadas**: un lote de 40 con paralelo 1 puede tardar horas; no hay barra de progreso global (solo
  contadores), y durante ese tiempo no se sincronizan las peticiones (pregunta 13).
- **Encolar es lento tras un cambio de reglas**: reconstruir 50 propuestas caducadas puede tardar decenas de segundos (§3.2).
- **Disco**: cada trabajo prepara enlaces duros o copias por reflink en la carpeta de subidas; con paralelo > 1 y remux activo hay
  varias copias/escrituras a la vez. Conviene probarlo en el NAS.
- **Limitador de eMuwarez no cubre a Uploadrr-EMU** (ver §5.6). El riesgo real es subir «Subidas en paralelo», o dejarlo en 0, con
  lotes grandes.
- **La rejilla de pósters**: la casilla no puede alterar la medida de la tarjeta ni la barra el ancho del scroll (bug previo de
  React 185). Comprobar en `:edge` con 200 selecciones.
- **Selección obsoleta**: una sincronización puede borrar un elemento mientras el modal está abierto; el servidor devuelve ese
  elemento como `blocked` y el lote sigue.
- **Dos copias del mismo contenido**: si el nombre final coincide (misma calidad en dos instancias), el segundo trabajo fallaría
  con «es de la subida #N» (`_paso_preparar`); el paso 2 lo salta por nombre repetido. Si los nombres difieren (4K y 1080p), se
  suben las dos, que es lo correcto.
- **Cancelar a la vez que termina**: `cancel_upload_job` escribe `cancelled` sin condición en `running`/`preparing`; con lotes es
  más probable cruzarse con el final. `cancelar_lote` relee el estado; la cancelación de una fila suelta conserva la carrera
  existente.
- **Panel con >100 trabajos vivos**: sin el cambio de §4 el que sube se cae de «En curso».
- **No verificado**: no se ejecutó la suite ni se abrió la interfaz; el comportamiento de Uploadrr-EMU ante un duplicado real y el
  coste de 50 hilos en el NAS requieren una prueba manual antes de dar el lote por bueno.

---

## 9. Qué cambió en la revisión del 04/11 (contra `adef702`)

Errores corregidos:
- El `INSERT` de `_insert_and_start_queued_job` tiene 18 `?`, no 20.
- `provider` solo llega a temporadas; el de una película va en `campos`, que deben ser el juego completo (D10).
- El servidor no vuelve a comprobar el castellano de películas y capítulos: `encolar_lote` revisa `checks.ready` y repite el
  contenido (D11).
- `cancelar_lote` no puede llamar a `cancel_upload_job` para los pendientes (se reintenta como el estado nuevo); escritura
  condicionada propia.
- `retry_upload_job` no hereda el lote (crea filas `ready` que no cuentan como activas).
- Reiniciar y cancelar no notifican.
- `useComprobacionesTanda` no se reutiliza «tal cual»: no corre con un elemento y depende de `step`.
- El nombre de un pack no sale del check `season_pack`: `nombre` en `run_upload_checks` pasa a obligatorio en PR 5.
- «Ver el lote» desde el detalle no puede ir por `sessionStorage`.
- `LIST_COLUMNS` es 7; líneas de `LibraryPage` y `useAsistente` movidas; campos del Panel `season_number`/`episode_number`.
- La casilla de la lista debe evitar desplegar la fila, no solo abrir la ficha.
- El repetido entre instancias se decide por nombre final, no por resolución.
- `test_iconos_frontend.py` no vigila iconos de componentes; la regla real es `Modal.tsx` (CodeRabbit).
- CI elige los tests por contenido, no por nombre de fichero.
- `db_conn` y `puerta` no son fixtures compartidas.
- Son 3 los tests de tanda, no ~6.
- Los literales `50` y la regex van en una sola constante.

Omisiones añadidas:
- Precondiciones de claves una vez en el servidor.
- Orden de `encolar_lote` (guardar `campos` al final) y transacción por elemento.
- Capítulo con su temporada en el mismo lote.
- Filtro de puntas en el servidor para que filas y contadores coincidan.
- «Subidas en paralelo» = 0.
- La sincronización de peticiones parada.
- Coste real de los hilos en espera (la caché pasa a PR 2).
- Barra en el flujo y no fija; casilla arriba a la izquierda.
- Selección en filas hijas recursivas y en vistas planas con filtros.
- Panel: elemento real `library_target_id`, peticiones duplicadas, «Otras ideas» plegado.
- «En curso» con más de 100 vivos; el tope pasa a PR 1.
- Avisos de nombre y `getEmuComparison(id, tuya)`.
- Regla completa para habilitar «Subir».
- Cierre con `Modal.tsx` y `onDone` al encolar.
- Detalles de `UploadsPage` (`filtrando`, chip con `lote_total > 1`).
- Test de migración con `DROP INDEX`.
- Tests de `DashboardPage`, `DetalleSubida` y `api/uploads`.
- Docs de usuario (README, tour).
- Dependencias entre PR.
- Publicaciones automáticas a mitad.
- PR 1 más pequeño (el resumen y el banner pasan a PR 2).
- Las preguntas 12-14.

---

### Ficheros críticos para la implementación
- `emuwarez_uploadrr/services/upload_queue.py`
- `emuwarez_uploadrr/services/upload_execution/ciclo_de_vida.py`
- `emuwarez_uploadrr/web/api/uploads.py`
- `emuwarez_uploadrr/database.py`
- `frontend/src/components/asistente/useAsistente.ts` y `useComprobaciones.ts`
- `frontend/src/pages/UploadsPage.tsx`
- `frontend/src/pages/LibraryPage.tsx` y `components/LibraryTreeRow.tsx`
