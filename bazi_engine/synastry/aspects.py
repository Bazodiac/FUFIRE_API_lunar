"""synastry/aspects.py — aspects between two charts (spec §3).

Full cross matrix A×B (not i<j), five major aspects, orb table
``synastry-orbs-v1``, at most one aspect per pair. ``orb`` is rounded to 4 dp
first; inclusion and ``tight`` (orb ≤ half the orb limit) are decided on that rounded orb, so the response
is self-consistent. ``time_sensitive`` (D15) flags rows whose aspect depends on
the unknown birth time of a Moon.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, NamedTuple, Optional, Tuple

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


MoonBounds = Optional[Tuple[float, float]]


def _endpoints(factor: str, longitude: float, moon_bounds: MoonBounds) -> Tuple[float, ...]:
    if factor == "Moon" and moon_bounds is not None:
        return moon_bounds
    return (longitude,)


def is_time_sensitive(
    hit_type: str, from_ends: Tuple[float, ...], to_ends: Tuple[float, ...],
) -> bool:
    """True when any combination of endpoints gives another aspect type (None counts as other).

    An endpoint set is the two Moon longitudes at local 00:00 and 23:59 for a
    person with an unknown birth time, else the single longitude. The Moon
    moves forward over one continuous arc of about 12–15° during the day, and
    every aspect window (exact angle ± orb) is a convex arc of longitude, far
    wider apart from the next window of the same type than the Moon travels in
    a day. So when the aspect type agrees at both bounds (at all four corners
    for Moon–Moon with both times unknown, where the separation is monotone in
    each Moon), the separation stays inside that one window over the whole day:
    checking the bounds is enough.
    """
    if len(from_ends) == 1 and len(to_ends) == 1:
        return False
    for lon_from in from_ends:
        for lon_to in to_ends:
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
    from_moon_bounds: MoonBounds = None,
    to_moon_bounds: MoonBounds = None,
) -> List[Dict[str, Any]]:
    """Every aspect between a factor of ``factors_from`` and one of ``factors_to``.

    ``*_moon_bounds`` are the Moon longitudes at local 00:00 and 23:59 of a
    person with an unknown birth time (D15), else None.
    """
    rows: List[Dict[str, Any]] = []
    for from_factor, lon_from in factors_from.items():
        from_ends = _endpoints(from_factor, lon_from, from_moon_bounds)
        for to_factor, lon_to in factors_to.items():
            hit = classify_aspect(lon_from, lon_to)
            if hit is not None:
                sensitive = is_time_sensitive(hit.type, from_ends, _endpoints(to_factor, lon_to, to_moon_bounds))
                rows.append(_aspect_row(from_person, from_factor, to_person, to_factor, hit,
                                        time_sensitive=sensitive))
    return rows
