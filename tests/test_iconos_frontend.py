"""Los iconos de los sitios van dentro del proyecto (frontend/src/assets/iconos): este test avisa si al añadir un
proveedor o un sitio de fichas se olvida su icono (`python scripts/descargar_iconos.py`), o si queda uno de un sitio
que ya no está en ninguna lista."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CARPETA = RAIZ / "frontend" / "src" / "assets" / "iconos"

# Sitios sin icono utilizable: Crunchyroll no deja bajarlo y a VRV (cerrado) Google no lo conoce. Salen con el de
# reserva. Si un día se consigue el de alguno, se quita de aquí.
SIN_ICONO = {"crunchyroll.com", "vrv.co"}


def _script():
    spec = importlib.util.spec_from_file_location("descargar_iconos", RAIZ / "scripts" / "descargar_iconos.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _con_icono() -> set[str]:
    return {p.name.rsplit(".", 1)[0] for p in CARPETA.iterdir() if p.is_file()}


def test_cada_sitio_de_las_listas_tiene_su_icono():
    esperados = set(_script().dominios_con_icono()) - SIN_ICONO
    faltan = sorted(esperados - _con_icono())
    assert not faltan, f"faltan iconos en frontend/src/assets/iconos: {faltan}. Corre scripts/descargar_iconos.py"


def test_no_quedan_iconos_de_sitios_que_ya_no_estan():
    sobran = sorted(_con_icono() - set(_script().dominios_con_icono()))
    assert not sobran, f"iconos de sitios que ya no están en ninguna lista: {sobran}"


def test_los_sin_icono_siguen_sin_tenerlo():
    """Si aparece el icono de uno de SIN_ICONO, hay que quitarlo de la lista de excepciones."""
    assert not (SIN_ICONO & _con_icono())
    assert SIN_ICONO <= set(_script().dominios_con_icono())


def test_las_webs_de_las_fichas_estan_en_el_script():
    """Los sitios a los que enlazan las fichas (`idVerifyUrl` en utils/libraryItem.ts y RequestFormModal.tsx) tienen
    que estar en WEBS_DE_FICHAS: sin ello su icono no se bajaría."""
    enlazados: set[str] = set()
    for fichero in ("utils/libraryItem.ts", "components/RequestFormModal.tsx"):
        texto = (RAIZ / "frontend" / "src" / fichero).read_text(encoding="utf-8")
        enlazados |= set(re.findall(r"`https://([\w.-]+)/(?:tv|movie|title|dereferrer|anime|shows)", texto))
    assert enlazados, "no se encontró ningún enlace de ficha"
    assert enlazados <= set(_script().WEBS_DE_FICHAS), enlazados - set(_script().WEBS_DE_FICHAS)


def test_los_iconos_son_imagenes_y_no_pesan_de_mas():
    for p in CARPETA.iterdir():
        datos = p.read_bytes()
        assert _script().extension_de(datos) is not None, f"{p.name} no es una imagen que se sirva"
        assert len(datos) <= 20_000, f"{p.name} pesa {len(datos)} bytes: redúcelo a un PNG de 64 px"
