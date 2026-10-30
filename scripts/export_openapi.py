import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "backend"))
from itunesremote.openapi import schema  # noqa: E402 - resolve the source tree without an editable install

destination = root / "api/openapi.json"
destination.parent.mkdir(exist_ok=True)
destination.write_text(json.dumps(schema(), ensure_ascii=False, indent=2) + "\n")
print("API-Vertrag exportiert: api/openapi.json")
