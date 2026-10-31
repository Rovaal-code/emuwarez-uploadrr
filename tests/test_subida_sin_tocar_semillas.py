"""La subida no puede corromper un torrent que siembra el archivo de la biblioteca.

Con mkvmerge/mkvpropedit de verdad, sobre MKV pequeños hechos con ffmpeg. Lo que
se comprueba en cada caso es lo que importa en el NAS: los bytes y el nombre del
original (y de su hardlink de la descarga) no cambian si lo comparte alguien, y
lo que se sube vive en la carpeta de subidas con el nombre de eMuwarez.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from emuwarez_uploadrr.services import upload_queue as uq

pytestmark = pytest.mark.skipif(
    not all(shutil.which(t) for t in ("ffmpeg", "mediainfo", "mkvmerge", "mkvpropedit")),
    reason="hacen falta ffmpeg, mediainfo y mkvtoolnix",
)

TITULO_FUENTE = "Fuente [www.web.com]"
PROPUESTO = "Peli.2024.1080p.WEB-DL.AVC.ESP-ING-EMU"


@pytest.fixture(scope="module")
def mkv_base(tmp_path_factory):
    """Vídeo + audio inglés + audio castellano, sin nombres de pista."""
    out = tmp_path_factory.mktemp("mkv") / "base.mkv"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=2",
        "-map", "0:v", "-map", "1:a", "-map", "2:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-c:a:1", "ac3",
        "-metadata", f"title={TITULO_FUENTE}",
        "-metadata:s:a:0", "language=eng", "-metadata:s:a:1", "language=spa",
        str(out),
    ], check=True, timeout=60)
    return out


def _sha(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _mkv_info(p) -> dict:
    data = json.loads(subprocess.run(["mkvmerge", "-J", str(p)], capture_output=True, text=True).stdout)
    return {
        "titulo": (data.get("container") or {}).get("properties", {}).get("title"),
        "pistas": [(t["type"], t["properties"].get("language"), t["properties"].get("track_name"))
                   for t in data["tracks"]],
    }


@pytest.fixture
def entorno(isolated_db, tmp_path, monkeypatch):
    from emuwarez_uploadrr.database import connect, init_db
    from emuwarez_uploadrr.services import carpeta_subida, uploadrr_contract
    from emuwarez_uploadrr.services.settings import set_setting

    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", str(tmp_path / "uploads"))
    monkeypatch.setattr(uploadrr_contract, "DEFAULT_ALLOWED_ROOTS", [str(tmp_path)])
    (tmp_path / "U").mkdir()
    (tmp_path / "U" / "upload.py").write_text("")
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    for k, v in (("emu.api_key", "a"), ("tmdb.api_key", "b"), ("uploadrr.path", str(tmp_path / "U"))):
        set_setting(conn, k, v)
    conn.commit()
    return {"conn": conn, "tmp": tmp_path, "uploads": tmp_path / "uploads"}


def _modo(entorno, modo: str) -> None:
    from emuwarez_uploadrr.services.settings import set_setting
    set_setting(entorno["conn"], "remux.track_mode", modo)
    entorno["conn"].commit()


def _reflink(como: str):
    """Sustituto de carpeta_subida.clonar: "copia" hace de reflink (inodo
    propio, mismos bytes) y "no" falla como en ext4/tmpfs."""
    def clonar(origen, destino):
        if como == "no":
            raise OSError(errno.EOPNOTSUPP, "Operation not supported")
        shutil.copyfile(origen, destino)
    return clonar


def _pelicula(entorno, mkv_base, *, carpeta: Path, nombre="Peli (2024) WEBDL-1080p.mkv", semilla=True):
    """Una película de la biblioteca. Con `semilla`, además un hardlink en la
    carpeta de descargas: el torrent que la sigue sembrando."""
    carpeta.mkdir(parents=True, exist_ok=True)
    f = carpeta / nombre
    shutil.copyfile(mkv_base, f)
    seed = None
    if semilla:
        (entorno["tmp"] / "downloads").mkdir(exist_ok=True)
        seed = entorno["tmp"] / "downloads" / "Peli.2024.WEB.mkv"
        os.link(f, seed)
    conn = entorno["conn"]
    iid = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                      path, size_bytes, tmdb_id, resolution, updated_at)
           VALUES ('movie', 'Peli', 2024, 'Disponible', 'Sin petición', 'No adaptada', ?, ?, '1', '1080p',
                   CURRENT_TIMESTAMP)""", (str(f), f.stat().st_size)).lastrowid
    now = datetime.now(timezone.utc).isoformat()
    pid = conn.execute(
        """INSERT INTO nomenclature_proposals (library_item_id, status, proposed_title, proposed_torrent_name,
                                               proposed_filename, created_at, updated_at)
           VALUES (?, 'valid', 'Peli', ?, ?, ?, ?)""",
        (iid, PROPUESTO.replace(".", " "), PROPUESTO, now, now)).lastrowid
    conn.commit()
    return {"id": iid, "proposal_id": pid, "f": f, "seed": seed}


def _subir(entorno, item_id: int, proposal_id: int | None = None) -> dict:
    """Pasa un trabajo por toda la cola, hasta justo antes de arrancar Uploadrr."""
    from emuwarez_uploadrr.services.upload_execution import _upload_concurrency_gate, get_upload_job_logs
    conn = entorno["conn"]
    jid = conn.execute(
        """INSERT INTO upload_jobs (library_item_id, status, stage, title, path, source_path, queued_until,
                                    nomenclature_proposal_id, created_at, updated_at)
           VALUES (?, 'queued', 'queued', 'X', '', '', '2099-01-01T00:00:00+00:00', ?,
                   CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""", (item_id, proposal_id)).lastrowid
    conn.commit()
    visto, refrescos = {}, []

    def arrancar(job_id, **kw):
        visto.update(dict(conn.execute("SELECT prepared_path, status FROM upload_jobs WHERE id = ?",
                                       (job_id,)).fetchone()))
        return {"error": None}

    with patch("emuwarez_uploadrr.services.upload_execution.start_upload_job", arrancar), \
         patch("emuwarez_uploadrr.services.library.refresh_arr_and_resync",
               lambda c, iid, **k: refrescos.append(iid)):
        uq._run_queued_job(jid)
    if visto:
        _upload_concurrency_gate.release()  # la cola la cede al hilo de Uploadrr, que aquí no existe
    job = dict(conn.execute("SELECT * FROM upload_jobs WHERE id = ?", (jid,)).fetchone())
    logs = [entry["message"] for entry in get_upload_job_logs(jid, conn=conn)["logs"]]
    return {"job": job, "visto": visto, "refrescos": refrescos, "logs": logs, "id": jid}


# ---------------------------------------------------------------------------
# Fichero compartido con un torrent (st_nlink > 1): nunca se escribe en él
# ---------------------------------------------------------------------------

def test_compartido_con_reflink_edita_solo_la_copia(entorno, mkv_base, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("copia"))
    _modo(entorno, "solo_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)")
    antes = _sha(peli["f"])

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    destino = entorno["uploads"] / f"{PROPUESTO}.mkv"
    assert r["visto"] == {"prepared_path": str(destino), "status": "ready"}, r["logs"]
    # El original y su semilla: mismos bytes, mismo nombre.
    assert _sha(peli["f"]) == antes and _sha(peli["seed"]) == antes
    assert [p.name for p in peli["f"].parent.iterdir()] == ["Peli (2024) WEBDL-1080p.mkv"]
    assert _mkv_info(peli["f"])["titulo"] == TITULO_FUENTE
    # La copia: inodo propio, con los nombres y el título de eMuwarez.
    assert destino.stat().st_ino != peli["f"].stat().st_ino
    info = _mkv_info(destino)
    assert info["titulo"] == PROPUESTO
    assert all(nombre for _t, _l, nombre in info["pistas"])
    assert any("copia por reflink" in m and "el original no se ha tocado" in m for m in r["logs"])
    assert r["refrescos"] == []          # nada que releer en Radarr/Sonarr
    snapshot = json.loads(r["job"]["remux_snapshot_json"])
    assert snapshot["ordered_tracks"] and "omitida" not in snapshot


def test_compartido_sin_reflink_se_enlaza_tal_cual_y_lo_dice(entorno, mkv_base, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("no"))
    _modo(entorno, "solo_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)")
    antes = _sha(peli["f"])

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    destino = entorno["uploads"] / f"{PROPUESTO}.mkv"
    assert r["visto"]["status"] == "ready", r["logs"]
    assert destino.stat().st_ino == peli["f"].stat().st_ino     # enlace duro
    assert _sha(peli["f"]) == antes and _sha(peli["seed"]) == antes
    aviso = next(m for m in r["logs"] if "sin reflink" in m)
    assert "los nombres de las pistas" in aviso and "el título interno" in aviso
    assert json.loads(r["job"]["remux_snapshot_json"]) == {"omitida": "sin reflink"}


def test_compartido_con_reflink_de_verdad_o_sin_el(entorno, mkv_base):
    """Sin sustitutos: en btrfs/XFS sale una copia por reflink; en el overlay o
    tmpfs del contenedor, un enlace duro con el aviso. El original, igual siempre."""
    from emuwarez_uploadrr.services.carpeta_subida import clonar
    _modo(entorno, "solo_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)")
    antes = _sha(peli["f"])
    try:
        clonar(str(peli["f"]), str(entorno["tmp"] / "prueba.mkv"))
        hay_reflink = True
    except OSError:
        hay_reflink = False

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    destino = entorno["uploads"] / f"{PROPUESTO}.mkv"
    assert r["visto"]["status"] == "ready", r["logs"]
    assert _sha(peli["f"]) == antes and _sha(peli["seed"]) == antes
    if hay_reflink:
        assert destino.stat().st_ino != peli["f"].stat().st_ino
        assert _mkv_info(destino)["titulo"] == PROPUESTO
        assert any("copia por reflink" in m for m in r["logs"])
    else:
        assert destino.stat().st_ino == peli["f"].stat().st_ino
        assert any("sin reflink" in m for m in r["logs"])


def test_compartido_no_se_reordena(entorno, mkv_base, monkeypatch):
    """Reordenar reescribe el fichero entero: ni en el original compartido ni
    con una copia completa."""
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("copia"))
    _modo(entorno, "reordenar_y_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)")
    antes = _sha(peli["f"])

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    destino = entorno["uploads"] / f"{PROPUESTO}.mkv"
    assert r["visto"]["status"] == "ready", r["logs"]
    assert _sha(peli["f"]) == antes and _sha(peli["seed"]) == antes
    assert any("no se reordenan las pistas" in m for m in r["logs"])
    # La copia conserva el orden del original (inglés primero) y sí lleva nombres.
    assert [lang for t, lang, _n in _mkv_info(destino)["pistas"] if t == "audio"] == ["eng", "spa"]
    assert not list(peli["f"].parent.glob("*.part"))


def test_si_falla_la_edicion_de_la_copia_se_borra_y_se_enlaza(entorno, mkv_base, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida, mkv_title
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("copia"))
    monkeypatch.setattr(mkv_title, "apply_internal_title_update",
                        lambda *a, **k: {"status": "error", "errors": ["Error: disco lleno"]})
    _modo(entorno, "solo_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)")
    antes = _sha(peli["f"])

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    destino = entorno["uploads"] / f"{PROPUESTO}.mkv"
    assert r["visto"]["status"] == "ready", r["logs"]
    assert destino.stat().st_ino == peli["f"].stat().st_ino
    assert _sha(destino) == antes
    assert any("falló la edición de la copia (Error: disco lleno)" in m for m in r["logs"])


# ---------------------------------------------------------------------------
# Fichero que no comparte nadie (st_nlink == 1)
# ---------------------------------------------------------------------------

def test_sin_compartir_las_pistas_se_editan_en_el_original_pero_no_el_titulo(entorno, mkv_base, monkeypatch):
    """El nombre y el título interno no se tocan nunca en la biblioteca."""
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("no"))
    _modo(entorno, "solo_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)", semilla=False)
    inodo = peli["f"].stat().st_ino

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    destino = entorno["uploads"] / f"{PROPUESTO}.mkv"
    assert r["visto"]["status"] == "ready", r["logs"]
    info = _mkv_info(peli["f"])
    assert peli["f"].stat().st_ino == inodo and peli["f"].exists()
    assert all(nombre for _t, _l, nombre in info["pistas"])      # renombradas en el sitio
    assert info["titulo"] == TITULO_FUENTE                          # el título, no
    assert destino.stat().st_ino == inodo
    assert any("pistas editadas en el original" in m for m in r["logs"])
    assert any("sin reflink" in m and "el título interno" in m for m in r["logs"])
    assert r["refrescos"] == [peli["id"]]                           # Radarr relee el archivo


def test_sin_compartir_se_reordena_y_se_barren_los_restos(entorno, mkv_base, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("copia"))
    _modo(entorno, "reordenar_y_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)", semilla=False)
    carpeta = peli["f"].parent
    viejo, reciente = carpeta / "tmpabcdefgh.mkv.part", carpeta / "tmpzzzzzzzz.mkv.part"
    propio = carpeta / "Peli (2024) WEBDL-1080p.remux.mkv.part"
    for f in (viejo, reciente, propio):
        f.write_bytes(b"resto")
    hace_3h = time.time() - 3 * 3600
    os.utime(viejo, (hace_3h, hace_3h))

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    assert r["visto"]["status"] == "ready", r["logs"]
    assert [lang for t, lang, _n in _mkv_info(peli["f"])["pistas"] if t == "audio"] == ["spa", "eng"]
    assert _mkv_info(peli["f"])["titulo"] == TITULO_FUENTE
    # El de un intento matado y el propio, fuera; el de otro remux en marcha, no.
    assert sorted(p.name for p in carpeta.iterdir()) == ["Peli (2024) WEBDL-1080p.mkv", "tmpzzzzzzzz.mkv.part"]
    assert _mkv_info(entorno["uploads"] / f"{PROPUESTO}.mkv")["titulo"] == PROPUESTO


def test_sin_espacio_para_reordenar_falla_antes_con_los_numeros(entorno, mkv_base, monkeypatch):
    from collections import namedtuple
    from emuwarez_uploadrr.services import mkv_remux
    uso = namedtuple("uso", "total used free")
    monkeypatch.setattr(mkv_remux.shutil, "disk_usage", lambda p: uso(10**9, 10**9, 1000))
    _modo(entorno, "reordenar_y_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)", semilla=False)
    antes = _sha(peli["f"])

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    assert r["job"]["status"] == "failed"
    assert "No hay espacio para reordenar" in r["job"]["error_message"]
    assert "GB" in r["job"]["error_message"]
    assert _sha(peli["f"]) == antes
    assert not list(peli["f"].parent.glob("*.part"))


# ---------------------------------------------------------------------------
# Ninguno, reintentos y borrado
# ---------------------------------------------------------------------------

def test_ninguno_no_toca_ni_las_pistas_ni_el_titulo(entorno, mkv_base):
    _modo(entorno, "ninguno")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)", semilla=False)
    antes = _sha(peli["f"])

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    destino = entorno["uploads"] / f"{PROPUESTO}.mkv"
    assert r["visto"]["status"] == "ready", r["logs"]
    assert _sha(peli["f"]) == antes and destino.stat().st_ino == peli["f"].stat().st_ino
    assert json.loads(r["job"]["remux_snapshot_json"]) == {"omitida": "Ninguno"}
    assert r["refrescos"] == []


def test_reintentar_no_suma_enlaces_ni_copias(entorno, mkv_base, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("no"))
    _modo(entorno, "solo_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)")
    antes = _sha(peli["f"])

    for _ in range(2):
        r = _subir(entorno, peli["id"], peli["proposal_id"])
        assert r["visto"]["status"] == "ready", r["logs"]
        entorno["conn"].execute("UPDATE upload_jobs SET status = 'failed' WHERE id = ?", (r["id"],))
        entorno["conn"].commit()

    assert os.listdir(entorno["uploads"]) == [f"{PROPUESTO}.mkv"]
    assert peli["f"].stat().st_nlink == 3          # biblioteca, semilla y el enlace de subidas
    assert _sha(peli["f"]) == antes


def test_borrar_la_subida_solo_quita_lo_de_la_carpeta_de_subidas(entorno, mkv_base, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.upload_execution import DELETE_CONFIRMATION_TOKEN, delete_upload_job
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("copia"))
    _modo(entorno, "solo_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["tmp"] / "media" / "Peli (2024)")
    antes = _sha(peli["f"])
    r = _subir(entorno, peli["id"], peli["proposal_id"])
    entorno["conn"].execute("UPDATE upload_jobs SET status = 'failed' WHERE id = ?", (r["id"],))
    entorno["conn"].commit()

    assert delete_upload_job(r["id"], confirmation=DELETE_CONFIRMATION_TOKEN, conn=entorno["conn"])["ok"]

    assert os.listdir(entorno["uploads"]) == []
    assert _sha(peli["f"]) == antes and _sha(peli["seed"]) == antes


# ---------------------------------------------------------------------------
# Un archivo que ya está en la carpeta de subidas (instancias "Up")
# ---------------------------------------------------------------------------

def test_en_la_carpeta_de_subidas_se_renombra_y_se_titula_en_su_sitio(entorno, mkv_base, monkeypatch):
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink("no"))
    _modo(entorno, "solo_renombrar")
    peli = _pelicula(entorno, mkv_base, carpeta=entorno["uploads"] / "Peli (2024)", semilla=False)
    inodo = peli["f"].stat().st_ino

    r = _subir(entorno, peli["id"], peli["proposal_id"])

    renombrado = entorno["uploads"] / "Peli (2024)" / f"{PROPUESTO}.mkv"
    assert r["visto"]["status"] == "ready", r["logs"]
    assert [p.name for p in renombrado.parent.iterdir()] == [renombrado.name]
    assert renombrado.stat().st_ino == inodo
    assert _mkv_info(renombrado)["titulo"] == PROPUESTO           # título en su sitio
    assert (entorno["uploads"] / f"{PROPUESTO}.mkv").stat().st_ino == inodo
    fila = entorno["conn"].execute("SELECT path, nomenclature_status FROM library_items WHERE id = ?",
                                   (peli["id"],)).fetchone()
    assert fila["path"] == str(renombrado) and fila["nomenclature_status"] == "Correcta"
    assert r["refrescos"] == [peli["id"]]


# ---------------------------------------------------------------------------
# Un pack desde la biblioteca (/data/media), de punta a punta
# ---------------------------------------------------------------------------

def _temporada(entorno, mkv_base) -> dict:
    """Una temporada de Sonarr en media/, cada capítulo con su hardlink en downloads/."""
    conn = entorno["conn"]
    carpeta = entorno["tmp"] / "media" / "Serie (2020)" / "Season 1"
    carpeta.mkdir(parents=True)
    (entorno["tmp"] / "downloads").mkdir(exist_ok=True)
    serie = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                      updated_at)
           VALUES ('series', 'Serie', 2020, 'Disponible', 'Sin petición', 'N/A', CURRENT_TIMESTAMP)""").lastrowid
    temporada = conn.execute(
        """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                      parent_id, season_number, updated_at)
           VALUES ('season', 'Serie - Temporada 1', 2020, 'Disponible', 'Sin petición', 'N/A', ?, 1,
                   CURRENT_TIMESTAMP)""", (serie,)).lastrowid
    capitulos = []
    for n in (1, 2):
        f = carpeta / f"Serie (2020) - S01E0{n} - Capítulo {n} WEBDL-1080p.mkv"
        shutil.copyfile(mkv_base, f)
        seed = entorno["tmp"] / "downloads" / f"Serie.S01E0{n}.WEB.mkv"
        os.link(f, seed)
        conn.execute(
            """INSERT INTO library_items (item_type, title, year, local_status, request_status, nomenclature_status,
                                          parent_id, season_number, episode_number, path, quality, resolution,
                                          audio_languages, subtitle_languages, updated_at)
               VALUES ('episode', ?, 2020, 'Disponible', 'Sin petición', 'No adaptada', ?, 1, ?, ?,
                       'WEBDL-1080p', '1080p', 'eng/spa', 'spa', CURRENT_TIMESTAMP)""",
            (f"Capítulo {n}", temporada, n, str(f)))
        capitulos.append({"f": f, "seed": seed, "sha": _sha(f)})
    conn.commit()
    return {"id": temporada, "carpeta": carpeta, "capitulos": capitulos}


@pytest.mark.parametrize("reflink", ["copia", "no"])
def test_un_pack_de_la_biblioteca_va_a_su_carpeta_con_los_nombres_de_emuwarez(entorno, mkv_base, monkeypatch,
                                                                              reflink):
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.season_pack import _sanitize_pack_folder_name, build_season_pack_plan
    monkeypatch.setattr(carpeta_subida, "clonar", _reflink(reflink))
    _modo(entorno, "solo_renombrar")
    pack = _temporada(entorno, mkv_base)

    r = _subir(entorno, pack["id"])

    assert r["visto"]["status"] == "ready", r["logs"]
    plan = build_season_pack_plan(pack["id"], conn=entorno["conn"])
    titulo = json.loads(r["job"]["uploadrr_command_json"])["title"]          # el -mt
    carpeta = Path(r["visto"]["prepared_path"])
    # La carpeta del pack se llama como el torrent, nunca "Season 1".
    assert carpeta.parent == entorno["uploads"]
    assert carpeta.name == _sanitize_pack_folder_name(titulo) == _sanitize_pack_folder_name(plan["season_pack_title"])
    assert carpeta.name.startswith("Serie S01")
    assert sorted(os.listdir(carpeta)) == sorted(ep["nombre"] for ep in plan["episodes"])
    assert all(n.startswith("Serie.S01E0") and n.endswith(".mkv") for n in os.listdir(carpeta))
    # La biblioteca y las semillas, intactas: nombres y bytes.
    assert sorted(p.name for p in pack["carpeta"].iterdir()) == [
        "Serie (2020) - S01E01 - Capítulo 1 WEBDL-1080p.mkv", "Serie (2020) - S01E02 - Capítulo 2 WEBDL-1080p.mkv"]
    for cap in pack["capitulos"]:
        assert _sha(cap["f"]) == cap["sha"] and _sha(cap["seed"]) == cap["sha"]
        assert _mkv_info(cap["f"])["titulo"] == TITULO_FUENTE
    inodos = {cap["f"].stat().st_ino for cap in pack["capitulos"]}
    enlazados = {(carpeta / n).stat().st_ino for n in os.listdir(carpeta)}
    if reflink == "copia":
        assert not inodos & enlazados                 # copias con inodo propio
        assert all(_mkv_info(carpeta / n)["titulo"] != TITULO_FUENTE for n in os.listdir(carpeta))
    else:
        assert enlazados == inodos                    # enlaces duros
    episodios = json.loads(r["job"]["remux_snapshot_json"])["episodes"]
    assert len(episodios) == 2
