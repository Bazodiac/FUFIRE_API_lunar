"""synastry/signs.py — the sign layer of the synastry (G1b, spec §5)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from ..wuxing.constants import SIGN_ELEMENT
from .factors import DayRanges
from .policy import PERSON_A, PERSON_B, SIGN_LAYER_FACTORS, SIGN_RELATIONS, ZODIAC_SIGNS

# Elements that share a polarity: Feuer–Luft (active), Erde–Wasser (receptive).
_COMPLEMENTARY = (frozenset({"Feuer", "Luft"}), frozenset({"Erde", "Wasser"}))


def _norm(longitude: float) -> float:
    lon = longitude % 360.0
    return 0.0 if lon >= 360.0 else lon  # a tiny negative input rounds up to exactly 360.0


def sign_entry(factor: str, longitude: float) -> Dict[str, Any]:
    lon = _norm(longitude)
    index = int(lon // 30.0) % 12
    return {
        "factor": factor,
        "sign": ZODIAC_SIGNS[index],
        "sign_index": index,
        "west_element": SIGN_ELEMENT[index],
        "degree": min(round(lon - 30.0 * index, 4), 29.9999),
        "sign_certain": None,
        "moon_range_deg": None,
    }


def day_range(bounds: Tuple[float, float]) -> Tuple[List[float], bool]:
    """``[start, end]`` (4 dp, in [0, 360)) and sign certainty over the local day.

    For the Moon the range is forward (end < start when crossing 0°). The sign
    test runs on the rounded values, so ``sign_certain`` agrees with the
    emitted Moon range (same rule as the rounded orb, D7). A sign is a convex
    arc and a planet moves monotonically over one day (D16), so the same sign
    at both bounds means the same sign over the whole day.
    """
    start, end = (_norm(round(_norm(b), 4)) for b in bounds)
    return [start, end], int(start // 30.0) == int(end // 30.0)


def sign_relation(index_a: int, index_b: int) -> str:
    distance = abs(index_a - index_b) % 12
    return SIGN_RELATIONS[min(distance, 12 - distance)]


def element_relation(element_a: str, element_b: str) -> str:
    if element_a == element_b:
        return "same"
    if frozenset({element_a, element_b}) in _COMPLEMENTARY:
        return "complementary"
    return "other"


def _entries(factors: Mapping[str, float], day_ranges: DayRanges) -> List[Dict[str, Any]]:
    entries = [sign_entry(f, factors[f]) for f in SIGN_LAYER_FACTORS if f in factors]
    if day_ranges is not None:
        for entry in entries:
            rng, entry["sign_certain"] = day_range(day_ranges[entry["factor"]])
            if entry["factor"] == "Moon":
                entry["moon_range_deg"] = rng
    return entries


def sign_layer(
    factors_a: Mapping[str, float],
    factors_b: Mapping[str, float],
    *,
    day_ranges_a: DayRanges = None,
    day_ranges_b: DayRanges = None,
) -> Dict[str, Any]:
    """Sign entries per person and every A×B sign pair.

    ``day_ranges_x`` (D15, D16): planet longitudes at local 00:00 and 23:59 for
    a person with an unknown birth time. They fill ``sign_certain`` on every
    sign-layer entry of that person (Sun … Mars; an unknown-time person has no
    Ascendant) and ``moon_range_deg`` on the Moon entry only. A known-time
    person carries null for both.
    """
    entries_a = _entries(factors_a, day_ranges_a)
    entries_b = _entries(factors_b, day_ranges_b)
    pairs = [
        {
            "factor_a": a["factor"],
            "factor_b": b["factor"],
            "sign_relation": sign_relation(a["sign_index"], b["sign_index"]),
            "element_relation": element_relation(a["west_element"], b["west_element"]),
        }
        for a in entries_a
        for b in entries_b
    ]
    return {"factors": {PERSON_A: entries_a, PERSON_B: entries_b}, "pairs": pairs}
