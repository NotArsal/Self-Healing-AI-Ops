"""Write the OpenAPI document to disk, for `make gen-client`.

Exists so client generation needs no running server: a codegen step that
depends on `uvicorn` being up is a codegen step that fails in CI and on a
teammate's machine. Importing the app and calling `app.openapi()` gives the
same document `/openapi.json` would serve.

The destination is derived from this file's location rather than passed in, so
the Makefile recipe stays one line and cannot drift from where the console
expects to find it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from kavach.main import app

# kavach/openapi.py -> kavach -> control-plane -> apps -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
DESTINATION = REPO_ROOT / "apps" / "console" / "lib" / "api" / "openapi.json"


def write(destination: Path = DESTINATION) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    destination.write_text(document, encoding="utf-8")
    return destination


if __name__ == "__main__":
    out = write(Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINATION)
    paths = len(app.openapi()["paths"])
    print(f"openapi: {paths} paths -> {out}")
