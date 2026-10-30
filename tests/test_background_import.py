"""Slow native imports must leave the last committed cache available."""

import time
from threading import Event

import pytest
from conftest import rate_body
from itunesremote.adapters import DemoAdapter
from itunesremote.models import AppError
from itunesremote.service import LibraryService
from itunesremote.store import Store


@pytest.mark.parametrize("fails", [False, True])
def test_slow_import_keeps_cache_readable_and_coalesces_clients(browser, monkeypatch, fails):
    client, headers = browser
    library = client.app.state.library
    original = library.adapter.snapshot
    before = client.get("/api/v1/tracks?limit=5").json()
    rating = rate_body(client, before["items"][0])
    started, release = Event(), Event()
    calls = []

    def slow_snapshot():
        calls.append(True)
        started.set()
        assert release.wait(10), "Test did not release the native import"
        if fails:
            raise AppError("REFRESH_FAILED", "Simulierter Importfehler", 503)
        snapshot = original()
        snapshot.tracks[0].title = "Nach dem Import"
        return snapshot

    monkeypatch.setattr(library.adapter, "snapshot", slow_snapshot)
    try:
        begin = time.monotonic()
        response = client.post("/api/v1/library/refresh", json={"background": True}, headers=headers)
        assert response.status_code == 200
        assert response.json()["refreshing"] is True
        assert started.wait(1)
        assert client.get("/api/v1/tracks?limit=5").json() == before
        assert client.get("/api/v1/tracks?query=Radiohead").json()["total"] == 6
        assert (
            client.get("/api/v1/tracks", params={"limit": 5, "cursor": before["nextCursor"]}).status_code
            == 200
        )
        assert client.get(f"/api/v1/tracks/{before['items'][0]['id']}").status_code == 200
        assert client.get("/api/v1/playlists").json()["items"]
        pending = client.get("/api/v1/status").json()
        assert pending["refreshing"] is True
        assert pending["progress"]["stage"] == "opening"
        assert client.get("/api/v1/capabilities").status_code == 200
        assert client.get(f"/api/v1/tracks/{before['items'][0]['id']}/artwork").status_code == 404
        assert client.get("/api/v1/requests/missing-request").status_code == 404
        again = client.post("/api/v1/library/refresh", json={"background": True}, headers=headers)
        assert again.status_code == 200
        assert len(calls) == 1
        busy = client.put(f"/api/v1/tracks/{before['items'][0]['id']}/rating", json=rating, headers=headers)
        assert busy.json()["error"]["code"] == "LIBRARY_BUSY"
        switch = client.post(
            "/api/v1/library/connect", json={"mode": "music", "background": True}, headers=headers
        )
        assert switch.json()["error"]["code"] == "LIBRARY_BUSY"
        assert time.monotonic() - begin < 2
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status = client.get("/api/v1/status").json()
        if not status["refreshing"]:
            break
        time.sleep(0.01)
    assert not status["refreshing"]
    assert status["progress"]["stage"] == ("failed" if fails else "done")
    after = client.get("/api/v1/tracks?limit=5").json()
    if fails:
        assert after == before
        assert status["error"]["code"] == "REFRESH_FAILED"
        assert not status["connected"]
    else:
        assert status["connected"]
        assert after["snapshotRevision"] != before["snapshotRevision"]
        assert (
            client.get("/api/v1/tracks", params={"limit": 5, "cursor": before["nextCursor"]}).status_code
            == 409
        )


def test_fresh_background_poll_does_not_report_an_import(browser, monkeypatch):
    client, headers = browser

    def unexpected():
        raise AssertionError("Fresh polling must not import")

    monkeypatch.setattr(client.app.state.library.adapter, "snapshot", unexpected)
    for _ in range(3):
        response = client.post(
            "/api/v1/library/refresh", json={"background": True, "ifStale": True}, headers=headers
        )
        assert response.status_code == 200
        assert not response.json()["refreshing"]


def test_cache_restart_does_not_import_before_serving_reads(tmp_path):
    class Music(DemoAdapter):
        mode = "music"

    library = LibraryService(tmp_path, adapter=Music())
    library.refresh()
    before = library.store.query()
    library.close()

    class Offline(Music):
        def snapshot(self):
            raise AssertionError("Startup must not wait for a native import")

    library = LibraryService(tmp_path, adapter=Offline())
    try:
        assert library.read_cached("query") == before
        assert library.read_cached("status")["hasCache"]
        assert not library.connected
        assert not library.refreshing
    finally:
        library.close()


def test_reader_holds_one_committed_snapshot_while_writer_publishes(tmp_path):
    store = Store(tmp_path / "index.sqlite3")
    snapshot = DemoAdapter().snapshot()
    store.replace(snapshot)
    before = store.query()
    try:
        with Store.reader(store.path) as reader:
            assert reader.query() == before
            snapshot.tracks[0].title = "Neuer Titel"
            store.replace(snapshot)
            assert reader.query() == before
        with Store.reader(store.path) as reader:
            assert reader.query() != before
            assert reader.query(query="Neuer Titel")["total"] == 1
    finally:
        store.close()


@pytest.mark.parametrize("endpoint", ["refresh", "connect"])
@pytest.mark.parametrize("value", [1, "true", None])
def test_invalid_background_option_does_not_start_import(browser, monkeypatch, endpoint, value):
    client, headers = browser

    def unexpected():
        raise AssertionError("Invalid requests must not import")

    monkeypatch.setattr(client.app.state.library.adapter, "snapshot", unexpected)
    response = client.post(
        f"/api/v1/library/{endpoint}", json={"mode": "demo", "background": value}, headers=headers
    )
    assert response.status_code == 400


@pytest.mark.parametrize("change", [None, "rating", "library"])
def test_rating_checks_identity_and_conflicts_without_full_import(tmp_path, change):
    class Music(DemoAdapter):
        mode = "music"

        def __init__(self):
            super().__init__()
            self.imports = 0
            self.scope = "demo-library-v1"
            self.writes = 0

        def snapshot(self):
            self.imports += 1
            return super().snapshot()

        def library_scope(self):
            return self.scope

        def write_rating(self, ident, stars):
            self.writes += 1
            return super().write_rating(ident, stars)

    adapter = Music()
    library = LibraryService(tmp_path, adapter=adapter)
    try:
        library.refresh()
        track = library.store.query(rating="unrated")["items"][0]
        body = {
            "stars": 5,
            "libraryScope": adapter.scope,
            "expectedRevision": track["ratingRevision"],
            "requestId": "direct-rating-test",
        }
        if change == "library":
            adapter.scope = "different-library"
        elif change == "rating":
            adapter.tracks[track["id"]].ratingRaw = 40
            adapter.tracks[track["id"]].ratingOrigin = "user"
        if change:
            with pytest.raises(AppError) as error:
                library.rate(track["id"], body, "owner")
            assert error.value.code == ("LIBRARY_CHANGED" if change == "library" else "RATING_CONFLICT")
            assert adapter.writes == 0
        else:
            result = library.rate(track["id"], body, "owner")
            assert result["state"] == "confirmed"
            assert result["track"]["ratingRaw"] == 100
            assert library.rate(track["id"], body, "owner") == result
            assert adapter.writes == 1
        assert adapter.imports == 1
    finally:
        library.close()
