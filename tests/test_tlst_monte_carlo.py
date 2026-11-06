"""FU-TLST-POLICY / INC-1, AC-05 — seeded Monte-Carlo TLST check in CI.

Runs ``scripts/tlst_monte_carlo.py`` (seed 20261106, >= 5 000 valid samples)
against the Swiss-Ephemeris oracle ``swe.lmt_to_lat`` and fails closed:
fewer valid samples than requested, any TLST delta above the documented
0.1-minute bound, any date/branch disagreement outside the boundary bucket,
or any disagreement the engine does not flag as within tolerance.

A smaller HTTP subset sends the first 40 accepted samples of the same seeded
stream through BOTH /v2 routes and checks the published pillars against
oracle-derived expectations (branch from the oracle hour, day from the
oracle solar date via the documented ``(JDN + 49) % 60`` rule).
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import swisseph as swe
from fastapi.testclient import TestClient

from bazi_engine.app import app

pytestmark = pytest.mark.swieph

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tlst_monte_carlo.py"
_SPEC = importlib.util.spec_from_file_location("tlst_monte_carlo", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
mc = importlib.util.module_from_spec(_SPEC)
sys.modules["tlst_monte_carlo"] = mc
_SPEC.loader.exec_module(mc)

SEED = 20261106
N = 5000
TOL = 0.1

STEMS = ["Jia", "Yi", "Bing", "Ding", "Wu", "Ji", "Geng", "Xin", "Ren", "Gui"]
BRANCHES = ["Zi", "Chou", "Yin", "Mao", "Chen", "Si", "Wu", "Wei", "Shen", "You", "Xu", "Hai"]


@pytest.fixture(autouse=True)
def _pin_swisseph_global_state():
    from bazi_engine.ephemeris import _resolve_ephe_path
    swe.set_ephe_path(str(_resolve_ephe_path(None)))
    swe.set_sid_mode(0)
    yield


@pytest.fixture(scope="module")
def report() -> dict:
    from bazi_engine.ephemeris import _resolve_ephe_path
    swe.set_ephe_path(str(_resolve_ephe_path(None)))
    return mc.run(SEED, N, TOL)


def test_seed_and_sample_count(report):
    assert report["seed"] == SEED
    assert report["valid"] == N, report["valid"]
    assert report["draws"] == report["valid"] + report["discarded_nonexistent"]


def test_tlst_within_documented_bound(report):
    assert report["max_abs_delta_min"] <= TOL, report["max_abs_delta_min"]
    assert report["p99_abs_delta_min"] <= report["max_abs_delta_min"]
    assert report["counts"].get("hour_mismatch", 0) == 0


def test_no_unexplained_date_branch_or_utc_disagreement(report):
    c = report["counts"]
    assert c.get("date_mismatch", 0) == 0, report["counterexamples"][:5]
    assert c.get("branch_mismatch", 0) == 0, report["counterexamples"][:5]
    assert c.get("utc_mismatch", 0) == 0, report["counterexamples"][:5]
    assert c.get("unflagged_disagreements", 0) == 0, report["counterexamples"][:5]
    assert report["violations"] == 0


def test_boundary_bucket_is_reported_not_hidden(report):
    c = report["counts"]
    assert c.get("proven_agreement", 0) + c.get("boundary_uncertain", 0) == report["valid"]
    assert c.get("boundary_uncertain", 0) == (c.get("boundary_uncertain_agreed", 0)
                                              + c.get("boundary_uncertain_disagreed", 0))


def test_distribution_covers_required_dimensions(report):
    d = report["distribution"]
    assert len(d["by_tz"]) >= 30
    assert set(d["by_hemisphere"]) == {"north", "south"}
    assert set(d["by_lon_sign"]) == {"negative", "positive"}
    assert {"dec_feb", "jun_aug"} <= set(d["by_season"])
    assert {"1950s", "2030s"} <= set(d["by_decade"])
    assert set(d["by_stratum"]) == {"anywhere", "dst_window", "near_meridian"}
    assert {"-1", "0", "1"} <= set(d["tlst_date_rollover"])
    assert report["counts"].get("local_status_ambiguous", 0) > 0
    assert report["discarded_nonexistent"] > 0


def test_generator_is_reproducible():
    assert mc.first_valid_samples(SEED, 25) == mc.first_valid_samples(SEED, 25)
    assert mc.first_valid_samples(SEED, 5) != mc.first_valid_samples(SEED + 1, 5)


# ── HTTP subset: full BaZi + Natal requests on seeded inputs ─────────────────


def _expected_day(d: date) -> str:
    jdn = int(swe.julday(d.year, d.month, d.day, 12.0) + 0.5)
    idx = (jdn + 49) % 60
    return f"{STEMS[idx % 10]}-{BRANCHES[idx % 12]}"


_HTTP_SAMPLES = mc.first_valid_samples(SEED, 40)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("idx", range(len(_HTTP_SAMPLES)))
def test_http_subset_matches_oracle(client, idx):
    s = _HTTP_SAMPLES[idx]
    boundary = "zi" if idx % 2 else "midnight"
    req = {"date": s.wall_clock, "tz": s.tz, "lat": s.lat, "lon": s.lon, "standard": "TLST",
           "boundary": boundary, "ambiguousTime": s.fold_choice}
    rb = client.post("/v2/calculate/bazi", json=req)
    rn = client.post("/v2/calculate/bazi/natal", json=req)
    assert rb.status_code == 200 and rn.status_code == 200, (rb.text, rn.text)
    b, n = rb.json(), rn.json()
    pb = b["pillars"]
    pn = n["pillars"]
    bazi4 = [f"{pb[k]['stamm']}-{pb[k]['zweig']}" for k in ("year", "month", "day", "hour")]
    natal4 = [f"{pn[k]['stem']}-{pn[k]['branch']}" for k in ("year", "month", "day", "hour")]
    assert bazi4 == natal4
    assert b["time_basis"] == n["time_basis"]
    tb = b["time_basis"]
    utc = datetime.fromisoformat(tb["utc"]).astimezone(timezone.utc)
    o_date, o_hours = mc.oracle(utc, s.lon)
    assert mc.circ_min(tb["tlst_hours"], o_hours) <= TOL
    if mc.oracle_edge_distance_min(o_hours) > TOL:
        hours, sdate = o_hours, o_date            # oracle decides
        assert tb["uncertainty"]["tlst_edge"]["status"] in ("clear", "within_eot_tolerance")
    else:
        hours, sdate = tb["tlst_hours"], date.fromisoformat(tb["tlst_date"])   # self-consistency
        assert tb["uncertainty"]["tlst_edge"]["status"] == "within_eot_tolerance"
    assert tb["tlst_date"] == sdate.isoformat()
    want_day = sdate + timedelta(days=1) if (boundary == "zi" and hours >= 23.0) else sdate
    assert bazi4[2] == _expected_day(want_day), (s, tb)
    assert bazi4[3].split("-")[1] == BRANCHES[mc.branch_of(hours)], (s, tb)
