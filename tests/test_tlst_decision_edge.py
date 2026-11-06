"""``time_context.nearest_tlst_decision_edge`` — pure edge arithmetic (INC-1)."""
from __future__ import annotations

import pytest

from bazi_engine.time_context import EOT_MODEL_TOLERANCE_MINUTES, nearest_tlst_decision_edge


def test_tolerance_constant_is_the_documented_bound():
    assert EOT_MODEL_TOLERANCE_MINUTES == 0.1


@pytest.mark.parametrize("hours,boundary,edge,kinds,dist", [
    (14.283, "midnight", 15.0, ("hour_branch",), 43.02),
    (22.999999, "zi", 23.0, ("hour_branch", "zi_day_start"), 0.00006),
    (22.999999, "midnight", 23.0, ("hour_branch",), 0.00006),
    (23.999, "midnight", 0.0, ("solar_midnight",), 0.06),
    (0.001, "midnight", 0.0, ("solar_midnight",), 0.06),
    (23.999, "zi", 23.0, ("hour_branch", "zi_day_start"), 59.94),
    (0.5, "zi", 1.0, ("hour_branch",), 30.0),
    (1.0, "midnight", 1.0, ("hour_branch",), 0.0),
])
def test_nearest_edge(hours, boundary, edge, kinds, dist):
    e = nearest_tlst_decision_edge(hours, day_boundary=boundary)
    assert e.edge_hours == edge
    assert e.kinds == kinds
    assert e.distance_minutes == pytest.approx(dist, abs=1e-6)


def test_within_tolerance_is_inclusive_and_tight():
    assert nearest_tlst_decision_edge(23.0 - 0.1 / 60, day_boundary="zi").within_eot_tolerance
    assert not nearest_tlst_decision_edge(23.0 - 0.11 / 60, day_boundary="zi").within_eot_tolerance


def test_non_default_zi_start_is_its_own_edge():
    e = nearest_tlst_decision_edge(22.0, day_boundary="zi", zi_start_hour=22.0)
    assert e.edge_hours == 22.0 and e.kinds == ("zi_day_start",)
