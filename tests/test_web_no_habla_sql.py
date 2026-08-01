"""La capa web no habla SQL.

Hallazgo 6.2 de la auditoría: había 54 consultas dentro de web/api/, veinte
solo en library.py. El ejemplo redondo era el guardado de nomenclatura: un
INSERT de dieciséis columnas escrito en el controlador HTTP, con seis líneas
de comentario explicando en qué columna escribir y por qué la de al lado era
huérfana. Eso es conocimiento de dominio y estaba en la puerta de entrada.

Un endpoint traduce HTTP a una llamada de servicio y de vuelta. Si además
decide qué se consulta, la misma pregunta acaba contestándose distinto según
si entras por la web o por otro sitio, que es el patrón que motivó toda la
auditoría.
"""
from __future__ import annotations

import io
import pathlib
import re
import tokenize

# Solo los ENDPOINTS. web/services/auth_service.py se queda fuera a
# propósito: la tabla `users` es de la capa web (sesiones y login), no del
# dominio de medios, y ahí el SQL está en su sitio.
API = pathlib.Path(__file__).resolve().parents[1] / "emuwarez_uploadrr" / "web" / "api"

_SQL = re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", re.I)


def _cadenas(src: str) -> list[str]:
    try:
        return [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                if t.type is tokenize.STRING]
    except tokenize.TokenError:
        return [src]


def test_ningun_endpoint_ejecuta_sql():
    culpables = []
    for f in sorted(API.rglob("*.py")):
        src = f.read_text()
        if ".execute(" not in src:
            continue
        if any(_SQL.search(c) for c in _cadenas(src)):
            culpables.append(str(f.relative_to(API.parent.parent)))
    assert not culpables, (
        "\nSQL dentro de la capa web:\n  " + "\n  ".join(culpables)
        + "\n\nMueve la consulta a services/ con un nombre que diga qué pregunta,"
          "\ny que el endpoint la llame."
    )
