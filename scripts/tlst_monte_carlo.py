"""Reproducible Monte-Carlo check of the engine's TLST context against Swiss Ephemeris.

FU-TLST-POLICY / INC-1, AC-05. Draws birth inputs from a seeded generator
(default seed 20261106) over 1950–2030, many IANA zones (north + south,
half/quarter-hour offsets, DST and non-DST zones, the ±12/±14 h extremes),
positive and negative longitudes — near the zone meridian AND anywhere on
Earth (large zone/longitude differences) — winter and summer dates, and
wall-clocks down to the microsecond. A DST-window stratum places wall-clocks
around real transitions so the ambiguous and nonexistent paths are exercised.

Each valid sample is resolved exactly as ``POST /v2/calculate/bazi`` resolves
it (``time_utils.resolve_local_instant``; nonexistent wall-clocks are
rejected → counted as discarded; ambiguous ones get a seeded fold choice) and
decomposed with ``time_context.compute_effective_time_context_from_instant``
(the function ``compute_bazi`` uses for ``standard="TLST"``). The result is
compared with the independent oracle ``swe.lmt_to_lat``:

* |TLST − oracle| in minutes (circular) — max, P99, mean;
* the apparent-solar calendar date (civil date + rollover vs oracle date);
* the 2-hour branch (half-open, Zi = [23, 1)) — formula written here.

Samples whose ORACLE hour lies within ``--tolerance`` minutes of a decision
edge (odd hours, solar midnight) are not counted as agreement: they go to the
``boundary_uncertain`` bucket and are reported with their outcome. Every
date/branch disagreement must additionally be flagged by the engine's own
``nearest_tlst_decision_edge`` (``unflagged_disagreements`` must be 0).

Usage::

    SE_EPHE_PATH=/tmp/ephe python scripts/tlst_monte_carlo.py --n 5000 --json out.json
    python scripts/tlst_monte_carlo.py --seed 20261106 --n 50000      # release-gate size

Exit 1 on any violation or if fewer than ``--n`` valid samples ran.
Read-only; no repository file is touched.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

import swisseph as swe

from bazi_engine.time_context import (
    EOT_MODEL_TOLERANCE_MINUTES,
    compute_effective_time_context_from_instant,
    nearest_tlst_decision_edge,
)
from bazi_engine.time_utils import LocalTimeError, resolve_local_instant

DEFAULT_SEED = 20261106
YEAR_MIN, YEAR_MAX = 1950, 2030

# A spread of IANA zones: hemispheres, DST / no DST, fractional offsets, extremes.
ZONES: tuple[str, ...] = (
    "UTC", "Europe/Berlin", "Europe/Madrid", "Europe/Lisbon", "Europe/London", "Europe/Moscow",
    "Africa/Johannesburg", "Africa/Lagos", "Asia/Tehran", "Asia/Kabul", "Asia/Kolkata",
    "Asia/Kathmandu", "Asia/Yangon", "Asia/Urumqi", "Asia/Shanghai", "Asia/Tokyo",
    "Australia/Eucla", "Australia/Adelaide", "Australia/Sydney", "Pacific/Auckland",
    "Pacific/Chatham", "Pacific/Apia", "Pacific/Kiritimati", "Etc/GMT+12", "Etc/GMT-14",
    "Pacific/Honolulu", "America/Anchorage", "America/Nome", "America/Los_Angeles",
    "America/Denver", "America/Chicago", "America/New_York", "America/Caracas",
    "America/St_Johns", "America/Sao_Paulo", "America/Santiago", "America/Argentina/Buenos_Aires",
)
STRATA = ("near_meridian", "anywhere", "dst_window")
STRATUM_WEIGHTS = (0.6, 0.3, 0.1)


@dataclass(frozen=True)
class Sample:
    tz: str
    wall_clock: str          # naive ISO, microseconds
    lon: float
    lat: float
    stratum: str
    fold_choice: str         # "earlier" | "later" (used only if ambiguous)


def _rand_wall_clock(rng: random.Random) -> datetime:
    start = datetime(YEAR_MIN, 1, 1)
    span_us = int((datetime(YEAR_MAX, 12, 31, 23, 59, 59, 999999) - start).total_seconds() * 1e6)
    return start + timedelta(microseconds=rng.randrange(span_us))


@lru_cache(maxsize=None)
def _dst_transitions(tz_name: str, year: int) -> tuple[datetime, ...]:
    """UTC instants at which the zone's offset changes in ``year`` (hour resolution, then minute)."""
    tz = ZoneInfo(tz_name)
    out: list[datetime] = []
    t = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    prev = t.astimezone(tz).utcoffset()
    while t < end:
        nxt = t + timedelta(days=1)
        off = nxt.astimezone(tz).utcoffset()
        if off != prev:
            lo, hi = t, nxt
            while hi - lo > timedelta(minutes=1):
                mid = lo + (hi - lo) / 2
                if mid.astimezone(tz).utcoffset() == prev:
                    lo = mid
                else:
                    hi = mid
            out.append(hi)
            prev = off
        t = nxt
    return tuple(out)


def draw(rng: random.Random) -> Sample:
    stratum = rng.choices(STRATA, weights=STRATUM_WEIGHTS)[0]
    tz_name = rng.choice(ZONES)
    wall = _rand_wall_clock(rng)
    if stratum == "dst_window":
        transitions = _dst_transitions(tz_name, wall.year)
        if transitions:
            edge = rng.choice(transitions)
            # wall-clock within ±90 min of the transition, expressed in the pre-transition offset
            before = (edge - timedelta(seconds=1)).astimezone(ZoneInfo(tz_name))
            wall = (before.replace(tzinfo=None) + timedelta(seconds=1)
                    + timedelta(microseconds=rng.randrange(-90 * 60 * 10**6, 90 * 60 * 10**6)))
        else:
            stratum = "near_meridian"
    if stratum == "anywhere":
        lon = rng.uniform(-180.0, 180.0)
    else:
        off = wall.replace(tzinfo=ZoneInfo(tz_name)).utcoffset() or timedelta(0)
        meridian = off.total_seconds() / 240.0
        lon = max(-180.0, min(180.0, meridian + rng.uniform(-25.0, 25.0)))
    return Sample(
        tz=tz_name,
        wall_clock=wall.isoformat(timespec="microseconds"),
        lon=round(lon, 6),
        lat=round(rng.uniform(-66.0, 66.0), 6),
        stratum=stratum,
        fold_choice=rng.choice(("earlier", "later")),
    )


def oracle(utc: datetime, lon: float) -> tuple[date, float]:
    jd_ut = swe.julday(utc.year, utc.month, utc.day,
                       utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3.6e9)
    r = swe.lmt_to_lat(jd_ut + lon / 360.0, lon)
    jd_lat = r[0] if isinstance(r, tuple) else r
    y, m, d, h = swe.revjul(jd_lat)
    return date(int(y), int(m), int(d)), float(h)


def branch_of(hours: float) -> int:
    return int(((hours + 1.0) % 24.0) // 2.0)


def circ_min(a_h: float, b_h: float) -> float:
    return abs(((a_h - b_h + 12.0) % 24.0) - 12.0) * 60.0


def oracle_edge_distance_min(hours: float) -> float:
    return min(circ_min(hours, float(e)) for e in (0, *range(1, 24, 2)))


def _percentile(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    k = max(0, min(len(sorted_vals) - 1, int(round(q * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def evaluate(sample: Sample) -> dict | None:
    """One sample → result dict, or ``None`` when the wall-clock is rejected
    (nonexistent DST time) exactly as /v2 rejects it."""
    try:
        resolved = resolve_local_instant(sample.wall_clock, sample.tz, ambiguous=sample.fold_choice,
                                         nonexistent="error")
    except LocalTimeError:
        return None
    # independent UTC check: stdlib zoneinfo with the same fold
    naive = datetime.fromisoformat(sample.wall_clock)
    utc_indep = naive.replace(tzinfo=ZoneInfo(sample.tz), fold=resolved.fold).astimezone(timezone.utc)
    ctx = compute_effective_time_context_from_instant(resolved.civil_local, sample.lon)
    o_date, o_hours = oracle(resolved.utc, sample.lon)
    engine_date = resolved.civil_local.date() + timedelta(days=ctx.date_rollover)
    flagged = nearest_tlst_decision_edge(ctx.tlst_hours, day_boundary="midnight").within_eot_tolerance
    flagged_zi = nearest_tlst_decision_edge(ctx.tlst_hours, day_boundary="zi").within_eot_tolerance
    return {
        "status": resolved.status,
        "utc_ok": utc_indep == resolved.utc,
        "delta_min": circ_min(ctx.tlst_hours, o_hours),
        "date_ok": engine_date == o_date,
        "branch_ok": branch_of(ctx.tlst_hours) == branch_of(o_hours),
        "oracle_edge_min": oracle_edge_distance_min(o_hours),
        "engine_flagged": flagged or flagged_zi,
        "tlst_hours": ctx.tlst_hours,
        "oracle_hours": o_hours,
        "rollover": ctx.date_rollover,
    }


def run(seed: int, n: int, tolerance_min: float, max_draws_factor: int = 3) -> dict:
    ephe = os.environ.get("SE_EPHE_PATH")
    if ephe:
        swe.set_ephe_path(ephe)
    rng = random.Random(seed)
    deltas: list[float] = []
    counts = Counter()
    by_tz: Counter = Counter()
    by_decade: Counter = Counter()
    by_stratum: Counter = Counter()
    by_hemisphere: Counter = Counter()
    by_season: Counter = Counter()
    by_lon_sign: Counter = Counter()
    rollovers: Counter = Counter()
    counterexamples: list[dict] = []
    uncertain_examples: list[dict] = []
    draws = 0
    while counts["valid"] < n and draws < n * max_draws_factor:
        draws += 1
        s = draw(rng)
        r = evaluate(s)
        if r is None:
            counts["discarded_nonexistent"] += 1
            continue
        counts["valid"] += 1
        counts[f"local_status_{r['status']}"] += 1
        by_tz[s.tz] += 1
        year = int(s.wall_clock[:4])
        by_decade[f"{year // 10 * 10}s"] += 1
        by_stratum[s.stratum] += 1
        by_hemisphere["south" if s.lat < 0 else "north"] += 1
        month = int(s.wall_clock[5:7])
        by_season["jun_aug" if month in (6, 7, 8) else "dec_feb" if month in (12, 1, 2) else "shoulder"] += 1
        by_lon_sign["negative" if s.lon < 0 else "positive"] += 1
        rollovers[str(r["rollover"])] += 1
        deltas.append(r["delta_min"])
        if not r["utc_ok"]:
            counts["utc_mismatch"] += 1
            counterexamples.append({"kind": "utc_mismatch", **asdict(s), **r})
        if r["delta_min"] > tolerance_min:
            counts["hour_mismatch"] += 1
            counterexamples.append({"kind": "tlst_delta", **asdict(s), **r})
        disagreement = not (r["date_ok"] and r["branch_ok"])
        if r["oracle_edge_min"] <= tolerance_min:
            counts["boundary_uncertain"] += 1
            counts["boundary_uncertain_disagreed" if disagreement else "boundary_uncertain_agreed"] += 1
            if len(uncertain_examples) < 25:
                uncertain_examples.append({**asdict(s), **r})
        else:
            if not r["date_ok"]:
                counts["date_mismatch"] += 1
                counterexamples.append({"kind": "date", **asdict(s), **r})
            if not r["branch_ok"]:
                counts["branch_mismatch"] += 1
                counterexamples.append({"kind": "branch", **asdict(s), **r})
            if r["date_ok"] and r["branch_ok"]:
                counts["proven_agreement"] += 1
        if disagreement and not r["engine_flagged"]:
            counts["unflagged_disagreements"] += 1
            counterexamples.append({"kind": "unflagged_disagreement", **asdict(s), **r})
    deltas.sort()
    violations = sum(counts[k] for k in ("utc_mismatch", "hour_mismatch", "date_mismatch",
                                         "branch_mismatch", "unflagged_disagreements"))
    return {
        "seed": seed,
        "requested_valid": n,
        "valid": counts["valid"],
        "draws": draws,
        "discarded_nonexistent": counts["discarded_nonexistent"],
        "tolerance_min": tolerance_min,
        "engine_tolerance_constant_min": EOT_MODEL_TOLERANCE_MINUTES,
        "max_abs_delta_min": round(deltas[-1], 6) if deltas else None,
        "p99_abs_delta_min": round(_percentile(deltas, 0.99), 6),
        "mean_abs_delta_min": round(sum(deltas) / len(deltas), 6) if deltas else None,
        "counts": {k: counts[k] for k in sorted(counts)},
        "violations": violations,
        "distribution": {
            "by_tz": dict(sorted(by_tz.items())),
            "by_decade": dict(sorted(by_decade.items())),
            "by_stratum": dict(sorted(by_stratum.items())),
            "by_hemisphere": dict(sorted(by_hemisphere.items())),
            "by_season": dict(sorted(by_season.items())),
            "by_lon_sign": dict(sorted(by_lon_sign.items())),
            "tlst_date_rollover": dict(sorted(rollovers.items())),
        },
        "counterexamples": counterexamples,
        "boundary_uncertain_examples": uncertain_examples,
        "ephemeris": {"se_ephe_path_set": bool(ephe), "swisseph_version": str(getattr(swe, "version", "?"))},
    }


def first_valid_samples(seed: int, k: int) -> list[Sample]:
    """The first ``k`` samples of the seeded stream that /v2 accepts (for HTTP spot checks)."""
    rng = random.Random(seed)
    out: list[Sample] = []
    while len(out) < k:
        s = draw(rng)
        if evaluate(s) is not None:
            out.append(s)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--n", type=int, default=5000, help="valid samples to evaluate (default 5000)")
    parser.add_argument("--tolerance", type=float, default=0.1, help="minutes (default 0.1)")
    parser.add_argument("--json", type=str, default=None, help="write the full report to this path")
    args = parser.parse_args(argv)
    report = run(args.seed, args.n, args.tolerance)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    c = report["counts"]
    print(f"seed={report['seed']} valid={report['valid']}/{report['requested_valid']} draws={report['draws']} "
          f"discarded_nonexistent={report['discarded_nonexistent']}")
    print(f"max|Δ|={report['max_abs_delta_min']} min  p99={report['p99_abs_delta_min']} min  "
          f"mean={report['mean_abs_delta_min']} min  (tolerance {args.tolerance} min)")
    print(f"proven_agreement={c.get('proven_agreement', 0)} boundary_uncertain={c.get('boundary_uncertain', 0)} "
          f"(agreed {c.get('boundary_uncertain_agreed', 0)}, disagreed {c.get('boundary_uncertain_disagreed', 0)})")
    print(f"hour_mismatch={c.get('hour_mismatch', 0)} date_mismatch={c.get('date_mismatch', 0)} "
          f"branch_mismatch={c.get('branch_mismatch', 0)} utc_mismatch={c.get('utc_mismatch', 0)} "
          f"unflagged_disagreements={c.get('unflagged_disagreements', 0)} violations={report['violations']}")
    print(f"local status: ok={c.get('local_status_ok', 0)} ambiguous={c.get('local_status_ambiguous', 0)}")
    print(f"rollover distribution: {report['distribution']['tlst_date_rollover']}")
    short = report["valid"] < report["requested_valid"]
    if short:
        print("FAIL: fewer valid samples than requested", file=sys.stderr)
    return 1 if (report["violations"] or short) else 0


if __name__ == "__main__":
    sys.exit(main())
