"""Owner decision 1 after the sprint-2 TLST review (report §5, R2 finding F2):

``/validate`` computed its TLST with the day-of-year Spencer approximation
(``eot_provenance = "spencer_1971"``, up to 0.8 min off) while every other
surface used the shared UTC-axis context with the Meeus EoT. At a 2-hour
branch edge the two could disagree on the hour branch. ``/validate`` now
consumes the same context; ``eot_provenance`` reports ``"meeus_1998"``.

HTTP-observable consequence: ``discretization_evidence.boundary_distance_deg``
is derived from the TLST hour (0.25° per minute of distance to the nearest
2-hour edge), so it must agree with ``/calculate/tst`` for the same instant.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft7Validator

from bazi_engine.app import app
from bazi_engine.bafe.mapping import hour_branch_index_from_tlst, nearest_hour_boundary_distance_minutes
from bazi_engine.bafe.time_model import evaluate_time

client = TestClient(app)
RESP_SCHEMA = json.loads(
    (Path(__file__).resolve().parents[1] / "spec" / "schemas" / "ValidateResponse.schema.json").read_text(encoding="utf-8")
)
RESP_VALIDATOR = Draft7Validator(RESP_SCHEMA)


def _engine_config(**overrides) -> dict:
    cfg = {
        "engine_version": "1.0.0-rc0",
        "parameter_set_id": "standard",
        "deterministic": True,
        "compliance_mode": "RELAXED",
        "bazi_ruleset_id": "standard_bazi_2026",
        "time_standard": "TLST",
        "time_fallback_policy": {"allow_compute_tlst_without_ut1": True},
        "refdata": {
            "refdata_pack_id": "refpack-test-001",
            "refdata_mode": "BUNDLED_OFFLINE",
            "allow_network": False,
            "refdata_root_path": None,
            "ephemeris_id": "swisseph-2026",
            "tzdb_version_id": "tzdb-2026a",
            "leaps_source_id": "leaps-iers",
            "eop_source_id": None,
            "verification_policy": {
                "tzdb_gpg_required": False,
                "ephemeris_hash_required": False,
                "leaps_expiry_enforced": False,
                "eop_redundancy_required": False,
            },
        },
    }
    cfg.update(overrides)
    return cfg


def _payload(birth_event: dict) -> dict:
    return {
        "validate_level": "FULL",
        "now_utc_override": "2026-01-01T00:00:00Z",
        "engine_config": _engine_config(),
        "birth_event": birth_event,
    }


# R2 finding F2: 2024-11-29 00:48:32 UTC, lon 0 → TLST 1.0039 h (Meeus) vs
# 0.9933 h (Spencer): Chou vs Zi, on opposite sides of the 01:00 edge.
EDGE_CASE = {"local_datetime": "2024-11-29T00:48:32", "tz_id": "UTC",
             "geo_lon_deg": 0.0, "geo_lat_deg": 51.5}
HANNOVER = {"local_datetime": "1990-07-15T15:44:00", "tz_id": "Europe/Berlin",
            "geo_lon_deg": 9.732, "geo_lat_deg": 52.3759}


def _evaluate(birth_event: dict):
    errors, warnings, evd, comp, tlst_hours = evaluate_time(
        engine_config=_engine_config(), birth_event=birth_event, positions_override=None,
        compliance_mode="RELAXED", now_utc=datetime(2026, 1, 1),
    )
    assert not errors, errors
    return evd, tlst_hours


def _tst_hours(local_iso: str, tz: str, lon: float) -> float:
    r = client.post("/calculate/tst", json={"date": local_iso, "tz": tz, "lon": lon})
    assert r.status_code == 200, r.text
    return r.json()["true_solar_time_hours"]


def test_validate_tlst_equals_calculate_tst_at_the_branch_edge():
    evd, tlst_hours = _evaluate(EDGE_CASE)
    assert evd["eot_provenance"] == "meeus_1998"
    assert evd["tlst_quality"] == "degraded"           # UT1 axis unchanged
    assert tlst_hours == pytest.approx(_tst_hours("2024-11-29T00:48:32", "UTC", 0.0), abs=1e-4)
    assert hour_branch_index_from_tlst(tlst_hours) == 1  # Chou — Spencer said Zi (0)


def test_validate_tlst_hannover_matches_the_reference_surface():
    evd, tlst_hours = _evaluate(HANNOVER)
    assert tlst_hours == pytest.approx(_tst_hours("1990-07-15T15:44:00", "Europe/Berlin", 9.732), abs=1e-4)
    assert hour_branch_index_from_tlst(tlst_hours) == 7  # Wei


def test_fixed_offset_branch_agrees_with_tz_id_branch():
    """``tz_offset_sec`` without ``tz_id`` must go through the same context."""
    by_tz, h_tz = _evaluate(HANNOVER)
    by_off, h_off = _evaluate({"local_datetime": "1990-07-15T15:44:00", "tz_offset_sec": 7200,
                               "geo_lon_deg": 9.732, "geo_lat_deg": 52.3759})
    assert h_off == pytest.approx(h_tz, abs=1e-9)
    assert by_off["eot_provenance"] == by_tz["eot_provenance"] == "meeus_1998"


def test_missing_zone_information_still_yields_missing_quality():
    errors, _, evd, _, tlst_hours = evaluate_time(
        engine_config=_engine_config(),
        birth_event={"local_datetime": "1990-07-15T15:44:00", "geo_lon_deg": 9.732, "geo_lat_deg": 52.3759},
        positions_override=None, compliance_mode="RELAXED", now_utc=datetime(2026, 1, 1),
    )
    assert tlst_hours is None
    assert evd["tlst_quality"] == "missing"
    assert evd["eot_provenance"] is None


def test_http_validate_reports_meeus_and_a_tst_consistent_boundary_distance():
    r = client.post("/validate", json=_payload(EDGE_CASE))
    assert r.status_code == 200, r.text
    body = r.json()
    assert not list(RESP_VALIDATOR.iter_errors(body)), list(RESP_VALIDATOR.iter_errors(body))
    assert body["evidence"]["time"]["eot_provenance"] == "meeus_1998"
    expected_deg = nearest_hour_boundary_distance_minutes(_tst_hours("2024-11-29T00:48:32", "UTC", 0.0)) * 0.25
    assert body["evidence"]["discretization"]["boundary_distance_deg"] == pytest.approx(expected_deg, abs=1e-3)
    # Spencer's 0.9933 h would have put the edge 0.4 min (0.1°) away; Meeus 0.23 min (0.059°).
    assert body["evidence"]["discretization"]["boundary_distance_deg"] < 0.08
