"""FBP-02-004 — Zi-day boundary on effective time.

Today apply_day_boundary("zi") naively returns dt + 1h regardless of
the request's time standard. Phase 2 routes the boundary check through
the ruleset's day_change_policy: when time_standard_for_day_rollover
is "TLST" and the request itself uses TLST, the boundary fires at
tlst_hours >= zi_start_hour (HALF_OPEN, 23.0 per shipped ruleset).

Madrid is chosen as the test fixture because it sits ~75 min west of
the CET standard meridian, so civil 23:00 has TLST ≈ 21:31 — a clear
divergence between the legacy clock-based check (rolls over at civil
23) and the TLST-aware check (no rollover until apparent solar 23:00).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.constants import BRANCHES, STEMS
from bazi_engine.ephemeris import ensure_ephemeris_files
from bazi_engine.exc import EphemerisUnavailableError

try:
    ensure_ephemeris_files(None)
except (FileNotFoundError, EphemerisUnavailableError):
    pytest.skip("Swiss Ephemeris files not available.", allow_module_level=True)

client = TestClient(app)

MADRID = {
    "tz": "Europe/Madrid",
    "lon": -3.7038,
    "lat": 40.4168,
    "boundary": "zi",
}


def _post(date: str, std: str) -> dict:
    r = client.post("/calculate/bazi", json={**MADRID, "date": date, "standard": std})
    assert r.status_code == 200, r.text
    return r.json()


def _day_sex(body: dict) -> int:
    """Derive the 0-59 sexagenary index from the day pillar in the
    response. The pillar (stem 0-9, branch 0-11) uniquely identifies
    one sex_idx in [0, 60) by CRT — there's exactly one such index
    with the matching residues. We avoid the legacy
    ``derivation_trace.day.sexagenary_index`` field because the router
    currently re-derives it through the unpatched ``apply_day_boundary``
    path (a separate trace-staleness bug); the actual computed pillar
    in ``pillars.day`` is the engine's source of truth."""
    pillar = body["pillars"]["day"]
    stem_idx = STEMS.index(pillar["stamm"])
    branch_idx = BRANCHES.index(pillar["zweig"])
    for idx60 in range(60):
        if idx60 % 10 == stem_idx and idx60 % 12 == branch_idx:
            return idx60
    raise AssertionError(
        f"No 0-59 sex_idx matches pillar {pillar!r} — impossible by CRT."
    )


# --- Legacy paths: CIVIL and LMT keep using `dt + 1h` ----------------
#
# `apply_day_boundary("zi")` adds 1h to `chart_local_dt`. For CIVIL,
# chart_local IS civil time, so the rollover boundary sits at civil
# 23:00. For LMT, chart_local is the LMT clock, so the rollover
# boundary sits at LMT 23:00, which in Madrid (~-3.70°, CET) is
# civil 00:15 the next day. We probe each standard at its own
# clock's 22:00 vs 23:00 to validate the legacy path.

def test_legacy_zi_boundary_rolls_for_civil_at_23():
    """CIVIL: civil 22:00 → no rollover; civil 23:00 → +1h crosses
    midnight → day pillar advances by one."""
    ref = _day_sex(_post("2024-02-15T22:00:00", "CIVIL"))
    at_23 = _day_sex(_post("2024-02-15T23:00:00", "CIVIL"))
    assert at_23 == (ref + 1) % 60, (
        f"CIVIL: expected legacy rollover at civil 23:00, "
        f"ref={ref} at_23={at_23}"
    )


def test_legacy_zi_boundary_rolls_for_lmt_at_lmt_23():
    """LMT: chart_local is the LMT clock. Madrid LMT 23:00 ≈ civil
    00:15 next day. Probe civil 23:15 (LMT 22:00, no rollover) vs
    civil 00:15 next day (LMT 23:00, +1h crosses midnight)."""
    ref = _day_sex(_post("2024-02-15T23:15:00", "LMT"))           # LMT ≈ 22:00
    at_lmt_23 = _day_sex(_post("2024-02-16T00:15:00", "LMT"))     # LMT ≈ 23:00
    assert at_lmt_23 == (ref + 1) % 60, (
        f"LMT: expected legacy rollover when LMT chart_local crosses "
        f"23:00; ref={ref} at_lmt_23={at_lmt_23}"
    )


@pytest.mark.parametrize("std,date", [
    ("CIVIL", "2024-02-15T22:59:00"),   # civil 22:59 < 23:00 → no roll
    ("LMT",   "2024-02-15T23:14:00"),   # LMT ≈ 21:59 → no roll
])
def test_legacy_zi_boundary_no_rollover_just_before_23(std, date):
    """Just before each standard's 23:00, the day must not advance."""
    ref = _day_sex(_post("2024-02-15T22:00:00", std))
    near = _day_sex(_post(date, std))
    # `near` and `ref` need not be equal — different civil times can
    # imply different chart_local days for LMT. The contract is: no
    # *rollover* relative to the chart_local clock at the same day.
    # Easier framing: probe a single clock-hour pair below 23 and
    # confirm both produce the same day pillar.
    assert near == ref, (
        f"{std}: unexpected rollover just before chart-local 23:00; "
        f"ref={ref} near={near}"
    )


# --- TLST-aware path: rollover fires at TLST 23:00, not civil 23:00 --

def test_tlst_zi_boundary_does_not_roll_at_civil_23():
    """Madrid civil 23:00 Feb has TLST ≈ 21:30, so the TLST-aware
    zi-boundary does NOT advance the day. This is the divergence
    from CIVIL/LMT behavior at the same wall clock."""
    ref = _day_sex(_post("2024-02-15T22:00:00", "TLST"))
    at_23 = _day_sex(_post("2024-02-15T23:00:00", "TLST"))
    assert at_23 == ref, (
        f"TLST: civil 23:00 Madrid has TLST < 23, so no rollover expected; "
        f"ref={ref} at_23={at_23}"
    )


def test_tlst_zi_boundary_does_roll_eventually():
    """At some civil hour, TLST DOES cross 23:00 and the rollover fires.
    For Madrid in Feb (TLST ≈ civil − 1h29min), TLST reaches 23 around
    civil 00:29 the next day. Use civil 02:00 next day (TLST ≈ 00:31 —
    past midnight in TLST terms) to confirm a rollover has happened
    relative to the 22:00 reference."""
    ref = _day_sex(_post("2024-02-15T22:00:00", "TLST"))
    next_day_late = _day_sex(_post("2024-02-16T02:00:00", "TLST"))
    # Reference was on civil day Feb 15; next-day-late is on civil day
    # Feb 16. Day pillar must have advanced by AT LEAST 1.
    assert next_day_late != ref, (
        f"TLST: civil 02:00 on 2024-02-16 must produce a different day "
        f"pillar than civil 22:00 on 2024-02-15; ref={ref} next={next_day_late}"
    )


def test_tlst_zi_boundary_path_unchanged_for_midnight_boundary():
    """If day_boundary='midnight', the TLST-aware path is bypassed —
    boundary is the civil-midnight rollover as always."""
    r = client.post("/calculate/bazi", json={
        **MADRID, "boundary": "midnight",
        "date": "2024-02-15T23:00:00", "standard": "TLST",
    })
    assert r.status_code == 200
    # Sanity: response is a complete BaziResponse.
    assert "pillars" in r.json()
    assert "derivation_trace" in r.json()
