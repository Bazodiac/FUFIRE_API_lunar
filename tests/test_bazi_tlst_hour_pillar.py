"""FBP-02-005 / FBP-TST-003 — TLST-derived hour pillar.

When a request opts into ``time_standard="TLST"``, the hour pillar
must be derived from True Local Solar Time (LMT + equation_of_time)
rather than from civil clock time. Concretely:

- At the timezone's standard meridian (e.g. 0° for UTC, 15° for CET),
  TLST equals LMT within ≈ 17 min of EoT. The hour-branch can still
  differ at the edge of a 2-hour Zi/Chou/Yin/… bin.
- The *only* legitimate source of a TLST-vs-LMT hour-branch divergence
  is the equation of time. The longitude correction is shared by both.

Boundary case (reference values from Swiss Ephemeris, see
``tests/fixtures/tlst_reference_corpus_v1.json`` case ``madrid_feb_0220_cet``):
Madrid 2024-02-22 02:20 CET (UTC+1) →
  UTC 01:20; LMT = UTC − 14.8 min = 01:05 → hour branch 1 (Chou)
  TLST = LMT + EoT(−13.6 min) = 00:51 → hour branch 0 (Zi)
So the hour pillar must differ between the LMT and TLST standards.

History: until FBP-TST-003 this fixture was ``02:00`` and "diverged" only
because ``tlst_hours`` added the longitude correction to the civil
wall-clock (DEV-2026-009). With correct math 02:00 gives LMT 00:45 and
TLST 00:31 — both Zi — so that fixture is now a *non*-divergence control.

The ``/calculate/bazi`` response shape returns each pillar as a dict
``{"stamm": "...", "zweig": "...", "tier": "...", "element": "..."}``,
so the assertions compare those dicts directly.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from bazi_engine.app import app

client = TestClient(app)


def _post(payload: dict) -> dict:
    r = client.post("/calculate/bazi", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


# Madrid: longitude ≈ -3.70°, in CET (standard meridian 15°), so
# LMT trails CIVIL by ~75 min and TLST trails LMT by EoT minutes.
_MADRID_BASE = {
    "tz": "Europe/Madrid",
    "lon": -3.7038,
    "lat": 40.4168,
    "boundary": "midnight",
}


def test_madrid_0220_tlst_hour_branch_differs_from_lmt_by_eot():
    """Madrid 2024-02-22 02:20 CET: LMT 01:05 (Chou) vs TLST 00:51 (Zi)."""
    payload = {**_MADRID_BASE, "date": "2024-02-22T02:20:00"}
    tlst = _post({**payload, "standard": "TLST"})
    lmt = _post({**payload, "standard": "LMT"})
    assert lmt["pillars"]["hour"]["zweig"] == "Chou", lmt["pillars"]["hour"]
    assert tlst["pillars"]["hour"]["zweig"] == "Zi", tlst["pillars"]["hour"]
    assert tlst["pillars"]["hour"] != lmt["pillars"]["hour"]


def test_madrid_0200_tlst_and_lmt_agree_control():
    """Madrid 2024-02-22 02:00 CET: LMT 00:45 and TLST 00:31 are both Zi.
    Guards against the DEV-2026-009 regression, where the zone offset leaked
    into TLST and pushed it to 01:31 (Chou)."""
    payload = {**_MADRID_BASE, "date": "2024-02-22T02:00:00"}
    tlst = _post({**payload, "standard": "TLST"})
    lmt = _post({**payload, "standard": "LMT"})
    assert lmt["pillars"]["hour"]["zweig"] == "Zi"
    assert tlst["pillars"]["hour"] == lmt["pillars"]["hour"]
    tr = tlst["derivation_trace"]["time_resolution"]
    assert 0.5 <= tr["tlst_hours"] < 0.6, tr


def test_hannover_user_case_tlst_hour_is_wei():
    """The reported case: 15:44 MESZ, Hannover → TLST 14:17 → Wei (not Shen)."""
    payload = {"date": "1990-07-15T15:44:00", "tz": "Europe/Berlin", "lon": 9.732, "lat": 52.3759}
    tlst = _post({**payload, "standard": "TLST"})
    lmt = _post({**payload, "standard": "LMT"})
    assert tlst["pillars"]["hour"]["zweig"] == "Wei", tlst["pillars"]["hour"]
    assert tlst["pillars"]["hour"] == lmt["pillars"]["hour"]
    tr = tlst["derivation_trace"]["time_resolution"]
    assert abs(tr["tlst_hours"] - 14.2858) < 0.02, tr


def test_civil_request_unchanged_after_phase2():
    """A CIVIL request must produce the same hour pillar in Phase 2 as
    it did pre-FBP-02-005. Regression guard on the legacy default path.

    02:00 civil on Feb 22 in Europe/Madrid: hour=2 →
    branch_index = (2+1)//2 % 12 = 1 (Chou).
    """
    civil = _post({**_MADRID_BASE, "date": "2024-02-22T02:00:00", "standard": "CIVIL"})
    assert civil["pillars"]["hour"]["zweig"] == "Chou", (
        f"Civil hour pillar at 02:00 must have zweig=Chou (branch=1); got "
        f"{civil['pillars']['hour']!r}"
    )


def test_tlst_request_no_longer_clamped_in_trace():
    """Post-FBP-02-005 the trace must record time_standard_used == TLST
    for a TLST request, not LMT (which was the Phase-1 clamp signature)."""
    r = client.post("/calculate/bazi", json={**_MADRID_BASE, "date": "2024-02-22T02:20:00", "standard": "TLST"})
    assert r.status_code == 200, r.text
    hour_trace = r.json()["derivation_trace"]["hour"]
    assert hour_trace["time_standard_requested"] == "TLST"
    assert hour_trace["time_standard_used"] == "TLST", (
        "Phase-2 must remove the router clamp; trace should show "
        "time_standard_used=TLST, not LMT."
    )
