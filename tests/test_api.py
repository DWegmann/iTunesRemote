import sqlite3
import time

import pytest
from conftest import HOST_KEY, browser_login, rate_body


def test_no_data_without_authentication(client):
    assert client.get("/health").json() == {"ok": True}
    assert client.get("/").status_code == 200
    for endpoint in ["status", "tracks", "playlists", "capabilities", "openapi.json"]:
        assert client.get(f"/api/v1/{endpoint}").status_code == 401


def test_browser_bootstrap_is_one_time_and_cookie_is_private(client):
    code = client.post(
        "/api/v1/auth/bootstrap", json={}, headers={"Authorization": f"Bearer {HOST_KEY}"}
    ).json()["code"]
    headers = {"Origin": "http://testserver"}
    response = client.post("/api/v1/auth/exchange", json={"code": code}, headers=headers)
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert client.post("/api/v1/auth/exchange", json={"code": code}, headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/bootstrap",
            json={},
            headers={**headers, "X-CSRF-Token": response.json()["csrfToken"]},
        ).status_code
        == 403
    )


def test_expired_bootstrap_cannot_login(client):
    client.app.state.auth.codes["unused"] = 0
    assert (
        client.post(
            "/api/v1/auth/exchange", json={"code": "unused"}, headers={"Origin": "http://testserver"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "headers,code",
    [
        ({"Host": "attacker.example"}, 421),
        ({"Origin": "https://attacker.example"}, 403),
        ({"Origin": "http://testserver", "X-CSRF-Token": "wrong"}, 403),
        ({}, 403),
    ],
)
def test_host_origin_and_csrf_are_enforced(browser, headers, code):
    client, _ = browser
    assert client.post("/api/v1/library/refresh", json={}, headers=headers).status_code == code


def test_content_type_and_stream_size_are_checked(browser):
    client, headers = browser
    assert client.post("/api/v1/library/refresh", content="{}", headers=headers).status_code == 415
    response = client.post(
        "/api/v1/library/refresh",
        content=b"a" * 8193,
        headers={**headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert client.post("/api/v1/library/connect", json=[], headers=headers).status_code == 400


def test_security_headers(browser):
    client, _ = browser
    response = client.get("/")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_search_and_playlist_filters(browser):
    client, _ = browser
    page = client.get("/api/v1/tracks?query=RADIOHEAD").json()
    assert page["total"] == 6
    assert all(t["artist"] == "Radiohead" for t in page["items"])
    lists = client.get("/api/v1/playlists").json()["items"]
    page = client.get("/api/v1/tracks", params={"playlistId": lists[0]["id"]}).json()
    assert page["total"] == lists[0]["trackCount"]
    assert client.get("/api/v1/tracks?playlistId=missing").status_code == 404


@pytest.mark.parametrize("sort,first,last", [("addedDate", "Familiar", "15 Step"), ("addedDateAsc", "15 Step", "Familiar")])
def test_tracks_can_be_sorted_by_added_date(browser, sort, first, last):
    client, _ = browser
    response = client.get("/api/v1/tracks", params={"sort": sort})
    assert response.status_code == 200
    tracks = response.json()["items"]
    assert tracks[0]["title"] == first
    assert tracks[-1]["title"] == last
    assert all(track["addedDate"] for track in tracks)
    assert client.get(f"/api/v1/tracks/{tracks[0]['id']}").json()["addedDate"] == tracks[0]["addedDate"]


def test_stable_pagination_and_expired_cursor(browser):
    client, headers = browser
    first = client.get("/api/v1/tracks?limit=5").json()
    second = client.get("/api/v1/tracks", params={"limit": 5, "cursor": first["nextCursor"]}).json()
    assert not ({t["id"] for t in first["items"]} & {t["id"] for t in second["items"]})
    track = first["items"][0]
    response = client.put(
        f"/api/v1/tracks/{track['id']}/rating", json=rate_body(client, track), headers=headers
    )
    assert response.status_code == 200
    expired = client.get("/api/v1/tracks", params={"limit": 5, "cursor": first["nextCursor"]})
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "CURSOR_EXPIRED"


def test_polling_clients_share_one_native_refresh(browser, monkeypatch):
    client, headers = browser
    library = client.app.state.library
    original = library.adapter.snapshot
    calls = []

    def counted():
        calls.append(True)
        return original()

    monkeypatch.setattr(library.adapter, "snapshot", counted)
    library.last_refresh = 0
    for _ in range(2):
        assert (
            client.post("/api/v1/library/refresh", json={"ifStale": True}, headers=headers).status_code == 200
        )
    assert len(calls) == 1
    assert client.post("/api/v1/library/refresh", json={}, headers=headers).status_code == 200
    assert len(calls) == 2


def test_refresh_without_changes_keeps_pagination(browser):
    client, headers = browser
    first = client.get("/api/v1/tracks?limit=5").json()
    client.post("/api/v1/library/refresh", json={}, headers=headers)
    assert client.get("/api/v1/tracks", params={"limit": 5, "cursor": first["nextCursor"]}).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "title; DROP TABLE tracks"},
        {"rating": "6"},
        {"limit": "no"},
        {"limit": 0},
        {"limit": 201},
        {"cursor": "forged"},
        {"query": "x" * 301},
    ],
)
def test_invalid_filters_are_rejected(browser, params):
    client, _ = browser
    assert client.get("/api/v1/tracks", params=params).status_code == 400


def test_device_bearer_works_without_cookies_and_can_be_rotated_and_revoked(browser):
    client, headers = browser
    device = client.post("/api/v1/auth/devices", json={"name": "iPad"}, headers=headers).json()
    assert "accessToken" in device
    client.cookies.clear()
    bearer = {"Authorization": f"Bearer {device['accessToken']}"}
    assert client.get("/api/v1/status", headers=bearer).status_code == 200
    assert client.get("/api/v1/capabilities", headers=bearer).json()["features"]["libraryModeChange"] is False
    assert client.post("/api/v1/library/connect", json={"mode": "demo"}, headers=bearer).status_code == 403
    assert (
        client.post("/api/v1/auth/devices", json={"name": "unauthorized"}, headers=bearer).status_code == 403
    )
    renewed = client.post("/api/v1/auth/refresh", json={"refreshToken": device["refreshToken"]}).json()
    assert client.get("/api/v1/status", headers=bearer).status_code == 401
    assert (
        client.post("/api/v1/auth/refresh", json={"refreshToken": device["refreshToken"]}).status_code == 401
    )
    bearer = {"Authorization": f"Bearer {renewed['accessToken']}"}
    assert client.get("/api/v1/status", headers=bearer).status_code == 200
    headers = browser_login(client)
    assert (
        client.request(
            "DELETE", f"/api/v1/auth/devices/{device['deviceId']}", json={}, headers=headers
        ).status_code
        == 200
    )
    assert client.get("/api/v1/status", headers=bearer).status_code == 401
    assert (
        client.post("/api/v1/auth/refresh", json={"refreshToken": renewed["refreshToken"]}).status_code == 401
    )


def test_device_access_token_expiry(browser):
    client, headers = browser
    device = client.post("/api/v1/auth/devices", json={"name": "iPad"}, headers=headers).json()
    # The connection is opened on a separate test thread; use an independent connection.
    path = client.app.state.auth.db.execute("PRAGMA database_list").fetchone()[2]
    with sqlite3.connect(path) as db:
        db.execute("UPDATE credentials SET expires=? WHERE kind='access'", (time.time() - 1,))
    client.cookies.clear()
    assert (
        client.get("/api/v1/status", headers={"Authorization": f"Bearer {device['accessToken']}"}).status_code
        == 401
    )


def test_native_device_writes_the_same_library_without_browser_cookies(browser):
    client, headers = browser
    device = client.post("/api/v1/auth/devices", json={"name": "Native iPad client"}, headers=headers).json()
    client.cookies.clear()
    bearer = {"Authorization": f"Bearer {device['accessToken']}"}
    page = client.get("/api/v1/tracks?rating=unrated", headers=bearer).json()
    track = page["items"][0]
    data = {
        "stars": 2,
        "expectedRevision": track["ratingRevision"],
        "libraryScope": page["libraryScope"],
        "requestId": "native-rating-test",
    }
    result = client.put(f"/api/v1/tracks/{track['id']}/rating", json=data, headers=bearer)
    assert result.status_code == 200
    assert result.json()["track"]["ratingRaw"] == 40
    browser_login(client)
    assert client.get(f"/api/v1/tracks/{track['id']}").json()["ratingRaw"] == 40


def test_openapi_covers_all_api_routes(browser):
    client, _ = browser
    spec = client.get("/api/v1/openapi.json").json()
    assert spec["openapi"] == "3.1.0"
    documented = {"/api/v1" + path for path in spec["paths"]}
    actual = {route.path for route in client.app.routes if route.path.startswith("/api/v1")}
    assert documented == actual
    assert spec["components"]["schemas"]["Track"]["properties"]["id"]["type"] == "string"
