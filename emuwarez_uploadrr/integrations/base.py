"""Small urllib based HTTP helpers to avoid new dependencies."""
from __future__ import annotations

import json
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional


class IntegrationError(RuntimeError):
    pass


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
                return remote_url.strip()
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
    )
    if not isinstance(file_entry, dict):
        return result
    media_info = file_entry.get("mediaInfo")
    if not isinstance(media_info, dict):
        return result
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
    def _do_request() -> Any:
        body: bytes | None = None
        req_headers = {"Accept": "application/json", "User-Agent": "emuwarez-uploadrr-cli/2"}
        if headers:
            req_headers.update(headers)
        if api_key:
            req_headers["X-Api-Key"] = api_key
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method.upper())
        context = None if verify_ssl else ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return {}
            return json.loads(raw)

    # `timeout` above only bounds the connect/read phases once a socket
    # exists (it's threaded through to socket.create_connection); DNS
    # resolution (getaddrinfo, called first) runs before that and is NOT
    # covered by it — a stuck/misconfigured resolver (common in Docker) can
    # hang past `timeout` indefinitely with no exception ever raised. Running
    # the call on a *daemon* thread and joining it with a hard deadline bounds
    # the whole call — DNS included — no matter what's actually stuck, while
    # still letting the process exit cleanly if the call never returns (a
    # non-daemon executor would otherwise block shutdown forever joining it).
    result: dict[str, Any] = {}

    def _worker() -> None:
        try:
            result["value"] = _do_request()
        except BaseException as exc:  # noqa: BLE001 — forwarded to the caller below
            result["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout + 5)
    if thread.is_alive():
        raise IntegrationError(f"Tiempo de espera agotado conectando con {url}")

    exc = result.get("error")
    if exc is not None:
        if isinstance(exc, urllib.error.HTTPError):
            raw = exc.read().decode("utf-8", errors="replace")
            raise IntegrationError(f"HTTP {exc.code} en {url}: {raw[:500]}") from exc
        if isinstance(exc, urllib.error.URLError):
            raise IntegrationError(f"No se pudo conectar con {url}: {exc.reason}") from exc
        if isinstance(exc, json.JSONDecodeError):
            raise IntegrationError(f"Respuesta no JSON desde {url}") from exc
        raise exc
    return result["value"]


def build_url(base_url: str, path: str, params: Optional[dict[str, Any]] = None) -> str:
    url = normalize_base_url(base_url) + "/" + path.lstrip("/")
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return url
