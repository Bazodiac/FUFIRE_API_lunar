"""FU-TLST-POLICY / INC-1 — opt-in True-Local-Solar-Time BaZi + Natal under /v2.

``POST /v2/calculate/bazi`` and ``POST /v2/calculate/bazi/natal`` compute the
four pillars with ``standard="TLST"`` only, through the existing engine
(``compute_bazi`` → ``time_context``). Every claim here is asserted at the
HTTP boundary (repo convention, WS-A retro).

Independence of the expectations (AC-03): astronomical expectations come from
Swiss Ephemeris (``swe.lmt_to_lat`` / ``swe.solcross_ut``), never from the
FuFirE function under test. Instants are *constructed* from a target apparent
solar wall-clock by inverting ``swe.lmt_to_lat``; the hour branch is derived
with the test's own half-open formula; the expected day pillar is the
documented ``(JDN + 49) % 60`` rule (CLAUDE.md, "Day Pillar Calibration")
evaluated with ``swe.julday`` on the oracle's solar date. That rule depends
on the day-cycle anchor, which stays ``unverified`` — these tests prove the
TLST date *selection*, not the anchor.

Instants inside the documented 0.1-minute EoT tolerance of a decision edge are
not compared with the oracle: the engine (Meeus) and Swiss Ephemeris may
legitimately fall on opposite sides there. For those the response must flag
``uncertainty.status == "boundary_within_tolerance"`` and its decision must be
consistent with its own published ``tlst_hours`` (engine self-consistency).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
import swisseph as swe
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.bazi import compute_bazi
from bazi_engine.types import BaziInput

pytestmark = pytest.mark.swieph

BAZI = "/v2/calculate/bazi"
NATAL = "/v2/calculate/bazi/natal"
ROUTES = (BAZI, NATAL)

EOT_TOL_MIN = 0.1          # documented Meeus-vs-swisseph bound (FBP-TST-006)
CLEAR_MARGIN_MIN = 1.0     # oracle-anchored boundary cases sit >= 1 min off the edge

STEMS = ["Jia", "Yi", "Bing", "Ding", "Wu", "Ji", "Geng", "Xin", "Ren", "Gui"]
BRANCHES = ["Zi", "Chou", "Yin", "Mao", "Chen", "Si", "Wu", "Wei", "Shen", "You", "Xu", "Hai"]

HANNOVER = {"date": "1990-07-15T15:44:00", "tz": "Europe/Berlin", "lat": 52.3759, "lon": 9.732}
MADRID = {"date": "2024-02-22T00:30:00", "tz": "Europe/Madrid", "lat": 40.4168, "lon": -3.7038}


# ── oracle helpers (Swiss Ephemeris only) ────────────────────────────────────


@pytest.fixture(autouse=True)
def _pin_swisseph_global_state():
    """Same re-pin as tests/test_tlst_reference_corpus.py: another test file can
    leave swisseph pointed at a throwaway directory."""
    from bazi_engine.ephemeris import _resolve_ephe_path
    swe.set_ephe_path(str(_resolve_ephe_path(None)))
    swe.set_sid_mode(0)
    yield


def _jd_ut(utc: datetime) -> float:
    return swe.julday(utc.year, utc.month, utc.day,
                      utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3.6e9)


def oracle_solar(utc: datetime, lon: float) -> tuple[date, float]:
    """Apparent solar (date, hour-of-day) of a UTC instant via swe.lmt_to_lat."""
    r = swe.lmt_to_lat(_jd_ut(utc) + lon / 360.0, lon)
    jd_lat = r[0] if isinstance(r, tuple) else r
    y, m, d, h = swe.revjul(jd_lat)
    return date(int(y), int(m), int(d)), float(h)


def utc_for_solar(solar_date: date, solar_hours: float, lon: float) -> datetime:
    """Invert swe.lmt_to_lat: the UTC instant whose apparent solar time at
    ``lon`` is ``solar_date`` + ``solar_hours`` (fixed-point on the oracle)."""
    target = datetime(solar_date.year, solar_date.month, solar_date.day, tzinfo=timezone.utc) + timedelta(
        hours=solar_hours)
    utc = target - timedelta(minutes=lon * 4.0)
    for _ in range(8):
        d, h = oracle_solar(utc, lon)
        got = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(hours=h)
        utc -= got - target
    d, h = oracle_solar(utc, lon)
    got = datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(hours=h)
    assert abs((got - target).total_seconds()) < 1e-3, (got, target)
    return utc


def independent_branch(hours: float) -> int:
    """Half-open 2-hour bins, Zi = [23, 1). Written here, not imported."""
    return int(((hours + 1.0) % 24.0) // 2.0)


def expected_day_pillar(d: date) -> str:
    jdn = int(swe.julday(d.year, d.month, d.day, 12.0) + 0.5)
    idx = (jdn + 49) % 60
    return f"{STEMS[idx % 10]}-{BRANCHES[idx % 12]}"


def civil_local_iso(utc: datetime, tz: str) -> tuple[str, int]:
    local = utc.astimezone(ZoneInfo(tz))
    return local.replace(tzinfo=None).isoformat(), local.fold


def circ_min(a_h: float, b_h: float) -> float:
    return abs(((a_h - b_h + 12.0) % 24.0) - 12.0) * 60.0


def edge_distance_min(hours: float, boundary: str) -> float:
    edges = [float(e) for e in range(1, 24, 2)] + ([0.0] if boundary == "midnight" else [])
    return min(circ_min(hours, e) for e in edges)


# ── request / response helpers ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def v2_body(base: dict, boundary: str = "midnight", **extra) -> dict:
    return {**base, "standard": "TLST", "boundary": boundary, **extra}


def pillars_of(route: str, body: dict) -> list[str]:
    p = body["pillars"]
    if route == BAZI:
        return [f"{p[k]['stamm']}-{p[k]['zweig']}" for k in ("year", "month", "day", "hour")]
    return [f"{p[k]['stem']}-{p[k]['branch']}" for k in ("year", "month", "day", "hour")]


def post_ok(client: TestClient, route: str, body: dict) -> dict:
    r = client.post(route, json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ═════════════════════════════════════════════════════════════════════════════
# AC-01 — TLST is really active (Hannover reference, Madrid solar-date rollover)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("route", ROUTES)
def test_hannover_v2_equals_explicit_engine_tlst_and_oracle(client, route):
    body = post_ok(client, route, v2_body(HANNOVER))
    engine = compute_bazi(BaziInput(
        birth_local=HANNOVER["date"], timezone=HANNOVER["tz"], longitude_deg=HANNOVER["lon"],
        latitude_deg=HANNOVER["lat"], time_standard="TLST", day_boundary="midnight",
    ))
    want = [f"{STEMS[p.stem_index]}-{BRANCHES[p.branch_index]}"
            for p in (engine.pillars.year, engine.pillars.month, engine.pillars.day, engine.pillars.hour)]
    assert pillars_of(route, body) == want
    tb = body["time_basis"]
    assert tb["standard"] == "TLST"
    assert tb["utc"] == "1990-07-15T13:44:00+00:00"
    assert tb["resolved_local"] == "1990-07-15T15:44:00+02:00"
    o_date, o_hours = oracle_solar(datetime(1990, 7, 15, 13, 44, tzinfo=timezone.utc), HANNOVER["lon"])
    assert circ_min(tb["tlst_hours"], o_hours) < EOT_TOL_MIN
    assert tb["tlst_date"] == o_date.isoformat() == "1990-07-15"
    assert pillars_of(route, body)[3].endswith("-" + BRANCHES[independent_branch(o_hours)])
    assert pillars_of(route, body)[3] == "Yi-Wei"      # civil 15:44 would be Shen
    assert tb["eot_source"] == "meeus_1998"
    assert tb["hour_branch_basis"] == "tlst_hours"


def test_hannover_v2_equals_v1_explicit_tlst(client):
    v2 = post_ok(client, BAZI, v2_body(HANNOVER))
    v1 = post_ok(client, "/v1/calculate/bazi", {**HANNOVER, "standard": "TLST"})
    assert v2["pillars"] == v1["pillars"]
    assert v2["derivation_trace"]["time_resolution"] == v1["derivation_trace"]["time_resolution"]
    assert v2["derivation_trace"]["hour"]["time_standard_used"] == "TLST"
    assert v2["derivation_trace"]["hour"]["true_solar_time_used"] is True
    assert v2["derivation_trace"]["time_resolution"]["effective_standard"] == "TLST"


@pytest.mark.parametrize("route", ROUTES)
def test_madrid_solar_date_rollover_midnight(client, route):
    body = post_ok(client, route, v2_body(MADRID, "midnight"))
    tb = body["time_basis"]
    utc = datetime(2024, 2, 21, 23, 30, tzinfo=timezone.utc)
    o_date, o_hours = oracle_solar(utc, MADRID["lon"])
    assert tb["utc"] == "2024-02-21T23:30:00+00:00"
    assert o_date == date(2024, 2, 21) and 23.0 < o_hours < 23.1
    assert tb["tlst_date"] == "2024-02-21"
    assert tb["tlst_date_rollover"] == -1
    assert tb["day_pillar_date"] == "2024-02-21"
    assert tb["day_boundary"] == "midnight"
    assert tb["day_boundary_rule"] == "tlst_solar_midnight"
    assert pillars_of(route, body)[2] == expected_day_pillar(date(2024, 2, 21))
    assert pillars_of(route, body)[3].endswith("-Zi")


@pytest.mark.parametrize("route", ROUTES)
def test_madrid_zi_boundary_advances_from_tlst_hour(client, route):
    body = post_ok(client, route, v2_body(MADRID, "zi"))
    tb = body["time_basis"]
    assert tb["tlst_date"] == "2024-02-21"
    assert tb["day_pillar_date"] == "2024-02-22"
    assert tb["day_boundary_rule"] == "tlst_zi_hour"
    assert tb["zi_start_hour"] == 23.0
    assert pillars_of(route, body)[2] == expected_day_pillar(date(2024, 2, 22))


@pytest.mark.parametrize("route", ROUTES)
def test_no_hidden_civil_or_lmt_fallback(client, route):
    """Madrid 00:30 CET: CIVIL day = 02-22, LMT day = 02-21 but LMT hour 00:45
    is Zi too — only the TLST *date* AND trace distinguish; check all three."""
    body = post_ok(client, route, v2_body(MADRID))
    civil = post_ok(client, "/v1/calculate/bazi", {**MADRID, "standard": "CIVIL"})
    assert pillars_of(route, body)[2] != f"{civil['pillars']['day']['stamm']}-{civil['pillars']['day']['zweig']}"
    assert body["time_basis"]["standard"] == "TLST"
    assert body["policy"]["time_standard"] == "TLST"


# ═════════════════════════════════════════════════════════════════════════════
# Provenance, policy and anchor status (no claimed verification)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("route", ROUTES)
def test_policy_block_keeps_anchor_unverified_and_opt_in(client, route):
    body = post_ok(client, route, v2_body(HANNOVER))
    pol = body["policy"]
    assert pol == {
        "time_standard": "TLST",
        "opt_in": True,
        "v1_default_standard": "CIVIL",
        "ruleset_id": "standard_bazi_2026",
        "ruleset_version": pol["ruleset_version"],
        "day_anchor_id": "standard_bazi_2026:jdn_2419451_unverified",
        "day_anchor_verification": "unverified",
    }
    assert isinstance(pol["ruleset_version"], str) and pol["ruleset_version"]


def test_bazi_v2_trace_is_always_present_and_consistent(client):
    body = post_ok(client, BAZI, v2_body(HANNOVER))
    tr = body["derivation_trace"]
    assert tr["provenance_ids"]["time_policy_id"] == "tlst_midnight"
    assert tr["day"]["day_anchor_evidence"]["anchor_verification"] == "unverified"
    assert tr["hour"]["branch_index"] == BRANCHES.index(body["pillars"]["hour"]["zweig"])
    assert tr["time_resolution"]["tlst_hours"] == body["time_basis"]["tlst_hours"]
    assert tr["time_resolution"]["utc"] == body["time_basis"]["utc"]


@pytest.mark.parametrize("route", ROUTES)
def test_input_is_echoed(client, route):
    body = post_ok(client, route, v2_body(HANNOVER, "zi"))
    assert body["input"] == {
        "date": HANNOVER["date"], "tz": HANNOVER["tz"], "lat": HANNOVER["lat"], "lon": HANNOVER["lon"],
        "standard": "TLST", "boundary": "zi", "ambiguousTime": None, "nonexistentTime": "error",
        "birth_time_known": True,
    }


# ═════════════════════════════════════════════════════════════════════════════
# AC-02 — hard input validation (real HTTP boundary, no PII echo)
# ═════════════════════════════════════════════════════════════════════════════

_VALID = v2_body({"date": "1987-11-23T09:41:17", "tz": "Europe/Vienna", "lat": 48.2082, "lon": 16.3738})


def _without(key: str) -> dict:
    return {k: v for k, v in _VALID.items() if k != key}


_INVALID_BODIES = {
    "missing_lat": _without("lat"),
    "missing_lon": _without("lon"),
    "missing_tz": _without("tz"),
    "missing_date": _without("date"),
    "missing_standard": _without("standard"),
    "missing_boundary": _without("boundary"),
    "lat_above_90": {**_VALID, "lat": 90.5},
    "lat_below_minus_90": {**_VALID, "lat": -90.5},
    "lon_above_180": {**_VALID, "lon": 180.25},
    "lon_below_minus_180": {**_VALID, "lon": -180.25},
    "standard_civil": {**_VALID, "standard": "CIVIL"},
    "standard_lmt": {**_VALID, "standard": "LMT"},
    "standard_lowercase": {**_VALID, "standard": "tlst"},
    "boundary_unknown": {**_VALID, "boundary": "noon"},
    "lat_null": {**_VALID, "lat": None},
    "lon_string": {**_VALID, "lon": "east"},
    "unknown_field": {**_VALID, "include_trace": False},
    "ambiguous_policy_unknown": {**_VALID, "ambiguousTime": "latest"},
}


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("case", sorted(_INVALID_BODIES))
def test_invalid_body_is_422(client, route, case):
    r = client.post(route, json=_INVALID_BODIES[case])
    assert r.status_code == 422, (case, r.text)
    body = r.json()
    assert set(body) >= {"error", "message", "detail"}
    # No raw echo of the subject's birth data in the error body.
    assert "1987-11-23" not in r.text
    assert "48.2082" not in r.text and "16.3738" not in r.text


_NON_FINITE = ["NaN", "Infinity", "-Infinity"]


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("field", ["lat", "lon"])
@pytest.mark.parametrize("token", _NON_FINITE)
def test_non_finite_coordinates_rejected(client, route, field, token):
    raw = json.dumps(_VALID).replace(json.dumps(_VALID[field]), token, 1)
    assert token in raw
    r = client.post(route, content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422, (field, token, r.text)
    assert "1987-11-23" not in r.text


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("tz", ["Mars/Olympus_Mons", "Europe/Berlinn", "UTC+5", ""])
def test_invalid_iana_timezone_is_client_error(client, route, tz):
    r = client.post(route, json={**_VALID, "tz": tz})
    assert r.status_code == 422, r.text
    assert "1987-11-23" not in r.text
    if tz:
        assert tz not in r.text


@pytest.mark.parametrize("route", ROUTES)
def test_offset_bearing_date_rejected(client, route):
    """An explicit numeric offset competes with the IANA zone — v2 refuses it
    instead of silently overriding it (v1 replaces the offset)."""
    r = client.post(route, json={**_VALID, "date": "1987-11-23T09:41:17+05:00"})
    assert r.status_code == 422, r.text
    assert "1987-11-23" not in r.text


@pytest.mark.parametrize("route", ROUTES)
def test_malformed_date_rejected(client, route):
    r = client.post(route, json={**_VALID, "date": "23.11.1987 09:41"})
    assert r.status_code == 422, r.text
    assert "23.11.1987" not in r.text


@pytest.mark.parametrize("route", ROUTES)
def test_nonexistent_dst_time_rejected_by_default(client, route):
    r = client.post(route, json=v2_body({"date": "2024-03-31T02:30:00", "tz": "Europe/Berlin",
                                         "lat": 52.52, "lon": 13.405}))
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "dst_time_error"
    assert "2024-03-31" not in r.text and "Europe/Berlin" not in r.text


@pytest.mark.parametrize("route", ROUTES)
def test_ambiguous_dst_time_without_choice_is_rejected(client, route):
    """No silent fold choice on v2 (v1 silently defaults to 'earlier')."""
    r = client.post(route, json=v2_body({"date": "2024-10-27T02:30:00", "tz": "Europe/Berlin",
                                         "lat": 52.52, "lon": 13.405}))
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "dst_time_error"
    assert "ambiguousTime" in r.json()["message"]
    assert "2024-10-27" not in r.text and "Europe/Berlin" not in r.text


@pytest.mark.parametrize("route", ROUTES)
def test_unambiguous_time_needs_no_choice(client, route):
    body = post_ok(client, route, v2_body({"date": "2024-10-27T04:30:00", "tz": "Europe/Berlin",
                                           "lat": 52.52, "lon": 13.405}))
    assert body["time_basis"]["local_time_status"] == "ok"
    assert body["time_basis"]["fold"] == 0


class TestApiKeyRequired:
    def setup_method(self):
        import os

        from bazi_engine.auth import _load_keys
        os.environ["FUFIRE_API_KEYS"] = "inc1-test-key"
        _load_keys.cache_clear()

    def teardown_method(self):
        import os

        from bazi_engine.auth import _load_keys
        os.environ.pop("FUFIRE_API_KEYS", None)
        _load_keys.cache_clear()

    @pytest.mark.parametrize("route", ROUTES)
    def test_missing_key_is_401(self, route):
        r = TestClient(app).post(route, json=_VALID)
        assert r.status_code == 401, r.text
        assert "1987-11-23" not in r.text

    @pytest.mark.parametrize("route", ROUTES)
    def test_wrong_key_is_401(self, route):
        r = TestClient(app).post(route, json=_VALID, headers={"X-API-Key": "nope"})
        assert r.status_code == 401, r.text

    @pytest.mark.parametrize("route", ROUTES)
    def test_valid_key_is_200(self, route):
        r = TestClient(app).post(route, json=_VALID, headers={"X-API-Key": "inc1-test-key"})
        assert r.status_code == 200, r.text


# ═════════════════════════════════════════════════════════════════════════════
# AC-03 — day and hour boundaries, oracle-anchored (>= 1 min off every edge)
# ═════════════════════════════════════════════════════════════════════════════

# (id, tz, lon, lat, solar_date, solar_hours, boundary)
_ORACLE_CASES = [
    ("zi_2259", "Europe/Berlin", 13.405, 52.52, date(2024, 6, 16), 22 + 59 / 60, "zi"),
    ("zi_2301", "Europe/Berlin", 13.405, 52.52, date(2024, 6, 16), 23 + 1 / 60, "zi"),
    ("mid_2359", "Europe/Berlin", 13.405, 52.52, date(2024, 6, 16), 23 + 58.5 / 60, "midnight"),
    ("mid_0001", "Europe/Berlin", 13.405, 52.52, date(2024, 6, 17), 1.5 / 60, "midnight"),
    ("branch_0059", "Europe/Berlin", 13.405, 52.52, date(2024, 6, 17), 59 / 60, "midnight"),
    ("branch_0101", "Europe/Berlin", 13.405, 52.52, date(2024, 6, 17), 1 + 1 / 60, "midnight"),
    ("rollover_fwd_kolkata", "Asia/Kolkata", 88.3639, 22.5726, date(2024, 11, 4), 20 / 60, "midnight"),
    ("rollover_back_madrid", "Europe/Madrid", -3.7038, 40.4168, date(2024, 2, 21), 23 + 10 / 60, "midnight"),
    ("rollover_minus2_kiritimati", "Pacific/Kiritimati", -157.4, 1.87, date(2024, 2, 11), 23.5, "midnight"),
    ("halfhour_kolkata", "Asia/Kolkata", 77.209, 28.6139, date(2023, 3, 14), 10.5, "midnight"),
    ("quarter_kathmandu", "Asia/Kathmandu", 85.324, 27.7172, date(2023, 3, 14), 10.5, "midnight"),
    ("halfhour_neg_st_johns", "America/St_Johns", -52.7126, 47.5615, date(2023, 1, 20), 10.5, "midnight"),
    ("quarter_chatham", "Pacific/Chatham", -176.5, -43.95, date(2023, 1, 20), 10.5, "midnight"),
    ("south_sydney_summer", "Australia/Sydney", 151.2093, -33.8688, date(2023, 1, 20), 16.25, "zi"),
    ("leap_day_madrid", "Europe/Madrid", -3.7038, 40.4168, date(2024, 2, 29), 23 + 5 / 60, "midnight"),
    ("year_end_madrid", "Europe/Madrid", -3.7038, 40.4168, date(2024, 12, 31), 23 + 5 / 60, "midnight"),
    ("year_end_zi_madrid", "Europe/Madrid", -3.7038, 40.4168, date(2024, 12, 31), 23 + 5 / 60, "zi"),
    ("century_1999_lisbon", "Europe/Lisbon", -9.1393, 38.7223, date(1999, 12, 31), 23.75, "midnight"),
    ("west_far_nome", "America/Nome", -165.4064, 64.5011, date(1975, 11, 2), 3.25, "midnight"),
]


def _oracle_case(case):
    cid, tz, lon, lat, sdate, shours, boundary = case
    utc = utc_for_solar(sdate, shours, lon)
    local_iso, fold = civil_local_iso(utc, tz)
    return cid, tz, lon, lat, sdate, shours, boundary, utc, local_iso, fold


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("case", _ORACLE_CASES, ids=[c[0] for c in _ORACLE_CASES])
def test_oracle_anchored_boundary(client, route, case):
    cid, tz, lon, lat, sdate, shours, boundary, utc, local_iso, fold = _oracle_case(case)
    assert edge_distance_min(shours, boundary) >= CLEAR_MARGIN_MIN - 1e-9, cid
    req = v2_body({"date": local_iso, "tz": tz, "lat": lat, "lon": lon}, boundary,
                  ambiguousTime="later" if fold else "earlier")
    body = post_ok(client, route, req)
    tb = body["time_basis"]
    # same physical instant
    got_utc = datetime.fromisoformat(tb["utc"])
    assert abs((got_utc - utc).total_seconds()) < 1e-6, (cid, tb["utc"], utc)
    # TLST value and solar date agree with the oracle
    assert circ_min(tb["tlst_hours"], shours) < EOT_TOL_MIN, (cid, tb["tlst_hours"], shours)
    assert tb["tlst_date"] == sdate.isoformat(), cid
    civil_date = datetime.fromisoformat(local_iso).date()
    assert tb["tlst_date_rollover"] == (sdate - civil_date).days, cid
    # hour branch from the oracle hour, day pillar from the oracle solar date
    want_day = sdate + timedelta(days=1) if (boundary == "zi" and shours >= 23.0) else sdate
    assert tb["day_pillar_date"] == want_day.isoformat(), cid
    got = pillars_of(route, body)
    assert got[2] == expected_day_pillar(want_day), (cid, got)
    assert got[3].split("-")[1] == BRANCHES[independent_branch(shours)], (cid, got)
    assert tb["uncertainty"]["tlst_edge"]["status"] == "clear", (cid, tb["uncertainty"])


def test_two_day_rollover_case_really_spans_two_days():
    *_, local_iso, _ = _oracle_case(_ORACLE_CASES[8])
    assert datetime.fromisoformat(local_iso).date() == date(2024, 2, 13)


def test_forward_rollover_case_really_is_forward():
    *_, local_iso, _ = _oracle_case(_ORACLE_CASES[6])
    assert datetime.fromisoformat(local_iso).date() == date(2024, 11, 3)


# ── DST start / end, fold=0 / fold=1 ─────────────────────────────────────────


@pytest.mark.parametrize("route", ROUTES)
def test_dst_start_shift_forward_is_explicit(client, route):
    body = post_ok(client, route, v2_body({"date": "2024-03-31T02:30:00", "tz": "Europe/Berlin",
                                           "lat": 52.52, "lon": 13.405}, nonexistentTime="shift_forward"))
    tb = body["time_basis"]
    assert tb["local_time_status"] == "nonexistent_shifted"
    assert tb["adjusted_minutes"] == 30
    assert tb["resolved_local"] == "2024-03-31T03:00:00+02:00"
    assert tb["utc"] == "2024-03-31T01:00:00+00:00"
    assert tb["local_time_warning_code"] == "nonexistent_local_time_shifted"
    _, o_hours = oracle_solar(datetime(2024, 3, 31, 1, 0, tzinfo=timezone.utc), 13.405)
    assert circ_min(tb["tlst_hours"], o_hours) < EOT_TOL_MIN


@pytest.mark.parametrize("route", ROUTES)
def test_dst_end_fold0_and_fold1_are_one_hour_apart(client, route):
    base = {"date": "2024-10-27T02:30:00", "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405}
    early = post_ok(client, route, v2_body(base, ambiguousTime="earlier"))["time_basis"]
    late = post_ok(client, route, v2_body(base, ambiguousTime="later"))["time_basis"]
    assert early["utc"] == "2024-10-27T00:30:00+00:00" and early["fold"] == 0
    assert late["utc"] == "2024-10-27T01:30:00+00:00" and late["fold"] == 1
    assert early["local_time_status"] == late["local_time_status"] == "ambiguous"
    assert early["utc_offset_minutes"] == 120 and late["utc_offset_minutes"] == 60
    for tb, utc in ((early, datetime(2024, 10, 27, 0, 30, tzinfo=timezone.utc)),
                    (late, datetime(2024, 10, 27, 1, 30, tzinfo=timezone.utc))):
        _, o_hours = oracle_solar(utc, 13.405)
        assert circ_min(tb["tlst_hours"], o_hours) < EOT_TOL_MIN
    assert abs(circ_min(late["tlst_hours"], early["tlst_hours"]) - 60.0) < 0.01


# ── LiChun / Jieqi proximity (instant-based, independent of TLST) ────────────


def _lichun_2024_utc() -> datetime:
    jd = swe.solcross_ut(315.0, swe.julday(2024, 1, 1, 0.0))
    jd = jd[0] if isinstance(jd, tuple) else jd
    y, m, d, h = swe.revjul(jd)
    return datetime(y, m, d, tzinfo=timezone.utc) + timedelta(hours=h)


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("offset_s,year,month_branch", [(-120, "Gui-Mao", "Chou"), (120, "Jia-Chen", "Yin")])
def test_lichun_two_minutes_either_side(client, route, offset_s, year, month_branch):
    utc = _lichun_2024_utc() + timedelta(seconds=offset_s)
    local_iso, _ = civil_local_iso(utc, "Asia/Shanghai")
    body = post_ok(client, route, v2_body({"date": local_iso, "tz": "Asia/Shanghai",
                                           "lat": 31.2304, "lon": 121.4737}))
    got = pillars_of(route, body)
    assert got[0] == year
    assert got[1].split("-")[1] == month_branch
    st = body["time_basis"]["uncertainty"]["solar_term"]
    assert abs(st["distance_seconds"] - abs(offset_s)) < 2.0, st
    assert st["status"] == "clear"


@pytest.mark.parametrize("route", ROUTES)
def test_lichun_sub_second_is_flagged(client, route):
    utc = _lichun_2024_utc() + timedelta(milliseconds=300)
    local_iso, _ = civil_local_iso(utc, "Asia/Shanghai")
    body = post_ok(client, route, v2_body({"date": local_iso, "tz": "Asia/Shanghai",
                                           "lat": 31.2304, "lon": 121.4737}))
    unc = body["time_basis"]["uncertainty"]
    assert unc["solar_term"]["status"] == "within_accuracy", unc
    assert unc["status"] == "boundary_within_tolerance"


# ── microseconds at the edge: engine self-consistency + uncertainty flag ─────


def _engine_edge_instant(start: datetime, lon: float, edge_hours: float) -> datetime:
    """First UTC microsecond at which the ENGINE's tlst_hours reaches
    ``edge_hours`` (bisection over the engine function). Used only for the
    self-consistency tests below — not as an oracle."""
    from bazi_engine.time_context import compute_effective_time_context_from_instant as ctx_of
    lo, hi = start - timedelta(minutes=5), start + timedelta(minutes=5)

    def past(t: datetime) -> bool:
        h = ctx_of(t, lon).tlst_hours
        return h >= edge_hours if edge_hours > 0 else h < 12.0

    assert not past(lo) and past(hi)
    while hi - lo > timedelta(microseconds=1):
        mid = lo + (hi - lo) / 2
        if past(mid):
            hi = mid
        else:
            lo = mid
    return hi


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("edge,boundary", [(23.0, "zi"), (1.0, "midnight"), (0.0, "midnight")])
def test_microsecond_either_side_of_engine_edge(client, route, edge, boundary):
    approx = utc_for_solar(date(2024, 6, 16 if edge else 17), edge, 0.0)
    first = _engine_edge_instant(approx, 0.0, edge)
    results = []
    for t in (first - timedelta(microseconds=1), first):
        local_iso, _ = civil_local_iso(t, "UTC")
        body = post_ok(client, route, v2_body({"date": local_iso, "tz": "UTC", "lat": 51.48, "lon": 0.0}, boundary))
        tb = body["time_basis"]
        h = tb["tlst_hours"]
        got = pillars_of(route, body)
        # decision consistent with the engine's own published TLST
        assert got[3].split("-")[1] == BRANCHES[independent_branch(h)], (h, got)
        sdate = date.fromisoformat(tb["tlst_date"])
        want_day = sdate + timedelta(days=1) if (boundary == "zi" and h >= 23.0) else sdate
        assert tb["day_pillar_date"] == want_day.isoformat()
        assert got[2] == expected_day_pillar(want_day)
        # and the response says the decision sits inside the EoT tolerance
        assert tb["uncertainty"]["tlst_edge"]["status"] == "within_eot_tolerance", tb["uncertainty"]
        assert tb["uncertainty"]["status"] == "boundary_within_tolerance"
        results.append((h, got[2], got[3]))
    before, after = results
    assert before[0] < after[0] or (edge == 0.0 and before[0] > 23.9 and after[0] < 0.1)
    if edge in (23.0, 1.0):
        assert before[2] != after[2]           # hour branch flips exactly at the engine edge
    if edge == 23.0 or edge == 0.0:
        assert before[1] != after[1]           # day pillar flips (zi start / solar midnight)


def test_rounding_trap_r2_case_stays_hai(client):
    """R2 TLST-1: 22:59:59.9995 apparent must not round up into Zi."""
    body = post_ok(client, BAZI, v2_body({"date": "2024-06-16T23:00:56.243413", "tz": "UTC",
                                          "lat": 50.0, "lon": 0.0}, "zi"))
    assert body["time_basis"]["tlst_hours"] == 22.999999
    assert body["pillars"]["hour"]["zweig"] == "Hai"
    assert body["time_basis"]["day_pillar_date"] == "2024-06-16"


# ═════════════════════════════════════════════════════════════════════════════
# AC-07 — BaZi / Natal parity over one deterministic input set
# ═════════════════════════════════════════════════════════════════════════════

_PARITY_INPUTS = [
    v2_body(HANNOVER), v2_body(HANNOVER, "zi"), v2_body(MADRID), v2_body(MADRID, "zi"),
    v2_body({"date": "2024-10-27T02:30:00", "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405},
            ambiguousTime="earlier"),
    v2_body({"date": "2024-10-27T02:30:00", "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405},
            ambiguousTime="later"),
    v2_body({"date": "2024-03-31T02:30:00", "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405},
            nonexistentTime="shift_forward"),
    v2_body({"date": "2024-02-13T00:14:00", "tz": "Pacific/Kiritimati", "lat": 1.87, "lon": -157.4}),
    v2_body({"date": "2023-03-14T09:52:00.123456", "tz": "Asia/Kathmandu", "lat": 27.7, "lon": 85.324}, "zi"),
    v2_body({"date": "1999-12-31T23:59:59.999999", "tz": "Europe/Lisbon", "lat": 38.7, "lon": -9.1393}, "zi"),
    v2_body({"date": "1962-07-04T05:12:00", "tz": "America/Sao_Paulo", "lat": -23.55, "lon": -46.6333}),
    v2_body({"date": "2030-12-31T23:30:00", "tz": "Pacific/Auckland", "lat": -36.85, "lon": 174.7633}, "zi"),
    v2_body(HANNOVER, birth_time_known=False),
]


@pytest.mark.parametrize("req", _PARITY_INPUTS, ids=[f"p{i}" for i in range(len(_PARITY_INPUTS))])
def test_bazi_natal_parity(client, req):
    b = post_ok(client, BAZI, req)
    n = post_ok(client, NATAL, req)
    assert pillars_of(BAZI, b) == pillars_of(NATAL, n)
    assert b["time_basis"] == n["time_basis"]
    assert b["policy"] == n["policy"]
    assert b["input"] == n["input"]
    assert b["chinese"]["day_master"] == n["day_master"]["stem"]
    assert b["precision"] == n["precision"]
    if not req.get("birth_time_known", True):
        assert b["precision"]["provisional_fields"] == ["hour"]


@pytest.mark.parametrize("route", ROUTES)
def test_ambiguous_without_choice_rejected_on_both(client, route):
    r = client.post(route, json=v2_body({"date": "2024-10-27T02:15:00", "tz": "Europe/Berlin",
                                         "lat": 52.52, "lon": 13.405}))
    assert r.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# AC-08 — v2 is additive: v1/legacy untouched, v2 only on /v2
# ═════════════════════════════════════════════════════════════════════════════


def test_v2_routes_exist_only_under_v2(client):
    for path in ("/calculate/bazi/natal", "/v1/calculate/bazi/natal", "/calculate/bazi", "/v1/calculate/bazi"):
        r = client.post(path, json=v2_body(HANNOVER))
        # v1/legacy accept the body (standard TLST is a valid v1 value) but answer
        # in the v1 shape — no time_basis/policy blocks leak onto v1.
        assert r.status_code == 200, r.text
        assert "time_basis" not in r.json() and "policy" not in r.json()


def test_openapi_documents_both_v2_routes(client):
    spec = client.get("/openapi.json").json()
    for path in (BAZI, NATAL):
        op = spec["paths"][path]["post"]
        assert op.get("security"), path
        assert "422" in op["responses"]
        assert "opt-in" in op["description"].lower()
        assert "unverified" in op["description"].lower()

