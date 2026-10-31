"""Tests for services/media_info_service.py (Phase 6B).

The `mediainfo` binary isn't installed in this dev/test sandbox (only the
Docker homelab image has it via apt) — every test here mocks
`mediainfo_available()`/`legacy.run_mediainfo_json()` rather than shelling
out for real.
"""
from __future__ import annotations

from unittest.mock import patch

from emuwarez_uploadrr.services import media_info_service as svc


def _fake_mediainfo_json():
    return {
        "media": {
            "track": [
                {"@type": "General"},
                {"@type": "Video", "Format": "HEVC", "Width": "1920", "Height": "1080"},
                {"@type": "Audio", "Format": "E-AC-3", "Language": "eng"},
                {"@type": "Audio", "Format": "E-AC-3", "Language": "spa"},
                {"@type": "Text", "Language": "eng"},
                {"@type": "Text", "Language": "spa"},
            ]
        }
    }


def test_mediainfo_available_reflects_shutil_which():
    with patch("shutil.which", return_value=None):
        assert svc.mediainfo_available() is False
    with patch("shutil.which", return_value="/usr/bin/mediainfo"):
        assert svc.mediainfo_available() is True


def test_read_media_info_summary_returns_none_when_binary_missing(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with patch.object(svc, "mediainfo_available", return_value=False):
        assert svc.read_media_info_summary(str(f)) is None


def test_read_media_info_summary_returns_none_for_missing_file():
    with patch.object(svc, "mediainfo_available", return_value=True):
        assert svc.read_media_info_summary("/nonexistent/path/movie.mkv") is None


def test_read_media_info_summary_returns_none_for_empty_path():
    assert svc.read_media_info_summary("") is None
    assert svc.read_media_info_summary(None) is None


def test_read_media_info_summary_parses_real_tracks(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", return_value=_fake_mediainfo_json()),
    ):
        result = svc.read_media_info_summary(str(f))
    assert result["video_codec"] == "HEVC"
    # legacy.audio_codec() maps the raw "E-AC-3" format string to its
    # commercial name (Dolby Digital Plus), not passed through verbatim.
    assert result["audio_codec"] == "DD+"
    assert result["audio_languages"] == "ING / ESP"
    assert result["subtitle_languages"] == "ING / ESP"


def test_read_media_info_summary_never_prompts_on_unknown_language(tmp_path):
    """The legacy CLI's map_audio_language() called prompt()/input() on an
    unmapped language — unacceptable in a web request handler. This must
    fall back to the base language's code instead of blocking (and without the
    dangling hyphen "XX-" the old whole-string truncation gave)."""
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    info = {"media": {"track": [
        {"@type": "Video", "Format": "AVC"},
        {"@type": "Audio", "Format": "AAC", "Language": "xx-unknown"},
    ]}}
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", return_value=info),
        patch("builtins.input", side_effect=AssertionError("must never prompt")),
    ):
        result = svc.read_media_info_summary(str(f))
    assert result["audio_languages"] == "XX"


def test_read_media_info_summary_handles_subprocess_failure(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", side_effect=RuntimeError("mediainfo falló")),
    ):
        assert svc.read_media_info_summary(str(f)) is None


# ---------------------------------------------------------------------------
# build_mediainfo_report — on-demand MediaInfo vs eMuwarez comparison table
# ---------------------------------------------------------------------------

def test_build_mediainfo_report_empty_path():
    r = svc.build_mediainfo_report("")
    assert r["available"] is False and r["rows"] == []


def test_build_mediainfo_report_binary_missing(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with patch.object(svc, "mediainfo_available", return_value=False):
        r = svc.build_mediainfo_report(str(f))
    assert r["available"] is False
    assert "mediainfo" in r["message"].lower()


def test_build_mediainfo_report_missing_file():
    with patch.object(svc, "mediainfo_available", return_value=True):
        r = svc.build_mediainfo_report("/nonexistent/movie.mkv")
    assert r["available"] is False and r["rows"] == []


def test_build_mediainfo_report_handles_subprocess_failure(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", side_effect=RuntimeError("boom")),
    ):
        r = svc.build_mediainfo_report(str(f))
    assert r["available"] is False and "boom" in r["message"]


def test_build_mediainfo_report_rows_and_emu_mapping(tmp_path):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", return_value=_fake_mediainfo_json()),
    ):
        r = svc.build_mediainfo_report(str(f))
    assert r["available"] is True
    by_field = {row["field"]: row for row in r["rows"]}
    # Two Spanish+English E-AC-3 tracks → DUAL DD+ in the eMuwarez segment.
    assert r["audio_summary"] and r["audio_summary"].startswith("DUAL DD+")
    # Each row exposes both the raw MediaInfo value and the eMuwarez value.
    assert "Subtítulos" in by_field
    assert by_field["Subtítulos"]["emu"] == "SUBS"


def test_build_mediainfo_report_codec_row_shows_encoder_fingerprint_alongside_format(tmp_path):
    """Regression: the raw MediaInfo column used to show bare "AVC" next to
    an eMuwarez "x264" value with no visible connection between the two —
    confusing, since both are true at once (generic Format vs. the specific
    hand encoder that produced it). Real case: One Piece S23E01, Format=AVC,
    Writing_library="x264 core 164"."""
    f = tmp_path / "One Piece - S23E01 [1080p].mkv"
    f.write_text("fake")
    info = {"media": {"track": [
        {"@type": "General"},
        {"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080",
         "Writing_library": "x264 core 164",
         "Encoded_Library_Settings": "cabac=1 / ref=4 / rc=2pass / bitrate=8000"},
        {"@type": "Audio", "Format": "AAC", "Language": "ja"},
    ]}}
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", return_value=info),
    ):
        r = svc.build_mediainfo_report(str(f))
    by_field = {row["field"]: row for row in r["rows"]}
    assert by_field["Códec de vídeo"]["mediainfo"] == "AVC (x264)"
    assert by_field["Códec de vídeo"]["emu"] == "x264"


# ---------------------------------------------------------------------------
# One entry per real audio track, in track order
# ---------------------------------------------------------------------------

def _mediainfo_with_audio(tracks: list[dict]):
    return {"media": {"track": [
        {"@type": "General"},
        {"@type": "Video", "Format": "HEVC", "Width": "1920", "Height": "1080"},
        *[{"@type": "Audio", **t} for t in tracks],
        {"@type": "Text", "Language": "spa"},
    ]}}


def _summary(tmp_path, tracks):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", return_value=_mediainfo_with_audio(tracks)),
    ):
        return svc.build_mediainfo_report(str(f))["audio_summary"]


def _report(tmp_path, tracks):
    f = tmp_path / "movie.mkv"
    f.write_text("fake")
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", return_value=_mediainfo_with_audio(tracks)),
    ):
        return svc.build_mediainfo_report(str(f))


def test_repeated_language_keeps_only_its_best_codec(tmp_path):
    """Un idioma en varias pistas se queda con UNA: la de mejor códec. El
    nombre del release dice qué calidad ofrece, no cuántas pistas trae, así
    que las dos japonesas (TrueHD y DD) se resumen en la TrueHD.

    Antes salían las dos. Y antes de eso salían mal del todo: los idiomas se
    de-duplicaban pero los códecs no, y al juntar las listas por posición cada
    entrada tras un idioma repetido se llevaba el códec de otra pista."""
    summary = _summary(tmp_path, [
        # A real TrueHD track: MediaInfo reports the raw format as "MLP FBA"
        # and the commercial name separately, which is what audio_codec reads.
        {"Format": "MLP FBA", "Format_Commercial_IfAny": "Dolby TrueHD",
         "Language": "ja", "Channels": "6"},
        {"Format": "AC-3", "Language": "ja", "Channels": "6"},
        {"Format": "E-AC-3", "Language": "ca", "Channels": "2"},
        {"Format": "E-AC-3", "Language": "es", "Channels": "2"},
    ])
    # La japonesa se queda en TrueHD (mejor que DD); catalán y castellano
    # comparten códec Y canales, así que son UNA entrada.
    assert summary == "JAP TrueHD 5.1 ESP-CAT DD+ 2.0"


def test_languages_sharing_a_codec_join_with_a_hyphen(tmp_path):
    """Straight out of the guide: "…BDRemux AVC ESP-CAT TrueHD 5.1…". Listing
    them separately would claim two audio tracks where the release states one
    shared one."""
    summary = _summary(tmp_path, [
        {"Format": "MLP FBA", "Format_Commercial_IfAny": "Dolby TrueHD",
         "Language": "ca", "Channels": "6"},
        {"Format": "MLP FBA", "Format_Commercial_IfAny": "Dolby TrueHD",
         "Language": "es", "Channels": "6"},
    ])
    # Spanish leads regardless of track order, same as _split_languages sorts it.
    assert summary == "ESP-CAT TrueHD 5.1"


def test_same_language_different_channels_keeps_the_wider_one(tmp_path):
    """Mismo códec y distintos canales también se resume en una: 5.1 es lo que
    ofrece el release. Y el orden en que mkvmerge liste las pistas no decide
    nada, que es lo que pasaba cuando el desempate era "la primera"."""
    summary = _summary(tmp_path, [
        {"Format": "AC-3", "Language": "es", "Channels": "6"},
        {"Format": "AC-3", "Language": "es", "Channels": "2"},
    ])
    assert summary == "ESP DD 5.1"


def test_the_worse_track_is_dropped_whatever_order_it_comes_in(tmp_path):
    """La peor primero o la mejor primero, da igual: gana la mejor."""
    peor_primero = _summary(tmp_path, [
        {"Format": "AC-3", "Language": "ja", "Channels": "6"},
        {"Format": "MLP FBA", "Format_Commercial_IfAny": "Dolby TrueHD",
         "Language": "ja", "Channels": "6"},
    ])
    assert peor_primero == "JAP TrueHD 5.1"


def test_every_audio_track_still_shows_in_the_technical_card(tmp_path):
    """Lo que se recorta es el segmento del NOMBRE. La ficha técnica sigue
    enseñando las pistas reales del archivo, una por fila, porque ahí lo que
    interesa es qué hay dentro."""
    report = _report(tmp_path, [
        {"Format": "MLP FBA", "Format_Commercial_IfAny": "Dolby TrueHD",
         "Language": "ja", "Channels": "6"},
        {"Format": "AC-3", "Language": "ja", "Channels": "6"},
    ])
    import re as _re
    filas = [r for r in report["rows"] if _re.fullmatch(r"Audio \d+", str(r["field"]))]
    assert [f["emu"] for f in filas] == ["JAP TrueHD 5.1", "JAP DD 5.1"], filas
    # Y el segmento que va al nombre sí se queda con una sola.
    assert report["audio_summary"] == "JAP TrueHD 5.1"


def test_every_track_keeps_its_own_codec(tmp_path):
    summary = _summary(tmp_path, [
        {"Format": "DTS", "Language": "es", "Channels": "6"},
        {"Format": "AC-3", "Language": "en", "Channels": "2"},
    ])
    assert summary == "ESP DTS 5.1 ING DD 2.0"


def test_identical_tracks_are_not_listed_twice(tmp_path):
    """Same language AND codec AND channels twice adds nothing to the name."""
    summary = _summary(tmp_path, [
        {"Format": "AC-3", "Language": "es", "Channels": "6"},
        {"Format": "AC-3", "Language": "es", "Channels": "6"},
    ])
    assert summary == "ESP DD 5.1"


def test_dual_applies_per_entry_not_to_the_whole_file(tmp_path):
    """DUAL describes ONE audio entry, so a file whose tracks don't all share a
    codec still gets it on the entry that does."""
    summary = _summary(tmp_path, [
        {"Format": "DTS", "Language": "ja", "Channels": "6"},
        {"Format": "E-AC-3", "Language": "es", "Channels": "2"},
        {"Format": "E-AC-3", "Language": "en", "Channels": "2"},
    ])
    assert summary == "JAP DTS 5.1 DUAL DD+ 2.0"


def test_dual_shortcut_still_applies(tmp_path):
    """Spanish + English on the same codec/channels stays "DUAL", it doesn't
    become two spelled-out entries."""
    summary = _summary(tmp_path, [
        {"Format": "E-AC-3", "Language": "es", "Channels": "6"},
        {"Format": "E-AC-3", "Language": "en", "Channels": "6"},
    ])
    assert summary == "DUAL DD+ 5.1"


def test_multi_shortcut_still_applies(tmp_path):
    summary = _summary(tmp_path, [
        {"Format": "AC-3", "Language": lang, "Channels": "6"}
        for lang in ("es", "en", "fr", "de")
    ])
    assert summary == "MULTI DD 5.1"


def test_un_mediainfo_colgado_no_bloquea(tmp_path, monkeypatch):
    """Sin timeout, un montaje colgado dejaba la petición (o la cola) esperando."""
    import subprocess
    from emuwarez_uploadrr.services import media_probe

    def colgado(*a, **k):
        assert k.get("timeout"), "mediainfo se lanza sin timeout"
        raise subprocess.TimeoutExpired(a[0], k["timeout"])
    monkeypatch.setattr(media_probe.subprocess, "run", colgado)
    f = tmp_path / "peli.mkv"
    f.write_bytes(b"x")
    with patch.object(svc, "mediainfo_available", return_value=True):
        informe = svc.build_mediainfo_report(str(f))
    assert informe["available"] is False and "no respondió" in informe["message"]


def test_un_informe_con_la_herramienta_a_medias_no_se_guarda(tmp_path):
    """La ayuda dice "se repetirá la próxima vez": si el informe entero se
    quedaba en la caché, la herramienta no volvía a pasar."""
    f = tmp_path / "peli.mkv"
    f.write_bytes(b"x" * 100)
    info = {"media": {"track": [{"@type": "Video", "Format": "AVC", "Width": "1920", "Height": "1080"}]}}
    llamadas = []

    def _analiza(path, radarr_source=None):
        llamadas.append(path)
        return {"prediction": {"label": "WEB-DL"}, "partial": "muestreo al 40 %"}
    with (
        patch.object(svc, "mediainfo_available", return_value=True),
        patch.object(svc, "source_engine_enabled", return_value=True),
        patch.object(svc.media_probe, "run_mediainfo_json", return_value=info),
        patch("emuwarez_uploadrr.services.source_engine.analyze_for_app", side_effect=_analiza),
    ):
        primero = svc.build_mediainfo_report(str(f))
        svc.build_mediainfo_report(str(f))
    assert len(llamadas) == 2
    fila = next(r for r in primero["rows"] if r["field"] == "Source")
    assert "análisis parcial" in fila["help"]
