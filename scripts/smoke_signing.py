#!/usr/bin/env python3
"""Verify that changed app and helper builds retain their certificate identity."""

from __future__ import annotations

import json
import plistlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from build_app import ROOT, code_identity


def code_hash(path: Path) -> str:
    result = subprocess.run(
        ["/usr/bin/codesign", "--display", "--verbose=4", str(path)],
        check=True, capture_output=True, text=True,
    )
    return re.search(r"^CDHash=(.+)$", result.stdout + result.stderr, re.MULTILINE)[1]


def main():
    original = ROOT / "dist/iTunesRemote.app"
    details = json.loads((ROOT / "dist/build-info.json").read_text())
    identity = details["signingIdentity"]
    assert identity != "-", "A certificate-signed build is required"
    helper = Path("Contents/Helpers/iTunesRemoteService.app")
    with tempfile.TemporaryDirectory(prefix="itunesremote-signing-") as folder:
        changed = Path(folder) / "iTunesRemote.app"
        shutil.copytree(original, changed, symlinks=True)
        for bundle in (changed / helper, changed):
            info_file = bundle / "Contents/Info.plist"
            info = plistlib.loads(info_file.read_bytes())
            info["CFBundleVersion"] = str(info.get("CFBundleVersion", "1")) + ".1"
            info_file.write_bytes(plistlib.dumps(info))
            subprocess.run(
                ["/usr/bin/codesign", "--force", "--sign", identity, "--options", "runtime",
                 "--entitlements", str(ROOT / "macos/Entitlements.plist"), str(bundle)],
                check=True, capture_output=True, text=True,
            )
        for relative in (Path("."), helper):
            before, after = original / relative, changed / relative
            before_requirement, before_team = code_identity(before)
            after_requirement, after_team = code_identity(after)
            assert before_team == after_team == details["teamIdentifier"]
            assert before_requirement == after_requirement
            assert code_hash(before) != code_hash(after), "The test must change the signed build"
            for target, requirement in ((after, before_requirement), (before, after_requirement)):
                subprocess.run(
                    ["/usr/bin/codesign", "--verify", "--strict", "-R", "=" + requirement, str(target)],
                    check=True, capture_output=True, text=True,
                )
        subprocess.run(
            ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(changed)], check=True,
        )
    print("Signatur: Geänderte App und Hilfsprozess erfüllen unverändert die bisherigen Identitätsanforderungen.")


if __name__ == "__main__":
    main()
