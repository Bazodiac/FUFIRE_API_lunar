"""synastry/aspects.py — aspects between two charts (spec §3).

Full cross matrix A×B (not i<j), five major aspects, orb table
``synastry-orbs-v1``, at most one aspect per pair. ``orb`` is rounded to 4 dp
first; inclusion and ``exact`` are decided on that rounded orb, so the response
is self-consistent.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, NamedTuple, Optional

from .policy import SYNASTRY_ASPECTS, factor_weight


class AspectHit(NamedTuple):
    type: str
    exact_angle: float
    orb: float
    orb_limit: float


def angular_separation(lon1: float, lon2: float) -> float:
    """Shortest angular distance between two ecliptic longitudes (0–180°)."""
    diff = abs(lon1 - lon2) % 360.0
    return min(diff, 360.0 - diff)


def classify_aspect(lon_from: float, lon_to: float) -> Optional[AspectHit]:
    """The one aspect whose orb window contains the separation, else None."""
    separation = angular_separation(lon_from, lon_to)
    for name, angle, orb_limit in SYNASTRY_ASPECTS:
        orb = round(abs(separation - angle), 4)
        if orb <= orb_limit:
            return AspectHit(name, angle, orb, orb_limit)
    return None


def _aspect_row(
    from_person: str, from_factor: str, to_person: str, to_factor: str, hit: AspectHit,
) -> Dict[str, Any]:
    _, from_weight = factor_weight(from_factor)
    _, to_weight = factor_weight(to_factor)
    return {
        "from_person": from_person,
        "from_factor": from_factor,
        "to_person": to_person,
        "to_factor": to_factor,
        "type": hit.type,
        "exact_angle": hit.exact_angle,
        "orb": hit.orb,
        "exact": hit.orb <= hit.orb_limit / 2.0,
        "from_weight": from_weight,
        "to_weight": to_weight,
        "weight": round(from_weight * to_weight, 6),
    }


def cross_aspects(
    factors_from: Mapping[str, float],
    factors_to: Mapping[str, float],
    *,
    from_person: str,
    to_person: str,
) -> List[Dict[str, Any]]:
    """Every aspect between a factor of ``factors_from`` and one of ``factors_to``."""
    rows: List[Dict[str, Any]] = []
    for from_factor, lon_from in factors_from.items():
        for to_factor, lon_to in factors_to.items():
            hit = classify_aspect(lon_from, lon_to)
            if hit is not None:
                rows.append(_aspect_row(from_person, from_factor, to_person, to_factor, hit))
    return rows
