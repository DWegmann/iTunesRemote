import json
import os
import selectors
import socket
import subprocess
import sys
from contextlib import contextmanager
from http.cookiejar import CookieJar
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

import pytest
from conftest import HOST_KEY
from itunesremote import __main__ as cli
from itunesremote import network
from itunesremote.api import create_app
from starlette.testclient import TestClient


def test_discovers_private_interface_addresses_without_dns(monkeypatch):
    interfaces = {
        "lo0": "127.0.0.1", "en0": "192.168.1.20", "en1": "10.0.0.2",
        "alias": "192.168.1.20", "public": "8.8.8.8", "unset": "0.0.0.0",
        "link": "169.254.10.2", "offline": None,
    }
    monkeypatch.setattr(socket, "if_nameindex", lambda: list(enumerate(interfaces)))

    def interface_address(fd, request, data):
        address = interfaces[data.split(b"\0", 1)[0].decode()]
        if address is None:
            raise OSError("No IPv4 address")
        return b"\0" * 20 + socket.inet_aton(address) + b"\0" * 232

    monkeypatch.setattr(network.fcntl, "ioctl", interface_address)
    assert network.lan_addresses() == ["10.0.0.2", "169.254.10.2", "192.168.1.20"]


def test_unavailable_interfaces_do_not_break_local_startup(monkeypatch):
    def unavailable():
        raise OSError("Interface discovery unavailable")

    monkeypatch.setattr(socket, "if_nameindex", unavailable)
    assert network.lan_addresses() == []


def test_lan_browser_requires_login_and_preserves_host_origin_and_csrf_checks(tmp_path):
    origin = "http://192.168.1.20:8765"
    app = create_app(
        tmp_path / "data", tmp_path / "web", HOST_KEY, "demo",
        authorities={"127.0.0.1:8765", "192.168.1.20:8765"},
    )
    with TestClient(app, base_url=origin) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/tracks").status_code == 401
        assert client.get("/health", headers={"Host": "attacker.example:8765"}).status_code == 421
        assert client.get("/health", headers={"Host": "192.168.1.99:8765"}).status_code == 421
        code = client.post(
            "http://127.0.0.1:8765/api/v1/auth/bootstrap", json={},
            headers={"Authorization": f"Bearer {HOST_KEY}"},
        ).json()["code"]
        response = client.post("/api/v1/auth/exchange", json={"code": code}, headers={"Origin": origin})
        assert response.status_code == 200
        csrf = response.json()["csrfToken"]
        assert client.get("/api/v1/tracks").json()["total"] == 34
        for headers in [{}, {"Origin": "http://127.0.0.1:8765", "X-CSRF-Token": csrf}, {"Origin": origin}]:
            assert client.post("/api/v1/library/refresh", json={}, headers=headers).status_code == 403
        headers = {"Origin": origin, "X-CSRF-Token": csrf}
        assert client.post("/api/v1/library/refresh", json={}, headers=headers).status_code == 200
        assert client.post("/api/v1/auth/bootstrap", json={}, headers=headers).status_code == 403
        assert client.post("/api/v1/auth/exchange", json={"code": code}, headers=headers).status_code == 401


@contextmanager
def demo_server(tmp_path, host=None, port=0):
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-m", "itunesremote", "--demo", "--data-dir", str(tmp_path / "data")]
    if host:
        command.extend(["--host", host])
    command.extend(["--port", str(port)])
    process = subprocess.Popen(
        command, cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "backend"), "ITUNESREMOTE_HOST_KEY": HOST_KEY},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            # Each progress line gets a bounded wait; the demo import contains only 34 tracks.
            for _ in range(100):
                assert selector.select(timeout=10), "Demo server did not become ready"
                line = process.stdout.readline()
                assert line, "Demo server exited before readiness"
                event = json.loads(line)
                if event.get("event") == "ready":
                    yield event
                    break
            else:
                raise AssertionError("Demo server emitted no ready event")
    finally:
        process.terminate()
        process.communicate(timeout=10)


@pytest.mark.parametrize(
    ("environment_port", "arguments", "expected"),
    [(None, [], 8765), ("23456", [], 23456), ("0", [], 0), ("23456", ["--port", "12345"], 12345)],
)
def test_cli_selects_stable_default_port_and_explicit_overrides(
    monkeypatch, environment_port, arguments, expected,
):
    if environment_port is None:
        monkeypatch.delenv("ITUNESREMOTE_PORT", raising=False)
    else:
        monkeypatch.setenv("ITUNESREMOTE_PORT", environment_port)
    monkeypatch.setattr(sys, "argv", ["itunesremote", "--demo", "--host", "127.0.0.1", *arguments])
    addresses = []

    class Bound(Exception):
        pass

    def bind(address):
        addresses.append(address)
        raise Bound

    monkeypatch.setattr(socket, "socket", lambda *args: SimpleNamespace(setsockopt=lambda *args: None, bind=bind))
    with pytest.raises(Bound):
        cli.main()
    assert addresses == [("127.0.0.1", expected)]


def test_cli_fixed_port_and_browser_session_survive_restart(tmp_path):
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
    origin = f"http://127.0.0.1:{port}"
    for restart in range(2):
        with demo_server(tmp_path, "127.0.0.1", port) as ready:
            assert ready["port"] == port
            if restart == 0:
                credentials = Request(
                    origin + "/api/v1/auth/password", headers={"Authorization": f"Bearer {HOST_KEY}"},
                )
                with opener.open(credentials, timeout=5) as response:
                    password = json.load(response)["password"]
                login = Request(
                    origin + "/api/v1/auth/login", data=json.dumps({"password": password}).encode(),
                    headers={"Content-Type": "application/json", "Origin": origin},
                )
                with opener.open(login, timeout=5) as response:
                    assert json.load(response)["csrfToken"]
            with opener.open(origin + "/api/v1/tracks", timeout=5) as response:
                assert json.load(response)["total"] == 34


def test_cli_busy_port_reports_error_without_changing_port(tmp_path):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = occupied.getsockname()[1]
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "itunesremote", "--demo", "--host", "127.0.0.1",
             "--port", str(port), "--data-dir", str(tmp_path / "unused")],
            cwd=root, env={**os.environ, "PYTHONPATH": str(root / "backend")},
            capture_output=True, text=True, timeout=10,
        )
    assert result.returncode == 2
    event = json.loads(result.stdout)
    assert event["event"] == "startup-error"
    assert event["code"] == "PORT_IN_USE"
    assert f"Port {port}" in event["message"]
    assert "bereits belegt" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "unused").exists()


def test_cli_can_keep_service_on_loopback(tmp_path):
    with demo_server(tmp_path, "127.0.0.1") as ready:
        assert ready["networkUrls"] == []
        opener = build_opener(ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{ready['port']}/health", timeout=5) as response:
            assert json.load(response) == {"ok": True}
        for address in network.lan_addresses():
            with pytest.raises(OSError):
                with socket.create_connection((address, ready["port"]), timeout=2):
                    pass


def test_cli_serves_authenticated_browser_over_real_lan_interface(tmp_path):
    with demo_server(tmp_path) as ready:
        if not ready["networkUrls"]:
            pytest.skip("No private IPv4 interface is available for the LAN connection test")
        opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
        origin = ready["networkUrls"][0].rstrip("/")

        def request(url, data=None, headers=None, method=None):
            req = Request(
                url, method=method,
                data=json.dumps(data).encode() if data is not None else None,
                headers={"Content-Type": "application/json", **(headers or {})},
            )
            with opener.open(req, timeout=5) as response:
                return json.load(response)

        assert request(f"{origin}/health") == {"ok": True}
        with pytest.raises(HTTPError) as denied:
            request(f"{origin}/api/v1/tracks")
        assert denied.value.code == 401
        password = request(
            f"http://127.0.0.1:{ready['port']}/api/v1/auth/password",
            headers={"Authorization": f"Bearer {HOST_KEY}"},
        )["password"]
        login = request(f"{origin}/api/v1/auth/login", {"password": password}, {"Origin": origin})
        assert request(f"{origin}/api/v1/auth/session")["kind"] == "cookie"
        page = request(f"{origin}/api/v1/tracks")
        track = page["items"][0]
        result = request(
            f"{origin}/api/v1/tracks/{track['id']}/rating",
            {"stars": 4, "libraryScope": page["libraryScope"], "expectedRevision": track["ratingRevision"],
             "requestId": "lan-demo-rating"},
            {"Origin": origin, "X-CSRF-Token": login["csrfToken"]}, "PUT",
        )
        assert result["state"] == "confirmed"
        assert result["track"]["ratingRaw"] == 80
