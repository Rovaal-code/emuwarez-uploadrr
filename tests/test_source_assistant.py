"""Tests for source_assistant service (Phase 10A)."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def _make_conn(tmp_path):
    from emuwarez_uploadrr.database import connect, init_db
    import os
    os.environ["CONFIG_DIR"] = str(tmp_path)
    conn = connect(str(tmp_path / "db.sqlite3"))
    init_db(conn)
    return conn


def _insert_library_item(conn, title="Test Movie", tmdb_id="123", path=None):
    conn.execute(
        "INSERT INTO library_items (title, item_type, tmdb_id, local_status, path) VALUES (?,?,?,?,?)",
        (title, "movie", tmdb_id, "downloaded", path),
    )
    conn.commit()
    row = conn.execute("SELECT last_insert_rowid() as id").fetchone()
    return row["id"]


# MediaInfo of the real file is now mandatory to build the fields (the wizard
# blocks otherwise), so tests provide an accessible file + a stubbed report.
_MI_OK = {
    "available": True,
    "audio_summary": "ESP AC3 5.1",
    "rows": [
        {"field": "Códec de vídeo", "mediainfo": "AVC", "emu": "H.264"},
        {"field": "HDR/DV", "mediainfo": None, "emu": None},
        {"field": "Source", "mediainfo": "del nombre del archivo", "emu": "WEB-DL"},
    ],
}


def _accessible_item(conn, tmp_path, **kw):
    f = tmp_path / "movie.mkv"
    f.write_bytes(b"x" * 2048)
    return _insert_library_item(conn, path=str(f), **kw)


def _insert_proposal(conn, item_id, torrent_name="Test.Movie.2024.1080p.WEB-DL.AMZN-EMUWAREZ"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT INTO nomenclature_proposals
           (library_item_id, status, proposed_filename, proposed_title, created_at, updated_at)
           VALUES (?,?,?,?,?,?)""",
        (item_id, "valid", torrent_name, "Test Movie", now, now),
    )
    conn.commit()


def test_list_emu_sources_returns_all():
    from emuwarez_uploadrr.services.source_assistant import list_emu_sources, EMU_SOURCES
    result = list_emu_sources()
    assert len(result) == len(EMU_SOURCES)
    for s in result:
        assert "code" in s
        assert "label" in s


def test_list_emu_providers_returns_all():
    from emuwarez_uploadrr.services.source_assistant import list_emu_providers, EMU_PROVIDERS
    result = list_emu_providers()
    assert len(result) == len(EMU_PROVIDERS)
    for p in result:
        assert "code" in p
        assert "name" in p


def test_build_source_string_webdl_nf():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    assert _build_source_string("WEB-DL", "NF") == "NF WEB-DL"


def test_build_source_string_webdl_dsnp():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    assert _build_source_string("WEB-DL", "DSNP") == "DSNP WEB-DL"


def test_build_source_string_webrip_ignores_provider():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    assert _build_source_string("WEBRip", "NF") == "WEBRip"


def test_build_source_string_none_source():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    assert _build_source_string(None, "AMZN") is None


def test_get_tmdb_available_providers_never_raises():
    with patch("emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw", return_value=[]):
        from emuwarez_uploadrr.services.source_assistant import get_tmdb_available_providers
        result = get_tmdb_available_providers(99999, "movie", region="ES")
        assert isinstance(result, list)


def test_get_tmdb_available_providers_handles_error():
    """_get_tmdb_available_providers_raw never raises; internal errors return []."""
    from emuwarez_uploadrr.integrations import tmdb as tmdb_mod
    with patch.object(tmdb_mod, "get_movie_watch_providers", side_effect=Exception("Network error")):
        from emuwarez_uploadrr.services.source_assistant import _get_tmdb_available_providers_raw
        result = _get_tmdb_available_providers_raw(99999, "movie", region="ES")
        assert result == []


def test_build_editable_nomenclature_fields_not_found(tmp_path):
    conn = _make_conn(tmp_path)
    from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
    result = build_editable_nomenclature_fields(9999, conn=conn)
    assert "error" in result


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_build_editable_nomenclature_fields_basic(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _accessible_item(conn, tmp_path, title="Dune", tmdb_id="438631")
    _insert_proposal(conn, item_id, "Dune.2021.1080p.WEB-DL.AMZN-EMUWAREZ")

    with patch(
        "emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw",
        return_value=[],
    ), patch(
        "emuwarez_uploadrr.services.media_info_service.build_mediainfo_report",
        return_value=_MI_OK,
    ):
        from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
        result = build_editable_nomenclature_fields(item_id, conn=conn)

    assert "fields" in result
    assert "torrent_name" in result
    assert "internal_mkv_title" in result


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_build_editable_nomenclature_fields_applies_overrides(tmp_path):
    """Regression: a season pack's Source/Proveedor/Tag overrides (applied
    uniformly to every episode via build_season_pack_plan/apply_season_pack)
    never reached this function at all, so "Ver nombre de todos los
    capítulos" kept showing each episode's own auto-detected values even
    after overriding the season pack's title."""
    conn = _make_conn(tmp_path)
    item_id = _accessible_item(conn, tmp_path, title="Dune", tmdb_id="438631")
    _insert_proposal(conn, item_id, "Dune.2021.1080p.BluRay.x264-EMUWAREZ")

    with patch(
        "emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw",
        return_value=[],
    ), patch(
        "emuwarez_uploadrr.services.media_info_service.build_mediainfo_report",
        return_value=_MI_OK,
    ):
        from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
        result = build_editable_nomenclature_fields(
            item_id, conn=conn,
            source_override="WEB-DL", provider_override="NF", tag_override="MYTAG",
        )

    assert result["fields"]["source"] == "WEB-DL"
    assert result["fields"]["provider"] == "NF"
    assert result["fields"]["tag"] == "MYTAG"


def test_update_nomenclature_fields_preview_webdl(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Pelicula", tmdb_id=None)
    _insert_proposal(conn, item_id, "Pelicula.2023.1080p.WEB-DL.NF-EMUWAREZ")

    from emuwarez_uploadrr.services.source_assistant import update_nomenclature_fields_preview
    fields = {
        "title": "Pelicula",
        "year": "2023",
        "resolution": "1080p",
        "source": "WEB-DL",
        "provider": "NF",
        "video_codec": "H.265",
        "audio_summary": "DDP5.1",
        "subs": "SPA",
        "tag": "EMUWAREZ",
    }
    result = update_nomenclature_fields_preview(item_id, fields, conn=conn)
    assert "torrent_name" in result
    assert "internal_mkv_title" in result
    torrent_name = result["torrent_name"]
    assert "NF WEB-DL" in torrent_name or "NF.WEB-DL" in torrent_name


def test_update_nomenclature_fields_preview_bluray(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Pelicula", tmdb_id=None)
    _insert_proposal(conn, item_id, "Pelicula.2023.1080p.BluRay-EMUWAREZ")

    from emuwarez_uploadrr.services.source_assistant import update_nomenclature_fields_preview
    fields = {
        "title": "Pelicula",
        "year": "2023",
        "resolution": "1080p",
        "source": "BluRay",
        "provider": "AMZN",
        "video_codec": "H.265",
        "audio_summary": "DTS-HD",
        "subs": "SPA",
        "tag": "EMUWAREZ",
    }
    result = update_nomenclature_fields_preview(item_id, fields, conn=conn)
    torrent_name = result.get("torrent_name", "")
    assert "AMZN" not in torrent_name
    assert "BluRay" in torrent_name or "bluray" in torrent_name.lower()


def test_suggest_provider_no_tmdb(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="NoTMDb", tmdb_id=None)

    from emuwarez_uploadrr.services.source_assistant import suggest_provider_for_item
    result = suggest_provider_for_item(item_id, conn=conn)
    assert "suggested" in result or "error" in result or result.get("suggested") is None


def _insert_arbol(conn, tmdb_serie="555", tmdb_temporada=None, tmdb_episodio=None):
    """Una serie con una temporada y un episodio; devuelve (serie, temporada, episodio)."""
    def _fila(tipo, tmdb, padre=None, nombre="x"):
        conn.execute(
            "INSERT INTO library_items (title, item_type, tmdb_id, parent_id, local_status, path) VALUES (?,?,?,?,?,?)",
            (nombre, tipo, tmdb, padre, "downloaded", None))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    serie = _fila("series", tmdb_serie, nombre="Serie")
    temporada = _fila("season", tmdb_temporada, serie, "Temporada 1")
    episodio = _fila("episode", tmdb_episodio, temporada, "Episodio 1")
    return serie, temporada, episodio


@pytest.mark.parametrize("quien", ["episodio", "temporada"])
def test_suggest_provider_usa_el_tmdb_de_la_serie_si_el_episodio_o_la_temporada_no_lo_tienen(tmp_path, quien):
    """Un episodio o una temporada antiguos (guardados antes de copiarles el de la serie) no traen `tmdb_id`: se
    pregunta a TMDb por el de la serie, como serie de televisión."""
    conn = _make_conn(tmp_path)
    _, temporada, episodio = _insert_arbol(conn)
    from emuwarez_uploadrr.services import source_assistant as sa
    with patch.object(sa, "get_tmdb_available_providers", return_value=["NF"]) as tmdb:
        result = sa.suggest_provider_for_item({"episodio": episodio, "temporada": temporada}[quien], conn=conn)
    assert result["suggested"] == "NF"
    tmdb.assert_called_once()
    assert tmdb.call_args.args[0] == 555 and tmdb.call_args.args[1] != "movie"


def test_suggest_provider_ignora_el_tmdb_de_una_temporada_que_no_es_el_de_la_serie(tmp_path):
    """Solo vale el id de un antepasado que sea una serie: el de una temporada histórica podría ser otro."""
    conn = _make_conn(tmp_path)
    _, _, episodio = _insert_arbol(conn, tmdb_serie="555", tmdb_temporada="999")
    from emuwarez_uploadrr.services import source_assistant as sa
    with patch.object(sa, "get_tmdb_available_providers", return_value=["NF"]) as tmdb:
        sa.suggest_provider_for_item(episodio, conn=conn)
    assert tmdb.call_args.args[0] == 555


def test_suggest_provider_prefiere_el_tmdb_propio_del_episodio(tmp_path):
    conn = _make_conn(tmp_path)
    _, _, episodio = _insert_arbol(conn, tmdb_episodio="777")
    from emuwarez_uploadrr.services import source_assistant as sa
    with patch.object(sa, "get_tmdb_available_providers", return_value=["NF"]) as tmdb:
        sa.suggest_provider_for_item(episodio, conn=conn)
    assert tmdb.call_args.args[0] == 777


def test_suggest_provider_sin_tmdb_en_ningun_nivel_sigue_sin_sugerir(tmp_path):
    conn = _make_conn(tmp_path)
    _, _, episodio = _insert_arbol(conn, tmdb_serie=None)
    from emuwarez_uploadrr.services import source_assistant as sa
    with patch.object(sa, "get_tmdb_available_providers", return_value=["NF"]) as tmdb:
        result = sa.suggest_provider_for_item(episodio, conn=conn)
    assert result["suggested"] is None and result["reason"] == "Sin TMDb ID"
    tmdb.assert_not_called()


def test_suggest_provider_con_un_padre_que_ya_no_existe_no_sugiere(tmp_path):
    conn = _make_conn(tmp_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("INSERT INTO library_items (title, item_type, parent_id, local_status) VALUES ('Huérfano','episode',99999,'downloaded')")
    conn.commit()
    huerfano = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    from emuwarez_uploadrr.services import source_assistant as sa
    with patch.object(sa, "get_tmdb_available_providers", return_value=["NF"]) as tmdb:
        result = sa.suggest_provider_for_item(huerfano, conn=conn)
    assert result["reason"] == "Sin TMDb ID"
    tmdb.assert_not_called()


def test_suggest_provider_una_cadena_sin_ninguna_serie_no_sugiere(tmp_path):
    """Episodio -> temporada -> temporada -> temporada: tres niveles y ninguno es una serie con id."""
    conn = _make_conn(tmp_path)
    def fila(tipo, tmdb, padre):
        conn.execute("INSERT INTO library_items (title, item_type, tmdb_id, parent_id, local_status) VALUES ('x',?,?,?,'downloaded')",
                     (tipo, tmdb, padre))
        conn.commit()
        return conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    a = fila("season", "999", None)
    b = fila("season", "999", a)
    c = fila("season", "999", b)
    episodio = fila("episode", None, c)
    from emuwarez_uploadrr.services import source_assistant as sa
    with patch.object(sa, "get_tmdb_available_providers", return_value=["NF"]) as tmdb:
        result = sa.suggest_provider_for_item(episodio, conn=conn)
    assert result["reason"] == "Sin TMDb ID"
    tmdb.assert_not_called()


def test_suggest_provider_una_pelicula_sin_tmdb_no_busca_padre(tmp_path):
    conn = _make_conn(tmp_path)
    item_id = _insert_library_item(conn, title="Peli", tmdb_id=None)
    from emuwarez_uploadrr.services import source_assistant as sa
    assert sa.suggest_provider_for_item(item_id, conn=conn)["reason"] == "Sin TMDb ID"


# ---------------------------------------------------------------------------
# check_auto_upload_source — automated-upload source-disparity gate
# ---------------------------------------------------------------------------

def _mi_report(from_name, from_mediainfo):
    return {
        "available": True,
        "source_signals": {"from_name": from_name, "from_mediainfo_bitrate": from_mediainfo},
    }



# ---------------------------------------------------------------------------
# Cuándo parpadea el aviso de Source
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,radarr,tool,agree,por_que", [
    # Los tres conocidos y de acuerdo.
    ("BluRay", "BluRay", "BluRay", True,  "todos coinciden"),
    # Contradicción real entre dos conocidos: para eso existe el aviso.
    ("BluRay", "WEB-DL", "BluRay", False, "nombre y Radarr se contradicen"),
    ("BluRay", "BluRay", "WEB-DL", False, "la herramienta contradice a los otros dos"),
    # Un valor ausente NO es un desacuerdo: antes esto parpadeaba, y hacía que
    # cualquier archivo sin palabra de source en el nombre avisara siempre.
    (None,     "BluRay", "BluRay", True,  "el nombre no dice nada, pero nadie se contradice"),
    ("BluRay", None,     "BluRay", True,  "Radarr no dice nada"),
    # Herramienta apagada: llega como None y se cae de la comparación.
    ("BluRay", "BluRay", None,     True,  "apagada, y los dos que quedan coinciden"),
    ("BluRay", "WEB-DL", None,     False, "apagada, pero nombre y Radarr se contradicen"),
    # Sin nada que comparar.
    (None,     None,     None,     True,  "no se conoce ningún valor"),
    (None,     None,     "BluRay", True,  "solo se conoce uno"),
])
def test_source_agreement(name, radarr, tool, agree, por_que):
    """El aviso significa "estos valores dicen cosas distintas", no "solo
    conozco uno"."""
    from emuwarez_uploadrr.services.source_assistant import source_values_agree
    assert source_values_agree(name, radarr, tool) is agree, por_que


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_una_ruta_preparada_muerta_no_bloquea_la_nomenclatura(tmp_path):
    """El caso de The Tudors S03 (2026-08-04).

    La versión vieja renombraba la carpeta real de Sonarr al título del
    release. El usuario deshizo ese renombrado a mano, actualizó en Sonarr y
    sincronizó: `path` quedó apuntando al fichero de verdad y `prepared_path`
    a la carpeta renombrada, que ya no existe. Como `prepared_path` iba
    primero, subir contestaba "Archivo no accesible" con una ruta que la ficha
    del contenido enseñaba correcta.

    La regla de cuál se lee vive ahora en path_mapping.py::ruta_de_lectura
    (con su propio test), pero hace falta comprobarlo TAMBIÉN aquí: el fallo
    no estaba en la regla sino en que este sitio tenía su propia copia.
    """
    conn = _make_conn(tmp_path)
    item_id = _accessible_item(conn, tmp_path, title="The Tudors", tmdb_id="1399")
    muerta = tmp_path / "Los Tudor S03 2007 1080p BluRay x264-CCX94" / "cap.mkv"
    conn.execute("UPDATE library_items SET prepared_path = ? WHERE id = ?",
                 (str(muerta), item_id))
    conn.commit()
    assert not muerta.exists()

    with patch(
        "emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw",
        return_value=[],
    ), patch(
        "emuwarez_uploadrr.services.media_info_service.build_mediainfo_report",
        return_value=_MI_OK,
    ):
        from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
        result = build_editable_nomenclature_fields(item_id, conn=conn)

    assert not result.get("blocked"), result.get("error")
    assert "fields" in result


@pytest.mark.usefixtures("ficheros_de_mentira")
def test_con_la_ruta_preparada_viva_se_sigue_leyendo_de_ella(tmp_path):
    """La otra mitad: durante una subida, los enlaces de la carpeta de subidas
    son el fichero bueno y tienen que seguir mandando."""
    conn = _make_conn(tmp_path)
    item_id = _accessible_item(conn, tmp_path, title="Dune", tmdb_id="438631")
    viva = tmp_path / "uploads" / "Dune.2021.1080p.mkv"
    viva.parent.mkdir()
    viva.write_bytes(b"x" * 2048)
    conn.execute("UPDATE library_items SET prepared_path = ? WHERE id = ?",
                 (str(viva), item_id))
    conn.commit()

    leidos = []

    def espia(path, *a, **k):
        leidos.append(path)
        return _MI_OK

    with patch(
        "emuwarez_uploadrr.services.source_assistant._get_tmdb_available_providers_raw",
        return_value=[],
    ), patch(
        "emuwarez_uploadrr.services.media_info_service.build_mediainfo_report",
        side_effect=espia,
    ):
        from emuwarez_uploadrr.services.source_assistant import build_editable_nomenclature_fields
        result = build_editable_nomenclature_fields(item_id, conn=conn)

    assert not result.get("blocked"), result.get("error")
    assert leidos and str(viva) in leidos[0], leidos
