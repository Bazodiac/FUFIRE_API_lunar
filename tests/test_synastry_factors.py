"""Factor extraction from a western chart (spec §2)."""
from __future__ import annotations

import pytest

from bazi_engine.exc import CalculationError
from bazi_engine.synastry.factors import extract_factors
from bazi_engine.synastry.policy import ANGLE_FACTORS, PLANET_FACTORS
from tests.fixtures.synastry_charts import BASE_A, make_chart


def test_unknown_time_yields_the_ten_planets_only() -> None:
    factors = extract_factors(make_chart(BASE_A), birth_time_known=False)
    assert tuple(factors) == PLANET_FACTORS


def test_known_time_adds_ascendant_and_mc_last() -> None:
    factors = extract_factors(make_chart(BASE_A, asc=15.0, mc=280.0), birth_time_known=True)
    assert tuple(factors) == PLANET_FACTORS + ANGLE_FACTORS
    assert factors["Ascendant"] == 15.0
    assert factors["MC"] == 280.0
    assert factors["Sun"] == 10.0


def test_longitudes_are_normalised() -> None:
    factors = extract_factors(make_chart(BASE_A, asc=360.0, mc=-90.0), birth_time_known=True)
    assert factors["Ascendant"] == 0.0
    assert factors["MC"] == 270.0


def test_missing_planet_fails_visibly() -> None:
    chart = make_chart(BASE_A)
    chart["bodies"]["Pluto"] = {"error": "swe failure"}
    with pytest.raises(CalculationError, match="Pluto"):
        extract_factors(chart, birth_time_known=True)
