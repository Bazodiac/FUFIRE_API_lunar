"""TDD contract for factual hidden-stem affinities, NOT a Tong-Gen verdict.

These tests intentionally avoid HTTP imports: the host lacks the rate-limit
runtime dependency. Their pass result must not be labelled endpoint coverage.
"""
from __future__ import annotations

import pytest

from bazi_engine.match.natal_facts import hidden_stem_affinities
from bazi_engine.match.types import StemSource, WuxingLedgerEntry


def _entry(pillar: str, stem: str, element: str, source: StemSource) -> WuxingLedgerEntry:
    return WuxingLedgerEntry(pillar=pillar, stem=stem, element=element, source=source, weight=1.0)


def test_hidden_stem_affinities_separate_exact_from_phase_peers():
    entries = (
        _entry("year", "Jia", "Holz", StemSource.VISIBLE),  # visible is not a root fact
        _entry("year", "Jia", "Holz", StemSource.HIDDEN_PRINCIPAL),
        _entry("month", "Yi", "Holz", StemSource.HIDDEN_CENTRAL),
        _entry("day", "Geng", "Metall", StemSource.HIDDEN_PRINCIPAL),
        _entry("hour", "Jia", "Holz", StemSource.HIDDEN_RESIDUAL),
    )

    actual = hidden_stem_affinities("Jia", entries, birth_time_known=False)
    assert actual == {
        "source_status": "CALCULATED",
        "exact_day_master_stem": [
            {"pillar": "year", "stem": "Jia", "qi": "principal", "provisional": False},
            {"pillar": "hour", "stem": "Jia", "qi": "residual", "provisional": True},
        ],
        "same_phase_other_stem": [
            {"pillar": "month", "stem": "Yi", "qi": "central", "provisional": False},
        ],
        "tong_gen_assessment": {"source_status": "NEEDS_DOMAIN_REVIEW", "blocked_by": "MISSING-003"},
    }


def test_no_hidden_affinities_is_empty_not_negative_strength():
    entries = (_entry("year", "Geng", "Metall", StemSource.HIDDEN_PRINCIPAL),)
    actual = hidden_stem_affinities("Jia", entries, birth_time_known=True)
    assert actual["exact_day_master_stem"] == []
    assert actual["same_phase_other_stem"] == []
    assert actual["tong_gen_assessment"]["source_status"] == "NEEDS_DOMAIN_REVIEW"


def test_birth_time_known_keeps_hour_stem_non_provisional():
    entries = (_entry("hour", "Yi", "Holz", StemSource.HIDDEN_CENTRAL),)
    actual = hidden_stem_affinities("Jia", entries, birth_time_known=True)
    assert actual["same_phase_other_stem"][0]["provisional"] is False


def test_unknown_day_master_fails_instead_of_guessing():
    with pytest.raises(KeyError):
        hidden_stem_affinities("UNKNOWN", (), birth_time_known=True)


def test_hidden_stem_affinities_match_published_response_fragment_schema():
    import json
    from pathlib import Path

    from jsonschema import Draft202012Validator

    schema_path = (
        Path(__file__).resolve().parents[1]
        / "schemas/calculate/bazi/natal.response.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    sub = {"$ref": "#/$defs/HiddenStemAffinities", "$defs": schema["$defs"]}
    occurrences = (
        _entry("month", "Jia", "Holz", StemSource.HIDDEN_PRINCIPAL),
        _entry("hour", "Yi", "Holz", StemSource.HIDDEN_CENTRAL),
    )
    result = hidden_stem_affinities("Jia", occurrences, birth_time_known=False)
    assert list(Draft202012Validator(sub).iter_errors(result)) == []


def test_hidden_stem_affinities_reject_contradictory_element_ledger():
    with pytest.raises(ValueError, match="ledger element mismatch"):
        hidden_stem_affinities(
            "Jia",
            (_entry("month", "Jia", "Feuer", StemSource.HIDDEN_PRINCIPAL),),
            birth_time_known=True,
        )


def test_real_natal_chart_hidden_stem_affinities_are_calculated_without_http():
    # This is a MoSEPH-only smoke: useful execution evidence, not SWIEPH validation.
    import os

    from bazi_engine.bazi import compute_bazi
    from bazi_engine.bazi_rules import load_default_ruleset
    from bazi_engine.match.normalize import normalize_chart
    from bazi_engine.types import BaziInput

    if os.environ.get("EPHEMERIS_MODE") != "MOSEPH":
        pytest.skip("Requires explicit EPHEMERIS_MODE=MOSEPH; do not silently change ephemeris")
    inp = BaziInput(
        birth_local="2016-08-15T16:00:00",
        timezone="Europe/Berlin",
        longitude_deg=13.405,
        latitude_deg=52.52,
    )
    result = compute_bazi(inp)
    chart = normalize_chart(result, birth_time_known=True, subject="natal", ruleset=load_default_ruleset())
    evidence = hidden_stem_affinities(chart.day_master, chart.wuxing_ledger, birth_time_known=True)
    assert chart.day_master == "Ji"
    assert evidence["exact_day_master_stem"] == []
    assert [(x["pillar"], x["stem"]) for x in evidence["same_phase_other_stem"]] == [
        ("year", "Wu"), ("month", "Wu"), ("day", "Wu"), ("hour", "Wu"),
    ]


def test_versioned_openapi_snapshot_declares_additive_natal_field():
    import json
    from pathlib import Path

    snapshot = json.loads(
        (Path(__file__).resolve().parents[1] / "spec/openapi/openapi.json").read_text(encoding="utf-8")
    )
    schema = snapshot["components"]["schemas"]["NatalResponse"]
    assert "hidden_stem_affinities" in schema["required"]
    assert schema["properties"]["hidden_stem_affinities"]["type"] == "object"
    for path in ("/calculate/bazi/natal", "/v1/calculate/bazi/natal"):
        response = snapshot["paths"][path]["post"]["responses"]["200"]
        assert response["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/NatalResponse"
