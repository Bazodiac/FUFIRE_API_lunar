"""Compute 12-sector soulprint vector from natal signals."""
from __future__ import annotations

from typing import Dict, List

from ..wuxing.constants import SIGN_ELEMENT, WEST_ELEMENT_TO_WUXING, WUXING_ORDER


def _phase_sector_shares() -> Dict[str, List[float]]:
    """Wu-Xing phase → share per zodiac sector (0 = Aries), summing to 1 per phase.

    The transpose of the consensus matrix (sign-element-consensus-v1): a phase is
    spread over the twelve signs in proportion to how much each sign's element
    gives to it, so the soulprint and the western Fusion vector use the same
    translation (since 2026-11-07; the former fixed pairs such as Holz → Cancer,
    Leo had no derivation).
    """
    shares: Dict[str, List[float]] = {}
    for phase in WUXING_ORDER:
        raw = [WEST_ELEMENT_TO_WUXING[SIGN_ELEMENT[sector]][phase] for sector in range(12)]
        total = sum(raw)
        shares[phase] = [value / total for value in raw]
    return shares


_PHASE_SECTOR_SHARE: Dict[str, List[float]] = _phase_sector_shares()


def compute_soulprint(
    sun_sign_idx: int,
    moon_sign_idx: int,
    asc_sign_idx: int,
    personal_planets: Dict[str, int],  # planet_name → sector_idx
    wuxing_vector: Dict[str, float],
) -> List[float]:
    """Return normalized 12-sector soulprint vector."""
    sectors = [0.0] * 12
    sectors[sun_sign_idx % 12] += 1.0
    sectors[moon_sign_idx % 12] += 0.8
    sectors[asc_sign_idx % 12] += 0.6
    for _planet, sector_idx in personal_planets.items():
        sectors[sector_idx % 12] += 0.4
    # Each phase adds its weight in total (as before: 0.5 to each of two sectors),
    # now spread over the signs by the transposed consensus matrix.
    for element, weight in wuxing_vector.items():
        for sector_idx, share in enumerate(_PHASE_SECTOR_SHARE.get(element, [])):
            sectors[sector_idx] += weight * share
    total = sum(sectors)
    if total > 0:
        sectors = [round(s / total, 6) for s in sectors]
    return sectors
