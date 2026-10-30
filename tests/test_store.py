import json
import sqlite3
import time

import pytest
from itunesremote.adapters import DemoAdapter
from itunesremote.models import Playlist, Snapshot, Track, canonical_id
from itunesremote.service import LibraryService
from itunesremote.store import Store


def test_persistent_id_preserves_unsigned_64_bits():
    assert canonical_id(0xFFFFFFFFFFFFFFFF) == "FFFFFFFFFFFFFFFF"
    assert canonical_id("a1") == "00000000000000A1"


def test_unicode_search_and_duplicate_playlist_names(tmp_path):
    store = Store(tmp_path / "index.sqlite3")
    tracks = [Track("0000000000000001", "Straße", "Björk", ratingRaw=70, ratingOrigin="user")]
    store.replace(
        Snapshot("scope", tracks, [Playlist("one", "Same", [tracks[0].id]), Playlist("two", "Same", [])])
    )
    assert store.query(query="strasse bjork")["total"] == 1
    assert store.query()["items"][0]["ratingRaw"] == 70
    assert store.query(playlist_id="one")["total"] == 1
    assert store.query(playlist_id="two")["total"] == 0
    store.close()


@pytest.mark.parametrize(
    "sort,expected",
    [("addedDate", [3, 4, 2, 1, 5]), ("addedDateAsc", [1, 2, 3, 4, 5])],
)
def test_added_date_sort_is_chronological_and_stable_across_pages(tmp_path, sort, expected):
    store = Store(tmp_path / "index.sqlite3")
    dates = [
        "2024-01-01T11:00:00Z",
        "2024-01-02T00:30:00+02:00",
        "2024-01-01T23:00:00Z",
        "2024-01-01T23:00:00Z",
        None,
    ]
    tracks = [
        Track(canonical_id(i), "Titel", addedDate=date, ratingRaw=60, ratingOrigin="user")
        for i, date in enumerate(dates, 1)
    ]
    store.replace(Snapshot("scope", tracks, [Playlist("list", "Auswahl", [t.id for t in tracks[:3]])]))
    ids, cursor = [], ""
    while True:
        page = store.query(sort=sort, limit=2, cursor=cursor)
        ids.extend(t["id"] for t in page["items"])
        cursor = page["nextCursor"]
        if not cursor:
            break
    assert ids == [canonical_id(i) for i in expected]
    filtered = store.query(query="Titel", rating="3", playlist_id="list", sort=sort)
    assert [t["id"] for t in filtered["items"]] == [canonical_id(i) for i in expected if i <= 3]
    assert store.update_rating(tracks[1].id, 100, "user")["addedDate"] == dates[1]
    assert [t["id"] for t in store.query(sort=sort)["items"]] == ids
    store.close()


def test_legacy_cache_migrates_without_losing_tracks_or_ratings(tmp_path):
    path = tmp_path / "index.sqlite3"
    track = Track(canonical_id(1), "Vorhandener Titel", ratingRaw=80, ratingOrigin="user")
    saved = track.to_dict()
    saved.pop("addedDate")
    with sqlite3.connect(path) as legacy:
        legacy.execute("""CREATE TABLE tracks (
            id TEXT PRIMARY KEY, title TEXT, artist TEXT, album TEXT, search TEXT,
            rating INTEGER, origin TEXT, duration INTEGER, payload TEXT NOT NULL
        )""")
        legacy.execute(
            "INSERT INTO tracks VALUES (?,?,?,?,?,?,?,?,?)",
            (track.id, "vorhandener titel", "", "", "vorhandener titel", 80, "user", 0, json.dumps(saved)),
        )
    store = Store(path)
    cached = store.query(sort="addedDate")["items"][0]
    assert cached["id"] == track.id
    assert cached["ratingRaw"] == 80
    assert cached["addedDate"] is None
    track.addedDate = "2024-01-01T12:00:00Z"
    store.replace(Snapshot("scope", [track], []))
    store.close()
    store = Store(path)
    assert store.query(sort="addedDateAsc")["items"][0]["addedDate"] == track.addedDate
    assert store.update_rating(track.id, 100, "user")["addedDate"] == track.addedDate
    store.close()


def test_demo_persistence_is_separate_from_real_cache(tmp_path):
    service = LibraryService(tmp_path, "demo")
    track = service.store.query(rating="unrated")["items"][0]
    service.rate(
        track["id"],
        {
            "stars": 5,
            "expectedRevision": track["ratingRevision"],
            "libraryScope": "demo-library-v1",
            "requestId": "persistent-test",
        },
        "owner",
    )
    service.close()
    service = LibraryService(tmp_path, "demo")
    assert service.store.track(track["id"])["ratingRaw"] == 100
    assert not (tmp_path / "index-music.sqlite3").exists()
    service.close()


def test_search_50000_tracks_under_300ms(tmp_path):
    store = Store(tmp_path / "index.sqlite3")
    tracks = [
        Track(canonical_id(i + 1), f"Titel {i}", f"Interpret {i % 100}", f"Album {i % 500}")
        for i in range(50000)
    ]
    store.replace(Snapshot("large", tracks, []))
    start = time.perf_counter()
    result = store.query(query="interpret 42", sort="title")
    elapsed = time.perf_counter() - start
    assert result["total"] > 0
    assert elapsed < 0.3, f"Search took {elapsed:.3f}s"
    store.close()


def test_confirmed_override_does_not_revert_on_stale_snapshot(tmp_path):
    adapter = DemoAdapter()
    service = LibraryService(tmp_path, adapter=adapter)
    track = service.store.query(rating="unrated")["items"][0]
    stale = adapter.snapshot()
    service.rate(
        track["id"],
        {
            "stars": 5,
            "expectedRevision": track["ratingRevision"],
            "libraryScope": "demo-library-v1",
            "requestId": "override-test",
        },
        "owner",
    )
    adapter.snapshot = lambda: stale
    service.refresh()
    assert service.store.track(track["id"])["ratingRaw"] == 100
    adapter.write_rating(track["id"], 2)
    service.refresh()
    assert service.store.track(track["id"])["ratingRaw"] == 40
    service.close()
