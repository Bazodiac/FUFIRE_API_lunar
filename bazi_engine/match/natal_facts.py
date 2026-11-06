"""Additional *observations* for a natal chart; not classical strength rules.

This module deliberately answers only whether the day master's exact stem,
or the other stem of its Wu-Xing phase, occurs among *hidden* stems.
Those observations help a future sourced Tong Gen / Day Master Strength
calculation, but do not themselves establish a classical root, strength
band, seasonal state, or Yong Shen (MISSING-003).

Pure Level-4 code: no HTTP, time system, or external I/O.
"""
from __future__ import annotations

from typing import Any, Dict, Sequence

from .normalize import stem_element
from .types import StemSource, WuxingLedgerEntry


def hidden_stem_affinities(
    day_master: str,
    ledger: Sequence[WuxingLedgerEntry],
    *,
    birth_time_known: bool,
) -> Dict[str, Any]:
    """Emit traceable, unscored, mutually exclusive hidden-stem matches.

    Exact identity and same-phase/other-stem are separated. Visible stems
    never count as hidden occurrences. Unknown birth time makes only
    *hour*-pillar occurrences provisional. This is NOT a Tong Gen verdict.
    """
    master_phase = stem_element(day_master)  # validates the input stem
    exact = []
    same_phase_other = []
    for entry in ledger:
        if entry.source is StemSource.VISIBLE:
            continue
        actual_phase = stem_element(entry.stem)
        if entry.element != actual_phase:
            raise ValueError(
                f"Hidden stem ledger element mismatch for {entry.stem}: "
                f"{entry.element!r} != {actual_phase!r}"
            )
        if actual_phase != master_phase:
            continue
        occurrence = {
            "pillar": entry.pillar,
            "stem": entry.stem,
            "qi": entry.source.value.removeprefix("hidden_"),
            "provisional": entry.pillar == "hour" and not birth_time_known,
        }
        if entry.stem == day_master:
            exact.append(occurrence)
        else:
            same_phase_other.append(occurrence)
    return {
        "source_status": "CALCULATED",
        "exact_day_master_stem": exact,
        "same_phase_other_stem": same_phase_other,
        "tong_gen_assessment": {
            "source_status": "NEEDS_DOMAIN_REVIEW",
            "blocked_by": "MISSING-003",
        },
    }
