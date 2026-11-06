"""HTTP helpers for the integrations (the requests themselves go out through `http_cliente`)."""
from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any, Optional

from . import http_cliente


class IntegrationError(RuntimeError):
    def __init__(self, mensaje: str = "", *, status: Optional[int] = None):
        super().__init__(mensaje)
        self.status = status  # código HTTP, si la respuesta llegó


def es_lista_de_fichas(data: Any) -> bool:
    """Si un listado de Radarr/Sonarr se puede tomar por todo lo que tienen: una lista de fichas con su id, un entero
    positivo. La sincronización de biblioteca borra lo que no ve, así que una respuesta de error o con fichas sin un
    id de verdad (que se guardarían todas como una sola) le haría borrar lo de la instancia entera. [] sí pasa: es
    lo legítimo en una instancia sin nada, y si la instancia ya tiene filas la sincronización la rechaza."""
    return isinstance(data, list) and all(isinstance(f, dict) and type(f.get("id")) is int and f["id"] > 0 for f in data)


def _extract_cover_url(images: Any, cover_type: str) -> Optional[str]:
    """Pick a cover URL of the given type out of a Radarr/Sonarr `images`
    array. Each entry looks like {"coverType": "poster"|"fanart", "url":
    "/MediaCover/...", "remoteUrl": "https://..."}. `remoteUrl` is preferred
    — it's a fully qualified, publicly loadable URL, unlike the relative
    `url` field, which normally requires the instance's own API key/session
    to load through `/MediaCover/...`. Returns None if there's no matching
    entry or no remoteUrl on it (never raises — this is best-effort
    metadata, not something sync should ever fail over)."""
    if not isinstance(images, list):
        return None
    for image in images:
        if isinstance(image, dict) and image.get("coverType") == cover_type:
            remote_url = image.get("remoteUrl")
            if isinstance(remote_url, str) and remote_url.strip():
                # La CSP de la interfaz solo deja cargar imágenes por https, y TMDb y TheTVDB también las sirven así.
                return re.sub(r"^http://", "https://", remote_url.strip(), flags=re.I)
    return None


def extract_poster_url(images: Any) -> Optional[str]:
    """Pick a poster URL out of a Radarr/Sonarr `images` array (Phase 11E)."""
    return _extract_cover_url(images, "poster")


def extract_backdrop_url(images: Any) -> Optional[str]:
    """Pick a fanart/backdrop URL out of a Radarr/Sonarr `images` array —
    same shape and origin as the poster, just the wide background art
    instead of the cover (used as the dedicated page's hero background)."""
    return _extract_cover_url(images, "fanart")


class MediaInfoSummary(dict):
    """video_codec/audio_codec/audio_languages/subtitle_languages, all
    Optional[str] — a plain dict subclass just for a descriptive type name."""


def _resolution_from_arr_media_info(media_info: dict) -> Optional[str]:
    """El código canónico de resolución a partir del "640x480" de *Arr."""
    crudo = str(media_info.get("resolution") or "").strip()
    m = re.match(r"(\d+)\s*[xX*]\s*(\d+)", crudo)
    if not m:
        return None
    from ..services.media_probe import resolution_code
    return resolution_code(int(m.group(1)), int(m.group(2)))


# Lo que *Arr toma por grupo cuando el archivo no lleva ninguno y el nombre
# acaba en un dato técnico ("…-AC3", "….1080p"). Comparado sin puntos ni guiones.
_GRUPOS_FALSOS = {
    "sd", "sdtv", "hd", "uhd", "4k", "8k",
    "x264", "x265", "h264", "h265", "hevc", "avc", "av1", "xvid", "divx", "vp9",
    "10bit", "8bit", "hdr", "hdr10", "dv", "sdr",
    "aac", "ac3", "eac3", "dd", "ddp", "dd+", "dts", "dtshd", "truehd", "atmos",
    "flac", "opus", "mp3", "pcm", "lpcm", "20", "51", "71",
    "web", "webdl", "webrip", "bluray", "bdrip", "brrip", "bdremux", "remux",
    "hdtv", "dvd", "dvdrip", "hdrip",
}


def extract_release_group(file_entry: Any) -> Optional[str]:
    """El `releaseGroup` de movieFile/episodeFile, salvo que sea un dato técnico."""
    grupo = (file_entry.get("releaseGroup") if isinstance(file_entry, dict) else None) or ""
    plano = re.sub(r"[.\- ]", "", grupo.strip().lower())
    if not plano or plano in _GRUPOS_FALSOS or re.fullmatch(r"\d{3,4}[pi]|\d{1,2}ch", plano):
        return None
    return grupo.strip()


def extract_media_info(file_entry: Any) -> MediaInfoSummary:
    """Pull codec/audio/subtitle info out of Radarr's `movieFile` or Sonarr's
    `episodeFile` — both come from the same underlying *arr `mediaInfo`
    sub-object shape (`/api/v3/moviefile`, `/api/v3/episodefile`). This is
    already present in the API response Radarr/Sonarr send for every
    synced item (no extra HTTP call), it was just never parsed — the app
    used to guess video_codec from a substring match against the quality
    profile NAME (e.g. "Bluray-1080p"), which has nothing to do with the
    actual codec and silently failed for exactly the common case where the
    quality name doesn't happen to mention it.

    Never raises — always returns a dict with every key present (None if
    absent), so callers can rely on `.get(...)` without checking shape."""
    result = MediaInfoSummary(
        video_codec=None, audio_codec=None, audio_languages=None,
        subtitle_languages=None, audio_channels=None, dynamic_range=None,
        resolution=None,
    )
    if not isinstance(file_entry, dict):
        return result
    media_info = file_entry.get("mediaInfo")
    if not isinstance(media_info, dict):
        return result
    # La resolución venía en el mismo `mediaInfo` y no se leía: Sonarr la manda
    # como "640x480". Sin ella, una serie SD ("SDTV", "DVD", "Raw-HD": nombres
    # de calidad sin ningún número) se quedaba con la resolución vacía en la
    # biblioteca, y entonces su temporada no se podía subir como pack porque la
    # regla exige que todos los capítulos coincidan en resolución. En Sonarr y
    # en Ver MediaInfo se veía perfectamente; solo faltaba aquí.
    result["resolution"] = _resolution_from_arr_media_info(media_info)
    result["video_codec"] = media_info.get("videoCodec") or None
    result["audio_codec"] = media_info.get("audioCodec") or None
    # audioLanguages/subtitles come back as a single string, e.g. "eng / spa"
    # — kept as-is (already human-readable), not split into a list.
    result["audio_languages"] = media_info.get("audioLanguages") or None
    result["subtitle_languages"] = media_info.get("subtitles") or None
    # audioChannels (e.g. 5.1) and HDR/DV (videoDynamicRangeType preferred, it
    # distinguishes DV vs HDR10 where videoDynamicRange is just "HDR").
    ch = media_info.get("audioChannels")
    result["audio_channels"] = str(ch) if ch not in (None, "", 0) else None
    result["dynamic_range"] = (
        media_info.get("videoDynamicRangeType") or media_info.get("videoDynamicRange") or None
    )
    return result


def normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise IntegrationError("URL vacía")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def request_json(
    method: str,
    url: str,
    *,
    api_key: Optional[str] = None,
    headers: Optional[dict[str, str]] = None,
    data: Any = None,
    timeout: int = 20,
    verify_ssl: bool = True,
) -> Any:
    req_headers = {"Accept": "application/json", "User-Agent": "emuwarez-uploadrr-cli/2"}
    if headers:
        req_headers.update(headers)
    if api_key:
        req_headers["X-Api-Key"] = api_key
    body: bytes | None = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json"

    def _do_request() -> Any:
        respuesta = http_cliente.pedir(
            method, url, cabeceras=req_headers, contenido=body, timeout=timeout, verify=verify_ssl,
        )
        raw = http_cliente.texto(respuesta.content)
        if not raw:
            return {}
        return json.loads(raw)

    # `timeout` only bounds each phase once a socket exists; DNS resolution
    # (getaddrinfo, called first) runs before that and is NOT covered by it —
    # a stuck/misconfigured resolver (common in Docker) can hang past
    # `timeout` indefinitely with no exception ever raised. con_plazo runs the
    # call on a *daemon* thread joined with a hard deadline, which bounds the
    # whole call — DNS included — no matter what's actually stuck, while still
    # letting the process exit cleanly if the call never returns.
    # Estos mensajes acaban en app.log, en task_runs y en la respuesta HTTP:
    # eMuwarez y TMDb llevan la clave en la URL, así que nunca va entera.
    safe_url = url_sin_claves(url)
    try:
        return http_cliente.con_plazo(_do_request, timeout + 5)
    except http_cliente.PlazoAgotado:
        raise IntegrationError(f"Tiempo de espera agotado conectando con {safe_url}") from None
    except http_cliente.ErrorHTTP as exc:
        # El cuerpo de error puede repetir la URL pedida, clave incluida.
        raw = _tapar_claves(exc.texto(), url)
        raise IntegrationError(f"HTTP {exc.status} en {safe_url}: {raw[:500]}", status=exc.status) from None
    except http_cliente.ErrorConexion as exc:
        raise IntegrationError(f"No se pudo conectar con {safe_url}: {_tapar_claves(exc.motivo, url)}") from None
    except json.JSONDecodeError:
        raise IntegrationError(f"Respuesta no JSON desde {safe_url}") from None
    except Exception as exc:
        # Su mensaje puede llevar la URL con la clave: solo el tipo.
        raise IntegrationError(f"Error con {safe_url}: {type(exc).__name__}") from None


_PARAMETROS_CLAVE = {"api_token", "api_key", "apikey"}


def _claves_de(url: str) -> list[str]:
    """Cada clave de la URL tal como puede reaparecer en un texto: la que viaja (con %2B, %2F...), la decodificada y
    sus formas citadas. Las más largas primero, para que una no se coma a otra."""
    query = urllib.parse.urlsplit(url).query
    variantes: set[str] = set()
    for par in query.split("&"):
        nombre, _, crudo = par.partition("=")
        if urllib.parse.unquote_plus(nombre).lower() not in _PARAMETROS_CLAVE or not crudo:
            continue
        valor = urllib.parse.unquote_plus(crudo)
        variantes.update({crudo, valor, urllib.parse.quote(valor, safe=""), urllib.parse.quote_plus(valor)})
    return sorted((v for v in variantes if v), key=len, reverse=True)


def _tapar_claves(texto: str, url: str) -> str:
    for clave in _claves_de(url):
        texto = texto.replace(clave, "***")
    return texto


def url_sin_claves(url: str) -> str:
    """La URL sin usuario:contraseña y con el valor de los parámetros de clave cambiado por ***."""
    parts = urllib.parse.urlsplit(url)
    parts = parts._replace(netloc=parts.netloc.rpartition("@")[2])
    query = [
        (k, "***" if k.lower() in _PARAMETROS_CLAVE else v)
        for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query, safe="*")))


# Nombres de parámetro, de campo o de cabecera cuyo valor es una credencial (api_key=…, token=…, password=…).
_NOMBRES_CLAVE = r"api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|token|password|passwd|pwd|secret|key"
_RE_PARAMETRO = re.compile(
    rf"(?<![A-Za-z0-9])((?:{_NOMBRES_CLAVE})\s*=\s*)(?!\*\*\*)[^&\s\"'<>)\]}},;]+", re.IGNORECASE,
)
_RE_CAMPO_JSON = re.compile(rf"""((?<![A-Za-z0-9])(?:{_NOMBRES_CLAVE})["']\s*:\s*["'])[^"']+""", re.IGNORECASE)  # "api_key": "…"
_RE_USUARIO_EN_URL = re.compile(r"(\b[A-Za-z][A-Za-z0-9+.-]*://)[^/?#\s@]+@")
_RE_CABECERA = re.compile(
    r"\b(x-api-key|authorization|proxy-authorization)([\"']?\s*[:=]\s*[\"']?)((?:Bearer|Basic|Token)\s+)?[^\s\"',;]+",
    re.IGNORECASE,
)
_RE_BOT_DE_TELEGRAM = re.compile(r"(/bot)\d+:[A-Za-z0-9_-]+")  # api.telegram.org/bot<id>:<token>/sendMessage
_RE_WEBHOOK_DE_DISCORD = re.compile(r"(/webhooks/\d+/)[A-Za-z0-9._-]+")


def tapar_claves(texto: str, *claves: Optional[str]) -> str:
    """El texto con las credenciales cambiadas por ***, en cualquier sitio donde aparezcan, no solo en una URL entera.

    Tapa cada valor de `claves` (la API key o la contraseña configuradas, tal cual y en sus formas citadas), y por
    forma: `api_key=…`/`api_token=…`/`token=…`/`password=…` (con cualquier separador alrededor), `usuario:clave@` en
    una URL, las cabeceras `X-Api-Key`/`Authorization`, el token de un bot de Telegram y el de un webhook de
    Discord. Para el texto de una excepción antes de devolverlo, registrarlo o guardarlo; no cambia el que no lleva
    nada de eso."""
    if not texto:
        return texto
    for clave in claves:
        if not clave or len(clave) < 4:
            continue
        variantes = {clave, urllib.parse.quote(clave, safe=""), urllib.parse.quote_plus(clave)}
        for variante in sorted(variantes, key=len, reverse=True):
            texto = texto.replace(variante, "***")
    texto = _RE_USUARIO_EN_URL.sub(r"\1***@", texto)
    texto = _RE_PARAMETRO.sub(r"\1***", texto)
    texto = _RE_CAMPO_JSON.sub(r"\1***", texto)
    texto = _RE_CABECERA.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}***", texto)
    texto = _RE_BOT_DE_TELEGRAM.sub(r"\1***", texto)
    return _RE_WEBHOOK_DE_DISCORD.sub(r"\1***", texto)


def texto_de_error(exc: BaseException, *claves: Optional[str]) -> str:
    """`str(exc)` con las credenciales tapadas (ver `tapar_claves`): el único camino para que el texto de una
    excepción llegue a una respuesta HTTP, un log, una notificación o una columna de la base. Una excepción de
    integración puede llevar la URL pedida, y eMuwarez y TMDb llevan la clave en ella."""
    return tapar_claves(str(exc), *claves)


def build_url(base_url: str, path: str, params: Optional[dict[str, Any]] = None) -> str:
    url = normalize_base_url(base_url) + "/" + path.lstrip("/")
    if params:
        # doseq: un valor lista repite la clave (category_id[]=1&category_id[]=2).
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
    return url
