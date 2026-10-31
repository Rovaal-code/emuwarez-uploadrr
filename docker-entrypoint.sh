#!/bin/sh
# docker-entrypoint.sh — prepara en /config lo que Uploadrr-EMU necesita guardar.
#
# Uploadrr-EMU va dentro de la imagen, en /opt/Uploadrr (ver Dockerfile), no en un
# montaje. Lo que tiene que sobrevivir a recrear el contenedor se guarda en el
# volumen /config, y la imagen ya trae los enlaces hacia allí:
#   data/config.yaml, data/config.yaml.bak, data/cookies/ → /config/Uploadrr/data/
#   tmp/ (torrents, capturas y descripciones de cada subida) → /config/Uploadrr/tmp
# El resto de data/ (services.json, tags.json, plantillas...) se queda en la imagen:
# una versión nueva lo actualiza. Aquí solo se crean los destinos; en /opt/Uploadrr
# no se escribe, así que sirve cualquier UID y funcionan los montajes a mano.
set -eu

UPLOADRR="/opt/Uploadrr"
ESTADO="/config/Uploadrr"
mkdir -p "$ESTADO/data/cookies" "$ESTADO/tmp"
# Donde se preparan los packs de temporada para subir: una carpeta con el
# nombre del release y enlaces a los capítulos, para que el torrent se llame
# como debe sin tocar la carpeta de Sonarr (services/carpeta_subida.py).
mkdir -p "$ESTADO/uploads"

# Primera vez con este /config: el config.yaml sale del ejemplo de la imagen. Un
# /config anterior ya lo tiene (y el resto de lo que guardaba, que ahora no se usa).
# Si data/ no es el de la imagen (un montaje a mano), no se toca.
if [ -L "$UPLOADRR/data/config.yaml" ] && [ ! -e "$ESTADO/data/config.yaml" ]; then
    cp "$UPLOADRR/data/backup/example_config.yaml" "$ESTADO/data/config.yaml"
fi

exec "$@"
