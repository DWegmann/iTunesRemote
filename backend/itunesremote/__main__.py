from __future__ import annotations

import argparse
import asyncio
import contextlib
import errno
import json
import os
import secrets
import signal
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from .api import create_app
from .network import lan_addresses


def main():
    parser = argparse.ArgumentParser(description="iTunesRemote local library service")
    parser.add_argument("--demo", action="store_true", help="Use isolated demo data instead of Music.app")
    parser.add_argument(
        "--port", type=int, default=os.environ.get("ITUNESREMOTE_PORT", "8765"),
        help="HTTP port (default: 8765 or ITUNESREMOTE_PORT); 0 selects a free port",
    )
    parser.add_argument(
        "--host", choices=("0.0.0.0", "127.0.0.1"), default="0.0.0.0",
        help="Listen on the local network (default); use 127.0.0.1 for this Mac only",
    )
    parser.add_argument(
        "--data-dir", type=Path, default=Path.home() / "Library/Application Support/iTunesRemote"
    )
    parser.add_argument("--web-dir", type=Path)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--parent-pid", type=int, help="Exit if the Mac host process terminates")
    parser.add_argument(
        "--diagnose", action="store_true", help="Verify bundled native bindings without accessing the library"
    )
    parser.add_argument(
        "--diagnose-permissions",
        action="store_true",
        help="Read authorization status without prompting or opening a library",
    )
    args = parser.parse_args()
    if sys.platform == "darwin" and not args.demo and not args.diagnose_permissions:
        from .permissions import initialize_native_app

        initialize_native_app()
    if args.diagnose_permissions:
        from .permissions import automation_status

        print(
            json.dumps(
                {"automationStatus": automation_status(ask=False)}
            )
        )
        return
    if args.diagnose:
        import AppKit
        import Foundation
        import iTunesLibrary
        import ScriptingBridge
        import StoreKit

        from .adapters import music_delegate_class
        from .permissions import media_authorization_status

        assert (
            AppKit.NSImage
            and iTunesLibrary.ITLibrary
            and ScriptingBridge.SBApplication
            and StoreKit.SKCloudServiceController
        )
        assert music_delegate_class().instancesRespondToSelector_(b"eventDidFail:withError:")
        print(
            json.dumps(
                {
                    "nativeBindings": True,
                    "mediaAuthorizationPreflight": isinstance(media_authorization_status(), int),
                    "bundleId": Foundation.NSBundle.mainBundle().bundleIdentifier(),
                    "mediaUsageDescription": bool(
                        Foundation.NSBundle.mainBundle().objectForInfoDictionaryKey_(
                            "NSAppleMusicUsageDescription"
                        )
                    ),
                }
            )
        )
        return
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    if args.web_dir:
        web_dir = args.web_dir
    elif getattr(sys, "frozen", False):
        web_dir = Path(sys._MEIPASS) / "web"
    else:
        web_dir = Path(__file__).resolve().parents[2] / "web/dist"
    host_key = os.environ.pop("ITUNESREMOTE_HOST_KEY", "") or secrets.token_urlsafe(32)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((args.host, args.port))
    except OSError as exc:
        sock.close()
        if exc.errno == errno.EADDRINUSE:
            code = "PORT_IN_USE"
            message = f"Port {args.port} ist bereits belegt. Bitte beende die andere App oder Dienstinstanz."
        else:
            code = "PORT_UNAVAILABLE"
            message = f"Port {args.port} konnte nicht geöffnet werden: {exc.strerror}."
        print(json.dumps({"event": "startup-error", "code": code, "message": message}), flush=True)
        parser.exit(2, message + "\n")
    port = sock.getsockname()[1]
    addresses = lan_addresses() if args.host == "0.0.0.0" else []
    network_urls = [f"http://{address}:{port}/" for address in addresses]
    app = create_app(
        args.data_dir,
        web_dir,
        host_key,
        "demo" if args.demo else "music",
        authorities={f"{host}:{port}" for host in ["127.0.0.1", "localhost", *addresses]},
        on_library_progress=lambda values: print(
            json.dumps({"event": "library-progress", **values}), flush=True
        ),
    )
    config = uvicorn.Config(
        app,
        log_level="warning",
        access_log=False,
        proxy_headers=False,
        timeout_keep_alive=5,
        limit_concurrency=40,
        loop="asyncio",
        http="h11",
        ws="none",
    )
    server = uvicorn.Server(config)

    def ready():
        while not server.started:
            if server.should_exit:
                return
            time.sleep(0.05)
        # Host readiness deliberately contains no browser code or authentication key.
        print(
            json.dumps(
                {
                    "event": "ready",
                    "port": port,
                    "serverId": app.state.library.server_id,
                    "networkUrls": network_urls,
                }
            ),
            flush=True,
        )
        if args.open_browser:
            # The browser signs in with the persistent password; URLs contain no credential.
            webbrowser.open(f"http://127.0.0.1:{port}/")
        if args.parent_pid:
            while True:
                if os.getppid() != args.parent_pid or server.should_exit:
                    if not server.should_exit:
                        os.kill(os.getpid(), signal.SIGTERM)
                    # A native consent dialog can outlive its HTTP request. Bound
                    # shutdown even when the framework's worker is still waiting.
                    # Healthy shutdown exits the process before this daemon wakes.
                    time.sleep(5)
                    os._exit(0)
                time.sleep(1)

    threading.Thread(target=ready, daemon=True, name="host-watchdog").start()
    async def serve():
        native_callbacks = None
        if sys.platform == "darwin" and not args.demo:
            from .permissions import service_native_callbacks

            native_callbacks = asyncio.create_task(service_native_callbacks())
        try:
            await server.serve(sockets=[sock])
        finally:
            if native_callbacks:
                native_callbacks.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await native_callbacks

    asyncio.run(serve())


if __name__ == "__main__":
    main()
