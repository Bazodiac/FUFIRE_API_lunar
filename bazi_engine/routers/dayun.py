"""
routers/dayun.py — POST /calculate/bazi/dayun.

Da-Yun (大運, "Decade Pillars" / luck pillars) endpoint. Wires the DY-2
helpers into one route:

  1. compute_bazi() — natal four pillars (year/month/day/hour stems & branches).
  2. resolve_direction_for_request() — forward / backward flow direction.
  3. resolve_jieqi_anchor() — nearest jieqi crossing in the resolved direction.
  4. compute_start_age() — calendar delta → life-years (3 days = 1 year rule).
  5. jiazi_at() — month-pillar position in the 60-cycle, walked N steps.
  6. select_current() — which decade brackets ``as_of_date``.
  7. compute_relation_to_day_master() — Ten-Gods classification per decade.

Returns a payload conforming to
``schemas/calculate/bazi/dayun.response.schema.json`` (a regression test in
``tests/test_dayun_endpoint.py`` validates the response against that schema).
"""
from __future__ import annotations

import logging
import warnings
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.requests import Request

from ..bazi import compute_bazi
from ..dayun.current_cycle import select_current
from ..dayun.dates import add_real_years
from ..dayun.direction import resolve_direction_for_request
from ..dayun.interpretation import build_semantic_summary
from ..dayun.jiazi import STEMS, jiazi_at
from ..dayun.jieqi import resolve_jieqi_anchor
from ..dayun.relation import compute_relation_to_day_master
from ..dayun.start_age import compute_start_age
from ..exc import BaziEngineError
from ..limiter import limiter, tier_limit
from ..types import BaziInput, DayBoundary

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/calculate", tags=["BaZi", "Dayun"])


# ── Request model ────────────────────────────────────────────────────────────


class DayunRequest(BaseModel):
    """Request payload for POST /calculate/bazi/dayun.

    Mirrors ``schemas/calculate/bazi/dayun.request.schema.json``. The oneOf
    constraint between explicit / traditional direction modes is NOT
    enforced here — ``resolve_direction_for_request`` raises
    ``DirectionBasisMissingError`` (HTTP 422) for any missing basis, which
    keeps the error message in a single place and routes through the
    existing ``BaziEngineError`` handler.
    """

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "1987-07-04T21:30:00",
            "tz": "Europe/Berlin",
            "lat": 52.52,
            "lon": 13.405,
            "as_of_date": "2026-05-22",
            "direction_method": "explicit",
            "flow_direction": "forward",
            "cycles": 8,
        }
    })

    date: str = Field(..., description="Local ISO 8601 datetime of birth.")
    tz: str = Field(..., description="IANA timezone identifier, e.g. 'Europe/Berlin'.")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Birth latitude in decimal degrees.")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Birth longitude in decimal degrees.")
    as_of_date: Optional[str] = Field(
        None,
        description="ISO date used to select the 'current' decade. Defaults to today (UTC) if omitted.",
    )
    boundary: Literal["midnight", "zi_hour"] = Field(
        "midnight", description="Day-boundary convention used by the underlying BaZi engine."
    )
    standard: Literal["CIVIL", "LMT", "TLST"] = Field(
        "CIVIL", description="Time standard for interpreting the local datetime."
    )
    direction_method: Literal["explicit", "year_stem_yinyang_and_sex"] = Field(
        ..., description="How the flow direction of decades is determined."
    )
    flow_direction: Optional[Literal["forward", "backward"]] = Field(
        None, description="Required when direction_method='explicit'."
    )
    sex_at_birth: Optional[Literal["male", "female"]] = Field(
        None, description="Required when direction_method='year_stem_yinyang_and_sex'."
    )
    start_age_method: Literal["three_days_one_year"] = Field(
        "three_days_one_year",
        description="Currently only the classical 3-days = 1-year mapping is supported.",
    )
    cycles: int = Field(8, ge=1, le=12, description="Number of decade cycles to return.")
    strict: bool = Field(True, description="Reserved for future degradation modes.")

    @model_validator(mode="after")
    def _shape_passthrough(self) -> "DayunRequest":
        """Defer direction-basis validation to resolve_direction_for_request.

        That helper raises ``DirectionBasisMissingError`` with the structured
        ``detail.missing`` payload and the right error code, which the global
        ``BaziEngineError`` handler maps to a 422 envelope. Doing the same
        check here would either duplicate the error code or hide the
        missing-fields detail.
        """
        return self


# ── Response model ───────────────────────────────────────────────────────────


class DayunProvenance(BaseModel):
    source: Literal["FuFirE"] = "FuFirE"
    ruleset_id: Literal["dayun_v1"] = "dayun_v1"
    solar_terms_source: str
    computed_at: str


class DayunPrecision(BaseModel):
    birth_time_known: bool
    direction_basis: Optional[Literal["explicit", "year_stem_yinyang_and_sex"]] = None
    provisional_fields: List[str] = Field(default_factory=list)


class DayunResponse(BaseModel):
    """Top-level shape for POST /calculate/bazi/dayun.

    The nested ``dayun`` block is intentionally schemaless at the Pydantic
    level (``Dict[str, Any]``) — its true contract is enforced by
    ``schemas/calculate/bazi/dayun.response.schema.json`` via the
    ``test_response_validates_against_response_schema`` regression test.
    """
    model_config = ConfigDict(extra="forbid")

    dayun: Dict[str, Any]
    provenance: DayunProvenance
    precision: DayunPrecision
    warnings: List[str] = Field(default_factory=list)


# ── Boundary translation ─────────────────────────────────────────────────────

# Request schema uses "zi_hour"; the BaZi engine's BaziInput.day_boundary is
# Literal["midnight", "zi"]. Map between the two surface forms here.
def _engine_day_boundary(boundary: Literal["midnight", "zi_hour"]) -> DayBoundary:
    if boundary == "zi_hour":
        return "zi"
    return "midnight"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _month_index60(stem_index: int, branch_index: int) -> int:
    """Return the 60-cycle position of (stem_index, branch_index).

    Solves the CRT system ``i ≡ stem_index (mod 10)``,
    ``i ≡ branch_index (mod 12)``. The closed form is
    ``(6*stem - 5*branch) mod 60``.

    Verifications:
      * Jia Chen (stem=0, branch=4) → (0 - 20) % 60 = 40. jiazi_at(40)
        returns stem=Jia, branch=Chen — matches.
      * Bing Wu (stem=2, branch=6) → (12 - 30) % 60 = 42. jiazi_at(42)
        returns stem=Bing, branch=Wu — matches.
    """
    return (6 * stem_index - 5 * branch_index) % 60


def _utc_now_iso_z() -> str:
    """UTC timestamp as ``YYYY-MM-DDTHH:MM:SSZ`` (seconds precision, Z suffix)."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/bazi/dayun", response_model=DayunResponse)
@limiter.limit(tier_limit)
def calculate_dayun_endpoint(request: Request, req: DayunRequest) -> Dict[str, Any]:
    """Da-Yun (Decade Pillars) for a natal chart.

    Returns the resolved flow direction, start anchor (jieqi + delta + start
    age), decade cycles with Ten-Gods classification, and an optional
    'current' block for the decade that brackets ``as_of_date``.
    """
    try:
        # 1. Natal four pillars via the existing engine.
        engine_boundary = _engine_day_boundary(req.boundary)
        bazi_input = BaziInput(
            birth_local=req.date,
            timezone=req.tz,
            longitude_deg=req.lon,
            latitude_deg=req.lat,
            time_standard=req.standard,
            day_boundary=engine_boundary,
        )
        bazi_result = compute_bazi(bazi_input)

        # 2. Resolve direction. DirectionBasisMissingError → 422 via handler.
        request_dict = req.model_dump()
        direction = resolve_direction_for_request(
            request_dict, bazi_result.pillars.year
        )

        # 3. Jieqi anchor in the resolved direction (relative to birth_local).
        birth_local_dt = bazi_result.birth_local_dt
        anchor = resolve_jieqi_anchor(birth_local_dt, direction)

        # 4. Start age (3 days = 1 year). Capture cap warning if it fires.
        warnings_list: list[str] = []
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            start_age = compute_start_age(anchor["delta"])
        for w in caught:
            msg = str(w.message)
            if "start_age_capped_at_120_years" in msg:
                warnings_list.append("start_age_capped_at_120_years")

        # 5. Walk N cycles from the month pillar in the 60-cycle.
        month_pillar = bazi_result.pillars.month
        month_index60 = _month_index60(
            month_pillar.stem_index, month_pillar.branch_index
        )
        dir_sign = 1 if direction == "forward" else -1
        day_master_stem_index = bazi_result.pillars.day.stem_index

        cycles: list[Dict[str, Any]] = []
        for i in range(req.cycles):
            cycle_index60 = (month_index60 + (i + 1) * dir_sign) % 60
            pillar = jiazi_at(cycle_index60)
            age_start = start_age["decimal_years"] + i * 10
            age_end = age_start + 10
            # Decades track real Gregorian years (leap-aware) via add_real_years,
            # so date_end - date_start is ~3652-3653 days, not a 3600-day ritual year.
            date_start = add_real_years(birth_local_dt, age_start).isoformat()
            date_end = add_real_years(birth_local_dt, age_end).isoformat()
            relation = compute_relation_to_day_master(
                decade_stem_index=STEMS.index(pillar["stem"]),
                day_master_stem_index=day_master_stem_index,
            )
            cycles.append({
                "sequence": i + 1,
                "age_start": round(age_start, 2),
                "age_end": round(age_end, 2),
                "date_start": date_start,
                "date_end": date_end,
                "pillar": pillar,
                "relation_to_day_master": relation,
                "is_current": False,
            })

        # 6. Select the current cycle, if as_of_date falls within range.
        as_of_str = req.as_of_date or date.today().isoformat()
        current_cycle = select_current(
            cycles, birth=birth_local_dt, as_of=as_of_str
        )
        current_block: Optional[Dict[str, Any]]
        if current_cycle is not None:
            # Mutate the matching list entry to flag is_current=True.
            current_cycle["is_current"] = True
            current_block = {
                "sequence": current_cycle["sequence"],
                "age_start": current_cycle["age_start"],
                "age_end": current_cycle["age_end"],
                "pillar": current_cycle["pillar"],
                "semantic_summary": build_semantic_summary(
                    day_master_stem_index=day_master_stem_index,
                    decade_pillar=current_cycle["pillar"],
                    natal_branches={
                        "year":  bazi_result.pillars.year.branch_index,
                        "month": bazi_result.pillars.month.branch_index,
                        "day":   bazi_result.pillars.day.branch_index,
                        "hour":  bazi_result.pillars.hour.branch_index,
                    },
                    relation=current_cycle["relation_to_day_master"],
                ),
            }
        else:
            current_block = None

        # 7. Assemble response.
        return {
            "dayun": {
                "label": "Da Yun",
                "display_label_de": "Dekaden-Säule",
                "direction": direction,
                "direction_method": req.direction_method,
                "start": {
                    "anchor_term": {
                        "name": anchor["name"],
                        "direction": anchor["direction"],
                        "local_dt": anchor["local_dt"],
                    },
                    "delta": anchor["delta"],
                    "start_age": start_age,
                    "method": req.start_age_method,
                },
                "cycles": cycles,
                "current": current_block,
            },
            "provenance": {
                "source": "FuFirE",
                "ruleset_id": "dayun_v1",
                "solar_terms_source": "existing_bazi_jieqi_engine",
                "computed_at": _utc_now_iso_z(),
            },
            "precision": {
                # precision.birth_time_known is hardcoded True for V1 — the request schema has no
                # birth-time-uncertain flag yet. When a later sprint adds birth_time_known to
                # DayunRequest, thread it through here and clear `precision.provisional_fields`
                # from any time-dependent outputs the schema lists.
                "birth_time_known": True,
                "direction_basis": req.direction_method,
                "provisional_fields": [],
            },
            "warnings": warnings_list,
        }
    except BaziEngineError:
        # Direction-basis-missing, jieqi search failures, etc. — let the
        # global handler render the ErrorEnvelope shape with the right status.
        raise
    except Exception:
        _log.exception("Da-Yun calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")
