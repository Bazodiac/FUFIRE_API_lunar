"""
routers/shared.py — Constants and helpers shared across routers.

Extracted from app.py to avoid duplication. Imported by individual routers.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..constants import BRANCHES, STEMS
from ..types import Pillar

if TYPE_CHECKING:
    from ..birth_time import BirthTimeInput

ZODIAC_SIGNS_DE = [
    "Widder", "Stier", "Zwillinge", "Krebs", "Löwe", "Jungfrau",
    "Waage", "Skorpion", "Schütze", "Steinbock", "Wassermann", "Fische",
]

STEM_TO_ELEMENT: Dict[str, str] = {
    "Jia": "Holz", "Yi": "Holz",
    "Bing": "Feuer", "Ding": "Feuer",
    "Wu": "Erde", "Ji": "Erde",
    "Geng": "Metall", "Xin": "Metall",
    "Ren": "Wasser", "Gui": "Wasser",
}

BRANCH_TO_ANIMAL: Dict[str, str] = {
    "Zi": "Ratte", "Chou": "Ochse", "Yin": "Tiger", "Mao": "Hase",
    "Chen": "Drache", "Si": "Schlange", "Wu": "Pferd", "Wei": "Ziege",
    "Shen": "Affe", "You": "Hahn", "Xu": "Hund", "Hai": "Schwein",
}


def format_pillar(pillar: Pillar) -> Dict[str, str]:
    stem = STEMS[pillar.stem_index]
    branch = BRANCHES[pillar.branch_index]
    return {
        "stamm": stem,
        "zweig": branch,
        "tier": BRANCH_TO_ANIMAL[branch],
        "element": STEM_TO_ELEMENT[stem],
    }


class ErrorEnvelope(BaseModel):
    """Standard error response envelope for all /v1/* and legacy endpoints.

    Canonical JSON Schema: spec/schemas/ErrorEnvelope.schema.json
    See FBP-03-006 for the planned RFC 9457 migration in /v2.
    """
    model_config = ConfigDict(extra="forbid")

    error: str
    message: str
    detail: Dict[str, Any] = {}
    status: int
    path: str
    timestamp: str
    request_id: str


class ProvenanceResponse(BaseModel):
    engine_version: str
    parameter_set_id: str
    ruleset_id: str
    ephemeris_id: str
    tzdb_version_id: str
    house_system: str
    zodiac_mode: str
    computation_timestamp: str
    parameter_set: Optional[Dict[str, Any]] = None


def _is_none(value: Any) -> bool:
    return value is None


REFERENCE_TIME_POLICY_DESCRIPTION = (
    "Present only when the request `date` had no time part: `date_only_noon` = "
    "the chart was computed at 12:00 civil local time of that date "
    "(docs/precision/date-only-birth-input.md). Absent when a time was supplied."
)


def absent_if_none(description: str) -> Any:
    """Optional response field that is left out (not ``null``) when unset.

    Used for fields added after a response shape was frozen: responses that do
    not need them stay byte-identical to the earlier ones.
    """
    return Field(None, exclude_if=_is_none, description=description)


class PrecisionBlock(BaseModel):
    birth_time_known: bool
    provisional_fields: list[str] = Field(default_factory=list)
    reference_time_policy: Optional[Literal["date_only_noon"]] = absent_if_none(
        REFERENCE_TIME_POLICY_DESCRIPTION
    )


WARNINGS_DESCRIPTION = (
    "Stable warning codes. Present only when there is one: `BIRTH_TIME_UNKNOWN` "
    "when the birth time is unknown (`birth_time_known=false`, or a `date` without "
    "a time part)."
)

ChartTypeQuality = Literal["exact", "assumed_day", "time_excluded"]


class QualityFlags(BaseModel):
    """Observable quality signals for downstream B2B consumers.

    Surfaces facts the engine previously kept implicit:
    - whether the requested house system was actually used,
    - which Swiss Ephemeris backend served the request (high-precision SE1
      vs. analytical Moshier).

    `chart_type_quality` is reserved for Task 8 (birth_time_known wiring) and
    remains optional so this model can be reused across endpoints incrementally.
    """

    house_system_fallback: bool
    house_system_requested: str
    house_system_used: str
    ephemeris_mode: Literal["SWIEPH", "MOSEPH"]
    chart_type_quality: Optional[ChartTypeQuality] = Field(
        None,
        description=(
            "exact: the ascendant (from the given time) is counted; assumed_day: no "
            "ascendant available; time_excluded: the time-dependent contributions "
            "(ascendant, hour pillar) were left out on request "
            "(`exclude_time_dependent`)."
        ),
    )

    model_config = ConfigDict(extra="forbid")


class MinimalQualityFlags(BaseModel):
    """Slimmer quality-flags model for non-house-computing endpoints.

    FQ-ATT-02 (T9), OQ-1 (CONFIRMED, user, 2026-07-01): ``/calculate/bazi``
    and ``/calculate/wuxing`` compute no house cusps at all, so
    ``house_system_fallback`` (and its `_requested`/`_used` siblings) must
    be ABSENT from their responses -- not merely ``null``. (``/calculate/tst``
    was originally in this group too but, refined 2026-07-01, omits
    ``quality_flags`` entirely instead -- see ``current_ephemeris_mode()``'s
    docstring below.)
    Reusing ``QualityFlags`` as-is (its house fields are required, non-
    ``Optional``) would either force fake house values onto these
    endpoints or require loosening ``QualityFlags`` to ``Optional``, which
    would blur the absent-vs-null distinction OQ-1's decision depends on.
    This model intentionally does not declare the house fields at all.
    """

    ephemeris_mode: Literal["SWIEPH", "MOSEPH"]
    chart_type_quality: Optional[Literal["exact", "assumed_day"]] = None

    model_config = ConfigDict(extra="forbid")


def current_ephemeris_mode(ephe_path: Optional[str] = None) -> Literal["SWIEPH", "MOSEPH"]:
    """Read the attested Swiss Ephemeris mode for endpoints that don't
    already expose a backend instance from their own compute pipeline.

    FQ-ATT-02 (T9): ``bazi``/``transit`` construct their own
    ``SwissEphBackend`` deep inside their compute pipeline
    (``compute_bazi()``, ``compute_transit_now()``, ...) without exposing
    it to the router, so this constructs a second, throwaway backend purely
    to read its attested ``.mode`` -- never a hardcoded/stubbed literal
    (VCHK-02). This can never diverge from (or precede) the guarantee the
    primary computation for the same request already enforced: every
    calculation endpoint's own compute pipeline already constructs a
    ``SwissEphBackend`` first and would have raised
    ``EphemerisUnavailableError`` before this is ever reached if the same
    environment could not attest SWIEPH.

    Not used by ``/calculate/tst`` (refined 2026-07-01, user decision):
    ``time_context.py`` touches no Swiss Ephemeris call at all, so there is
    no already-enforced guarantee to piggyback on there -- calling this
    would introduce a brand-new failure mode, not a redundant re-check, and
    ``tst`` intentionally omits ``quality_flags``/``ephemeris_mode``
    entirely rather than attest something with zero causal bearing on its
    response. ``wuxing`` reuses ``compute_western_chart()``'s own already-
    attested mode directly instead of calling this function.
    """
    from ..ephemeris import SwissEphBackend

    return SwissEphBackend(ephe_path=ephe_path).mode  # type: ignore[return-value]


def precision_block(
    birth_time: "BirthTimeInput", unknown_time_fields: list[str],
) -> Dict[str, Any]:
    """Precision block for a birth-input endpoint.

    ``unknown_time_fields`` is used only when the birth time is unknown: the
    endpoint's fixed time-dependent fields followed by the ones measured over the
    civil day (pillar boundaries, sign changes).
    """
    if birth_time.birth_time_known:
        return {"birth_time_known": True, "provisional_fields": []}
    block: Dict[str, Any] = {
        "birth_time_known": False,
        "provisional_fields": list(dict.fromkeys(unknown_time_fields)),
    }
    if birth_time.reference_time_policy is not None:
        block["reference_time_policy"] = birth_time.reference_time_policy
    return block
