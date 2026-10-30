#!/usr/bin/env python3
"""Verify the actual Mac host samples only its own unresponsive fake helper."""

from __future__ import annotations

import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from smoke_bundle import APP, read_ready

FAKE_HELPER = r"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

folder = Path(os.environ["ITUNESREMOTE_DATA_DIR"])
(folder / "helper.pid").write_text(str(os.getpid()))
parent = os.getppid()

def watch_parent():
    while os.getppid() == parent:
        time.sleep(0.2)
    os._exit(0)

threading.Thread(target=watch_parent, daemon=True).start()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps({"code": "isolated-diagnostics-test"}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/v1/auth/password":
            body = json.dumps({"password": "isolated-diagnostics-test"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        # Withhold status responses; never open a library or ask for consent.
        time.sleep(60)

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(json.dumps({"event": "library-progress", "stage": "native-cleanup",
    "completed": 0, "total": 50000, "sequence": 1,
    "elapsedSeconds": 0, "stageElapsedSeconds": 0, "idleSeconds": 0}), flush=True)
print(json.dumps({"event": "ready", "port": server.server_address[1]}), flush=True)
server.serve_forever()
"""


def main():
    with tempfile.TemporaryDirectory(prefix="itunesremote-diagnostics-") as folder:
        root = Path(folder)
        bundle = root / "DiagnosticsTest.app/Contents"
        binary = bundle / "MacOS/iTunesRemote"
        helper = bundle / "Helpers/iTunesRemoteService.app/Contents/MacOS/iTunesRemoteService"
        binary.parent.mkdir(parents=True)
        helper.parent.mkdir(parents=True)
        shutil.copy2(APP / "Contents/MacOS/iTunesRemote", binary)
        shutil.copy2(APP / "Contents/Info.plist", bundle / "Info.plist")
        helper.write_text(f"#!{sys.executable}\n" + FAKE_HELPER)
        helper.chmod(0o700)
        data = root / "data"
        host = subprocess.Popen(
            [str(binary), "--demo", "--no-browser"],
            env={**os.environ, "ITUNESREMOTE_DATA_DIR": str(data)},
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            read_ready(host)
            deadline = time.monotonic() + 40
            report = data / "import-native.sample.txt"
            while time.monotonic() < deadline:
                assert host.poll() is None, "Diagnostics host exited"
                if report.exists() and "Call graph:" in report.read_text(errors="replace"):
                    helper_pid = int((data / "helper.pid").read_text())
                    assert f"(pid {helper_pid})" in report.read_text(errors="replace")
                    assert stat.S_IMODE(report.stat().st_mode) == 0o600
                    print(
                        "Diagnose: Mac-Host erfasst seinen nicht antwortenden Test-Hilfsprozess automatisch."
                    )
                    return
                time.sleep(0.2)
            messages = (
                (data / "import-native.log").read_text()
                if (data / "import-native.log").exists()
                else "No sample attempted"
            )
            raise AssertionError(messages)
        finally:
            host.terminate()
            host.wait(timeout=10)
            pid_file = data / "helper.pid"
            if pid_file.exists():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGTERM)
                except ProcessLookupError:
                    pass


if __name__ == "__main__":
    main()
