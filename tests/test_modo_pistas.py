"""Los cuatro modos de "Renombrar/Ordenar pistas".

Antes esto eran DOS decisiones repartidas en dos sitios: un sí/no en
Configuración que solo controlaba el orden, y una casilla en la tarjeta de Ver
Pistas para conservar los nombres actuales, que además solo aparecía subiendo
una película o un capítulo suelto, nunca una temporada entera. Ahora las dos
viven en el mismo desplegable.

Lo que se comprueba aquí es que cada modo hace exactamente sus dos mitades, y
sobre todo que la tabla que se le enseña al usuario dice lo mismo que se va a
aplicar: la columna "Nombre nuevo" repite el nombre actual cuando no se
renombra, en vez de enseñar un nombre propuesto que nadie va a escribir.
"""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.mkv_remux import (
    ETIQUETAS_MODO_PISTAS, MODOS_PISTAS, MODO_PISTAS_POR_DEFECTO,
    MODO_NINGUNO, MODO_REORDENAR_Y_RENOMBRAR, MODO_SOLO_RENOMBRAR, MODO_SOLO_REORDENAR,
    build_track_plan, modo_pistas, renombra, reordena, toca_el_fichero,
)

# Un archivo cuyo orden en disco NO es el que debería quedar: japonés primero,
# castellano el último. Así se distingue "ordenado" de "sin tocar".
_MKV = {"tracks": [
    {"id": 0, "type": "video", "codec": "AVC/H.264",
     "properties": {"pixel_dimensions": "1920x1080", "track_name": "x264 CRF18"}},
    {"id": 1, "type": "audio", "codec": "AAC",
     "properties": {"language": "jpn", "audio_channels": 2, "track_name": "Japanese"}},
    {"id": 2, "type": "audio", "codec": "AAC",
     "properties": {"language": "cat", "audio_channels": 2}},
    {"id": 3, "type": "audio", "codec": "AC-3",
     "properties": {"language": "spa", "audio_channels": 6, "track_name": "Castellano"}},
    {"id": 4, "type": "subtitles", "codec": "SubRip/SRT",
     "properties": {"language": "spa", "track_name": "Spanish"}},
]}


def _plan(modo):
    return build_track_plan(_MKV, reorder=reordena(modo), rename=renombra(modo))


def _nombres(plan):
    return {t["id"]: t["new_name"] for t in plan["ordered_tracks"]}


def _orden(plan):
    return [t["id"] for t in plan["ordered_tracks"]]


class TestLasDosMitades:
    def test_cada_modo_dice_lo_que_hace(self):
        assert (reordena(MODO_REORDENAR_Y_RENOMBRAR), renombra(MODO_REORDENAR_Y_RENOMBRAR)) == (True, True)
        assert (reordena(MODO_SOLO_RENOMBRAR), renombra(MODO_SOLO_RENOMBRAR)) == (False, True)
        assert (reordena(MODO_SOLO_REORDENAR), renombra(MODO_SOLO_REORDENAR)) == (True, False)
        assert (reordena(MODO_NINGUNO), renombra(MODO_NINGUNO)) == (False, False)

    def test_los_cuatro_modos_son_las_cuatro_combinaciones(self):
        """Ni sobra ni falta ninguno: si mañana se añade un quinto valor sin
        una combinación propia, este test lo dice."""
        assert {(reordena(m), renombra(m)) for m in MODOS_PISTAS} == {
            (True, True), (False, True), (True, False), (False, False)}

    def test_solo_ninguno_deja_el_fichero_sin_tocar(self):
        assert [m for m in MODOS_PISTAS if not toca_el_fichero(m)] == [MODO_NINGUNO]

    def test_todos_tienen_etiqueta(self):
        assert set(ETIQUETAS_MODO_PISTAS) == set(MODOS_PISTAS)


class TestLoQueEnsenaLaTabla:
    """La columna "Nombre nuevo" es lo que se le promete al usuario."""

    def test_reordenar_y_renombrar(self):
        plan = _plan(MODO_REORDENAR_Y_RENOMBRAR)
        # Vídeo, luego audio por prioridad (Español, Català, Japonés), luego subs.
        assert _orden(plan) == [0, 3, 2, 1, 4]
        assert _nombres(plan) == {
            0: "1080p AVC",
            3: "Español (Castellano) - DD 5.1",
            2: "Català - AAC 2.0",
            1: "Japonés - AAC 2.0",
            4: "Español (Castellano)",
        }

    def test_solo_renombrar(self):
        plan = _plan(MODO_SOLO_RENOMBRAR)
        assert _orden(plan) == [0, 1, 2, 3, 4], "el orden del archivo no se toca"
        assert _nombres(plan)[3] == "Español (Castellano) - DD 5.1"
        assert _nombres(plan)[2] == "Català - AAC 2.0", "la que no tenía nombre lo recibe"

    def test_solo_reordenar(self):
        plan = _plan(MODO_SOLO_REORDENAR)
        assert _orden(plan) == [0, 3, 2, 1, 4], "ordenadas"
        assert _nombres(plan) == {
            0: "x264 CRF18", 3: "Castellano", 2: None, 1: "Japanese", 4: "Spanish",
        }, "cada una con el nombre que ya tenía; la de Català sigue sin ninguno"

    def test_ninguno(self):
        plan = _plan(MODO_NINGUNO)
        assert _orden(plan) == [0, 1, 2, 3, 4]
        assert _nombres(plan) == {
            0: "x264 CRF18", 1: "Japanese", 2: None, 3: "Castellano", 4: "Spanish",
        }

    def test_sin_renombrar_el_nombre_nuevo_es_exactamente_el_actual(self):
        """La regla, sin depender de este archivo concreto: es lo que hace que
        la tabla se pueda leer igual en los cuatro modos."""
        for modo in (MODO_SOLO_REORDENAR, MODO_NINGUNO):
            for t in _plan(modo)["ordered_tracks"]:
                assert t["new_name"] == t["current_name"], modo


class TestLaPistaPredeterminada:
    """Marcarla no es ni renombrar ni reordenar: se hace en los tres modos que
    tocan el fichero. Es lo que decide qué audio suena al abrirlo."""

    @pytest.mark.parametrize("modo", [
        MODO_REORDENAR_Y_RENOMBRAR, MODO_SOLO_RENOMBRAR, MODO_SOLO_REORDENAR,
    ])
    def test_el_castellano_queda_marcado(self, modo):
        por_id = {t["id"]: t for t in _plan(modo)["ordered_tracks"]}
        assert por_id[3]["default_after"] is True, "el audio en castellano"
        assert por_id[1]["default_after"] is False, "el japonés no"

    def test_sin_reordenar_se_marca_igual_aunque_no_se_mueva(self):
        """El castellano sigue siendo la tercera pista de audio del archivo y
        aun así queda marcado: la regla es de idioma, no de posición."""
        plan = _plan(MODO_SOLO_RENOMBRAR)
        assert _orden(plan).index(3) == 3
        assert {t["id"]: t["default_after"] for t in plan["ordered_tracks"]}[3] is True


class TestElAjusteGuardado:
    @pytest.fixture
    def conn(self, isolated_db):
        from emuwarez_uploadrr.database import connect, init_db
        conn = connect(isolated_db / "emuwarez_uploadrr.db")
        init_db(conn)
        return conn

    def _poner(self, conn, clave, valor):
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (clave, valor))
        conn.commit()

    def test_sin_nada_guardado_solo_renombrar(self, conn):
        """Reordenar rompe hardlinks y cuesta tiempo: de fábrica no se hace."""
        assert modo_pistas(conn) == MODO_SOLO_RENOMBRAR == MODO_PISTAS_POR_DEFECTO

    @pytest.mark.parametrize("modo", MODOS_PISTAS)
    def test_se_lee_lo_guardado(self, conn, modo):
        self._poner(conn, "remux.track_mode", modo)
        assert modo_pistas(conn) == modo

    def test_un_valor_desconocido_no_rompe(self, conn):
        self._poner(conn, "remux.track_mode", "pepe")
        assert modo_pistas(conn) == MODO_PISTAS_POR_DEFECTO

    # La migración. Sin esto, quien tuviera reordenar activado se lo encontraba
    # apagado después de actualizar, sin haber tocado nada.
    def test_quien_tenia_reordenar_activado_lo_conserva(self, conn):
        self._poner(conn, "remux.reorder_tracks", "true")
        assert modo_pistas(conn) == MODO_REORDENAR_Y_RENOMBRAR

    def test_quien_lo_tenia_apagado_pasa_a_solo_renombrar(self, conn):
        """Que es lo que hacía: renombrar y marcar, sin mover nada."""
        self._poner(conn, "remux.reorder_tracks", "false")
        assert modo_pistas(conn) == MODO_SOLO_RENOMBRAR

    def test_el_ajuste_nuevo_gana_al_viejo(self, conn):
        self._poner(conn, "remux.reorder_tracks", "true")
        self._poner(conn, "remux.track_mode", MODO_NINGUNO)
        assert modo_pistas(conn) == MODO_NINGUNO


class TestLasEdicionesAMano:
    """Lo que el usuario escribe en la tabla de Ver Pistas."""

    def test_sin_renombrar_se_descarta_el_nombre_escrito(self):
        """Un nombre escrito ANTES de cambiar el ajuste sigue guardado en el
        trabajo encolado, y sin esto se colaría por detrás."""
        from emuwarez_uploadrr.services.mkv_remux import _sin_nombres
        assert _sin_nombres({3: {"new_name": "Lo que sea"}}) == {}

    def test_pero_la_predeterminada_elegida_a_mano_se_respeta(self):
        from emuwarez_uploadrr.services.mkv_remux import _sin_nombres
        assert _sin_nombres({3: {"new_name": "X", "default_after": False}}) == {
            3: {"default_after": False}}

    def test_sin_ediciones_no_inventa_ninguna(self):
        from emuwarez_uploadrr.services.mkv_remux import _sin_nombres
        assert _sin_nombres(None) is None
        assert _sin_nombres({}) == {}


def test_en_ninguno_la_predeterminada_es_la_que_ya_trae():
    """La columna "Predet." no puede prometer un cambio que nadie va a hacer.

    Con "Ninguno" no se toca el archivo, así que la pista marcada tiene que ser
    la que ya está marcada dentro, no la que se elegiría. Se vio en el
    navegador con un MKV real: la tabla marcaba el castellano en un modo que no
    ejecuta nada.
    """
    mkv = {"tracks": [
        {"id": 0, "type": "audio", "codec": "AAC",
         "properties": {"language": "jpn", "audio_channels": 2, "default_track": True}},
        {"id": 1, "type": "audio", "codec": "AC-3",
         "properties": {"language": "spa", "audio_channels": 6}},
    ]}
    plan = build_track_plan(mkv, reorder=False, rename=False, mark_default=False)
    marcadas = {t["id"]: t["default_after"] for t in plan["ordered_tracks"]}
    assert marcadas == {0: True, 1: False}, "la que trae el archivo, el japonés"
    assert plan["any_changed"] is False, "nada que aplicar, y la tarjeta lo dice"
