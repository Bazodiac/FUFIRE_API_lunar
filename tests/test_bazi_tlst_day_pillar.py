"""FBP-TST-005 / DEV-2026-011 — the TLST day pillar follows the apparent-solar date.

Owner decision E5-A (2026-10-16, ``docs/plans/2026-10-16-tlst-fix-sprint-2.md``):
under ``standard=TLST`` the calendar date the day pillar is derived from is the
date of the TLST instant (``civil_date + date_rollover``), with ``boundary=zi``
adding one day once ``tlst_hours >= 23``. This is the same rule the LMT path
already applies through ``to_chart_local`` (LMT-labelled datetime → LMT date).

Oracle: the boundary cases are built by *inverting* Swiss Ephemeris —
``swe.lat_to_lmt`` turns a target apparent-solar wall-clock into the UTC
instant, which is then expressed in the IANA zone and sent to the API. The
expected day pillar is whatever a ``CIVIL`` request at noon of the expected
date yields, so the test never trusts the engine's own TLST arithmetic.

Targets sit ±2 min off the 23:00 / 00:00 / 01:00 edges: the engine's EoT is
still the day-of-year approximation (≤ 0.8 min off swisseph until FBP-TST-006),
so a target exactly on the edge would be a test of the approximation, not of
the day-boundary rule.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import swisseph as swe
from fastapi.testclient import TestClient

from bazi_engine.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _pin_swisseph_global_state():
    from bazi_engine.ephemeris import _resolve_ephe_path
    swe.set_ephe_path(str(_resolve_ephe_path(None)))
    swe.set_sid_mode(0)
    yield


# (label, tz, lon, lat, solar base date) — one site west and one east of its zone meridian.
SITES = [
    ("madrid_cet_west", "Europe/Madrid", -3.7038, 40.4168, date(2024, 2, 21)),      # LMT ≈ CET − 75 min
    ("auckland_nzdt_east", "Pacific/Auckland", 174.7633, -36.8485, date(2024, 1, 15)),  # LMT ≈ NZDT − 81 min
]

# (target TLST wall-clock on the base date, expected date offset for midnight, for zi)
TARGETS = [
    ("22:58", 0, 0),
    ("23:02", 0, 1),
    ("23:58", 0, 1),
    ("00:02", 0, 0),
    ("00:58", 0, 0),
    ("01:02", 0, 0),
]


def _civil_iso_for_tlst(tz: str, lon: float, solar_date: date, hhmm: str) -> str:
    """Invert swisseph: apparent-solar wall-clock at ``lon`` → civil ISO in ``tz``."""
    hh, mm = (int(x) for x in hhmm.split(":"))
    jd_lat = swe.julday(solar_date.year, solar_date.month, solar_date.day, hh + mm / 60.0)
    r = swe.lat_to_lmt(jd_lat, lon)
    jd_lmt = r[0] if isinstance(r, tuple) else r
    jd_ut = jd_lmt - lon / 360.0
    y, m, d, h = swe.revjul(jd_ut)
    utc = datetime(int(y), int(m), int(d), tzinfo=timezone.utc) + timedelta(hours=h)
    civil = utc.astimezone(ZoneInfo(tz)).replace(microsecond=0)
    return civil.replace(tzinfo=None).isoformat()


def _day_pillar(payload: dict) -> dict:
    r = client.post("/calculate/bazi", json=payload)
    if r.status_code == 503:
        pytest.skip("ephemeris unavailable")
    assert r.status_code == 200, r.text
    body = r.json()
    # GT6 invariant: trace day must match the headline day pillar.
    from bazi_engine.constants import BRANCHES, STEMS
    p = body["pillars"]["day"]
    s, b = STEMS.index(p["stamm"]), BRANCHES.index(p["zweig"])
    headline_idx = next(i for i in range(60) if i % 10 == s and i % 12 == b)
    assert body["derivation_trace"]["day"]["sexagenary_index"] == headline_idx
    return p


def _expected_pillar(tz: str, lon: float, lat: float, expected_date: date) -> dict:
    return _day_pillar({
        "date": f"{expected_date.isoformat()}T12:00:00", "tz": tz, "lon": lon, "lat": lat,
        "standard": "CIVIL", "boundary": "midnight",
    })


@pytest.mark.parametrize("site", SITES, ids=[s[0] for s in SITES])
@pytest.mark.parametrize("target", TARGETS, ids=[t[0] for t in TARGETS])
@pytest.mark.parametrize("boundary", ["midnight", "zi"])
def test_tlst_day_pillar_boundary_matrix(site, target, boundary):
    _, tz, lon, lat, solar_date = site
    hhmm, off_midnight, off_zi = target
    civil_iso = _civil_iso_for_tlst(tz, lon, solar_date, hhmm)
    expected_date = solar_date + timedelta(days=off_zi if boundary == "zi" else off_midnight)

    actual = _day_pillar({
        "date": civil_iso, "tz": tz, "lon": lon, "lat": lat,
        "standard": "TLST", "boundary": boundary,
    })
    expected = _expected_pillar(tz, lon, lat, expected_date)
    assert actual == expected, (
        f"{site[0]} TLST {hhmm} ({civil_iso} civil), boundary={boundary}: "
        f"expected day pillar of {expected_date} {expected}, got {actual}"
    )


def test_madrid_0030_cet_uses_previous_solar_day():
    """The DEV-2026-011 case: Madrid 2024-02-22 00:30 CET has TLST 23:01 on 02-21."""
    actual = _day_pillar({"date": "2024-02-22T00:30:00", "tz": "Europe/Madrid", "lon": -3.7038,
                          "lat": 40.4168, "standard": "TLST", "boundary": "midnight"})
    assert actual == _expected_pillar("Europe/Madrid", -3.7038, 40.4168, date(2024, 2, 21))
    # Under zi the 23:01 solar hour rolls forward again → 02-22.
    actual_zi = _day_pillar({"date": "2024-02-22T00:30:00", "tz": "Europe/Madrid", "lon": -3.7038,
                             "lat": 40.4168, "standard": "TLST", "boundary": "zi"})
    assert actual_zi == _expected_pillar("Europe/Madrid", -3.7038, 40.4168, date(2024, 2, 22))


def test_rollover_plus_one_east_of_greenwich_in_utc_zone():
    """UTC zone, lon +30°: civil 23:30 → TLST ≈ 01:29 next day → next day's pillar."""
    actual = _day_pillar({"date": "2024-06-15T23:30:00", "tz": "UTC", "lon": 30.0, "lat": 50.0,
                          "standard": "TLST", "boundary": "midnight"})
    assert actual == _expected_pillar("UTC", 30.0, 50.0, date(2024, 6, 16))


def test_tlst_and_lmt_agree_when_on_the_same_side_of_the_boundary():
    """LMT and TLST differ only by the EoT; when both sit on the same calendar
    date they must yield the same day pillar (Madrid 00:30 CET: LMT 23:15,
    TLST 23:01, both on 02-21)."""
    base = {"date": "2024-02-22T00:30:00", "tz": "Europe/Madrid", "lon": -3.7038, "lat": 40.4168,
            "boundary": "midnight"}
    assert _day_pillar({**base, "standard": "TLST"}) == _day_pillar({**base, "standard": "LMT"})


def test_civil_and_lmt_paths_unchanged():
    """Regression guard: the E5-A rule touches only the TLST branch."""
    base = {"date": "2024-02-22T00:30:00", "tz": "Europe/Madrid", "lon": -3.7038, "lat": 40.4168}
    civil = _day_pillar({**base, "standard": "CIVIL", "boundary": "midnight"})
    assert civil == _expected_pillar("Europe/Madrid", -3.7038, 40.4168, date(2024, 2, 22))
    lmt = _day_pillar({**base, "standard": "LMT", "boundary": "midnight"})
    assert lmt == _expected_pillar("Europe/Madrid", -3.7038, 40.4168, date(2024, 2, 21))
