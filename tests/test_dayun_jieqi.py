"""Tests for the Da-Yun jieqi anchor resolver adapter.

TASK-DY-007: thin adapter over the existing FuFirE solar-terms engine that
returns the nearest jieqi anchor in a given direction from a birth datetime.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bazi_engine.ephemeris import ensure_ephemeris_files
from bazi_engine.exc import EphemerisUnavailableError

try:
    ensure_ephemeris_files(None)
except (FileNotFoundError, EphemerisUnavailableError):
    pytest.skip(
        "Jieqi anchor tests require Swiss Ephemeris files. "
        "Set SE_EPHE_PATH to run.",
        allow_module_level=True,
    )

from bazi_engine.dayun.jieqi import resolve_jieqi_anchor

# ── Schema-shape assertions ──────────────────────────────────────────────

def test_forward_returns_required_keys():
    """Forward anchor returns dict with the four required keys + correct types."""
    birth = datetime(1987, 7, 4, 21, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    out = resolve_jieqi_anchor(birth, "forward")
    assert set(out.keys()) == {"name", "direction", "local_dt", "delta"}
    assert out["direction"] == "next"
    assert isinstance(out["name"], str)
    assert isinstance(out["local_dt"], str)
    assert set(out["delta"].keys()) == {"days", "hours", "minutes"}
    assert all(isinstance(v, int) for v in out["delta"].values())


def test_backward_returns_required_keys():
    birth = datetime(1987, 7, 4, 21, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    out = resolve_jieqi_anchor(birth, "backward")
    assert out["direction"] == "previous"


def test_name_is_in_schema_enum():
    """Returned name MUST match the schema's JieqiEnum (space-separated Pinyin)."""
    JIEQI_SCHEMA_NAMES = {
        "Li Chun", "Yu Shui", "Jing Zhe", "Chun Fen", "Qing Ming", "Gu Yu",
        "Li Xia", "Xiao Man", "Mang Zhong", "Xia Zhi", "Xiao Shu", "Da Shu",
        "Li Qiu", "Chu Shu", "Bai Lu", "Qiu Fen", "Han Lu", "Shuang Jiang",
        "Li Dong", "Xiao Xue", "Da Xue", "Dong Zhi", "Xiao Han", "Da Han",
    }
    birth = datetime(2026, 1, 15, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert resolve_jieqi_anchor(birth, "forward")["name"] in JIEQI_SCHEMA_NAMES
    assert resolve_jieqi_anchor(birth, "backward")["name"] in JIEQI_SCHEMA_NAMES


def test_delta_is_non_negative():
    """Delta components are always >= 0 (the adapter takes absolute value)."""
    birth = datetime(1987, 7, 4, 21, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    for d in ("forward", "backward"):
        delta = resolve_jieqi_anchor(birth, d)["delta"]
        assert delta["days"] >= 0
        assert 0 <= delta["hours"] < 24
        assert 0 <= delta["minutes"] < 60


def test_local_dt_is_in_birth_tz():
    """local_dt offset matches the birth datetime's tz offset."""
    birth = datetime(1987, 7, 4, 21, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    out = resolve_jieqi_anchor(birth, "forward")
    # Europe/Berlin in July = CEST = UTC+02:00. ISO suffix should reflect this.
    assert "+02:00" in out["local_dt"], f"Expected +02:00 in {out['local_dt']}"


# ── Article-example sanity (values discovered, not asserted from article) ──

def test_article_example_forward_anchor_is_xiao_shu():
    """For birth 1987-07-04T21:30 Berlin forward, the next jieqi should be Xiao Shu (105°)."""
    birth = datetime(1987, 7, 4, 21, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    out = resolve_jieqi_anchor(birth, "forward")
    assert out["name"] == "Xiao Shu", f"Expected Xiao Shu, got {out['name']}"
    assert out["direction"] == "next"
    # The article claims 8d14h; live engine value to be confirmed during impl.
    # Acceptable bounds: delta must be < 16 days (max gap between jieqi).
    delta_days_total = (
        out["delta"]["days"]
        + out["delta"]["hours"] / 24
        + out["delta"]["minutes"] / 1440
    )
    assert delta_days_total < 16, f"Delta {delta_days_total}d exceeds max jieqi gap"


# ── Input validation ─────────────────────────────────────────────────────

def test_naive_birth_datetime_raises():
    naive = datetime(1987, 7, 4, 21, 30)  # no tzinfo
    with pytest.raises(Exception, match="(naive|tz|timezone|aware)"):
        resolve_jieqi_anchor(naive, "forward")


def test_invalid_direction_raises():
    birth = datetime(1987, 7, 4, 21, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    with pytest.raises(Exception, match="(direction|forward|backward)"):
        resolve_jieqi_anchor(birth, "sideways")


# ── Regression: Da Yun anchors on jie (节) only, never on zhongqi (中气) ────
#
# The start age (3 days = 1 year) counts to the next / previous jie — the 12
# month-opening terms that bound the month pillar (even indices in the
# Li-Chun-based order: Li Chun, Jing Zhe, Qing Ming, ...).  The 12 zhongqi
# (odd indices: Yu Shui, Chun Fen, Gu Yu, ...) are never an anchor.  All
# birth data below are neutral synthetic dates, not personal data.

_JIE_NAMES = frozenset({
    "Li Chun", "Jing Zhe", "Qing Ming", "Li Xia", "Mang Zhong", "Xiao Shu",
    "Li Qiu", "Bai Lu", "Han Lu", "Li Dong", "Da Xue", "Xiao Han",
})


def _delta_days(delta: dict) -> float:
    return delta["days"] + delta["hours"] / 24 + delta["minutes"] / 1440


def test_forward_anchor_skips_zhongqi_yu_shui():
    """1987-02-17 12:00 Berlin, forward: the next term is Yu Shui (中气,
    1987-02-19), but Da Yun counts to the next jie, Jing Zhe (惊蛰, early
    March) — about 16.7 days, i.e. a start age of ~5.55 instead of ~0.58 years."""
    birth = datetime(1987, 2, 17, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    out = resolve_jieqi_anchor(birth, "forward")
    assert out["name"] == "Jing Zhe"
    assert out["direction"] == "next"
    assert out["local_dt"].startswith("1987-03-06T")
    assert 16 <= out["delta"]["days"] <= 17


def test_backward_anchor_skips_zhongqi_yu_shui():
    """2001-03-03 12:00 Berlin, backward: the previous term is Yu Shui (中气,
    2001-02-18), but Da Yun counts back to the previous jie, Li Chun (立春,
    2001-02-03 evening in Berlin, 02-04 in Beijing) — about 27.7 days."""
    birth = datetime(2001, 3, 3, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    out = resolve_jieqi_anchor(birth, "backward")
    assert out["name"] == "Li Chun"
    assert out["direction"] == "previous"
    assert out["local_dt"].startswith("2001-02-03T")
    assert 27 <= out["delta"]["days"] <= 28


def test_control_jie_anchor_unchanged_by_jie_only_rule():
    """Control: 2000-06-25 12:00 Berlin, forward.  Xia Zhi (中气) already lies
    before birth, so the nearest term in flow direction is the jie Xiao Shu.
    Values pinned from the pre-fix engine (commit 011d938): the jie-only rule
    must not change them.  ``local_dt`` is compared to the minute because
    its seconds differ by one between the SWIEPH and MOSEPH backends."""
    birth = datetime(2000, 6, 25, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    out = resolve_jieqi_anchor(birth, "forward")
    assert out["name"] == "Xiao Shu"
    assert out["direction"] == "next"
    assert out["local_dt"].startswith("2000-07-06T21:13:")
    assert out["local_dt"].endswith("+02:00")
    assert out["delta"] == {"days": 11, "hours": 9, "minutes": 13}


@pytest.mark.swieph
def test_anchor_invariants_against_month_pillar_oracle():
    """Invariant sweep: every 7th day 1900-2100 (12:00 UTC), both directions.

    For every sample: the anchor is one of the 12 jie, lies strictly on the
    flow side of birth, and is at most 32 days away.

    Two oracles on every 8th sample:

    * Selection oracle (``compute_bazi`` month pillar, an independent code
      path for choosing the month): the pillar changes exactly at the anchor
      (one minute before vs. one minute after) and is the same at birth as
      on the birth side of the anchor.  Because a month pillar never repeats
      within 32 days, equality at both ends means no jie lies between birth
      and anchor, i.e. the anchor is the nearest jie.  It shares the
      ``find_crossing`` solver with the resolver, so it does not check the
      crossing instants themselves.
    * Instant oracle: Swiss Ephemeris' own ``solcross_ut`` (not
      ``find_crossing``) puts the Sun at the jie's longitude — taken from a
      table written out in this test, not from the resolver's index formula —
      within 2 seconds of the anchor.
    """
    from datetime import timedelta, timezone

    from bazi_engine.bazi import compute_bazi
    from bazi_engine.ephemeris import SwissEphBackend, datetime_utc_to_jd_ut
    from bazi_engine.types import BaziInput

    jie_longitude = {
        "Li Chun": 315.0, "Jing Zhe": 345.0, "Qing Ming": 15.0, "Li Xia": 45.0,
        "Mang Zhong": 75.0, "Xiao Shu": 105.0, "Li Qiu": 135.0, "Bai Lu": 165.0,
        "Han Lu": 195.0, "Li Dong": 225.0, "Da Xue": 255.0, "Xiao Han": 285.0,
    }
    backend = SwissEphBackend()

    def month_pillar(dt_utc: datetime) -> tuple[int, int]:
        res = compute_bazi(BaziInput(
            birth_local=dt_utc.strftime("%Y-%m-%dT%H:%M:%S"),
            timezone="UTC",
            longitude_deg=0.0,
            latitude_deg=0.0,
        ))
        return (res.pillars.month.stem_index, res.pillars.month.branch_index)

    one_minute = timedelta(minutes=1)
    birth = datetime(1900, 1, 8, 12, 0, tzinfo=timezone.utc)
    end = datetime(2100, 12, 24, 12, 0, tzinfo=timezone.utc)
    sample = 0
    oracle_checks = 0
    while birth <= end:
        oracle = sample % 8 == 0
        birth_pillar = month_pillar(birth) if oracle else None
        for direction in ("forward", "backward"):
            out = resolve_jieqi_anchor(birth, direction)
            ctx = f"{birth.isoformat()} {direction} -> {out}"
            anchor = datetime.fromisoformat(out["local_dt"])
            assert out["name"] in _JIE_NAMES, ctx
            assert _delta_days(out["delta"]) <= 32, ctx
            if direction == "forward":
                assert anchor > birth, ctx
            else:
                assert anchor < birth, ctx
            if oracle:
                before = month_pillar(anchor - one_minute)
                after = month_pillar(anchor + one_minute)
                assert before != after, f"month pillar does not change at anchor: {ctx}"
                birth_side = before if direction == "forward" else after
                assert birth_pillar == birth_side, (
                    f"month pillar changes between birth and anchor: {ctx}"
                )
                anchor_jd = datetime_utc_to_jd_ut(anchor.astimezone(timezone.utc))
                sun_jd = backend.solcross_ut(jie_longitude[out["name"]], anchor_jd - 20.0)
                assert sun_jd is not None, ctx
                assert abs(sun_jd - anchor_jd) * 86400 <= 2.0, (
                    f"anchor is {(anchor_jd - sun_jd) * 86400:.1f} s off solcross_ut: {ctx}"
                )
                oracle_checks += 1
        sample += 1
        birth += timedelta(days=7)
    assert sample > 10_000
    assert oracle_checks > 2_500
