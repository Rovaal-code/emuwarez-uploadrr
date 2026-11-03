"""Subida por pasos con nombre, y reintento que reanuda desde el paso que falló.

Cubre: el vocabulario de pasos (services/subida_pasos.py), que se apunte dónde se
paró una subida (upload_states.escribir_estado), que un reintento decida si reanuda
(upload_queue.queue_retry_for_job) y que el pipeline reutilice la preparación de la
subida anterior solo cuando sigue valiendo en disco.
"""
from __future__ import annotations

import json
import os
import pytest

from emuwarez_uploadrr.services import subida_pasos as sp
from emuwarez_uploadrr.services import upload_queue as uq
from emuwarez_uploadrr.services.upload_states import escribir_estado


@pytest.fixture(autouse=True)
def _biblioteca_en_tmp(tmp_path, monkeypatch):
    from emuwarez_uploadrr.services import uploadrr_contract
    monkeypatch.setattr(uploadrr_contract, "DEFAULT_ALLOWED_ROOTS", [str(tmp_path)])


@pytest.fixture
def db_conn(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    return conn


def _estados(status, stage=None, parada=None):
    return {p["clave"]: p["estado"] for p in sp.pasos_de_subida(status, stage, parada)}


# ---------------------------------------------------------------------------
# El vocabulario de pasos
# ---------------------------------------------------------------------------

def test_los_pasos_tienen_nombre_y_orden():
    assert sp.CLAVES == ("nomenclatura", "preparacion", "verificacion", "subida")
    assert all(sp.NOMBRES[c] for c in sp.CLAVES)


def test_cada_fase_del_pipeline_cae_en_un_paso():
    from emuwarez_uploadrr.services.upload_states import ETAPAS_DE_PARADA
    assert [sp.indice_de_fase(f) is not None for f in ETAPAS_DE_PARADA] == [True] * len(ETAPAS_DE_PARADA)
    assert sp.indice_de_fase("queued") is None and sp.indice_de_fase(None) is None


def test_subida_completada_tiene_todos_los_pasos_hechos():
    assert set(_estados("completed", "finished").values()) == {sp.HECHO}


def test_subida_en_marcha_marca_el_paso_actual():
    assert _estados("preparing", "remux") == {
        "nomenclatura": sp.HECHO, "preparacion": sp.EN_CURSO, "verificacion": sp.PENDIENTE, "subida": sp.PENDIENTE}
    assert _estados("running", "running")["subida"] == sp.EN_CURSO
    assert set(_estados("queued", "queued").values()) == {sp.PENDIENTE}


def test_un_trabajo_listo_esta_en_la_verificacion():
    """_populate_ready lo deja con status = 'ready' y stage = 'preflight' antes de lanzar Uploadrr."""
    assert _estados("ready", "preflight") == {
        "nomenclatura": sp.HECHO, "preparacion": sp.HECHO, "verificacion": sp.EN_CURSO, "subida": sp.PENDIENTE}


@pytest.mark.parametrize("status", ["queued", "draft", "preflight", "blocked", "pending"])
def test_los_estados_sin_empezar_dejan_todos_los_pasos_pendientes(status):
    assert set(_estados(status, "queued").values()) == {sp.PENDIENTE}


def test_subida_fallida_marca_el_paso_donde_se_paro():
    assert _estados("failed", "failed", "verificacion_presubida") == {
        "nomenclatura": sp.HECHO, "preparacion": sp.HECHO, "verificacion": sp.FALLIDO, "subida": sp.PENDIENTE}


def test_subida_cancelada_marca_el_paso_como_cancelado():
    assert _estados("cancelled", "cancelled", "remux")["preparacion"] == sp.CANCELADO


def test_sin_saber_donde_se_paro_todo_queda_pendiente():
    assert set(_estados("failed", "failed", None).values()) == {sp.PENDIENTE}


@pytest.mark.parametrize("parada,esperado", [
    ("nomenclature", None), ("remux", None), (None, None),
    ("verificacion_presubida", "verificacion"), ("config_staging", "verificacion"), ("running", "verificacion"),
])
def test_reanudar_desde_solo_si_la_preparacion_estaba_hecha(parada, esperado):
    assert sp.reanudar_desde("failed", parada) == esperado
    assert sp.reanudar_desde("cancelled", parada) == esperado


def test_solo_se_reanuda_una_subida_parada():
    assert sp.reanudar_desde("running", "running") is None
    assert sp.reanudar_desde("completed", "running") is None


# ---------------------------------------------------------------------------
# Se apunta dónde se paró
# ---------------------------------------------------------------------------

def _trabajo(conn, item_id=None, status="running", stage="running", **extra):
    columnas = {"library_item_id": item_id, "status": status, "stage": stage, "title": "X", "path": "",
                "source_path": "", **extra}
    cur = conn.execute(
        f"INSERT INTO upload_jobs ({', '.join(columnas)}, created_at, updated_at) "
        f"VALUES ({', '.join('?' * len(columnas))}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        list(columnas.values()))
    conn.commit()
    return cur.lastrowid


def _parada(conn, job_id):
    return conn.execute("SELECT etapa_parada FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()[0]


def test_fallar_apunta_la_fase_en_que_estaba(db_conn):
    j = _trabajo(db_conn, stage="verificacion_presubida", status="preparing")
    assert escribir_estado(j, salvo=("cancelled",), status="failed", stage="failed", conn=db_conn)
    assert _parada(db_conn, j) == "verificacion_presubida"


def test_finalizando_cuenta_como_subir_y_se_apunta(db_conn):
    """upload_execution escribe stage = 'finalizing' con SQL suelto mientras Uploadrr termina de salir."""
    assert _estados("running", "finalizing")["subida"] == sp.EN_CURSO
    j = _trabajo(db_conn, stage="finalizing")
    escribir_estado(j, salvo=("cancelled",), status="failed", stage="failed", conn=db_conn)
    assert _parada(db_conn, j) == "finalizing"
    assert sp.reanudar_desde("failed", "finalizing") == "verificacion"


def test_fallar_al_arrancar_uploadrr_cuenta_como_la_verificacion(db_conn):
    """_populate_ready deja stage = 'preflight' y start_upload_job puede fallar justo después
    (por ejemplo, con un runtime no soportado): la preparación ya estaba hecha."""
    j = _trabajo(db_conn, stage="preflight", status="ready")
    escribir_estado(j, salvo=("cancelled",), status="failed", stage="failed", conn=db_conn)
    assert _parada(db_conn, j) == "preflight"
    assert _estados("failed", "failed", "preflight") == {
        "nomenclatura": sp.HECHO, "preparacion": sp.HECHO, "verificacion": sp.FALLIDO, "subida": sp.PENDIENTE}
    assert sp.reanudar_desde("failed", "preflight") == "verificacion"


def test_una_subida_interrumpida_al_arrancar_apunta_donde_estaba(db_conn):
    j = _trabajo(db_conn, stage="running", status="running")
    otra = _trabajo(db_conn, stage="remux", status="preparing")

    assert uq.reconcile_interrupted_jobs(conn=db_conn) == 2

    assert _parada(db_conn, j) == "running"
    assert _parada(db_conn, otra) == "remux"
    assert sp.reanudar_desde("failed", _parada(db_conn, j)) == "verificacion"
    assert sp.reanudar_desde("failed", _parada(db_conn, otra)) is None


def test_cancelar_tambien_apunta_donde_estaba(db_conn):
    j = _trabajo(db_conn, stage="remux", status="preparing")
    escribir_estado(j, salvo=(), status="cancelled", stage="cancelled", conn=db_conn)
    assert _parada(db_conn, j) == "remux"


def test_fallar_dos_veces_no_pisa_el_primer_paso(db_conn):
    j = _trabajo(db_conn, stage="running")
    escribir_estado(j, salvo=("cancelled",), status="failed", stage="failed", conn=db_conn)
    escribir_estado(j, salvo=("cancelled",), status="failed", stage="failed", conn=db_conn)
    assert _parada(db_conn, j) == "running"


def test_fallar_sin_haber_empezado_no_apunta_nada(db_conn):
    j = _trabajo(db_conn, stage="queued", status="queued")
    escribir_estado(j, salvo=("cancelled",), status="failed", stage="failed", conn=db_conn)
    assert _parada(db_conn, j) is None


def test_avanzar_de_fase_no_apunta_nada(db_conn):
    j = _trabajo(db_conn, stage="remux", status="preparing")
    escribir_estado(j, salvo=("cancelled", "failed"), status="preparing", stage="verificacion_presubida", conn=db_conn)
    assert _parada(db_conn, j) is None


# ---------------------------------------------------------------------------
# El reintento decide si reanuda
# ---------------------------------------------------------------------------

def _peli(conn, ruta):
    conn.execute(
        """INSERT INTO library_items (item_type, title, local_status, request_status, nomenclature_status, path,
                                      size_bytes, updated_at)
           VALUES ('movie', 'X', 'Disponible', 'Sin petición', 'N/A', ?, 100, CURRENT_TIMESTAMP)""", (ruta,))
    conn.commit()
    return conn.execute("SELECT id FROM library_items ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _reintento(conn, original, **kw):
    r = uq.queue_retry_for_job(original, conn=conn, **kw)
    assert r["status"] == "queued", r
    return conn.execute("SELECT * FROM upload_jobs WHERE id = ?", (r["job"]["id"],)).fetchone()


@pytest.mark.parametrize("parada,reutiliza", [("running", 1), ("config_staging", 1), ("verificacion_presubida", 1),
                                              ("remux", 0), ("nomenclature", 0), (None, 0)])
def test_el_reintento_reanuda_si_la_preparacion_estaba_hecha(db_conn, tmp_path, parada, reutiliza):
    iid = _peli(db_conn, str(tmp_path / "a.mkv"))
    original = _trabajo(db_conn, iid, status="failed", stage="failed", etapa_parada=parada)
    assert _reintento(db_conn, original)["reutiliza_preparacion"] == reutiliza


def test_el_reintento_desde_el_principio_no_reutiliza(db_conn, tmp_path):
    iid = _peli(db_conn, str(tmp_path / "a.mkv"))
    original = _trabajo(db_conn, iid, status="failed", stage="failed", etapa_parada="running")
    assert _reintento(db_conn, original, desde_el_principio=True)["reutiliza_preparacion"] == 0


def test_el_reintento_conserva_las_elecciones_del_pack(db_conn, tmp_path):
    """Sin ellas el pack saldría con otro nombre y no habría preparación que reutilizar."""
    iid = _peli(db_conn, str(tmp_path / "a.mkv"))
    eleccion = {"source": "WEB-DL", "idiomas": {"1": "spa"}}
    original = _trabajo(db_conn, iid, status="failed", stage="failed", season_overrides_json=json.dumps(eleccion))
    assert json.loads(_reintento(db_conn, original)["season_overrides_json"]) == eleccion


# ---------------------------------------------------------------------------
# Qué preparación se puede reutilizar
# ---------------------------------------------------------------------------

def _huellas(originales: dict) -> str:
    """Lo que la preparación apunta de cada original: nombre en la carpeta de subidas -> su huella."""
    return json.dumps({nombre: uq._huella_de(str(ruta)) for nombre, ruta in originales.items()})


def _anterior(conn, iid, destino, originales=None, **extra):
    datos = {"status": "failed", "stage": "failed", "etapa_parada": "running", "prepared_path": str(destino),
             "remux_snapshot_json": json.dumps({"omitida": "Ninguno"}), **extra}
    if originales is not None:
        datos["huellas_preparacion_json"] = _huellas(originales)
    return _trabajo(conn, iid, **datos)


def _con_anterior(conn, tmp_path, **extra):
    destino = tmp_path / "subidas" / "Peli.2024.mkv"
    destino.parent.mkdir()
    destino.write_bytes(b"x")
    origen = tmp_path / "origen.mkv"
    origen.write_bytes(b"original")
    iid = _peli(conn, str(origen))
    extra.setdefault("originales", {"Peli.2024.mkv": origen})
    ant = _anterior(conn, iid, destino, **extra)
    return destino, {"retry_of_job_id": ant}, [(iid, str(origen), "Peli.2024.mkv")]


def test_se_reutiliza_si_sigue_en_su_sitio(db_conn, tmp_path):
    destino, job, ficheros = _con_anterior(db_conn, tmp_path)
    anterior, motivo = uq._motivo_no_reutilizable(job, str(destino), ficheros, False, db_conn)
    assert motivo is None and anterior["id"] == job["retry_of_job_id"]


@pytest.mark.parametrize("cambio,texto", [
    ({"etapa_parada": "remux"}, "no llegó a terminar"),
    ({"remux_snapshot_json": None}, "qué pistas"),
])
def test_no_se_reutiliza_si_la_anterior_no_dejo_la_preparacion(db_conn, tmp_path, cambio, texto):
    destino, job, ficheros = _con_anterior(db_conn, tmp_path, **cambio)
    anterior, motivo = uq._motivo_no_reutilizable(job, str(destino), ficheros, False, db_conn)
    assert anterior is None and texto in motivo


def test_no_se_reutiliza_si_el_original_ha_cambiado_aunque_el_nombre_sea_el_mismo(db_conn, tmp_path):
    """Una mejora de Radarr/Sonarr puede dejar otro fichero con el mismo nombre de salida: lo preparado sería el viejo."""
    destino, job, ficheros = _con_anterior(db_conn, tmp_path)
    origen = tmp_path / "origen.mkv"
    origen.write_bytes(b"otro contenido, mas largo")          # cambia el tamaño
    anterior, motivo = uq._motivo_no_reutilizable(job, str(destino), ficheros, False, db_conn)
    assert anterior is None and "«Peli.2024.mkv» ha cambiado" in motivo


def test_no_se_reutiliza_si_el_original_se_sustituye_por_otro_del_mismo_tamano(db_conn, tmp_path):
    destino, job, ficheros = _con_anterior(db_conn, tmp_path)
    origen = tmp_path / "origen.mkv"
    origen.unlink()
    origen.write_bytes(b"ORIGINAL")                            # mismo tamaño, otro inodo y otra fecha
    _, motivo = uq._motivo_no_reutilizable(job, str(destino), ficheros, False, db_conn)
    assert "ha cambiado" in motivo


def test_no_se_reutiliza_si_no_quedo_apuntada_la_huella(db_conn, tmp_path):
    """Las subidas de antes de apuntarla (o a medio preparar) no tienen con qué compararse: se prepara de nuevo."""
    destino, job, ficheros = _con_anterior(db_conn, tmp_path, originales=None)
    anterior, motivo = uq._motivo_no_reutilizable(job, str(destino), ficheros, False, db_conn)
    assert anterior is None and "huella" in motivo


def test_no_se_reutiliza_si_el_original_ya_no_esta(db_conn, tmp_path):
    destino, job, ficheros = _con_anterior(db_conn, tmp_path)
    (tmp_path / "origen.mkv").unlink()
    _, motivo = uq._motivo_no_reutilizable(job, str(destino), ficheros, False, db_conn)
    assert "ha cambiado" in motivo


def test_no_se_reutiliza_si_cambio_el_sitio(db_conn, tmp_path):
    destino, job, ficheros = _con_anterior(db_conn, tmp_path)
    _, motivo = uq._motivo_no_reutilizable(job, str(tmp_path / "subidas" / "Otro.mkv"), ficheros, False, db_conn)
    assert "ha cambiado" in motivo


def test_no_se_reutiliza_si_el_fichero_ya_no_esta(db_conn, tmp_path):
    destino, job, ficheros = _con_anterior(db_conn, tmp_path)
    destino.unlink()
    _, motivo = uq._motivo_no_reutilizable(job, str(destino), ficheros, False, db_conn)
    assert "ya no está" in motivo


def test_no_se_reutiliza_si_la_anterior_ya_no_existe(db_conn, tmp_path):
    destino, _job, ficheros = _con_anterior(db_conn, tmp_path)
    _, motivo = uq._motivo_no_reutilizable({"retry_of_job_id": 99999}, str(destino), ficheros, False, db_conn)
    assert "ya no existe" in motivo


def test_un_pack_necesita_todos_sus_capitulos(db_conn, tmp_path):
    carpeta = tmp_path / "subidas" / "Serie.S01"
    carpeta.mkdir(parents=True)
    (carpeta / "E01.mkv").write_bytes(b"x")
    iid = _peli(db_conn, str(tmp_path / "a.mkv"))
    origenes = {n: tmp_path / f"origen_{n}" for n in ("E01.mkv", "E02.mkv")}
    for ruta in origenes.values():
        ruta.write_bytes(b"original")
    job = {"retry_of_job_id": _anterior(db_conn, iid, carpeta, originales=origenes)}
    ficheros = [(1, str(origenes["E01.mkv"]), "E01.mkv"), (2, str(origenes["E02.mkv"]), "E02.mkv")]
    _, motivo = uq._motivo_no_reutilizable(job, str(carpeta), ficheros, True, db_conn)
    assert "faltan ficheros" in motivo
    (carpeta / "E02.mkv").write_bytes(b"x")
    anterior, motivo = uq._motivo_no_reutilizable(job, str(carpeta), ficheros, True, db_conn)
    assert motivo is None and anterior


def test_en_un_pack_basta_con_que_cambie_un_capitulo(db_conn, tmp_path):
    carpeta = tmp_path / "subidas" / "Serie.S01"
    carpeta.mkdir(parents=True)
    iid = _peli(db_conn, str(tmp_path / "a.mkv"))
    origenes = {n: tmp_path / f"origen_{n}" for n in ("E01.mkv", "E02.mkv")}
    for n, ruta in origenes.items():
        ruta.write_bytes(b"original")
        (carpeta / n).write_bytes(b"x")
    job = {"retry_of_job_id": _anterior(db_conn, iid, carpeta, originales=origenes)}
    ficheros = [(1, str(origenes["E01.mkv"]), "E01.mkv"), (2, str(origenes["E02.mkv"]), "E02.mkv")]
    origenes["E02.mkv"].write_bytes(b"cambiado del todo")
    _, motivo = uq._motivo_no_reutilizable(job, str(carpeta), ficheros, True, db_conn)
    assert "«E02.mkv» ha cambiado" in motivo


# ---------------------------------------------------------------------------
# El pipeline: reutiliza o prepara de nuevo
# ---------------------------------------------------------------------------

@pytest.fixture
def pipeline(db_conn, tmp_path, monkeypatch, ficheros_de_mentira):
    """_run_queued_job de una película hasta el arranque de Uploadrr, que no se lanza.
    Devuelve las veces que se preparó un fichero de verdad."""
    from emuwarez_uploadrr.services import carpeta_subida, nomenclature, upload_execution

    subidas = tmp_path / "subidas"
    subidas.mkdir()
    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", str(subidas))
    monkeypatch.setattr(uq, "_check_generic_upload_preconditions", lambda *a, **k: True)
    monkeypatch.setattr(uq, "_populate_ready", lambda *a, **k: True)
    monkeypatch.setattr(uq, "_renombrar_si_esta_en_subidas", lambda _j, _i, origen, *a, **k: origen)

    def arrancar(*_a, **_k):
        # En producción el hilo de Uploadrr hereda la plaza de "Subidas en paralelo" y la suelta al acabar.
        upload_execution._upload_concurrency_gate.release()
        return {}

    monkeypatch.setattr(upload_execution, "start_upload_job", arrancar)
    origen = tmp_path / "Peli.mkv"
    origen.write_bytes(b"x" * 100)
    monkeypatch.setattr(nomenclature, "build_nomenclature_apply_plan", lambda *a, **k: {
        "status": "ready", "source_path": str(origen), "nombre": "Peli.2024.mkv", "proposal": None,
        "raw_destination_path": None})
    preparados = []

    def preparar(job_id, item_id, org, destino, modo, conn, **kw):
        preparados.append(destino)
        os.link(org, destino)
        return {"metodo": "enlace duro", "original_editado": False, "pistas": None, "omitida": "Ninguno"}

    monkeypatch.setattr(uq, "_preparar_fichero", preparar)
    return type("P", (), {"origen": origen, "destino": subidas / "Peli.2024.mkv", "preparados": preparados})


def _logs(conn, job_id):
    return [f["message"] for f in conn.execute(
        "SELECT message FROM upload_job_logs WHERE upload_job_id = ?", (job_id,))]


def _reanuda(conn, job_id):
    return conn.execute("SELECT reanuda_uploadrr FROM upload_jobs WHERE id = ?", (job_id,)).fetchone()[0]


def _retry_en_marcha(db_conn, pipeline, **kw):
    iid = _peli(db_conn, str(pipeline.origen))
    _anterior(db_conn, iid, pipeline.destino, **kw)
    anterior = db_conn.execute("SELECT MAX(id) FROM upload_jobs").fetchone()[0]
    return anterior, _reintento(db_conn, anterior)["id"]


def test_el_reintento_reutiliza_la_preparacion_que_sigue_valiendo(db_conn, pipeline):
    os.link(pipeline.origen, pipeline.destino)
    anterior, nuevo = _retry_en_marcha(db_conn, pipeline,
                                       remux_snapshot_json=json.dumps({"ordered_tracks": [{"id": 1}]}),
                                       originales={"Peli.2024.mkv": pipeline.origen})

    uq._run_queued_job(nuevo)

    assert pipeline.preparados == []
    fila = db_conn.execute("SELECT remux_snapshot_json, prepared_path, huellas_preparacion_json FROM upload_jobs "
                           "WHERE id = ?", (nuevo,)).fetchone()
    assert json.loads(fila["remux_snapshot_json"]) == {"ordered_tracks": [{"id": 1}]}
    # La huella pasa a la subida nueva: un segundo reintento seguirá pudiendo comprobarla.
    assert json.loads(fila["huellas_preparacion_json"]) == json.loads(_huellas({"Peli.2024.mkv": pipeline.origen}))
    assert fila["prepared_path"] == str(pipeline.destino)
    assert any(f"Se reutiliza la preparación de la subida #{anterior}" in m for m in _logs(db_conn, nuevo))
    # Con los ficheros de la anterior, Uploadrr-EMU también reanuda (`--resume`).
    assert _reanuda(db_conn, nuevo) == 1


@pytest.mark.parametrize("extra", [
    # Falló en la verificación, sin lanzar Uploadrr-EMU: su tmp es de una preparación más vieja.
    {"etapa_parada": "verificacion_presubida"},
    # La ficha ya estaba en eMuwarez.
    {"pasos_uploadrr_json": json.dumps(["screenshots", "torrent", "tracker"])},
])
def test_el_reintento_reutiliza_los_ficheros_pero_uploadrr_no_reanuda(db_conn, pipeline, extra):
    os.link(pipeline.origen, pipeline.destino)
    _anterior_id, nuevo = _retry_en_marcha(db_conn, pipeline, originales={"Peli.2024.mkv": pipeline.origen}, **extra)

    uq._run_queued_job(nuevo)

    assert pipeline.preparados == []                 # la preparación sí se reutiliza
    assert _reanuda(db_conn, nuevo) == 0             # pero Uploadrr-EMU empieza de cero
    assert db_conn.execute("SELECT pasos_uploadrr_json FROM upload_jobs WHERE id = ?", (nuevo,)).fetchone()[0] is None


def test_el_reintento_dice_que_uploadrr_no_repetira_lo_que_termino(db_conn, pipeline):
    os.link(pipeline.origen, pipeline.destino)
    anterior, nuevo = _retry_en_marcha(db_conn, pipeline, originales={"Peli.2024.mkv": pipeline.origen},
                                       pasos_uploadrr_json=json.dumps(["screenshots", "torrent"]))

    uq._run_queued_job(nuevo)

    assert any("Uploadrr no repetirá: capturas, torrent" in m for m in _logs(db_conn, nuevo))
    # Los pasos pasan al trabajo nuevo: si falla antes de terminar otro, el siguiente reintento sigue sabiéndolos.
    assert db_conn.execute("SELECT pasos_uploadrr_json FROM upload_jobs WHERE id = ?", (nuevo,)).fetchone()[0] == \
        json.dumps(["screenshots", "torrent"])


def test_el_reintento_prepara_de_nuevo_si_el_original_ha_cambiado(db_conn, pipeline):
    """Mismo nombre de salida, otro fichero: se comprobó el nuevo, así que no se puede subir lo preparado del viejo."""
    os.link(pipeline.origen, pipeline.destino)
    _anterior_id, nuevo = _retry_en_marcha(db_conn, pipeline, originales={"Peli.2024.mkv": pipeline.origen})
    viejo = pipeline.origen.read_bytes()
    pipeline.origen.unlink()
    pipeline.origen.write_bytes(viejo + b"mejorado")

    uq._run_queued_job(nuevo)

    assert pipeline.preparados == [str(pipeline.destino)]
    assert any("No se reutiliza la preparación anterior" in m and "ha cambiado" in m for m in _logs(db_conn, nuevo))
    # Ficheros rehechos: el torrent y las capturas de la anterior no valen, Uploadrr-EMU empieza de cero.
    assert _reanuda(db_conn, nuevo) == 0


def test_preparar_apunta_la_huella_del_original(db_conn, pipeline):
    iid = _peli(db_conn, str(pipeline.origen))
    nuevo = _trabajo(db_conn, iid, status="queued", stage="queued")

    uq._run_queued_job(nuevo)

    guardada = db_conn.execute("SELECT huellas_preparacion_json FROM upload_jobs WHERE id = ?", (nuevo,)).fetchone()[0]
    assert json.loads(guardada) == json.loads(_huellas({"Peli.2024.mkv": pipeline.origen}))


def test_el_reintento_prepara_de_nuevo_si_el_fichero_ya_no_esta(db_conn, pipeline):
    _anterior_id, nuevo = _retry_en_marcha(db_conn, pipeline, originales={"Peli.2024.mkv": pipeline.origen})

    uq._run_queued_job(nuevo)

    assert pipeline.preparados == [str(pipeline.destino)]
    assert any("No se reutiliza la preparación anterior" in m and "ya no está" in m for m in _logs(db_conn, nuevo))


def test_el_reintento_desde_el_principio_siempre_prepara(db_conn, pipeline):
    os.link(pipeline.origen, pipeline.destino)
    iid = _peli(db_conn, str(pipeline.origen))
    anterior = _anterior(db_conn, iid, pipeline.destino)
    nuevo = _reintento(db_conn, anterior, desde_el_principio=True)["id"]

    pipeline.destino.unlink()      # preparar_fichero_suelto rehace lo que dejó un intento anterior
    uq._run_queued_job(nuevo)

    assert pipeline.preparados == [str(pipeline.destino)]


# ---------------------------------------------------------------------------
# La migración (esquema 47)
# ---------------------------------------------------------------------------

def test_la_migracion_añade_las_columnas_y_se_puede_repetir(db_conn):
    from emuwarez_uploadrr.database import _migrate_upload_jobs_pasos
    columnas = lambda: {f[1] for f in db_conn.execute("PRAGMA table_info(upload_jobs)")}  # noqa: E731
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN etapa_parada")
    db_conn.execute("ALTER TABLE upload_jobs DROP COLUMN reutiliza_preparacion")
    assert not {"etapa_parada", "reutiliza_preparacion"} & columnas()

    _migrate_upload_jobs_pasos(db_conn)
    _migrate_upload_jobs_pasos(db_conn)

    assert {"etapa_parada", "reutiliza_preparacion"} <= columnas()
    j = _trabajo(db_conn)
    assert db_conn.execute("SELECT etapa_parada, reutiliza_preparacion FROM upload_jobs WHERE id = ?", (j,)).fetchone()[:] == (None, 0)
