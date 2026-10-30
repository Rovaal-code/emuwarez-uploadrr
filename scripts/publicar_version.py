#!/usr/bin/env python3
"""Publica el manifiesto de versión que lee la tarjeta de Diagnóstico.

El repositorio y el paquete de imágenes son privados, así que la aplicación no
puede preguntarle al registro si hay algo nuevo. La salida es este manifiesto:
un único JSON, público, con el commit, la fecha, el digest y una nota. El
código y la imagen siguen privados; lo único que se publica es "cuál es la
última versión".

Se ejecuta DESPUÉS de `docker push`, porque el digest no existe hasta entonces:

    python3 scripts/publicar_version.py \\
        --digest sha256:abc... \\
        --notas "Una serie SD recupera su resolución"

Sin `--repo` escribe el JSON y dice qué hacer con él, sin tocar nada remoto:
publicar es una acción hacia fuera y no se hace sola.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REPO_POR_DEFECTO = "Kisnov/uploadrr-version"
FICHERO = "latest.json"

# Este fichero es PÚBLICO. La nota de cada versión la lee cualquiera, incluido
# quien quiera atacar a los que todavía no han actualizado: decir "se arregla
# que la API key salía sin enmascarar" es contarle dónde mirar en la versión
# anterior. Estas palabras no significan que el cambio sea malo, significan
# que la nota hay que redactarla en neutro ("mejoras de seguridad").
_PALABRAS_DELICADAS = (
    "api key", "apikey", "clave", "contraseña", "password", "token", "secreto",
    "secret", "credencial", "enmascar", "vulnerab", "exploit", "inyec",
    "systemexit", "expone", "expuesto", "fuga", "leak", "auth", "sesión",
    "permiso", "traversal", "rce", "xss", "csrf",
)


def revisar_nota(nota: str) -> list[str]:
    """Las palabras delicadas que aparecen en la nota, si las hay."""
    bajo = nota.lower()
    return [p for p in _PALABRAS_DELICADAS if p in bajo]


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def construir_manifiesto(digest: str | None, notas: str | None) -> dict:
    return {
        "commit": _git("rev-parse", "HEAD"),
        "fecha": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "digest": digest,
        # NUNCA el título del commit por defecto: es donde se describe el fallo
        # que se acaba de arreglar, y esto es público.
        "notas": notas or "Actualización disponible",
        # La versión del paquete, informativa: la comparación se hace por
        # commit, que es lo único que cambia en cada despliegue.
        "version": _leer_version(),
    }


def _leer_version() -> str:
    raiz = pathlib.Path(__file__).resolve().parents[1]
    for linea in (raiz / "emuwarez_uploadrr" / "__init__.py").read_text(encoding="utf-8").splitlines():
        if linea.startswith("__version__"):
            return linea.split("=", 1)[1].strip().strip('"\'')
    return "?"


def version_publicada(repo: str) -> str | None:
    """La versión del manifiesto publicado ahora mismo.

    Se pregunta a la API de GitHub y NO a raw.githubusercontent.com: esa URL
    sirve una copia cacheada varios minutos, así que justo después de publicar
    devuelve todavía la anterior. Con la caché de por medio este guardián no
    saltaba (comprobado: dejó republicar la misma versión).

    None solo si el manifiesto no existe todavía. Si no se puede preguntar
    (sin red, sin permiso, sin respuesta), lanza RuntimeError: seguir a ciegas
    podría volver a subir una versión ya publicada."""
    import base64
    try:
        salida = subprocess.run(
            ["gh", "api", f"repos/{repo}/contents/{FICHERO}", "--jq", ".content"],
            capture_output=True, text=True, check=True, timeout=20).stdout
    except subprocess.CalledProcessError as e:
        # 404 es también «ese repo no existe o no se ve»: solo es «nada publicado» si el repo responde.
        if "HTTP 404" in (e.stderr or ""):
            try:
                subprocess.run(["gh", "api", f"repos/{repo}", "--silent"],
                               capture_output=True, text=True, check=True, timeout=20)
            except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired) as e2:
                raise RuntimeError(f"no se puede acceder al repositorio {repo}") from e2
            return None
        raise RuntimeError(f"no se pudo leer el manifiesto publicado: {(e.stderr or '').strip()}") from e
    except (OSError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"no se pudo leer el manifiesto publicado: {e}") from e
    return json.loads(base64.b64decode(salida)).get("version")


def _numeros(version: str) -> tuple[int, ...] | None:
    """X.Y.Z como números para compararlas; None si no tiene esa forma."""
    partes = version.split(".")
    return tuple(int(p) for p in partes) if all(p.isdigit() for p in partes) else None


def publicar(manifiesto: dict, repo: str) -> None:
    """Sube el manifiesto al repositorio público, con un commit por versión."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["gh", "repo", "clone", repo, tmp, "--", "--depth", "1"],
                       check=True, capture_output=True)
        destino = pathlib.Path(tmp) / FICHERO
        # UTF-8 explícito: sin él, en Windows sale en cp1252 y la app, que lo
        # lee como UTF-8, no puede decodificar la primera tilde de la nota.
        destino.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
        subprocess.run(["git", "-C", tmp, "add", FICHERO], check=True)
        subprocess.run(["git", "-C", tmp, "commit", "-m",
                        f"{manifiesto['commit'][:7]}: {manifiesto['notas']}"], check=True)
        subprocess.run(["git", "-C", tmp, "push"], check=True)
    print(f"✓ publicado en {repo}/{FICHERO}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--digest", help="digest de la imagen recién subida (sha256:...)")
    p.add_argument("--notas", help="qué trae esta versión, en una línea y en neutro")
    p.add_argument("--acepto-la-nota", action="store_true",
                   help="publicar aunque la nota mencione algo delicado")
    p.add_argument("--misma-version", action="store_true",
                   help="publicar aunque el número de versión no haya cambiado")
    p.add_argument("--solo-comprobar", action="store_true",
                   help="hacer las comprobaciones (nota y, con --repo, versión) y salir sin escribir nada")
    p.add_argument("--repo", nargs="?", const=REPO_POR_DEFECTO,
                   help=f"repositorio público donde publicar (por defecto {REPO_POR_DEFECTO})")
    args = p.parse_args()

    manifiesto = construir_manifiesto(args.digest, args.notas)
    delicadas = revisar_nota(manifiesto["notas"])
    if delicadas and not args.acepto_la_nota:
        print("✗ La nota menciona algo delicado y este fichero es PÚBLICO:",
              ", ".join(delicadas), file=sys.stderr)
        print("\n  " + manifiesto["notas"], file=sys.stderr)
        print("\nQuien lea esto sabe qué buscar en la versión ANTERIOR, que es la que"
              "\nsigue ejecutando quien no haya actualizado. Redáctala en neutro"
              '\n(por ejemplo: "Correcciones y mejoras de seguridad") o repite con'
              "\n--acepto-la-nota si de verdad no compromete nada.", file=sys.stderr)
        return 1

    # La tarjeta y la notificación anuncian la versión por su NÚMERO. Si dos
    # despliegues llevan el mismo, quien lo lea no puede distinguirlos: la
    # notificación dirá lo mismo las dos veces. La comparación interna se hace
    # por commit y sigue funcionando, pero el aviso al usuario queda inútil.
    if args.repo:
        try:
            anterior = version_publicada(args.repo)
        except RuntimeError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        if anterior and anterior == manifiesto["version"] and not args.misma_version:
            print(f"✗ La versión publicada ya es {anterior} y vas a publicar la misma.",
                  file=sys.stderr)
            print("\n  Súbela ANTES de construir la imagen, que es donde se sella:",
                  file=sys.stderr)
            print("    python3 scripts/subir_version.py patch", file=sys.stderr)
            print("\n  O repite con --misma-version si de verdad es una republicación.",
                  file=sys.stderr)
            return 1
        nueva, vieja = _numeros(manifiesto["version"]), _numeros(anterior or "")
        if nueva and vieja and nueva < vieja:
            print(f"✗ La versión publicada es {anterior}, más nueva que la {manifiesto['version']} de este commit.",
                  file=sys.stderr)
            print("\n  Para volver a una versión anterior, fíjala en el compose"
                  " (EMUWAREZ_UPLOADRR_TAG=X.Y.Z): no se republica.", file=sys.stderr)
            return 1

    # Antes de construir: una versión ya publicada no debe mover las etiquetas de la imagen.
    if args.solo_comprobar:
        return 0

    texto = json.dumps(manifiesto, indent=2, ensure_ascii=False)

    if not args.repo:
        salida = pathlib.Path("latest.json")
        salida.write_text(texto + "\n", encoding="utf-8")
        print(texto)
        print(f"\nEscrito en {salida.resolve()}. Para publicarlo de verdad:")
        print(f"  python3 {sys.argv[0]} --digest ... --repo")
        return 0

    publicar(manifiesto, args.repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
