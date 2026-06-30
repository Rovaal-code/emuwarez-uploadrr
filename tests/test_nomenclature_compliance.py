"""Compliance tests for EMU nomenclature formula (Phase 10A)."""
from __future__ import annotations

import pytest


def test_emu_sources_list():
    from emuwarez_uploadrr.services.source_assistant import list_emu_sources, EMU_SOURCES
    sources = list_emu_sources()
    assert len(sources) == len(EMU_SOURCES)
    codes = [s["code"] for s in sources]
    assert "WEB-DL" in codes
    assert "BluRay" in codes


def test_provider_sources_only_webdl():
    from emuwarez_uploadrr.services.source_assistant import PROVIDER_SOURCES
    assert PROVIDER_SOURCES == frozenset({"WEB-DL"})


def test_build_source_string_webdl_with_provider():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    result = _build_source_string("WEB-DL", "AMZN")
    assert result == "AMZN WEB-DL"


def test_build_source_string_webdl_without_provider():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    result = _build_source_string("WEB-DL", None)
    assert result == "WEB-DL"


def test_build_source_string_blueray_ignores_provider():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    result = _build_source_string("BluRay", "AMZN")
    assert result == "BluRay"


def test_build_source_string_bdremu_ignores_provider():
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    result = _build_source_string("BDRemux", "NF")
    assert result == "BDRemux"


@pytest.mark.parametrize("source", ["Full BluRay", "BDRemux", "BluRay", "MHD", "WEBRip", "HDTV"])
def test_non_webdl_sources_ignore_provider(source):
    from emuwarez_uploadrr.services.source_assistant import _build_source_string
    result = _build_source_string(source, "AMZN")
    assert result == source


def test_internal_mkv_title_spaces_to_dots():
    from emuwarez_uploadrr.services.source_assistant import _build_internal_mkv_title_from_name
    title = _build_internal_mkv_title_from_name("Titulo Pelicula 2024 1080p WEB-DL AMZN - EMUWAREZ")
    assert " " not in title
    assert "." in title
    assert title == "Titulo.Pelicula.2024.1080p.WEB-DL.AMZN.-.EMUWAREZ"


def test_emu_providers_list():
    from emuwarez_uploadrr.services.source_assistant import list_emu_providers
    providers = list_emu_providers()
    codes = [p["code"] for p in providers]
    assert "AMZN" in codes
    assert "NF" in codes
    assert "DSNP" in codes
    assert "MAX" in codes
    assert "ATVP" in codes


def test_tmdb_provider_map_normalization():
    from emuwarez_uploadrr.services.source_assistant import map_tmdb_provider_to_emu_provider
    assert map_tmdb_provider_to_emu_provider("Netflix") == "NF"
    assert map_tmdb_provider_to_emu_provider("amazon prime video") == "AMZN"
    assert map_tmdb_provider_to_emu_provider("Disney+") == "DSNP"
    assert map_tmdb_provider_to_emu_provider("unknown service xyz") is None


def test_mkv_title_token():
    from emuwarez_uploadrr.services.mkv_title import MKV_CONFIRMATION_TOKEN
    assert MKV_CONFIRMATION_TOKEN == "APLICAR_TITULO_MKV"


def test_build_internal_mkv_title():
    from emuwarez_uploadrr.services.mkv_title import build_internal_mkv_title
    result = build_internal_mkv_title("El Titulo 2024 1080p BluRay - EMUWAREZ")
    assert " " not in result
    assert result == "El.Titulo.2024.1080p.BluRay.-.EMUWAREZ"
