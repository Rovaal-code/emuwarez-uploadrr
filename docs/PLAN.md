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
  - «Abrir en qBittorrent» no estaba: la URL que la app conoce es la del servidor (puede ser un nombre de contenedor) y no guarda
    el info-hash. Se añadió después con una URL pública configurable (#234).
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
    activa, en un PR aparte y con comparación visual); en una tanda el Resumen no lista el nombre de cada torrent («Subir por
    lotes» sí, desde su PR 5; el `nombre` de `run_upload_checks` serviría también aquí para los packs).
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
- **Oleada 4, «Mejoras posibles»:** cuarto grupo de Recomendaciones del Panel (`rec_group = 4`, `rec_aportes`): lo disponible
  que ya está en eMuwarez (`emu_in_catalog = 1`) y cuya copia aporta algo que ninguno de sus torrents tiene (resolución,
  source, códec o castellano: los `emu_aportes` que la ficha de Biblioteca marca como «Aportas»). Mismas unidades y exigencias
  que el contenido único (película o temporada con castellano y rollup de pack). Sale en «Otras ideas (sin petición)» con una
  etiqueta por aporte y «Subir» abre el asistente sin petición; el Resumen del asistente da el veredicto frente a cada torrent
  (no es un permiso: revisa las reglas de trumps). Los capítulos sueltos no entran (sus aportes se calculan, pero se sube por
  temporada). Sin migración. Sin ver en el navegador.
- **Oleada 4, estadísticas del tracker por subida:** el detalle de una subida completada con ficha (`result_tracker`) enseña el bloque
  «En eMuwarez»: seeders, leechers, veces completado y, si los tiene, freeleech y doble subida. `GET /api/uploads/{id}/tracker-stats`
  (`services/emu_torrent_stats.py`, `emu_get_torrent`) saca el id de la ficha y pide `GET /api/torrents/{id}` a eMuwarez, siempre
  a `EMU_BASE_URL` y por el limitador de las consultas sueltas. Una llamada por subida, solo al abrir el detalle o con «Actualizar»
  (nunca por reloj ni en la lista: la clave se comparte con Sonarr, Radarr y qui), con caché de 5 min en memoria (30 s si falló).
  Un fallo del tracker es `disponible: false` con su mensaje, no un error; sin ficha es un 404. Sin migración ni historial: solo
  la lectura de ahora. Los nombres de los atributos (`seeders`, `leechers`, `times_completed`, `freeleech`, `double_upload`) son los de
  UNIT3D; **sin probar contra el eMuwarez real**.
- **Oleada 4, resumen de duplicados y trumps:** el Resumen del asistente de subida pone, sobre la tabla «En eMuwarez ya hay», una
  conclusión en una frase (`conclusionDuplicados`, `utils/resumenSubida.ts`, solo con los veredictos que ya da el servidor): «sería
  un duplicado» si alguno tiene tu misma calidad; «puede ser un trump» si mejoras todos; «no es un trump claro» si mejoras unos y
  empeoras otros; «probablemente la rechace» si eres peor que todos; y no afirma nada si no se pudo comparar. Sigue sin ser un
  permiso: no se conocen las reglas de trumps de eMuwarez y el texto manda revisarlas.
- **Oleada 4, el grupo de release en las listas:** columna «Grupo» en «Tu copia vs eMuwarez» (tu copia, y el grupo que cierra el
  nombre de cada torrent, `grupo_del_nombre`: lo que sigue al último guion, sin contar el «DL» de un WEB-DL) y en la lista de
  Subidas (`release_groups` de lo que se sube: el de la copia o los de todos los capítulos de una temporada). **No** se añadió a la
  lista de Peticiones: una petición no pide grupo y su copia local ya enseña el suyo en el detalle (`local_release_groups`).
- **Oleada 4, rediseño P3, P2 y P6, y los retoques del Panel (#207, #208, #209, #204, #205):**
  - Peticiones (#207): agrupada por lo que se puede hacer: «Lista para subir», «Parcial» y «No la tienes», más «Cerradas» (reclamadas,
    llenas o ya subidas, que no se pueden subir y mentirían en ningún otro grupo); dentro de cada grupo, por recompensa. Elegir otra
    ordenación (selector o cabecera) deja la lista plana. La columna Autor se pensó oculta por defecto (casilla «Mostrar autor»), pero
    07f7fa2 la dejó siempre visible. «Temporada 0» ya estaba arreglado (8510288).
  - Biblioteca (#208; **revertido en parte por Gabriel en e4f9910 y #224: cada dato filtrable vuelve a su columna propia, 12 columnas, y los
    pósters miden 44×66; lo que sigue describe la primera versión**): las columnas pasan de 13 a 7. Tipo, origen, resolución, proveedor, source y grupo se pliegan en una línea de
    especificaciones bajo el título (con el grupo de release a la derecha de la línea del título) y sus seis filtros pasan a la cabecera
    de Título. Filas de 63 a 57 px y sin scroll horizontal a 1280. Vistas guardadas en localStorage (los filtros viven en el estado de
    la página, no en la URL). El desplegable «Orden» se queda: ordena por título, año y reciente, que ninguna cabecera hace.
  - Configuración (#209): índice de secciones sticky con buscador, barra de guardado con el número de campos cambiados (compara
    campo a campo con lo cargado) y «Avanzado» plegado (hoy solo trae las rutas permitidas: la ruta de Python y los timeouts no se
    muestran en la pantalla). Por debajo de 1100 px el índice es una fila sin fijar.
  - Pósters del Panel (#204): todos de 44×66 px, el alto del texto de una fila con grupo de release e idiomas.
  - Barra lateral (#205): un carril recto de arriba abajo, sin esquinas redondeadas (#192 se las había dado y dejaba un hueco junto a la
    barra superior) ni margen inferior; la línea bajo el logo es la misma que la de la barra superior.
- **Oleada 4, subida por lotes, PR 1: las tandas del asistente quedan agrupadas como lote:** esquema 52, columna
  `upload_jobs.lote_id` (12 hex, con índice; sin tabla: el lote es una etiqueta). Cada tanda del asistente (temporadas o
  capítulos) genera un id en el navegador y lo manda en cada `queueUpload`; un reintento (`queue_retry_for_job`) lo conserva, un
  «Subir» nuevo del mismo elemento no, y el camino heredado `retry_upload_job` tampoco (crea filas `ready` que no cuentan como
  activas). `services/lotes.py` guarda el tope (`MAX_ELEMENTOS_LOTE`, copia vigilada en `utils/lote.ts`), el patrón del id y
  `contar_por_lote`. `GET /uploads?lote_id=…` y `/uploads/count?lote_id=…` devuelven y cuentan solo la punta de cada cadena
  (`CONDICION_PUNTA`, la misma regla que `_find_latest_job_for_item`), y cada subida trae `lote_id`/`lote_total`. Subidas enseña
  el chip «Lote · N» (solo con más de un elemento) que filtra por el lote; «Quitar filtros» lo quita. «En curso» del Panel enseña
  como mucho 6 filas vivas y «+N en cola · Ver todas las subidas»; con más de 100 subidas vivas el Panel aún puede perder la que
  sube (pide las 100 más nuevas), pendiente para cuando haya lotes grandes. Sin ver en el navegador. Sigue el PR 2 del plan (resumen,
  cancelar pendientes y reintentar fallidas del lote).
- **Oleada 4, subida por lotes, PR 2: resumen, cancelar pendientes y reintentar fallidas de un lote:** con el filtro de un lote,
  Subidas enseña sus contadores (`GET /uploads/lotes/{id}`, `lotes.resumen_de_lote`, solo base local), «Cancelar pendientes»
  (`POST …/cancelar`; con la casilla «Parar también las que ya se están preparando o subiendo», `solo_pendientes=false`) y
  «Reintentar fallidas» (`POST …/reintentar`, en el orden del lote; el reintento sigue en él). Cancelar escribe primero todas las
  de la cola con la guardia `desde={"queued"}` y solo después las saca de la puerta, así ninguna toma la plaza que deja otra; una
  que ya había arrancado entre medias se cuenta como intacta (no pasa por `cancel_upload_job`, que la cancelaría como lo que es
  ahora). `queue_retry_for_job` solo acepta la punta de la cadena (reintentar un intento anterior abría otra punta y, si la punta
  estaba completada, volvía a subir lo subido), y en Subidas «Reintentar» queda apagado en los intentos anteriores. El detalle
  de una subida dice «Parte de un lote de N · Ver el lote». La puerta de «Subidas en paralelo» guarda el límite leído un segundo
  y lo olvida al vaciarse la cola (con un lote, cada hilo en espera abría una conexión por vuelta). Sin ver en el navegador.
- **Oleada 4, subida por lotes, PR 3: `POST /uploads/lote`** (solo backend, sin interfaz todavía): `lotes.encolar_lote` encola
  hasta `MAX_ELEMENTOS_LOTE` (50) elementos en el orden dado con una misma etiqueta. Antes de crear nada mira una vez las
  precondiciones que harían fallar a todos (`uploadrr.path`, claves de eMuwarez y TMDb): si falta algo, 409 y nada encolado.
  Por elemento, y antes de escribir nada, salta con su motivo: repetido en el lote, inexistente, serie («Elige sus
  temporadas»), capítulo cuya temporada va en el mismo lote, comprobaciones sin `ready`, película o capítulo que no pasa otra
  vez la comprobación de contenido en el servidor (el castellano de una película no se volvía a mirar al correr el trabajo) y
  elemento con una subida en marcha; solo después guarda `campos` (como «save-fields») y encola. Cada elemento va en su propia
  transacción: uno que revienta se salta sin dejar escrituras a medias. `provider` solo llega a los packs; el de una película va
  en `campos`. Si no se encola ninguno no queda lote. Asumido sin la respuesta de Gabriel (preguntas 1, 2 y 12 del plan): lote
  sin edición por elemento, tope de 50, respeta «Subidas en paralelo» tal cual y con 0 (sin límite) solo avisará la interfaz.
- **Oleada 4, subida por lotes, PR 4: Biblioteca, selección de películas y modal «Subir por lotes»:** el botón «Seleccionar» de
  la barra de Biblioteca pone una casilla en cada película (no en series, temporadas ni capítulos) de las tres vistas: en la
  lista dentro de la celda del título (siguen 7 columnas), en los pósters arriba a la izquierda y fuera del layout (la tarjeta
  no cambia de alto). La selección (`useSeleccionLote`, tope de 50) vive en la página: sobrevive a filtrar, a una vista guardada
  y a cambiar de vista, y se limpia al salir de Biblioteca, al apagar «Seleccionar» y al encolar. Un pie en el flujo de
  `.bib-pagina` (`BarraLote`, no fijo) dice cuántas hay y cuántas esconde el filtro. El modal (`components/lote/`): paso 1,
  qué entra (las que no están en disco o sin castellano, desmarcadas con su motivo, `razonNoSubible`); paso 2, por película el
  nombre del torrent, sus avisos, su comprobación y lo que ya hay en eMuwarez (`conclusionDuplicados`), con «Incluir». Las
  comprobaciones son las de `useComprobacionesTanda` (nuevo `minimo`, 1 aquí y 2 en el asistente): el entorno una vez, el
  contenido por película, nada en el paso 1. Se salta (desmarcada y sin poder marcarse) la que falla su comprobación, tiene la
  nomenclatura bloqueada o saldría con el mismo nombre que otra; llegan desmarcadas la de una pista sin idioma («Súbela suelta
  para elegir el idioma»), el duplicado y la peor que todo. A una WEB-DL sin proveedor se le sugiere el de TMDb y se mandan sus
  `campos` completos. Dice de cuántas en cuántas irán («Subidas en paralelo»; con 0 avisa de que irán todas a la vez).
  «Subir N» llama a `POST /uploads/lote`; el resultado lista las saltadas y «Ver el lote en Subidas» abre Subidas filtrada por
  él (`emuwarez_open_lote`); un 409 enseña sus motivos. Decidido sin Gabriel: la selección se enciende con «Seleccionar» (sin
  él no hay casillas). Sin ver en el navegador (falta comprobar a mano la rejilla con 200 marcadas).
- **Oleada 4, subida por lotes, PR 5: series y temporadas en el lote:** «Seleccionar» pone casilla también en series y
  temporadas (en la lista, las filas hijas de una serie desplegada; en pósters, las temporadas cuando un filtro las saca), nunca
  en capítulos. La fila de una serie recibe sus temporadas marcadas como un texto (`temporadasMarcadas`, «12,15»), para que el
  memo compare por valor. En el paso 1 del modal cada serie se cambia por sus temporadas (`getLibrary` con `parent_id`, como el
  asistente, de una en una y con «Cargando las temporadas… (N de M)»; `expandirSeleccion`): una temporada marcada sola y por su
  serie sale una vez, las aptas para pack llegan marcadas y las demás desmarcadas con el motivo de `seasonNotReadyReason`, y el
  tope de 50 cuenta después de expandir. Una serie sin temporadas o que no se pudo cargar se dice arriba. En el Resumen, una
  temporada pasa por las mismas comprobaciones de contenido que una película; su nombre sale del `nombre` nuevo de
  `run_upload_checks` (el `season_pack_title` del plan, solo con el pack listo; compatible hacia atrás) y lo que ya hay en
  eMuwarez de `getEmuComparison(id)`, como una tanda de temporadas del asistente. No lleva `campos`. Nombres repetidos se miran
  entre películas y temporadas. Decidido sin Gabriel (pregunta 8 del plan, la opción recomendada): solo packs aptos, sin
  capítulos sueltos desde Biblioteca. Tampoco se elige proveedor en el lote: el pack usa el que decide su plan (nombre de los
  capítulos o TMDb) y no se manda `provider`; con proveedores distintos su comprobación falla y la temporada se salta con ese
  motivo y «Súbela suelta para elegirlo». Los avisos del plan (pista de audio sin idioma, source distinto) no se enseñan por
  temporada. Sin ver en el navegador.
- **Oleada 4, subida por lotes, PR 6: «Subir seleccionadas» en «Listo para subir» del Panel:** «Seleccionar» en la cabecera
  del carril pone casilla en las peticiones y en las otras ideas («Contenido único» y «Mejoras posibles», también plegadas);
  no en faltantes, que solo se piden. La selección (`useSeleccionLote`, ahora con clave propia: `claveDelPanel`, petición +
  fila que se sube, porque el grupo 1 hace una fila por petición y dos pueden apuntar al mismo elemento) se limpia al salir
  del Panel, al apagar «Seleccionar» y al encolar. «Subir seleccionadas (N)», en un pie del carril fuera del scroller
  (`BarraLote` con su texto, `Carril` con `accion` y `pie`), pide la fila real de cada una (`getLibraryItem(library_target_id
  ?? id)`, una vez por fila) y abre el modal de «Subir por lotes», que ahora recibe `entradas` (`{ item, requestId?, alcance?
  }`, `EntradaLote`; Biblioteca manda solo `item`). En el paso 1 (`expandirEntradas`) una serie pedida entera sale como sus
  temporadas aptas y una pedida por temporada solo como esa, todas con la petición; una petición de capítulo sube ese capítulo
  (el tipo que cuenta es el de la fila real); dos peticiones sobre el mismo elemento son una fila con un desplegable para
  elegir cuál se enlaza (la primera por defecto); cada fila dice «Petición #N». Una petición de capítulo cuya fila resultó ser
  la temporada (el capítulo no está) no entra y se dice arriba; las que ya no están en la biblioteca, en el aviso del Panel, y
  el lote se abre con el resto. Las otras ideas entran sin petición. `queueLote` lleva `request_item_id` por elemento. El
  tour lo menciona en «Listo para subir». Sin ver en el navegador.

- **Oleada 4, subida por lotes, después del PR 6:** «En curso» del Panel pide aparte todas las subidas vivas
  (`status=queued,staging,preparing,running`, hasta 500) y las junta con las 100 más nuevas: con lotes grandes, la que sube
  (la más vieja) ya no se cae de la lista. Y en «Subir por lotes» cada temporada enseña los avisos de su plan
  (`run_upload_checks` devuelve `avisos` y `sin_idioma` del pack: proveedor, source que no cuadra, pista de audio sin idioma);
  con audio sin idioma llega desmarcada («Súbela suelta para elegir el idioma»), como una película. Sin ver en el navegador.

- **Oleada 4, subida por lotes, PR 8 (preguntas 6, 9, 10 y 13):** un lote desde Biblioteca enlaza cada elemento a la petición
  abierta «Compatible» que lo cubre si hay una sola en el nivel más cercano (`requests.peticion_que_enlazar`, con `_cubre` y
  `_scoped_library_id`; la elegida en el Panel gana). Peticiones tiene «Seleccionar» y «Subir seleccionadas» como el Panel
  (`peticionSeleccionableEnLote`, `entradaDePeticion`; una petición de temporada o capítulo pide su detalle para dar con la
  fila). «Borrar lote» en el banner del lote de Subidas (`POST /uploads/lotes/{id}/borrar`, mismo token y mismo
  `delete_upload_job` que el borrado suelto, cadena entera; las vivas no se tocan). La sincronización de peticiones ya no se
  para por las subidas en cola (`ESTADOS_EN_MARCHA`). Sin ver en el navegador.

- **Oleada 4, subida por lotes, PR 9 (pregunta 5):** Ajustes → Notificaciones → «Subidas por lotes» elige entre «Una por
  subida» (por defecto, lo de antes) y «Una por lote» (`notify_lote_modo`, copia vigilada en `utils/lote.ts`). Con «Una por
  lote», las subidas de un lote de más de un elemento no avisan solas y, cuando su última punta llega a un estado final, sale
  `upload_batch_done` («Lote terminado: N subidas, X completadas, Y fallidas, Z canceladas», con las fallidas por título; en
  la campana abre Subidas filtrada por el lote). Un solo aviso: «¿ha terminado?» y apuntar la firma del lote (ids de sus
  puntas, `app_state` `lote_avisado:<id>`) van en un `BEGIN IMMEDIATE`; «Reintentar fallidas» cambia la firma y vuelve a
  avisar al terminar. Cancelar también cierra el lote; reiniciar no avisa. Sin migración: al pasar a «Una por lote», la
  pestaña marca el aviso nuevo en los canales que avisaban de las subidas. Y «Subir seleccionadas» (Panel y Peticiones) no
  abre un lote viejo si lo marcado cambia mientras se piden las fichas: lo vuelve a preparar con lo de ahora
  (`useSeleccionLote().vigente`). Sin ver en el navegador.

- **Oleada 4, subida por lotes, PR 10 (pregunta 4): freno tras 5 fallos seguidos con el mismo motivo.** Cuando una subida de un
  lote falla, `lotes.frenar_si_fallo_sistemico` (desde `_notify_upload_failed`, por donde pasan todos los fallos; el arranque
  no) mira las puntas terminadas por orden de fin: si los 5 últimos fallos que cuentan comparten motivo (primera línea de
  `error_message`), las que siguen en cola quedan `cancelled` con fase `lote_parado` y el motivo («Lote parado: 5 fallos
  seguidos por «…»»); las que ya se preparan o suben siguen. No cuentan los fallos propios de cada elemento
  (`MARCAS_DE_FALLO_POR_ELEMENTO`: los de la app y los títulos de panel de Uploadrr-EMU, como «Potential duplicate on»); una
  completada corta la racha. Decide uno solo (un `RLock` del proceso, que también envuelve cada elemento de `encolar_lote`: si la racha llega mientras se encola, el resto sale `blocked`). Con «Una por subida», un
  aviso «Lote parado»; con «Una por lote», una línea en el resumen. El banner del lote lo dice y «Reintentar fallidas» las
  relanza. Sin ver en el navegador.
- **Oleada 4, límite de «Subidas en paralelo» compartido entre el CLI y el servidor (#226):** la puerta de cada proceso sigue repartiendo
  turnos por id a sus hilos y, antes de admitir, toma una plaza compartida (`services/upload_execution/plazas_compartidas.py`): 64
  ficheros `<CONFIG_DIR>/plazas/plaza-N` con `flock` exclusivo y un `mutex` para contar y tomar en un paso. Se eligió el fichero y no una
  tabla porque el núcleo suelta el `flock` al morir el proceso (también con kill -9): ni PIDs, ni latidos, ni limpieza, ni migración.
  0 = sin límite: toma plaza pero nunca espera. El límite se lee como antes (caché de 1 s, olvidada al vaciarse la cola); cancelar o retirar
  se comprueba en cada vuelta (3 s) y tras tomar plaza. Sin `fcntl` (Windows) o con el directorio inservible, aviso y límite solo del
  proceso. Un recorrido que falla a mitad cierra la plaza ya tomada. **Sin ver:** no hay cola ni orden entre procesos (gana el primero que
  llega a una plaza libre en su vuelta; el «puesto en la cola» sigue siendo solo del servidor); un servidor que muere con un Uploadrr-EMU
  huérfano subiendo libera su plaza; solo probado en Linux y python 3.13, no en Docker; `flock` sobre NFS/SMB podría no funcionar
  (`CONFIG_DIR` suele ser local).
- **Oleada 4, pasada de diseño con `frontend-design`, `impeccable` y las guías web de Vercel (06/11, #227-#232):** cada pantalla se rehízo
  dentro del lenguaje HUD existente (sin tokens, fuentes ni librerías nuevas) y pasó por dos pasadas: primero `frontend-design`, después
  una revisión con `impeccable` (su detector de «slop» sin red: franjas laterales de acento, fuente sobreusada) y con las guías de Vercel
  (`web-interface-guidelines`: nombres accesibles, `div onClick`, medidas de imagen, `overscroll-behavior`, `touch-action`…). **La
  revisión con `impeccable` fue degradada:** los agentes no tenían herramienta de subagentes, así que `critique`/`audit`/`polish` los
  hicieron en un solo contexto, con el detector y sin `PRODUCT.md`/`DESIGN.md` (queda pendiente `/impeccable init`). Se descartó lo que
  choca con el criterio de Gabriel («más audaz», cambiar de tipografía: Inter se queda). Criterio del 06/11: esquinas redondeadas firmes,
  densidad flexible. **Lección:** `node_modules/` con barra no ignora el symlink `frontend/node_modules` de un worktree y se coló en un PR;
  `.gitignore` ya lleva `frontend/node_modules` sin barra (#227).
  - Marco y móvil, P7 (#229): el cajón a ≤768 px y el paso «Configuración» del tour **ya estaban hechos** (5166cd8, c3f6dd5, d3aab6d; se
    verificaron en navegador). Nuevo: botón de búsqueda en la cabecera (en móvil no se podía abrir Ctrl+K), la cuenta (usuario, enlaces de
    eMuwarez, cerrar sesión) al pie del cajón (`CuentaDelCajon`), la campana como panel de ancho completo, fondo opaco en campana, modales
    y paleta, y objetivos táctiles de 44 px solo con puntero táctil (`--tap-min`, compensado por la escala de la interfaz; `.btn` 40 px
    y campos a 16 px). El tour es un diálogo accesible (foco atrapado, Escape, retorno del foco) y en móvil salta el paso de la barra
    lateral. «Saltar al contenido», `document.title` y `h1` por sección, el velo del modal cierra al pulsar *y* soltar (iOS), «Borrar todo»
    de la campana pide dos pulsaciones y se anuncia, login que explica qué falta, `role="alert"` en los errores del asistente de primera
    configuración. Guía para el resto de pantallas: `.page-container` es el único scroll (usar `--vh100`, nunca `100vh`), nada depende del
    hover, `Modal` siempre, tablas anchas con scroll propio, tooltips que no cuentan en táctil. **Sin ver:** iOS/móvil real, el cajón con
    el perfil de eMuwarez cargado, la cabecera con una sincronización en curso a 390 px, los pasos 3 a 9 del asistente de primera
    configuración a 390 px y el tour completo con perfil.
  - Panel y Estadísticas (#227): cabecera con la cuenta en su propia franja, carriles de 360 px mínimo con scroll de página en ventanas
    bajas (cabe a 1280×800), «Necesita atención» con el título a la izquierda. «Listo para subir» dice «No se pudo cargar» con «Reintentar»
    (antes enseñaba «Ninguna petición lista», falso) y, si una recarga falla con datos previos, los deja bajo un aviso; las fallidas
    de «En curso» dicen su motivo. `GraficoLinea` se dibuja a su ancho real (el texto de los ejes deja de encogerse en móvil), enseña
    el último valor y la variación del rango, y se lee día a día con ratón, dedo o teclado (`aria-live`); «Subido y bajado» ocupa la
    fila, las diez tarjetas van en dos grupos y la tabla alternativa tiene scroll interno. `h1` en ambas pantallas (el resto siguen con
    `div`), insignia del rol con el contraste corregido (2,1:1). **Anotado, no hecho:** `HoverTitle` (en `Tooltip.tsx`) es un
    `div role="link"`. **Sin ver:** lector de pantalla, el Panel a 2000 px, la banda con más de cuatro instancias caídas con el tour abierto.
  - Peticiones, Subidas y detalle de subida (#228): Peticiones lleva un resumen por grupo (cada chip salta a su grupo y lo despliega),
    grupos plegables con cabecera pegada (se recuerda en `localStorage`, `emuwarez_pet_grupos_plegados`), el motivo por el que una petición
    aún no está lista (`motivoDeLaPreparacion`) y los puntos con su moneda; a 1280 px cabe sin desplazar y por debajo de 760 px se queda con
    título, compatibilidad y puntos. La ficha abre con el veredicto y la recompensa (`FichaPoster` de 230 px). Subidas junta Estado y
    Progreso en una celda (de 13 a 10 columnas sin plegar ningún dato filtrable), los intentos anteriores pasan a un chip, las acciones son
    iconos y solo las posibles, las fallidas dejan de parpadear y el banner del lote suma una barra por estado. En el detalle, el recorrido
    de pasos va dentro del recuadro de resultado, con los subpasos de Uploadrr colgando del paso 4. **Ya estaba hecho:** la columna Autor
    siempre visible (07f7fa2), la agrupación de Peticiones (#207) y el detalle «por el resultado» (#195). **Aplazado:** virtualizar las
    listas de más de 50 filas (`FilasVirtuales`; Peticiones pide hasta 2000 a la vez), una tarjeta por fila en móvil, y el texto del estado
    vacío cuando un lote se queda sin subidas tras «Borrar lote».
  - Biblioteca, su ficha y «Subir por lotes» (#230, solo frontend): los datos de las columnas pasan a texto atenuado sin caja (los
    enlaces de origen y proveedor conservan su ficha), «Sin petición» es un guion, el título queda fijo a la izquierda al desplazarse (las
    12 columnas necesitan ~1380 px), los capítulos sin póster no reservan el hueco de la carátula (de 77 a ~50 px), las filas hijas, la
    abierta y la marcada para el lote se distinguen por tinte, y la vista es un solo control con iconos; ≤760 px la tabla enseña título,
    estado y acciones. La tarjeta de póster enseña título, tipo y año al pasar el ratón o al enfocarla (siempre en táctil) y lleva un
    botón de verdad; su medida sigue fijada solo por `aspect-ratio` (medido con scroll rápido, sin el aviso de `RejillaVirtual`). El título
    de la lista es un enlace real `/library/:id`. La ficha mide 420 px (`DetailPoster` admite `alto`; las otras fichas siguen en 480), pone
    las acciones en la línea del título y pasa las tarjetas a dos columnas por debajo de 1000 px. «Subir por lotes» alinea el paso 1,
    abre el paso 2 con el recuento (se subirán, se saltarán, por comprobar) y en móvil enseña «Incluir» en cada bloque. **Aplazado, la
    «petición heredada» en la lista:** el filtro es SQL (`listado._build_library_filter`), una serie pedida entera marcaría todos sus
    capítulos «Compatible» y mostrarla solo en la celda desajusta columna y filtro; si se quiere, una etiqueta «de la serie» solo en la
    celda, con una consulta por lote de antepasados reutilizando `_cubre`. **Sin ver:** `EmuComparisonSection` y `SourceComparisonModal`, el
    paso 2 del lote con comprobaciones en verde, el contraste AA medido y el lector de pantalla.
  - Asistente de subida, P5 completo (#232): el panel es una columna y solo el cuerpo del paso hace scroll; el pie (Volver, Continuar,
    Subir) queda fijo a 1280×800, 1440×900 y 390×844 (cerrado el detalle del pie cortado de «Siguiente») y el veredicto de las
    comprobaciones va en el pie. Nomenclatura, Pistas y MediaInfo pasan de modales a pestañas del paso 2 (`role="tablist"`, flechas,
    Inicio y Fin; `pestana` sustituye a `showMiCard`/`showRemuxCard` en `useAsistente`, así que cambiar de pestaña no pierde lo editado;
    «Pistas» avisa de cuántas no tienen idioma). El Resumen de una tanda lista el nombre de cada torrent: en packs, el `nombre` de
    `run_upload_checks`, que ahora lleva lo editado a mano (backend compatible hacia atrás: `source`, `tag`, `title` e `idiomas` opcionales
    en `POST /library/{id}/upload/checks`; la caché de la tanda se invalida por Proveedor y ajustes); en capítulos, la vista previa de la
    nomenclatura (`useNombresTanda`). Arreglado de paso: el nombre del torrent pintaba `x265` como `×265` (ligadura de Inter). **Sin ver:**
    tour abierto, lector de pantalla, contraste medido y una subida real (la API de nomenclatura, pistas y MediaInfo se simuló: la máquina de
    pruebas no tiene mediainfo ni mkvmerge).
  - Configuración, Tareas, Instancias, Logs y Guía (#231): Configuración con cabecera común por tarjeta, campos con `<label for>` (`Campo`),
    las claves solo como estado («Configurada»/«Sin configurar», nunca el valor), interruptores `role="switch"`, validación de las URL de
    qBittorrent y qui en el propio campo con foco en el primer error, y barra de guardado con «Descartar» (Notificaciones la comparte);
    el índice sticky con buscador y «Avanzado» ya estaban (#209). Tareas en dos columnas con estado y error a la vista y un solo reloj
    compartido (sigue en `TasksPage`, en `RELOJES`); Instancias dice si responde cada una sin afirmar «en marcha» sin base y elimina con
    `Modal` (no `window.confirm`), y una recarga silenciosa que falla conserva la lista; Logs ocupa la pantalla, resalta lo buscado, copia
    líneas y no se repinta sin novedades; la Guía lleva lista lateral con saltos a subtítulos. `etiquetaIntervalo(90)` da «1h 30 min».
    **Aplazado:** el `window.confirm` de regenerar o quitar la clave del widget (`WidgetCard.tsx`) → `Modal`; la pestaña Backup sigue
    llamándose «Backup». **Sin ver:** una instancia en «Prueba correcta», subir o restaurar un backup real, «Probar conexión» real,
    Configuración con el tour abierto y touch real.
- **Oleada 4, «Abrir en qBittorrent» (#234):** ajuste opcional «URL pública del WebUI» (`qbit.public_url`, Configuración → qBittorrent), solo
  http/https con host y sin usuario ni contraseña; se valida en el PUT con `error_de_url_publica` (no con un validador de pydantic) y no es un
  secreto, así que viaja en las copias de configuración. `GET /api/uploads/seeding` devuelve `url_publica` (se vuelve a validar al leerla, por si
  viene de una copia restaurada). En el bloque de seeding del detalle de una subida completada, con la URL puesta: «Abrir en qBittorrent» (pestaña
  nueva, `noopener noreferrer`) y «Copiar nombre» (el nombre de la carpeta o fichero subido, para el filtro de la WebUI). La WebUI no tiene enlace
  directo a un torrent y la app no guarda el info-hash, así que se abre la WebUI sin más. No está en la fila de la lista de Subidas. **Sin ver:**
  el campo y el bloque en el navegador, ni contra un qBittorrent real.
- **Oleada 4, el error 422 ya no devuelve ni registra lo enviado (#235):** pydantic repite `input` (y `ctx`) en cada error de validación, y aquí
  ese valor puede ser una URL con clave (el proxy de qui), una API key, un token de Telegram o una contraseña. Un manejador global de
  `RequestValidationError` (`web/errors.py`) los quita y deja `type`, `loc` y `msg`, que es lo que lee el frontend. `tests/test_422_sin_claves.py`
  (ajustes, asistente de primera configuración, instancias, notificaciones, login y JSON inválido, con un valor sentinela).
- **Oleada 4, los errores de integración ya no llevan las claves (#237):** eMuwarez y TMDb llevan la clave en la URL y el texto de una excepción
  puede repetirla. `integrations/base.py` gana `tapar_claves` y `texto_de_error` (tapan `api_key=`, `token=`, `password=`, `secret=`, `key=`, campos
  JSON, `usuario:clave@`, cabeceras `X-Api-Key`/`Authorization`, el token de un bot de Telegram y el de un webhook de Discord, y las claves
  configuradas que el sitio les pase). Se usan en el 500 genérico, en las respuestas de instancias, asistente de primera configuración,
  peticiones y biblioteca, y en todo lo que se guarda o notifica (`task_runs`, resultados de tareas, `last_test_status`, `error_message` de las
  subidas, salud de *Arr, pruebas de conexión, seeding, manifiesto de versión). Además, una fábrica de `LogRecord` global
  (`web/logging_setup.py`) tapa mensaje, traceback y stack de cualquier registro (app.log, consola, `/api/logs`). `tests/test_errores_sin_claves.py`.
  **Limitaciones:** la fábrica es global al proceso; un secreto sin forma reconocible (ni `clave=valor`, ni cabecera, ni URL) solo se tapa si el
  sitio le pasa la clave configurada. Suite completa sobre la rama: 4248 pasan, 69 omitidas. **Después:**
  `tests/test_errores_por_texto_de_error.py` (ast) cierra la puerta: en web/ y services/ el nombre de un `except … as X` no acaba en
  `str(X)`, `repr(X)`, f-string, `%`, `.format` ni concatenado sin `texto_de_error` (los argumentos de `logger.*` no cuentan, los tapa la
  fábrica); quedaron 4 sitios permitidos por fichero y función, con su motivo, y se arreglaron los 33 restantes.
- **Oleada 4, limpieza tras el rediseño (#236):** fuera `NomenclatureModal`, `NomenclatureFieldsModal` y `UploadPreflightModal` (nada los abría; los
  sustituyó el asistente) con `styles/nomenclatura.css`, las funciones y tipos de `api/` que solo ellos usaban y el CSS huérfano (`.settings-tab`,
  `.fields-grid`, `.preview-*`, fondos de `.login-card`/`.wizard-card` que el HUD pisaba); `test_copias_frontend` ya no exige los tokens de
  nomenclatura y título MKV en el frontend (siguen en backend y CLI). `theme-color` y `site.webmanifest` pasan a `#0a0d14`. `HeaderFilter` cierra con
  `pointerdown` (iOS). `formatBytes` usa espacio duro. Tras «Borrar lote» con todo borrado, Subidas dice «Este lote ya no tiene subidas» y ofrece
  «Quitar filtro del lote». La franja de cuenta del Panel pierde Mensajes y Notificaciones (están en la barra superior y el cajón) y queda «Mis
  subidas», solo con icono entre 769 y 1400 px para ir en una fila. Los modales ya eran opacos tras #229. **Pendiente:** `--color-tab-active`
  (globals.css); `pages/ajustes/formatBytes.ts` sigue con espacio
  normal y otra precisión; `viewport-fit=cover` espera a que el marco trate las safe areas; tablet táctil a 769–1400 px sin probar.
  **Después:** fuera los endpoints sin uso desde la interfaz: `GET /library/{id}/nomenclature`, `POST …/nomenclature/preview`,
  `POST …/adapt-nomenclature`, `GET …/nomenclature/operations`, `POST …/upload/preflight` y `GET`/`POST …/nomenclature-check`, con sus
  modelos, `list_filesystem_operations`, sus tests y `getNomenclatureCheckInfo`/`runNomenclatureCheck` del frontend. Los servicios siguen
  (la CLI usa propuesta, renombrado y preflight); `nomenclature_check.check_item`/`count_pending` ya solo los llaman los tests.

## Siguiente

Sin pendientes de la oleada 3 ni de la oleada 4 de funciones. Los tres detalles que salieron de la comprobación del 03/11 están
cerrados: el paso «Configuración» del tour (d3aab6d), el cajón a ≤768 px (5166cd8) y el pie del asistente a 1280×800 (#232).

Subida por lotes: hecha (PR 1-10, ver «Hecho» y `docs/PLAN_SUBIDA_POR_LOTES.md` §6 «PR 7 en adelante»). Falta que Gabriel la
pruebe en `:edge` (duplicado real en Uploadrr-EMU, 50 hilos en el NAS, la rejilla con 200 seleccionadas) y que decida, al
probarla, si guardar los `campos` y crear el trabajo van en una sola transacción.

## Oleada 4

- Funciones nuevas que faltan:
  - ~~subida por lotes~~ (hecho, PR 1 a 10, ver «Hecho»; el plan está en `docs/PLAN_SUBIDA_POR_LOTES.md`, con las respuestas de
    Gabriel en su §8). Queda que Gabriel la pruebe (ver «Siguiente»);
  - ~~resumen de duplicados y trumps~~ (hecho, ver «Hecho»);
  - ~~«Mejoras posibles»~~ (hecho, ver «Hecho»);
  - ~~estadísticas del tracker por subida~~ (hecho, ver «Hecho»).
- Rediseño de la interfaz, un PR por pantalla y en este orden (maqueta en el informe de hallazgos): P1 Panel, P4 detalle de subida, P5 asistente con Resumen,
  P2 Biblioteca, P3 Peticiones, P6 Configuración y P7 móvil (todos hechos; el 06/11 pasaron también por `frontend-design`, `impeccable` y
  las guías de Vercel, ver «Hecho»). Queda, de P7, una tarjeta por fila en móvil para las listas largas. Las funciones que
  tocan Biblioteca, Panel y el asistente van junto a su pantalla. Criterio de Gabriel: le gusta el diseño original y solo quiere mejoras para ver mejor el contenido nuevo;
  esquinas redondeadas (la esquina cortada, demasiado contrastada, no); algo compacto pero solo un poco y sin regla fija
  (si dar aire mejora la lectura, se da; Tracearr era solo una inspiración); y pasar cada pantalla por la skill `frontend-design`.

## Aplazado / ideas

- Que la columna «Petición» de la lista de Biblioteca (y su filtro) cuente la petición heredada: hoy la temporada de
  una serie pedida entera dice «Sin petición» en la lista aunque su ficha enseñe la de la serie. `request_id` guarda
  una petición por fila, la que se escribe donde la petición pide. Propuesta y razones en la entrada de Biblioteca (#230).
- `window.confirm` del widget de Homepage (`WidgetCard.tsx`) → `Modal`; virtualizar las listas de Peticiones y Subidas de más de 50 filas;
  una tarjeta por fila en móvil para esas listas; `HoverTitle` es un `div role="link"`; `h1` en el resto de pantallas; `/impeccable init`
  (`PRODUCT.md`/`DESIGN.md`).
- Recuperar solo el añadido a qBittorrent de una subida que ya estaba en eMuwarez (necesita un cambio en Uploadrr-EMU, otro repo).
- Probar en el NAS (`:edge`): el límite compartido entre CLI y servidor (`flock` sobre el volumen de `CONFIG_DIR`), el campo y el enlace de
  qBittorrent, y la subida por lotes (ver «Siguiente»).

## Datos útiles

- NAS UGREEN DXP4800; `/data` es btrfs y reflink funciona.
- Los nombres de la biblioteca no cambian fuera de la carpeta de subidas. Las subidas van a `UPLOADRR_UPLOADS_DIR`
  con nombre de eMuwarez: enlace duro, o copia reflink cuando hay que editar un fichero compartido (salvo que el
  ajuste lo prohíba).
- Cleanuparr «unlinked» solo vigila las categorías de radarr y sonarr.
