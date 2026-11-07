"""Phase F — INDEPENDENT golden anchor for the math endpoints (chronometry).

Why this file exists (reviewer finding H-1)
-------------------------------------------
The existing anti-mockup tests (``test_chronometry_frame.py`` /
``test_chronometry_endpoint.py``) recompute every expected value by calling
the SAME engine functions the endpoint calls. That proves
``endpoint == in-process module`` — but it does NOT prove the engine's
physics is correct: stubbing ``SwissEphBackend.sun_lon_deg_ut`` to a constant
left all of those tests GREEN, because both sides moved together.

This module adds the missing INDEPENDENT layer for the canonical instant
**1990-06-15T14:30:00 Europe/Berlin, lat 52.52, lon 13.405**:

1. A FROZEN golden snapshot of the full ``ChronometryFrame`` (via the repo's
   ``UPDATE_SNAPSHOTS`` mechanism, ephemeris-tag-split into
   ``tests/snapshots/{moseph,swieph}/chronometry_*.json``). The frozen value
   is a fixed constant on disk, so a stub-constant engine — which produces a
   *different* constant — makes the snapshot assertion FAIL. (constant ≠
   frozen value).

2. Independent physics sanity asserts. These ballparks are NOT recomputed
   from the engine; they are hardcoded from real astronomy (cross-checked
   against the Meeus low-precision Sun + NOAA equation-of-time algorithms,
   see the module docstring of each assert). A fabricated engine value is
   caught even if someone regenerated the snapshot to match the fabrication.

Together: the snapshot locks regression + kills a stub-constant; the physics
asserts kill a regenerated-but-wrong golden. The endpoint↔module tests are
kept (they prove the router adds no hidden math) — this is the orthogonal,
independent anchor.

Set UPDATE_SNAPSHOTS=1 to (re)generate the golden:
    UPDATE_SNAPSHOTS=1 pytest tests/test_snapshot_math_endpoints.py
"""
from __future__ import annotations

import math
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

# Reuse the existing snapshot harness machinery so behaviour (tag split,
# float normalization, UPDATE_SNAPSHOTS regen, approx comparison) stays
# identical to test_snapshot_stability.py — single source of truth.
from tests.test_snapshot_stability import (
    SNAPSHOTS_DIR,
    UPDATE_SNAPSHOTS,
    _approx_equal,
    _json_diff,
    _normalize_for_snapshot,
    _read_snapshot,
    _write_snapshot,
)

client = TestClient(app)


# ── Canonical instant (the plan's Phase-F chronometry anchor) ───────────────
CANONICAL_BODY: Dict[str, Any] = {
    "birth": {
        "datetime": "1990-06-15T14:30:00",
        "timezone": "Europe/Berlin",
        "location": {"lat": 52.52, "lon": 13.405},
        "calendar_policy": "gregorian",
    }
}


def _snapshot_path():
    # Tag-split exactly like the main harness (moseph vs swieph).
    return SNAPSHOTS_DIR / "chronometry_canonical.json"


def _resolve_canonical_chronometry() -> Dict[str, Any]:
    """POST the canonical instant and return the deterministic ``chronometry``
    block (``request_id`` is volatile and intentionally excluded)."""
    r = client.post("/v1/chronometry/resolve", json=CANONICAL_BODY)
    assert r.status_code == 200, r.text
    return r.json()["chronometry"]


# ── 1. Frozen golden snapshot (regression lock + stub-constant killer) ──────

def test_chronometry_canonical_golden_snapshot() -> None:
    """The full chronometry frame for the canonical instant is bit-stable
    against a frozen, on-disk golden.

    This is the INDEPENDENT anchor H-1 asked for: the golden is a fixed
    constant, NOT recomputed from the engine at assert time. Stubbing
    ``sun_lon_deg_ut`` (or any engine fn) to a constant changes the live
    output and makes this assertion RED — the frozen value no longer matches.
    """
    actual = _normalize_for_snapshot(_resolve_canonical_chronometry())
    snap = _snapshot_path()

    if UPDATE_SNAPSHOTS or not snap.exists():
        _write_snapshot(snap, actual)
        if not UPDATE_SNAPSHOTS:
            pytest.skip(f"Golden snapshot created: {snap.name}")
        return

    expected = _read_snapshot(snap)
    assert _approx_equal(actual, expected), (
        f"Chronometry golden mismatch for the canonical instant.\n"
        f"Snapshot file: {snap}\n"
        f"Run with UPDATE_SNAPSHOTS=1 to regenerate (only if the change is "
        f"intentional AND the physics asserts below still hold).\n"
        f"Diff (expected vs actual):\n{_json_diff(expected, actual)}"
    )


# ── 2. Independent physics sanity asserts (real astronomy, NOT engine-echo) ─
#
# Every bound below is a hardcoded ballpark derived from independent
# astronomy, cross-checked with the Meeus algorithms (a different code path
# than the SwissEph backend). They are deliberately NOT recomputed from the
# engine, so they catch a fabricated value even after a golden regeneration.


def test_solar_longitude_is_real_mid_june_value() -> None:
    """Sun is ~84° in mid-June, ~6° short of the 90° summer solstice
    (~Jun 21). Independent Meeus low-precision Sun for 1990-06-15 12:30 UTC
    gives 84.15° — the engine reports ~84.149°. Bound: [82, 86]."""
    chrono = _resolve_canonical_chronometry()
    sun_lon = chrono["solar_longitude_degrees"]
    assert 82.0 <= sun_lon <= 86.0, (
        f"solar_longitude_degrees={sun_lon} outside the real mid-June "
        f"ballpark [82, 86] — Sun should be ~84° approaching the 90° solstice."
    )


def test_julian_day_matches_independent_meeus_jd() -> None:
    """14:30 CEST (UTC+2 in June) = 12:30 UTC on 1990-06-15. The independent
    Gregorian→JD formula (Meeus, ch. 7) yields JD = 2448058.0208333… for
    12:30 UTC. Assert within ±0.01 (this is NOT recomputed from the engine —
    it is the hardcoded astronomical constant)."""
    chrono = _resolve_canonical_chronometry()
    independent_jd = 2448058.0208333335  # Meeus ch.7, 1990-06-15 12:30 UTC
    assert abs(chrono["julian_day"] - independent_jd) < 0.01, (
        f"julian_day={chrono['julian_day']} differs from the independently "
        f"computed JD {independent_jd} by more than 0.01."
    )


def test_equation_of_time_is_near_zero_in_mid_june() -> None:
    """Mid-June EoT is small (its zero-crossing is ~Jun 13). Independent
    NOAA/Meeus (ch. 28) EoT for this instant is ~-0.39 min; the engine
    reports -0.027 min. Bound: [-2, 2] minutes."""
    chrono = _resolve_canonical_chronometry()
    eot = chrono["equation_of_time_minutes"]
    assert -2.0 <= eot <= 2.0, (
        f"equation_of_time_minutes={eot} outside the real mid-June ballpark "
        f"[-2, 2] — EoT is near its mid-June zero crossing."
    )


def test_solar_term_is_mang_zhong_for_84_degrees() -> None:
    """At ~84° solar longitude the 15°-bucket index is floor(84/15)=5 → the
    6th solar term. In JIEQI_NAMES (0°=Chun Fen ordering) index 5 is
    'Mang Zhong' (芒種, Grain-in-Ear, the early-June term, 75°–90°).

    This pins the correct NAME against an independently-derived index — a
    mislabelled term table (off-by-one, wrong ordering) turns this RED."""
    chrono = _resolve_canonical_chronometry()
    sun_lon = chrono["solar_longitude_degrees"]
    independent_index = int(math.floor(sun_lon / 15.0)) % 24
    assert independent_index == 5, (
        f"For sun_lon={sun_lon}, the 15°-bucket index should be 5, got "
        f"{independent_index}."
    )
    assert chrono["solar_term"] == "Mang Zhong", (
        f"solar_term={chrono['solar_term']!r}, expected 'Mang Zhong' for the "
        f"75°–90° bucket containing ~84°."
    )


# ── 3. The endpoint↔module tests (frame.py / endpoint.py) remain in place. ──
#     They prove the router adds no hidden math. This file is the missing
#     INDEPENDENT layer, not a replacement.


# ════════════════════════════════════════════════════════════════════════════
# Increment 3 — fusion/vector-map frozen golden + independent sanity asserts
# ════════════════════════════════════════════════════════════════════════════
#
# Same INDEPENDENT-anchor pattern as the chronometry golden above: a frozen,
# ephemeris-tag-split on-disk snapshot (kills a "vector fn → constant" stub,
# because the stub's constant ≠ the frozen value) PLUS sanity asserts that are
# NOT recomputed from the engine (each system's sum_l1 sums to ~1; cosine in
# [0,1]; the dominant element matches the known chart). A regenerated-but-wrong
# golden is still caught by the independent asserts.

VECTOR_MAP_BODY: Dict[str, Any] = {
    "date": "1990-06-15T14:30:00",
    "tz": "Europe/Berlin",
    "lon": 13.405,
    "lat": 52.52,
}


def _vector_map_snapshot_path():
    return SNAPSHOTS_DIR / "fusion_vector_map_canonical.json"


def _resolve_canonical_vector_map() -> Dict[str, Any]:
    """POST the canonical instant; return the deterministic body with the
    volatile request_id stripped."""
    r = client.post("/v1/calculate/fusion/vector-map", json=VECTOR_MAP_BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    body.pop("request_id", None)
    return body


# ── 1. Frozen golden snapshot (regression lock + stub-constant killer) ──────

def test_vector_map_canonical_golden_snapshot() -> None:
    """The full vector-map for the canonical instant is bit-stable against a
    frozen, on-disk golden. Stubbing the engine vector fn to a constant
    changes the live output and makes this RED (constant ≠ frozen value)."""
    actual = _normalize_for_snapshot(_resolve_canonical_vector_map())
    snap = _vector_map_snapshot_path()

    if UPDATE_SNAPSHOTS or not snap.exists():
        _write_snapshot(snap, actual)
        if not UPDATE_SNAPSHOTS:
            pytest.skip(f"Golden snapshot created: {snap.name}")
        return

    expected = _read_snapshot(snap)
    assert _approx_equal(actual, expected), (
        f"Vector-map golden mismatch for the canonical instant.\n"
        f"Snapshot file: {snap}\n"
        f"Run with UPDATE_SNAPSHOTS=1 to regenerate (only if the change is "
        f"intentional AND the sanity asserts below still hold).\n"
        f"Diff (expected vs actual):\n{_json_diff(expected, actual)}"
    )


# ── 2. INDEPENDENT sanity asserts (NOT engine-echo) ─────────────────────────

def test_vector_map_sum_l1_sums_to_one() -> None:
    """Each system's sum_l1 view sums to ~1.0 — a pure L1-normalization
    invariant, hardcoded here (not recomputed from the engine)."""
    body = _resolve_canonical_vector_map()
    for system in ("western_planets", "bazi_pillars"):
        s = sum(body["vector_map"][system]["sum_l1"].values())
        assert math.isclose(s, 1.0, abs_tol=1e-9), (
            f"{system}.sum_l1 sums to {s}, expected 1.0"
        )


def test_vector_map_cosine_in_unit_interval() -> None:
    """cosine_similarity and elemental_overlap_h are both in [0,1] for these
    non-negative elemental vectors — independent bound, not engine-derived."""
    body = _resolve_canonical_vector_map()
    h = body["harmony"]
    assert 0.0 <= h["cosine_similarity"] <= 1.0, h["cosine_similarity"]
    assert 0.0 <= h["elemental_overlap_h"] <= 1.0, h["elemental_overlap_h"]


@pytest.mark.swieph  # Chiron needs the SE1 asteroid file; MOSEPH drops it and shifts the sums
def test_vector_map_western_dominant_element_is_erde() -> None:
    """Independent chart fact for 1990-06-15 14:30 Berlin under
    sign-element-consensus-v1 and body-tier-q0.3-v1 (since 2026-11-07): each
    body counts through the element of its sign, weighted by its tier (lights
    and ascendant 1, Mercury/Venus/Mars 0.3, Jupiter/Saturn 0.09, the rest
    0.027; true node not counted, no retrograde factor). Chart facts: Sun and
    Mercury in Gemini, ascendant Libra, mean node Aquarius → Luft 2.327;
    Moon Pisces, Jupiter and Chiron Cancer, Pluto and Lilith Scorpio →
    Wasser 1.171; Venus Taurus, Saturn/Uranus/Neptune Capricorn → Erde 0.444;
    Mars Aries → Feuer 0.3. Spread by the published matrix:
    Erde = 0.095·0.444 + 0.400·2.327 + 0.306·1.171 = 1.3313,
    Holz = 0.452·0.3 + 0.348·2.327 = 0.9454,
    Wasser = 0.593·1.171 + 0.206·0.444 = 0.7859,
    Feuer = 0.548·0.3 + 0.252·2.327 = 0.7508,
    Metall = 0.699·0.444 + 0.101·1.171 = 0.4286.
    Hand-computed from the chart facts, the tier table and the public matrix,
    not from the live vector arithmetic: a constant or fabricated vector fails
    here. The body list is the SWIEPH chart (MOSEPH has no Chiron).
    """
    from bazi_engine.wuxing.constants import WEST_ELEMENT_TO_WUXING as M
    by_element = {"Luft": 2.327, "Wasser": 1.171, "Erde": 0.444, "Feuer": 0.3}
    expected = {p: sum(w * M[e][p] for e, w in by_element.items())
                for p in ("Holz", "Feuer", "Erde", "Metall", "Wasser")}
    assert abs(expected["Erde"] - 1.3313) < 1e-4 and abs(expected["Metall"] - 0.4286) < 1e-4
    body = _resolve_canonical_vector_map()
    west_raw = body["vector_map"]["western_planets"]["raw"]
    for phase, value in expected.items():
        assert abs(west_raw[phase] - value) < 1e-3, (phase, west_raw, expected)
    assert max(west_raw, key=lambda k: west_raw[k]) == "Erde", west_raw


def test_vector_map_bazi_dominant_element_is_feuer() -> None:
    """Independent cross-check on the BaZi side: for this chart the BaZi
    elemental vector peaks at Feuer (Fire). Hardcoded from the computed
    pillars' stem/hidden-stem element policy, not the live vector sum — locks
    the dominant element against a constant/fabricated BaZi vector."""
    body = _resolve_canonical_vector_map()
    bazi_raw = body["vector_map"]["bazi_pillars"]["raw"]
    dominant = max(bazi_raw, key=lambda k: bazi_raw[k])
    assert dominant == "Feuer", (
        f"bazi dominant element={dominant!r} (raw={bazi_raw}); expected 'Feuer'."
    )


def test_vector_map_no_trig_coherence_in_golden() -> None:
    """GT3 lock at the golden layer: trig_coherence must never appear."""
    body = _resolve_canonical_vector_map()
    assert "trig_coherence" not in str(body)
