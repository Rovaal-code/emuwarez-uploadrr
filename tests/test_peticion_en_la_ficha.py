"""La ficha de Biblioteca dice qué petición tiene el elemento: quién la pidió, la recompensa y el enlace.

GET /api/library/{id} trae `peticion` (la de library_items.request_id, o la que lo cubre desde su temporada o su
serie) y, en una serie o temporada, `peticiones_debajo`. La lista no los trae: serían consultas por fila.
"""
from __future__ import annotations

import pytest


def _fila(conn, item_type, title, *, parent_id=None, season=None, episode=None, request_id=None,
          request_status="Sin petición"):
    cur = conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, parent_id, season_number, episode_number,
                                      request_id, request_status, instance_id, instance_type, instance_name,
                                      external_id)
           VALUES (?,?,'Disponible',?,?,?,?,?,1,'sonarr','Sonarr',?)""",
        (item_type, title, parent_id, season, episode, request_id, request_status,
         f"{item_type}-{title}-{season}-{episode}"))
    return int(cur.lastrowid)


def _peticion(conn, emu_id, title, *, author="Gabriel", visible=True, points=1000, scope=None, season=None,
              episode=None, url=None):
    from emuwarez_uploadrr.models import RequestItem
    from emuwarez_uploadrr.services.requests import upsert_request
    return upsert_request(conn, RequestItem(
        id=None, emu_id=emu_id, title=title, points=points, created_at="2026-04-19T10:00:00Z",
        emu_status="Sin llenar", url=url or f"https://emu-warez.com/requests/{emu_id}",
        author=author, author_visible=visible, req_scope=scope, req_season=season, req_episode=episode))


@pytest.fixture
def base(client, auth_headers):
    from emuwarez_uploadrr.database import connect, db_path, init_db
    from emuwarez_uploadrr.services.settings import set_setting
    conn = connect(db_path())
    init_db(conn)
    set_setting(conn, "emu.username", "gabriel")
    conn.commit()
    yield conn, client, auth_headers
    conn.close()


def _ficha(client, cab, item_id):
    r = client.get(f"/api/library/{item_id}", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def test_una_pelicula_con_peticion_dice_quien_la_pidio_y_su_enlace(base):
    conn, client, cab = base
    rid = _peticion(conn, "501", "Dune", points=12500)
    peli = _fila(conn, "movie", "Dune", request_id=rid, request_status="Compatible")
    conn.commit()

    p = _ficha(client, cab, peli)["peticion"]
    assert p["id"] == rid
    assert p["title"] == "Dune"
    assert p["author"] == "Gabriel" and p["is_mine"] is True
    assert p["points"] == 12500
    assert p["url"] == "https://emu-warez.com/requests/501"
    assert p["emu_status"] == "Sin llenar"
    assert p["created_at"] == "2026-04-19T10:00:00Z"
    assert p["heredada_de"] is None
    assert p["estado"] == "Compatible" and p["library_item_id"] == peli


def test_sin_peticion_es_null(base):
    conn, client, cab = base
    peli = _fila(conn, "movie", "Nada")
    conn.commit()
    ficha = _ficha(client, cab, peli)
    assert ficha["peticion"] is None
    assert ficha["peticiones_debajo"] is None
    assert ficha["request_status"] == "Sin petición"


def test_el_autor_oculto_no_sale(base):
    conn, client, cab = base
    rid = _peticion(conn, "502", "Anónima", author="alguien", visible=False)
    peli = _fila(conn, "movie", "Anónima", request_id=rid, request_status="Compatible")
    conn.commit()
    p = _ficha(client, cab, peli)["peticion"]
    assert p["author"] is None and p["is_mine"] is False
    assert p["points"] == 1000


def test_una_peticion_que_ya_no_existe_es_null(base):
    conn, client, cab = base
    peli = _fila(conn, "movie", "Colgada", request_id=987654, request_status="Compatible")
    conn.commit()
    assert _ficha(client, cab, peli)["peticion"] is None


@pytest.mark.parametrize("guardada, esperada", [
    # Una URL de la API con la clave en la consulta: se queda la ruta, nunca la clave.
    ("https://emu-warez.com/api/requests/9?api_token=SECRETO", "https://emu-warez.com/api/requests/9"),
    ("https://user:pass@emu-warez.com/requests/9#c", "https://emu-warez.com/requests/9"),
    ("javascript:alert(1)", None),
])
def test_la_url_nunca_lleva_una_clave(base, guardada, esperada):
    conn, client, cab = base
    rid = _peticion(conn, "503", "Con clave", url=guardada)
    peli = _fila(conn, "movie", "Con clave", request_id=rid, request_status="Compatible")
    conn.commit()
    r = client.get(f"/api/library/{peli}", headers=cab)
    assert "SECRETO" not in r.text and "pass@" not in r.text
    assert r.json()["peticion"]["url"] == esperada


def test_una_temporada_hereda_la_peticion_de_la_serie_entera(base):
    """Re:Zero: la petición de toda la serie se guarda solo en la fila de la serie; la temporada 1 y su capítulo
    la enseñan como heredada, sin cambiar su estado guardado."""
    conn, client, cab = base
    rid = _peticion(conn, "600", "Re:Zero")
    serie = _fila(conn, "series", "Re:Zero", request_id=rid, request_status="Compatible")
    t1 = _fila(conn, "season", "Temporada 1", parent_id=serie, season=1)
    e1 = _fila(conn, "episode", "Re:Zero S01E01", parent_id=t1, season=1, episode=1)
    conn.commit()

    for item_id in (t1, e1):
        ficha = _ficha(client, cab, item_id)
        assert ficha["request_status"] == "Sin petición"
        p = ficha["peticion"]
        assert p["id"] == rid
        assert p["heredada_de"] == "serie"
        assert p["estado"] == "Compatible" and p["library_item_id"] == serie
        assert p["author"] == "Gabriel"


def test_un_capitulo_hereda_la_de_su_temporada(base):
    conn, client, cab = base
    serie = _fila(conn, "series", "The Bear")
    rid = _peticion(conn, "601", "The Bear", scope="season", season=2)
    t2 = _fila(conn, "season", "Temporada 2", parent_id=serie, season=2, request_id=rid, request_status="Parcial")
    e3 = _fila(conn, "episode", "The Bear S02E03", parent_id=t2, season=2, episode=3)
    conn.commit()
    p = _ficha(client, cab, e3)["peticion"]
    assert p["id"] == rid and p["heredada_de"] == "temporada"
    assert p["estado"] == "Parcial" and p["library_item_id"] == t2
    assert (p["req_scope"], p["req_season"]) == ("season", 2)


def test_la_peticion_propia_gana_a_la_heredada(base):
    conn, client, cab = base
    de_la_serie = _peticion(conn, "602", "Arcane")
    serie = _fila(conn, "series", "Arcane", request_id=de_la_serie, request_status="Compatible")
    propia = _peticion(conn, "603", "Arcane", scope="season", season=1, author="otro")
    t1 = _fila(conn, "season", "Temporada 1", parent_id=serie, season=1, request_id=propia,
               request_status="No compatible")
    conn.commit()
    p = _ficha(client, cab, t1)["peticion"]
    assert p["id"] == propia and p["heredada_de"] is None
    assert p["author"] == "otro" and p["is_mine"] is False


def test_una_peticion_de_otra_temporada_no_se_hereda(base):
    """Si la serie guarda una petición de la temporada 2 (no había fila de esa temporada), la 1 no la hereda."""
    conn, client, cab = base
    rid = _peticion(conn, "604", "Fargo", scope="season", season=2)
    serie = _fila(conn, "series", "Fargo", request_id=rid, request_status="Compatible")
    t1 = _fila(conn, "season", "Temporada 1", parent_id=serie, season=1)
    conn.commit()
    assert _ficha(client, cab, t1)["peticion"] is None


def test_sin_peticion_en_el_camino_sigue_sin_peticion(base):
    conn, client, cab = base
    serie = _fila(conn, "series", "Sola")
    t1 = _fila(conn, "season", "Temporada 1", parent_id=serie, season=1)
    e1 = _fila(conn, "episode", "Sola S01E01", parent_id=t1, season=1, episode=1)
    conn.commit()
    for item_id in (serie, t1, e1):
        ficha = _ficha(client, cab, item_id)
        assert ficha["peticion"] is None and ficha["request_status"] == "Sin petición"


def test_una_serie_lista_las_peticiones_de_sus_temporadas(base):
    """Una serie con una petición por temporada: cada una se guarda en su temporada, y la ficha de la serie las
    enseña todas debajo, por orden, también las de capítulo."""
    conn, client, cab = base
    serie = _fila(conn, "series", "Los Tudor")
    t2_req = _peticion(conn, "610", "Los Tudor", scope="season", season=2, points=300)
    t1_req = _peticion(conn, "611", "Los Tudor", scope="season", season=1, author="x", visible=False)
    e_req = _peticion(conn, "612", "Los Tudor", scope="episode", season=1, episode=4)
    t1 = _fila(conn, "season", "Temporada 1", parent_id=serie, season=1, request_id=t1_req,
               request_status="Compatible")
    _fila(conn, "season", "Temporada 2", parent_id=serie, season=2, request_id=t2_req, request_status="Parcial")
    e4 = _fila(conn, "episode", "Los Tudor S01E04", parent_id=t1, season=1, episode=4, request_id=e_req,
               request_status="Compatible")
    conn.commit()

    ficha = _ficha(client, cab, serie)
    assert ficha["peticion"] is None
    debajo = ficha["peticiones_debajo"]
    assert [p["id"] for p in debajo] == [t1_req, e_req, t2_req]
    assert [p["estado"] for p in debajo] == ["Compatible", "Compatible", "Parcial"]
    assert debajo[0]["author"] is None          # anónima
    assert debajo[1]["library_item_id"] == e4

    # La temporada 1 tiene la suya y, debajo, la de su capítulo 4.
    t1_ficha = _ficha(client, cab, t1)
    assert t1_ficha["peticion"]["id"] == t1_req
    assert [p["id"] for p in t1_ficha["peticiones_debajo"]] == [e_req]


def test_la_lista_no_trae_la_peticion(base):
    conn, client, cab = base
    rid = _peticion(conn, "620", "Lista")
    _fila(conn, "movie", "Lista", request_id=rid, request_status="Compatible")
    conn.commit()
    r = client.get("/api/library?limit=50", headers=cab)
    assert r.status_code == 200
    fila = next(i for i in r.json()["items"] if i["title"] == "Lista")
    assert fila["peticion"] is None and fila["peticiones_debajo"] is None


def test_el_cruce_guarda_la_de_temporada_en_la_temporada_y_la_serie_la_ve_debajo(base):
    """Por el camino real: _guardar_casamientos escribe la petición de temporada en la fila de la temporada
    (_scoped_library_id), no en la serie; la ficha de la serie la encuentra debajo."""
    from emuwarez_uploadrr.services.requests import _guardar_casamientos, _scoped_library_id
    conn, client, cab = base
    serie = _fila(conn, "series", "Severance")
    t1 = _fila(conn, "season", "Temporada 1", parent_id=serie, season=1)
    rid = _peticion(conn, "630", "Severance", scope="season", season=1)
    conn.commit()
    req = dict(conn.execute("SELECT * FROM request_items WHERE id = ?", (rid,)).fetchone())
    item = dict(conn.execute("SELECT * FROM library_items WHERE id = ?", (serie,)).fetchone())
    destino = _scoped_library_id(conn, item, req)
    assert destino == t1
    cls = {"status": "Compatible", "confidence": 0.9, "resolution_match": True, "source_match": True,
           "reasons": []}
    _guardar_casamientos(conn, [(req, {"item": item, "id_match": True}, cls, destino)])

    serie_ficha = _ficha(client, cab, serie)
    assert serie_ficha["request_status"] == "Sin petición" and serie_ficha["peticion"] is None
    assert [p["id"] for p in serie_ficha["peticiones_debajo"]] == [rid]
    assert _ficha(client, cab, t1)["peticion"]["id"] == rid


# ---------------------------------------------------------------------------
# La lista: la celda «Petición» dice de quién la hereda (#230), sin tocar el estado ni el filtro
# ---------------------------------------------------------------------------

def _lista(client, cab, **params):
    r = client.get("/api/library", params={"limit": 50, **params}, headers=cab)
    assert r.status_code == 200, r.text
    return {i["id"]: i for i in r.json()["items"]}


def test_la_lista_dice_de_quien_hereda_la_peticion_una_temporada_o_un_capitulo(base):
    conn, client, cab = base
    rid = _peticion(conn, "640", "Re:Zero")
    serie = _fila(conn, "series", "Re:Zero", request_id=rid, request_status="Compatible")
    t1 = _fila(conn, "season", "Temporada 1", parent_id=serie, season=1)
    e1 = _fila(conn, "episode", "Re:Zero S01E01", parent_id=t1, season=1, episode=1)
    otra = _fila(conn, "series", "Bear")
    t2_req = _peticion(conn, "641", "Bear", scope="season", season=2)
    t2 = _fila(conn, "season", "Temporada 2", parent_id=otra, season=2, request_id=t2_req, request_status="Parcial")
    e3 = _fila(conn, "episode", "Bear S02E03", parent_id=t2, season=2, episode=3)
    t3 = _fila(conn, "season", "Temporada 3", parent_id=otra, season=3)
    conn.commit()

    temporadas = _lista(client, cab, parent_id=serie)
    assert temporadas[t1]["peticion_heredada"] == "serie"
    assert temporadas[t1]["request_status"] == "Sin petición"  # el estado guardado no cambia
    assert _lista(client, cab, parent_id=t1)[e1]["peticion_heredada"] == "serie"
    assert _lista(client, cab, parent_id=t2)[e3]["peticion_heredada"] == "temporada"
    de_bear = _lista(client, cab, parent_id=otra)
    assert de_bear[t2]["peticion_heredada"] is None  # tiene la suya
    assert de_bear[t3]["peticion_heredada"] is None  # nadie la pide
    assert _lista(client, cab)[serie]["peticion_heredada"] is None  # una serie no hereda

    # El filtro sigue siendo el estado guardado: la temporada heredada sale con «Sin petición».
    assert t1 not in _lista(client, cab, parent_id=serie, request_status="Compatible")
    assert t1 in _lista(client, cab, parent_id=serie, request_status="Sin petición")


def test_la_peticion_heredada_de_una_pagina_es_una_sola_consulta(base):
    from emuwarez_uploadrr.services.requests import peticiones_heredadas
    conn, _, _ = base
    rid = _peticion(conn, "650", "Larga")
    serie = _fila(conn, "series", "Larga", request_id=rid, request_status="Compatible")
    ids = []
    for s in range(1, 4):
        t = _fila(conn, "season", f"Temporada {s}", parent_id=serie, season=s)
        ids.append(t)
        ids.extend(_fila(conn, "episode", f"Larga S0{s}E0{e}", parent_id=t, season=s, episode=e)
                   for e in range(1, 6))
    conn.commit()

    consultas: list[str] = []
    conn.set_trace_callback(consultas.append)
    try:
        heredadas = peticiones_heredadas(conn, ids)
    finally:
        conn.set_trace_callback(None)
    assert heredadas == {i: "serie" for i in ids}
    assert len([c for c in consultas if c.lstrip().upper().startswith("SELECT")]) == 1
