"""FU-TLST-POLICY / INC-1, decision A — v1/legacy surfaces keep the CIVIL default.

PR #77 (87422a4) switched the *implicit* time standard of the existing BaZi
surfaces from CIVIL to TLST. The product owner chose variant A: existing
callers keep their clock-time default; TLST stays available on request (and,
later, as the opt-in /v2 product path). These tests pin that contract at the
real HTTP boundary (WS-A convention) for every surface PR #77 changed, directly
or through the shared ``BaziRequest`` model:

* ``/calculate/bazi``, ``/calculate/bazi/trace``, ``/calculate/bazi/wuxing``
  (legacy + ``/v1``) and ``/v1/match/bazi-hehun`` (``MatchPersonInput``
  inherits ``BaziRequest``);
* ``/calculate/bazi/natal``, ``/calculate/bazi/dayun``;
* ``/calculate/fusion`` and ``/calculate/fusion/vector-map`` (BaZi side,
  auto-computed pillars).

PR #79 (787f1b5) did the same for four more public entry points, which decision
A covers too:

* ``/chart`` (legacy only; ``time_standard`` request default);
* ``/personalize``, ``/impact/active`` and ``/experience/{bootstrap,daily}``
  (legacy + ``/v1``; fixed engine input, no request field).

Not covered by decision A and therefore not pinned here: the CLI default and
the schema-hidden ``/internal`` ElevenLabs webhooks (TLST since #79).

Expected values are NOT derived from the implementation under test:

* the four-pillar pins (Hannover TLST reference, Madrid solar-date rollover,
  Beijing LiChun night) × every standard × both day boundaries are taken from
  PR #76 (``tests/test_v1_time_standard_contract.py`` at 464e81a), where they
  were captured on base 3b574f2 BEFORE PR #77;
* the dayun, fusion, vector-map and match pins were captured on the same base
  3b574f2 (pre-PR #77) with the SHA-verified SWIEPH ephemeris;
* the chart, personalize, impact and experience pins were captured on 3b574f2
  as well (SWIEPH, space weather stubbed to its offline default).

Explicit ``CIVIL`` / ``LMT`` / ``TLST`` must keep their own semantics; the
Hannover case is the counter-example whose hour pillar differs between CIVIL
(15:44 → Shen) and the solar standards (Wei).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

_CASES = {
    "hannover": {"date": "1990-07-15T15:44:00", "tz": "Europe/Berlin", "lon": 9.732, "lat": 52.3759},
    "madrid": {"date": "2024-02-22T00:30:00", "tz": "Europe/Madrid", "lon": -3.7038, "lat": 40.4168},
    "beijing": {"date": "1984-02-04T23:30:00", "tz": "Asia/Shanghai", "lon": 116.4074, "lat": 39.9042},
}

# (case, standard or None = omitted, boundary) -> "year month day hour" as stem-branch.
# Source: PR #76, captured on 3b574f2 (pre-PR #77).
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
_PIN_KEYS = sorted(_PINS, key=lambda k: (k[0], str(k[1]), k[2]))

# Captured on 3b574f2 (pre-PR #77), SWIEPH: BaZi-side Wu-Xing of the Hannover
# CIVIL chart (Geng-Wu Gui-Wei Xin-Si Bing-Shen). The western side is NOT pinned:
# PR #77 deliberately changed the western mapping (sign-element-consensus-v1).
_HANNOVER_CIVIL_BAZI_RAW = {"Erde": 2.1, "Feuer": 3.5, "Holz": 0.3, "Metall": 3.5, "Wasser": 1.5}
_HANNOVER_CIVIL_BAZI_L2 = {
    "Erde": 0.3756594202199647,
    "Feuer": 0.6260990336999411,
    "Holz": 0.05366563145999495,
    "Metall": 0.6260990336999411,
    "Wasser": 0.2683281572999747,
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

_PREFIXES = ["", "/v1"]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _bazi_pillars(body: dict) -> str:
    """``/calculate/bazi`` speaks stamm/zweig, ``/calculate/bazi/wuxing`` stem/branch."""
    p = body["pillars"]
    return " ".join(
        f"{p[k].get('stamm', p[k].get('stem'))}-{p[k].get('zweig', p[k].get('branch'))}"
        for k in ("year", "month", "day", "hour")
    )


def _natal_pillars(body: dict) -> str:
    p = body["pillars"]
    return " ".join(f"{p[k]['stem']}-{p[k]['branch']}" for k in ("year", "month", "day", "hour"))


def _payload(case: str, standard: str | None, boundary: str | None = None) -> dict:
    body = dict(_CASES[case])
    if boundary is not None:
        body["boundary"] = boundary
    if standard is not None:
        body["standard"] = standard
    return body


def _post_ok(client: TestClient, path: str, body: dict) -> dict:
    r = client.post(path, json=body)
    assert r.status_code == 200, (path, r.status_code, r.text[:500])
    return r.json()


# ── Four-pillar regression pins (PR #76, pre-PR #77 base) ─────────────────────


@pytest.mark.swieph
@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("key", _PIN_KEYS)
def test_bazi_pillars_match_pre_pr77_pins(client, prefix, key):
    case, standard, boundary = key
    body = _post_ok(client, f"{prefix}/calculate/bazi", _payload(case, standard, boundary))
    assert _bazi_pillars(body) == _PINS[key]


@pytest.mark.swieph
@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("key", _PIN_KEYS)
def test_natal_pillars_match_pre_pr77_pins(client, prefix, key):
    case, standard, boundary = key
    body = _post_ok(client, f"{prefix}/calculate/bazi/natal", _payload(case, standard, boundary))
    assert _natal_pillars(body) == _PINS[key]


@pytest.mark.swieph
@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("path", ["/calculate/bazi/trace", "/calculate/bazi/wuxing"])
@pytest.mark.parametrize("case", sorted(_CASES))
def test_bazi_sibling_routes_use_civil_pillars_by_default(client, prefix, path, case):
    """``BaziRequest`` is shared: trace and the BaZi Wu-Xing route default to CIVIL too."""
    default = _post_ok(client, f"{prefix}{path}", _payload(case, None))
    civil = _post_ok(client, f"{prefix}{path}", _payload(case, "CIVIL"))
    tlst = _post_ok(client, f"{prefix}{path}", _payload(case, "TLST"))
    assert _bazi_pillars(default) == _PINS[(case, None, "midnight")]
    assert _scrub(default) == _scrub(civil)
    assert _bazi_pillars(tlst) == _PINS[(case, "TLST", "midnight")]


@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("path", ["/calculate/bazi/trace", "/calculate/bazi/wuxing"])
def test_bazi_sibling_routes_default_hour_and_day_any_backend(client, prefix, path):
    """Backend-independent guard (runs on MOSEPH too): hour and day pillar only.

    Hannover's hour pillar (Shen vs Wei) and Madrid's day pillar (Bing-Chen vs
    Yi-Mao) do not sit near a solar-term boundary, so they hold on both backends.
    """
    def branch(body, pillar):
        p = body["pillars"][pillar]
        return f"{p.get('stamm', p.get('stem'))}-{p.get('zweig', p.get('branch'))}"

    hannover = _post_ok(client, f"{prefix}{path}", _payload("hannover", None))
    madrid = _post_ok(client, f"{prefix}{path}", _payload("madrid", None))
    assert branch(hannover, "hour") == "Bing-Shen"
    assert branch(madrid, "day") == "Bing-Chen"
    tlst = _post_ok(client, f"{prefix}{path}", _payload("hannover", "TLST"))
    assert branch(tlst, "hour") == "Yi-Wei"


_VOLATILE_KEYS = {"computation_timestamp", "computed_at", "request_id"}


def _scrub(obj):
    """Drop per-call volatile values so two responses can be compared whole."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items() if k not in _VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


# ── Default semantics: omitted standard is CIVIL ──────────────────────────────


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_bazi_default_standard_is_civil(client, prefix):
    body = _post_ok(client, f"{prefix}/calculate/bazi", _CASES["hannover"])
    assert body["input"]["standard"] == "CIVIL"
    assert body["input"]["boundary"] == "midnight"
    assert body["derivation_trace"]["time_resolution"]["effective_standard"] == "CIVIL"
    assert body["derivation_trace"]["hour"]["time_standard_requested"] == "CIVIL"
    assert body["derivation_trace"]["hour"]["time_standard_used"] == "CIVIL"
    assert body["derivation_trace"]["hour"]["true_solar_time_used"] is False
    assert body["derivation_trace"]["hour"]["lmt_used"] is False
    # Civil 15:44 is Shen; the solar answers (LMT/TLST) are Wei.
    assert body["pillars"]["hour"]["zweig"] == "Shen"


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_natal_default_equals_bazi_civil(client, prefix):
    for case in ("hannover", "madrid"):
        natal = _post_ok(client, f"{prefix}/calculate/bazi/natal", _CASES[case])
        civil = _post_ok(client, f"{prefix}/calculate/bazi", {**_CASES[case], "standard": "CIVIL"})
        assert _natal_pillars(natal) == _bazi_pillars(civil)


@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("standard", ["CIVIL", "LMT", "TLST"])
def test_explicit_standard_is_echoed_and_used(client, prefix, standard):
    body = _post_ok(client, f"{prefix}/calculate/bazi", {**_CASES["hannover"], "standard": standard})
    assert body["input"]["standard"] == standard
    hour = body["derivation_trace"]["hour"]
    assert hour["time_standard_requested"] == standard
    assert hour["time_standard_used"] == standard
    assert hour["true_solar_time_used"] is (standard == "TLST")
    assert hour["lmt_used"] is (standard == "LMT")
    assert body["derivation_trace"]["time_resolution"]["effective_standard"] == standard


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_civil_lmt_tlst_stay_three_distinct_conventions(client, prefix):
    """Same birth, three standards: CIVIL ≠ solar hour; LMT and TLST are not one thing.

    Hannover: CIVIL keeps the Shen hour, both solar standards land in Wei but
    with different solar clocks (LMT = mean, TLST = mean + equation of time).
    """
    res = {
        s: _post_ok(client, f"{prefix}/calculate/bazi", {**_CASES["hannover"], "standard": s})
        for s in ("CIVIL", "LMT", "TLST")
    }
    assert res["CIVIL"]["pillars"]["hour"]["zweig"] == "Shen"
    assert res["LMT"]["pillars"]["hour"]["zweig"] == "Wei"
    assert res["TLST"]["pillars"]["hour"]["zweig"] == "Wei"
    tr = {s: res[s]["derivation_trace"]["time_resolution"] for s in res}
    # The three time representations are reported whatever the requested standard …
    assert tr["CIVIL"]["lmt"] == tr["LMT"]["lmt"] == tr["TLST"]["lmt"]
    assert tr["CIVIL"]["tlst_hours"] == tr["LMT"]["tlst_hours"] == tr["TLST"]["tlst_hours"]
    # … and the TLST clock is the LMT clock plus the equation of time (not LMT itself).
    lmt_clock = tr["LMT"]["lmt"][11:19]
    lmt_hours = int(lmt_clock[:2]) + int(lmt_clock[3:5]) / 60 + float(lmt_clock[6:8]) / 3600
    eot = tr["TLST"]["eot_minutes"]
    assert abs(eot) > 1.0
    assert (tr["TLST"]["tlst_hours"] - lmt_hours) * 60 == pytest.approx(eot, abs=0.05)
    hour = {s: res[s]["derivation_trace"]["hour"] for s in res}
    assert hour["CIVIL"]["local_hour"] == 15
    assert hour["LMT"]["local_hour"] == hour["TLST"]["local_hour"] == 14
    assert (hour["LMT"]["lmt_used"], hour["LMT"]["true_solar_time_used"]) == (True, False)
    assert (hour["TLST"]["lmt_used"], hour["TLST"]["true_solar_time_used"]) == (False, True)


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_dayun_default_standard_is_civil(client, prefix):
    """Madrid 00:30: the TLST date rolls back a day, so the day master would flip."""
    base = {**_CASES["madrid"], "as_of_date": "2026-05-22", "direction_method": "explicit",
            "flow_direction": "forward", "cycles": 8}
    default = _post_ok(client, f"{prefix}/calculate/bazi/dayun", base)
    civil = _post_ok(client, f"{prefix}/calculate/bazi/dayun", {**base, "standard": "CIVIL"})
    tlst = _post_ok(client, f"{prefix}/calculate/bazi/dayun", {**base, "standard": "TLST"})
    # Pre-PR #77 pin (3b574f2): day master of the CIVIL chart Jia-Chen Bing-Yin Bing-Chen Wu-Zi.
    assert default["dayun"]["cycles"][0]["relation_to_day_master"]["day_master"] == "Bing"
    assert default["dayun"] == civil["dayun"]
    assert tlst["dayun"]["cycles"][0]["relation_to_day_master"]["day_master"] == "Yi"


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_fusion_default_uses_civil_bazi_pillars(client, prefix):
    default = _post_ok(client, f"{prefix}/calculate/fusion", _CASES["hannover"])
    civil = _post_ok(client, f"{prefix}/calculate/fusion", {**_CASES["hannover"], "standard": "CIVIL"})
    tlst = _post_ok(client, f"{prefix}/calculate/fusion", {**_CASES["hannover"], "standard": "TLST"})
    bazi = default["wu_xing_vectors"]["bazi_pillars"]
    for phase, value in _HANNOVER_CIVIL_BAZI_L2.items():
        assert bazi[phase] == pytest.approx(value, abs=1e-12), (phase, bazi)
    assert bazi == civil["wu_xing_vectors"]["bazi_pillars"]
    # Explicit TLST stays available and really changes the hour pillar.
    assert tlst["wu_xing_vectors"]["bazi_pillars"] != bazi
    # The western side does not depend on the time standard (real UTC moment).
    assert default["wu_xing_vectors"]["western_planets"] == tlst["wu_xing_vectors"]["western_planets"]


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_fusion_default_equals_explicit_pre_pr77_civil_pillars(client, prefix):
    """Oracle independent of the auto-compute path: feed the pinned CIVIL pillars."""
    pillars = {
        "year": {"stem": "Geng", "branch": "Wu"},
        "month": {"stem": "Gui", "branch": "Wei"},
        "day": {"stem": "Xin", "branch": "Si"},
        "hour": {"stem": "Bing", "branch": "Shen"},
    }
    default = _post_ok(client, f"{prefix}/calculate/fusion", _CASES["hannover"])
    explicit = _post_ok(client, f"{prefix}/calculate/fusion", {**_CASES["hannover"], "bazi_pillars": pillars})
    assert default["wu_xing_vectors"]["bazi_pillars"] == explicit["wu_xing_vectors"]["bazi_pillars"]


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_vector_map_default_uses_civil_bazi_pillars(client, prefix):
    path = f"{prefix}/calculate/fusion/vector-map"
    default = _post_ok(client, path, _CASES["hannover"])
    civil = _post_ok(client, path, {**_CASES["hannover"], "standard": "CIVIL"})
    tlst = _post_ok(client, path, {**_CASES["hannover"], "standard": "TLST"})
    raw = default["vector_map"]["bazi_pillars"]["raw"]
    for phase, value in _HANNOVER_CIVIL_BAZI_RAW.items():
        assert raw[phase] == pytest.approx(value, abs=1e-9), (phase, raw)
    assert default["vector_map"]["bazi_pillars"] == civil["vector_map"]["bazi_pillars"]
    assert tlst["vector_map"]["bazi_pillars"] != default["vector_map"]["bazi_pillars"]


def test_match_person_default_standard_is_civil(client):
    """``MatchPersonInput`` inherits ``BaziRequest``: its default follows the v1 contract."""
    def req(std):
        def person(case):
            return _payload(case, std)
        return {"mode": "birth_input", "person_a": person("hannover"), "person_b": person("madrid"),
                "options": {"second_person_consent_confirmed": True}}

    default = _post_ok(client, "/v1/match/bazi-hehun", req(None))
    civil = _post_ok(client, "/v1/match/bazi-hehun", req("CIVIL"))
    tlst = _post_ok(client, "/v1/match/bazi-hehun", req("TLST"))
    pa = default["individual"]["person_a"]["four_pillars"]
    pb = default["individual"]["person_b"]["four_pillars"]
    # Pre-PR #77 pins: Hannover hour Bing-Shen, Madrid day Bing-Chen (CIVIL).
    assert (pa["hour"]["stamm"], pa["hour"]["zweig"]) == ("Bing", "Shen")
    assert (pb["day"]["stamm"], pb["day"]["zweig"]) == ("Bing", "Chen")
    assert default["individual"] == civil["individual"]
    assert tlst["individual"]["person_a"]["four_pillars"]["hour"]["zweig"] == "Wei"


# ── Request-default contract in OpenAPI and the frozen v1 shape ───────────────


@pytest.mark.parametrize(
    "schema_name",
    ["BaziRequest", "NatalRequest", "DayunRequest", "FusionRequest", "VectorMapRequest", "MatchPersonInput"],
)
def test_openapi_request_default_is_civil(schema_name):
    schemas = app.openapi()["components"]["schemas"]
    prop = schemas[schema_name]["properties"]["standard"]
    assert prop.get("default") == "CIVIL", (schema_name, prop)
    assert "Default TLST" not in prop.get("description", ""), (schema_name, prop)


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_missing_location_still_defaults_to_berlin(client, prefix):
    """The frozen v1 contract keeps its Berlin location defaults."""
    body = _post_ok(client, f"{prefix}/calculate/bazi", {"date": "1990-07-15T15:44:00"})
    assert body["input"]["lon"] == 13.405
    assert body["input"]["lat"] == 52.52
    assert body["input"]["tz"] == "Europe/Berlin"


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_response_key_sets_unchanged(client, prefix):
    body = _post_ok(client, f"{prefix}/calculate/bazi", _CASES["hannover"])
    assert set(body) == _BAZI_TOP_KEYS
    assert set(body["input"]) == _BAZI_INPUT_KEYS
    assert set(body["derivation_trace"]) == _TRACE_KEYS
    assert set(body["derivation_trace"]["time_resolution"]) == _TIME_RESOLUTION_KEYS
    natal = _post_ok(client, f"{prefix}/calculate/bazi/natal", _CASES["hannover"])
    assert set(natal) == _NATAL_TOP_KEYS


# ── PR #79 entry points: /chart, /personalize, /impact/active, /experience/* ──
#
# Pins captured on 3b574f2 (pre-PR #77), SWIEPH, space weather stubbed to its
# offline default. Hannover: CIVIL hour Shen (branch index 8), solar hour Wei.
# Madrid 00:30: CIVIL day master Bing; under TLST the date rolls back (Yi).

_CHART_CASES = {
    case: {"local_datetime": c["date"], "tz_id": c["tz"], "geo_lon_deg": c["lon"], "geo_lat_deg": c["lat"]}
    for case, c in _CASES.items()
}


def _split_birth(case: str, *, seconds: bool) -> dict:
    c = _CASES[case]
    day, clock = c["date"].split("T")
    return {"date": day, "time": clock if seconds else clock[:5], "tz": c["tz"], "lat": c["lat"], "lon": c["lon"]}


def _chart_pillars(body: dict) -> str:
    p = body["bazi"]["pillars"]
    return " ".join(f"{p[k]['stem']}-{p[k]['branch']}" for k in ("year", "month", "day", "hour"))


@pytest.fixture
def offline_space_weather(monkeypatch):
    """No NOAA call: both routers get the documented offline default."""
    from bazi_engine.routers import experience, impact
    from bazi_engine.services.space_weather import _default_space_weather

    async def _offline():
        return _default_space_weather(), True

    monkeypatch.setattr(impact, "fetch_space_weather", _offline)
    monkeypatch.setattr(experience, "fetch_space_weather", _offline)


@pytest.mark.swieph
@pytest.mark.parametrize("standard", [None, "CIVIL", "LMT", "TLST"])
@pytest.mark.parametrize("case", sorted(_CASES))
def test_chart_pillars_match_pre_pr77_pins(client, case, standard):
    """``/chart`` is legacy-only; its default day boundary is midnight."""
    body = dict(_CHART_CASES[case])
    if standard is not None:
        body["time_standard"] = standard
    res = _post_ok(client, "/chart", body)
    assert _chart_pillars(res) == _PINS[(case, standard, "midnight")]


@pytest.mark.parametrize("case", ["hannover", "madrid"])
def test_chart_default_time_standard_is_civil(client, case):
    default = _post_ok(client, "/chart", _CHART_CASES[case])
    civil = _post_ok(client, "/chart", {**_CHART_CASES[case], "time_standard": "CIVIL"})
    tlst = _post_ok(client, "/chart", {**_CHART_CASES[case], "time_standard": "TLST"})
    assert (default["bazi"]["time_standard_requested"], default["bazi"]["time_standard_used"]) == ("CIVIL", "CIVIL")
    assert _scrub(default) == _scrub(civil)
    assert (tlst["bazi"]["time_standard_requested"], tlst["bazi"]["time_standard_used"]) == ("TLST", "TLST")
    assert _chart_pillars(tlst) != _chart_pillars(default)


def test_chart_openapi_default_is_civil():
    prop = app.openapi()["components"]["schemas"]["ChartComputeRequest"]["properties"]["time_standard"]
    assert prop.get("default") == "CIVIL", prop


@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize(
    ("case", "hour_branch_index", "day_master"), [("hannover", 8, "Xin"), ("madrid", 0, "Bing")]
)
def test_personalize_uses_civil_pillars(client, prefix, case, hour_branch_index, day_master):
    c = _CASES[case]
    body = _post_ok(client, f"{prefix}/personalize", {
        "birth_datetime": c["date"], "lat": c["lat"], "lon": c["lon"], "tz": c["tz"],
        "birth_time_known": True, "locale": "en",
    })
    trace = body["domain_extras"]["bazi_trace"]
    assert trace["hour"]["time_standard_requested"] == "CIVIL"
    assert trace["hour"]["time_standard_used"] == "CIVIL"
    assert trace["hour"]["true_solar_time_used"] is False
    assert trace["hour"]["branch_index"] == hour_branch_index
    assert trace["day"]["day_master_stem"] == day_master


# Resonance type per active planet for Madrid, target 2026-05-22 (pre-PR #77 pin).
_IMPACT_MADRID_RESONANCE = [
    "kontrolle", "gleichklang", "gleichklang", "naehrung", "gleichklang",
    "kontrolle", "naehrung", "kontrolle", "naehrung", "naehrung",
]


@pytest.mark.swieph
@pytest.mark.parametrize("prefix", _PREFIXES)
def test_impact_active_uses_civil_day_master(client, prefix, offline_space_weather):
    """Madrid's day master flips under TLST, so every resonance relation would move."""
    body = _post_ok(client, f"{prefix}/impact/active",
                    {"birth": _split_birth("madrid", seconds=False), "target_date": "2026-05-22"})
    assert [a["bazi_resonance"]["type"] for a in body["active_planets"]] == _IMPACT_MADRID_RESONANCE


@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize(("case", "day_master"), [("hannover", "Xin"), ("madrid", "Bing")])
def test_experience_bootstrap_uses_civil_day_master(client, prefix, case, day_master):
    body = _post_ok(client, f"{prefix}/experience/bootstrap", {"birth": _split_birth(case, seconds=True)})
    assert body["profile"]["day_master"] == day_master


@pytest.mark.parametrize("prefix", _PREFIXES)
def test_experience_daily_uses_civil_day_master(client, prefix, offline_space_weather):
    sectors = [1 / 12] * 12
    body = _post_ok(client, f"{prefix}/experience/daily", {
        "birth": _split_birth("madrid", seconds=True), "soulprint_sectors": sectors,
        "quiz_sectors": sectors, "target_date": "2026-05-22", "locale": "en",
    })
    evidence = body["eastern"]["evidence"]
    assert evidence["day_master"] == "Bing"
    assert evidence["relation_to_day_master"] == "companion"
