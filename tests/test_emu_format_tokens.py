"""Los tokens del nombre de eMuwarez (services/emu_format.py) a partir de lo que
reportan MediaInfo y Radarr/Sonarr."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.emu_format import (
    format_audio_codec,
    format_channels,
    format_hdr,
    format_video_codec,
)


@pytest.mark.parametrize("codec, pista, token", [
    ("x264", "", "x264"),
    ("", "Peli.2020.1080p.x265-GRP", "x265"),
    ("AV1", "", "AV1"),
    ("VP9", "", "VP9"),
    ("H.266", "", "VVC"),
    ("HEVC", "", "HEVC"),
    ("h265", "", "HEVC"),
    ("MPEG-4 AVC", "", "AVC"),
    ("H.264", "", "AVC"),
    ("VC-1", "", "VC-1"),
    ("MPEG-2 Video", "", "MPEG"),
    ("Theora", "", "Theora"),
    (None, "", None),
])
def test_codec_de_video(codec, pista, token):
    assert format_video_codec(codec, pista) == token


@pytest.mark.parametrize("rango, token", [
    ("Dolby Vision, HDR10", "DV HDR"),
    ("Dolby Vision", "DV"),
    ("DV", "DV"),
    ("HDR10+", "HDR"),
    ("HLG", "HDR"),
    ("SMPTE ST 2084 (PQ)", "HDR"),
    ("SDR", None),
    ("", None),
])
def test_hdr(rango, token):
    assert format_hdr(rango) == token


@pytest.mark.parametrize("codec, token", [
    ("TrueHD Atmos", "TrueHD Atmos"),
    ("MLP FBA", "MLP"),
    ("DTS-HD MA", "DTS-HD MA"),
    ("DTS-HD Master Audio", "DTS-HD MA"),
    ("DTS-HD High Resolution Audio", "DTS-HD HRA"),
    ("DTS:X", "DTS:X"),
    ("DTS", "DTS"),
    ("E-AC-3", "DD+"),
    ("Dolby Digital Plus Atmos", "DD+ Atmos"),
    ("AC-3", "DD"),
    ("Dolby Digital", "DD"),
    ("AAC LC", "AAC LC"),
    ("AAC HE", "AAC HE"),
    ("AAC", "AAC"),
    ("Opus", "OPUS"),
    ("FLAC", "FLAC"),
    ("ALAC", "ALAC"),
    ("MP3", "MP3"),
    ("PCM", "PCM"),
    ("Speex", "Speex"),
    (None, None),
])
def test_codec_de_audio(codec, token):
    assert format_audio_codec(codec) == token


@pytest.mark.parametrize("canales, token", [
    ("5.1", "5.1"),
    (6, "5.1"),
    ("8 channels", "7.1"),
    (2, "2.0"),
    ("sin número", None),
    ("", None),
    (None, None),
])
def test_canales(canales, token):
    assert format_channels(canales) == token


@pytest.mark.parametrize("pista", [{"Channel_s_": "10"}, {"Channel_s_": "Object Based"}, {}])
def test_unos_canales_desconocidos_no_se_inventan(pista):
    """Antes salía "2.0" en el nombre (y "10.0" en el menú de pistas)."""
    from emuwarez_uploadrr.services.media_probe import audio_channels
    assert audio_channels(pista) is None


def test_el_menu_de_pistas_usa_los_mismos_canales():
    from emuwarez_uploadrr.services.mkv_remux import build_track_plan
    plan = build_track_plan({"tracks": [
        {"id": 0, "type": "video", "codec": "AVC", "properties": {}},
        {"id": 1, "type": "audio", "codec": "TrueHD", "properties": {"language": "eng", "audio_channels": 10}},
        {"id": 2, "type": "audio", "codec": "AC-3", "properties": {"language": "spa", "audio_channels": 6}},
    ]})
    nombres = [t["new_name"] for t in plan["ordered_tracks"] if t["type"] == "audio"]
    assert nombres == ["Español (Castellano) - DD 5.1", "Inglés - TrueHD"]


_MA = {"Format": "DTS", "Format_Commercial_IfAny": "DTS-HD Master Audio", "Format_AdditionalFeatures": "XLL"}


@pytest.mark.parametrize("pista,token", [
    (_MA, "DTS-HD MA"),
    ({**_MA, "Format_AdditionalFeatures": "XLL X"}, "DTS:X"),
    ({"Format": "DTS", "Format_Commercial_IfAny": "DTS-HD High Resolution Audio",
      "Format_AdditionalFeatures": "XBR"}, "DTS-HD HRA"),
    ({"Format": "DTS", "Format_AdditionalFeatures": "XCH"}, "DTS"),
    ({"Format": "MPEG Audio", "Format_Profile": "Layer 3"}, "MP3"),
    ({"Format": "Vorbis"}, "Vorbis"),
])
def test_el_codec_de_mediainfo(pista, token):
    """El DTS:X salía como DTS-HD MA: los dos llevan "DTS-HD Master Audio" y
    solo los extras ("XLL X") los distinguen."""
    from emuwarez_uploadrr.services.media_probe import audio_codec
    assert audio_codec(pista) == token


def test_el_motor_de_source_no_confunde_ma_con_dts_x():
    from emuwarez_uploadrr.services.source_engine.profile import build_audio_tracks
    ma = {"@type": "Audio", **_MA, "Compression_Mode": "Lossless / Lossy"}
    x = {**ma, "Format_AdditionalFeatures": "XLL X"}
    pistas = build_audio_tracks({"media": {"track": [ma, x]}}, None, None)
    assert [(p["dts_x"], p["lossless"]) for p in pistas] == [(False, True), (True, True)]


def test_el_mp2_no_es_mp3():
    """MPEG Audio Layer 2 (DVD, HDTV) salía MP3 en el nombre."""
    from emuwarez_uploadrr.services.media_probe import audio_codec
    assert audio_codec({"Format": "MPEG Audio", "Format_Profile": "Layer 2"}) == "MP2"


def test_und_de_radarr_no_entra_en_el_nombre():
    """Sin MediaInfo, un "und" de Radarr/Sonarr tampoco se escribe en el nombre."""
    from emuwarez_uploadrr.services.emu_format import build_audio_string
    assert build_audio_string("AC3", "spa / und", 6) == "ESP DD 5.1"
