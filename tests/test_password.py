import sqlite3
import time

import pytest
from conftest import HOST_KEY, browser_login
from itunesremote.auth import Auth, token_hash


def test_password_survives_restart_build_change_and_new_host_key(tmp_path, monkeypatch):
    path = tmp_path / "auth.sqlite3"
    first = Auth(path, "first-runtime-key")
    password = first.web_password
    assert len(password) == 24
    sid, _ = first.login(password)
    owner = first.authenticate("", sid).owner
    first.close()
    monkeypatch.setenv("ITUNESREMOTE_APP_BUILD", "next-version")

    def no_regeneration(*args):
        raise AssertionError("An update must reuse the stored password")

    monkeypatch.setattr("itunesremote.auth.secrets.token_urlsafe", no_regeneration)
    second = Auth(path, "different-runtime-key")
    try:
        assert second.web_password == password
        assert second.authenticate("", sid).owner == owner
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        second.close()


def test_password_migration_preserves_existing_sessions_and_devices(tmp_path):
    path = tmp_path / "auth.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE sessions (hash TEXT PRIMARY KEY, owner TEXT, csrf TEXT, expires REAL);
            CREATE TABLE devices (id TEXT PRIMARY KEY, name TEXT, revoked INTEGER DEFAULT 0);
            CREATE TABLE credentials (hash TEXT PRIMARY KEY, device TEXT, kind TEXT, expires REAL);
        """)
        db.execute("INSERT INTO sessions VALUES (?,?,?,?)", (token_hash("old-session"), "owner", "csrf", time.time() + 1000))
        db.execute("INSERT INTO devices VALUES ('old-device', 'Existing device', 0)")
        db.execute(
            "INSERT INTO credentials VALUES (?,?,?,?)",
            (token_hash("old-token"), "old-device", "access", time.time() + 1000),
        )
    auth = Auth(path, HOST_KEY)
    try:
        assert auth.web_password
        assert auth.authenticate("", "old-session").owner == "owner"
        assert auth.authenticate("old-token", "").owner == "old-device"
        assert len(auth.devices()) == 1
    finally:
        auth.close()


@pytest.mark.parametrize("password", [None, "", "incorrect", "a" * 129, 123, [], {}])
def test_wrong_or_malformed_password_never_creates_session(client, password):
    response = client.post("/api/v1/auth/login", json={"password": password}, headers={"Origin": "http://testserver"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_PASSWORD"
    assert "set-cookie" not in response.headers
    assert client.get("/api/v1/status").status_code == 401


def test_password_is_only_retrievable_by_mac_host(client):
    assert client.get("/api/v1/auth/password").status_code == 401
    response = client.get("/api/v1/auth/password", headers={"Authorization": f"Bearer {HOST_KEY}"})
    assert response.status_code == 200
    password = response.json()["password"]
    assert response.headers["cache-control"] == "no-store"
    headers = browser_login(client)
    assert client.get("/api/v1/auth/password").status_code == 403
    device = client.post("/api/v1/auth/devices", json={"name": "Device"}, headers=headers).json()
    assert client.get(
        "/api/v1/auth/password", headers={"Authorization": f"Bearer {device['accessToken']}"}
    ).status_code == 403
    assert password not in client.get("/api/v1/status").text
    assert password not in client.get("/api/v1/openapi.json").text


@pytest.mark.parametrize("origin", [None, "https://attacker.example", "http://localhost"])
def test_password_login_requires_exact_browser_origin(client, origin):
    password = client.app.state.auth.web_password
    headers = {"Origin": origin} if origin else {}
    response = client.post("/api/v1/auth/login", json={"password": password}, headers=headers)
    assert response.status_code == 403
    assert "set-cookie" not in response.headers


def test_password_login_session_csrf_logout_and_relogin(client):
    password = client.app.state.auth.web_password
    origin = {"Origin": "http://testserver"}
    response = client.post("/api/v1/auth/login", json={"password": password}, headers=origin)
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert "Max-Age=43200" in response.headers["set-cookie"]
    assert client.get("/api/v1/tracks").status_code == 200
    assert client.post("/api/v1/library/refresh", json={}, headers=origin).status_code == 403
    csrf = response.json()["csrfToken"]
    headers = {**origin, "X-CSRF-Token": csrf}
    assert client.post("/api/v1/library/refresh", json={}, headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code == 200
    assert client.get("/api/v1/tracks").status_code == 401
    again = client.post("/api/v1/auth/login", json={"password": password}, headers=origin)
    assert again.status_code == 200
    assert again.json()["csrfToken"] != csrf


def test_password_login_is_rate_limited_without_logging_password(client, caplog):
    password = client.app.state.auth.web_password
    for _ in range(30):
        assert client.post(
            "/api/v1/auth/login", json={"password": "incorrect"}, headers={"Origin": "http://testserver"}
        ).status_code == 401
    response = client.post(
        "/api/v1/auth/login", json={"password": password}, headers={"Origin": "http://testserver"}
    )
    assert response.status_code == 429
    assert password not in caplog.text
    assert password not in response.text
