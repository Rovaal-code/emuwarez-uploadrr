"""Tests for filesystem_apply service."""
import pytest

from emuwarez_uploadrr.services.filesystem_apply import ensure_path_under_base


# ---------------------------------------------------------------------------
# ensure_path_under_base
# ---------------------------------------------------------------------------

def test_ensure_path_under_base_valid(tmp_path):
    child = tmp_path / "subdir" / "file.mkv"
    assert ensure_path_under_base(str(child), str(tmp_path)) is True


def test_ensure_path_under_base_traversal(tmp_path):
    other = tmp_path.parent / "other"
    assert ensure_path_under_base(str(other), str(tmp_path)) is False


def test_ensure_path_under_base_same_dir(tmp_path):
    # The base itself does not count as "under" itself
    assert ensure_path_under_base(str(tmp_path), str(tmp_path)) is True


def test_ensure_path_under_base_sibling(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    assert ensure_path_under_base(str(b), str(a)) is False


# --- La función que escribe no se fía del plan (hallazgo 3.5) --------------

@pytest.fixture
def subidas(tmp_path, monkeypatch):
    """tmp_path hace de carpeta de subidas: lo único que se puede renombrar."""
    from emuwarez_uploadrr.services import carpeta_subida
    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", str(tmp_path))
    return tmp_path


def test_applying_a_hand_made_plan_cannot_escape_the_source_folder(tmp_path, subidas):
    """apply_rename_plan recibía un diccionario y se fiaba de que `status`
    dijera "ready". Las comprobaciones las había hecho quien construyó el plan,
    antes. Hoy los dos únicos llamantes lo construyen justo encima, así que no
    era explotable, pero la barrera era la costumbre, no el código."""
    from emuwarez_uploadrr.services.filesystem_apply import apply_rename_plan

    origen = tmp_path / "serie" / "S01E01.mkv"
    origen.parent.mkdir(parents=True)
    origen.write_bytes(b"video")
    fuera = tmp_path / "otra_carpeta"
    fuera.mkdir()

    plan = {
        "status": "ready", "operation_type": "nomenclature_rename",
        "source_path": str(origen), "destination_path": str(fuera / "robado.mkv"),
        "errors": [], "warnings": [],
    }
    r = apply_rename_plan(plan, dry_run=False)

    assert r["status"] == "blocked"
    assert origen.exists(), "ha movido el archivo fuera de su carpeta"
    assert not (fuera / "robado.mkv").exists()


def test_a_traversal_in_the_destination_is_refused(tmp_path, subidas):
    from emuwarez_uploadrr.services.filesystem_apply import apply_rename_plan

    origen = tmp_path / "serie" / "S01E01.mkv"
    origen.parent.mkdir(parents=True)
    origen.write_bytes(b"video")

    plan = {
        "status": "ready", "operation_type": "nomenclature_rename",
        "source_path": str(origen),
        "destination_path": str(origen.parent / ".." / "fuera.mkv"),
        "errors": [], "warnings": [],
    }
    r = apply_rename_plan(plan, dry_run=False)
    assert r["status"] == "blocked"
    assert origen.exists()


# --- Solo se renombra en la carpeta de subidas --------------------------------

def test_un_archivo_de_la_biblioteca_no_se_renombra(tmp_path, monkeypatch):
    """Jellyfin lee la biblioteca con los nombres de Radarr/Sonarr."""
    from emuwarez_uploadrr.services import carpeta_subida
    from emuwarez_uploadrr.services.filesystem_apply import (SOLO_EN_SUBIDAS, apply_rename_plan,
                                                             build_safe_rename_plan)
    monkeypatch.setattr(carpeta_subida, "RAIZ_SUBIDAS", str(tmp_path / "uploads"))
    origen = tmp_path / "media" / "Peli (2020).mkv"
    origen.parent.mkdir(parents=True)
    origen.write_bytes(b"video")
    destino = str(origen.parent / "Peli.2020.1080p.mkv")

    plan = build_safe_rename_plan(str(origen), destino)
    assert plan["status"] == "blocked" and SOLO_EN_SUBIDAS in plan["errors"]
    r = apply_rename_plan({**plan, "status": "ready", "errors": []}, dry_run=False)
    assert r["status"] == "blocked"
    assert [p.name for p in origen.parent.iterdir()] == ["Peli (2020).mkv"]


def test_uno_de_la_carpeta_de_subidas_si(tmp_path, subidas):
    from emuwarez_uploadrr.services.filesystem_apply import apply_rename_plan, build_safe_rename_plan
    origen = tmp_path / "Peli (2020)" / "Peli (2020).mkv"
    origen.parent.mkdir()
    origen.write_bytes(b"video")
    destino = origen.parent / "Peli.2020.1080p.mkv"

    r = apply_rename_plan(build_safe_rename_plan(str(origen), str(destino)), dry_run=False)
    assert r["status"] == "applied"
    assert destino.read_bytes() == b"video" and not origen.exists()
