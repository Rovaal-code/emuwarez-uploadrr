#!/bin/sh
# docker-entrypoint.sh — makes Uploadrr-EMU's writable state survive across
# container recreation without the user having to mount anything for it.
#
# Uploadrr-EMU is bundled inside the image at /opt/Uploadrr (see Dockerfile) —
# it is NOT an external bind mount, on purpose: one less thing to configure.
# But two of its subdirectories need to be writable and persistent:
#   data/ — config.yaml, staged/restored with TMDb/eMuwarez keys on every upload
#   tmp/  — torrents, screenshots and descriptions written during a real upload
# /opt/Uploadrr itself lives in the image's layers, which are discarded on
# every rebuild/recreate — so instead of writing there, these two subdirs are
# replaced with symlinks into /config/Uploadrr/{data,tmp}, inside the /config
# volume the user already mounts for the database. Nothing new to configure.
set -eu

DATA_TARGET="/config/Uploadrr/data"
TMP_TARGET="/config/Uploadrr/tmp"

mkdir -p "$TMP_TARGET"

if [ ! -e "$DATA_TARGET" ]; then
    # First boot with this /config volume — seed it from whatever the image's
    # Uploadrr-EMU checkout shipped (its own default config.yaml etc.) so a
    # fresh deploy doesn't start from an empty data/.
    if [ -d /opt/Uploadrr/data ] && [ ! -L /opt/Uploadrr/data ]; then
        cp -a /opt/Uploadrr/data "$DATA_TARGET"
    else
        mkdir -p "$DATA_TARGET"
    fi
fi

rm -rf /opt/Uploadrr/data /opt/Uploadrr/tmp
ln -s "$DATA_TARGET" /opt/Uploadrr/data
ln -s "$TMP_TARGET" /opt/Uploadrr/tmp

exec "$@"
