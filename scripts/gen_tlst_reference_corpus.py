"""Generate the True-Local-Solar-Time (TLST) reference corpus.

Writes ``tests/fixtures/tlst_reference_corpus_v1.json``: for a fixed set
of birth inputs ``(civil local ISO, IANA zone, longitude, fold)`` it
records the **reference** decomposition into UTC, Local Mean Time (LMT),
equation of time (EoT) and apparent solar time (TLST), computed with
Swiss Ephemeris as an independent oracle:

- ``swe.time_equ(jd_ut)``  → equation of time at the exact instant
  (apparent − mean, in days; stored here in minutes).
- ``swe.lmt_to_lat(jd_lmt, geolon)`` → local apparent time from local
  mean time (the definitional TLST = LMT + EoT).

Nothing in this script touches ``bazi_engine.time_context`` or
``bazi_engine.solar_time``; the corpus must stay independent of the code
under test so ``tests/test_tlst_reference_corpus.py`` can diff the
engine against it. See ``docs/plans/2026-10-15-true-solar-time-remediation.md``
(DEV-2026-009 … DEV-2026-012).

Usage::

    python scripts/gen_tlst_reference_corpus.py              # writes default path
    python scripts/gen_tlst_reference_corpus.py --check      # exits 1 on drift

Both Swiss Ephemeris modes (SWIEPH files / Moshier fallback) yield the
same EoT to better than 1e-3 min, so the corpus is backend-agnostic; the
file still records the mode and lock id it was generated under.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import swisseph as swe

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "tlst_reference_corpus_v1.json"
LOCK_PATH = REPO_ROOT / "ephemeris.lock.json"

# (id, civil_local_iso, tz, longitude_deg, fold, note)
# Only **append** cases; never re-order or edit existing ids (the test
# file references ids by name).
CASES: list[tuple[str, str, str, float, int, str]] = [
    ("hannover_1990_mesz_1544", "1990-07-15T15:44:00", "Europe/Berlin", 9.7320, 0,
     "User-reported case: 15:44 MESZ (UTC+2), Hannover. Reference TLST 14:17 (Wei)."),
    ("berlin_doc_example_2024_cet_1430", "2024-02-10T14:30:00", "Europe/Berlin", 13.4050, 0,
     "docs/fusion/04_solar_time.md worked example (TST ≈ 14:09 WSZ)."),
    ("berlin_summer_noon_cest", "2024-06-21T12:00:00", "Europe/Berlin", 13.4050, 0,
     "Solstice, CEST (UTC+2)."),
    ("madrid_feb_0200_cet", "2024-02-22T02:00:00", "Europe/Madrid", -3.7038, 0,
     "Fixture of tests/test_bazi_tlst_hour_pillar.py. Reference TLST 00:31 (Zi) == LMT branch (Zi)."),
    ("madrid_feb_0220_cet", "2024-02-22T02:20:00", "Europe/Madrid", -3.7038, 0,
     "Genuine EoT divergence: LMT 01:05 (Chou) vs TLST 00:51 (Zi)."),
    ("madrid_feb_0030_cet_rollover_minus1", "2024-02-22T00:30:00", "Europe/Madrid", -3.7038, 0,
     "TLST falls on the PREVIOUS civil date (23:01 on 02-21)."),
    ("berlin_gt6_2330_cet", "2024-02-15T23:30:00", "Europe/Berlin", 13.4050, 0,
     "GT6 fixture (tests/test_bazi_trace_endpoint.py). Reference TLST 23:09 → late-Zi rollover fires."),
    ("utc_lon0_identity", "2024-09-22T18:30:00", "UTC", 0.0, 0,
     "Zone offset 0, longitude 0: TLST = civil + EoT."),
    ("utc_lon30_2330_rollover_plus1", "2024-06-15T23:30:00", "UTC", 30.0, 0,
     "Fixture of tests/test_bazi_time_context.py::test_date_rollover_when_tlst_crosses_midnight."),
    ("auckland_nzdt_utc13", "2024-01-10T09:15:00", "Pacific/Auckland", 174.7633, 0,
     "UTC+13 (NZDT): the largest common zone offset."),
    ("kathmandu_utc0545", "2024-05-05T06:10:00", "Asia/Kathmandu", 85.3240, 0,
     "Non-integer zone offset (+5:45)."),
    ("st_johns_nst_minus0330", "2024-01-20T07:05:00", "America/St_Johns", -52.7126, 0,
     "Negative non-integer zone offset (-3:30)."),
    ("chengdu_cst_west_of_meridian", "2024-03-30T08:00:00", "Asia/Shanghai", 104.0665, 0,
     "China Standard Time (meridian 120°E) ~64 min ahead of local mean time."),
    ("new_york_est_winter", "2024-02-14T06:40:00", "America/New_York", -74.0060, 0,
     "EST, near annual EoT minimum."),
    ("los_angeles_pdt_summer", "2024-07-04T21:50:00", "America/Los_Angeles", -118.2437, 0,
     "PDT (UTC-7), late evening → TLST next-hour bin check."),
    ("tehran_irst_utc0330", "2024-11-02T13:00:00", "Asia/Tehran", 51.3890, 0,
     "UTC+3:30, near annual EoT maximum."),
    ("lisbon_wet_winter", "2024-12-21T16:30:00", "Europe/Lisbon", -9.1393, 0,
     "Zone offset 0 but longitude -9° → TLST ≠ civil although tz==UTC."),
    ("berlin_dst_fallback_fold0", "2024-10-27T02:30:00", "Europe/Berlin", 13.4050, 0,
     "Ambiguous local time, first occurrence (CEST, UTC+2)."),
    ("berlin_dst_fallback_fold1", "2024-10-27T02:30:00", "Europe/Berlin", 13.4050, 1,
     "Ambiguous local time, second occurrence (CET, UTC+1) — differs from fold0 by exactly 1 h."),
    ("london_bst_1950", "1950-06-15T10:00:00", "Europe/London", -0.1278, 0,
     "Historical BST (UTC+1)."),
    ("singapore_1965_utc0730", "1965-08-09T10:00:00", "Asia/Singapore", 103.8500, 0,
     "Historical +7:30 zone."),
]


def _jd_ut(dt_utc: datetime) -> float:
    frac = dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0 + dt_utc.microsecond / 3.6e9
    return float(swe.julday(dt_utc.year, dt_utc.month, dt_utc.day, frac))


def _scalar(value: Any) -> float:
    """pyswisseph returns tuples for some calls; normalise to float."""
    return float(value[0]) if isinstance(value, tuple) else float(value)


def _jd_to_civil(jd: float) -> tuple[str, float]:
    y, m, d, h = swe.revjul(jd)
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}", float(h)


def _hour_branch_index(hours: float) -> int:
    """Spec rule (bafe/mapping.py): floor(((h + 1) mod 24) / 2), HALF_OPEN bins."""
    return int(((hours + 1.0) % 24.0) // 2.0) % 12


def reference_case(case_id: str, iso: str, tz: str, lon: float, fold: int, note: str) -> dict[str, Any]:
    civil = datetime.fromisoformat(iso).replace(tzinfo=ZoneInfo(tz), fold=fold)
    offset = civil.utcoffset()
    assert offset is not None
    utc = civil.astimezone(timezone.utc)
    jd_ut = _jd_ut(utc)
    eot_min = _scalar(swe.time_equ(jd_ut)) * 1440.0
    jd_lmt = jd_ut + lon / 360.0
    jd_lat = _scalar(swe.lmt_to_lat(jd_lmt, lon))
    lmt_date, lmt_hours = _jd_to_civil(jd_lmt)
    tlst_date, tlst_hours = _jd_to_civil(jd_lat)
    civil_date = civil.date().isoformat()
    rollover = (datetime.fromisoformat(tlst_date) - datetime.fromisoformat(civil_date)).days
    return {
        "id": case_id,
        "note": note,
        "input": {
            "birth_local_iso": iso,
            "timezone": tz,
            "longitude_deg": lon,
            "fold": fold,
        },
        "reference": {
            "utc_iso": utc.isoformat(),
            "utc_offset_minutes": int(round(offset.total_seconds() / 60.0)),
            "longitude_correction_minutes": round(lon * 4.0, 4),
            "equation_of_time_minutes": round(eot_min, 4),
            "lmt_date": lmt_date,
            "lmt_hours": round(lmt_hours, 6),
            "tlst_date": tlst_date,
            "tlst_hours": round(tlst_hours, 6),
            "tlst_date_rollover_vs_civil": rollover,
            "hour_branch_index_tlst": _hour_branch_index(tlst_hours),
            "hour_branch_index_lmt": _hour_branch_index(lmt_hours),
        },
    }


def _ephemeris_provenance() -> dict[str, Any]:
    ephe_path = os.environ.get("SE_EPHE_PATH")
    lock_id = None
    if LOCK_PATH.exists():
        lock_id = json.loads(LOCK_PATH.read_text(encoding="utf-8")).get("lock_id")
    return {
        "oracle": "pyswisseph swe.time_equ + swe.lmt_to_lat",
        "swisseph_version": str(getattr(swe, "version", "unknown")),
        "se_ephe_path_set": bool(ephe_path),
        "ephemeris_lock_id": lock_id,
        "note": "EoT via Moshier fallback and via SE1 files agree to <1e-3 min; corpus is backend-agnostic.",
    }


def build_corpus() -> dict[str, Any]:
    return {
        "schema": "fufire.tlst_reference_corpus.v1",
        "definition": {
            "lmt": "UTC + longitude_deg * 4 min (east positive)",
            "tlst": "LMT + equation_of_time (apparent - mean)",
            "hour_branch": "floor(((hours + 1) mod 24) / 2), HALF_OPEN 2h bins (Zi = [23, 1))",
        },
        "provenance": _ephemeris_provenance(),
        "cases": [reference_case(*c) for c in CASES],
    }


def _dump(corpus: dict[str, Any]) -> str:
    return json.dumps(corpus, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# SE1 files vs Moshier differ in the 4th decimal of EoT minutes / 6th of
# hours (≈ 6 ms). ``--check`` must not flag that as drift.
_CHECK_TOLERANCE = 1e-3


def _cases_equivalent(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x["id"] != y["id"] or x["input"] != y["input"]:
            return False
        for key, xv in x["reference"].items():
            yv = y["reference"].get(key)
            if isinstance(xv, float) or isinstance(yv, float):
                if abs(float(xv) - float(yv)) > _CHECK_TOLERANCE:
                    return False
            elif xv != yv:
                return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="diff against on-disk corpus; exit 1 on drift")
    args = parser.parse_args(argv)
    corpus = build_corpus()
    text = _dump(corpus)
    if args.check:
        if not args.out.exists():
            print(f"missing corpus: {args.out}", file=sys.stderr)
            return 1
        on_disk = json.loads(args.out.read_text(encoding="utf-8"))
        if not _cases_equivalent(on_disk.get("cases", []), corpus["cases"]):
            print("TLST reference corpus drift detected (cases differ)", file=sys.stderr)
            return 1
        print("OK: TLST reference corpus unchanged")
        return 0
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out} ({len(corpus['cases'])} cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
