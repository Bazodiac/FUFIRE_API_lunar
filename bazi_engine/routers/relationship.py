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
from datetime import timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from ..exc import BaziEngineError
from ..limiter import limiter, tier_limit
from ..match.privacy import log_consent_decision
from ..synastry import SynastryPersonInput, compute_synastry
from ..time_utils import AmbiguousTimeChoice, NonexistentTimePolicy, resolve_local_iso
from ..western import compute_western_chart

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/relationship", tags=["Relationship"])

# Letters with single inner separators; no digits, no "@" (first name or initial only).
_LABEL_PATTERN = r"^[^\W\d_]+(?:[ .'\-][^\W\d_]+)*\.?$"

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
    exact: bool = Field(..., description="True when the orb is at most half the orb limit")
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
def _person_input(person: SynastryPerson) -> SynastryPersonInput:
    dt_local, _ = resolve_local_iso(
        person.date, person.tz, ambiguous=person.ambiguousTime, nonexistent=person.nonexistentTime,
    )
    chart = compute_western_chart(dt_local.astimezone(timezone.utc), person.lat, person.lon)
    return SynastryPersonInput(chart=chart, birth_time_known=person.birth_time_known)

def _subject(person: SynastryPerson) -> Dict[str, Any]:
    return {"display_label": person.display_label, "birth_time_known": person.birth_time_known}

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
