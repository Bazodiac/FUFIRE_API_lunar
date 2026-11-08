"""compute_synastry on synthetic charts: determinism, symmetry, time gate (spec acceptance)."""
from __future__ import annotations

import json

import pytest

from bazi_engine import __version__
from bazi_engine.exc import CalculationError
from bazi_engine.synastry import SynastryPersonInput, compute_synastry
from tests.fixtures.synastry_charts import BASE_A, BASE_B, assert_mirrored, day_bounds, make_chart


def _a(**kw: object) -> SynastryPersonInput:
    return SynastryPersonInput(chart=make_chart(BASE_A, asc=15.0, mc=280.0, cusp_start=15.0), **kw)  # type: ignore[arg-type]


def _b(**kw: object) -> SynastryPersonInput:
    return SynastryPersonInput(chart=make_chart(BASE_B, asc=200.0, mc=110.0, cusp_start=200.0), **kw)  # type: ignore[arg-type]


def test_top_level_shape() -> None:
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=True))
    assert set(out) == {"aspects", "house_overlays", "sign_layer", "wuxing_pair_factors", "provenance"}
    assert out["aspects"], "fixture must produce at least one aspect"


def test_deterministic() -> None:
    first = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=True))
    second = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=True))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.parametrize("known_a, known_b", [(True, True), (True, False), (False, True), (False, False)])
def test_swapping_a_and_b_mirrors_the_result(known_a: bool, known_b: bool) -> None:
    ab = compute_synastry(_a(birth_time_known=known_a), _b(birth_time_known=known_b))
    ba = compute_synastry(_b(birth_time_known=known_b), _a(birth_time_known=known_a))
    assert_mirrored(ab, ba)


def test_birth_time_gate_for_b() -> None:
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=False))
    # no overlays in B's houses
    assert all(r["house"] is None and r["status"] == "unavailable_missing_time" for r in out["house_overlays"]["a_in_b"])
    # overlays in A's houses still present
    assert all(isinstance(r["house"], int) and r["status"] == "ok" for r in out["house_overlays"]["b_in_a"])
    # no ascendant / MC of B anywhere
    assert all(r["to_factor"] not in ("Ascendant", "MC") for r in out["aspects"])
    assert "Ascendant" not in [e["factor"] for e in out["sign_layer"]["factors"]["person_b"]]
    assert "Ascendant" not in [f["factor"] for f in out["wuxing_pair_factors"]["person_b"]["factors"]]
    # A keeps its angles
    assert "Ascendant" in [e["factor"] for e in out["sign_layer"]["factors"]["person_a"]]
    assert out["provenance"]["house_system_used"] == {"person_a": "placidus", "person_b": None}
    assert {"code": "birth_time_unknown", "person": "person_b",
            "detail": "Birth time unknown: computed at the assumed local time 12:00:00; Ascendant, MC and houses "
                      "are not used."} \
        in out["provenance"]["warnings"]


def test_moon_range_clause_only_with_bounds() -> None:
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=False, day_bounds=day_bounds(BASE_B, Moon=(183.0, 196.0))))
    (warning,) = out["provenance"]["warnings"]
    assert warning["detail"] == (
        "Birth time unknown: computed at the assumed local time 12:00:00; Ascendant, MC and houses are not used; "
        "the Moon range over the local day is in sign_layer."
    )


def test_discarded_clock_time_is_named_in_the_warning() -> None:
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=False, time_discarded=True))
    (warning,) = out["provenance"]["warnings"]
    assert warning["detail"].endswith(" The supplied clock time was discarded.")


def test_known_time_rejects_unknown_time_extras() -> None:
    with pytest.raises(ValueError):
        _a(birth_time_known=True, time_discarded=True)
    with pytest.raises(ValueError):
        _a(birth_time_known=True, day_bounds=day_bounds(BASE_A))


def test_provenance() -> None:
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=True))
    assert out["provenance"] == {
        "engine_version": __version__,
        "ephemeris_mode": "SWIEPH",
        "zodiac_mode": "tropical",
        "house_system_used": {"person_a": "placidus", "person_b": "placidus"},
        "orb_policy_id": "synastry-orbs-v1",
        "weighting_id": "synastry-weights-v1",
        "base_weighting_id": "body-tier-q0.3-v1",
        "mapping_version": "sign-element-consensus-v1",
        "warnings": [],
    }


def test_house_system_fallback_is_warned_without_coordinates() -> None:
    a = SynastryPersonInput(chart=make_chart(BASE_A, house_system_used="porphyry", fallback=True), birth_time_known=True)
    out = compute_synastry(a, _b(birth_time_known=True))
    assert out["provenance"]["house_system_used"]["person_a"] == "porphyry"
    assert out["provenance"]["warnings"] == [
        {"code": "house_system_fallback", "person": "person_a", "detail": "Placidus undefined; porphyry used."},
    ]


def test_mixed_ephemeris_modes_fail_visibly() -> None:
    a = SynastryPersonInput(chart=make_chart(BASE_A, ephemeris_mode="MOSEPH"), birth_time_known=True)
    with pytest.raises(CalculationError):
        compute_synastry(a, _b(birth_time_known=True))
