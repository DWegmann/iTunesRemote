import pytest
from itunesremote.api import create_app
from starlette.testclient import TestClient

HOST_KEY = "host-key-for-isolated-tests-only"


@pytest.fixture
def client(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><body>Test UI</body></html>")
    app = create_app(tmp_path / "data", web, HOST_KEY, "demo")
    with TestClient(app) as client:
        yield client


def browser_login(client):
    password = client.get(
        "/api/v1/auth/password", headers={"Authorization": f"Bearer {HOST_KEY}"}
    ).json()["password"]
    response = client.post(
        "/api/v1/auth/login", json={"password": password}, headers={"Origin": "http://testserver"}
    )
    assert response.status_code == 200
    return {"Origin": "http://testserver", "X-CSRF-Token": response.json()["csrfToken"]}


@pytest.fixture
def browser(client):
    return client, browser_login(client)


def rate_body(client, track, stars=5, request_id="test-request-0001"):
    status = client.get("/api/v1/status").json()
    return {
        "stars": stars,
        "libraryScope": status["libraryScope"],
        "expectedRevision": track["ratingRevision"],
        "requestId": request_id,
    }
