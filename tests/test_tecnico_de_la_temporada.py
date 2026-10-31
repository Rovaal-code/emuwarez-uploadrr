"""Un capítulo faltante no vacía lo técnico (códec, audio, subtítulos...) de su temporada ni de su serie."""
from __future__ import annotations

from emuwarez_uploadrr.services import library

from tests import arr_falso

# Las fixtures de arr_falso (la autouse, solo para que actúe) se ven desde este módulo.
conn, _progreso_aparte = arr_falso.conn, arr_falso._progreso_aparte


# --- BIB-4: un capítulo faltante no vacía lo técnico de la temporada ------------------------------------------

def test_un_capitulo_faltante_no_borra_el_audio_ni_el_codec_de_la_temporada(conn):
    def fila(**k):
        return conn.execute(f"INSERT INTO library_items ({','.join(k)}) VALUES ({','.join('?' * len(k))})",
                            list(k.values())).lastrowid

    serie = fila(item_type="series", title="S", local_status="Parcial", external_id="s")
    temp = fila(item_type="season", title="S T1", local_status="Parcial", parent_id=serie, season_number=1,
                external_id="t1")
    for n in (1, 2):
        fila(item_type="episode", title=f"E{n}", local_status="Disponible", parent_id=temp, season_number=1,
             external_id=f"e{n}", path=f"/tv/S/Season 1/S0T1E{n}.1080p.AMZN.WEB-DL.mkv", resolution="1080p", source="WEB-DL",
             video_codec="x265", audio_codec="AC3", audio_languages="spa", subtitle_languages="spa")
    fila(item_type="episode", title="E3", local_status="Faltante", parent_id=temp, season_number=1, external_id="e3")
    conn.commit()

    for ficha, lista in (
        (library._child_quality_rollup(conn, temp, "season"), library._batch_rollups(conn, [], [temp], True)[temp]),
        (library._child_quality_rollup(conn, serie, "series"), library._batch_rollups(conn, [serie], [], True)[serie]),
    ):
        assert ficha == lista["quality"]
        assert ficha["audio_languages"] == "spa" and ficha["video_codec"] == "x265"
        assert ficha["resolution"] == "1080p" and ficha["provider"] == "AMZN"
