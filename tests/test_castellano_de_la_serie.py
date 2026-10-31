"""La columna Español de una serie no cuenta los especiales cuando se ignoran."""
from __future__ import annotations

from emuwarez_uploadrr.services import library
from emuwarez_uploadrr.services.settings import set_setting

from tests import arr_falso

# Las fixtures de arr_falso (la autouse, solo para que actúe) se ven desde este módulo.
conn, _progreso_aparte = arr_falso.conn, arr_falso._progreso_aparte


# --- BIB-3: «Español» de la serie sin los especiales ---------------------------------------------------------

def _serie_con_especial(conn):
    def fila(**k):
        return conn.execute(f"INSERT INTO library_items ({','.join(k)}) VALUES ({','.join('?' * len(k))})",
                            list(k.values())).lastrowid

    serie = fila(item_type="series", title="S", local_status="Disponible", external_id="s")
    t1 = fila(item_type="season", title="S T1", local_status="Disponible", parent_id=serie, season_number=1,
              external_id="t1")
    t0 = fila(item_type="season", title="S T0", local_status="Disponible", parent_id=serie, season_number=0,
              external_id="t0")
    fila(item_type="episode", title="E1", local_status="Disponible", parent_id=t1, season_number=1,
         audio_languages="spa/eng", subtitle_languages="eng", external_id="e1")
    fila(item_type="episode", title="E0", local_status="Disponible", parent_id=t0, season_number=0,
         audio_languages="eng", subtitle_languages="eng", external_id="e0")
    conn.commit()
    return serie, t1, t0


def test_el_castellano_de_la_serie_no_cuenta_los_especiales_si_se_ignoran(conn):
    serie, t1, t0 = _serie_con_especial(conn)
    flag = lambda i: conn.execute("SELECT has_spanish_audio FROM library_items WHERE id = ?", (i,)).fetchone()[0]

    library.recompute_spanish_flags(conn)  # «ignorar especiales» es lo normal
    assert (flag(serie), flag(t1), flag(t0)) == (1, 1, 0)

    library.recompute_spanish_flags(conn, ignore_specials=False)
    assert (flag(serie), flag(t1), flag(t0)) == (0, 1, 0)

    set_setting(conn, "series.ignore_specials", "false")
    library.recompute_spanish_flags(conn)
    assert flag(serie) == 0
