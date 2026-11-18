"""
birth_time.py — Level 4: birth input without a clock time, and what an unknown
birth time leaves open.

Used only by the endpoints that compute a natal chart (``/calculate/bazi``,
``/bazi/trace``, ``/bazi/natal``, ``/bazi/wuxing``, ``/calculate/western``,
``/calculate/fusion``, ``/fusion/vector-map``, ``/bazi/dayun``). Endpoints where
a bare date means a whole day (transits, daily, tst, chronometry, experience,
personalize, match, synastry) keep calling ``time_utils.resolve_local_iso``
directly, which still reads a bare date as 00:00.

Rules (docs/precision/date-only-birth-input.md):

* A ``date`` without a time part is computed at 12:00 civil local time
  (``reference_time_policy = "date_only_noon"``) and reported as
  ``birth_time_known = false``, whatever the request flag says. A noon that does
  not exist locally (a skipped calendar day) is a 422, never shifted.
* A ``date`` with a time part is computed at exactly that time. With
  ``birth_time_known = false`` only the precision block is marked, so a client
  can sample a time window and compare the values.
* With an unknown birth time the precision block names every value that can
  change within the civil day: pillars whose boundary falls inside the day and
  western bodies that change sign during the day.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from .bazi import compute_bazi
from .time_utils import NonexistentTimePolicy, resolve_local_iso
from .types import BaziInput, Fold
from .western import compute_western_chart

# 12:00 civil time keeps the true-solar day on the calendar day wherever the zone
# offset and the longitude differ by less than 12 hours — everywhere except the
# zones east of the date line at western longitudes (Pacific/Kiritimati since
# 1995, Pacific/Apia since 2012), where the whole civil day is the previous solar
# day (docs/precision/date-only-birth-input.md, measured).
DATE_ONLY_REFERENCE_LOCAL_TIME = "12:00:00"
ReferenceTimePolicy = Literal["date_only_noon"]
REFERENCE_TIME_POLICY_DATE_ONLY_NOON: ReferenceTimePolicy = "date_only_noon"
BIRTH_TIME_UNKNOWN = "BIRTH_TIME_UNKNOWN"

# Bounds of the civil day: (local time, fold, nonexistent policy). Midnight can
# fall into a DST gap (shift to the first valid minute); on a fall-back day the
# end of the day is the later occurrence of 23:59:59.
_DAY_START: Tuple[str, Fold, NonexistentTimePolicy] = ("00:00:00", 0, "shift_forward")
_DAY_END: Tuple[str, Fold, NonexistentTimePolicy] = ("23:59:59", 1, "shift_forward")

_PILLAR_ORDER = ("year", "month", "day")


@dataclass(frozen=True)
class BirthTimeInput:
    """How a birth-input ``date`` is computed.

    ``local_iso`` is the local wall time that goes into the engine;
    ``nonexistent`` the DST-gap policy for it (always ``error`` for a bare
    date: a shifted noon would no longer be the documented reference time).
    """

    local_iso: str
    date_only: bool
    birth_time_known: bool
    nonexistent: NonexistentTimePolicy
    reference_time_policy: Optional[ReferenceTimePolicy] = None

    @property
    def warnings(self) -> List[str]:
        return [] if self.birth_time_known else [BIRTH_TIME_UNKNOWN]


def date_only_day(text: str) -> Optional[date]:
    """The calendar date when ``text`` carries no time part, else ``None``.

    "No time part" means: Python's own ``date.fromisoformat`` reads it. A string
    with any time part (``T00:00`` included) is not date-only.
    """
    try:
        return date.fromisoformat(text.strip())
    except ValueError:
        return None


def resolve_birth_time_input(
    text: str, birth_time_known: bool, nonexistent: NonexistentTimePolicy,
) -> BirthTimeInput:
    """Apply the date-only rule to a birth-input ``date``."""
    day = date_only_day(text)
    if day is None:
        return BirthTimeInput(
            local_iso=text,
            date_only=False,
            birth_time_known=birth_time_known,
            nonexistent=nonexistent,
        )
    return BirthTimeInput(
        local_iso=f"{day.isoformat()}T{DATE_ONLY_REFERENCE_LOCAL_TIME}",
        date_only=True,
        birth_time_known=False,
        nonexistent="error",
        reference_time_policy=REFERENCE_TIME_POLICY_DATE_ONLY_NOON,
    )


def civil_day_bounds(day: date, tz_name: str) -> Tuple[datetime, datetime]:
    """First and last second of the local civil ``day`` as aware datetimes."""
    bounds = []
    for hms, fold, gap in (_DAY_START, _DAY_END):
        dt, _ = resolve_local_iso(
            f"{day.isoformat()}T{hms}", tz_name,
            ambiguous="earlier" if fold == 0 else "later", nonexistent=gap,
        )
        bounds.append(dt)
    return bounds[0], bounds[1]


def _pillar_pair(inp: BaziInput, at: datetime) -> Dict[str, Tuple[int, int]]:
    res = compute_bazi(replace(
        inp,
        birth_local=at.replace(tzinfo=None).isoformat(),
        fold=at.fold,  # type: ignore[arg-type]
        strict_local_time=True,
    ))
    return {
        name: (getattr(res.pillars, name).stem_index, getattr(res.pillars, name).branch_index)
        for name in _PILLAR_ORDER
    }


def provisional_pillars(inp: BaziInput, day: date) -> List[str]:
    """Pillars (of year, month, day) that differ between the two ends of the civil day.

    A pillar changes at most once inside one day, so comparing the two ends finds
    every boundary in the day: the day pillar when the day boundary of the
    requested time standard falls inside the civil day (under TLST almost every
    day), the month pillar on a jie (节) day, the year pillar on the Li Chun day.
    The hour pillar is not listed here; it is always provisional.
    """
    start, end = civil_day_bounds(day, inp.timezone)
    at_start = _pillar_pair(inp, start)
    at_end = _pillar_pair(inp, end)
    return [name for name in _PILLAR_ORDER if at_start[name] != at_end[name]]


def _signs(chart: Dict[str, Any]) -> Dict[str, int]:
    return {
        name: int(float(data["longitude"]) // 30) % 12
        for name, data in chart.get("bodies", {}).items()
        if "error" not in data and "longitude" in data
    }


def provisional_bodies(
    day: date, tz_name: str, lat: float, lon: float, *, zodiac_mode: str = "tropical",
) -> List[str]:
    """Western bodies (names as in ``bodies``) whose sign changes during the civil day."""
    start, end = civil_day_bounds(day, tz_name)
    signs = [
        _signs(compute_western_chart(dt.astimezone(timezone.utc), lat, lon, zodiac_mode=zodiac_mode))
        for dt in (start, end)
    ]
    return [name for name, sign in signs[0].items() if signs[1].get(name, sign) != sign]
