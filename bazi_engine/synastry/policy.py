"""synastry/policy.py — fixed policy data for the synastry layer (pure data).

Level 4. Decisions: docs/superpowers/specs/2026-11-08-synastry-g1-design.md.

Orb table ``synastry-orbs-v1`` comes from Astro-Noctum (spec §3) and is the
same when the ascendant or MC is a partner. The windows do not overlap, so a
pair can match at most one aspect. Weights reuse the Fusion tiers
(``body-tier-q0.3-v1``); MC, which the Fusion table does not list, counts as
tier 1 like the ascendant (D2). The Fusion table itself is not changed.
"""
from __future__ import annotations

import re
from typing import Dict, Final, Tuple

from ..time_utils import AmbiguousTimeChoice, NonexistentTimePolicy
from ..wuxing.constants import WESTERN_TIER_WEIGHT, western_body_weight

SYNASTRY_ORB_POLICY_ID: Final[str] = "synastry-orbs-v1"
SYNASTRY_WEIGHTING_ID: Final[str] = "synastry-weights-v1"

# (type, exact angle, orb limit in degrees)
SYNASTRY_ASPECTS: Final[Tuple[Tuple[str, float, float], ...]] = (
    ("conjunction", 0.0, 8.0),
    ("sextile", 60.0, 4.0),
    ("square", 90.0, 6.0),
    ("trine", 120.0, 6.0),
    ("opposition", 180.0, 8.0),
)

PLANET_FACTORS: Final[Tuple[str, ...]] = (
    "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
)
# Only when the person's birth time is known.
ANGLE_FACTORS: Final[Tuple[str, ...]] = ("Ascendant", "MC")
FACTOR_ORDER: Final[Tuple[str, ...]] = PLANET_FACTORS + ANGLE_FACTORS
# G1b sign layer (spec §5) and its Wu-Xing translation (spec §6, D3).
SIGN_LAYER_FACTORS: Final[Tuple[str, ...]] = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Ascendant")

SYNASTRY_TIER_OVERRIDES: Final[Dict[str, int]] = {"MC": 1}


def factor_weight(factor: str) -> Tuple[int, float]:
    """Tier and weight of a synastry factor (Fusion tiers, MC tier 1)."""
    if factor in SYNASTRY_TIER_OVERRIDES:
        tier = SYNASTRY_TIER_OVERRIDES[factor]
        return tier, WESTERN_TIER_WEIGHT[tier]
    return western_body_weight(factor)


# Literal copy of routers.shared.ZODIAC_SIGNS_DE (Level 5, not importable here);
# tests/test_synastry_policy.py pins the two equal.
ZODIAC_SIGNS: Final[Tuple[str, ...]] = (
    "Widder", "Stier", "Zwillinge", "Krebs", "Löwe", "Jungfrau",
    "Waage", "Skorpion", "Schütze", "Steinbock", "Wassermann", "Fische",
)

# Index = shortest distance between two signs (0..6).
SIGN_RELATIONS: Final[Tuple[str, ...]] = (
    "same_sign", "semi_sextile", "sextile", "square", "trine", "quincunx", "opposition",
)

PERSON_A: Final[str] = "person_a"
PERSON_B: Final[str] = "person_b"

STATUS_OK: Final[str] = "ok"
STATUS_MISSING_TIME: Final[str] = "unavailable_missing_time"

# Unknown birth time (D14, D15; Confluence BG 62259202, FUF-163..165): the chart is
# computed at local 12:00:00 of the calendar day, visibly; a supplied time part is
# discarded. The Moon is also computed at the two ends of the local day.
UNKNOWN_TIME_ASSUMED_LOCAL: Final[str] = "12:00:00"
UNKNOWN_TIME_ASSUMPTION_REASON: Final[str] = "birth_time_unknown"
# Moon range over the local calendar day (F7)
MOON_RANGE_LOCAL_TIMES: Final[Tuple[str, str]] = ("00:00:00", "23:59:00")
# DST policy (ambiguous, nonexistent) per bound: midnight can fall in a gap, and on a
# fall-back day 23:59 occurs twice — the end of the day is the later occurrence.
MOON_RANGE_DST_POLICIES: Final[Tuple[Tuple[AmbiguousTimeChoice, NonexistentTimePolicy], ...]] = (
    ("earlier", "shift_forward"),
    ("later", "shift_forward"),
)

_DAY_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def unknown_time_day(date: str) -> Tuple[str, bool]:
    """Calendar day ``YYYY-MM-DD`` of ``date`` and whether a time part followed it.

    The error message never contains the value (it is birth data).
    """
    text = date.strip()
    day = text[:10]
    if not _DAY_PREFIX.match(day):
        raise ValueError("date must start with YYYY-MM-DD")
    return day, len(text) > 10
