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
