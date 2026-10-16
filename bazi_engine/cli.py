from __future__ import annotations

import argparse
import sys

from .bazi import compute_bazi
from .types import BaziInput


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate BaZi (Four Pillars) chart.")
    parser.add_argument("date", help="Local ISO8601 date, e.g. 2024-02-10T14:30:00")
    parser.add_argument("--tz", default="Europe/Berlin", help="Timezone name (default: Europe/Berlin)")
    parser.add_argument("--lon", type=float, default=13.4050, help="Longitude in degrees (default: 13.4050 for Berlin)")
    parser.add_argument("--lat", type=float, default=52.52, help="Latitude in degrees (default: 52.52)")
    parser.add_argument(
        "--standard", choices=["CIVIL", "LMT", "TLST"], default="CIVIL",
        help="Time standard: CIVIL (zone time), LMT (local mean time), TLST (true local solar time; FBP-TST-007) (default: CIVIL)",
    )
    parser.add_argument("--boundary", choices=["midnight", "zi"], default="midnight", help="Day boundary (default: midnight)")
    parser.add_argument("--accuracy", type=float, default=1.0, help="Iteration accuracy in seconds (default: 1.0)")
    parser.add_argument("--strict", action="store_true", default=True, help="Strict local time validation (default: True)")
    parser.add_argument("--no-strict", dest="strict", action="store_false", help="Disable strict local time validation")
    parser.add_argument("--json", action="store_true", help="Output JSON results")

    args = parser.parse_args()

    try:
        inp = BaziInput(
            birth_local=args.date,
            timezone=args.tz,
            longitude_deg=args.lon,
            latitude_deg=args.lat,
            time_standard=args.standard,
            day_boundary=args.boundary,
            accuracy_seconds=args.accuracy,
            strict_local_time=args.strict,
            fold=0,
        )
        res = compute_bazi(inp)
        
        if args.json:
            import json
            data = {
                "pillars": {
                   "year": str(res.pillars.year),
                   "month": str(res.pillars.month),
                   "day": str(res.pillars.day),
                   "hour": str(res.pillars.hour)
                },
                "dates": {
                    "birth_local": res.birth_local_dt.isoformat(),
                    "birth_utc": res.birth_utc_dt.isoformat(),
                    "lichun_local": res.lichun_local_dt.isoformat()
                },
                "solar_terms": len(res.solar_terms_local_dt) if res.solar_terms_local_dt else 0
            }
            print(json.dumps(data, indent=2))
        else:
            print(f"Input: {args.date} {args.tz} ({args.lon}, {args.lat})")
            print(f"Pillars: {res.pillars.year} {res.pillars.month} {res.pillars.day} {res.pillars.hour}")
            print(f"LiChun local: {res.lichun_local_dt.isoformat()}")
            if res.solar_terms_local_dt:
                print(f"Solar terms: {len(res.solar_terms_local_dt)}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
