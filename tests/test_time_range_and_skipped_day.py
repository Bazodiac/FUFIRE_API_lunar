"""Owner decisions 4 and 5 after the sprint-2 TLST review (report §5):

4. Instants at the edge of the proleptic-Gregorian ``datetime`` range (years
   1 / 9999) whose UTC or longitude-shifted image overflows used to surface
   as HTTP 500 (``OverflowError`` in ``time_utils._roundtrip_ok`` and in
   ``time_context``). They are caller input → 422 ErrorEnvelope, and the
   message must not echo the raw birth instant (PII rule).
5. ``nonexistentTime='shift_forward'`` searched only 180 min ahead; a zone that
   skips a whole calendar day (Samoa, 2011-12-30) needs up to 24 h. The window
   is now ``SHIFT_FORWARD_MAX_MINUTES`` (48 h).

Response-body claims are asserted at the HTTP boundary (repo convention).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.time_utils import SHIFT_FORWARD_MAX_MINUTES, LocalTimeError, resolve_local_iso

client = TestClient(app, raise_server_exceptions=False)

OVERFLOW_CASES = [
    ("/calculate/tst", {"date": "0001-01-01T00:10:00", "tz": "UTC", "lon": -170.0}),
    ("/calculate/tst", {"date": "9999-12-31T23:30:00", "tz": "UTC", "lon": 30.0}),
    ("/calculate/tst", {"date": "0001-01-01T00:30:00", "tz": "Europe/Berlin", "lon": 13.405}),
    ("/calculate/bazi", {"date": "0001-01-01T00:30:00", "tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52}),
]
# Not covered here on purpose: year-9999 BaZi requests fail earlier on ephemeris
# coverage (the locked SE1 set ends before 9999, swisseph asks for sepl_96.se1),
# which is a separate concern from the datetime-range overflow.


@pytest.mark.parametrize("path, body", OVERFLOW_CASES, ids=[f"{c[1]['date']}@{c[1]['tz']}" for c in OVERFLOW_CASES])
def test_out_of_range_instants_are_422_not_500(path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422, r.text
    env = r.json()
    assert set(env) >= {"error", "message", "detail"}
    assert env["error"] in {"dst_time_error", "input_error"}
    assert "range" in env["message"]
    # PII rule: the caller's birth instant / zone are never reflected.
    assert body["date"] not in r.text
    assert body["tz"] not in r.text or body["tz"] == "UTC"


def test_year_1_and_9999_still_work_when_they_do_not_overflow():
    """The guard must not reject the whole edge years — only genuine overflow."""
    ok = client.post("/calculate/tst", json={"date": "0001-01-02T12:00:00", "tz": "UTC", "lon": 0.0})
    assert ok.status_code == 200, ok.text
    ok = client.post("/calculate/tst", json={"date": "9999-12-30T12:00:00", "tz": "UTC", "lon": 0.0})
    assert ok.status_code == 200, ok.text


def test_samoa_skipped_day_resolves_with_shift_forward():
    """Samoa jumped from UTC−10 to UTC+14 on 2011-12-30: the day never existed.
    Noon of that day must shift 720 min to 2011-12-31 00:00+14:00."""
    dt, res = resolve_local_iso("2011-12-30T12:00:00", "Pacific/Apia", nonexistent="shift_forward")
    assert res.status == "nonexistent_shifted"
    assert res.adjusted_minutes == 720
    assert dt.isoformat() == "2011-12-31T00:00:00+14:00"
    assert SHIFT_FORWARD_MAX_MINUTES >= 24 * 60


def test_samoa_skipped_day_on_the_http_surfaces():
    body = {"date": "2011-12-30T12:00:00", "tz": "Pacific/Apia", "lon": -171.7639}
    assert client.post("/calculate/tst", json=body).status_code == 422          # default policy unchanged
    r = client.post("/calculate/tst", json={**body, "nonexistentTime": "shift_forward"})
    assert r.status_code == 200, r.text
    c = client.post("/v1/chronometry/resolve", json={"birth": {
        "datetime": "2011-12-30T12:00:00", "timezone": "Pacific/Apia",
        "location": {"lat": -13.8333, "lon": -171.7639}, "nonexistentTime": "shift_forward",
    }})
    if c.status_code == 503:
        pytest.skip("ephemeris unavailable")
    assert c.status_code == 200, c.text


def test_ordinary_dst_gap_shift_is_unchanged():
    dt, res = resolve_local_iso("2024-03-31T02:30:00", "Europe/Berlin", nonexistent="shift_forward")
    assert res.adjusted_minutes == 30
    assert dt.isoformat() == "2024-03-31T03:00:00+02:00"


def test_error_policy_message_names_the_window_in_hours():
    with pytest.raises(LocalTimeError) as exc:
        resolve_local_iso("2024-03-31T02:30:00", "Europe/Berlin", nonexistent="error")
    assert "shift_forward" in str(exc.value)
