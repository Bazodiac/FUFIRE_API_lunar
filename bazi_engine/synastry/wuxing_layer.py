"""synastry/wuxing_layer.py — Wu-Xing translation of the sign layer (spec §6, D3).

Each sign-layer factor is spread over the five phases by the consensus matrix
``sign-element-consensus-v1`` (the Fusion vector's matrix). The person vector
is the tier-weighted mean of the factor vectors (sum 1). No comparison number
between the two persons is computed (G1).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from ..wuxing.constants import WEST_ELEMENT_TO_WUXING, WESTERN_MAPPING_ID, WUXING_ORDER
from .policy import PERSON_A, PERSON_B, factor_weight


def factor_vector(west_element: str) -> List[float]:
    shares = WEST_ELEMENT_TO_WUXING[west_element]
    return [shares[phase] for phase in WUXING_ORDER]


def person_wuxing(entries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    factors: List[Dict[str, Any]] = []
    totals = [0.0] * len(WUXING_ORDER)
    weight_sum = 0.0
    for entry in entries:
        _, weight = factor_weight(entry["factor"])
        vector = factor_vector(entry["west_element"])
        factors.append({"factor": entry["factor"], "west_element": entry["west_element"],
                        "weight": weight, "vector": vector})
        totals = [t + weight * v for t, v in zip(totals, vector)]
        weight_sum += weight
    return {"factors": factors, "vector": [round(t / weight_sum, 6) for t in totals]}


def wuxing_pair_factors(
    entries_a: Sequence[Mapping[str, Any]], entries_b: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        "order": list(WUXING_ORDER),
        PERSON_A: person_wuxing(entries_a),
        PERSON_B: person_wuxing(entries_b),
        "mapping_version": WESTERN_MAPPING_ID,
    }
