"""Deterministic Moon uncertainty for an unknown birth time (D15).

The Moon is also computed at local 00:00 and 23:59 of the calendar day. The
Moon sign entry carries ``sign_certain`` and ``moon_range_deg``; every aspect
row carries ``time_sensitive`` = the aspect is not the same at all bounds.
Since D16 every planet is assessed the same way (tests/test_synastry_day_uncertainty.py);
the Moon cases here pass the bounds as ``day_bounds`` / day ranges.
"""
from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.synastry import SynastryPersonInput, compute_synastry
from bazi_engine.synastry.aspects import cross_aspects
from bazi_engine.synastry.policy import MOON_RANGE_DST_POLICIES, MOON_RANGE_LOCAL_TIMES
from bazi_engine.synastry.signs import sign_layer
from bazi_engine.time_utils import resolve_local_iso
from bazi_engine.western import compute_western_chart
from tests.fixtures.synastry_charts import BASE_A, BASE_B, assert_mirrored, day_bounds, make_chart
from tests.fixtures.synastry_payloads import SYNASTRY_PATH, VALID_SYNASTRY_REQUEST, request_with

client = TestClient(app)

BERLIN: Dict[str, Any] = {"tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52}
# Chile leaves DST at 2024-04-07 00:00 → 2024-04-06 23:00: local 23:00–23:59 occurs twice.
SANTIAGO: Dict[str, Any] = {"tz": "America/Santiago", "lon": -70.6693, "lat": -33.4489}
FALL_BACK_DATE = "2024-04-06"
DAY_CHANGE_DATE = "1990-01-05"  # Moon Widder → Stier during the local day (see test_synastry_unknown_time)
NO_INGRESS_DATE = "1990-01-02"  # first date from 1990-01-01 with one Moon sign at local 00:00 and 23:59


def _rows(frm: Dict[str, float], to: Dict[str, float], **bounds: Any) -> List[Dict[str, Any]]:
    return cross_aspects(frm, to, from_person="person_a", to_person="person_b", **bounds)


def _ranges(base: Dict[str, float], **moon: Any) -> Dict[str, Any]:
    """Day ranges with every planet stationary at ``base`` except the given Moon range."""
    start, end = day_bounds(base, **moon)
    return {f: (start[f], end[f]) for f in start}


# ── aspects ──────────────────────────────────────────────────────────────────
def test_bounds_straddling_an_orb_limit_are_time_sensitive() -> None:
    (row,) = _rows({"Sun": 0.0}, {"Moon": 7.0}, to_day_ranges={"Moon": (2.0, 14.0)})
    assert row["type"] == "conjunction"
    assert row["time_sensitive"] is True


def test_bounds_well_inside_the_window_are_not_time_sensitive() -> None:
    (row,) = _rows({"Sun": 0.0}, {"Moon": 3.0}, to_day_ranges={"Moon": (1.0, 6.0)})
    assert row["time_sensitive"] is False


def test_bounds_entering_another_aspect_are_time_sensitive() -> None:
    # 12:00 square at 91°, the day ends at 120.5° (a trine): a different type counts too.
    (row,) = _rows({"Moon": 91.0}, {"Sun": 0.0}, from_day_ranges={"Moon": (85.0, 120.5)})
    assert row["type"] == "square"
    assert row["time_sensitive"] is True


def test_known_time_rows_are_never_time_sensitive() -> None:
    rows = _rows({"Sun": 0.0, "Moon": 7.0}, {"Sun": 2.0, "Moon": 7.9})
    assert rows and all(r["time_sensitive"] is False for r in rows)


def test_a_planet_that_stays_in_the_window_is_not_time_sensitive() -> None:
    rows = _rows({"Sun": 0.0}, {"Sun": 7.9, "Moon": 7.0}, to_day_ranges={"Sun": (7.5, 7.95), "Moon": (2.0, 14.0)})
    assert {r["to_factor"]: r["time_sensitive"] for r in rows} == {"Sun": False, "Moon": True}


def test_moon_moon_with_both_times_unknown_uses_the_four_corners() -> None:
    # Diagonal corners (354,354) and (6,6) are both exact conjunctions; only the
    # cross corners (354,6) and (6,354) are 12° apart — no aspect.
    (row,) = _rows({"Moon": 0.0}, {"Moon": 0.0}, from_day_ranges={"Moon": (354.0, 6.0)},
                  to_day_ranges={"Moon": (354.0, 6.0)})
    assert row["type"] == "conjunction"
    assert row["time_sensitive"] is True


def test_moon_moon_stable_at_all_corners() -> None:
    (row,) = _rows({"Moon": 0.0}, {"Moon": 180.0}, from_day_ranges={"Moon": (358.0, 2.0)},
                  to_day_ranges={"Moon": (178.0, 182.0)})
    assert row["type"] == "opposition"
    assert row["time_sensitive"] is False


# ── sign layer ───────────────────────────────────────────────────────────────
def _moon(layer: Dict[str, Any], person: str) -> Dict[str, Any]:
    return next(e for e in layer["factors"][person] if e["factor"] == "Moon")


def test_moon_range_crossing_zero_is_uncertain() -> None:
    layer = sign_layer(BASE_A, BASE_B, day_ranges_b=_ranges(BASE_B, Moon=(355.0, 8.0)))
    moon = _moon(layer, "person_b")
    assert moon["sign_certain"] is False
    assert moon["moon_range_deg"] == [355.0, 8.0]


def test_moon_range_inside_one_sign_is_certain() -> None:
    layer = sign_layer(BASE_A, BASE_B, day_ranges_a=_ranges(BASE_A, Moon=(91.12346, 103.98764)))
    moon = _moon(layer, "person_a")
    assert moon["sign_certain"] is True
    assert moon["moon_range_deg"] == [91.1235, 103.9876]


def test_moon_range_is_kept_below_360() -> None:
    moon = _moon(sign_layer(BASE_A, BASE_B, day_ranges_a=_ranges(BASE_A, Moon=(359.99999, 12.0))), "person_a")
    assert moon["moon_range_deg"] == [0.0, 12.0]
    assert moon["sign_certain"] is True


def test_only_the_moon_entry_carries_the_range() -> None:
    layer = sign_layer(BASE_A, BASE_B, day_ranges_b=_ranges(BASE_B, Moon=(185.0, 197.0)))
    others = [e for e in layer["factors"]["person_b"] if e["factor"] != "Moon"]
    assert others and all(e["moon_range_deg"] is None and isinstance(e["sign_certain"], bool) for e in others)
    assert all(e["sign_certain"] is None and e["moon_range_deg"] is None for e in layer["factors"]["person_a"])


def test_existing_callers_get_null_range_fields() -> None:
    layer = sign_layer(BASE_A, BASE_B)
    assert all(e["sign_certain"] is None and e["moon_range_deg"] is None
               for p in ("person_a", "person_b") for e in layer["factors"][p])


# ── engine ───────────────────────────────────────────────────────────────────
def _a(**kw: Any) -> SynastryPersonInput:
    return SynastryPersonInput(chart=make_chart(BASE_A, asc=15.0, mc=280.0, cusp_start=15.0), **kw)


def _b(**kw: Any) -> SynastryPersonInput:
    return SynastryPersonInput(chart=make_chart(BASE_B, asc=200.0, mc=110.0, cusp_start=200.0), **kw)


def test_engine_threads_the_bounds_into_signs_and_aspects() -> None:
    # B's Moon 188 opposes A's Sun 10 (orb 2); over the day B's Moon runs 183 → 196,
    # inside the opposition window 182..198 of A's Sun.
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=False, day_bounds=day_bounds(BASE_B, Moon=(183.0, 196.0))))
    moon_b = _moon(out["sign_layer"], "person_b")
    assert moon_b["moon_range_deg"] == [183.0, 196.0] and moon_b["sign_certain"] is True
    row = next(r for r in out["aspects"] if (r["from_factor"], r["to_factor"]) == ("Sun", "Moon"))
    assert row["type"] == "opposition" and row["time_sensitive"] is False
    straddle = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=False, day_bounds=day_bounds(BASE_B, Moon=(183.0, 199.0))))
    row = next(r for r in straddle["aspects"] if (r["from_factor"], r["to_factor"]) == ("Sun", "Moon"))
    assert row["time_sensitive"] is True


@pytest.mark.parametrize("bounds_a, bounds_b", [
    (None, (183.0, 199.0)), ((95.0, 108.0), None), ((95.0, 108.0), (183.0, 199.0)),
])
def test_swap_mirrors_with_bounds(bounds_a: Any, bounds_b: Any) -> None:
    a = _a(birth_time_known=bounds_a is None, day_bounds=bounds_a and day_bounds(BASE_A, Moon=bounds_a))
    b = _b(birth_time_known=bounds_b is None, day_bounds=bounds_b and day_bounds(BASE_B, Moon=bounds_b))
    ab, ba = compute_synastry(a, b), compute_synastry(b, a)
    assert any(r["time_sensitive"] for r in ab["aspects"])  # non-vacuous
    assert_mirrored(ab, ba)


# ── HTTP boundary ────────────────────────────────────────────────────────────
def _post(body: Dict[str, Any]) -> Dict[str, Any]:
    resp = client.post(SYNASTRY_PATH, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _ref_moon(local_iso: str, place: Dict[str, Any] = BERLIN, ambiguous: str = "earlier") -> float:
    dt_local, _ = resolve_local_iso(local_iso, place["tz"], ambiguous=ambiguous, nonexistent="shift_forward")  # type: ignore[arg-type]
    chart = compute_western_chart(dt_local.astimezone(timezone.utc), place["lat"], place["lon"])
    return float(chart["bodies"]["Moon"]["longitude"]) % 360.0


@pytest.mark.swieph
def test_day_with_a_moon_ingress_is_uncertain() -> None:
    out = _post(request_with(person_b={**BERLIN, "date": f"{DAY_CHANGE_DATE}T23:50:00", "birth_time_known": False}))
    moon = _moon(out["sign_layer"], "person_b")
    assert moon["sign_certain"] is False
    start, end = moon["moon_range_deg"]
    assert start == pytest.approx(_ref_moon(f"{DAY_CHANGE_DATE}T00:00:00"), abs=1e-4)
    assert end == pytest.approx(_ref_moon(f"{DAY_CHANGE_DATE}T23:59:00", ambiguous="later"), abs=1e-4)


@pytest.mark.swieph
def test_day_without_a_moon_ingress_is_certain() -> None:
    out = _post(request_with(person_b={**BERLIN, "date": NO_INGRESS_DATE, "birth_time_known": False}))
    moon = _moon(out["sign_layer"], "person_b")
    assert moon["sign_certain"] is True
    start, end = moon["moon_range_deg"]
    assert start == pytest.approx(_ref_moon(f"{NO_INGRESS_DATE}T00:00:00"), abs=1e-4)
    assert end == pytest.approx(_ref_moon(f"{NO_INGRESS_DATE}T23:59:00", ambiguous="later"), abs=1e-4)


def test_moon_range_dst_policies() -> None:
    assert MOON_RANGE_DST_POLICIES == (("earlier", "shift_forward"), ("later", "shift_forward"))
    assert len(MOON_RANGE_DST_POLICIES) == len(MOON_RANGE_LOCAL_TIMES)


@pytest.mark.swieph
def test_fall_back_day_end_bound_uses_the_later_fold() -> None:
    out = _post(request_with(person_b={**SANTIAGO, "date": FALL_BACK_DATE, "birth_time_known": False}))
    start, end = _moon(out["sign_layer"], "person_b")["moon_range_deg"]
    later = _ref_moon(f"{FALL_BACK_DATE}T23:59:00", SANTIAGO, ambiguous="later")
    earlier = _ref_moon(f"{FALL_BACK_DATE}T23:59:00", SANTIAGO, ambiguous="earlier")
    assert abs(later - earlier) > 0.1  # non-vacuous: 23:59 really occurs twice
    assert end == pytest.approx(later, abs=1e-4)
    assert start == pytest.approx(_ref_moon(f"{FALL_BACK_DATE}T00:00:00", SANTIAGO), abs=1e-4)


def test_known_time_response_has_no_time_uncertainty() -> None:
    out = _post(VALID_SYNASTRY_REQUEST)
    assert out["aspects"] and all(r["time_sensitive"] is False for r in out["aspects"])
    entries = [e for p in ("person_a", "person_b") for e in out["sign_layer"]["factors"][p]]
    assert entries and all(e["sign_certain"] is None and e["moon_range_deg"] is None for e in entries)


def test_unknown_time_rows_carry_time_sensitive() -> None:
    # Since D16 a non-Moon row can be time-sensitive too (see test_synastry_day_uncertainty).
    out = _post(request_with(person_b={"birth_time_known": False}))
    assert all(isinstance(r["time_sensitive"], bool) for r in out["aspects"])
    assert all(e["moon_range_deg"] is None for e in out["sign_layer"]["factors"]["person_a"])
