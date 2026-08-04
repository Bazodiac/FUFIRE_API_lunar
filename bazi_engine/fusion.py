"""
fusion.py — Level 4: Fusion Astrology orchestration.

Combines Western planetary data with BaZi pillars into a unified
energetic profile. All Wu-Xing domain logic lives in bazi_engine/wuxing/.

Re-exports:
  equation_of_time, true_solar_time  — from solar_time (Level 2)
  All Wu-Xing symbols                — from wuxing package (Level 4 peer)

Own functions:
  true_solar_time_from_civil()       — fusion-specific TST helper
  compute_fusion_analysis()          — main orchestrator
  generate_fusion_interpretation()   — text generation
"""
from __future__ import annotations

from typing import Any, Dict, Optional

# ── Re-exports for backwards compatibility ────────────────────────────────────
from .solar_time import equation_of_time, true_solar_time  # noqa: F401
from .wuxing import (  # noqa: F401
    PLANET_TO_WUXING,
    WUXING_INDEX,
    WUXING_ORDER,
    WuXingVector,
    calculate_harmony_index,
    calculate_wuxing_from_bazi,
    calculate_wuxing_from_bazi_with_ledger,
    calculate_wuxing_vector_from_planets,
    calculate_wuxing_vector_from_planets_with_ledger,
    interpret_harmony,
    is_night_chart,
    planet_to_wuxing,
)
from .wuxing.calibration import CalibrationResult, calibrate_harmony

# ─────────────────────────────────────────────────────────────────────────────


def true_solar_time_from_civil(
    civil_time_hours: float,
    longitude_deg: float,
    day_of_year: int,
    standard_meridian_deg: Optional[float] = None,
) -> float:
    """True Solar Time from civil time via standard meridian correction.

    TST = civil_time + 4*(standard_meridian - longitude) + EoT

    Args:
        civil_time_hours:    Local civil time in hours.
        longitude_deg:       Observer's longitude (positive = east).
        day_of_year:         Day of year (1–366).
        standard_meridian_deg: Standard meridian for the timezone (e.g. 15° for CET).
                              Auto-estimated from longitude if None.

    Returns:
        True Solar Time in hours [0, 24).
    """
    if standard_meridian_deg is None:
        standard_meridian_deg = round(longitude_deg / 15) * 15

    longitude_correction_hours = (standard_meridian_deg - longitude_deg) * 4 / 60
    E_t_hours = equation_of_time(day_of_year) / 60.0
    TST = civil_time_hours + longitude_correction_hours + E_t_hours

    while TST < 0:
        TST += 24
    while TST >= 24:
        TST -= 24

    return round(TST, 4)


def compute_fusion_analysis(
    birth_utc_dt: Any,
    latitude: float,
    longitude: float,
    bazi_pillars: Dict[str, Dict[str, str]],
    western_bodies: Dict[str, Dict[str, Any]],
    ascendant: Optional[float] = None,
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    """Complete Fusion Astrology Analysis.

    Combines Western planetary positions with BaZi pillars to produce
    a unified Wu-Xing energetic profile.

    Args:
        birth_utc_dt:   Birth datetime in UTC.
        latitude:       Birth latitude in degrees.
        longitude:      Birth longitude in degrees.
        bazi_pillars:   Year/month/day/hour pillars (stem + branch).
        western_bodies: Planetary data from compute_western_chart().
        ascendant:      Ascendant longitude for day/night chart detection.
                        If None, defaults to day chart (assumed_day quality).
        strict:         When True, a missing ascendant raises ValueError
                        instead of silently degrading the Mercury day/night
                        classification. Use at router-layer call sites that
                        always have a real ascendant (from
                        western['angles']['Ascendant']).

    Returns:
        Dict with wu_xing_vectors, harmony_index, calibration,
        elemental_comparison, cosmic_state, and fusion_interpretation.
    """
    western_wuxing, western_ledger = calculate_wuxing_vector_from_planets_with_ledger(
        western_bodies, ascendant=ascendant, strict=strict,
    )
    bazi_wuxing, bazi_ledger = calculate_wuxing_from_bazi_with_ledger(bazi_pillars)
    harmony = calculate_harmony_index(western_wuxing, bazi_wuxing)

    # Calibrate H relative to empirical baseline for this input density
    cal = calibrate_harmony(
        h_raw=harmony["harmony_index"],
        western_bodies=western_bodies,
        bazi_pillars=bazi_pillars,
        western_vector=western_wuxing,
        bazi_vector=bazi_wuxing,
    )
    calibration_dict = {
        "h_raw": cal.h_raw,
        "h_calibrated": cal.h_calibrated,
        "h_baseline": cal.h_baseline,
        "h_sigma": cal.h_sigma,
        "sigma_above": cal.sigma_above,
        "quality": cal.quality,
        "interpretation_band": cal.interpretation_band,
        "n_west": cal.n_west,
        "n_bazi_contributions": cal.n_bazi_contributions,
    }

    western_norm = western_wuxing.normalize()
    bazi_norm = bazi_wuxing.normalize()

    elemental_comparison: Dict[str, Dict[str, float]] = {}
    for elem in WUXING_ORDER:
        w_val = getattr(western_norm, elem.lower())
        b_val = getattr(bazi_norm, elem.lower())
        elemental_comparison[elem] = {
            "western": round(w_val, 3),
            "bazi": round(b_val, 3),
            "difference": round(w_val - b_val, 3),
        }

    cosmic_state = sum(
        w * b for w, b in zip(western_norm.to_list(), bazi_norm.to_list())
    )

    return {
        "wu_xing_vectors": {
            "western_planets": western_norm.to_dict(),
            "bazi_pillars": bazi_norm.to_dict(),
        },
        "harmony_index": harmony,
        "calibration": calibration_dict,
        "elemental_comparison": elemental_comparison,
        "cosmic_state": round(cosmic_state, 4),
        "fusion_interpretation": generate_fusion_interpretation(
            harmony["harmony_index"], elemental_comparison, western_wuxing, bazi_wuxing,
            calibration=cal,
        ),
        "contribution_ledger": {
            "western": western_ledger,
            "bazi": bazi_ledger,
            "chart_type_quality": "exact" if ascendant is not None else "assumed_day",
        },
    }


def generate_fusion_interpretation(
    harmony: float,
    comparison: Dict[str, Dict[str, float]],
    western: WuXingVector,
    bazi: WuXingVector,
    calibration: Optional[CalibrationResult] = None,
) -> str:
    """Generate a claim-safe text interpretation of the fusion analysis.

    FUF-147 fail-closed containment: the raw harmony value must never drive
    user-facing judgment prose (raw H is empirically always ≥ 0.5, so the old
    thresholds emitted positive resonance claims for nearly every chart).

    - With a calibration result (quality != "degenerate"): report the
      calibrated coherence and its interpretation band.
    - Without calibration, or degenerate input: fully reduced diagnostic
      output — no coherence band, no judgment sentence.
    - The raw value appears only under an explicit expert-diagnostics label.
    """
    w_dict = western.to_dict()
    b_dict = bazi.to_dict()
    w_dominant = max(w_dict, key=lambda k: w_dict[k])
    b_dominant = max(b_dict, key=lambda k: b_dict[k])

    if calibration is not None and calibration.quality != "degenerate":
        coherence_lines = [
            f"Kalibrierte Kohärenz: {calibration.h_calibrated:.2%} "
            f"({calibration.interpretation_band})",
            f"Datenqualität: {calibration.quality}",
        ]
    else:
        coherence_lines = [
            "Kalibrierte Kohärenz: nicht verfügbar — Ausgabe fail-closed reduziert.",
        ]

    lines = [
        *coherence_lines,
        f"Expertendiagnostik: H_raw={harmony:.2f} "
        "(unkalibrierter Rohwert — kein Nutzerurteil)",
        "",
        f"Westliche Dominanz: {w_dominant}",
        f"Östliche Dominanz: {b_dominant}",
    ]
    return "\n".join(lines)
