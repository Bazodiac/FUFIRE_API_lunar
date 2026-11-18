"""exclude_time_dependent on /calculate/fusion and /fusion/vector-map.

With the switch on, the ascendant and the hour pillar leave both vectors, every
derived value (elemental_comparison, harmony, cosmic_state, calibration) is
computed from the reduced inputs, and the left-out contributions are listed in
contribution_ledger.excluded (reason "time_dependent"). Expected values are
recomputed here from the reduced inputs with local tables, not by calling the
engine's vector code.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.wuxing import calculate_wuxing_vector_from_planets_with_ledger, is_night_chart
from bazi_engine.wuxing.calibration import _BASELINE_TABLE

ORDER = ["Holz", "Feuer", "Erde", "Metall", "Wasser"]
STEM_EL = {"Jia": "Holz", "Yi": "Holz", "Bing": "Feuer", "Ding": "Feuer", "Wu": "Erde", "Ji": "Erde",
           "Geng": "Metall", "Xin": "Metall", "Ren": "Wasser", "Gui": "Wasser"}
HIDDEN = {
    "Zi": [("Wasser", 1.0)], "Chou": [("Erde", 1.0), ("Wasser", 0.5), ("Metall", 0.3)],
    "Yin": [("Holz", 1.0), ("Feuer", 0.5), ("Erde", 0.3)], "Mao": [("Holz", 1.0)],
    "Chen": [("Erde", 1.0), ("Holz", 0.5), ("Wasser", 0.3)], "Si": [("Feuer", 1.0), ("Metall", 0.5), ("Erde", 0.3)],
    "Wu": [("Feuer", 1.0), ("Erde", 0.5)], "Wei": [("Erde", 1.0), ("Feuer", 0.5), ("Holz", 0.3)],
    "Shen": [("Metall", 1.0), ("Wasser", 0.5), ("Erde", 0.3)], "You": [("Metall", 1.0)],
    "Xu": [("Erde", 1.0), ("Metall", 0.5), ("Feuer", 0.3)], "Hai": [("Wasser", 1.0), ("Holz", 0.5)],
}
REQ = {"date": "1985-08-02T14:15:00", "tz": "Europe/Berlin", "lat": 48.1374, "lon": 11.5755}
CLIENT_PILLARS = {
    "year": {"stamm": "Yi", "zweig": "Chou"}, "month": {"stamm": "Gui", "zweig": "Wei"},
    "day": {"stamm": "Gui", "zweig": "You"}, "hour": {"stamm": "Ji", "zweig": "Wei"},
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _post(client: TestClient, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    resp = client.post(path, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _bazi_vector(pillars: Dict[str, Dict[str, str]]) -> List[float]:
    v = dict.fromkeys(ORDER, 0.0)
    for p in pillars.values():
        v[STEM_EL[p["stamm"]]] += 1.0
        for el, w in HIDDEN[p["zweig"]]:
            v[el] += w
    return [v[k] for k in ORDER]


def _west_vector(ledger: List[Dict[str, Any]]) -> List[float]:
    v = dict.fromkeys(ORDER, 0.0)
    for e in ledger:
        for el, amount in e["distribution"].items():
            v[el] += amount
    return [v[k] for k in ORDER]


def _unit(v: List[float]) -> List[float]:
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def _bucket(n: int, edges: tuple) -> str:
    return "sparse" if n <= edges[0] else "medium" if n <= edges[1] else "dense"


def _pillars_from_bazi(client: TestClient) -> Dict[str, Dict[str, str]]:
    bazi = _post(client, "/v1/calculate/bazi", REQ)
    return {k: {"stamm": v["stamm"], "zweig": v["zweig"]} for k, v in bazi["pillars"].items()}


def _check_reduced(body: Dict[str, Any], pillars: Dict[str, Dict[str, str]]) -> None:
    ledger = body["contribution_ledger"]
    # Nothing time-dependent in the active ledger; both kinds in `excluded`.
    assert all(e["planet"] != "Ascendant" for e in ledger["western"])
    assert all(e["pillar"] != "hour" for e in ledger["bazi"])
    excluded = ledger["excluded"]
    assert [e["planet"] for e in excluded if e["system"] == "western"] == ["Ascendant"]
    hour = pillars["hour"]
    assert sorted((e.get("stem_name") or e.get("branch_name"), e["weight"]) for e in excluded if e["system"] == "bazi") == sorted(
        [(hour["stamm"], 1.0)] + [(hour["zweig"], w) for _, w in HIDDEN[hour["zweig"]]]
    )
    assert {e["reason"] for e in excluded} == {"time_dependent"}
    assert ledger["chart_type_quality"] == "time_excluded"
    assert body["quality_flags"]["chart_type_quality"] == "time_excluded"
    assert body["provenance"]["parameter_set"]["time_dependent_excluded"] is True

    reduced = {k: v for k, v in pillars.items() if k != "hour"}
    n_bazi = sum(1 + len(HIDDEN[p["zweig"]]) for p in reduced.values())
    cal = body["calibration"]
    assert cal["n_bazi_contributions"] == n_bazi

    west = _unit(_west_vector(ledger["western"]))
    bazi = _unit(_bazi_vector(reduced))
    for i, el in enumerate(ORDER):
        assert body["elemental_comparison"][el] == {
            "western": round(west[i], 3), "bazi": round(bazi[i], 3), "difference": round(west[i] - bazi[i], 3),
        }
        assert body["wu_xing_vectors"]["bazi_pillars"][el] == pytest.approx(bazi[i], abs=1e-9)
    cos = sum(w * b for w, b in zip(west, bazi))
    assert body["cosmic_state"] == round(cos, 4)
    assert cal["h_raw"] == pytest.approx(body["harmony_index"]["harmony_index"])
    baseline, sigma = _BASELINE_TABLE[(_bucket(cal["n_west"], (3, 8)), _bucket(n_bazi, (8, 16)))]
    assert cal["h_baseline"] == round(baseline, 4)
    assert cal["sigma_above"] == round((cal["h_raw"] - baseline) / sigma, 3)


def test_switch_on_computed_pillars(client: TestClient) -> None:
    body = _post(client, "/v1/calculate/fusion", dict(REQ, exclude_time_dependent=True))
    _check_reduced(body, _pillars_from_bazi(client))
    assert body["precision"] == {"birth_time_known": True, "provisional_fields": []}


def test_switch_follows_birth_time_known(client: TestClient) -> None:
    body = _post(client, "/v1/calculate/fusion", dict(REQ, birth_time_known=False))
    _check_reduced(body, _pillars_from_bazi(client))
    explicit_off = _post(client, "/v1/calculate/fusion", dict(REQ, birth_time_known=False, exclude_time_dependent=False))
    assert "excluded" not in explicit_off["contribution_ledger"]
    assert any(e["planet"] == "Ascendant" for e in explicit_off["contribution_ledger"]["western"])


def test_switch_on_client_pillars(client: TestClient) -> None:
    body = _post(client, "/v1/calculate/fusion", dict(REQ, bazi_pillars=CLIENT_PILLARS, exclude_time_dependent=True))
    _check_reduced(body, CLIENT_PILLARS)


def test_switch_on_date_only(client: TestClient) -> None:
    """The Reading-Kit call: date only, no standard, no switch → excluded by default."""
    body = _post(client, "/v1/calculate/fusion", {"date": "1985-08-02", "tz": "Europe/Berlin",
                                                 "lat": 48.1374, "lon": 11.5755, "birth_time_known": False})
    bazi = _post(client, "/v1/calculate/bazi", {"date": "1985-08-02", "tz": "Europe/Berlin", "lat": 48.1374, "lon": 11.5755})
    _check_reduced(body, {k: {"stamm": v["stamm"], "zweig": v["zweig"]} for k, v in bazi["pillars"].items()})


@pytest.mark.parametrize("pillars", [None, CLIENT_PILLARS])
def test_vector_map_switch_on(client: TestClient, pillars) -> None:
    body = dict(REQ, exclude_time_dependent=True)
    if pillars:
        body["bazi_pillars"] = pillars
    vm = _post(client, "/v1/calculate/fusion/vector-map", body)
    fusion = _post(client, "/v1/calculate/fusion", body)
    used = pillars or _pillars_from_bazi(client)
    reduced = {k: v for k, v in used.items() if k != "hour"}
    raw_bazi = _bazi_vector(reduced)
    assert [vm["vector_map"]["bazi_pillars"]["raw"][k] for k in ORDER] == pytest.approx(raw_bazi)
    raw_west = _west_vector(fusion["contribution_ledger"]["western"])
    assert [vm["vector_map"]["western_planets"]["raw"][k] for k in ORDER] == pytest.approx(raw_west)
    assert vm["harmony"]["cosine_similarity"] == fusion["cosmic_state"]
    assert vm["metadata"]["time_dependent_excluded"] is True


def test_switch_off_known_time_adds_nothing(client: TestClient) -> None:
    omitted = _post(client, "/v1/calculate/fusion", REQ)
    explicit = _post(client, "/v1/calculate/fusion", dict(REQ, exclude_time_dependent=False))
    for body in (omitted, explicit):
        assert "excluded" not in body["contribution_ledger"]
        assert body["contribution_ledger"]["chart_type_quality"] == "exact"
        assert "time_dependent_excluded" not in body["provenance"]["parameter_set"]
        assert "warnings" not in body
        assert any(e["planet"] == "Ascendant" for e in body["contribution_ledger"]["western"])
    for body in (omitted, explicit):
        body["provenance"].pop("computation_timestamp")
    assert omitted == explicit
    vm = _post(client, "/v1/calculate/fusion/vector-map", REQ)
    assert set(vm) == {"request_id", "input", "vector_map", "harmony", "metadata"}
    assert set(vm["metadata"]) == {"mapping_version", "algorithm_version"}


def test_sparse_bazi_side_is_reported_not_bypassed(client: TestClient) -> None:
    """Three single-Qi branches leave n_bazi = 6 < 8: quality "sparse", sparse cell."""
    pillars = {"year": {"stamm": "Jia", "zweig": "Zi"}, "month": {"stamm": "Ding", "zweig": "Mao"},
               "day": {"stamm": "Xin", "zweig": "You"}, "hour": {"stamm": "Wu", "zweig": "Wu"}}
    body = _post(client, "/v1/calculate/fusion", dict(REQ, bazi_pillars=pillars, exclude_time_dependent=True))
    cal = body["calibration"]
    assert cal["n_bazi_contributions"] == 6
    assert cal["quality"] == "sparse"
    assert cal["h_baseline"] == _BASELINE_TABLE[(_bucket(cal["n_west"], (3, 8)), "sparse")][0]


def test_day_night_changes_no_contribution() -> None:
    """Under sign-element-consensus-v1 / body-tier-q0.3-v1 no body depends on day/night."""
    bodies = {"Sun": {"longitude": 130.0}, "Moon": {"longitude": 10.0}, "Mercury": {"longitude": 140.0},
              "Venus": {"longitude": 100.0}, "Saturn": {"longitude": 230.0}}
    day_asc, night_asc = 200.0, 20.0  # Sun above / below the horizon
    assert is_night_chart(130.0, day_asc) != is_night_chart(130.0, night_asc)
    v_day, l_day = calculate_wuxing_vector_from_planets_with_ledger(bodies, ascendant=day_asc, strict=True, include_ascendant=False)
    v_night, l_night = calculate_wuxing_vector_from_planets_with_ledger(bodies, ascendant=night_asc, strict=True, include_ascendant=False)
    assert v_day.to_list() == v_night.to_list()
    assert [e["distribution"] for e in l_day] == [e["distribution"] for e in l_night]
