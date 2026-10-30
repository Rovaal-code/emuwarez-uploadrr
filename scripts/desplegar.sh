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
# Al publicar crea también la etiqueta vX.Y.Z en el commit y la sube, y la
# imagen sale también como :X.Y.Z, que es la que se fija en el compose
# (EMUWAREZ_UPLOADRR_TAG=X.Y.Z) para quedarse en una versión o volver a ella.
#
# Lo normal es el workflow «Publicar versión», que hace lo mismo en GitHub tras
# pasar los tests. Esto es la alternativa local, sin gastar minutos de Actions.
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

# La etiqueta vX.Y.Z de esta versión. Nunca se pisa: si ya existe en otro
# commit, aquí o en GitHub, se para antes de construir nada y hay que
# resolverlo a mano. Lo que manda es GitHub, porque es su etiqueta la que
# marca la versión publicada. De una etiqueta anotada, ls-remote da también la
# línea "^{}" con el commit al que apunta; de una ligera (las de una release
# hecha en la web), solo esa.
ETIQUETA="v$VERSION"

# Si no se puede preguntar a GitHub (sin red, sin permiso), es un error, no
# "no hay etiqueta": se para en vez de seguir a ciegas.
etiqueta_remota() {
  local salida
  salida="$(git ls-remote --tags origin "refs/tags/$ETIQUETA" "refs/tags/$ETIQUETA^{}")" || {
    echo "No se pudo consultar en GitHub la etiqueta $ETIQUETA." >&2
    return 1
  }
  printf '%s\n' "$salida" | sort -k2 | tail -1 | cut -f1
}

etiqueta_local() {
  git rev-parse -q --verify "refs/tags/$ETIQUETA^{commit}" || true
}

comprobar_etiqueta() {
  local remota local_
  # Con `|| return 1` explícito: se llama dentro de un `||`, donde set -e no
  # actúa, y un fallo de la consulta pasaría por "no hay etiqueta".
  remota="$(etiqueta_remota)" || return 1
  local_="$(etiqueta_local)"
  if [[ -n "$remota" && "$remota" != "$COMMIT" ]]; then
    echo "La etiqueta $ETIQUETA ya está en GitHub en $remota, no en este commit." >&2
    echo "No se pisa: sube la versión (--version patch) o quita la etiqueta que sobra." >&2
    return 1
  fi
  if [[ -n "$local_" && "$local_" != "$COMMIT" ]]; then
    echo "La etiqueta $ETIQUETA existe aquí en $local_, no en este commit." >&2
    echo "Si sobra:  git tag -d $ETIQUETA  y vuelve a lanzar esto." >&2
    return 1
  fi
}

# Al final, con el manifiesto ya publicado: crea la etiqueta, o sube la que
# una ejecución anterior dejó solo aquí. Solo si el commit es la punta de
# master en GitHub: la etiqueta marca en el repo el commit de esta versión.
etiquetar() {
  # Otra vez, por si algo ha cambiado mientras se construía.
  comprobar_etiqueta || return 1
  local remota
  remota="$(etiqueta_remota)" || return 1
  # Entre una consulta y otra alguien podría haberla creado en otro commit.
  if [[ -n "$remota" && "$remota" != "$COMMIT" ]]; then
    echo "La etiqueta $ETIQUETA ya está en GitHub en $remota, no en este commit." >&2
    return 1
  fi
  if [[ -n "$remota" ]]; then
    echo "La etiqueta $ETIQUETA ya está en GitHub."
    return 0
  fi
  git fetch -q origin master
  if [[ "$(git rev-parse origin/master)" != "$COMMIT" ]]; then
    echo "Este commit no es la punta de master en GitHub, así que no creo $ETIQUETA." >&2
    echo "Cuando lo sea:  git tag -a $ETIQUETA -m \"…\" $COMMIT && git push origin $ETIQUETA" >&2
    return 0
  fi
  if [[ -n "$(etiqueta_local)" ]]; then
    echo "La etiqueta $ETIQUETA estaba creada aquí pero sin subir: la subo."
  else
    git tag -a "$ETIQUETA" -m "${NOTAS:-Versión $VERSION}" "$COMMIT"
  fi
  git push -q origin "$ETIQUETA"
  echo "Etiqueta .... $ETIQUETA"
}

if [[ "$PUBLICAR" -eq 1 ]]; then
  comprobar_etiqueta || exit 1
  # Antes de construir: repetir una versión ya publicada movería :latest y :X.Y.Z a otro digest.
  python3 scripts/publicar_version.py --solo-comprobar --notas "$NOTAS" --repo
  # Y que gh puede escribir el manifiesto: el endpoint de push de git solo da 200 a quien puede.
  # El token va por stdin (printf es interno), no en los argumentos de curl.
  if ! printf 'user = "x:%s"\n' "$(gh auth token)" | curl -sf -o /dev/null --connect-timeout 10 --max-time 30 \
      --config - "https://github.com/Kisnov/uploadrr-version.git/info/refs?service=git-receive-pack"; then
    echo "gh no puede escribir en Kisnov/uploadrr-version: no se sube ninguna imagen." >&2
    exit 1
  fi
fi

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
# :X.Y.Z solo al publicar (comprobar_etiqueta ya ha parado si esa versión es de otro commit), y
# antes que :latest: si falla una de las dos, :latest no avanza a algo sin anunciar.
if [[ "$PUBLICAR" -eq 1 ]]; then
  docker tag "$IMAGEN" "${IMAGEN%:*}:$VERSION"
  docker push "${IMAGEN%:*}:$VERSION"
fi
docker push "$IMAGEN"
DIGEST="$(docker image inspect "$IMAGEN" --format '{{index .RepoDigests 0}}' | cut -d@ -f2)"
echo "Digest ...... $DIGEST"

if [[ "$PUBLICAR" -eq 0 ]]; then
  echo
  echo "Sin publicar el manifiesto ni crear la etiqueta, como pediste. Para anunciarla:"
  echo "  docker tag $IMAGEN ${IMAGEN%:*}:$VERSION && docker push ${IMAGEN%:*}:$VERSION"
  echo "  python3 scripts/publicar_version.py --digest $DIGEST --notas \"…\" --repo"
  echo "  git tag -a v$VERSION -m \"…\" $COMMIT && git push origin v$VERSION"
  exit 0
fi

echo "Publicando el manifiesto…"
python3 scripts/publicar_version.py --digest "$DIGEST" --notas "$NOTAS" --repo
etiquetar
