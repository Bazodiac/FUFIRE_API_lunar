"""Owner decisions 2 and 3 after the sprint-2 review (R1 findings F10/F11):

- ``/chronometry/resolve`` accepts ``ambiguousTime`` / ``nonexistentTime`` with
  the same semantics as ``/calculate/bazi`` and ``/calculate/tst`` — a DST
  fall-back duplicate is no longer silently resolved as the earlier instant.
- ``tlst_date_rollover`` (additive) on the chronometry frame, the
  ``/personalize`` chronometry extras and the BaZi trace ``time_resolution``
  block places ``true_solar_time`` on its own calendar day next to the civil
  ``julian_day_number``.

All response-body claims are asserted at the HTTP boundary (repo convention).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

client = TestClient(app)

BERLIN_FALLBACK = {"datetime": "2024-10-27T02:30:00", "timezone": "Europe/Berlin",
                   "location": {"lat": 52.52, "lon": 13.405}}
BERLIN_GAP = {"datetime": "2024-03-31T02:30:00", "timezone": "Europe/Berlin",
              "location": {"lat": 52.52, "lon": 13.405}}
MADRID_0030 = {"datetime": "2024-02-22T00:30:00", "timezone": "Europe/Madrid",
               "location": {"lat": 40.4168, "lon": -3.7038}}


def _resolve(birth: dict, **extra):
    r = client.post("/v1/chronometry/resolve", json={"birth": {**birth, **extra}})
    if r.status_code == 503:
        pytest.skip("ephemeris unavailable")
    return r


def _bazi(date: str, tz: str, lon: float, lat: float, **extra):
    r = client.post("/calculate/bazi", json={"date": date, "tz": tz, "lon": lon, "lat": lat,
                                             "standard": "TLST", **extra})
    if r.status_code == 503:
        pytest.skip("ephemeris unavailable")
    assert r.status_code == 200, r.text
    return r.json()


def test_ambiguous_time_default_is_earlier_and_later_shifts_one_hour():
    default = _resolve(BERLIN_FALLBACK)
    earlier = _resolve(BERLIN_FALLBACK, ambiguousTime="earlier")
    later = _resolve(BERLIN_FALLBACK, ambiguousTime="later")
    for r in (default, earlier, later):
        assert r.status_code == 200, r.text
    assert default.json()["chronometry"] == earlier.json()["chronometry"]
    jd_e = earlier.json()["chronometry"]["julian_day"]
    jd_l = later.json()["chronometry"]["julian_day"]
    assert jd_l - jd_e == pytest.approx(1 / 24, abs=1e-9)   # one real hour apart
    assert earlier.json()["chronometry"]["true_solar_time"] != later.json()["chronometry"]["true_solar_time"]


def test_later_fold_matches_calculate_bazi_trace():
    """The frame and the BaZi trace resolve the same fold to the same instant."""
    chrono = _resolve(BERLIN_FALLBACK, ambiguousTime="later").json()["chronometry"]
    trace = _bazi("2024-10-27T02:30:00", "Europe/Berlin", 13.405, 52.52,
                  ambiguousTime="later")["derivation_trace"]["time_resolution"]
    assert trace["utc"] == "2024-10-27T01:30:00+00:00"
    hh, mm = (int(x) for x in chrono["true_solar_time"].split(":"))
    assert abs(hh + mm / 60 - trace["tlst_hours"]) < 1 / 60 + 1e-6


def test_nonexistent_time_error_by_default_and_shift_forward_resolves():
    err = _resolve(BERLIN_GAP)
    assert err.status_code == 422, err.text
    ok = _resolve(BERLIN_GAP, nonexistentTime="shift_forward")
    assert ok.status_code == 200, ok.text
    assert ok.json()["chronometry"]["true_solar_time"] is not None


def test_invalid_policy_values_are_rejected():
    assert _resolve(BERLIN_FALLBACK, ambiguousTime="middle").status_code == 422
    assert _resolve(BERLIN_FALLBACK, nonexistentTime="ignore").status_code == 422


def test_tlst_date_rollover_places_true_solar_time_on_the_previous_day():
    """Madrid 2024-02-22 00:30 CET: TLST 23:01 on 02-21 (R1 finding F11)."""
    chrono = _resolve(MADRID_0030).json()["chronometry"]
    assert chrono["true_solar_time"].startswith("23:0")
    assert chrono["tlst_date_rollover"] == -1
    assert chrono["julian_day_number"] == 2460363          # civil 02-22, unchanged contract
    trace = _bazi("2024-02-22T00:30:00", "Europe/Madrid", -3.7038, 40.4168)["derivation_trace"]
    assert trace["time_resolution"]["tlst_date_rollover"] == -1
    assert trace["day"]["julian_day_number"] == chrono["julian_day_number"] + chrono["tlst_date_rollover"]


def test_tlst_date_rollover_is_zero_for_an_ordinary_afternoon():
    chrono = _resolve({"datetime": "1990-07-15T15:44:00", "timezone": "Europe/Berlin",
                       "location": {"lat": 52.3759, "lon": 9.732}}).json()["chronometry"]
    assert chrono["tlst_date_rollover"] == 0


def test_tlst_date_rollover_is_null_when_birth_time_unknown():
    for birth in (
        {"datetime": "1990-07-15", "timezone": "Europe/Berlin", "location": {"lat": 52.38, "lon": 9.73}},
        {"datetime": "1990-07-15T15:44:00", "timezone": "Europe/Berlin",
         "location": {"lat": 52.38, "lon": 9.73}, "time_known": False},
    ):
        chrono = _resolve(birth).json()["chronometry"]
        assert chrono["true_solar_time"] is None
        assert chrono["tlst_date_rollover"] is None


def test_personalize_chronometry_extras_carry_the_rollover():
    from bazi_engine.chronometry import resolve_chronometry
    frame = resolve_chronometry("2024-02-22T00:30:00", "Europe/Madrid", 40.4168, -3.7038)
    assert frame.tlst_date_rollover == -1
    # The /personalize aggregation forwards the frame field by field; the
    # endpoint itself needs geocoding, so assert the mapping on the module it uses.
    import inspect

    import bazi_engine.routers.personalize as personalize
    assert '"tlst_date_rollover": frame.tlst_date_rollover' in inspect.getsource(personalize)
