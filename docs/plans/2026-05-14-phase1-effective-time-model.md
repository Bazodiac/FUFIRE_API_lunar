# BAZI-PRECISION-V2 Phase 1 — Effective Time Model

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `TLST` as an explicit, opt-in time standard alongside `CIVIL` and `LMT`, and ship a typed `EffectiveTimeContext` that the BaZi core can consume in Phase 2. **No `/v1` default behavior change.** Pillars are still derived from CIVIL/LMT in this phase — TLST flows only into diagnostic outputs (trace + `/calculate/tst` consistency).

**Architecture:** Five small additive changes plus one new module, gated by tests. The new module `bazi_engine/time_context.py` becomes the single source for converting `(birth_local, tz, longitude)` → effective time decomposition. `/calculate/tst` is refactored to consume the same source so the two surfaces cannot drift. The router-layer `Literal` types are widened to accept `"TLST"`, but `compute_bazi()` is *not* touched — sending `time_standard="TLST"` makes the engine route through its existing LMT path while the trace surfaces what TLST *would* be. That asymmetry is deliberate Phase-1 scope; Phase 2 (FBP-02-005) wires TLST into the actual hour-branch derivation.

**Tech Stack:** Python 3.10+, Pydantic 2, FastAPI, pytest. No new runtime dependencies. `bazi_engine/solar_time.py` remains pure / stdlib-only (enforced by `tests/test_import_hierarchy.py::test_solar_time_has_no_internal_imports`).

**Non-negotiables (Release-Gate §0):**
- `/v1` default stays `CIVIL`.
- CIVIL, LMT, TLST never aliased.
- TLST is **not** a `tzinfo`. It is apparent solar time + day-rollover offset.
- `solar_time.py` stays pure.
- Existing CIVIL/LMT golden cases stay green.

**Pre-flight (already verified):**
- `bazi_engine/types.py:9` — `TimeStandard = Literal["CIVIL", "LMT"]`.
- `bazi_engine/types.py:41` — `BaziInput.time_standard: TimeStandard = "CIVIL"`.
- `bazi_engine/routers/bazi.py:49` — `BaziRequest.standard: Literal["CIVIL", "LMT"]` (own copy).
- `bazi_engine/routers/chart.py:51` — `time_standard: Literal["CIVIL", "LMT"]` (own copy).
- `bazi_engine/routers/fusion.py:255-278` — `/calculate/tst` already uses `equation_of_time()` and computes `TST = (civil_hours + delta_t_long + E_t) % 24` inline. This is the formula `EffectiveTimeContext.tlst_hours` must match. **⚠ Retro-note 2026-10-15:** this inline formula omits the zone offset (`civil` instead of `UTC`) and is wrong for every non-UTC zone — DEV-2026-009. Do not treat it as the reference; see `docs/plans/2026-10-15-true-solar-time-remediation.md`.
- `bazi_engine/solar_time.py:17-60` — `equation_of_time()` and `true_solar_time()` available, stdlib-only.

---

## Task 1 — FBP-01-001: Widen `TimeStandard` to accept `TLST`

**Why:** TLST cannot be selected today (`Literal["CIVIL", "LMT"]`). Step 1 makes it a valid value at the type / API boundary without changing engine behavior.

**Files:**
- Modify: `bazi_engine/types.py:9`
- Modify: `bazi_engine/routers/bazi.py:49` (BaziRequest.standard)
- Modify: `bazi_engine/routers/chart.py:51` (time_standard)
- Test: `tests/test_endpoint_negative.py` (extend); `tests/test_time_standard_acceptance.py` (new)

### Step 1 — Write failing test (TLST accepted, INVALID still 422)

Create `tests/test_time_standard_acceptance.py`:

```python
"""FBP-01-001 — TLST is accepted at the API boundary; INVALID still rejected."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from bazi_engine.app import app

client = TestClient(app)
BASE = {
    "date": "2024-02-10T14:30:00",
    "tz": "Europe/Berlin",
    "lon": 13.405, "lat": 52.52,
}


@pytest.mark.parametrize("std", ["CIVIL", "LMT", "TLST"])
def test_calculate_bazi_accepts_time_standard(std):
    r = client.post("/calculate/bazi", json={**BASE, "standard": std})
    # 200 if ephemeris is available; otherwise the request validates
    # but the engine call may fail with a non-422 status. The key is
    # the request itself must not be a 422 schema rejection.
    assert r.status_code != 422, r.text


def test_calculate_bazi_rejects_unknown_time_standard():
    r = client.post("/calculate/bazi", json={**BASE, "standard": "UTC"})
    assert r.status_code == 422


@pytest.mark.parametrize("std", ["CIVIL", "LMT", "TLST"])
def test_chart_accepts_time_standard(std):
    payload = {
        "birth_local": "2024-02-10T14:30:00",
        "timezone": "Europe/Berlin",
        "longitude_deg": 13.405,
        "latitude_deg": 52.52,
        "time_standard": std,
    }
    r = client.post("/api/chart", json=payload)
    assert r.status_code != 422, r.text
```

### Step 2 — RED

```bash
.venv/bin/python -m pytest tests/test_time_standard_acceptance.py -q
```

Expected: `TLST` cases return 422 because the Literal type rejects it.

### Step 3 — Widen the three Literals

`bazi_engine/types.py:9`:
```python
TimeStandard = Literal["CIVIL", "LMT", "TLST"]
```

`bazi_engine/routers/bazi.py:49`:
```python
standard: Literal["CIVIL", "LMT", "TLST"] = Field("CIVIL")
```

`bazi_engine/routers/chart.py:51`:
```python
time_standard: Literal["CIVIL", "LMT", "TLST"] = Field("CIVIL")
```

### Step 4 — GREEN + regression

```bash
.venv/bin/python -m pytest \
  tests/test_time_standard_acceptance.py \
  tests/test_endpoint_negative.py \
  tests/test_openapi_contract.py \
  -q
```

Expected: all green. The OpenAPI drift check may flag the schema change — regenerate with `python scripts/export_openapi.py`.

### Step 5 — Router-layer clamp (Option 2, decided 2026-05-14)

`compute_bazi()` is **not** changed in Phase 1. Both `routers/bazi.py` and `routers/chart.py` clamp `TLST` → `LMT` *before* constructing `BaziInput`, so the engine path stays in known CIVIL/LMT territory. The original requested value is preserved in the derivation trace as `time_standard_requested` so consumers can distinguish "TLST requested, LMT used for pillars" from "LMT requested, LMT used for pillars".

Pillar values for a TLST request therefore equal pillar values for an LMT request. The diagnostic surface for TLST is `/calculate/tst` and (Phase 3, FBP-03-003) the future typed trace. The clamp is removed by FBP-02-005 when the engine learns to derive pillars from TLST natively.

Concretely:

`bazi_engine/routers/bazi.py` — inside `calculate_bazi_endpoint` (around line 168), before `BaziInput(...)`:

```python
requested_standard = req.standard
engine_standard = "LMT" if requested_standard == "TLST" else requested_standard
inp = BaziInput(
    birth_local=resolved_naive,
    timezone=req.tz,
    longitude_deg=req.lon,
    latitude_deg=req.lat,
    time_standard=engine_standard,
    day_boundary=req.boundary,
    fold=fold,
)
```

And inside the derivation trace dict returned from `_build_trace` (around line 144-154):

```python
"hour": {
    "local_hour": res.chart_local_dt.hour,
    "branch_index": hb,
    # DEV-2026-001 is still open; this field will be corrected in
    # FBP-03-002. Phase 1 only adds the requested/used split.
    "true_solar_time_used": inp.time_standard == "LMT",
    "time_standard_requested": requested_standard,
    "time_standard_used": inp.time_standard,
},
```

(`requested_standard` needs to be threaded into `_build_trace` — add a parameter; default to `inp.time_standard` for backwards-callable safety.)

Identical clamp + trace field in `routers/chart.py` if it surfaces the trace.

---

## Task 2 — FBP-01-002 + FBP-01-006: Introduce `EffectiveTimeContext`

**Why:** Centralizes the conversion `(birth_local, tz, longitude) → {civil, utc, lmt, tlst_hours, eot_minutes, tz_offset_minutes, date_rollover}`. Both the BaZi trace (FBP-03-003) and `/calculate/tst` (FBP-01-003) will consume this. FBP-01-006: TLST is encoded as **hours + day offset**, not as a `tzinfo`.

**Files:**
- Create: `bazi_engine/time_context.py`
- Create: `tests/test_bazi_time_context.py`

### Step 1 — Write failing tests

Create `tests/test_bazi_time_context.py`:

```python
"""FBP-01-002 / FBP-01-006 — EffectiveTimeContext spec.

Properties enforced here:
- civil, utc are tz-aware datetimes.
- lmt is a tz-aware datetime in a *constant-offset* zone derived from
  longitude (NOT IANA, NOT DST-sensitive).
- tlst_hours is a float in [0, 24).
- date_rollover is the integer day shift relative to civil local date.
- TLST is NOT modeled as a tzinfo — there is no `tlst` datetime field
  with a TLST-zone tzinfo. (FBP-01-006.)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from bazi_engine.time_context import EffectiveTimeContext, compute_effective_time_context


def test_civil_and_utc_are_tz_aware():
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    assert ctx.civil_local.tzinfo is not None
    assert ctx.utc.tzinfo == timezone.utc


def test_lmt_uses_longitude_offset_not_iana():
    """LMT is mean solar time at the given longitude."""
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    # 13.405° E → 13.405 × 4 min/° = 53.62 min offset from Greenwich
    expected_offset_min = 13.4050 * 4
    assert math.isclose(ctx.lmt_local.utcoffset().total_seconds() / 60,
                        expected_offset_min, abs_tol=0.1)


def test_tlst_is_not_a_tzinfo():
    """Stored as float hours + day offset, not as a datetime with tlst tzinfo."""
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    assert isinstance(ctx.tlst_hours, float)
    assert 0.0 <= ctx.tlst_hours < 24.0
    # No tlst_local field with a custom tzinfo.
    assert not hasattr(ctx, "tlst_local")


def test_eot_minutes_matches_solar_time_module():
    """EoT must come from solar_time.equation_of_time, not be re-derived."""
    from bazi_engine.solar_time import equation_of_time
    ctx = compute_effective_time_context(
        birth_local_iso="2024-06-21T12:00:00",
        tz_name="UTC",
        longitude_deg=0.0,
    )
    day_of_year = 173  # June 21
    assert math.isclose(ctx.eot_minutes, equation_of_time(day_of_year), abs_tol=0.5)


def test_tlst_formula_matches_calculate_tst_endpoint():
    """FBP-01-003 precondition: same input → same TLST hours
    as the inline formula in fusion.py:267 currently uses."""
    from bazi_engine.solar_time import equation_of_time
    iso = "2024-06-21T12:00:00"
    tz = "Europe/Berlin"
    lon = 13.4050

    ctx = compute_effective_time_context(iso, tz, lon)
    # Replicate fusion.py:264-267 directly:
    civil_dt = datetime.fromisoformat(iso)
    civil_hours = civil_dt.hour + civil_dt.minute / 60 + civil_dt.second / 3600
    delta_t_long = lon * 4 / 60
    E_t = equation_of_time(civil_dt.timetuple().tm_yday) / 60
    expected = (civil_hours + delta_t_long + E_t) % 24
    assert math.isclose(ctx.tlst_hours, expected, abs_tol=1e-6), (
        f"EffectiveTimeContext.tlst_hours = {ctx.tlst_hours}, fusion.py = {expected}"
    )


def test_date_rollover_when_tlst_crosses_midnight():
    """A civil time near midnight in a far-east-of-meridian longitude
    can push TLST past 24h or below 0h; the context must record the day shift."""
    # Civil 23:30 at longitude +30° → LMT ≈ 01:30 next day (UTC offset +2h).
    ctx = compute_effective_time_context(
        birth_local_iso="2024-06-15T23:30:00",
        tz_name="UTC",   # civil = UTC so longitude is the only shift
        longitude_deg=30.0,
    )
    assert ctx.date_rollover == 1


def test_effective_time_context_is_frozen():
    """Immutability invariant — mirrors BaziInput / BaziResult / Provenance."""
    ctx = compute_effective_time_context(
        birth_local_iso="2024-02-10T14:30:00",
        tz_name="Europe/Berlin",
        longitude_deg=13.4050,
    )
    with pytest.raises((AttributeError, Exception)):
        ctx.civil_local = None  # type: ignore[misc]
```

### Step 2 — RED

```bash
.venv/bin/python -m pytest tests/test_bazi_time_context.py -q
```

Expected: import error — module does not exist yet.

### Step 3 — Implement `bazi_engine/time_context.py`

```python
"""EffectiveTimeContext — typed decomposition of a birth instant
across the three time standards used by the BaZi engine.

FBP-01-002 / FBP-01-006:
- CIVIL  = legal local time in the IANA timezone (tz-aware).
- LMT    = mean solar time at the given longitude (constant-offset
           tzinfo derived purely from longitude, NOT DST-sensitive).
- TLST   = apparent solar time = LMT + equation_of_time. Stored as a
           float hour-of-day plus an integer day_rollover; **not** a
           tzinfo. TLST is not a legal/civil zone — modeling it as a
           tzinfo would invite false symmetry with CIVIL/LMT.

Dependencies: stdlib + ``bazi_engine.solar_time`` (which is itself
stdlib-only). This module sits at Level 2 — it must not import from
``bazi`` or any router.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional
from zoneinfo import ZoneInfo

from .solar_time import equation_of_time


class _LongitudeMeanTime(tzinfo):
    """A constant-offset tzinfo for Local Mean Time at a given longitude.

    Not a real IANA zone; never observes DST; offset is purely
    longitude × 4 min/° east of Greenwich. Returned by
    ``EffectiveTimeContext.lmt_local.tzinfo`` so consumers can format
    the value, but it is **not** registered with ``zoneinfo``.
    """

    __slots__ = ("_offset",)

    def __init__(self, longitude_deg: float) -> None:
        self._offset = timedelta(minutes=longitude_deg * 4)

    def utcoffset(self, dt: Optional[datetime]) -> timedelta:
        return self._offset

    def dst(self, dt: Optional[datetime]) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: Optional[datetime]) -> str:
        total_min = int(self._offset.total_seconds() / 60)
        sign = "+" if total_min >= 0 else "-"
        h, m = divmod(abs(total_min), 60)
        return f"LMT{sign}{h:02d}:{m:02d}"


@dataclass(frozen=True)
class EffectiveTimeContext:
    """All three time standards plus the small metadata needed to
    diagnose boundary cases (rollovers, EoT magnitude, tz offset)."""
    civil_local: datetime           # tz-aware, IANA tz
    utc: datetime                   # tz-aware, UTC
    lmt_local: datetime             # tz-aware, constant longitude offset
    tlst_hours: float               # apparent solar hour-of-day, in [0, 24)
    eot_minutes: float              # equation of time, minutes
    tz_offset_minutes: int          # civil_local utcoffset, minutes
    date_rollover: int              # day shift of TLST relative to civil_local date


def compute_effective_time_context(
    birth_local_iso: str,
    tz_name: str,
    longitude_deg: float,
) -> EffectiveTimeContext:
    """Resolve a civil ISO timestamp + IANA zone + longitude into the
    three time standards.

    Caller is responsible for DST disambiguation upstream — by the
    time we get here, ``birth_local_iso`` is expected to be the
    resolved naive ISO (the engine already calls
    ``resolve_local_iso`` before constructing ``BaziInput``).
    """
    civil_naive = datetime.fromisoformat(birth_local_iso)
    civil_local = civil_naive.replace(tzinfo=ZoneInfo(tz_name))
    utc = civil_local.astimezone(timezone.utc)

    lmt_tz = _LongitudeMeanTime(longitude_deg)
    lmt_local = utc.astimezone(lmt_tz)

    day_of_year = civil_local.timetuple().tm_yday
    eot_min = float(equation_of_time(day_of_year))
    # Civil hours + longitude correction + EoT. Matches the inline
    # formula in bazi_engine/routers/fusion.py:264-267 — that endpoint
    # will be migrated to this function in FBP-01-003.
    civil_hours = civil_local.hour + civil_local.minute / 60 + civil_local.second / 3600
    delta_t_long = longitude_deg * 4 / 60
    raw_tlst = civil_hours + delta_t_long + (eot_min / 60)
    tlst_hours = raw_tlst % 24.0
    rollover = int(raw_tlst // 24.0)

    tz_off = civil_local.utcoffset()
    tz_off_min = 0 if tz_off is None else int(tz_off.total_seconds() / 60)

    return EffectiveTimeContext(
        civil_local=civil_local,
        utc=utc,
        lmt_local=lmt_local,
        tlst_hours=round(tlst_hours, 6),
        eot_minutes=round(eot_min, 4),
        tz_offset_minutes=tz_off_min,
        date_rollover=rollover,
    )
```

### Step 4 — GREEN

```bash
.venv/bin/python -m pytest tests/test_bazi_time_context.py tests/test_import_hierarchy.py -q
```

Expected: time_context tests pass; `solar_time.py` purity test still green; `time_context.py` is allowed to import `solar_time` (Level 2 → Level 2 is fine; the hierarchy rule is bottom-up).

### Step 5 — Lint check

```bash
.venv/bin/python -m ruff check bazi_engine/time_context.py tests/test_bazi_time_context.py
.venv/bin/python -m mypy bazi_engine/time_context.py --ignore-missing-imports
```

Both should be silent or close to it.

---

## Task 3 — FBP-01-003 + FBP-01-004: `/calculate/tst` consumes `EffectiveTimeContext`

**Why:** Removes the duplicated TLST formula in `fusion.py:264-267`. The two surfaces (`/calculate/tst` and the future BaZi trace) become provably consistent.

**Files:**
- Modify: `bazi_engine/routers/fusion.py:255-283`
- Create: `tests/test_tst_endpoint_consistency.py`

### Step 1 — Write failing consistency test

```python
"""FBP-01-003 — /calculate/tst must agree with EffectiveTimeContext."""
from __future__ import annotations

import math
import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from bazi_engine.time_context import compute_effective_time_context

client = TestClient(app)

CASES = [
    {"date": "2024-06-21T12:00:00", "tz": "Europe/Berlin", "lon": 13.4050},
    {"date": "2024-12-21T12:00:00", "tz": "Europe/Berlin", "lon": 13.4050},
    {"date": "2024-03-20T06:00:00", "tz": "Asia/Tokyo",    "lon": 139.69},
    {"date": "2024-09-22T18:30:00", "tz": "UTC",           "lon": 0.0},
]


@pytest.mark.parametrize("payload", CASES, ids=lambda p: f"{p['tz']}_{p['date']}")
def test_tst_endpoint_matches_effective_time_context(payload):
    r = client.post("/calculate/tst", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    ctx = compute_effective_time_context(
        birth_local_iso=payload["date"],
        tz_name=payload["tz"],
        longitude_deg=payload["lon"],
    )
    assert math.isclose(
        body["true_solar_time_hours"], ctx.tlst_hours, abs_tol=1e-3
    ), (body["true_solar_time_hours"], ctx.tlst_hours)
    assert math.isclose(
        body["equation_of_time_hours"], ctx.eot_minutes / 60.0, abs_tol=1e-3
    )
```

### Step 2 — RED (likely passes already — see Step 4)

```bash
.venv/bin/python -m pytest tests/test_tst_endpoint_consistency.py -q
```

If it already passes (the formulas are mathematically identical), proceed to refactor; the test is the regression guard.

### Step 3 — Refactor `/calculate/tst` to consume the context

Replace the body of `calculate_tst_endpoint` (`bazi_engine/routers/fusion.py:255-283`):

```python
@router.post("/tst", response_model=TSTResponse)
def calculate_tst_endpoint(req: TSTRequest) -> Dict[str, Any]:
    """True Solar Time (TST) calculation.

    Delegates to :func:`bazi_engine.time_context.compute_effective_time_context`
    so the endpoint and the BaZi engine trace cannot drift.
    """
    try:
        dt, _ = resolve_local_iso(
            req.date, req.tz,
            ambiguous=req.ambiguousTime, nonexistent=req.nonexistentTime,
        )
        resolved = dt.replace(tzinfo=None).isoformat()
        ctx = compute_effective_time_context(
            birth_local_iso=resolved,
            tz_name=req.tz,
            longitude_deg=req.lon,
        )
        civil_hours = ctx.civil_local.hour + ctx.civil_local.minute / 60 + ctx.civil_local.second / 3600
        hours = int(ctx.tlst_hours)
        minutes = int((ctx.tlst_hours - hours) * 60)
        return {
            "input": {"date": req.date, "tz": req.tz, "lon": req.lon},
            "civil_time_hours":             round(civil_hours, 4),
            "longitude_correction_hours":   round(req.lon * 4 / 60, 4),
            "equation_of_time_hours":       round(ctx.eot_minutes / 60.0, 4),
            "true_solar_time_hours":        round(ctx.tlst_hours, 4),
            "true_solar_time_formatted":    f"{hours:02d}:{minutes:02d}",
            "provenance": build_provenance(),
        }
    except BaziEngineError:
        raise
    except Exception:
        _log.exception("Calculation failed")
        raise HTTPException(status_code=500, detail="Internal calculation error")
```

Add the import near the top of `bazi_engine/routers/fusion.py`:

```python
from bazi_engine.time_context import compute_effective_time_context
```

### Step 4 — GREEN + regression

```bash
.venv/bin/python -m pytest \
    tests/test_tst_endpoint_consistency.py \
    tests/test_solar_time.py \
    tests/test_integration_fusion.py \
    -q
```

Expected: all green. If `test_integration_fusion.py` was pinning the response shape exactly, the field ordering may have shifted — diff and accept if the values agree.

---

## Task 4 — FBP-01-005: Compatibility guard for `to_chart_local()` + existing CIVIL/LMT tests

**Why:** Belt-and-suspenders. The plan demands existing CIVIL/LMT tests stay green and new TLST tests use the new context rather than the LMT `tzinfo`. Add a guard test that fails if anyone wires TLST through `to_chart_local()`.

**Files:**
- Test: `tests/test_time_utils.py` (extend)

### Step 1 — Add the guard

In `tests/test_time_utils.py`, append:

```python
def test_to_chart_local_does_not_advertise_tlst():
    """FBP-01-005 — to_chart_local handles CIVIL and LMT only.

    TLST has no IANA zone; new TLST consumers must use
    bazi_engine.time_context.compute_effective_time_context.
    """
    import inspect
    from bazi_engine import time_utils
    src = inspect.getsource(time_utils)
    assert "TLST" not in src.upper().split("ZONEINFO"), (
        "to_chart_local must not gain a TLST branch; route TLST through "
        "bazi_engine.time_context instead."
    )
```

(Test is purposefully fuzzy — it just enforces that nobody adds a TLST `tzinfo` here. Refine if it produces false positives.)

### Step 2 — Run all existing time_utils tests + the new guard

```bash
.venv/bin/python -m pytest tests/test_time_utils.py -q
```

Expected: all green.

---

## Task 5 — Final review pass + commit grouping

### Step 1 — Run the full Phase 0 + Phase 1 slice

```bash
.venv/bin/python -m pytest \
  tests/test_bazi_day_anchor_invariants.py \
  tests/test_bazi_golden_case_schema.py \
  tests/test_bazi_baseline_inventory.py \
  tests/test_regression_v1_compatibility.py \
  tests/test_bazi_baseline_dst_fold.py \
  tests/test_constants.py \
  tests/test_time_standard_acceptance.py \
  tests/test_bazi_time_context.py \
  tests/test_tst_endpoint_consistency.py \
  tests/test_time_utils.py \
  tests/test_solar_time.py \
  tests/test_import_hierarchy.py \
  tests/test_openapi_contract.py \
  -q
```

Expected: all green.

### Step 2 — Regenerate OpenAPI

```bash
.venv/bin/python scripts/export_openapi.py
```

The TLST literal change widens the schema. Commit the regenerated `spec/openapi/openapi.json` alongside.

### Step 3 — Suggested commit split

1. `feat(types): add TLST to TimeStandard literal (FBP-01-001)` — types.py + routers/bazi.py + routers/chart.py + `tests/test_time_standard_acceptance.py` + regenerated OpenAPI.
2. `feat(time): add EffectiveTimeContext (FBP-01-002, FBP-01-006)` — `bazi_engine/time_context.py` + `tests/test_bazi_time_context.py`.
3. `refactor(fusion): /calculate/tst delegates to EffectiveTimeContext (FBP-01-003, FBP-01-004)` — `bazi_engine/routers/fusion.py` + `tests/test_tst_endpoint_consistency.py`.
4. `test(time_utils): guard against TLST entering to_chart_local (FBP-01-005)` — `tests/test_time_utils.py`.

---

## Stop-gates (Release-Gate §1 Phase 1 → Phase 2)

To advance to Phase 2, all of the following must be true:

- ✅ `bazi_engine/time_context.py` exists with `EffectiveTimeContext` carrying `civil_local`, `utc`, `lmt_local`, `tlst_hours`, `eot_minutes`, `tz_offset_minutes`, `date_rollover`.
- ✅ `TimeStandard` accepts `TLST`; `INVALID` still returns 422.
- ✅ `/calculate/tst` and `EffectiveTimeContext.tlst_hours` agree within documented tolerance (test exists).
- ✅ `solar_time.py` purity test stays green (`test_import_hierarchy.py::test_solar_time_has_no_internal_imports`).
- ✅ LMT and TLST never aliased in code, trace, or tests.
- ✅ `/v1` default remains `CIVIL`. No CIVIL/LMT golden case changed value.

## Out of scope (deferred to Phase 2+)

- Wiring TLST into `compute_bazi()` hour-pillar derivation — that's FBP-02-005.
- Updating the BaZi trace to surface `civil_local`, `utc`, `lmt`, `tlst_hours`, `eot`, `tz_offset`, `effective_standard` — that's FBP-03-003.
- Zi-day boundary on effective time — FBP-02-004.

## Estimated wall-clock

~45–60 minutes including verification and OpenAPI regeneration.
