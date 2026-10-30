"""El grupo de release que Radarr/Sonarr leen del nombre del archivo
(`releaseGroup`) llega a la columna Grupo de Biblioteca."""
from __future__ import annotations

from emuwarez_uploadrr.integrations import radarr, sonarr
from emuwarez_uploadrr.models import LibraryItem
from emuwarez_uploadrr.services.library import upsert_library_item


def test_radarr_guarda_el_grupo_del_archivo():
    movie = {
        "id": 1, "title": "Dune", "year": 2021, "tmdbId": 438631,
        "movieFile": {"id": 10, "path": "/movies/Dune.mkv", "size": 1,
                      "releaseGroup": "FLUX",
                      "quality": {"quality": {"name": "WEBDL-1080p"}}},
    }
    item = radarr.movie_to_library_item(movie, instance_id=1, instance_name="Radarr")
    assert item.release_group == "FLUX"


def test_sonarr_guarda_el_grupo_del_capitulo():
    series = {"id": 1, "title": "Inuyasha", "year": 2000, "tvdbId": 1}
    episode = {"id": 100, "seasonNumber": 6, "episodeNumber": 29}
    ep_file = {"id": 50, "path": "/shows/Inuyasha/S06E29.mkv", "size": 1,
               "releaseGroup": "Loco87",
               "quality": {"quality": {"name": "HDTV-1080p"}}}
    item = sonarr.episode_to_library_item(episode, ep_file, series, instance_id=2, instance_name="Sonarr")
    assert item.release_group == "Loco87"


def test_un_capitulo_sin_archivo_no_tiene_grupo():
    series = {"id": 1, "title": "Dark", "year": 2017, "tvdbId": 1}
    episode = {"id": 200, "seasonNumber": 2, "episodeNumber": 3}
    item = sonarr.episode_to_library_item(episode, None, series, instance_id=2, instance_name="Sonarr")
    assert item.release_group is None


def test_la_sincronizacion_lo_guarda_y_lo_actualiza(isolated_db):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path()); init_db(conn)
    item = LibraryItem(id=None, item_type="movie", title="Dune", instance_id=1,
                       instance_type="radarr", instance_name="Radarr", external_id="1",
                       release_group="FLUX")
    item_id = upsert_library_item(conn, item, notify_missing=False)
    item.release_group = "NTb"
    upsert_library_item(conn, item, notify_missing=False)
    row = conn.execute("SELECT release_group FROM library_items WHERE id = ?", (item_id,)).fetchone()
    assert row["release_group"] == "NTb"
    conn.close()


def _serie(conn, grupos: list[str]) -> None:
    serie = conn.execute(
        "INSERT INTO library_items (item_type, title, local_status, instance_id, instance_type, "
        "instance_name, external_id) VALUES ('series','Inuyasha','Disponible',1,'sonarr','Sonarr','7')"
    ).lastrowid
    temporada = conn.execute(
        "INSERT INTO library_items (item_type, title, local_status, parent_id, season_number, "
        "instance_id, instance_type, instance_name, external_id) "
        "VALUES ('season','T6','Disponible',?,6,1,'sonarr','Sonarr','7-6')", (serie,)
    ).lastrowid
    for n, grupo in enumerate(grupos, 1):
        conn.execute(
            "INSERT INTO library_items (item_type, title, local_status, parent_id, season_number, "
            "episode_number, path, release_group, instance_id, instance_type, instance_name, external_id) "
            "VALUES ('episode',?,'Disponible',?,6,?,?,?,1,'sonarr','Sonarr',?)",
            (f"Inuyasha S06E{n:02d}", temporada, n, f"/data/Inuyasha/S06E{n:02d}.mkv", grupo, f"7-6-{n}"),
        )
    conn.commit()


def _fila(client, auth_headers, item_type: str) -> dict:
    r = client.get("/api/library?limit=50", headers=auth_headers)
    assert r.status_code == 200, r.text
    return next(i for i in r.json()["items"] if i["item_type"] == item_type)


def test_una_serie_de_un_solo_grupo_lo_ensena(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path()); init_db(conn)
    _serie(conn, ["Loco87", "Loco87"])
    conn.close()
    assert _fila(client, auth_headers, "series")["release_group"] == "Loco87"
    assert _fila(client, auth_headers, "season")["release_group"] == "Loco87"


def test_una_serie_con_grupos_mezclados_no_ensena_ninguno(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path()); init_db(conn)
    _serie(conn, ["Loco87", "Okeda"])
    conn.close()
    assert _fila(client, auth_headers, "series")["release_group"] is None


def test_el_filtro_ofrece_los_grupos_que_hay(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    conn = connect(db_path()); init_db(conn)
    _serie(conn, ["Okeda", "Loco87", "Okeda"])
    conn.close()
    r = client.get("/api/library/filter-options", headers=auth_headers)
    assert r.json()["release_groups"] == ["Loco87", "Okeda"]
