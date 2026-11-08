"""synastry/houses.py — one person's planets in the other person's houses (spec §4)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from ..exc import CalculationError
from .policy import PLANET_FACTORS, STATUS_MISSING_TIME, STATUS_OK


def house_of(longitude: float, cusps: Mapping[str, float]) -> int:
    """House (1–12) containing ``longitude``; a cusp belongs to the house it opens."""
    lon = longitude % 360.0
    for house in range(1, 13):
        start = float(cusps[str(house)]) % 360.0
        end = float(cusps[str(house % 12 + 1)]) % 360.0
        span = (end - start) % 360.0
        if span > 0.0 and (lon - start) % 360.0 < span:
            return house
    raise CalculationError("Longitude could not be placed in any house", detail={})


def house_overlays(
    guest_factors: Mapping[str, float],
    host_chart: Mapping[str, Any],
    *,
    host_time_known: bool,
) -> List[Dict[str, Any]]:
    """The guest's ten planets in the host's houses.

    Gate: without the host's birth time the host has no houses, so every row
    is ``unavailable_missing_time`` with ``house: None`` (no values).
    """
    if not host_time_known:
        return [{"factor": f, "house": None, "status": STATUS_MISSING_TIME} for f in PLANET_FACTORS]
    cusps = host_chart["houses"]
    return [
        {"factor": f, "house": house_of(guest_factors[f], cusps), "status": STATUS_OK}
        for f in PLANET_FACTORS
    ]
