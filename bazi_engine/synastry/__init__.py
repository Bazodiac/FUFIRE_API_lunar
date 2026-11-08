"""bazi_engine/synastry — western pair facts for two charts (G1 + G1b).

Level 4. Pure functions over two ``compute_western_chart`` results: no
ephemeris calls, no BaZi, no routers. No interpretation and no score.
Decisions: docs/superpowers/specs/2026-11-08-synastry-g1-design.md.
"""
from .factors import extract_factors
from .policy import (
    FACTOR_ORDER,
    SIGN_LAYER_FACTORS,
    SYNASTRY_ASPECTS,
    SYNASTRY_ORB_POLICY_ID,
    SYNASTRY_WEIGHTING_ID,
    factor_weight,
)

__all__ = [
    "FACTOR_ORDER",
    "SIGN_LAYER_FACTORS",
    "SYNASTRY_ASPECTS",
    "SYNASTRY_ORB_POLICY_ID",
    "SYNASTRY_WEIGHTING_ID",
    "extract_factors",
    "factor_weight",
]
