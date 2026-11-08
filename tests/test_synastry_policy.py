"""Synastry policy data (spec 2026-11-08 §3, D1/D2/D8)."""
from __future__ import annotations

from bazi_engine.routers.shared import ZODIAC_SIGNS_DE
from bazi_engine.synastry.policy import (
    ANGLE_FACTORS,
    FACTOR_ORDER,
    PLANET_FACTORS,
    SIGN_LAYER_FACTORS,
    SIGN_RELATIONS,
    SYNASTRY_ASPECTS,
    SYNASTRY_ORB_POLICY_ID,
    ZODIAC_SIGNS,
    factor_weight,
)
from bazi_engine.wuxing.constants import western_body_weight


def test_orb_policy_matches_the_spec() -> None:
    assert SYNASTRY_ORB_POLICY_ID == "synastry-orbs-v1"
    assert SYNASTRY_ASPECTS == (
        ("conjunction", 0.0, 8.0),
        ("sextile", 60.0, 4.0),
        ("square", 90.0, 6.0),
        ("trine", 120.0, 6.0),
        ("opposition", 180.0, 8.0),
    )


def test_orb_windows_do_not_overlap() -> None:
    # One aspect per pair is guaranteed by construction, not by tie-breaking.
    windows = sorted((angle - orb, angle + orb) for _, angle, orb in SYNASTRY_ASPECTS)
    for (_, upper), (lower, _) in zip(windows, windows[1:]):
        assert upper < lower


def test_factor_sets() -> None:
    assert PLANET_FACTORS == (
        "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
    )
    assert ANGLE_FACTORS == ("Ascendant", "MC")
    assert FACTOR_ORDER == PLANET_FACTORS + ANGLE_FACTORS
    assert SIGN_LAYER_FACTORS == ("Sun", "Moon", "Mercury", "Venus", "Mars", "Ascendant")


def test_weights_follow_the_fusion_tiers() -> None:
    for factor in PLANET_FACTORS + ("Ascendant",):
        assert factor_weight(factor) == western_body_weight(factor)
    assert factor_weight("Sun") == (1, 1.0)
    assert factor_weight("Venus") == (2, 0.3)
    assert factor_weight("Saturn") == (3, 0.09)
    assert factor_weight("Pluto") == (4, 0.027)


def test_mc_is_tier_one_like_the_ascendant() -> None:
    # D2: the Fusion table would give MC the tier-4 fallback (0.027).
    assert western_body_weight("MC") == (4, 0.027)
    assert factor_weight("MC") == (1, 1.0)


def test_sign_names_match_the_names_the_api_already_emits() -> None:
    assert list(ZODIAC_SIGNS) == ZODIAC_SIGNS_DE


def test_sign_relations_are_indexed_by_sign_distance() -> None:
    assert SIGN_RELATIONS == (
        "same_sign", "semi_sextile", "sextile", "square", "trine", "quincunx", "opposition",
    )
