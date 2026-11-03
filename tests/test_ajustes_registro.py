"""El registro de ajustes (services/ajustes_registro.py) frente al API.

Cada campo de GET/PUT /api/settings sale del registro o está apartado a
propósito en web/api/settings.FUERA_DEL_REGISTRO: un campo nuevo que no esté en
ninguno de los dos hace fallar el primer test. Los demás fijan lo que el
registro sustituyó sin cambiarlo: valores por defecto, conversión desde el
texto guardado, mensajes de error y qué claves son secretos.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services import ajustes_registro as reg
from emuwarez_uploadrr.services.ajustes_registro import AJUSTES, BOOL, CHOICE, INT, SECRET, STR, TIPOS


def _campos_del_api() -> tuple[set[str], set[str]]:
    from emuwarez_uploadrr.web.api.settings import SettingsResponse, SettingsUpdateRequest
    return set(SettingsResponse.model_fields), set(SettingsUpdateRequest.model_fields)


def _del_registro_en_respuesta() -> set[str]:
    campos = set()
    for a in AJUSTES.values():
        if a.tipo == SECRET:
            campos.add(f"{a.campo_estado}_configured")
            if a.enmascara:
                campos.add(f"{a.campo_estado}_masked")
        else:
            campos.add(a.campo)
    return campos


def test_cada_campo_del_api_sale_del_registro_o_esta_apartado():
    from emuwarez_uploadrr.web.api.settings import FUERA_DEL_REGISTRO
    respuesta, peticion = _campos_del_api()
    del_registro = _del_registro_en_respuesta()

    assert del_registro <= respuesta, f"faltan en SettingsResponse: {sorted(del_registro - respuesta)}"
    assert set(AJUSTES) <= peticion, f"faltan en SettingsUpdateRequest: {sorted(set(AJUSTES) - peticion)}"

    sueltos = (respuesta - del_registro) | (peticion - set(AJUSTES))
    assert sueltos == FUERA_DEL_REGISTRO, (
        f"\nsin registrar ni apartar: {sorted(sueltos - FUERA_DEL_REGISTRO)}"
        f"\napartados que ya no existen: {sorted(FUERA_DEL_REGISTRO - sueltos)}"
    )
    assert not (FUERA_DEL_REGISTRO & del_registro)


@pytest.mark.parametrize("ajuste", list(AJUSTES.values()), ids=list(AJUSTES))
def test_cada_ajuste_tiene_tipo_y_defecto_coherentes(ajuste):
    assert ajuste.tipo in TIPOS
    if ajuste.tipo == BOOL:
        assert isinstance(ajuste.defecto, bool)
    elif ajuste.tipo == INT:
        assert isinstance(ajuste.defecto, int)
    elif ajuste.tipo == CHOICE:
        assert ajuste.opciones and all(isinstance(o, str) for o in ajuste.opciones)
    else:
        assert ajuste.defecto is None or isinstance(ajuste.defecto, str)
    if ajuste.opciones:
        assert ajuste.defecto in ajuste.opciones
    if ajuste.minimo is not None:
        assert ajuste.tipo == INT and ajuste.defecto >= ajuste.minimo
    if ajuste.tipo == SECRET:
        assert ajuste.campo_estado
    else:
        assert not (ajuste.campo_estado or ajuste.borrable)


def test_los_secretos_son_los_de_siempre():
    """Lo que es_secreto contestaba antes del registro, clave por clave."""
    from emuwarez_uploadrr.services.settings import es_secreto
    antes = {
        "tmdb.api_key", "emu.api_key", "emu.endpoint_url",
        "notify.discord.webhook_url", "notify.telegram.bot_token",
        "tmdb_api_key", "emu_api_key", "qbit.password", "qbit.qui_proxy_url",
    }
    for clave in antes | {"imghost.key.imgbb"}:
        assert es_secreto(clave), clave
    for a in AJUSTES.values():
        assert es_secreto(a.clave) == (a.clave in antes), a.clave


def test_los_alias_antiguos_son_de_ajustes_conocidos():
    from emuwarez_uploadrr.database import CANONICAL_SETTING_ALIASES
    from emuwarez_uploadrr.services.ajustes_registro import POR_CLAVE
    # La única que no es un tipo sencillo: una lista guardada como JSON.
    assert set(CANONICAL_SETTING_ALIASES) - set(POR_CLAVE) == {"uploadrr.allowed_roots"}


def test_la_concurrencia_de_subidas_es_la_del_registro():
    from emuwarez_uploadrr.services.upload_execution import concurrencia as ue
    a = AJUSTES["upload_max_concurrent"]
    assert (ue.UPLOAD_MAX_CONCURRENT_SETTING_KEY, ue.UPLOAD_MAX_CONCURRENT_CHOICES,
            ue.UPLOAD_MAX_CONCURRENT_DEFAULT) == (a.clave, a.opciones, a.defecto)


@pytest.mark.parametrize("campo,crudo,esperado", [
    # Encendido de fábrica: solo "false" lo apaga.
    ("emu_add_logo", None, True), ("emu_add_logo", "false", False), ("emu_add_logo", "no", True),
    # Apagado de fábrica: solo "true" lo enciende.
    ("source_engine_enabled", None, False), ("source_engine_enabled", "true", True),
    ("source_engine_enabled", "1", False), ("source_engine_enabled", "TRUE", False),
    # Número de una lista: lo que no está en ella es el de fábrica.
    ("recent_activity_limit", "50", 50), ("recent_activity_limit", "7", 100), ("recent_activity_limit", "x", 100),
    # Número sin lista: el mínimo solo cuenta en el PUT, como lo lee uploadrr_contract.
    ("uploadrr_timeout", "-5", -5), ("uploadrr_timeout", "nope", 7200), ("uploadrr_timeout", None, 7200),
    # El runtime se lee tal cual, como lo usa la subida.
    ("uploadrr_runtime_type", "raro", "raro"), ("uploadrr_runtime_type", None, "uploadrr_emu"),
    ("tmdb_watch_region", None, "ES"), ("emu_username", None, None),
])
def test_conversion_desde_el_texto_guardado(campo, crudo, esperado):
    assert reg.desde_texto(AJUSTES[campo], crudo) == esperado


@pytest.mark.parametrize("campo,valor,mensaje", [
    ("recent_activity_limit", 7, "recent_activity_limit debe ser uno de (0, 50, 100, 150, 200, 250, 300)"),
    ("upload_max_concurrent", 11, "upload_max_concurrent debe ser uno de (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)"),
    ("remux_track_mode", "pepe",
     "remux_track_mode debe ser uno de ['reordenar_y_renombrar', 'solo_renombrar', 'solo_reordenar', 'ninguno']"),
    ("uploadrr_runtime_type", "x", "uploadrr_runtime_type inválido: 'x'. Debe ser uno de: uploadrr_emu, uploadrr_generic"),
    ("uploadrr_timeout", 0, "uploadrr_timeout debe ser un entero positivo"),
])
def test_los_mensajes_de_error_son_los_de_antes(campo, valor, mensaje):
    assert reg.error_de(AJUSTES[campo], valor) == mensaje
    assert reg.error_de(AJUSTES[campo], AJUSTES[campo].defecto) is None


def test_el_get_de_fabrica_da_los_valores_por_defecto(client, auth_headers):
    datos = client.get("/api/settings", headers=auth_headers).json()
    # init_db siembra la ruta de Python de la imagen; no es un valor por
    # defecto del registro: si alguien la vacía, el GET da None, como antes.
    assert datos.pop("uploadrr_python_path") == "/usr/local/bin/python"
    assert AJUSTES["uploadrr_python_path"].defecto is None
    for campo, a in AJUSTES.items():
        if a.tipo == SECRET:
            assert datos[f"{a.campo_estado}_configured"] is False, campo
            if a.enmascara:
                assert datos[f"{a.campo_estado}_masked"] is None, campo
            else:
                assert f"{a.campo_estado}_masked" not in datos
        elif campo != "uploadrr_python_path":
            assert datos[campo] == a.defecto, campo


def _otro_valor(a):
    if a.tipo == BOOL:
        return not a.defecto
    if a.opciones:
        return next(o for o in a.opciones if o != a.defecto)
    if a.tipo == INT:
        return a.defecto + 1
    return "otro"


@pytest.mark.parametrize("campo", [c for c, a in AJUSTES.items() if a.tipo != SECRET])
def test_cada_ajuste_sencillo_se_guarda_en_su_clave_y_se_lee(client, auth_headers, campo):
    from emuwarez_uploadrr.database import connect, db_path
    from emuwarez_uploadrr.services.settings import get_setting_canonical

    a = AJUSTES[campo]
    valor = _otro_valor(a)
    if a.tipo == STR:
        enviado, valor = (f"  http://{valor}  ", f"http://{valor}") if campo == "qbit_url" else (f"  {valor}  ", valor)
    else:
        enviado = valor
    resp = client.put("/api/settings", json={campo: enviado}, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()[campo] == valor
    assert client.get("/api/settings", headers=auth_headers).json()[campo] == valor

    conn = connect(db_path())
    try:
        guardado = get_setting_canonical(conn, a.clave)
    finally:
        conn.close()
    assert guardado == reg.a_texto(a, valor)
    if a.tipo == BOOL:
        assert guardado == ("true" if valor else "false")


# --- Lecturas de sí/no fuera del API ----------------------------------------

_BOOLEANOS = [a for a in AJUSTES.values() if a.tipo == BOOL]


@pytest.fixture
def conn_ajustes(isolated_db):
    from emuwarez_uploadrr.database import connect, init_db
    conn = connect(isolated_db / "emuwarez_uploadrr.db")
    init_db(conn)
    yield conn
    conn.close()


@pytest.mark.parametrize("ajuste", _BOOLEANOS, ids=[a.campo for a in _BOOLEANOS])
def test_leer_ajuste_de_un_si_no_usa_el_defecto_del_registro(conn_ajustes, ajuste):
    """El defecto vive solo en el registro: `leer_ajuste` lo da sin fila, con la
    fila vacía o con un texto que no es "true"/"false"; y solo el contrario
    escrito tal cual lo cambia."""
    from emuwarez_uploadrr.services.settings import leer_ajuste, set_setting
    assert leer_ajuste(conn_ajustes, ajuste.campo) is ajuste.defecto
    for raro in ("", "False", "TRUE", "1", "no", " false"):
        set_setting(conn_ajustes, ajuste.clave, raro)
        assert leer_ajuste(conn_ajustes, ajuste.campo) is ajuste.defecto, raro
    set_setting(conn_ajustes, ajuste.clave, "true")
    assert leer_ajuste(conn_ajustes, ajuste.campo) is True
    set_setting(conn_ajustes, ajuste.clave, "false")
    assert leer_ajuste(conn_ajustes, ajuste.campo) is False


def test_series_ignore_specials_se_lee_con_el_registro(conn_ajustes):
    """El caso que había en seis sitios a mano: encendido de fábrica, y solo un
    "false" guardado lo apaga."""
    from emuwarez_uploadrr.services.settings import set_setting
    from emuwarez_uploadrr.web.api.library import _ignore_specials
    assert _ignore_specials(conn_ajustes) is True
    set_setting(conn_ajustes, "series.ignore_specials", "false")
    assert _ignore_specials(conn_ajustes) is False
    set_setting(conn_ajustes, "series.ignore_specials", "true")
    assert _ignore_specials(conn_ajustes) is True


def test_ningun_si_no_del_registro_se_lee_a_mano():
    """Un sí/no que está en el registro se lee con `leer_ajuste`, no con
    `(get_setting_canonical(...) or "true") != "false"` y parecidos: cada copia
    llevaba su propio defecto y podía desfasarse del registro."""
    import pathlib
    import re

    raiz = pathlib.Path(__file__).resolve().parents[1] / "emuwarez_uploadrr"
    lectura = re.compile(r"get_(?:setting\w*|secret_setting)\(\s*\w+\s*,\s*(f?)(['\"])([^'\"]+)\2")
    idioma = re.compile(r"(?:==|!=)\s*['\"](?:true|false)['\"]|\bor\s+['\"](?:true|false)['\"]")
    claves = {a.clave for a in _BOOLEANOS}
    exentos = {"services/settings.py", "database.py", "services/ajustes_registro.py"}

    def es_del_registro(texto: str, es_fstring: bool) -> bool:
        if not es_fstring:
            return texto in claves
        # f"notify.{canal}.enabled": el hueco puede ser cualquier tramo sin punto.
        molde = re.escape(re.sub(r"\{[^}]*\}", "\0", texto)).replace("\0", "[^.]+")
        return any(re.fullmatch(molde, c) for c in claves)

    sueltas = []
    for f in sorted(raiz.rglob("*.py")):
        rel = f.relative_to(raiz).as_posix()
        if rel in exentos:
            continue
        for n, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            m = lectura.search(linea)
            if m and idioma.search(linea[m.end():]) and es_del_registro(m.group(3), bool(m.group(1))):
                sueltas.append(f"{rel}:{n}: {linea.strip()}")
    assert not sueltas, (
        "\nLectura de sí/no a mano de un ajuste del registro; usa "
        "services.settings.leer_ajuste(conn, <campo>):\n  " + "\n  ".join(sueltas))
