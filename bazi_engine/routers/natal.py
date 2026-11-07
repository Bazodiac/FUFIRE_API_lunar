"""routers/natal.py — POST /calculate/bazi/natal.

Natal per-pillar analysis endpoint. Exposes, for a SINGLE birth chart, the
facts the engine already computes internally (and until now only used inside
the ``/bazi-hehun`` pair matcher):

* per-pillar **hidden stems** (ruleset ``hidden_stems`` identities + the
  DECISION-003 Qi-role weights the ``/calculate/wuxing`` ledger uses),
* **Ten Gods relative to the day master** for every pillar stem AND every
  hidden stem (ruleset ``ten_gods`` table via ``match.ten_gods``; Pinyin /
  ``element_relation`` / ``label_de`` via the dayun relation module),
* the **month command** (Yue Ling) — deterministic ruleset facts only
  (``match.individual.MonthCommand``). NO seasonal-strength assessment
  (Wang/Xiang/Xiu/Qiu/Si) is emitted: that would need the domain-reviewed
  tables still pending as MISSING-003, and fabricating it is forbidden
  (AC-005c). The same ledger item keeps ``day_master_strength``/``yong_shen``
  and any rooting (通根) derivation out of this response — none exists in the
  engine, so none is invented here.

Everything is a REUSED internal computation — this module adds zero rule
logic of its own:

  1. ``compute_bazi()`` — natal four pillars (same input shaping as
     ``routers/bazi.py``: ``resolve_local_iso`` + fold + strict local time).
  2. ``match.normalize.normalize_chart()`` — day master + the per-stem
     Wu-Xing ledger (visible/hidden sources, Qi roles, weights) + stable
     warning codes.
  3. ``match.individual.analyze_individual()`` — the ``MonthCommand`` block.
  4. ``match.ten_gods.ten_god_for_stems()`` — ruleset Ten-God labels.
  5. ``dayun.relation.compute_relation_to_day_master()`` — Pinyin Ten-God
     names, element relation and German labels (the vocabulary
     ``/calculate/bazi/dayun`` already ships; its stem-index arguments are
     generic heavenly stems, not decade-specific).

Element vocabulary note: the response uses the English lowercase element
labels of the dayun endpoint (``wood``/``fire``/``earth``/``metal``/
``water``, via ``dayun.jiazi.STEM_ELEMENT``); the internal ledger's German
labels (``WUXING_ORDER``) name the same elements. ``branch_element`` is the
element of the branch's principal hidden stem — the identical derivation
``MonthCommand.element`` already uses for the month branch.

Returns a payload conforming to
``schemas/calculate/bazi/natal.response.schema.json`` (regression-locked by
``tests/test_natal_endpoint.py``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from ..bazi import compute_bazi
from ..bazi_rules import load_default_ruleset
from ..constants import BRANCHES, STEMS
from ..dayun.jiazi import BRANCHES_CN, STEM_ELEMENT, STEM_POLARITY, STEMS_CN
from ..dayun.relation import compute_relation_to_day_master
from ..exc import BaziEngineError
from ..limiter import limiter, tier_limit
from ..match.individual import IndividualAnalysis, analyze_individual
from ..match.normalize import normalize_chart
from ..match.ten_gods import ten_god_for_stems
from ..match.types import NormalizedChart, StemSource, WuxingLedgerEntry
from ..time_utils import AmbiguousTimeChoice, NonexistentTimePolicy, resolve_local_iso
from ..types import BaziInput, BaziResult, Fold

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/calculate", tags=["BaZi", "Natal"])

_PILLAR_NAMES: tuple[str, ...] = ("year", "month", "day", "hour")

# Ledger StemSource → response "qi" role, following the ruleset
# ``hidden_stems_weighting.role_weights`` vocabulary (principal/central/
# residual) — the same names ``match.types.StemSource`` is built on.
_QI_ROLE: Dict[StemSource, str] = {
    StemSource.HIDDEN_PRINCIPAL: "principal",
    StemSource.HIDDEN_CENTRAL: "central",
    StemSource.HIDDEN_RESIDUAL: "residual",
}

_STEM_INDEX: Dict[str, int] = {name: i for i, name in enumerate(STEMS)}


# ── Request model ────────────────────────────────────────────────────────────


class NatalRequest(BaseModel):
    """Request payload for POST /calculate/bazi/natal.

    Mirrors the ``BaziRequest`` essentials (``routers/bazi.py``) minus the
    trace toggle; ``date``/``tz``/``lat``/``lon`` are required (dayun-style —
    no silent location default on this new surface). Mirrors
    ``schemas/calculate/bazi/natal.request.schema.json``.
    """

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "1990-06-15T14:30:00",
            "tz": "Europe/Berlin",
            "lat": 52.52,
            "lon": 13.405,
            "standard": "CIVIL",
            "boundary": "midnight",
            "ambiguousTime": "earlier",
            "nonexistentTime": "error",
            "birth_time_known": True,
        }
    })

    date: str = Field(..., description="Local ISO 8601 datetime of birth.")
    tz: str = Field(..., description="IANA timezone identifier, e.g. 'Europe/Berlin'.")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Birth latitude in decimal degrees.")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Birth longitude in decimal degrees.")
    standard: Literal["CIVIL", "LMT", "TLST"] = Field(
        "CIVIL", description="Time standard for interpreting the local datetime."
    )
    boundary: Literal["midnight", "zi"] = Field(
        "midnight", description="Day-boundary convention for the day pillar."
    )
    ambiguousTime: AmbiguousTimeChoice = Field(
        "earlier", description="DST fall-back disambiguation (matches /calculate/bazi)."
    )
    nonexistentTime: NonexistentTimePolicy = Field(
        "error", description="DST spring-forward gap handling (matches /calculate/bazi)."
    )
    birth_time_known: bool = Field(
        True,
        description="False if birth time is uncertain — flags the hour pillar as provisional.",
    )


# ── Response model ───────────────────────────────────────────────────────────


class NatalProvenance(BaseModel):
    source: Literal["FuFirE"] = "FuFirE"
    ruleset_id: str
    ruleset_version: str
    computed_at: str


class NatalPrecision(BaseModel):
    birth_time_known: bool
    provisional_fields: List[str] = Field(default_factory=list)


class NatalResponse(BaseModel):
    """Top-level shape for POST /calculate/bazi/natal.

    The nested ``pillars`` / ``day_master`` / ``month_command`` blocks are
    intentionally schemaless at the Pydantic level (``Dict[str, Any]``) —
    like the dayun endpoint, their true contract is enforced by
    ``schemas/calculate/bazi/natal.response.schema.json`` via the
    ``test_response_validates_against_response_schema`` regression test.
    """

    model_config = ConfigDict(extra="forbid")

    pillars: Dict[str, Any]
    day_master: Dict[str, Any]
    month_command: Dict[str, Any]
    provenance: NatalProvenance
    precision: NatalPrecision
    warnings: List[str] = Field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────────────────────


def _utc_now_iso_z() -> str:
    """UTC timestamp as ``YYYY-MM-DDTHH:MM:SSZ`` (seconds precision, Z suffix)."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _ten_god_block(
    ruleset: Dict[str, Any], day_master: str, target_stem: str
) -> Dict[str, Any]:
    """Ten-God facts for ``target_stem`` relative to the day master.

    ``name`` comes from the ruleset table (``ten_god_for_stems``); the
    Pinyin name, element relation and German label come verbatim from the
    dayun relation module — both encode the same closed rule
    (element relation × polarity match).
    """
    relation = compute_relation_to_day_master(
        decade_stem_index=_STEM_INDEX[target_stem],
        day_master_stem_index=_STEM_INDEX[day_master],
    )
    return {
        "name": ten_god_for_stems(ruleset, day_master, target_stem),
        "pinyin": relation["ten_god"],
        "element_relation": relation["element_relation"],
        "label_de": relation["label_de"],
    }


def _hidden_stem_entries(
    ledger: tuple[WuxingLedgerEntry, ...],
    pillar_name: str,
    ruleset: Dict[str, Any],
    day_master: str,
) -> List[Dict[str, Any]]:
    """This pillar's hidden stems from the normalized Wu-Xing ledger.

    Order and weights are the ledger's (DECISION-003: the same source
    ``/calculate/wuxing`` computes from); every hidden stem carries its own
    Ten God relative to the day master.
    """
    entries: List[Dict[str, Any]] = []
    for e in ledger:
        if e.pillar != pillar_name or not e.source.is_hidden:
            continue
        entries.append({
            "stem": e.stem,
            "stem_cn": STEMS_CN[_STEM_INDEX[e.stem]],
            "element": STEM_ELEMENT[e.stem],
            "qi": _QI_ROLE[e.source],
            "weight": e.weight,
            "ten_god": _ten_god_block(ruleset, day_master, e.stem),
        })
    return entries


def _pillar_block(
    chart: NormalizedChart,
    pillar_name: str,
    ruleset: Dict[str, Any],
) -> Dict[str, Any]:
    """One pillar's response block; the day pillar's ``ten_god`` is null
    (the day stem IS the day master — no relation to itself is emitted)."""
    pillar = getattr(chart.pillars, pillar_name)
    stem = STEMS[pillar.stem_index]
    branch = BRANCHES[pillar.branch_index]
    hidden = _hidden_stem_entries(
        chart.wuxing_ledger, pillar_name, ruleset, chart.day_master
    )
    # Branch element = element of the branch's principal hidden stem — the
    # identical derivation MonthCommand.element uses for the month branch.
    principal = next(e for e in hidden if e["qi"] == "principal")
    return {
        "stem": stem,
        "branch": branch,
        "stem_cn": STEMS_CN[pillar.stem_index],
        "branch_cn": BRANCHES_CN[pillar.branch_index],
        "stem_element": STEM_ELEMENT[stem],
        "branch_element": principal["element"],
        "polarity": STEM_POLARITY[stem],
        "ten_god": (
            None
            if pillar_name == "day"
            else _ten_god_block(ruleset, chart.day_master, stem)
        ),
        "hidden_stems": hidden,
    }


def _day_master_block(day_master: str) -> Dict[str, Any]:
    return {
        "stem": day_master,
        "stem_cn": STEMS_CN[_STEM_INDEX[day_master]],
        "element": STEM_ELEMENT[day_master],
        "polarity": STEM_POLARITY[day_master],
    }


def _month_command_block(analysis: IndividualAnalysis) -> Dict[str, Any]:
    """Month-command facts from ``match.individual.MonthCommand`` verbatim.

    ``element`` is emitted in this endpoint's English vocabulary via the
    principal Qi stem (``MonthCommand.element`` holds the same element under
    its German ``WUXING_ORDER`` label). Deliberately NO seasonal-strength
    field: none exists in the engine (MISSING-003, see module docstring).
    """
    mc = analysis.month_command
    return {
        "branch": mc.branch,
        "branch_cn": BRANCHES_CN[mc.branch_index],
        "branch_index": mc.branch_index,
        "principal_qi_stem": mc.principal_qi_stem,
        "principal_qi_stem_cn": STEMS_CN[_STEM_INDEX[mc.principal_qi_stem]],
        "element": STEM_ELEMENT[mc.principal_qi_stem],
        "source_status": mc.source_status.value,
    }


def _assemble_response(
    req: NatalRequest,
    chart: NormalizedChart,
    analysis: IndividualAnalysis,
    ruleset: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "pillars": {
            name: _pillar_block(chart, name, ruleset) for name in _PILLAR_NAMES
        },
        "day_master": _day_master_block(chart.day_master),
        "month_command": _month_command_block(analysis),
        "provenance": {
            "source": "FuFirE",
            "ruleset_id": str(ruleset.get("ruleset_id", "MISSING")),
            "ruleset_version": str(ruleset.get("ruleset_version", "MISSING")),
            "computed_at": _utc_now_iso_z(),
        },
        "precision": {
            "birth_time_known": req.birth_time_known,
            "provisional_fields": [] if req.birth_time_known else ["hour"],
        },
        # Stable warning codes from the normalized chart (AC-004c), surfaced
        # dayun-style as a flat string array.
        "warnings": [w.code.value for w in chart.warnings],
    }


def _compute_natal_chart(req: NatalRequest) -> BaziResult:
    """Natal four pillars — same input shaping as ``routers/bazi.py``."""
    dt_local, _ = resolve_local_iso(
        req.date, req.tz,
        ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
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
    return compute_bazi(inp)


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/bazi/natal", response_model=NatalResponse)
@limiter.limit(tier_limit)
def calculate_natal_endpoint(request: Request, req: NatalRequest) -> Dict[str, Any]:
    """Natal per-pillar analysis: hidden stems, Ten Gods vs. the day master
    (pillar stems and hidden stems), and the month command — purely additive
    exposure of facts the engine already computes for the pair matcher."""
    try:
        result = _compute_natal_chart(req)
        ruleset = load_default_ruleset()
        chart = normalize_chart(
            result,
            birth_time_known=req.birth_time_known,
            subject="natal",
            ruleset=ruleset,
        )
        analysis = analyze_individual(chart, subject="natal", ruleset=ruleset)
        return _assemble_response(req, chart, analysis, ruleset)
    except BaziEngineError:
        # DST/time-resolution errors etc. — the global handler renders the
        # ErrorEnvelope shape with the right status.
        raise
    except Exception:
        _log.exception("Natal analysis calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")
