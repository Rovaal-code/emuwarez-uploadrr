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
  concretos, **no** una probabilidad estadística calibrada contra un
  dataset real (no existe ese dataset todavía — ver "Cómo calibrar").
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

## Cómo calibrar las probabilidades con datos reales

Hoy los rangos de `bits_per_pixel_per_frame` por candidato
(`evidence.py::_BPPF_RANGES`) y los pesos de `STRENGTH_WEIGHT`/
`_TEMPERATURE` (`scoring.py`) son heurísticos, documentados como tales
(`confidence_score`, nunca "probability"). Para calibrarlos con un
dataset real y etiquetado:
1. Recolectar archivos con source conocido (no solo por nombre — con
   verificación humana) y ejecutar `analyze()` sobre cada uno con
   `use_cache=False`.
2. Comparar el candidato ganador contra la etiqueta real; para los fallos,
   mirar qué evidencias pesaron más (`result["evidence"]`) y ajustar sus
   `contributions`/`reliability` en el detector correspondiente.
3. Ajustar `_BPPF_RANGES` con los percentiles reales de
   `bits_per_pixel_per_frame` observados por tier, en vez de las
   estimaciones actuales.
4. Subir `ENGINE_VERSION` — invalida la caché automáticamente.

## Limitaciones conocidas

- No usa Bento4 ni GPAC/MP4Box (parsing profundo de boxes MP4) — MediaInfo
  + ffprobe ya cubren fragmentación/brands para el nivel de detalle que
  necesita el scoring actual; queda como mejora futura si se necesita
  inspeccionar boxes concretas (ej. `mdat`/`moof` a mano).
- El muestreo de bitstream (`sampling.py`) depende del backend de
  almacenamiento — sobre un montaje de red lento puede no completarse
  nunca (se salta con seguridad, ver "Presupuesto de tiempo").
- Las probabilidades de recodificación (`transcode.py`) y los rangos de
  bpppf son heurísticos, no calibrados contra un dataset etiquetado real.
- No distingue un WEBRip re-encodeado de un MicroHD re-encodeado por
  bitrate en el rango medio — ambos dejan la misma huella de encoder de
  mano (limitación también reconocida explícitamente en la spec original).

## Próximas mejoras recomendadas

- Calibración con dataset real (ver arriba).
- Bento4/GPAC para inspección de boxes MP4 cuando el fragmentado/brand no
  sea suficiente.
- Persistir el resultado completo en `library_items` (hoy solo se cachea
  por archivo) para poder listarlo/filtrarlo en Biblioteca sin re-analizar.
