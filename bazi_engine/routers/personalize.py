"""routers/personalize.py — POST /personalize  (+ /v1/personalize).

REQ-002 / REQ-003. Aggregates INTERNAL engine compute (NOT HTTP self-calls)
— geocoding (REQ-001) + bazi + wuxing + bazi trace + chronometry — and maps
the assembled engine response shapes into the small set of flat prompt
variables the downstream prompt template needs, with provenance, issues, and
caveats.

This is the value-critical "no invented data" boundary, ported from the TS
consumer interpreter
(``Sizhu_middleware/server/services/fufireResponseInterpreter.ts``):

  - animal           ← de: bazi.pillars.year.tier / en: bazi.chinese.year.animal
  - element          ← bazi.pillars.year.element
  - birth_year       ← bazi.transition.solar_year  (a finite number)
  - dominant_element ← wuxing.dominant_element

A source that is absent / empty / the wrong type yields a NULL variable plus a
``PROMPT_VARIABLE_SOURCE_MISSING`` issue — never a default or a guess. The
day-pillar ``anchor_verification`` caveat is surfaced verbatim, never laundered.

domain_extras carries the REAL engine outputs (bazi_trace + chronometry) — the
REQ-003 migration (the old interpreter render-blocked these as "no real
sample"; this endpoint provides the real data).

The four module-level aggregation seams (``_compute_bazi_for``,
``_compute_wuxing_for``, ``_compute_chronometry_for``, ``_resolve_location``)
are the T2↔T3 mock-seam contract (see test_personalize_endpoint.py): each
routes to the REAL engine compute, and the acceptance tests patch them by name.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.requests import Request

from ..chronometry import resolve_chronometry
from ..limiter import limiter, tier_limit
from ..services.geocoding import (
    AMBIGUITY_THRESHOLD,
    compute_confidence,
    geocode_candidates,
    project_candidate,
)
from .bazi import BaziRequest, _compute_bazi_response
from .fusion import WxRequest, _compute_wuxing_response

_log = logging.getLogger(__name__)

router = APIRouter(tags=["Personalize"])

# The literal token recorded whenever a required prompt-variable source is
# absent. Downstream code and the contract test grep for this EXACT string
# (byte-matches the TS const) — it MUST NOT be reworded.
PROMPT_VARIABLE_SOURCE_MISSING = "PROMPT_VARIABLE_SOURCE_MISSING"


# ── Request / response models ────────────────────────────────────────────────

class PersonalizeRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "birth_datetime": "1990-06-15T14:30:00",
                "place": "Berlin, DE",
                "birth_time_known": True,
                "locale": "en",
            }
        },
    )

    birth_datetime: str = Field(
        ..., description="Local ISO 8601 birth datetime (e.g. '1990-06-15T14:30:00')."
    )
    # Location is oneOf: EITHER place OR (lat + lon + tz). Enforced below.
    place: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Place name (resolved via internal geocoding). Mutually exclusive with lat/lon/tz.",
    )
    lat: Optional[float] = Field(
        None, ge=-90.0, le=90.0, description="Latitude in degrees (requires lon + tz)."
    )
    lon: Optional[float] = Field(
        None, ge=-180.0, le=180.0, description="Longitude in degrees (requires lat + tz)."
    )
    tz: Optional[str] = Field(
        None, description="IANA timezone name (requires lat + lon)."
    )
    birth_time_known: bool = Field(
        True, description="False if birth time is uncertain — flags time-dependent outputs as provisional."
    )
    locale: Literal["de", "en"] = Field(
        "en", description="Render locale; selects the (paired) animal source."
    )
    # Resolved location {lat, lon, tz}, populated by the route after
    # _resolve_location runs. Excluded from the OpenAPI/request schema — it is
    # never client-supplied. Kept on the request so the compute seams match the
    # documented single-arg (req) contract without re-resolving the location.
    resolved_location: Optional[Dict[str, Any]] = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _validate_location_oneof(self) -> "PersonalizeRequest":
        """Exactly one of {place} XOR {lat, lon, tz} must be fully provided."""
        has_place = self.place is not None
        coord_parts = [self.lat is not None, self.lon is not None, self.tz is not None]
        has_full_coords = all(coord_parts)
        has_any_coords = any(coord_parts)

        if has_place and has_any_coords:
            raise ValueError(
                "Provide EITHER 'place' OR ('lat' + 'lon' + 'tz'), not both."
            )
        if not has_place and not has_any_coords:
            raise ValueError(
                "Location required: provide EITHER 'place' OR ('lat' + 'lon' + 'tz')."
            )
        if not has_place and not has_full_coords:
            raise ValueError(
                "Explicit coordinates require all of 'lat', 'lon', and 'tz'."
            )
        return self


class PersonalizeResponse(BaseModel):
    animal: Optional[str] = Field(None, description="Year-pillar animal (locale-paired). Null when source missing.")
    element: Optional[str] = Field(None, description="Year-pillar element. Null when source missing.")
    birth_year: Optional[int] = Field(None, description="Solar year. Null when source missing.")
    dominant_element: Optional[str] = Field(None, description="Wu-Xing dominant element. Null when source missing.")
    sources: Dict[str, str] = Field(default_factory=dict, description="Matched source path per resolved variable.")
    issues: List[str] = Field(default_factory=list, description="PROMPT_VARIABLE_SOURCE_MISSING entries for absent sources.")
    caveats: List[str] = Field(default_factory=list, description="Provider-declared caveats surfaced verbatim.")
    domain_extras: Dict[str, Any] = Field(default_factory=dict, description="Real engine outputs: bazi_trace + chronometry.")


# ── Safe traversal helpers (mirror the TS interpreter's readPath/resolve*) ────

def _read_path(root: Any, path: str) -> tuple[bool, Any]:
    """Read a dot-path; returns (found, value). found=False if any segment is
    missing or a non-mapping is traversed. Distinguishes a present null/0/""
    from an absent path."""
    current = root
    for segment in path.split("."):
        if not isinstance(current, dict) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def _resolve_string(root: Any, path: str) -> Optional[str]:
    """A present, non-empty string at ``path``; else None (missing)."""
    found, value = _read_path(root, path)
    if found and isinstance(value, str) and value.strip() != "":
        return value
    return None


def _resolve_number(root: Any, path: str) -> Optional[int]:
    """A present, finite number at ``path`` (as int); else None (missing).

    bool is rejected (it is an int subclass but never a valid solar year).
    """
    found, value = _read_path(root, path)
    if (
        found
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value == value  # reject NaN (NaN != NaN)
        and value not in (float("inf"), float("-inf"))
    ):
        return int(value)
    return None


def _missing_source_issue(variable: str, path: str) -> str:
    return f"{PROMPT_VARIABLE_SOURCE_MISSING}: {variable} (no source at {path})"


# Locale-driven animal source (paired; selected by locale, never mixed).
_ANIMAL_SOURCE_BY_LOCALE: Dict[str, str] = {
    "de": "pillars.year.tier",   # "Pferd"
    "en": "chinese.year.animal",  # "Horse"
}


# ── Aggregation seams (the T2↔T3 mock-seam contract) ──────────────────────────
# Each routes to the REAL engine compute. The acceptance tests patch these four
# by name and feed captured-sample-shaped payloads. NO stubs.

async def _resolve_location(req: PersonalizeRequest) -> Dict[str, Any]:
    """Resolve {lat, lon, tz} for the PLACE branch via internal geocoding.

    Invoked ONLY when ``req.place`` is given (the route uses explicit
    lat/lon/tz directly without this seam). Resolves via REQ-001
    ``geocode_candidates`` + the REQ-001 confidence rule (1 candidate → 1.0;
    >=2 → pop_top/(pop_top+pop_second); missing population → 0.5). confidence
    < 0.6 → 422 ambiguous_place; no candidates → 404 place_not_found.
    Open-Meteo supplies the timezone.
    """
    # _resolve_location is the PLACE branch only (gated by the caller); narrow for mypy.
    assert req.place is not None
    try:
        # m2: pass the request locale through so candidate names match the
        # render locale. req.locale is the Literal["de","en"] — the same codes
        # Open-Meteo's `language` param accepts — so map it 1:1 (default "de").
        candidates = await geocode_candidates(req.place, language=req.locale)
    except (httpx.HTTPError, ValueError) as exc:
        _log.warning("personalize.geocode_unavailable place=%r err=%s", req.place, exc)
        raise HTTPException(
            status_code=503, detail={"error": "geocoding_unavailable"}
        ) from exc

    if not candidates:
        raise HTTPException(status_code=404, detail={"error": "place_not_found"})

    confidence = compute_confidence(candidates)
    if confidence < AMBIGUITY_THRESHOLD:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "ambiguous_place",
                "candidates": [project_candidate(c) for c in candidates],
                "confidence": confidence,
            },
        )

    top = candidates[0]
    return {
        "lat": float(top["latitude"]),
        "lon": float(top["longitude"]),
        "tz": str(top.get("timezone") or ""),
    }


def _required_location(req: PersonalizeRequest) -> Dict[str, Any]:
    """The location resolved by the route (set on req.resolved_location).

    Raised loudly rather than silently geocoding twice if the route wiring is
    ever broken — the compute seams must run after _resolve_location.
    """
    location = req.resolved_location
    if not location:
        raise RuntimeError(
            "resolved_location not set — _resolve_location must run before compute seams"
        )
    return location


def _compute_bazi_for(req: PersonalizeRequest) -> Dict[str, Any]:
    """Real bazi response dict (pillars/chinese/transition/derivation_trace).

    Reuses ``routers/bazi._compute_bazi_response`` with ``force_trace=True`` so
    the derivation trace (carrying day_anchor_evidence.anchor_verification, the
    caveat source, and the domain_extras.bazi_trace) is always attached. NO new
    metaphysics math — the exact engine path /calculate/bazi uses.

    B1/M1 FIX: ``_compute_bazi_response`` returns ``derivation_trace`` as a
    Pydantic MODEL INSTANCE (``BaziDerivationTrace``), not a dict. The parity
    mapping's ``_read_path`` requires ``isinstance(current, dict)`` at every
    segment, so a model-instance trace would silently drop the verbatim
    day-anchor caveat (B1) and put a model — not a dict — into
    ``domain_extras.bazi_trace`` (M1). We normalise the WHOLE response to plain
    JSON types via ``_to_plain_dict`` so the assembled ``bazi`` is fully
    dict-shaped before the mapping and before ``domain_extras``.
    """
    location = _required_location(req)
    bazi_req = BaziRequest(
        date=req.birth_datetime,
        tz=str(location["tz"]),
        lon=float(location["lon"]),
        lat=float(location["lat"]),
        birth_time_known=req.birth_time_known,
        standard="CIVIL",
        boundary="midnight",
        ambiguousTime="earlier",
        nonexistentTime="error",
        include_trace=True,
    )
    return _to_plain_dict(_compute_bazi_response(bazi_req, force_trace=True))


def _to_plain_dict(response: Any) -> Dict[str, Any]:
    """Coerce a (possibly model-carrying) bazi response into plain JSON types.

    ``_compute_bazi_response`` returns a dict whose ``derivation_trace`` is a
    ``BaziDerivationTrace`` model (and may nest other models). ``_read_path``
    only traverses ``dict`` mappings, so any nested model must be turned into a
    plain dict first. ``model_dump(mode="json")`` is used per-model so nested
    values (datetimes, enums) become JSON-native — matching the captured-sample
    shapes the parity mapping was written against. Plain values pass through.
    """
    if isinstance(response, BaseModel):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return {key: _to_plain_value(value) for key, value in response.items()}
    raise TypeError(f"unexpected bazi response type: {type(response)!r}")


def _to_plain_value(value: Any) -> Any:
    """Recursively coerce models/containers within a value to plain JSON types."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _to_plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_value(item) for item in value]
    return value


def _compute_wuxing_for(req: PersonalizeRequest) -> Dict[str, Any]:
    """Real wuxing response dict (carrying dominant_element).

    Reuses ``routers/fusion._compute_wuxing_response`` — the exact engine path
    /calculate/wuxing uses.
    """
    location = _required_location(req)
    wx_req = WxRequest(
        date=req.birth_datetime,
        tz=str(location["tz"]),
        lon=float(location["lon"]),
        lat=float(location["lat"]),
    )
    return _compute_wuxing_response(wx_req)


def _compute_chronometry_for(req: PersonalizeRequest) -> Dict[str, Any]:
    """Real chronometry frame (domain_extras.chronometry).

    Reuses the pure ``bazi_engine.chronometry.resolve_chronometry`` and
    serialises it exactly like ``routers/chronometry`` does — engine-truth, no
    recompute.
    """
    location = _required_location(req)
    frame = resolve_chronometry(
        birth_datetime=req.birth_datetime,
        timezone=str(location["tz"]),
        lat=float(location["lat"]),
        lon=float(location["lon"]),
        time_known=req.birth_time_known,
    )
    return {
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
    }


# ── Parity mapping (EXACT — from the TS interpreter; EV-002-Parität) ──────────

def _map_prompt_variables(
    bazi: Dict[str, Any],
    wuxing: Dict[str, Any],
    locale: str,
) -> tuple[Dict[str, Any], Dict[str, str], List[str], List[str]]:
    """Map the assembled engine responses into the 4 flat prompt variables.

    Returns (variables, sources, issues, caveats). A missing/empty/wrong-type
    source yields a None variable + a PROMPT_VARIABLE_SOURCE_MISSING issue —
    never a default or guess. The day-pillar anchor_verification caveat is
    surfaced verbatim.
    """
    variables: Dict[str, Any] = {
        "animal": None,
        "element": None,
        "birth_year": None,
        "dominant_element": None,
    }
    sources: Dict[str, str] = {}
    issues: List[str] = []
    caveats: List[str] = []

    # animal — locale-driven, paired source, never mixed.
    animal_path = _ANIMAL_SOURCE_BY_LOCALE.get(locale, _ANIMAL_SOURCE_BY_LOCALE["en"])
    animal = _resolve_string(bazi, animal_path)
    if animal is not None:
        variables["animal"] = animal
        sources["animal"] = f"bazi.{animal_path}"
    else:
        issues.append(_missing_source_issue("animal", f"bazi.{animal_path}"))

    # element ← bazi.pillars.year.element
    element_path = "pillars.year.element"
    element = _resolve_string(bazi, element_path)
    if element is not None:
        variables["element"] = element
        sources["element"] = f"bazi.{element_path}"
    else:
        issues.append(_missing_source_issue("element", f"bazi.{element_path}"))

    # birth_year ← bazi.transition.solar_year (a finite number)
    birth_year_path = "transition.solar_year"
    birth_year = _resolve_number(bazi, birth_year_path)
    if birth_year is not None:
        variables["birth_year"] = birth_year
        sources["birth_year"] = f"bazi.{birth_year_path}"
    else:
        issues.append(_missing_source_issue("birth_year", f"bazi.{birth_year_path}"))

    # dominant_element ← wuxing.dominant_element (location-invariant western)
    dominant_path = "dominant_element"
    dominant = _resolve_string(wuxing, dominant_path)
    if dominant is not None:
        variables["dominant_element"] = dominant
        sources["dominant_element"] = f"wuxing.{dominant_path}"
    else:
        issues.append(_missing_source_issue("dominant_element", f"wuxing.{dominant_path}"))

    # Day-anchor caveat — surfaced verbatim, never laundered.
    anchor_path = "derivation_trace.day.day_anchor_evidence.anchor_verification"
    anchor = _resolve_string(bazi, anchor_path)
    if anchor is not None:
        caveats.append(f"day-pillar anchor_verification: {anchor}")
    else:
        issues.append(
            f"{PROMPT_VARIABLE_SOURCE_MISSING}: day-pillar anchor_verification "
            f"(no source at bazi.{anchor_path})"
        )

    return variables, sources, issues, caveats


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post("/personalize", response_model=PersonalizeResponse)
@limiter.limit(tier_limit)
async def personalize_endpoint(
    request: Request, req: PersonalizeRequest
) -> Dict[str, Any]:
    """Resolve a birth input into the flat prompt variables + provenance.

    Aggregates internal engine compute (geocode + bazi + wuxing + bazi trace +
    chronometry) and maps the assembled responses into the 4 prompt variables
    with provenance, issues, and verbatim caveats — never inventing data.
    domain_extras carries the real bazi_trace and chronometry engine outputs.
    """
    # Explicit coords are used directly (no geocode); the place branch resolves
    # through the _resolve_location seam (REQ-001 geocode + confidence rule).
    if req.place is not None:
        req.resolved_location = await _resolve_location(req)
    else:
        # Validator guarantees lat/lon/tz are all present here; narrow for mypy.
        assert req.lat is not None and req.lon is not None and req.tz is not None
        req.resolved_location = {
            "lat": float(req.lat),
            "lon": float(req.lon),
            "tz": str(req.tz),
        }

    bazi = _compute_bazi_for(req)
    wuxing = _compute_wuxing_for(req)
    chronometry = _compute_chronometry_for(req)

    variables, sources, issues, caveats = _map_prompt_variables(
        bazi, wuxing, req.locale
    )

    # domain_extras: REAL engine outputs (REQ-003 migration). bazi_trace is the
    # real derivation trace; chronometry is the real frame. Never flagged as
    # PROMPT_VARIABLE_SOURCE_MISSING — they are provided, not deferred.
    bazi_trace = bazi.get("derivation_trace")

    return {
        "animal": variables["animal"],
        "element": variables["element"],
        "birth_year": variables["birth_year"],
        "dominant_element": variables["dominant_element"],
        "sources": sources,
        "issues": issues,
        "caveats": caveats,
        "domain_extras": {
            "bazi_trace": bazi_trace,
            "chronometry": chronometry,
        },
    }
