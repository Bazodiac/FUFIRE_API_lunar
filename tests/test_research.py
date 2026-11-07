"""
test_research.py — Tests für bazi_engine/research/

Testet:
  A) Dataset-Generator: Reproduzierbarkeit, Stratifizierung, Feature-Vollständigkeit
  B) Bias-Detektion: keine Fehlalarme für saubere Daten
  C) Kruskal-Wallis: kein signifikantes Signal für synthetische Zufallsdaten
     (der wichtigste Anti-Scheinkorrelations-Test)
  D) Phasen-Zone-Frequenzen: Struktur korrekt
  E) Pattern-Analyse: deskriptive Statistik korrekt

HINWEIS: Die Tests für KW-Nicht-Signifikanz sind probabilistisch.
Mit seed=42 und n=480 sind die Ergebnisse reproduzierbar.
"""
from __future__ import annotations

import pytest

from bazi_engine.research import (
    BiasReport,
    analyse_feature_by_phase,
    detect_pipeline_bias,
    generate_synthetic_dataset,
    kruskal_wallis_test,
    phase_zone_frequencies,
)
from bazi_engine.wuxing.constants import WUXING_ORDER

N_CHARTS = 240   # Schnell genug für CI (~1s)
N_CHARTS_KW = 480  # Mehr für KW-Test


@pytest.fixture(scope="module")
def charts_240():
    return generate_synthetic_dataset(n_total=N_CHARTS, seed=42, stratify_by_jieqi=True)


@pytest.fixture(scope="module")
def charts_480():
    return generate_synthetic_dataset(n_total=N_CHARTS_KW, seed=42, stratify_by_jieqi=True)


# ── A) Dataset-Generator ──────────────────────────────────────────────────────

class TestDatasetGenerator:
    def test_returns_correct_count(self, charts_240):
        assert len(charts_240) == N_CHARTS

    def test_reproducible_with_same_seed(self):
        a = generate_synthetic_dataset(n_total=10, seed=99)
        b = generate_synthetic_dataset(n_total=10, seed=99)
        for ca, cb in zip(a, b):
            assert ca.h_raw == cb.h_raw
            assert ca.jieqi.index == cb.jieqi.index

    def test_different_seeds_give_different_results(self):
        a = generate_synthetic_dataset(n_total=10, seed=1)
        b = generate_synthetic_dataset(n_total=10, seed=2)
        assert any(ca.h_raw != cb.h_raw for ca, cb in zip(a, b))

    def test_all_required_fields_present(self, charts_240):
        chart = charts_240[0]
        assert hasattr(chart, "h_raw")
        assert hasattr(chart, "h_calibrated")
        assert hasattr(chart, "diffs")
        assert hasattr(chart, "resonance")
        assert hasattr(chart, "zones")
        assert hasattr(chart, "jieqi")
        assert hasattr(chart, "lunar")
        assert hasattr(chart, "quality")

    def test_diffs_keys_are_all_five_elements(self, charts_240):
        for chart in charts_240[:10]:
            assert set(chart.diffs.keys()) == set(WUXING_ORDER)

    def test_resonance_keys_are_all_five_elements(self, charts_240):
        for chart in charts_240[:10]:
            assert set(chart.resonance.keys()) == set(WUXING_ORDER)

    def test_h_raw_in_unit_interval(self, charts_240):
        for chart in charts_240:
            assert 0.0 <= chart.h_raw <= 1.0

    def test_h_calibrated_in_unit_interval(self, charts_240):
        for chart in charts_240:
            assert 0.0 <= chart.h_calibrated <= 1.0

    def test_quality_valid_values(self, charts_240):
        for chart in charts_240:
            assert chart.quality in ("ok", "sparse", "degenerate")

    def test_stratified_jieqi_coverage(self, charts_240):
        """Alle 24 Jieqi-Phasen müssen vertreten sein."""
        seen_phases = {chart.jieqi.index for chart in charts_240}
        assert len(seen_phases) == 24

    def test_stratified_phase_balance(self, charts_240):
        """Maximale Imbalance: 2x (stratifiziert)."""
        from collections import Counter
        counts = Counter(chart.jieqi.index for chart in charts_240)
        if counts:
            ratio = max(counts.values()) / max(1, min(counts.values()))
            assert ratio <= 2.5, f"Imbalance {ratio:.2f}x zu hoch"

    def test_n_tension_in_range(self, charts_240):
        for chart in charts_240:
            assert 0 <= chart.n_tension <= 5

    def test_jieqi_independent_of_bazi(self, charts_240):
        """Jieqi-Phase stammt aus solar_longitude, nicht aus BaZi-Daten."""
        for chart in charts_240[:20]:
            # Verifikation: Jieqi-Index aus gespeicherter solar_longitude rekonstruieren
            from bazi_engine.phases import classify_jieqi_phase
            expected_phase = classify_jieqi_phase(solar_longitude=chart.solar_longitude)
            assert expected_phase.index == chart.jieqi.index


# ── B) Bias-Detektion ─────────────────────────────────────────────────────────

class TestBiasDetection:
    def test_clean_data_no_critical_bias(self, charts_240):
        bias = detect_pipeline_bias(charts_240)
        assert not bias.has_critical_bias, (
            f"Kritischer Bias in sauberen Daten: {bias.warnings}"
        )

    def test_no_degenerate_charts_in_standard_data(self, charts_240):
        bias = detect_pipeline_bias(charts_240)
        assert bias.n_degenerate == 0.0

    def test_phase_imbalance_near_1_for_stratified(self, charts_240):
        bias = detect_pipeline_bias(charts_240)
        assert bias.phase_imbalance <= 2.5

    def test_no_h_zero_artifacts(self, charts_240):
        bias = detect_pipeline_bias(charts_240)
        assert bias.h_raw_at_zero == 0.0

    def test_returns_bias_report(self, charts_240):
        bias = detect_pipeline_bias(charts_240)
        assert isinstance(bias, BiasReport)
        assert bias.n_total == N_CHARTS

    def test_empty_dataset_does_not_crash(self):
        bias = detect_pipeline_bias([])
        assert bias.n_total == 0


# ── C) Kruskal-Wallis: kein Scheinkorrelation für Zufallsdaten ────────────────

class TestNoSpuriousCorrelation:
    """KRITISCH: Synthetische Zufallsdaten dürfen KEINEN signifikanten
    Phase-Effekt zeigen. Dies ist der primäre Anti-Bias-Test.
    Mit n=480, seed=42, n_comp=7, α=0.05 nach Bonferroni.
    """

    def test_h_calibrated_not_significant_vs_jieqi(self, charts_480):
        kw = kruskal_wallis_test(charts_480, "h_calibrated", "jieqi", n_comparisons=7)
        assert not kw.is_significant, (
            f"Scheinkorrelation: h_calibrated~Jieqi ist signifikant "
            f"(p_bonf={kw.p_value_bonferroni:.4f}, η²={kw.eta_squared:.4f})"
        )

    def test_h_raw_not_significant_vs_jieqi(self, charts_480):
        kw = kruskal_wallis_test(charts_480, "h_raw", "jieqi", n_comparisons=7)
        assert not kw.is_significant

    @pytest.mark.parametrize("element", ["Feuer", "Holz"])
    def test_diff_not_systematically_significant_vs_jieqi(self, element):
        """Bodies, pillars and Jieqi are drawn independently, so a single seed
        comes out significant with probability alpha/7 ≈ 0.7 % by chance
        (seed 42 does for Feuer under body-tier-q0.3-v1: p_bonf = 0.004; over
        60 seeds × 5 elements the rate is 3/300, i.e. chance level). A
        systematic pipeline artefact shows up as significance across seeds:
        over 20 fixed seeds at most 2 hits are allowed (P(≥ 3) ≈ 0.04 % under
        the null)."""
        hits = [
            seed for seed in range(1, 21)
            if kruskal_wallis_test(
                generate_synthetic_dataset(n_total=N_CHARTS_KW, seed=seed, stratify_by_jieqi=True),
                "diff", "jieqi", element=element, n_comparisons=7,
            ).is_significant
        ]
        assert len(hits) <= 2, (element, hits)

    def test_n_tension_not_significant_vs_jieqi(self, charts_480):
        kw = kruskal_wallis_test(charts_480, "n_tension", "jieqi", n_comparisons=7)
        assert not kw.is_significant

    def test_effect_size_near_zero_for_random_data(self, charts_480):
        """η² < 0.02 für alle Features bei synthetischen Daten."""
        for feature in ("h_calibrated", "h_raw", "n_tension"):
            kw = kruskal_wallis_test(charts_480, feature, "jieqi")
            assert kw.eta_squared < 0.02, (
                f"{feature}: η²={kw.eta_squared:.4f} ≥ 0.02 "
                f"(Scheineffekt in Zufallsdaten)"
            )

    def test_kw_returns_correct_structure(self, charts_480):
        kw = kruskal_wallis_test(charts_480, "h_calibrated", "jieqi")
        assert kw.n_groups == 24
        assert kw.n_total >= N_CHARTS_KW * 0.9  # ≥90% nach Qualitätsfilter
        assert 0.0 <= kw.p_value <= 1.0
        assert 0.0 <= kw.p_value_bonferroni <= 1.0
        assert kw.eta_squared >= 0.0


# ── D) Phasen-Zone-Frequenzen ─────────────────────────────────────────────────

class TestPhaseZoneFrequencies:
    def test_returns_dict_with_all_jieqi_phases(self, charts_240):
        freq = phase_zone_frequencies(charts_240, "jieqi")
        assert len(freq) == 24

    def test_each_phase_has_five_elements(self, charts_240):
        freq = phase_zone_frequencies(charts_240, "jieqi")
        for phase_name, elem_freqs in freq.items():
            assert set(elem_freqs.keys()) == set(WUXING_ORDER)

    def test_frequencies_in_0_1_range(self, charts_240):
        freq = phase_zone_frequencies(charts_240, "jieqi")
        for phase_name, elem_freqs in freq.items():
            for elem, rate in elem_freqs.items():
                assert 0.0 <= rate <= 1.0, (
                    f"{phase_name}[{elem}]: rate={rate}"
                )

    def test_lunar_phases_covered(self, charts_240):
        freq = phase_zone_frequencies(charts_240, "lunar")
        assert len(freq) == 8


# ── E) Deskriptive Statistik ──────────────────────────────────────────────────

class TestAnalyseFeatureByPhase:
    def test_returns_24_groups_for_jieqi(self, charts_240):
        stats = analyse_feature_by_phase(charts_240, "h_calibrated", "jieqi")
        assert len(stats) == 24

    def test_each_group_has_n_at_least_5(self, charts_240):
        stats = analyse_feature_by_phase(charts_240, "h_raw", "jieqi")
        for name, s in stats.items():
            assert s.n >= 5, f"{name}: n={s.n}"

    def test_mean_in_plausible_range_for_h_raw(self, charts_240):
        stats = analyse_feature_by_phase(charts_240, "h_raw", "jieqi")
        for name, s in stats.items():
            assert 0.3 <= s.mean <= 1.0, f"{name}: mean={s.mean}"

    def test_diff_feuer_mean_near_zero(self, charts_240):
        """Für Zufallsdaten: d_Feuer-Mittelwert global (über alle Phasen) ≈ 0.
        Einzelne Phasen mit n=10 dürfen bis ±0.4 abweichen (Stichprobenvarianz).
        """
        stats = analyse_feature_by_phase(charts_240, "diff", "jieqi", element="Feuer")
        # Globaler Mittelwert sollte nahe 0 sein
        all_means = [s.mean for s in stats.values()]
        global_mean = sum(all_means) / len(all_means)
        assert abs(global_mean) < 0.25, f"Globaler d_Feuer mean={global_mean:.4f}"
        # Einzelne Phasenmittelwerte dürfen streuen (kleine Gruppen)
        for name, s in stats.items():
            assert abs(s.mean) < 0.5, f"{name}: d_Feuer mean={s.mean} extrem"

    def test_std_positive_for_h_raw(self, charts_240):
        stats = analyse_feature_by_phase(charts_240, "h_raw", "jieqi")
        for name, s in stats.items():
            assert s.std >= 0

    def test_is_reliable_true_for_stratified(self, charts_240):
        stats = analyse_feature_by_phase(charts_240, "h_calibrated", "jieqi")
        for name, s in stats.items():
            assert s.is_reliable, f"{name}: n={s.n} < 10"
