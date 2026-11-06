"""Tests for Monte Carlo calibration simulation."""
from __future__ import annotations

import pytest


def test_simulate_baseline_returns_mean_and_std():
    from scripts.calibrate_baselines import simulate_baseline
    result = simulate_baseline(n_contributions=10, n_trials=100, seed=42)
    assert "mean" in result
    assert "std" in result
    assert 0.0 < result["mean"] < 1.0
    assert 0.0 < result["std"] < 0.5


def test_simulate_baseline_is_deterministic():
    from scripts.calibrate_baselines import simulate_baseline
    r1 = simulate_baseline(n_contributions=10, n_trials=500, seed=123)
    r2 = simulate_baseline(n_contributions=10, n_trials=500, seed=123)
    assert r1["mean"] == r2["mean"]
    assert r1["std"] == r2["std"]


def test_sparse_baseline_lower_than_dense():
    """Sparse vectors (fewer non-zero components) should have lower expected cosine."""
    from scripts.calibrate_baselines import simulate_baseline
    sparse = simulate_baseline(n_contributions=2, n_trials=1000, seed=99)
    dense = simulate_baseline(n_contributions=12, n_trials=1000, seed=99)
    assert sparse["mean"] < dense["mean"]


def test_baseline_table_matches_simulation():
    """Verify calibration.py values match reproducible simulation.

    Cells listed in BIRTHS_CALIBRATED_CELLS come from shuffled real births and
    are checked by test_births_cells_match_real_birth_simulation instead.
    """
    from bazi_engine.wuxing.calibration import _BASELINE_TABLE, BIRTHS_CALIBRATED_CELLS
    from scripts.calibrate_baselines import run_full_simulation

    results = run_full_simulation(n_trials=5000, seed=42)
    for r in results:
        key = (r["west_bucket"], r["bazi_bucket"])
        if key in BIRTHS_CALIBRATED_CELLS:
            continue
        existing_mean, existing_std = _BASELINE_TABLE[key]
        assert abs(r["mean"] - existing_mean) < 0.001, (
            f"{key}: mean {existing_mean} != simulated {r['mean']}"
        )
        assert abs(r["std"] - existing_std) < 0.001, (
            f"{key}: std {existing_std} != simulated {r['std']}"
        )


def test_simulation_stable_across_trial_counts():
    """Baselines should be stable whether we run 5000 or 10000 trials."""
    from scripts.calibrate_baselines import simulate_baseline_pair
    r5k = simulate_baseline_pair(n_west=11, n_bazi=12, n_trials=5000, seed=42)
    r10k = simulate_baseline_pair(n_west=11, n_bazi=12, n_trials=10000, seed=42)
    assert abs(r5k["mean"] - r10k["mean"]) < 0.01, "Baseline unstable at 5000 trials"


@pytest.mark.swieph
def test_births_cells_match_real_birth_simulation():
    """The real-birth cells reproduce from the documented command (seed 42)."""
    from bazi_engine.wuxing.calibration import _BASELINE_TABLE, BIRTHS_CALIBRATED_CELLS
    from scripts.calibrate_baselines import simulate_births_baseline

    results = {(r["west_bucket"], r["bazi_bucket"]): r
               for r in simulate_births_baseline(n_births=3000, seed=42)}
    for key in BIRTHS_CALIBRATED_CELLS:
        mean, std = _BASELINE_TABLE[key]
        assert abs(results[key]["mean"] - mean) < 0.001, (key, results[key], mean)
        assert abs(results[key]["std"] - std) < 0.001, (key, results[key], std)
