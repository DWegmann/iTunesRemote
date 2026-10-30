"""Exercise the actual Swift progress reducer without starting Music or the app."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("swiftc"), reason="Requires Swift on macOS")
def test_native_progress_recovers_completion_and_rejects_old_events(tmp_path):
    root = Path(__file__).resolve().parents[1]
    executable = tmp_path / "progress-tests"
    subprocess.run(
        [
            "swiftc",
            "-parse-as-library",
            "-module-cache-path",
            str(tmp_path / "module-cache"),
            str(root / "macos/LibraryProgress.swift"),
            str(root / "tests/LibraryProgressTests.swift"),
            "-o",
            str(executable),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    subprocess.run(
        [str(executable), str(root / "tests/import_progress_cases.json")],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
