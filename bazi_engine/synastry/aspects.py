"""synastry/aspects.py — aspects between two charts (spec §3).

Full cross matrix A×B (not i<j), five major aspects, orb table
``synastry-orbs-v1``, at most one aspect per pair. ``orb`` is rounded to 4 dp
first; inclusion and ``tight`` (orb ≤ half the orb limit) are decided on that rounded orb, so the response
is self-consistent. ``time_sensitive`` (D15, D16) flags rows whose aspect depends
on the unknown birth time of either person (every planet, not only the Moon).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Tuple

from .factors import DayRanges
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


def _samples(factor: str, longitude: float, day_ranges: DayRanges) -> Tuple[float, ...]:
    if day_ranges is not None and factor in day_ranges:
        return day_ranges[factor]
    return (longitude,)


def is_time_sensitive(
    hit_type: str, from_samples: Tuple[float, ...], to_samples: Tuple[float, ...],
) -> bool:
    """True when any combination of samples gives another aspect type (None counts as other).

    A sample set is a planet's two longitudes at local 00:00 and 23:59 for a
    person with an unknown birth time (D16), else the single longitude: two
    combinations, or four when both persons are unknown-time. Every aspect
    window (exact angle ± orb) is convex in longitude, and over one day each
    planet moves monotonically, apart from a station where the motion is
    below 1 arcminute; the signed separation is then monotone in each
    person's time. Agreement at both bounds (all four corners) and at noon
    (the row itself) therefore means the aspect is stable over the whole day.
    """
    if len(from_samples) == 1 and len(to_samples) == 1:
        return False
    for lon_from in from_samples:
        for lon_to in to_samples:
            hit = classify_aspect(lon_from, lon_to)
            if hit is None or hit.type != hit_type:
                return True
    return False


def _aspect_row(
    from_person: str, from_factor: str, to_person: str, to_factor: str, hit: AspectHit,
    *, time_sensitive: bool,
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
        "tight": hit.orb <= hit.orb_limit / 2.0,
        "time_sensitive": time_sensitive,
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
    from_day_ranges: DayRanges = None,
    to_day_ranges: DayRanges = None,
) -> List[Dict[str, Any]]:
    """Every aspect between a factor of ``factors_from`` and one of ``factors_to``.

    The row is the 12:00 (or known-time) aspect. ``*_day_ranges`` are the
    planet longitudes at local 00:00 and 23:59 of a person with an unknown
    birth time (D16), else None. An aspect that exists only at another time of
    that day is not output.
    """
    rows: List[Dict[str, Any]] = []
    for from_factor, lon_from in factors_from.items():
        from_samples = _samples(from_factor, lon_from, from_day_ranges)
        for to_factor, lon_to in factors_to.items():
            hit = classify_aspect(lon_from, lon_to)
            if hit is not None:
                sensitive = is_time_sensitive(hit.type, from_samples, _samples(to_factor, lon_to, to_day_ranges))
                rows.append(_aspect_row(from_person, from_factor, to_person, to_factor, hit,
                                        time_sensitive=sensitive))
    return rows
