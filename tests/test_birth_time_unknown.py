"""Birth input without a clock time, and birth_time_known=false (FU-BIRTH-TIME-UNKNOWN).

Rules under test (docs/precision/date-only-birth-input.md):

1. A ``date`` without a time part is computed at 12:00 civil local time on the
   birth endpoints (bazi, bazi/trace, bazi/natal, bazi/wuxing, western, fusion,
   fusion/vector-map, bazi/dayun), reported as birth_time_known=false with the
   BIRTH_TIME_UNKNOWN warning and reference_time_policy=date_only_noon.
2. A ``date`` with a time part and birth_time_known=false is computed at exactly
   that time; only precision and warnings differ from birth_time_known=true.
3. precision.provisional_fields names what can change within the civil day.
4. Endpoints where a bare date means a whole day keep reading it as 00:00.

All assertions are made at the HTTP boundary (TestClient, resp.json()).
"""
from __future__ import annotations

import copy
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.birth_time import date_only_day, resolve_birth_time_input

MUNICH = {"tz": "Europe/Berlin", "lat": 48.1374, "lon": 11.5755}
BERLIN = {"tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405}
CASE = dict(MUNICH, date="1985-08-02", standard="TLST", boundary="midnight", birth_time_known=False)
FUSION_CASE = {k: CASE[k] for k in ("date", "tz", "lat", "lon", "birth_time_known")}
DAYUN = dict(MUNICH, date="1985-08-02", direction_method="explicit", flow_direction="forward", as_of_date="2026-11-18")

VOLATILE = {"computation_timestamp", "computed_at", "request_id"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _post(client: TestClient, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    resp = client.post(path, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _strip(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _strip(v) for k, v in x.items() if k not in VOLATILE}
    if isinstance(x, list):
        return [_strip(v) for v in x]
    return x


# ── Parsing ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text", ["1985-08-02", " 1985-08-02 "])
def test_date_only_detected(text: str) -> None:
    assert date_only_day(text) is not None
    bt = resolve_birth_time_input(text, True, "shift_forward")
    assert bt.local_iso == "1985-08-02T12:00:00"
    assert bt.birth_time_known is False
    assert bt.nonexistent == "error"  # a skipped noon is a 422, never shifted
    assert bt.reference_time_policy == "date_only_noon"


@pytest.mark.parametrize("text", ["1985-08-02T00:00", "1985-08-02T00:00:00", "1985-08-02T14:30:00"])
def test_explicit_time_is_kept(text: str) -> None:
    assert date_only_day(text) is None
    bt = resolve_birth_time_input(text, False, "error")
    assert bt.local_iso == text
    assert bt.birth_time_known is False
    assert bt.reference_time_policy is None


# ── Abnahme 1: 02.08.1985 Munich, date only ──────────────────────────────────


@pytest.mark.parametrize("flag", [False, True])
def test_munich_date_only_day_pillar_bazi(client: TestClient, flag: bool) -> None:
    body = _post(client, "/v1/calculate/bazi", dict(CASE, birth_time_known=flag))
    assert (body["pillars"]["day"]["stamm"], body["pillars"]["day"]["zweig"]) == ("Gui", "You")  # 癸酉
    assert body["chinese"]["day_master"] == "Gui"
    assert body["dates"]["birth_local"] == "1985-08-02T12:00:00+02:00"
    tr = body["derivation_trace"]["time_resolution"]
    assert tr["tlst_date_rollover"] == 0
    assert tr["reference_time_policy"] == "date_only_noon"
    assert body["precision"]["birth_time_known"] is False  # also when the request said true
    assert body["precision"]["reference_time_policy"] == "date_only_noon"
    assert body["warnings"] == ["BIRTH_TIME_UNKNOWN"]
    assert body["input"]["date"] == "1985-08-02"  # the echo is the request


def test_munich_date_only_other_endpoints(client: TestClient) -> None:
    natal = _post(client, "/v1/calculate/bazi/natal", CASE)
    assert natal["pillars"]["day"]["stem_cn"] + natal["pillars"]["day"]["branch_cn"] == "癸酉"
    assert natal["day_master"]["stem"] == "Gui"
    assert natal["precision"]["reference_time_policy"] == "date_only_noon"
    assert "BIRTH_TIME_UNKNOWN" in natal["warnings"]

    wx = _post(client, "/v1/calculate/bazi/wuxing", CASE)
    assert wx["pillars"]["day"] == {"stem": "Gui", "branch": "You"}
    assert wx["precision"]["reference_time_policy"] == "date_only_noon"
    assert wx["warnings"] == ["BIRTH_TIME_UNKNOWN"]

    trace = _post(client, "/v1/calculate/bazi/trace", CASE)
    assert trace["derivation_trace"]["time_resolution"]["reference_time_policy"] == "date_only_noon"

    west = _post(client, "/v1/calculate/western", {k: CASE[k] for k in ("date", "tz", "lat", "lon")})
    assert west["precision"]["birth_time_known"] is False
    assert west["precision"]["reference_time_policy"] == "date_only_noon"
    assert west["warnings"] == ["BIRTH_TIME_UNKNOWN"]

    dayun = _post(client, "/v1/calculate/bazi/dayun", DAYUN)
    assert dayun["precision"]["birth_time_known"] is False
    assert dayun["precision"]["reference_time_policy"] == "date_only_noon"
    assert "start" in dayun["precision"]["provisional_fields"]
    assert "BIRTH_TIME_UNKNOWN" in dayun["warnings"]


def test_fusion_and_bazi_agree_without_standard(client: TestClient) -> None:
    """/fusion computes the same pillars as /bazi when neither request names a standard.

    00:30 civil in Munich (summer) is the previous day in true solar time, so the
    CIVIL and TLST pillars differ: a default mismatch would show here.
    """
    req = dict(MUNICH, date="1985-08-02T00:30:00")
    bazi = _post(client, "/v1/calculate/bazi", req)
    fusion = _post(client, "/v1/calculate/fusion", req)
    pillars: Dict[str, list] = {}
    for e in fusion["contribution_ledger"]["bazi"]:
        if e["source"] == "stem":
            pillars.setdefault(e["pillar"], [None, None])[0] = e["stem_name"]
        elif e["source"] == "hidden_main":
            pillars.setdefault(e["pillar"], [None, None])[1] = e["branch_name"]
    assert {k: tuple(v) for k, v in pillars.items()} == {
        k: (v["stamm"], v["zweig"]) for k, v in bazi["pillars"].items()
    }
    civil = _post(client, "/v1/calculate/bazi", dict(req, standard="CIVIL"))
    assert civil["pillars"]["day"] != bazi["pillars"]["day"]  # the case discriminates


# ── Abnahme 3: same time, birth_time_known true vs false ─────────────────────

SAMPLE = dict(MUNICH, date="1985-08-02T14:15:00")


def _without_precision(body: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(_strip(body))
    out.pop("precision", None)
    out.pop("warnings", None)
    out.get("input", {}).pop("birth_time_known", None)
    return out


@pytest.mark.parametrize("path, extra", [
    ("/v1/calculate/bazi", {}),
    ("/v1/calculate/bazi/trace", {}),
    ("/v1/calculate/bazi/wuxing", {}),
    ("/v1/calculate/western", {}),
    ("/v1/calculate/fusion", {"exclude_time_dependent": False}),
    ("/v1/calculate/fusion", {"exclude_time_dependent": True}),
    ("/v1/calculate/fusion/vector-map", {"exclude_time_dependent": False}),
    ("/v1/calculate/fusion/vector-map", {"exclude_time_dependent": True}),
])
def test_known_and_unknown_time_compute_the_same_values(client: TestClient, path: str, extra: dict) -> None:
    known = _post(client, path, dict(SAMPLE, birth_time_known=True, **extra))
    unknown = _post(client, path, dict(SAMPLE, birth_time_known=False, **extra))
    assert _without_precision(known) == _without_precision(unknown)
    assert unknown["precision"]["birth_time_known"] is False
    assert "reference_time_policy" not in unknown["precision"]
    assert unknown["warnings"] == ["BIRTH_TIME_UNKNOWN"]
    assert "warnings" not in known


def test_known_and_unknown_time_natal_and_dayun(client: TestClient) -> None:
    for path, base in (("/v1/calculate/bazi/natal", SAMPLE), ("/v1/calculate/bazi/dayun", dict(DAYUN, date=SAMPLE["date"]))):
        known = _post(client, path, dict(base, birth_time_known=True))
        unknown = _post(client, path, dict(base, birth_time_known=False))
        k, u = _without_precision(known), _without_precision(unknown)
        assert k == u, path
        assert unknown["precision"]["birth_time_known"] is False
        assert "BIRTH_TIME_UNKNOWN" in unknown["warnings"]
        assert "BIRTH_TIME_UNKNOWN" not in known["warnings"]


def test_dayun_known_time_precision_unchanged(client: TestClient) -> None:
    body = _post(client, "/v1/calculate/bazi/dayun", dict(DAYUN, date="1987-07-04T21:30:00"))
    assert body["precision"] == {"birth_time_known": True, "direction_basis": "explicit", "provisional_fields": []}


# ── Abnahme 6: provisional_fields ────────────────────────────────────────────


def _bazi_prov(client: TestClient, place: dict, date: str, standard: str) -> list:
    return _post(client, "/v1/calculate/bazi", dict(place, date=date, standard=standard, include_trace=False))["precision"]["provisional_fields"]


def _west_prov(client: TestClient, place: dict, date: str) -> list:
    return _post(client, "/v1/calculate/western", dict(place, date=date))["precision"]["provisional_fields"]


@pytest.mark.swieph
def test_provisional_moon_changes_sign(client: TestClient) -> None:
    # Moon enters a new sign on 1990-06-02 (Berlin civil day).
    assert _west_prov(client, BERLIN, "1990-06-02") == ["ascendant", "houses", "mc", "Moon"]


@pytest.mark.swieph
def test_provisional_jie_day_month(client: TestClient) -> None:
    # Mang Zhong (芒种, 75°) on 1990-06-06: the month pillar changes that day.
    assert _bazi_prov(client, BERLIN, "1990-06-06", "CIVIL") == ["hour", "month"]


@pytest.mark.swieph
def test_provisional_lichun_day_year_and_month(client: TestClient) -> None:
    # Li Chun on 2024-02-04 (09:27 Berlin): year and month pillar change that day.
    assert _bazi_prov(client, BERLIN, "2024-02-04", "CIVIL") == ["hour", "year", "month"]


@pytest.mark.swieph
def test_provisional_true_solar_day_boundary(client: TestClient) -> None:
    # Under TLST the true-solar midnight of Berlin falls inside the civil day.
    assert _bazi_prov(client, BERLIN, "1990-06-01", "TLST") == ["hour", "day"]
    natal = _post(client, "/v1/calculate/bazi/natal", dict(BERLIN, date="1990-06-01"))
    assert natal["precision"]["provisional_fields"] == ["hour", "day"]


@pytest.mark.swieph
def test_provisional_control_day(client: TestClient) -> None:
    """1990-06-01, Berlin, CIVIL: no pillar boundary and no sign change that day."""
    assert _bazi_prov(client, BERLIN, "1990-06-01", "CIVIL") == ["hour"]
    assert _west_prov(client, BERLIN, "1990-06-01") == ["ascendant", "houses", "mc"]
    fusion = _post(client, "/v1/calculate/fusion", dict(BERLIN, date="1990-06-01", standard="CIVIL"))
    assert fusion["precision"]["provisional_fields"] == ["signature", "hour", "ascendant", "houses"]


def test_known_time_has_no_provisional_fields(client: TestClient) -> None:
    for path in ("/v1/calculate/bazi", "/v1/calculate/western", "/v1/calculate/fusion"):
        body = _post(client, path, dict(BERLIN, date="1990-06-06T14:30:00"))
        assert body["precision"] == {"birth_time_known": True, "provisional_fields": []}
        assert "warnings" not in body


# ── Abnahme 9: a local day that does not exist ──────────────────────────────

APIA_SKIPPED = {"date": "2011-12-30", "tz": "Pacific/Apia", "lat": -13.83, "lon": -171.77}


@pytest.mark.parametrize("path, extra", [
    ("/v1/calculate/bazi", {}),
    ("/v1/calculate/bazi/trace", {}),
    ("/v1/calculate/bazi/wuxing", {}),
    ("/v1/calculate/bazi/natal", {}),
    ("/v1/calculate/western", {}),
    ("/v1/calculate/fusion", {}),
    ("/v1/calculate/fusion/vector-map", {}),
    ("/v1/calculate/bazi/dayun", {"direction_method": "explicit", "flow_direction": "forward"}),
])
@pytest.mark.parametrize("gap", ["error", "shift_forward"])
def test_skipped_local_day_is_422(client: TestClient, path: str, extra: dict, gap: str) -> None:
    body = dict(APIA_SKIPPED, **extra)
    if path != "/v1/calculate/bazi/dayun":
        body["nonexistentTime"] = gap
    resp = client.post(path, json=body)
    assert resp.status_code == 422, resp.text
    payload = resp.json()
    assert set(payload) >= {"error", "message", "detail"}
    assert "2011-12-30" not in resp.text  # birth data is not echoed


# ── Abnahme 5: endpoints where a bare date means a whole day ────────────────


def test_untouched_endpoints_keep_midnight(client: TestClient) -> None:
    tst = _post(client, "/v1/calculate/tst", {"date": "1985-08-02", "tz": "Europe/Berlin", "lon": 11.5755})
    assert tst["civil_time_hours"] == 0.0
    wx_bare = _post(client, "/v1/calculate/wuxing", dict(MUNICH, date="1985-08-02"))
    wx_mid = _post(client, "/v1/calculate/wuxing", dict(MUNICH, date="1985-08-02T00:00:00"))
    assert _strip(wx_bare)["wu_xing_vector"] == _strip(wx_mid)["wu_xing_vector"]
    assert wx_bare["true_solar_time"] == wx_mid["true_solar_time"]
