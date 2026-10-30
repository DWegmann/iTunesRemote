# PyInstaller builds a real nested .app so the helper has stable privacy usage strings.
import os
from pathlib import Path

root = Path(SPECPATH).parent
identity = os.environ.get("ITUNESREMOTE_SIGN_IDENTITY") or None
minimum = os.environ.get("ITUNESREMOTE_MIN_MACOS", "14.0")
analysis = Analysis(
    [str(root / "scripts/service_entry.py")],
    pathex=[str(root / "backend")],
    binaries=[],
    datas=[(str(root / "web/dist"), "web")],
    hiddenimports=["iTunesLibrary", "ScriptingBridge", "StoreKit", "AppKit", "uvicorn.logging",
                   "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl", "uvicorn.lifespan.on"],
    excludes=["pytest", "httpx", "httpx2", "PyInstaller", "ruff", "tkinter"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name="iTunesRemoteService",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, codesign_identity=identity,
    entitlements_file=str(root / "macos/Entitlements.plist"),
)
collect = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="iTunesRemoteService")
app = BUNDLE(
    collect, name="iTunesRemoteService.app", version="0.1.0",
    bundle_identifier="de.wegmann.iTunesRemote.service",
    info_plist={
        "LSUIElement": True,
        "LSMinimumSystemVersion": minimum,
        "NSAppleMusicUsageDescription": "iTunesRemote zeigt Titel, Playlists und Bewertungen deiner Musikbibliothek an.",
        "NSAppleEventsUsageDescription": "iTunesRemote speichert die von dir gewählten Sternebewertungen in der Musik-App.",
        "NSLocalNetworkUsageDescription": "iTunesRemote stellt die Weboberfläche für deine anderen Geräte im lokalen Netzwerk bereit.",
    },
)
