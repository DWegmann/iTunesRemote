#!/usr/bin/env python3
"""Exercise only demo data using the bundled runtime, then check the native host."""

from __future__ import annotations

import json
import os
import secrets
import selectors
import socket
import stat
import subprocess
import tempfile
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "dist/iTunesRemote.app"
HELPER = APP / "Contents/Helpers/iTunesRemoteService.app/Contents/MacOS/iTunesRemoteService"
OPENER = build_opener(ProxyHandler({}))


def request(port, path, key=None, method="GET", body=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = Request(
        f"http://127.0.0.1:{port}{path}",
        method=method,
        headers=headers,
        data=json.dumps(body or {}).encode() if method != "GET" else None,
    )
    with OPENER.open(req, timeout=5) as response:
        return json.load(response)


def read_ready(process, require_permissions=False, return_event=False):
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + 20
    try:
        while time.monotonic() < deadline:
            if selector.select(timeout=0.2):
                line = process.stdout.readline()
                if not line:
                    raise RuntimeError("Bundled service exited before readiness")
                message = json.loads(line)
                if message.get("event") == "ready":
                    if require_permissions:
                        assert message.get("permissionCheck") is True, (
                            "Native permission request did not complete"
                        )
                    return message if return_event else message["port"]
            if process.poll() is not None:
                raise RuntimeError("Bundled service exited before readiness")
        raise TimeoutError("Bundled service did not become ready")
    finally:
        selector.close()


def main():
    diagnostic = subprocess.check_output([str(HELPER), "--diagnose"], text=True)
    result = json.loads(diagnostic)
    assert result["nativeBindings"] and result["mediaUsageDescription"]
    assert result["mediaAuthorizationPreflight"]
    assert result["bundleId"] == "de.wegmann.iTunesRemote.service"
    print("Paket: Native Frameworks und Datenschutzhinweise geladen.")
    with tempfile.TemporaryDirectory(prefix="itunesremote-bundle-") as folder:
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            conflict = subprocess.run(
                [str(HELPER), "--demo", "--host", "127.0.0.1", "--port", str(port), "--data-dir", folder],
                capture_output=True, text=True, timeout=10,
            )
        assert conflict.returncode == 2
        assert json.loads(conflict.stdout)["code"] == "PORT_IN_USE"
        assert f"Port {port}" in conflict.stderr
        print("Paket: Belegter Port wird verständlich gemeldet; kein Wechsel der Adresse.")
        key = secrets.token_urlsafe(32)
        process = subprocess.Popen(
            [str(HELPER), "--demo", "--port", "0", "--data-dir", folder],
            env={**os.environ, "ITUNESREMOTE_HOST_KEY": key},
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            ready = read_ready(process, return_event=True)
            port = ready["port"]
            assert request(port, "/health")["ok"]
            password = request(port, "/api/v1/auth/password", key)["password"]
            for url in ready["networkUrls"]:
                browser = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))
                origin = url.rstrip("/")
                with browser.open(url + "health", timeout=5) as response:
                    assert json.load(response)["ok"]
                with browser.open(url, timeout=5) as response:
                    assert b"/assets/" in response.read()
                try:
                    browser.open(url + "api/v1/tracks", timeout=5)
                    raise AssertionError("Unauthenticated LAN library access accepted")
                except HTTPError as exc:
                    assert exc.code == 401
                exchange = Request(
                    url + "api/v1/auth/login", data=json.dumps({"password": password}).encode(),
                    headers={"Content-Type": "application/json", "Origin": origin},
                )
                with browser.open(exchange, timeout=5) as response:
                    assert json.load(response)["csrfToken"]
                with browser.open(url + "api/v1/tracks", timeout=5) as response:
                    assert json.load(response)["total"] == 34
            if ready["networkUrls"]:
                print("Paket: LAN-Verbindung, Webdateien, Passwortanmeldung und Cookie-Zugriff über private IPv4 geprüft.")
            else:
                print("Paket: Keine private IPv4-Adresse verfügbar; LAN-Prüfung ausgelassen.")
            try:
                request(port, "/api/v1/tracks")
                raise AssertionError("Unauthenticated library access accepted")
            except HTTPError as exc:
                assert exc.code == 401
            page = request(port, "/api/v1/tracks", key)
            assert page["total"] == 34
            status = request(port, "/api/v1/status", key)
            assert status["refreshing"] is False
            assert status["progress"]["stage"] == "done"
            assert status["progress"]["total"] == 34
            assert status["progress"]["sequence"] > 0
            assert status["progress"]["runId"]
            assert status["progress"]["elapsedSeconds"] >= 0
            log = Path(folder) / "import.log"
            records = [json.loads(line) for line in log.read_text().splitlines()]
            assert records[-1]["stage"] == "done"
            assert any(record.get("stage") == "snapshot-tracks" for record in records)
            newest = request(port, "/api/v1/tracks?sort=addedDate", key)["items"]
            oldest = request(port, "/api/v1/tracks?sort=addedDateAsc", key)["items"]
            assert newest[0]["title"] == oldest[-1]["title"] == "Familiar"
            assert oldest[0]["title"] == newest[-1]["title"] == "15 Step"
            assert all(track["addedDate"] for track in newest)
            track = page["items"][0]
            data = {
                "stars": 5,
                "libraryScope": page["libraryScope"],
                "expectedRevision": track["ratingRevision"],
                "requestId": "bundled-smoke-request",
            }
            result = request(port, f"/api/v1/tracks/{track['id']}/rating", key, "PUT", data)
            assert result["track"]["ratingRaw"] == 100 and result["state"] == "confirmed"
            with OPENER.open(f"http://127.0.0.1:{port}/", timeout=5) as response:
                assert b"/assets/" in response.read()
            print("Paket: HTTP-Dienst, Webdateien, Zugriffsschutz, Fortschrittsstatus, Hinzufügedatum und Demobewertung geprüft.")
            queued = request(port, "/api/v1/rating-queue", key, "POST", {
                "libraryScope": page["libraryScope"],
                "items": [
                    {"trackId": result["track"]["id"], "stars": 2,
                     "expectedRevision": result["track"]["ratingRevision"], "requestId": "bundled-queue-first"},
                    {"trackId": page["items"][1]["id"], "stars": 4,
                     "expectedRevision": page["items"][1]["ratingRevision"], "requestId": "bundled-queue-second"},
                ],
            })
            assert len(queued["items"]) == 2
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                queued = request(port, "/api/v1/rating-queue?libraryScope=" + page["libraryScope"]
                                 + "&ids=bundled-queue-first,bundled-queue-second", key)
                if all(job["state"] == "confirmed" for job in queued["items"]) and len(queued["items"]) == 2:
                    break
                time.sleep(0.05)
            assert [job["result"]["track"]["ratingRaw"] for job in queued["items"]] == [40, 80]
            assert stat.S_IMODE((Path(folder) / "rating-queue.sqlite3").stat().st_mode) == 0o600
            print("Paket: Dauerhafte Bewertungswarteschlange, Batch-Verarbeitung und private Dateirechte bestätigt.")
        finally:
            process.terminate()
            process.wait(timeout=15)

        new_key = secrets.token_urlsafe(32)
        restarted = subprocess.Popen(
            [str(HELPER), "--demo", "--port", "0", "--data-dir", folder],
            env={**os.environ, "ITUNESREMOTE_HOST_KEY": new_key, "ITUNESREMOTE_APP_BUILD": "upgrade-check"},
            stdout=subprocess.PIPE, text=True,
        )
        try:
            port = read_ready(restarted)
            assert request(port, "/api/v1/auth/password", new_key)["password"] == password
            print("Paket: Dasselbe Webpasswort nach Neustart mit neuem Hostschlüssel und geänderter Buildkennung.")
        finally:
            restarted.terminate()
            restarted.wait(timeout=15)

    with tempfile.TemporaryDirectory(prefix="itunesremote-host-") as folder:
        host = subprocess.Popen(
            [str(APP / "Contents/MacOS/iTunesRemote"), "--demo", "--no-browser", "--request-permissions"],
            env={**os.environ, "ITUNESREMOTE_DATA_DIR": folder, "ITUNESREMOTE_PORT": "0"},
            stdout=subprocess.PIPE,
            text=True,
        )
        child_pid = None
        try:
            # This event is emitted only after the host successfully authenticates
            # via URLSession and retrieves the persistent web password.
            ready = read_ready(host, require_permissions=True, return_event=True)
            assert ready["passwordAvailable"] is True
            bootstrap_port = ready["port"]
            assert request(bootstrap_port, "/health")["ok"]
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                assert host.poll() is None, "Native host exited"
                children = subprocess.run(
                    ["/usr/bin/pgrep", "-P", str(host.pid)], capture_output=True, text=True
                )
                for child in children.stdout.split():
                    listening = subprocess.run(
                        ["/usr/sbin/lsof", "-nP", "-a", "-p", child, "-iTCP", "-sTCP:LISTEN", "-Fn"],
                        capture_output=True,
                        text=True,
                    )
                    endpoints = [
                        line[1:] for line in listening.stdout.splitlines()
                        if line.startswith(("n127.0.0.1:", "n*:"))
                    ]
                    if endpoints:
                        port = int(endpoints[0].rsplit(":", 1)[1])
                        assert request(port, "/health")["ok"]
                        child_pid = int(child)
                        break
                if child_pid:
                    break
                time.sleep(0.2)
            assert child_pid, "Native host did not start its bundled service"
            print(
                "Mac-App: Berechtigungsabfrage im Demomodus und geschützter Passwortabruf über URLSession bestätigt."
            )
        finally:
            host.terminate()
            host.wait(timeout=10)
        if child_pid:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                try:
                    request(port, "/health")
                except (URLError, ConnectionError, TimeoutError):
                    print("Mac-App: Dienst beendet sich nach Ende des Hosts.")
                    break
                time.sleep(0.2)
            else:
                os.kill(child_pid, 15)
                raise AssertionError("Orphaned service after host termination")


if __name__ == "__main__":
    main()
