"""routers/relationship.py — POST /v1/relationship/synastry (G1 + G1b).

Level 5 HTTP seam over the Level-4 ``bazi_engine.synastry`` package. Mounted at
/v1 ONLY (like Hehun): a new B2B surface never gets a legacy unauthenticated
twin. Both charts come from the existing ``compute_western_chart`` (no own
ephemeris). No score, no interpretation. Consent parity with Hehun (D4).
Birth data and display labels never reach a log line; the only log record on
the success path is the consent hash with the request id.
Decisions: docs/superpowers/specs/2026-11-08-synastry-g1-design.md.
"""
from __future__ import annotations

import logging
import re
from datetime import timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.requests import Request

from ..exc import BaziEngineError
from ..limiter import limiter, tier_limit
from ..match.privacy import log_consent_decision
from ..synastry import SynastryPersonInput, compute_synastry, extract_factors
from ..synastry.policy import (
    MOON_RANGE_LOCAL_TIMES,
    UNKNOWN_TIME_ASSUMED_LOCAL,
    UNKNOWN_TIME_ASSUMPTION_REASON,
    unknown_time_day,
)
from ..time_utils import AmbiguousTimeChoice, NonexistentTimePolicy, resolve_local_iso
from ..western import compute_western_chart

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/relationship", tags=["Relationship"])

# Letters with single inner separators; no digits, no "@" (first name or initial only).
_LABEL_PATTERN = r"^[^\W\d_]+(?:[ .'\-][^\W\d_]+)*\.?$"

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_CONSENT_DESCRIPTION = (
    "Confirms the second person has agreed to their birth data being used for this "
    "one-off synastry. Required: the request is rejected when this is false or absent. "
    "No data is persisted."
)

PersonLabel = Literal["person_a", "person_b"]
AspectType = Literal["conjunction", "sextile", "square", "trine", "opposition"]
SignRelation = Literal["same_sign", "semi_sextile", "sextile", "square", "trine", "quincunx", "opposition"]
ElementRelation = Literal["same", "complementary", "other"]
OverlayStatus = Literal["ok", "unavailable_missing_time"]
WestElement = Literal["Feuer", "Erde", "Luft", "Wasser"]

# ── Request ──────────────────────────────────────────────────────────────────
class SynastryPerson(BaseModel):
    """One person — the /calculate/western birth fields, but date/tz/lon/lat are required (D5)."""

    model_config = ConfigDict(extra="forbid")

    date: str = Field(..., description="Local ISO8601 datetime")
    tz: str = Field(..., description="IANA timezone name")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    ambiguousTime: AmbiguousTimeChoice = Field("earlier")
    nonexistentTime: NonexistentTimePolicy = Field("error")
    birth_time_known: bool = Field(
        True, description="False if the birth time is unknown: no ascendant, MC or houses for this person.",
    )
    display_label: Optional[str] = Field(
        None, min_length=1, max_length=40, pattern=_LABEL_PATTERN,
        description="Optional first name or initial, echoed in `subjects`. Never logged.",
    )
    @model_validator(mode="after")
    def _date_matches_the_birth_time_gate(self) -> "SynastryPerson":
        if self.birth_time_known and _DATE_ONLY.match(self.date.strip()):
            raise ValueError("date needs a time part when birth_time_known is true")
        if not self.birth_time_known:
            unknown_time_day(self.date)  # ValueError without the value → 422 validation_error (D14)
        return self

class SynastryOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    second_person_consent_confirmed: bool = Field(..., description=_CONSENT_DESCRIPTION)

class SynastryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "person_a": {"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52,
                     "display_label": "A."},
        "person_b": {"date": "1992-11-03T08:15:00", "tz": "Europe/Vienna", "lon": 16.3738, "lat": 48.2082,
                     "display_label": "B."},
        "options": {"second_person_consent_confirmed": True},
    }})

    person_a: SynastryPerson
    person_b: SynastryPerson
    options: SynastryOptions

# ── Response ─────────────────────────────────────────────────────────────────
class SynastryAspect(BaseModel):
    from_person: PersonLabel
    from_factor: str
    to_person: PersonLabel
    to_factor: str
    type: AspectType
    exact_angle: float
    orb: float = Field(..., description="Deviation from the exact angle in degrees (4 dp)")
    tight: bool = Field(..., description="True when the orb is at most half the orb limit (a tight aspect)")
    time_sensitive: bool = Field(
        ..., description="True when the aspect type is not the same at local 00:00 and 23:59 of an unknown-time Moon "
        "(all four corners for Moon–Moon with both times unknown); always false otherwise",
    )
    from_weight: float
    to_weight: float
    weight: float = Field(..., description="from_weight × to_weight (tier weights, synastry-weights-v1)")

class SynastryHouseOverlay(BaseModel):
    factor: str
    house: Optional[int] = Field(None, ge=1, le=12)
    status: OverlayStatus

class SynastryHouseOverlays(BaseModel):
    a_in_b: List[SynastryHouseOverlay]
    b_in_a: List[SynastryHouseOverlay]

class SynastrySignFactor(BaseModel):
    factor: str
    sign: str
    sign_index: int = Field(..., ge=0, le=11)
    west_element: WestElement
    degree: float
    sign_certain: Optional[bool] = Field(
        None, description="Moon of an unknown-time person only: true when the Moon stays in one sign over the "
        "local day (00:00–23:59); null for every other entry",
    )
    moon_range_deg: Optional[List[float]] = Field(
        None, min_length=2, max_length=2,
        description="Moon of an unknown-time person only: [start, end] longitude at local 00:00 and 23:59 "
        "(4 dp, [0, 360), forward; end < start when the range crosses 0°); null for every other entry",
    )

class SynastrySignFactors(BaseModel):
    person_a: List[SynastrySignFactor]
    person_b: List[SynastrySignFactor]

class SynastrySignPair(BaseModel):
    factor_a: str
    factor_b: str
    sign_relation: SignRelation
    element_relation: ElementRelation

class SynastrySignLayer(BaseModel):
    factors: SynastrySignFactors
    pairs: List[SynastrySignPair]

class SynastryWuXingFactor(BaseModel):
    factor: str
    west_element: WestElement
    weight: float
    vector: List[float] = Field(..., min_length=5, max_length=5)

class SynastryWuXingPerson(BaseModel):
    factors: List[SynastryWuXingFactor]
    vector: List[float] = Field(..., min_length=5, max_length=5, description="Tier-weighted mean, sums to 1")

class SynastryWuXingPairFactors(BaseModel):
    order: List[str]
    person_a: SynastryWuXingPerson
    person_b: SynastryWuXingPerson
    mapping_version: str

class SynastryWarning(BaseModel):
    code: Literal["birth_time_unknown", "house_system_fallback"]
    person: PersonLabel
    detail: str

class SynastryHouseSystems(BaseModel):
    person_a: Optional[str] = None
    person_b: Optional[str] = None

class SynastryProvenance(BaseModel):
    engine_version: str
    ephemeris_mode: str
    zodiac_mode: Literal["tropical"]
    house_system_used: SynastryHouseSystems
    orb_policy_id: str
    weighting_id: str
    base_weighting_id: str
    mapping_version: str
    warnings: List[SynastryWarning]

class SynastrySubject(BaseModel):
    display_label: Optional[str] = None
    birth_time_known: bool
    assumed_local_time: Optional[str] = Field(
        None, description="Local time the chart was computed at when the birth time is unknown (12:00:00), else null",
    )
    assumption_reason: Optional[str] = Field(
        None, description="birth_time_unknown when the birth time is unknown, else null",
    )

class SynastrySubjects(BaseModel):
    person_a: SynastrySubject
    person_b: SynastrySubject

class SynastryResponse(BaseModel):
    aspects: List[SynastryAspect]
    house_overlays: SynastryHouseOverlays
    sign_layer: SynastrySignLayer
    wuxing_pair_factors: SynastryWuXingPairFactors
    provenance: SynastryProvenance
    subjects: SynastrySubjects

# ── Handler ──────────────────────────────────────────────────────────────────
def _chart_at(local_iso: str, person: SynastryPerson) -> Dict[str, Any]:
    dt_local, _ = resolve_local_iso(
        local_iso, person.tz, ambiguous=person.ambiguousTime, nonexistent=person.nonexistentTime,
    )
    return compute_western_chart(dt_local.astimezone(timezone.utc), person.lat, person.lon)

def _person_input(person: SynastryPerson) -> SynastryPersonInput:
    if person.birth_time_known:
        return SynastryPersonInput(chart=_chart_at(person.date, person), birth_time_known=True)
    # D14: the calendar day is authoritative; the supplied clock time is never used.
    day, time_discarded = unknown_time_day(person.date)
    chart = _chart_at(f"{day}T{UNKNOWN_TIME_ASSUMED_LOCAL}", person)
    start, end = (_moon_at(f"{day}T{hms}", person) for hms in MOON_RANGE_LOCAL_TIMES)
    return SynastryPersonInput(
        chart=chart, birth_time_known=False, time_discarded=time_discarded, moon_bounds=(start, end),
    )

def _moon_at(local_iso: str, person: SynastryPerson) -> float:
    """D15 bound: Moon longitude at a fixed local time; midnight can fall in a DST gap."""
    dt_local, _ = resolve_local_iso(local_iso, person.tz, ambiguous="earlier", nonexistent="shift_forward")
    chart = compute_western_chart(dt_local.astimezone(timezone.utc), person.lat, person.lon)
    return extract_factors(chart, birth_time_known=False)["Moon"]

def _subject(person: SynastryPerson) -> Dict[str, Any]:
    unknown = not person.birth_time_known
    return {
        "display_label": person.display_label,
        "birth_time_known": person.birth_time_known,
        "assumed_local_time": UNKNOWN_TIME_ASSUMED_LOCAL if unknown else None,
        "assumption_reason": UNKNOWN_TIME_ASSUMPTION_REASON if unknown else None,
    }

@router.post("/synastry", response_model=SynastryResponse)
@limiter.limit(tier_limit)
def synastry_endpoint(request: Request, req: SynastryRequest) -> Dict[str, Any]:
    """Western synastry facts for two people: cross aspects (synastry-orbs-v1), house overlays, sign layer and its Wu-Xing translation (sign-element-consensus-v1). Deterministic; no interpretation and no compatibility rating of any kind. Second-person consent is required; birth data is never logged or persisted."""
    request_id = getattr(request.state, "request_id", "unknown")
    log_consent_decision(request_id, req.options.second_person_consent_confirmed)
    if not req.options.second_person_consent_confirmed:
        raise HTTPException(status_code=422, detail={
            "error": "consent_required",
            "message": "Second-person consent is required for this synastry and must be confirmed (true).",
            "detail": {"code": "consent_required", "field": "options.second_person_consent_confirmed"},
        })
    try:
        result = compute_synastry(_person_input(req.person_a), _person_input(req.person_b))
    except BaziEngineError:
        raise
    except Exception:
        _log.exception("synastry calculation failed request_id=%s", request_id)
        raise HTTPException(status_code=500, detail={
            "error": "calculation_error", "message": "Internal calculation error", "detail": {},
        })
    result["subjects"] = {"person_a": _subject(req.person_a), "person_b": _subject(req.person_b)}
    return result
