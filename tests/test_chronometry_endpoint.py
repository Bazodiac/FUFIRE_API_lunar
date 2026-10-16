"""Phase C — POST /v1/chronometry/resolve endpoint spec.

Anti-mockup contract: the endpoint's numbers MUST equal the in-process
``resolve_chronometry`` for the same input (C2). The endpoint-vs-in-process
comparison is backend-agnostic, so no ephemeris-tag split is needed here.

Covers: 200 + full shape + algorithm_version (C1), endpoint==pure module
(C2), invalid input → stable 422 ErrorEnvelope (C3), unknown-time through
HTTP with no noon default (C4).
"""
from __future__ import annotations

import math

from fastapi.testclient import TestClient

from bazi_engine import __version__ as ENGINE_VERSION
from bazi_engine.app import app
from bazi_engine.chronometry import resolve_chronometry

client = TestClient(app)

KNOWN_BODY = {
    "birth": {
        "datetime": "1990-06-15T14:30:00",
        "timezone": "Europe/Berlin",
        "location": {"lat": 52.52, "lon": 13.405},
        "calendar_policy": "gregorian",
    }
}


def _post(body: dict, path: str = "/v1/chronometry/resolve"):
    return client.post(path, json=body)


# ── C1: 200 + full shape + algorithm_version == __version__ ─────────────────

def test_endpoint_200_shape():
    r = _post(KNOWN_BODY)
    assert r.status_code == 200, r.text
    data = r.json()

    assert "request_id" in data
    assert "chronometry" in data
    chrono = data["chronometry"]

    for key in (
        "julian_day",
        "julian_day_number",
        "delta_t_seconds",
        "equation_of_time_minutes",
        "eot_source",
        "longitude_correction_minutes",
        "true_solar_time",
        "solar_longitude_degrees",
        "solar_term",
        "boundary_flags",
        "precision",
    ):
        assert key in chrono, f"missing field: {key}"

    assert chrono["precision"]["algorithm_version"] == ENGINE_VERSION
    assert chrono["precision"]["grade"] in {"exact", "degraded", "unknown_time", "unresolved"}
    assert isinstance(chrono["precision"]["warnings"], list)
    assert chrono["longitude_correction_minutes"] == 13.405 * 4


def test_bare_route_also_registered():
    """Bare (non-/v1) route is registered alongside the /v1 path."""
    r = _post(KNOWN_BODY, path="/chronometry/resolve")
    assert r.status_code == 200, r.text


# ── C2: endpoint JSON == resolve_chronometry(...) in-process (anti-mockup) ──

def test_endpoint_equals_pure_module():
    r = _post(KNOWN_BODY)
    assert r.status_code == 200, r.text
    chrono = r.json()["chronometry"]

    frame = resolve_chronometry(
        "1990-06-15T14:30:00", "Europe/Berlin", 52.52, 13.405, calendar_policy="gregorian"
    )

    assert math.isclose(chrono["julian_day"], frame.julian_day, rel_tol=0, abs_tol=1e-9)
    assert chrono["julian_day_number"] == frame.julian_day_number
    assert math.isclose(chrono["delta_t_seconds"], frame.delta_t_seconds, rel_tol=0, abs_tol=1e-9)
    assert math.isclose(
        chrono["equation_of_time_minutes"], frame.equation_of_time_minutes, rel_tol=0, abs_tol=1e-9
    )
    assert math.isclose(
        chrono["longitude_correction_minutes"], frame.longitude_correction_minutes, abs_tol=1e-9
    )
    assert chrono["true_solar_time"] == frame.true_solar_time
    assert math.isclose(
        chrono["solar_longitude_degrees"], frame.solar_longitude_degrees, rel_tol=0, abs_tol=1e-9
    )
    assert chrono["solar_term"] == frame.solar_term
    assert math.isclose(
        chrono["boundary_flags"]["lichun_jd_ut"], frame.boundary_flags["lichun_jd_ut"], abs_tol=1e-9
    )
    assert chrono["boundary_flags"]["is_before_lichun"] == frame.boundary_flags["is_before_lichun"]
    assert chrono["precision"]["grade"] == frame.precision["grade"]


# ── C3: invalid input → stable 422 ErrorEnvelope (not 500) ──────────────────

def test_invalid_latitude_422():
    body = {
        "birth": {
            "datetime": "1990-06-15T14:30:00",
            "timezone": "Europe/Berlin",
            "location": {"lat": 999, "lon": 13.405},
        }
    }
    r = _post(body)
    assert r.status_code == 422, r.text
    _assert_error_envelope(r.json())


def test_invalid_timezone_422():
    body = {
        "birth": {
            "datetime": "1990-06-15T14:30:00",
            "timezone": "Not/AZone",
            "location": {"lat": 52.52, "lon": 13.405},
        }
    }
    r = _post(body)
    assert r.status_code == 422, r.text
    _assert_error_envelope(r.json())


def test_missing_location_422():
    body = {
        "birth": {
            "datetime": "1990-06-15T14:30:00",
            "timezone": "Europe/Berlin",
        }
    }
    r = _post(body)
    assert r.status_code == 422, r.text
    _assert_error_envelope(r.json())


def _assert_error_envelope(payload: dict) -> None:
    # ErrorEnvelope conventions (routers/shared.py): error/message/status/
    # path/timestamp/request_id present.
    for key in ("error", "message", "status", "path", "timestamp", "request_id"):
        assert key in payload, f"ErrorEnvelope missing {key}: {payload}"
    assert payload["status"] == 422


# ── C4: unknown-time through HTTP (no noon default) ─────────────────────────

def test_unknown_time_no_noon_default_date_only():
    body = {
        "birth": {
            "datetime": "1990-06-15",
            "timezone": "Europe/Berlin",
            "location": {"lat": 52.52, "lon": 13.405},
        }
    }
    r = _post(body)
    assert r.status_code == 200, r.text
    chrono = r.json()["chronometry"]
    assert chrono["precision"]["grade"] == "unknown_time"
    assert chrono["true_solar_time"] is None
    assert chrono["precision"]["warnings"], "unknown-time must carry a warning"


def test_unknown_time_explicit_flag():
    body = {
        "birth": {
            "datetime": "1990-06-15T14:30:00",
            "timezone": "Europe/Berlin",
            "location": {"lat": 52.52, "lon": 13.405},
            "time_known": False,
        }
    }
    r = _post(body)
    assert r.status_code == 200, r.text
    chrono = r.json()["chronometry"]
    assert chrono["precision"]["grade"] == "unknown_time"
    assert chrono["true_solar_time"] is None
