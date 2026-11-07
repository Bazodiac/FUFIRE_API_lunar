"""
routers/chart.py — POST /chart (combined BaZi + Western + Wu-Xing chart)
"""
from __future__ import annotations

import os
from datetime import timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import __version__ as _ENGINE_VERSION
from ..bafe import validate_request as bafe_validate_request
from ..bazi import compute_bazi
from ..constants import ANIMALS, BRANCHES, STEMS
from ..exc import BaziEngineError
from ..fusion import (
    calculate_harmony_index,
    calculate_wuxing_from_bazi,
    calculate_wuxing_vector_from_planets,
)
from ..limiter import limiter, tier_limit
from ..provenance import build_provenance, normalize_house_system
from ..time_context import compute_effective_time_context_from_instant
from ..time_utils import AmbiguousTimeChoice, LocalTimeError, NonexistentTimePolicy, resolve_local_iso
from ..types import BaziInput, Fold, Pillar
from ..western import compute_western_chart
from .shared import STEM_TO_ELEMENT, ZODIAC_SIGNS_DE, ProvenanceResponse, QualityFlags

router = APIRouter(tags=["Chart"])

_BUILD_VERSION = os.environ.get("BUILD_VERSION", _ENGINE_VERSION)

ZODIAC_SIGNS_EN = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]


# ── Request / Response models ─────────────────────────────────────────────────

class ChartComputeRequest(BaseModel):
    local_datetime: str = Field(..., description="ISO 8601 local datetime")
    tz_id: str = Field("Europe/Berlin", description="IANA timezone name")
    geo_lon_deg: float = Field(13.4050, ge=-180.0, le=180.0, description="Geographic longitude in degrees")
    geo_lat_deg: float = Field(52.5200, ge=-90.0, le=90.0, description="Geographic latitude in degrees")
    dst_policy: Literal["error", "earlier", "later"] = Field("error")
    bodies: Optional[List[str]] = Field(None, description="Filter planetary bodies (default: all)")
    include_validation: bool = Field(False)
    time_standard: Literal["CIVIL", "LMT", "TLST"] = Field("CIVIL")
    day_boundary: Literal["midnight", "zi"] = Field("midnight")


class TimeScaleQuality(BaseModel):
    tlst: str

class TimeScales(BaseModel):
    utc: str
    civil_local: str
    jd_ut: float
    tlst_hours: float
    eot_min: float
    dst_status: str
    dst_fold: int
    tz_abbrev: str
    quality: TimeScaleQuality

class Position(BaseModel):
    name: str
    longitude_deg: Optional[float] = None
    latitude_deg: Optional[float] = None
    speed_deg_per_day: Optional[float] = None
    distance_au: Optional[float] = None
    is_retrograde: bool = False
    sign_index: int
    sign_name: str
    sign_name_de: str
    degree_in_sign: Optional[float] = None

class PillarSpec(BaseModel):
    stem_index: int
    branch_index: int
    stem: str
    branch: str
    animal: str
    element: str

class BaziPillars(BaseModel):
    year: PillarSpec
    month: PillarSpec
    day: PillarSpec
    hour: PillarSpec

class BaziDates(BaseModel):
    birth_local: str
    birth_utc: str
    lichun_local: str

class BaziTransition(BaseModel):
    solar_year: int
    is_before_lichun: bool
    lichun_year_start: str
    lichun_next: Optional[str] = None

class BaziSection(BaseModel):
    ruleset_id: str
    pillars: BaziPillars
    day_master: str
    dates: BaziDates
    transition: Optional[BaziTransition] = None
    # FBP-02-005: Phase-1 router clamp removed. ``time_standard_used``
    # now equals ``time_standard_requested`` for any of the three legal
    # values (CIVIL / LMT / TLST). The requested/used split is kept for
    # backward compatibility with Phase-1 consumers; Optional remains
    # because /v1 callers that don't set time_standard see ``None``.
    time_standard_requested: Optional[Literal["CIVIL", "LMT", "TLST"]] = None
    time_standard_used: Optional[Literal["CIVIL", "LMT", "TLST"]] = None

class WuXingDistribution(BaseModel):
    Holz: float
    Feuer: float
    Erde: float
    Metall: float
    Wasser: float

class WuXingSection(BaseModel):
    from_planets: WuXingDistribution
    from_bazi: WuXingDistribution
    harmony_index: float
    dominant_planet: str
    dominant_bazi: str

class ValidationResult(BaseModel):
    ok: bool
    error: Optional[str] = None

class ChartResponse(BaseModel):
    engine_version: str
    parameter_set_id: str
    time_scales: TimeScales
    positions: List[Position]
    bazi: BaziSection
    wuxing: WuXingSection
    houses: Dict[str, float]
    angles: Dict[str, float]
    quality_flags: QualityFlags
    provenance: ProvenanceResponse
    validation: Optional[ValidationResult] = None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _format_pillar_spec(pillar: Pillar) -> Dict[str, Any]:
    stem = STEMS[pillar.stem_index]
    branch = BRANCHES[pillar.branch_index]
    return {
        "stem_index": pillar.stem_index,
        "branch_index": pillar.branch_index,
        "stem": stem,
        "branch": branch,
        "animal": ANIMALS[pillar.branch_index],
        "element": STEM_TO_ELEMENT[stem],
    }


# ── Endpoint ─────────────────────────────────────────────────────────────────

@router.post("/chart", response_model=ChartResponse)
@limiter.limit(tier_limit)
def chart_endpoint(request: Request, req: ChartComputeRequest) -> Dict[str, Any]:
    """Combined chart: Western positions + BaZi pillars + time scales + Wu-Xing."""
    try:
        if req.dst_policy == "error":
            ambiguous: AmbiguousTimeChoice = "earlier"
            nonexistent: NonexistentTimePolicy = "error"
        elif req.dst_policy == "earlier":
            ambiguous = "earlier"
            nonexistent = "shift_forward"
        else:
            ambiguous = "later"
            nonexistent = "shift_forward"

        dt, time_res = resolve_local_iso(
            req.local_datetime, req.tz_id,
            ambiguous=ambiguous, nonexistent=nonexistent,
        )
        dt_utc = dt.astimezone(timezone.utc)

        # Western chart
        western = compute_western_chart(dt_utc, req.geo_lat_deg, req.geo_lon_deg)
        bodies_raw = western.get("bodies", {})

        positions = []
        for name, body in bodies_raw.items():
            if req.bodies and name not in req.bodies:
                continue
            sign_idx = int(body.get("zodiac_sign", 0))
            positions.append({
                "name": name,
                "longitude_deg": body.get("longitude"),
                "latitude_deg": body.get("latitude"),
                "speed_deg_per_day": body.get("speed"),
                "distance_au": body.get("distance"),
                "is_retrograde": body.get("is_retrograde", False),
                "sign_index": sign_idx,
                "sign_name": ZODIAC_SIGNS_EN[sign_idx],
                "sign_name_de": ZODIAC_SIGNS_DE[sign_idx],
                "degree_in_sign": body.get("degree_in_sign"),
            })

        # BaZi pillars
        fold: Fold = 0 if ambiguous == "earlier" else 1
        # FBP-02-005 — Phase-1 router clamp removed. The chart endpoint
        # forwards TLST verbatim to compute_bazi(), which now derives
        # hour pillars from True Local Solar Time directly.
        engine_time_standard = req.time_standard
        bazi_input = BaziInput(
            birth_local=dt.replace(tzinfo=None).isoformat(),
            timezone=req.tz_id,
            longitude_deg=req.geo_lon_deg,
            latitude_deg=req.geo_lat_deg,
            time_standard=engine_time_standard,
            day_boundary=req.day_boundary,
            strict_local_time=True,
            fold=fold,
        )
        bazi_result = compute_bazi(bazi_input)

        bazi_section = {
            "ruleset_id": "standard_bazi_2026",
            "pillars": {
                "year":  _format_pillar_spec(bazi_result.pillars.year),
                "month": _format_pillar_spec(bazi_result.pillars.month),
                "day":   _format_pillar_spec(bazi_result.pillars.day),
                "hour":  _format_pillar_spec(bazi_result.pillars.hour),
            },
            "day_master": STEMS[bazi_result.pillars.day.stem_index],
            "dates": {
                "birth_local":  bazi_result.birth_local_dt.isoformat(),
                "birth_utc":    bazi_result.birth_utc_dt.isoformat(),
                "lichun_local": bazi_result.lichun_local_dt.isoformat(),
            },
            "transition": {
                "solar_year": bazi_result.solar_year,
                "is_before_lichun": bazi_result.is_before_lichun,
                "lichun_year_start": bazi_result.lichun_local_dt.isoformat(),
                "lichun_next": bazi_result.lichun_next_local_dt.isoformat() if bazi_result.lichun_next_local_dt else None,
            },
            # FBP-01-001 (I-P1-1 follow-up): surface what the user
            # requested vs what the engine actually used for pillar
            # derivation. Mirrors the derivation_trace.hour fields on
            # /calculate/bazi. With the Phase-1 router clamp, TLST
            # requests produce LMT-derived pillars; consumers need a
            # way to tell that from a literal LMT request.
            "time_standard_requested": req.time_standard,
            "time_standard_used":      engine_time_standard,
        }

        # Wu-Xing
        wuxing_planet = calculate_wuxing_vector_from_planets(bodies_raw)
        bazi_pillars_for_wuxing = {
            p: {"stem": STEMS[getattr(bazi_result.pillars, p).stem_index],
                "branch": BRANCHES[getattr(bazi_result.pillars, p).branch_index]}
            for p in ("year", "month", "day", "hour")
        }
        wuxing_bazi = calculate_wuxing_from_bazi(bazi_pillars_for_wuxing)
        harmony_result = calculate_harmony_index(wuxing_planet, wuxing_bazi)
        element_names = ["Holz", "Feuer", "Erde", "Metall", "Wasser"]
        dominant_planet = element_names[wuxing_planet.to_list().index(max(wuxing_planet.to_list()))]
        dominant_bazi   = element_names[wuxing_bazi.to_list().index(max(wuxing_bazi.to_list()))]

        wuxing_section = {
            "from_planets": wuxing_planet.to_dict(),
            "from_bazi":    wuxing_bazi.to_dict(),
            "harmony_index": harmony_result["harmony_index"],
            "dominant_planet": dominant_planet,
            "dominant_bazi":   dominant_bazi,
        }

        # Time scales — FBP-TST-004 (DEV-2026-008): same UTC-axis context as
        # /calculate/tst, the BaZi trace and chronometry (was civil + EoT).
        time_ctx = compute_effective_time_context_from_instant(dt, req.geo_lon_deg)
        eot_min = time_ctx.eot_minutes
        tst_hours = time_ctx.tlst_hours

        time_scales: Dict[str, Any] = {
            "utc":         time_res.resolved_utc_iso,
            "civil_local": time_res.resolved_local_iso,
            "jd_ut":       western.get("jd_ut"),
            "tlst_hours":  round(tst_hours, 6),
            "eot_min":     round(eot_min, 4),
            "dst_status":  time_res.status,
            "dst_fold":    time_res.fold,
            "tz_abbrev":   time_res.tz_abbrev,
            "quality":     {"tlst": "ok"},
        }

        # Optional validation embed
        validation = None
        if req.include_validation:
            validate_payload: Dict[str, Any] = {
                "engine_config": {
                    "branch_coordinate_convention": "SHIFT_BOUNDARIES",
                    "zi_apex_deg": 270.0,
                    "branch_width_deg": 30.0,
                },
                "birth_event": {
                    "local_datetime": req.local_datetime,
                    "tz_id": req.tz_id,
                    "geo_lon_deg": req.geo_lon_deg,
                    "geo_lat_deg": req.geo_lat_deg,
                },
            }
            try:
                validation = bafe_validate_request(validate_payload)
            except Exception:
                validation = {"ok": False, "error": "Validation unavailable"}

        response: Dict[str, Any] = {
            "engine_version":   _BUILD_VERSION,
            "parameter_set_id": "pz_2026_02_core",
            "time_scales":      time_scales,
            "positions":        positions,
            "bazi":             bazi_section,
            "wuxing":           wuxing_section,
            "houses":           western.get("houses"),
            "angles":           western.get("angles"),
            # FQ-ATT-02 (T9): /chart computes real house cusps via
            # compute_western_chart() above -- confirmed gap (was
            # completely absent), same class as WesternResponse. Reuse the
            # SAME quality_flags dict compute_western_chart() already built
            # (house_system_fallback/_requested/_used + ephemeris_mode) --
            # no second backend, no re-derivation.
            "quality_flags":    western.get("quality_flags"),
            "provenance": build_provenance(
                house_system=normalize_house_system(western.get("house_system")),
            ),
        }
        if validation is not None:
            response["validation"] = validation
        return response

    except LocalTimeError as e:
        raise HTTPException(status_code=422, detail={
            "error": str(e), "type": "dst_error",
            "hint": "Use dst_policy='earlier' or 'later' to auto-resolve.",
        })
    except BaziEngineError:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Internal calculation error")
