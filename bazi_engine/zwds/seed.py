"""ZWDS-P1-05/06 — seed pipeline (chronometry + calendar halves).

Turns a civil birth input + ruleset time/calendar policy into the
``resolution.chronometry`` and ``resolution.calendar`` contracts from the
design pack (``docs/zwds/design-pack/response_example_core.json``) plus the
downstream ``ResolvedZwdsSeed`` formula inputs ``(m, d, y_s, y_b, h-1)`` that
the ZWDS palace/star formulas consume (design pack §2 variable contract).

Pipeline (design pack §4, all seven steps):

1. Resolve the civil local time, disambiguating DST (fold / gap) via
   :func:`bazi_engine.time_utils.resolve_local_iso`.
2. Apply the ruleset *time standard* (``CIVIL`` / ``LMT`` / ``TLST``) to obtain
   the effective-local instant.
3. Derive the hour branch from the effective-local hour.
4. Detect late Zi (23:00–23:59) and apply the late-Zi chart-date policy.
   *(Steps 1–4 = the chronometry half, :func:`resolve_chronometry`.)*
5. Convert the chart-local date to the Chinese lunisolar date via the
   swisseph-native provider (:func:`build_core_seed_calendar`).
6. Apply the leap-month interpretation policy ``split-after-day-15.guide-v1``
   to derive the effective month ``m`` (:func:`effective_month_for_leap_split`).
7. Resolve the year stem/branch/animal from the lunar year label via the
   ``lunar-year.guide-v1`` policy (:func:`year_cycle_for_label`).
   *(Steps 5–7 = the calendar half, :func:`resolve_calendar_seed`.)*

**Time-standard model.** All three standards relabel the *same physical birth
instant* onto a fixed UTC offset, so ``utc`` is invariant and ``effective_local``
is always a real tz-aware datetime:

* ``CIVIL`` — the civil (IANA zone) offset at the birth instant.
* ``LMT``   — mean solar offset ``longitude × 4 min`` (see
  :func:`bazi_engine.time_utils.lmt_tzinfo`).
* ``TLST``  — apparent solar offset ``longitude × 4 min + equation_of_time``.
  The equation-of-time value is taken from
  :func:`bazi_engine.time_context.compute_effective_time_context_from_instant`.
  (Its ``tlst_hours`` is UTC-anchored since FBP-TST-003 / DEV-2026-009 and
  agrees with this offset; the seed keeps its own tz-aware ``effective_local``
  because the ZWDS calendar provider needs a real UTC offset, not an
  hour-of-day.)

Layer: this module may import ``time_utils``, ``time_context`` and its ZWDS
siblings (``zwds.domain``, ``zwds.errors``, ``zwds.calendar_provider``) only. It
must NOT import ``bazi.*``, ``zwds.engine``, routers or ``app``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from typing import Optional, Tuple

from bazi_engine.time_context import compute_effective_time_context_from_instant
from bazi_engine.time_utils import lmt_tzinfo, resolve_local_iso
from bazi_engine.zwds.calendar_provider import (
    ResolvedLunarDate,
    build_core_seed_calendar,
)
from bazi_engine.zwds.domain import AnimalId, BranchId, StemId, mod10, mod12
from bazi_engine.zwds.errors import ZwdsBirthTimeRequiredError

_UTC = dt_timezone.utc

#: Core-seed late-Zi policy: a 23:00–23:59 birth belongs to the *next* chart day.
NEXT_CHART_DAY_POLICY_ID = "next-chart-day.v1"


@dataclass(frozen=True)
class Location:
    """Birth geographic coordinates (degrees; lon east-positive)."""

    lat: float
    lon: float


@dataclass(frozen=True)
class ChronometryResolution:
    """The ``resolution.chronometry`` contract plus calendar-half carry-overs.

    The contract fields mirror ``response_example_core.json`` exactly. The last
    two fields are *not* part of that JSON block; they are the derived values
    the calendar half (lunar month/day + year cycle) consumes:

    * ``chart_local_date`` — the civil date the chart is drawn for (late-Zi may
      advance it by one day); the calendar engine converts THIS to a lunar date.
    * ``day_boundary_offset_hours`` — the fixed UTC offset (hours) of
      ``effective_local``; the lunisolar provider floors new-moon UTC instants
      with it (see :class:`bazi_engine.zwds.calendar_provider.SwissephLunisolarCalendar`).
    """

    civil_local: str
    utc: str
    effective_local: str
    effective_standard: str
    timezone: str
    location: Location
    local_time_status: str
    fold: int
    warning: Optional[str]
    hour_branch_id: str
    late_zi_applied: bool
    late_zi_policy_id: str
    # ── derived for the calendar half (not in the chronometry JSON block) ──
    chart_local_date: date
    day_boundary_offset_hours: float


def _iso_z(dt: datetime) -> str:
    """Format a tz-aware datetime as UTC with a trailing ``Z``."""
    return dt.astimezone(_UTC).isoformat().replace("+00:00", "Z")


def hour_branch_index(hour: int) -> int:
    """Earthly-branch index (ZI=0) for a 24-hour clock ``hour``.

    Two-hour double-hours anchored on Zi: 23:00–00:59 → ZI(0),
    01:00–02:59 → CHOU(1), …, 21:00–22:59 → HAI(11).
    """
    return ((hour + 1) // 2) % 12


def resolve_chronometry(
    *,
    datetime_local: str,
    timezone: str,
    lat: float,
    lon: float,
    ambiguous_time: str = "earlier",
    nonexistent_time: str = "error",
    time_standard: str = "CIVIL",
    late_zi_policy_id: str = NEXT_CHART_DAY_POLICY_ID,
) -> ChronometryResolution:
    """Resolve civil birth input into a :class:`ChronometryResolution`.

    Parameters
    ----------
    datetime_local
        Naive ISO-8601 local datetime, e.g. ``"1984-02-01T23:30:00"``.
    timezone
        IANA timezone name, e.g. ``"Asia/Shanghai"``.
    lat, lon
        Birth latitude / longitude in degrees (lon east-positive).
    ambiguous_time
        DST fall-back choice: ``"earlier"`` (fold=0) or ``"later"`` (fold=1).
    nonexistent_time
        DST spring-forward-gap policy: ``"error"`` or ``"shift_forward"``.
    time_standard
        ``"CIVIL"`` | ``"LMT"`` | ``"TLST"``.
    late_zi_policy_id
        Late-Zi chart-date policy id. ``"next-chart-day.v1"`` advances the chart
        date by one day for a 23:00–23:59 birth.

    Raises
    ------
    ZwdsBirthTimeRequiredError
        If ``datetime_local`` is missing/blank.
    bazi_engine.time_utils.LocalTimeError
        If the local time is nonexistent and ``nonexistent_time="error"`` (the
        message is PII-scrubbed by ``resolve_local_iso`` — no birth instant
        leaks).
    ValueError
        If ``time_standard`` is not one of CIVIL / LMT / TLST.
    """
    if datetime_local is None or not str(datetime_local).strip():
        raise ZwdsBirthTimeRequiredError(
            "A birth time is required to resolve ZWDS chronometry."
        )

    # 1. Civil local + DST resolution (raises PII-scrubbed on a real DST gap).
    civil_dt, res = resolve_local_iso(
        datetime_local,
        timezone,
        ambiguous=ambiguous_time,  # type: ignore[arg-type]
        nonexistent=nonexistent_time,  # type: ignore[arg-type]
    )
    birth_utc = civil_dt.astimezone(_UTC)

    # 2. Effective-local per the ruleset time standard. Same instant, relabeled
    #    onto a fixed UTC offset so `utc` stays invariant.
    std = time_standard.upper()
    if std == "CIVIL":
        effective_local = civil_dt
    elif std == "LMT":
        effective_local = birth_utc.astimezone(lmt_tzinfo(lon))
    elif std == "TLST":
        eot_minutes = compute_effective_time_context_from_instant(
            civil_dt, lon
        ).eot_minutes
        tlst_offset_min = lon * 4.0 + eot_minutes
        effective_local = birth_utc.astimezone(
            dt_timezone(timedelta(minutes=tlst_offset_min))
        )
    else:
        raise ValueError(
            "time_standard must be one of 'CIVIL', 'LMT', 'TLST'."
        )

    # 3. Hour branch from the effective-local hour.
    hour = effective_local.hour
    hour_branch = BranchId(hour_branch_index(hour))

    # 4. Late Zi (23:00–23:59) → chart-date advance under next-chart-day.v1.
    late_zi_applied = hour == 23
    eff_date = effective_local.date()
    if late_zi_applied and late_zi_policy_id == NEXT_CHART_DAY_POLICY_ID:
        chart_local_date = eff_date + timedelta(days=1)
    else:
        chart_local_date = eff_date

    # day_boundary_offset_hours: the fixed UTC offset the calendar provider
    # floors new-moon instants with (CIVIL: zone offset; LMT/TLST: solar offset).
    utc_off = effective_local.utcoffset()
    day_boundary_offset_hours = (
        utc_off.total_seconds() / 3600.0 if utc_off is not None else 0.0
    )

    return ChronometryResolution(
        civil_local=civil_dt.isoformat(),
        utc=_iso_z(birth_utc),
        effective_local=effective_local.isoformat(),
        effective_standard=std,
        timezone=timezone,
        location=Location(lat=lat, lon=lon),
        local_time_status=res.status,
        fold=res.fold,
        warning=res.warning,
        hour_branch_id=hour_branch.name,
        late_zi_applied=late_zi_applied,
        late_zi_policy_id=late_zi_policy_id,
        chart_local_date=chart_local_date,
        day_boundary_offset_hours=day_boundary_offset_hours,
    )


# ── calendar half (ZWDS-P1-06): lunisolar + leap policy + year cycle ─────────

#: ZWDS leap *interpretation* policy: a leap birth on day ≤ 15 keeps the repeated
#: month number; on day ≥ 16 it rolls to the next month (design-pack C-08).
#: This is a chart-formula policy, NOT the calendar's astronomical leap
#: determination (that already lives in ``ResolvedLunarDate.is_leap_month``).
LEAP_MONTH_POLICY_ID = "split-after-day-15.guide-v1"

#: Year-cycle basis: the sexagenary year is taken from the *lunar* year label
#: (正月-anchored), Jia-Zi = the year whose label ≡ 4 (mod 60).
YEAR_CYCLE_BASIS_POLICY_ID = "lunar-year.guide-v1"


@dataclass(frozen=True)
class LunarDate:
    """A resolved Chinese lunisolar date — the ``calendar.*_lunar_date`` block.

    Mirrors ``response_example_core.json`` exactly (integers + bool, no engine
    tag): ``{year_label, month, day, is_leap_month, month_length}``.
    """

    year_label: int
    month: int
    day: int
    is_leap_month: bool
    month_length: int


@dataclass(frozen=True)
class YearCycle:
    """The ``calendar.year_cycle`` block: sexagenary year stem/branch + basis.

    ``stem_id`` / ``branch_id`` are the canonical enum *names* (e.g. ``"JIA"``,
    ``"ZI"``) so the block serializes byte-for-byte like the design pack. They
    are two independent typed axes — never a fused ``庚/午`` string (spec §2).
    """

    stem_id: str
    branch_id: str
    basis_policy_id: str


@dataclass(frozen=True)
class CalendarResolution:
    """The ``resolution.calendar`` contract (design-pack ``calendar`` block)."""

    calendar_engine_id: str
    pre_late_zi_lunar_date: LunarDate
    chart_lunar_date: LunarDate
    effective_month_for_chart: int
    leap_month_policy_id: str
    year_cycle: YearCycle
    warnings: Tuple[str, ...]


@dataclass(frozen=True)
class ResolvedZwdsSeed:
    """Downstream ZWDS formula inputs (design-pack §2 variable contract).

    * ``month`` — effective ``m`` (1..12) after the leap-split policy.
    * ``day`` — chart lunar ``d`` (1..30).
    * ``year_stem_index`` — ``y_s`` (0..9, Jia = 0).
    * ``year_branch_index`` — ``y_b`` (0..11, Zi = 0).
    * ``hour_branch_index`` — the double-hour ordinal as a 0-based branch index
      (0..11, Zi = 0); equals the spec's ``h - 1``.
    * ``year_animal_id`` — the zodiac animal of ``y_b`` (a distinct typed axis).
    """

    month: int
    day: int
    year_stem_index: int
    year_branch_index: int
    hour_branch_index: int
    year_animal_id: AnimalId


def effective_month_for_leap_split(
    *, month: int, day: int, is_leap_month: bool
) -> int:
    """Effective ZWDS month ``m`` under ``split-after-day-15.guide-v1``.

    * non-leap lunation → the month itself;
    * leap lunation, day ≤ 15 → the repeated (same) month number;
    * leap lunation, day ≥ 16 → the *next* month number, wrapping 12 → 1.

    Pure arithmetic; no ephemeris. See design-pack ``claim_audit`` C-08.
    """
    if not is_leap_month or day <= 15:
        return month
    return (month % 12) + 1


def year_cycle_for_label(year_label: int) -> Tuple[StemId, BranchId, AnimalId]:
    """Sexagenary year stem/branch + zodiac animal for a lunar ``year_label``.

    ``lunar-year.guide-v1``: ``y_s = mod10(Y - 4)``, ``y_b = mod12(Y - 4)``; the
    animal shares the branch index but is a *separate* typed axis. E.g.
    ``1984 → (JIA, ZI, RAT)``. Pure arithmetic; no ephemeris.
    """
    y_s = mod10(year_label - 4)
    y_b = mod12(year_label - 4)
    return StemId(y_s), BranchId(y_b), AnimalId(y_b)


def _lunar_date(resolved: ResolvedLunarDate) -> LunarDate:
    """Project a provider :class:`ResolvedLunarDate` onto the contract block."""
    return LunarDate(
        year_label=resolved.year_label,
        month=resolved.month,
        day=resolved.day,
        is_leap_month=resolved.is_leap_month,
        month_length=resolved.month_length,
    )


def resolve_calendar_seed(
    chronometry: ChronometryResolution,
    *,
    leap_month_policy_id: str = LEAP_MONTH_POLICY_ID,
    year_cycle_basis_policy_id: str = YEAR_CYCLE_BASIS_POLICY_ID,
) -> Tuple[CalendarResolution, ResolvedZwdsSeed]:
    """Calendar half: chronometry → ``CalendarResolution`` + ``ResolvedZwdsSeed``.

    Builds the lunisolar calendar in the chart's own effective-local frame
    (``day_boundary_offset_hours``), resolves both the chart date and the
    pre-late-Zi date, applies the leap-split policy for the effective month, and
    derives the sexagenary year cycle from the chart lunar-year label.
    """
    calendar = build_core_seed_calendar(
        day_boundary_offset_hours=chronometry.day_boundary_offset_hours
    )

    # Step 5 — convert the chart date and the pre-late-Zi (effective_local) date.
    chart_resolved = calendar.resolve(chronometry.chart_local_date)
    pre_late_zi_date = datetime.fromisoformat(chronometry.effective_local).date()
    pre_resolved = calendar.resolve(pre_late_zi_date)

    # Step 6 — leap-month interpretation → effective month `m`, day `d`.
    effective_month = effective_month_for_leap_split(
        month=chart_resolved.month,
        day=chart_resolved.day,
        is_leap_month=chart_resolved.is_leap_month,
    )

    # Step 7 — sexagenary year cycle from the chart lunar-year label.
    year_stem, year_branch, year_animal = year_cycle_for_label(
        chart_resolved.year_label
    )

    calendar_resolution = CalendarResolution(
        calendar_engine_id=chart_resolved.calendar_engine_id,
        pre_late_zi_lunar_date=_lunar_date(pre_resolved),
        chart_lunar_date=_lunar_date(chart_resolved),
        effective_month_for_chart=effective_month,
        leap_month_policy_id=leap_month_policy_id,
        year_cycle=YearCycle(
            stem_id=year_stem.name,
            branch_id=year_branch.name,
            basis_policy_id=year_cycle_basis_policy_id,
        ),
        warnings=(),
    )

    seed = ResolvedZwdsSeed(
        month=effective_month,
        day=chart_resolved.day,
        year_stem_index=int(year_stem),
        year_branch_index=int(year_branch),
        hour_branch_index=int(BranchId[chronometry.hour_branch_id]),
        year_animal_id=year_animal,
    )
    return calendar_resolution, seed


def resolve_seed(
    *,
    datetime_local: str,
    timezone: str,
    lat: float,
    lon: float,
    ambiguous_time: str = "earlier",
    nonexistent_time: str = "error",
    time_standard: str = "CIVIL",
    late_zi_policy_id: str = NEXT_CHART_DAY_POLICY_ID,
    leap_month_policy_id: str = LEAP_MONTH_POLICY_ID,
    year_cycle_basis_policy_id: str = YEAR_CYCLE_BASIS_POLICY_ID,
) -> Tuple[ChronometryResolution, CalendarResolution, ResolvedZwdsSeed]:
    """Full seed resolution: chronometry + calendar in one call.

    Chains :func:`resolve_chronometry` (steps 1–4) and
    :func:`resolve_calendar_seed` (steps 5–7) so the engine layer resolves the
    entire ``(m, d, y_s, y_b)`` seed and both resolution blocks from raw civil
    birth input with a single entry point.
    """
    chronometry = resolve_chronometry(
        datetime_local=datetime_local,
        timezone=timezone,
        lat=lat,
        lon=lon,
        ambiguous_time=ambiguous_time,
        nonexistent_time=nonexistent_time,
        time_standard=time_standard,
        late_zi_policy_id=late_zi_policy_id,
    )
    calendar_resolution, seed = resolve_calendar_seed(
        chronometry,
        leap_month_policy_id=leap_month_policy_id,
        year_cycle_basis_policy_id=year_cycle_basis_policy_id,
    )
    return chronometry, calendar_resolution, seed
