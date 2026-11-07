"""
provenance.py — Computation provenance metadata for Datenwahrheit.

Every /calculate/* response includes a provenance block documenting
which engine version, ephemeris, ruleset, and parameters produced the result.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from . import __version__
from .exc import EphemerisUnavailableError

WUXING_PARAMETER_SET: Dict[str, Any] = {
    "version": "1.2.0",
    # 1.2.0 (2026-11-07): western Fusion vector = sign element × consensus
    # matrix × tier weight; no retrograde factor, no Mercury day/night rule.
    # Literal copy of bazi_engine.wuxing.constants (this module is Layer 1 and
    # may not import Layer 4); tests/test_parameter_set.py pins the two equal.
    "retrograde_weight": 1.0,
    "western_mapping_id": "sign-element-consensus-v1",
    "western_weighting_id": "body-tier-q0.3-v1",
    "western_tier_weight": {"1": 1.0, "2": 0.3, "3": 0.09, "4": 0.027},
    "western_body_tier": {
        "Sun": 1, "Moon": 1, "Ascendant": 1,
        "Mercury": 2, "Venus": 2, "Mars": 2,
        "Jupiter": 3, "Saturn": 3,
        "Uranus": 4, "Neptune": 4, "Pluto": 4,
        "Chiron": 4, "Lilith": 4, "NorthNode": 4,
    },
    "western_excluded_bodies": ["TrueNorthNode"],
    "hidden_stem_main_qi": 1.0,
    "hidden_stem_middle_qi": 0.5,
    "hidden_stem_residual_qi": 0.3,
    "stem_weight": 1.0,
    "mercury_dual_rule": "none",
    "harmony_method": "dot_product",
    "aspect_orb_model": "differentiated_v1",
    "aspect_base_orbs": {
        "Sun": 10.0, "Moon": 10.0,
        "Mercury": 7.0, "Venus": 7.0, "Mars": 7.0,
        "Jupiter": 8.0, "Saturn": 8.0,
        "Uranus": 5.0, "Neptune": 5.0, "Pluto": 5.0,
        "Chiron": 3.0, "Lilith": 2.0,
        "NorthNode": 3.0, "TrueNorthNode": 3.0,
    },
    "aspect_factors": {
        "conjunction": 1.0,
        "sextile": 0.75,
        "square": 0.875,
        "trine": 1.0,
        "opposition": 1.0,
    },
    "soulprint_weights": {
        "sun": 1.0,
        "moon": 0.8,
        "ascendant": 0.6,
        "personal_planet": 0.4,
        "wuxing_sector": 0.5,
    },
    "wuxing_sector_mapping": {
        "Holz": [3, 4],
        "Feuer": [4, 5],
        "Erde": [1, 7],
        "Metall": [6, 9],
        "Wasser": [8, 11],
    },
    "transit_planet_weights": {
        "sun": 1.0, "moon": 0.5,
        "mercury": 0.6, "venus": 0.7, "mars": 0.8,
        "jupiter": 1.2, "saturn": 1.5,
        "uranus": 1.5, "neptune": 1.8, "pluto": 2.0,
    },
}


HOUSE_SYSTEM_LABELS: Dict[str, str] = {
    "P": "placidus",
    "O": "porphyry",
    "W": "whole_sign",
}


def normalize_house_system(code: Optional[str]) -> str:
    """Map single-char house system code to stable label for provenance.

    ``compute_western_chart()`` returns ``"P"``, ``"O"``, or ``"W"``
    depending on latitude-driven fallback.  We normalise to a human-readable
    lowercase label so the provenance block is always consistent.
    """
    if code is None:
        return "unknown"
    return HOUSE_SYSTEM_LABELS.get(code, code.lower())


def _detect_tzdb_version() -> str:
    """Detect the pinned IANA tzdata version (FQ-ATT-02, AC-02-1).

    ``tzdata`` is a pinned, declared dependency (``pyproject.toml`` /
    ``requirements.lock`` / ``uv.lock`` -- T7) as of this increment, so this
    must always resolve to a real IANA version string in any deployed
    environment.

    OQ-7 (decided): if detection still somehow fails here (e.g. ``tzdata``
    is missing/corrupted at runtime despite being a pinned, locked
    dependency), this **raises** ``EphemerisUnavailableError`` instead of
    silently returning the literal placeholder string ``"unknown"`` --
    consistent with this repo's "fail visibly, no masking" development
    principle (``CLAUDE.md``). This is a deliberate failure-mode semantics
    change from the pre-T7/T8 behavior: previously a degraded 200 response
    carried a bad placeholder string; now this is a 503 on an edge case
    that should not occur once ``tzdata`` is correctly pinned and locked --
    flagged explicitly for the code-review gate (T12), not silently
    shipped.
    """
    try:
        from importlib.metadata import version as pkg_version
        return pkg_version("tzdata")
    except Exception:
        pass
    try:
        import importlib.resources as ir
        tzdata = ir.files("tzdata")
        zi_dir = tzdata / "zoneinfo"
        tz_file = zi_dir / "tzdata.zi"
        if hasattr(tz_file, "read_text"):
            first_line = tz_file.read_text().split("\n", 1)[0]
            if first_line.startswith("# version"):
                return first_line.split()[-1]
    except Exception:
        pass
    raise EphemerisUnavailableError(
        "Could not detect the installed tzdata package version via "
        "importlib.metadata or the tzdata.zi resource file. tzdata is a "
        "pinned, required dependency (pyproject.toml) -- this indicates it "
        "is missing or corrupted in the deployed environment, not a "
        "cosmetic gap. Refusing to silently report 'unknown' "
        "(PRD fufire-premium-verification-ci FQ-ATT-02 §3.4/§9 OQ-7).",
        detail={"probe": "importlib.metadata.version('tzdata')"},
    )


def _detect_ephemeris_id() -> str:
    """Identify the active ephemeris backend."""
    mode = os.environ.get("EPHEMERIS_MODE", "SWIEPH").upper()
    if mode == "MOSEPH":
        return "moshier_analytic"
    # Default: Swiss Ephemeris with sepl_18 data files
    return "swieph_sepl18"


@dataclass(frozen=True)
class Provenance:
    """Immutable provenance record attached to every /calculate/* response."""
    engine_version: str
    parameter_set_id: str
    ruleset_id: str
    ephemeris_id: str
    tzdb_version_id: str
    house_system: str
    zodiac_mode: str
    computation_timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "parameter_set_id": self.parameter_set_id,
            "ruleset_id": self.ruleset_id,
            "ephemeris_id": self.ephemeris_id,
            "tzdb_version_id": self.tzdb_version_id,
            "house_system": self.house_system,
            "zodiac_mode": self.zodiac_mode,
            "computation_timestamp": self.computation_timestamp,
        }


def build_provenance(
    *,
    parameter_set_id: str = "default_v1",
    ruleset_id: str = "traditional_bazi_2026",
    house_system: str = "placidus",
    zodiac_mode: str = "tropical",
) -> Dict[str, Any]:
    """Build a provenance dict for inclusion in API responses.

    Parameters can be overridden per-endpoint when the request specifies
    a non-default house system or zodiac mode.
    """
    prov = Provenance(
        engine_version=__version__,
        parameter_set_id=parameter_set_id,
        ruleset_id=ruleset_id,
        ephemeris_id=_detect_ephemeris_id(),
        tzdb_version_id=_detect_tzdb_version(),
        house_system=house_system,
        zodiac_mode=zodiac_mode,
        computation_timestamp=datetime.now(timezone.utc).isoformat(),
    )
    result = prov.to_dict()
    result["parameter_set"] = WUXING_PARAMETER_SET
    return result
