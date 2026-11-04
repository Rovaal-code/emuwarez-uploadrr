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
  navegador con el CSS real, antes y después. Comprobado en la aplicación real el 03/11: el aviso no sale.
- **Sugerencia de proveedor por TMDb para episodios y temporadas antiguos:** si un episodio o una temporada no traen
  `tmdb_id` (la sincronización ya se lo copia de la serie, pero los guardados antes de eso no lo tienen),
  `suggest_provider_for_item` usa el de la serie de la que cuelgan (`_tmdb_id_de_la_serie`, por `parent_id`, solo si el
  antepasado es una serie) y pregunta a TMDb como serie. Un `tmdb_id` propio sigue ganando, y sin ninguno en la cadena no
  se sugiere nada.
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
  se hizo el 03/11: sin diferencias.
- **Oleada 4, Ctrl+K:** `components/CommandPalette.tsx` (Ctrl+K o Cmd+K desde cualquier sección, en `AppShell`): escribes
  y salta a una sección o abre la ficha de una película o serie de la Biblioteca (`/library/:id`, por el mismo camino
  que la campana, con la pregunta de «cambios sin guardar»). Flechas, Intro y Escape. Lógica pura en `utils/paleta.ts`.
  Busca solo el nivel de arriba (películas y series), con 8 resultados como máximo.
- **Oleada 4, Recomendaciones por recompensa:** en el Panel, el grupo 1 de Recomendaciones (cada petición de eMuwarez
  con una coincidencia *Compatible*) va ordenado por recompensa: la que más paga primero, las que no dicen puntos al
  final y, a igual recompensa, la más nueva delante (el orden de «Puntos / recompensa» en Peticiones). La tabla tiene
  una columna «Recompensa» (la moneda de Peticiones y los puntos; «—» en una petición sin puntos y en los grupos 2 y 3,
  que no son peticiones); la API la da como `rec_points`. Además deja fuera las peticiones cuya copia no tiene
  castellano (preparación guardada `no_castellano`, la misma de Peticiones y del aviso): eMuwarez las rechazaría. Una
  que aún no se ha evaluado (`NULL`) sigue saliendo. Los grupos 2 y 3 no cambian. Sustituye al carril «Peticiones
  listas para subir» que se puso encima de la cuadrícula: solo enseñaba las `ready_to_upload`, un estado mucho más
  estricto que «Compatible», así que en la práctica salía vacío y repetía Recomendaciones. Se quitó con su filtro
  `readiness` de `GET /api/requests`. Visto en el navegador con datos de prueba: a 1440×900 cabe (la columna lleva
  6 px de relleno lateral para no empujar fuera «Actividad de subida») y el título pasa de unos 240 a 153 px, así que
  los largos van en dos o tres líneas. A 1280×800 (modo estrecho) la cuadrícula ya se salía por la derecha desde antes:
  la primera columna era `1fr` y no podía encoger por debajo de la tabla (~900 px), así que «Actividad de subida» quedaba
  cortada. Con `minmax(0, 1fr)` en `.dashboard-grid` (y su variante `.ui-estrecha`) la columna encoge, la tabla se desplaza
  dentro de su panel y la columna derecha se ve entera.
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
    Probado en el NAS (03/11): la ratio que enseña la app es la misma que la de la WebUI de qBittorrent.
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
    139,84 kB (gzip 45,32) a 218,78 kB (gzip 68,26); `index` queda igual. Comprobado en el navegador el 03/11:
    Biblioteca con scroll rápido en pósters (`RejillaVirtual`) va bien.
- **Peticiones sin castellano no están «listas para subir»:** eMuwarez es un tracker español y solo admite contenido con
  castellano, en el audio o, si no, en los subtítulos (la regla de la comprobación «Tiene castellano» de la subida y de
  `has_spanish_ok` en la biblioteca). El criterio de preparación de las peticiones no la miraba, así que el carril del Panel,
  el aviso de peticiones nuevas y el contador del widget podían contar una copia que la subida iba a rechazar. Ahora
  `_evaluate_readiness` da el estado `no_castellano` («Sin castellano», acción «Revisar en Radarr/Sonarr») cuando
  `has_spanish_ok = 0`; si aún no se ha leído (`NULL`) todo sigue igual y lo decide la comprobación previa.
- **La ficha de Biblioteca dice qué petición tiene:** la fila «Petición» enseña, además de la insignia, quién la pidió
  (si eMuwarez enseña el autor), la recompensa, «Ver petición» (la abre en Peticiones, como la campana) y el icono de
  eMuwarez con su página. Una temporada o un capítulo sin petición propia enseñan la de su temporada o su serie si los
  cubre («Petición de la serie», con el estado de la serie; su estado guardado sigue siendo «Sin petición»), y una
  serie o temporada lista en una fila aparte las de sus temporadas o capítulos («Peticiones de sus temporadas»: cada
  una con su estado y un enlace a Peticiones). Solo en `GET /api/library/{id}` (`peticion`, `peticiones_debajo`), no
  en la lista; la URL va sin consulta ni usuario.

- **Reanudar a mitad de Uploadrr-EMU (contrato cambiado en los dos repos):** Uploadrr-EMU dice qué pasos terminó con una
  línea fija por paso, `Step done: screenshots` y `Step done: torrent` (la ficha, `Torrent URL:`, cierra la subida al
  tracker), y la app los apunta en `upload_jobs.pasos_uploadrr_json` (migración 51). Un reintento que reutiliza los
  ficheros de la subida anterior, y cuya anterior llegó a lanzar Uploadrr-EMU (su `tmp` es el de esos ficheros), lo
  lanza con `--resume` (columna `reanuda_uploadrr`) y este reutiliza las
  capturas y el torrent marcados como hechos; el detalle de la subida enseña los subpasos (capturas, torrent, subida a
  eMuwarez) y el botón de reintentar dice lo que no repetirá. **Cambio de comportamiento:** sin `--resume`, Uploadrr-EMU
  borra su `tmp/<nombre>` al empezar cada elemento, así que unos ficheros rehechos con el mismo nombre ya no se
  encuentran con un `BASE.torrent` o unas capturas viejas. Si la ficha ya estaba en eMuwarez (`tracker` hecho) el
  reintento no ofrece reutilizar nada: chocaría con el duplicado. Aplazado: que un reintento recupere solo el añadido a
  qBittorrent de una subida que ya estaba en eMuwarez.
- **Oleada 3 y 4, comprobación visual (03/11):** dos instancias en Docker con los mismos datos de prueba, una con el
  commit anterior a las tandas de estilos (19a3add, esquema 47, padre de #137) y otra con `master` (f3fef2c, esquema 50).
  Se compararon capturas y las ~100 propiedades computadas y el rectángulo de cada elemento de Panel, Biblioteca (póster,
  póster grande, lista, árbol, ficha), Peticiones y su detalle, Subidas y su detalle, Guía, Tareas, Instancias, Logs,
  Configuración, asistente de subida (película y temporada), modales, campana, tour y asistente de primera
  configuración, a 1440×900 y, salvo Setup y tour, a 1280×800. Las tandas de estilos a clases no cambian nada:
  Guía, Instancias, detalle de petición, Tareas, Setup, modales, pasos del asistente, Configuración y la lista y el
  árbol de Biblioteca salen idénticos; el resto de diferencias vienen de funciones nuevas. Lo demás:
  - widget de Homepage (#161): la clave se genera y se enseña una sola vez; `/api/widget` da 404 sin clave configurada,
    401 con clave mala, sin cabecera o por `?api_key=`, y 200 con `X-Api-Key` o `Bearer`; la clave no abre ningún otro
    endpoint;
  - aviso de peticiones nuevas (#158): sale en la campana, con contador, y lleva a Peticiones;
  - Biblioteca en pósters con React 19 y scroll rápido (rueda, barra y saltos, de 390 a 1440 px): el aviso «RejillaVirtual
    no se calma» y el error 185 no salen, y la altura del scroller no oscila.
  Sin ver: Setup pasos 4 a 9 por el flujo real (el paso 3 pide una clave real de eMuwarez), una subida real de extremo a
  extremo, hover y foco, y los pasos 4 a 6 del asistente de temporada.
- **TypeScript 7 (#178):** `tsc` pasa de ~4,7 s a ~1,3 s y `npm run build` de 5,5 s a 1,4 s; mismo bundle. `typescript`
  apunta a `npm:@typescript/typescript6` porque typescript-eslint aún no admite TS 7.0 (no hay API JS hasta 7.1, issue
  typescript-eslint#10940) y `@typescript/native` es el TS 7 que usa `tsc`; se puede volver a un solo `typescript` cuando
  typescript-eslint admita 7.1. `frontend/src/vite-env.d.ts` existe porque TS 7 comprueba por defecto los `import './x.css'`.
- **Oleada 4, rediseño P1: el Panel (#189, #190, #192):** sigue llamándose «Panel» (Gabriel descartó «Hoy»; los ficheros `hoy/`
  y `AvisoHoy` conservan el nombre interno).
  - Cabecera: el perfil de eMuwarez (`CuentaEmu`), un solo «Sincronizar todo» y «Última sincronización… · próxima…».
    «Sincronizar todo» encadena biblioteca, catálogo incremental y peticiones con la misma barra de la topbar; se salta lo que
    eMuwarez limita a una vez por hora, un 429 del catálogo no corta la cadena y cualquier otro error sí.
  - Dos carriles, «Listo para subir» (las peticiones *Compatible* por recompensa; «Subir» abre el asistente sobre lo que la
    petición cubre, con un plegable «Otras ideas (sin petición)» para los grupos 2 y 3 de Recomendaciones) y «En curso».
  - «Necesita atención» es una banda fina bajo los carriles: una línea («Todo en orden») si no hay nada; con avisos, cuatro en dos
    columnas y «y N más»: instancias caídas (vigilancia #157; «no responde», no «apagada desde ayer», porque su estado vive en
    memoria), subidas fallidas de 3 días y versión nueva. Sin vigilancia activada no afirma ninguna caída. `aria-live="polite"`.
  - Franja de cinco cifras (en biblioteca, en disco, únicos sin subir, peticiones abiertas, tus subidas) con el `StatCard` de
    siempre, en una fila. Las otras diez tarjetas, las de peticiones incluidas, están arriba de Estadísticas.
  - Se van «Últimas tareas ejecutadas» (siguen en Tareas), «Conexiones» y «Actividad de subida» como estaban: su contenido pasa a los carriles.
  - Un solo `Tooltip` global se abre por arriba si no cabe por abajo; `StatCard` con `info` pasa a `role="group"` con nombre.
  - #189: CPU, RAM y disco, en una línea al pie de la barra lateral (disco = el sistema de ficheros de la carpeta de subidas).
  - #192: los recuadres del HUD pasan de esquinas cortadas a redondeadas (`--radius-card` 12 px, `--radius-small` 7 px) y con
    borde y resplandor más suaves, en toda la app.
  - Sigue sin verse: el perfil real a 2000 px, la banda con más de cuatro instancias caídas y con el tour abierto.
- **Oleada 4, rediseño P4: el detalle de una subida (#195):** abre por el resultado.
  - Completada: «Subido a eMuwarez» con la insignia de seeding (las mismas `seedingDe`/`claseSeeding` del bloque #160), una
    cuadrícula de datos y «Ver en eMuwarez», «Rellenar petición», «Ver en Biblioteca» y «Ver registro». Las fases quedan tras «Ver
    todas las fases».
  - «Dónde se fue el tiempo»: una barra por fase, proporcional al total y con el tiempo escrito (la barra es `aria-hidden`), a partir
    del `progress_json`; «Pistas» dice «omitida» si el remux se omitió. Una fase sin marcas de tiempo enseña solo su estado.
  - En curso, fallida o cancelada: mismo diseño con el problema primero (estado, motivo y reintento #126 arriba); el motivo
    (`error_message`) por fin se ve en esta pantalla. El tiempo transcurrido va fuera de la región `aria-live`.
  - No tiene «Abrir en qBittorrent»: la URL que la app conoce es la del servidor (puede ser un nombre de contenedor) y no guarda
    el info-hash. Haría falta una URL pública de qBittorrent en Configuración.
  - Sin ver: una subida real de punta a punta, el contraste AA medido con una herramienta y un lector de pantalla.
- **Oleada 4, rediseño P5: el asistente de subida con Resumen (#200):** un stepper con los pasos reales de cada flujo (película o
  capítulo: «Nombre y pistas → Resumen»; serie, temporada o tanda: «Contenido → Nombre y pistas → Resumen») y un paso final que
  enseña lo que se sube: nombre del torrent, ficheros, categoría (Película o Serie: Uploadrr-EMU solo envía `movie`/`tv`, así que
  no dice «Anime»), petición (con aviso si hay una abierta que la subida no cubre), pistas y copia (no predice reflink: depende de
  `st_nlink` al preparar). «En eMuwarez ya hay» saca del catálogo local los torrents del mismo contenido y dice si lo tuyo es
  mejor, igual o peor (`veredicto`, calculado en el servidor); no cuenta como permiso: revisa las reglas de trumps. El pie del
  asistente queda siempre a la vista. La columna se llama «Lo tuyo» y no «Tuyo» porque el catálogo local no guarda el autor.
  - Sin hacer: Nomenclatura, Pistas y MediaInfo como pestañas dentro del paso 2 en vez de modales (encaja: `PasoArchivo` y
    `PasoTemporada` tienen ya los tres bloques; hace falta sustituir los booleanos `showRemuxCard`/`showMiCard` por una pestaña
    activa, en un PR aparte y con comparación visual); en una tanda el Resumen no lista el nombre de cada torrent.
- **Oleada 4, el Panel, segunda ronda (#197):** «En curso» vuelve a enseñar las subidas recientes (las cinco últimas, con su
  insignia); «Listo para subir» enseña el grupo de release y los idiomas de cada petición; con un solo aviso en «Necesita atención»
  la acción queda a la derecha.
- **Oleada 4, el grupo de release a la vista (#199):** `release_groups` (lista) en las series y temporadas; fila «Grupo» en la
  ficha de Biblioteca, «Varios (N)» en las celdas de la tabla de hijos cuando se mezclan, «Grupo» en el detalle de una subida y
  una columna en la comparación de Peticiones. El grupo viene del `releaseGroup` de Radarr/Sonarr y se rellena en la siguiente
  sincronización: una base sin resincronizar lo tiene vacío. Falta en la lista de Subidas, la de Peticiones y «Tu copia vs eMuwarez».
- **Publicar la versión de un commit anterior (#198):** `publicar.yml` acepta `ref`; la versión y su etiqueta van a `release/vX.Y.Z`
  (no a master), sin tests (se pasan antes en local) y sin mover `:edge`; si falla después de subir la versión, se reanuda con
  `ref=release/vX.Y.Z`. Se usó para sacar la 0.16.2 desde `6acfa83`, el último commit antes del rediseño; hay que fusionar la
  rama `release/vX.Y.Z` en master para que `__version__` no se quede atrás (#201).

## Siguiente

Sin pendientes de la oleada 3 ni de la primera tanda de la oleada 4: lo que quedaba por ver se comprobó el 03/11 (ver en
«Hecho»). Lo siguiente es la oleada 4. Tres detalles que salieron de la comprobación, ninguno por los estilos (ya estaban antes):
- el paso «Configuración» del tour no resalta nada si Configuración se dejó en otra pestaña (`data-tour="settings-content"`
  solo existe en la pestaña Configuración);
- a 1280×800 el pie del asistente de subida queda cortado y el cuerpo del modal hace scroll por dentro;
- a 390 px el sidebar no se pliega.

## Oleada 4

- Funciones nuevas que faltan:
  - subida por lotes;
  - resumen de duplicados y trumps;
  - «Mejoras posibles»;
  - estadísticas del tracker por subida.
- Rediseño de la interfaz, un PR por pantalla y en este orden (maqueta en el informe de hallazgos): ~~P1 Panel~~, ~~P4 detalle de subida~~ y ~~P5 asistente con Resumen~~ (hechos),
  quedan P2 Biblioteca, P3 Peticiones y P6 Configuración. P7 móvil, pendiente de decidir. Las funciones que
  tocan Biblioteca, Panel y el asistente van junto a su pantalla. Criterio de Gabriel: le gusta el diseño original y solo quiere mejoras para ver mejor el contenido nuevo;
  esquinas redondeadas (la esquina cortada, demasiado contrastada, no); modo compacto pero legible, inspirándose en apps como
  Tracearr; y pasar cada pantalla por la skill `frontend-design`.

## Aplazado / ideas

- Límite de concurrencia compartido entre el CLI y el servidor (hoy cada proceso tiene el suyo, en memoria). Hace
  falta un cerrojo en fichero o en la base.
- Que la columna «Petición» de la lista de Biblioteca (y su filtro) cuente la petición heredada: hoy la temporada de
  una serie pedida entera dice «Sin petición» en la lista aunque su ficha enseñe la de la serie. `request_id` guarda
  una petición por fila, la que se escribe donde la petición pide.

## Datos útiles

- NAS UGREEN DXP4800; `/data` es btrfs y reflink funciona.
- Los nombres de la biblioteca no cambian fuera de la carpeta de subidas. Las subidas van a `UPLOADRR_UPLOADS_DIR`
  con nombre de eMuwarez: enlace duro, o copia reflink cuando hay que editar un fichero compartido (salvo que el
  ajuste lo prohíba).
- Cleanuparr «unlinked» solo vigila las categorías de radarr y sonarr.
