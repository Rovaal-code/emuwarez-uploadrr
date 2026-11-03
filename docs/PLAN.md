# Plan de mejoras

Estado y siguiente paso del plan que salió de la revisión completa de octubre de 2026. Lo leen igual las sesiones
en local y en la nube: **actualízalo en el mismo PR que termina un paso** (marca lo hecho, añade lo aplazado).
Hallazgos y maquetas: https://claude.ai/artifact/PjPRTxSfEs3Y8aVtXzN32i

## Cómo se trabaja

- Reglas de PR, CodeRabbit y presupuesto de revisiones/CI: `CLAUDE.md` («Workflow» y «Saving review and CI budget»).
- Gabriel autoriza fusionar un PR cuando está listo:
  - CodeRabbit ha revisado su último commit (o su último comentario dice «No actionable comments» para ese commit)
    y no quedan comentarios «Outside diff» sin responder;
  - no quedan hilos de revisión abiertos;
  - todos los checks están en verde, con `codecov/patch` ≥ 70 %.
- Un PR cada vez, el más barato primero. El trabajo de código se puede delegar en agentes nuevos (con worktree),
  que cuestan menos que una conversación larga.
- En la nube (claude.ai/code) GraphQL está bloqueado:
  - abre PRs con `gh api repos/Kisnov/emuwarez-uploadrr/pulls`;
  - lee los hilos con `/pulls/N/ccr/review_threads`;
  - resuélvelos con `/pulls/N/ccr/comments/ID/resolve`.
- Mejor en local:
  - lo que necesita el NAS: subidas reales, `comprova-subides`, probar `:latest`;
  - el trabajo de interfaz que conviene ver en marcha.

## Hecho

- **Oleada 1 (01/11):** #106, #109, #111, #112, #114, #115, #116, #117. En resumen:
  - seguridad del acceso;
  - mantenimiento nocturno y copias automáticas;
  - subidas sin espera fija y cancelables en todo momento;
  - un solo proveedor para el pack y sus capítulos;
  - pistas sin idioma que avisan en vez de bloquear;
  - filtros de biblioteca.
- **Oleada 2 (01/11):**
  - #118: ajuste «No hacer nunca copias reflink».
  - #119: idiomas de pistas sin idioma también en packs, aviso cuando la fuente de MediaInfo no cuadra y la campana
    con tope de 15 s.
  - #120: ruff `E9,F` en la CI.
- **Versión 0.14.0** publicada con todo lo anterior.
- **Oleada 3, pendientes del asistente y de faltantes (#122):** nombres del pack que no se desfasan al cambiar el
  idioma (`versionDatosPack`), avisos del plan sin repetir en el paso de temporada y el total real de `/missing`.
- **Oleada 3, registro de ajustes:** `services/ajustes_registro.py` declara cada ajuste sencillo de Configuración
  (campo del API, clave, tipo, defecto, opciones o mínimo, secreto). De él salen los defectos y la conversión del
  GET, la validación y la escritura del PUT, el enmascarado y `es_secreto`. Lo que no cabe en un tipo sencillo
  (listas JSON, hosts de imágenes, eventos por canal) está en `FUERA_DEL_REGISTRO` de `web/api/settings.py`, y un
  test falla si aparece un campo nuevo que no esté en uno de los dos sitios. Las lecturas sueltas de sí/no fuera de
  la API (`series.ignore_specials` en seis sitios, `emu.add_logo`, `notify.*.enabled`…) ya pasan por
  `settings.leer_ajuste`, así que el defecto vive solo en el registro; un test falla si reaparece
  `(get_setting_canonical(…) or "true") != "false"` para una clave del registro.
- **Biblioteca, vista de pósters en negro al desplazarse deprisa:** `RejillaVirtual` repintaba sin fin si su medida
  oscilaba (error 185 de React) y la pantalla quedaba en negro hasta F5. Las correcciones seguidas ahora tienen
  tope, y cada página va dentro de `LimiteDeErrores`, que enseña un mensaje en vez de dejar la pantalla en negro.
  Cuando el tope corta una oscilación, la consola avisa una vez con «RejillaVirtual no se calma: 3×300 → 3×330 → …»
  y el ancho, el alto real, el zoom y el scroll; si el fallo es de otro componente, dirá «Error de render» con la
  pila de componentes. **Causa (vista en `:edge` con React 19, 03/11):** el aviso salió con «3×245 → 3×240 → …» y
  514 px de ancho. La rejilla mide el alto en la primera tarjeta que pinta y cuál es la primera depende de ese alto,
  y las tarjetas no medían lo mismo: la `img` iba dentro de un marco `aspect-ratio: 2/3` y, una vez cargada, un
  póster que no fuera 2:3 (o el hueco de línea de una `img` en línea) alargaba el marco (240, 244, 257, 277 px). Ahora
  la imagen va en `position: absolute` dentro del marco (`.bib-tarjeta-marco` y `.poster-grande-marco`) y el alto lo
  fija solo `aspect-ratio`: todas miden 240 (pósters pequeños) o 370 (grandes) a ese ancho. Comprobado en el
  navegador con el CSS real, antes y después. Pendiente: ver que el aviso ya no sale en la aplicación real.
- **Iconos de los sitios, dentro del proyecto:** los de proveedores de imágenes y de vídeo, eMuwarez y las webs de las
  fichas (TMDb, IMDb, TVDB, MAL, TVmaze) son ficheros en `frontend/src/assets/iconos/<dominio>.<ext>` (50 de 52 sitios; 240 KB),
  y `Favicon` los pinta sin pedir nada fuera: antes cada navegador los pedía al sitio y a Google, y con un DNS que bloquea
  esos nombres salían decenas de `ERR_NAME_NOT_RESOLVED` en Configuración. Los logos no cambian y la lista es cerrada, así
  que no hace falta servidor (se probó y se descartó: ~600 líneas por unas imágenes). Para un proveedor nuevo: añadirlo a
  su lista y correr `python scripts/descargar_iconos.py` (baja el que falta y avisa de lo que no encuentra);
  `tests/test_iconos_frontend.py` falla si falta el icono de un sitio de las listas, si sobra uno, o si pesa más de 20 KB.
  Sin icono, y por tanto con el de reserva de siempre: Crunchyroll y VRV. El campo `favicon` de `image_hosts` ya solo lo
  usa el script.
- **Oleada 3, subida por pasos (#127):** `_run_queued_job` es un bucle sobre `PASOS` (`upload_queue.py`): comprobar,
  nombre, preparar e iniciar, cada uno con su `stage` (que es su punto de cancelación), su fila de Fases y lo que
  deja en `_Trabajo` para el siguiente. Mismo comportamiento que antes; lo fijan
  `test_la_preparacion_recorre_los_pasos_en_orden` y `test_cancelar_para_la_preparacion_en_el_siguiente_punto`.
- **Oleada 3, partir upload_execution.py (#130):** pasa a ser el paquete `services/upload_execution/`: `comun` (constantes, fases,
  secretos), `consultas` (leer y validar), `registro` (logs y artefactos), `estado` (transiciones y avisos), `config`
  (config.yaml compartido), `concurrencia` (puerta de «Subidas en paralelo»), `progreso` (fases), `procesos`
  (subprocesos en marcha), `ejecucion` (el subproceso y `start_upload_job`) y `ciclo_de_vida` (reintentar, cancelar,
  borrar). `__init__` re-exporta todo: `from ...services.upload_execution import X` sigue igual, pero un test que
  parchee un nombre debe hacerlo en el módulo que lo usa.
- **Oleada 3, partir cli.py (#129):** `cli.py` queda como punto de entrada (`main`, `modern_main` y el despacho); los comandos
  viven en el paquete `comandos/`: `parser.py` (`build_parser`), `comunes.py` (tabla, traducción de filtros, conexión),
  `biblioteca.py` (instancias, sync, biblioteca, peticiones, faltantes, *arr), `nomenclatura.py` (nomenclatura y título
  MKV), `subida.py` (subida, tareas, logs), `web.py` (comandos `web`) y `mantenimiento.py` (mantenimiento y demo).
  `emuwarez_uploadrr.cli:main` sigue siendo el entry point; el código se movió sin cambios (`--help` idéntico).
- **Oleada 3, Configuración partida (#131):** `pages/SettingsPage.tsx` queda en el marco (pestañas, aviso y botón de
  guardar) y lo demás vive en `pages/ajustes/`: una pestaña por fichero (`ConfigTab`, `NotificationsTab`,
  `DiagnosticsTab`, `BackupTab`) y una tarjeta por fichero en `config/` y `diagnostico/`. El formulario de la pestaña
  Configuración es `config/useConfigForm.ts`, compartido por sus tarjetas; lo que solo toca una (pruebas de
  conexión, modal de claves de imágenes) está en su tarjeta. Comportamiento igual: lo fija
  `pages/__tests__/SettingsPage.test.tsx` (jsdom, nueva dependencia de desarrollo).
- **Oleada 3, estilos de Configuración a clases (#136):** `SettingsPage` y `pages/ajustes/` ya no llevan estilos en línea,
  salvo los colores calculados (resultado de una prueba, mensaje de guardado) y el de un icono. Las clases están
  en `styles/ajustes.css` (prefijo `aj-`). Mismo aspecto.
- **Oleada 3, subida por pasos con reintento (#126):** sobre `PASOS` (#127), cada subida enseña sus cuatro pasos con
  nombre (comprobar y poner el nombre, preparar los ficheros, verificar antes de subir, subir con Uploadrr) y cuál se
  paró (`upload_jobs.etapa_parada`, `services/subida_pasos.py`). Un reintento de una subida que ya había preparado los ficheros reanuda desde la
  verificación y reutiliza la preparación si sigue valiendo en disco; «Reintentar desde el principio» lo rehace todo.
  El reintento ahora también conserva las elecciones del pack (`season_overrides_json`).
- **Oleada 3, partir library.py (#128):** `services/library.py` pasa a ser el paquete `services/library/`, sin cambiar lo que
  hace: `sync` (alta y sincronización con Radarr/Sonarr, avisos de faltantes, progreso y candado), `castellano`
  (audio y subtítulos en castellano), `listado` (filtros, orden, paginación, recuentos y faltantes), `resync`
  (releer un elemento tras renombrar), `panel` (datos del Dashboard), `rollups` (agregados de series y temporadas) y
  `valores` (valores de filtro con su caché). `__init__.py` reexporta todo, así que `from ...library import X` sigue
  valiendo. Lo que un test parchea ahora se parchea en el módulo que lo usa (`library.sync.publicar`,
  `library.valores._VALORES_DE_FILTRO_SEGUNDOS`…).
- **Oleada 3, asistente de subida partido (#132):** `UploadWizardModal.tsx` queda en el marco (pasos y cierre) y lo
  demás vive en `components/asistente/`: el estado y la lógica en `useAsistente.ts` (con `useComprobaciones.ts` y
  `useDetallesTemporada.ts`), un componente por paso (`PasoSeleccion`, `PasoArchivo`, `PasoTemporada`, `PasoSubida`,
  `PasoSubidaTanda`) y las piezas compartidas (`RemuxTable`, `MediaInfoTable`, `Capitulos`, `piezas`,
  `constantes`). Comportamiento igual: lo fija `components/__tests__/UploadWizardModal.test.tsx` (jsdom). Arreglado
  de paso: «Ver nombre de todos los capítulos» y «Ver Pistas», si estaban abiertos al cambiar el idioma del pack, se
  recargan con el idioma confirmado en vez de quedarse vacíos.
- **Oleada 3, un solo limitador para eMuwarez (#134):** toda petición a la API de eMuwarez pasa por
  `integrations/emu_limitador.py` (los conectores de `emu.py` y la prueba de conexión de `integration_tests.py`):
  ventana deslizante de 60 s por API key, planificada para 28 de las 30 que deja eMuwarez. Los recorridos largos
  (catálogo y peticiones) se quedan en 20 por minuto entre todos; los 8 huecos restantes son para las consultas
  sueltas (perfil, probar conexión, detalle, comprobación de antes de subir), que no se ponen a la cola de un
  catálogo y, si tendrían que esperar más de 15 s, fallan con un mensaje claro. Un 429 pausa 60 s a todos los que
  usan esa clave, no solo al que lo recibió. Se van las pausas sueltas (`EMU_MIN_REQUEST_INTERVAL`,
  `EMU_PETICIONES_INTERVALO`, `min_interval`). En los tests, un fixture de `conftest.py` le da a cada test su
  limitador con un reloj falso: nada duerme de verdad.
- **Oleada 3, httpx (#135):** las peticiones salientes (Radarr, Sonarr, eMuwarez, TMDb, qBittorrent, proveedores de imágenes,
  Discord, Telegram, manifiesto de versiones) dejan urllib y salen todas por `integrations/http_cliente.py` (`pedir`),
  con dos clientes httpx compartidos (con y sin verificar el certificado) que reaprovechan conexiones. Hereda lo de
  urllib: certificados del sistema, redirecciones seguidas (hasta 10), sin cookies salvo la sesión propia del inicio
  de sesión de qBittorrent, proxies del entorno, `timeout` por fase y el Content-Type de formulario por defecto.
  `request_json` mantiene el plazo de reloj (`con_plazo`, `timeout` + 5 s, DNS incluido), `IntegrationError` con su
  `.status` y los mismos mensajes sin la URL; httpx y httpcore no apuntan sus peticiones (llevarían la clave). httpx
  pasa al extra `web` con su pin. En los tests, un solo servidor falso (`tests/http_falso.py`, fixture `http_falso`,
  `httpx.MockTransport`) sustituye a los parches de `urlopen`, y `test_ninguna_peticion_sale_por_otro_lado` vigila
  que nadie más importe urllib.request, http.client ni httpx.
- **Oleada 3, estilos del asistente a clases (#137):** `UploadWizardModal.tsx` y `components/asistente/` ya no llevan
  `style={{` (de 180 a 3): las clases `asist-*` están en `styles/asistente.css`. Siguen en línea los tres
  `width: '100%'` de `<Tooltip style>` en `PasoSeleccion` y los dos `tituloStyle` de los modales de pistas, porque
  `Tooltip` y `Modal` solo admiten objeto de estilo.
- **Oleada 3, ESLint `react-hooks` (#142):** el frontend tiene `eslint.config.js` con solo `rules-of-hooks` y `exhaustive-deps`
  (nada más), `npm run lint` (`--max-warnings 0`) y un paso en el job `frontend` de la CI. Todo `eslint-disable` de
  esas reglas lleva su motivo tras `--`; ESLint avisa de los que sobran. Una dependencia que falta no se añade a
  ciegas: un efecto que se recrea en cada pintado puede crear un bucle (como el de `RejillaVirtual`).
- **Oleada 3, segunda tanda de estilos a clases:** mismo método que en Configuración y el asistente (sin cambio
  visual, solo tokens y variables que ya existían; una hoja por pantalla, importada en `main.tsx` tras las demás):
  - #144: Peticiones (`styles/peticiones.css`);
  - #143: detalle de subida (`styles/detalle-subida.css`);
  - #148: Guía (`styles/guia.css`);
  - #149: asistente de primera configuración, `SetupWizard` (`styles/setup.css`);
  - #150: lista de Subidas (`styles/subidas.css`);
  - #151: Panel, `DashboardPage` (`styles/panel.css`, prefijo `panel-`): de 58 `style={{` a 2 (la barra de progreso
    con `scaleX` calculado y la transición de la fila que se despide).
  Siguen en línea, con comentario, los valores calculados. La comparación visual con capturas de antes y después
  está pendiente.
- **Oleada 4, Ctrl+K:** `components/CommandPalette.tsx` (Ctrl+K o Cmd+K desde cualquier sección, en `AppShell`): escribes
  y salta a una sección o abre la ficha de una película o serie de la Biblioteca (`/library/:id`, por el mismo camino
  que la campana, con la pregunta de «cambios sin guardar»). Flechas, Intro y Escape. Lógica pura en `utils/paleta.ts`.
  Busca solo el nivel de arriba (películas y series), con 8 resultados como máximo.
- **Oleada 4, carril de «listas» por recompensa:** el Panel abre, encima de la cuadrícula, con «Peticiones listas para
  subir»: una fila con las cinco (tres con la interfaz estrecha) de más recompensa, en una línea cada una (título con
  año o temporada y puntos), y cuántas listas hay. Cada una es un botón que abre su ficha en Peticiones, como la
  campana. Sin ninguna lista no se pinta. Los datos salen de `GET /api/requests?readiness=ready_to_upload&sort=points_desc`
  (filtro `readiness` nuevo sobre la preparación ya guardada, el mismo criterio de la lista y del aviso
  `request_new_ready`) y se recargan con el resto del Panel y al terminar una subida. Sin «Ver todas»: Peticiones
  no deja fijar el orden ni filtrar por preparación desde fuera. Visto en el navegador con datos de prueba a 1440 y
  1280 px. A 1280×800 la cuadrícula ya iba justa (las cifras van de tres en tres) y el carril le quita unos 115 px
  a Recomendaciones.
- **Pendientes pequeños de la oleada 4:** el build usa `build.rolldownOptions.output.codeSplitting` (el chunk `react` sale igual)
  en vez del `manualChunks` obsoleto; y una selección vacía de eventos guardada (`notify.<canal>.events` = "") ya
  no se lee como «sin configurar»: ese canal no recibe ningún evento (`channel_events` lee la clave tal cual).
- **Oleada 3, última tanda de estilos y HTTPS (#141):** `LoginPage` y los componentes menores pasan a clases
  (`styles/paginas.css`, `styles/componentes-menores.css`, prefijo `menores-`); de 92 `style={{` quedan 67, todos
  dinámicos. «Probar conexión» de eMuwarez rechaza una URL `http://` (estado `insecure_url`) antes de enviar la API
  key, sin excepción para loopback, y no sigue una redirección que baje a `http://`.
- **Oleada 3, tercera tanda de estilos a clases:** mismo método (sin cambio visual, solo tokens ya existentes, una hoja
  por grupo, importadas al final de `main.tsx`; `Modal` pasa de `style` a `className`):
  - `styles/biblioteca.css` (`bib-`): `LibraryPage` y `LibraryTreeRow` (de 66 `style={{` a 5: sangrías y anchos calculados);
  - `styles/tareas-instancias.css`: `TasksPage` e `InstancesPage` (de 53 a 4: colores de estado);
  - `styles/comparacion.css` (`comp-`): `EmuComparisonSection` y `SourceComparisonModal` (de 59 a 1);
  - `styles/nomenclatura.css`: `NomenclatureModal` y `UploadPreflightModal` (de 54 a 0);
  - `styles/componentes.css`: `DetailCard`, `LogsPage`, `ProviderPriorityPicker`, `RequestFormModal`, `LibraryDetailPage`,
    `LargePosterCard`, `EmuSyncButton`, `DeleteUploadModal` y `LibraryChildrenSection` (de 99 a 8). El hover de
    `EmuSyncButton` pasó de estado de React a `:hover` en CSS.
- **Oleada 3, arreglos sueltos:**
  - #138: «Probar conexión» de eMuwarez no bloquea la base y acepta una clave nueva sin URL;
  - #139 y #147: el asistente de subida aguanta los fallos de red y las comprobaciones que llegan tarde (en una
    tanda, una comprobación vieja o fallida no habilita «Subir todas»; «Reintentar» solo rehace los capítulos que
    fallaron; cambiar el Proveedor vuelve a comprobar esa temporada);
  - #145: Configuración no deja guardar si la carga falló (ofrece reintentar) ni pierde lo editado al guardar las
    rutas;
  - #146: la base ya no guarda la clave del indexador que traen la cola y el historial de Radarr/Sonarr.
- **Oleada 4, primera tanda:**
  - #155: en una tanda del asistente se salta un capítulo con la nomenclatura bloqueada y se cuenta como fallido, y una
    película o un pack enseñan el error si fallan las comprobaciones (#152); Configuración descarta una lectura que
    llega tarde y no deja guardar tras una recarga fallida (#153).
  - #156: Vite 8.3, plugin-react 6 y Vitest 5 (React y TypeScript siguen igual). Solo afecta a la herramienta: el
    `vite build` pasa de ~2,5 s a ~1,6 s y el bundle pesa lo mismo. `@codecov/vite-plugin` aún no declara Vite 8 y
    lleva un `override` en `package.json`.
  - #157 (N14): la tarea «Vigilar instancias» mira cada 5 min si responden Radarr y Sonarr y sincroniza la que vuelve
    tras estar caída (nunca a la primera mirada de una que ya estaba viva). El estado va en memoria, para que un
    reinicio no lance una sincronización en cadena; una misma instancia no se sincroniza más de una vez cada 15 min.
    Se apaga en Configuración → Otros (`biblioteca.sincronizar_al_volver`, activado).
  - #158 (N8 y N9): «Rellenar petición» en Subidas y en el detalle de una subida completada que cubría una petición:
    copia la URL del torrent y abre la petición (si el navegador no deja copiar, un modal enseña la URL). Aviso
    `request_new_ready` cuando la sincronización diaria encuentra una petición nueva que ya se puede rellenar: uno
    por petición y en un solo mensaje; no avisa en la primera sincronización ni sobre una base incompleta (migración
    49, `request_items.aviso_pendiente`, que también lo añade a la campana de quien ya guardó sus eventos).
  - #159 (N12): migración 50 (`perfil_historial`): una instantánea al día de ratio, subido, bajado y bonus, que se
    guarda donde se guarda el perfil y se vacía si el perfil pasa a ser de otro usuario. Página Estadísticas con
    gráficos SVG a mano y una tabla con los datos. No guarda Hit & Run: es un contador que no cambia y ya sale en el
    perfil del Panel.
  - #160 (N11): `GET /api/uploads/seeding` lee de qBittorrent el estado, la ratio y lo subido de cada subida
    completada (columna en Subidas y bloque en el detalle). Solo lectura, caché de 60 s, sin migración. Casa por la
    ruta de contenido (la app no guarda el info-hash) y, si es ambiguo, dice «No se encuentra» en vez de adivinar.
  - #161 (N16): `GET /api/widget` con cinco contadores para el widget `customapi` de Homepage y su propia clave de
    solo lectura (`X-Api-Key` o `Bearer`; la base solo guarda su hash). Se genera en Configuración y solo abre ese
    endpoint; sin clave responde 404. Ejemplo de `services.yaml` en `docs/DEPLOYMENT_DOCKER.md`.
  - «Probar conexión» de eMuwarez ya no sigue una redirección a otro servidor aunque sea por `https` (la clave va en
    la query): cada salto debe tener el mismo esquema, nombre y puerto que la petición original (el 443 de https
    equivale a no ponerlo; `www.` y otro puerto cuentan como otro servidor). Si el sitio redirige el dominio pelado
    a `www.`, el resultado dice «redirección a otro servidor (www…)» y hay que guardar esa URL en Configuración.
  - React 19.3 (`react`, `react-dom` y sus tipos). Solo hizo falta tipar los `RefObject` de `FilasVirtuales` como
    `RefObject<HTMLElement | null>` (en React 19 `useRef<T>(null)` devuelve `RefObject<T | null>`); el código ya
    trataba `.current` como posiblemente nulo y no cambia de comportamiento. El chunk `react` del bundle pasa de
    139,84 kB (gzip 45,32) a 218,78 kB (gzip 68,26); `index` queda igual. Pendiente de ver en el navegador:
    Biblioteca con scroll rápido en pósters (`RejillaVirtual`).

## Siguiente (oleada 3)

1. Comparar con capturas de antes y después las tandas de estilos a clases (Configuración, asistente, Peticiones, detalle
   de subida, Guía, `SetupWizard`, Subidas, Panel, Biblioteca, Tareas, Instancias, comparación, modales y componentes).
   Ya no queda nada convertible: los 67 `style={{` que siguen en línea son valores calculados (colores de estado,
   sangrías, posiciones, `transform`) o van a `Tooltip`/`Modal`, que solo admiten un objeto de estilo.
2. Pequeños pendientes de la primera tanda de la oleada 4:
   - probar en el NAS el seeding (#160): que el estado, la ratio y los bytes cuadren con la WebUI de qBittorrent y que
     el casamiento por ruta funcione con la carpeta de subidas que ve qBittorrent;
   - ver en marcha la tarjeta del widget (#161) y el aviso de peticiones nuevas (#158). «Rellenar petición» y
     Estadísticas sí se vieron en una instancia local con datos de prueba; de ahí salió el arreglo del modal, que
     quedaba atrapado bajo la columna fija de acciones.

## Oleada 4

- React 19 y TypeScript 7 (Vite 8, Vitest 5 y React 19 ya están; falta TypeScript 7).
- Funciones nuevas que faltan:
  - subida por lotes;
  - resumen de duplicados y trumps;
  - «Mejoras posibles»;
  - estadísticas del tracker por subida.
- Rediseño de la interfaz: Hoy, detalle de subida, resumen del asistente, Biblioteca, Peticiones y Configuración.
  Espera las capturas de Gabriel; las funciones que tocan Biblioteca, Panel y el asistente van junto a él.

## Aplazado / ideas

- Reanudar a mitad de Uploadrr-EMU (capturas, torrent, subida al tracker): hace falta que el subproceso diga qué
  pasos terminó y cambiar el contrato en los dos repositorios a la vez. Hoy un reintento reanuda solo en la verificación.
- Límite de concurrencia compartido entre el CLI y el servidor (hoy cada proceso tiene el suyo, en memoria). Hace
  falta un cerrojo en fichero o en la base.
- Sugerencia de proveedor por TMDb con el `tmdb_id` de la serie para episodios antiguos sin el suyo.

## Datos útiles

- NAS UGREEN DXP4800; `/data` es btrfs y reflink funciona.
- Los nombres de la biblioteca no cambian fuera de la carpeta de subidas. Las subidas van a `UPLOADRR_UPLOADS_DIR`
  con nombre de eMuwarez: enlace duro, o copia reflink cuando hay que editar un fichero compartido (salvo que el
  ajuste lo prohíba).
- Cleanuparr «unlinked» solo vigila las categorías de radarr y sonarr.
