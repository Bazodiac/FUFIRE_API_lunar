"""
test_integration_fusion.py — End-to-end integration tests for compute_fusion_analysis()

Testet vier Ebenen:
  I.   Schemavalidierung (Ausgabestruktur vollständig?)
  II.  Mathematische Invarianten (Vektoren, H-Bereich, Determinismus)
  III. Interpretationskonsistenz (Text passt zu H-Wert)
  IV.  Logik-B-Integration (compute_fusion_analysis → classify_zones → format_report_b)
       ← NEU: verbindet Fusion-Output mit Zonenklassifikation

No HTTP, no ephemeris files needed. Alle Tests mit synthetischen Daten.
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import isclose

import pytest

from bazi_engine.fusion import compute_fusion_analysis, generate_fusion_interpretation
from bazi_engine.wuxing.analysis import interpret_harmony
from bazi_engine.wuxing.vector import WuXingVector

# ── Fixtures ─────────────────────────────────────────────────────────────────

BIRTH_UTC = datetime(2024, 2, 10, 13, 30, tzinfo=timezone.utc)

# Realistic western chart snapshot (no actual ephemeris needed)
WESTERN_BODIES_AQUARIUS = {
    "Sun":    {"longitude": 321.5, "is_retrograde": False, "zodiac_sign": 10},  # Aquarius → Fire
    "Moon":   {"longitude":  45.2, "is_retrograde": False, "zodiac_sign":  1},  # Taurus → Earth/Metal
    "Mercury":{"longitude": 305.1, "is_retrograde": True,  "zodiac_sign":  9},  # Capricorn → Earth (retro)
    "Venus":  {"longitude": 310.0, "is_retrograde": False, "zodiac_sign":  9},  # Metal
    "Mars":   {"longitude": 150.0, "is_retrograde": False, "zodiac_sign":  4},  # Fire
    "Jupiter":{"longitude":  60.0, "is_retrograde": False, "zodiac_sign":  2},  # Wood
    "Saturn": {"longitude": 340.0, "is_retrograde": False, "zodiac_sign": 10},  # Earth
}

BAZI_PILLARS_STANDARD = {
    "year":  {"stem": "Jia",  "branch": "Chen"},  # Wood / Earth
    "month": {"stem": "Bing", "branch": "Yin"},   # Fire  / Wood
    "day":   {"stem": "Jia",  "branch": "Chen"},  # Wood / Earth
    "hour":  {"stem": "Xin",  "branch": "Wei"},   # Metal / Earth
}

# Pure-element bodies for edge-case testing
BODIES_PURE_FIRE = {
    "Sun":  {"longitude": 0.0,   "is_retrograde": False},
    "Mars": {"longitude": 90.0,  "is_retrograde": False},
    "Pluto":{"longitude": 180.0, "is_retrograde": False},
}

BODIES_PURE_WATER = {
    "Moon":    {"longitude": 0.0,  "is_retrograde": False},
    "Neptune": {"longitude": 90.0, "is_retrograde": False},
    "Chiron":  {"longitude": 180.0,"is_retrograde": False},
}

PILLARS_PURE_WOOD = {
    "year":  {"stem": "Jia", "branch": "Mao"},  # Wood/Wood
    "month": {"stem": "Yi",  "branch": "Yin"},  # Wood/Wood
    "day":   {"stem": "Jia", "branch": "Mao"},
    "hour":  {"stem": "Yi",  "branch": "Yin"},
}

PILLARS_PURE_METAL = {
    "year":  {"stem": "Geng", "branch": "You"},  # Metal/Metal
    "month": {"stem": "Xin",  "branch": "You"},
    "day":   {"stem": "Geng", "branch": "Shen"},
    "hour":  {"stem": "Xin",  "branch": "You"},
}


# ── Schema / structure tests ──────────────────────────────────────────────────

class TestFusionOutputSchema:
    def setup_method(self):
        self.result = compute_fusion_analysis(
            birth_utc_dt=BIRTH_UTC,
            latitude=52.52,
            longitude=13.405,
            bazi_pillars=BAZI_PILLARS_STANDARD,
            western_bodies=WESTERN_BODIES_AQUARIUS,
        )

    def test_top_level_keys_present(self):
        expected = {
            "wu_xing_vectors", "harmony_index",
            "elemental_comparison", "cosmic_state", "fusion_interpretation",
        }
        assert expected <= self.result.keys()

    def test_wu_xing_vectors_has_two_sub_keys(self):
        vecs = self.result["wu_xing_vectors"]
        assert "western_planets" in vecs
        assert "bazi_pillars" in vecs

    def test_wu_xing_each_vector_has_five_elements(self):
        vecs = self.result["wu_xing_vectors"]
        for key in ("western_planets", "bazi_pillars"):
            assert len(vecs[key]) == 5, f"{key} should have 5 elements"

    def test_wu_xing_element_keys_are_german(self):
        for key in ("western_planets", "bazi_pillars"):
            assert set(self.result["wu_xing_vectors"][key].keys()) == {
                "Holz", "Feuer", "Erde", "Metall", "Wasser"
            }

    def test_harmony_index_structure(self):
        h = self.result["harmony_index"]
        assert "harmony_index" in h
        assert "interpretation" in h

    def test_elemental_comparison_has_five_elements(self):
        comp = self.result["elemental_comparison"]
        assert len(comp) == 5

    def test_elemental_comparison_each_has_diff_keys(self):
        for elem, data in self.result["elemental_comparison"].items():
            assert {"western", "bazi", "difference"} <= data.keys()

    def test_cosmic_state_is_float(self):
        assert isinstance(self.result["cosmic_state"], float)

    def test_fusion_interpretation_is_non_empty_string(self):
        interp = self.result["fusion_interpretation"]
        assert isinstance(interp, str)
        assert len(interp) > 10


# ── Mathematical invariants ───────────────────────────────────────────────────

class TestFusionMathInvariants:
    def _run(self, western, pillars):
        return compute_fusion_analysis(
            birth_utc_dt=BIRTH_UTC,
            latitude=52.52,
            longitude=13.405,
            bazi_pillars=pillars,
            western_bodies=western,
        )

    def test_harmony_index_in_0_1(self):
        result = self._run(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        h = result["harmony_index"]["harmony_index"]
        assert 0.0 <= h <= 1.0

    def test_cosmic_state_in_0_1(self):
        result = self._run(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        assert 0.0 <= result["cosmic_state"] <= 1.0

    def test_elemental_difference_equals_western_minus_bazi(self):
        result = self._run(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        vecs = result["wu_xing_vectors"]
        comp = result["elemental_comparison"]
        for elem in ("Holz", "Feuer", "Erde", "Metall", "Wasser"):
            expected_diff = round(vecs["western_planets"][elem] - vecs["bazi_pillars"][elem], 3)
            assert isclose(comp[elem]["difference"], expected_diff, abs_tol=1e-6), (
                f"{elem}: diff={comp[elem]['difference']}, expected={expected_diff}"
            )

    def test_normalized_vectors_have_l2_norm_1(self):
        """wu_xing_vectors stores L2-normalized unit vectors (‖v‖₂ = 1)."""
        from math import sqrt
        result = self._run(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        for key in ("western_planets", "bazi_pillars"):
            values = list(result["wu_xing_vectors"][key].values())
            l2 = sqrt(sum(x ** 2 for x in values))
            assert isclose(l2, 1.0, abs_tol=1e-6), f"{key} L2 norm={l2}, expected 1.0"

    def test_determinism_same_input_same_output(self):
        r1 = self._run(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        r2 = self._run(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        assert r1["harmony_index"]["harmony_index"] == r2["harmony_index"]["harmony_index"]
        assert r1["cosmic_state"] == r2["cosmic_state"]
        assert r1["fusion_interpretation"] == r2["fusion_interpretation"]

    def test_pure_fire_vs_pure_water_low_harmony(self):
        """Sun+Mars+Pluto (Fire) vs Water pillars → orthogonal → low harmony."""
        result = self._run(BODIES_PURE_FIRE, {
            "year": {"stem": "Ren", "branch": "Zi"},
            "month": {"stem": "Gui", "branch": "Hai"},
            "day": {"stem": "Ren", "branch": "Zi"},
            "hour": {"stem": "Gui", "branch": "Hai"},
        })
        h = result["harmony_index"]["harmony_index"]
        assert h < 0.3, f"Fire vs Water should have low harmony, got {h}"

    def test_same_element_profile_high_harmony(self):
        """Same bodies for both systems → perfect harmony."""
        # Use same planetary bodies for western, and pillars that map to same elements
        # Jia/Mao = pure Wood, Jupiter = Wood → high harmony
        result = self._run(
            {"Jupiter": {"longitude": 0.0, "is_retrograde": False}},
            PILLARS_PURE_WOOD,
        )
        h = result["harmony_index"]["harmony_index"]
        assert h > 0.7, f"Wood vs Wood should have high harmony, got {h}"


# ── Interpretation consistency ────────────────────────────────────────────────

class TestFusionInterpretationConsistency:
    def _run(self, western, pillars):
        return compute_fusion_analysis(
            birth_utc_dt=BIRTH_UTC,
            latitude=0.0, longitude=0.0,
            bazi_pillars=pillars,
            western_bodies=western,
        )

    def test_high_raw_harmony_gets_no_judgment_text(self):
        # FUF-147: even maximal raw congruence must not produce judgment prose.
        result = self._run(
            {"Jupiter": {"longitude": 0.0, "is_retrograde": False}},
            PILLARS_PURE_WOOD,
        )
        text = result["fusion_interpretation"]
        assert "starker Resonanz" not in text
        assert "harmonisch" not in text
        assert "kein Nutzerurteil" in text

    def test_low_raw_harmony_gets_no_judgment_text(self):
        result = self._run(BODIES_PURE_FIRE, {
            "year": {"stem": "Ren", "branch": "Zi"},
            "month": {"stem": "Gui", "branch": "Hai"},
            "day": {"stem": "Ren", "branch": "Zi"},
            "hour": {"stem": "Gui", "branch": "Hai"},
        })
        text = result["fusion_interpretation"]
        assert "unterschiedliche Richtungen" not in text
        assert "kein Nutzerurteil" in text

    def test_calibrated_coherence_in_interpretation_text(self):
        result = self._run(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        text = result["fusion_interpretation"]
        assert "Kalibrierte Kohärenz" in text
        assert "kein Nutzerurteil" in text

    def test_dominant_elements_mentioned(self):
        result = self._run(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        text = result["fusion_interpretation"]
        assert "Westliche Dominanz" in text
        assert "Östliche Dominanz" in text


# ── generate_fusion_interpretation standalone ─────────────────────────────────

class TestGenerateFusionInterpretation:
    def test_returns_string(self):
        v = WuXingVector(1.0, 1.0, 1.0, 1.0, 1.0)
        comp = {e: {"western": 0.2, "bazi": 0.2, "difference": 0.0}
                for e in ("Holz", "Feuer", "Erde", "Metall", "Wasser")}
        result = generate_fusion_interpretation(0.8, comp, v, v)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize("h", [0.8, 0.5, 0.1])
    def test_raw_value_only_as_labeled_diagnostic(self, h):
        # FUF-147: the raw value appears only as a labeled expert diagnostic,
        # never as level-dependent judgment prose.
        v = WuXingVector(1.0, 0.0, 0.0, 0.0, 0.0)
        comp = {}
        result = generate_fusion_interpretation(h, comp, v, v)
        assert f"H_raw={h:.2f}" in result
        assert "kein Nutzerurteil" in result
        for forbidden in ("Resonanz", "Balance", "unterschiedliche Richtungen"):
            assert forbidden not in result, f"h={h}: judgment fragment {forbidden!r} present"


# ── Edge cases ────────────────────────────────────────────────────────────────

class TestFusionEdgeCases:
    def test_empty_bodies_still_returns_result(self):
        """No planetary bodies → zero vector → result still valid dict."""
        result = compute_fusion_analysis(
            birth_utc_dt=BIRTH_UTC,
            latitude=0.0, longitude=0.0,
            bazi_pillars=BAZI_PILLARS_STANDARD,
            western_bodies={},
        )
        assert "harmony_index" in result
        assert "wu_xing_vectors" in result

    def test_all_error_bodies_treated_as_empty(self):
        bodies_with_errors = {
            "Sun":  {"error": "calc failed"},
            "Moon": {"error": "not found"},
        }
        result = compute_fusion_analysis(
            birth_utc_dt=BIRTH_UTC,
            latitude=0.0, longitude=0.0,
            bazi_pillars=BAZI_PILLARS_STANDARD,
            western_bodies=bodies_with_errors,
        )
        assert isinstance(result["cosmic_state"], float)

    def test_single_pillar_works(self):
        result = compute_fusion_analysis(
            birth_utc_dt=BIRTH_UTC,
            latitude=0.0, longitude=0.0,
            bazi_pillars={"year": {"stem": "Jia", "branch": "Zi"}},
            western_bodies=WESTERN_BODIES_AQUARIUS,
        )
        assert 0.0 <= result["harmony_index"]["harmony_index"] <= 1.0


# ── IV. Logik-B-Integration ───────────────────────────────────────────────────
# Verbindet compute_fusion_analysis() → classify_zones() → format_report_b()
# Das ist der vollständige Interpretationspfad der diagnostischen Karte.

from bazi_engine.wuxing.zones import (
    ZoneResult,
    build_leitfragen,
    classify_zones,
    format_report_b,
)


def _fusion_to_zones(western_bodies, bazi_pillars) -> tuple[dict, ZoneResult]:
    """Hilfsfunktion: Fusion → elemental_comparison → ZoneResult."""
    fusion = compute_fusion_analysis(
        birth_utc_dt=BIRTH_UTC,
        latitude=52.52, longitude=13.405,
        bazi_pillars=bazi_pillars,
        western_bodies=western_bodies,
    )
    assert "elemental_comparison" in fusion
    west_norm = fusion["wu_xing_vectors"]["western_planets"]
    bazi_norm = fusion["wu_xing_vectors"]["bazi_pillars"]
    result = classify_zones(west_norm, bazi_norm)
    return fusion, result


class TestLogikBPipeline:
    """Testet den vollständigen Fusion → Zonen → Report Pfad."""

    def test_classify_zones_from_fusion_output_returns_zone_result(self):
        _, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        assert isinstance(result, ZoneResult)
        assert set(result.zones.keys()) == {"Holz", "Feuer", "Erde", "Metall", "Wasser"}

    def test_all_zones_are_valid_labels(self):
        _, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        for zone in result.zones.values():
            assert zone in ("TENSION", "STRENGTH", "DEVELOPMENT", "NEUTRAL")

    def test_diffs_from_zones_match_elemental_comparison(self):
        """ZoneResult.diffs und elemental_comparison weichen maximal 5e-4 ab.

        elemental_comparison["difference"] = round(w − b, 3) → gerundet.
        classify_zones() berechnet diffs aus den Rohwerten (nicht gerundet).
        Beide stammen aus denselben wu_xing_vectors → Abweichung ≤ 5e-4.
        """
        fusion, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        comp = fusion["elemental_comparison"]
        for elem in ("Holz", "Feuer", "Erde", "Metall", "Wasser"):
            stored_diff = comp[elem]["difference"]
            zone_diff   = result.diffs[elem]
            assert abs(zone_diff - stored_diff) < 5e-4, (
                f"{elem}: zones.diffs={zone_diff:.6f}, "
                f"elemental_comparison={stored_diff:.6f} "
                f"(Δ={abs(zone_diff-stored_diff):.2e})"
            )

    def test_zone_tension_matches_high_abs_diff(self):
        """Jedes Element mit |d| > 0.15 muss TENSION sein."""
        fusion, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        comp = fusion["elemental_comparison"]
        for elem in ("Holz", "Feuer", "Erde", "Metall", "Wasser"):
            abs_d = abs(comp[elem]["difference"])
            if abs_d > 0.15:
                assert result.zones[elem] == "TENSION", (
                    f"{elem}: |d|={abs_d:.4f} > 0.15 → expected TENSION, "
                    f"got {result.zones[elem]}"
                )

    def test_zone_non_tension_matches_low_abs_diff(self):
        """Jedes Element mit |d| ≤ 0.15 darf nicht TENSION sein."""
        fusion, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        comp = fusion["elemental_comparison"]
        for elem in ("Holz", "Feuer", "Erde", "Metall", "Wasser"):
            abs_d = abs(comp[elem]["difference"])
            if abs_d <= 0.15:
                assert result.zones[elem] != "TENSION", (
                    f"{elem}: |d|={abs_d:.4f} ≤ 0.15 → should not be TENSION"
                )

    def test_build_leitfragen_from_fusion_returns_dict(self):
        _, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        lf = build_leitfragen(result)
        assert "tension" in lf
        assert "development" in lf

    def test_format_report_b_runs_on_fusion_data(self):
        fusion, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        h = fusion["harmony_index"]["harmony_index"]
        label = interpret_harmony(h)
        report = format_report_b(h, label, result, use_sheng=True)
        assert isinstance(report, str)
        assert len(report) > 100

    def test_report_harmony_value_matches_fusion_harmony(self):
        """Der im Report angezeigte H-Wert muss dem Fusion-H entsprechen."""
        fusion, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        h = fusion["harmony_index"]["harmony_index"]
        label = interpret_harmony(h)
        report = format_report_b(h, label, result)
        # H×100, gerundet auf 2 Dezimalen
        h_str = f"{h * 100:.2f}"
        assert h_str in report, f"H={h_str} nicht im Report gefunden"

    def test_pure_fire_vs_water_produces_tension_elements(self):
        """Feuer vs. Wasser: hohe Differenzen → mindestens ein TENSION-Element."""
        _, result = _fusion_to_zones(
            BODIES_PURE_FIRE,
            {"year": {"stem": "Ren", "branch": "Zi"},
             "month": {"stem": "Gui", "branch": "Hai"},
             "day": {"stem": "Ren", "branch": "Zi"},
             "hour": {"stem": "Gui", "branch": "Hai"}},
        )
        assert len(result.tension_elements()) >= 1

    def test_same_element_produces_no_tension(self):
        """Reines Holz West + Reines Holz BaZi → kein TENSION (d ≈ 0 für Holz)."""
        _, result = _fusion_to_zones(
            {"Jupiter": {"longitude": 0.0, "is_retrograde": False},
             "Uranus":  {"longitude": 60.0, "is_retrograde": False}},
            PILLARS_PURE_WOOD,
        )
        # Holz sollte kein Tension haben (beide Seiten hoch, d klein)
        assert result.zones["Holz"] != "TENSION"

    def test_report_sections_present_for_active_elements(self):
        """Wenn Tension-Elemente existieren, muss SPANNUNGSFELDER im Report sein."""
        fusion, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        h = fusion["harmony_index"]["harmony_index"]
        report = format_report_b(h, interpret_harmony(h), result)
        if result.tension_elements():
            assert "SPANNUNGSFELDER" in report
        if result.strength_elements():
            assert "STÄRKEFELDER" in report

    def test_leitfragen_tension_elements_match_zones(self):
        """Leitfragen-Tension-Keys müssen exakt mit tension_elements() übereinstimmen."""
        _, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        lf = build_leitfragen(result)
        assert set(lf["tension"].keys()) == set(result.tension_elements())

    def test_leitfragen_development_elements_match_zones(self):
        """Leitfragen-Development-Keys müssen exakt mit development_elements() übereinstimmen."""
        _, result = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        lf = build_leitfragen(result)
        assert set(lf["development"].keys()) == set(result.development_elements())

    def test_cosmic_state_equals_harmony_index(self):
        """cosmic_state ist derzeit redundant mit harmony_index (dokumentierte Limitation)."""
        fusion, _ = _fusion_to_zones(WESTERN_BODIES_AQUARIUS, BAZI_PILLARS_STANDARD)
        h = fusion["harmony_index"]["harmony_index"]
        cs = fusion["cosmic_state"]
        assert abs(h - cs) < 1e-6, (
            f"cosmic_state={cs} ≠ harmony_index={h} (Redundanz-Invariante verletzt)"
        )
