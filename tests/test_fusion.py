"""
test_fusion.py — Tests für fusion.py (Re-Export-Integrität + Regressionstests)

Dieser Test prüft primär:
  1. Re-Export-Kette: alle Symbole via bazi_engine.fusion erreichbar
  2. Regressionstests der Kernsemantik (keine Duplikation zu spezialisierten Tests)
  3. Logik-B-Verbindung: classify_zones() nutzt fusion-Ausgabe korrekt

Spezialisierte Tests für die gleichen Funktionen:
  test_wuxing_vector.py    — WuXingVector Geometrie
  test_wuxing_analysis.py  — Harmony, planet_to_wuxing, BaZi-Extraktion
  test_wuxing_constants.py — PLANET_TO_WUXING, WUXING_ORDER, WUXING_INDEX
  test_wuxing_zones.py     — classify_zones, Leitfragen, Sheng-Zyklus
  test_solar_time.py       — equation_of_time, true_solar_time (NOAA-Goldwerte)
  test_integration_fusion.py — compute_fusion_analysis End-to-End
"""
from __future__ import annotations

from math import isclose

import pytest

from bazi_engine.fusion import (
    WUXING_ORDER,
    WuXingVector,
    calculate_harmony_index,
    calculate_wuxing_from_bazi,
    compute_fusion_analysis,
    equation_of_time,
    generate_fusion_interpretation,
    interpret_harmony,
    is_night_chart,
    planet_to_wuxing,
    true_solar_time,
    true_solar_time_from_civil,
)


class TestWuXingVector:
    """Tests for WuXingVector dataclass."""

    def test_to_list(self):
        v = WuXingVector(1.0, 2.0, 3.0, 4.0, 5.0)
        assert v.to_list() == [1.0, 2.0, 3.0, 4.0, 5.0]

    def test_to_dict(self):
        v = WuXingVector(1.0, 2.0, 3.0, 4.0, 5.0)
        d = v.to_dict()
        assert d == {"Holz": 1.0, "Feuer": 2.0, "Erde": 3.0, "Metall": 4.0, "Wasser": 5.0}

    def test_magnitude(self):
        v = WuXingVector(3.0, 4.0, 0.0, 0.0, 0.0)
        assert v.magnitude() == 5.0

    def test_normalize(self):
        v = WuXingVector(3.0, 4.0, 0.0, 0.0, 0.0)
        n = v.normalize()
        assert isclose(n.holz, 0.6, abs_tol=1e-9)
        assert isclose(n.feuer, 0.8, abs_tol=1e-9)
        assert isclose(n.magnitude(), 1.0, abs_tol=1e-9)

    def test_normalize_zero_vector(self):
        v = WuXingVector.zero()
        n = v.normalize()
        assert n.to_list() == [0, 0, 0, 0, 0]

    def test_zero(self):
        v = WuXingVector.zero()
        assert v.to_list() == [0, 0, 0, 0, 0]


class TestPlanetToWuxing:
    """Tests for planet_to_wuxing mapping."""

    def test_sun_is_fire(self):
        assert planet_to_wuxing("Sun") == "Feuer"

    def test_moon_is_water(self):
        assert planet_to_wuxing("Moon") == "Wasser"

    def test_mercury_day_is_earth(self):
        assert planet_to_wuxing("Mercury", is_night=False) == "Erde"

    def test_mercury_night_is_metal(self):
        assert planet_to_wuxing("Mercury", is_night=True) == "Metall"

    def test_venus_is_metal(self):
        assert planet_to_wuxing("Venus") == "Metall"

    def test_mars_is_fire(self):
        assert planet_to_wuxing("Mars") == "Feuer"

    def test_jupiter_is_wood(self):
        assert planet_to_wuxing("Jupiter") == "Holz"

    def test_saturn_is_earth(self):
        assert planet_to_wuxing("Saturn") == "Erde"

    def test_unknown_planet_defaults_to_earth(self):
        assert planet_to_wuxing("UnknownPlanet") == "Erde"


class TestIsNightChart:
    """Tests for is_night_chart detection."""

    def test_default_is_day_chart(self):
        # Without ascendant, defaults to day chart
        assert is_night_chart(0.0) is False
        assert is_night_chart(180.0) is False

    def test_with_ascendant_sun_below_horizon(self):
        # ASC=180 → IC=270 (nadir). Sun at IC = below horizon = night.
        assert is_night_chart(270.0, ascendant=180.0) is True

    def test_with_ascendant_sun_above_horizon(self):
        # ASC=180 → MC=90 (zenith). Sun at MC = above horizon = day.
        assert is_night_chart(90.0, ascendant=180.0) is False


class TestCalculateWuxingFromBazi:
    """Tests for BaZi to Wu-Xing conversion."""

    def test_simple_pillars(self):
        pillars = {
            "year": {"stem": "Jia", "branch": "Zi"},  # Wood stem, Water branch
            "month": {"stem": "Bing", "branch": "Yin"},  # Fire stem, Wood branch
            "day": {"stem": "Wu", "branch": "Chen"},  # Earth stem, Earth branch
            "hour": {"stem": "Geng", "branch": "Shen"},  # Metal stem, Metal branch
        }
        v = calculate_wuxing_from_bazi(pillars)
        # Stems: Jia=Wood(1), Bing=Fire(1), Wu=Earth(1), Geng=Metal(1)
        # Branches have hidden stems with weights
        assert v.holz > 0
        assert v.feuer > 0
        assert v.erde > 0
        assert v.metall > 0
        assert v.wasser > 0

    def test_german_keys(self):
        # Test with German keys (stamm/zweig)
        pillars = {
            "year": {"stamm": "Jia", "zweig": "Zi"},
        }
        v = calculate_wuxing_from_bazi(pillars)
        assert v.holz > 0  # Jia = Wood
        assert v.wasser > 0  # Zi = Water


class TestHarmonyIndex:
    """Tests for harmony index calculation."""

    def test_identical_vectors_perfect_harmony(self):
        v1 = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        v2 = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        result = calculate_harmony_index(v1, v2)
        assert result["harmony_index"] == pytest.approx(1.0, abs=0.01)

    def test_orthogonal_vectors_low_harmony(self):
        v1 = WuXingVector(1.0, 0.0, 0.0, 0.0, 0.0)
        v2 = WuXingVector(0.0, 1.0, 0.0, 0.0, 0.0)
        result = calculate_harmony_index(v1, v2)
        assert result["harmony_index"] == pytest.approx(0.0, abs=0.01)

    def test_cosine_method(self):
        v1 = WuXingVector(1.0, 1.0, 0.0, 0.0, 0.0)
        v2 = WuXingVector(1.0, 1.0, 0.0, 0.0, 0.0)
        result = calculate_harmony_index(v1, v2, method="cosine")
        assert result["harmony_index"] == pytest.approx(1.0, abs=0.01)
        assert result["method"] == "cosine"

    def test_invalid_method_raises(self):
        v1 = WuXingVector.zero()
        v2 = WuXingVector.zero()
        with pytest.raises(ValueError):
            calculate_harmony_index(v1, v2, method="invalid")


class TestInterpretHarmony:
    """Tests for harmony interpretation."""

    def test_high_value_is_diagnostic_only(self):
        # FUF-147: raw values must never map to judgment prose.
        result = interpret_harmony(0.85)
        assert "Rohwert" in result
        assert "kein Nutzerurteil" in result
        assert "Starke Resonanz" not in result

    def test_mid_value_is_diagnostic_only(self):
        result = interpret_harmony(0.45)
        assert "Rohwert" in result
        assert "0.45" in result

    def test_low_value_is_diagnostic_only(self):
        result = interpret_harmony(0.1)
        assert "kein Nutzerurteil" in result


class TestEquationOfTime:
    """Tests for equation of time calculation."""

    def test_february_negative(self):
        # Around day 45 (mid-Feb), EoT should be around -14 minutes
        eot = equation_of_time(45)
        assert -15 < eot < -10

    def test_november_positive(self):
        # Around day 310 (early Nov), EoT should be around +16 minutes
        eot = equation_of_time(310)
        assert 10 < eot < 18

    def test_april_near_zero(self):
        # Around day 105 (mid-Apr), EoT should be near 0
        eot = equation_of_time(105)
        assert -5 < eot < 5

    def test_simplified_formula(self):
        eot_precise = equation_of_time(180, use_precise=True)
        eot_simple = equation_of_time(180, use_precise=False)
        # Both should be in reasonable range
        assert -10 < eot_precise < 10
        assert -10 < eot_simple < 10

    def test_range_full_year(self):
        # EoT should always be between -15 and +17 minutes
        for day in range(1, 366):
            eot = equation_of_time(day)
            assert -16 < eot < 18


class TestTrueSolarTime:
    """Tests for true solar time calculations."""

    def test_basic_calculation(self):
        # 12:00 civil time at prime meridian
        tst = true_solar_time(12.0, 0.0, 1)
        assert 11.5 < tst < 12.5

    def test_with_timezone_offset(self):
        # Berlin: lon=13.4°, tz=+1
        tst = true_solar_time(12.0, 13.4, 180, timezone_offset_hours=1.0)
        assert 0 <= tst < 24

    def test_normalization(self):
        # Result should always be 0-24
        tst = true_solar_time(23.5, 180.0, 1)
        assert 0 <= tst < 24


class TestTrueSolarTimeFromCivil:
    """Tests for true solar time from civil time."""

    def test_berlin_example(self):
        # Berlin: lon=13.405°, standard meridian=15° (CET)
        tst = true_solar_time_from_civil(12.0, 13.405, 180, standard_meridian_deg=15.0)
        assert 11.5 < tst < 12.5

    def test_auto_standard_meridian(self):
        # Should auto-calculate standard meridian
        tst = true_solar_time_from_civil(12.0, 13.405, 180)
        assert 0 <= tst < 24


def test_non_ledger_function_accepts_ascendant():
    """Non-ledger variant must accept ascendant parameter."""
    from bazi_engine.wuxing.analysis import (
        calculate_wuxing_vector_from_planets,
        calculate_wuxing_vector_from_planets_with_ledger,
    )
    bodies = {
        "Sun": {"longitude": 100.0, "is_retrograde": False},
        "Moon": {"longitude": 200.0, "is_retrograde": False},
        "Mercury": {"longitude": 50.0, "is_retrograde": False},
    }
    v_with_asc = calculate_wuxing_vector_from_planets(bodies, ascendant=280.0)
    v_ledger, _ = calculate_wuxing_vector_from_planets_with_ledger(bodies, ascendant=280.0)
    assert v_with_asc.to_list() == v_ledger.to_list()


_STANDARD_PILLARS = {
    "year":  {"stem": "Jia",  "branch": "Chen"},
    "month": {"stem": "Bing", "branch": "Yin"},
    "day":   {"stem": "Jia",  "branch": "Chen"},
    "hour":  {"stem": "Xin",  "branch": "Wei"},
}
_STANDARD_BODIES = {
    "Sun":     {"longitude": 321.5, "is_retrograde": False},
    "Moon":    {"longitude":  45.2, "is_retrograde": False},
    "Mercury": {"longitude": 280.1, "is_retrograde": True},
    "Venus":   {"longitude": 310.0, "is_retrograde": False},
    "Mars":    {"longitude": 150.0, "is_retrograde": False},
    "Jupiter": {"longitude":  60.0, "is_retrograde": False},
    "Saturn":  {"longitude": 340.0, "is_retrograde": False},
}


class TestComputeFusionAnalysis:
    """Tests for complete fusion analysis — schema and re-export contract."""

    def _run(self):
        from datetime import datetime, timezone
        return compute_fusion_analysis(
            birth_utc_dt=datetime(2024, 2, 10, 13, 30, tzinfo=timezone.utc),
            latitude=52.52,
            longitude=13.405,
            bazi_pillars=_STANDARD_PILLARS,
            western_bodies=_STANDARD_BODIES,
        )

    def test_returns_expected_keys(self):
        result = self._run()
        assert "wu_xing_vectors" in result
        assert "harmony_index" in result
        assert "elemental_comparison" in result
        assert "cosmic_state" in result
        assert "fusion_interpretation" in result

    def test_elemental_comparison_has_five_elements(self):
        result = self._run()
        assert set(result["elemental_comparison"].keys()) == {
            "Holz", "Feuer", "Erde", "Metall", "Wasser"
        }

    def test_elemental_comparison_diff_equals_west_minus_bazi(self):
        """Regressiontest: difference = round(western − bazi, 3).

        elemental_comparison["difference"] wird auf 3 Dezimalen gerundet gespeichert.
        Toleranz = 5e-4 (halbe letzte Stelle bei round(..., 3)).
        """
        result = self._run()
        vecs = result["wu_xing_vectors"]
        for elem in ("Holz", "Feuer", "Erde", "Metall", "Wasser"):
            w = vecs["western_planets"][elem]
            b = vecs["bazi_pillars"][elem]
            d = result["elemental_comparison"][elem]["difference"]
            assert abs(round(w - b, 3) - d) < 5e-4, (
                f"{elem}: round(w−b)={round(w-b,3):.6f}, stored diff={d:.6f}"
            )

    def test_logik_b_pipeline_from_fusion_output(self):
        """Verbindet compute_fusion_analysis → classify_zones → format_report_b.

        Dieser Test ist der Nachweis, dass der Logik-B-Interpretationspfad
        auf realer Fusion-Ausgabe funktioniert.
        """
        from bazi_engine.wuxing.analysis import interpret_harmony as ih
        from bazi_engine.wuxing.zones import classify_zones, format_report_b

        result = self._run()
        west_norm = result["wu_xing_vectors"]["western_planets"]
        bazi_norm = result["wu_xing_vectors"]["bazi_pillars"]

        zone_result = classify_zones(west_norm, bazi_norm)
        h = result["harmony_index"]["harmony_index"]
        report = format_report_b(h, ih(h), zone_result)

        assert isinstance(report, str)
        assert len(report) > 50
        assert "FUSION ANALYSE" in report

    def test_logik_b_zone_diffs_match_elemental_comparison(self):
        """Zonenklassifikation (Rohwerte) und elemental_comparison (gerundet) weichen
        um maximal 5e-4 ab (Rundungsartefakt: elemental_comparison rundet auf 3 Stellen).
        Beide stammen aus denselben normierten Vektoren — classify_zones nutzt die
        ungerundeten Rohwerte aus wu_xing_vectors direkt.
        """
        from bazi_engine.wuxing.zones import classify_zones

        result = self._run()
        west_norm = result["wu_xing_vectors"]["western_planets"]
        bazi_norm = result["wu_xing_vectors"]["bazi_pillars"]
        zone_result = classify_zones(west_norm, bazi_norm)

        for elem in ("Holz", "Feuer", "Erde", "Metall", "Wasser"):
            stored_diff = result["elemental_comparison"][elem]["difference"]
            zone_diff   = zone_result.diffs[elem]
            # elemental_comparison rundet auf 3 Dezimalen → max. Abweichung 5e-4
            assert abs(stored_diff - zone_diff) < 5e-4, (
                f"{elem}: elemental_comparison.difference={stored_diff:.6f}, "
                f"zones.diffs={zone_diff:.6f} (Diff: {abs(stored_diff-zone_diff):.2e})"
            )


class TestGenerateFusionInterpretation:
    """Tests for fusion interpretation generation."""

    def test_returns_string(self):
        western = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        bazi = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        comparison = {
            elem: {"western": 0.2, "bazi": 0.2, "difference": 0.0}
            for elem in WUXING_ORDER
        }
        result = generate_fusion_interpretation(0.8, comparison, western, bazi)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_high_raw_value_yields_no_judgment_prose(self):
        # FUF-147: without a calibration result the output is fail-closed.
        western = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        bazi = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        comparison = {}
        result = generate_fusion_interpretation(0.8, comparison, western, bazi)
        assert "starker Resonanz" not in result
        assert "harmonisch" not in result
        assert "kein Nutzerurteil" in result
        assert "fail-closed" in result

    def test_low_raw_value_yields_no_judgment_prose(self):
        western = WuXingVector(1.0, 0.0, 0.0, 0.0, 0.0)
        bazi = WuXingVector(0.0, 1.0, 0.0, 0.0, 0.0)
        comparison = {}
        result = generate_fusion_interpretation(0.2, comparison, western, bazi)
        assert "unterschiedliche Richtungen" not in result
        assert "kein Nutzerurteil" in result
