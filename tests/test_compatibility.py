"""Tests for emuwarez_uploadrr/services/compatibility.py — Phase 5B."""
from __future__ import annotations

import pytest

from emuwarez_uploadrr.services.compatibility import (
    normalize_title,
    compact_title,
    parse_resolution,
    parse_source,
    compare_resolution,
    compare_source,
    match_request_to_library,
    classify_request_match,
    rank_request_matches,
    emu_override_status,
)


# ---------------------------------------------------------------------------
# emu_override_status
# ---------------------------------------------------------------------------

def test_emu_override_status_reclamado():
    assert emu_override_status("Reclamado") == "Reclamado"
    assert emu_override_status("reclamado") == "Reclamado"
    assert emu_override_status("claimed") == "Reclamado"


def test_emu_override_status_pendiente():
    assert emu_override_status("Pendiente") == "Pendiente"
    assert emu_override_status("pending") == "Pendiente"


def test_emu_override_status_llena():
    assert emu_override_status("Llena") == "Llena"
    assert emu_override_status("filled") == "Llena"
    assert emu_override_status("1") == "Llena"


def test_emu_override_status_open_beats_llena_substring():
    # "Sin llenar" contains "llena" as a substring — must not false-positive.
    assert emu_override_status("Sin llenar") is None
    assert emu_override_status("unfilled") is None
    assert emu_override_status("open") is None


def test_emu_override_status_none_for_empty_or_unknown():
    assert emu_override_status(None) is None
    assert emu_override_status("") is None
    assert emu_override_status("some other status") is None


# ---------------------------------------------------------------------------
# normalize_title
# ---------------------------------------------------------------------------

def test_normalize_title_basic():
    assert normalize_title("The Matrix") == "the matrix"


def test_normalize_title_accents():
    assert normalize_title("Café") == "cafe"


def test_normalize_title_spanish():
    assert normalize_title("El Señor de los Anillos") == "el senor de los anillos"


def test_normalize_title_punctuation():
    assert normalize_title("Spider-Man: No Way Home!") == "spider man no way home"


def test_normalize_title_none():
    assert normalize_title(None) == ""


def test_normalize_title_empty():
    assert normalize_title("") == ""


def test_normalize_title_collapses_whitespace():
    assert normalize_title("  lots   of   spaces  ") == "lots of spaces"


# ---------------------------------------------------------------------------
# compact_title
# ---------------------------------------------------------------------------

def test_compact_title_removes_the():
    assert compact_title("The Matrix") == "matrix"


def test_compact_title_removes_el():
    assert compact_title("El Señor") == "senor"


def test_compact_title_removes_whitespace():
    assert compact_title("Spider Man") == "spiderman"


def test_compact_title_no_article():
    assert compact_title("Interstellar") == "interstellar"


# ---------------------------------------------------------------------------
# parse_resolution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("1080p", 1080),
    ("720p", 720),
    ("4K", 2160),
    ("2160p", 2160),
    ("4k", 2160),
    ("480p", 480),
    ("UHD", 2160),
    (None, None),
    ("", None),
    ("SD", None),
    ("unknown", None),
])
def test_parse_resolution(value, expected):
    assert parse_resolution(value) == expected


# ---------------------------------------------------------------------------
# parse_source
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("BluRay", "bluray"),
    ("blu-ray", "bluray"),
    ("WEB-DL", "webdl"),
    ("WEBDL", "webdl"),
    ("WEBRip", "webrip"),
    ("HDTV", "hdtv"),
    ("BDRemux", "bdremux"),
    (None, None),
    ("", None),
    ("totally-unknown-src", None),
])
def test_parse_source(value, expected):
    assert parse_source(value) == expected


# ---------------------------------------------------------------------------
# compare_resolution
# ---------------------------------------------------------------------------

def test_compare_resolution_no_restriction():
    assert compare_resolution(None, "1080p") is None
    assert compare_resolution("any", "720p") is None
    assert compare_resolution("cualquiera", "1080p") is None


def test_compare_resolution_satisfies():
    assert compare_resolution("1080p", "1080p") is True
    assert compare_resolution("720p", "1080p") is True   # local >= requested


def test_compare_resolution_fails():
    assert compare_resolution("1080p", "720p") is False


def test_compare_resolution_unknown_local():
    assert compare_resolution("1080p", None) is False
    assert compare_resolution("1080p", "SD") is False


def test_compare_resolution_unknown_request():
    # Unrecognised request value → no restriction
    assert compare_resolution("fullhd", "1080p") is None


# ---------------------------------------------------------------------------
# compare_source
# ---------------------------------------------------------------------------

def test_compare_source_no_restriction():
    assert compare_source(None, "BluRay") is None
    assert compare_source("any", "WEB-DL") is None


def test_compare_source_satisfies():
    assert compare_source("WEB-DL", "BluRay") is True   # BluRay > WEB-DL
    assert compare_source("WEB-DL", "WEB-DL") is True   # equal


def test_compare_source_fails():
    assert compare_source("BluRay", "HDTV") is False


def test_compare_source_unknown_local():
    assert compare_source("BluRay", None) is False


# ---------------------------------------------------------------------------
# match_request_to_library
# ---------------------------------------------------------------------------

def _make_req(**kwargs):
    defaults = {"id": 1, "title": "Test Movie", "tmdb_id": None, "imdb_id": None,
                "requested_resolution": None, "requested_source": None, "emu_status": None}
    defaults.update(kwargs)
    return defaults


def _make_item(**kwargs):
    defaults = {"id": 10, "title": "Test Movie", "tmdb_id": None, "imdb_id": None,
                "resolution": None, "source": None, "local_status": "Disponible",
                "nomenclature_status": "N/A"}
    defaults.update(kwargs)
    return defaults


def test_match_by_tmdb():
    req = _make_req(tmdb_id="12345")
    library = [_make_item(tmdb_id="12345")]
    results = match_request_to_library(req, library)
    assert len(results) == 1
    assert results[0]["id_match"] is True
    assert results[0]["confidence"] == 1.0


def test_match_by_imdb():
    req = _make_req(imdb_id="tt0000001")
    library = [_make_item(imdb_id="tt0000001")]
    results = match_request_to_library(req, library)
    assert len(results) == 1
    assert results[0]["id_match"] is True
    assert results[0]["confidence"] >= 0.9


def test_match_by_exact_title():
    req = _make_req(title="Interstellar")
    library = [_make_item(title="Interstellar")]
    results = match_request_to_library(req, library)
    assert len(results) == 1
    assert results[0]["title_match"] is True


def test_match_by_title_accents():
    req = _make_req(title="El Señor de los Anillos")
    library = [_make_item(title="El senor de los anillos")]
    results = match_request_to_library(req, library)
    assert len(results) == 1
    assert results[0]["title_match"] is True


def test_no_match():
    req = _make_req(title="Completely Different Film")
    library = [_make_item(title="Some Other Movie")]
    results = match_request_to_library(req, library)
    assert len(results) == 0


def test_tmdb_beats_title():
    req = _make_req(tmdb_id="111", title="Generic Title")
    library = [
        _make_item(id=10, tmdb_id="111", title="Different Name"),
        _make_item(id=20, tmdb_id=None, title="Generic Title"),
    ]
    results = match_request_to_library(req, library)
    # TMDb match should have higher confidence
    assert results[0]["item"]["id"] == 10
    assert results[0]["id_match"] is True


# ---------------------------------------------------------------------------
# classify_request_match
# ---------------------------------------------------------------------------

def test_classify_compatible():
    req = _make_req(requested_resolution="1080p", requested_source="WEB-DL")
    item = _make_item(resolution="1080p", source="BluRay")
    result = classify_request_match(req, item, id_match=True)
    assert result["status"] == "Compatible"
    assert result["confidence"] > 0


def test_classify_parcial_resolution_fail():
    req = _make_req(requested_resolution="1080p", requested_source="WEB-DL")
    item = _make_item(resolution="720p", source="WEB-DL")
    result = classify_request_match(req, item, title_match=True)
    assert result["status"] == "Parcial"


def test_classify_not_compatible():
    req = _make_req(requested_resolution="4K", requested_source="BluRay")
    item = _make_item(resolution="720p", source="HDTV")
    result = classify_request_match(req, item)
    assert result["status"] == "No compatible"


def test_classify_filled():
    req = _make_req(emu_status="filled")
    item = _make_item()
    result = classify_request_match(req, item)
    assert result["status"] == "Llena"


@pytest.mark.parametrize("emu_status,expected", [
    ("Lleno", "Llena"),          # real eMuwarez value
    ("Reclamado", "Reclamado"),
    ("Pendiente", "Pendiente"),
])
def test_classify_real_emu_states(emu_status, expected):
    req = _make_req(emu_status=emu_status, requested_resolution="1080p")
    item = _make_item(resolution="1080p", local_status="Disponible")
    assert classify_request_match(req, item, id_match=True)["status"] == expected


def test_sin_llenar_is_open_not_filled():
    """'Sin llenar' (abierta) must NOT be read as 'Llena' just because the word
    'llenar' contains the substring 'llena'."""
    req = _make_req(emu_status="Sin llenar", requested_resolution="1080p")
    item = _make_item(resolution="1080p", local_status="Disponible")
    assert classify_request_match(req, item, id_match=True)["status"] == "Compatible"


def test_classify_no_restriction():
    req = _make_req(requested_resolution=None, requested_source=None)
    item = _make_item(resolution="720p", source="HDTV")
    result = classify_request_match(req, item, id_match=True)
    assert result["status"] == "Compatible"
    assert result["resolution_match"] is None
    assert result["source_match"] is None


def test_classify_reasons_included():
    req = _make_req(requested_resolution="1080p", requested_source="BluRay")
    item = _make_item(resolution="1080p", source="BluRay")
    result = classify_request_match(req, item, id_match=True)
    assert len(result["reasons"]) > 0
    assert any("ID" in r for r in result["reasons"])


# ---------------------------------------------------------------------------
# rank_request_matches
# ---------------------------------------------------------------------------

def test_rank_puts_compatible_first():
    matches = [
        {"compatibility_status": "Parcial", "compatibility_confidence": 0.6, "library_item": {"local_status": "Disponible", "nomenclature_status": "N/A"}},
        {"compatibility_status": "Compatible", "compatibility_confidence": 0.9, "library_item": {"local_status": "Disponible", "nomenclature_status": "Correcta"}},
        {"compatibility_status": "No compatible", "compatibility_confidence": 0.3, "library_item": {"local_status": "Faltante", "nomenclature_status": "N/A"}},
    ]
    ranked = rank_request_matches(matches)
    assert ranked[0]["compatibility_status"] == "Compatible"
    assert ranked[-1]["compatibility_status"] == "No compatible"


def test_rank_compatible_available_correct_nomenclature_first():
    matches = [
        {
            "compatibility_status": "Compatible",
            "compatibility_confidence": 0.9,
            "library_item": {"local_status": "Disponible", "nomenclature_status": "No adaptada"},
        },
        {
            "compatibility_status": "Compatible",
            "compatibility_confidence": 0.9,
            "library_item": {"local_status": "Disponible", "nomenclature_status": "Correcta"},
        },
    ]
    ranked = rank_request_matches(matches)
    assert ranked[0]["library_item"]["nomenclature_status"] == "Correcta"


def test_rank_local_status_parcial_ranks_between_available_and_missing():
    """A Parcial (series/season rollup) local candidate must rank worse
    than a fully Disponible one but better than an unlisted/Faltante one
    isn't guaranteed by this ranking alone — this just documents Parcial
    has its own explicit rank entry instead of an unexplained gap."""
    matches = [
        {"compatibility_status": "Compatible", "compatibility_confidence": 0.9,
         "library_item": {"local_status": "Parcial", "nomenclature_status": "N/A"}},
        {"compatibility_status": "Compatible", "compatibility_confidence": 0.9,
         "library_item": {"local_status": "Disponible", "nomenclature_status": "N/A"}},
    ]
    ranked = rank_request_matches(matches)
    assert ranked[0]["library_item"]["local_status"] == "Disponible"
    assert ranked[1]["library_item"]["local_status"] == "Parcial"


def test_rank_empty():
    assert rank_request_matches([]) == []


def test_not_available_match_is_no_disponible():
    """A spec-compatible match whose file is Faltante becomes 'No disponible',
    not 'Compatible' — so it doesn't pollute the Compatible filter."""
    req = {"tmdb_id": "1", "title": "X", "requested_resolution": "1080p",
           "requested_source": "Any", "emu_status": "open"}
    available = {"tmdb_id": "1", "title": "X", "resolution": "1080p", "source": "WEB-DL",
                 "local_status": "Disponible"}
    missing = {**available, "local_status": "Faltante"}
    assert classify_request_match(req, available, id_match=True)["status"] == "Compatible"
    assert classify_request_match(req, missing, id_match=True)["status"] == "No disponible"


def test_availability_only_downgrades_compatible():
    """The availability override only turns a would-be 'Compatible' into 'No
    disponible' — a spec mismatch keeps its own status (not overridden)."""
    req = {"tmdb_id": "1", "title": "X", "requested_resolution": "2160p",
           "requested_source": "Any", "emu_status": "open"}
    missing = {"tmdb_id": "1", "title": "X", "resolution": "720p", "source": "WEB-DL",
               "local_status": "Faltante"}
    status = classify_request_match(req, missing, id_match=True)["status"]
    assert status != "No disponible" and status != "Compatible"  # a real mismatch
