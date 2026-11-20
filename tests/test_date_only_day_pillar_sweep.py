"""Date-only requests keep the day pillar on the calendar day — independent check.

1170 seeded random dates 1900–2030 at nine places, each sent as a bare date to
POST /v1/calculate/bazi. The expected day pillar comes from an independent
formula, (JDN + 49) mod 60, with the JDN computed here (Fliegel & Van Flandern),
not by the engine. The formula itself is checked at two known dates.

Finding (docs/precision/date-only-birth-input.md): 12:00 civil time keeps the
TRUE-SOLAR day on the calendar day only where zone offset and longitude differ
by less than 12 hours. Pacific/Kiritimati (UTC+14 since 1995 at 157° W) and
Pacific/Apia (UTC+13/+14 since 2011-12-31 at 172° W) lie a whole day ahead of
their solar time: under TLST every hour of such a civil day is the previous
solar day. There the TLST day pillar is the calendar day minus one; under CIVIL
it is the calendar day everywhere.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from typing import List, Tuple

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

STEMS = ["Jia", "Yi", "Bing", "Ding", "Wu", "Ji", "Geng", "Xin", "Ren", "Gui"]
BRANCHES = ["Zi", "Chou", "Yin", "Mao", "Chen", "Si", "Wu", "Wei", "Shen", "You", "Xu", "Hai"]

PLACES = [
    ("Berlin", "Europe/Berlin", 52.52, 13.405),
    ("Madrid", "Europe/Madrid", 40.4168, -3.7038),
    ("London", "Europe/London", 51.5074, -0.1278),
    ("Kashgar", "Asia/Shanghai", 39.4677, 75.9938),
    ("Anchorage", "America/Anchorage", 61.2181, -149.9003),
    ("Honolulu", "Pacific/Honolulu", 21.3069, -157.8583),
    ("Apia", "Pacific/Apia", -13.8333, -171.7667),
    ("Kiritimati", "Pacific/Kiritimati", 1.8721, -157.4278),
    ("Sydney", "Australia/Sydney", -33.8688, 151.2093),
]
PER_PLACE = 130  # 9 × 130 = 1170 samples
FIRST, LAST = date(1900, 1, 1), date(2030, 12, 31)

# Local days that do not exist (the zone jumped across the date line).
SKIPPED_DAYS = {("Pacific/Apia", date(2011, 12, 30)), ("Pacific/Kiritimati", date(1994, 12, 31))}
# From these dates on, the zone's civil day is the previous true-solar day.
DATE_LINE_FROM = {"Pacific/Apia": date(2011, 12, 31), "Pacific/Kiritimati": date(1995, 1, 1)}


def jdn(d: date) -> int:
    """Julian Day Number of a Gregorian date (Fliegel & Van Flandern 1968)."""
    a = (14 - d.month) // 12
    y = d.year + 4800 - a
    m = d.month + 12 * a - 3
    return d.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045


def day_pillar(d: date) -> Tuple[str, str]:
    idx = (jdn(d) + 49) % 60
    return STEMS[idx % 10], BRANCHES[idx % 12]


def test_formula_reference_dates() -> None:
    assert (jdn(date(2000, 1, 1)) + 49) % 60 == 54
    assert day_pillar(date(2000, 1, 1)) == ("Wu", "Wu")      # 戊午
    assert (jdn(date(1949, 10, 1)) + 49) % 60 == 0
    assert day_pillar(date(1949, 10, 1)) == ("Jia", "Zi")    # 甲子 (1949-10-01)


def _samples() -> List[Tuple[str, str, float, float, date]]:
    rng = random.Random(20261118)
    span = (LAST - FIRST).days
    out = []
    for name, tz, lat, lon in PLACES:
        for _ in range(PER_PLACE):
            out.append((name, tz, lat, lon, FIRST + timedelta(days=rng.randrange(span + 1))))
    return out


SAMPLES = _samples()


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _day(client: TestClient, tz: str, lat: float, lon: float, d: date, standard: str):
    resp = client.post("/v1/calculate/bazi", json={
        "date": d.isoformat(), "tz": tz, "lat": lat, "lon": lon,
        "standard": standard, "include_trace": False,
    })
    if (tz, d) in SKIPPED_DAYS:
        assert resp.status_code == 422, resp.text
        return None
    assert resp.status_code == 200, (tz, d, resp.text)
    p = resp.json()["pillars"]["day"]
    return p["stamm"], p["zweig"]


def test_sample_size() -> None:
    assert len(SAMPLES) >= 1000
    assert {s[1] for s in SAMPLES} == {p[1] for p in PLACES}


def test_civil_date_only_day_pillar_is_calendar_day(client: TestClient) -> None:
    misses = []
    for name, tz, lat, lon, d in SAMPLES:
        got = _day(client, tz, lat, lon, d, "CIVIL")
        if got is not None and got != day_pillar(d):
            misses.append((name, d.isoformat(), got, day_pillar(d)))
    assert misses == []


def test_tlst_date_only_day_pillar(client: TestClient) -> None:
    """TLST: calendar day everywhere except the date-line zones after their switch,
    where it is the calendar day minus one (the documented exception)."""
    misses = []
    date_line = 0
    for name, tz, lat, lon, d in SAMPLES:
        got = _day(client, tz, lat, lon, d, "TLST")
        if got is None:
            continue
        on_date_line = tz in DATE_LINE_FROM and d >= DATE_LINE_FROM[tz]
        expected = day_pillar(d - timedelta(days=1)) if on_date_line else day_pillar(d)
        date_line += on_date_line
        if got != expected:
            misses.append((name, d.isoformat(), got, expected))
    assert misses == []
    assert date_line > 0  # the exception is exercised, not vacuous
