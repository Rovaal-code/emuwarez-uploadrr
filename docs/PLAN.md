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
- **Oleada 3, partir cli.py:** `cli.py` queda como punto de entrada (`main`, `modern_main` y el despacho); los comandos
  viven en el paquete `comandos/`: `parser.py` (`build_parser`), `comunes.py` (tabla, traducción de filtros, conexión),
  `biblioteca.py` (instancias, sync, biblioteca, peticiones, faltantes, *arr), `nomenclatura.py` (nomenclatura y título
  MKV), `subida.py` (subida, tareas, logs), `web.py` (comandos `web`) y `mantenimiento.py` (mantenimiento y demo).
  `emuwarez_uploadrr.cli:main` sigue siendo el entry point; el código se movió sin cambios (`--help` idéntico).
- **Oleada 3, subida por pasos con reintento (#126):** sobre `PASOS` (#127), cada subida enseña sus cuatro pasos con
  nombre (comprobar y poner el nombre, preparar los ficheros, verificar antes de subir, subir con Uploadrr) y cuál se
  paró (`upload_jobs.etapa_parada`, `services/subida_pasos.py`). Un reintento de una subida que ya había preparado los ficheros reanuda desde la
  verificación y reutiliza la preparación si sigue valiendo en disco; «Reintentar desde el principio» lo rehace todo.
  El reintento ahora también conserva las elecciones del pack (`season_overrides_json`).
- **Oleada 3, asistente de subida partido (#132):** `UploadWizardModal.tsx` queda en el marco (pasos y cierre) y lo
  demás vive en `components/asistente/`: el estado y la lógica en `useAsistente.ts` (con `useComprobaciones.ts` y
  `useDetallesTemporada.ts`), un componente por paso (`PasoSeleccion`, `PasoArchivo`, `PasoTemporada`, `PasoSubida`,
  `PasoSubidaTanda`) y las piezas compartidas (`RemuxTable`, `MediaInfoTable`, `Capitulos`, `piezas`,
  `constantes`). Comportamiento igual: lo fija `components/__tests__/UploadWizardModal.test.tsx` (jsdom). Arreglado
  de paso: «Ver nombre de todos los capítulos» y «Ver Pistas», si estaban abiertos al cambiar el idioma del pack, se
  recargan con el idioma confirmado en vez de quedarse vacíos.

## Siguiente (oleada 3)

1. Partir `library.py` y `upload_execution.py`.
2. Partir `SettingsPage.tsx`; los estilos en línea, a clases.
3. `httpx` y un solo limitador de eMuwarez compartido (30 peticiones por minuto).
4. ESLint `react-hooks`.

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
