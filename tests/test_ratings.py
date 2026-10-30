import pytest
from conftest import HOST_KEY, rate_body
from itunesremote.models import AppError


def test_confirmed_rating_idempotency_and_request_ownership(browser):
    client, headers = browser
    track = client.get("/api/v1/tracks?rating=unrated").json()["items"][0]
    body = rate_body(client, track, 4)
    result = client.put(f"/api/v1/tracks/{track['id']}/rating", json=body, headers=headers)
    assert result.status_code == 200
    assert result.json()["state"] == "confirmed"
    assert result.json()["track"]["ratingRaw"] == 80
    assert (
        client.put(f"/api/v1/tracks/{track['id']}/rating", json=body, headers=headers).json() == result.json()
    )
    assert client.get(f"/api/v1/requests/{body['requestId']}").json() == result.json()
    assert (
        client.get(
            f"/api/v1/requests/{body['requestId']}", headers={"Authorization": f"Bearer {HOST_KEY}"}
        ).status_code
        == 404
    )
    changed = {**body, "stars": 1}
    assert (
        client.put(f"/api/v1/tracks/{track['id']}/rating", json=changed, headers=headers).json()["error"][
            "code"
        ]
        == "REQUEST_ID_REUSED"
    )


@pytest.mark.parametrize("stars", [-1, 6, 2.5, True, "3", None])
def test_invalid_star_values_do_not_write(browser, stars):
    client, headers = browser
    track = client.get("/api/v1/tracks").json()["items"][0]
    body = rate_body(client, track, stars)
    assert client.put(f"/api/v1/tracks/{track['id']}/rating", json=body, headers=headers).status_code == 400
    assert client.get(f"/api/v1/tracks/{track['id']}").json() == track


def test_album_rating_is_unrated_and_reappears_after_clear(browser):
    client, headers = browser
    inherited = next(
        t for t in client.get("/api/v1/tracks?rating=unrated").json()["items"] if t["ratingOrigin"] == "album"
    )
    assert inherited["ratingRaw"] == 80
    response = client.put(
        f"/api/v1/tracks/{inherited['id']}/rating", json=rate_body(client, inherited, 5), headers=headers
    )
    assert response.status_code == 200
    track = response.json()["track"]
    assert track["ratingOrigin"] == "user"
    response = client.put(
        f"/api/v1/tracks/{inherited['id']}/rating",
        json=rate_body(client, track, 0, "test-clear-request"),
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["track"]["ratingOrigin"] == "album"
    assert response.json()["track"]["ratingRaw"] == 80


def test_conflict_does_not_overwrite_newer_rating(browser):
    client, headers = browser
    track = client.get("/api/v1/tracks?rating=unrated").json()["items"][0]
    adapter = client.app.state.library.adapter
    adapter.write_rating(track["id"], 2)
    response = client.put(
        f"/api/v1/tracks/{track['id']}/rating", json=rate_body(client, track, 5), headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RATING_CONFLICT"
    assert adapter.read_rating(track["id"])[0] == 40


def test_first_rating_accepts_legacy_zero_album_revision(browser):
    client, headers = browser
    service = client.app.state.library
    track = next(
        t for t in client.get("/api/v1/tracks?rating=unrated").json()["items"] if t["ratingRaw"] == 0
    )
    legacy = service.store.update_rating(track["id"], 0, "album", confirmed=False)
    body = rate_body(client, legacy, 5)
    response = client.put(f"/api/v1/tracks/{track['id']}/rating", json=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["state"] == "confirmed"
    assert response.json()["track"]["ratingRaw"] == 100
    assert response.json()["track"]["ratingOrigin"] == "user"
    assert service.adapter.read_rating(track["id"]) == (100, "user")
    assert client.put(f"/api/v1/tracks/{track['id']}/rating", json=body, headers=headers).json() == response.json()


@pytest.mark.parametrize(
    ("cached_raw", "cached_origin", "live_raw", "live_origin"),
    [(0, "album", 40, "user"), (0, "album", 80, "album"),
     (80, "user", 0, "none"), (80, "album", 0, "none"), (80, "album", 80, "user")],
)
def test_rating_normalization_preserves_real_conflicts(
    browser, cached_raw, cached_origin, live_raw, live_origin,
):
    client, headers = browser
    service = client.app.state.library
    track = client.get("/api/v1/tracks").json()["items"][0]
    cached = service.store.update_rating(track["id"], cached_raw, cached_origin, confirmed=False)
    native = service.adapter.tracks[track["id"]]
    native.ratingRaw, native.ratingOrigin = live_raw, live_origin
    response = client.put(
        f"/api/v1/tracks/{track['id']}/rating", json=rate_body(client, cached, 5), headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RATING_CONFLICT"
    assert service.adapter.read_rating(track["id"]) == (live_raw, live_origin)
    current = response.json()["error"]["details"]["track"]
    assert (current["ratingRaw"], current["ratingOrigin"]) == (live_raw, live_origin)


def test_wrong_library_never_writes(browser):
    client, headers = browser
    track = client.get("/api/v1/tracks").json()["items"][0]
    data = {**rate_body(client, track), "libraryScope": "other-library"}
    response = client.put(f"/api/v1/tracks/{track['id']}/rating", json=data, headers=headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LIBRARY_CHANGED"


def test_failed_write_never_returns_success_and_is_not_repeated(browser, monkeypatch):
    client, headers = browser
    track = client.get("/api/v1/tracks").json()["items"][0]
    calls = []

    def fail(*args):
        calls.append(args)
        raise AppError("AUTOMATION_DENIED", "Denied", 403)

    monkeypatch.setattr(client.app.state.library.adapter, "write_rating", fail)
    data = rate_body(client, track)
    for _ in range(2):
        response = client.put(f"/api/v1/tracks/{track['id']}/rating", json=data, headers=headers)
        assert response.status_code == 403
    assert len(calls) == 1
    assert client.get(f"/api/v1/tracks/{track['id']}").json()["ratingRaw"] == track["ratingRaw"]


def test_failed_refresh_preserves_index(browser, monkeypatch):
    client, headers = browser
    before = client.get("/api/v1/tracks").json()

    def fail():
        raise AppError("REFRESH_FAILED", "Failed", 503)

    monkeypatch.setattr(client.app.state.library.adapter, "snapshot", fail)
    assert client.post("/api/v1/library/refresh", json={}, headers=headers).status_code == 503
    after = client.get("/api/v1/tracks").json()
    assert before == after
    assert not client.get("/api/v1/status").json()["connected"]
    track = before["items"][0]
    assert (
        client.put(
            f"/api/v1/tracks/{track['id']}/rating", json=rate_body(client, track), headers=headers
        ).status_code
        == 409
    )
