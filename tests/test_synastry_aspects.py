"""Synastry cross aspects (spec §3, D1, D7)."""
from __future__ import annotations

import pytest

from bazi_engine.synastry.aspects import angular_separation, classify_aspect, cross_aspects

# (aspect, separation exactly at the orb limit, separation just beyond it)
BOUNDARIES = [
    ("conjunction", 8.0, 8.01),
    ("sextile", 64.0, 64.01),
    ("sextile", 56.0, 55.99),
    ("square", 96.0, 96.01),
    ("square", 84.0, 83.99),
    ("trine", 126.0, 126.01),
    ("trine", 114.0, 113.99),
    ("opposition", 172.0, 171.99),
]


@pytest.mark.parametrize("aspect, at_limit, beyond", BOUNDARIES)
def test_orb_limit_is_inclusive_and_just_beyond_is_out(aspect: str, at_limit: float, beyond: float) -> None:
    hit = classify_aspect(0.0, at_limit)
    assert hit is not None
    assert hit.type == aspect
    assert classify_aspect(0.0, beyond) is None


def test_every_aspect_type_has_a_boundary_fixture() -> None:
    assert {b[0] for b in BOUNDARIES} == {"conjunction", "sextile", "square", "trine", "opposition"}


def test_separation_wraps_over_the_aries_point() -> None:
    assert angular_separation(355.0, 3.0) == 8.0
    hit = classify_aspect(355.0, 3.0)
    assert hit is not None and hit.type == "conjunction" and hit.orb == 8.0


def test_direction_does_not_change_the_hit() -> None:
    assert classify_aspect(10.0, 130.5) == classify_aspect(130.5, 10.0)


@pytest.mark.parametrize("lon_to, exact", [(4.0, True), (4.01, False), (62.0, True), (62.01, False)])
def test_exact_means_orb_within_half_the_limit(lon_to: float, exact: bool) -> None:
    rows = cross_aspects({"Sun": 0.0}, {"Moon": lon_to}, from_person="person_a", to_person="person_b")
    assert len(rows) == 1
    assert rows[0]["exact"] is exact


def test_row_shape_and_weights() -> None:
    rows = cross_aspects(
        {"Sun": 0.0},
        {"Moon": 8.0, "Venus": 8.01, "Mars": 180.0, "Pluto": 120.0},
        from_person="person_a",
        to_person="person_b",
    )
    assert rows == [
        {
            "from_person": "person_a", "from_factor": "Sun", "to_person": "person_b", "to_factor": "Moon",
            "type": "conjunction", "exact_angle": 0.0, "orb": 8.0, "exact": False,
            "from_weight": 1.0, "to_weight": 1.0, "weight": 1.0,
        },
        {
            "from_person": "person_a", "from_factor": "Sun", "to_person": "person_b", "to_factor": "Mars",
            "type": "opposition", "exact_angle": 180.0, "orb": 0.0, "exact": True,
            "from_weight": 1.0, "to_weight": 0.3, "weight": 0.3,
        },
        {
            "from_person": "person_a", "from_factor": "Sun", "to_person": "person_b", "to_factor": "Pluto",
            "type": "trine", "exact_angle": 120.0, "orb": 0.0, "exact": True,
            "from_weight": 1.0, "to_weight": 0.027, "weight": 0.027,
        },
    ]


def test_full_cross_matrix_not_only_i_lt_j() -> None:
    rows = cross_aspects(
        {"Sun": 0.0, "Moon": 0.0}, {"Sun": 0.0, "Moon": 0.0}, from_person="person_a", to_person="person_b",
    )
    assert [(r["from_factor"], r["to_factor"]) for r in rows] == [
        ("Sun", "Sun"), ("Sun", "Moon"), ("Moon", "Sun"), ("Moon", "Moon"),
    ]


def test_angles_take_the_same_orbs_and_mc_weighs_one() -> None:
    rows = cross_aspects({"Venus": 0.0}, {"Ascendant": 8.0, "MC": 64.0}, from_person="person_a", to_person="person_b")
    assert [(r["to_factor"], r["type"], r["weight"]) for r in rows] == [
        ("Ascendant", "conjunction", 0.3), ("MC", "sextile", 0.3),
    ]


def test_tier_products_are_rounded_free_of_float_noise() -> None:
    rows = cross_aspects({"Venus": 0.0}, {"Saturn": 0.0}, from_person="person_a", to_person="person_b")
    assert rows[0]["weight"] == 0.027  # 0.3 * 0.09 = 0.026999999999999996 unrounded
