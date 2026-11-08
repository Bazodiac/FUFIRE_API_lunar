"""The documented synastry example equals the live output (SWIEPH)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

pytestmark = pytest.mark.swieph

EXAMPLES = Path(__file__).resolve().parents[1] / "docs" / "relationship" / "examples"


def test_docs_example_matches_the_live_response() -> None:
    request = json.loads((EXAMPLES / "synastry_example_request.json").read_text(encoding="utf-8"))
    expected = json.loads((EXAMPLES / "synastry_example_response.json").read_text(encoding="utf-8"))
    resp = TestClient(app).post("/v1/relationship/synastry", json=request)
    assert resp.status_code == 200
    assert resp.json() == expected, "regenerate: SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py"
