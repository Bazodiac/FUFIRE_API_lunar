#!/usr/bin/env python3
"""Standalone FuFirE mock server for frontend development and integration testing.

Serves deterministic responses from snapshot fixtures — no ephemeris files needed.
Supports scenario switching, latency simulation, and error injection.

Usage:
    python tests/mock_server.py                     # default port 8081
    python tests/mock_server.py --port 9000         # custom port
    python tests/mock_server.py --latency 200       # 200ms simulated latency
    python tests/mock_server.py --scenario hilat    # use high-latitude fixtures
    MOCK_FAIL_RATE=0.1 python tests/mock_server.py  # 10% random 500 errors
"""
from __future__ import annotations

import json
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from bazi_engine.wuxing.analysis import calculate_wuxing_from_bazi_with_ledger

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots" / "moseph"

# Precision-sensitive surfaces intentionally not represented by the mock.
# Consumers must call a real SWIEPH-backed test boundary for these paths.
MOCK_EXCLUSIONS: dict[str, str] = {
    "/v2/astronomy/lunar-state": (
        "Scientific Lunar V2 values and provider provenance must come from a "
        "real locked ephemeris boundary, not a fabricated endpoint-tester response."
    ),
    "/v2/calculate/bazi": (
        "Opt-in TLST pillars, time basis and boundary-uncertainty flags (INC-1) must "
        "come from a real locked ephemeris boundary, not a fabricated endpoint-tester response."
    ),
    "/v2/calculate/bazi/natal": (
        "Opt-in TLST natal chart and its shared time basis (INC-1) must come from a "
        "real locked ephemeris boundary, not a fabricated endpoint-tester response."
    ),
}

# ---------------------------------------------------------------------------
# Scenario registry — maps scenario prefixes to snapshot case IDs
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict[str, str]] = {
    "default": {
        "bazi": "std_1990_berlin",
        "western": "std_1990_berlin",
        "fusion": "std_1990_berlin",
        "wuxing": "std_1990_berlin",
    },
    "lichun": {
        "bazi": "lichun_2024_after_berlin",
        "western": "lichun_2024_after_berlin",
        "fusion": "lichun_2024_after_berlin",
        "wuxing": "lichun_2024_after_berlin",
    },
    "hilat": {
        "bazi": "hilat_longyearbyen",
        "western": "hilat_longyearbyen",
        "fusion": "hilat_longyearbyen",
        "wuxing": "hilat_longyearbyen",
    },
    "zi": {
        "bazi": "zi_2300_berlin",
        "western": "zi_2300_berlin",
        "fusion": "zi_2300_berlin",
        "wuxing": "zi_2300_berlin",
    },
}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SCENARIO = os.environ.get("MOCK_SCENARIO", "default")
_LATENCY_MS = int(os.environ.get("MOCK_LATENCY_MS", "0"))
_FAIL_RATE = float(os.environ.get("MOCK_FAIL_RATE", "0"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_snapshot(case_id: str, endpoint: str) -> dict[str, Any]:
    """Load a snapshot fixture file."""
    path = SNAPSHOTS_DIR / f"{case_id}__{endpoint}.json"
    if not path.exists():
        raise FileNotFoundError(f"Snapshot not found: {path}")
    return json.loads(path.read_text())


def _resolve_case(endpoint: str) -> str:
    """Resolve the current scenario's case ID for an endpoint."""
    scenario = SCENARIOS.get(_SCENARIO, SCENARIOS["default"])
    return scenario.get(endpoint, scenario.get("bazi", "std_1990_berlin"))


def _maybe_fail() -> None:
    """Randomly inject 500 errors at the configured rate."""
    if _FAIL_RATE > 0 and random.random() < _FAIL_RATE:
        raise HTTPException(
            status_code=500,
            detail={
                "error": "mock_injected_error",
                "message": "Simulated server error (MOCK_FAIL_RATE)",
            },
        )


def _simulate_latency() -> None:
    """Add simulated network latency.

    Uses blocking sleep intentionally — this mock server is designed for
    single-threaded dev/test use, not production concurrency.
    """
    if _LATENCY_MS > 0:
        time.sleep(_LATENCY_MS / 1000)


def _std_headers(request_id: str | None = None) -> dict[str, str]:
    rid = request_id or str(uuid.uuid4())
    return {
        "X-Request-ID": rid,
        "X-API-Version": "1.0.0-rc1-mock",
        "X-Response-Time-ms": str(_LATENCY_MS or 1),
        "X-Mock-Server": "true",
        "X-Mock-Scenario": _SCENARIO,
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FuFirE Mock Server",
    version="1.0.0-rc1-mock",
    description=(
        "Mock server for FuFirE API development. "
        "Serves deterministic snapshot fixtures without ephemeris dependencies."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Info endpoints (static)
# ---------------------------------------------------------------------------


@app.get("/health")
@app.get("/v1/health")
def health():
    return {"status": "healthy", "mode": "mock", "scenario": _SCENARIO}


@app.get("/")
@app.get("/v1/")
def root():
    return {
        "status": "ok",
        "service": "FuFirE — Fusion Firmament Engine (MOCK)",
        "mode": "mock",
        "scenario": _SCENARIO,
        "available_scenarios": list(SCENARIOS.keys()),
    }


@app.get("/build")
@app.get("/v1/build")
def build():
    return {"version": "1.0.0-rc1-mock", "mock": True}


@app.get("/ready")
@app.get("/v1/ready")
def ready():
    return {"ready": True, "mock": True}


# ---------------------------------------------------------------------------
# Mock scenario control (not in production API)
# Note: Global state mutation is intentional for this dev-only mock server.
# Not thread-safe — designed for single-client dev/test use.
# ---------------------------------------------------------------------------


@app.get("/mock/scenarios")
def list_scenarios():
    """List available mock scenarios and current selection."""
    return {
        "current": _SCENARIO,
        "available": list(SCENARIOS.keys()),
        "snapshots_dir": str(SNAPSHOTS_DIR),
        "total_snapshots": len(list(SNAPSHOTS_DIR.glob("*.json"))),
    }


@app.post("/mock/scenario/{name}")
def switch_scenario(name: str):
    """Switch the active mock scenario."""
    global _SCENARIO
    if name not in SCENARIOS:
        raise HTTPException(404, detail=f"Unknown scenario: {name}. Available: {list(SCENARIOS.keys())}")
    _SCENARIO = name
    return {"scenario": _SCENARIO, "message": f"Switched to '{name}'"}


@app.post("/mock/latency/{ms}")
def set_latency(ms: int):
    """Set simulated latency in milliseconds."""
    global _LATENCY_MS
    _LATENCY_MS = max(0, ms)
    return {"latency_ms": _LATENCY_MS}


# ---------------------------------------------------------------------------
# Calculation endpoints (serve snapshots)
# ---------------------------------------------------------------------------


@app.post("/calculate/bazi")
@app.post("/v1/calculate/bazi")
def calculate_bazi(
    request: Request,
    x_api_key: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    _simulate_latency()
    _maybe_fail()
    data = _load_snapshot(_resolve_case("bazi"), "bazi")
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.post("/calculate/bazi/trace")
@app.post("/v1/calculate/bazi/trace")
def calculate_bazi_trace(
    request: Request,
    x_api_key: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    # ADR-1 alias: same body shape as /calculate/bazi with the derivation
    # trace always attached. The bazi snapshot already includes the trace,
    # so we reuse it directly.
    _simulate_latency()
    _maybe_fail()
    data = _load_snapshot(_resolve_case("bazi"), "bazi")
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.post("/calculate/western")
@app.post("/v1/calculate/western")
def calculate_western(
    request: Request,
    x_api_key: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    _simulate_latency()
    _maybe_fail()
    data = _load_snapshot(_resolve_case("western"), "western")
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.post("/calculate/fusion")
@app.post("/v1/calculate/fusion")
def calculate_fusion(
    request: Request,
    x_api_key: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    _simulate_latency()
    _maybe_fail()
    data = _load_snapshot(_resolve_case("fusion"), "fusion")
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.post("/calculate/wuxing")
@app.post("/v1/calculate/wuxing")
def calculate_wuxing(
    request: Request,
    x_api_key: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    _simulate_latency()
    _maybe_fail()
    data = _load_snapshot(_resolve_case("wuxing"), "wuxing")
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.post("/calculate/bazi/wuxing")
@app.post("/v1/calculate/bazi/wuxing")
def calculate_bazi_wuxing(
    request: Request,
    x_api_key: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    """Derive the BaZi Wu-Xing mock from the selected frozen BaZi snapshot."""
    del request, x_api_key
    _simulate_latency()
    _maybe_fail()
    bazi = _load_snapshot(_resolve_case("bazi"), "bazi")
    pillars = {
        name: {"stem": item["stamm"], "branch": item["zweig"]}
        for name, item in bazi["pillars"].items()
    }
    vector, ledger = calculate_wuxing_from_bazi_with_ledger(pillars)
    values = vector.to_dict()
    ephemeris_id = bazi["provenance"].get("ephemeris_id", "")
    mode = "MOSEPH" if ephemeris_id == "moshier_analytic" else "SWIEPH"
    body = {
        "input": bazi["input"],
        "wu_xing_vector": values,
        "dominant_element": max(values, key=values.__getitem__),
        "basis": "bazi_four_pillars",
        "pillars": pillars,
        "contribution_ledger": {"bazi": ledger},
        "provenance": bazi["provenance"],
        "quality_flags": {"ephemeris_mode": mode},
        "precision": bazi["precision"],
    }
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.post("/calculate/fusion/vector-map")
@app.post("/v1/calculate/fusion/vector-map")
def calculate_fusion_vector_map(
    request: Request,
    x_api_key: str | None = Header(None),
    x_request_id: str | None = Header(None),
):
    # Increment 3 (beta): Wu-Xing fusion vector map. Served from the canonical
    # frozen golden (generated from the live engine), with a fresh request_id
    # so the mock matches the real response shape.
    _simulate_latency()
    _maybe_fail()
    path = SNAPSHOTS_DIR / "fusion_vector_map_canonical.json"
    data = json.loads(path.read_text())
    data["request_id"] = x_request_id or str(uuid.uuid4())
    return Response(
        content=json.dumps(data),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


# ---------------------------------------------------------------------------
# Error simulation endpoints
# ---------------------------------------------------------------------------


@app.post("/calculate/bazi/dayun")
@app.post("/v1/calculate/bazi/dayun")
def calculate_dayun(request: Request, x_request_id: str | None = Header(None)):
    _simulate_latency()
    _maybe_fail()
    # No snapshot for /calculate/bazi/dayun — return a minimal payload that
    # conforms to schemas/calculate/bazi/dayun.response.schema.json so the
    # mock-contract sanity check can pass.
    body = {
        "dayun": {
            "label": "Da Yun",
            "display_label_de": "Dekaden-Säule",
            "direction": "forward",
            "direction_method": "explicit",
            "start": {
                "anchor_term": {
                    "name": "Xiao Shu",
                    "direction": "next",
                    "local_dt": "1987-07-08T03:00:00+02:00",
                },
                "delta": {"days": 3, "hours": 5, "minutes": 30},
                "start_age": {"years": 1, "months": 0, "days": 22, "decimal_years": 1.06},
                "method": "three_days_one_year",
            },
            "cycles": [
                {
                    "sequence": 1,
                    "age_start": 1.06,
                    "age_end": 11.06,
                    "date_start": "1988-07-26",
                    "date_end": "1998-07-23",
                    "pillar": {
                        "stem": "Gui",
                        "branch": "Wei",
                        "element": "water",
                        "polarity": "yin",
                        "index60": 19,
                    },
                    "relation_to_day_master": {
                        "day_master": "Wu",
                        "ten_god": "Zheng Cai",
                        "element_relation": "controlled_by_day_master",
                        "label_de": "Direktes Vermögen",
                    },
                    "is_current": False,
                }
            ],
            "current": None,
        },
        "provenance": {
            "source": "FuFirE",
            "ruleset_id": "dayun_v1",
            "solar_terms_source": "mock_server",
            "computed_at": "2026-05-22T00:00:00Z",
        },
        "precision": {
            "birth_time_known": True,
            "direction_basis": "explicit",
            "provisional_fields": [],
        },
        "warnings": [],
    }
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.post("/calculate/bazi/natal")
@app.post("/v1/calculate/bazi/natal")
def calculate_natal(request: Request, x_request_id: str | None = Header(None)):
    _simulate_latency()
    _maybe_fail()
    # No snapshot for /calculate/bazi/natal — return a minimal payload that
    # conforms to schemas/calculate/bazi/natal.response.schema.json (the
    # tests/test_natal_endpoint.py reference chart, 2016-08-15T16:00
    # Europe/Berlin: Bing Shen / Bing Shen / Ji Si / Ren Shen, day master Ji)
    # so the mock-contract sanity check can pass.
    ten_gods = {
        "DirectRes": ("Zheng Yin", "produces_day_master", "Direkte Quelle"),
        "DirectWealth": ("Zheng Cai", "controlled_by_day_master", "Direktes Vermögen"),
        "HurtingOfficer": ("Shang Guan", "produced_by_day_master", "Disruptive Ausgabe"),
        "RobWealth": ("Jie Cai", "same_element", "Rivale"),
    }

    def god(name: str) -> dict[str, str]:
        pinyin, relation, label_de = ten_gods[name]
        return {"name": name, "pinyin": pinyin, "element_relation": relation, "label_de": label_de}

    def hidden(stem: str, stem_cn: str, element: str, qi: str, weight: float, god_name: str) -> dict[str, Any]:
        return {"stem": stem, "stem_cn": stem_cn, "element": element, "qi": qi, "weight": weight, "ten_god": god(god_name)}

    shen_hidden = [
        hidden("Geng", "庚", "metal", "principal", 1.0, "HurtingOfficer"),
        hidden("Ren", "壬", "water", "central", 0.5, "DirectWealth"),
        hidden("Wu", "戊", "earth", "residual", 0.3, "RobWealth"),
    ]
    si_hidden = [
        hidden("Bing", "丙", "fire", "principal", 1.0, "DirectRes"),
        hidden("Geng", "庚", "metal", "central", 0.5, "HurtingOfficer"),
        hidden("Wu", "戊", "earth", "residual", 0.3, "RobWealth"),
    ]

    def pillar(stem: str, stem_cn: str, stem_element: str, polarity: str, branch: str,
               branch_cn: str, branch_element: str, god_name: str | None,
               hidden_stems: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "stem": stem, "branch": branch, "stem_cn": stem_cn, "branch_cn": branch_cn,
            "stem_element": stem_element, "branch_element": branch_element,
            "polarity": polarity,
            "ten_god": god(god_name) if god_name else None,
            "hidden_stems": hidden_stems,
        }

    body = {
        "pillars": {
            "year": pillar("Bing", "丙", "fire", "yang", "Shen", "申", "metal", "DirectRes", shen_hidden),
            "month": pillar("Bing", "丙", "fire", "yang", "Shen", "申", "metal", "DirectRes", shen_hidden),
            "day": pillar("Ji", "己", "earth", "yin", "Si", "巳", "fire", None, si_hidden),
            "hour": pillar("Ren", "壬", "water", "yang", "Shen", "申", "metal", "DirectWealth", shen_hidden),
        },
        "day_master": {"stem": "Ji", "stem_cn": "己", "element": "earth", "polarity": "yin"},
        "month_command": {
            "branch": "Shen", "branch_cn": "申", "branch_index": 8,
            "principal_qi_stem": "Geng", "principal_qi_stem_cn": "庚",
            "element": "metal", "source_status": "CALCULATED",
        },
        "provenance": {
            "source": "FuFirE",
            "ruleset_id": "standard_bazi_2026",
            "ruleset_version": "1.0.0",
            "computed_at": "2026-07-14T00:00:00Z",
        },
        "precision": {"birth_time_known": True, "provisional_fields": []},
        "warnings": [],
    }
    return Response(
        content=json.dumps(body),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.post("/calculate/tst")
@app.post("/v1/calculate/tst")
def calculate_tst(request: Request, x_request_id: str | None = Header(None)):
    _simulate_latency()
    _maybe_fail()
    # TST has no snapshot — return a minimal valid response
    return Response(
        content=json.dumps({
            "true_solar_time": "2024-02-10T14:22:17",
            "equation_of_time_minutes": -14.22,
            "longitude_correction_minutes": -2.38,
            "input": {"date": "2024-02-10T14:30:00", "lon": 13.405},
        }),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


@app.get("/transit/now")
@app.get("/v1/transit/now")
def transit_now(x_request_id: str | None = Header(None)):
    _simulate_latency()
    _maybe_fail()
    return Response(
        content=json.dumps({
            "datetime_utc": "2026-03-23T12:00:00Z",
            "bodies": {
                "Sun": {"longitude": 2.5, "sign": "Aries", "degree": 2.5},
                "Moon": {"longitude": 145.3, "sign": "Leo", "degree": 25.3},
                "Mercury": {"longitude": 350.1, "sign": "Pisces", "degree": 20.1},
                "Venus": {"longitude": 30.8, "sign": "Taurus", "degree": 0.8},
                "Mars": {"longitude": 95.4, "sign": "Cancer", "degree": 5.4},
                "Jupiter": {"longitude": 72.2, "sign": "Gemini", "degree": 12.2},
                "Saturn": {"longitude": 345.9, "sign": "Pisces", "degree": 15.9},
            },
            "mock": True,
        }),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


# ---------------------------------------------------------------------------
# Validation endpoint (mock)
# ---------------------------------------------------------------------------


@app.post("/validate")
@app.post("/v1/validate")
def validate(request: Request, x_request_id: str | None = Header(None)):
    _simulate_latency()
    _maybe_fail()
    return Response(
        content=json.dumps({
            "valid": True,
            "issues": [],
            "engine_version": "1.0.0-rc1-mock",
            "ruleset_id": "standard_bazi_2026",
            "mock": True,
        }),
        media_type="application/json",
        headers=_std_headers(x_request_id),
    )


# ---------------------------------------------------------------------------
# WuXing mapping (static)
# ---------------------------------------------------------------------------


@app.get("/info/wuxing-mapping")
@app.get("/v1/info/wuxing-mapping")
def wuxing_mapping():
    return {
        "elements": ["Wood", "Fire", "Earth", "Metal", "Water"],
        "stems": {
            "Jia": "Wood", "Yi": "Wood",
            "Bing": "Fire", "Ding": "Fire",
            "Wu": "Earth", "Ji": "Earth",
            "Geng": "Metal", "Xin": "Metal",
            "Ren": "Water", "Gui": "Water",
        },
        "mock": True,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="FuFirE Mock Server")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--scenario", default=os.environ.get("MOCK_SCENARIO", "default"))
    parser.add_argument("--latency", type=int, default=0, help="Simulated latency in ms")
    args = parser.parse_args()

    _SCENARIO = args.scenario
    _LATENCY_MS = args.latency

    import uvicorn
    print(f"FuFirE Mock Server starting on http://{args.host}:{args.port}")
    print(f"  Scenario: {_SCENARIO}")
    print(f"  Latency: {_LATENCY_MS}ms")
    print(f"  Snapshots: {SNAPSHOTS_DIR} ({len(list(SNAPSHOTS_DIR.glob('*.json')))} files)")
    print("  Control: POST /mock/scenario/{name}, POST /mock/latency/{ms}")
    uvicorn.run(app, host=args.host, port=args.port)
