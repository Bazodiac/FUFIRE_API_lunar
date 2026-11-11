"""Endpoint tests for POST /calculate/bazi/dayun (TASK-DY-010).

Covers happy path against the article example (1987-07-04 Berlin), traditional
direction resolution, validation envelope shape, and response-schema lock.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from bazi_engine.app import app

client = TestClient(app)

ARTICLE_PAYLOAD = {
    "date": "1987-07-04T21:30:00",
    "tz": "Europe/Berlin",
    "lat": 52.52,
    "lon": 13.405,
    "as_of_date": "2026-05-22",
    "direction_method": "explicit",
    "flow_direction": "forward",
    "sex_at_birth": None,
    "cycles": 8,
}


def test_happy_path_returns_200_with_dayun_block():
    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "dayun" in body
    assert "provenance" in body
    assert "precision" in body
    assert body["dayun"]["direction"] == "forward"
    assert body["dayun"]["direction_method"] == "explicit"
    assert isinstance(body["dayun"]["cycles"], list)
    assert len(body["dayun"]["cycles"]) == 8


def test_happy_path_provenance_pins():
    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["provenance"]["ruleset_id"] == "dayun_v1"
    assert body["provenance"]["source"] == "FuFirE"


def test_happy_path_first_cycle_pillar_shape():
    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    cycles = res.json()["dayun"]["cycles"]
    p = cycles[0]["pillar"]
    assert isinstance(p["stem"], str)
    assert isinstance(p["branch"], str)
    assert isinstance(p["element"], str)
    assert p["polarity"] in ("yin", "yang")
    assert 0 <= p["index60"] <= 59


def test_happy_path_relation_to_day_master_present():
    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    rel = res.json()["dayun"]["cycles"][0]["relation_to_day_master"]
    for key in ("day_master", "ten_god", "element_relation", "label_de"):
        assert key in rel
    assert isinstance(rel["ten_god"], str)


def test_happy_path_current_set_when_as_of_in_range():
    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["dayun"]["current"] is not None
    matching = [c for c in body["dayun"]["cycles"] if c["is_current"]]
    assert len(matching) == 1
    assert matching[0]["sequence"] == body["dayun"]["current"]["sequence"]


def test_missing_direction_returns_422():
    payload = dict(ARTICLE_PAYLOAD)
    del payload["flow_direction"]
    res = client.post("/calculate/bazi/dayun", json=payload)
    assert res.status_code == 422
    body = res.json()
    assert body.get("error") == "direction_basis_missing"
    assert "message" in body
    assert "request_id" in body


def test_traditional_mode_without_sex_returns_422():
    payload = dict(ARTICLE_PAYLOAD)
    payload["direction_method"] = "year_stem_yinyang_and_sex"
    payload.pop("flow_direction", None)
    payload["sex_at_birth"] = None
    res = client.post("/calculate/bazi/dayun", json=payload)
    assert res.status_code == 422
    body = res.json()
    assert body.get("error") == "direction_basis_missing"


def test_traditional_mode_with_sex_returns_200():
    payload = dict(ARTICLE_PAYLOAD)
    payload["direction_method"] = "year_stem_yinyang_and_sex"
    payload.pop("flow_direction", None)
    payload["sex_at_birth"] = "female"
    res = client.post("/calculate/bazi/dayun", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["dayun"]["direction_method"] == "year_stem_yinyang_and_sex"
    # 1987 = Ding (yin) year (stem_index=3). Yin year + female → forward.
    assert body["dayun"]["direction"] == "forward"


def test_invalid_payload_returns_422():
    payload = dict(ARTICLE_PAYLOAD)
    payload["lat"] = 100.0
    res = client.post("/calculate/bazi/dayun", json=payload)
    assert res.status_code == 422


def test_default_cycles_is_8():
    payload = dict(ARTICLE_PAYLOAD)
    del payload["cycles"]
    res = client.post("/calculate/bazi/dayun", json=payload)
    assert res.status_code == 200, res.text
    assert len(res.json()["dayun"]["cycles"]) == 8


def test_decade_dates_span_real_gregorian_years():
    """Each cycle's date_end - date_start is a real decade (~3652-3653 days),
    not the old 360-day ritual decade (3600 days)."""
    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    cycles = res.json()["dayun"]["cycles"]
    for c in cycles:
        span = (date.fromisoformat(c["date_end"]) - date.fromisoformat(c["date_start"])).days
        assert 3652 <= span <= 3653, f"cycle {c['sequence']} span {span}d"


def test_decade_dates_are_contiguous():
    """Consecutive decades abut: cycle[i+1].date_start == cycle[i].date_end."""
    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    cycles = res.json()["dayun"]["cycles"]
    for i in range(len(cycles) - 1):
        assert cycles[i + 1]["date_start"] == cycles[i]["date_end"], (
            f"gap between cycle {cycles[i]['sequence']} and {cycles[i + 1]['sequence']}"
        )


def test_date_model_and_current_selection_agree():
    """Locks date-model ↔ current-cycle agreement: an as_of_date strictly inside
    cycle 4's [date_start, date_end) must make cycle 4 the current one, and the
    single is_current cycle must actually bracket that as_of date."""
    first = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert first.status_code == 200, first.text
    cycle4 = first.json()["dayun"]["cycles"][3]
    start = date.fromisoformat(cycle4["date_start"])
    end = date.fromisoformat(cycle4["date_end"])
    midpoint = start + (end - start) / 2  # strictly inside [start, end)

    payload = dict(ARTICLE_PAYLOAD)
    payload["as_of_date"] = midpoint.isoformat()
    res = client.post("/calculate/bazi/dayun", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["dayun"]["current"]["sequence"] == 4
    matching = [c for c in body["dayun"]["cycles"] if c["is_current"]]
    assert len(matching) == 1
    cur = matching[0]
    assert cur["sequence"] == 4
    assert cur["date_start"] <= payload["as_of_date"] < cur["date_end"]


def test_current_semantic_summary_is_populated():
    """DL-3: the current decade's semantic_summary is filled deterministically
    from the Ten-God bucket + classical branch relations. The article payload's
    current decade (Geng Xu) 六合-combines the natal year pillar (Mao) and carries
    a Qi Sha friction, so both supports and frictions are non-empty."""
    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    current = res.json()["dayun"]["current"]
    assert current is not None
    ss = current["semantic_summary"]
    assert set(ss.keys()) == {"road_metaphor", "supports", "frictions", "practice"}
    assert isinstance(ss["road_metaphor"], str)
    assert len(ss["practice"]) == 1
    for key in ("supports", "frictions", "practice"):
        assert isinstance(ss[key], list)
        assert all(isinstance(item, str) for item in ss[key])
    # Crafted case: at least one of supports/frictions carries evidence.
    assert ss["supports"] or ss["frictions"]
    # Specifically: a 六合 support line and the Qi Sha friction phrase.
    assert any(line.startswith("六合") for line in ss["supports"])
    assert any("Druck/Struktur" in line for line in ss["frictions"])


def test_response_validates_against_response_schema():
    """Regression-lock: response must validate against
    schemas/calculate/bazi/dayun.response.schema.json (Draft 2020-12)."""
    schema_path = (
        Path(__file__).resolve().parent.parent
        / "schemas"
        / "calculate"
        / "bazi"
        / "dayun.response.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    res = client.post("/calculate/bazi/dayun", json=ARTICLE_PAYLOAD)
    assert res.status_code == 200, res.text
    body = res.json()
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.path))
    assert not errors, "Response schema violations: " + "; ".join(
        f"{list(e.path)}: {e.message}" for e in errors[:5]
    )


def test_start_anchor_is_jie_not_zhongqi():
    """Regression: 1987-02-17 12:00 Berlin, forward.  The next term after birth
    is the zhongqi Yu Shui; Da Yun must count to the next jie, Jing Zhe, which
    gives a start age of 5 years (not 0).  Neutral synthetic birth data."""
    payload = dict(ARTICLE_PAYLOAD)
    payload["date"] = "1987-02-17T12:00:00"
    res = client.post("/calculate/bazi/dayun", json=payload)
    assert res.status_code == 200, res.text
    start = res.json()["dayun"]["start"]
    assert start["anchor_term"]["name"] == "Jing Zhe"
    assert start["anchor_term"]["direction"] == "next"
    assert start["start_age"]["years"] == 5
