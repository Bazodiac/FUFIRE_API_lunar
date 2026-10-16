"""routers/chronometry.py — POST /chronometry/resolve  (beta).

Thin FastAPI wrapper over the pure ``bazi_engine.chronometry`` module.
Every value returned here is engine-truth — the route does NOT recompute
anything; it serialises the ``ChronometryFrame`` produced by
``resolve_chronometry`` (see test_chronometry_endpoint::
test_endpoint_equals_pure_module for the anti-mockup lock).

Request shape follows the PRD nested BirthContext:
``birth.{datetime, timezone, location.{lat, lon}, calendar_policy}``.
Date-only ``datetime`` or ``time_known=false`` triggers the unknown-time
path (no noon default; ``true_solar_time`` null; grade ``unknown_time``).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from ..chronometry import resolve_chronometry
from ..limiter import limiter, tier_limit
from ..time_utils import AmbiguousTimeChoice, NonexistentTimePolicy

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/chronometry", tags=["Chronometry (beta)"])


# ── Request models (PRD nested BirthContext) ────────────────────────────────

class LocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")


class BirthContext(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "datetime": "1990-06-15T14:30:00",
                "timezone": "Europe/Berlin",
                "location": {"lat": 52.52, "lon": 13.405},
                "calendar_policy": "gregorian",
            }
        },
    )
    datetime: str = Field(
        ...,
        description=(
            "Local ISO 8601 datetime (e.g. '1990-06-15T14:30:00'). A "
            "date-only value (e.g. '1990-06-15') is treated as time-unknown: "
            "no noon default is applied and true_solar_time is null."
        ),
    )
    timezone: str = Field(..., description="IANA timezone name (e.g. 'Europe/Berlin')")
    location: LocationInput
    calendar_policy: Optional[str] = Field(
        None, description="Reserved calendar-selection hint (no effect yet)."
    )
    time_known: bool = Field(
        True,
        description=(
            "Set False when the birth time is not known. Forces the "
            "unknown-time path (no noon default, true_solar_time null, "
            "precision.grade='unknown_time')."
        ),
    )
    ambiguousTime: AmbiguousTimeChoice = Field(
        "earlier",
        description=(
            "Which instant to use when the local time occurs twice (DST "
            "fall-back): 'earlier' (default) or 'later'. Same semantics as "
            "/calculate/bazi and /calculate/tst."
        ),
    )
    nonexistentTime: NonexistentTimePolicy = Field(
        "error",
        description=(
            "Policy for a local time skipped by a DST spring-forward: 'error' "
            "(default, 422) or 'shift_forward'. Same semantics as /calculate/bazi."
        ),
    )


class ChronometryResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    birth: BirthContext


# ── Response models (typed for OpenAPI / codegen) ───────────────────────────

class PrecisionInfo(BaseModel):
    grade: str = Field(..., description="exact | degraded | unknown_time | unresolved")
    warnings: list[str] = Field(default_factory=list)
    algorithm_version: str


class BoundaryFlags(BaseModel):
    lichun_jd_ut: float
    is_before_lichun: bool
    near_lichun: bool
    days_from_lichun: float


class ChronometryFrameResponse(BaseModel):
    julian_day: float = Field(..., description="Fractional UT Julian Day")
    julian_day_number: int = Field(..., description="JDN of the resolved civil date")
    delta_t_seconds: float
    equation_of_time_minutes: float
    eot_source: str = Field(
        ..., description='Provenance of equation_of_time_minutes, e.g. "meeus_1998" (FBP-TST-006)'
    )
    longitude_correction_minutes: float = Field(..., description="lon * 4 minutes")
    true_solar_time: Optional[str] = Field(
        None, description="HH:MM apparent solar time; null when birth time unknown"
    )
    tlst_date_rollover: Optional[int] = Field(
        None,
        description=(
            "Calendar-day shift of the apparent-solar (TLST) date relative to the "
            "civil date (−2…+1): true_solar_time belongs to civil date + this many "
            "days, while julian_day_number stays the civil date's JDN. Null when "
            "birth time unknown."
        ),
    )
    solar_longitude_degrees: float
    solar_term: str = Field(..., description="JIEQI_NAMES[floor(solar_longitude / 15)]")
    boundary_flags: BoundaryFlags
    precision: PrecisionInfo


class ChronometryResolveResponse(BaseModel):
    request_id: str
    chronometry: ChronometryFrameResponse


@router.post("/resolve", response_model=ChronometryResolveResponse)
@limiter.limit(tier_limit)
def resolve_chronometry_endpoint(
    request: Request, req: ChronometryResolveRequest
) -> Dict[str, Any]:
    """Resolve a birth instant into a full chronometry frame (beta).

    Exposes the deterministic time/ephemeris engine: Julian Day (fractional
    UT + civil-date JDN), ΔT, equation of time, longitude correction, true
    solar time, live solar longitude, the corresponding solar term, and Li
    Chun boundary flags. Numbers equal the in-process engine exactly.

    Unknown birth time (date-only input or `time_known=false`) →
    `precision.grade="unknown_time"`, `true_solar_time=null`, with an
    explanatory warning. No silent noon default is ever applied.
    """
    birth = req.birth
    # LocalTimeError (invalid tz / unparseable datetime) is an InputError
    # subclass → mapped to a stable 422 ErrorEnvelope by app.py. Let it
    # propagate; do NOT swallow into a 500.
    frame = resolve_chronometry(
        birth_datetime=birth.datetime,
        timezone=birth.timezone,
        lat=birth.location.lat,
        lon=birth.location.lon,
        calendar_policy=birth.calendar_policy,
        time_known=birth.time_known,
        ambiguous_time=birth.ambiguousTime,
        nonexistent_time=birth.nonexistentTime,
    )
    return {
        "request_id": getattr(request.state, "request_id", "unknown"),
        "chronometry": {
            "julian_day": frame.julian_day,
            "julian_day_number": frame.julian_day_number,
            "delta_t_seconds": frame.delta_t_seconds,
            "equation_of_time_minutes": frame.equation_of_time_minutes,
            "eot_source": frame.eot_source,
            "longitude_correction_minutes": frame.longitude_correction_minutes,
            "true_solar_time": frame.true_solar_time,
            "tlst_date_rollover": frame.tlst_date_rollover,
            "solar_longitude_degrees": frame.solar_longitude_degrees,
            "solar_term": frame.solar_term,
            "boundary_flags": frame.boundary_flags,
            "precision": frame.precision,
        },
    }
