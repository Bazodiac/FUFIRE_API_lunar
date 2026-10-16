"""Unit tests for ``scripts/minimize_snapshot_diff.py`` (owner decision E7).

The script keeps the HEAD value wherever a regenerated snapshot differs only
by float noise inside the snapshot tolerance, so a regeneration diff shows
material changes only. These tests pin the pure merge/report functions; the
git-facing wrapper is exercised by the regeneration recipe in CLAUDE.md.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "minimize_snapshot_diff.py"
SPEC = importlib.util.spec_from_file_location("minimize_snapshot_diff", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

TOL = 1e-6


def test_noise_below_tolerance_keeps_head_value():
    old = {"a": 1.0, "b": [1.0, 2.0], "c": {"d": 0.5}}
    new = {"a": 1.0 + 5e-7, "b": [1.0, 2.0 - 9e-7], "c": {"d": 0.5 + 1e-7}}
    assert mod.merge(old, new, TOL) == old
    assert mod.material_paths(old, mod.merge(old, new, TOL)) == []


def test_material_change_is_kept_and_reported():
    old = {"eot": -13.614, "tst": 22.0262, "label": "rc4"}
    new = {"eot": -13.8803, "tst": 22.0262 + 1e-9, "label": "rc5"}
    merged = mod.merge(old, new, TOL)
    assert merged == {"eot": -13.8803, "tst": 22.0262, "label": "rc5"}
    assert sorted(mod.material_paths(old, merged)) == ["/eot", "/label"]


def test_additive_key_keeps_sibling_noise_at_head():
    """S-4 review finding: one added key (e.g. ``eot_source``) must not turn
    every float sibling into a rewritten value or collapse the report."""
    old = {"x": {"a": 1.0, "c": [0.1, 0.2]}}
    new = {"x": {"a": 1.0 + 1e-9, "b": 2.0, "c": [0.1 + 1e-9, 0.2]}}
    merged = mod.merge(old, new, TOL)
    assert merged == {"x": {"a": 1.0, "b": 2.0, "c": [0.1, 0.2]}}
    assert mod.material_paths(old, merged) == ["/x/b (added)"]


def test_removed_key_and_list_length_changes_are_reported():
    assert mod.merge({"a": 1.0, "gone": 1.0}, {"a": 1.0 + 1e-9}, TOL) == {"a": 1.0}
    assert mod.material_paths({"a": 1.0, "gone": 1.0}, {"a": 1.0}) == ["/gone (removed)"]
    assert mod.merge([1.0, 2.0], [1.0 + 1e-9], TOL) == [1.0]
    assert mod.merge([1.0], [1.0 + 1e-9, 3.0], TOL) == [1.0, 3.0]
    assert mod.material_paths([1.0, 2.0], [1.0]) == ["[] (length 2 -> 1)"]


def test_bools_are_never_treated_as_numbers():
    assert mod.merge(True, False, TOL) is False
    assert mod.merge({"f": True}, {"f": 1}, TOL) == {"f": 1}


def test_exactly_at_tolerance_is_noise_and_above_is_material():
    assert mod.merge(1.0, 1.0 + TOL, TOL) == 1.0
    assert mod.merge(1.0, 1.0 + 2 * TOL, TOL) == 1.0 + 2 * TOL
