# eMuwarez Uploadrr - Refactor v1

Este paquete es el primer paso del refactor de `emuwarez-auto-uploader_v1.0.py`.

## Objetivo de esta versión

- Mantener el comportamiento actual de la CLI.
- Separar el proyecto en un paquete Python.
- Exponer módulos por responsabilidad para que los siguientes pasos puedan mover código físicamente sin cambiar la interfaz pública.
- Preparar la base para Radarr/Sonarr, peticiones EMU, SQLite, backend web y Docker.

## Estructura

```text
emuwarez_uploader.py                  # lanzador compatible
emuwarez_uploadrr/
  legacy.py                           # motor actual completo, con script_dir adaptado
  cli.py                              # entrypoint CLI
  constants.py                        # constantes reexportadas
  ui.py                               # helpers de terminal
  logging_utils.py                    # logging
  paths.py                            # rutas
  models.py                           # dataclasses actuales
  crypto.py                           # cifrado de configuración
  config.py                           # configuración propia
  uploadrr_config.py                  # editor config.yaml de Uploadrr
  validators.py                       # validaciones/API/qBittorrent
  bootstrap.py                        # venv/dependencias/bootstrap
  tmdb.py                             # TMDb y matching
  media_info.py                       # MediaInfo
  source.py                           # source
  naming.py                           # nomenclatura
  planner.py                          # construcción de plan
  proposal.py                         # salida de propuesta
  hardlinks.py                        # filesystem/hardlinks
  progress.py                         # progreso Uploadrr
  uploadrr_runner.py                  # ejecución Uploadrr
  results.py                          # resumen final
```

## Uso

Coloca `emuwarez_uploader.py` y la carpeta `emuwarez_uploadrr/` en el directorio donde antes estaba el script monolítico, junto a `Uploadrr/`.

```bash
python3 emuwarez_uploader.py --help
python3 emuwarez_uploader.py --configure
python3 emuwarez_uploader.py /ruta/contenido --dry-run
```

También puedes forzar el directorio base si lo necesitas:

```bash
EMUWAREZ_UPLOADRR_BASE=/home/orangepi/Uploadrr-EMU python3 emuwarez_uploader.py --help
```

## Nota

Esta versión es una refactorización de compatibilidad: la lógica sigue centralizada en `legacy.py` para minimizar riesgo. Los módulos ya existen como fachadas estables. En el siguiente paso se puede mover código real desde `legacy.py` a cada módulo, empezando por `ui.py`, `paths.py`, `constants.py`, `models.py` y `config.py`.
