"""
wuxing/analysis.py — Wu-Xing calculation functions.

Contains:
  planet_to_wuxing()                  — planet → element mapping
  calculate_wuxing_vector_from_planets() — planetary positions → WuXingVector
  is_night_chart()                    — day/night chart detection
  calculate_wuxing_from_bazi()        — BaZi pillars → WuXingVector
  calculate_harmony_index()           — cosine harmony between two vectors
  interpret_harmony()                 — human-readable harmony label
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constants import PLANET_TO_WUXING, WUXING_INDEX
from .vector import WuXingVector


def planet_to_wuxing(planet_name: str, is_night: bool = False) -> str:
    """Return the Wu-Xing element for a planet.

    Mercury is dual: Earth (day chart) / Metal (night chart).
    Unknown planets default to Earth.
    """
    element: Any = PLANET_TO_WUXING.get(planet_name, "Erde")
    if isinstance(element, list):
        return element[1] if is_night else element[0]
    return element


def is_night_chart(
    sun_longitude: float,
    ascendant: Optional[float] = None,
    *,
    strict: bool = False,
) -> bool:
    """Determine whether this is a night chart.

    Without an Ascendant, defaults to day chart (False) — backward compatible.
    With Ascendant: True if Sun is between DSC and ASC (houses 1–6).

    Args:
        sun_longitude: Ecliptic longitude of the Sun in degrees (0–360).
        ascendant:     Ecliptic longitude of the Ascendant in degrees, or
                       None when no ascendant is available (e.g. unknown
                       birth time, extreme latitude where Placidus fails).
        strict:        When True, an unusable ascendant (None) raises
                       ValueError instead of silently falling back to a
                       day chart. Use at router-layer call sites where the
                       chart_type_quality should be ``"exact"`` — this
                       turns a silent regression (e.g. an ascmc/angles
                       naming mismatch upstream) into a loud failure.

    Raises:
        ValueError: When ``strict=True`` and ``ascendant`` is ``None``.

    Backward compatibility:
        ``strict`` defaults to ``False``, so all existing callers keep the
        prior behavior (None ascendant → day chart).
    """
    if ascendant is not None:
        # Sun is below horizon (houses 1–6, night) iff its zodiacal longitude
        # lies in the 180° arc starting at ASC and going CCW to DSC.
        # Equivalent: (sun - ASC) mod 360 ∈ [0, 180).
        return (sun_longitude - ascendant) % 360 < 180
    if strict:
        raise ValueError(
            "ascendant required for is_night_chart with strict=True; "
            "got None. The ascendant should come from "
            "western['angles']['Ascendant'] (compute_western_chart()). "
            "A None value here usually means the ascendant key was not "
            "propagated from the western chart result."
        )
    return False


def calculate_wuxing_vector_from_planets(
    bodies: Dict[str, Dict[str, Any]],
    use_retrograde_weight: bool = True,
    ascendant: Optional[float] = None,
    *,
    strict: bool = False,
) -> WuXingVector:
    """Calculate Wu-Xing vector from a set of planetary positions.

    Args:
        bodies:                 Planetary data dict from compute_western_chart().
        use_retrograde_weight:  If True, retrograde planets carry 1.3× weight.
        ascendant:              Ascendant longitude for day/night detection.
                                If None, defaults to day chart (assumed_day quality).
        strict:                 When True, propagate to is_night_chart() so
                                a missing ascendant raises ValueError instead
                                of silently degrading to assumed_day. Used at
                                router-layer call sites that already wire the
                                ascendant from western['angles']['Ascendant'].

    Returns:
        WuXingVector with raw (un-normalized) element scores.
    """
    vector, _ = calculate_wuxing_vector_from_planets_with_ledger(
        bodies,
        use_retrograde_weight=use_retrograde_weight,
        ascendant=ascendant,
        strict=strict,
    )
    return vector


def calculate_wuxing_vector_from_planets_with_ledger(
    bodies: Dict[str, Dict[str, Any]],
    use_retrograde_weight: bool = True,
    ascendant: Optional[float] = None,
    *,
    strict: bool = False,
) -> tuple[WuXingVector, list[dict[str, Any]]]:
    """Like calculate_wuxing_vector_from_planets but also returns per-planet ledger.

    Args:
        bodies:                 Planetary data dict from compute_western_chart().
        use_retrograde_weight:  If True, retrograde planets carry 1.3x weight.
        ascendant:              Ascendant longitude for day/night detection.
                                If None, defaults to day chart (assumed_day quality).
        strict:                 When True, propagate to is_night_chart() so
                                a missing ascendant raises ValueError instead
                                of silently degrading to assumed_day.
    """
    values = [0.0, 0.0, 0.0, 0.0, 0.0]
    ledger: list[dict[str, Any]] = []
    sun_data = bodies.get("Sun", {})
    sun_lon = sun_data.get("longitude", 0)
    night = is_night_chart(sun_lon, ascendant, strict=strict)
    chart_type_quality = "exact" if ascendant is not None else "assumed_day"

    traditional_planets = {"Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"}
    modern_planets = {"Uranus", "Neptune", "Pluto"}

    for planet, data in bodies.items():
        if "error" in data:
            continue
        is_retrograde = data.get("is_retrograde", False)
        element = planet_to_wuxing(planet, night)
        weight = 1.3 if (use_retrograde_weight and is_retrograde) else 1.0
        values[WUXING_INDEX[element]] += weight

        rationale = "Classical rulership"
        if planet == "Mercury":
            chart_type = "night chart" if night else "day chart"
            rationale = f"Dual element — {element} ({chart_type})"

        if planet in traditional_planets:
            category = "traditional"
        elif planet in modern_planets:
            category = "modern_heuristic"
        else:
            category = "experimental"

        entry: dict[str, Any] = {
            "planet": planet,
            "element": element,
            "weight": weight,
            "is_retrograde": is_retrograde,
            "rationale": rationale,
            "category": category,
        }
        if planet == "Mercury":
            entry["chart_type_quality"] = chart_type_quality
        ledger.append(entry)

    return WuXingVector(*values), ledger


# Hidden stems in Earthly Branches (藏干) with traditional Qi weights.
# Main Qi (主气) = 1.0, Middle Qi (中气) = 0.5, Residual Qi (余气) = 0.3
_BRANCH_HIDDEN: Dict[str, List[tuple[str, float]]] = {
    "Zi":   [("Wasser", 1.0)],
    "Chou": [("Erde", 1.0), ("Wasser", 0.5), ("Metall", 0.3)],
    "Yin":  [("Holz", 1.0), ("Feuer", 0.5), ("Erde", 0.3)],
    "Mao":  [("Holz", 1.0)],
    "Chen": [("Erde", 1.0), ("Holz", 0.5), ("Wasser", 0.3)],
    "Si":   [("Feuer", 1.0), ("Metall", 0.5), ("Erde", 0.3)],
    "Wu":   [("Feuer", 1.0), ("Erde", 0.5)],
    "Wei":  [("Erde", 1.0), ("Feuer", 0.5), ("Holz", 0.3)],
    "Shen": [("Metall", 1.0), ("Wasser", 0.5), ("Erde", 0.3)],
    "You":  [("Metall", 1.0)],
    "Xu":   [("Erde", 1.0), ("Metall", 0.5), ("Feuer", 0.3)],
    "Hai":  [("Wasser", 1.0), ("Holz", 0.5)],
}

_STEM_TO_ELEMENT: Dict[str, str] = {
    "Jia": "Holz", "Yi": "Holz",
    "Bing": "Feuer", "Ding": "Feuer",
    "Wu": "Erde", "Ji": "Erde",
    "Geng": "Metall", "Xin": "Metall",
    "Ren": "Wasser", "Gui": "Wasser",
}


def calculate_wuxing_from_bazi(pillars: Dict[str, Dict[str, str]]) -> WuXingVector:
    """Extract Wu-Xing vector from BaZi pillars.

    Each pillar contributes via:
    - Heavenly Stem → direct element (weight 1.0)
    - Earthly Branch → hidden stems with traditional Qi weights

    Supports both English keys (stem/branch) and German keys (stamm/zweig).
    """
    values = [0.0, 0.0, 0.0, 0.0, 0.0]

    for _pillar_name, pillar_data in pillars.items():
        stem = pillar_data.get("stem", pillar_data.get("stamm", ""))
        branch = pillar_data.get("branch", pillar_data.get("zweig", ""))

        if stem in _STEM_TO_ELEMENT:
            values[WUXING_INDEX[_STEM_TO_ELEMENT[stem]]] += 1.0

        for elem, weight in _BRANCH_HIDDEN.get(branch, []):
            values[WUXING_INDEX[elem]] += weight

    return WuXingVector(*values)


def calculate_wuxing_from_bazi_with_ledger(
    pillars: Dict[str, Dict[str, str]],
) -> tuple[WuXingVector, list[dict[str, Any]]]:
    """Extract Wu-Xing vector from BaZi pillars with per-contribution ledger."""
    values = [0.0, 0.0, 0.0, 0.0, 0.0]
    ledger: list[dict[str, Any]] = []
    _QI_LABELS = {1.0: "hidden_main", 0.5: "hidden_middle", 0.3: "hidden_residual"}

    for pillar_name, pillar_data in pillars.items():
        stem = pillar_data.get("stem", pillar_data.get("stamm", ""))
        branch = pillar_data.get("branch", pillar_data.get("zweig", ""))

        if stem in _STEM_TO_ELEMENT:
            element = _STEM_TO_ELEMENT[stem]
            values[WUXING_INDEX[element]] += 1.0
            ledger.append({
                "pillar": pillar_name,
                "source": "stem",
                "stem_name": stem,
                "element": element,
                "weight": 1.0,
                "category": "traditional",
            })

        for elem, weight in _BRANCH_HIDDEN.get(branch, []):
            values[WUXING_INDEX[elem]] += weight
            ledger.append({
                "pillar": pillar_name,
                "source": _QI_LABELS.get(weight, "hidden"),
                "branch_name": branch,
                "element": elem,
                "weight": weight,
                "category": "traditional",
            })

    return WuXingVector(*values), ledger


def calculate_harmony_index(
    western_vector: WuXingVector,
    bazi_vector: WuXingVector,
    method: str = "dot_product",
) -> Dict[str, Any]:
    """Compute the Harmony Index between two Wu-Xing vectors.

    Args:
        western_vector: Vector derived from western planetary positions.
        bazi_vector:    Vector derived from BaZi pillars.
        method:         "dot_product" (default) or "cosine".

    Returns:
        Dict with harmony_index (0–1), interpretation, method, and normalized vectors.

    Raises:
        ValueError: If method is not supported.
    """
    w_norm = western_vector.normalize()
    b_norm = bazi_vector.normalize()

    if method == "dot_product":
        dot = sum(w * b for w, b in zip(w_norm.to_list(), b_norm.to_list()))
        harmony = max(0.0, dot)
    elif method == "cosine":
        mag_w = western_vector.magnitude()
        mag_b = bazi_vector.magnitude()
        if mag_w == 0 or mag_b == 0:
            harmony = 0.0
        else:
            dot = sum(w * b for w, b in zip(western_vector.to_list(), bazi_vector.to_list()))
            harmony = dot / (mag_w * mag_b)
    else:
        raise ValueError(f"Unknown harmony method: {method!r}")

    return {
        "harmony_index":   round(harmony, 4),
        "interpretation":  interpret_harmony(harmony),
        "method":          method,
        "western_vector":  w_norm.to_dict(),
        "bazi_vector":     b_norm.to_dict(),
    }


def interpret_harmony(h: float) -> str:
    """Return a claim-safe diagnostic label for a RAW harmony index value.

    FUF-147 fail-closed containment: the raw H = cos(θ) lies empirically in
    [0.50, 1.0] for real charts (positive orthant), so raw-threshold judgment
    prose ("Starke Resonanz", "Gute Harmonie", …) was structurally always
    positive. Until the calibrated card-pair model (FUF-55B) ships, the raw
    value must never be presented as a user-facing judgment — only as an
    expert diagnostic. Calibrated judgments live in
    ``CalibrationResult.interpretation_band`` (wuxing/calibration.py).
    """
    return (
        f"Rohwert-Diagnostik (unkalibriert): H_raw={h:.2f} — "
        "Expertendiagnostik, kein Nutzerurteil"
    )
