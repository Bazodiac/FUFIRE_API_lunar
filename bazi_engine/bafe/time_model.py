from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..time_context import compute_effective_time_context_from_instant
from .errors import make_issue


def _parse_local_datetime(local_dt_str: str) -> datetime:
    # Accept ISO string without timezone
    return datetime.fromisoformat(local_dt_str)

def _detect_local_time_status(naive: datetime, tz: ZoneInfo) -> Tuple[str, Optional[int]]:
    """
    Returns (status, fold_to_use)
    status in {"ok", "ambiguous", "nonexistent"}
    fold_to_use: suggested fold for ambiguous times (0 by default)
    """
    ok_folds: List[int] = []
    offsets: List[Optional[timedelta]] = []
    for fold in (0, 1):
        dt = naive.replace(tzinfo=tz, fold=fold)
        utc = dt.astimezone(timezone.utc)
        back = utc.astimezone(tz).replace(tzinfo=None)
        if back == naive:
            ok_folds.append(fold)
            offsets.append(dt.utcoffset())
    if len(ok_folds) == 0:
        return "nonexistent", None
    if len(ok_folds) == 2:
        # ambiguous if offsets differ
        if offsets[0] != offsets[1]:
            return "ambiguous", 0
        return "ok", ok_folds[0]
    return "ok", ok_folds[0]

def _resolve_local_time(naive: datetime, tz: ZoneInfo, dst_policy: str) -> Tuple[Optional[datetime], Optional[Dict[str, Any]]]:
    """
    Resolve local time according to dst_policy.
    Returns (dt_local, issue) where issue is an Issue dict if error policy triggers.
    """
    status, fold_suggested = _detect_local_time_status(naive, tz)
    if status == "ok":
        fold = 0 if fold_suggested is None else fold_suggested
        return naive.replace(tzinfo=tz, fold=fold), None
    if status == "ambiguous":
        if dst_policy == "error":
            return None, make_issue(
                "DST_AMBIGUOUS_LOCAL_TIME",
                "Ambiguous local time (DST fold) with dst_policy=error",
                path="/birth_event/local_datetime",
                details={"tz_id": str(tz.key), "local_datetime": naive.isoformat()},
            )
        fold = 0 if dst_policy == "earlier" else 1
        return naive.replace(tzinfo=tz, fold=fold), None
    # nonexistent
    if dst_policy == "error":
        return None, make_issue(
            "DST_NONEXISTENT_LOCAL_TIME",
            "Nonexistent local time (DST gap) with dst_policy=error",
            path="/birth_event/local_datetime",
            details={"tz_id": str(tz.key), "local_datetime": naive.isoformat()},
        )
    # For earlier/later, do a deterministic nudge to the nearest valid time.
    # This is a simple policy: shift by +60min for 'later', -60min for 'earlier'.
    delta = timedelta(hours=1) if dst_policy == "later" else -timedelta(hours=1)
    nudged = naive + delta
    # Re-evaluate; if still invalid, fallback to error
    status2, fold2 = _detect_local_time_status(nudged, tz)
    if status2 != "ok":
        return None, make_issue(
            "DST_NONEXISTENT_LOCAL_TIME",
            "Could not resolve nonexistent local time via deterministic nudge",
            path="/birth_event/local_datetime",
            details={"tz_id": str(tz.key), "local_datetime": naive.isoformat(), "nudged": nudged.isoformat()},
        )
    fold = 0 if fold2 is None else fold2
    return nudged.replace(tzinfo=tz, fold=fold), None


def _aware_birth_instant(
    birth_event: Dict[str, Any], dst_policy: str, errors: List[Dict[str, Any]]
) -> Optional[datetime]:
    """The birth instant as an aware datetime, or ``None`` when the event
    carries neither ``tz_id`` nor ``tz_offset_sec``. A DST issue raised by the
    ``dst_policy`` is appended to ``errors`` and yields ``None``."""
    naive = _parse_local_datetime(str(birth_event["local_datetime"]))
    tz_id = birth_event.get("tz_id", None)
    tz_offset_sec = birth_event.get("tz_offset_sec", None)
    if tz_id:
        dt_aware, issue = _resolve_local_time(naive, ZoneInfo(str(tz_id)), dst_policy)
        if issue:
            errors.append(issue)
        return dt_aware
    if tz_offset_sec is not None:
        return naive.replace(tzinfo=timezone(timedelta(seconds=int(tz_offset_sec))))
    return None


def _tlst_from_birth_event(
    birth_event: Dict[str, Any], dst_policy: str, errors: List[Dict[str, Any]]
) -> Tuple[Optional[float], Optional[str], str]:
    """``(tlst_hours, eot_provenance, tlst_quality)`` for a TLST validation.

    Owner decision 1 after the sprint-2 TLST review: ``/validate`` uses the
    SAME UTC-axis decomposition as ``/calculate/tst``, the BaZi trace and
    chronometry (``time_context``, Meeus EoT, pure math — no Swiss-Ephemeris
    call) instead of the day-of-year Spencer approximation that could put
    the hour branch on the other side of a 2-hour edge (R2 review finding
    F2). ``tlst_quality`` keeps its UT1 semantics: ``"degraded"`` means
    computed without a UT1 time scale, not an approximate EoT.
    """
    try:
        dt_aware = _aware_birth_instant(birth_event, dst_policy, errors)
        if dt_aware is None:
            return None, None, "missing"
        ctx = compute_effective_time_context_from_instant(dt_aware, float(birth_event["geo_lon_deg"]))
        return float(ctx.tlst_hours), ctx.eot_source, "degraded"
    except Exception:
        return None, None, "missing"


def evaluate_time(
    *,
    engine_config: Dict[str, Any],
    birth_event: Optional[Dict[str, Any]],
    positions_override: Optional[Dict[str, Any]],
    compliance_mode: str,
    now_utc: datetime,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], Dict[str, Any], Optional[float]]:
    """
    Returns (errors, warnings, time_evidence, component_status, tlst_hours)
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    time_standard = str(engine_config.get("time_standard", "CIVIL")).upper()
    dst_policy = str(engine_config.get("dst_policy", "error"))
    if birth_event and isinstance(birth_event.get("dst_policy"), str):
        dst_policy = str(birth_event["dst_policy"])

    # Determine UT1/TT availability from overrides (best-effort)
    ut1_quality = "missing"
    tt_quality = "missing"
    if positions_override and isinstance(positions_override, dict):
        ts = str(positions_override.get("time_scale", "")).upper()
        if ts == "UT1":
            ut1_quality = "ok"
        if ts == "TT":
            tt_quality = "ok"

    # TLST computation (optional)
    tlst_hours: Optional[float] = None
    tlst_quality = "missing"
    eot_prov: Optional[str] = None

    time_fallback = engine_config.get("time_fallback_policy") or {}
    allow_compute_tlst_without_ut1 = bool(time_fallback.get("allow_compute_tlst_without_ut1", False))

    if time_standard == "TLST":
        if birth_event and isinstance(birth_event, dict):
            # Compute TLST even without UT1 if explicitly allowed (or in non-strict modes).
            if allow_compute_tlst_without_ut1 or ut1_quality != "missing" or compliance_mode in {"RELAXED", "DEV"}:
                tlst_hours, eot_prov, tlst_quality = _tlst_from_birth_event(birth_event, dst_policy, errors)
            else:
                tlst_quality = "missing"
        else:
            tlst_quality = "missing"

    # Evaluate local time validity even if time_standard != TLST (policy gate)
    if birth_event and isinstance(birth_event, dict):
        tz_id = birth_event.get("tz_id", None)
        if tz_id:
            try:
                naive = _parse_local_datetime(str(birth_event["local_datetime"]))
                tz = ZoneInfo(str(tz_id))
                _, issue = _resolve_local_time(naive, tz, dst_policy)
                if issue:
                    errors.append(issue)
            except Exception:
                # No dedicated error code in contract; mark degraded via notes only.
                pass

    # In STRICT compliance, missing TT can be an error if required downstream.
    # The rule for "required" is checked in service.py (needs ruleset).
    # Here we only report quality.

    time_evd: Dict[str, Any] = {
        "time_standard": time_standard if time_standard in {"CIVIL","LMT","TLST"} else "CIVIL",
        "dst_policy": dst_policy if dst_policy in {"error","earlier","later"} else "error",
        "ut1_quality": ut1_quality,
        "tt_quality": tt_quality,
        "tlst_quality": tlst_quality,
        "eot_provenance": eot_prov,
        "uncertainty_budget_sec": None,
    }

    status = "OK"
    notes: List[str] = []
    if errors:
        status = "FAIL"
    elif warnings or (time_standard == "TLST" and tlst_quality in {"missing"} and compliance_mode == "STRICT"):
        status = "DEGRADED"
    notes.append(f"time_standard={time_standard}")
    notes.append(f"dst_policy={dst_policy}")
    if time_standard == "TLST":
        notes.append(f"tlst_quality={tlst_quality}")
    comp = {"status": status, "notes": notes}

    return errors, warnings, time_evd, comp, tlst_hours
