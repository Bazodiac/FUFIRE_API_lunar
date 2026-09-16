"""
routers/bazi.py — POST /calculate/bazi
"""
from __future__ import annotations

import logging
from datetime import timezone as _tz
from typing import Any, Dict, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from ..bazi import compute_bazi, hour_branch_index, jdn_gregorian, sexagenary_day_index_from_date
from ..bazi_rules import day_offset_from_ruleset, load_default_ruleset
from ..constants import ANIMALS, BRANCHES, STEMS
from ..exc import BaziEngineError
from ..limiter import limiter, tier_limit
from ..provenance import WUXING_PARAMETER_SET, build_provenance
from ..time_context import compute_effective_time_context
from ..time_utils import AmbiguousTimeChoice, NonexistentTimePolicy, apply_day_boundary, resolve_local_iso
from ..types import BaziInput, BaziResult, Fold
from ..wuxing.analysis import calculate_wuxing_from_bazi_with_ledger
from .shared import (
    MinimalQualityFlags,
    PrecisionBlock,
    ProvenanceResponse,
    current_ephemeris_mode,
    format_pillar,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/calculate", tags=["BaZi"])


class BaziRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "1990-06-15T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
            "standard": "CIVIL",
            "boundary": "midnight",
            "ambiguousTime": "earlier",
            "nonexistentTime": "error",
            "birth_time_known": True,
        }
    })

    date: str = Field(..., description="Local ISO8601 datetime")
    tz: str = Field("Europe/Berlin", description="IANA timezone name")
    lon: float = Field(13.4050, ge=-180.0, le=180.0, description="Longitude in degrees")
    lat: float = Field(52.52, ge=-90.0, le=90.0, description="Latitude in degrees")
    standard: Literal["CIVIL", "LMT", "TLST"] = Field("CIVIL")
    boundary: Literal["midnight", "zi"] = Field("midnight")
    ambiguousTime: AmbiguousTimeChoice = Field("earlier")
    nonexistentTime: NonexistentTimePolicy = Field("error")
    birth_time_known: bool = Field(True, description="False if birth time is uncertain — flags time-dependent outputs as provisional")
    # ADR-1: opt-out for the derivation trace. Default True preserves the
    # current behaviour (trace always present → zero snapshot churn) while
    # giving callers a real opt-out (False → derivation_trace = null).
    # NOTE: this toggle is intentionally NOT echoed in ``response.input``
    # (see BaziInputEcho) so existing snapshots stay byte-identical. It is
    # a plain field here (no Field(exclude=...)) to keep a single
    # ``BaziRequest`` OpenAPI component for the B2B/contract tests.
    include_trace: bool = Field(
        True,
        description="When False, omit the derivation_trace from the response (set null). Default True keeps the current behaviour. Not echoed in response.input.",
    )


class BaziInputEcho(BaseModel):
    """Echo of the request in ``response.input``.

    Mirrors ``BaziRequest`` EXCEPT the ADR-1 ``include_trace`` toggle, which
    is a response-shaping option and not part of the metaphysical request
    contract. Keeping it out of the echo preserves byte-identical responses
    for pre-ADR-1 callers (zero snapshot churn), while ``BaziRequest`` stays
    a single OpenAPI component for the B2B/contract tests.
    """
    date: str
    tz: str
    lon: float
    lat: float
    standard: Literal["CIVIL", "LMT", "TLST"]
    boundary: Literal["midnight", "zi"]
    ambiguousTime: AmbiguousTimeChoice
    nonexistentTime: NonexistentTimePolicy
    birth_time_known: bool


class PillarDetail(BaseModel):
    stamm: str
    zweig: str
    tier: str
    element: str


class BaziPillarsResponse(BaseModel):
    year: PillarDetail
    month: PillarDetail
    day: PillarDetail
    hour: PillarDetail


class ChineseYearInfo(BaseModel):
    stem: str
    branch: str
    animal: str


class ChineseSection(BaseModel):
    year: ChineseYearInfo
    month_master: str
    day_master: str
    hour_master: str


class BaziDatesResponse(BaseModel):
    birth_local: str
    birth_utc: str
    lichun_local: str


class BaziTransitionResponse(BaseModel):
    solar_year: int
    is_before_lichun: bool
    lichun_year_start: str
    lichun_next: Optional[str] = None


class DayAnchorEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ruleset_id: str
    ruleset_version: str
    anchor_jdn: Optional[int] = None
    anchor_sex_idx: Optional[int] = None
    anchor_verification: str


class YearDerivationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lichun_crossing_utc: str
    is_before_lichun: bool
    solar_longitude_lichun: float


class MonthDerivationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jieqi_crossing_utc: str
    solar_longitude_deg: float
    month_branch_index: int


class DayDerivationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    julian_day_number: int
    sexagenary_index: int
    day_offset_used: int
    day_master_stem: str
    day_anchor_evidence: DayAnchorEvidence


class HourDerivationTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_hour: int
    branch_index: int
    # FBP-03-002 (DEV-2026-001): fixed — true only when TLST was used.
    true_solar_time_used: bool
    # FBP-03-002: dedicated LMT flag so CIVIL/LMT/TLST are distinguishable.
    lmt_used: bool
    time_standard_requested: str
    time_standard_used: str
    hour_branch_time_policy: Optional[str] = None  # populated by FBP-02-005


class ProvenanceIds(BaseModel):
    """Model version identifiers that governed this calculation (FBP-03-004 / DEV-2026-007).

    Consumers can use these IDs to pin and reproduce a calculation
    deterministically without inspecting the full parameter_set block.
    """
    model_config = ConfigDict(extra="forbid")
    ruleset_id: str       # e.g. "standard_bazi_2026"
    ruleset_version: str  # e.g. "1.0.0"
    time_policy_id: str   # "{standard}_{boundary}", e.g. "civil_midnight"
    day_anchor_id: str    # "{ruleset_id}:jdn_{anchor_jdn}_{verification}"
    vector_model_id: str  # e.g. "wuxing_v1.1.0"


class TimeResolutionTrace(BaseModel):
    """All three time-standard representations of the birth instant (FBP-03-003).

    Always present regardless of the requested standard, so consumers can
    compare all time bases without re-computing.
    """
    model_config = ConfigDict(extra="forbid")
    civil_local: str       # ISO 8601, tz-aware civil local time
    utc: str               # ISO 8601, UTC
    lmt: str               # ISO 8601, Local Mean Time (longitude-offset, no DST)
    tlst_hours: float      # apparent solar hour-of-day in [0, 24)
    eot_minutes: float     # equation of time in minutes (positive = sun fast)
    tz_offset_minutes: int  # civil UTC offset in integer minutes
    effective_standard: str  # CIVIL | LMT | TLST


class BaziDerivationTrace(BaseModel):
    year: YearDerivationTrace
    month: MonthDerivationTrace
    day: DayDerivationTrace
    hour: HourDerivationTrace
    time_resolution: TimeResolutionTrace
    provenance_ids: ProvenanceIds


class BaziResponse(BaseModel):
    input: BaziInputEcho
    pillars: BaziPillarsResponse
    chinese: ChineseSection
    dates: BaziDatesResponse
    transition: BaziTransitionResponse
    solar_terms_count: int
    provenance: ProvenanceResponse
    quality_flags: MinimalQualityFlags
    precision: PrecisionBlock
    derivation_trace: Optional[BaziDerivationTrace] = None


def _day_anchor_evidence(ruleset: dict) -> DayAnchorEvidence:
    """Surface the day-cycle anchor record the engine used (FBP-02-008).

    Accepts the already-loaded ruleset from the caller to avoid a
    redundant load_default_ruleset() call inside _build_derivation_trace.
    """
    anchor = (ruleset or {}).get("day_cycle_anchor", {}) or {}
    return DayAnchorEvidence(
        ruleset_id=ruleset.get("ruleset_id", "MISSING"),
        ruleset_version=ruleset.get("ruleset_version", "MISSING"),
        anchor_jdn=anchor.get("anchor_jdn"),
        anchor_sex_idx=anchor.get("anchor_sexagenary_index_0based"),
        anchor_verification=anchor.get("anchor_verification", "MISSING"),
    )


def _build_derivation_trace(
    res: BaziResult,
    inp: BaziInput,
    requested_standard: Optional[str] = None,
) -> BaziDerivationTrace:
    """Build typed derivation trace from computed BaziResult intermediate values.

    ``requested_standard`` defaults to ``inp.time_standard`` so existing
    callers keep working. When the router clamps ``TLST`` to ``LMT``
    (FBP-01-001, Phase 1), the original value is threaded in so the
    trace records what the user asked for in addition to what the
    engine used.
    """
    if requested_standard is None:
        requested_standard = inp.time_standard
    # Year trace: LiChun crossing
    lichun_utc = res.lichun_local_dt.astimezone(_tz.utc).isoformat()

    # Month trace: jieqi crossing for current month boundary
    month_boundary_dt = res.month_boundaries_local_dt[res.month_index]
    month_boundary_utc = month_boundary_dt.astimezone(_tz.utc).isoformat()
    # Jie qi solar longitudes: month 0 (LiChun) = 315, each +30
    solar_lon_deg = (315.0 + res.month_index * 30.0) % 360.0

    # Day trace: JDN and sexagenary index
    dt_for_day = apply_day_boundary(res.chart_local_dt, inp.day_boundary)
    jdn = jdn_gregorian(dt_for_day.year, dt_for_day.month, dt_for_day.day)
    sex_idx = sexagenary_day_index_from_date(
        dt_for_day.year, dt_for_day.month, dt_for_day.day,
    )

    # Hour trace
    hb = hour_branch_index(res.chart_local_dt)

    # FBP-03-004 — provenance IDs derived from loaded ruleset + request params.
    ruleset = load_default_ruleset()
    _anchor = (ruleset or {}).get("day_cycle_anchor", {}) or {}
    _anchor_jdn = _anchor.get("anchor_jdn", "unknown")
    _anchor_verif = _anchor.get("anchor_verification", "unknown")
    _ruleset_id = (ruleset or {}).get("ruleset_id", "unknown")
    _ruleset_version = (ruleset or {}).get("ruleset_version", "unknown")
    prov_ids = ProvenanceIds(
        ruleset_id=_ruleset_id,
        ruleset_version=_ruleset_version,
        time_policy_id=f"{inp.time_standard.lower()}_{inp.day_boundary}",
        day_anchor_id=f"{_ruleset_id}:jdn_{_anchor_jdn}_{_anchor_verif}",
        vector_model_id=f"wuxing_v{WUXING_PARAMETER_SET['version']}",
    )

    # FBP-03-003 — compute the full effective time context regardless of the
    # requested standard so the trace always exposes all three time bases.
    time_ctx = compute_effective_time_context(
        birth_local_iso=inp.birth_local,
        tz_name=inp.timezone,
        longitude_deg=inp.longitude_deg,
    )

    return BaziDerivationTrace(
        year=YearDerivationTrace(
            lichun_crossing_utc=lichun_utc,
            is_before_lichun=res.is_before_lichun,
            solar_longitude_lichun=315.0,
        ),
        month=MonthDerivationTrace(
            jieqi_crossing_utc=month_boundary_utc,
            solar_longitude_deg=solar_lon_deg,
            month_branch_index=res.pillars.month.branch_index,
        ),
        day=DayDerivationTrace(
            julian_day_number=jdn,
            sexagenary_index=sex_idx,
            day_offset_used=day_offset_from_ruleset(ruleset),
            day_master_stem=STEMS[res.pillars.day.stem_index],
            day_anchor_evidence=_day_anchor_evidence(ruleset),
        ),
        hour=HourDerivationTrace(
            local_hour=res.chart_local_dt.hour,
            branch_index=hb,
            true_solar_time_used=inp.time_standard == "TLST",
            lmt_used=inp.time_standard == "LMT",
            time_standard_requested=requested_standard,
            time_standard_used=inp.time_standard,
        ),
        time_resolution=TimeResolutionTrace(
            civil_local=time_ctx.civil_local.isoformat(),
            utc=time_ctx.utc.isoformat(),
            lmt=time_ctx.lmt_local.isoformat(),
            tlst_hours=time_ctx.tlst_hours,
            eot_minutes=time_ctx.eot_minutes,
            tz_offset_minutes=time_ctx.tz_offset_minutes,
            effective_standard=inp.time_standard,
        ),
        provenance_ids=prov_ids,
    )


def _compute_bazi_response(req: BaziRequest, *, force_trace: bool = False) -> Dict[str, Any]:
    """Build the full BaZi response dict for ``req``.

    Single source of truth shared by ``/calculate/bazi`` and the alias
    route ``/calculate/bazi/trace`` (ADR-1). The trace is computed by the
    existing ``_build_derivation_trace`` — NO new trace math.

    ``force_trace=True`` (used by the alias) always attaches the trace,
    overriding ``req.include_trace``; otherwise ``req.include_trace``
    decides (default True → present; False → null).
    """
    try:
        dt_local, _ = resolve_local_iso(
            req.date, req.tz,
            ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
        )
        resolved_naive = dt_local.replace(tzinfo=None).isoformat()
        fold: Fold = 0 if req.ambiguousTime == "earlier" else 1
        # FBP-02-005 — Phase-1 router clamp removed. compute_bazi() now
        # handles TLST natively (TLST-derived hour pillar). For CIVIL
        # and LMT the engine keeps the legacy path. requested_standard
        # is kept in the trace alongside the engine's used value (which
        # for Phase 2 onward equals the requested value).
        requested_standard = req.standard
        engine_standard = requested_standard
        inp = BaziInput(
            birth_local=resolved_naive,
            timezone=req.tz,
            longitude_deg=req.lon,
            latitude_deg=req.lat,
            time_standard=engine_standard,
            day_boundary=req.boundary,
            strict_local_time=True,
            fold=fold,
        )
        res = compute_bazi(inp)
        # ADR-1: gate the trace. force_trace (alias route) always wins;
        # otherwise honour the request flag. Same compute_bazi result +
        # same _build_derivation_trace — no duplicated trace math.
        attach_trace = force_trace or req.include_trace
        derivation_trace = (
            _build_derivation_trace(res, inp, requested_standard=requested_standard)
            if attach_trace
            else None
        )
        return {
            # ADR-1 "zero snapshot churn": echo every request field EXCEPT
            # the include_trace toggle (BaziResponse.input is typed as
            # BaziInputEcho, which omits it) — existing callers' responses
            # stay byte-identical.
            "input": req.model_dump(exclude={"include_trace"}),
            "pillars": {
                "year":  format_pillar(res.pillars.year),
                "month": format_pillar(res.pillars.month),
                "day":   format_pillar(res.pillars.day),
                "hour":  format_pillar(res.pillars.hour),
            },
            "chinese": {
                "year": {
                    "stem":   STEMS[res.pillars.year.stem_index],
                    "branch": BRANCHES[res.pillars.year.branch_index],
                    "animal": ANIMALS[res.pillars.year.branch_index],
                },
                "month_master": STEMS[res.pillars.month.stem_index],
                "day_master":   STEMS[res.pillars.day.stem_index],
                "hour_master":  STEMS[res.pillars.hour.stem_index],
            },
            "dates": {
                "birth_local":  res.birth_local_dt.isoformat(),
                "birth_utc":    res.birth_utc_dt.isoformat(),
                "lichun_local": res.lichun_local_dt.isoformat(),
            },
            "transition": {
                "solar_year": res.solar_year,
                "is_before_lichun": res.is_before_lichun,
                "lichun_year_start": res.lichun_local_dt.isoformat(),
                "lichun_next": res.lichun_next_local_dt.isoformat() if res.lichun_next_local_dt else None,
            },
            "solar_terms_count": len(res.solar_terms_local_dt) if res.solar_terms_local_dt else 0,
            "provenance": build_provenance(),
            # FQ-ATT-02 (T9), AC-02-3: BaZi computes no house cusps -- OQ-1
            # scopes house_system_fallback to house-computing endpoints only,
            # so this carries the minimal, non-house attestation subset.
            "quality_flags": {"ephemeris_mode": current_ephemeris_mode()},
            "precision": {
                "birth_time_known": req.birth_time_known,
                "provisional_fields": [] if req.birth_time_known else ["hour"],
            },
            "derivation_trace": derivation_trace,
        }
    except BaziEngineError:
        raise
    except Exception:
        _log.exception("Calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


@router.post("/bazi", response_model=BaziResponse)
@limiter.limit(tier_limit)
def calculate_bazi_endpoint(request: Request, req: BaziRequest) -> Dict[str, Any]:
    """Four Pillars (BaZi) calculation. Computes Year, Month, Day, and Hour pillars using precise solar-term boundaries from Swiss Ephemeris. Year boundary is LiChun (~315° solar longitude, ~Feb 3–5), not January 1st. Supports Civil and Local Mean Time (LMT), midnight and zi-hour day boundaries, and DST disambiguation via `ambiguousTime`/`nonexistentTime`. Set `include_trace=false` to omit the derivation trace."""
    return _compute_bazi_response(req)


@router.post(
    "/bazi/trace",
    response_model=BaziResponse,
    tags=["BaZi Trace (beta)"],
    description=(
        "BETA — Four Pillars (BaZi) calculation with the full derivation "
        "trace always attached.\n\n"
        "Thin alias for `POST /calculate/bazi` that forces "
        "`include_trace=true`: it reuses the exact same engine "
        "(`compute_bazi`) and the same `_build_derivation_trace` — no new "
        "or duplicated trace math. The returned `derivation_trace` "
        "deep-equals the one from `/calculate/bazi` for an identical "
        "request, and exposes the real engine trace shape "
        "`{year, month, day, hour, time_resolution, provenance_ids}` (not "
        "the PRD's hypothetical fields). The `include_trace` flag in the "
        "body is ignored here — this route always returns the trace.\n\n"
        "**Known limitation (tracked):** for `standard=TLST` with "
        "`boundary=zi` near the 23:00 late-Zi rollover, "
        "`derivation_trace.day` may diverge by one day from the headline "
        "day pillar — trust the headline day pillar; the trace/pillar "
        "consistency fix is tracked in the backlog (GT6)."
    ),
)
@limiter.limit(tier_limit)
def calculate_bazi_trace_endpoint(request: Request, req: BaziRequest) -> Dict[str, Any]:
    """BETA — Four Pillars (BaZi) calculation with the full derivation trace always attached.

    Thin alias for `POST /calculate/bazi` that forces `include_trace=true`:
    it reuses the exact same engine (`compute_bazi`) and the same
    `_build_derivation_trace` — no new or duplicated trace math. The
    returned `derivation_trace` deep-equals the one from `/calculate/bazi`
    for an identical request, and exposes the real engine trace shape
    `{year, month, day, hour, time_resolution, provenance_ids}` (not the
    PRD's hypothetical fields). The `include_trace` flag in the body is
    ignored here — this route always returns the trace.

    Known limitation (tracked, GT6): for ``standard=TLST`` with
    ``boundary=zi`` near the 23:00 late-Zi rollover,
    ``_build_derivation_trace`` re-derives the day via the legacy
    ``apply_day_boundary`` (naive +1h), which can disagree with
    ``compute_bazi``'s TLST-aware late-Zi rollover. In that corner the
    ``derivation_trace.day`` may be one day off from the headline day
    pillar — trust the headline day pillar. The engine fix is deferred to
    its own increment (it churns snapshots); see GT6 in the plan.
    """
    return _compute_bazi_response(req, force_trace=True)


# ── /calculate/bazi/wuxing ────────────────────────────────────────────────────
# The CANONICAL BaZi Wu-Xing (Five Elements) distribution: derived from the Four
# Pillars (Heavenly Stems + Earthly Branch hidden stems, Qi-weighted). This is
# the element distribution a BaZi reading is built on. It is DISTINCT from
# ``POST /calculate/wuxing`` (routers/fusion.py), whose vector is derived from
# WESTERN PLANETARY positions and exists only for the Fusion layer — consumers
# that want "the person's Wu-Xing" must use THIS endpoint, not the planetary one.
# Pillar derivation mirrors ``/calculate/bazi`` and the ``/chart`` bazi branch
# byte-for-byte (same resolve_local_iso → BaziInput → compute_bazi chain), so the
# ``wu_xing_vector`` here equals ``/chart``'s ``wuxing.from_bazi``.


class BaziWuXingResponse(BaseModel):
    input: Dict[str, Any]
    wu_xing_vector: Dict[str, float] = Field(
        ..., description="Raw Wu-Xing counts (German keys Holz/Feuer/Erde/Metall/Wasser) from the Four Pillars."
    )
    dominant_element: str = Field(..., description="Element with the largest share of the BaZi vector.")
    basis: Literal["bazi_four_pillars"] = Field(
        ...,
        description=(
            "Provenance of the vector: derived from the BaZi Four Pillars (NOT western "
            "planetary positions). REQUIRED and deliberately without a default: a "
            "defaulted field lets the response model supply this value when the handler "
            "does not, which turns an absent producer fact into a fabricated provenance "
            "claim. Consumers treat this string as proof of origin, so it must be proof "
            "that the handler stated it."
        ),
    )
    pillars: Dict[str, Dict[str, str]] = Field(..., description="The four pillars {stem, branch} the vector was built from.")
    contribution_ledger: Dict[str, Any] = Field(
        ..., description="Per-contribution ledger under key 'bazi': each stem/hidden-stem and its element + Qi weight."
    )
    provenance: ProvenanceResponse
    quality_flags: MinimalQualityFlags
    precision: PrecisionBlock


@router.post(
    "/bazi/wuxing",
    response_model=BaziWuXingResponse,
    summary="BaZi Wu-Xing (Five Elements) from the Four Pillars",
    description=(
        "The **canonical BaZi Wu-Xing distribution**: the Five-Element balance "
        "derived from the Four Pillars (Heavenly Stems + Earthly-Branch hidden "
        "stems, Qi-weighted). This is the vector a BaZi personality/element "
        "reading is built on.\n\n"
        "**Not to be confused with `POST /calculate/wuxing`**, whose vector is "
        "derived from **western planetary positions** and exists only to feed the "
        "Fusion layer. For the person's actual Wu-Xing, use THIS endpoint.\n\n"
        "The pillar derivation is identical to `POST /calculate/bazi` and the "
        "`/chart` bazi branch, so `wu_xing_vector` equals `/chart`'s "
        "`wuxing.from_bazi`."
    ),
)
@limiter.limit(tier_limit)
def calculate_bazi_wuxing_endpoint(request: Request, req: BaziRequest) -> Dict[str, Any]:
    """BaZi Wu-Xing (Five Elements) distribution from the Four Pillars."""
    try:
        dt_local, _ = resolve_local_iso(
            req.date, req.tz, ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
        )
        fold: Fold = 0 if req.ambiguousTime == "earlier" else 1
        inp = BaziInput(
            birth_local=dt_local.replace(tzinfo=None).isoformat(),
            timezone=req.tz,
            longitude_deg=req.lon,
            latitude_deg=req.lat,
            time_standard=req.standard,
            day_boundary=req.boundary,
            strict_local_time=True,
            fold=fold,
        )
        res = compute_bazi(inp)
        pillars = {
            p: {
                "stem":   STEMS[getattr(res.pillars, p).stem_index],
                "branch": BRANCHES[getattr(res.pillars, p).branch_index],
            }
            for p in ("year", "month", "day", "hour")
        }
        vec, ledger = calculate_wuxing_from_bazi_with_ledger(pillars)
        wx = vec.to_dict()
        return {
            "input": req.model_dump(exclude={"include_trace"}),
            "wu_xing_vector":   wx,
            "dominant_element": max(wx, key=lambda k: wx[k]),
            "basis":            "bazi_four_pillars",
            "pillars":          pillars,
            "contribution_ledger": {"bazi": ledger},
            "provenance":       build_provenance(),
            "quality_flags":    {"ephemeris_mode": current_ephemeris_mode()},
            "precision": {
                "birth_time_known": req.birth_time_known,
                "provisional_fields": [] if req.birth_time_known else ["hour"],
            },
        }
    except BaziEngineError:
        raise
    except Exception:
        _log.exception("BaZi Wu-Xing calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")
