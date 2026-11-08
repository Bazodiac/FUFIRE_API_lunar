"""Wu-Xing translation of the sign layer (spec §6, D3)."""
from __future__ import annotations

import pytest

from bazi_engine.provenance import WUXING_PARAMETER_SET
from bazi_engine.synastry.signs import sign_entry
from bazi_engine.synastry.wuxing_layer import factor_vector, person_wuxing, wuxing_pair_factors
from bazi_engine.wuxing import calculate_wuxing_vector_from_planets_with_ledger
from bazi_engine.wuxing.constants import SIGN_ELEMENT, WESTERN_MAPPING_ID, WUXING_ORDER


@pytest.mark.parametrize("element", ["Feuer", "Erde", "Luft", "Wasser"])
def test_each_factor_vector_sums_to_one(element: str) -> None:
    assert sum(factor_vector(element)) == pytest.approx(1.0, abs=1e-12)


def test_vector_is_in_wuxing_order() -> None:
    assert WUXING_ORDER == ["Holz", "Feuer", "Erde", "Metall", "Wasser"]
    assert factor_vector("Feuer") == [0.452, 0.548, 0.0, 0.0, 0.0]
    assert factor_vector("Wasser") == [0.0, 0.0, 0.306, 0.101, 0.593]


@pytest.mark.parametrize("lon", [5.0, 35.0, 65.0, 95.0])
def test_same_matrix_as_the_fusion_vector(lon: float) -> None:
    # A lone Sun (tier 1, weight 1.0) in the Fusion ledger distributes exactly
    # one matrix row; the synastry factor vector must be that row.
    _, ledger = calculate_wuxing_vector_from_planets_with_ledger({"Sun": {"longitude": lon}})
    expected = [ledger[0]["distribution"].get(p, 0.0) for p in WUXING_ORDER]
    assert factor_vector(SIGN_ELEMENT[int(lon // 30)]) == pytest.approx(expected, abs=1e-9)


def test_person_vector_is_the_tier_weighted_mean() -> None:
    entries = [sign_entry("Sun", 5.0), sign_entry("Mars", 35.0)]  # Feuer w=1.0, Erde w=0.3
    out = person_wuxing(entries)
    fire, earth = factor_vector("Feuer"), factor_vector("Erde")
    expected = [round((1.0 * f + 0.3 * e) / 1.3, 6) for f, e in zip(fire, earth)]
    assert out["vector"] == expected
    assert out["factors"] == [
        {"factor": "Sun", "west_element": "Feuer", "weight": 1.0, "vector": fire, "sign_certain": None},
        {"factor": "Mars", "west_element": "Erde", "weight": 0.3, "vector": earth, "sign_certain": None},
    ]


def test_person_vector_sums_to_one() -> None:
    entries = [sign_entry(f, lon) for f, lon in
               [("Sun", 5.0), ("Moon", 100.0), ("Mercury", 200.0), ("Venus", 300.0), ("Mars", 50.0), ("Ascendant", 170.0)]]
    assert sum(person_wuxing(entries)["vector"]) == pytest.approx(1.0, abs=1e-5)


def test_mapping_version_is_the_one_fusion_attests() -> None:
    out = wuxing_pair_factors([sign_entry("Sun", 5.0)], [sign_entry("Sun", 95.0)])
    assert out["mapping_version"] == "sign-element-consensus-v1"
    assert out["mapping_version"] == WESTERN_MAPPING_ID
    assert out["mapping_version"] == WUXING_PARAMETER_SET["western_mapping_id"]
    assert out["order"] == WUXING_ORDER
    assert set(out) == {"order", "person_a", "person_b", "mapping_version"}  # no comparison number
