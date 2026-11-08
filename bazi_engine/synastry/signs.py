"""synastry/signs.py — the sign layer of the synastry (G1b, spec §5)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from ..wuxing.constants import SIGN_ELEMENT
from .policy import PERSON_A, PERSON_B, SIGN_LAYER_FACTORS, SIGN_RELATIONS, ZODIAC_SIGNS

# Elements that share a polarity: Feuer–Luft (active), Erde–Wasser (receptive).
_COMPLEMENTARY = (frozenset({"Feuer", "Luft"}), frozenset({"Erde", "Wasser"}))


def sign_entry(factor: str, longitude: float) -> Dict[str, Any]:
    lon = longitude % 360.0
    index = int(lon // 30.0) % 12
    return {
        "factor": factor,
        "sign": ZODIAC_SIGNS[index],
        "sign_index": index,
        "west_element": SIGN_ELEMENT[index],
        "degree": round(lon - 30.0 * index, 4),
    }


def sign_relation(index_a: int, index_b: int) -> str:
    distance = abs(index_a - index_b) % 12
    return SIGN_RELATIONS[min(distance, 12 - distance)]


def element_relation(element_a: str, element_b: str) -> str:
    if element_a == element_b:
        return "same"
    if frozenset({element_a, element_b}) in _COMPLEMENTARY:
        return "complementary"
    return "other"


def _entries(factors: Mapping[str, float]) -> List[Dict[str, Any]]:
    return [sign_entry(f, factors[f]) for f in SIGN_LAYER_FACTORS if f in factors]


def sign_layer(factors_a: Mapping[str, float], factors_b: Mapping[str, float]) -> Dict[str, Any]:
    entries_a = _entries(factors_a)
    entries_b = _entries(factors_b)
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
