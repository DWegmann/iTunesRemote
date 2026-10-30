from conftest import rate_body
from itunesremote.models import AppError


def test_unavailable_cloud_track_is_marked_without_faking_success(browser, monkeypatch):
    client, headers = browser
    track = client.get("/api/v1/tracks").json()["items"][0]
    adapter = client.app.state.library.adapter

    def unavailable(ident):
        raise AppError("TRACK_NOT_SCRIPTABLE", "Lade den Titel zuerst in Musik.", 422)

    with monkeypatch.context() as context:
        context.setattr(adapter, "read_rating", unavailable)
        response = client.put(
            f"/api/v1/tracks/{track['id']}/rating", json=rate_body(client, track), headers=headers
        )
        assert response.status_code == 422
        assert response.json()["error"]["details"]["track"]["ratingCapability"] == "unavailable"
        current = client.get(f"/api/v1/tracks/{track['id']}").json()
        assert current["ratingRaw"] == track["ratingRaw"]
        assert current["capabilityReason"] == "Lade den Titel zuerst in Musik."
    client.post("/api/v1/library/refresh", json={}, headers=headers)
    assert client.get(f"/api/v1/tracks/{track['id']}").json()["ratingCapability"] == "writable"
