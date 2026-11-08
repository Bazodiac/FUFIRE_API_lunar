"""Write or check the documented synastry example (docs/relationship/examples/).

The example is produced by the live app on the real Swiss Ephemeris, never by
hand. Regenerate after any change to the synastry output or the engine build
label:

    SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py
    SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py --check   # exit 1 when stale

Exit codes: 0 = written / up to date, 1 = stale (--check), 2 = no SWIEPH,
3 = the request to the app failed (not the same as stale).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # scripts/ is sys.path[0]; the package need not be installed

EXAMPLES = ROOT / "docs" / "relationship" / "examples"
REQUEST_FILE = EXAMPLES / "synastry_example_request.json"
RESPONSE_FILE = EXAMPLES / "synastry_example_response.json"

# Synthetic test pair (no real persons).
REQUEST: Dict[str, Any] = {
    "person_a": {"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52,
                 "display_label": "A."},
    "person_b": {"date": "1992-11-03T08:15:00", "tz": "Europe/Vienna", "lon": 16.3738, "lat": 48.2082,
                 "display_label": "B."},
    "options": {"second_person_consent_confirmed": True},
}


class BuildError(Exception):
    """The live app did not return 200 for the example request."""


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def build_response() -> str:
    from fastapi.testclient import TestClient

    from bazi_engine.app import app

    resp = TestClient(app).post("/v1/relationship/synastry", json=REQUEST)
    if resp.status_code != 200:
        raise BuildError(f"synastry request failed: {resp.status_code} {resp.text}")
    return _dump(resp.json())


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 when the files are stale")
    args = parser.parse_args(argv)
    if not os.environ.get("SE_EPHE_PATH") or os.environ.get("EPHEMERIS_MODE", "SWIEPH").upper() != "SWIEPH":
        print("needs SE_EPHE_PATH and SWIEPH (the example documents the real ephemeris)", file=sys.stderr)
        return 2
    try:
        request_text, response_text = _dump(REQUEST), build_response()
    except BuildError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    if args.check:
        stale = [p.name for p, text in ((REQUEST_FILE, request_text), (RESPONSE_FILE, response_text))
                 if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"stale: {', '.join(stale)} — regenerate", file=sys.stderr)
            return 1
        return 0
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    REQUEST_FILE.write_text(request_text, encoding="utf-8")
    RESPONSE_FILE.write_text(response_text, encoding="utf-8")
    print(f"wrote {REQUEST_FILE.relative_to(ROOT)} and {RESPONSE_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
