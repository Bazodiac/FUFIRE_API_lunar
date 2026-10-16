"""EffectiveTimeContext — typed decomposition of a birth instant
across the three time standards used by the BaZi engine.

FBP-01-002 / FBP-01-006 / FBP-TST-002 / FBP-TST-003:

- ``CIVIL`` = legal local time in the IANA timezone (tz-aware).
- ``LMT``   = mean solar time at the given longitude (tz-aware, with a
              constant-offset tzinfo derived purely from longitude;
              NOT DST-sensitive, NOT registered with ``zoneinfo``).
- ``TLST``  = apparent solar time = LMT + equation of time (Meeus). Stored as
              a float hour-of-day plus an integer ``date_rollover``.
              **Not** a tzinfo. TLST is not a legal/civil zone, and
              modeling it as a tzinfo would invite false symmetry with
              CIVIL/LMT.

Definition (``docs/fusion/04_solar_time.md``)::

    UTC  = civil − zone_offset
    LMT  = UTC + longitude_deg × 4 min
    TLST = LMT + equation_of_time

All three relabel the **same physical instant**; ``utc`` is the only axis
the solar corrections are applied to. (DEV-2026-009 was exactly the
mistake of applying them to the civil wall-clock instead, which made
``tlst_hours`` wrong by the zone offset for every non-UTC zone.)

Dependencies: stdlib + ``bazi_engine.solar_time`` (which is itself
stdlib-only). This module sits at Level 2 and must not import from
``bazi.py``, ``fusion.py``, or any router.

See ``docs/plans/2026-10-15-true-solar-time-remediation.md`` and
``docs/audits/fufire_bazi_precision_pre_audit.md`` §2 for context.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

from .solar_time import EOT_SOURCE_MEEUS, equation_of_time_jd, jd_ut_from_datetime


class _LongitudeMeanTime(tzinfo):
    """A constant-offset ``tzinfo`` for Local Mean Time at a given longitude.

    Not a real IANA zone; never observes DST; offset is purely
    ``longitude_deg × 4 min/° east``. Returned by
    ``EffectiveTimeContext.lmt_local.tzinfo`` so consumers can format
    the value, but the instance is **not** registered with
    ``zoneinfo`` and must not be passed where an IANA zone is required.
    """

    __slots__ = ("_offset",)

    def __init__(self, longitude_deg: float) -> None:
        self._offset = timedelta(minutes=longitude_deg * 4)

    def utcoffset(self, dt: Optional[datetime]) -> timedelta:
        return self._offset

    def dst(self, dt: Optional[datetime]) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: Optional[datetime]) -> str:
        total_min = int(round(self._offset.total_seconds() / 60))
        sign = "+" if total_min >= 0 else "-"
        h, m = divmod(abs(total_min), 60)
        return f"LMT{sign}{h:02d}:{m:02d}"


@dataclass(frozen=True)
class EffectiveTimeContext:
    """All three time standards plus the metadata needed to diagnose
    boundary cases (TLST rollover, EoT magnitude, civil tz offset).

    Frozen by design — mirrors ``BaziInput`` / ``BaziResult`` /
    ``Provenance``. Build via :func:`compute_effective_time_context`
    or :func:`compute_effective_time_context_from_instant`.
    """

    civil_local: datetime           # tz-aware, IANA tz (fold preserved)
    utc: datetime                   # tz-aware, UTC
    lmt_local: datetime             # tz-aware, constant longitude offset
    tlst_hours: float               # apparent solar hour-of-day, in [0, 24)
    eot_minutes: float              # equation of time, minutes
    tz_offset_minutes: int          # civil_local UTC offset, minutes
    date_rollover: int              # day shift of TLST relative to civil date
    eot_source: str = EOT_SOURCE_MEEUS  # provenance label of eot_minutes (FBP-TST-006)


def compute_effective_time_context_from_instant(
    civil_local: datetime,
    longitude_deg: float,
) -> EffectiveTimeContext:
    """Decompose an **aware** civil datetime + longitude into the three
    time standards.

    This is the canonical entry point: the caller has already resolved
    DST (gap / fold) and hands over the exact instant, so no information
    is lost. ``civil_local.fold`` is honoured because the conversion to
    UTC goes through ``astimezone`` on the aware value itself.

    Parameters
    ----------
    civil_local
        Timezone-aware local datetime (IANA zone, ``fold`` set as resolved).
    longitude_deg
        Geographic longitude, degrees east (negative = west).

    Raises
    ------
    ValueError
        If ``civil_local`` is naive.
    """
    if civil_local.tzinfo is None or civil_local.utcoffset() is None:
        raise ValueError("civil_local must be timezone-aware (resolve DST first).")

    utc = civil_local.astimezone(timezone.utc)
    lmt_local = utc.astimezone(_LongitudeMeanTime(longitude_deg))

    # FBP-TST-006 (E6-M): EoT evaluated at the exact UT instant with the
    # pure-math Meeus formula (no Swiss Ephemeris call — attestation
    # invariant F3). Agreement with swe.time_equ is < 0.1 min, see
    # tests/test_solar_time.py::TestMeeusEquationOfTime and
    # tests/test_tlst_reference_corpus.py::test_eot_meeus_bound_full_year_vs_swisseph.
    eot_min = equation_of_time_jd(jd_ut_from_datetime(utc))

    # TLST on the UTC axis: one timedelta applied to the instant. The
    # result is kept as a *naive* wall-clock (hour-of-day + calendar date)
    # on purpose — TLST is not a tzinfo (FBP-01-006).
    tlst_wall = utc.replace(tzinfo=None) + timedelta(
        minutes=longitude_deg * 4.0 + eot_min
    )
    # Hour-of-day to 6 decimals by TRUNCATION of the integer microsecond
    # count, never by rounding: rounding lifted 22:59:59.9995 to 23.000000
    # and flipped the hour branch (Hai → Zi) plus the zi day advance for an
    # instant that is still before 23:00 (R2 review finding TLST-1), and
    # lifted the last ~2 ms of a day to 24.0 (S-4 finding). Truncation keeps
    # every decision (hour branch, zi rule, date_rollover) on the correct
    # side of its edge and bounds the value in [0, 23.999999].
    wall_us = (
        (tlst_wall.hour * 60 + tlst_wall.minute) * 60 + tlst_wall.second
    ) * 1_000_000 + tlst_wall.microsecond
    tlst_hours = (wall_us // 3600) / 1e6
    rollover = (tlst_wall.date() - civil_local.date()).days

    tz_off = civil_local.utcoffset()
    tz_off_min = 0 if tz_off is None else int(round(tz_off.total_seconds() / 60))

    return EffectiveTimeContext(
        civil_local=civil_local,
        utc=utc,
        lmt_local=lmt_local,
        tlst_hours=tlst_hours,
        eot_minutes=round(eot_min, 4),
        tz_offset_minutes=tz_off_min,
        date_rollover=rollover,
        eot_source=EOT_SOURCE_MEEUS,
    )


def compute_effective_time_context(
    birth_local_iso: str,
    tz_name: str,
    longitude_deg: float,
    *,
    fold: int = 0,
) -> EffectiveTimeContext:
    """Convenience wrapper: naive ISO + IANA zone (+ ``fold``) → context.

    The caller is responsible for DST disambiguation upstream — by the
    time this function is invoked, ``birth_local_iso`` is expected to
    be the resolved naive ISO produced by
    :func:`bazi_engine.time_utils.resolve_local_iso`, and ``fold`` the
    choice that resolution made (``0`` = first occurrence, ``1`` = second
    occurrence of an ambiguous fall-back time). Callers that already hold
    the aware datetime should use
    :func:`compute_effective_time_context_from_instant` directly.

    Parameters
    ----------
    birth_local_iso
        Naive ISO 8601 local datetime, e.g. ``"2024-02-10T14:30:00"``.
    tz_name
        IANA timezone name, e.g. ``"Europe/Berlin"``.
    longitude_deg
        Geographic longitude, degrees east (negative = west).
    fold
        DST fold for ambiguous local times (default ``0``).

    Returns
    -------
    EffectiveTimeContext
        Immutable record. ``tlst_hours`` is the apparent-solar
        hour-of-day in ``[0, 24)``; if TLST falls on a different calendar
        day than the civil input, ``date_rollover`` records the shift
        (``+1`` next day, ``-1`` previous day).
    """
    civil_naive = datetime.fromisoformat(birth_local_iso)
    civil_local = civil_naive.replace(tzinfo=ZoneInfo(tz_name), fold=fold)
    return compute_effective_time_context_from_instant(civil_local, longitude_deg)
