"""ZWDS-P1-05 — seed time pipeline (chronometry half) tests.

The time pipeline is ephemeris-free (pure zoneinfo + arithmetic), so no
``swieph`` marker is needed here — none of these tests touch Swiss Ephemeris.
"""

from __future__ import annotations

from datetime import date

import pytest

from bazi_engine.time_utils import LocalTimeError
from bazi_engine.zwds.errors import ZwdsBirthTimeRequiredError
from bazi_engine.zwds.seed import (
    ChronometryResolution,
    Location,
    resolve_chronometry,
)

# The canonical design-pack vector.
_SHANGHAI = dict(
    datetime_local="1984-02-01T23:30:00",
    timezone="Asia/Shanghai",
    lat=31.2304,
    lon=121.4737,
    ambiguous_time="earlier",
    nonexistent_time="error",
)


def test_example_vector_matches_response_example_core() -> None:
    r = resolve_chronometry(**_SHANGHAI, time_standard="CIVIL")

    # Exact chronometry fields from response_example_core.json.
    assert r.civil_local == "1984-02-01T23:30:00+08:00"
    assert r.utc == "1984-02-01T15:30:00Z"
    assert r.effective_local == "1984-02-01T23:30:00+08:00"
    assert r.effective_standard == "CIVIL"
    assert r.timezone == "Asia/Shanghai"
    assert r.location == Location(lat=31.2304, lon=121.4737)
    assert r.local_time_status == "ok"
    assert r.fold == 0
    assert r.warning is None
    assert r.hour_branch_id == "ZI"
    assert r.late_zi_applied is True
    assert r.late_zi_policy_id == "next-chart-day.v1"

    # Derived carry-overs for the calendar half.
    assert r.chart_local_date == date(1984, 2, 2)
    assert r.day_boundary_offset_hours == 8.0


def test_result_is_frozen() -> None:
    r = resolve_chronometry(**_SHANGHAI)
    with pytest.raises(Exception):
        r.hour_branch_id = "WU"  # type: ignore[misc]
    assert isinstance(r, ChronometryResolution)


@pytest.mark.parametrize(
    ("local", "expected_branch", "expected_late_zi"),
    [
        ("2000-06-15T00:30:00", "ZI", False),
        ("2000-06-15T01:00:00", "CHOU", False),
        ("2000-06-15T11:30:00", "WU", False),
        ("2000-06-15T13:00:00", "WEI", False),
        ("2000-06-15T22:00:00", "HAI", False),
        ("2000-06-15T23:15:00", "ZI", True),
    ],
)
def test_hour_branch_table(
    local: str, expected_branch: str, expected_late_zi: bool
) -> None:
    r = resolve_chronometry(
        datetime_local=local,
        timezone="Asia/Shanghai",
        lat=31.2304,
        lon=121.4737,
        ambiguous_time="earlier",
        nonexistent_time="error",
        time_standard="CIVIL",
    )
    assert r.hour_branch_id == expected_branch
    assert r.late_zi_applied is expected_late_zi


def test_non_late_zi_keeps_effective_date() -> None:
    r = resolve_chronometry(
        datetime_local="1984-02-01T14:30:00",
        timezone="Asia/Shanghai",
        lat=31.2304,
        lon=121.4737,
        ambiguous_time="earlier",
        nonexistent_time="error",
        time_standard="CIVIL",
    )
    assert r.late_zi_applied is False
    assert r.hour_branch_id == "WEI"  # 14:30 -> ((14+1)//2)%12 = 7
    assert r.chart_local_date == date(1984, 2, 1)


def test_missing_birth_time_raises_zwds_required() -> None:
    with pytest.raises(ZwdsBirthTimeRequiredError):
        resolve_chronometry(
            datetime_local="",
            timezone="Asia/Shanghai",
            lat=31.2304,
            lon=121.4737,
            ambiguous_time="earlier",
            nonexistent_time="error",
        )


def test_dst_gap_raises_and_does_not_leak_birth_instant() -> None:
    # Europe/Berlin 2024-03-31 02:00 -> 03:00 spring-forward: 02:30 does not exist.
    with pytest.raises(LocalTimeError) as excinfo:
        resolve_chronometry(
            datetime_local="2024-03-31T02:30:00",
            timezone="Europe/Berlin",
            lat=52.52,
            lon=13.405,
            ambiguous_time="earlier",
            nonexistent_time="error",
            time_standard="CIVIL",
        )
    # PII-scrub parity: the raised message must not echo the birth instant.
    assert "02:30" not in str(excinfo.value)
    assert "2024-03-31" not in str(excinfo.value)


@pytest.mark.parametrize(
    ("choice", "expected_fold"),
    [("earlier", 0), ("later", 1)],
)
def test_dst_fold_ambiguous_resolves_with_expected_fold(
    choice: str, expected_fold: int
) -> None:
    # Europe/Berlin 2024-10-27 03:00 -> 02:00 fall-back: 02:30 occurs twice.
    r = resolve_chronometry(
        datetime_local="2024-10-27T02:30:00",
        timezone="Europe/Berlin",
        lat=52.52,
        lon=13.405,
        ambiguous_time=choice,
        nonexistent_time="error",
        time_standard="CIVIL",
    )
    assert r.local_time_status == "ambiguous"
    assert r.fold == expected_fold
    assert r.warning is not None


def test_lmt_relabels_same_instant_with_longitude_offset() -> None:
    r = resolve_chronometry(**_SHANGHAI, time_standard="LMT")
    # Same physical birth instant -> `utc` invariant vs. the CIVIL vector.
    assert r.utc == "1984-02-01T15:30:00Z"
    assert r.effective_standard == "LMT"
    # LMT offset = 121.4737 * 4 min = 8.09825 h; late-Zi still applies (23:35).
    assert r.day_boundary_offset_hours == pytest.approx(121.4737 / 15.0)
    assert r.hour_branch_id == "ZI"
    assert r.late_zi_applied is True
    assert r.chart_local_date == date(1984, 2, 2)


def test_tlst_uses_apparent_solar_offset_anchored_to_utc() -> None:
    r = resolve_chronometry(**_SHANGHAI, time_standard="TLST")
    assert r.utc == "1984-02-01T15:30:00Z"  # instant invariant
    assert r.effective_standard == "TLST"
    # Apparent solar offset = longitude offset + equation-of-time (early Feb EoT
    # is ~ -13 min), so the offset is a bit under the LMT longitude offset.
    assert r.day_boundary_offset_hours < 121.4737 / 15.0
    # Oracle: swe.time_equ at the UT instant (FBP-TST-006 — the engine EoT is
    # the Meeus formula, within 0.1 min of swisseph). Before S-2 the day-of-year
    # approximation pinned 7.8787 h here; the exact value is 7.8721 h (swe) /
    # 7.8726 h (Meeus).
    import swisseph as swe
    jd_ut = swe.julday(1984, 2, 1, 15.5)
    r_eot = swe.time_equ(jd_ut)
    eot_min = (r_eot[0] if isinstance(r_eot, tuple) else r_eot) * 1440.0
    expected = (121.4737 * 4.0 + eot_min) / 60.0
    assert r.day_boundary_offset_hours == pytest.approx(expected, abs=0.1 / 60.0)
    assert r.day_boundary_offset_hours == pytest.approx(7.8726, abs=1e-3)
    assert r.hour_branch_id == "ZI"


def test_tlst_offset_is_exactly_the_shared_context_offset() -> None:
    """FBP-TST-007 consistency: the ZWDS seed's TLST day-boundary offset must be
    *exactly* ``lon·4 min + EffectiveTimeContext.eot_minutes`` for the same
    instant — the seed consumes the shared context (FBP-TST-006 Meeus EoT),
    it does not carry an EoT of its own. A drift here would mean the two
    engines disagree on what TLST is."""
    from bazi_engine.time_context import compute_effective_time_context_from_instant
    from bazi_engine.time_utils import resolve_local_iso

    r = resolve_chronometry(**_SHANGHAI, time_standard="TLST")
    civil_dt, _ = resolve_local_iso(_SHANGHAI["datetime_local"], _SHANGHAI["timezone"])
    ctx = compute_effective_time_context_from_instant(civil_dt, _SHANGHAI["lon"])
    assert ctx.eot_source == "meeus_1998"
    expected_offset_min = _SHANGHAI["lon"] * 4.0 + ctx.eot_minutes
    assert r.day_boundary_offset_hours * 60.0 == pytest.approx(expected_offset_min, abs=1e-6)
    # And the LMT offset is the pure longitude term (no EoT).
    r_lmt = resolve_chronometry(**_SHANGHAI, time_standard="LMT")
    assert r_lmt.day_boundary_offset_hours * 60.0 == pytest.approx(_SHANGHAI["lon"] * 4.0, abs=1e-6)
