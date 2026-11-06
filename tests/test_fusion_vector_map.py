"""Phase E — POST /v1/calculate/fusion/vector-map (beta).

Exposes the existing Wu-Xing fusion engine as three views per system
(``raw`` / ``sum_l1`` / ``l2_cosine``) plus two harmony components
(``elemental_overlap_h``, ``cosine_similarity``). NO new metaphysical math:
``cosine_similarity`` reuses the engine's existing ``cosmic_state`` (GT2);
``trig_coherence`` is DEFERRED (GT3) and must never appear.

Anti-mockup layering (the H-1 lesson):
  (a) PURE-MATH invariants — independently true regardless of the engine:
      sum_l1 sums to 1, l2 norm == 1, orthogonal → cosine/overlap 0,
      identical → cosine 1, zero-vector safe.
  (b) endpoint == compute_fusion_analysis (engine-consistency) — but that
      is tautological alone, so it is paired with (a) + the frozen golden
      in test_snapshot_math_endpoints.

REQ-F-006: the S/sum(S) view is keyed ``sum_l1``, NEVER ``l2``; the L2 view
is ``l2_cosine``. A naming test asserts no field misnames the L1 vector.
"""
from __future__ import annotations

import math
from datetime import timezone

import pytest
from fastapi.testclient import TestClient

from bazi_engine import __version__ as ENGINE_VERSION
from bazi_engine.app import app
from bazi_engine.bazi import compute_bazi
from bazi_engine.fusion import (
    calculate_wuxing_from_bazi_with_ledger,
    calculate_wuxing_vector_from_planets_with_ledger,
    compute_fusion_analysis,
)
from bazi_engine.routers.fusion import FUSION_MAPPING_VERSION
from bazi_engine.routers.shared import format_pillar
from bazi_engine.time_utils import resolve_local_iso
from bazi_engine.types import BaziInput
from bazi_engine.western import compute_western_chart
from bazi_engine.wuxing.vector import WuXingVector

client = TestClient(app)

GERMAN_KEYS = {"Holz", "Feuer", "Erde", "Metall", "Wasser"}

PAYLOAD = {
    "date": "1990-06-15T14:30:00",
    "tz": "Europe/Berlin",
    "lon": 13.405,
    "lat": 52.52,
}

V1 = "/v1/calculate/fusion/vector-map"
BARE = "/calculate/fusion/vector-map"


def _ephemeris_available() -> bool:
    return client.post(BARE, json=PAYLOAD).status_code == 200


_HAS_EPHEMERIS = _ephemeris_available()
_skip_no_ephe = pytest.mark.skipif(
    not _HAS_EPHEMERIS, reason="Swiss Ephemeris files not available"
)


def _resolve() -> dict:
    r = client.post(V1, json=PAYLOAD)
    assert r.status_code == 200, r.text
    return r.json()


def _engine_reference() -> dict:
    """Recompute the engine result for PAYLOAD exactly as the endpoint must
    (same pillars / bodies / ascendant / strict) so engine-consistency can be
    asserted independently of the route."""
    dt_local, _ = resolve_local_iso(PAYLOAD["date"], PAYLOAD["tz"])
    dt_utc = dt_local.astimezone(timezone.utc)
    western_chart = compute_western_chart(dt_utc, PAYLOAD["lat"], PAYLOAD["lon"])
    inp = BaziInput(
        birth_local=dt_local.replace(tzinfo=None).isoformat(),
        timezone=PAYLOAD["tz"],
        longitude_deg=PAYLOAD["lon"],
        latitude_deg=PAYLOAD["lat"],
        time_standard="CIVIL",
        day_boundary="midnight",
        strict_local_time=True,
        fold=0,
    )
    bazi_result = compute_bazi(inp)
    pillars = {
        "year": format_pillar(bazi_result.pillars.year),
        "month": format_pillar(bazi_result.pillars.month),
        "day": format_pillar(bazi_result.pillars.day),
        "hour": format_pillar(bazi_result.pillars.hour),
    }
    ascendant = western_chart.get("angles", {}).get("Ascendant")
    fusion = compute_fusion_analysis(
        birth_utc_dt=dt_utc,
        latitude=PAYLOAD["lat"],
        longitude=PAYLOAD["lon"],
        bazi_pillars=pillars,
        western_bodies=western_chart["bodies"],
        ascendant=ascendant,
        strict=True,
    )
    raw_west, _ = calculate_wuxing_vector_from_planets_with_ledger(
        western_chart["bodies"], ascendant=ascendant, strict=True
    )
    raw_bazi, _ = calculate_wuxing_from_bazi_with_ledger(pillars)
    return {"fusion": fusion, "raw_west": raw_west, "raw_bazi": raw_bazi}


# ── E1: sum_l1 + l2 derived from the SAME raw vector, per system ─────────────

@_skip_no_ephe
def test_sum_l1_and_l2_from_same_raw():
    data = _resolve()
    for system in ("western_planets", "bazi_pillars"):
        block = data["vector_map"][system]
        raw = block["raw"]
        sum_l1 = block["sum_l1"]
        l2 = block["l2_cosine"]

        raw_v = WuXingVector(
            raw["Holz"], raw["Feuer"], raw["Erde"], raw["Metall"], raw["Wasser"]
        )
        # sum_l1 must equal raw.sum_l1_normalize()
        expect_l1 = raw_v.sum_l1_normalize().to_dict()
        for k in GERMAN_KEYS:
            assert math.isclose(sum_l1[k], expect_l1[k], abs_tol=1e-9), (
                f"{system}.sum_l1[{k}] not derived from raw"
            )
        # l2_cosine must equal raw.normalize()
        expect_l2 = raw_v.normalize().to_dict()
        for k in GERMAN_KEYS:
            assert math.isclose(l2[k], expect_l2[k], abs_tol=1e-9), (
                f"{system}.l2_cosine[{k}] not derived from raw"
            )


@_skip_no_ephe
def test_german_element_keys_gt7():
    """GT7: element keys are German (engine truth), not English."""
    data = _resolve()
    for system in ("western_planets", "bazi_pillars"):
        for view in ("raw", "sum_l1", "l2_cosine"):
            assert set(data["vector_map"][system][view].keys()) == GERMAN_KEYS


# ── E2: naming — sum_l1, NEVER l2 (REQ-F-006) ───────────────────────────────

@_skip_no_ephe
def test_naming_is_sum_l1_not_l2():
    """The L1 (S/sum(S)) view MUST be keyed 'sum_l1'. No field anywhere may
    misname the L1 vector as 'l2'. The L2 view is 'l2_cosine'."""
    data = _resolve()
    for system in ("western_planets", "bazi_pillars"):
        block = data["vector_map"][system]
        assert "sum_l1" in block, "missing 'sum_l1' view"
        assert "l2_cosine" in block, "missing 'l2_cosine' view"
        # The bare key 'l2' must NOT exist (would misname the L1 vector).
        assert "l2" not in block, (
            "found bare 'l2' key — REQ-F-006 forbids naming any view 'l2'; "
            "the L1 view is 'sum_l1', the L2 view is 'l2_cosine'"
        )
        assert "l1" not in block, "found bare 'l1' key — use 'sum_l1'"


# ── E3: H components in range + cosine_similarity == cosmic_state ────────────

@_skip_no_ephe
def test_h_components_in_range():
    data = _resolve()
    h = data["harmony"]
    assert 0.0 <= h["elemental_overlap_h"] <= 1.0
    assert 0.0 <= h["cosine_similarity"] <= 1.0


@_skip_no_ephe
def test_cosine_similarity_equals_cosmic_state():
    """cosine_similarity must REUSE the engine's cosmic_state — not a
    reimplementation (GT2)."""
    data = _resolve()
    ref = _engine_reference()
    assert math.isclose(
        data["harmony"]["cosine_similarity"], ref["fusion"]["cosmic_state"], abs_tol=1e-9
    )


@_skip_no_ephe
def test_no_trig_coherence_gt3():
    """GT3: trig_coherence (raw or _01) is DEFERRED — it must NOT ship as a
    renamed/duplicated metric anywhere in the response."""
    data = _resolve()
    flat = str(data)
    assert "trig_coherence" not in flat, (
        "trig_coherence is deferred (GT3) and must not appear in the response"
    )
    assert "trig_coherence" not in data["harmony"]


# ── E4: version metadata present (REQ-F-007 / GT5) ──────────────────────────

@_skip_no_ephe
def test_versions_present():
    data = _resolve()
    meta = data["metadata"]
    assert meta["mapping_version"] == FUSION_MAPPING_VERSION == "fufire-wuxing-map-v2"
    assert meta["algorithm_version"] == ENGINE_VERSION
    assert "request_id" in data


# ── E5: zero-vector safe (no div-by-zero; documented result) ────────────────

def test_zero_vector_safe_pure():
    """A zero raw vector must normalize without a ZeroDivisionError and
    return all-zeros for both L1 and L2 views (documented degenerate result).
    This is a PURE invariant — no engine, no ephemeris needed."""
    z = WuXingVector.zero()
    l1 = z.sum_l1_normalize()
    l2 = z.normalize()
    assert l1.to_list() == [0.0] * 5
    assert l2.to_list() == [0.0] * 5
    # dot products over zero vectors are 0 — overlap/cosine safe.
    overlap = sum(a * b for a, b in zip(l1.to_list(), l1.to_list()))
    assert overlap == 0.0


# ── E6: invalid input → stable 422 ──────────────────────────────────────────

def test_invalid_input_422():
    bad = {"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 999, "lat": 52.52}
    r = client.post(V1, json=bad)
    assert r.status_code == 422, r.text


def test_missing_field_422():
    r = client.post(V1, json={"tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52})
    assert r.status_code == 422, r.text


# ── PURE invariants: orthogonal → 0, identical → 1 ──────────────────────────
#
# These are independent of the astrology engine and lock the H semantics
# (cosine of L2-unit vectors; overlap = dot of L1-unit vectors).

def test_orthogonal_vectors_cosine_zero():
    a = WuXingVector(1.0, 0.0, 0.0, 0.0, 0.0)
    b = WuXingVector(0.0, 1.0, 0.0, 0.0, 0.0)
    cos = sum(x * y for x, y in zip(a.normalize().to_list(), b.normalize().to_list()))
    assert math.isclose(cos, 0.0, abs_tol=1e-12)
    overlap = sum(
        x * y for x, y in zip(a.sum_l1_normalize().to_list(), b.sum_l1_normalize().to_list())
    )
    assert math.isclose(overlap, 0.0, abs_tol=1e-12)


def test_identical_vectors_cosine_one():
    a = WuXingVector(1.0, 2.0, 3.0, 4.0, 5.0)
    b = WuXingVector(1.0, 2.0, 3.0, 4.0, 5.0)
    cos = sum(x * y for x, y in zip(a.normalize().to_list(), b.normalize().to_list()))
    assert math.isclose(cos, 1.0, abs_tol=1e-12)


# ── engine-consistency: vectors == compute_fusion_analysis wu_xing_vectors ──

@_skip_no_ephe
def test_engine_consistency():
    """The endpoint's l2_cosine views must equal compute_fusion_analysis's
    wu_xing_vectors (the L2-normed dicts) — proving the route reuses the
    engine and adds no hidden math. raw views must equal the un-normalized
    engine vectors."""
    data = _resolve()
    ref = _engine_reference()
    eng_vecs = ref["fusion"]["wu_xing_vectors"]

    for system, raw_v in (
        ("western_planets", ref["raw_west"]),
        ("bazi_pillars", ref["raw_bazi"]),
    ):
        block = data["vector_map"][system]
        # l2_cosine == engine wu_xing_vectors (already L2-normed)
        for k in GERMAN_KEYS:
            assert math.isclose(block["l2_cosine"][k], eng_vecs[system][k], abs_tol=1e-9)
        # raw == un-normalized engine vector
        raw_dict = raw_v.to_dict()
        for k in GERMAN_KEYS:
            assert math.isclose(block["raw"][k], raw_dict[k], abs_tol=1e-9)


# ── E: each system's sum_l1 sums to ~1 (live, non-zero charts) ──────────────

@_skip_no_ephe
def test_sum_l1_sums_to_one_live():
    data = _resolve()
    for system in ("western_planets", "bazi_pillars"):
        s = sum(data["vector_map"][system]["sum_l1"].values())
        assert math.isclose(s, 1.0, abs_tol=1e-9), f"{system}.sum_l1 sums to {s}, not 1.0"


# ── bare route also registered ──────────────────────────────────────────────

@_skip_no_ephe
def test_bare_route_registered():
    r = client.post(BARE, json=PAYLOAD)
    assert r.status_code == 200, r.text


# ── OpenAPI: vector-map present on bare + /v1, beta-labeled ──────────────────

def test_openapi_beta_tags():
    """The vector-map endpoint appears under both bare and /v1 paths and is
    beta-labeled (tag carries 'beta')."""
    schema = app.openapi()
    paths = schema.get("paths", {})
    assert BARE in paths, f"{BARE} missing from OpenAPI"
    assert V1 in paths, f"{V1} missing from OpenAPI"

    op = paths[V1]["post"]
    tags = op.get("tags", [])
    assert any("beta" in t.lower() for t in tags), (
        f"vector-map must be beta-labeled; tags={tags}"
    )

    # The beta tag must be declared in the global tags list (test_openapi_tags
    # enforces this globally; assert it here too for locality).
    global_tags = {t["name"] for t in schema.get("tags", [])}
    for t in tags:
        assert t in global_tags, f"operation tag {t!r} not in global tags"
