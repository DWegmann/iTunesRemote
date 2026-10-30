"""Isolated demo server for browser tests; never opens the real Music library."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from itunesremote.__main__ import main

with tempfile.TemporaryDirectory(prefix="itunesremote-browser-") as folder:
    os.environ["ITUNESREMOTE_HOST_KEY"] = "isolated-ui-tests-only"
    sys.argv = ["itunesremote", "--demo", "--host", "127.0.0.1", "--port", "18766", "--data-dir", folder]
    main()
