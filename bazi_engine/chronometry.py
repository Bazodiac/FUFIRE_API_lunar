"""chronometry.py — pure chronometry resolution (no FastAPI).

Composes the existing deterministic time/ephemeris engines into a single
``ChronometryFrame`` for the ``POST /v1/chronometry/resolve`` endpoint.

Design constraints (math-endpoints plan, Phases B+C):

- **No new metaphysical math.** Every numeric field is produced by an
  existing engine function (``compute_effective_time_context``,
  ``SwissEphBackend``, ``datetime_utc_to_jd_ut``, ``jdn_gregorian``,
  ``_lichun_jd_ut_for_year``) or a trivially-defined transform
  (``lon * 4`` longitude correction, ``floor(sun_lon / 15)`` term index).
- **No silent noon default for unknown birth time.** When the time is not
  known, ``true_solar_time`` (and every other hour-derived value) is
  ``None`` and ``precision.grade == "unknown_time"`` with a non-empty
  warning list. This is the load-bearing anti-mockup rule.
- ``JIEQI_NAMES`` is pure public-domain reference DATA (GT4) — the 24 solar
  terms in solar-longitude order, NOT invented math.

This module sits below the router layer and must not import FastAPI.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import __version__
from .bazi import _lichun_jd_ut_for_year, jdn_gregorian
from .ephemeris import (
    SwissEphBackend,
    datetime_utc_to_jd_ut,
)
from .time_context import compute_effective_time_context_from_instant
from .time_utils import AmbiguousTimeChoice, NonexistentTimePolicy, resolve_local_iso

# ── Pure reference data (GT4) ───────────────────────────────────────────────
# The 24 solar terms (jieqi), indexed by ``floor(solar_longitude / 15°)``.
# Index 0 == 0° (Chun Fen / spring equinox). These are fixed public-domain
# names — NAMING data only, deterministic, not derived from any proprietary
# table or invented metaphysical math. The numeric solar longitude that
# selects the index always comes from the live Swiss-Ephemeris Sun position.
JIEQI_NAMES: List[str] = [
    "Chun Fen",    # 0°   — Spring Equinox
    "Qing Ming",   # 15°  — Clear and Bright
    "Gu Yu",       # 30°  — Grain Rain
    "Li Xia",      # 45°  — Start of Summer
    "Xiao Man",    # 60°  — Grain Full
    "Mang Zhong",  # 75°  — Grain in Ear
    "Xia Zhi",     # 90°  — Summer Solstice
    "Xiao Shu",    # 105° — Minor Heat
    "Da Shu",      # 120° — Major Heat
    "Li Qiu",      # 135° — Start of Autumn
    "Chu Shu",     # 150° — Limit of Heat
    "Bai Lu",      # 165° — White Dew
    "Qiu Fen",     # 180° — Autumn Equinox
    "Han Lu",      # 195° — Cold Dew
    "Shuang Jiang",  # 210° — Frost Descent
    "Li Dong",     # 225° — Start of Winter
    "Xiao Xue",    # 240° — Minor Snow
    "Da Xue",      # 255° — Major Snow
    "Dong Zhi",    # 270° — Winter Solstice
    "Xiao Han",    # 285° — Minor Cold
    "Da Han",      # 300° — Major Cold
    "Li Chun",     # 315° — Start of Spring
    "Yu Shui",     # 330° — Rain Water
    "Jing Zhe",    # 345° — Awakening of Insects
]
assert len(JIEQI_NAMES) == 24

# Proximity window (in days) for the near-Li-Chun boundary flag. A birth
# instant within this many days of the year's Li Chun crossing is flagged
# so consumers know the year pillar sits on a knife-edge.
_LICHUN_PROXIMITY_DAYS = 1.0

# Precision grades. ``exact`` (high-precision SE1 backend, time known),
# ``degraded`` (analytical MOSEPH fallback, time known), ``unknown_time``
# (no usable birth time → no noon default), ``unresolved`` (reserved for
# callers that cannot resolve the instant at all).
GRADE_EXACT = "exact"
GRADE_DEGRADED = "degraded"
GRADE_UNKNOWN_TIME = "unknown_time"
GRADE_UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class ChronometryFrame:
    """Immutable, fully-resolved chronometry frame for one birth instant.

    Every field is engine-truth (see module docstring). ``true_solar_time``
    is ``None`` exactly when the birth time is unknown — never a noon
    default.
    """

    julian_day: float                       # fractional UT JD = datetime_utc_to_jd_ut(ctx.utc)
    julian_day_number: int                  # jdn_gregorian of resolved civil date
    delta_t_seconds: float
    equation_of_time_minutes: float
    eot_source: str                         # provenance of the EoT (ctx.eot_source, FBP-TST-006)
    longitude_correction_minutes: float     # = lon * 4
    true_solar_time: Optional[str]          # "HH:MM" from ctx.tlst_hours; None if time unknown
    tlst_date_rollover: Optional[int]       # TLST calendar date − civil date (days); None if time unknown
    solar_longitude_degrees: float          # SwissEphBackend.sun_lon_deg_ut
    solar_term: str                         # JIEQI_NAMES[floor(sun_lon / 15)]
    boundary_flags: Dict[str, Any]          # Li Chun proximity / before-after
    precision: Dict[str, Any]               # {grade, warnings[], algorithm_version}


def _is_date_only(birth_datetime: str) -> bool:
    """True when the ISO string carries no time-of-day component."""
    return "T" not in birth_datetime and " " not in birth_datetime.strip()


def _format_tlst(tlst_hours: float) -> str:
    """Format an apparent-solar hour-of-day in [0, 24) as ``HH:MM`` (clock,
    floor-to-minute)."""
    h = int(tlst_hours) % 24
    m = int((tlst_hours - int(tlst_hours)) * 60)
    return f"{h:02d}:{m:02d}"


def grade_precision(
    *,
    time_known: bool,
    ephemeris_mode: str,
) -> Dict[str, Any]:
    """Derive the precision block.

    - Unknown birth time → ``unknown_time`` + a non-empty warning. NO
      hour-derived field may be reported as high-confidence (the caller
      nulls ``true_solar_time``).
    - Known time on the analytical MOSEPH fallback → ``degraded`` + a
      precision-warning (lower-precision ephemeris).
    - Known time on the high-precision SE1 backend → ``exact``.
    """
    warnings: List[str] = []
    if not time_known:
        warnings.append(
            "Birth time unknown: hour-derived fields (true solar time) are "
            "omitted. No noon default is applied."
        )
        grade = GRADE_UNKNOWN_TIME
    elif ephemeris_mode.upper() == "MOSEPH":
        warnings.append(
            "Computed with the analytical Moshier ephemeris (MOSEPH). "
            "Solar longitude precision is degraded relative to the Swiss "
            "Ephemeris SE1 data files."
        )
        grade = GRADE_DEGRADED
    else:
        grade = GRADE_EXACT

    return {
        "grade": grade,
        "warnings": warnings,
        "algorithm_version": __version__,
    }


def _boundary_flags(jd_ut: float, civil_year: int, backend: SwissEphBackend) -> Dict[str, Any]:
    """Li Chun proximity flags for the resolved instant.

    ``is_before_lichun`` mirrors ``compute_bazi``'s year-boundary test
    (the instant precedes the year's Li Chun crossing). ``near_lichun`` is
    True within ``_LICHUN_PROXIMITY_DAYS`` of that crossing.
    """
    lichun_jd = _lichun_jd_ut_for_year(civil_year, backend)
    delta_days = jd_ut - lichun_jd
    return {
        "lichun_jd_ut": lichun_jd,
        "is_before_lichun": delta_days < 0.0,
        "near_lichun": abs(delta_days) <= _LICHUN_PROXIMITY_DAYS,
        "days_from_lichun": delta_days,
    }


def resolve_chronometry(
    birth_datetime: str,
    timezone: str,
    lat: float,
    lon: float,
    calendar_policy: Optional[str] = None,
    time_known: bool = True,
    ambiguous_time: AmbiguousTimeChoice = "earlier",
    nonexistent_time: NonexistentTimePolicy = "error",
) -> ChronometryFrame:
    """Resolve a birth instant into a full chronometry frame.

    Parameters
    ----------
    birth_datetime
        ISO 8601 local datetime (``"1990-06-15T14:30:00"``) or a date-only
        string (``"1990-06-15"``). A date-only string OR ``time_known=False``
        triggers the unknown-time path: NO noon default, ``true_solar_time``
        is ``None``, grade is ``unknown_time``.
    timezone
        IANA timezone name (e.g. ``"Europe/Berlin"``). Invalid names raise
        ``LocalTimeError`` (an ``InputError`` → HTTP 422 at the router).
    lat, lon
        Geographic latitude / longitude in degrees. ``lat`` is carried for
        provenance/symmetry; longitude drives the longitude correction and
        the LMT/TLST decomposition.
    calendar_policy
        Reserved for future calendar selection; currently accepted and
        threaded through unchanged (no behavioural effect yet).
    time_known
        ``False`` to force the unknown-time path even for a full ISO string.
    ambiguous_time, nonexistent_time
        DST resolution policy for the local wall-clock, identical to the
        ``ambiguousTime`` / ``nonexistentTime`` request fields of
        ``/calculate/bazi`` and ``/calculate/tst`` (owner decision after the
        sprint-2 review, R1 finding F10): before this the frame silently
        resolved a fall-back duplicate as the *earlier* instant and rejected
        spring-gap times, with no way to ask otherwise.

    Returns
    -------
    ChronometryFrame
        Immutable, engine-truth frame.
    """
    date_only = _is_date_only(birth_datetime)
    effective_time_known = time_known and not date_only

    # Normalise the input to a resolvable local ISO. For date-only input we
    # anchor the *date* at midnight purely to obtain a valid civil date and
    # UTC instant for the (time-independent) day/solar-longitude fields —
    # this is NOT a noon default and never reaches true_solar_time.
    iso_for_resolution = birth_datetime if not date_only else f"{birth_datetime}T00:00:00"

    dt_local, _resolution = resolve_local_iso(
        iso_for_resolution, timezone,
        ambiguous=ambiguous_time, nonexistent=nonexistent_time,
    )

    # FBP-TST-002: hand over the resolved aware instant (fold-faithful).
    ctx = compute_effective_time_context_from_instant(dt_local, lon)
    backend = SwissEphBackend()

    jd_ut = datetime_utc_to_jd_ut(ctx.utc)
    jdn = jdn_gregorian(ctx.civil_local.year, ctx.civil_local.month, ctx.civil_local.day)
    delta_t = backend.delta_t_seconds(jd_ut)
    sun_lon = backend.sun_lon_deg_ut(jd_ut)
    term_index = int(math.floor(sun_lon / 15.0)) % 24

    boundary = _boundary_flags(jd_ut, ctx.civil_local.year, backend)
    precision = grade_precision(
        time_known=effective_time_known,
        ephemeris_mode=backend.mode,
    )

    true_solar_time = None if not effective_time_known else _format_tlst(ctx.tlst_hours)
    # R1 finding F11: the frame's julian_day_number is the CIVIL date's JDN by
    # contract; expose the TLST date shift so a reader can place
    # true_solar_time on its own calendar day (−1 = previous solar day, …).
    tlst_date_rollover = None if not effective_time_known else ctx.date_rollover

    return ChronometryFrame(
        julian_day=jd_ut,
        julian_day_number=jdn,
        delta_t_seconds=delta_t,
        equation_of_time_minutes=ctx.eot_minutes,
        eot_source=ctx.eot_source,
        longitude_correction_minutes=lon * 4,
        true_solar_time=true_solar_time,
        tlst_date_rollover=tlst_date_rollover,
        solar_longitude_degrees=sun_lon,
        solar_term=JIEQI_NAMES[term_index],
        boundary_flags=boundary,
        precision=precision,
    )
