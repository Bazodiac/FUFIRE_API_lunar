"""routers/bazi_tlst_v2.py — opt-in True-Local-Solar-Time BaZi + Natal under /v2.

FU-TLST-POLICY / INC-1. Two ``/v2``-only routes that expose the existing TLST
engine path as an explicit, auditable product surface:

* ``POST /v2/calculate/bazi``        — four pillars + derivation trace
* ``POST /v2/calculate/bazi/natal``  — natal hidden stems / Ten Gods / month command

Both share ONE computation (``_compute_tlst_chart``): local wall-clock + IANA
zone → DST resolution (``resolve_local_instant``) → exact UTC instant →
``compute_bazi(time_standard="TLST")``. The router adds no time math of its
own — TLST, the solar-date rollover and the zi rule all come from
``time_context`` / ``bazi.compute_bazi`` (the code the v1 ``standard="TLST"``
path already runs). It only reports what the engine used (``time_basis``) and
flags decisions that lie inside the documented model tolerance.

Contract differences to v1 (deliberate, /v2 only):

* ``standard`` is REQUIRED and must be ``"TLST"``; ``boundary`` is REQUIRED.
* ``tz``, ``lat``, ``lon`` are REQUIRED — no Berlin defaults; NaN/Infinity
  are rejected.
* An ambiguous DST wall-clock without ``ambiguousTime`` is rejected (422)
  instead of silently resolved to ``earlier``; a nonexistent wall-clock is
  rejected unless ``nonexistentTime="shift_forward"``.
* A date carrying a numeric UTC offset is rejected (the IANA zone is the only
  authority); unknown body fields are rejected.

Release boundary: these routes are opt-in. The v1 / legacy defaults stay
``CIVIL``. The day-cycle anchor is ``unverified`` in the shipped ruleset and
the response says so in ``policy`` — nothing here claims domain verification.
"""
from __future__ import annotations

import logging
from datetime import timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from ..bazi import compute_bazi
from ..bazi_rules import load_default_ruleset
from ..constants import ANIMALS, BRANCHES, STEMS
from ..exc import BaziEngineError
from ..limiter import limiter, tier_limit
from ..match.individual import analyze_individual
from ..match.normalize import normalize_chart
from ..provenance import build_provenance
from ..time_context import (
    EOT_MODEL_TOLERANCE_MINUTES,
    compute_effective_time_context_from_instant,
    nearest_tlst_decision_edge,
)
from ..time_utils import LocalTimeError, ResolvedInstant, resolve_local_instant
from ..types import BaziInput, BaziResult
from . import bazi as _bazi_v1
from . import natal as _natal_v1
from .bazi import (
    BaziDatesResponse,
    BaziDerivationTrace,
    BaziPillarsResponse,
    BaziTransitionResponse,
    ChineseSection,
)
from .shared import (
    MinimalQualityFlags,
    PrecisionBlock,
    ProvenanceResponse,
    current_ephemeris_mode,
    format_pillar,
)

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/calculate", tags=["BaZi v2 (TLST)"])

_RELEASE_NOTE = (
    "**Opt-in True Local Solar Time (TLST).** `standard` must be `\"TLST\"`; "
    "the v1 and legacy routes keep their `CIVIL` default and are unchanged. "
    "Flow: local wall-clock + IANA zone → explicit DST resolution → exact UTC "
    "instant → TLST (UTC + longitude × 4 min + Meeus equation of time) → "
    "pillars. The hour branch is taken from the TLST hour; the day pillar "
    "follows the apparent-solar calendar date (`boundary=\"midnight\"`) or "
    "advances at TLST 23:00 (`boundary=\"zi\"`).\n\n"
    "`time_basis` reports the instant, TLST value, equation of time, solar "
    "date rollover and day rule the engine actually used, and "
    "`time_basis.uncertainty` flags decisions inside the 0.1-minute EoT "
    "tolerance or the solar-term search accuracy.\n\n"
    "**Not a verified production standard:** the sexagenary day-cycle anchor "
    "of the shipped ruleset is `unverified` (see `policy.day_anchor_verification`); "
    "domain sign-off is pending. Missing `tz`/`lat`/`lon`, a non-TLST "
    "`standard`, an unresolved ambiguous DST time or a nonexistent DST time "
    "(without `nonexistentTime=\"shift_forward\"`) are rejected with 422."
)


# ── Request ──────────────────────────────────────────────────────────────────


class TlstV2Request(BaseModel):
    """Birth data for the opt-in TLST routes. No location or zone defaults."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "date": "1990-07-15T15:44:00",
                "tz": "Europe/Berlin",
                "lat": 52.3759,
                "lon": 9.732,
                "standard": "TLST",
                "boundary": "midnight",
                "nonexistentTime": "error",
                "birth_time_known": True,
            }
        },
    )

    date: str = Field(
        ..., min_length=1, max_length=64,
        description="Local ISO 8601 birth wall-clock WITHOUT a UTC offset (seconds and microseconds allowed).",
    )
    tz: str = Field(..., min_length=1, max_length=128, description="IANA timezone of the birth place.")
    lat: float = Field(..., ge=-90.0, le=90.0, allow_inf_nan=False, description="Birth latitude, degrees north.")
    lon: float = Field(
        ..., ge=-180.0, le=180.0, allow_inf_nan=False,
        description="Birth longitude, degrees east (negative = west). Drives the TLST correction.",
    )
    standard: Literal["TLST"] = Field(..., description="Time standard. Only \"TLST\" is accepted on this route.")
    boundary: Literal["midnight", "zi"] = Field(
        ..., description="Day rule: apparent-solar midnight, or zi hour start (TLST 23:00).",
    )
    ambiguousTime: Optional[Literal["earlier", "later"]] = Field(
        None,
        description=(
            "Required when the wall-clock is ambiguous (DST fall-back): \"earlier\" = first "
            "occurrence (fold 0), \"later\" = second (fold 1). Omitted + ambiguous → 422."
        ),
    )
    nonexistentTime: Literal["error", "shift_forward"] = Field(
        "error", description="DST spring-forward gap: reject (default) or shift to the next valid minute.",
    )
    birth_time_known: bool = Field(
        True, description="False if the birth time is uncertain — flags the hour pillar as provisional.",
    )


class TlstV2InputEcho(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str
    tz: str
    lat: float
    lon: float
    standard: Literal["TLST"]
    boundary: Literal["midnight", "zi"]
    ambiguousTime: Optional[Literal["earlier", "later"]]
    nonexistentTime: Literal["error", "shift_forward"]
    birth_time_known: bool


# ── Response blocks ──────────────────────────────────────────────────────────


class TlstEdgeUncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    edge_hours: float = Field(..., description="Nearest decision edge on the TLST dial (0.0 = solar midnight).")
    kinds: List[Literal["hour_branch", "zi_day_start", "solar_midnight"]]
    distance_minutes: float
    tolerance_minutes: float = Field(..., description="Documented Meeus-vs-Swiss-Ephemeris EoT bound.")
    status: Literal["clear", "within_eot_tolerance"]


class SolarTermUncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nearest_boundary_utc: str = Field(..., description="Nearest jie (month) boundary incl. LiChun, UTC.")
    distance_seconds: float
    accuracy_seconds: float = Field(..., description="Solar-term crossing search accuracy used by the engine.")
    status: Literal["clear", "within_accuracy"]


class TimeBasisUncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["clear", "boundary_within_tolerance"]
    tlst_edge: TlstEdgeUncertainty
    solar_term: SolarTermUncertainty


class TlstTimeBasis(BaseModel):
    """What the engine actually used for this chart."""

    model_config = ConfigDict(extra="forbid")
    standard: Literal["TLST"]
    input_local: str
    resolved_local: str
    timezone: str
    fold: int
    local_time_status: Literal["ok", "ambiguous", "nonexistent_shifted"]
    adjusted_minutes: int
    local_time_warning_code: Optional[str]
    utc_offset_minutes: int
    utc: str
    longitude_deg: float
    lmt: str
    tlst_hours: float = Field(..., description="Apparent solar hour-of-day in [0, 24), truncated to 1 µs·h⁻¹ steps.")
    tlst_date: str = Field(..., description="Apparent-solar calendar date (civil date + tlst_date_rollover).")
    tlst_date_rollover: int
    eot_minutes: float
    eot_source: str
    hour_branch_basis: Literal["tlst_hours"]
    day_boundary: Literal["midnight", "zi"]
    day_boundary_rule: Literal["tlst_solar_midnight", "tlst_zi_hour"]
    zi_start_hour: float
    day_pillar_date: str = Field(..., description="Calendar date whose sexagenary day was used for the day pillar.")
    uncertainty: TimeBasisUncertainty


class TlstPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time_standard: Literal["TLST"]
    opt_in: bool
    v1_default_standard: str
    ruleset_id: str
    ruleset_version: str
    day_anchor_id: str
    day_anchor_verification: str = Field(..., description="Verbatim ruleset status; \"unverified\" = no domain sign-off.")


class BaziTlstV2Response(BaseModel):
    input: TlstV2InputEcho
    pillars: BaziPillarsResponse
    chinese: ChineseSection
    dates: BaziDatesResponse
    transition: BaziTransitionResponse
    solar_terms_count: int
    provenance: ProvenanceResponse
    quality_flags: MinimalQualityFlags
    precision: PrecisionBlock
    derivation_trace: BaziDerivationTrace
    time_basis: TlstTimeBasis
    policy: TlstPolicy


class NatalTlstV2Response(_natal_v1.NatalResponse):
    """The v1 natal shape plus the shared TLST ``input``/``time_basis``/``policy``."""

    input: TlstV2InputEcho
    time_basis: TlstTimeBasis
    policy: TlstPolicy


# ── Shared computation ───────────────────────────────────────────────────────


def _resolve_instant(req: TlstV2Request) -> ResolvedInstant:
    """Exactly one physical instant, or a 422 — never a silent fold choice."""
    resolved = resolve_local_instant(
        req.date,
        req.tz,
        ambiguous=req.ambiguousTime or "earlier",
        nonexistent=req.nonexistentTime,
    )
    if resolved.status == "ambiguous" and req.ambiguousTime is None:
        # No echo of the wall-clock or zone (birth-data PII, see time_utils).
        raise LocalTimeError(
            "Ambiguous local time during a DST fall-back transition. Set "
            "ambiguousTime to 'earlier' or 'later'; /v2 does not choose silently."
        )
    return resolved


def _compute_tlst_chart(req: TlstV2Request) -> Tuple[BaziResult, BaziInput, ResolvedInstant]:
    resolved = _resolve_instant(req)
    inp = BaziInput(
        birth_local=resolved.civil_local.replace(tzinfo=None).isoformat(),
        timezone=req.tz,
        longitude_deg=req.lon,
        latitude_deg=req.lat,
        time_standard=req.standard,
        day_boundary=req.boundary,
        strict_local_time=True,
        fold=1 if resolved.fold else 0,
    )
    return compute_bazi(inp), inp, resolved


def _solar_term_uncertainty(res: BaziResult, accuracy_seconds: float) -> Dict[str, Any]:
    bounds = list(res.month_boundaries_local_dt)
    birth_utc = res.birth_utc_dt
    nearest = min(bounds, key=lambda b: abs((b - birth_utc).total_seconds()))
    distance = abs((nearest - birth_utc).total_seconds())
    return {
        "nearest_boundary_utc": nearest.astimezone(timezone.utc).isoformat(),
        "distance_seconds": round(distance, 3),
        "accuracy_seconds": accuracy_seconds,
        "status": "within_accuracy" if distance <= accuracy_seconds else "clear",
    }


def _time_basis(
    res: BaziResult,
    inp: BaziInput,
    resolved: ResolvedInstant,
    ruleset: Dict[str, Any],
) -> Dict[str, Any]:
    # Same function, same aware instant, same longitude as compute_bazi's own
    # TLST context (bazi._effective_time_context_for_input) — a report of the
    # value the engine used, not a second derivation.
    ctx = compute_effective_time_context_from_instant(res.birth_local_dt, inp.longitude_deg)
    if res.chart_day_dt is None:  # compute_bazi always sets it; fail loudly if not
        raise RuntimeError("compute_bazi returned no chart_day_dt")
    zi_start = float(((ruleset.get("day_change_policy") or {}).get("zi_start_hour", 23.0)))
    edge = nearest_tlst_decision_edge(ctx.tlst_hours, day_boundary=inp.day_boundary, zi_start_hour=zi_start)
    solar_term = _solar_term_uncertainty(res, inp.accuracy_seconds)
    edge_block = {
        "edge_hours": edge.edge_hours,
        "kinds": list(edge.kinds),
        "distance_minutes": round(edge.distance_minutes, 4),
        "tolerance_minutes": EOT_MODEL_TOLERANCE_MINUTES,
        "status": "within_eot_tolerance" if edge.within_eot_tolerance else "clear",
    }
    overall = (
        "boundary_within_tolerance"
        if edge.within_eot_tolerance or solar_term["status"] == "within_accuracy"
        else "clear"
    )
    tlst_date = ctx.civil_local.date() + timedelta(days=ctx.date_rollover)
    return {
        "standard": inp.time_standard,
        "input_local": resolved.input_local_iso,
        "resolved_local": resolved.civil_local.isoformat(),
        "timezone": resolved.timezone,
        "fold": resolved.fold,
        "local_time_status": resolved.status,
        "adjusted_minutes": resolved.adjusted_minutes,
        "local_time_warning_code": resolved.warning_code,
        "utc_offset_minutes": int(round(resolved.utc_offset_seconds / 60)),
        "utc": ctx.utc.isoformat(),
        "longitude_deg": inp.longitude_deg,
        "lmt": ctx.lmt_local.isoformat(),
        "tlst_hours": ctx.tlst_hours,
        "tlst_date": tlst_date.isoformat(),
        "tlst_date_rollover": ctx.date_rollover,
        "eot_minutes": ctx.eot_minutes,
        "eot_source": ctx.eot_source,
        "hour_branch_basis": "tlst_hours",
        "day_boundary": inp.day_boundary,
        "day_boundary_rule": "tlst_zi_hour" if inp.day_boundary == "zi" else "tlst_solar_midnight",
        "zi_start_hour": zi_start,
        "day_pillar_date": res.chart_day_dt.date().isoformat(),
        "uncertainty": {"status": overall, "tlst_edge": edge_block, "solar_term": solar_term},
    }


def _policy(ruleset: Dict[str, Any]) -> Dict[str, Any]:
    anchor = (ruleset.get("day_cycle_anchor") or {})
    ruleset_id = str(ruleset.get("ruleset_id", "MISSING"))
    verification = str(anchor.get("anchor_verification", "MISSING"))
    return {
        "time_standard": "TLST",
        "opt_in": True,
        # Read from the frozen v1 model, not restated here.
        "v1_default_standard": str(_bazi_v1.BaziRequest.model_fields["standard"].default),
        "ruleset_id": ruleset_id,
        "ruleset_version": str(ruleset.get("ruleset_version", "MISSING")),
        "day_anchor_id": f"{ruleset_id}:jdn_{anchor.get('anchor_jdn', 'MISSING')}_{verification}",
        "day_anchor_verification": verification,
    }


def _bazi_payload(req: TlstV2Request, res: BaziResult, inp: BaziInput, resolved: ResolvedInstant) -> Dict[str, Any]:
    ruleset = load_default_ruleset()
    return {
        "input": req.model_dump(),
        "pillars": {
            "year": format_pillar(res.pillars.year),
            "month": format_pillar(res.pillars.month),
            "day": format_pillar(res.pillars.day),
            "hour": format_pillar(res.pillars.hour),
        },
        "chinese": {
            "year": {
                "stem": STEMS[res.pillars.year.stem_index],
                "branch": BRANCHES[res.pillars.year.branch_index],
                "animal": ANIMALS[res.pillars.year.branch_index],
            },
            "month_master": STEMS[res.pillars.month.stem_index],
            "day_master": STEMS[res.pillars.day.stem_index],
            "hour_master": STEMS[res.pillars.hour.stem_index],
        },
        "dates": {
            "birth_local": res.birth_local_dt.isoformat(),
            "birth_utc": res.birth_utc_dt.isoformat(),
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
        "quality_flags": {"ephemeris_mode": current_ephemeris_mode()},
        "precision": {
            "birth_time_known": req.birth_time_known,
            "provisional_fields": [] if req.birth_time_known else ["hour"],
        },
        "derivation_trace": _bazi_v1._build_derivation_trace(res, inp, requested_standard=req.standard),
        "time_basis": _time_basis(res, inp, resolved, ruleset),
        "policy": _policy(ruleset),
    }


def _natal_payload(req: TlstV2Request, res: BaziResult, inp: BaziInput, resolved: ResolvedInstant) -> Dict[str, Any]:
    ruleset = load_default_ruleset()
    chart = normalize_chart(res, birth_time_known=req.birth_time_known, subject="natal", ruleset=ruleset)
    analysis = analyze_individual(chart, subject="natal", ruleset=ruleset)
    # The v1 natal assembler reads only ``birth_time_known`` from its request;
    # the request is rebuilt faithfully so a future reader sees the real input.
    natal_req = _natal_v1.NatalRequest(
        date=req.date,
        tz=req.tz,
        lat=req.lat,
        lon=req.lon,
        standard=req.standard,
        boundary=req.boundary,
        ambiguousTime="later" if resolved.fold else "earlier",
        nonexistentTime=req.nonexistentTime,
        birth_time_known=req.birth_time_known,
    )
    payload = _natal_v1._assemble_response(natal_req, chart, analysis, ruleset)
    payload["input"] = req.model_dump()
    payload["time_basis"] = _time_basis(res, inp, resolved, ruleset)
    payload["policy"] = _policy(ruleset)
    return payload


# ── Routes ───────────────────────────────────────────────────────────────────


@router.post(
    "/bazi",
    response_model=BaziTlstV2Response,
    summary="BaZi Four Pillars in True Local Solar Time (opt-in)",
    description=_RELEASE_NOTE,
)
@limiter.limit(tier_limit)
def calculate_bazi_tlst_v2_endpoint(request: Request, req: TlstV2Request) -> Dict[str, Any]:
    """Four Pillars with the explicit TLST policy and the full derivation trace."""
    try:
        res, inp, resolved = _compute_tlst_chart(req)
        return _bazi_payload(req, res, inp, resolved)
    except BaziEngineError:
        raise
    except Exception:
        _log.exception("TLST v2 BaZi calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


@router.post(
    "/bazi/natal",
    response_model=NatalTlstV2Response,
    summary="BaZi natal analysis in True Local Solar Time (opt-in)",
    description=(
        _RELEASE_NOTE
        + "\n\nSame instant, TLST policy and four pillars as `POST /v2/calculate/bazi` "
        "for identical input; hidden stems, Ten Gods and the month command are the "
        "v1 natal facts computed on that shared chart. No day-master strength or "
        "yong shen is emitted."
    ),
)
@limiter.limit(tier_limit)
def calculate_natal_tlst_v2_endpoint(request: Request, req: TlstV2Request) -> Dict[str, Any]:
    """Natal hidden stems, Ten Gods and month command on the shared TLST chart."""
    try:
        res, inp, resolved = _compute_tlst_chart(req)
        return _natal_payload(req, res, inp, resolved)
    except BaziEngineError:
        raise
    except Exception:
        _log.exception("TLST v2 natal calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")


__all__ = ["router", "TlstV2Request", "BaziTlstV2Response", "NatalTlstV2Response"]
