"""Foto congelada del informe de MediaInfo.

`build_mediainfo_report` alimenta la nomenclatura, la ficha técnica, la
comparación de peticiones y el pack de temporada: un cambio sutil ahí sale por
cuatro sitios distintos. Este test no juzga si el informe es correcto, lo
FOTOGRAFÍA: se compara entero contra un fichero de referencia.

Sirve para migrar `media_info_service` fuera de `legacy.py` (hallazgo 1.1 de la
auditoría) sabiendo que el resultado no cambia ni en una coma. Si al mover algo
esta comparación falla, o el refactor está mal o había un fallo escondido — y
las dos cosas hay que verlas antes de seguir.

La entrada es la salida REAL de `mediainfo` sobre dos MKV con dos pistas de
audio cada uno (grabada en tests/fixtures/mediainfo_crudo.json), no un
diccionario inventado: así el informe recorre el camino de verdad.

Si el informe cambia A PROPÓSITO, se regenera la referencia con:
    python -m tests.test_media_info_congelado --regenerar
y se revisa el diff del JSON en el commit, que es justo lo que se quiere ver.
"""
from __future__ import annotations

import json
import pathlib
from unittest.mock import patch

import pytest

from emuwarez_uploadrr.services import media_info_service as svc

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
CRUDO = FIXTURES / "mediainfo_crudo.json"
REFERENCIA = FIXTURES / "mediainfo_informe_esperado.json"


def _casos() -> dict:
    return json.loads(CRUDO.read_text())


def _informe(nombre: str, datos: dict, tmp_path: pathlib.Path) -> dict:
    """El informe tal cual lo produce el servicio, con el fichero simulado al
    tamaño real del original: la estimación de fuente mira los bytes."""
    f = tmp_path / nombre
    f.write_bytes(b"\0" * datos["tamano_bytes"])
    with patch.object(svc, "mediainfo_available", return_value=True), \
         patch.object(svc.media_probe, "run_mediainfo_json", return_value=datos["mediainfo"]):
        informe = svc.build_mediainfo_report(str(f))
    # La ruta cambia en cada ejecución (tmp_path); el resto sí se compara.
    informe.pop("path", None)
    return informe


def _generar(tmp_path: pathlib.Path) -> dict:
    return {nombre: _informe(nombre, datos, tmp_path) for nombre, datos in sorted(_casos().items())}


@pytest.mark.parametrize("nombre", sorted(_casos()))
def test_el_informe_no_ha_cambiado(nombre, tmp_path):
    esperado = json.loads(REFERENCIA.read_text())[nombre]
    obtenido = _informe(nombre, _casos()[nombre], tmp_path)
    assert obtenido == esperado, (
        f"\nEl informe de MediaInfo para {nombre} ha cambiado.\n"
        "Si NO era intencionado, el refactor ha alterado el comportamiento.\n"
        "Si sí lo era, regenera la referencia y revisa el diff en el commit."
    )


def test_la_referencia_cubre_lo_que_importa(tmp_path):
    """Una foto de un informe vacío no protegería nada: se comprueba que la
    referencia tiene contenido real en los campos que alimentan al resto."""
    informe = json.loads(REFERENCIA.read_text())["S01E01.mkv"]
    assert informe.get("available") is True
    assert informe.get("rows"), "el informe de referencia no tiene filas"
    assert informe.get("audio_by_language"), "sin audio por idioma no cubre el pack de temporada"
    assert informe.get("proposed_name") or informe.get("audio_summary")


if __name__ == "__main__":  # pragma: no cover - utilidad de mantenimiento
    import sys
    import tempfile

    if "--regenerar" in sys.argv:
        with tempfile.TemporaryDirectory() as d:
            REFERENCIA.write_text(json.dumps(_generar(pathlib.Path(d)), indent=1,
                                             ensure_ascii=False, sort_keys=True))
        print(f"referencia regenerada: {REFERENCIA}")
    else:
        print(__doc__)
