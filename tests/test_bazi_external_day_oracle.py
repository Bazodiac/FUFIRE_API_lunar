"""Independent published-calendar checks for the default day offset.

Cited results were transcribed from third-party almanacs on 2026-11-06;
this is useful corroboration, not expert-reviewed formal verification.
No ephemeris files, API or rate-limiter dependency required.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from bazi_engine.bazi import sexagenary_day_index_from_date
from bazi_engine.bazi_rules import day_offset_from_ruleset
from bazi_engine.constants import BRANCHES, DAY_OFFSET, STEMS

_BASE = Path(__file__).resolve().parents[1]
_ORACLE = json.loads((_BASE / "tests/external_sexagenary_day_oracle.json").read_text(encoding="utf-8"))
_RULESET = json.loads((_BASE / "spec/rulesets/standard_bazi_2026.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _ORACLE["cases"], ids=[c["date"] for c in _ORACLE["cases"]])
def test_day_cycle_matches_published_calendar_cases(case):
    d = date.fromisoformat(case["date"])
    idx = sexagenary_day_index_from_date(d.year, d.month, d.day)
    assert (STEMS[idx % 10], BRANCHES[idx % 12]) == (case["expected_stem"], case["expected_branch"])
    assert case["source_urls"], "An oracle case without provenance is not independently checkable"


def test_ruleset_offset_matches_external_cases_without_auto_certification():
    assert day_offset_from_ruleset(_RULESET) == DAY_OFFSET
    assert _RULESET["day_cycle_anchor"]["anchor_verification"] == "unverified"
