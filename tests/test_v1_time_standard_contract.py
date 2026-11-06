"""FU-TLST-POLICY / INC-1, step A — the frozen v1/legacy time-standard contract.

The opt-in ``/v2/calculate/bazi`` and ``/v2/calculate/bazi/natal`` routes must
not change a single existing caller. These tests pin, at the HTTP boundary:

* the default time standard of ``/calculate/bazi``, ``/v1/calculate/bazi``,
  ``/calculate/bazi/natal`` and ``/v1/calculate/bazi/natal`` stays ``CIVIL``;
* explicit ``CIVIL`` / ``LMT`` / ``TLST`` keep their semantics on v1;
* the four pillars of three reference cases (Hannover TLST reference,
  Madrid solar-date rollover, Beijing LiChun night) × every standard × both
  day boundaries stay byte-identical. The literal values were captured on the
  base commit 3b574f221d9160b610ef3db09c0ada9e3b883030 BEFORE any INC-1 code
  was written (regression pins, not oracle values — the external TLST oracle
  lives in tests/test_tlst_reference_corpus.py and tests/test_v2_bazi_tlst.py);
* the v1 response key sets stay as they are (no field added or dropped).
  Volatile values (``provenance.computation_timestamp``, natal
  ``provenance.computed_at``) are excluded on purpose: they change per call.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

pytestmark = pytest.mark.swieph

_CASES = {
    "hannover": {"date": "1990-07-15T15:44:00", "tz": "Europe/Berlin", "lon": 9.732, "lat": 52.3759},
    "madrid": {"date": "2024-02-22T00:30:00", "tz": "Europe/Madrid", "lon": -3.7038, "lat": 40.4168},
    "beijing": {"date": "1984-02-04T23:30:00", "tz": "Asia/Shanghai", "lon": 116.4074, "lat": 39.9042},
}

# (case, standard or None = omitted, boundary) -> "year month day hour" as stem-branch.
_PINS = {
    ("hannover", None, "midnight"): "Geng-Wu Gui-Wei Xin-Si Bing-Shen",
    ("hannover", None, "zi"): "Geng-Wu Gui-Wei Xin-Si Bing-Shen",
    ("hannover", "CIVIL", "midnight"): "Geng-Wu Gui-Wei Xin-Si Bing-Shen",
    ("hannover", "CIVIL", "zi"): "Geng-Wu Gui-Wei Xin-Si Bing-Shen",
    ("hannover", "LMT", "midnight"): "Geng-Wu Gui-Wei Xin-Si Yi-Wei",
    ("hannover", "LMT", "zi"): "Geng-Wu Gui-Wei Xin-Si Yi-Wei",
    ("hannover", "TLST", "midnight"): "Geng-Wu Gui-Wei Xin-Si Yi-Wei",
    ("hannover", "TLST", "zi"): "Geng-Wu Gui-Wei Xin-Si Yi-Wei",
    ("madrid", None, "midnight"): "Jia-Chen Bing-Yin Bing-Chen Wu-Zi",
    ("madrid", None, "zi"): "Jia-Chen Bing-Yin Bing-Chen Wu-Zi",
    ("madrid", "CIVIL", "midnight"): "Jia-Chen Bing-Yin Bing-Chen Wu-Zi",
    ("madrid", "CIVIL", "zi"): "Jia-Chen Bing-Yin Bing-Chen Wu-Zi",
    ("madrid", "LMT", "midnight"): "Jia-Chen Bing-Yin Yi-Mao Bing-Zi",
    ("madrid", "LMT", "zi"): "Jia-Chen Bing-Yin Bing-Chen Wu-Zi",
    ("madrid", "TLST", "midnight"): "Jia-Chen Bing-Yin Yi-Mao Bing-Zi",
    ("madrid", "TLST", "zi"): "Jia-Chen Bing-Yin Bing-Chen Wu-Zi",
    ("beijing", None, "midnight"): "Jia-Zi Bing-Yin Wu-Chen Ren-Zi",
    ("beijing", None, "zi"): "Jia-Zi Bing-Yin Ji-Si Jia-Zi",
    ("beijing", "CIVIL", "midnight"): "Jia-Zi Bing-Yin Wu-Chen Ren-Zi",
    ("beijing", "CIVIL", "zi"): "Jia-Zi Bing-Yin Ji-Si Jia-Zi",
    ("beijing", "LMT", "midnight"): "Jia-Zi Bing-Yin Wu-Chen Ren-Zi",
    ("beijing", "LMT", "zi"): "Jia-Zi Bing-Yin Ji-Si Jia-Zi",
    ("beijing", "TLST", "midnight"): "Jia-Zi Bing-Yin Wu-Chen Ren-Zi",
    ("beijing", "TLST", "zi"): "Jia-Zi Bing-Yin Ji-Si Jia-Zi",
}

_BAZI_TOP_KEYS = {
    "chinese", "dates", "derivation_trace", "input", "pillars", "precision",
    "provenance", "quality_flags", "solar_terms_count", "transition",
}
_BAZI_INPUT_KEYS = {
    "date", "tz", "lon", "lat", "standard", "boundary", "ambiguousTime",
    "nonexistentTime", "birth_time_known",
}
_TRACE_KEYS = {"day", "hour", "month", "provenance_ids", "time_resolution", "year"}
_TIME_RESOLUTION_KEYS = {
    "civil_local", "effective_standard", "eot_minutes", "eot_source", "lmt",
    "tlst_date_rollover", "tlst_hours", "tz_offset_minutes", "utc",
}
_NATAL_TOP_KEYS = {"day_master", "month_command", "pillars", "precision", "provenance", "warnings"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _bazi_pillars(body: dict) -> str:
    p = body["pillars"]
    return " ".join(f"{p[k]['stamm']}-{p[k]['zweig']}" for k in ("year", "month", "day", "hour"))


def _natal_pillars(body: dict) -> str:
    p = body["pillars"]
    return " ".join(f"{p[k]['stem']}-{p[k]['branch']}" for k in ("year", "month", "day", "hour"))


def _payload(case: str, standard: str | None, boundary: str) -> dict:
    body = dict(_CASES[case], boundary=boundary)
    if standard is not None:
        body["standard"] = standard
    return body


@pytest.mark.parametrize("prefix", ["", "/v1"])
@pytest.mark.parametrize("key", sorted(_PINS, key=lambda k: (k[0], str(k[1]), k[2])))
def test_v1_bazi_pillars_unchanged(client, prefix, key):
    case, standard, boundary = key
    r = client.post(f"{prefix}/calculate/bazi", json=_payload(case, standard, boundary))
    assert r.status_code == 200, r.text
    assert _bazi_pillars(r.json()) == _PINS[key]


@pytest.mark.parametrize("prefix", ["", "/v1"])
@pytest.mark.parametrize("key", sorted(_PINS, key=lambda k: (k[0], str(k[1]), k[2])))
def test_v1_natal_pillars_unchanged(client, prefix, key):
    case, standard, boundary = key
    r = client.post(f"{prefix}/calculate/bazi/natal", json=_payload(case, standard, boundary))
    assert r.status_code == 200, r.text
    assert _natal_pillars(r.json()) == _PINS[key]


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_v1_bazi_default_standard_is_civil(client, prefix):
    r = client.post(f"{prefix}/calculate/bazi", json=_CASES["hannover"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["input"]["standard"] == "CIVIL"
    assert body["input"]["boundary"] == "midnight"
    assert body["derivation_trace"]["time_resolution"]["effective_standard"] == "CIVIL"
    assert body["derivation_trace"]["hour"]["time_standard_used"] == "CIVIL"
    assert body["derivation_trace"]["hour"]["true_solar_time_used"] is False
    # Civil 15:44 is Shen; the solar answers (LMT/TLST) are Wei.
    assert body["pillars"]["hour"]["zweig"] == "Shen"


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_v1_natal_default_equals_bazi_civil(client, prefix):
    natal = client.post(f"{prefix}/calculate/bazi/natal", json=_CASES["madrid"])
    civil = client.post(f"{prefix}/calculate/bazi", json={**_CASES["madrid"], "standard": "CIVIL"})
    assert natal.status_code == 200 and civil.status_code == 200
    assert _natal_pillars(natal.json()) == _bazi_pillars(civil.json())


@pytest.mark.parametrize("prefix", ["", "/v1"])
@pytest.mark.parametrize("standard", ["CIVIL", "LMT", "TLST"])
def test_v1_explicit_standard_is_echoed_and_used(client, prefix, standard):
    r = client.post(f"{prefix}/calculate/bazi", json={**_CASES["hannover"], "standard": standard})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["input"]["standard"] == standard
    hour = body["derivation_trace"]["hour"]
    assert hour["time_standard_requested"] == standard
    assert hour["time_standard_used"] == standard
    assert hour["true_solar_time_used"] is (standard == "TLST")
    assert hour["lmt_used"] is (standard == "LMT")
    assert body["derivation_trace"]["time_resolution"]["effective_standard"] == standard


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_v1_missing_location_still_defaults_to_berlin(client, prefix):
    """The frozen v1 contract keeps its Berlin location defaults. INC-1 must not
    tighten v1 — the no-default rule applies to the new /v2 routes only."""
    r = client.post(f"{prefix}/calculate/bazi", json={"date": "1990-07-15T15:44:00"})
    assert r.status_code == 200, r.text
    assert r.json()["input"]["lon"] == 13.405
    assert r.json()["input"]["lat"] == 52.52
    assert r.json()["input"]["tz"] == "Europe/Berlin"


@pytest.mark.parametrize("prefix", ["", "/v1"])
def test_v1_response_key_sets_unchanged(client, prefix):
    r = client.post(f"{prefix}/calculate/bazi", json=_CASES["hannover"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == _BAZI_TOP_KEYS
    assert set(body["input"]) == _BAZI_INPUT_KEYS
    assert set(body["derivation_trace"]) == _TRACE_KEYS
    assert set(body["derivation_trace"]["time_resolution"]) == _TIME_RESOLUTION_KEYS
    n = client.post(f"{prefix}/calculate/bazi/natal", json=_CASES["hannover"])
    assert n.status_code == 200, n.text
    assert set(n.json()) == _NATAL_TOP_KEYS


def test_v2_routes_do_not_leak_onto_v1_or_legacy(client):
    """The v2 TLST surface is /v2-only: no /v1 or legacy twin may exist."""
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/v2/calculate/bazi" in paths
    assert "/v2/calculate/bazi/natal" in paths
    assert "/v2/calculate/bazi/trace" not in paths
    assert "/v2/calculate/bazi/wuxing" not in paths
    assert not any(p.startswith("/v1/v2") or p.startswith("/v2/v1") for p in paths)
