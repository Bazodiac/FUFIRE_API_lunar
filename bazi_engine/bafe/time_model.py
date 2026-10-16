from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from ..solar_time import EOT_SOURCE_SPENCER, true_solar_time
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
                try:
                    naive = _parse_local_datetime(str(birth_event["local_datetime"]))
                    lon = float(birth_event["geo_lon_deg"])
                    tz_id = birth_event.get("tz_id", None)
                    tz_offset_sec = birth_event.get("tz_offset_sec", None)

                    if tz_id:
                        tz = ZoneInfo(str(tz_id))
                        dt_local, issue = _resolve_local_time(naive, tz, dst_policy)
                        if issue:
                            errors.append(issue)
                        if dt_local is not None:
                            utc_offset = dt_local.utcoffset()
                            offset_h = utc_offset.total_seconds() / 3600.0 if utc_offset else 0.0
                            civil_time = dt_local.hour + dt_local.minute/60.0 + dt_local.second/3600.0
                            day_of_year = int(dt_local.timetuple().tm_yday)
                            tlst_hours = float(true_solar_time(civil_time, lon, day_of_year, offset_h))
                            tlst_quality = "degraded"
                            eot_prov = EOT_SOURCE_SPENCER
                    elif tz_offset_sec is not None:
                        offset_h = float(tz_offset_sec) / 3600.0
                        civil_time = naive.hour + naive.minute/60.0 + naive.second/3600.0
                        day_of_year = int(naive.timetuple().tm_yday)
                        tlst_hours = float(true_solar_time(civil_time, lon, day_of_year, offset_h))
                        tlst_quality = "degraded"
                        eot_prov = EOT_SOURCE_SPENCER
                    else:
                        # No timezone info: cannot compute
                        tlst_quality = "missing"
                except Exception:
                    tlst_quality = "missing"
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
