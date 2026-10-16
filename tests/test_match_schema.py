"""test_match_schema.py — T8 direct model validation (no HTTP).

Binding contract anchors (docs/testing/bazi-hehun.acceptance-tests.md,
docs/plans/2026-07-02-bazi-hehun.md §5 T8, docs/context/bazi-hehun.
response-schema-decision.md DECISION-002):

- AC-002a: ``birth_input`` requires ``person_a`` and ``person_b`` with the
  core birth fields (``date`` is required on the reused ``BaziRequest``).
- AC-002b: ``mode=raw_bazi`` and raw chart payloads are rejected; the
  request forbids unknown top-level keys (``extra="forbid"``).
- AC-002c: an invalid ``mode`` or a malformed payload is a validation
  error (never silently computed).
- AC-012b: ``options.persist_raw`` defaults to ``False``.
- AC-012d: the consent field description is neutral copy — it must not
  imply legal review or platform certification (T-012-06 schema side).
- AC-007a/b/c (schema side): no score field name exists anywhere in the
  request OR response schema graph (the five forbidden keys of contract
  §0.4).

These are the *schema-side* (direct Pydantic) halves of the acceptance
contract; the assembled-app (integration-fake) halves land with the T9
endpoint. T8 is MODELS ONLY — no endpoint, no mount.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Iterator, List

import pytest
from pydantic import ValidationError

from bazi_engine.provenance import build_provenance
from bazi_engine.routers.match import (
    MatchOptions,
    MatchQualityFlags,
    MatchRequest,
    MatchResponse,
)
from tests.fixtures.match_payloads import SENTINEL_A, VALID_MATCH_REQUEST

# Contract §0.4 — the five forbidden score keys (exact key match, recursive).
FORBIDDEN_SCORE_KEYS = frozenset(
    {
        "total_score",
        "sub_scores",
        "score_class",
        "awarded_points",
        "score_confidence",
    }
)

# D3 (matrix layers deferred) — no such property name may exist in the
# response schema (case-insensitive substring); mirrors T-006-02.
FORBIDDEN_MATRIX_SUBSTRINGS = ("branch_matrix", "stem_matrix", "ten_gods", "shensha", "shen_sha")

# D4 (no LLM/Fusion interpretation-readiness claim) — no such flag exists.
FORBIDDEN_D4_FIELDS = (
    "allowed_for_llm_interpretation",
    "ready_for_downstream_interpretation",
)


# ── schema-graph helpers ─────────────────────────────────────────────────────
def _iter_property_names(schema: Dict[str, Any]) -> Iterator[str]:
    """Yield every ``properties`` key reachable in a model JSON schema.

    Walks the model's ``$defs`` and nested ``properties`` recursively so the
    scan covers the transitive schema graph, not just the top level.
    """
    stack: List[Any] = [schema]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                yield from props.keys()
            for value in node.values():
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)


def _iter_all_keys(node: Any) -> Iterator[str]:
    """Yield every dict key at every depth of a plain (dumped) response."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _iter_all_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_all_keys(item)


# ── response payload builder (authoritative T8 example shape) ─────────────────
def _pillars() -> Dict[str, Dict[str, str]]:
    one = {"stamm": "Jia", "zweig": "Zi", "tier": "Ratte", "element": "Holz"}
    return {"year": one, "month": one, "day": one, "hour": one}


def _individual(subject: str) -> Dict[str, Any]:
    return {
        "subject": subject,
        "four_pillars": _pillars(),
        "day_master": "Jia",
        "day_master_element": "Holz",
        "month_command": {
            "branch": "Wu",
            "branch_index": 6,
            "principal_qi_stem": "Ding",
            "element": "Feuer",
            "source_status": "CALCULATED",
        },
        "spouse_palace": {
            "palace_pillar": "day",
            "day_branch": "Zi",
            "day_branch_index": 0,
            "hidden_stems": ["Gui"],
            "position_source_status": "CALCULATED",
            "position_source_note": (
                "day branch = spouse palace (日支=夫妻宫), "
                "standard BaZi position identification"
            ),
            "source_status": "NEEDS_DOMAIN_REVIEW",
        },
        "wuxing_vector": [1.0, 2.0, 3.0, 4.0, 5.0],
        "wuxing_ledger": [
            {
                "pillar": "day",
                "stem": "Jia",
                "element": "Holz",
                "source": "visible",
                "weight": 1.0,
            },
            {
                "pillar": "day",
                "stem": "Gui",
                "element": "Wasser",
                "source": "hidden_principal",
                "weight": 1.0,
            },
        ],
        "derived_fields": [
            {
                "field": "day_master_strength",
                "source_status": "NEEDS_DOMAIN_REVIEW",
                "confidence": 0.0,
                "blocked_by": "MISSING-003",
            },
            {
                "field": "yong_shen",
                "source_status": "PENDING_TABLES",
                "confidence": 0.0,
                "blocked_by": "MISSING-003",
            },
        ],
        "spouse_star": {
            "gender_used": None,
            "source_status": "PENDING_TABLES",
            "confidence": 0.0,
            "blocked_by": "GENDER_NOT_PROVIDED",
            "occurrences": [],
        },
        "source_status": "CALCULATED",
        "warnings": [
            {
                "code": "DAY_ANCHOR_UNVERIFIED",
                "subject": "ruleset",
                "message": "Day-cycle anchor is not verified.",
                "evidence_ids": ["ev:warning:ruleset:DAY_ANCHOR_UNVERIFIED"],
            }
        ],
    }


def _subject(subject_id: str, role: str, label: str) -> Dict[str, Any]:
    return {
        "subject_id": subject_id,
        "role": role,
        "display_label": label,
        "identity_policy": "Pseudonymous; no real name is required or stored.",
        "birth_context": {
            "birth_time_known": True,
            "time_precision": "minute",
            "location_precision": "coordinate",
            "status": "REDACTED",
            "redacted_input_ref": {
                "input_hash": "sha256:" + "a" * 64,
                "canonical_birth_context_hash": "sha256:" + "b" * 64,
            },
        },
    }


def _pair_layer(name: str) -> Dict[str, Any]:
    return {
        "name": name,
        "facts": [
            {
                "key": "person_a_day_master",
                "value": "Jia",
                "source_status": "CALCULATED",
            }
        ],
        "source_status": "CALCULATED",
        "evidence_ids": ["ev:pair:" + name],
    }


def _valid_response_payload() -> Dict[str, Any]:
    """A full, valid ``MatchResponse`` body — the T8 authoritative example."""
    return {
        "meta": {
            "schema_name": "BaziHehunRawResponse",
            "schema_version": "hehun-mvp-1",
            "endpoint": "/v1/match/bazi-hehun",
            "response_kind": "raw_analysis_data",
            "generated_at_utc": "2026-07-03T00:00:00+00:00",
            "request_id": "req-abc-123",
            "correlation_id": None,
            "ruleset_id": "standard_bazi_2026",
            "ruleset_version": "1.0.0",
            "engine_version": "1.0.0-rc2-20261016",
        },
        "request_context": {
            "mode": "birth_input",
            "input_mode_status": "ACCEPTED",
        },
        "subjects": {
            "person_a": _subject("subject_a", "person_a", "Person A"),
            "person_b": _subject("subject_b", "person_b", "Person B"),
        },
        "individual": {
            "person_a": _individual("person_a"),
            "person_b": _individual("person_b"),
        },
        "pair": {
            "day_master_comparison": _pair_layer("day_master_comparison"),
            "spouse_palace_day_branch": _pair_layer("spouse_palace_day_branch"),
            "wuxing_vector_comparison": _pair_layer("wuxing_vector_comparison"),
        },
        "raw_analysis_text": [
            {
                "id": "blk:day_master_comparison:01",
                "layer": "day_master_comparison",
                "statement_type": "CALCULATED_FACT",
                "subject": "pair",
                "text": "Day master of person_a is Jia (Holz).",
                "source_status": "CALCULATED",
                "evidence_ids": ["ev:pair:day_master_comparison"],
            }
        ],
        "warnings": [
            {
                "code": "DAY_ANCHOR_UNVERIFIED",
                "subject": "ruleset",
                "message": "Day-cycle anchor is not verified.",
                "evidence_ids": ["ev:warning:ruleset:DAY_ANCHOR_UNVERIFIED"],
            }
        ],
        "evidence_ledger": [
            {
                "id": "ev:pair:day_master_comparison",
                "kind": "COMPUTATION",
                "source_ref": "bazi_engine.match.pair.analyze_pair",
                "description": "Day-master stems, elements and relation.",
            }
        ],
        "relationship_context": {
            "consent_status": {
                "acknowledgement": True,
                "consent_text_version": "v1",
                "final_legal_text_status": "PENDING",
                "go_live_blocker": True,
            }
        },
        "provenance": build_provenance(),
        "quality_flags": {"ephemeris_mode": "MOSEPH"},
        "precision": {
            "person_a": {"birth_time_known": True, "provisional_fields": []},
            "person_b": {"birth_time_known": True, "provisional_fields": []},
        },
        "safety_and_language_policy": {
            "allowed_output": ["calculated_fact", "rule_application"],
            "blocked_output": ["marriage promise", "compatibility rating"],
            "requires_human_review_before_go_live": True,
        },
        "missing_and_blockers": [
            {
                "id": "MISSING-001",
                "title": "Domain-approved interaction tables",
                "status": "OPEN",
            }
        ],
    }


# ── MatchRequest — birth_input / consent / extra=forbid (AC-002*, AC-012*) ────
def test_valid_request_constructs() -> None:
    req = MatchRequest.model_validate(VALID_MATCH_REQUEST)
    assert req.mode == "birth_input"
    assert req.options.second_person_consent_confirmed is True


def test_missing_person_a_or_b_is_rejected() -> None:
    for missing in ("person_a", "person_b"):
        payload = copy.deepcopy(VALID_MATCH_REQUEST)
        del payload[missing]
        with pytest.raises(ValidationError):
            MatchRequest.model_validate(payload)


def test_person_missing_core_date_field_is_rejected() -> None:
    # ``date`` is required on the reused BaziRequest (AC-002a).
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["person_a"] = {k: v for k, v in SENTINEL_A.items() if k != "date"}
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


def test_raw_chart_shaped_person_is_rejected() -> None:
    # A chart-shaped payload has no birth ``date`` ⇒ rejected (AC-002b).
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["person_a"] = {"pillars": {"day": "Jia-Zi"}, "day_master": "Jia"}
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


# ── GF-1 (docs/plans/2026-07-04-bazi-hehun-gender-field.md) — optional gender ─
@pytest.mark.parametrize("gender", ["male", "female", "divers"])
def test_person_gender_accepts_all_three_values(gender: str) -> None:
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["person_a"] = {**SENTINEL_A, "gender": gender}
    req = MatchRequest.model_validate(payload)
    assert req.person_a.gender == gender


def test_person_gender_rejects_invalid_value() -> None:
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["person_a"] = {**SENTINEL_A, "gender": "other"}
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


def test_person_gender_omission_is_backward_compatible() -> None:
    # No "gender" key at all -- exactly what every existing caller sends today.
    req = MatchRequest.model_validate(VALID_MATCH_REQUEST)
    assert req.person_a.gender is None
    assert req.person_b.gender is None


def test_bazi_request_itself_carries_no_gender_field() -> None:
    """Regression lock (GF-1): gender lives on the match-local
    ``MatchPersonInput`` wrapper ONLY. If someone later merges it into the
    SHARED ``BaziRequest`` (reused by /calculate/bazi and /personalize),
    this must fail loudly rather than silently leak the field into those
    unrelated, already-live endpoints."""
    from bazi_engine.routers.bazi import BaziRequest

    assert "gender" not in BaziRequest.model_json_schema()["properties"]


def test_mode_raw_bazi_is_rejected() -> None:
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["mode"] = "raw_bazi"
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


def test_invalid_mode_value_is_rejected() -> None:
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["mode"] = "banana"
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


def test_mode_enum_contains_only_birth_input() -> None:
    schema = MatchRequest.model_json_schema()
    mode_schema = schema["properties"]["mode"]
    # Literal["birth_input"] renders as const or a single-value enum.
    values = mode_schema.get("enum") or (
        [mode_schema["const"]] if "const" in mode_schema else []
    )
    assert values == ["birth_input"]


def test_unknown_top_level_key_is_rejected() -> None:
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["canonical_chart"] = {"pillars": {}}
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


def test_options_required() -> None:
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    del payload["options"]
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


def test_consent_field_required_in_options() -> None:
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["options"] = {}
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


def test_unknown_option_is_rejected() -> None:
    # Deferred scoring/matrix options ⇒ 422 (AC-009b schema side).
    payload = copy.deepcopy(VALID_MATCH_REQUEST)
    payload["options"] = {
        "second_person_consent_confirmed": True,
        "include_scores": True,
    }
    with pytest.raises(ValidationError):
        MatchRequest.model_validate(payload)


def test_persist_raw_defaults_false() -> None:
    req = MatchRequest.model_validate(VALID_MATCH_REQUEST)
    assert req.options.persist_raw is False
    schema = MatchOptions.model_json_schema()
    assert schema["properties"]["persist_raw"]["default"] is False


def test_consent_ancestors_all_required_in_schema() -> None:
    # Contract §3 WATCH item: every ancestor on the consent path is required.
    req_schema = MatchRequest.model_json_schema()
    assert "options" in req_schema["required"]
    opt_schema = MatchOptions.model_json_schema()
    assert "second_person_consent_confirmed" in opt_schema["required"]


def test_consent_copy_implies_no_legal_review() -> None:
    schema = MatchOptions.model_json_schema()
    description = schema["properties"]["second_person_consent_confirmed"][
        "description"
    ].lower()
    for forbidden in ("legally reviewed", "gdpr-compliant", "certified"):
        assert forbidden not in description


# ── MatchQualityFlags (AC-004 parity, plan §4.3) ─────────────────────────────
def test_quality_flags_ephemeris_mode_literal() -> None:
    assert MatchQualityFlags(ephemeris_mode="SWIEPH").ephemeris_mode == "SWIEPH"
    assert MatchQualityFlags(ephemeris_mode="MOSEPH").ephemeris_mode == "MOSEPH"
    with pytest.raises(ValidationError):
        MatchQualityFlags(ephemeris_mode="GUESS")


def test_quality_flags_has_no_western_house_fields() -> None:
    # BaZi-only endpoint: no dishonest western house_system noise (plan §4.3).
    props = MatchQualityFlags.model_json_schema()["properties"]
    assert "ephemeris_mode" in props
    for western in ("house_system_used", "house_system_requested", "house_system_fallback"):
        assert western not in props


# ── Score-absence + D3/D4 at the schema level (AC-007a/b/c, D3, D4) ───────────
def test_no_score_field_in_request_or_response_schema() -> None:
    for model in (MatchRequest, MatchResponse):
        names = set(_iter_property_names(model.model_json_schema()))
        leaked = names & FORBIDDEN_SCORE_KEYS
        assert not leaked, f"{model.__name__} leaks score fields: {leaked}"


def test_no_matrix_property_names_in_response_schema() -> None:
    names = [n.lower() for n in _iter_property_names(MatchResponse.model_json_schema())]
    for name in names:
        for forbidden in FORBIDDEN_MATRIX_SUBSTRINGS:
            assert forbidden not in name, f"matrix leakage: {name!r}"


def test_no_llm_readiness_flag_in_response_schema() -> None:
    names = set(_iter_property_names(MatchResponse.model_json_schema()))
    for forbidden in FORBIDDEN_D4_FIELDS:
        assert forbidden not in names


# ── MatchResponse structural contract (DECISION-002 adopted blocks) ──────────
def test_response_constructs_and_has_all_adopted_blocks() -> None:
    resp = MatchResponse.model_validate(_valid_response_payload())
    dumped = resp.model_dump(mode="json")
    for block in (
        "meta",
        "request_context",
        "subjects",
        "individual",
        "pair",
        "raw_analysis_text",
        "warnings",
        "evidence_ledger",
        "relationship_context",
        "provenance",
        "quality_flags",
        "precision",
        "safety_and_language_policy",
        "missing_and_blockers",
    ):
        assert block in dumped, f"missing adopted block: {block}"


def test_response_pair_has_exactly_three_layers() -> None:
    resp = MatchResponse.model_validate(_valid_response_payload())
    dumped = resp.model_dump(mode="json")
    assert set(dumped["pair"]) == {
        "day_master_comparison",
        "spouse_palace_day_branch",
        "wuxing_vector_comparison",
    }


def test_response_subjects_carry_redacted_hashes() -> None:
    resp = MatchResponse.model_validate(_valid_response_payload())
    ref = resp.model_dump(mode="json")["subjects"]["person_a"]["birth_context"][
        "redacted_input_ref"
    ]
    assert "input_hash" in ref and "canonical_birth_context_hash" in ref


def test_response_individual_carries_deferral_statuses() -> None:
    resp = MatchResponse.model_validate(_valid_response_payload())
    person_a = resp.model_dump(mode="json")["individual"]["person_a"]
    derived = person_a["derived_fields"]
    fields = {d["field"] for d in derived}
    assert {"day_master_strength", "yong_shen"} <= fields
    for entry in derived:
        assert entry["source_status"] in ("PENDING_TABLES", "NEEDS_DOMAIN_REVIEW")
        assert "confidence" in entry

    # spouse_star (GF-3) lives in its own field now, not derived_fields.
    spouse_star = person_a["spouse_star"]
    assert spouse_star["source_status"] in ("PENDING_TABLES", "CALCULATED")
    assert "confidence" in spouse_star
    assert "occurrences" in spouse_star


def test_dumped_response_has_no_score_keys_recursively() -> None:
    resp = MatchResponse.model_validate(_valid_response_payload())
    keys = set(_iter_all_keys(resp.model_dump(mode="json")))
    assert not (keys & FORBIDDEN_SCORE_KEYS)
