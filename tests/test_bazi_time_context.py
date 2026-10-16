"""FBP-01-002 / FBP-01-006 — EffectiveTimeContext spec.

Properties enforced here:
- civil, utc are tz-aware datetimes.
- lmt_local is a tz-aware datetime in a *constant-offset* zone derived
  from longitude (NOT IANA, NOT DST-sensitive).
- tlst_hours is a float in [0, 24).
- date_rollover is the integer day shift relative to civil local date.
- TLST is NOT modeled as a tzinfo — there is no ``tlst_local`` field
  with a TLST tzinfo (FBP-01-006).
- TLST is computed on the UTC axis (``UTC + lon·4 min + EoT``), is
  invariant under zone relabeling and honours the DST fold
  (FBP-TST-002 / FBP-TST-003, DEV-2026-009 / DEV-2026-010).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from bazi_engine.time_context import (
    compute_effective_time_context,
)


def test_civil_and_utc_are_tz_aware():
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    assert ctx.civil_local.tzinfo is not None
    assert ctx.utc.tzinfo == timezone.utc


def test_lmt_uses_longitude_offset_not_iana():
    """LMT is mean solar time at the given longitude (4 min/° east)."""
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    expected_offset_min = 13.4050 * 4  # 53.62
    actual_offset_min = ctx.lmt_local.utcoffset().total_seconds() / 60
    assert math.isclose(actual_offset_min, expected_offset_min, abs_tol=0.1)


def test_tlst_is_not_a_tzinfo():
    """Stored as float hours + day offset, not as a datetime with tlst tzinfo."""
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    assert isinstance(ctx.tlst_hours, float)
    assert 0.0 <= ctx.tlst_hours < 24.0
    assert not hasattr(ctx, "tlst_local"), (
        "TLST must not be modeled as a tzinfo. See FBP-01-006."
    )


def test_eot_minutes_matches_solar_time_module():
    """EoT must come from solar_time.equation_of_time, not be re-derived."""
    from bazi_engine.solar_time import equation_of_time
    ctx = compute_effective_time_context(
        birth_local_iso="2024-06-21T12:00:00",
        tz_name="UTC",
        longitude_deg=0.0,
    )
    day_of_year = 173  # June 21
    assert math.isclose(
        ctx.eot_minutes, equation_of_time(day_of_year), abs_tol=0.5
    )


def test_tlst_formula_is_utc_based():
    """FBP-TST-003 / DEV-2026-009: TLST = UTC + longitude·4 min + EoT.

    History: this test used to pin the *civil*-based inline formula of the
    pre-Phase-1 ``/calculate/tst`` endpoint (``civil + lon/15 + EoT``), which
    omitted the zone offset and was wrong by exactly that offset for every
    non-UTC zone. It now pins the definition from
    ``docs/fusion/04_solar_time.md``.
    """
    from bazi_engine.solar_time import equation_of_time
    iso = "2024-06-21T12:00:00"
    tz = "Europe/Berlin"   # CEST, UTC+2
    lon = 13.4050

    ctx = compute_effective_time_context(iso, tz, lon)
    civil_dt = datetime.fromisoformat(iso)
    utc_hours = (civil_dt.hour + civil_dt.minute / 60 + civil_dt.second / 3600) - 2.0
    delta_t_long = lon * 4 / 60
    E_t = equation_of_time(civil_dt.timetuple().tm_yday) / 60
    expected = (utc_hours + delta_t_long + E_t) % 24
    assert math.isclose(ctx.tlst_hours, expected, abs_tol=1e-3), (
        f"EffectiveTimeContext.tlst_hours = {ctx.tlst_hours}, expected = {expected}"
    )
    # The same instant expressed in UTC must give the same TLST (zone invariance).
    ctx_utc = compute_effective_time_context("2024-06-21T10:00:00", "UTC", lon)
    assert ctx_utc.utc == ctx.utc
    assert math.isclose(ctx_utc.tlst_hours, ctx.tlst_hours, abs_tol=1e-6)


def test_tlst_minus_lmt_equals_eot():
    """Internal consistency: the context's own LMT and TLST differ by its EoT."""
    ctx = compute_effective_time_context("1990-07-15T15:44:00", "Europe/Berlin", 9.732)
    lmt_hours = ctx.lmt_local.hour + ctx.lmt_local.minute / 60 + ctx.lmt_local.second / 3600
    diff_min = (((ctx.tlst_hours - lmt_hours + 12.0) % 24.0) - 12.0) * 60.0
    assert math.isclose(diff_min, ctx.eot_minutes, abs_tol=0.05)


def test_fold_is_honoured_for_ambiguous_fallback_time():
    """FBP-TST-002 / DEV-2026-010: Berlin 2024-10-27 02:30 occurs twice.
    fold=0 is CEST (UTC+2 → 00:30Z), fold=1 is CET (UTC+1 → 01:30Z)."""
    c0 = compute_effective_time_context("2024-10-27T02:30:00", "Europe/Berlin", 13.405, fold=0)
    c1 = compute_effective_time_context("2024-10-27T02:30:00", "Europe/Berlin", 13.405, fold=1)
    assert c0.utc.isoformat() == "2024-10-27T00:30:00+00:00"
    assert c1.utc.isoformat() == "2024-10-27T01:30:00+00:00"
    assert c0.tz_offset_minutes == 120 and c1.tz_offset_minutes == 60
    assert math.isclose(c1.tlst_hours - c0.tlst_hours, 1.0, abs_tol=1e-3)


def test_from_instant_rejects_naive_datetime():
    from bazi_engine.time_context import compute_effective_time_context_from_instant
    with pytest.raises(ValueError):
        compute_effective_time_context_from_instant(datetime(2024, 6, 21, 12, 0), 13.405)


def test_date_rollover_minus_one_west_of_meridian():
    """Madrid 00:30 CET: TLST is 23:01 on the previous calendar day."""
    ctx = compute_effective_time_context("2024-02-22T00:30:00", "Europe/Madrid", -3.7038)
    assert ctx.date_rollover == -1
    assert 23.0 <= ctx.tlst_hours < 23.1


def test_date_rollover_when_tlst_crosses_midnight():
    """A civil time near midnight + far-east longitude pushes TLST past 24h.
    The context must record the day shift instead of dropping it via modulo.
    """
    # Civil 23:30 UTC at +30° E → LMT ≈ 01:30 next day.
    ctx = compute_effective_time_context(
        birth_local_iso="2024-06-15T23:30:00",
        tz_name="UTC",
        longitude_deg=30.0,
    )
    assert ctx.date_rollover == 1


def test_tz_offset_recorded_for_civil():
    """Civil offset must match the IANA zone's offset for that instant."""
    ctx = compute_effective_time_context(
        birth_local_iso="2024-06-15T12:00:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    # CEST in June = UTC+2
    assert ctx.tz_offset_minutes == 120


def test_effective_time_context_is_frozen():
    """Immutability invariant — mirrors BaziInput / BaziResult / Provenance."""
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    with pytest.raises(Exception):
        ctx.civil_local = None  # type: ignore[misc]


def test_lmt_tzname_includes_offset_signature():
    """The LMT tzinfo's tzname is informative (no IANA identity stolen)."""
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    name = ctx.lmt_local.tzname() or ""
    assert "LMT" in name, name
