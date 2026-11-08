"""synastry/houses.py — one person's planets in the other person's houses (spec §4)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from ..exc import CalculationError
from .factors import DayRanges
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


def _time_sensitive(house: int, factor: str, cusps: Mapping[str, float], guest_ranges: DayRanges) -> bool:
    """True when the guest's day bounds put the factor in another house than at 12:00 (D16).

    A house is a convex arc between two cusps and a planet moves monotonically
    over one day, so the same house at both bounds and at noon means the same
    house over the whole day.
    """
    if guest_ranges is None:
        return False
    start, end = guest_ranges[factor]
    return house_of(start, cusps) != house or house_of(end, cusps) != house


def house_overlays(
    guest_factors: Mapping[str, float],
    host_chart: Mapping[str, Any],
    *,
    host_time_known: bool,
    guest_day_ranges: DayRanges = None,
) -> List[Dict[str, Any]]:
    """The guest's ten planets in the host's houses.

    Gate: without the host's birth time the host has no houses, so every row
    is ``unavailable_missing_time`` with ``house: None`` (no values) and
    ``time_sensitive: False``. Otherwise the host cusps are the host's fixed
    chart; ``guest_day_ranges`` (an unknown-time guest, D16) sets
    ``time_sensitive``, which is false for a known-time guest.
    """
    if not host_time_known:
        return [{"factor": f, "house": None, "status": STATUS_MISSING_TIME, "time_sensitive": False}
                for f in PLANET_FACTORS]
    cusps = host_chart["houses"]
    rows: List[Dict[str, Any]] = []
    for factor in PLANET_FACTORS:
        house = house_of(guest_factors[factor], cusps)
        rows.append({"factor": factor, "house": house, "status": STATUS_OK,
                     "time_sensitive": _time_sensitive(house, factor, cusps, guest_day_ranges)})
    return rows
