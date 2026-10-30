#!/usr/bin/env python3
"""Build a self-contained app with a native host, Python runtime and static web UI."""

from __future__ import annotations

import argparse
import builtins
import importlib.metadata
import json
import os
import platform
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = ROOT / "dist"
SIGNING_CONFIG = ROOT / ".local/signing.json"


def run(args: list[str], **kwargs):
    print("Build:", args[0], flush=True)
    subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def signing_identity(requested: str | None, configuration: dict) -> tuple[str, str]:
    selected = requested or os.environ.get("ITUNESREMOTE_SIGN_IDENTITY") or configuration.get("identity")
    if selected == "-":
        return "-", "ad-hoc"
    listing = subprocess.check_output(
        ["/usr/bin/security", "find-identity", "-v", "-p", "codesigning"], text=True,
    )
    identities = re.findall(r'^\s*\d+\)\s+([A-Fa-f0-9]{40})\s+"([^"]+)"', listing, re.MULTILINE)
    if selected:
        identities = [(fingerprint, name) for fingerprint, name in identities
                      if selected.casefold() == fingerprint.casefold() or selected == name]
    if len(identities) != 1:
        if selected:
            raise ValueError("Die festgelegte Signaturidentität fehlt oder ist ungültig. Bitte prüfe den Schlüsselbund.")
        raise ValueError(
            "Bitte wähle eine gültige Signatur mit --identity. Der Build wechselt nicht automatisch zu Ad-hoc. "
            "Für einen absichtlichen Testbuild ist --identity - verfügbar."
        )
    fingerprint, name = identities[0]
    kind = next((kind for kind in ("Developer ID Application", "Apple Development", "Apple Distribution")
                 if name.startswith(kind + ":")), "certificate")
    return fingerprint.upper(), kind


def code_identity(path: Path) -> tuple[str, str | None]:
    result = subprocess.run(
        ["/usr/bin/codesign", "--display", "--verbose=4", "-r", "-", str(path)],
        check=True, capture_output=True, text=True,
    )
    output = result.stdout + result.stderr
    requirement = re.search(r"^#?\s*designated => (.+)$", output, re.MULTILINE)
    if requirement is None:
        raise ValueError("Die Signatur enthält keine prüfbare App-Identität.")
    team = re.search(r"^TeamIdentifier=(.+)$", output, re.MULTILINE)
    return requirement[1], team[1] if team else None


def check_signing_continuity(configuration: dict, identity: str, requirements: dict):
    if identity == "-":
        return
    if any(re.search(r"\bcdhash\b", requirement) for requirement in requirements.values()):
        raise ValueError("Die Signaturidentität ist an einen einzelnen Build gebunden.")
    if configuration.get("identity") == identity and configuration.get("requirements"):
        if configuration["requirements"] != requirements:
            raise ValueError("Die gespeicherte App-Identität hat sich geändert. Der bisherige Build bleibt erhalten.")


def python_minimum() -> str:
    framework = sysconfig.get_config_var("PYTHONFRAMEWORKPREFIX")
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    library = Path(framework or "/Library/Frameworks") / f"Python.framework/Versions/{version}/Python"
    if not library.exists():
        library = Path(sysconfig.get_config_var("LIBDIR")) / sysconfig.get_config_var("LDLIBRARY")
    output = subprocess.check_output(["/usr/bin/otool", "-l", str(library)], text=True)
    versions = re.findall(r"\bminos ([\d.]+)", output)
    versions += re.findall(r"\bversion ([\d.]+)\n\s+sdk", output)
    return max(["14.0", *versions], key=lambda v: tuple(int(x) for x in v.split(".")))


def notices(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    for package in [
        "starlette",
        "uvicorn",
        "anyio",
        "idna",
        "typing_extensions",
        "click",
        "h11",
        "pyobjc-core",
        "pyobjc-framework-Cocoa",
        "pyobjc-framework-iTunesLibrary",
        "pyobjc-framework-ScriptingBridge",
        "pyobjc-framework-StoreKit",
        "pyinstaller",
    ]:
        distribution = importlib.metadata.distribution(package)
        for file in distribution.files or []:
            if ".dist-info/" in str(file) and any(
                token in str(file).lower() for token in ("license", "copying")
            ):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = destination / package / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    # Some PyObjC wheels omit their common project license. Include the license
    # shipped with the Cocoa wheel for the complete PyObjC distribution.
    cocoa_license = destination / "pyobjc-framework-Cocoa/LICENSE.txt"
    if cocoa_license.exists():
        shutil.copy2(cocoa_license, destination / "PyObjC-LICENSE.txt")
    # Homebrew runtimes may bundle additional shared libraries. Include the
    # installed notices when they are present; system frameworks stay on macOS.
    for prefix in (Path("/opt/homebrew/opt"), Path("/usr/local/opt")):
        for package in ("openssl@3", "xz", "zstd", "mpdecimal", "sqlite"):
            folder = prefix / package
            for name in ("LICENSE", "LICENSE.txt", "COPYING", "COPYING.0BSD", "COPYING.LGPLv2.1"):
                source = folder / name
                if source.is_file():
                    target = destination / package / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    for package in ["react", "react-dom", "scheduler", "lucide-react"]:
        folder = ROOT / "web/node_modules" / package
        for source in folder.glob("LICENSE*"):
            target = destination / package / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    shutil.copy2(ROOT / "THIRD_PARTY_NOTICES.md", destination / "README.md")
    # Include the embedded Python runtime's full license as well.
    for file in [
        Path(sys.base_prefix) / "LICENSE.txt",
        Path(sys.base_prefix) / "Resources/English.lproj/License.rtf",
    ]:
        if file.is_file():
            shutil.copy2(file, destination / file.name)
    builtins.license._Printer__setup()
    (destination / "Python-license.txt").write_text("\n".join(builtins.license._Printer__lines) + "\n")


def write_icns(iconset: Path, destination: Path):
    # ICNS supports embedded PNG representations. Use explicit sizes instead of
    # depending on iconutil's validation, which varies between SDK installations.
    entries = [
        (b"ic07", "icon_128x128.png"),
        (b"ic08", "icon_256x256.png"),
        (b"ic09", "icon_512x512.png"),
        (b"ic10", "icon_512x512@2x.png"),
    ]
    chunks = []
    for kind, filename in entries:
        png = (iconset / filename).read_bytes()
        chunks.append(kind + struct.pack(">I", len(png) + 8) + png)
    payload = b"".join(chunks)
    destination.write_bytes(b"icns" + struct.pack(">I", len(payload) + 8) + payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-web", action="store_true")
    parser.add_argument(
        "--identity", help="Signing identity; default: pinned certificate or the sole valid identity; '-' is ad-hoc"
    )
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("The app bundle must be built on macOS")
    configuration = json.loads(SIGNING_CONFIG.read_text()) if SIGNING_CONFIG.exists() else {}
    try:
        identity, signing_kind = signing_identity(args.identity, configuration)
    except ValueError as exc:
        parser.error(str(exc))
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    if not args.skip_web:
        if not (ROOT / "web/node_modules").exists():
            run(["npm", "--prefix", str(ROOT / "web"), "ci"])
        run(["npm", "--prefix", str(ROOT / "web"), "run", "build"])
    minimum = python_minimum()
    environment = dict(os.environ)
    environment["PYINSTALLER_CONFIG_DIR"] = str(BUILD / "pyinstaller-cache")
    environment["ITUNESREMOTE_MIN_MACOS"] = minimum
    environment.pop("ITUNESREMOTE_SIGN_IDENTITY", None)
    if identity != "-":
        environment["ITUNESREMOTE_SIGN_IDENTITY"] = identity
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--distpath",
            str(BUILD / "service-dist"),
            "--workpath",
            str(BUILD / "pyinstaller"),
            str(ROOT / "macos/service.spec"),
        ],
        env=environment,
    )
    staging = BUILD / "app/iTunesRemote.app"
    if staging.exists():
        shutil.rmtree(staging)
    macos, resources, helpers = (staging / "Contents" / p for p in ("MacOS", "Resources", "Helpers"))
    for folder in (macos, resources, helpers):
        folder.mkdir(parents=True, exist_ok=True)
    info = plistlib.loads((ROOT / "macos/Info.plist").read_bytes())
    info["LSMinimumSystemVersion"] = minimum
    (staging / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    (staging / "Contents/PkgInfo").write_bytes(b"APPL????")
    shutil.copytree(
        BUILD / "service-dist/iTunesRemoteService.app", helpers / "iTunesRemoteService.app", symlinks=True
    )
    run(
        [
            "/usr/bin/swiftc",
            "-parse-as-library",
            "-swift-version",
            "5",
            "-O",
            "-target",
            f"{platform.machine()}-apple-macosx{minimum}",
            "-module-cache-path",
            str(BUILD / "swift-module-cache"),
            str(ROOT / "macos/iTunesRemote.swift"),
            str(ROOT / "macos/LibraryProgress.swift"),
            "-o",
            str(macos / "iTunesRemote"),
        ]
    )
    iconset = BUILD / "AppIcon.iconset"
    run(
        [
            "/usr/bin/swift",
            "-module-cache-path",
            str(BUILD / "swift-module-cache"),
            str(ROOT / "macos/Icon.swift"),
            str(iconset),
        ]
    )
    write_icns(iconset, resources / "AppIcon.icns")
    notices(resources / "ThirdPartyNotices")
    sys.path.insert(0, str(ROOT / "backend"))
    from itunesremote.openapi import schema

    (resources / "openapi.json").write_text(json.dumps(schema(), indent=2, ensure_ascii=False) + "\n")
    run(
        [
            "/usr/bin/codesign",
            "--force",
            "--sign",
            identity,
            "--options",
            "runtime",
            "--entitlements",
            str(ROOT / "macos/Entitlements.plist"),
            str(staging),
        ]
    )
    run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(staging)])
    app_requirement, app_team = code_identity(staging)
    helper_requirement, helper_team = code_identity(helpers / "iTunesRemoteService.app")
    requirements = {"app": app_requirement, "service": helper_requirement}
    check_signing_continuity(configuration, identity, requirements)
    if identity != "-" and (not app_team or app_team == "not set" or helper_team != app_team):
        parser.error("App und Hilfsprozess besitzen keine gemeinsame Signaturidentität.")
    target = DIST / staging.name
    if target.exists():
        shutil.rmtree(target)
    shutil.move(staging, target)
    details = {
        "version": "0.1.0",
        "architecture": platform.machine(),
        "minimumMacOS": minimum,
        "build": info["CFBundleVersion"],
        "signing": signing_kind,
        "signingIdentity": identity,
        "teamIdentifier": app_team,
        "requirements": requirements,
        "notarized": False,
    }
    (DIST / "build-info.json").write_text(json.dumps(details, indent=2) + "\n")
    if identity != "-":
        SIGNING_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        SIGNING_CONFIG.write_text(json.dumps({"identity": identity, "requirements": requirements}, indent=2) + "\n")
    print(
        f"Fertig: {target}\nmacOS >= {minimum}; {platform.machine()}; {details['signing']}; nicht notarisiert."
    )


if __name__ == "__main__":
    main()
