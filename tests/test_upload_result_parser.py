"""Tests for upload_result_parser — pure functions, no DB."""
import pytest
from emuwarez_uploadrr.services.upload_result_parser import (
    build_error_summary,
    classify_upload_result,
    extract_torrent_url,
    season_pack_warning,
    torrent_id_from_url,
)

# La salida real de Uploadrr-EMU al subir (src/trackers/UNIT3D.py): la ficha del torrent va en una línea fija.
SALIDA_SUBIDA = """\
Searching for existing torrents on EMU...
No dupes found
[pixhost] https://t.pixhost.to/thumbs/1/captura.jpg
TMDb: https://www.themoviedb.org/movie/550
Torrent URL: https://emu-warez.com/torrents/123456
Torrent uploaded successfully!
Added to: /data/uploads/Peli
"""

# Con cualquier fallo, Uploadrr-EMU acaba con el resumen y la despedida.
PIE_DE_FALLO = """\
╭───────────────────────── Upload Summary ─────────────────────────╮
│ Processed 1 Unique Uploads                                       │
│ Successful Uploads: 0                                            │
│ Failed Uploads: 1                                                │
╰──────────────────────────────────────────────────────────────────╯
                         see you soon ^.<
"""


def _panel(titulo: str) -> str:
    return (
        f"╭──────────────────── {titulo} ────────────────────╮\n"
        "│ Path: /data/uploads/                             │\n"
        "│ • Peli.2020.1080p.mkv                            │\n"
        "╰──────────────────────────────────────────────────╯\n"
    )


def test_extract_torrent_url_reads_the_fixed_line():
    assert extract_torrent_url(SALIDA_SUBIDA) == "https://emu-warez.com/torrents/123456"


def test_extract_torrent_url_ignores_other_urls():
    """Antes valía la primera URL de la salida: la de una imagen o la de TMDb."""
    texto = "[pixhost] https://t.pixhost.to/a.jpg\nTMDb: https://www.themoviedb.org/movie/1"
    assert extract_torrent_url(texto) is None


def test_extract_torrent_url_needs_the_whole_line():
    assert extract_torrent_url("Visto en Torrent URL: https://emu-warez.com/torrents/1") is None
    assert extract_torrent_url("") is None


def test_torrent_id_comes_from_the_url():
    assert torrent_id_from_url("https://emu-warez.com/torrents/123456") == "123456"
    assert torrent_id_from_url("https://emu-warez.com/otra/ruta") is None
    assert torrent_id_from_url(None) is None


def test_classify_exit_0_is_completed():
    result = classify_upload_result("OK", "", 0)
    assert result["status"] == "completed"
    assert result["error_summary"] is None
    assert result["exit_code"] == 0
    assert result["result_url"] is None
    assert result["torrent_id"] is None


def test_classify_exit_1_is_failed():
    result = classify_upload_result("", "Error: connection refused", 1)
    assert result["status"] == "failed"
    assert result["exit_code"] == 1


def test_classify_takes_the_torrent_url_and_its_id():
    result = classify_upload_result(SALIDA_SUBIDA, "", 0)
    assert result["status"] == "completed"
    assert result["result_url"] == "https://emu-warez.com/torrents/123456"
    assert result["torrent_id"] == "123456"


def test_classify_does_not_take_a_torrent_id_from_loose_text():
    """Un `id: 12345` suelto (el id de TMDb con el modo debug) no es el torrent."""
    result = classify_upload_result("tmdb id: 54321\ntorrent_id: 77777\n", "", 0)
    assert result["torrent_id"] is None


def test_classify_exit_none_is_failed():
    result = classify_upload_result("", "", None)
    assert result["status"] == "failed"


def test_build_error_summary_from_stderr():
    stderr = "line1\nline2\nERROR: authentication failed\n"
    summary = build_error_summary(stderr, "", 1)
    assert "authentication failed" in summary
    assert "Exit code: 1" in summary


def test_build_error_summary_empty():
    summary = build_error_summary("", "", 0)
    # exit_code 0 → no "Exit code" appended, and no lines → None
    assert summary is None


def test_build_error_summary_fallback_stdout():
    # No stderr but stdout has content
    summary = build_error_summary("", "last line from stdout", 1)
    assert "last line from stdout" in summary


def test_error_summary_is_the_reason_not_the_closing_banner():
    """Las dos últimas líneas de la salida eran el marco del último panel y «see you soon»."""
    stdout = (
        "Searching for existing torrents on EMU...\n"
        "Exact size match. Aborting..\n"
        + _panel("Potential duplicate on EMU")
        + _panel("Pre-upload checks failed")
        + PIE_DE_FALLO
    )
    assert build_error_summary("", stdout, 1) == "Potential duplicate on EMU\nExit code: 1"


def test_error_summary_of_a_tracker_rejection_keeps_message_and_details():
    stdout = (
        "Uploading to EMU\n"
        "Upload failed: The name has already been taken.\n"
        "Error details: {'name': ['The name has already been taken.']}\n"
        + _panel("EMU Rejected Upload")
        + PIE_DE_FALLO
    )
    lineas = build_error_summary("", stdout, 1).splitlines()
    assert lineas[0] == "Upload failed: The name has already been taken."
    assert lineas[1].startswith("Error details:")
    assert lineas[2] == "EMU Rejected Upload"
    assert "see you soon" not in "\n".join(lineas)


def test_error_summary_of_a_missing_tmdb_id():
    stdout = _panel("TMDb ID not found") + PIE_DE_FALLO
    assert build_error_summary("", stdout, 1) == "TMDb ID not found\nExit code: 1"


def test_error_summary_reads_log_handler_errors_without_level_or_path():
    stdout = (
        "ERROR    Forbidden (403): la cuenta no tiene permiso de subida                UNIT3D.py:384\n"
        + PIE_DE_FALLO
    )
    assert build_error_summary("", stdout, 1) == "Forbidden (403): la cuenta no tiene permiso de subida\nExit code: 1"


def test_error_summary_ignores_an_old_error_when_a_verdict_exists():
    """El fallo de un host de imágenes, ya superado, no es el motivo de un duplicado."""
    stdout = (
        "ERROR    [pixhost] Upload failed: timeout                                  pixhost.py:47\n"
        + _panel("Potential duplicate on EMU")
        + PIE_DE_FALLO
    )
    assert build_error_summary("", stdout, 1) == "Potential duplicate on EMU\nExit code: 1"


def test_error_summary_without_markers_skips_banner_and_summary():
    """Sin ninguna marca, las últimas líneas que no sean decoración."""
    stdout = "Algo inesperado ha pasado\n" + PIE_DE_FALLO
    assert build_error_summary("", stdout, 2) == "Algo inesperado ha pasado\nExit code: 2"


def test_api_token_in_output_not_in_result():
    """Caller must redact before passing, but parser itself must not leak."""
    # Simulate already-redacted output arriving at classifier
    stdout = "api_token=***REDACTED*** Subida OK\nTorrent URL: https://emu.me/torrents/1"
    result = classify_upload_result(stdout, "", 0)
    # The real token is not in the output — redaction happened upstream
    assert "***REDACTED***" not in str(result.get("error_summary") or "")


# ---------------------------------------------------------------------------
# Pack de temporada incompleto (aviso de mkbrr que imprime Uploadrr-EMU)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("linea", "aviso"),
    [
        (
            "Incomplete season pack: season 1, missing episodes 3, 5, 7",
            "Pack de temporada posiblemente incompleto (temporada 1): faltan los episodios 3, 5 y 7.",
        ),
        (
            "Incomplete season pack: season 2, missing episodes 4",
            "Pack de temporada posiblemente incompleto (temporada 2): falta el episodio 4.",
        ),
        ("Incomplete season pack: season 1", "Pack de temporada posiblemente incompleto (temporada 1)."),
    ],
)
def test_season_pack_warning(linea, aviso):
    assert season_pack_warning(f"Hashing with mkbrr: 100.0%\n{linea}\nUploading to EMU") == aviso


def test_season_pack_warning_none_without_line():
    assert season_pack_warning("Hashing with mkbrr: 100.0%\nUploading to EMU") is None


def test_classify_includes_season_pack_warning():
    result = classify_upload_result("Incomplete season pack: season 1, missing episodes 2", "", 0)
    assert result["season_pack_warning"] == "Pack de temporada posiblemente incompleto (temporada 1): falta el episodio 2."
    assert classify_upload_result("ok", "", 0)["season_pack_warning"] is None
