from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .exc import InputError


def _sanitize_user_input(value: str, max_len: int = 60) -> str:
    """Sanitize user-provided strings before including in error messages.

    Prevents reflected content injection by:
    1. Truncating to max_len
    2. Keeping only alphanumeric, hyphens, underscores, colons, slashes, dots, plus, spaces
    3. Collapsing to avoid any executable-looking content
    """
    safe = value[:max_len]
    # Whitelist: only safe characters for timezone/datetime display
    safe = "".join(c for c in safe if c.isalnum() or c in "-_:/.+T ")
    return safe.strip()


class LocalTimeError(InputError, ValueError):
    """Raised for nonexistent or ambiguous local times (DST edge cases).

    Inherits from both InputError (→ HTTP 422 via global handler) and
    ValueError for backwards compatibility with code that catches ValueError.
    """
    http_status = 422
    error_code = "dst_time_error"

    def __init__(self, message: str, **kwargs: object) -> None:
        # InputError expects keyword-only 'detail'; ValueError expects positional.
        InputError.__init__(self, message)
        ValueError.__init__(self, message)

NonexistentTimePolicy = Literal["error", "shift_forward"]
AmbiguousTimeChoice = Literal["earlier", "later"]
LocalTimeStatus = Literal["ok", "ambiguous", "nonexistent_shifted"]


@dataclass(frozen=True)
class LocalTimeResolution:
    tz: str
    status: LocalTimeStatus
    fold: int
    input_local_iso: str
    resolved_local_iso: str
    resolved_utc_iso: str
    tz_abbrev: Optional[str] = None
    adjusted_minutes: int = 0
    warning: Optional[str] = None


@dataclass(frozen=True)
class ResolvedInstant:
    """Canonical, fold-preserving representation of one physical instant.

    The aware ``civil_local`` value returned by the DST resolver is retained
    directly.  Downstream V2 calculations consume ``utc`` and must never
    reconstruct the instant from a naive string.
    """

    input_local_iso: str
    timezone: str
    civil_local: datetime
    utc: datetime
    fold: int
    status: LocalTimeStatus
    utc_offset_seconds: int
    dst_offset_seconds: int
    tz_abbrev: Optional[str]
    adjusted_minutes: int
    warning_code: Optional[str]
    warning: Optional[str]


# Upper bound for ``nonexistentTime='shift_forward'``. DST gaps are 30–120 min,
# but a zone can skip a whole calendar day (Samoa 2011-12-30 jumped from UTC−10
# to UTC+14: a noon input needs +720 min), so the window covers two full days.
# Owner decision 5 after the sprint-2 review (R2 out-of-range observation).
SHIFT_FORWARD_MAX_MINUTES = 48 * 60

_OUT_OF_RANGE_MESSAGE = (
    "Local time is outside the supported calendar range: converting it to UTC "
    "or applying the timezone offset leaves years 1–9999. Use a date inside "
    "that range."
)


def _roundtrip_ok(naive_local: datetime, tz: ZoneInfo, fold: int) -> bool:
    dt = naive_local.replace(tzinfo=tz, fold=fold)
    try:
        back = dt.astimezone(timezone.utc).astimezone(tz)
    except OverflowError as e:
        # Year 1 / 9999 inputs whose UTC image leaves the datetime range used
        # to surface as HTTP 500 (owner decision 4 after the sprint-2 review,
        # R1 finding F12). It is caller input, so it is a 422.
        raise LocalTimeError(_OUT_OF_RANGE_MESSAGE) from e
    return back.replace(tzinfo=None) == naive_local


def resolve_local_iso(
    birth_local_iso: str,
    tz_name: str,
    *,
    ambiguous: AmbiguousTimeChoice = "earlier",
    nonexistent: NonexistentTimePolicy = "error",
) -> Tuple[datetime, LocalTimeResolution]:
    """Resolve local ISO time with explicit DST handling.

    - Ambiguous times (DST fall-back): choose ``earlier`` (fold=0) or ``later`` (fold=1).
    - Nonexistent times (DST spring-forward gap):
        ``error``: raise LocalTimeError (default).
        ``shift_forward``: advance minute-by-minute to the next valid local time.
    """
    try:
        naive = datetime.fromisoformat(birth_local_iso)
    except ValueError as e:
        # Do NOT echo the caller's raw birth string: even injection-sanitized,
        # it is a subject's birth instant (PII) reflected into a client-facing
        # 422 body. Name the failure class + the expected shape, echo nothing.
        raise LocalTimeError(
            "Invalid date/time format. Expected ISO 8601 local time "
            "(e.g. '2024-02-10T14:30:00').",
        ) from e
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError) as e:
        # Do NOT echo the caller's raw tz string (birth-location PII class —
        # same scrub rationale as the birth-instant messages in this module).
        raise LocalTimeError(
            "Unknown or invalid IANA timezone identifier. Use an IANA "
            "timezone name (e.g. 'Europe/Berlin').",
        ) from e

    ok0 = _roundtrip_ok(naive, tz, fold=0)
    ok1 = _roundtrip_ok(naive, tz, fold=1)

    dt0 = naive.replace(tzinfo=tz, fold=0)
    dt1 = naive.replace(tzinfo=tz, fold=1)
    is_ambiguous = ok0 and ok1 and dt0.utcoffset() != dt1.utcoffset()
    is_nonexistent = (not ok0) and (not ok1)

    chosen_fold = 0 if ambiguous == "earlier" else 1

    if is_nonexistent:
        if nonexistent == "error":
            # Do NOT interpolate the raw birth_local_iso/tz_name: this message
            # is surfaced to API clients as the error body and would reflect a
            # subject's exact birth instant + timezone (PII) on every birth-input
            # endpoint (bazi/western/fusion/chart/chronometry/webhooks/personalize).
            raise LocalTimeError(
                "Nonexistent local time due to DST transition (spring-forward "
                "gap). Provide a valid time or set nonexistentTime='shift_forward'."
            )
        # Shift forward to the next valid minute. DST gaps are 30–120 min; a
        # skipped calendar day (Samoa 2011) needs up to 24 h, see
        # SHIFT_FORWARD_MAX_MINUTES.
        for minutes in range(1, SHIFT_FORWARD_MAX_MINUTES + 1):
            try:
                candidate = naive + timedelta(minutes=minutes)
            except OverflowError as e:
                raise LocalTimeError(_OUT_OF_RANGE_MESSAGE) from e
            if _roundtrip_ok(candidate, tz, fold=0) or _roundtrip_ok(candidate, tz, fold=1):
                dt = candidate.replace(tzinfo=tz, fold=0)
                return dt, LocalTimeResolution(
                    tz=tz_name,
                    status="nonexistent_shifted",
                    fold=0,
                    input_local_iso=birth_local_iso,
                    resolved_local_iso=dt.isoformat(),
                    resolved_utc_iso=dt.astimezone(timezone.utc).isoformat(),
                    tz_abbrev=dt.tzname(),
                    adjusted_minutes=minutes,
                    warning=f"Input local time did not exist (DST gap). "
                            f"Shifted forward by {minutes} min to {dt.isoformat()}.",
                )
        # Raw values omitted from the client-facing message (PII — see above).
        raise LocalTimeError(
            f"Could not resolve nonexistent local time within "
            f"{SHIFT_FORWARD_MAX_MINUTES // 60} hours."
        )

    # Normal or ambiguous
    dt = naive.replace(tzinfo=tz, fold=chosen_fold)
    status: LocalTimeStatus = "ambiguous" if is_ambiguous else "ok"
    warning = None
    if is_ambiguous:
        warning = (
            f"Ambiguous local time during DST fall-back. "
            f"Chosen: {ambiguous} (fold={chosen_fold}, offset={dt.utcoffset()})."
        )
    return dt, LocalTimeResolution(
        tz=tz_name,
        status=status,
        fold=chosen_fold,
        input_local_iso=birth_local_iso,
        resolved_local_iso=dt.isoformat(),
        resolved_utc_iso=dt.astimezone(timezone.utc).isoformat(),
        tz_abbrev=dt.tzname(),
        warning=warning,
    )


def resolve_local_instant(
    local_iso: str,
    tz_name: str,
    *,
    ambiguous: AmbiguousTimeChoice = "earlier",
    nonexistent: NonexistentTimePolicy = "error",
) -> ResolvedInstant:
    """Resolve a local civil timestamp once into a canonical UTC instant.

    Offset-bearing input is rejected because an explicit numeric offset and
    an IANA timezone are competing authorities.  Callers that already know a
    UTC instant should express it as a naive local value with ``timezone=UTC``.
    The legacy :func:`resolve_local_iso` contract remains unchanged.
    """

    if ambiguous not in {"earlier", "later"}:
        raise LocalTimeError("Invalid ambiguous-time policy.")
    if nonexistent not in {"error", "shift_forward"}:
        raise LocalTimeError("Invalid nonexistent-time policy.")

    try:
        parsed = datetime.fromisoformat(local_iso)
    except ValueError as exc:
        raise LocalTimeError(
            "Invalid date/time format. Expected ISO 8601 local time "
            "(e.g. '2024-02-10T14:30:00').",
        ) from exc
    if parsed.tzinfo is not None or parsed.utcoffset() is not None:
        raise LocalTimeError(
            "Offset-bearing local datetime is not allowed when an IANA "
            "timezone is supplied. Provide a local datetime without an offset."
        )

    civil_local, resolution = resolve_local_iso(
        local_iso,
        tz_name,
        ambiguous=ambiguous,
        nonexistent=nonexistent,
    )
    resolved_utc = civil_local.astimezone(timezone.utc)
    utc_offset = civil_local.utcoffset()
    dst_offset = civil_local.dst()
    if utc_offset is None:
        raise LocalTimeError("Resolved local datetime has no UTC offset.")

    warning_code: Optional[str] = None
    warning: Optional[str] = None
    if resolution.status == "ambiguous":
        warning_code = "ambiguous_local_time_resolved"
        warning = "Ambiguous local time resolved using the requested fold policy."
    elif resolution.status == "nonexistent_shifted":
        warning_code = "nonexistent_local_time_shifted"
        warning = "Nonexistent local time shifted forward to the next valid minute."

    return ResolvedInstant(
        input_local_iso=local_iso,
        timezone=tz_name,
        civil_local=civil_local,
        utc=resolved_utc,
        fold=civil_local.fold,
        status=resolution.status,
        utc_offset_seconds=int(utc_offset.total_seconds()),
        dst_offset_seconds=int(dst_offset.total_seconds()) if dst_offset is not None else 0,
        tz_abbrev=civil_local.tzname(),
        adjusted_minutes=resolution.adjusted_minutes,
        warning_code=warning_code,
        warning=warning,
    )


def parse_local_iso(birth_local_iso: str, tz_name: str, *, strict: bool, fold: int) -> datetime:
    try:
        naive = datetime.fromisoformat(birth_local_iso)
    except ValueError as e:
        # Do NOT echo the caller's raw birth string: even injection-sanitized,
        # it is a subject's birth instant (PII) reflected into a client-facing
        # 422 body. Name the failure class + the expected shape, echo nothing.
        raise LocalTimeError(
            "Invalid date/time format. Expected ISO 8601 local time "
            "(e.g. '2024-02-10T14:30:00').",
        ) from e
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, KeyError) as e:
        # Do NOT echo the caller's raw tz string (birth-location PII class —
        # same scrub rationale as the birth-instant messages in this module).
        raise LocalTimeError(
            "Unknown or invalid IANA timezone identifier. Use an IANA "
            "timezone name (e.g. 'Europe/Berlin').",
        ) from e
    dt = naive.replace(tzinfo=tz, fold=fold)

    if not strict:
        return dt

    # Round-trip check local -> utc -> local
    utc = dt.astimezone(timezone.utc)
    back = utc.astimezone(tz)

    if back.replace(tzinfo=None) != naive:
        # Do NOT interpolate the raw birth_local_iso/tz_name OR the normalized
        # round-trip instant (back.isoformat()): this message is surfaced to API
        # clients as the error body (bazi_engine_error_handler -> 422) and would
        # reflect a subject's exact birth instant + timezone (PII). This strict
        # round-trip raise is the sibling leak site of resolve_local_iso's
        # nonexistent-time raises above, reachable on every endpoint that builds
        # BaziInput from the raw request date with the default
        # strict_local_time=True and no resolve_local_iso pre-resolution
        # (impact/active, experience/bootstrap + daily + signature-delta,
        # calculate/bazi/dayun). Mirrors the scrub e5d4207 applied to
        # resolve_local_iso's messages -- name the DST failure mode + the
        # remedies, interpolate nothing.
        raise LocalTimeError(
            "Nonexistent or normalized local time due to a DST transition "
            "(spring-forward gap). Provide a valid local time, choose an "
            "explicit fold, or set nonexistentTime='shift_forward' / "
            "strict_local_time=False to auto-resolve."
        )
    return dt

def lmt_tzinfo(longitude_deg: float) -> timezone:
    return timezone(timedelta(seconds=longitude_deg * 240.0))

def to_chart_local(birth_local: datetime, longitude_deg: float, time_standard: str) -> Tuple[datetime, datetime]:
    birth_utc = birth_local.astimezone(timezone.utc)
    if time_standard.upper() == "LMT":
        return birth_utc.astimezone(lmt_tzinfo(longitude_deg)), birth_utc
    return birth_local, birth_utc

def apply_day_boundary(dt_local: datetime, day_boundary: str) -> datetime:
    if day_boundary.lower() == "zi":
        return dt_local + timedelta(hours=1)
    return dt_local
