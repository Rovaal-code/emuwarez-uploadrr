"""Tests for filesystem_apply service."""
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

def test_applying_a_hand_made_plan_cannot_escape_the_source_folder(tmp_path):
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


def test_a_traversal_in_the_destination_is_refused(tmp_path):
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
