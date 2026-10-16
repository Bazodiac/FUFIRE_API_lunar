"""Grid check of the engine's TLST decomposition against the Swiss Ephemeris oracle.

Re-runs the 18 432-sample grid from the remediation plan
(``docs/plans/2026-10-15-true-solar-time-remediation.md`` §1: 16 zones ×
12 dates × 96 quarter-hours) against ``swe.lmt_to_lat`` and reports, per
zone, how many samples disagree on the TLST hour-of-day (> ``--tolerance``
minutes), on the TLST calendar date, or on the 2-hour hour branch. Samples
whose oracle TLST lies within the tolerance of a branch edge are excluded
from the branch count (the branch is undefined there to the EoT's own
precision) and reported separately.

Usage::

    SE_EPHE_PATH=/tmp/ephe python scripts/tlst_grid_check.py            # exit 1 on any violation
    python scripts/tlst_grid_check.py --tolerance 0.1 --json out.json

Read-only; no repository file is touched.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import swisseph as swe

from bazi_engine.bafe.mapping import hour_branch_index_from_tlst
from bazi_engine.time_context import compute_effective_time_context_from_instant

# (zone, longitude east) — same 16 sites as the original repro.
SITES: list[tuple[str, float]] = [
    ("Europe/Berlin", 9.732),          # Hannover, the reported case
    ("Europe/Madrid", -3.7038),
    ("Europe/Lisbon", -9.1393),
    ("UTC", 0.0),
    ("Etc/GMT+12", -179.9),
    ("Pacific/Auckland", 174.7633),
    ("Pacific/Apia", -171.7639),
    ("Pacific/Kiritimati", -157.4),
    ("Asia/Kolkata", 77.209),
    ("Asia/Kathmandu", 85.324),
    ("Asia/Shanghai", 121.4737),
    ("Asia/Tokyo", 139.6917),
    ("America/St_Johns", -52.7126),
    ("America/Chicago", -87.6298),
    ("America/Nome", -165.4064),
    ("America/Sao_Paulo", -46.6333),
]

# 12 civil dates spread over 1950–2030, incl. DST-transition and LiChun-adjacent days.
DATES: list[date] = [
    date(1950, 1, 1), date(1962, 7, 4), date(1975, 11, 2), date(1984, 2, 4),
    date(1990, 7, 15), date(1999, 12, 31), date(2008, 3, 30), date(2016, 10, 30),
    date(2024, 2, 21), date(2024, 6, 16), date(2024, 11, 3), date(2030, 12, 31),
]
QUARTER_HOURS = [timedelta(minutes=15 * k) for k in range(96)]


def oracle(utc: datetime, lon: float) -> tuple[date, float]:
    """Apparent-solar (date, hour-of-day) of a UTC instant at ``lon`` via swisseph."""
    jd_ut = swe.julday(utc.year, utc.month, utc.day,
                       utc.hour + utc.minute / 60 + utc.second / 3600 + utc.microsecond / 3.6e9)
    r = swe.lmt_to_lat(jd_ut + lon / 360.0, lon)
    jd_lat = r[0] if isinstance(r, tuple) else r
    y, m, d, h = swe.revjul(jd_lat)
    return date(int(y), int(m), int(d)), float(h)


def _circ_min(a_h: float, b_h: float) -> float:
    return abs(((a_h - b_h + 12.0) % 24.0) - 12.0) * 60.0


def run(tolerance_min: float) -> dict:
    ephe = os.environ.get("SE_EPHE_PATH")
    if ephe:
        swe.set_ephe_path(ephe)
    per_zone: dict[str, dict[str, int]] = {}
    worst_min = 0.0
    total = 0
    for tz_name, lon in SITES:
        tz = ZoneInfo(tz_name)
        counts = {"samples": 0, "hour_mismatch": 0, "date_mismatch": 0,
                  "branch_mismatch": 0, "branch_edge_excluded": 0}
        for d in DATES:
            for q in QUARTER_HOURS:
                naive = datetime(d.year, d.month, d.day) + q
                for fold in (0, 1):
                    civil = naive.replace(tzinfo=tz, fold=fold)
                    # skip nonexistent wall-clocks; evaluate fold=1 only when ambiguous
                    if civil.utcoffset() != civil.astimezone(timezone.utc).astimezone(tz).utcoffset():
                        continue
                    if fold == 1 and naive.replace(tzinfo=tz, fold=0).utcoffset() == civil.utcoffset():
                        continue
                    utc = civil.astimezone(timezone.utc)
                    ctx = compute_effective_time_context_from_instant(civil, lon)
                    o_date, o_hours = oracle(utc, lon)
                    counts["samples"] += 1
                    total += 1
                    dmin = _circ_min(ctx.tlst_hours, o_hours)
                    worst_min = max(worst_min, dmin)
                    if dmin > tolerance_min:
                        counts["hour_mismatch"] += 1
                    if civil.date() + timedelta(days=ctx.date_rollover) != o_date:
                        counts["date_mismatch"] += 1
                    edge_dist = min(_circ_min(o_hours, e) for e in (1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23))
                    if edge_dist <= tolerance_min:
                        counts["branch_edge_excluded"] += 1
                    elif hour_branch_index_from_tlst(ctx.tlst_hours) != hour_branch_index_from_tlst(o_hours):
                        counts["branch_mismatch"] += 1
        per_zone[tz_name] = counts
    violations = sum(c["hour_mismatch"] + c["date_mismatch"] + c["branch_mismatch"] for c in per_zone.values())
    return {"tolerance_min": tolerance_min, "samples": total, "worst_hour_delta_min": round(worst_min, 4),
            "violations": violations, "per_zone": per_zone,
            "ephemeris": {"se_ephe_path_set": bool(ephe), "swisseph_version": str(getattr(swe, "version", "?"))}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tolerance", type=float, default=0.1, help="minutes (default 0.1)")
    parser.add_argument("--json", type=str, default=None, help="write the full report to this path")
    args = parser.parse_args(argv)
    report = run(args.tolerance)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
    print(f"samples={report['samples']} worst|Δ|={report['worst_hour_delta_min']} min "
          f"violations={report['violations']} (tolerance {args.tolerance} min)")
    for z, c in report["per_zone"].items():
        print(f"  {z:22s} n={c['samples']:5d} hour={c['hour_mismatch']} date={c['date_mismatch']} "
              f"branch={c['branch_mismatch']} edge_excluded={c['branch_edge_excluded']}")
    return 1 if report["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
