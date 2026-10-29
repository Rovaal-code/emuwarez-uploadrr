#!/usr/bin/env bash
# Construye, publica y anuncia una versión, en ese orden y sin pasos sueltos.
#
# Existe porque los dos build-args de este Dockerfile son fáciles de olvidar y
# fallan en silencio, cada uno a su manera:
#
#   UPLOADRR_COMMIT  Docker cachea el `git clone` del fork por el texto del
#                    comando, no por lo que hay al otro lado de la red. Sin
#                    este argumento la imagen sale con una copia vieja del
#                    fork sin avisar. Ya pasó, varias veces.
#
#   APP_COMMIT       Es el sello que la tarjeta de Diagnóstico compara con el
#                    manifiesto publicado. Sin él la imagen se construye
#                    igual, pero "Comprobar versión" queda Omitido para
#                    siempre, diciendo que estás ejecutando desde el código
#                    fuente aunque estés en la imagen. También pasó.
#
# Uso:
#   scripts/desplegar.sh --notas "Lo que cambia, en una línea"
#   scripts/desplegar.sh --notas "..." --version patch   # sube la versión antes
#   scripts/desplegar.sh --notas "..." --sin-publicar    # construye y sube, sin anunciar
#
# Al publicar crea también la etiqueta vX.Y.Z en el commit y la sube. Con ella
# el workflow Imagen le pone a la imagen de ese commit la etiqueta X.Y.Z, que es
# la que se fija en el compose (EMUWAREZ_UPLOADRR_TAG=X.Y.Z) para quedarse en
# una versión o volver a ella.
#
# Necesita `gh auth login` hecho, para publicar la versión.
set -euo pipefail

IMAGEN="ghcr.io/kisnov/emuwarez-uploadrr:latest"
FORK="https://github.com/Kisnov/Uploadrr-EMU.git"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

NOTAS=""
ESCALA=""
PUBLICAR=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --notas)         NOTAS="$2"; shift 2 ;;
    --version)       ESCALA="$2"; shift 2 ;;
    --sin-publicar)  PUBLICAR=0; shift ;;
    -h|--help)       sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "Argumento no reconocido: $1" >&2; exit 2 ;;
  esac
done

cd "$RAIZ"

if [[ -z "$NOTAS" && "$PUBLICAR" -eq 1 ]]; then
  echo "Falta --notas: es la línea que verá el usuario en el aviso de versión." >&2
  echo "(o --sin-publicar si esta vez no quieres anunciar nada)" >&2
  exit 2
fi

# El árbol tiene que estar limpio ANTES de sellar: el sello es el commit, y un
# cambio sin commitear se colaría en la imagen sin aparecer en ese commit.
if [[ -n "$(git status --porcelain)" ]]; then
  echo "Hay cambios sin commitear. El sello sería mentira: la imagen llevaría" >&2
  echo "código que ese commit no tiene. Commitea primero." >&2
  git status --short >&2
  exit 1
fi

if [[ -n "$ESCALA" ]]; then
  python3 scripts/subir_version.py "$ESCALA"
  echo "La versión ha cambiado: commitea ese cambio y vuelve a lanzar esto." >&2
  exit 1
fi

COMMIT="$(git rev-parse HEAD)"
FECHA="$(date -u '+%Y-%m-%d %H:%M UTC')"
VERSION="$(python3 scripts/subir_version.py --ver)"

echo "Versión ..... $VERSION"
echo "Commit ...... $COMMIT"
echo "Construida .. $FECHA"

echo "Resolviendo el HEAD del fork…"
COMMIT_FORK="$(git ls-remote "$FORK" main | cut -f1)"
if [[ -z "$COMMIT_FORK" ]]; then
  echo "No se pudo leer el HEAD del fork. Sin eso la caché de Docker serviría" >&2
  echo "una copia vieja sin avisar, así que paramos aquí." >&2
  exit 1
fi
echo "Fork ........ $COMMIT_FORK"

REGISTRO="$(mktemp -t desplegar-XXXXXX.log)"
echo "Construyendo (registro en $REGISTRO)…"
if ! docker build \
    --build-arg "UPLOADRR_COMMIT=$COMMIT_FORK" \
    --build-arg "APP_COMMIT=$COMMIT" \
    --build-arg "APP_BUILD_DATE=$FECHA" \
    -t "$IMAGEN" . > "$REGISTRO" 2>&1; then
  echo "La construcción ha fallado. Últimas líneas:" >&2
  tail -30 "$REGISTRO" >&2
  exit 1
fi

# Comprobar el sello en la imagen ya construida, no fiarse de haberlo pasado:
# es justo el fallo que este script existe para evitar.
SELLO="$(docker image inspect "$IMAGEN" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
if [[ "$SELLO" != "$COMMIT" ]]; then
  echo "La imagen ha salido sellada como '$SELLO' en vez de '$COMMIT'." >&2
  echo "No se sube: quedaría otra build muda." >&2
  exit 1
fi
echo "Sello verificado en la imagen."

echo "Subiendo…"
docker push "$IMAGEN"
DIGEST="$(docker image inspect "$IMAGEN" --format '{{index .RepoDigests 0}}' | cut -d@ -f2)"
echo "Digest ...... $DIGEST"

# La etiqueta vX.Y.Z en este commit. Solo si es la punta de master ya subida a
# GitHub: la imagen de cada commit la construye el workflow Imagen con el push a
# master, y la etiqueta solo le añade el nombre de la versión a esa imagen.
etiquetar() {
  local etiqueta="v$VERSION" remota local_
  # Lo que manda es GitHub: es la etiqueta de allí la que dispara el workflow.
  # De una etiqueta anotada, ls-remote da también la línea "^{}" con el commit
  # al que apunta; de una ligera (las de una release hecha en la web), solo esa.
  remota="$(git ls-remote --tags origin "refs/tags/$etiqueta" "refs/tags/$etiqueta^{}" |
    sort -k2 | tail -1 | cut -f1)"
  if [[ -n "$remota" ]]; then
    if [[ "$remota" == "$COMMIT" ]]; then
      echo "La etiqueta $etiqueta ya está en GitHub."
    else
      echo "La etiqueta $etiqueta ya está en GitHub, pero en $remota y no en este commit: no la toco." >&2
    fi
    return 0
  fi
  git fetch -q origin master
  if [[ "$(git rev-parse origin/master)" != "$COMMIT" ]]; then
    echo "Este commit no es la punta de master en GitHub, así que no creo $etiqueta." >&2
    echo "Cuando lo sea:  git tag -a $etiqueta -m \"…\" $COMMIT && git push origin $etiqueta" >&2
    return 0
  fi
  # Puede estar ya aquí y no en GitHub: una ejecución anterior la creó y el push
  # falló. Si es de este commit se sube; si es de otro, se avisa.
  if local_="$(git rev-parse -q --verify "refs/tags/$etiqueta^{commit}")"; then
    if [[ "$local_" != "$COMMIT" ]]; then
      echo "La etiqueta $etiqueta existe aquí pero en $local_, no en este commit." >&2
      echo "Si sobra:  git tag -d $etiqueta  y vuelve a lanzar esto." >&2
      return 0
    fi
    echo "La etiqueta $etiqueta estaba creada aquí pero sin subir: la subo."
  else
    git tag -a "$etiqueta" -m "${NOTAS:-Versión $VERSION}" "$COMMIT"
  fi
  git push -q origin "$etiqueta"
  echo "Etiqueta .... $etiqueta (la imagen :$VERSION la añade el workflow Imagen)"
}

if [[ "$PUBLICAR" -eq 0 ]]; then
  echo
  echo "Sin publicar el manifiesto ni crear la etiqueta, como pediste. Para anunciarla:"
  echo "  python3 scripts/publicar_version.py --digest $DIGEST --notas \"…\" --repo"
  echo "  git tag -a v$VERSION -m \"…\" $COMMIT && git push origin v$VERSION"
  exit 0
fi

echo "Publicando el manifiesto…"
python3 scripts/publicar_version.py --digest "$DIGEST" --notas "$NOTAS" --repo
etiquetar
