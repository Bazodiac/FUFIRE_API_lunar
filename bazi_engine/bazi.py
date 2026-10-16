from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import swisseph as swe

from .bafe.mapping import hour_branch_index_from_tlst
from .bafe.ruleset_loader import (
    hour_stem_for_day_stem,
    load_ruleset,
    month_stem_for_year_stem,
)
from .bazi_rules import day_offset_from_ruleset
from .constants import DAY_OFFSET
from .ephemeris import SwissEphBackend, datetime_utc_to_jd_ut, jd_ut_to_datetime_utc
from .exc import CalculationError, NotSupportedError
from .jieqi import compute_24_solar_terms_for_window, compute_month_boundaries_from_lichun
from .time_context import EffectiveTimeContext, compute_effective_time_context_from_instant
from .time_utils import apply_day_boundary, parse_local_iso, to_chart_local
from .types import BaziInput, BaziResult, FourPillars, Pillar, SolarTerm

_DEFAULT_RULESET_ID = "standard_bazi_2026"

def jdn_gregorian(y: int, m: int, d: int) -> int:
    a = (14 - m) // 12
    y2 = y + 4800 - a
    m2 = m + 12 * a - 3
    return d + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100 + y2 // 400 - 32045

def sexagenary_day_index_from_date(y: int, m: int, d: int, offset: int = DAY_OFFSET) -> int:
    return (jdn_gregorian(y, m, d) + offset) % 60

def pillar_from_index60(idx60: int) -> Pillar:
    return Pillar(idx60 % 10, idx60 % 12)

def year_pillar_from_solar_year(solar_year: int) -> Pillar:
    idx60 = (solar_year - 1984) % 60
    return pillar_from_index60(idx60)

def month_pillar_from_year_stem(
    year_stem_index: int,
    month_index: int,
    ruleset: dict[str, object] | None = None,
) -> Pillar:
    branch_index = (2 + month_index) % 12
    if ruleset is not None:
        stem_index = month_stem_for_year_stem(ruleset, year_stem_index, month_index)
    else:
        stem_index = (year_stem_index * 2 + 2 + month_index) % 10
    return Pillar(stem_index, branch_index)

def hour_branch_index(dt_local: datetime) -> int:
    return ((dt_local.hour + 1) // 2) % 12

def hour_pillar_from_day_stem(
    day_stem_index: int,
    hour_branch: int,
    ruleset: dict[str, object] | None = None,
) -> Pillar:
    if ruleset is not None:
        stem_index = hour_stem_for_day_stem(ruleset, day_stem_index, hour_branch)
    else:
        stem_index = (day_stem_index * 2 + hour_branch) % 10
    return Pillar(stem_index, hour_branch)

def _load_ruleset_or_none() -> dict[str, Any] | None:
    try:
        return load_ruleset(_DEFAULT_RULESET_ID)
    except (FileNotFoundError, ValueError):
        return None


def _ruleset_or_empty(ruleset: dict[str, Any] | None) -> dict[str, Any]:
    return ruleset if ruleset is not None else {}


def _day_offset_for_input(inp: BaziInput, ruleset: dict[str, Any] | None) -> int:
    if inp.day_anchor_date_iso and inp.day_anchor_pillar_idx is not None:
        anchor_dt = datetime.fromisoformat(inp.day_anchor_date_iso)
        anchor_jdn = jdn_gregorian(anchor_dt.year, anchor_dt.month, anchor_dt.day)
        return (inp.day_anchor_pillar_idx - anchor_jdn) % 60
    if ruleset is None:
        return DAY_OFFSET
    effective_ruleset: dict[str, Any] = _ruleset_or_empty(ruleset)
    return day_offset_from_ruleset(effective_ruleset)


def _effective_time_context_for_input(
    inp: BaziInput,
    birth_local_dt: datetime,
) -> EffectiveTimeContext | None:
    """TLST context for a TLST request, built from the *resolved* aware
    birth datetime so the DST fold chosen upstream is honoured
    (DEV-2026-010)."""
    if inp.time_standard != "TLST":
        return None
    return compute_effective_time_context_from_instant(birth_local_dt, inp.longitude_deg)


def _dt_for_day_pillar(
    inp: BaziInput,
    chart_local_dt: datetime,
    ruleset: dict[str, Any] | None,
    ctx: EffectiveTimeContext | None,
) -> datetime:
    day_change_policy = (ruleset or {}).get("day_change_policy", {}) or {}
    if ctx is None:
        # CIVIL / LMT: chart_local_dt already carries the standard's own
        # calendar date (LMT via to_chart_local); legacy boundary rule.
        return apply_day_boundary(chart_local_dt, inp.day_boundary)

    # TLST — FBP-TST-005 (DEV-2026-011, owner decision E5-A): the day pillar
    # follows the APPARENT-SOLAR calendar date, exactly as the LMT path
    # follows the LMT date. chart_local_dt is civil for TLST (TLST is not a
    # tzinfo, FBP-01-006), so shift it by the day the TLST instant falls on.
    solar_day_dt = chart_local_dt + timedelta(days=ctx.date_rollover)
    if inp.day_boundary != "zi":
        return solar_day_dt
    # The zi decision for a TLST request is always taken on the TLST hour;
    # the ruleset only parameterises ``zi_start_hour``. (Before S-4 a ruleset
    # without ``time_standard_for_day_rollover == "TLST"`` fell through to
    # ``apply_day_boundary`` — the civil +1 h rule applied to the solar
    # date, a mixed rule that double-counted the rollover.)
    zi_start = float(day_change_policy.get("zi_start_hour", 23.0))
    if ctx.tlst_hours >= zi_start:
        return solar_day_dt + timedelta(days=1)
    return solar_day_dt


def _month_index_for_chart(
    chart_local_dt: datetime,
    month_bounds_local: list[datetime],
) -> int:
    for k in range(12):
        if month_bounds_local[k] <= chart_local_dt < month_bounds_local[k + 1]:
            return k
    return 11


def _solar_terms_for_result(
    backend: SwissEphBackend,
    month_bounds_ut: list[float],
    chart_local_dt: datetime,
    accuracy_seconds: float,
) -> list[SolarTerm] | None:
    try:
        term_pairs = compute_24_solar_terms_for_window(
            backend,
            month_bounds_ut[0],
            month_bounds_ut[-1],
            accuracy_seconds=accuracy_seconds,
        )
        return [
            SolarTerm(
                index=idx,
                target_lon_deg=15.0 * idx,
                utc_dt=jd_ut_to_datetime_utc(jd),
                local_dt=jd_ut_to_datetime_utc(jd).astimezone(chart_local_dt.tzinfo),
            )
            for (idx, jd) in term_pairs
        ]
    except Exception:
        return None


def _lichun_jd_ut_for_year(year: int, backend: SwissEphBackend) -> float:
    jd0 = swe.julday(year, 1, 1, 0.0)
    result = backend.solcross_ut(315.0, jd0)
    if result is None:
        raise CalculationError(
            f"Failed to find LiChun crossing for year {year}",
            detail={"year": year, "target_lon_deg": 315.0},
        )
    return float(result)

def compute_bazi(inp: BaziInput) -> BaziResult:
    if inp.ephemeris_backend.lower() != "swisseph":
        raise NotSupportedError("v0.2 ships a skyfield stub only; swisseph is implemented.")

    # FBP-02-006: month_boundary_scheme is vestigial — the ruleset's
    # month_boundary block is the actual source of truth. Warn callers
    # who set a non-default value so they know it has no effect.
    if inp.month_boundary_scheme != "jie_only":
        import warnings as _warnings
        _warnings.warn(
            f"BaziInput.month_boundary_scheme={inp.month_boundary_scheme!r} "
            "has no effect on the computed pillars. The active "
            "month-boundary policy is read from the ruleset's "
            "`month_boundary` block. This field is deprecated and "
            "will be removed in /v2.",
            DeprecationWarning,
            stacklevel=2,
        )

    ruleset = _load_ruleset_or_none()

    backend = SwissEphBackend(ephe_path=inp.ephe_path)

    birth_local_dt = parse_local_iso(
        inp.birth_local,
        inp.timezone,
        strict=inp.strict_local_time,
        fold=int(inp.fold),
    )
    chart_local_dt, birth_utc_dt = to_chart_local(birth_local_dt, inp.longitude_deg, inp.time_standard)

    jd_ut = datetime_utc_to_jd_ut(birth_utc_dt)
    delta_t_seconds = backend.delta_t_seconds(jd_ut)
    jd_tt = backend.jd_tt_from_jd_ut(jd_ut)

    # Year by LiChun
    y = chart_local_dt.year
    jd_lichun_this = _lichun_jd_ut_for_year(y, backend)
    lichun_this_local = jd_ut_to_datetime_utc(jd_lichun_this).astimezone(chart_local_dt.tzinfo)

    before_lichun = chart_local_dt < lichun_this_local
    if before_lichun:
        solar_year = y - 1
        jd_lichun_used = _lichun_jd_ut_for_year(y - 1, backend)
        jd_lichun_next = jd_lichun_this
    else:
        solar_year = y
        jd_lichun_used = jd_lichun_this
        jd_lichun_next = _lichun_jd_ut_for_year(y + 1, backend)

    year_p = year_pillar_from_solar_year(solar_year)

    # Month boundaries
    month_bounds_ut = compute_month_boundaries_from_lichun(
        backend,
        jd_lichun_used,
        accuracy_seconds=inp.accuracy_seconds,
    )
    month_bounds_local = [jd_ut_to_datetime_utc(jd).astimezone(chart_local_dt.tzinfo) for jd in month_bounds_ut]

    month_index = _month_index_for_chart(chart_local_dt, month_bounds_local)
    month_p = month_pillar_from_year_stem(year_p.stem_index, month_index, ruleset=ruleset)

    ctx = _effective_time_context_for_input(inp, birth_local_dt)

    calculated_offset = _day_offset_for_input(inp, ruleset)
    dt_for_day = _dt_for_day_pillar(inp, chart_local_dt, ruleset, ctx)

    day_idx60 = sexagenary_day_index_from_date(
        dt_for_day.year, dt_for_day.month, dt_for_day.day,
        offset=calculated_offset,
    )
    day_p = pillar_from_index60(day_idx60)

    # Hour pillar — reuse pre-computed ctx if available.
    if ctx is not None:
        hb = hour_branch_index_from_tlst(ctx.tlst_hours)
    else:
        hb = hour_branch_index(chart_local_dt)
    hour_p = hour_pillar_from_day_stem(day_p.stem_index, hb, ruleset=ruleset)

    pillars = FourPillars(year=year_p, month=month_p, day=day_p, hour=hour_p)

    solar_terms = _solar_terms_for_result(
        backend,
        month_bounds_ut,
        chart_local_dt,
        inp.accuracy_seconds,
    )

    return BaziResult(
        input=inp,
        pillars=pillars,
        birth_local_dt=birth_local_dt,
        birth_utc_dt=birth_utc_dt,
        chart_local_dt=chart_local_dt,
        jd_ut=jd_ut,
        jd_tt=jd_tt,
        delta_t_seconds=delta_t_seconds,
        lichun_local_dt=jd_ut_to_datetime_utc(jd_lichun_used).astimezone(chart_local_dt.tzinfo),
        month_boundaries_local_dt=month_bounds_local,
        month_index=month_index,
        solar_year=solar_year,
        is_before_lichun=before_lichun,
        lichun_next_local_dt=jd_ut_to_datetime_utc(jd_lichun_next).astimezone(chart_local_dt.tzinfo),
        solar_terms_local_dt=solar_terms,
        chart_day_dt=dt_for_day,
    )
