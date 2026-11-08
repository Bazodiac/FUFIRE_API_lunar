"""Synthetic western charts for the synastry unit tests.

``make_chart`` builds the subset of a ``compute_western_chart`` result that the
synastry package reads: ``bodies[*].longitude``, ``angles``, ``houses`` and
``quality_flags``. Equal 30° houses starting at ``cusp_start`` keep the
expected house of every longitude computable by hand.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

BASE_A: Dict[str, float] = {
    "Sun": 10.0, "Moon": 100.0, "Mercury": 20.0, "Venus": 40.0, "Mars": 200.0,
    "Jupiter": 250.0, "Saturn": 300.0, "Uranus": 280.0, "Neptune": 285.0, "Pluto": 230.0,
}
BASE_B: Dict[str, float] = {
    "Sun": 130.0, "Moon": 188.0, "Mercury": 125.0, "Venus": 70.0, "Mars": 15.0,
    "Jupiter": 340.0, "Saturn": 45.0, "Uranus": 290.0, "Neptune": 292.0, "Pluto": 235.0,
}


def make_chart(
    planets: Dict[str, float],
    *,
    asc: float = 0.0,
    mc: float = 270.0,
    cusp_start: float = 0.0,
    ephemeris_mode: str = "SWIEPH",
    house_system_used: str = "placidus",
    fallback: bool = False,
) -> Dict[str, Any]:
    bodies = {name: {"longitude": lon % 360.0} for name, lon in planets.items()}
    houses = {str(i + 1): (cusp_start + 30.0 * i) % 360.0 for i in range(12)}
    return {
        "bodies": bodies,
        "angles": {"Ascendant": asc, "MC": mc, "Vertex": 0.0},
        "houses": houses,
        "quality_flags": {
            "house_system_fallback": fallback,
            "house_system_requested": "placidus",
            "house_system_used": house_system_used,
            "ephemeris_mode": ephemeris_mode,
        },
    }


def _aspect_key(a: Dict[str, Any]) -> Tuple[Any, ...]:
    return (a["from_factor"], a["to_factor"], a["type"], a["orb"], a["exact"], a["weight"])


def _pair_keys(result: Dict[str, Any]) -> List[Tuple[str, str, str, str]]:
    return sorted(
        (p["factor_a"], p["factor_b"], p["sign_relation"], p["element_relation"])
        for p in result["sign_layer"]["pairs"]
    )


def _warning_keys(result: Dict[str, Any], swap: bool) -> List[Tuple[Any, ...]]:
    flip = {"person_a": "person_b", "person_b": "person_a"}
    return sorted(
        (w["code"], flip.get(w["person"], w["person"]) if swap else w["person"], w.get("detail"))
        for w in result["provenance"]["warnings"]
    )


def _aspect_full(a: Dict[str, Any], swap: bool) -> Tuple[Any, ...]:
    frm, to = ("to", "from") if swap else ("from", "to")
    return (
        a[f"{frm}_factor"], a[f"{to}_factor"], a["type"], a["exact_angle"], a["orb"], a["exact"],
        a[f"{frm}_weight"], a[f"{to}_weight"], a["weight"],
    )


def assert_mirrored(r1: Dict[str, Any], r2: Dict[str, Any]) -> None:
    """r2 = result for the swapped request (B, A); r1 = result for (A, B)."""
    assert all(a["from_person"] == "person_a" and a["to_person"] == "person_b" for a in r1["aspects"] + r2["aspects"])
    mirrored = sorted(
        (a["to_factor"], a["from_factor"], a["type"], a["orb"], a["exact"], a["weight"]) for a in r1["aspects"]
    )
    assert sorted(_aspect_key(a) for a in r2["aspects"]) == mirrored
    assert r2["house_overlays"]["a_in_b"] == r1["house_overlays"]["b_in_a"]
    assert r2["house_overlays"]["b_in_a"] == r1["house_overlays"]["a_in_b"]
    f1, f2 = r1["sign_layer"]["factors"], r2["sign_layer"]["factors"]
    assert f2["person_a"] == f1["person_b"] and f2["person_b"] == f1["person_a"]
    assert _pair_keys(r2) == sorted((b, a, s, e) for a, b, s, e in _pair_keys(r1))
    w1, w2 = r1["wuxing_pair_factors"], r2["wuxing_pair_factors"]
    assert w2["person_a"] == w1["person_b"] and w2["person_b"] == w1["person_a"]
    hs1, hs2 = r1["provenance"]["house_system_used"], r2["provenance"]["house_system_used"]
    assert hs2 == {"person_a": hs1["person_b"], "person_b": hs1["person_a"]}
    assert sorted(_aspect_full(a, swap=False) for a in r2["aspects"]) == sorted(
        _aspect_full(a, swap=True) for a in r1["aspects"]
    )
    assert _warning_keys(r2, swap=False) == _warning_keys(r1, swap=True)
