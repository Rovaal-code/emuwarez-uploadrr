# Motor de detección de source (`services/source_engine`)

Detector multi-herramienta del "source" (BluRay/WEB-DL/HDTV/...) de un
archivo de vídeo, integrado en el botón **Ver MediaInfo** / **Internal
Source Tool** ya existente en el asistente de subida. Sustituye a la
heurística anterior (un único umbral de bitrate en `legacy.py`) por un
sistema de evidencias ponderadas que siempre puntúa los 9 candidatos
oficiales de eMuwarez y nunca devuelve "unknown".

## Candidatos

Coinciden exactamente con la tabla "Formato (Source)" de
`references/nomenclatura-emuwarez.md`:

```
FBD  FDVD  BDRemux  BluRay  MHD  WEB-DL  WEBRIP  HDTV  SD
```

Esto es un vocabulario **distinto** del campo Source seleccionable de la app
(`services/source_assistant.py::EMU_SOURCES`, que por compatibilidad con
datos ya guardados sigue usando `"Full BluRay"`/`"WEBRip"` en vez de
`"FBD"`/`"WEBRIP"`). El puente entre ambos vive en `integration.py`
(`ENGINE_TO_APP_SOURCE`) — es el único punto que conoce los dos vocabularios.

## Dependencias

Ninguna nueva: `mediainfo`, `ffmpeg`/`ffprobe` y `mkvtoolnix` (mkvmerge) ya
estaban instalados en la imagen Docker y en este entorno de desarrollo. No
se usa Bento4/GPAC/ExifTool en esta primera versión (ver "Limitaciones").

## Cómo se ejecuta

Automáticamente: cada vez que se pide **Ver MediaInfo** desde el asistente
de subida (`GET /api/library/{id}/mediainfo`, `media_info_service.py`).
También se puede invocar directamente:

```python
from emuwarez_uploadrr.services.source_engine import analyze
result = analyze("/ruta/al/archivo.mkv")
```

Benchmark:

```bash
python -m emuwarez_uploadrr.services.source_engine.benchmark /ruta/a/dataset
```

Tests:

```bash
pytest tests/test_source_engine.py tests/test_source_engine_realfiles.py -q
```

(el segundo archivo se salta solo si falta alguna de las 3 herramientas).

## Arquitectura

```
tools.py       — invoca mediainfo --Full / ffprobe / mkvmerge -J (vía proc.py)
proc.py        — subprocess con timeout, sin shell, captura acotada
budget.py      — presupuesto de tiempo global compartido
profile.py     — normaliza las 3 salidas a un esquema canónico (MediaProfile)
names.py       — etiqueta nombres de pista (commentary/forced/SDH/dub/...)
transcode.py   — señales de recodificación (encoder, CRF, resize, ...)
sampling.py    — muestreo acotado del bitstream (ffprobe -read_intervals)
evidence.py    — ~15 detectores, cada uno aporta puntos a los 9 candidatos
scoring.py     — combina evidencias, normaliza, elige ganador, explica
cache.py       — caché en sqlite (tabla source_engine_cache)
engine.py      — orquestador: ejecuta todo lo anterior con el presupuesto
integration.py — mapeo al vocabulario de la app + wrapper "nunca falla"
benchmark.py   — CLI de benchmark
```

Los 3 tools primarios (mediainfo/ffprobe/mkvmerge) se lanzan **en
paralelo** — su coste es I/O (leer cabeceras/índice), no CPU, así que el
tiempo total es aprox. el más lento de los tres, no la suma.

El muestreo de bitstream (`sampling.py`) es **best-effort**: solo se
ejecuta con el tiempo que quede del presupuesto global tras los 3 tools
primarios, y nunca bloquea el resultado — si no le queda tiempo, el
resultado sale igual, con `sample_coverage: 0`.

## Presupuesto de tiempo

`DEFAULT_BUDGET_S = 10.0` (constants.py) — pensado para "un ordenador
potente con almacenamiento local" (igual que pide la spec). Sobre un
montaje de red lento (SSHFS a un servidor saturado, por ejemplo) el propio
`mediainfo`/`ffprobe` pueden tardar más que eso — en ese caso el motor
**no se cuelga**: cada tool tiene su propio timeout derivado del
presupuesto, y si ninguno responde a tiempo se devuelve un resultado bien
formado (9 candidatos, todos en el suelo estructural, certeza "bajo") en
vez de colgar la petición. Puede pasarse un presupuesto mayor
explícitamente (`analyze(path, budget_s=30.0)`) para una validación puntual.

## Caché

`services/source_engine/cache.py`, tabla `source_engine_cache`
(migración `_migrate_source_engine_cache` en `database.py`, versión de
esquema 24). Clave: `(ruta real, tamaño, mtime, versión del motor)` — sin
hash de contenido. Cambiar el archivo, la versión del motor
(`ENGINE_VERSION`) o las reglas de scoring invalida automáticamente la
entrada correspondiente.

## Qué significa cada score

- **raw_score**: suma de todas las contribuciones de evidencia para ese
  candidato (positivas menos negativas), con un suelo de -60 para que
  ningún candidato desaparezca de la tabla.
- **normalized_score / confidence_score**: `raw_score` pasado por una
  softmax (temperatura 18) — siempre suma ~100% entre los 9 candidatos.
  Es una puntuación de confianza relativa entre estos 9 candidatos
  concretos, **no** una probabilidad estadística en sentido frecuentista
  estricto (no hay un dataset externo etiquetado por terceros contra el
  que calibrarla formalmente) — aunque sí está calibrada contra una
  muestra real grande (ver "Calibración realizada" abajo).
- **margin**: diferencia de `normalized_score` entre el 1º y el 2º,
  en puntos porcentuales.
- **certainty** ("alto"/"medio"/"bajo"): etiqueta puramente descriptiva
  del margen (umbrales en `constants.py::CERTAINTY_THRESHOLDS`); el
  ganador se decide siempre por `raw_score`, la certeza solo comunica
  cuán reñida estuvo la carrera.
- **evidence_strength**: cuánta evidencia (en cantidad × fuerza ×
  fiabilidad) se acumuló en total, independientemente de si el resultado
  fue reñido o no — un archivo con muy poca información (sin nombre, sin
  duración, sin audio) puede tener un ganador claro y aun así una
  `evidence_strength` baja.

## Cómo añadir una nueva regla de evidencia

1. Añadir una función en `evidence.py` que reciba el `MediaProfile` (y,
   si hace falta, las señales de `transcode.py`/`sampling.py`) y devuelva
   una lista de `Evidence(feature, value, contributions, strength,
   reliability, explanation)`.
2. `contributions` es un dict con las 9 claves de `CANDIDATES` — usa el
   helper `_c(**kwargs)` para no tener que enumerar las que quedan a 0.
3. Añadirla a la lista `detectors` de `collect_all_evidence()`.
4. Ningún detector debe decidir un candidato por sí solo — mantén los
   valores moderados (ver los tests `test_pgs_alone_does_not_dominate_*`
   como referencia de "cuánto es demasiado").
5. Añadir un test unitario en `test_source_engine.py` con un
   `MediaProfile` de ejemplo construido a mano (sin tocar subprocess).

## Calibración realizada (2026-07-23)

Se hizo una pasada de calibración real contra el informe de MediaInfo de
toda la biblioteca del usuario (`mediainfo_report_20260717_144848.txt`,
2802 archivos). Metodología: la "verdad" usada es el source que indica el
propio **nombre de archivo** (vía `legacy._detect_source_by_name`, la misma
regex que ya usa el resto de la app como primera prioridad — no un dataset
etiquetado externamente, pero sí una base razonable dado que son releases
ya seleccionados/nombrados según la guía oficial). El script vive en
`/tmp/.../scratchpad/calibrate.py` de esa sesión (no forma parte del
repo — procesa un fichero privado del usuario fuera de él); se parseó el
texto de MediaInfo directamente (sin red, sin releer los archivos) y se
corrió `evidence.py`/`scoring.py` de forma "name-blind" (las evidencias
nunca ven el nombre del archivo, solo lo técnico) para comparar contra esa
etiqueta.

De 2802 archivos, 1410 tenían un source reconocible por nombre (el resto,
sin etiqueta, se ignoraron). Resultado **antes** de la calibración: 21.2%
de acierto top-1 (30.6% top-2). Hallazgo clave: la señal
`video_transcode_probability` (huella de encoder x264/x265) estaba
prácticamente siempre presente — tanto en WEB-DL genuinos de Netflix como
en re-encodes — porque **varias plataformas de streaming usan libx264/
libx265 internamente y dejan la misma cadena de `Encoded_Library_Settings`
que un encoder manual**, algo que la primera versión asumía que NO pasaba.
Eso hacía que casi cualquier WEB-DL real se puntuara como WEBRip/BluRay.

Corrección aplicada (`transcode.py` + `evidence.py::transcode_signal`):
solo el marcador **two-pass** (`pass=2` en los ajustes del encoder) se
trata ahora como señal fuerte de recodificación de mano — las plataformas
de streaming usan CRF/VBR de una sola pasada, no two-pass clásico. Un
fingerprint x264/x265 sin two-pass pasó de pesar como señal "fuerte" a
pesar como señal "débil" (nudge pequeño, no decisivo). También se
recalibraron los rangos de `bits_per_pixel_per_frame` por tier
(`evidence.py::_BPPF_RANGES`) con los percentiles p25/p75 reales
observados (MediaInfo ya calcula ese campo, no hubo que recalcularlo), y
se añadió una señal nueva y débil (`subtitle_language_breadth`): las
plataformas grandes tienden a empaquetar subtítulos de muchos idiomas en
su propio WEB-DL.

**Resultado después de la calibración: 76.6% de acierto top-1 (86.5%
top-2)** sobre los mismos 1410 archivos — sin haber tocado nunca el
nombre del archivo durante el análisis, solo evidencia técnica.
Confusiones que quedan (minoritarias): WEBRip clasificado como WEB-DL
(117 casos) y BluRay/WEB-DL confundidos entre sí con BDRemux en el rango
alto de bitrate (cuentan con muestra real pequeña o nula — ver
limitaciones). `BDRemux`/`FBD`/`FDVD`/`SD` no tenían ninguna muestra real
en esta biblioteca concreta (0 archivos con ese source en el nombre).

**Corrección conceptual adicional (misma fecha, sin datos reales de
respaldo — pura razón técnica)**: `SD` se quitó de `_BPPF_RANGES`. La
primera versión asumía "formato antiguo = bitrate bajo", pero normalizado
por resolución es al revés — MPEG-2 (el códec de DVD) es mucho menos
eficiente que AVC/HEVC, así que un DVD real normalizado da un bpppf
moderado-alto pese a su Mbps absoluto modesto (pocos píxeles). `FBD`/
`FDVD` tampoco tienen rango de bpppf: un Blu-ray/DVD completo no se
distingue de un BDRemux/DVD-SD por bitrate — la película en sí tiene el
mismo bitrate, la diferencia es la estructura de disco completa (menús,
varios streams) frente a un único archivo, y eso ya lo decide
`structural_single_file` con fuerza. La detección de SD queda enteramente
en manos de `resolution_signal` (altura SD) y `video_codec_signal`
(MPEG-2/DivX/Xvid), que no tienen ese problema de confusión con la
eficiencia del códec.

## Segunda pasada de calibración: catálogo completo de eMuwarez (2026-07-23)

Se repitió el mismo tipo de calibración contra el catálogo completo de
torrents de eMuwarez ya sincronizado (`emu_catalog`, 11338 filas — ver
`services/emu_catalog.py`), muchísimo más grande que la biblioteca personal
pero con mucha menos profundidad: solo nombre, resolución y tamaño, **sin
duración, sin audio/subtítulos/capítulos, sin encoder**. Se filtró a solo
películas (7816, sin patrón de serie `SxxEyy` ni `season_number`) porque
permiten asumir una duración razonable (110 min a 24 fps) para poder
estimar bpppf — el catálogo no trae la duración real, así que este bpppf
es una **estimación**, más ruidosa que la de MediaInfo real.

Aportó justo lo que faltaba: **BDRemux tenía 0 muestras** en la biblioteca
personal; aquí hay 199, con p25-p75 real de **0.401-0.716** — mucho más
alto que la estimación original sin validar (0.20-0.55), confirmando que
BDRemux es, junto con FBD, el tier de mayor bitrate normalizado de todos.
MHD pasó de 8 a 25 muestras combinadas; su rango se ensanchó para cubrir
ambas pasadas (0.07-0.13).

Validación cruzada con el pipeline completo (evidencia + scoring, sin ver
el nombre) sobre las 7816 películas: **75.8% de acierto top-1 (82.7%
top-2)** — consistente con el 77.6%/87.7% de la biblioteca personal, pero
es un **límite inferior**: al catálogo le faltan señales que si ayudan en
un análisis real (audio sin pérdida, PGS, capítulos, scan type), así que
la mayor confusión aquí (BluRay→WEB-DL, 1193 casos) es en buena parte un
artefacto de esta prueba reducida, no necesariamente del motor completo.

## Cómo seguir calibrando

1. Recolectar (o pedir) archivos con `SD` reales (1 sola muestra en ambas
   pasadas de 2026-07) y repetir el mismo proceso — especialmente para
   confirmar o corregir el razonamiento anterior sobre SD con datos reales.
2. Para los fallos restantes (`result["evidence"]` trae la contribución de
   cada señal), ajustar `contributions`/`reliability` del detector que más
   pesó en el error.
3. Subir `ENGINE_VERSION` tras cualquier cambio de reglas — invalida la
   caché automáticamente.

## Limitaciones conocidas

- No usa Bento4 ni GPAC/MP4Box (parsing profundo de boxes MP4) — MediaInfo
  + ffprobe ya cubren fragmentación/brands para el nivel de detalle que
  necesita el scoring actual; impacto bajo (la mayoría de aportes de la
  guía son MKV, donde mkvmerge ya da todo esto). Mejora futura si algún
  día hace falta inspeccionar boxes concretas de MP4 sin decodificar
  (tabla de keyframes `stss`, fragmentación `moof` exacta) — especialmente
  útil para acelerar el muestreo de bitstream en redes lentas. GPAC
  (MP4Box) está en repos oficiales (Debian y Arch/CachyOS); Bento4 no.
- El muestreo de bitstream (`sampling.py`) depende del backend de
  almacenamiento — sobre un montaje de red lento (ej. SSHFS saturado)
  puede no completarse nunca; se salta con seguridad (ver "Presupuesto de
  tiempo"), nunca bloquea el resultado.
- `BDRemux` no tenía ninguna muestra real en la calibración de 2026-07 —
  su rango de bitrate sigue sin validar. `FBD`/`FDVD`/`SD` no usan bpppf
  en absoluto (ver "Corrección conceptual" arriba) por diseño, no por
  falta de datos.
- No distingue un WEBRip re-encodeado de un MicroHD re-encodeado por
  bitrate en el rango medio — ambos dejan la misma huella de encoder de
  mano (limitación también reconocida explícitamente en la spec original).

## Próximas mejoras recomendadas

- Calibración con dataset real (ver arriba).
- Bento4/GPAC para inspección de boxes MP4 cuando el fragmentado/brand no
  sea suficiente.
- Persistir el resultado completo en `library_items` (hoy solo se cachea
  por archivo) para poder listarlo/filtrarlo en Biblioteca sin re-analizar.
