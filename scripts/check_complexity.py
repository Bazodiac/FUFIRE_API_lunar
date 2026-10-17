#!/usr/bin/env python3
"""CI gate: reject new functions exceeding the cyclomatic-complexity threshold.

Existing high-complexity functions are grandfathered via BASELINE below.
New functions above MAX_CC will fail the check.

Usage:
    python scripts/check_complexity.py          # default threshold CC>15
    python scripts/check_complexity.py --max 10 # stricter threshold
    python scripts/check_complexity.py --check  # CI mode (non-zero exit on violation)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Grandfathered functions that predate the gate.
# Format: "module:function" -> current CC at time of baselining.
# These are allowed but should be reduced over time.
BASELINE: dict[str, int] = {
    "bazi_engine/bafe/service.py:validate_request": 53,
    "bazi_engine/bafe/refdata.py:evaluate_refdata": 44,
    "bazi_engine/bafe/time_model.py:evaluate_time": 27,
    "bazi_engine/routers/webhooks.py:elevenlabs_chart_webhook": 27,
    "bazi_engine/research/pattern_analysis.py:detect_pipeline_bias": 21,
    "bazi_engine/western.py:compute_western_chart": 21,
    "bazi_engine/research/pattern_analysis.py:kruskal_wallis_test": 20,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Cyclomatic complexity gate")
    parser.add_argument("--max", type=int, default=15, help="Max allowed CC for new code")
    parser.add_argument("--check", action="store_true", help="CI mode: exit 1 on violation")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    try:
        from radon.complexity import cc_visit
    except ImportError:
        print("ERROR: radon not installed. Run: pip install radon>=6.0", file=sys.stderr)
        return 1

    root = Path("bazi_engine")
    violations: list[dict[str, object]] = []
    baseline_improved: list[str] = []

    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        try:
            source = py_file.read_text()
            results = cc_visit(source)
        except Exception as exc:
            print(f"ERROR: failed to analyze {py_file}: {exc}", file=sys.stderr)
            if args.check:
                return 1
            violations.append({
                "file": str(py_file),
                "function": None,
                "line": None,
                "complexity": None,
                "reason": "analysis error",
            })
            continue

        for block in results:
            key = f"{py_file}:{block.name}"
            cc = block.complexity
            baseline_cc = BASELINE.get(key)

            if baseline_cc is not None:
                # Grandfathered: only flag if it got WORSE
                if cc > baseline_cc:
                    violations.append({
                        "file": str(py_file),
                        "function": block.name,
                        "line": block.lineno,
                        "complexity": cc,
                        "baseline": baseline_cc,
                        "reason": "baseline regression",
                    })
                elif cc < baseline_cc:
                    baseline_improved.append(
                        f"  {key}: {baseline_cc} -> {cc} (update baseline!)"
                    )
                continue

            if cc > args.max:
                violations.append({
                    "file": str(py_file),
                    "function": block.name,
                    "line": block.lineno,
                    "complexity": cc,
                    "threshold": args.max,
                    "reason": "exceeds threshold",
                })

    if args.json:
        print(json.dumps({"violations": violations, "ok": len(violations) == 0}))
        return 1 if violations and args.check else 0

    if violations:
        print(f"Complexity violations ({len(violations)}):\n")
        for v in violations:
            reason = v["reason"]
            if reason == "baseline regression":
                print(f"  REGRESSION {v['file']}:{v['line']}  {v['function']}()  "
                      f"CC={v['complexity']} (was {v['baseline']})")
            else:
                print(f"  NEW        {v['file']}:{v['line']}  {v['function']}()  "
                      f"CC={v['complexity']} (max={v['threshold']})")
        print(f"\nRefactor these functions to CC<={args.max} or add to BASELINE if justified.")
    else:
        print(f"Complexity check passed (threshold: {args.max})")

    if baseline_improved:
        print("\nBaseline improvements detected (update BASELINE in this script):")
        for line in baseline_improved:
            print(line)

    if violations and args.check:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
