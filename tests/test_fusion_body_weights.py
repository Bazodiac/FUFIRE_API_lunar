"""2026-11-07: tier weights for the western Wu-Xing vector (body-tier-q0.3-v1).

Lights and ascendant 1, Mercury/Venus/Mars 0.3, Jupiter/Saturn 0.09, the rest
0.027; the lunar node counts once; retrograde motion adds nothing.
Derivation: docs/fusion/12_west_element_mapping.md.
Boundary claims are asserted on real HTTP responses (WS-A convention).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.wuxing.analysis import calculate_wuxing_vector_from_planets
from bazi_engine.wuxing.constants import (
    SIGN_ELEMENT,
    WEST_ELEMENT_TO_WUXING,
    WESTERN_BODY_TIER,
    WESTERN_EXCLUDED_BODIES,
    WESTERN_TIER_RATIO,
    WESTERN_TIER_WEIGHT,
    WESTERN_WEIGHTING_ID,
    WUXING_ORDER,
    western_body_weight,
)

client = TestClient(app)
BIRTH = {"date": "2016-08-15T16:00:00", "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405}


def _vec(bodies, **kw):
    return calculate_wuxing_vector_from_planets(bodies, **kw).to_list()


def test_tier_weights_fall_by_the_ratio():
    assert WESTERN_WEIGHTING_ID == "body-tier-q0.3-v1"
    for tier in (2, 3, 4):
        assert WESTERN_TIER_WEIGHT[tier] == pytest.approx(WESTERN_TIER_WEIGHT[tier - 1] * WESTERN_TIER_RATIO)
    assert WESTERN_TIER_WEIGHT[1] == 1.0


def test_tiers_keep_the_traditional_order():
    tier = WESTERN_BODY_TIER
    assert tier["Sun"] == tier["Moon"] == tier["Ascendant"] == 1
    assert tier["Mercury"] == tier["Venus"] == tier["Mars"] == 2
    assert tier["Jupiter"] == tier["Saturn"] == 3
    assert {tier[b] for b in ("Uranus", "Neptune", "Pluto", "Chiron", "Lilith", "NorthNode")} == {4}
    assert western_body_weight("SomethingNew") == (4, WESTERN_TIER_WEIGHT[4])


def test_the_lunar_node_counts_once():
    assert "TrueNorthNode" in WESTERN_EXCLUDED_BODIES
    mean_only = {"NorthNode": {"longitude": 300.0, "is_retrograde": True}}
    both = {**mean_only, "TrueNorthNode": {"longitude": 301.0, "is_retrograde": True}}
    assert _vec(both) == _vec(mean_only)


def test_retrograde_motion_adds_no_weight():
    direct = {"Saturn": {"longitude": 280.0, "is_retrograde": False}}
    retro = {"Saturn": {"longitude": 280.0, "is_retrograde": True}}
    assert _vec(direct) == _vec(retro)
    # The legacy option still exists for explicit callers.
    assert _vec(retro, use_retrograde_weight=True) == pytest.approx([1.3 * x for x in _vec(direct)])


def test_ascendant_counts_like_a_light():
    bodies = {"Sun": {"longitude": 10.0, "is_retrograde": False}}
    without = _vec(bodies)
    with_asc = _vec(bodies, ascendant=190.0)  # Libra → Luft
    added = [b - a for a, b in zip(without, with_asc)]
    luft = WEST_ELEMENT_TO_WUXING[SIGN_ELEMENT[6]]
    assert added == pytest.approx([luft[p] for p in WUXING_ORDER])


def test_sun_outweighs_pluto_in_the_same_sign():
    sun = _vec({"Sun": {"longitude": 40.0, "is_retrograde": False}})
    pluto = _vec({"Pluto": {"longitude": 40.0, "is_retrograde": False}})
    assert sum(sun) == pytest.approx(1.0)
    assert sum(pluto) == pytest.approx(0.027)


def test_fusion_ledger_shows_tiers_ascendant_and_single_node():
    r = client.post("/v1/calculate/fusion", json=BIRTH)
    assert r.status_code == 200, r.text
    western = r.json()["contribution_ledger"]["western"]
    names = [e["planet"] for e in western]
    assert "Ascendant" in names
    assert "TrueNorthNode" not in names
    assert names.count("NorthNode") == 1
    for entry in western:
        tier, weight = western_body_weight(entry["planet"])
        assert (entry["weight_tier"], entry["weight"]) == (tier, weight)
        assert WESTERN_WEIGHTING_ID in entry["rationale"]
