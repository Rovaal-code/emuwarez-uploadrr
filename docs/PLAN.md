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
  test falla si aparece un campo nuevo que no esté en uno de los dos sitios. Faltan las lecturas sueltas de sí/no
  fuera de la API (p. ej. `series.ignore_specials` en `library.py`).
- **Biblioteca, vista de pósters en negro al desplazarse deprisa:** `RejillaVirtual` repintaba sin fin si su medida
  oscilaba (error 185 de React) y la pantalla quedaba en negro hasta F5. Las correcciones seguidas ahora tienen
  tope, y cada página va dentro de `LimiteDeErrores`, que enseña un mensaje en vez de dejar la pantalla en negro.
  Reproducido con un arnés de navegador forzando la oscilación; no se ha visto aún qué la provoca en la aplicación
  real. Cuando el tope corta una oscilación, la consola avisa una vez con «RejillaVirtual no se calma: 3×300 →
  3×330 → …» y el ancho, el alto real, el zoom y el scroll; si el fallo es de otro componente, dirá «Error de render»
  con la pila de componentes. Pendiente: mirar ese aviso en la aplicación real.
- **Oleada 3, subida por pasos (#127):** `_run_queued_job` es un bucle sobre `PASOS` (`upload_queue.py`): comprobar,
  nombre, preparar e iniciar, cada uno con su `stage` (que es su punto de cancelación), su fila de Fases y lo que
  deja en `_Trabajo` para el siguiente. Mismo comportamiento que antes; lo fijan
  `test_la_preparacion_recorre_los_pasos_en_orden` y `test_cancelar_para_la_preparacion_en_el_siguiente_punto`.
- **Oleada 3, partir upload_execution.py:** pasa a ser el paquete `services/upload_execution/`: `comun` (constantes, fases,
  secretos), `consultas` (leer y validar), `registro` (logs y artefactos), `estado` (transiciones y avisos), `config`
  (config.yaml compartido), `concurrencia` (puerta de «Subidas en paralelo»), `progreso` (fases), `procesos`
  (subprocesos en marcha), `ejecucion` (el subproceso y `start_upload_job`) y `ciclo_de_vida` (reintentar, cancelar,
  borrar). `__init__` re-exporta todo: `from ...services.upload_execution import X` sigue igual, pero un test que
  parchee un nombre debe hacerlo en el módulo que lo usa.
- **Oleada 3, partir cli.py:** `cli.py` queda como punto de entrada (`main`, `modern_main` y el despacho); los comandos
  viven en el paquete `comandos/`: `parser.py` (`build_parser`), `comunes.py` (tabla, traducción de filtros, conexión),
  `biblioteca.py` (instancias, sync, biblioteca, peticiones, faltantes, *arr), `nomenclatura.py` (nomenclatura y título
  MKV), `subida.py` (subida, tareas, logs), `web.py` (comandos `web`) y `mantenimiento.py` (mantenimiento y demo).
  `emuwarez_uploadrr.cli:main` sigue siendo el entry point; el código se movió sin cambios (`--help` idéntico).
- **Oleada 3, Configuración partida:** `pages/SettingsPage.tsx` queda en el marco (pestañas, aviso y botón de
  guardar) y lo demás vive en `pages/ajustes/`: una pestaña por fichero (`ConfigTab`, `NotificationsTab`,
  `DiagnosticsTab`, `BackupTab`) y una tarjeta por fichero en `config/` y `diagnostico/`. El formulario de la pestaña
  Configuración es `config/useConfigForm.ts`, compartido por sus tarjetas; lo que solo toca una (pruebas de
  conexión, modal de claves de imágenes) está en su tarjeta. Comportamiento igual: lo fija
  `pages/__tests__/SettingsPage.test.tsx` (jsdom, nueva dependencia de desarrollo). Los estilos en línea siguen
  sin pasar a clases.
- **Oleada 3, estilos de Configuración a clases:** `SettingsPage` y `pages/ajustes/` ya no llevan estilos en línea,
  salvo los colores calculados (resultado de una prueba, mensaje de guardado) y el de un icono. Las clases están
  en `styles/ajustes.css` (prefijo `aj-`). Mismo aspecto.
- **Oleada 3, subida por pasos con reintento (#126):** sobre `PASOS` (#127), cada subida enseña sus cuatro pasos con
  nombre (comprobar y poner el nombre, preparar los ficheros, verificar antes de subir, subir con Uploadrr) y cuál se
  paró (`upload_jobs.etapa_parada`, `services/subida_pasos.py`). Un reintento de una subida que ya había preparado los ficheros reanuda desde la
  verificación y reutiliza la preparación si sigue valiendo en disco; «Reintentar desde el principio» lo rehace todo.
  El reintento ahora también conserva las elecciones del pack (`season_overrides_json`).
- **Oleada 3, partir library.py:** `services/library.py` pasa a ser el paquete `services/library/`, sin cambiar lo que
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
- **Oleada 3, un solo limitador para eMuwarez:** toda petición a la API de eMuwarez pasa por
  `integrations/emu_limitador.py` (los conectores de `emu.py` y la prueba de conexión de `integration_tests.py`):
  ventana deslizante de 60 s por API key, planificada para 28 de las 30 que deja eMuwarez. Los recorridos largos
  (catálogo y peticiones) se quedan en 20 por minuto entre todos; los 8 huecos restantes son para las consultas
  sueltas (perfil, probar conexión, detalle, comprobación de antes de subir), que no se ponen a la cola de un
  catálogo y, si tendrían que esperar más de 15 s, fallan con un mensaje claro. Un 429 pausa 60 s a todos los que
  usan esa clave, no solo al que lo recibió. Se van las pausas sueltas (`EMU_MIN_REQUEST_INTERVAL`,
  `EMU_PETICIONES_INTERVALO`, `min_interval`). En los tests, un fixture de `conftest.py` le da a cada test su
  limitador con un reloj falso: nada duerme de verdad.
- **Oleada 3, estilos del asistente a clases:** `UploadWizardModal.tsx` y `components/asistente/` ya no llevan
  `style={{` (de 180 a 3): las clases `asist-*` están en `styles/asistente.css`. Siguen en línea los tres
  `width: '100%'` de `<Tooltip style>` en `PasoSeleccion` y los dos `tituloStyle` de los modales de pistas, porque
  `Tooltip` y `Modal` solo admiten objeto de estilo.
- **Oleada 3, ESLint `react-hooks`:** el frontend tiene `eslint.config.js` con solo `rules-of-hooks` y `exhaustive-deps`
  (nada más), `npm run lint` (`--max-warnings 0`) y un paso en el job `frontend` de la CI. Todo `eslint-disable` de
  esas reglas lleva su motivo tras `--`; ESLint avisa de los que sobran. Una dependencia que falta no se añade a
  ciegas: un efecto que se recrea en cada pintado puede crear un bucle (como el de `RejillaVirtual`).

## Siguiente (oleada 3)

1. Los estilos en línea, a clases. Hecho en el asistente de subida y en Configuración; faltan el resto de pantallas y componentes.
2. `httpx` y un solo limitador de eMuwarez compartido (30 peticiones por minuto).

## Oleada 4

- React 19, Vite 8, Vitest 5 y TypeScript 7.
- Funciones nuevas:
  - subida por lotes;
  - resumen de duplicados y trumps;
  - carril de «listas» ordenado por recompensa;
  - rellenar la petición tras subir;
  - avisar de peticiones nuevas que se pueden rellenar;
  - «Mejoras posibles»;
  - salud del seeding;
  - historial de la cuenta;
  - estadísticas del tracker;
  - sincronizar cuando vuelve una instancia;
  - widget para Homepage;
  - Ctrl+K.
- Rediseño de la interfaz: Hoy, detalle de subida, resumen del asistente, Biblioteca, Peticiones y Configuración.

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
