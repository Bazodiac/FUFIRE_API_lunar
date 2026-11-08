"""Unknown birth time: every planet is assessed over the local day (D16, F9a–F9c).

For an unknown-time person the router computes the two bound charts at local
00:00 and 23:59 (the same two charts as the D15 Moon range) and passes all ten
planet longitudes as ``SynastryPersonInput.day_bounds``. Aspects and house
overlays carry ``time_sensitive``; sign-layer and Wu-Xing factors carry
``sign_certain``. Element, weight and vectors stay at the 12:00 value.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Tuple

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.exc import CalculationError
from bazi_engine.synastry import SynastryPersonInput, compute_synastry
from tests.fixtures.synastry_charts import BASE_A, BASE_B, assert_mirrored, day_bounds, make_chart
from tests.fixtures.synastry_payloads import SYNASTRY_PATH, VALID_SYNASTRY_REQUEST, request_with, swapped

client = TestClient(app)

SIGN_LAYER_PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars"]
BERLIN: Dict[str, Any] = {"tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52}
# Found by a deterministic day-by-day scan from 1992-11-03 (person_b of the valid request,
# Europe/Vienna, unknown time) against person_a of the valid request, with an independent
# oracle (HEAD's classify_aspect / house_of on the two bound charts and the 12:00 chart):
# the first day with a non-Moon time-sensitive aspect is 1992-11-03 itself (A Venus → B Sun
# opposition: no aspect at one bound), the first with a non-Moon time-sensitive overlay is 1992-11-05
# (B Mercury moves from A's house 2 into house 3).
NON_MOON_ASPECT_DATE = "1992-11-03"
NON_MOON_OVERLAY_DATE = "1992-11-05"

Bounds = Tuple[Dict[str, float], Dict[str, float]]


def _known(planets: Mapping[str, float] = BASE_A) -> SynastryPersonInput:
    return SynastryPersonInput(chart=make_chart(dict(planets), asc=15.0, mc=280.0, cusp_start=15.0),
                               birth_time_known=True)


def _unknown(planets: Mapping[str, float], bounds: Optional[Bounds]) -> SynastryPersonInput:
    return SynastryPersonInput(chart=make_chart(dict(planets), cusp_start=200.0),
                               birth_time_known=False, day_bounds=bounds)


def _row(out: Dict[str, Any], frm: str, to: str) -> Dict[str, Any]:
    return next(r for r in out["aspects"] if (r["from_factor"], r["to_factor"]) == (frm, to))


def _entry(out: Dict[str, Any], person: str, factor: str) -> Dict[str, Any]:
    return next(e for e in out["sign_layer"]["factors"][person] if e["factor"] == factor)


# ── F9b: input contract ──────────────────────────────────────────────────────
def test_day_bounds_are_only_allowed_for_an_unknown_time() -> None:
    with pytest.raises(ValueError):
        SynastryPersonInput(chart=make_chart(BASE_A), birth_time_known=True, day_bounds=day_bounds(BASE_A))


def test_a_planet_missing_from_a_bound_chart_fails_naming_the_factor() -> None:
    start, end = day_bounds(BASE_B)
    del end["Saturn"]
    with pytest.raises(CalculationError) as excinfo:
        compute_synastry(_known(), _unknown(BASE_B, (start, end)))
    assert excinfo.value.detail == {"factor": "Saturn"}
    assert "Saturn" in str(excinfo.value)


# ── F9b: aspects ─────────────────────────────────────────────────────────────
def test_mercury_bounds_straddling_an_orb_limit_are_time_sensitive() -> None:
    # A Sun 10 – B Mercury 125: trine, orb 5 (limit 6). At 00:00 Mercury is at 123 (orb 7: none).
    out = compute_synastry(_known(), _unknown(BASE_B, day_bounds(BASE_B, Mercury=(123.0, 127.0))))
    row = _row(out, "Sun", "Mercury")
    assert row["type"] == "trine"
    assert row["time_sensitive"] is True


def test_mercury_bounds_well_inside_the_window_are_not_time_sensitive() -> None:
    out = compute_synastry(_known(), _unknown(BASE_B, day_bounds(BASE_B, Mercury=(124.5, 126.0))))
    assert _row(out, "Sun", "Mercury")["time_sensitive"] is False


def test_both_unknown_uses_the_four_corners() -> None:
    # Both Mercuries move 12° in parallel: the diagonal corners (14,74) and (26,86) are exact
    # sextiles, only the cross corners (14,86)=72° and (26,74)=48° leave the window.
    a = _unknown({**BASE_A, "Mercury": 20.0}, day_bounds(BASE_A, Mercury=(14.0, 26.0)))
    b = _unknown({**BASE_B, "Mercury": 80.0}, day_bounds(BASE_B, Mercury=(74.0, 86.0)))
    row = _row(compute_synastry(a, b), "Mercury", "Mercury")
    assert row["type"] == "sextile" and row["orb"] == 0.0
    assert row["time_sensitive"] is True


def test_both_unknown_stable_at_all_four_corners() -> None:
    a = _unknown({**BASE_A, "Mercury": 20.0}, day_bounds(BASE_A, Mercury=(19.0, 21.0)))
    b = _unknown({**BASE_B, "Mercury": 80.0}, day_bounds(BASE_B, Mercury=(79.0, 81.0)))
    assert _row(compute_synastry(a, b), "Mercury", "Mercury")["time_sensitive"] is False


def test_the_moon_range_still_comes_from_the_day_bounds() -> None:
    out = compute_synastry(_known(), _unknown(BASE_B, day_bounds(BASE_B, Moon=(183.0, 199.0))))
    moon = _entry(out, "person_b", "Moon")
    assert moon["moon_range_deg"] == [183.0, 199.0] and moon["sign_certain"] is True
    assert _row(out, "Sun", "Moon")["time_sensitive"] is True  # opposition window of A's Sun ends at 198


# ── F9b: sign layer ──────────────────────────────────────────────────────────
def test_mercury_across_a_sign_cusp_is_not_sign_certain() -> None:
    out = compute_synastry(_known(), _unknown({**BASE_B, "Mercury": 120.5}, day_bounds(BASE_B, Mercury=(119.0, 121.0))))
    mercury = _entry(out, "person_b", "Mercury")
    assert mercury["sign_certain"] is False
    assert mercury["moon_range_deg"] is None  # the range itself is reported for the Moon only


def test_mercury_inside_one_sign_is_sign_certain() -> None:
    out = compute_synastry(_known(), _unknown(BASE_B, day_bounds(BASE_B, Mercury=(124.0, 126.0))))
    assert _entry(out, "person_b", "Mercury")["sign_certain"] is True


def test_sign_certain_uses_the_rounded_bounds() -> None:
    # 29.99999 rounds to 30.0 (Stier), so the Mercury day range 30.0 → 31.0 is one sign.
    out = compute_synastry(_known(), _unknown({**BASE_B, "Mercury": 30.5}, day_bounds(BASE_B, Mercury=(29.99999, 31.0))))
    assert _entry(out, "person_b", "Mercury")["sign_certain"] is True


def test_every_sign_layer_planet_of_an_unknown_time_person_is_marked() -> None:
    out = compute_synastry(_known(), _unknown(BASE_B, day_bounds(BASE_B)))
    entries = out["sign_layer"]["factors"]["person_b"]
    assert [e["factor"] for e in entries] == SIGN_LAYER_PLANETS
    assert all(e["sign_certain"] is True for e in entries)
    assert all(e["moon_range_deg"] is None for e in entries if e["factor"] != "Moon")


def test_known_time_person_has_null_sign_certain() -> None:
    out = compute_synastry(_known(), _unknown(BASE_B, day_bounds(BASE_B, Mercury=(119.0, 121.0))))
    assert all(e["sign_certain"] is None and e["moon_range_deg"] is None
               for e in out["sign_layer"]["factors"]["person_a"])


@pytest.mark.parametrize("unknown_a, unknown_b", [(False, True), (True, False), (True, True)])
def test_swap_mirrors_with_day_bounds(unknown_a: bool, unknown_b: bool) -> None:
    a = (_unknown(BASE_A, day_bounds(BASE_A, Mercury=(14.0, 26.0), Moon=(95.0, 108.0))) if unknown_a else _known())
    b = (_unknown(BASE_B, day_bounds(BASE_B, Mercury=(123.0, 127.0), Venus=(58.0, 61.0))) if unknown_b
         else SynastryPersonInput(chart=make_chart(BASE_B, cusp_start=200.0), birth_time_known=True))
    ab, ba = compute_synastry(a, b), compute_synastry(b, a)
    assert any(r["time_sensitive"] for r in ab["aspects"] if "Moon" not in (r["from_factor"], r["to_factor"]))
    assert_mirrored(ab, ba)


# ── F9a: house overlays ──────────────────────────────────────────────────────
def _overlay(out: Dict[str, Any], side: str, factor: str) -> Dict[str, Any]:
    return next(r for r in out["house_overlays"][side] if r["factor"] == factor)


def test_guest_mars_straddling_a_host_cusp_is_time_sensitive() -> None:
    # A's houses start at 15° (equal 30° houses): B's Mars runs 14 → 16 over the day, house 12 → 1.
    out = compute_synastry(_known(), _unknown(BASE_B, day_bounds(BASE_B, Mars=(14.0, 16.0))))
    row = _overlay(out, "b_in_a", "Mars")
    assert (row["house"], row["status"]) == (1, "ok")
    assert row["time_sensitive"] is True


def test_guest_mars_well_inside_a_house_is_not_time_sensitive() -> None:
    out = compute_synastry(_known(), _unknown({**BASE_B, "Mars": 25.0}, day_bounds(BASE_B, Mars=(24.0, 26.0))))
    assert _overlay(out, "b_in_a", "Mars")["time_sensitive"] is False


def test_a_bound_house_other_than_the_noon_house_is_time_sensitive() -> None:
    # Both bounds in house 1 (16°, 17°), the 12:00 value in house 12 (14°).
    out = compute_synastry(_known(), _unknown({**BASE_B, "Mars": 14.0}, day_bounds(BASE_B, Mars=(16.0, 17.0))))
    row = _overlay(out, "b_in_a", "Mars")
    assert row["house"] == 12 and row["time_sensitive"] is True


def test_known_time_guest_rows_are_not_time_sensitive() -> None:
    b = SynastryPersonInput(chart=make_chart(BASE_B, cusp_start=200.0), birth_time_known=True)
    out = compute_synastry(_known(), b)
    rows = out["house_overlays"]["a_in_b"] + out["house_overlays"]["b_in_a"]
    assert len(rows) == 20 and all(r["time_sensitive"] is False for r in rows)


def test_unknown_time_host_stays_gated_and_not_time_sensitive() -> None:
    out = compute_synastry(_known(), _unknown(BASE_B, day_bounds(BASE_B, Mars=(14.0, 16.0))))
    assert out["house_overlays"]["a_in_b"] == [
        {"factor": f, "house": None, "status": "unavailable_missing_time", "time_sensitive": False}
        for f in ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
    ]


def test_swap_mirrors_the_overlay_flag() -> None:
    a, b = _known(), _unknown(BASE_B, day_bounds(BASE_B, Mars=(14.0, 16.0)))
    ab, ba = compute_synastry(a, b), compute_synastry(b, a)
    assert _overlay(ab, "b_in_a", "Mars")["time_sensitive"] is True  # non-vacuous
    assert_mirrored(ab, ba)


# ── HTTP boundary (swieph) ───────────────────────────────────────────────────
def _post(body: Dict[str, Any]) -> Dict[str, Any]:
    resp = client.post(SYNASTRY_PATH, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest.mark.swieph
def test_http_unknown_time_marks_every_sign_layer_planet() -> None:
    out = _post(request_with(person_b={**BERLIN, "date": "1990-01-05", "birth_time_known": False}))
    entries = out["sign_layer"]["factors"]["person_b"]
    assert [e["factor"] for e in entries] == SIGN_LAYER_PLANETS
    assert all(isinstance(e["sign_certain"], bool) for e in entries)
    assert _entry(out, "person_b", "Moon")["sign_certain"] is False  # the D15 Moon ingress day


@pytest.mark.swieph
def test_http_non_moon_aspect_is_time_sensitive_on_the_pinned_day() -> None:
    out = _post(request_with(person_b={"date": NON_MOON_ASPECT_DATE, "birth_time_known": False}))
    row = _row(out, "Venus", "Sun")
    assert row["type"] == "opposition"
    assert row["time_sensitive"] is True


@pytest.mark.swieph
def test_http_swap_with_unknown_time_mirrors_on_the_pinned_day() -> None:
    body = request_with(person_b={"date": NON_MOON_ASPECT_DATE, "birth_time_known": False})
    ab, ba = _post(body), _post(swapped(body))
    assert any(r["time_sensitive"] for r in ab["aspects"])
    assert_mirrored(ab, ba)


@pytest.mark.swieph
def test_http_non_moon_overlay_is_time_sensitive_on_the_pinned_day() -> None:
    out = _post(request_with(person_b={"date": NON_MOON_OVERLAY_DATE, "birth_time_known": False}))
    row = _overlay(out, "b_in_a", "Mercury")
    assert row["status"] == "ok" and row["time_sensitive"] is True
    assert all(r["time_sensitive"] is False for r in out["house_overlays"]["a_in_b"])  # gated host


def test_http_known_time_response_has_no_day_uncertainty() -> None:
    out = _post(VALID_SYNASTRY_REQUEST)
    assert out["aspects"] and all(r["time_sensitive"] is False for r in out["aspects"])
    overlays = out["house_overlays"]["a_in_b"] + out["house_overlays"]["b_in_a"]
    assert len(overlays) == 20 and all(r["time_sensitive"] is False for r in overlays)
    entries = [e for p in ("person_a", "person_b") for e in out["sign_layer"]["factors"][p]]
    assert entries and all(e["sign_certain"] is None and e["moon_range_deg"] is None for e in entries)
