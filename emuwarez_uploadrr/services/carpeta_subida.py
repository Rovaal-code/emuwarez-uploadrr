"""Lo que se le entrega a Uploadrr para subir: enlaces dentro de /config/Uploadrr/uploads.

EL PROBLEMA. `torf` toma el nombre del torrent del nombre de la carpeta, y ese
nombre es la carpeta que recibe QUIEN SE DESCARGUE el release. Entregando la
carpeta de Sonarr tal cual, el torrent se llama "Season 1" — la ficha de
eMuwarez sí sale bien, porque el nombre se le pasa aparte con -mt, pero quien
lo baje se encuentra una carpeta "Season 1" en su disco.

LO QUE SE HACÍA ANTES, y por qué se quita: renombrar la carpeta de Sonarr al
título del release. Funcionaba, pero tocaba la biblioteca del usuario — y
Sonarr es quien gestiona esa carpeta. Además dejaba rutas guardadas apuntando
a un sitio que ya no existía, y de ahí salían nombres calculados con datos de
Radarr/Sonarr en vez de con el fichero.

LO QUE SE HACE AHORA. Una carpeta aparte, con el nombre del release, dentro de
/config/Uploadrr/uploads, y dentro ENLACES DUROS a los ficheros reales:

    …/Sherlock Hound/Season 1/cap1.mkv        ← intacto, de Sonarr
    /config/Uploadrr/uploads/Sherlock Hound S01 …/cap1.mkv   ← enlace duro

Un enlace duro es otro nombre para los MISMOS datos: no ocupa disco, no copia
nada, y borrar uno de los dos no toca al otro. Uploadrr recibe la carpeta
nueva, el torrent se llama como debe, y la biblioteca no se toca.

CUÁNDO NO SE PUEDE. Un enlace duro exige que las dos rutas estén en el mismo
sistema de ficheros. Es habitual tener la configuración en un SSD y los medios
en otro disco, y ahí `os.link` falla con EXDEV. En ese caso se cae a un enlace
simbólico, que cruza sistemas de ficheros sin copiar: mkvmerge y qBittorrent
leen a través de él sin enterarse.

TODO PASA POR AQUÍ, no solo los packs. Una película o un capítulo suelto no
necesitaban esto —a Uploadrr se le entrega el FICHERO, y torf nombra el torrent
con el nombre del fichero, que la nomenclatura ya dejó bien— pero se enlazan
igual para que todo lo que subas esté en el mismo sitio: qBittorrent siembra
siempre desde uploads y la biblioteca no aparece en ninguna ruta de subida.

Un fichero suelto se enlaza DIRECTAMENTE en uploads, nunca dentro de una
carpeta propia: metido en una, torf haría un torrent de varios ficheros con esa
carpeta dentro, y eso cambia el release (comprobado: singlefile vs multifile).

LO QUE NO HACE: borrarlo solo. Mientras siembres, esos enlaces son de donde
qBittorrent lee. Se borra al borrar la subida, no antes.
"""
from __future__ import annotations

import errno
import logging
import os
import shutil
import threading
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# Dentro de /config, que es el volumen que el usuario ya monta: no hay nada
# nuevo que configurar, y sobrevive a reconstruir la imagen.
RAIZ_SUBIDAS = os.environ.get("UPLOADRR_UPLOADS_DIR", "/config/Uploadrr/uploads")

# Crear un enlace y guardarlo en prepared_path, o comprobar que nadie lo usa y
# borrarlo, va de uno en uno: un borrado no se lleva el enlace de otra subida.
ENLACES = threading.Lock()


def _enlazar(origen: str, destino: str) -> str:
    """Enlace duro si se puede, simbólico si no. Devuelve cuál se usó."""
    try:
        os.link(origen, destino)
        return "duro"
    except OSError as e:
        if e.errno not in (errno.EXDEV, errno.EPERM, errno.EMLINK):
            raise
        # EXDEV: distinto sistema de ficheros. EPERM: algunos montajes (CIFS,
        # ciertos NFS) no permiten enlaces duros aunque no crucen nada.
        os.symlink(origen, destino)
        return "simbólico"


def preparar_carpeta_de_pack(
    nombre_release: str,
    ficheros: Iterable[str],
    *,
    raiz: Optional[str] = None,
) -> dict:
    """Deja lista la carpeta que se le pasa a Uploadrr y devuelve qué pasó.

    `nombre_release` es el título del pack, ya saneado como nombre de carpeta.
    `ficheros` son las rutas LOCALES de los capítulos, ya renombrados.

    Si la carpeta existe de antes (un reintento), se rehace: los enlaces son
    baratos y así no queda un capítulo viejo de una tanda anterior.
    """
    raiz = raiz or RAIZ_SUBIDAS
    destino = os.path.join(raiz, nombre_release)

    ficheros = [f for f in ficheros if f]
    if not ficheros:
        return {"status": "blocked", "carpeta": None,
                "errors": ["No hay ficheros que enlazar."]}

    faltan = [f for f in ficheros if not os.path.isfile(f)]
    if faltan:
        return {"status": "blocked", "carpeta": None,
                "errors": [f"No existe: {f}" for f in faltan]}

    try:
        if os.path.isdir(destino):
            # Solo si es nuestra: nunca se borra algo que no hayamos creado.
            if os.path.realpath(destino).startswith(os.path.realpath(raiz)):
                shutil.rmtree(destino)
            else:
                return {"status": "blocked", "carpeta": None,
                        "errors": [f"La carpeta de destino no está bajo {raiz}: {destino}"]}
        os.makedirs(destino, exist_ok=True)
    except OSError as e:
        return {"status": "blocked", "carpeta": None,
                "errors": [f"No se pudo preparar {destino}: {e}"]}

    tipos: set[str] = set()
    try:
        for origen in ficheros:
            tipos.add(_enlazar(origen, os.path.join(destino, os.path.basename(origen))))
    except OSError as e:
        shutil.rmtree(destino, ignore_errors=True)
        return {"status": "blocked", "carpeta": None,
                "errors": [f"No se pudieron enlazar los capítulos: {e}"]}

    return {"status": "ready", "carpeta": destino, "errors": [],
            "enlaces": sorted(tipos), "cuantos": len(ficheros)}


def preparar_fichero_suelto(fichero: str, *, raiz: Optional[str] = None) -> dict:
    """Enlaza UN fichero (película o capítulo) en la carpeta de subidas.

    Directamente en la raíz, sin carpeta propia: dentro de una, torf haría un
    torrent de varios ficheros con esa carpeta dentro y el release dejaría de
    ser un fichero suelto.

    El nombre se conserva tal cual, que ya es el de la nomenclatura: es lo que
    torf usa para nombrar el torrent.
    """
    raiz = raiz or RAIZ_SUBIDAS
    if not fichero or not os.path.isfile(fichero):
        return {"status": "blocked", "ruta": None,
                "errors": [f"No existe: {fichero or '(sin ruta)'}"]}
    if not asegurar_raiz(raiz):
        return {"status": "blocked", "ruta": None,
                "errors": [f"No se pudo crear la carpeta de subidas: {raiz}"]}

    destino = os.path.join(raiz, os.path.basename(fichero))
    try:
        if os.path.lexists(destino):
            # Un reintento, o un enlace de una subida anterior del mismo
            # contenido: se rehace, que es más barato que averiguar si sirve.
            os.unlink(destino)
        tipo = _enlazar(fichero, destino)
    except OSError as e:
        return {"status": "blocked", "ruta": None,
                "errors": [f"No se pudo enlazar en {raiz}: {e}"]}

    return {"status": "ready", "ruta": destino, "errors": [],
            "enlaces": [tipo], "cuantos": 1}


def en_carpeta_de_subidas(ruta: str, *, raiz: Optional[str] = None) -> bool:
    """Si la ruta está en la carpeta de subidas, aunque sea un enlace simbólico
    que apunta a la biblioteca.

    Mira el realpath del PADRE, no el de la ruta: resolver el enlace la dejaría
    fuera de la raíz.
    """
    raiz = raiz or RAIZ_SUBIDAS
    padre, raiz = os.path.realpath(os.path.dirname(ruta)), os.path.realpath(raiz)
    # Por componentes: con startswith, /data/uploads-old pasaba por /data/uploads.
    return os.path.commonpath((padre, raiz)) == raiz


def borrar_de_subidas(ruta: Optional[str], *, raiz: Optional[str] = None) -> bool:
    """Borra de la carpeta de subidas, sea una carpeta de pack o un fichero
    suelto. Solo borra ENLACES: lo de verdad sigue en la biblioteca.

    Nunca toca nada fuera de la carpeta de subidas — `prepared_path` puede
    apuntar a la biblioteca en subidas viejas, anteriores a que todo pasara por
    aquí, y borrar una subida no puede llevarse el fichero del usuario.
    """
    raiz = raiz or RAIZ_SUBIDAS
    if not ruta or not os.path.lexists(ruta):
        return False
    if not en_carpeta_de_subidas(ruta, raiz=raiz):
        logger.warning("No se borra %s: está fuera de %s", ruta, raiz)
        return False
    try:
        if os.path.isdir(ruta) and not os.path.islink(ruta):
            shutil.rmtree(ruta)
        else:
            os.unlink(ruta)
        return True
    except OSError:
        logger.warning("No se pudo borrar de la carpeta de subidas: %s", ruta, exc_info=True)
        return False


def borrar_carpeta_de_pack(carpeta: Optional[str], *, raiz: Optional[str] = None) -> bool:
    """Borra la carpeta de enlaces. Solo borra enlaces: los ficheros de verdad
    siguen donde estaban, que es la gracia de todo esto.

    Devuelve True si borró algo. No lanza: se llama al limpiar una subida y un
    fallo aquí no puede tumbar esa limpieza.
    """
    raiz = raiz or RAIZ_SUBIDAS
    if not carpeta or not os.path.isdir(carpeta):
        return False
    # Nunca fuera de lo nuestro, por si esta ruta llegara de un sitio raro.
    if not os.path.realpath(carpeta).startswith(os.path.realpath(raiz)):
        logger.warning("No se borra %s: está fuera de %s", carpeta, raiz)
        return False
    try:
        shutil.rmtree(carpeta)
        return True
    except OSError:
        logger.warning("No se pudo borrar la carpeta de subida %s", carpeta, exc_info=True)
        return False


def asegurar_raiz(raiz: Optional[str] = None) -> bool:
    """Deja la carpeta de subidas creada y lista. Se llama al arrancar, para
    que exista antes de la primera subida en vez de aparecer a mitad."""
    raiz = raiz or RAIZ_SUBIDAS
    try:
        os.makedirs(raiz, exist_ok=True)
        return True
    except OSError:
        logger.warning("No se pudo crear la carpeta de subidas %s", raiz, exc_info=True)
        return False


def comprobar_enlace(fichero: str, *, raiz: Optional[str] = None) -> dict:
    """Si se puede enlazar ESE fichero dentro de la carpeta de subidas.

    Se comprueba haciéndolo de verdad y deshaciéndolo, no deduciéndolo de los
    números de dispositivo: hay montajes (CIFS, algunos NFS) donde los dos
    lados dan el mismo `st_dev` y aun así `os.link` falla con EPERM. Cuesta
    microsegundos y no puede equivocarse.

    Devuelve {ok, tipo, error}. `tipo` es "duro" o "simbólico": el segundo
    también vale —Uploadrr y qBittorrent leen a través de él— pero conviene
    decirlo, porque significa que la carpeta de subidas está en otro disco.
    """
    raiz = raiz or RAIZ_SUBIDAS
    if not asegurar_raiz(raiz):
        return {"ok": False, "tipo": None,
                "error": f"No se pudo crear la carpeta de subidas: {raiz}"}
    if not fichero or not os.path.isfile(fichero):
        return {"ok": False, "tipo": None,
                "error": f"No existe el archivo con el que probar: {fichero or '(sin ruta)'}"}

    prueba = os.path.join(raiz, f".prueba-enlace-{os.getpid()}")
    try:
        if os.path.lexists(prueba):
            os.unlink(prueba)
        tipo = _enlazar(fichero, prueba)
        return {"ok": True, "tipo": tipo, "error": None}
    except OSError as e:
        return {"ok": False, "tipo": None, "error": f"{raiz}: {e}"}
    finally:
        try:
            if os.path.lexists(prueba):
                os.unlink(prueba)
        except OSError:
            pass
