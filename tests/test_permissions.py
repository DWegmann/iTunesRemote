from types import SimpleNamespace

import pytest
from conftest import HOST_KEY
from itunesremote.adapters import DemoAdapter
from itunesremote.models import AppError
from itunesremote.service import LibraryService
from starlette.testclient import TestClient


def test_permission_endpoint_requires_local_authentication(client):
    assert client.post("/api/v1/permissions/request", json={}).status_code == 401
    response = client.post(
        "/api/v1/permissions/request", json={}, headers={"Authorization": f"Bearer {HOST_KEY}"}
    )
    assert response.status_code == 200
    assert response.json()["media"]["status"] == "notRequired"


def test_browser_can_request_permissions_without_changing_demo_ratings(browser):
    client, headers = browser
    before = client.get("/api/v1/tracks").json()
    response = client.post("/api/v1/permissions/request", json={}, headers=headers)
    assert response.status_code == 200
    assert response.json()["mode"] == "demo"
    assert response.json()["needsSettings"] is False
    assert response.json()["automation"]["status"] == "notRequired"
    assert client.get("/api/v1/tracks").json() == before


def test_remote_device_cannot_trigger_system_permission_dialogs(browser, monkeypatch):
    client, headers = browser

    def unexpected():
        raise AssertionError("A device must not request local system permissions")

    monkeypatch.setattr(client.app.state.library, "request_permissions", unexpected)
    tokens = client.post("/api/v1/auth/devices", json={"name": "iPad"}, headers=headers).json()
    client.cookies.clear()
    response = client.post(
        "/api/v1/permissions/request", json={}, headers={"Authorization": f"Bearer {tokens['accessToken']}"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "LOCAL_ADMIN_REQUIRED"


@pytest.mark.parametrize(
    "media,automation,connected",
    [("granted", "granted", True), ("granted", "unavailable", True), ("unavailable", "granted", False)],
)
def test_media_permission_controls_reading_independently_of_automation(
    tmp_path, media, automation, connected
):
    demo = DemoAdapter()
    adapter = SimpleNamespace(
        mode="music",
        snapshot=demo.snapshot,
        request_permissions=lambda: {
            "mode": "music",
            "needsSettings": "unavailable" in (media, automation),
            "media": {"status": media, "message": "Media"},
            "automation": {"status": automation, "message": "Automation"},
        },
    )
    library = LibraryService(tmp_path, adapter=adapter)
    try:
        result = library.request_permissions()
        assert result["media"]["status"] == media
        assert result["automation"]["status"] == automation
        assert result["libraryConnected"] is False
        assert library.store.summary()["total"] == 0
        if media == "granted":
            library.refresh()
        assert library.connected is connected
        assert bool(library.store.summary()["total"]) is connected
    finally:
        library.close()


def test_library_error_does_not_masquerade_as_permission_denial(tmp_path):
    def fail():
        raise AppError("LIBRARY_ID_UNAVAILABLE", "Keine eindeutige Bibliothek", 503)

    adapter = SimpleNamespace(
        mode="music",
        snapshot=fail,
        request_permissions=lambda: {
            "mode": "music",
            "needsSettings": False,
            "media": {"status": "granted", "message": "Media"},
            "automation": {"status": "granted", "message": "Automation"},
        },
    )
    library = LibraryService(tmp_path, adapter=adapter)
    try:
        result = library.request_permissions()
        assert result["media"]["status"] == "granted"
        assert "libraryError" not in result
        assert result["libraryConnected"] is False
        with pytest.raises(AppError) as error:
            library.refresh()
        assert error.value.code == "LIBRARY_ID_UNAVAILABLE"
    finally:
        library.close()


def test_import_reports_progress_and_always_finishes(tmp_path, monkeypatch):
    events = []
    library = LibraryService(tmp_path, "demo", on_progress=events.append)
    assert events[0]["stage"] == "opening"
    assert events[-1]["stage"] == "done"
    assert events[-1]["total"] == 34
    assert library.status()["progress"] == events[-1]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert next(event for event in events if event["stage"] == "indexing")["completed"] == 0
    assert any(event["stage"] == "indexing" and event["completed"] == 34 for event in events)
    assert events[-2]["stage"] == "saving"
    events.clear()

    def fail():
        raise RuntimeError("Index failure")

    monkeypatch.setattr(library.adapter, "snapshot", fail)
    try:
        with pytest.raises(RuntimeError):
            library.refresh()
        assert events[-1]["stage"] == "failed"
        assert library.status()["progress"] == events[-1]
        assert not library.connected
    finally:
        library.close()


def test_progress_sequences_remain_ordered_across_library_mode_changes(tmp_path):
    events = []
    library = LibraryService(tmp_path, "demo", on_progress=events.append)
    sequence = events[-1]["sequence"]
    try:
        # Switching to Music constructs an idle adapter and does not access the real library.
        library.set_mode("music")
        library.set_mode("demo")
        assert events[-1]["sequence"] > sequence
        assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
        assert library.status()["progress"]["stage"] == "done"
    finally:
        library.close()


def test_repeated_api_connects_cannot_request_missing_media_permission(tmp_path, monkeypatch):
    pytest.importorskip("iTunesLibrary")
    from itunesremote import permissions
    from itunesremote.adapters import MusicAdapter
    from itunesremote.api import create_app

    adapter = MusicAdapter()
    library = LibraryService(tmp_path / "data", adapter=adapter)
    library.store.replace(DemoAdapter().snapshot())
    before = library.store.query()

    def unexpected(*args):
        raise AssertionError("Connect must not request consent or open the native library")

    monkeypatch.setattr(permissions, "media_authorization_status", lambda: 0)
    monkeypatch.setattr(permissions, "request_media_access", unexpected)
    monkeypatch.setattr(adapter, "_open_library", unexpected)
    app = create_app(tmp_path / "data", tmp_path, HOST_KEY, service=library)
    with TestClient(app) as client:
        headers = {"Authorization": f"Bearer {HOST_KEY}"}
        for _ in range(3):
            response = client.post("/api/v1/library/connect", json={"mode": "music"}, headers=headers)
            assert response.status_code == 403
            assert response.json()["error"]["code"] == "MEDIA_PERMISSION_REQUIRED"
            assert client.get("/api/v1/tracks", headers=headers).json() == before
