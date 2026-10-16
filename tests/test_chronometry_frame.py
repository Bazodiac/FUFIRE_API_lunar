"""Phase B — chronometry pure-module spec (anti-mockup, engine-truth).

These tests pin ``bazi_engine.chronometry.resolve_chronometry`` to the
*in-process* engine functions it composes. Every numeric field must EQUAL
what the live engine computes for the same input — no hand-typed magic
numbers, no positional/heuristic shortcuts. This is the load-bearing
anti-fabrication contract from the math-endpoints plan (DoD bullet
"Chronometry == live in-process engine").

Backend-agnostic: each test recomputes the expected value from the same
engine functions, so it passes identically under MOSEPH and swieph
(no ephemeris-tag split needed at this layer).
"""
from __future__ import annotations

import math

from bazi_engine import __version__ as ENGINE_VERSION
from bazi_engine.bazi import _lichun_jd_ut_for_year, jdn_gregorian
from bazi_engine.chronometry import (
    JIEQI_NAMES,
    ChronometryFrame,
    resolve_chronometry,
)
from bazi_engine.ephemeris import (
    SwissEphBackend,
    datetime_utc_to_jd_ut,
)
from bazi_engine.time_context import compute_effective_time_context
from bazi_engine.time_utils import resolve_local_iso

# Reused known case across B-series tests.
KNOWN_ISO = "1990-06-15T14:30:00"
KNOWN_TZ = "Europe/Berlin"
KNOWN_LAT = 52.52
KNOWN_LON = 13.405


def _engine_ctx(iso: str, tz: str, lon: float):
    dt_local, _ = resolve_local_iso(iso, tz)
    resolved = dt_local.replace(tzinfo=None).isoformat()
    return compute_effective_time_context(resolved, tz, lon)


def test_jieqi_names_is_24_term_table():
    """JIEQI_NAMES is pure 24-entry reference data (GT4)."""
    assert len(JIEQI_NAMES) == 24
    assert all(isinstance(n, str) and n for n in JIEQI_NAMES)
    # Index 0 corresponds to 0° solar longitude (spring equinox / Chun Fen).
    assert JIEQI_NAMES[0]


# ── B1: known case matches in-process engine (anti-mockup) ──────────────────

def test_resolve_known_case_matches_engine():
    frame = resolve_chronometry(KNOWN_ISO, KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    assert isinstance(frame, ChronometryFrame)

    ctx = _engine_ctx(KNOWN_ISO, KNOWN_TZ, KNOWN_LON)
    backend = SwissEphBackend()
    jd_ut = datetime_utc_to_jd_ut(ctx.utc)

    # EoT — exactly the engine value, not re-derived.
    assert frame.equation_of_time_minutes == ctx.eot_minutes
    assert frame.eot_source == ctx.eot_source == "meeus_1998"
    # Longitude correction = lon * 4 (minutes).
    assert frame.longitude_correction_minutes == KNOWN_LON * 4
    # Fractional UT Julian Day.
    assert frame.julian_day == jd_ut
    # Civil-date JDN.
    assert frame.julian_day_number == jdn_gregorian(
        ctx.civil_local.year, ctx.civil_local.month, ctx.civil_local.day
    )
    # delta_t and sun longitude come straight from the backend.
    assert frame.delta_t_seconds == backend.delta_t_seconds(jd_ut)
    assert frame.solar_longitude_degrees == backend.sun_lon_deg_ut(jd_ut)


def test_true_solar_time_derived_from_tlst_hours():
    frame = resolve_chronometry(KNOWN_ISO, KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    ctx = _engine_ctx(KNOWN_ISO, KNOWN_TZ, KNOWN_LON)
    h = int(ctx.tlst_hours)
    m = int((ctx.tlst_hours - h) * 60)
    assert frame.true_solar_time == f"{h:02d}:{m:02d}"


def test_algorithm_version_is_engine_version():
    frame = resolve_chronometry(KNOWN_ISO, KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    assert frame.precision["algorithm_version"] == ENGINE_VERSION


# ── B2: solar_term == JIEQI_NAMES[floor(sun_lon/15)] ────────────────────────

def test_solar_term_matches_floor_of_sun_longitude():
    frame = resolve_chronometry(KNOWN_ISO, KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    ctx = _engine_ctx(KNOWN_ISO, KNOWN_TZ, KNOWN_LON)
    backend = SwissEphBackend()
    jd_ut = datetime_utc_to_jd_ut(ctx.utc)
    sun_lon = backend.sun_lon_deg_ut(jd_ut)
    expected_idx = int(math.floor(sun_lon / 15.0)) % 24
    assert frame.solar_term == JIEQI_NAMES[expected_idx]


# ── B3: Li Chun boundary flag flips around a Li Chun crossing ───────────────

def test_lichun_boundary_flags_flip_across_crossing():
    # 2024 Li Chun crosses ~09:27 local Berlin. These two instants straddle it.
    before = resolve_chronometry("2024-02-04T09:26:00", KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    after = resolve_chronometry("2024-02-04T09:28:00", KNOWN_TZ, KNOWN_LAT, KNOWN_LON)

    assert before.boundary_flags["is_before_lichun"] is True
    assert after.boundary_flags["is_before_lichun"] is False
    # Both are within the near-Li-Chun proximity window.
    assert before.boundary_flags["near_lichun"] is True
    assert after.boundary_flags["near_lichun"] is True

    # A far-from-Li-Chun instant is not flagged near.
    far = resolve_chronometry(KNOWN_ISO, KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    assert far.boundary_flags["near_lichun"] is False


def test_lichun_jd_in_boundary_flags_matches_engine():
    frame = resolve_chronometry("2024-02-04T09:26:00", KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    backend = SwissEphBackend()
    expected = _lichun_jd_ut_for_year(2024, backend)
    assert frame.boundary_flags["lichun_jd_ut"] == expected


# ── B4: date-only / time unknown → grade=unknown_time, no noon default ──────

def test_missing_time_grade_unknown():
    frame = resolve_chronometry("1990-06-15", KNOWN_TZ, KNOWN_LAT, KNOWN_LON, time_known=False)
    assert frame.precision["grade"] == "unknown_time"
    # NO silent noon default — hour-derived field is None.
    assert frame.true_solar_time is None
    # Warnings must be non-empty (caller is told the time is missing).
    assert frame.precision["warnings"]


def test_date_only_input_infers_unknown_time():
    """A date-only ISO string is treated as time-unknown even if the
    caller forgets to pass time_known=False."""
    frame = resolve_chronometry("1990-06-15", KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    assert frame.precision["grade"] == "unknown_time"
    assert frame.true_solar_time is None


def test_known_time_grade_not_unknown():
    frame = resolve_chronometry(KNOWN_ISO, KNOWN_TZ, KNOWN_LAT, KNOWN_LON)
    assert frame.precision["grade"] != "unknown_time"
    assert frame.true_solar_time is not None


# ── B5: non-integer tz + far-from-meridian longitude ────────────────────────

def test_noninteger_tz_and_far_longitude():
    # Asia/Kathmandu is UTC+5:45 (345 minutes) — a non-integer-hour zone.
    lon = 85.324  # Kathmandu, far from the +5:45 meridian.
    frame = resolve_chronometry("1990-06-15T14:30:00", "Asia/Kathmandu", 27.7172, lon)
    ctx = _engine_ctx("1990-06-15T14:30:00", "Asia/Kathmandu", lon)

    assert ctx.tz_offset_minutes == 345
    assert frame.longitude_correction_minutes == lon * 4
    # The frame composes the same context — true solar time present + non-None.
    assert frame.true_solar_time is not None
