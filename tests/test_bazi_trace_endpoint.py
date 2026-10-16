"""ADR-1 (Increment 2) — POST /v1/calculate/bazi/trace + include_trace opt-out.

Phase D of docs/plans/2026-06-05-math-endpoints.md.

These tests lock the ADR-1 design:

* ``include_trace: bool = True`` on ``BaziRequest`` — default keeps the
  current behaviour (trace always present → zero snapshot churn); a
  caller can opt out with ``include_trace=false`` to get
  ``derivation_trace = null``.
* a thin alias route ``POST /calculate/bazi/trace`` (+ ``/v1``) that
  reuses the *same* handler with ``include_trace`` forced True. It does
  **no** new trace math — its trace must deep-equal the trace produced
  by ``/calculate/bazi`` for an identical input.

Anti-mockup contract (GT1 / GT6):
* the alias trace == ``/calculate/bazi`` trace for the same input;
* the trace's pillars == ``compute_bazi(inp).pillars`` (engine truth);
* only the REAL trace fields are exposed
  ``{year, month, day, hour, time_resolution, provenance_ids}`` — the
  PRD fictions (``seasonal_strength``, ``five_tigers_step``,
  ``five_rats_step``, ``late_rat_correction``, ``hidden_stems``) are
  absent.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.bazi import compute_bazi
from bazi_engine.constants import BRANCHES, STEMS
from bazi_engine.time_utils import resolve_local_iso
from bazi_engine.types import BaziInput

client = TestClient(app)

PAYLOAD = {
    "date": "2024-02-10T14:30:00",
    "tz": "Europe/Berlin",
    "lon": 13.405,
    "lat": 52.52,
}

# PRD field-name fictions that DO NOT EXIST in the real trace (GT1).
# The endpoint must never silently invent these.
PRD_FICTIONS = (
    "seasonal_strength",
    "five_tigers_step",
    "five_rats_step",
    "late_rat_correction",
    "hidden_stems",
)

REAL_TRACE_KEYS = {
    "year", "month", "day", "hour", "time_resolution", "provenance_ids",
}


def _ephemeris_available() -> bool:
    return client.post("/calculate/bazi", json=PAYLOAD).status_code == 200


_HAS_EPHEMERIS = _ephemeris_available()
_skip_no_ephe = pytest.mark.skipif(
    not _HAS_EPHEMERIS, reason="Swiss Ephemeris files not available"
)


def _input_from_payload(payload: dict) -> BaziInput:
    """Mirror the router's BaziRequest → BaziInput mapping so a test can
    call ``compute_bazi`` with exactly what the endpoint computed."""
    dt_local, _ = resolve_local_iso(
        payload["date"],
        payload.get("tz", "Europe/Berlin"),
        ambiguous=payload.get("ambiguousTime", "earlier"),
        nonexistent=payload.get("nonexistentTime", "error"),
    )
    resolved_naive = dt_local.replace(tzinfo=None).isoformat()
    fold = 0 if payload.get("ambiguousTime", "earlier") == "earlier" else 1
    return BaziInput(
        birth_local=resolved_naive,
        timezone=payload.get("tz", "Europe/Berlin"),
        longitude_deg=payload.get("lon", 13.405),
        latitude_deg=payload.get("lat", 52.52),
        time_standard=payload.get("standard", "CIVIL"),
        day_boundary=payload.get("boundary", "midnight"),
        strict_local_time=True,
        fold=fold,
    )


# ── D1: include_trace opt-out ────────────────────────────────────────────────

@_skip_no_ephe
def test_include_trace_false_omits_trace():
    """include_trace=False → derivation_trace is None; omitted/default →
    trace present (backward-compatible)."""
    r_off = client.post("/calculate/bazi", json={**PAYLOAD, "include_trace": False})
    assert r_off.status_code == 200, r_off.text
    assert r_off.json()["derivation_trace"] is None

    # Default (omitted) — backward-compat: trace still present.
    r_default = client.post("/calculate/bazi", json=PAYLOAD)
    assert r_default.status_code == 200, r_default.text
    assert r_default.json()["derivation_trace"] is not None

    # Explicit True — same as default.
    r_on = client.post("/calculate/bazi", json={**PAYLOAD, "include_trace": True})
    assert r_on.status_code == 200, r_on.text
    assert r_on.json()["derivation_trace"] is not None


# ── D2: alias route deep-equals existing trace ───────────────────────────────

@_skip_no_ephe
def test_trace_alias_route_matches_existing():
    """/v1/calculate/bazi/trace deep-equals the derivation_trace from
    /v1/calculate/bazi for identical input (no new trace math)."""
    base = client.post("/v1/calculate/bazi", json=PAYLOAD)
    alias = client.post("/v1/calculate/bazi/trace", json=PAYLOAD)
    assert base.status_code == 200, base.text
    assert alias.status_code == 200, alias.text

    base_trace = base.json()["derivation_trace"]
    alias_trace = alias.json()["derivation_trace"]
    assert alias_trace is not None
    assert alias_trace == base_trace


@_skip_no_ephe
def test_trace_alias_forces_trace_even_if_false_requested():
    """The alias route forces include_trace True — passing False in the
    body must NOT suppress the trace (the alias's contract is to always
    return it)."""
    alias = client.post(
        "/v1/calculate/bazi/trace", json={**PAYLOAD, "include_trace": False}
    )
    assert alias.status_code == 200, alias.text
    assert alias.json()["derivation_trace"] is not None


@_skip_no_ephe
def test_trace_alias_bare_route_present():
    """Both bare and /v1 alias routes exist."""
    bare = client.post("/calculate/bazi/trace", json=PAYLOAD)
    assert bare.status_code == 200, bare.text
    assert bare.json()["derivation_trace"] is not None


# ── D3: real fields, not PRD fictions ────────────────────────────────────────

@_skip_no_ephe
def test_trace_exposes_real_fields():
    """Assert the REAL trace keys exist and that PRD fictions are absent
    (no silent faking)."""
    trace = client.post("/v1/calculate/bazi/trace", json=PAYLOAD).json()["derivation_trace"]
    assert set(trace.keys()) == REAL_TRACE_KEYS

    # The PRD fictions must not appear anywhere in the trace (top-level or
    # nested in any sub-block).
    flat_keys = set(trace.keys())
    for sub in trace.values():
        if isinstance(sub, dict):
            flat_keys |= set(sub.keys())
    for fiction in PRD_FICTIONS:
        assert fiction not in flat_keys, (
            f"PRD fiction {fiction!r} leaked into the trace — the real "
            f"trace shape is {sorted(REAL_TRACE_KEYS)}"
        )


# ── pillar consistency: trace day/hour evidence == compute_bazi ──────────────

@_skip_no_ephe
def test_trace_pillars_match_compute_bazi():
    """The trace's pillar evidence must equal compute_bazi(inp).pillars
    (engine truth) for the same input — anti-mockup."""
    resp = client.post("/v1/calculate/bazi/trace", json=PAYLOAD).json()
    trace = resp["derivation_trace"]

    inp = _input_from_payload(PAYLOAD)
    res = compute_bazi(inp)

    # Year/month/hour pillars: response `pillars` block mirrors the trace's
    # source result; assert the response's pillars equal compute_bazi's.
    pillars = resp["pillars"]
    assert STEMS.index(pillars["year"]["stamm"]) == res.pillars.year.stem_index
    assert BRANCHES.index(pillars["year"]["zweig"]) == res.pillars.year.branch_index
    assert STEMS.index(pillars["month"]["stamm"]) == res.pillars.month.stem_index
    assert BRANCHES.index(pillars["month"]["zweig"]) == res.pillars.month.branch_index
    assert STEMS.index(pillars["day"]["stamm"]) == res.pillars.day.stem_index
    assert BRANCHES.index(pillars["day"]["zweig"]) == res.pillars.day.branch_index
    assert STEMS.index(pillars["hour"]["stamm"]) == res.pillars.hour.stem_index
    assert BRANCHES.index(pillars["hour"]["zweig"]) == res.pillars.hour.branch_index

    # Trace day evidence: the day master stem must equal the computed day
    # pillar's stem (engine truth). This is the field GT6 warns about; the
    # midnight-boundary CIVIL fixture above does NOT hit the late-Zi+TLST
    # corner, so trace and pillar agree.
    assert trace["day"]["day_master_stem"] == STEMS[res.pillars.day.stem_index]
    assert trace["month"]["month_branch_index"] == res.pillars.month.branch_index


# ── late-Zi vs midnight ──────────────────────────────────────────────────────
#
# GT6: _build_derivation_trace re-derives the day via the LEGACY
# apply_day_boundary (naive +1h for "zi"), which can disagree with
# compute_bazi's TLST-aware late-Zi rollover. To avoid that corner we use
# CIVIL (not TLST): for CIVIL, chart_local IS civil time, so the legacy
# zi-boundary fires at civil 23:00 and trace/pillar agree. We assert the
# documented engine behaviour via the computed pillar (engine source of
# truth), and confirm the trace inherits the same decision honestly.

@_skip_no_ephe
def test_late_zi_vs_midnight():
    """23:30 birth, CIVIL standard:
    * boundary='zi'  → +1h crosses midnight → day pillar advances;
    * boundary='midnight' → no advance.
    Assert against the engine's computed pillar (source of truth), and
    confirm the trace's JDN reflects the same rollover decision (CIVIL
    avoids the GT6 late-Zi+TLST corner)."""
    base = {
        "date": "2024-02-15T23:30:00",
        "tz": "Europe/Berlin",
        "lon": 13.405,
        "lat": 52.52,
        "standard": "CIVIL",
    }

    midnight = client.post(
        "/v1/calculate/bazi/trace", json={**base, "boundary": "midnight"}
    ).json()
    zi = client.post(
        "/v1/calculate/bazi/trace", json={**base, "boundary": "zi"}
    ).json()

    def _day_sex(body: dict) -> int:
        p = body["pillars"]["day"]
        s, b = STEMS.index(p["stamm"]), BRANCHES.index(p["zweig"])
        for idx in range(60):
            if idx % 10 == s and idx % 12 == b:
                return idx
        raise AssertionError("impossible by CRT")

    mid_sex = _day_sex(midnight)
    zi_sex = _day_sex(zi)

    # Engine truth: zi-boundary at civil 23:30 advances the day by one.
    assert zi_sex == (mid_sex + 1) % 60, (
        f"CIVIL zi-boundary at 23:30 must advance the day pillar; "
        f"midnight={mid_sex} zi={zi_sex}"
    )

    # Trace inherits the same decision honestly: the zi-trace JDN is one
    # greater than the midnight-trace JDN (legacy apply_day_boundary +1h
    # crosses midnight for CIVIL — trace and pillar agree here).
    assert (
        zi["derivation_trace"]["day"]["julian_day_number"]
        == midnight["derivation_trace"]["day"]["julian_day_number"] + 1
    )


# ── GT6: TLST+zi late-Zi trace/pillar consistency (resolved, FBP-TST-003) ───
#
# _build_derivation_trace used to re-derive the day via the legacy
# apply_day_boundary (+1h) while compute_bazi applied the TLST-aware zi
# rollover, so derivation_trace.day could be one day off from the headline
# pillar. The trace now reads BaziResult.chart_day_dt (the engine's own
# decision); this test guards that they can never diverge again.

@_skip_no_ephe
def test_trace_day_pillar_matches_headline_tlst_zi():
    """GT6 (resolved): for standard=TLST + boundary=zi at the 23:30 late-Zi
    rollover (Berlin CET → TLST 23:09, rollover fires), the trace's day
    sexagenary index must equal the headline day pillar's sexagenary index."""
    payload = {
        "date": "2024-02-15T23:30:00",
        "tz": "Europe/Berlin",
        "lon": 13.405,
        "lat": 52.52,
        "standard": "TLST",
        "boundary": "zi",
    }
    body = client.post("/v1/calculate/bazi/trace", json=payload).json()

    # Headline day pillar → sexagenary index (engine source of truth).
    p = body["pillars"]["day"]
    s, b = STEMS.index(p["stamm"]), BRANCHES.index(p["zweig"])
    headline_sex_idx = next(
        idx for idx in range(60) if idx % 10 == s and idx % 12 == b
    )

    # Trace-derived day sexagenary index (legacy apply_day_boundary path).
    trace_sex_idx = body["derivation_trace"]["day"]["sexagenary_index"]

    # The transparency trace must not contradict the headline result.
    assert trace_sex_idx == headline_sex_idx, (
        f"GT6: trace day sexagenary index {trace_sex_idx} diverges from "
        f"headline day pillar index {headline_sex_idx} (TLST+zi late-Zi)"
    )


# ── regression: default /calculate/bazi response unchanged ───────────────────

@_skip_no_ephe
def test_default_response_still_includes_trace():
    """Backward-compat guard duplicated from the v1 regression suite: the
    default /calculate/bazi response (no include_trace) keeps the trace."""
    r = client.post("/calculate/bazi", json=PAYLOAD)
    assert r.status_code == 200
    assert r.json()["derivation_trace"] is not None
    assert set(r.json()["derivation_trace"].keys()) == REAL_TRACE_KEYS
