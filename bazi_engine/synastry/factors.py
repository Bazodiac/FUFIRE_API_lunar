"""synastry/factors.py — the synastry factors of one western chart."""
from __future__ import annotations

from typing import Any, Dict, Mapping

from ..exc import CalculationError
from .policy import ANGLE_FACTORS, PLANET_FACTORS


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
        factors[name] = float(body["longitude"]) % 360.0
    if birth_time_known:
        for name in ANGLE_FACTORS:
            factors[name] = float(chart["angles"][name]) % 360.0
    return factors
