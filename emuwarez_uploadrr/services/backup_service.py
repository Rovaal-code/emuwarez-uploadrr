"""Backup and restore of CONFIG_DIR — keys left out unless asked for, confirmation required for restore."""
from __future__ import annotations

import datetime
import fnmatch
import os
import posixpath
import shutil
import sqlite3
import tarfile
import tempfile
from pathlib import Path

from ..database import CANONICAL_SETTING_ALIASES, SCHEMA_VERSION, _version_guardada, olvidar_esquema
from .settings import all_settings, es_secreto, get_setting_canonical, set_setting

RESTORE_CONFIRMATION = "RESTAURAR_CONFIG"
_DB_NAME = "emuwarez_uploadrr.db"
_CABECERA_SQLITE = b"SQLite format 3\x00"
# Lo que no va en la copia: las copias anteriores, los enlaces de subida y los
# temporales de Uploadrr (capturas, torrents; en una instalación real, 1,7 GB).
# Una carpeta "backups" a cualquier profundidad tampoco: la copia no se mete a sí misma.
_FUERA_DE_LA_COPIA = (("Uploadrr", "uploads"), ("Uploadrr", "tmp"))
# Lo que solo va en la copia con secretos. El config.yaml de Uploadrr-EMU y su
# .bak (donde van los cambios a mano) pueden llevar claves de cualquier tracker
# y con cualquier nombre: taparlas línea a línea no da garantías. Las cookies
# son sesiones abiertas. config.py, config.json y backup/old_config.py son
# configuraciones antiguas de Uploadrr que aún reconoce (su .gitignore las
# deja fuera por lo mismo). config.json y config.enc.json en la raíz son del
# CLI antiguo (services/cli_config.py) y llevan la API key de eMuwarez.
_CON_CLAVES = (
    ("Uploadrr", "data", "config.yaml"),
    ("Uploadrr", "data", "config.yaml.bak"),
    ("Uploadrr", "data", "cookies"),
    ("Uploadrr", "data", "config.py"),
    ("Uploadrr", "data", "config.json"),
    ("Uploadrr", "data", "backup", "old_config.py"),
    ("config.json",),
    ("config.enc.json",),
)


def _fuera_de_la_copia(rel_parts: tuple[str, ...], include_secrets: bool = False) -> bool:
    fuera = _FUERA_DE_LA_COPIA if include_secrets else _FUERA_DE_LA_COPIA + _CON_CLAVES
    return "backups" in rel_parts or any(rel_parts[:len(p)] == p for p in fuera)


def _es_sqlite(path: Path) -> bool:
    with open(path, "rb") as f:
        return f.read(16) == _CABECERA_SQLITE


def _vaciar_claves(snapshot: Path) -> None:
    """Deja vacías las claves de la instantánea: los ajustes secretos
    (settings.es_secreto) y la API key de cada instancia de Radarr/Sonarr.

    El VACUUM no sobra: un UPDATE cambia la fila pero el valor anterior puede
    seguir en los bytes del fichero, y la base viva ya trae en sus páginas
    libres las claves que se cambiaron antes. VACUUM reescribe el fichero solo
    con lo que está vivo.
    """
    conn = sqlite3.connect(str(snapshot))
    conn.row_factory = sqlite3.Row
    try:
        # La instantánea hereda el modo WAL de la base viva. Fuera de WAL, el
        # VACUUM reescribe el propio .db, que es lo único que entra en la copia.
        conn.execute("PRAGMA journal_mode = DELETE")
        for key, value in all_settings(conn).items():
            if value and es_secreto(key):
                set_setting(conn, key, "")
        try:
            conn.execute("UPDATE instances SET api_key = ''")
        except sqlite3.OperationalError:
            pass  # una base sin la tabla: no hay claves que vaciar
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()


def _add_db_snapshot(
    tar: tarfile.TarFile, db_file: Path, arcname: str, *, include_secrets: bool = False,
) -> None:
    """Mete en la copia una instantánea coherente de la base de datos, con las
    claves vacías salvo que se pidan.

    Con la app en marcha la base está en modo WAL: copiar el .db, el -wal y el
    -shm uno detrás de otro mientras alguien escribe da una copia rota. La API
    de backup de SQLite lee todo dentro de una misma transacción.
    """
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / db_file.name
        # mode=rw: si la base ha desaparecido, falla en vez de crear una vacía.
        src = sqlite3.connect(db_file.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
        dst = sqlite3.connect(str(snapshot))
        try:
            src.backup(dst)
        except sqlite3.DatabaseError:
            # Una base SQLite que falla no se copia en crudo: saldría rota.
            if _es_sqlite(db_file):
                raise
            snapshot = db_file
        finally:
            dst.close()
            src.close()
        if snapshot != db_file and not include_secrets:
            _vaciar_claves(snapshot)
        tar.add(snapshot, arcname=arcname)


def _get_config_dir() -> Path:
    env = os.environ.get("CONFIG_DIR")
    if env:
        return Path(env)
    return Path.home() / ".config" / "emuwarez-renamer"


def _get_backup_dir(base: Path | None = None) -> Path:
    config = base if base is not None else _get_config_dir()
    d = config / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_backup_dir() -> Path:
    """Public accessor for the directory backups are read from/written to."""
    return _get_backup_dir()


def get_config_inventory() -> dict:
    """Returns a summary of config files — counts only, no secret values."""
    config_dir = _get_config_dir()
    if not config_dir.exists():
        return {"config_dir": str(config_dir), "exists": False, "files": [], "total_size_bytes": 0}
    files = []
    total = 0
    for f in sorted(config_dir.rglob("*")):
        rel_parts = f.relative_to(config_dir).parts
        # Lo mismo que excluye create_config_backup en la copia normal, la que
        # hace la interfaz: este inventario es lo que se le enseña al usuario
        # como "esto es lo que se va a copiar", así que contar aquí algo que la
        # copia no lleva sería mentir.
        if _fuera_de_la_copia(rel_parts):
            continue
        if f.is_file():
            size = f.stat().st_size
            total += size
            files.append({"name": str(f.relative_to(config_dir)), "size_bytes": size})
    return {
        "config_dir": str(config_dir),
        "exists": True,
        "files": files,
        "total_size_bytes": total,
    }


def create_config_backup(
    *,
    output_dir: Path | None = None,
    include_secrets: bool = False,
    confirmation: str | None = None,
) -> dict:
    """Creates a .tar.gz backup of CONFIG_DIR in output_dir (or default backups/).

    By default the keys stay out: the database goes with every secret setting
    and every instance API key empty, and the files that carry keys
    (_CON_CLAVES) are skipped. include_secrets=True keeps them all and
    requires confirmation=RESTAURAR_CONFIG (reused token).
    The archive always excludes the backups/ subdirectory.
    """
    if include_secrets and confirmation != RESTORE_CONFIRMATION:
        return {
            "ok": False,
            "error": f"Para incluir secretos, pasa confirmation='{RESTORE_CONFIRMATION}'",
        }

    config_dir = _get_config_dir()
    if not config_dir.exists():
        return {"ok": False, "error": f"CONFIG_DIR no existe: {config_dir}"}

    backup_dir = _get_backup_dir(config_dir) if output_dir is None else Path(output_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "_with_secrets" if include_secrets else ""
    archive_name = f"emuwarez_config_{ts}{suffix}.tar.gz"
    archive_path = backup_dir / archive_name

    # "backups": no meter copias dentro de copias.
    #
    # "Uploadrr/uploads": ahí viven los enlaces de lo que se está subiendo o
    # sembrando (services/carpeta_subida.py). Con enlaces SIMBÓLICOS entrarían
    # como enlaces rotos, inútiles; con enlaces DUROS —que es lo que se usa
    # cuando /config y los medios comparten sistema de ficheros— tar no los
    # distingue de un fichero normal y metería CADA PELÍCULA ENTERA en la copia
    # (comprobado: 5 MB de película en una copia que debía pesar 1 KB). Una
    # copia de configuración no puede engordar con el catálogo.
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in sorted(config_dir.rglob("*")):
            rel = item.relative_to(config_dir)
            if _fuera_de_la_copia(rel.parts, include_secrets):
                continue
            # La base antes que is_file(): si desaparece por el camino, la copia falla.
            if item.name == _DB_NAME:
                _add_db_snapshot(tar, item, str(rel), include_secrets=include_secrets)
                continue
            if not item.is_file() or item.name in (f"{_DB_NAME}-wal", f"{_DB_NAME}-shm"):
                continue
            try:
                tar.add(item, arcname=str(rel))
            except FileNotFoundError:
                # Un temporal que desaparece entre listarlo y copiarlo.
                continue

    size = archive_path.stat().st_size
    return {
        "ok": True,
        "archive_path": str(archive_path),
        "archive_name": archive_name,
        "size_bytes": size,
        "include_secrets": include_secrets,
        "config_dir": str(config_dir),
    }


def list_config_backups(directory: Path | None = None) -> list[dict]:
    """Lists existing backup archives, newest first."""
    config_dir = _get_config_dir()
    backup_dir = directory if directory is not None else _get_backup_dir(config_dir)
    if not backup_dir.exists():
        return []
    backups = []
    for f in sorted(backup_dir.glob("emuwarez_config_*.tar.gz"), reverse=True):
        stat = f.stat()
        backups.append({
            "name": f.name,
            "path": str(f),
            "size_bytes": stat.st_size,
            "created_at": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    return backups


def resolver_copia(nombre: str) -> Path | None:
    """La copia con ese nombre dentro de get_backup_dir(), o None si no es una de las que lista
    list_config_backups. La API no acepta rutas: así no lee ningún tar de fuera de esa carpeta."""
    if not fnmatch.fnmatchcase(nombre, "emuwarez_config_*.tar.gz") or any(c in nombre for c in ("/", "\\", "\x00")):
        return None
    ruta = get_backup_dir() / nombre
    # is_file() sigue los enlaces: un enlace con nombre de copia llevaría a un tar de fuera.
    return ruta if ruta.is_file() and not ruta.is_symlink() else None


def _motivo_de_rechazo(tar: tarfile.TarFile, config_dir: Path) -> str | None:
    """Por qué no se puede restaurar esta copia, o None si se puede: algún miembro se saldría de
    config_dir (el filtro "data" de tarfile) o su base es de un esquema más nuevo que este código.
    Se mira antes de tocar nada: la base se coloca primero y un rechazo a medias dejaría la
    instalación a medio restaurar."""
    miembros = tar.getmembers()
    for miembro in miembros:
        try:
            tarfile.data_filter(miembro, str(config_dir))
        except tarfile.FilterError as exc:
            return f"La copia no es segura ({miembro.name}): {exc}"
        # Solo nombres canónicos y relativos: «./emuwarez_uploadrr.db», «x/../emuwarez_uploadrr.db» o
        # «/emuwarez_uploadrr.db» (el filtro le quita la barra) son la base para la extracción pero no para
        # las comprobaciones de abajo, que la buscan por su nombre.
        if miembro.name != posixpath.normpath(miembro.name) or miembro.name.startswith("/"):
            return f"La copia no es válida: nombre no canónico «{miembro.name}»"
    # Lo que el filtro no ve porque mira cada miembro por separado: un nombre repetido (la segunda base se
    # colocaría sin haberse mirado), la base como algo que no es un fichero, o un fichero que es a la vez carpeta
    # (la extracción fallaría con la base ya cambiada). Las copias de la aplicación nunca lo tienen.
    nombres = [posixpath.normpath(m.name) for m in miembros]
    visto: set[str] = set()
    for nombre in nombres:
        if nombre in visto:
            return f"La copia no es válida: repite «{nombre}»"
        visto.add(nombre)
    ficheros = {n for m, n in zip(miembros, nombres) if not m.isdir()}
    for nombre in nombres:
        padre = posixpath.dirname(nombre)
        while padre:
            if padre in ficheros:
                return f"La copia no es válida: «{padre}» es a la vez un fichero y una carpeta"
            padre = posixpath.dirname(padre)
    if any(n == _DB_NAME and not m.isfile() for m, n in zip(miembros, nombres)):
        return "La copia no es válida: su base de datos no es un fichero normal"
    base = next((m for m in miembros if m.name == _DB_NAME), None)
    if base is None:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        ruta = Path(tmp) / _DB_NAME
        with tar.extractfile(base) as origen, open(ruta, "wb") as destino:
            shutil.copyfileobj(origen, destino)
        version = _version_de_base(ruta)
    if version is not None and version > SCHEMA_VERSION:
        return (
            f"La copia es de una versión más nueva (esquema {version}) que esta aplicación "
            f"(esquema {SCHEMA_VERSION}): restaurarla dejaría la aplicación sin arrancar. "
            "Actualiza la imagen y restaura entonces."
        )
    return None


def _version_de_base(ruta: Path) -> int | None:
    """El esquema de una base, o None si no es SQLite o no lo dice."""
    conn = sqlite3.connect(str(ruta))
    try:
        return _version_guardada(conn)
    except sqlite3.DatabaseError:
        return None
    finally:
        conn.close()


def restore_config_backup(
    backup_path: str,
    *,
    dry_run: bool = True,
    apply: bool = False,
    confirmation: str | None = None,
) -> dict:
    """Restores a backup archive to CONFIG_DIR.

    dry_run=True (default) previews only.
    apply=True requires confirmation=RESTAURAR_CONFIG and dry_run=False.
    Keys the backup doesn't carry (empty in its database, files not in it)
    stay as they are in the current install.
    """
    path = Path(backup_path)
    if not path.exists():
        return {"ok": False, "dry_run": dry_run, "error": f"Archivo no encontrado: {backup_path}"}
    if not tarfile.is_tarfile(str(path)):
        return {"ok": False, "dry_run": dry_run, "error": "El archivo no es un tarball válido"}

    do_apply = apply and not dry_run
    if do_apply and confirmation != RESTORE_CONFIRMATION:
        return {
            "ok": False,
            "dry_run": dry_run,
            "error": f"Confirmación requerida: pasa confirmation='{RESTORE_CONFIRMATION}'",
        }

    config_dir = _get_config_dir()

    with tarfile.open(str(path), "r:gz") as tar:
        members = tar.getnames()
        motivo = _motivo_de_rechazo(tar, config_dir)
    if motivo:
        return {"ok": False, "dry_run": dry_run, "error": motivo}

    if dry_run or not do_apply:
        return {
            "ok": True,
            "dry_run": True,
            "action": "preview",
            "archive": str(path),
            "target_dir": str(config_dir),
            "files_in_archive": len(members),
            "files": members[:50],
            "message": "Previsualización — no se han restaurado archivos",
        }

    config_dir.mkdir(parents=True, exist_ok=True)
    conservadas: list[str] = []
    with tarfile.open(str(path), "r:gz") as tar:
        resto = []
        for member in tar.getmembers():
            if member.name != _DB_NAME or not member.isfile():
                resto.append(member)
                continue
            # La base primero: si falla, el resto de ficheros sigue como estaba.
            with tempfile.TemporaryDirectory() as tmp:
                restaurada = Path(tmp) / _DB_NAME
                with tar.extractfile(member) as origen, open(restaurada, "wb") as destino:
                    shutil.copyfileobj(origen, destino)
                conservadas = _colocar_base(restaurada, config_dir / _DB_NAME)
        tar.extractall(path=config_dir, members=resto, filter="data")

    message = f"Restauración completada: {len(members)} archivos"
    if conservadas:
        message += (
            f". Se han conservado {len(conservadas)} claves de la instalación actual"
            " que el backup no llevaba"
        )
    return {
        "ok": True,
        "dry_run": False,
        "action": "restored",
        "archive": str(path),
        "target_dir": str(config_dir),
        "files_restored": len(members),
        "secrets_kept": conservadas,
        "message": message,
    }


def _canonica(key: str) -> str:
    """La grafía con punto de un alias antiguo (tmdb_api_key -> tmdb.api_key)."""
    return next((punto for punto, alias in CANONICAL_SETTING_ALIASES.items() if alias == key), key)


def _conservar_claves(restaurada: Path, viva: Path) -> list[str]:
    """Pone en la base restaurada las claves de la instalación actual que la
    copia no trae, y devuelve cuáles.

    Una copia normal las lleva vacías (_vaciar_claves): restaurarla tal cual
    dejaría la instalación sin ninguna. Lo que la copia sí trae manda.
    """
    actual = sqlite3.connect(str(viva), timeout=30)
    actual.row_factory = sqlite3.Row
    try:
        ajustes = {k: v for k, v in all_settings(actual).items() if v and es_secreto(k)}
        try:
            instancias = {
                (r["type"], r["name"]): r["api_key"]
                for r in actual.execute("SELECT type, name, api_key FROM instances")
                if r["api_key"]
            }
        except sqlite3.OperationalError:
            instancias = {}
    finally:
        actual.close()

    conservadas: list[str] = []
    conn = sqlite3.connect(str(restaurada))
    conn.row_factory = sqlite3.Row
    try:
        # Por la grafía con punto: si la copia trae el alias antiguo con valor,
        # la clave está, y ponerle al lado la actual la taparía. Se decide
        # antes de escribir nada, o la clave con punto recién puesta haría
        # creer que su alias también venía en la copia.
        faltan = [k for k in ajustes if not get_setting_canonical(conn, _canonica(k))]
        for key in faltan:
            set_setting(conn, key, ajustes[key])
            conservadas.append(key)
        for (tipo, nombre), api_key in instancias.items():
            try:
                cur = conn.execute(
                    "UPDATE instances SET api_key = ? WHERE type = ? AND name = ? AND api_key = ''",
                    (api_key, tipo, nombre),
                )
            except sqlite3.OperationalError:
                break  # una copia sin la tabla: no hay instancias que completar
            if cur.rowcount:
                conservadas.append(f"{tipo}:{nombre}")
        conn.commit()
    finally:
        conn.close()
    return conservadas


def _colocar_base(restaurada: Path, viva: Path) -> list[str]:
    """Pone la base de la copia en el sitio de la actual, conservando las
    claves que la copia no trae. Devuelve cuáles ha conservado.

    Se coloca con la API de backup de SQLite y no sobrescribiendo el .db: con
    la app en marcha, junto a la base vive su -wal, y SQLite lo aplicaría
    encima del fichero nuevo.
    """
    # Un fichero vacío sí vale: para SQLite es una base sin nada.
    viva_no_es_base = viva.exists() and viva.stat().st_size > 0 and not _es_sqlite(viva)
    if viva_no_es_base or not _es_sqlite(restaurada):
        # La de la copia no es una base (_add_db_snapshot la copió en crudo),
        # o la actual no lo es: no hay nada que fusionar, va tal cual.
        shutil.copyfile(restaurada, viva)
        olvidar_esquema()
        return []
    conservadas = _conservar_claves(restaurada, viva) if viva.exists() else []
    src = sqlite3.connect(str(restaurada))
    dst = sqlite3.connect(str(viva), timeout=30)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
        olvidar_esquema()  # la restaurada puede ser de otra versión de esquema
    return conservadas
