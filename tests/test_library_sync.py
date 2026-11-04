"""Tests for library sync (Phase 4).

All HTTP calls are mocked — no real Radarr/Sonarr required.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from emuwarez_uploadrr.database import connect, init_db
from emuwarez_uploadrr.models import LocalStatus



















# ---------------------------------------------------------------------------
# Library sync — mocked HTTP
# ---------------------------------------------------------------------------

def _fake_movie(movie_id: int, title: str, has_file: bool = True) -> dict:
    result = {"id": movie_id, "title": title, "year": 2020, "tmdbId": movie_id + 10000}
    if has_file:
        result["movieFile"] = {
            "id": movie_id * 10, "path": f"/movies/{title}.mkv", "size": 1000000,
            "quality": {"quality": {"name": "WEB-DL-1080p"}},
        }
    return result


def _fake_series(series_id: int, title: str, has_episodes: bool = True) -> dict:
    return {
        "id": series_id, "title": title, "year": 2021, "tvdbId": series_id + 20000,
        "titleSlug": title.lower().replace(" ", "-"),
        "statistics": {
            "episodeCount": 10,
            "episodeFileCount": 10 if has_episodes else 0,
        },
        "path": f"/tv/{title}",
    }


def _fake_episode(ep_id: int, series_id: int, has_file: bool = True) -> dict:
    return {
        "id": ep_id, "seriesId": series_id,
        "seasonNumber": 1, "episodeNumber": ep_id,
        "title": f"Episode {ep_id}",
        "hasFile": has_file,
        "episodeFileId": ep_id * 10 if has_file else 0,
    }


def _fake_ep_file(ep_id: int) -> dict:
    return {
        "id": ep_id * 10,
        "path": f"/tv/Series/S01E{ep_id:02d}.mkv",
        "size": 500000,
        "quality": {"quality": {"name": "WEBRip-720p"}},
    }


@pytest.fixture
def mem_conn():
    """In-memory SQLite with schema initialized."""
    conn = connect(":memory:")
    init_db(conn)
    # Add a test instance
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES (?, ?, ?, ?, 1)",
        ("radarr", "Test Radarr", "http://radarr:7878", "key123"),
    )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def sonarr_conn():
    conn = connect(":memory:")
    init_db(conn)
    conn.execute(
        "INSERT INTO instances (type, name, url, api_key, enabled) VALUES (?, ?, ?, ?, 1)",
        ("sonarr", "Test Sonarr", "http://sonarr:8989", "key456"),
    )
    conn.commit()
    yield conn
    conn.close()


def test_sync_radarr_available_movie(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [_fake_movie(1, "Inception", has_file=True)]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        imported, missing = sync_instance(mem_conn, instance)

    assert imported == 1
    assert missing == 0
    rows = mem_conn.execute("SELECT * FROM library_items").fetchall()
    assert len(rows) == 1
    assert rows[0]["local_status"] == LocalStatus.AVAILABLE.value
    assert rows[0]["resolution"] == "1080p"
    assert rows[0]["source"] == "WEB-DL"


def test_sync_radarr_missing_movie(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [_fake_movie(2, "Missing Film", has_file=False)]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        imported, missing = sync_instance(mem_conn, instance)

    assert imported == 1
    assert missing == 1
    row = mem_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["local_status"] == LocalStatus.MISSING.value


def test_sync_radarr_queued_movie(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [_fake_movie(3, "Downloading Film", has_file=False)]
    queue = [{"movieId": 3, "status": "downloading", "statusMessages": []}]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=queue),
    ):
        imported, missing = sync_instance(mem_conn, instance)

    row = mem_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["local_status"] == LocalStatus.DOWNLOADING.value
    assert missing == 1  # still counts as not available


def test_sync_radarr_upsert_updates(mem_conn):
    """Running sync twice should update the item, not create a duplicate."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movie = [_fake_movie(4, "Cached Film", has_file=False)]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movie),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    movie2 = [_fake_movie(4, "Cached Film", has_file=True)]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movie2),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    rows = mem_conn.execute("SELECT * FROM library_items").fetchall()
    assert len(rows) == 1
    assert rows[0]["local_status"] == LocalStatus.AVAILABLE.value


# ---------------------------------------------------------------------------
# content_missing_new notification (status transition, not date-based)
# ---------------------------------------------------------------------------

def test_first_sync_missing_movie_does_not_notify(mem_conn):
    """Instance's very first sync — a bulk backfill, not a fresh request —
    must never fire content_missing_new even though the movie is Faltante."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [_fake_movie(50, "Brand New Instance Film", has_file=False)]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    assert list_notifications(mem_conn) == []


def test_incremental_sync_new_missing_movie_notifies(mem_conn):
    """A movie added to Radarr AFTER the instance already has other rows —
    the real 'just requested it, not found' scenario — must notify."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    # Seed the instance with one existing, available movie so it's no longer
    # a first sync.
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(60, "Existing Film", has_file=True)]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)
    assert list_notifications(mem_conn) == []

    # Now a brand-new movie shows up, already missing.
    movies = [_fake_movie(60, "Existing Film", has_file=True), _fake_movie(61, "Just Requested Film", has_file=False)]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    notes = list_notifications(mem_conn)
    assert len(notes) == 1
    assert notes[0]["event_type"] == "content_missing_new"
    assert "Just Requested Film" in notes[0]["content_title"]


def test_new_missing_notification_explains_when_not_released_yet(mem_conn):
    """A movie added to Radarr while still "inCinemas" (not released in a
    downloadable form) can't actually be requested on eMuwarez yet — same
    gate get_dashboard_recommendations' "Faltante" group already applies.
    The notification must say so instead of unconditionally suggesting
    "you may want to create a request"."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(90, "Seed Film", has_file=True)]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    in_cinemas_movie = _fake_movie(91, "Still In Cinemas", has_file=False)
    in_cinemas_movie["status"] = "inCinemas"
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies",
              return_value=[_fake_movie(90, "Seed Film", has_file=True), in_cinemas_movie]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    notes = list_notifications(mem_conn)
    note = next(n for n in notes if "Still In Cinemas" in n["content_title"])
    assert "estrenado" in note["body"].lower()
    assert "petición" not in note["body"].lower()


def test_new_missing_notification_suggests_request_when_released(mem_conn):
    """The default wording (suggesting a request) still applies once Radarr
    marks the movie 'released' — this must not regress."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(92, "Seed Film 2", has_file=True)]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    released_movie = _fake_movie(93, "Released Missing Film", has_file=False)
    released_movie["status"] = "released"
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies",
              return_value=[_fake_movie(92, "Seed Film 2", has_file=True), released_movie]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    notes = list_notifications(mem_conn)
    note = next(n for n in notes if "Released Missing Film" in n["content_title"])
    assert "petición" in note["body"].lower()


def test_resyncing_already_missing_movie_does_not_renotify(mem_conn):
    """Syncing again while a movie is STILL Faltante (no status change) must
    not fire a second notification."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(70, "Seed Film", has_file=True)]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    movies = [_fake_movie(70, "Seed Film", has_file=True), _fake_movie(71, "Still Missing Film", has_file=False)]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)
    assert len(list_notifications(mem_conn)) == 1

    # Re-sync with the exact same data — still Faltante, no transition.
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)
    assert len(list_notifications(mem_conn)) == 1


def test_movie_becoming_available_does_not_notify(mem_conn):
    """The reverse transition (Faltante -> Disponible) is not what this event
    is for — must never fire content_missing_new."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(80, "Seed Film", has_file=True)]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(80, "Seed Film", has_file=True), _fake_movie(81, "Now Missing", has_file=False)]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)
    assert len(list_notifications(mem_conn)) == 1

    # It gets downloaded — status flips back to Disponible.
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(80, "Seed Film", has_file=True), _fake_movie(81, "Now Missing", has_file=True)]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)
    assert len(list_notifications(mem_conn)) == 1  # unchanged


def test_incremental_sync_new_missing_movie_notification_includes_poster(mem_conn):
    """The notification should carry the movie's own poster_url through, for
    the UI thumbnail / Discord-Telegram full-size image."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(90, "Seed Film", has_file=True)]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    movie_with_poster = _fake_movie(91, "Poster Film", has_file=False)
    movie_with_poster["images"] = [{"coverType": "poster", "remoteUrl": "https://image.tmdb.org/t/p/original/poster.jpg"}]
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[_fake_movie(90, "Seed Film", has_file=True), movie_with_poster]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    notes = list_notifications(mem_conn)
    assert len(notes) == 1
    assert notes[0]["poster_url"] == "https://image.tmdb.org/t/p/original/poster.jpg"


def test_sync_sonarr_available_series(sonarr_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series = [_fake_series(10, "Peaky Blinders", has_episodes=True)]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=series),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
    ):
        imported, missing = sync_instance(sonarr_conn, instance, include_episodes=False)

    assert imported == 1
    assert missing == 0
    row = sonarr_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["local_status"] == LocalStatus.AVAILABLE.value
    assert row["item_type"] == "series"
    assert row["title_slug"] == "peaky-blinders"


def test_sync_sonarr_missing_series(sonarr_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series = [_fake_series(11, "Missing Show", has_episodes=False)]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=series),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
    ):
        imported, missing = sync_instance(sonarr_conn, instance, include_episodes=False)

    assert missing == 1
    row = sonarr_conn.execute("SELECT * FROM library_items").fetchone()
    assert row["local_status"] == LocalStatus.MISSING.value


def test_sync_sonarr_with_episodes(sonarr_conn):
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series_data = [_fake_series(20, "Miniseries", has_episodes=False)]
    episodes = [_fake_episode(1, 20, has_file=True), _fake_episode(2, 20, has_file=False)]
    ep_files = [_fake_ep_file(1)]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=series_data),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=episodes),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=ep_files),
    ):
        imported, missing = sync_instance(sonarr_conn, instance, include_episodes=True)

    # 1 series + 1 season (materialized bottom-up from the episodes, since
    # this fixture's series has no "seasons" array) + 2 episodes
    assert imported == 4
    rows = sonarr_conn.execute("SELECT id, item_type, local_status, parent_id FROM library_items ORDER BY id").fetchall()
    types = [r["item_type"] for r in rows]
    assert "series" in types
    assert "season" in types
    assert "episode" in types
    series_row = next(r for r in rows if r["item_type"] == "series")
    season_row = next(r for r in rows if r["item_type"] == "season")
    episode_rows = [r for r in rows if r["item_type"] == "episode"]
    assert season_row["parent_id"] == series_row["id"]
    for ep in episode_rows:
        assert ep["parent_id"] == season_row["id"]


def test_sync_sonarr_creates_season_rows_from_seasons_array(sonarr_conn):
    """When Sonarr's own series["seasons"] carries per-season statistics,
    trust them directly instead of the bottom-up fallback."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series_data = _fake_series(21, "Full Statistics Show", has_episodes=True)
    series_data["seasons"] = [
        {"seasonNumber": 1, "statistics": {"episodeCount": 2, "episodeFileCount": 2}},
    ]
    episodes = [_fake_episode(1, 21, has_file=True), _fake_episode(2, 21, has_file=True)]
    ep_files = [_fake_ep_file(1), _fake_ep_file(2)]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=[series_data]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=episodes),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=ep_files),
    ):
        imported, missing = sync_instance(sonarr_conn, instance, include_episodes=True)

    assert imported == 4  # 1 series + 1 season + 2 episodes
    season_row = sonarr_conn.execute(
        "SELECT * FROM library_items WHERE item_type = 'season'"
    ).fetchone()
    assert season_row["local_status"] == LocalStatus.AVAILABLE.value
    assert season_row["season_number"] == 1
    for row in sonarr_conn.execute("SELECT * FROM library_items WHERE item_type = 'episode'").fetchall():
        assert row["season_number"] == 1
        assert row["episode_number"] in (1, 2)


def test_sync_sonarr_partial_series_and_season(sonarr_conn):
    """A series/season with some but not all episode files must be Parcial,
    not squeezed into the old binary Disponible/Faltante rollup."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series_data = _fake_series(22, "Partial Show", has_episodes=True)
    series_data["statistics"] = {"episodeCount": 2, "episodeFileCount": 1}
    episodes = [_fake_episode(1, 22, has_file=True), _fake_episode(2, 22, has_file=False)]
    ep_files = [_fake_ep_file(1)]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=[series_data]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=episodes),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=ep_files),
    ):
        imported, missing = sync_instance(sonarr_conn, instance, include_episodes=True)

    series_row = sonarr_conn.execute(
        "SELECT * FROM library_items WHERE item_type = 'series'"
    ).fetchone()
    season_row = sonarr_conn.execute(
        "SELECT * FROM library_items WHERE item_type = 'season'"
    ).fetchone()
    assert series_row["local_status"] == LocalStatus.PARTIAL.value
    assert season_row["local_status"] == LocalStatus.PARTIAL.value
    # Parcial must NOT inflate the "missing" sync summary tally — it's
    # available in part, not "not yet available". Only the one truly
    # missing episode counts here.
    assert missing == 1


def test_sync_sonarr_season_rollup_set_when_episodes_agree(sonarr_conn):
    """The season row's own resolution/source/codec/audio/subs must be
    filled in when every available episode shares the same value — this
    never happened at all before (season_to_library_item unconditionally
    left these None), so the wizard's "Información técnica"/consistency
    checks always saw a blank field regardless of real agreement."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series_data = _fake_series(30, "Rollup Show", has_episodes=False)
    episodes = [_fake_episode(1, 30, has_file=True), _fake_episode(2, 30, has_file=True)]
    media_info = {"videoCodec": "x264", "audioCodec": "AAC", "audioLanguages": "jpn", "subtitles": "spa"}
    ep_files = [
        {"id": 10, "path": "/tv/S/S01E01.mkv", "size": 500, "quality": {"quality": {"name": "WEBRip-1080p"}}, "mediaInfo": media_info},
        {"id": 20, "path": "/tv/S/S01E02.mkv", "size": 700, "quality": {"quality": {"name": "WEBRip-1080p"}}, "mediaInfo": media_info},
    ]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=[series_data]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=episodes),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=ep_files),
    ):
        sync_instance(sonarr_conn, instance, include_episodes=True)

    season_row = sonarr_conn.execute("SELECT * FROM library_items WHERE item_type = 'season'").fetchone()
    assert season_row["resolution"] == "1080p"
    assert season_row["source"] == "WEBRip"
    assert season_row["video_codec"] == "x264"
    assert season_row["audio_codec"] == "AAC"
    assert season_row["audio_languages"] == "jpn"
    assert season_row["subtitle_languages"] == "spa"
    # Tamaño is a SUM, not an agreement rollup — episodes are naturally
    # different sizes, that's not a "disagreement" to hide.
    assert season_row["size_bytes"] == 1200


def test_sync_sonarr_season_rollup_none_when_episodes_disagree(sonarr_conn):
    """Real case that motivated this: episodes agree on codec/audio but NOT
    on subtitles (one has SUBS, the other doesn't) — the season row's
    subtitle_languages must stay None (not silently pick one episode's
    value), while the fields that DO agree still roll up normally."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series_data = _fake_series(31, "Disagreement Show", has_episodes=False)
    episodes = [_fake_episode(1, 31, has_file=True), _fake_episode(2, 31, has_file=True)]
    # _fake_episode(ep_id, ...) hardcodes episodeFileId = ep_id * 10 — the
    # fake file "id" here must match that exactly or files_by_id.get(...)
    # silently misses and the episode looks like it has no file at all.
    ep_files = [
        {"id": 10, "path": "/tv/D/S01E01.mkv", "size": 1, "quality": {"quality": {"name": "HDTV-1080p"}},
         "mediaInfo": {"videoCodec": "x264", "audioCodec": "AAC", "audioLanguages": "jpn", "subtitles": "spa"}},
        {"id": 20, "path": "/tv/D/S01E02.mkv", "size": 1, "quality": {"quality": {"name": "HDTV-1080p"}},
         "mediaInfo": {"videoCodec": "x264", "audioCodec": "AAC", "audioLanguages": "jpn", "subtitles": None}},
    ]

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=[series_data]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=episodes),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=ep_files),
    ):
        sync_instance(sonarr_conn, instance, include_episodes=True)

    season_row = sonarr_conn.execute("SELECT * FROM library_items WHERE item_type = 'season'").fetchone()
    assert season_row["video_codec"] == "x264"
    assert season_row["subtitle_languages"] is None


def test_sync_sonarr_progress_total_counts_seasons(sonarr_conn):
    """on_total() must count every level _bump()/on_progress() fires for —
    series + seasons + episodes — or the live "done" counter runs past
    "total" partway through a real sync (seasons were missing from the
    total entirely before, since series["seasons"] is on the series
    response Sonarr already returns, not a separate per-season fetch)."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    series_data = _fake_series(40, "Two Season Show", has_episodes=True)
    series_data["seasons"] = [
        {"seasonNumber": 1, "statistics": {"episodeCount": 2, "episodeFileCount": 2}},
        {"seasonNumber": 2, "statistics": {"episodeCount": 1, "episodeFileCount": 1}},
    ]
    series_data["statistics"]["totalEpisodeCount"] = 3
    episodes = [
        {**_fake_episode(1, 40, has_file=True), "seasonNumber": 1},
        {**_fake_episode(2, 40, has_file=True), "seasonNumber": 1},
        {**_fake_episode(3, 40, has_file=True), "seasonNumber": 2},
    ]
    ep_files = [_fake_ep_file(1), _fake_ep_file(2), _fake_ep_file(3)]

    totals: list[int] = []
    done_values: list[int] = []

    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=[series_data]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=episodes),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=ep_files),
    ):
        imported, _missing = sync_instance(
            sonarr_conn, instance, include_episodes=True,
            on_total=totals.append, on_progress=done_values.append,
        )

    # 1 series + 2 seasons + 3 episodes.
    assert imported == 6
    assert totals == [6]
    assert max(done_values) <= totals[0]


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

def test_dashboard_summary_empty(mem_conn):
    from emuwarez_uploadrr.services.library import get_dashboard_summary
    summary = get_dashboard_summary(mem_conn)
    assert summary["library_total"] == 0
    assert summary["available"] == 0
    assert summary["missing"] == 0
    assert summary["last_sync_at"] is None


def test_dashboard_summary_after_sync(mem_conn):
    from emuwarez_uploadrr.services.library import sync_instance, get_dashboard_summary
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movies = [
        _fake_movie(10, "Available Film", has_file=True),
        _fake_movie(11, "Missing Film", has_file=False),
    ]

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=movies),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)

    summary = get_dashboard_summary(mem_conn)
    assert summary["library_total"] == 2
    assert summary["available"] == 1
    assert summary["missing"] == 1
    assert summary["radarr_items"] == 2


# ---------------------------------------------------------------------------
# sync_all() recomputing emu_in_catalog for newly-synced items (Recomendaciones
# Group 2/3 need it resolved to exactly 0/1, not NULL, right after a plain
# library sync — otherwise a new item stays invisible there until someone
# happens to also run a full eMuwarez catalog sync).
# ---------------------------------------------------------------------------

def test_sync_all_recomputes_emu_status_for_new_movie(mem_conn):
    from emuwarez_uploadrr.database import set_state
    from emuwarez_uploadrr.services.emu_catalog import SYNC_COMPLETED_STATE_KEY
    from emuwarez_uploadrr.services.library import sync_all

    movie = _fake_movie(20, "Missing Film", has_file=False)
    mem_conn.execute(
        "INSERT INTO emu_catalog (torrent_id, name, tmdb_id, category) VALUES (?,?,?,?)",
        ("1", "Some Other Film 2019", str(movie["tmdbId"]), "Películas"),
    )
    set_state(mem_conn, SYNC_COMPLETED_STATE_KEY, "2024-01-01T00:00:00+00:00")
    mem_conn.commit()

    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[movie]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_all(mem_conn, include_episodes=False)

    row = mem_conn.execute(
        "SELECT emu_in_catalog FROM library_items WHERE title = ?", ("Missing Film",)
    ).fetchone()
    assert row["emu_in_catalog"] == 1


def test_sync_all_leaves_emu_status_null_before_any_emu_sync(mem_conn):
    """No eMuwarez catalog sync has ever completed — recompute must no-op
    instead of confidently marking everything "not on eMuwarez" against an
    empty catalog table."""
    from emuwarez_uploadrr.services.library import sync_all

    movie = _fake_movie(21, "Another Missing Film", has_file=False)
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[movie]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_all(mem_conn, include_episodes=False)

    row = mem_conn.execute(
        "SELECT emu_in_catalog FROM library_items WHERE title = ?", ("Another Missing Film",)
    ).fetchone()
    assert row["emu_in_catalog"] is None


def test_upsert_sets_missing_since_only_on_transition_into_faltante(mem_conn):
    """missing_since must be stamped the moment an item first becomes
    Faltante, kept unchanged while it stays Faltante across resyncs (so an
    old missing item never looks freshly-missing just because it was
    resynced), and left alone on a resync that doesn't change status."""
    from emuwarez_uploadrr.services.library import sync_instance
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(mem_conn)[0]

    movie = _fake_movie(30, "Becomes Missing", has_file=True)
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[movie]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)
    row = mem_conn.execute(
        "SELECT missing_since FROM library_items WHERE title = ?", ("Becomes Missing",)
    ).fetchone()
    assert row["missing_since"] is None  # available — never missing yet

    missing_movie = _fake_movie(30, "Becomes Missing", has_file=False)
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[missing_movie]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)
    row = mem_conn.execute(
        "SELECT missing_since FROM library_items WHERE title = ?", ("Becomes Missing",)
    ).fetchone()
    first_missing_since = row["missing_since"]
    assert first_missing_since is not None

    # Resyncing while still missing must not bump missing_since.
    with (
        patch("emuwarez_uploadrr.integrations.radarr.get_movies", return_value=[missing_movie]),
        patch("emuwarez_uploadrr.integrations.radarr.get_queue", return_value=[]),
    ):
        sync_instance(mem_conn, instance)
    row = mem_conn.execute(
        "SELECT missing_since FROM library_items WHERE title = ?", ("Becomes Missing",)
    ).fetchone()
    assert row["missing_since"] == first_missing_since


def test_faltante_group_orders_by_missing_since_not_arr_added(mem_conn):
    """Recomendaciones' "Faltante" group must rank by when an item actually
    became missing (missing_since), not by Radarr/Sonarr's own "added" date
    (when it was added to Radarr/Sonarr) — an item added recently for an
    unrelated reason (e.g. a fresh request) shouldn't outrank one that
    genuinely became missing more recently but was added long ago."""
    import json
    from emuwarez_uploadrr.services.library import get_dashboard_recommendations

    old_add_new_missing = json.dumps({"monitored": True, "status": "released", "added": "2020-01-01T00:00:00Z"})
    new_add_old_missing = json.dumps({"monitored": True, "status": "released", "added": "2026-01-01T00:00:00Z"})
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, tmdb_id, emu_in_catalog, missing_since, raw_json) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Recently Missing", "movie", "Faltante", "101", 0, "2026-07-26T12:00:00+00:00", old_add_new_missing),
    )
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, tmdb_id, emu_in_catalog, missing_since, raw_json) "
        "VALUES (?,?,?,?,?,?,?)",
        ("Old Missing Recently Added", "movie", "Faltante", "102", 0, None, new_add_old_missing),
    )
    mem_conn.commit()

    recs = get_dashboard_recommendations(mem_conn)
    faltante_titles = [r["title"] for r in recs if r["rec_group"] == 3]
    assert faltante_titles == ["Recently Missing", "Old Missing Recently Added"]


def test_unique_content_excludes_season_with_inconsistent_episodes(mem_conn):
    """Group 2 ("Contenido único") must not recommend a season whose own
    rollup fields aren't all filled in — that only happens when every
    episode agrees (_update_season_rollup) — since build_season_pack_plan
    would block the actual upload anyway. Genuinely unique, but not
    actually uploadable, so it shouldn't be recommended as if it were.

    Subtitles are NOT one of those fields any more: they may differ between
    episodes as long as all of them carry Castilian, so the disqualifying
    signal for them is has_spanish_subs, not subtitle_languages being NULL."""
    from emuwarez_uploadrr.services.library import get_dashboard_recommendations

    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog) "
        "VALUES ('Ready Show', 'series', 'Disponible', 1)"
    )
    series_id = mem_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    # Consistent season: every rollup field filled in, Castilian subs — appears.
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Ready Show - Temporada 1', 'season', 'Disponible', 0, ?, "
        "'1080p', 'WEB-DL', 'x264', 'AAC', 'jpn', 'spa', 1, 1)",
        (series_id,),
    )
    # Episodios con RESOLUCIONES distintas (rollup NULL): eso sí sigue
    # bloqueando el pack, así que no debe recomendarse.
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Ready Show - Temporada 2', 'season', 'Disponible', 0, ?, "
        "NULL, 'WEB-DL', 'x264', 'AAC', 'jpn', 'spa', 1, 1)",
        (series_id,),
    )
    # Códec de vídeo distinto entre capítulos: ya NO bloquea, se queda fuera
    # del nombre del pack y la temporada se recomienda igual.
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Ready Show - Temporada 5', 'season', 'Disponible', 0, ?, "
        "'1080p', 'WEB-DL', NULL, 'AAC', 'jpn', 'spa', 1, 1)",
        (series_id,),
    )
    # Subtitle tracks differ across episodes (rollup NULL) but every one has
    # Castilian — the pack IS uploadable now, so this one must appear.
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Ready Show - Temporada 3', 'season', 'Disponible', 0, ?, "
        "'1080p', 'WEB-DL', 'x264', 'AAC', 'jpn', NULL, 1, 1)",
        (series_id,),
    )
    # Same, but an episode has no Castilian subs at all — still blocked.
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Ready Show - Temporada 4', 'season', 'Disponible', 0, ?, "
        "'1080p', 'WEB-DL', 'x264', 'AAC', 'jpn', 'eng', 0, 0)",
        (series_id,),
    )
    mem_conn.commit()

    recs = get_dashboard_recommendations(mem_conn)
    unique_titles = [r["title"] for r in recs if r["rec_group"] == 2]
    assert "Ready Show - Temporada 1" in unique_titles
    assert "Ready Show - Temporada 2" not in unique_titles
    assert "Ready Show - Temporada 3" in unique_titles
    assert "Ready Show - Temporada 4" not in unique_titles


def test_unique_content_lists_seasons_not_whole_series(mem_conn):
    """Regression: Group 2 previously collapsed an entire series into ONE
    row when every season of it was also unique (emu_in_catalog=0) — but
    eMuwarez uploads happen per season pack, never "a series" as a single
    unit, and each season can have its own readiness independent of its
    siblings. Even when the whole series is unique, each of its seasons
    must still show up as its own row — never a combined "series" row."""
    from emuwarez_uploadrr.services.library import get_dashboard_recommendations

    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog) "
        "VALUES ('Whole Show', 'series', 'Disponible', 0)"
    )
    series_id = mem_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for n in (1, 2):
        mem_conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
            "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
            "has_spanish_subs, has_spanish_ok) "
            f"VALUES ('Whole Show - Temporada {n}', 'season', 'Disponible', 0, ?, "
            "'1080p', 'WEB-DL', 'x264', 'AAC', 'jpn', 'spa', 1, 1)",
            (series_id,),
        )
    mem_conn.commit()

    recs = get_dashboard_recommendations(mem_conn)
    unique_titles = [r["title"] for r in recs if r["rec_group"] == 2]
    assert "Whole Show" not in unique_titles
    assert "Whole Show - Temporada 1" in unique_titles
    assert "Whole Show - Temporada 2" in unique_titles


def _peticion_compatible(conn, titulo: str, *, puntos, creada: str, preparacion, has_spanish_ok,
                         alcance: str | None = None, temporada: int | None = None) -> int:
    """Una petición de eMuwarez cuya mejor coincidencia es Compatible con su propia fila de la biblioteca (una
    película, o una serie con su temporada si `alcance` es 'season'), con la recompensa, la fecha y la preparación
    guardada que se pidan. `has_spanish_ok` va en la fila que pide la petición, como la lee request_readiness."""
    if alcance == "season":
        conn.execute("INSERT INTO library_items (title, item_type, local_status, emu_in_catalog) "
                     "VALUES (?, 'series', 'Disponible', 0)", (titulo,))
        lib_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
                     "season_number, has_spanish_ok) VALUES (?, 'season', 'Disponible', 0, ?, ?, ?)",
                     (f"{titulo} - Temporada {temporada}", lib_id, temporada, has_spanish_ok))
    else:
        conn.execute("INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, has_spanish_ok) "
                     "VALUES (?, 'movie', 'Disponible', 0, ?)", (titulo, has_spanish_ok))
        lib_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO request_items (emu_id, title, points, created_at, readiness_status, req_scope, req_season) "
                 "VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (f"rec-{titulo}", titulo, puntos, creada, preparacion, alcance, temporada))
    req_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute("INSERT INTO request_matches (library_item_id, request_item_id, status, confidence) "
                 "VALUES (?, ?, 'Compatible', 1.0)", (lib_id, req_id))
    return req_id


def test_peticiones_compatibles_por_recompensa_y_sin_las_de_sin_castellano(mem_conn):
    """Recomendaciones, grupo 1: la petición que más paga primero (points de mayor a menor), las que no dicen
    recompensa al final y, a igual recompensa, la más nueva delante; la recompensa sale en cada fila (rec_points).
    Sin las que su copia no tiene castellano (la preparación guardada es no_castellano: eMuwarez la rechazaría);
    una que aún no se ha evaluado (readiness NULL) o cuyo castellano no se ha leído se queda. Los grupos 2 y 3 siguen
    detrás, en su orden de siempre (lo más nuevo primero), aunque sean más nuevos que las peticiones."""
    import json
    from emuwarez_uploadrr.services.library import get_dashboard_recommendations

    ids = {
        "Sin puntos": _peticion_compatible(mem_conn, "Sin puntos", puntos=None, creada="2026-10-05",
                                           preparacion="ready_to_upload", has_spanish_ok=1),
        "Poca": _peticion_compatible(mem_conn, "Poca", puntos=100, creada="2026-10-04",
                                     preparacion="needs_nomenclature", has_spanish_ok=1),
        "Mucha vieja": _peticion_compatible(mem_conn, "Mucha vieja", puntos=5000, creada="2026-10-01",
                                            preparacion="preflight_needed", has_spanish_ok=1),
        "Mucha nueva": _peticion_compatible(mem_conn, "Mucha nueva", puntos=5000, creada="2026-10-03",
                                            preparacion="ready_to_upload", has_spanish_ok=1),
        # Sin evaluar todavía y sin castellano leído: no se sabe, así que se queda.
        "Sin evaluar": _peticion_compatible(mem_conn, "Sin evaluar", puntos=800, creada="2026-10-02",
                                            preparacion=None, has_spanish_ok=None),
        # La temporada pedida, con su castellano y su recompensa.
        "Serie": _peticion_compatible(mem_conn, "Serie", puntos=3000, creada="2026-10-02",
                                      preparacion="ready_to_upload", has_spanish_ok=1, alcance="season", temporada=2),
    }
    # La que más paga, pero sin castellano: fuera, sea película o temporada.
    _peticion_compatible(mem_conn, "Rica sin castellano", puntos=99999, creada="2026-10-06",
                         preparacion="no_castellano", has_spanish_ok=0)
    _peticion_compatible(mem_conn, "Serie sin castellano", puntos=88888, creada="2026-10-06",
                         preparacion="no_castellano", has_spanish_ok=0, alcance="season", temporada=1)
    # Grupo 2 (único, con castellano) y grupo 3 (faltante), más nuevos que cualquier petición.
    mem_conn.execute("INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, has_spanish_ok, "
                     "raw_json) VALUES ('Unica', 'movie', 'Disponible', 0, 1, ?)",
                     (json.dumps({"added": "2027-01-01T00:00:00Z"}),))
    mem_conn.execute("INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, raw_json) "
                     "VALUES ('Falta', 'movie', 'Faltante', 0, ?)",
                     (json.dumps({"monitored": True, "status": "released", "added": "2027-01-02T00:00:00Z"}),))
    mem_conn.commit()

    recs = get_dashboard_recommendations(mem_conn)
    orden = ["Mucha nueva", "Mucha vieja", "Serie", "Sin evaluar", "Poca", "Sin puntos"]
    assert [(r["rec_group"], r["rec_request_id"], r["rec_points"]) for r in recs] == [
        (1, ids["Mucha nueva"], 5000), (1, ids["Mucha vieja"], 5000), (1, ids["Serie"], 3000),
        (1, ids["Sin evaluar"], 800), (1, ids["Poca"], 100), (1, ids["Sin puntos"], None),
        (2, None, None), (3, None, None),
    ]
    assert [r["title"] for r in recs] == orden + ["Unica", "Falta"]
    # La temporada pedida sigue con su nombre y su tipo.
    serie = recs[orden.index("Serie")]
    assert serie["item_type"] == "season" and serie["season_number"] == 2
    assert serie["content_name"].endswith("Temporada 2")

    # El tope corta por el final: lo primero son siempre las peticiones que más pagan.
    assert [r["title"] for r in get_dashboard_recommendations(mem_conn, limit=3)] == orden[:3]


def test_dashboard_summary_unique_seasons_excludes_inconsistent(mem_conn):
    """Regression: the Panel's "Contenido único" stat card counted a season
    as soon as it was local_status=Disponible and emu_in_catalog=0, with no
    check that its episodes actually agree on resolution/source/codecs/
    audio, and carry Castilian subtitles — the same requirement
    Recomendaciones' Group 2 and build_season_pack_plan already enforce. A
    season whose episodes disagree is genuinely unique but can't actually be
    uploaded as a pack, so it shouldn't inflate this count.

    Subtitles count by content, not by agreement: differing subtitle tracks
    no longer disqualify a season, a missing Castilian one does."""
    from emuwarez_uploadrr.services.library import get_dashboard_summary

    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog) "
        "VALUES ('Show', 'series', 'Disponible', 0)"
    )
    series_id = mem_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    # Consistent season with 2 episodes — must count (season + both episodes).
    # Its subtitle tracks differ across episodes (rollup NULL) but all have
    # Castilian, which is exactly the case that must NOT disqualify it.
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Show - Temporada 1', 'season', 'Disponible', 0, ?, "
        "'1080p', 'WEB-DL', 'x264', 'AAC', 'jpn', NULL, 1, 1)",
        (series_id,),
    )
    season1_id = mem_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for n in (1, 2):
        mem_conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, episode_number) "
            f"VALUES ('Show S01E0{n}', 'episode', 'Disponible', 0, ?, {n})",
            (season1_id,),
        )
    # Capítulos con RESOLUCIONES distintas (rollup NULL): sigue sin poder
    # subirse como pack, así que ni ella ni sus capítulos cuentan. El códec de
    # vídeo, en cambio, ya no descalifica a nadie.
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Show - Temporada 2', 'season', 'Disponible', 0, ?, "
        "NULL, 'WEB-DL', 'x264', 'AAC', 'jpn', 'spa', 1, 1)",
        (series_id,),
    )
    season2_id = mem_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, episode_number) "
        "VALUES ('Show S02E01', 'episode', 'Disponible', 0, ?, 1)",
        (season2_id,),
    )
    mem_conn.commit()

    # And a third one where an episode simply has no Castilian subtitles.
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Show - Temporada 3', 'season', 'Disponible', 0, ?, "
        "'1080p', 'WEB-DL', 'x264', 'AAC', 'jpn', 'eng', 0, 0)",
        (series_id,),
    )
    season3_id = mem_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, episode_number) "
        "VALUES ('Show S03E01', 'episode', 'Disponible', 0, ?, 1)",
        (season3_id,),
    )
    mem_conn.commit()

    summary = get_dashboard_summary(mem_conn)
    assert summary["unique_seasons"] == 1
    assert summary["unique_episodes"] == 2


def test_missing_since_backfilled_from_added_at_on_migration(mem_conn):
    """Content that was already Faltante before missing_since existed must
    not be stuck at NULL forever (falling back to Radarr/Sonarr's own
    "added" date) — the one-time migration backfill uses added_at (when we
    first synced this row) as its best available proxy."""
    from emuwarez_uploadrr.database import init_db

    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, added_at) VALUES (?,?,?,?)",
        ("Old Missing Movie", "movie", "Faltante", "2023-05-01T00:00:00"),
    )
    mem_conn.commit()
    # Simulate "before this migration ever ran": drop the column and force
    # init_db to redo the whole migration cascade (see
    # test_instances_unique_name_migration.py's _seed_old_schema_with_conflict
    # for the same DELETE-schema_version trick).
    mem_conn.execute("ALTER TABLE library_items DROP COLUMN missing_since")
    mem_conn.execute("DELETE FROM app_state WHERE key = 'schema_version'")
    mem_conn.commit()

    init_db(mem_conn)

    row = mem_conn.execute(
        "SELECT missing_since FROM library_items WHERE title = ?", ("Old Missing Movie",)
    ).fetchone()
    assert row["missing_since"] == "2023-05-01T00:00:00"


def test_missing_since_backfill_runs_even_when_column_already_exists(mem_conn):
    """Regression: an earlier deploy of this migration only added the
    missing_since column (no backfill yet). Anyone who already ran THAT
    version has the column but every Faltante row still stuck at NULL — the
    backfill must not skip itself just because the ALTER TABLE now fails
    (column already there)."""
    from emuwarez_uploadrr.database import init_db

    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, added_at) VALUES (?,?,?,?)",
        ("Stuck Null Movie", "movie", "Faltante", "2022-11-11T00:00:00"),
    )
    # missing_since column already exists (mem_conn ran init_db in its own
    # fixture setup) — only force the migration cascade to run again,
    # without dropping the column, simulating "deployed the column-only
    # version already".
    mem_conn.execute("DELETE FROM app_state WHERE key = 'schema_version'")
    mem_conn.commit()

    init_db(mem_conn)

    row = mem_conn.execute(
        "SELECT missing_since FROM library_items WHERE title = ?", ("Stuck Null Movie",)
    ).fetchone()
    assert row["missing_since"] == "2022-11-11T00:00:00"


# ---------------------------------------------------------------------------
# One notification per missing SEASON instead of one per missing episode
# ---------------------------------------------------------------------------

def _fake_episode_in(ep_id: int, series_id: int, season: int, number: int, has_file: bool) -> dict:
    return {
        "id": ep_id, "seriesId": series_id,
        "seasonNumber": season, "episodeNumber": number,
        "title": f"Episode {number}",
        "hasFile": has_file,
        "episodeFileId": ep_id * 10 if has_file else 0,
    }


def _sync_sonarr(conn, instance, series_data, episodes, ep_files):
    from emuwarez_uploadrr.services.library import sync_instance
    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series", return_value=series_data),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes", return_value=episodes),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files", return_value=ep_files),
    ):
        return sync_instance(conn, instance, include_episodes=True)


def test_a_whole_missing_season_sends_one_notification_not_one_per_episode(sonarr_conn):
    """Adding a season with nothing downloaded used to fire one notification
    per episode, burying the bell. One per season says the same thing."""
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    # First sync (a bulk backfill) never notifies — seed the instance with an
    # unrelated, fully available season so the next pass is incremental.
    seeded = [_fake_episode_in(1 + i, 20, 1, 1 + i, True) for i in range(3)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], seeded,
                 [_fake_ep_file(1 + i) for i in range(3)])
    assert list_notifications(sonarr_conn) == []

    # Now season 2 appears, entirely missing.
    season2 = [_fake_episode_in(10 + i, 20, 2, 1 + i, False) for i in range(6)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], seeded + season2,
                 [_fake_ep_file(1 + i) for i in range(3)])

    notes = list_notifications(sonarr_conn)
    assert len(notes) == 1, [n["content_title"] for n in notes]
    assert notes[0]["event_type"] == "content_missing_new"
    assert "Temporada 2" in notes[0]["content_title"]
    assert "6" in (notes[0]["body"] or "")     # names how many episodes


def test_a_partially_missing_season_still_notifies_per_episode(sonarr_conn):
    """The season notification only replaces the episode ones when the WHOLE
    season is missing — otherwise it would claim more than it knows."""
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    seeded = [_fake_episode_in(1, 20, 1, 1, True)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], seeded, [_fake_ep_file(1)])
    assert list_notifications(sonarr_conn) == []

    # Season 2: one downloaded, two missing.
    season2 = [
        _fake_episode_in(10, 20, 2, 1, True),
        _fake_episode_in(11, 20, 2, 2, False),
        _fake_episode_in(12, 20, 2, 3, False),
    ]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], seeded + season2,
                 [_fake_ep_file(1), _fake_ep_file(10)])

    notes = list_notifications(sonarr_conn)
    assert len(notes) == 2
    assert all("Temporada" not in (n["content_title"] or "") for n in notes)


def test_an_already_missing_season_does_not_re_notify(sonarr_conn):
    """Nothing NEW turned missing on the second pass, so the season must stay
    quiet instead of re-announcing itself on every sync."""
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    seeded = [_fake_episode_in(1, 20, 1, 1, True)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], seeded, [_fake_ep_file(1)])

    season2 = [_fake_episode_in(10 + i, 20, 2, 1 + i, False) for i in range(4)]
    all_eps = seeded + season2
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], all_eps, [_fake_ep_file(1)])
    assert len(list_notifications(sonarr_conn)) == 1

    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], all_eps, [_fake_ep_file(1)])
    assert len(list_notifications(sonarr_conn)) == 1


def test_single_episode_season_keeps_the_episode_notification(sonarr_conn):
    """"Temporada 3" and "S03E01" would say the same thing for a one-episode
    season, and the episode one is the more precise of the two."""
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    seeded = [_fake_episode_in(1, 20, 1, 1, True)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], seeded, [_fake_ep_file(1)])

    lone = [_fake_episode_in(10, 20, 3, 1, False)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], seeded + lone, [_fake_ep_file(1)])

    notes = list_notifications(sonarr_conn)
    assert len(notes) == 1
    assert "Temporada" not in (notes[0]["content_title"] or "")


def test_unique_content_counts_a_dubbed_season_without_subtitles(mem_conn):
    """Castilian audio makes subtitles unnecessary, so a dubbed season with no
    subtitle tracks at all is uploadable and must be counted."""
    from emuwarez_uploadrr.services.library import get_dashboard_summary, get_dashboard_recommendations

    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog) "
        "VALUES ('Doblada', 'series', 'Disponible', 0)"
    )
    series_id = mem_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, parent_id, "
        "resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
        "has_spanish_subs, has_spanish_ok) "
        "VALUES ('Doblada - Temporada 1', 'season', 'Disponible', 0, ?, "
        "'1080p', 'WEB-DL', 'x264', 'AAC', 'spa', NULL, NULL, 1)",
        (series_id,),
    )
    mem_conn.commit()

    assert get_dashboard_summary(mem_conn)["unique_seasons"] == 1
    recs = get_dashboard_recommendations(mem_conn)
    assert "Doblada - Temporada 1" in [r["title"] for r in recs if r["rec_group"] == 2]


def test_unique_content_excludes_a_film_without_castilian(mem_conn):
    """A film without Castilian is blocked by the pre-upload checks the same as
    a season, so counting it as ready to go would be a lie."""
    from emuwarez_uploadrr.services.library import get_dashboard_summary, get_dashboard_recommendations

    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, has_spanish_ok) "
        "VALUES ('Con castellano', 'movie', 'Disponible', 0, 1)"
    )
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, has_spanish_ok) "
        "VALUES ('Sin castellano', 'movie', 'Disponible', 0, 0)"
    )
    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, has_spanish_ok) "
        "VALUES ('Sin leer', 'movie', 'Disponible', 0, NULL)"
    )
    mem_conn.commit()

    assert get_dashboard_summary(mem_conn)["unique_movies"] == 1
    titles = [r["title"] for r in get_dashboard_recommendations(mem_conn) if r["rec_group"] == 2]
    assert titles == ["Con castellano"]


def test_unique_content_counts_a_vose_film(mem_conn):
    """A film that was never dubbed but carries Castilian subtitles IS
    uploadable, so it must count — "sin castellano" means neither audio nor
    subtitles, not "not dubbed"."""
    from emuwarez_uploadrr.services.library import get_dashboard_summary, get_dashboard_recommendations

    mem_conn.execute(
        "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, "
        "audio_languages, subtitle_languages, has_spanish_audio, has_spanish_subs, has_spanish_ok) "
        "VALUES ('VOSE', 'movie', 'Disponible', 0, 'eng', 'spa', 0, 1, 1)"
    )
    mem_conn.commit()

    assert get_dashboard_summary(mem_conn)["unique_movies"] == 1
    titles = [r["title"] for r in get_dashboard_recommendations(mem_conn) if r["rec_group"] == 2]
    assert titles == ["VOSE"]


def test_a_whole_missing_series_sends_one_notification_not_one_per_season(sonarr_conn):
    """The "just added an 8 season show" case: ~150 notifications before any
    grouping, 8 with only the per-season one, 1 now."""
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    # Seed an unrelated available series so the next pass isn't a first sync.
    seeded = [_fake_episode_in(1, 20, 1, 1, True)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Ya tengo")], seeded, [_fake_ep_file(1)])
    assert list_notifications(sonarr_conn) == []

    # A second series shows up with 3 seasons and nothing downloaded.
    nueva = [
        _fake_episode_in(100 + s * 10 + e, 21, s, e, False)
        for s in (1, 2, 3) for e in (1, 2, 3, 4)
    ]
    with (
        patch("emuwarez_uploadrr.integrations.sonarr.get_series",
              return_value=[_fake_series(20, "Ya tengo"), _fake_series(21, "Serie Nueva")]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_queue", return_value=[]),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episodes",
              side_effect=lambda url, key, sid: seeded if sid == 20 else nueva),
        patch("emuwarez_uploadrr.integrations.sonarr.get_episode_files",
              side_effect=lambda url, key, sid: [_fake_ep_file(1)] if sid == 20 else []),
    ):
        from emuwarez_uploadrr.services.library import sync_instance
        sync_instance(sonarr_conn, instance, include_episodes=True)

    notes = list_notifications(sonarr_conn)
    assert len(notes) == 1, [n["content_title"] for n in notes]
    assert "Serie Nueva" in notes[0]["content_title"]
    # Says the whole show, not one of its seasons.
    assert "Temporada" not in (notes[0]["content_title"] or "")
    assert "3 temporadas" in (notes[0]["body"] or "")


def test_a_series_with_one_season_downloaded_falls_back_to_the_season_notification(sonarr_conn):
    """Not the whole series → the series notification would overstate it, so
    the per-season grouping takes over."""
    from emuwarez_uploadrr.services.notification_center import list_notifications
    from emuwarez_uploadrr.services.instances import list_instances
    instance = list_instances(sonarr_conn)[0]

    have = [_fake_episode_in(1 + i, 20, 1, 1 + i, True) for i in range(2)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], have,
                 [_fake_ep_file(1 + i) for i in range(2)])
    assert list_notifications(sonarr_conn) == []

    # Season 2 arrives empty; season 1 is still fully downloaded.
    s2 = [_fake_episode_in(10 + i, 20, 2, 1 + i, False) for i in range(3)]
    _sync_sonarr(sonarr_conn, instance, [_fake_series(20, "Serie")], have + s2,
                 [_fake_ep_file(1 + i) for i in range(2)])

    notes = list_notifications(sonarr_conn)
    assert len(notes) == 1
    assert "Temporada 2" in notes[0]["content_title"]


def test_mejoras_posibles_son_lo_que_ya_esta_en_emuwarez_y_tu_copia_mejora(mem_conn):
    """Grupo 4 de Recomendaciones: disponible, ya en eMuwarez (emu_in_catalog = 1) y con aportes. Sin aportes, sin
    castellano o sin tener el fichero no entra, y el grupo 2 (contenido único) sigue sin repetirlo."""
    from emuwarez_uploadrr.services.library import get_dashboard_recommendations

    def peli(titulo, estado="Disponible", en_catalogo=1, aportes='[{"dim": "resolucion", "detail": "2160p"}]', es=1):
        mem_conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, emu_aportes, has_spanish_ok) "
            "VALUES (?, 'movie', ?, ?, ?, ?)", (titulo, estado, en_catalogo, aportes, es))

    peli("Mejor")
    peli("Igual", aportes="[]")
    peli("Sin aportes calculados", aportes=None)
    peli("Sin castellano", es=0)
    peli("No la tienes", estado="Faltante")
    peli("Subida ya", estado="Subido")
    peli("No esta en eMuwarez", en_catalogo=0, aportes="[]")
    peli("JSON roto", aportes="{no es json")
    mem_conn.commit()

    recs = get_dashboard_recommendations(mem_conn)
    mejoras = [r for r in recs if r["rec_group"] == 4]
    assert [r["title"] for r in mejoras] == ["Mejor"]
    assert mejoras[0]["rec_aportes"] == [{"dim": "resolucion", "detail": "2160p"}]
    # El único no se mezcla con las mejoras, ni al revés.
    assert [r["title"] for r in recs if r["rec_group"] == 2] == ["No esta en eMuwarez"]
    assert all(r["rec_aportes"] == [] for r in recs if r["rec_group"] != 4)


def test_mejoras_posibles_de_temporada_exigen_lo_mismo_que_el_pack(mem_conn):
    """Una temporada con aportes solo es una mejora subible si sus capítulos coinciden (rollup del pack) y llevan
    castellano, igual que en el contenido único."""
    from emuwarez_uploadrr.services.library import get_dashboard_recommendations

    mem_conn.execute("INSERT INTO library_items (title, item_type, local_status, emu_in_catalog) "
                     "VALUES ('Serie', 'series', 'Disponible', 1)")
    serie = mem_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for n, (res, ok) in enumerate((("1080p", 1), (None, 1), ("1080p", 0)), start=1):
        mem_conn.execute(
            "INSERT INTO library_items (title, item_type, local_status, emu_in_catalog, emu_aportes, parent_id, "
            "season_number, resolution, source, video_codec, audio_codec, audio_languages, subtitle_languages, "
            "has_spanish_subs, has_spanish_ok) "
            f"VALUES ('Serie - Temporada {n}', 'season', 'Disponible', 1, "
            "'[{\"dim\": \"codec\", \"detail\": \"HEVC\"}]', ?, ?, ?, 'WEB-DL', 'x265', 'AAC', 'jpn', 'spa', 1, ?)",
            (serie, n, res, ok))
    mem_conn.commit()

    titulos = [r["title"] for r in get_dashboard_recommendations(mem_conn) if r["rec_group"] == 4]
    assert titulos == ["Serie - Temporada 1"]
