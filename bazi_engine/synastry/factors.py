"""synastry/factors.py — the synastry factors of one western chart."""
from __future__ import annotations

from typing import Any, Dict, Mapping

from ..exc import CalculationError
from .policy import ANGLE_FACTORS, PLANET_FACTORS


def normalize_longitude(longitude: float) -> float:
    """Longitude in [0, 360): a tiny negative value must not be stored as 360.0."""
    lon = longitude % 360.0
    return 0.0 if lon >= 360.0 else lon


def extract_factors(chart: Mapping[str, Any], *, birth_time_known: bool) -> Dict[str, float]:
    """Return ``{factor: longitude}`` in ``FACTOR_ORDER``.

    The ten planets always; ascendant and MC only when the birth time is
    known (spec §2). A planet the chart could not compute fails loudly instead
    of silently shrinking the factor set.
    """
    bodies = chart["bodies"]
    factors: Dict[str, float] = {}
    for name in PLANET_FACTORS:
        body = bodies.get(name, {})
        if "longitude" not in body:
            raise CalculationError(
                f"Synastry factor {name} is missing from the western chart",
                detail={"factor": name},
            )
        factors[name] = normalize_longitude(float(body["longitude"]))
    if birth_time_known:
        for name in ANGLE_FACTORS:
            factors[name] = normalize_longitude(float(chart["angles"][name]))
    return factors
