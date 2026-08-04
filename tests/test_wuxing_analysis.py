"""
test_wuxing_analysis.py — Unit tests for bazi_engine/wuxing/analysis.py

All imports directly from wuxing.analysis — not via fusion re-exports.
Tests domain correctness of planet mapping, BaZi extraction, and harmony math.
"""
from __future__ import annotations

from math import isclose

import pytest

from bazi_engine.wuxing.analysis import (
    _BRANCH_HIDDEN,
    _STEM_TO_ELEMENT,
    calculate_harmony_index,
    calculate_wuxing_from_bazi,
    calculate_wuxing_vector_from_planets,
    interpret_harmony,
    is_night_chart,
    planet_to_wuxing,
)
from bazi_engine.wuxing.vector import WuXingVector

VALID_ELEMENTS = {"Holz", "Feuer", "Erde", "Metall", "Wasser"}
ALL_BRANCHES = ["Zi","Chou","Yin","Mao","Chen","Si","Wu","Wei","Shen","You","Xu","Hai"]
ALL_STEMS = ["Jia","Yi","Bing","Ding","Wu","Ji","Geng","Xin","Ren","Gui"]


# ── planet_to_wuxing ─────────────────────────────────────────────────────────

class TestPlanetToWuxing:
    def test_sun_feuer(self):
        assert planet_to_wuxing("Sun") == "Feuer"

    def test_moon_wasser(self):
        assert planet_to_wuxing("Moon") == "Wasser"

    def test_mercury_day_is_erde(self):
        assert planet_to_wuxing("Mercury", is_night=False) == "Erde"

    def test_mercury_night_is_metall(self):
        assert planet_to_wuxing("Mercury", is_night=True) == "Metall"

    def test_jupiter_holz(self):
        assert planet_to_wuxing("Jupiter") == "Holz"

    def test_saturn_erde(self):
        assert planet_to_wuxing("Saturn") == "Erde"

    def test_unknown_defaults_to_erde(self):
        assert planet_to_wuxing("Quaoar") == "Erde"

    def test_all_results_are_valid_elements(self):
        planets = ["Sun","Moon","Venus","Mars","Jupiter","Saturn","Uranus","Neptune","Pluto","Chiron"]
        for p in planets:
            assert planet_to_wuxing(p) in VALID_ELEMENTS


# ── is_night_chart ────────────────────────────────────────────────────────────

class TestIsNightChart:
    def test_without_ascendant_defaults_day(self):
        assert is_night_chart(180.0) is False

    def test_sun_above_horizon_is_day(self):
        # ASC=180 → MC=90 (Cancer 0° culminating).
        # Sun at 90 sits at the MC = above horizon → day chart.
        assert is_night_chart(90.0, ascendant=180.0) is False

    def test_sun_below_horizon_is_night(self):
        # ASC=180 → IC=270 (Capricorn 0° at nadir).
        # Sun at 270 sits at the IC = below horizon → night chart.
        assert is_night_chart(270.0, ascendant=180.0) is True

    def test_returns_bool(self):
        assert isinstance(is_night_chart(0.0), bool)


# ── calculate_wuxing_vector_from_planets ─────────────────────────────────────

class TestCalculateWuxingVectorFromPlanets:
    MINIMAL_BODIES = {
        "Sun": {"longitude": 315.0, "is_retrograde": False, "zodiac_sign": 10},
        "Moon": {"longitude": 45.0, "is_retrograde": False, "zodiac_sign": 1},
        "Jupiter": {"longitude": 60.0, "is_retrograde": False, "zodiac_sign": 2},
    }

    def test_returns_wuxing_vector(self):
        result = calculate_wuxing_vector_from_planets(self.MINIMAL_BODIES)
        assert isinstance(result, WuXingVector)

    def test_sun_contributes_feuer(self):
        bodies = {"Sun": {"longitude": 0.0, "is_retrograde": False}}
        v = calculate_wuxing_vector_from_planets(bodies)
        assert v.feuer > 0

    def test_moon_contributes_wasser(self):
        bodies = {"Moon": {"longitude": 0.0, "is_retrograde": False}}
        v = calculate_wuxing_vector_from_planets(bodies)
        assert v.wasser > 0

    def test_jupiter_contributes_holz(self):
        bodies = {"Jupiter": {"longitude": 0.0, "is_retrograde": False}}
        v = calculate_wuxing_vector_from_planets(bodies)
        assert v.holz > 0

    def test_retrograde_weight_higher(self):
        direct_body = {"Sun": {"longitude": 0.0, "is_retrograde": False}}
        retro_body  = {"Sun": {"longitude": 0.0, "is_retrograde": True}}
        v_direct = calculate_wuxing_vector_from_planets(direct_body, use_retrograde_weight=True)
        v_retro  = calculate_wuxing_vector_from_planets(retro_body,  use_retrograde_weight=True)
        assert v_retro.feuer > v_direct.feuer

    def test_retrograde_disabled_equal_weight(self):
        direct_body = {"Sun": {"longitude": 0.0, "is_retrograde": False}}
        retro_body  = {"Sun": {"longitude": 0.0, "is_retrograde": True}}
        v_direct = calculate_wuxing_vector_from_planets(direct_body, use_retrograde_weight=False)
        v_retro  = calculate_wuxing_vector_from_planets(retro_body,  use_retrograde_weight=False)
        assert v_retro.feuer == v_direct.feuer

    def test_error_bodies_skipped(self):
        bodies = {
            "Sun":  {"longitude": 0.0, "is_retrograde": False},
            "Fake": {"error": "not found"},
        }
        v_with_error = calculate_wuxing_vector_from_planets(bodies)
        v_clean      = calculate_wuxing_vector_from_planets({"Sun": bodies["Sun"]})
        assert v_with_error.to_list() == v_clean.to_list()

    def test_all_values_non_negative(self):
        v = calculate_wuxing_vector_from_planets(self.MINIMAL_BODIES)
        assert all(x >= 0 for x in v.to_list())


# ── _BRANCH_HIDDEN and _STEM_TO_ELEMENT completeness ─────────────────────────

class TestBranchHiddenData:
    def test_all_12_branches_present(self):
        assert set(_BRANCH_HIDDEN.keys()) == set(ALL_BRANCHES)

    @pytest.mark.parametrize("branch", ALL_BRANCHES)
    def test_hidden_elements_are_valid(self, branch):
        for elem, weight in _BRANCH_HIDDEN[branch]:
            assert elem in VALID_ELEMENTS, f"{branch}: invalid element {elem!r}"

    @pytest.mark.parametrize("branch", ALL_BRANCHES)
    def test_weights_are_positive(self, branch):
        for elem, weight in _BRANCH_HIDDEN[branch]:
            assert weight > 0, f"{branch}: non-positive weight {weight}"

    @pytest.mark.parametrize("branch", ALL_BRANCHES)
    def test_main_qi_weight_is_1(self, branch):
        """First hidden stem (Main Qi, 主气) must always have weight 1.0."""
        first_weight = _BRANCH_HIDDEN[branch][0][1]
        assert first_weight == 1.0, f"{branch}: Main Qi weight={first_weight}, expected 1.0"

    def test_all_10_stems_present(self):
        assert set(_STEM_TO_ELEMENT.keys()) == set(ALL_STEMS)

    @pytest.mark.parametrize("stem", ALL_STEMS)
    def test_stem_elements_are_valid(self, stem):
        assert _STEM_TO_ELEMENT[stem] in VALID_ELEMENTS


# ── calculate_wuxing_from_bazi ────────────────────────────────────────────────

class TestCalculateWuxingFromBazi:
    SAMPLE_PILLARS = {
        "year":  {"stem": "Jia",  "branch": "Zi"},   # Wood/Water
        "month": {"stem": "Bing", "branch": "Yin"},  # Fire/Wood
        "day":   {"stem": "Wu",   "branch": "Chen"},  # Earth/Earth
        "hour":  {"stem": "Geng", "branch": "Shen"},  # Metal/Metal
    }

    def test_returns_wuxing_vector(self):
        assert isinstance(calculate_wuxing_from_bazi(self.SAMPLE_PILLARS), WuXingVector)

    def test_all_values_non_negative(self):
        v = calculate_wuxing_from_bazi(self.SAMPLE_PILLARS)
        assert all(x >= 0 for x in v.to_list())

    def test_jia_stem_adds_holz(self):
        pillars = {"year": {"stem": "Jia", "branch": "Mao"}}  # Mao=pure Wood
        v = calculate_wuxing_from_bazi(pillars)
        assert v.holz > 0

    def test_bing_stem_adds_feuer(self):
        pillars = {"year": {"stem": "Bing", "branch": "Zi"}}  # Zi=pure Water
        v = calculate_wuxing_from_bazi(pillars)
        assert v.feuer > 0

    def test_german_keys_work(self):
        pillars = {"year": {"stamm": "Jia", "zweig": "Mao"}}
        v = calculate_wuxing_from_bazi(pillars)
        assert v.holz > 0

    def test_four_pillars_more_than_one(self):
        v_four = calculate_wuxing_from_bazi(self.SAMPLE_PILLARS)
        v_one  = calculate_wuxing_from_bazi({"year": self.SAMPLE_PILLARS["year"]})
        total_four = sum(v_four.to_list())
        total_one  = sum(v_one.to_list())
        assert total_four > total_one

    def test_zi_branch_adds_wasser(self):
        """Zi (子) is pure Water — hidden stem is only Gui (Wasser)."""
        pillars = {"year": {"stem": "Wu", "branch": "Zi"}}  # Wu=Earth, Zi=Water
        v = calculate_wuxing_from_bazi(pillars)
        # Erde from stem + Wasser from branch
        assert v.erde > 0
        assert v.wasser > 0


# ── calculate_harmony_index ───────────────────────────────────────────────────

class TestCalculateHarmonyIndex:
    def test_identical_vectors_harmony_1(self):
        v = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        result = calculate_harmony_index(v, v)
        assert isclose(result["harmony_index"], 1.0, abs_tol=0.01)

    def test_orthogonal_vectors_harmony_0(self):
        v1 = WuXingVector(1.0, 0.0, 0.0, 0.0, 0.0)
        v2 = WuXingVector(0.0, 1.0, 0.0, 0.0, 0.0)
        result = calculate_harmony_index(v1, v2)
        assert isclose(result["harmony_index"], 0.0, abs_tol=0.01)

    def test_harmony_in_0_1_range(self):
        import random
        rng = random.Random(42)
        for _ in range(20):
            v1 = WuXingVector(*[rng.random() for _ in range(5)])
            v2 = WuXingVector(*[rng.random() for _ in range(5)])
            result = calculate_harmony_index(v1, v2)
            assert 0.0 <= result["harmony_index"] <= 1.0

    def test_returns_required_keys(self):
        v = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        result = calculate_harmony_index(v, v)
        assert {"harmony_index", "interpretation", "method", "western_vector", "bazi_vector"} <= result.keys()

    def test_cosine_method(self):
        v = WuXingVector(1.0, 2.0, 0.0, 0.5, 3.0)
        result = calculate_harmony_index(v, v, method="cosine")
        assert isclose(result["harmony_index"], 1.0, abs_tol=0.01)
        assert result["method"] == "cosine"

    def test_invalid_method_raises(self):
        v = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        with pytest.raises(ValueError, match="Unknown harmony method"):
            calculate_harmony_index(v, v, method="euclidean")

    def test_zero_vectors_return_0(self):
        z = WuXingVector.zero()
        result = calculate_harmony_index(z, z, method="cosine")
        assert result["harmony_index"] == 0.0

    def test_interpretation_is_string(self):
        v = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        result = calculate_harmony_index(v, v)
        assert isinstance(result["interpretation"], str)
        assert len(result["interpretation"]) > 0


# ── interpret_harmony ─────────────────────────────────────────────────────────

class TestInterpretHarmony:
    """FUF-147: interpret_harmony is a claim-safe raw diagnostic label.

    The old raw-threshold judgment labels ("Starke Resonanz", "Gute
    Harmonie", …) are forbidden — raw H is empirically always >= 0.5, so
    they read as positive user judgments for nearly every chart.
    """

    CASES = [0.9, 0.7, 0.5, 0.3, 0.05]

    @pytest.mark.parametrize("h", CASES)
    def test_label_is_diagnostic_not_judgment(self, h):
        result = interpret_harmony(h)
        assert "Rohwert" in result
        assert "kein Nutzerurteil" in result
        assert f"{h:.2f}" in result

    @pytest.mark.parametrize("h", [0.6, 0.8, 1.0])
    def test_high_raw_values_produce_no_positive_judgment(self, h):
        result = interpret_harmony(h)
        for forbidden in ("Starke Resonanz", "Gute Harmonie", "perfekter Harmonie"):
            assert forbidden not in result

    def test_returns_non_empty_string(self):
        for h in [0.0, 0.25, 0.5, 0.75, 1.0]:
            assert isinstance(interpret_harmony(h), str)
            assert len(interpret_harmony(h)) > 0
