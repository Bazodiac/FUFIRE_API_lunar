"""House overlays (spec §4, D6)."""
from __future__ import annotations

import pytest

from bazi_engine.exc import CalculationError
from bazi_engine.synastry.houses import house_of, house_overlays
from bazi_engine.synastry.policy import PLANET_FACTORS
from tests.fixtures.synastry_charts import BASE_A, make_chart

EQUAL_FROM_0 = {str(i + 1): 30.0 * i for i in range(12)}
EQUAL_FROM_350 = {str(i + 1): (350.0 + 30.0 * i) % 360.0 for i in range(12)}
UNEQUAL = {
    "1": 100.0, "2": 125.0, "3": 155.0, "4": 190.0, "5": 220.0, "6": 250.0,
    "7": 280.0, "8": 305.0, "9": 335.0, "10": 10.0, "11": 40.0, "12": 70.0,
}


@pytest.mark.parametrize("lon, house", [(0.0, 1), (29.999, 1), (30.0, 2), (185.0, 7), (359.9, 12)])
def test_equal_houses(lon: float, house: int) -> None:
    assert house_of(lon, EQUAL_FROM_0) == house


@pytest.mark.parametrize("lon, house", [(350.0, 1), (355.0, 1), (5.0, 1), (20.0, 2), (349.9, 12)])
def test_house_one_spanning_the_aries_point(lon: float, house: int) -> None:
    assert house_of(lon, EQUAL_FROM_350) == house


@pytest.mark.parametrize("lon, house", [(100.0, 1), (124.9, 1), (125.0, 2), (5.0, 9), (10.0, 10), (99.9, 12)])
def test_unequal_houses(lon: float, house: int) -> None:
    assert house_of(lon, UNEQUAL) == house


def test_degenerate_cusps_fail_visibly() -> None:
    with pytest.raises(CalculationError):
        house_of(10.0, {str(i + 1): 0.0 for i in range(12)})


def test_overlays_when_the_host_time_is_known() -> None:
    guest = {**BASE_A, "Ascendant": 5.0, "MC": 275.0}
    rows = house_overlays(guest, make_chart(BASE_A, cusp_start=0.0), host_time_known=True)
    assert [r["factor"] for r in rows] == list(PLANET_FACTORS)  # D6: no ASC/MC rows
    assert rows[0] == {"factor": "Sun", "house": 1, "status": "ok"}       # 10°
    assert rows[1] == {"factor": "Moon", "house": 4, "status": "ok"}      # 100°
    assert rows[4] == {"factor": "Mars", "house": 7, "status": "ok"}      # 200°


def test_overlays_are_gated_when_the_host_time_is_unknown() -> None:
    rows = house_overlays(BASE_A, make_chart(BASE_A), host_time_known=False)
    assert rows == [{"factor": f, "house": None, "status": "unavailable_missing_time"} for f in PLANET_FACTORS]
