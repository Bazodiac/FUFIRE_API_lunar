"""
routers/fusion.py — Wu-Xing Fusion endpoints.

Endpoints:
  POST /calculate/fusion   — Wu-Xing + Western harmony analysis
  POST /calculate/wuxing   — Wu-Xing vector from planetary positions
  POST /calculate/tst      — True Solar Time calculation
"""
from __future__ import annotations

import logging
from datetime import timezone
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from .. import __version__ as ENGINE_VERSION
from ..bazi import compute_bazi
from ..exc import BaziEngineError
from ..fusion import (
    calculate_wuxing_from_bazi_with_ledger,
    calculate_wuxing_vector_from_planets_with_ledger,
    compute_fusion_analysis,
)
from ..limiter import limiter, tier_limit
from ..provenance import build_provenance, normalize_house_system
from ..time_context import compute_effective_time_context_from_instant
from ..time_utils import AmbiguousTimeChoice, NonexistentTimePolicy, resolve_local_iso
from ..types import BaziInput, Fold
from ..western import compute_western_chart
from ..wuxing.vector import WuXingVector
from .shared import (
    MinimalQualityFlags,
    PrecisionBlock,
    ProvenanceResponse,
    QualityFlags,
    format_pillar,
)
from .western import HouseQuality

_log = logging.getLogger(__name__)

# Version of the planet→element / pillar→element mapping policy exposed by
# /calculate/fusion/vector-map. Bump when the mapping (PLANET_TO_WUXING, hidden
# stems, Qi weights, or the view definitions) changes. Anchors REQ-F-007 /
# GT5; the engine math version is bazi_engine.__version__ (algorithm_version).
FUSION_MAPPING_VERSION = "fufire-wuxing-map-v1"

router = APIRouter(prefix="/calculate", tags=["Fusion / Wu-Xing"])


# ── /calculate/fusion ────────────────────────────────────────────────────────

class FusionRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "1990-06-15T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
            "birth_time_known": True,
        }
    })

    date: str = Field(..., description="ISO 8601 local date time")
    tz: str = Field("Europe/Berlin", description="Timezone name")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    ambiguousTime: AmbiguousTimeChoice = "earlier"
    nonexistentTime: NonexistentTimePolicy = "error"
    birth_time_known: bool = Field(True, description="False if birth time is uncertain — flags hour/signature/ascendant/houses as provisional")
    bazi_pillars: Optional[Dict[str, Dict[str, str]]] = Field(
        None, description="BaZi pillars (auto-computed if omitted)"
    )


class FusionResponse(BaseModel):
    input: Dict[str, Any]
    wu_xing_vectors: Dict[str, Dict[str, float]]
    harmony_index: Dict[str, Any]
    calibration: Optional[Dict[str, Any]] = None
    elemental_comparison: Dict[str, Dict[str, float]]
    cosmic_state: float
    fusion_interpretation: str
    contribution_ledger: Optional[Dict[str, Any]] = None
    house_quality: Optional[HouseQuality] = None
    quality_flags: QualityFlags
    provenance: ProvenanceResponse
    precision: PrecisionBlock


@router.post("/fusion", response_model=FusionResponse)
@limiter.limit(tier_limit)
def calculate_fusion_endpoint(request: Request, req: FusionRequest) -> Dict[str, Any]:
    """Wu-Xing + Western harmony analysis."""
    try:
        dt_local, _ = resolve_local_iso(
            req.date, req.tz,
            ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
        )
        dt_utc = dt_local.astimezone(timezone.utc)
        western_chart = compute_western_chart(dt_utc, req.lat, req.lon)

        pillars = req.bazi_pillars
        if pillars is None:
            fold: Fold = 0 if req.ambiguousTime == "earlier" else 1
            inp = BaziInput(
                birth_local=dt_local.replace(tzinfo=None).isoformat(),
                timezone=req.tz,
                longitude_deg=req.lon,
                latitude_deg=req.lat,
                time_standard="CIVIL",
                day_boundary="midnight",
                strict_local_time=True,
                fold=fold,
            )
            bazi_result = compute_bazi(inp)
            pillars = {
                "year":  format_pillar(bazi_result.pillars.year),
                "month": format_pillar(bazi_result.pillars.month),
                "day":   format_pillar(bazi_result.pillars.day),
                "hour":  format_pillar(bazi_result.pillars.hour),
            }

        ascendant = western_chart.get("angles", {}).get("Ascendant")
        fusion = compute_fusion_analysis(
            birth_utc_dt=dt_utc,
            latitude=req.lat,
            longitude=req.lon,
            bazi_pillars=pillars,
            western_bodies=western_chart["bodies"],
            ascendant=ascendant,
            strict=True,  # router-layer: ascendant must be wired through
        )

        # Merge the western chart's quality_flags with the natal fusion's
        # chart_type_quality. The two come from different sources of truth:
        #   - house_system_*/ephemeris_mode → compute_western_chart()
        #   - chart_type_quality            → compute_fusion_analysis() ledger
        # Combining them here gives B2B callers a single trust signal so
        # they don't need a separate /calculate/western round-trip.
        western_qf = dict(western_chart.get("quality_flags") or {})
        fusion_ledger = fusion.get("contribution_ledger") or {}
        chart_type_quality = fusion_ledger.get("chart_type_quality")
        if chart_type_quality not in ("exact", "assumed_day"):
            chart_type_quality = "exact" if ascendant is not None else "assumed_day"
        western_qf["chart_type_quality"] = chart_type_quality

        return {
            "input": {"date": req.date, "tz": req.tz, "lon": req.lon, "lat": req.lat},
            "wu_xing_vectors":      fusion["wu_xing_vectors"],
            "harmony_index":        fusion["harmony_index"],
            "calibration":          fusion["calibration"],
            "elemental_comparison": fusion["elemental_comparison"],
            "cosmic_state":         fusion["cosmic_state"],
            "fusion_interpretation": fusion["fusion_interpretation"],
            "contribution_ledger": fusion["contribution_ledger"],
            "house_quality": western_chart.get("house_quality"),
            "quality_flags": western_qf,
            "provenance": build_provenance(
                house_system=normalize_house_system(western_chart.get("house_system")),
            ),
            "precision": {
                "birth_time_known": req.birth_time_known,
                "provisional_fields": [] if req.birth_time_known else ["signature", "hour", "ascendant", "houses"],
            },
        }
    except BaziEngineError:
        raise
    except ValueError as exc:
        _log.error("strict ascendant precondition failed: %s", exc, exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "ascendant_unavailable", "message": str(exc)},
        )
    except Exception:
        _log.exception("Calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


# ── /calculate/wuxing ────────────────────────────────────────────────────────

class WxRequest(BaseModel):
    date: str = Field(..., description="ISO 8601 local date time")
    tz: str = Field("Europe/Berlin", description="Timezone name")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    ambiguousTime: AmbiguousTimeChoice = "earlier"
    nonexistentTime: NonexistentTimePolicy = "error"


class WxResponse(BaseModel):
    input: Dict[str, Any]
    wu_xing_vector: Dict[str, float] = Field(
        ..., description="Wu-Xing vector derived from WESTERN PLANETARY positions (normalized). NOT the BaZi Five Elements.",
    )
    dominant_element: str
    basis: Literal["western_planetary"] = Field(
        "western_planetary",
        description="Provenance of the vector: derived from western planetary positions (for the Fusion layer), NOT the BaZi Four Pillars. For the BaZi Wu-Xing use POST /calculate/bazi/wuxing.",
    )
    equation_of_time: float
    true_solar_time: float
    contribution_ledger: Optional[Dict[str, Any]] = None
    provenance: ProvenanceResponse
    quality_flags: MinimalQualityFlags


def _compute_wuxing_response(req: WxRequest) -> Dict[str, Any]:
    """Build the full Wu-Xing response dict for ``req``.

    Single source of truth shared by ``/calculate/wuxing`` and the internal
    aggregation in ``routers/personalize.py`` (REQ-002). No new metaphysics
    math — same western chart + same vector ledger + same dominant-element
    derivation the endpoint always used.
    """
    try:
        dt, _ = resolve_local_iso(
            req.date, req.tz,
            ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
        )
        dt_utc = dt.astimezone(timezone.utc)
        western_chart = compute_western_chart(dt_utc, req.lat, req.lon)
        asc = western_chart.get("angles", {}).get("Ascendant")
        wx_vector, wx_ledger = calculate_wuxing_vector_from_planets_with_ledger(
            western_chart["bodies"], ascendant=asc, strict=True,
        )
        wx_norm = wx_vector.normalize()
        wx_dict = wx_norm.to_dict()
        # FBP-TST-004 (DEV-2026-008): the TST/EoT fields come from the same
        # UTC-axis context as /calculate/tst, the BaZi trace and chronometry,
        # so the four surfaces can no longer drift. (Historically this path
        # called true_solar_time() without the zone offset, i.e. civil + EoT.)
        time_ctx = compute_effective_time_context_from_instant(dt, req.lon)
        # FQ-ATT-02 (T9), AC-02-3: Wu-Xing computes no house cusps of its own
        # (OQ-1 scopes house_system_fallback to house-computing endpoints
        # only) but DOES already construct a real SwissEphBackend via
        # compute_western_chart() above -- reuse that backend's own attested
        # mode rather than constructing a second, unrelated one.
        ephemeris_mode = (western_chart.get("quality_flags") or {}).get("ephemeris_mode")
        return {
            "input": {"date": req.date, "tz": req.tz, "lon": req.lon, "lat": req.lat},
            "wu_xing_vector":  wx_dict,
            "dominant_element": max(wx_dict, key=lambda k: wx_dict[k]),
            "basis":           "western_planetary",
            "equation_of_time": time_ctx.eot_minutes,
            "true_solar_time":  round(time_ctx.tlst_hours, 4),
            "contribution_ledger": {"western": wx_ledger},
            "provenance": build_provenance(
                house_system=normalize_house_system(western_chart.get("house_system")),
            ),
            "quality_flags": {"ephemeris_mode": ephemeris_mode},
        }
    except BaziEngineError:
        raise
    except ValueError as exc:
        _log.error("strict ascendant precondition failed: %s", exc, exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "ascendant_unavailable", "message": str(exc)},
        )
    except Exception:
        _log.exception("Calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


@router.post(
    "/wuxing",
    response_model=WxResponse,
    summary="Wu-Xing vector from WESTERN PLANETARY positions (Fusion input — not BaZi)",
    description=(
        "Wu-Xing element vector derived from **western planetary positions** "
        "(Sun→Fire, Moon→Water, … classical rulership), projected into the "
        "five-element vector space. Its purpose is to be the **western half of "
        "the Fusion** (`POST /calculate/fusion`), where it is compared against "
        "the BaZi vector.\n\n"
        "**This is NOT the person's BaZi Wu-Xing.** A BaZi element/personality "
        "reading must use **`POST /calculate/bazi/wuxing`** (derived from the "
        "Four Pillars). The `dominant_element` here reflects planetary weighting "
        "and will routinely differ from the BaZi dominant element. The response "
        "carries `basis: \"western_planetary\"` to make the provenance explicit."
    ),
)
@limiter.limit(tier_limit)
def calculate_wuxing_endpoint(request: Request, req: WxRequest) -> Dict[str, Any]:
    """Wu-Xing element vector from western planetary positions (Fusion input, NOT BaZi)."""
    return _compute_wuxing_response(req)


# ── /calculate/tst ───────────────────────────────────────────────────────────

class TSTRequest(BaseModel):
    date: str = Field(..., description="ISO 8601 local date time")
    tz: str = Field("Europe/Berlin", description="Timezone name")
    lon: float = Field(..., description="Longitude in degrees")
    ambiguousTime: AmbiguousTimeChoice = "earlier"
    nonexistentTime: NonexistentTimePolicy = "error"


class TSTResponse(BaseModel):
    input: Dict[str, Any]
    civil_time_hours: float
    longitude_correction_hours: float
    equation_of_time_hours: float
    eot_source: str = Field(
        ..., description='Provenance of the equation of time, e.g. "meeus_1998" (FBP-TST-006).',
    )
    true_solar_time_hours: float
    true_solar_time_formatted: str
    provenance: ProvenanceResponse


@router.post("/tst", response_model=TSTResponse)
@limiter.limit(tier_limit)
def calculate_tst_endpoint(request: Request, req: TSTRequest) -> Dict[str, Any]:
    """True Solar Time (TST) calculation.

    Delegates to :func:`bazi_engine.time_context.compute_effective_time_context_from_instant`
    so the endpoint and the BaZi engine's effective-time decomposition
    cannot drift (FBP-01-003 / FBP-01-004).
    """
    try:
        dt, _ = resolve_local_iso(
            req.date, req.tz,
            ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
        )
        # FBP-TST-002: hand over the resolved aware instant (fold-faithful).
        ctx = compute_effective_time_context_from_instant(dt, req.lon)
        civil_hours = (
            ctx.civil_local.hour
            + ctx.civil_local.minute / 60
            + ctx.civil_local.second / 3600
        )
        hours = int(ctx.tlst_hours)
        minutes = int((ctx.tlst_hours - hours) * 60)
        return {
            "input": {"date": req.date, "tz": req.tz, "lon": req.lon},
            "civil_time_hours":             round(civil_hours, 4),
            "longitude_correction_hours":   round(req.lon * 4 / 60, 4),
            "equation_of_time_hours":       round(ctx.eot_minutes / 60.0, 4),
            "eot_source":                   ctx.eot_source,
            "true_solar_time_hours":        round(ctx.tlst_hours, 4),
            "true_solar_time_formatted":    f"{hours:02d}:{minutes:02d}",
            "provenance": build_provenance(),
            # FQ-ATT-02 (T9), AC-02-3, refined 2026-07-01 (user decision): /calculate/tst
            # is pure civil-time / equation-of-time math -- time_context.py touches no
            # Swiss Ephemeris call at all, unlike bazi/wuxing/transit, which construct a
            # real backend as part of their own computation (making a throwaway
            # current_ephemeris_mode() check there genuinely redundant with an
            # already-enforced guarantee). For tst there was no such guarantee to piggyback
            # on -- the throwaway backend construction was a *new* failure mode, not a
            # redundant re-check, and attesting an ephemeris_mode with zero causal bearing
            # on the response is itself a form of the "fake-attested value" risk FQ-ATT-02
            # exists to close. tst intentionally does not expose quality_flags at all.
        }
    except BaziEngineError:
        raise
    except Exception:
        _log.exception("Calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


# ── /calculate/fusion/vector-map (beta) ──────────────────────────────────────

class VectorMapRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "1990-06-15T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
        }
    })

    date: str = Field(..., description="ISO 8601 local date time")
    tz: str = Field("Europe/Berlin", description="Timezone name")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    ambiguousTime: AmbiguousTimeChoice = "earlier"
    nonexistentTime: NonexistentTimePolicy = "error"
    bazi_pillars: Optional[Dict[str, Dict[str, str]]] = Field(
        None, description="BaZi pillars (auto-computed if omitted)"
    )


class SystemViews(BaseModel):
    """Three views of ONE system's raw Wu-Xing vector (German element keys)."""
    raw: Dict[str, float] = Field(..., description="Un-normalized element scores")
    sum_l1: Dict[str, float] = Field(
        ..., description="L1 (S/sum(S)) view — sums to 1 for non-negative vectors"
    )
    l2_cosine: Dict[str, float] = Field(
        ..., description="L2 unit view (the cosine-space vector)"
    )


class VectorMapBlock(BaseModel):
    western_planets: SystemViews
    bazi_pillars: SystemViews


class HarmonyComponents(BaseModel):
    elemental_overlap_h: float = Field(
        ..., description="Dot product of the two sum_l1 vectors; [0,1] for non-negative"
    )
    cosine_similarity: float = Field(
        ..., description="Dot of the two l2_cosine vectors = engine cosmic_state; [0,1]"
    )


class VectorMapMetadata(BaseModel):
    mapping_version: str = Field(..., description="Wu-Xing mapping policy version")
    algorithm_version: str = Field(..., description="Engine build version (bazi_engine.__version__)")


class VectorMapResponse(BaseModel):
    request_id: str
    input: Dict[str, Any]
    vector_map: VectorMapBlock
    harmony: HarmonyComponents
    metadata: VectorMapMetadata


def _system_views(raw: WuXingVector) -> Dict[str, Dict[str, float]]:
    """Three views of a single RAW vector, all from the SAME source:
    raw (un-normalized), sum_l1 (L1), l2_cosine (L2 unit). German keys (GT7)."""
    return {
        "raw":       raw.to_dict(),
        "sum_l1":    raw.sum_l1_normalize().to_dict(),
        "l2_cosine": raw.normalize().to_dict(),
    }


@router.post("/fusion/vector-map", response_model=VectorMapResponse, tags=["Fusion Vector-Map (beta)"])
@limiter.limit(tier_limit)
def calculate_fusion_vector_map_endpoint(
    request: Request, req: VectorMapRequest
) -> Dict[str, Any]:
    """Wu-Xing fusion vector map (beta).

    Exposes the existing deterministic fusion engine as three views per system
    (``raw`` / ``sum_l1`` / ``l2_cosine``, German element keys) plus two
    harmony components. NO new metaphysical math:

    * ``cosine_similarity`` = the engine's existing ``cosmic_state`` (dot of the
      L2-normalized vectors) — reused, not reimplemented (GT2).
    * ``elemental_overlap_h`` = dot product of the two ``sum_l1`` vectors → [0,1].
    * ``trig_coherence`` is DEFERRED (GT3) and intentionally NOT returned.

    All views are derived from the SAME raw vectors the engine computes; the
    ``l2_cosine`` view equals ``compute_fusion_analysis``'s ``wu_xing_vectors``.
    """
    try:
        dt_local, _ = resolve_local_iso(
            req.date, req.tz,
            ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
        )
        dt_utc = dt_local.astimezone(timezone.utc)
        western_chart = compute_western_chart(dt_utc, req.lat, req.lon)

        pillars = req.bazi_pillars
        if pillars is None:
            fold: Fold = 0 if req.ambiguousTime == "earlier" else 1
            inp = BaziInput(
                birth_local=dt_local.replace(tzinfo=None).isoformat(),
                timezone=req.tz,
                longitude_deg=req.lon,
                latitude_deg=req.lat,
                time_standard="CIVIL",
                day_boundary="midnight",
                strict_local_time=True,
                fold=fold,
            )
            bazi_result = compute_bazi(inp)
            pillars = {
                "year":  format_pillar(bazi_result.pillars.year),
                "month": format_pillar(bazi_result.pillars.month),
                "day":   format_pillar(bazi_result.pillars.day),
                "hour":  format_pillar(bazi_result.pillars.hour),
            }

        ascendant = western_chart.get("angles", {}).get("Ascendant")

        # RAW (un-normalized) vectors — the SAME inputs compute_fusion_analysis
        # uses internally — built BEFORE any normalization.
        raw_west, _ = calculate_wuxing_vector_from_planets_with_ledger(
            western_chart["bodies"], ascendant=ascendant, strict=True,
        )
        raw_bazi, _ = calculate_wuxing_from_bazi_with_ledger(pillars)

        # Reuse the engine for cosine_similarity (== cosmic_state, GT2) — do
        # NOT reimplement the metric. Same pillars/bodies/ascendant/strict.
        fusion = compute_fusion_analysis(
            birth_utc_dt=dt_utc,
            latitude=req.lat,
            longitude=req.lon,
            bazi_pillars=pillars,
            western_bodies=western_chart["bodies"],
            ascendant=ascendant,
            strict=True,
        )

        west_l1 = raw_west.sum_l1_normalize()
        bazi_l1 = raw_bazi.sum_l1_normalize()
        elemental_overlap_h = sum(
            w * b for w, b in zip(west_l1.to_list(), bazi_l1.to_list())
        )

        return {
            "request_id": getattr(request.state, "request_id", "unknown"),
            "input": {"date": req.date, "tz": req.tz, "lon": req.lon, "lat": req.lat},
            "vector_map": {
                "western_planets": _system_views(raw_west),
                "bazi_pillars":    _system_views(raw_bazi),
            },
            "harmony": {
                "elemental_overlap_h": round(elemental_overlap_h, 4),
                # cosine_similarity = the engine's cosmic_state (GT2 — reused).
                "cosine_similarity":   fusion["cosmic_state"],
            },
            "metadata": {
                "mapping_version":   FUSION_MAPPING_VERSION,
                "algorithm_version": ENGINE_VERSION,
            },
        }
    except BaziEngineError:
        raise
    except ValueError as exc:
        _log.error("strict ascendant precondition failed: %s", exc, exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "ascendant_unavailable", "message": str(exc)},
        )
    except Exception:
        _log.exception("Calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")
