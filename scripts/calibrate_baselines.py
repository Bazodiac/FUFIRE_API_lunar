#!/usr/bin/env python3
"""Monte Carlo simulation for Wu-Xing cosine similarity baselines.

Generates random vector pairs in the positive orthant of R^5,
computes their cosine similarity, and derives mean + stddev
per density configuration.

Usage:
    python scripts/calibrate_baselines.py                    # run full simulation
    python scripts/calibrate_baselines.py --trials 10000     # more trials
    python scripts/calibrate_baselines.py --patch            # update calibration.py
    python scripts/calibrate_baselines.py --json results.json # export results
"""
from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path


def _random_wuxing_vector(rng: random.Random, n_contributions: int) -> list[float]:
    """Generate a random non-negative R^5 vector by distributing n contributions.

    Simulates the actual Wu-Xing accumulation process:
    each contribution adds weight 1.0 to a randomly chosen element bin.
    This mirrors how planets/stems/branches each add to one of 5 elements.
    """
    v = [0.0, 0.0, 0.0, 0.0, 0.0]
    for _ in range(n_contributions):
        idx = rng.randint(0, 4)
        v[idx] += 1.0
    return v


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors. Returns 0 if either is zero."""
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def simulate_baseline(
    n_contributions: int,
    n_trials: int = 5000,
    seed: int = 42,
) -> dict[str, float]:
    """Run Monte Carlo simulation for a single density configuration.

    Args:
        n_contributions: Number of element contributions per vector.
                         Both vectors in each trial use this count.
        n_trials:        Number of random vector pairs to generate.
        seed:            RNG seed for reproducibility.

    Returns:
        {"mean": float, "std": float, "n_trials": int, "n_contributions": int}
    """
    rng = random.Random(seed)
    similarities = []
    for _ in range(n_trials):
        a = _random_wuxing_vector(rng, n_contributions)
        b = _random_wuxing_vector(rng, n_contributions)
        similarities.append(_cosine_similarity(a, b))

    return {
        "mean": round(statistics.mean(similarities), 4),
        "std": round(statistics.stdev(similarities), 4),
        "n_trials": n_trials,
        "n_contributions": n_contributions,
    }


def simulate_baseline_pair(
    n_west: int,
    n_bazi: int,
    n_trials: int = 5000,
    seed: int = 42,
) -> dict[str, float]:
    """Simulate baseline for asymmetric vector pair (different contribution counts).

    In practice, Western vectors have ~7-13 contributions (planets),
    BaZi vectors have ~8-20 contributions (stems + hidden stems).
    """
    rng = random.Random(seed)
    similarities = []
    for _ in range(n_trials):
        a = _random_wuxing_vector(rng, n_west)
        b = _random_wuxing_vector(rng, n_bazi)
        similarities.append(_cosine_similarity(a, b))

    return {
        "mean": round(statistics.mean(similarities), 4),
        "std": round(statistics.stdev(similarities), 4),
        "n_trials": n_trials,
        "n_west": n_west,
        "n_bazi": n_bazi,
    }


# Density configurations matching calibration.py bucket definitions:
# n_west_bucket: 1-3 = sparse, 4-8 = medium, 9+ = dense
# n_bazi_bucket: 1-8 = sparse, 9-16 = medium, 17+ = dense
# We use representative midpoints for each bucket.
DENSITY_CONFIGS: list[dict[str, int | str]] = [
    {"west_bucket": "sparse",  "bazi_bucket": "sparse",  "n_west": 2,  "n_bazi": 5},
    {"west_bucket": "sparse",  "bazi_bucket": "medium",  "n_west": 2,  "n_bazi": 12},
    {"west_bucket": "sparse",  "bazi_bucket": "dense",   "n_west": 2,  "n_bazi": 20},
    {"west_bucket": "medium",  "bazi_bucket": "sparse",  "n_west": 6,  "n_bazi": 5},
    {"west_bucket": "medium",  "bazi_bucket": "medium",  "n_west": 6,  "n_bazi": 12},
    {"west_bucket": "medium",  "bazi_bucket": "dense",   "n_west": 6,  "n_bazi": 20},
    {"west_bucket": "dense",   "bazi_bucket": "sparse",  "n_west": 11, "n_bazi": 5},
    {"west_bucket": "dense",   "bazi_bucket": "medium",  "n_west": 11, "n_bazi": 12},
    {"west_bucket": "dense",   "bazi_bucket": "dense",   "n_west": 11, "n_bazi": 20},
]


def run_full_simulation(n_trials: int = 5000, seed: int = 42) -> list[dict]:
    """Run simulation for all 9 density configurations."""
    results = []
    for config in DENSITY_CONFIGS:
        result = simulate_baseline_pair(
            n_west=config["n_west"],
            n_bazi=config["n_bazi"],
            n_trials=n_trials,
            seed=seed,
        )
        result["west_bucket"] = config["west_bucket"]
        result["bazi_bucket"] = config["bazi_bucket"]
        results.append(result)
    return results


def format_baseline_table(results: list[dict]) -> str:
    """Format results as Python source for _BASELINE_TABLE."""
    lines = [
        "_BASELINE_TABLE: dict[tuple[str, str], tuple[float, float]] = {",
    ]
    for r in results:
        wb = r["west_bucket"]
        bb = r["bazi_bucket"]
        lines.append(f'    ("{wb}",{" " * (8 - len(wb))}"{bb}"):{" " * (8 - len(bb))} ({r["mean"]}, {r["std"]}),')
    lines.append("}")
    return "\n".join(lines)


def compare_with_existing(results: list[dict]) -> str:
    """Compare simulation results with existing hardcoded baselines."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from bazi_engine.wuxing.calibration import _BASELINE_TABLE

    lines = []
    lines.append(f"{'Config':<25} {'Existing':>18} {'Simulated':>18} {'Delta mean':>12}")
    lines.append("-" * 75)

    for r in results:
        key = (r["west_bucket"], r["bazi_bucket"])
        existing = _BASELINE_TABLE.get(key, (0, 0))
        delta = r["mean"] - existing[0]
        flag = " ***" if abs(delta) > 0.02 else ""
        lines.append(
            f"({key[0]:>8}, {key[1]:<8})  "
            f"({existing[0]:.4f}, {existing[1]:.4f})  "
            f"({r['mean']:.4f}, {r['std']:.4f})  "
            f"{delta:+.4f}{flag}"
        )

    return "\n".join(lines)


def patch_calibration_file(results: list[dict]) -> None:
    """Replace _BASELINE_TABLE in calibration.py with simulation results."""
    cal_path = Path(__file__).resolve().parent.parent / "bazi_engine" / "wuxing" / "calibration.py"
    content = cal_path.read_text()

    begin = "# ── BEGIN BASELINE_TABLE"
    end = "# ── END BASELINE_TABLE"
    try:
        start_idx = content.index(begin)
        end_marker_idx = content.index(end)
        newline_idx = content.find("\n", end_marker_idx)
        if newline_idx == -1:
            end_idx = len(content)
        else:
            end_idx = newline_idx + 1
    except ValueError:
        print(f"ERROR: Sentinel markers not found in {cal_path}", file=sys.stderr)
        print("Expected: '# ── BEGIN BASELINE_TABLE' and '# ── END BASELINE_TABLE'", file=sys.stderr)
        sys.exit(1)

    new_block = (
        "# ── BEGIN BASELINE_TABLE (do not edit manually — use scripts/calibrate_baselines.py) ──\n"
        + format_baseline_table(results)
        + "\n# ── END BASELINE_TABLE ──"
    )
    new_content = content[:start_idx] + new_block + content[end_idx:]
    cal_path.write_text(new_content)
    print(f"Patched: {cal_path}")


def _random_birth_vectors(n_births: int, seed: int) -> list[tuple[list[float], list[float], int]]:
    """Real charts for random births: (western raw, BaZi raw, n_bazi contributions).

    Births are drawn uniformly over 1940–2010 (minute resolution) at random
    places (|lat| ≤ 60°, any longitude); the moment is given in UTC, the BaZi
    pillars use TLST (time-zone independent), the western vector uses the
    production path (sign element × consensus matrix). Needs the Swiss
    Ephemeris files (SE_EPHE_PATH).
    """
    import datetime as dt

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from bazi_engine.bazi import compute_bazi
    from bazi_engine.routers.shared import format_pillar
    from bazi_engine.types import BaziInput
    from bazi_engine.western import compute_western_chart
    from bazi_engine.wuxing.analysis import (
        calculate_wuxing_from_bazi,
        calculate_wuxing_vector_from_planets,
    )
    from bazi_engine.wuxing.calibration import _count_bazi_contributions

    rng = random.Random(seed)
    start = dt.datetime(1940, 1, 1)
    span_minutes = int((dt.datetime(2011, 1, 1) - start).total_seconds() // 60)
    out = []
    while len(out) < n_births:
        moment = start + dt.timedelta(minutes=rng.randrange(span_minutes))
        lat = rng.uniform(-60.0, 60.0)
        lon = rng.uniform(-180.0, 180.0)
        try:
            western = compute_western_chart(moment.replace(tzinfo=dt.timezone.utc), lat, lon)
            bazi = compute_bazi(BaziInput(
                birth_local=moment.isoformat(), timezone="UTC",
                longitude_deg=lon, latitude_deg=lat,
                time_standard="TLST", day_boundary="midnight", strict_local_time=False,
            ))
        except Exception:  # noqa: BLE001 — skip charts the engine rejects (e.g. polar houses)
            continue
        pillars = {k: format_pillar(getattr(bazi.pillars, k)) for k in ("year", "month", "day", "hour")}
        asc = western.get("angles", {}).get("Ascendant")
        west = calculate_wuxing_vector_from_planets(western["bodies"], ascendant=asc).to_list()
        bz = calculate_wuxing_from_bazi(pillars).to_list()
        out.append((west, bz, _count_bazi_contributions(pillars)))
    return out


def simulate_births_baseline(n_births: int = 3000, permutations: int = 5, seed: int = 42) -> list[dict]:
    """Baseline from REAL random births: harmony of shuffled (west_i, bazi_j) pairs.

    The synthetic null (uniform random bins, weight 1.0) does not match real
    charts: real western vectors carry ~14 bodies with retrograde weights and a
    fixed matrix, real BaZi vectors carry 1.0/0.5/0.3 Qi weights. Shuffling
    real pairs keeps both marginal distributions and removes any link between
    the two sides — exactly the "no relation" reference the calibration needs.
    Results are grouped by the BaZi density bucket of the pair; the western
    side of a full chart is always "dense".
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from bazi_engine.wuxing.analysis import calculate_harmony_index
    from bazi_engine.wuxing.calibration import _n_bazi_bucket
    from bazi_engine.wuxing.vector import WuXingVector

    charts = _random_birth_vectors(n_births, seed)
    rng = random.Random(seed + 1)
    buckets: dict[str, list[float]] = {}
    for _ in range(permutations):
        order = list(range(len(charts)))
        rng.shuffle(order)
        for i, j in enumerate(order):
            if i == j:
                continue
            h = calculate_harmony_index(WuXingVector(*charts[i][0]), WuXingVector(*charts[j][1]))["harmony_index"]
            buckets.setdefault(_n_bazi_bucket(charts[j][2]), []).append(h)
    results = []
    for bb, values in sorted(buckets.items()):
        results.append({
            "west_bucket": "dense", "bazi_bucket": bb, "n_pairs": len(values),
            "mean": round(statistics.mean(values), 4), "std": round(statistics.pstdev(values), 4),
            "source": f"real births, n={n_births}, permutations={permutations}, seed={seed}",
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Monte Carlo Wu-Xing baseline calibration")
    parser.add_argument("--trials", type=int, default=5000, help="Trials per config (default: 5000)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument("--json", type=str, help="Export results to JSON file")
    parser.add_argument("--patch", action="store_true", help="Update calibration.py with new values")
    parser.add_argument("--quiet", action="store_true", help="Suppress comparison output")
    parser.add_argument("--null", choices=["synthetic", "births"], default="synthetic",
                        help="Null model: synthetic random bins (default) or shuffled real births")
    parser.add_argument("--births", type=int, default=3000, help="Random births for --null births")
    parser.add_argument("--min-pairs", type=int, default=500,
                        help="Minimum pairs before a births cell replaces the synthetic cell")
    args = parser.parse_args()

    if args.null == "births":
        print(f"Real-birth null model: {args.births} births, seed={args.seed}")
        births = simulate_births_baseline(n_births=args.births, seed=args.seed)
        synthetic = run_full_simulation(n_trials=args.trials, seed=args.seed)
        by_key = {(r["west_bucket"], r["bazi_bucket"]): r for r in synthetic}
        for r in births:
            print(f"  dense/{r['bazi_bucket']}: n_pairs={r['n_pairs']} mean={r['mean']} std={r['std']}")
            if r["n_pairs"] >= args.min_pairs:
                by_key[(r["west_bucket"], r["bazi_bucket"])] = r
        results = [by_key[(c["west_bucket"], c["bazi_bucket"])] for c in DENSITY_CONFIGS]
        if not args.quiet:
            print(compare_with_existing(results))
            print(format_baseline_table(results))
        if args.json:
            Path(args.json).write_text(json.dumps(results, indent=2))
        if args.patch:
            patch_calibration_file(results)
        return 0

    print(f"Running Monte Carlo simulation: {args.trials} trials/config, seed={args.seed}")
    print(f"Configurations: {len(DENSITY_CONFIGS)}")
    print()

    results = run_full_simulation(n_trials=args.trials, seed=args.seed)

    if not args.quiet:
        print(compare_with_existing(results))
        print()
        print("New baseline table:")
        print(format_baseline_table(results))

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2))
        print(f"\nExported: {args.json}")

    if args.patch:
        patch_calibration_file(results)

    return 0


if __name__ == "__main__":
    sys.exit(main())
