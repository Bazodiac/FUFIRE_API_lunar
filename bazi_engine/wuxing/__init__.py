"""
bazi_engine/wuxing — Wu-Xing (Five Elements) domain package.

Re-exports everything for backwards compatibility with
``from bazi_engine.fusion import WuXingVector, PLANET_TO_WUXING, ...``
"""
from .analysis import (
    calculate_harmony_index,
    calculate_wuxing_from_bazi,
    calculate_wuxing_from_bazi_with_ledger,
    calculate_wuxing_vector_from_planets,
    calculate_wuxing_vector_from_planets_with_ledger,
    interpret_harmony,
    is_night_chart,
    planet_to_wuxing,
)
from .constants import (
    PLANET_TO_WUXING,
    SIGN_ELEMENT,
    WEST_ELEMENT_TO_WUXING,
    WESTERN_BODY_TIER,
    WESTERN_EXCLUDED_BODIES,
    WESTERN_MAPPING_ID,
    WESTERN_TIER_RATIO,
    WESTERN_TIER_WEIGHT,
    WESTERN_WEIGHTING_ID,
    WUXING_INDEX,
    WUXING_ORDER,
    western_body_weight,
)
from .ke_cycle import (
    KE_CYCLE,
    KE_INVERSE,
    KeCycleRelation,
    ke_cross_tensions,
    ke_cycle_summary,
    ke_tensions_in_vector,
)
from .vector import WuXingVector
from .zones import (
    ZoneLabel,
    ZoneResult,
    build_leitfragen,
    classify_zones,
    format_report_b,
    question_development,
    question_tension,
)

__all__ = [
    "PLANET_TO_WUXING",
    "SIGN_ELEMENT",
    "WEST_ELEMENT_TO_WUXING",
    "WESTERN_MAPPING_ID",
    "WESTERN_WEIGHTING_ID",
    "WESTERN_TIER_RATIO",
    "WESTERN_TIER_WEIGHT",
    "WESTERN_BODY_TIER",
    "WESTERN_EXCLUDED_BODIES",
    "western_body_weight",
    "WUXING_ORDER",
    "WUXING_INDEX",
    "WuXingVector",
    "planet_to_wuxing",
    "calculate_wuxing_vector_from_planets",
    "calculate_wuxing_vector_from_planets_with_ledger",
    "is_night_chart",
    "calculate_wuxing_from_bazi",
    "calculate_wuxing_from_bazi_with_ledger",
    "calculate_harmony_index",
    "interpret_harmony",
    # Logik B — Zonenklassifikation
    "ZoneResult",
    "ZoneLabel",
    "classify_zones",
    "question_tension",
    "question_development",
    "build_leitfragen",
    "format_report_b",
    # Ke-cycle (相剋) — destructive relationships
    "KE_CYCLE",
    "KE_INVERSE",
    "KeCycleRelation",
    "ke_tensions_in_vector",
    "ke_cross_tensions",
    "ke_cycle_summary",
]
