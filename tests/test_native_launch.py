"""Compile the actual native service controller with an isolated fake helper."""

import os
import plistlib
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

FAKE_SERVICE = r'''
import json
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

parent = os.getppid()

def watch_parent():
    while os.getppid() == parent:
        time.sleep(0.1)
    os._exit(0)

def terminate(signum, frame):
    # Keep the port occupied briefly to expose an immediate restart race.
    def delayed_exit():
        time.sleep(0.4)
        os._exit(0)
    threading.Thread(target=delayed_exit, daemon=True).start()

signal.signal(signal.SIGTERM, terminate)
threading.Thread(target=watch_parent, daemon=True).start()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        payload = {"password": "isolated-lifecycle-test"} if self.path.endswith("/password") else {
            "refreshing": False, "progress": None, "error": None,
        }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

server = ThreadingHTTPServer(("127.0.0.1", int(os.environ["ITUNESREMOTE_PORT"])), Handler)
folder = Path(os.environ["ITUNESREMOTE_DATA_DIR"])
with (folder / "launches").open("a") as log:
    log.write(str(os.getpid()) + "\n")
port = server.server_address[1]
print(json.dumps({"event": "ready", "port": port, "networkUrls": [f"http://127.0.0.1:{port}/"]}), flush=True)
server.serve_forever()
'''


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("swiftc"), reason="Requires Swift on macOS")
def test_native_restart_waits_until_previous_service_releases_fixed_port(tmp_path):
    root = Path(__file__).resolve().parents[1]
    bundle = tmp_path / "LifecycleTest.app/Contents"
    executable = bundle / "MacOS/LifecycleTest"
    executable.parent.mkdir(parents=True)
    (bundle / "Info.plist").write_bytes(plistlib.dumps({
        "CFBundleIdentifier": "de.wegmann.iTunesRemote.lifecycle-test",
        "CFBundleExecutable": "LifecycleTest", "CFBundleVersion": "isolated-test",
        "CFBundlePackageType": "APPL",
    }))
    # Use the production controller verbatim, with only the app's entry point removed.
    source = (root / "macos/iTunesRemote.swift").read_text()
    entry_point = "@main\nstruct ITunesRemoteApp: App"
    assert source.count(entry_point) == 1
    controller = tmp_path / "Controller.swift"
    controller.write_text(source.replace(entry_point, "struct ITunesRemoteApp: App"))
    subprocess.run(
        [
            "swiftc", "-parse-as-library", "-module-cache-path", str(tmp_path / "module-cache"),
            str(controller), str(root / "macos/LibraryProgress.swift"),
            str(root / "tests/ServiceLifecycleTests.swift"), "-o", str(executable),
        ],
        check=True, capture_output=True, text=True, timeout=90,
    )
    helper = bundle / "Helpers/iTunesRemoteService.app/Contents/MacOS/iTunesRemoteService"
    helper.parent.mkdir(parents=True)
    helper.write_text(f"#!{sys.executable}\n" + FAKE_SERVICE)
    helper.chmod(0o700)
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    subprocess.run(
        [str(executable), "--demo", "--no-browser"],
        env={**os.environ, "ITUNESREMOTE_DATA_DIR": str(tmp_path / "data"), "ITUNESREMOTE_PORT": str(port)},
        check=True, capture_output=True, text=True, timeout=30,
    )
