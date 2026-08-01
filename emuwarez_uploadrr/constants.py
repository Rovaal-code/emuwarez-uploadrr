"""Constantes de la aplicación.

Este módulo **define** estas constantes; no las reexporta. Hasta el
2026-08-01 era un alias de `legacy.py`, que era donde vivían de verdad: se
invirtió la dependencia en vez de mover a los consumidores, porque así los
tres ficheros que ya importaban de aquí no se enteran del cambio y es
`legacy` quien pasa a depender de este módulo, no al revés.

No importa nada de la aplicación a propósito: es la hoja del árbol de
dependencias, y cualquier import que se le añada puede crear un ciclo.
"""
from __future__ import annotations

import re
from pathlib import Path


APP_NAME = "emuwarez-renamer"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
CONFIG_ENC_FILE = CONFIG_DIR / "config.enc.json"
LOG_DIR = CONFIG_DIR / "logs"


DEFAULT_TRACKER = "EMU"
DEFAULT_TAG = "EMUWAREZ"
DEFAULT_HARDLINK_BASE = "/mnt/storage/uploads/emu"
DEFAULT_WATCH_FOLDER = "~/test_torrents"
DEFAULT_IMAGE_HOST = "imgbox"
DEFAULT_IMG_HOSTS = ["imgbox", "ptpimg", "ptscreens", "onlyimage", "hamster", "imghost", "imgbb", "lensdump", "pixhost", "fastpic"]
IMAGE_API_HOSTS = ["imgbb", "ptpimg", "lensdump", "ptscreens", "onlyimage"]
IMAGE_HOST_LABELS = {
    "imgbb": "ImgBB",
    "ptpimg": "PTPIMG",
    "lensdump": "Lensdump",
    "ptscreens": "PTScreens",
    "onlyimage": "OnlyImage",
}

MIN_PYTHON = (3, 10)
RECOMMENDED_PYTHON = (3, 11)
PYTHON_CANDIDATES = ("python3.11", "python3.10", "python3.12", "python3.13", "python3")

TMDB_BASE = "https://api.themoviedb.org/3"
EMU_TEST_URL = "https://emuwarez.com/api/torrents/filter?perPage=1"

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".m2ts", ".ts"}

REQUIRED_SYSTEM_TOOLS = ("mediainfo", "mkvpropedit")
SYSTEM_TOOL_PACKAGES = {"mediainfo": "mediainfo", "mkvpropedit": "mkvtoolnix"}

# Imports que Uploadrr puede tener en rutas opcionales. No se instalan,
# no aparecen como pendientes, y no bloquean el flujo EMU normal.
OPTIONAL_UPLOADRR_IMPORTS = {"awsmfunc", "torrentman", "vapoursynth", "oxipng", "pyoxipng"}

# Paquetes problemáticos en algunas distros/arquitecturas. Se intentan con
# una estrategia especial, pero si fallan no bloquean si Uploadrr arranca.
PROBLEMATIC_REQUIREMENT_NAMES = {"pyrobase"}

# El script usa stdlib para que pueda arrancar antes de crear el venv.
# Si en el futuro se añade alguna dependencia propia, ponerla aquí.
SCRIPT_PIP_DEPS: list[str] = []

IMPORT_TO_PIP = {
    "yaml": "PyYAML",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "bs4": "beautifulsoup4",
    "dateutil": "python-dateutil",
    "dotenv": "python-dotenv",
    "Crypto": "pycryptodome",
    "lxml": "lxml",
}

LANG_MAP = {
    "es": "ESP", "spa": "ESP", "spanish": "ESP", "castilian": "ESP", "castellano": "ESP", "es-es": "ESP",
    "es-419": "LAT", "latino": "LAT", "latam": "LAT", "latin american spanish": "LAT",
    "en": "ING", "eng": "ING", "english": "ING",
    "ja": "JAP", "jpn": "JAP", "japanese": "JAP",
    "ko": "COR", "kor": "COR", "korean": "COR",
    "fr": "FRA", "fra": "FRA", "fre": "FRA", "french": "FRA",
    "de": "ALE", "deu": "ALE", "ger": "ALE", "german": "ALE",
    "it": "ITA", "ita": "ITA", "italian": "ITA",
    "pt": "POR", "por": "POR", "portuguese": "POR",
    "ca": "CAT", "cat": "CAT", "catalan": "CAT",
}

SOURCE_PATTERNS = [
    (re.compile(r"\b(?:bd[ ._-]?remux|bluray[ ._-]?remux)\b", re.I), "BDRemux"),
    # "Full BluRay" y no "FBD": es el código que usa la aplicación
    # (source_assistant.EMU_SOURCES). El motor de Source sí habla en FBD, pero
    # traduce al salir (source_engine/integration.ENGINE_TO_APP_SOURCE); esta
    # detección por nombre no traducía nada, así que un fichero con "bd50" en
    # el nombre acababa con un source que el tracker no acepta.
    (re.compile(r"\b(?:full[ ._-]?bd|bd50|bd25)\b", re.I), "Full BluRay"),
    (re.compile(r"\b(?:full[ ._-]?dvd|dvd9|dvd5)\b", re.I), "FDVD"),
    (re.compile(r"\b(?:web[ ._-]?dl|webdl)\b", re.I), "WEB-DL"),
    (re.compile(r"\b(?:web[ ._-]?rip|webrip)\b", re.I), "WEBRip"),
    (re.compile(r"\b(?:hdtv)\b", re.I), "HDTV"),
    (re.compile(r"\b(?:micro[ ._-]?hd|mhd)\b", re.I), "MHD"),
    (re.compile(r"\b(?:blu[ ._-]?ray|bdrip|brrip|bdr)\b", re.I), "BluRay"),
    (re.compile(r"\b(?:dvd[ ._-]?rip|dvdrip|dvd)\b", re.I), "SD"),
]

EPISODE_PATTERNS = [
    re.compile(r"(?i)\bS(?P<s>\d{1,2})[ ._-]*E(?P<e>\d{1,3})\b"),
    re.compile(r"(?i)\b(?P<s>\d{1,2})x(?P<e>\d{1,3})\b"),
    re.compile(r"(?i)\bSeason[ ._-]*(?P<s>\d{1,2}).*?Episode[ ._-]*(?P<e>\d{1,3})\b"),
    re.compile(r"(?i)\bTemporada[ ._-]*(?P<s>\d{1,2}).*?(?:Capitulo|Capítulo|Episodio)[ ._-]*(?P<e>\d{1,3})\b"),
]
SEASON_RE = re.compile(r"(?i)^(?:season|temporada)[ ._-]*(\d{1,2})$|^S(\d{1,2})$")
