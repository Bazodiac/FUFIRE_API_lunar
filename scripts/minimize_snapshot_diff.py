"""Reduce a regenerated snapshot set to its *material* changes (owner decision E7).

After ``UPDATE_SNAPSHOTS=1 pytest tests/test_snapshot_stability.py …`` every
float in every snapshot is rewritten with the exact bits this machine
produced. Across machines (CI runner vs. the SHA-verified ephemeris run on a
laptop or container) Swiss Ephemeris output differs in the 8th–10th decimal
(planet speeds, house cusps) — far inside the snapshot tolerance
(``_FLOAT_ATOL = 1e-6`` in ``tests/test_snapshot_stability.py``) but enough
to turn a 2-field change into a 1 200-line diff nobody can review.

This script walks every snapshot file that differs from ``git HEAD``, keeps
the HEAD value wherever the regenerated value is numerically within
``--tolerance`` (default 1e-6, the snapshot tolerance), and writes the
regenerated value only where the change is material (non-numeric, or a
delta above the tolerance). The result still passes the verify run.

Usage::

    python scripts/minimize_snapshot_diff.py                 # both backends
    python scripts/minimize_snapshot_diff.py --backend swieph
    python scripts/minimize_snapshot_diff.py --report        # print changed JSON paths

Regeneration recipe (CLAUDE.md → Testing):

    python scripts/fetch_ephemeris.py --destination /tmp/ephe
    SE_EPHE_PATH=/tmp/ephe UPDATE_SNAPSHOTS=1 pytest -q tests/test_snapshot_stability.py tests/test_snapshot_math_endpoints.py
    python scripts/minimize_snapshot_diff.py --backend swieph --report
    SE_EPHE_PATH=/tmp/ephe pytest -q tests/test_snapshot_stability.py tests/test_snapshot_math_endpoints.py   # verify, no update
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ROOT = REPO_ROOT / "tests" / "snapshots"


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True).stdout


def _changed_files(backend: str) -> list[Path]:
    out = _git("diff", "--name-only", "--", f"tests/snapshots/{backend}")
    return [REPO_ROOT / line for line in out.split() if line.endswith(".json")]


def _head_version(path: Path) -> Any | None:
    rel = path.relative_to(REPO_ROOT).as_posix()
    try:
        return json.loads(_git("show", f"HEAD:{rel}"))
    except subprocess.CalledProcessError:
        return None  # new file: nothing to minimise against


def merge(old: Any, new: Any, tol: float) -> Any:
    """Return ``new`` with every immaterial numeric change replaced by ``old``."""
    if isinstance(old, dict) and isinstance(new, dict) and set(old) == set(new):
        return {k: merge(old[k], new[k], tol) for k in old}
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        return [merge(a, b, tol) for a, b in zip(old, new)]
    if (
        isinstance(old, (int, float)) and isinstance(new, (int, float))
        and not isinstance(old, bool) and not isinstance(new, bool)
    ):
        return new if abs(old - new) > tol else old
    return new


def material_paths(old: Any, new: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(old, dict) and isinstance(new, dict) and set(old) == set(new):
        for k in old:
            out.extend(material_paths(old[k], new[k], f"{path}/{k}"))
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for a, b in zip(old, new):
            out.extend(material_paths(a, b, f"{path}[]"))
    elif old != new:
        out.append(path or "/")
    return out


def minimise(backend: str, tol: float, report: bool) -> int:
    files = _changed_files(backend)
    counter: collections.Counter[str] = collections.Counter()
    for f in files:
        head = _head_version(f)
        raw = f.read_text(encoding="utf-8")
        new = json.loads(raw)
        if head is None:
            continue
        merged = merge(head, new, tol)
        f.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False, sort_keys=True)
            + ("\n" if raw.endswith("\n") else ""),
            encoding="utf-8",
        )
        for p in material_paths(head, merged):
            counter[p] += 1
    print(f"[{backend}] {len(files)} changed file(s) minimised (tolerance {tol:g})")
    if report:
        for p, n in counter.most_common():
            print(f"  {n:4d}  {p}")
    return len(files)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=["swieph", "moseph", "both"], default="both")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument("--report", action="store_true", help="print the material JSON paths that remain changed")
    args = parser.parse_args(argv)
    backends = ["swieph", "moseph"] if args.backend == "both" else [args.backend]
    for b in backends:
        if not (SNAPSHOT_ROOT / b).exists():
            print(f"no snapshot dir for backend {b}", file=sys.stderr)
            return 1
        minimise(b, args.tolerance, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
