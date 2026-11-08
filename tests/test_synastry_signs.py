"""Sign layer (spec §5, D8)."""
from __future__ import annotations

import pytest

from bazi_engine.synastry.signs import element_relation, sign_entry, sign_layer, sign_relation


@pytest.mark.parametrize(
    "lon_b, relation",
    [
        (5.0, "same_sign"),
        (35.0, "semi_sextile"),
        (65.0, "sextile"),
        (95.0, "square"),
        (125.0, "trine"),
        (155.0, "quincunx"),
        (185.0, "opposition"),
    ],
)
def test_all_seven_sign_distance_classes(lon_b: float, relation: str) -> None:
    a = sign_entry("Sun", 5.0)
    b = sign_entry("Moon", lon_b)
    assert sign_relation(a["sign_index"], b["sign_index"]) == relation


def test_sign_distance_is_the_shorter_way_round() -> None:
    assert sign_relation(11, 0) == "semi_sextile"
    assert sign_relation(0, 7) == "quincunx"
    assert sign_relation(0, 10) == "sextile"
    assert sign_relation(2, 9) == sign_relation(9, 2)


def test_sign_entry() -> None:
    assert sign_entry("Venus", 245.5) == {
        "factor": "Venus", "sign": "Schütze", "sign_index": 8, "west_element": "Feuer", "degree": 5.5,
    }
    assert sign_entry("Sun", 0.0)["sign"] == "Widder"
    assert sign_entry("Sun", 359.5)["sign"] == "Fische"


@pytest.mark.parametrize(
    "a, b, relation",
    [
        ("Feuer", "Feuer", "same"),
        ("Wasser", "Wasser", "same"),
        ("Feuer", "Luft", "complementary"),
        ("Luft", "Feuer", "complementary"),
        ("Erde", "Wasser", "complementary"),
        ("Wasser", "Erde", "complementary"),
        ("Feuer", "Wasser", "other"),
        ("Erde", "Luft", "other"),
        ("Feuer", "Erde", "other"),
        ("Luft", "Wasser", "other"),
    ],
)
def test_element_relations(a: str, b: str, relation: str) -> None:
    assert element_relation(a, b) == relation


def test_sign_layer_shape_without_an_ascendant_for_b() -> None:
    a = {"Sun": 5.0, "Moon": 40.0, "Mercury": 70.0, "Venus": 100.0, "Mars": 130.0, "Ascendant": 160.0,
         "Jupiter": 1.0, "MC": 2.0}
    b = {"Sun": 185.0, "Moon": 215.0, "Mercury": 250.0, "Venus": 280.0, "Mars": 310.0, "Jupiter": 3.0}
    layer = sign_layer(a, b)
    assert [e["factor"] for e in layer["factors"]["person_a"]] == ["Sun", "Moon", "Mercury", "Venus", "Mars", "Ascendant"]
    assert [e["factor"] for e in layer["factors"]["person_b"]] == ["Sun", "Moon", "Mercury", "Venus", "Mars"]
    assert len(layer["pairs"]) == 30
    assert layer["pairs"][0] == {
        "factor_a": "Sun", "factor_b": "Sun", "sign_relation": "opposition", "element_relation": "complementary",
    }
    assert all(p["factor_b"] != "Ascendant" for p in layer["pairs"])
