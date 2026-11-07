"""Endpoint tests for POST /calculate/bazi/natal.

Covers: happy path + response-schema lock, Ten-God agreement with the
internal ``match.ten_gods.ten_god_for_stems`` source (pillar stems AND
hidden stems), the null day-pillar Ten God, hidden-stem identity/weights
against the ruleset + DECISION-003 table (Shen 申 → Geng/Ren/Wu), the
month-command block, precision/warnings behaviour, dual mount parity and
the shared error contract.

Reference chart (2016-08-15T16:00 Europe/Berlin): year Bing Shen,
month Bing Shen, day Ji Si, hour Ren Shen — day master Ji (yin earth).
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from bazi_engine.app import app
from bazi_engine.bafe.ruleset_loader import hidden_stems_for_branch
from bazi_engine.bazi_rules import load_default_ruleset
from bazi_engine.match.ten_gods import ten_god_for_stems

client = TestClient(app)

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas" / "calculate" / "bazi"

REFERENCE_PAYLOAD = {
    "date": "2016-08-15T16:00:00",
    "tz": "Europe/Berlin",
    "lat": 52.52,
    "lon": 13.405,
}


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _post_reference() -> dict:
    res = client.post("/calculate/bazi/natal", json=REFERENCE_PAYLOAD)
    assert res.status_code == 200, res.text
    return res.json()


# ── Happy path ────────────────────────────────────────────────────────────────


def test_happy_path_returns_200_with_all_blocks():
    body = _post_reference()
    for key in ("pillars", "day_master", "month_command", "provenance", "precision", "warnings"):
        assert key in body
    assert set(body["pillars"].keys()) == {"year", "month", "day", "hour"}


def test_response_validates_against_response_schema():
    """Regression-lock: response must validate against
    schemas/calculate/bazi/natal.response.schema.json (Draft 2020-12)."""
    body = _post_reference()
    errors = sorted(
        _validator("natal.response.schema.json").iter_errors(body),
        key=lambda e: list(e.path),
    )
    assert not errors, "Response schema violations: " + "; ".join(
        f"{list(e.path)}: {e.message}" for e in errors[:5]
    )


def test_reference_chart_pillars():
    body = _post_reference()
    got = {
        name: (p["stem"], p["branch"]) for name, p in body["pillars"].items()
    }
    assert got == {
        "year": ("Bing", "Shen"),
        "month": ("Bing", "Shen"),
        "day": ("Ji", "Si"),
        "hour": ("Ren", "Shen"),
    }
    assert body["day_master"] == {
        "stem": "Ji", "stem_cn": "己", "element": "earth", "polarity": "yin",
    }


# ── Ten Gods ─────────────────────────────────────────────────────────────────


def test_pillar_stem_ten_gods_match_internal_source():
    """Every non-day pillar stem's ten_god.name equals the internal
    ``ten_god_for_stems`` result for (day master, stem)."""
    body = _post_reference()
    ruleset = load_default_ruleset()
    day_master = body["day_master"]["stem"]
    for name in ("year", "month", "hour"):
        pillar = body["pillars"][name]
        expected = ten_god_for_stems(ruleset, day_master, pillar["stem"])
        assert pillar["ten_god"]["name"] == expected, name


def test_day_pillar_ten_god_is_null():
    body = _post_reference()
    assert body["pillars"]["day"]["ten_god"] is None


def test_hidden_stem_ten_gods_match_internal_source():
    """Every hidden stem (all four pillars, including the day branch)
    carries a ten_god whose name matches ``ten_god_for_stems``."""
    body = _post_reference()
    ruleset = load_default_ruleset()
    day_master = body["day_master"]["stem"]
    checked = 0
    for pillar in body["pillars"].values():
        for hs in pillar["hidden_stems"]:
            expected = ten_god_for_stems(ruleset, day_master, hs["stem"])
            assert hs["ten_god"]["name"] == expected
            checked += 1
    assert checked >= 4  # every branch has at least a principal Qi stem


def test_ten_god_block_shape_and_known_value():
    """Hour stem Ren vs day master Ji (yin earth controls yang water,
    opposite polarity) → DirectWealth / Zheng Cai."""
    tg = _post_reference()["pillars"]["hour"]["ten_god"]
    assert tg == {
        "name": "DirectWealth",
        "pinyin": "Zheng Cai",
        "element_relation": "controlled_by_day_master",
        "label_de": "Direktes Vermögen",
    }


# ── Hidden stems ─────────────────────────────────────────────────────────────


def test_shen_hidden_stems_match_internal_table():
    """Shen 申 → Geng/Ren/Wu in Qi order (principal/central/residual),
    weights per the DECISION-003 source (1.0/0.5/0.3)."""
    body = _post_reference()
    hour = body["pillars"]["hour"]
    assert hour["branch"] == "Shen"
    got = [(h["stem"], h["qi"], h["weight"]) for h in hour["hidden_stems"]]
    assert got == [
        ("Geng", "principal", 1.0),
        ("Ren", "central", 0.5),
        ("Wu", "residual", 0.3),
    ]


def test_hidden_stem_identities_match_ruleset_for_every_pillar():
    """Per pillar, the hidden-stem identities equal the ruleset
    ``hidden_stems.branch_to_hidden`` list for that branch, in order."""
    body = _post_reference()
    ruleset = load_default_ruleset()
    for name, pillar in body["pillars"].items():
        expected = hidden_stems_for_branch(ruleset, pillar["branch"])
        got = [h["stem"] for h in pillar["hidden_stems"]]
        assert got == expected, name


def test_branch_element_is_principal_qi_element():
    body = _post_reference()
    for pillar in body["pillars"].values():
        principal = pillar["hidden_stems"][0]
        assert principal["qi"] == "principal"
        assert pillar["branch_element"] == principal["element"]


# ── Month command ────────────────────────────────────────────────────────────


def test_month_command_present_with_ruleset_facts():
    mc = _post_reference()["month_command"]
    assert mc == {
        "branch": "Shen",
        "branch_cn": "申",
        "branch_index": 8,
        "principal_qi_stem": "Geng",
        "principal_qi_stem_cn": "庚",
        "element": "metal",
        "source_status": "CALCULATED",
    }


def test_month_command_carries_no_seasonal_strength():
    """No Wang/Xiang-style seasonal-strength assessment exists in the
    engine (MISSING-003) — the endpoint must not fabricate one."""
    mc = _post_reference()["month_command"]
    for forbidden in ("seasonal_state", "strength", "wang_xiang"):
        assert forbidden not in mc


# ── Provenance / precision / warnings ────────────────────────────────────────


def test_provenance_pins_ruleset():
    prov = _post_reference()["provenance"]
    assert prov["source"] == "FuFirE"
    assert prov["ruleset_id"] == "standard_bazi_2026"
    assert prov["ruleset_version"] == "1.0.0"


def test_birth_time_unknown_flags_hour_and_warns():
    payload = dict(REFERENCE_PAYLOAD)
    payload["birth_time_known"] = False
    res = client.post("/calculate/bazi/natal", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["precision"]["birth_time_known"] is False
    assert body["precision"]["provisional_fields"] == ["hour"]
    assert "BIRTH_TIME_UNKNOWN" in body["warnings"]


def test_default_precision_has_no_provisional_fields():
    body = _post_reference()
    assert body["precision"]["birth_time_known"] is True
    assert body["precision"]["provisional_fields"] == []


# ── Mounts ───────────────────────────────────────────────────────────────────


def test_v1_mount_returns_same_chart():
    legacy = _post_reference()
    v1 = client.post("/v1/calculate/bazi/natal", json=REFERENCE_PAYLOAD)
    assert v1.status_code == 200, v1.text
    body = v1.json()
    # computed_at differs per call; everything else must be identical.
    assert body["pillars"] == legacy["pillars"]
    assert body["day_master"] == legacy["day_master"]
    assert body["month_command"] == legacy["month_command"]


# ── Error contract ───────────────────────────────────────────────────────────


def test_invalid_payload_returns_422_envelope():
    payload = dict(REFERENCE_PAYLOAD)
    payload["lat"] = 100.0
    res = client.post("/calculate/bazi/natal", json=payload)
    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "validation_error"
    assert "message" in body
    assert "request_id" in body
    errors = sorted(
        _validator("natal.error.schema.json").iter_errors(body),
        key=lambda e: list(e.path),
    )
    assert not errors, "Error schema violations: " + "; ".join(
        f"{list(e.path)}: {e.message}" for e in errors[:5]
    )


def test_missing_required_field_returns_422():
    payload = dict(REFERENCE_PAYLOAD)
    del payload["date"]
    res = client.post("/calculate/bazi/natal", json=payload)
    assert res.status_code == 422
    assert res.json()["error"] == "validation_error"


def test_dst_gap_with_error_policy_returns_engine_422():
    """Nonexistent local time (spring-forward gap) under the default
    nonexistentTime='error' policy → the shared BaziEngineError envelope."""
    payload = dict(REFERENCE_PAYLOAD)
    payload["date"] = "2021-03-28T02:30:00"  # gap in Europe/Berlin
    res = client.post("/calculate/bazi/natal", json=payload)
    assert res.status_code == 422
    body = res.json()
    assert body["error"] == "dst_time_error"
    assert "request_id" in body
    errors = list(_validator("natal.error.schema.json").iter_errors(body))
    assert not errors
