"""
solar_time.py — Level 2: Pure solar time mathematics.

No internal imports, no third-party imports. Provides:
  - jd_ut_from_datetime()  aware datetime → Julian Day (UT), stdlib only
  - equation_of_time_jd()  Equation of Time in minutes, Meeus (1998) ch. 28 —
                           the engine path (FBP-TST-006, decision E6-M)
  - equation_of_time()     Equation of Time in minutes keyed on day-of-year
                           (Spencer/NOAA approximation, ≤ 0.8 min error) —
                           legacy leaf, no production caller since /validate
                           moved to the shared context (kept for the
                           true_solar_time() helper and its reference tests)
  - true_solar_time()      Civil time → True Solar Time conversion (leaf helper)

Extracted from fusion.py so that bafe/time_model.py (Level 5) can import
this without depending on the full fusion module (Level 4).

Why pure math and not ``swe.time_equ``: ``/calculate/tst`` is contractually
free of Swiss-Ephemeris work (attestation invariant F3, 2026-07-01,
``tests/test_attestation_contract.py``), and ``time_context.py`` sits at
Level 2 next to ``ephemeris.py`` rather than above it. Meeus' formula
reproduces ``swe.time_equ`` to well under 0.1 min (see
``tests/test_solar_time.py::TestMeeusEquationOfTime``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from math import atan2, cos, degrees, pi, radians, sin
from typing import Optional

J2000_JD = 2451545.0           # 2000-01-01 12:00 TT (used here with UT; ΔT is negligible for the EoT)
_J2000_UTC = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_SECONDS_PER_DAY = 86400.0

EOT_SOURCE_MEEUS = "meeus_1998"      # equation_of_time_jd — engine path
EOT_SOURCE_SPENCER = "spencer_1971"  # equation_of_time — /validate degraded path


def jd_ut_from_datetime(dt_utc: datetime) -> float:
    """Julian Day (UT) of an **aware** datetime, stdlib only.

    Mirrors ``ephemeris.datetime_utc_to_jd_ut`` (which goes through
    ``swe.julday``) to the microsecond, without touching Swiss Ephemeris.

    Raises ``ValueError`` for a naive datetime: the caller must have
    resolved the zone (and DST fold) already.
    """
    if dt_utc.tzinfo is None or dt_utc.utcoffset() is None:
        raise ValueError("jd_ut_from_datetime requires a timezone-aware datetime")
    delta = dt_utc.astimezone(timezone.utc) - _J2000_UTC
    return J2000_JD + delta.total_seconds() / _SECONDS_PER_DAY


def _norm_deg(x: float) -> float:
    return x % 360.0


def equation_of_time_jd(jd_ut: float) -> float:
    """Equation of Time in **minutes** for a Julian Day (UT), Meeus (1998) ch. 28.

    Sign convention (same as ``swe.time_equ`` and ``equation_of_time``):
    ``E = apparent solar time − mean solar time``; positive = sundial fast.

    Method (Meeus, *Astronomical Algorithms*, 2nd ed., eq. 28.1):

        E = L0 − 0.0057183° − α + Δψ·cos ε

    with the Sun's mean longitude ``L0`` (28.2), its apparent right
    ascension ``α`` from the low-accuracy solar position of ch. 25
    (true longitude + aberration + nutation, obliquity of ch. 22), and the
    nutation in longitude ``Δψ`` / true obliquity ``ε`` from the ch. 22
    short series. Result converted from degrees to minutes of time (×4).

    The input is UT rather than TT; the ΔT difference (≤ ~70 s in
    1950–2030) moves the Sun by < 0.003″ in the EoT, far below the
    0.1 min tolerance enforced in tests. Validated against
    ``swe.time_equ``: max |Δ| = 0.038 min over 1950–2030 at 6 h steps
    (and ≤ 0.08 min for years 1–3000).
    """
    T = (jd_ut - J2000_JD) / 36525.0
    T2, T3 = T * T, T * T * T

    # Sun, ch. 25 (low accuracy) — mean longitude, mean anomaly, eccentricity.
    L0 = _norm_deg(280.46646 + 36000.76983 * T + 0.0003032 * T2)
    M = _norm_deg(357.52911 + 35999.05029 * T - 0.0001537 * T2)
    Mr = radians(M)
    C = (
        (1.914602 - 0.004817 * T - 0.000014 * T2) * sin(Mr)
        + (0.019993 - 0.000101 * T) * sin(2 * Mr)
        + 0.000289 * sin(3 * Mr)
    )
    true_lon = L0 + C

    # Nutation + obliquity, ch. 22 (short series: dominant Ω term + Sun/Moon).
    omega = _norm_deg(125.04452 - 1934.136261 * T + 0.0020708 * T2 + T3 / 450000.0)
    L_sun = _norm_deg(280.4665 + 36000.7698 * T)
    L_moon = _norm_deg(218.3165 + 481267.8813 * T)
    om_r, ls_r, lm_r = radians(omega), radians(L_sun), radians(L_moon)
    dpsi_arcsec = -17.20 * sin(om_r) - 1.32 * sin(2 * ls_r) - 0.23 * sin(2 * lm_r) + 0.21 * sin(2 * om_r)
    deps_arcsec = 9.20 * cos(om_r) + 0.57 * cos(2 * ls_r) + 0.10 * cos(2 * lm_r) - 0.09 * cos(2 * om_r)
    eps0 = 23.0 + (26.0 + (21.448 - 46.8150 * T - 0.00059 * T2 + 0.001813 * T3) / 60.0) / 60.0
    dpsi = dpsi_arcsec / 3600.0
    eps = eps0 + deps_arcsec / 3600.0

    # Apparent longitude = true longitude + nutation in longitude − aberration
    # (25.9/25.10 with the explicit Δψ above). Meeus' low-accuracy shorthand
    # ``λ = Θ − 0.00569° − 0.00478°·sin Ω`` (25.8) folds the dominant
    # nutation term into that −0.00478°·sin Ω; using it *and* Δψ would count
    # the nutation twice (S-4 review finding, +0.02 min error).
    apparent_lon = true_lon + dpsi - 0.00569

    # Apparent right ascension (25.6) — atan2 keeps the quadrant.
    lam_r, eps_r = radians(apparent_lon), radians(eps)
    alpha = _norm_deg(degrees(atan2(cos(eps_r) * sin(lam_r), cos(lam_r))))

    # 28.1 — difference wrapped into (-180°, 180°] before scaling.
    E_deg = L0 - 0.0057183 - alpha + dpsi * cos(eps_r)
    E_deg = (E_deg + 180.0) % 360.0 - 180.0
    return E_deg * 4.0


def equation_of_time(day_of_year: int, use_precise: bool = True) -> float:
    """
    Calculate Equation of Time (E_t) in minutes (day-of-year approximation).

    **Not the engine path.** Since FBP-TST-006 every production surface
    (BaZi, fusion, chronometry and — since the sprint-2 review decision 1 —
    ``/validate``) uses :func:`equation_of_time_jd` (Meeus, exact to
    < 0.1 min). This day-of-year form (Spencer 1971 / NOAA, max error
    ≈ 0.8 min vs Swiss Ephemeris, measured 1950–2026) has no production
    caller any more; it is kept for the :func:`true_solar_time` leaf helper
    and the reference tests that pin its documented error budget.

    The Equation of Time quantifies the discrepancy between
    apparent solar time and mean solar time due to:
    1. Earth's elliptical orbit (eccentricity effect)
    2. Earth's axial tilt (obliquity effect)

    Args:
        day_of_year: Day number (1-366)
        use_precise: If True, use more accurate formula with both effects

    Returns:
        Equation of Time in minutes (can be positive or negative)
        Range: approximately -14.2 to +16.4 minutes

    Formula (standard approximation):
        E_t = 9.87*sin(2B) - 7.53*cos(B) - 1.5*sin(B)
        where B = 360*(N-81)/365 degrees

    More precise formula separates eccentricity and obliquity effects.
    """
    if use_precise:
        # More accurate formula using both eccentricity and obliquity
        # Reference: NOAA Solar Calculator / Astronomical Algorithms
        gamma = 2 * pi * (day_of_year - 1) / 365.0
        E = 229.18 * (
            0.000075
            + 0.001868 * cos(gamma)
            - 0.032077 * sin(gamma)
            - 0.014615 * cos(2 * gamma)
            - 0.040849 * sin(2 * gamma)
        )
        return round(E, 3)
    else:
        B = 360 * (day_of_year - 81) / 365
        B_rad = radians(B)
        E = (
            9.87 * sin(2 * B_rad)
            - 7.53 * cos(B_rad)
            - 1.5 * sin(B_rad)
        )
        return round(E, 2)


def true_solar_time(
    civil_time_hours: float,
    longitude_deg: float,
    day_of_year: int,
    timezone_offset_hours: Optional[float] = None,
) -> float:
    """
    Calculate True Solar Time (TST) from civil time.

    TST = Local Mean Time + Equation of Time
    LMT = UTC + (longitude / 15) hours

    For civil time with a timezone:
    TST = civil_time - tz_offset + (longitude/15) + E_t

    Args:
        civil_time_hours: Local civil time in hours (e.g., 14.5 = 14:30)
        longitude_deg: Longitude (positive = east, negative = west)
        day_of_year: Day of year (1-366)
        timezone_offset_hours: Timezone offset from UTC in hours (e.g., +1 for CET).
                              If None, treats input as LMT.

    Returns:
        True Solar Time in hours (0-24)
    """
    if timezone_offset_hours is not None:
        utc_hours = civil_time_hours - timezone_offset_hours
        lmt_hours = utc_hours + (longitude_deg / 15.0)
    else:
        lmt_hours = civil_time_hours

    E_t = equation_of_time(day_of_year) / 60.0
    TST = lmt_hours + E_t

    while TST < 0:
        TST += 24
    while TST >= 24:
        TST -= 24

    return round(TST, 4)
