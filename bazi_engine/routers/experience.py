"""
routers/experience.py — Experience API endpoints.

POST /experience/bootstrap        — Full profile bootstrap from birth data.
POST /experience/signature-delta  — Incremental signature update from quiz answer.
POST /experience/daily            — Daily horoscope with fusion narrative.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import __version__

# Core compute modules
from ..bazi import compute_bazi
from ..constants import BRANCHES, STEMS
from ..exc import BaziEngineError, CalculationError
from ..fusion import compute_fusion_analysis

# Impact engine imports (for include=["impact"])
from ..impact import find_active_planets
from ..impact_harmony import (
    build_evidence,
    build_resonance_badges,
    classify_day_mode,
    compute_drivers,
    compute_harmony_index,
    compute_intensity,
    find_top_sector,
    natal_wuxing_vector,
    transit_wuxing_vector,
)
from ..impact_resonance import day_master_element, enrich_active_planets
from ..impact_types import ImpactResponse
from ..limiter import limiter, tier_limit
from ..provenance import build_provenance, normalize_house_system
from ..services.daily_eastern import generate_eastern_daily
from ..services.daily_fusion import generate_fusion_daily
from ..services.daily_western import generate_western_daily
from ..services.quiz_affinity import resolve_quiz_sectors
from ..services.signature_blueprint import compute_signature_blueprint

# Experience services
from ..services.soulprint import compute_soulprint
from ..services.space_weather import compute_space_weather_score, fetch_space_weather
from ..transit import ZODIAC_SIGNS, compute_transit_now
from ..types import BaziInput
from ..western import compute_western_chart
from .shared import ProvenanceResponse, QualityFlags

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/experience", tags=["Experience"])

_SIGN_DE = {
    "aries": "Widder", "taurus": "Stier", "gemini": "Zwillinge",
    "cancer": "Krebs", "leo": "Loewe", "virgo": "Jungfrau",
    "libra": "Waage", "scorpio": "Skorpion", "sagittarius": "Schuetze",
    "capricorn": "Steinbock", "aquarius": "Wassermann", "pisces": "Fische",
}


# ── Shared models ────────────────────────────────────────────────────────────

class BirthInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Birth date YYYY-MM-DD")
    time: str = Field(..., pattern=r"^\d{2}:\d{2}:\d{2}$", description="Birth time HH:MM:SS")
    tz: str = Field(..., description="IANA timezone identifier")
    lat: float = Field(..., ge=-90, le=90, description="Latitude")
    lon: float = Field(..., ge=-180, le=180, description="Longitude")
    place_label: Optional[str] = Field(None, description="Human-readable place name")
    birth_time_known: bool = Field(
        True,
        description=(
            "Set False when the birth time is not authoritatively known and "
            "the supplied `time` is a placeholder. The engine will treat the "
            "ascendant/houses/MC as provisional and force "
            "`chart_type_quality=\"assumed_day\"` regardless of the computed "
            "ascendant. Default: True (Phase A behaviour preserved). "
            "Audit: forbids silent assumed_day — callers must opt in explicitly."
        ),
    )

    @field_validator("date")
    @classmethod
    def validate_real_date(cls, v: str) -> str:
        from datetime import datetime as _dt
        try:
            _dt.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date: {v}")
        return v

    @field_validator("time")
    @classmethod
    def validate_real_time(cls, v: str) -> str:
        from datetime import datetime as _dt
        try:
            _dt.strptime(v, "%H:%M:%S")
        except ValueError:
            raise ValueError(f"Invalid time: {v}")
        return v


class VisualParams(BaseModel):
    symmetry: float = Field(..., ge=0, le=1)
    curvature: float = Field(..., ge=0, le=1)
    angularity: float = Field(..., ge=0, le=1)
    density: float = Field(..., ge=0, le=1)
    contrast: float = Field(..., ge=0, le=1)
    orbit_count: int = Field(..., ge=1, le=7)


class SignatureBlueprint(BaseModel):
    seed: str
    visual: Optional[VisualParams] = None
    elements: Optional[Dict[str, float]] = None


class QuizAnswer(BaseModel):
    keyword: str


class ProfileSummary(BaseModel):
    sun_sign: str
    moon_sign: str
    ascendant_sign: str
    day_master: str
    harmony_index: float = Field(..., ge=0, le=1)


class MetaInfo(BaseModel):
    engine_version: str
    generated_at: Optional[str] = None


# ── Sector list helpers ──────────────────────────────────────────────────────

def _validate_sectors_01(v: List[float]) -> List[float]:
    for i, val in enumerate(v):
        if val < 0 or val > 1:
            raise ValueError(f"Element {i} = {val} not in range [0, 1]")
    return v


# ── Bootstrap ────────────────────────────────────────────────────────────────

class BootstrapRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    birth: BirthInput
    locale: str = "de-DE"


class BootstrapResponse(BaseModel):
    profile: ProfileSummary
    soulprint_sectors: List[float] = Field(..., min_length=12, max_length=12)
    signature_blueprint: SignatureBlueprint
    meta: MetaInfo


# ── Signature Delta ──────────────────────────────────────────────────────────

class SignatureDeltaRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    soulprint_sectors: List[float] = Field(..., min_length=12, max_length=12)
    signature_blueprint: SignatureBlueprint
    quiz_answer: QuizAnswer

    @field_validator("soulprint_sectors")
    @classmethod
    def validate_soulprint(cls, v: List[float]) -> List[float]:
        return _validate_sectors_01(v)


class SignatureDelta(BaseModel):
    curvature: float
    contrast: float
    density: float


class SignatureDeltaResponse(BaseModel):
    quiz_sectors: List[float] = Field(..., min_length=12, max_length=12)
    signature_delta: SignatureDelta
    signature_blueprint: SignatureBlueprint


# ── Daily ────────────────────────────────────────────────────────────────────

class DailyPillar(BaseModel):
    stem: str
    branch: str


class DailyEvidence(BaseModel):
    transit_sectors: Optional[List[int]] = None
    natal_focus: Optional[List[str]] = None
    day_master: Optional[str] = None
    daily_pillar: Optional[DailyPillar] = None
    relation_to_day_master: Optional[str] = None
    jieqi: Optional[str] = None
    weekday: Optional[str] = None


class DailySection(BaseModel):
    summary: str
    themes: List[str]
    caution: str
    opportunity: str
    evidence: DailyEvidence
    jieqi_note: Optional[str] = None
    weekday_note: Optional[str] = None


class DailyFusion(BaseModel):
    summary: str
    synthesis: str
    action: str
    pushworthy: bool
    push_text: Optional[str] = None
    jieqi_note: Optional[str] = None
    weekday_note: Optional[str] = None


class DailyRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    birth: BirthInput
    soulprint_sectors: List[float] = Field(..., min_length=12, max_length=12)
    quiz_sectors: List[float] = Field(..., min_length=12, max_length=12)
    target_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    locale: str = "de-DE"
    include: Optional[List[str]] = Field(
        default=None,
        description='Optional includes. Currently supports: ["impact"].',
    )

    @field_validator("soulprint_sectors", "quiz_sectors")
    @classmethod
    def validate_sector_values(cls, v: List[float]) -> List[float]:
        return _validate_sectors_01(v)

    @field_validator("target_date")
    @classmethod
    def validate_target_date(cls, v: str) -> str:
        from datetime import datetime as _dt
        try:
            _dt.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date: {v}")
        return v


class DailyResponse(BaseModel):
    date: str
    western: DailySection
    eastern: DailySection
    fusion: DailyFusion
    chart_type_quality: Literal["exact", "assumed_day"] = Field(
        default="assumed_day",
        description=(
            "DEPRECATED: alias for quality_flags.chart_type_quality. "
            "Maintained for backward compatibility with Phase A consumers "
            "(Bazodiac frontend, ElevenLabs proxy). Read "
            "quality_flags.chart_type_quality going forward — this field "
            "will be removed once downstream consumers migrate."
        ),
    )
    quality_flags: QualityFlags = Field(
        ...,
        description=(
            "Canonical trust signal for the natal chart powering this "
            "daily reading. Combines the house-system fallback + "
            "ephemeris-mode signals from the western chart with the "
            "chart_type_quality value from the natal fusion ledger. "
            "Surfaced here so B2B callers can read it without an extra "
            "/v1/calculate/western or /v1/calculate/fusion round-trip."
        ),
    )
    provenance: ProvenanceResponse = Field(
        ...,
        description=(
            "FQ-ATT-02 (T9): confirmed gap -- previously the natal "
            "provenance backing this daily reading flowed only through "
            "the internal profile computation, with no top-level field "
            "surfacing ephemeris_id/tzdb_version_id to the caller. Mirrors "
            "the same house_system-aware build_provenance() call the "
            "western chart above already used internally."
        ),
    )
    meta: MetaInfo
    impact: Optional[ImpactResponse] = Field(
        default=None,
        description="Impact data (included when request has include=['impact']).",
    )


# ── Helpers ──────────────────────────────────────────────────────────────────

def _birth_to_iso(birth: BirthInput) -> str:
    """Convert BirthInput date+time to ISO local string for BaziInput."""
    return f"{birth.date}T{birth.time}"


def _select_profile_harmony(fusion: Dict[str, Any]) -> float:
    """Select the user-facing harmony value from a fusion result (FUF-147).

    Fail-closed: only the calibrated value may drive user-facing output. If
    ``h_calibrated`` is missing, fall back to the neutral 0.5 — never to the
    raw harmony index (raw H is empirically always ≥ 0.5 and would silently
    reintroduce positive-judgment values).
    """
    cal = fusion.get("calibration", {})
    harmony_index = cal.get("h_calibrated", 0.5)
    if not isinstance(harmony_index, (int, float)):
        harmony_index = 0.5
    return max(0.0, min(1.0, float(harmony_index)))


def _compute_astro_profile(birth: BirthInput) -> Dict[str, Any]:
    """Run BaZi + Western + Fusion calculations from birth data.

    Returns dict with keys: bazi_result, western_chart, fusion, day_master,
    sun_sign_idx, moon_sign_idx, asc_sign_idx, personal_planets, wuxing_vector,
    harmony_index.
    """
    birth_iso = _birth_to_iso(birth)

    # BaZi calculation
    bazi_inp = BaziInput(
        birth_local=birth_iso,
        timezone=birth.tz,
        longitude_deg=birth.lon,
        latitude_deg=birth.lat,
    )
    try:
        bazi_result = compute_bazi(bazi_inp)
    except BaziEngineError:
        # Let domain-specific errors bubble up to the global error handler
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "computation_error", "message": f"BaZi calculation failed: {exc}"},
        )
    pillars = bazi_result.pillars
    day_master = STEMS[pillars.day.stem_index]

    # Pillars as dict for fusion
    bazi_pillars_dict = {
        "year": {
            "stem": STEMS[pillars.year.stem_index],
            "branch": BRANCHES[pillars.year.branch_index],
        },
        "month": {
            "stem": STEMS[pillars.month.stem_index],
            "branch": BRANCHES[pillars.month.branch_index],
        },
        "day": {
            "stem": STEMS[pillars.day.stem_index],
            "branch": BRANCHES[pillars.day.branch_index],
        },
        "hour": {
            "stem": STEMS[pillars.hour.stem_index],
            "branch": BRANCHES[pillars.hour.branch_index],
        },
    }

    # Western chart
    try:
        western = compute_western_chart(
            birth_utc_dt=bazi_result.birth_utc_dt,
            lat=birth.lat,
            lon=birth.lon,
        )
    except BaziEngineError:
        # FQ-ATT-02 (T9): let domain-specific errors (notably
        # EphemerisUnavailableError under a forced-MOSEPH condition) bubble
        # up to the global error handler for a real 503, the same way the
        # compute_bazi() step above already does -- previously this bare
        # `except Exception` flattened EphemerisUnavailableError into a
        # generic 500 "computation_error", hiding the attestation failure
        # from callers (tests/test_ephemeris_attestation.py, AC-01-4a).
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "computation_error", "message": f"Western chart calculation failed: {exc}"},
        )
    bodies = western.get("bodies", {})
    angles = western.get("angles") or {}
    ascendant = angles.get("Ascendant")

    # Extract sign indices
    sun_data = bodies.get("Sun", {})
    moon_data = bodies.get("Moon", {})
    sun_sign_idx = sun_data.get("zodiac_sign", 0) if isinstance(sun_data, dict) else 0
    moon_sign_idx = moon_data.get("zodiac_sign", 0) if isinstance(moon_data, dict) else 0
    asc_sign_idx = int((ascendant or 0) // 30) % 12

    # Personal planet sectors
    personal_planets: Dict[str, int] = {}
    for pname in ("Mercury", "Venus", "Mars"):
        pdata = bodies.get(pname, {})
        if isinstance(pdata, dict) and "zodiac_sign" in pdata:
            personal_planets[pname] = pdata["zodiac_sign"]

    # Fusion analysis
    try:
        fusion = compute_fusion_analysis(
            birth_utc_dt=bazi_result.birth_utc_dt,
            latitude=birth.lat,
            longitude=birth.lon,
            bazi_pillars=bazi_pillars_dict,
            western_bodies=bodies,
            ascendant=ascendant,
            strict=True,  # router-layer: ascendant must be wired through
        )
    except Exception as exc:
        logger.error("Fusion analysis failed: %s", exc, exc_info=exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "computation_error", "message": f"Fusion analysis failed: {exc}"},
        )

    # Wu-Xing vector (normalized)
    wuxing_western = fusion.get("wu_xing_vectors", {}).get("western_planets", {})
    wuxing_bazi = fusion.get("wu_xing_vectors", {}).get("bazi_pillars", {})
    # Average of both systems
    wuxing_vector: Dict[str, float] = {}
    for elem in ("Holz", "Feuer", "Erde", "Metall", "Wasser"):
        w = wuxing_western.get(elem, 0.2)
        b = wuxing_bazi.get(elem, 0.2)
        wuxing_vector[elem] = round((w + b) / 2, 4)

    harmony_index = _select_profile_harmony(fusion)

    return {
        "bazi_result": bazi_result,
        "western_chart": western,
        "fusion": fusion,
        "day_master": day_master,
        "sun_sign_idx": sun_sign_idx,
        "moon_sign_idx": moon_sign_idx,
        "asc_sign_idx": asc_sign_idx,
        "personal_planets": personal_planets,
        "wuxing_vector": wuxing_vector,
        "harmony_index": harmony_index,
    }


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/bootstrap", response_model=BootstrapResponse)
@limiter.limit(tier_limit)
def experience_bootstrap(body: BootstrapRequest, request: Request) -> BootstrapResponse:
    """Full profile bootstrap from birth data."""
    profile_data = _compute_astro_profile(body.birth)

    # Compute soulprint
    soulprint = compute_soulprint(
        sun_sign_idx=profile_data["sun_sign_idx"],
        moon_sign_idx=profile_data["moon_sign_idx"],
        asc_sign_idx=profile_data["asc_sign_idx"],
        personal_planets=profile_data["personal_planets"],
        wuxing_vector=profile_data["wuxing_vector"],
    )

    # Compute signature blueprint
    blueprint = compute_signature_blueprint(
        soulprint_sectors=soulprint,
        wuxing_vector=profile_data["wuxing_vector"],
        harmony_index=profile_data["harmony_index"],
    )

    # Build profile summary
    sun_sign = ZODIAC_SIGNS[profile_data["sun_sign_idx"] % 12]
    moon_sign = ZODIAC_SIGNS[profile_data["moon_sign_idx"] % 12]
    asc_sign = ZODIAC_SIGNS[profile_data["asc_sign_idx"] % 12]

    # Localize sign names for German
    if body.locale.startswith("de"):
        sun_sign = _SIGN_DE.get(sun_sign, sun_sign)
        moon_sign = _SIGN_DE.get(moon_sign, moon_sign)
        asc_sign = _SIGN_DE.get(asc_sign, asc_sign)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return BootstrapResponse(
        profile=ProfileSummary(
            sun_sign=sun_sign,
            moon_sign=moon_sign,
            ascendant_sign=asc_sign,
            day_master=profile_data["day_master"],
            harmony_index=round(profile_data["harmony_index"], 4),
        ),
        soulprint_sectors=soulprint,
        signature_blueprint=SignatureBlueprint(
            seed=blueprint["seed"],
            visual=VisualParams(**blueprint["visual"]),
            elements=blueprint["elements"],
        ),
        meta=MetaInfo(engine_version=__version__, generated_at=now),
    )


@router.post("/signature-delta", response_model=SignatureDeltaResponse)
@limiter.limit(tier_limit)
def experience_signature_delta(body: SignatureDeltaRequest, request: Request) -> SignatureDeltaResponse:
    """Incremental signature update from a quiz answer."""
    keyword = body.quiz_answer.keyword

    # Resolve quiz keyword → sector weights
    quiz_sectors = resolve_quiz_sectors(keyword)

    # Blend soulprint with quiz influence to get new sectors
    blended = [
        round(sp * 0.7 + qs * 0.3, 6)
        for sp, qs in zip(body.soulprint_sectors, quiz_sectors)
    ]
    # Normalize blended to [0, 1]
    total = sum(blended) or 1.0
    blended = [round(b / total, 6) for b in blended]

    # Compute new signature blueprint from blended sectors
    # Use a default wuxing vector if elements not provided
    wuxing = body.signature_blueprint.elements or {
        "Holz": 0.2, "Feuer": 0.2, "Erde": 0.2, "Metall": 0.2, "Wasser": 0.2,
    }
    new_blueprint = compute_signature_blueprint(
        soulprint_sectors=blended,
        wuxing_vector=wuxing,
        harmony_index=0.5,  # harmony doesn't change from quiz
    )

    # Compute visual deltas
    old_visual = body.signature_blueprint.visual
    if old_visual:
        delta_curvature = round(new_blueprint["visual"]["curvature"] - old_visual.curvature, 4)
        delta_contrast = round(new_blueprint["visual"]["contrast"] - old_visual.contrast, 4)
        delta_density = round(new_blueprint["visual"]["density"] - old_visual.density, 4)
    else:
        delta_curvature = new_blueprint["visual"]["curvature"]
        delta_contrast = new_blueprint["visual"]["contrast"]
        delta_density = new_blueprint["visual"]["density"]

    return SignatureDeltaResponse(
        quiz_sectors=quiz_sectors,
        signature_delta=SignatureDelta(
            curvature=delta_curvature,
            contrast=delta_contrast,
            density=delta_density,
        ),
        signature_blueprint=SignatureBlueprint(
            seed=new_blueprint["seed"],
            visual=VisualParams(**new_blueprint["visual"]),
            elements=new_blueprint.get("elements"),
        ),
    )


async def _compute_impact_for_daily(
    body: "DailyRequest",
    profile_data: Dict[str, Any],
) -> Optional[ImpactResponse]:
    """Compute impact data inline for the daily endpoint (include=["impact"]).

    Reuses the pre-computed profile_data from the daily handler to avoid
    redundant natal chart computation. Returns None on failure (graceful
    degradation — daily response is still valid without impact).
    """
    try:
        # Reuse pre-computed natal data
        bazi_result = profile_data["bazi_result"]
        stem_name = STEMS[bazi_result.pillars.day.stem_index]
        master_elem = day_master_element(stem_name)

        western = profile_data["western_chart"]
        natal_bodies = western.get("bodies", {})
        house_cusps = western.get("houses", {})

        from datetime import datetime as _dt
        target = _dt.strptime(body.target_date, "%Y-%m-%d").date()
        target_dt = datetime(target.year, target.month, target.day, 12, 0, 0, tzinfo=timezone.utc)
        transit_data = compute_transit_now(dt_utc=target_dt)
        transit_planets = transit_data.get("planets", {})

        active = find_active_planets(natal_bodies, transit_planets, house_cusps)
        active = enrich_active_planets(active, master_elem)

        space_weather, sw_partial = await fetch_space_weather()
        sw_score = compute_space_weather_score(space_weather)

        # Convert 12-sector soulprint/quiz to 5-element Wu-Xing dict for harmony calc.
        # Sectors map to elements: [0-1]=fire, [2-3]=earth, [4-5]=metal, [6-7]=water, [8-9]=wood, [10-11]=fire
        sp_wuxing = _sectors_to_wuxing_dict(body.soulprint_sectors) if body.soulprint_sectors else None
        qz_wuxing = _sectors_to_wuxing_dict(body.quiz_sectors) if body.quiz_sectors else None

        natal_vec = natal_wuxing_vector(sp_wuxing, qz_wuxing)
        transit_vec = transit_wuxing_vector(active)
        harmony = compute_harmony_index(natal_vec, transit_vec)
        intensity = compute_intensity(harmony, len(active), sw_score)
        mode = classify_day_mode(harmony, intensity)
        drivers = compute_drivers(sw_score, len(active), harmony)

        return ImpactResponse(
            harmony_index=harmony,
            day_mode=mode,
            intensity=intensity,
            active_planets=active,
            space_weather=space_weather,
            space_weather_score=sw_score,
            drivers=drivers,
            resonance_badges=build_resonance_badges(active),
            top_sector=find_top_sector(active),
            day_master=master_elem,
            evidence=build_evidence(natal_vec, transit_vec, harmony),
            partial=sw_partial,
        )
    except Exception as exc:
        logger.error("Impact computation failed for daily endpoint: %s", exc)
        return None


def _sectors_to_wuxing_dict(sectors: List[float]) -> Dict[str, float]:
    """Convert 12-sector zodiac vector to 5-element Wu-Xing dict.

    Maps zodiac signs to Wu-Xing elements matching impact.py's _SIGN_TO_ELEMENT:
    Aries(0)=fire, Taurus(1)=earth, Gemini(2)=metal, Cancer(3)=water,
    Leo(4)=fire, Virgo(5)=earth, Libra(6)=metal, Scorpio(7)=water,
    Sagittarius(8)=fire, Capricorn(9)=earth, Aquarius(10)=metal, Pisces(11)=water.

    Wood comes from planet-level Wu-Xing mapping (Jupiter, Uranus, NorthNode)
    rather than zodiac sectors — this is consistent with the impact.py convention.
    """
    elements: Dict[str, float] = {"wood": 0.0, "fire": 0.0, "earth": 0.0, "metal": 0.0, "water": 0.0}
    _map = {
        0: "fire", 1: "earth", 2: "metal", 3: "water",
        4: "fire", 5: "earth", 6: "metal", 7: "water",
        8: "fire", 9: "earth", 10: "metal", 11: "water",
    }
    for i, val in enumerate(sectors[:12]):
        elem = _map.get(i, "earth")
        elements[elem] += val
    total = sum(elements.values())
    if total > 0:
        elements = {k: round(v / total, 6) for k, v in elements.items()}
    return elements


def _daily_profile_missing(
    day_master: Any,
    sun_sign_idx: Any,
    moon_sign_idx: Any,
    asc_sign_idx: Any,
) -> bool:
    return any(value is None for value in (day_master, sun_sign_idx, moon_sign_idx, asc_sign_idx))


def _daily_profile_context(
    body: DailyRequest,
) -> tuple[str, int, int, int, Optional[Dict[str, Any]]]:
    # Allow callers to pass precomputed natal signals (day_master and sign indices)
    # to avoid recomputing the full astro profile on every daily request.
    day_master = getattr(body, "day_master", None)
    sun_sign_idx = getattr(body, "sun_sign_idx", None)
    moon_sign_idx = getattr(body, "moon_sign_idx", None)
    asc_sign_idx = getattr(body, "asc_sign_idx", None)

    profile_data = None
    if _daily_profile_missing(day_master, sun_sign_idx, moon_sign_idx, asc_sign_idx):
        profile_data = _compute_astro_profile(body.birth)
        day_master = profile_data["day_master"]
        sun_sign_idx = profile_data["sun_sign_idx"]
        moon_sign_idx = profile_data["moon_sign_idx"]
        asc_sign_idx = profile_data["asc_sign_idx"]

    assert isinstance(day_master, str)
    assert isinstance(sun_sign_idx, int)
    assert isinstance(moon_sign_idx, int)
    assert isinstance(asc_sign_idx, int)
    return day_master, sun_sign_idx, moon_sign_idx, asc_sign_idx, profile_data


def _impact_requested(body: DailyRequest) -> bool:
    return bool(body.include and "impact" in body.include)


def _chart_type_quality_for_daily(
    body: DailyRequest,
    profile_data: Optional[Dict[str, Any]],
) -> Literal["exact", "assumed_day"]:
    chart_type_quality: Literal["exact", "assumed_day"] = "assumed_day"
    if profile_data is not None:
        natal_fusion = profile_data.get("fusion") or {}
        ledger = natal_fusion.get("contribution_ledger") or {}
        raw_quality = ledger.get("chart_type_quality", "assumed_day")
        if raw_quality in ("exact", "assumed_day"):
            chart_type_quality = raw_quality
    if body.birth.birth_time_known is False:
        return "assumed_day"
    return chart_type_quality


def _quality_flags_for_daily(
    chart_type_quality: Literal["exact", "assumed_day"],
    profile_data: Optional[Dict[str, Any]],
) -> QualityFlags:
    """Build the merged QualityFlags block for /experience/daily's response.

    FQ-ATT-02 (T9), AC-02-4: ``profile_data`` is only ``None`` when
    ``_daily_profile_missing()`` returns ``False`` in
    ``_daily_profile_context()`` -- which requires ``DailyRequest`` to
    declare ``day_master``/``sun_sign_idx``/``moon_sign_idx``/
    ``asc_sign_idx`` fields. It does not (confirmed, PRD §3.6): this branch
    is unreachable via the public ``/experience/daily`` HTTP endpoint today.

    This previously silently built ``QualityFlags(house_system_fallback=
    None, ...)`` against QualityFlags's non-``Optional`` fields whenever
    ``profile_data`` was ``None`` -- an opaque Pydantic ``ValidationError``
    trap rather than a clear, diagnosable failure. Raise a dedicated
    ``CalculationError`` instead, in case a future internal caller ever
    wires precomputed signals through this path and reaches it for real.
    """
    if profile_data is None:
        raise CalculationError(
            "_quality_flags_for_daily() called with profile_data=None -- "
            "this should be unreachable via the public /experience/daily "
            "endpoint (DailyRequest declares no day_master/sun_sign_idx/"
            "moon_sign_idx/asc_sign_idx fields, PRD fufire-premium-"
            "verification-ci FQ-ATT-02 §3.6). Refusing to synthesize "
            "QualityFlags with None values.",
        )
    western_qf = dict(profile_data.get("western_chart", {}).get("quality_flags") or {})
    western_qf["chart_type_quality"] = chart_type_quality
    return QualityFlags(**western_qf)


def _provenance_for_daily(profile_data: Optional[Dict[str, Any]]) -> ProvenanceResponse:
    """Build the top-level ProvenanceResponse for /experience/daily's response.

    FQ-ATT-02 (T9), AC-02-2/AC-02-3: confirmed gap beyond PRD §3.5's initial
    "(via profile)" note -- provenance data was computed internally (via
    the natal western chart's ``house_system``) but never actually surfaced
    as a top-level ``provenance`` field on ``DailyResponse``. Mirrors the
    same ``build_provenance(house_system=normalize_house_system(...))``
    call every other house-computing router already makes.

    ``profile_data`` is guaranteed non-``None`` via the public
    ``/experience/daily`` endpoint for the same reason documented in
    ``_quality_flags_for_daily()`` above (PRD §3.6) -- raise the same clear
    internal error rather than silently defaulting if that invariant is
    ever violated by a future internal caller.
    """
    if profile_data is None:
        raise CalculationError(
            "_provenance_for_daily() called with profile_data=None -- this "
            "should be unreachable via the public /experience/daily "
            "endpoint (see _quality_flags_for_daily()'s docstring, PRD "
            "fufire-premium-verification-ci FQ-ATT-02 §3.6).",
        )
    western_chart = profile_data.get("western_chart") or {}
    return ProvenanceResponse(
        **build_provenance(
            house_system=normalize_house_system(western_chart.get("house_system")),
        )
    )


@router.post("/daily", response_model=DailyResponse)
@limiter.limit(tier_limit)
async def experience_daily(body: DailyRequest, request: Request) -> DailyResponse:
    """Daily horoscope combining Western, Eastern, and Fusion layers.

    When ``include=["impact"]`` is set, the response includes an ``impact``
    block identical to the ``POST /impact/active`` response (PRD P0-4).
    Without ``include``, the response is identical to v1 (backwards compatible).
    """
    (
        day_master,
        sun_sign_idx,
        moon_sign_idx,
        asc_sign_idx,
        profile_data,
    ) = _daily_profile_context(body)

    # Western daily
    western_result = generate_western_daily(
        sun_sign_idx=sun_sign_idx,
        moon_sign_idx=moon_sign_idx,
        asc_sign_idx=asc_sign_idx,
        soulprint_sectors=body.soulprint_sectors,
        target_date=body.target_date,
        tz=body.birth.tz,
        lat=body.birth.lat,
        lon=body.birth.lon,
        locale=body.locale,
    )

    # Eastern daily
    eastern_result = generate_eastern_daily(
        day_master=day_master,
        target_date=body.target_date,
        tz=body.birth.tz,
        locale=body.locale,
    )

    # Fusion daily
    fusion_result = generate_fusion_daily(
        western=western_result,
        eastern=eastern_result,
        locale=body.locale,
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build eastern evidence with DailyPillar model
    eastern_evidence = eastern_result.get("evidence", {})
    daily_pillar_raw = eastern_evidence.get("daily_pillar")
    daily_pillar = None
    if isinstance(daily_pillar_raw, dict):
        daily_pillar = DailyPillar(**daily_pillar_raw)

    # Optionally compute impact block (PRD P0-4)
    impact_data: Optional[ImpactResponse] = None
    if _impact_requested(body) and profile_data is not None:
        impact_data = await _compute_impact_for_daily(body, profile_data)

    # Surface and mirror chart_type_quality once so B2B integrators can trust-gate
    # the response without digging into the nested fusion sub-tree.
    chart_type_quality = _chart_type_quality_for_daily(body, profile_data)
    quality_flags = _quality_flags_for_daily(chart_type_quality, profile_data)
    provenance = _provenance_for_daily(profile_data)

    return DailyResponse(
        date=body.target_date,
        western=DailySection(
            summary=western_result["summary"],
            themes=western_result["themes"],
            caution=western_result["caution"],
            opportunity=western_result["opportunity"],
            evidence=DailyEvidence(**western_result["evidence"]),
            weekday_note=western_result.get("weekday_note"),
        ),
        eastern=DailySection(
            summary=eastern_result["summary"],
            themes=eastern_result["themes"],
            caution=eastern_result["caution"],
            opportunity=eastern_result["opportunity"],
            evidence=DailyEvidence(
                day_master=eastern_evidence.get("day_master"),
                daily_pillar=daily_pillar,
                relation_to_day_master=eastern_evidence.get("relation_to_day_master"),
                jieqi=eastern_evidence.get("jieqi"),
                weekday=eastern_evidence.get("weekday"),
            ),
            jieqi_note=eastern_result.get("jieqi_note"),
            weekday_note=eastern_result.get("weekday_note"),
        ),
        fusion=DailyFusion(
            summary=fusion_result["summary"],
            synthesis=fusion_result["synthesis"],
            action=fusion_result["action"],
            pushworthy=fusion_result["pushworthy"],
            push_text=fusion_result.get("push_text"),
            jieqi_note=fusion_result.get("jieqi_note"),
            weekday_note=fusion_result.get("weekday_note"),
        ),
        chart_type_quality=chart_type_quality,
        quality_flags=quality_flags,
        provenance=provenance,
        meta=MetaInfo(engine_version=__version__, generated_at=now),
        impact=impact_data,
    )
