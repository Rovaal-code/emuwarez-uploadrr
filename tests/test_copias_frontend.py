"""Las copias que el frontend tiene del backend, vigiladas desde aquí.

El navegador no puede llamar a Python, así que hay reglas escritas dos veces:
una en `services/` y otra en TypeScript. La auditoría (hallazgos 5.1, 5.2, 5.3
y 7.3) cuenta cuatro, y ninguna la protegía nada más que un comentario pidiendo
cuidado. La regla del pack cambió tres veces en dos días y en cada cambio se
olvidó al menos un sitio.

La técnica es la que ya usa tests/test_emu_format.py con la Guía: abrir el
fichero TypeScript, sacar la lista con una expresión regular y compararla con
la de Python. No es bonito, pero falla cuando tiene que fallar, que es lo
único que se le pide.

El frontend no tiene infraestructura de test (hallazgo 7.1: ni una dependencia
en package.json), así que esta es la única red posible hoy sin montarla.
"""
from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
FRONT = RAIZ / "frontend/src"


def _texto(rel: str) -> str:
    return (FRONT / rel).read_text()


def _cadenas_del_set(fuente: str, nombre: str) -> set[str]:
    """Los literales de un `new Set(['a', 'b'])` declarado en TypeScript."""
    m = re.search(rf"{re.escape(nombre)}\s*=\s*new Set\(\[(.*?)\]\)", fuente, re.S)
    assert m, f"no se encontró {nombre} en el frontend"
    return set(re.findall(r"'([^']+)'", m.group(1)))


def test_la_regla_del_pack_coincide():
    """utils/libraryItem.ts predice lo que hará season_pack. Es la última copia
    viva del hallazgo 2.1: el backend ya genera su SQL y su predicado desde una
    definición, pero el frontend tiene la suya escrita a mano."""
    from emuwarez_uploadrr.services.season_pack import _PACK_ROLLUP_FIELDS

    fuente = _texto("utils/libraryItem.ts")
    m = re.search(r"SEASON_CONSISTENCY_FIELDS[^=]*=\s*\[(.*?)\]", fuente, re.S)
    assert m, "no se encontró SEASON_CONSISTENCY_FIELDS"
    campos = tuple(re.findall(r"key:\s*'([^']+)'", m.group(1)))
    assert campos == tuple(_PACK_ROLLUP_FIELDS), (
        f"\nfrontend: {campos}\nbackend:  {tuple(_PACK_ROLLUP_FIELDS)}"
    )


def test_el_vocabulario_de_estados_coincide():
    """Los conjuntos del frontend son PREDICCIONES de lo que el backend
    aceptará: qué botón se habilita. Si se separan, la interfaz ofrece algo que
    el servidor va a rechazar, o esconde algo que sí valdría.

    Hasta la Fase 4 tres de ellos ni siquiera tenían nombre en el backend: eran
    literales sueltos dentro de consultas, así que no había con qué comparar."""
    from emuwarez_uploadrr.services import upload_states as st

    casos = [
        ("utils/uploadStatus.ts", "ACTIVE_JOB_STATUSES", st.ACTIVE_JOB_STATUSES),
        ("pages/UploadsPage.tsx", "CANCELLABLE_STATUSES", st.CANCELLABLE_STATUSES),
        ("pages/UploadsPage.tsx", "RETRYABLE_STATUSES", st.RETRYABLE_STATUSES),
        ("pages/UploadsPage.tsx", "DELETABLE_STATUSES", st.DELETABLE_STATUSES),
        ("pages/UploadsPage.tsx", "HIDDEN_STATES", st.PREPARATORY_STATUSES),
    ]
    diferencias = []
    for rel, nombre, backend in casos:
        front = _cadenas_del_set(_texto(rel), nombre)
        if front != set(backend):
            diferencias.append(f"{nombre}: frontend={sorted(front)} backend={sorted(backend)}")
    assert not diferencias, "\n" + "\n".join(diferencias)


def test_los_tokens_de_confirmacion_coinciden():
    """Cada acción destructiva pide escribir un token. Están declarados en su
    servicio y repetidos como literal en el frontend; cambiar uno en el backend
    rompía su botón con un "Confirmación requerida" que no explica nada."""
    from emuwarez_uploadrr.services.backup_service import RESTORE_CONFIRMATION
    from emuwarez_uploadrr.services.maintenance_service import (
        CLEANUP_CONFIRMATION, VACUUM_CONFIRMATION,
    )
    from emuwarez_uploadrr.services.mkv_title import MKV_CONFIRMATION_TOKEN
    from emuwarez_uploadrr.services.nomenclature import CONFIRMATION_TOKEN as NOM_TOKEN
    from emuwarez_uploadrr.services.upload_execution import (
        CONFIRMATION_TOKEN as UPLOAD_TOKEN, DELETE_CONFIRMATION_TOKEN,
    )

    # token del backend -> fichero del frontend que lo escribe a mano
    esperados = {
        UPLOAD_TOKEN: "components/UploadPreflightModal.tsx",
        DELETE_CONFIRMATION_TOKEN: "api/uploads.ts",
        NOM_TOKEN: "components/NomenclatureModal.tsx",
        MKV_CONFIRMATION_TOKEN: "components/NomenclatureFieldsModal.tsx",
        VACUUM_CONFIRMATION: "pages/SettingsPage.tsx",
        CLEANUP_CONFIRMATION: "pages/SettingsPage.tsx",
        RESTORE_CONFIRMATION: "pages/SettingsPage.tsx",
    }
    faltan = [f"{token} (esperado en {rel})" for token, rel in esperados.items()
              if token not in _texto(rel)]
    assert not faltan, (
        "\nTokens que el backend exige y el frontend ya no escribe:\n  "
        + "\n  ".join(faltan)
        + "\n\nSi se renombró el token, hay que cambiarlo también en el frontend;"
          "\nsi el botón se movió de fichero, actualiza este test."
    )


def test_el_frontend_conoce_todas_las_fases_de_la_subida():
    """PHASE_LABEL traduce la fase a texto. Una fase que no conozca se enseña
    con su clave interna cruda ("hash_torrent"), y eso pasa justo cuando no hay
    progreso legible: con un trabajo atascado, que es el peor momento."""
    from emuwarez_uploadrr.services.uploadrr_progress import PHASE_ORDER

    fuente = _texto("utils/uploadStatus.ts")
    m = re.search(r"PHASE_LABEL:\s*Record<string, string>\s*=\s*\{(.*?)\n\}", fuente, re.S)
    assert m, "no se encontró PHASE_LABEL"
    conocidas = set(re.findall(r"^\s*([a-z_]+):", m.group(1), re.M))
    faltan = [f for f in PHASE_ORDER if f not in conocidas]
    assert not faltan, (
        f"\nFases que el backend publica y el frontend no sabe traducir: {faltan}"
        f"\nSe enseñarían con su clave interna."
    )


def test_toda_tarea_programada_tiene_nombre_en_espanol():
    """El Panel enseña `task_runs.name`, que es la clave interna. Sin su
    traducción sale en crudo ("check-version"), que fue justo lo que ocurrió al
    añadir la comprobación de versión."""
    from emuwarez_uploadrr.services.scheduler import DEFAULT_TASKS

    fuente = _texto("pages/DashboardPage.tsx")
    m = re.search(r"TASK_NAME_LABEL:\s*Record<string, string>\s*=\s*\{(.*?)\n\}", fuente, re.S)
    assert m, "no se encontró TASK_NAME_LABEL"
    traducidas = dict(re.findall(r"'([^']+)':\s*'([^']+)'", m.group(1)))

    faltan = [clave for clave, *_ in DEFAULT_TASKS if clave not in traducidas]
    assert not faltan, f"\nTareas que el Panel enseñaría con su clave interna: {faltan}"

    # Y con el MISMO nombre que usa Ajustes -> Tareas programadas, para que no
    # se llame de dos maneras según la pantalla.
    distintas = [f"{clave}: Panel='{traducidas[clave]}' Tareas='{nombre}'"
                 for clave, nombre, *_ in DEFAULT_TASKS
                 if clave in traducidas and traducidas[clave] != nombre]
    assert not distintas, "\n" + "\n".join(distintas)
