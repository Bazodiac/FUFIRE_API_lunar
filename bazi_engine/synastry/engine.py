"""synastry/engine.py — compose the synastry layers from two western charts.

Pure: takes two ``compute_western_chart`` results, returns plain dicts. No
timestamp is added (D10), so equal inputs give byte-identical responses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .. import __version__
from ..exc import CalculationError
from ..wuxing.constants import WESTERN_MAPPING_ID, WESTERN_WEIGHTING_ID
from .aspects import cross_aspects
from .factors import extract_factors
from .houses import house_overlays
from .policy import (
    PERSON_A,
    PERSON_B,
    SYNASTRY_ORB_POLICY_ID,
    SYNASTRY_WEIGHTING_ID,
    UNKNOWN_TIME_ASSUMED_LOCAL,
)
from .signs import sign_layer
from .wuxing_layer import wuxing_pair_factors

# D14: names the 12:00:00 assumption; never the supplied date or time (privacy, D9).
_TIME_UNKNOWN_DETAIL = (
    f"Birth time unknown: computed at the assumed local time {UNKNOWN_TIME_ASSUMED_LOCAL}; "
    "Ascendant, MC and houses are not used; the Moon range over the local day is in sign_layer."
)
_TIME_DISCARDED_DETAIL = " The supplied clock time was discarded."


@dataclass(frozen=True)
class SynastryPersonInput:
    """One person: a ``compute_western_chart`` result and the birth-time gate.

    For an unknown birth time the chart is the one at local 12:00:00 (D14);
    ``time_discarded`` says a supplied clock time was replaced, and
    ``moon_bounds`` holds the Moon longitudes at local 00:00 and 23:59 (D15).
    """

    chart: Mapping[str, Any]
    birth_time_known: bool
    time_discarded: bool = False
    moon_bounds: Optional[Tuple[float, float]] = None

    def __post_init__(self) -> None:
        if self.birth_time_known and (self.time_discarded or self.moon_bounds is not None):
            raise ValueError("time_discarded and moon_bounds apply only to an unknown birth time")


def compute_synastry(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> Dict[str, Any]:
    factors_a = extract_factors(person_a.chart, birth_time_known=person_a.birth_time_known)
    factors_b = extract_factors(person_b.chart, birth_time_known=person_b.birth_time_known)
    signs = sign_layer(factors_a, factors_b)
    return {
        "aspects": cross_aspects(factors_a, factors_b, from_person=PERSON_A, to_person=PERSON_B),
        "house_overlays": {
            "a_in_b": house_overlays(factors_a, person_b.chart, host_time_known=person_b.birth_time_known),
            "b_in_a": house_overlays(factors_b, person_a.chart, host_time_known=person_a.birth_time_known),
        },
        "sign_layer": signs,
        "wuxing_pair_factors": wuxing_pair_factors(signs["factors"][PERSON_A], signs["factors"][PERSON_B]),
        "provenance": _provenance(person_a, person_b),
    }


def _house_system_used(person: SynastryPersonInput) -> Optional[str]:
    if not person.birth_time_known:
        return None
    return str(person.chart["quality_flags"]["house_system_used"])


def _ephemeris_mode(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> str:
    modes = {str(p.chart["quality_flags"]["ephemeris_mode"]) for p in (person_a, person_b)}
    if len(modes) != 1:
        raise CalculationError("The two charts were computed with different ephemeris modes", detail={})
    return modes.pop()


def _warnings(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    for label, person in ((PERSON_A, person_a), (PERSON_B, person_b)):
        if not person.birth_time_known:
            detail = _TIME_UNKNOWN_DETAIL + (_TIME_DISCARDED_DETAIL if person.time_discarded else "")
            warnings.append({"code": "birth_time_unknown", "person": label, "detail": detail})
        elif person.chart["quality_flags"]["house_system_fallback"]:
            used = person.chart["quality_flags"]["house_system_used"]
            # The chart's own fallback reason names the latitude — never copied (D9).
            warnings.append({"code": "house_system_fallback", "person": label,
                             "detail": f"Placidus undefined; {used} used."})
    return warnings


def _provenance(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> Dict[str, Any]:
    return {
        "engine_version": __version__,
        "ephemeris_mode": _ephemeris_mode(person_a, person_b),
        "zodiac_mode": "tropical",
        "house_system_used": {PERSON_A: _house_system_used(person_a), PERSON_B: _house_system_used(person_b)},
        "orb_policy_id": SYNASTRY_ORB_POLICY_ID,
        "weighting_id": SYNASTRY_WEIGHTING_ID,
        "base_weighting_id": WESTERN_WEIGHTING_ID,
        "mapping_version": WESTERN_MAPPING_ID,
        "warnings": _warnings(person_a, person_b),
    }
