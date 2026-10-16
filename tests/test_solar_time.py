"""
test_solar_time.py — Isolation tests for bazi_engine/solar_time.py

All imports go directly to solar_time, never via fusion.
This tests the module as a standalone unit and guards the re-export parity.

Reference values derived from:
  - NOAA Solar Calculator: https://gml.noaa.gov/grad/solcalc/
  - Astronomical Algorithms (Meeus, 2nd ed.), Chapter 27
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from math import isclose
from pathlib import Path

import pytest

# ── Direct imports from the new module ──────────────────────────────────────
from bazi_engine.solar_time import (
    EOT_SOURCE_MEEUS,
    equation_of_time,
    equation_of_time_jd,
    jd_ut_from_datetime,
    true_solar_time,
)

# ============================================================================
# Module isolation guard
# ============================================================================

class TestModuleIsolation:
    """solar_time.py must remain a pure-math leaf — zero internal imports."""

    def test_no_internal_imports(self):
        path = Path(__file__).resolve().parents[1] / "bazi_engine" / "solar_time.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        internal = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                internal.append(ast.unparse(node))
        assert internal == [], (
            "solar_time.py must have no relative imports. Found:\n" + "\n".join(internal)
        )

    def test_no_third_party_imports(self):
        """Only stdlib math is allowed."""
        path = Path(__file__).resolve().parents[1] / "bazi_engine" / "solar_time.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        STDLIB_ALLOWED = {"math", "__future__", "typing", "datetime"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top in STDLIB_ALLOWED, f"Unexpected import: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                top = node.module.split(".")[0]
                assert top in STDLIB_ALLOWED, f"Unexpected import: {node.module}"


# ============================================================================
# equation_of_time — reference values & properties
# ============================================================================

class TestEquationOfTime:
    """Validate against NOAA reference values (±0.3 min tolerance)."""

    # NOAA reference: https://gml.noaa.gov/grad/solcalc/
    # (day_of_year, expected_minutes, description)
    NOAA_REFERENCES = [
        (1,   -3.2,  "Jan 1  — near zero, slightly negative"),
        (45,  -14.0, "Feb 14 — annual minimum (~-14.2 min)"),
        (106,  1.1,  "Apr 16 — near zero crossing (positive side)"),
        (180, -3.0,  "Jun 29 — small negative trough (after April zero crossing)"),
        (214, -6.5,  "Aug 2  — crossing to negative"),
        (298,  16.0, "Oct 25 — annual maximum (~+16.4 min)"),
        (355,  2.5,  "Dec 21 — near zero after November peak"),
    ]

    @pytest.mark.parametrize("day,expected,desc", NOAA_REFERENCES)
    def test_noaa_reference_values(self, day, expected, desc):
        eot = equation_of_time(day, use_precise=True)
        assert abs(eot - expected) < 1.5, (
            f"Day {day} ({desc}): got {eot:.2f} min, expected ~{expected:.1f} min"
        )

    def test_annual_minimum_near_day_45(self):
        """True minimum of EoT is around day 45 (mid-February)."""
        values = [(d, equation_of_time(d)) for d in range(30, 60)]
        min_day, min_val = min(values, key=lambda x: x[1])
        assert min_val < -12.0, f"Annual minimum should be < -12 min, got {min_val:.2f} at day {min_day}"
        assert 35 <= min_day <= 55, f"Minimum should be near day 45, got day {min_day}"

    def test_annual_maximum_near_day_310(self):
        """True maximum of EoT is around day 310 (early November)."""
        values = [(d, equation_of_time(d)) for d in range(295, 325)]
        max_day, max_val = max(values, key=lambda x: x[1])
        assert max_val > 14.0, f"Annual maximum should be > 14 min, got {max_val:.2f} at day {max_day}"
        assert 300 <= max_day <= 320, f"Maximum should be near day 310, got day {max_day}"

    def test_physical_range_full_year(self):
        """EoT is physically bounded to roughly -15 to +17 minutes."""
        for day in range(1, 367):
            eot = equation_of_time(day, use_precise=True)
            assert -16.0 < eot < 18.0, f"Day {day}: EoT={eot:.3f} outside physical range"

    def test_simplified_vs_precise_close(self):
        """Both formulas agree within 2 minutes throughout the year."""
        for day in range(1, 366, 10):
            precise = equation_of_time(day, use_precise=True)
            simple  = equation_of_time(day, use_precise=False)
            assert abs(precise - simple) < 2.5, (
                f"Day {day}: precise={precise:.2f}, simple={simple:.2f} — diff too large"
            )

    def test_boundary_day_1(self):
        eot = equation_of_time(1)
        assert isinstance(eot, float)
        assert -16 < eot < 18

    def test_boundary_day_365(self):
        eot = equation_of_time(365)
        assert isinstance(eot, float)
        assert -16 < eot < 18

    def test_boundary_day_366_leap_year(self):
        eot = equation_of_time(366)
        assert isinstance(eot, float)
        assert -16 < eot < 18

    def test_return_type_is_float(self):
        assert isinstance(equation_of_time(100), float)
        assert isinstance(equation_of_time(100, use_precise=False), float)


# ============================================================================
# true_solar_time — golden values & properties
# ============================================================================

class TestTrueSolarTime:
    """
    Golden values computed manually:
      TST = civil_time - tz_offset + (longitude/15) + EoT/60
    """

    def test_prime_meridian_utc_no_offset(self):
        """At lon=0, tz=0, TST ≈ civil_time + EoT only."""
        day = 180  # ~June 29, EoT ≈ +2 min = +0.033 h
        eot_h = equation_of_time(day) / 60.0
        civil = 12.0
        expected = civil + eot_h
        tst = true_solar_time(civil, 0.0, day, timezone_offset_hours=0.0)
        assert isclose(tst, expected % 24, abs_tol=0.01), (
            f"Prime meridian TST={tst:.4f}, expected={expected:.4f}"
        )

    def test_berlin_summer_noon(self):
        """Berlin: lon=13.405°, CEST tz=+2. Day 180."""
        # TST = 12 - 2 + 13.405/15 + EoT(180)/60
        #     = 12 - 2 + 0.8937 + ~0.033
        day = 180
        lon = 13.405
        tz = 2.0
        eot_h = equation_of_time(day) / 60.0
        utc = 12.0 - tz
        lmt = utc + lon / 15.0
        expected = (lmt + eot_h) % 24
        tst = true_solar_time(12.0, lon, day, timezone_offset_hours=tz)
        assert isclose(tst, expected, abs_tol=0.01), (
            f"Berlin summer noon: TST={tst:.4f}, expected={expected:.4f}"
        )

    def test_tokyo_winter_noon(self):
        """Tokyo: lon=139.69°, JST tz=+9. Day 15 (Jan 15)."""
        day = 15
        lon = 139.69
        tz = 9.0
        eot_h = equation_of_time(day) / 60.0
        utc = 12.0 - tz
        lmt = utc + lon / 15.0
        expected = (lmt + eot_h) % 24
        tst = true_solar_time(12.0, lon, day, timezone_offset_hours=tz)
        assert isclose(tst, expected, abs_tol=0.01)

    def test_new_york_winter_noon(self):
        """New York: lon=-74.0°, EST tz=-5. Day 45."""
        day = 45
        lon = -74.0
        tz = -5.0
        eot_h = equation_of_time(day) / 60.0
        utc = 12.0 - tz
        lmt = utc + lon / 15.0
        expected = (lmt + eot_h) % 24
        tst = true_solar_time(12.0, lon, day, timezone_offset_hours=tz)
        assert isclose(tst, expected, abs_tol=0.01)

    def test_no_timezone_treated_as_lmt(self):
        """When timezone_offset_hours=None, input is treated as LMT."""
        day = 180
        eot_h = equation_of_time(day) / 60.0
        civil = 12.0
        expected = (civil + eot_h) % 24
        tst = true_solar_time(civil, 13.405, day, timezone_offset_hours=None)
        assert isclose(tst, expected, abs_tol=0.01)

    def test_result_always_in_0_24(self):
        """TST must always be normalized to [0, 24)."""
        test_cases = [
            (23.9, 180.0, 1, 12.0),   # would wrap over midnight
            (0.1, -180.0, 1, -12.0),  # would wrap below zero
            (6.0, 90.0, 180, 6.0),
        ]
        for civil, lon, day, tz in test_cases:
            tst = true_solar_time(civil, lon, day, timezone_offset_hours=tz)
            assert 0.0 <= tst < 24.0, (
                f"civil={civil}, lon={lon}, day={day}, tz={tz} → TST={tst} out of range"
            )

    def test_return_type_is_float(self):
        assert isinstance(true_solar_time(12.0, 0.0, 180, 0.0), float)

    def test_precision_4_decimal_places(self):
        """Return value is rounded to 4 decimal places."""
        tst = true_solar_time(12.0, 13.405, 180, 2.0)
        # Check that it's a float with at most 4 decimal places
        assert tst == round(tst, 4)


# ============================================================================
# Fusion re-export parity
# ============================================================================

class TestFusionReexportParity:
    """
    fusion.py re-exports equation_of_time and true_solar_time from solar_time.
    Both import paths must yield bit-identical results.
    """

    def test_equation_of_time_identical(self):
        from bazi_engine.fusion import equation_of_time as eot_fusion
        for day in range(1, 366, 7):
            direct = equation_of_time(day)
            via_fusion = eot_fusion(day)
            assert direct == via_fusion, (
                f"Day {day}: solar_time={direct}, fusion={via_fusion}"
            )

    def test_true_solar_time_identical(self):
        from bazi_engine.fusion import true_solar_time as tst_fusion
        test_cases = [
            (12.0, 13.405, 180, 2.0),
            (6.0, -74.0, 45, -5.0),
            (23.5, 139.69, 15, 9.0),
            (0.0, 0.0, 1, 0.0),
        ]
        for civil, lon, day, tz in test_cases:
            direct = true_solar_time(civil, lon, day, tz)
            via_fusion = tst_fusion(civil, lon, day, tz)
            assert direct == via_fusion, (
                f"TST mismatch: solar_time={direct}, fusion={via_fusion}"
            )


# ============================================================================
# FBP-TST-006 — Meeus equation of time (engine path) vs Swiss Ephemeris oracle
# ============================================================================

class TestMeeusEquationOfTime:
    """``equation_of_time_jd`` is pure stdlib math (attestation invariant F3:
    no Swiss-Ephemeris call on the ``/calculate/tst`` path) and must agree
    with ``swe.time_equ`` to < 0.1 min. The oracle calls below are confined to
    the test; ``swe.time_equ`` is identical on SWIEPH and the Moshier fallback
    (< 1e-3 min), so this runs unchanged without SE1 files."""

    MEEUS_TOL_MIN = 0.1   # hard bound (sprint-2 plan §4.2); measured max 0.058 min 1950–2030

    @pytest.fixture(autouse=True)
    def _pin_swisseph_global_state(self):
        import swisseph as swe

        from bazi_engine.ephemeris import _resolve_ephe_path
        swe.set_ephe_path(str(_resolve_ephe_path(None)))
        swe.set_sid_mode(0)
        yield

    @staticmethod
    def _oracle_min(jd_ut: float) -> float:
        import swisseph as swe
        r = swe.time_equ(jd_ut)
        return (r[0] if isinstance(r, tuple) else r) * 1440.0

    def test_label_constant(self):
        assert EOT_SOURCE_MEEUS == "meeus_1998"

    def test_vs_swisseph_1950_2030_every_6h(self):
        import swisseph as swe
        jd = swe.julday(1950, 1, 1, 0.0)
        end = swe.julday(2030, 12, 31, 18.0)
        worst = 0.0
        worst_jd = jd
        while jd <= end:
            d = abs(equation_of_time_jd(jd) - self._oracle_min(jd))
            if d > worst:
                worst, worst_jd = d, jd
            jd += 0.25
        assert worst < self.MEEUS_TOL_MIN, (worst, swe.revjul(worst_jd))

    @pytest.mark.parametrize("ymd_h, expected_min", [
        ((1990, 7, 15, 13.7333), -5.919),    # Hannover corpus case
        ((2024, 2, 11, 12.0), -14.193),        # near the annual minimum (early Feb)
        ((2024, 11, 3, 12.0), 16.45),         # near the annual maximum (early Nov)
        ((2024, 6, 13, 12.0), -0.197),         # near the mid-June zero crossing
    ])
    def test_known_values(self, ymd_h, expected_min):
        """Literal pins (``swe.time_equ`` × 1440, rounded to 1e-3 min) so a
        regression is visible without the oracle."""
        import swisseph as swe
        jd = swe.julday(*ymd_h)
        assert isclose(equation_of_time_jd(jd), expected_min, abs_tol=self.MEEUS_TOL_MIN)

    def test_continuous_across_year_boundary(self):
        """No wrap-around artefact at the L0/α discontinuity: consecutive
        hourly samples around 2024/2025 New Year differ by < 0.05 min."""
        import swisseph as swe
        jd = swe.julday(2024, 12, 31, 0.0)
        prev = equation_of_time_jd(jd)
        for _ in range(48):
            jd += 1 / 24
            cur = equation_of_time_jd(jd)
            assert abs(cur - prev) < 0.05, (jd, cur, prev)
            prev = cur

    def test_physical_range_full_year(self):
        import swisseph as swe
        jd = swe.julday(2024, 1, 1, 0.0)
        for _ in range(366 * 4):
            assert -14.5 < equation_of_time_jd(jd) < 16.6
            jd += 0.25

    def test_better_than_day_of_year_approximation(self):
        """The reason for E6-M: the Meeus path must beat the Spencer form at
        the Spencer form's worst 2024 sample by a wide margin."""
        import swisseph as swe
        worst_spencer = 0.0
        worst_meeus = 0.0
        d = datetime(2024, 1, 1)
        while d.year == 2024:
            jd = swe.julday(d.year, d.month, d.day, 12.0)
            ref = self._oracle_min(jd)
            worst_spencer = max(worst_spencer, abs(equation_of_time(d.timetuple().tm_yday) - ref))
            worst_meeus = max(worst_meeus, abs(equation_of_time_jd(jd) - ref))
            d += timedelta(days=1)
        assert worst_meeus < 0.1 < worst_spencer

    def test_jd_ut_from_datetime_matches_ephemeris_helper(self):
        from bazi_engine.ephemeris import datetime_utc_to_jd_ut
        for dt in (
            datetime(1950, 1, 1, tzinfo=timezone.utc),
            datetime(1990, 7, 15, 13, 44, tzinfo=timezone.utc),
            datetime(2024, 2, 21, 23, 59, 59, 999999, tzinfo=timezone.utc),
            datetime(2030, 12, 31, 18, tzinfo=timezone.utc),
        ):
            assert isclose(jd_ut_from_datetime(dt), datetime_utc_to_jd_ut(dt), abs_tol=1e-9)

    def test_jd_ut_from_datetime_accepts_non_utc_aware_and_rejects_naive(self):
        from zoneinfo import ZoneInfo
        berlin = datetime(1990, 7, 15, 15, 44, tzinfo=ZoneInfo("Europe/Berlin"))
        assert jd_ut_from_datetime(berlin) == jd_ut_from_datetime(berlin.astimezone(timezone.utc))
        with pytest.raises(ValueError):
            jd_ut_from_datetime(datetime(1990, 7, 15, 15, 44))

    def test_j2000_epoch(self):
        assert jd_ut_from_datetime(datetime(2000, 1, 1, 12, tzinfo=timezone.utc)) == 2451545.0
