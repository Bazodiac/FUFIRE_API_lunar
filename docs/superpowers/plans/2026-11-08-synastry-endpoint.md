# Synastry Endpoint (G1 + G1b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /v1/relationship/synastry` returns deterministic western pair facts for two people (cross aspects, house overlays, sign layer, Wu-Xing translation via `sign-element-consensus-v1`) with no interpretation and no score.

**Architecture:** A new pure Level-4 package `bazi_engine/synastry/` (policy data, factor extraction, aspects, houses, signs, Wu-Xing layer, engine) works on two results of the existing `compute_western_chart()` — no own ephemeris calls. A thin Level-5 router `bazi_engine/routers/relationship.py` parses the request, enforces consent (Hehun parity), computes both charts, calls `compute_synastry()` and echoes `subjects`. Mounted `/v1` only, like Hehun.

**Tech Stack:** Python 3.10–3.12, FastAPI + Pydantic 2.12, pyswisseph (through `western.compute_western_chart`), pytest, ruff, mypy, uv.

**Spec:** `docs/superpowers/specs/2026-11-08-synastry-g1-design.md` (Part A = Ben's spec verbatim, Part B = decisions D1–D11). Read both before Task 1.

## Global Constraints

- Work only in the worktree `/Users/benjaminpoersch/FUFIRE/FUFIRE_API_lunar-wt-synastry`, branch `feat/synastry-g1`, based on `origin/master` = `6557de2`. The main checkout `~/FUFIRE/FUFIRE_API_lunar` is on a stale, dirty master — never edit there.
- **No push, no PR, no deploy** without Ben's explicit approval. Local commits only.
- Endpoint: `POST /v1/relationship/synastry`, `/v1` only (no legacy mount), protected by the API key, `@limiter.limit(tier_limit)`.
- Orb policy id `synastry-orbs-v1`: conjunction 8°, opposition 8°, trine 6°, square 6°, sextile 4°; same orbs with ASC/MC as partner; at most one aspect per pair; `exact` ⇔ orb ≤ half the orb limit.
- Mapping `sign-element-consensus-v1` (= `bazi_engine.wuxing.constants.WESTERN_MAPPING_ID`), vectors in `WUXING_ORDER` = `["Holz", "Feuer", "Erde", "Metall", "Wasser"]`.
- Weights: Fusion tiers `body-tier-q0.3-v1` (`western_body_weight`), MC overridden to tier 1 (D2); `weight = from_weight × to_weight` (D1).
- No field named or containing `score`, `compat`, `percent`, `rating`, `points` anywhere in request or response.
- No birth field (date/tz/lon/lat) and no `display_label` in any log record.
- Out of scope: composite, relationship transits, minor aspects, Chiron, nodes, interpretation text, cross resonance (G3), BaZi branch combinations (G2).
- Do not touch `WESTERN_BODY_TIER`, `aspects.py`, `western.py`, or any existing endpoint's output. Do not bump the engine build label (no existing output changes).
- Every new module goes into `LAYERS` in `tests/test_import_hierarchy.py` (unregistered modules are silently skipped).
- Lint scope is CI's: `ruff check bazi_engine/ tests/ scripts/`. New functions must have cyclomatic complexity ≤ 15.
- Release-please owns `CHANGELOG.md` and the version files — do not edit them.

## File Structure

| File | Responsibility |
|------|----------------|
| Create `bazi_engine/synastry/__init__.py` | Public re-exports of the package |
| Create `bazi_engine/synastry/policy.py` | Pure data: orb table, factor sets, MC tier override, sign names, relation labels, status/person literals |
| Create `bazi_engine/synastry/factors.py` | `extract_factors(chart, birth_time_known)` → ordered `{factor: longitude}` |
| Create `bazi_engine/synastry/aspects.py` | `classify_aspect`, `cross_aspects` (full A×B matrix) |
| Create `bazi_engine/synastry/houses.py` | `house_of`, `house_overlays` with the missing-time gate |
| Create `bazi_engine/synastry/signs.py` | `sign_entry`, `sign_relation`, `element_relation`, `sign_layer` |
| Create `bazi_engine/synastry/wuxing_layer.py` | `factor_vector`, `person_wuxing`, `wuxing_pair_factors` |
| Create `bazi_engine/synastry/engine.py` | `SynastryPersonInput`, `compute_synastry` (+ provenance, warnings) |
| Create `bazi_engine/routers/relationship.py` | Request/response models, consent gate, handler |
| Modify `bazi_engine/routers/registry.py` | One `Mount(relationship.router, legacy_prefix=None)` row |
| Modify `bazi_engine/openapi_ext.py` | Declare the `Relationship` tag |
| Modify `tests/test_import_hierarchy.py` | Register `synastry*` + `routers.relationship`; forbidden edges |
| Regenerate `tests/golden/route_table.json`, `spec/openapi/openapi.json` | Contract artefacts |
| Create `tests/fixtures/synastry_charts.py` | Synthetic chart builder + mirror assertion |
| Create `tests/fixtures/synastry_payloads.py` | HTTP payloads (test pair + sentinel pair) |
| Create `tests/test_synastry_policy.py`, `test_synastry_factors.py`, `test_synastry_aspects.py`, `test_synastry_houses.py`, `test_synastry_signs.py`, `test_synastry_wuxing.py`, `test_synastry_engine.py`, `test_synastry_endpoint.py`, `test_synastry_contract.py`, `test_synastry_example.py` | Tests |
| Create `scripts/gen_synastry_example.py` | Writes/checks the documented example pair |
| Create `docs/relationship/01_synastry.md`, `docs/relationship/examples/synastry_example_request.json`, `docs/relationship/examples/synastry_example_response.json` | Documentation + example |
| Modify `3-code/tasks.md` | Task row `REL-G1-001` |

---

### Task 1: Environment, policy data, factor extraction, layer registration

**Files:**
- Create: `bazi_engine/synastry/__init__.py`, `bazi_engine/synastry/policy.py`, `bazi_engine/synastry/factors.py`
- Create: `tests/fixtures/synastry_charts.py`, `tests/test_synastry_policy.py`, `tests/test_synastry_factors.py`
- Modify: `tests/test_import_hierarchy.py` (the `LAYERS` dict, lines 35–113; `FORBIDDEN_EDGES`, lines 125–135)

**Interfaces:**
- Consumes: `bazi_engine.wuxing.constants.western_body_weight(name) -> tuple[int, float]`, `WESTERN_TIER_WEIGHT: Dict[int, float]`; `bazi_engine.exc.CalculationError(message: str, *, detail=None)`; chart dicts as returned by `bazi_engine.western.compute_western_chart` (`bodies[name]["longitude"]`, `angles["Ascendant"|"MC"]`, `houses["1".."12"]`, `quality_flags["ephemeris_mode"|"house_system_used"|"house_system_fallback"]`).
- Produces (later tasks rely on these exact names):
  - `policy.SYNASTRY_ORB_POLICY_ID = "synastry-orbs-v1"`, `policy.SYNASTRY_WEIGHTING_ID = "synastry-weights-v1"`
  - `policy.SYNASTRY_ASPECTS: tuple[tuple[str, float, float], ...]` — `(type, exact_angle, orb_limit)`
  - `policy.PLANET_FACTORS`, `policy.ANGLE_FACTORS`, `policy.FACTOR_ORDER`, `policy.SIGN_LAYER_FACTORS` (tuples of str)
  - `policy.SYNASTRY_TIER_OVERRIDES = {"MC": 1}`, `policy.factor_weight(factor: str) -> tuple[int, float]`
  - `policy.ZODIAC_SIGNS: tuple[str, ...]` (12 German names), `policy.SIGN_RELATIONS: tuple[str, ...]` (index = sign distance 0..6)
  - `policy.PERSON_A = "person_a"`, `policy.PERSON_B = "person_b"`, `policy.STATUS_OK = "ok"`, `policy.STATUS_MISSING_TIME = "unavailable_missing_time"`
  - `factors.extract_factors(chart: Mapping[str, Any], *, birth_time_known: bool) -> Dict[str, float]` — keys in `FACTOR_ORDER` order, longitudes normalised to [0, 360)
  - `tests/fixtures/synastry_charts.make_chart(planets, *, asc=0.0, mc=270.0, cusp_start=0.0, ephemeris_mode="SWIEPH", house_system_used="placidus", fallback=False) -> Dict[str, Any]`, `BASE_A`, `BASE_B`

- [ ] **Step 0: Set up the worktree environment and a green baseline**

```bash
cd /Users/benjaminpoersch/FUFIRE/FUFIRE_API_lunar-wt-synastry
git log --oneline -1          # expect: 6557de2 feat(api): TLST is the standard BaZi time again …
git status --short            # expect: only the two new docs/superpowers files (untracked)
uv sync --frozen --extra dev
ls /tmp/ephe                  # expect the four files: seas_18.se1 semo_18.se1 sepl_18.se1 seplm06.se1
# if missing: uv run python scripts/fetch_ephemeris.py --destination /tmp/ephe
SE_EPHE_PATH=/tmp/ephe uv run pytest -q -x 2>&1 | tail -3
```
Expected: the baseline suite passes (record the pass/skip counts in your notes — Task 9 compares against them). If the baseline is red, stop and report; do not start Task 1 on a red base.

Commit the spec and this plan first so the branch carries them:
```bash
git add docs/superpowers/specs/2026-11-08-synastry-g1-design.md docs/superpowers/plans/2026-11-08-synastry-endpoint.md
git commit -m "docs(synastry): spec and implementation plan for /v1/relationship/synastry (G1 + G1b)"
```

- [ ] **Step 1: Write the chart fixture builder**

Create `tests/fixtures/synastry_charts.py`:

```python
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
```

(`assert_mirrored` is used from Task 6 on; it lives here so the engine test and the HTTP test share one definition.)

- [ ] **Step 2: Write the failing policy and factor tests**

Create `tests/test_synastry_policy.py`:

```python
"""Synastry policy data (spec 2026-11-08 §3, D1/D2/D8)."""
from __future__ import annotations

from bazi_engine.routers.shared import ZODIAC_SIGNS_DE
from bazi_engine.synastry.policy import (
    ANGLE_FACTORS,
    FACTOR_ORDER,
    PLANET_FACTORS,
    SIGN_LAYER_FACTORS,
    SIGN_RELATIONS,
    SYNASTRY_ASPECTS,
    SYNASTRY_ORB_POLICY_ID,
    ZODIAC_SIGNS,
    factor_weight,
)
from bazi_engine.wuxing.constants import western_body_weight


def test_orb_policy_matches_the_spec() -> None:
    assert SYNASTRY_ORB_POLICY_ID == "synastry-orbs-v1"
    assert SYNASTRY_ASPECTS == (
        ("conjunction", 0.0, 8.0),
        ("sextile", 60.0, 4.0),
        ("square", 90.0, 6.0),
        ("trine", 120.0, 6.0),
        ("opposition", 180.0, 8.0),
    )


def test_orb_windows_do_not_overlap() -> None:
    # One aspect per pair is guaranteed by construction, not by tie-breaking.
    windows = sorted((angle - orb, angle + orb) for _, angle, orb in SYNASTRY_ASPECTS)
    for (_, upper), (lower, _) in zip(windows, windows[1:]):
        assert upper < lower


def test_factor_sets() -> None:
    assert PLANET_FACTORS == (
        "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
    )
    assert ANGLE_FACTORS == ("Ascendant", "MC")
    assert FACTOR_ORDER == PLANET_FACTORS + ANGLE_FACTORS
    assert SIGN_LAYER_FACTORS == ("Sun", "Moon", "Mercury", "Venus", "Mars", "Ascendant")


def test_weights_follow_the_fusion_tiers() -> None:
    for factor in PLANET_FACTORS + ("Ascendant",):
        assert factor_weight(factor) == western_body_weight(factor)
    assert factor_weight("Sun") == (1, 1.0)
    assert factor_weight("Venus") == (2, 0.3)
    assert factor_weight("Saturn") == (3, 0.09)
    assert factor_weight("Pluto") == (4, 0.027)


def test_mc_is_tier_one_like_the_ascendant() -> None:
    # D2: the Fusion table would give MC the tier-4 fallback (0.027).
    assert western_body_weight("MC") == (4, 0.027)
    assert factor_weight("MC") == (1, 1.0)


def test_sign_names_match_the_names_the_api_already_emits() -> None:
    assert list(ZODIAC_SIGNS) == ZODIAC_SIGNS_DE


def test_sign_relations_are_indexed_by_sign_distance() -> None:
    assert SIGN_RELATIONS == (
        "same_sign", "semi_sextile", "sextile", "square", "trine", "quincunx", "opposition",
    )
```

Create `tests/test_synastry_factors.py`:

```python
"""Factor extraction from a western chart (spec §2)."""
from __future__ import annotations

import pytest

from bazi_engine.exc import CalculationError
from bazi_engine.synastry.factors import extract_factors
from bazi_engine.synastry.policy import ANGLE_FACTORS, PLANET_FACTORS
from tests.fixtures.synastry_charts import BASE_A, make_chart


def test_unknown_time_yields_the_ten_planets_only() -> None:
    factors = extract_factors(make_chart(BASE_A), birth_time_known=False)
    assert tuple(factors) == PLANET_FACTORS


def test_known_time_adds_ascendant_and_mc_last() -> None:
    factors = extract_factors(make_chart(BASE_A, asc=15.0, mc=280.0), birth_time_known=True)
    assert tuple(factors) == PLANET_FACTORS + ANGLE_FACTORS
    assert factors["Ascendant"] == 15.0
    assert factors["MC"] == 280.0
    assert factors["Sun"] == 10.0


def test_longitudes_are_normalised() -> None:
    factors = extract_factors(make_chart(BASE_A, asc=360.0, mc=-90.0), birth_time_known=True)
    assert factors["Ascendant"] == 0.0
    assert factors["MC"] == 270.0


def test_missing_planet_fails_visibly() -> None:
    chart = make_chart(BASE_A)
    chart["bodies"]["Pluto"] = {"error": "swe failure"}
    with pytest.raises(CalculationError, match="Pluto"):
        extract_factors(chart, birth_time_known=True)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synastry_policy.py tests/test_synastry_factors.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'bazi_engine.synastry'`.

- [ ] **Step 4: Implement policy, factors and the package init**

Create `bazi_engine/synastry/policy.py`:

```python
"""synastry/policy.py — fixed policy data for the synastry layer (pure data).

Level 4. Decisions: docs/superpowers/specs/2026-11-08-synastry-g1-design.md.

Orb table ``synastry-orbs-v1`` comes from Astro-Noctum (spec §3) and is the
same when the ascendant or MC is a partner. The windows do not overlap, so a
pair can match at most one aspect. Weights reuse the Fusion tiers
(``body-tier-q0.3-v1``); MC, which the Fusion table does not list, counts as
tier 1 like the ascendant (D2). The Fusion table itself is not changed.
"""
from __future__ import annotations

from typing import Dict, Final, Tuple

from ..wuxing.constants import WESTERN_TIER_WEIGHT, western_body_weight

SYNASTRY_ORB_POLICY_ID: Final[str] = "synastry-orbs-v1"
SYNASTRY_WEIGHTING_ID: Final[str] = "synastry-weights-v1"

# (type, exact angle, orb limit in degrees)
SYNASTRY_ASPECTS: Final[Tuple[Tuple[str, float, float], ...]] = (
    ("conjunction", 0.0, 8.0),
    ("sextile", 60.0, 4.0),
    ("square", 90.0, 6.0),
    ("trine", 120.0, 6.0),
    ("opposition", 180.0, 8.0),
)

PLANET_FACTORS: Final[Tuple[str, ...]] = (
    "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
)
# Only when the person's birth time is known.
ANGLE_FACTORS: Final[Tuple[str, ...]] = ("Ascendant", "MC")
FACTOR_ORDER: Final[Tuple[str, ...]] = PLANET_FACTORS + ANGLE_FACTORS
# G1b sign layer (spec §5) and its Wu-Xing translation (spec §6, D3).
SIGN_LAYER_FACTORS: Final[Tuple[str, ...]] = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Ascendant")

SYNASTRY_TIER_OVERRIDES: Final[Dict[str, int]] = {"MC": 1}


def factor_weight(factor: str) -> Tuple[int, float]:
    """Tier and weight of a synastry factor (Fusion tiers, MC tier 1)."""
    if factor in SYNASTRY_TIER_OVERRIDES:
        tier = SYNASTRY_TIER_OVERRIDES[factor]
        return tier, WESTERN_TIER_WEIGHT[tier]
    return western_body_weight(factor)


# Literal copy of routers.shared.ZODIAC_SIGNS_DE (Level 5, not importable here);
# tests/test_synastry_policy.py pins the two equal.
ZODIAC_SIGNS: Final[Tuple[str, ...]] = (
    "Widder", "Stier", "Zwillinge", "Krebs", "Löwe", "Jungfrau",
    "Waage", "Skorpion", "Schütze", "Steinbock", "Wassermann", "Fische",
)

# Index = shortest distance between two signs (0..6).
SIGN_RELATIONS: Final[Tuple[str, ...]] = (
    "same_sign", "semi_sextile", "sextile", "square", "trine", "quincunx", "opposition",
)

PERSON_A: Final[str] = "person_a"
PERSON_B: Final[str] = "person_b"

STATUS_OK: Final[str] = "ok"
STATUS_MISSING_TIME: Final[str] = "unavailable_missing_time"
```

Create `bazi_engine/synastry/factors.py`:

```python
"""synastry/factors.py — the synastry factors of one western chart."""
from __future__ import annotations

from typing import Any, Dict, Mapping

from ..exc import CalculationError
from .policy import ANGLE_FACTORS, PLANET_FACTORS


def extract_factors(chart: Mapping[str, Any], *, birth_time_known: bool) -> Dict[str, float]:
    """Return ``{factor: longitude}`` in ``FACTOR_ORDER``.

    The ten planets always; ascendant and MC only when the birth time is
    known (spec §2). A planet the chart could not compute fails loudly instead
    of silently shrinking the factor set.
    """
    bodies = chart["bodies"]
    factors: Dict[str, float] = {}
    for name in PLANET_FACTORS:
        body = bodies.get(name, {})
        if "longitude" not in body:
            raise CalculationError(
                f"Synastry factor {name} is missing from the western chart",
                detail={"factor": name},
            )
        factors[name] = float(body["longitude"]) % 360.0
    if birth_time_known:
        for name in ANGLE_FACTORS:
            factors[name] = float(chart["angles"][name]) % 360.0
    return factors
```

Create `bazi_engine/synastry/__init__.py`:

```python
"""bazi_engine/synastry — western pair facts for two charts (G1 + G1b).

Level 4. Pure functions over two ``compute_western_chart`` results: no
ephemeris calls, no BaZi, no routers. No interpretation and no score.
Decisions: docs/superpowers/specs/2026-11-08-synastry-g1-design.md.
"""
from .factors import extract_factors
from .policy import (
    FACTOR_ORDER,
    SIGN_LAYER_FACTORS,
    SYNASTRY_ASPECTS,
    SYNASTRY_ORB_POLICY_ID,
    SYNASTRY_WEIGHTING_ID,
    factor_weight,
)

__all__ = [
    "FACTOR_ORDER",
    "SIGN_LAYER_FACTORS",
    "SYNASTRY_ASPECTS",
    "SYNASTRY_ORB_POLICY_ID",
    "SYNASTRY_WEIGHTING_ID",
    "extract_factors",
    "factor_weight",
]
```

- [ ] **Step 5: Register the package in the layer map**

In `tests/test_import_hierarchy.py`, inside `LAYERS`, directly after the `"match.observability":   4,` line, add:

```python
    # synastry sub-modules are Level 4 (western pair facts, spec 2026-11-08):
    # Levels 0-4 only; FORBIDDEN_EDGES below keeps them free of BaZi/ZWDS/match.
    "synastry":              4,
    "synastry.policy":       4,
    "synastry.factors":      4,
    "synastry.aspects":      4,
    "synastry.houses":       4,
    "synastry.signs":        4,
    "synastry.wuxing_layer": 4,
    "synastry.engine":       4,
```

and directly after the `"routers.astronomy":    5,` line:

```python
    "routers.relationship": 5,
```

In `FORBIDDEN_EDGES`, after the `("synergy", ("routers", "app")),` entry, add:

```python
    # synastry is western-only (G1): BaZi pair layers are G2, cross resonance
    # is G3 and belongs in synergy/. It must not reach into either engine.
    ("synastry", ("bazi", "zwds", "match", "impact", "fusion")),
```

(Modules that do not exist yet — aspects, houses, signs, wuxing_layer, engine, routers.relationship — are harmless entries until their task creates them.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_synastry_policy.py tests/test_synastry_factors.py tests/test_import_hierarchy.py -q`
Expected: all PASS.

Run: `uv run pytest tests/test_import_hierarchy.py -q -rs 2>&1 | grep "not registered" | grep -c synastry`
Expected: `0` (no synastry module is skipped as unregistered).

- [ ] **Step 7: Canary the forbidden edge**

Temporarily add `from ..bazi import compute_bazi  # noqa: F401` as the last import line of `bazi_engine/synastry/factors.py`.
Run: `uv run pytest tests/test_import_hierarchy.py -q 2>&1 | tail -3`
Expected: FAIL naming `synastry.factors` and `bazi`. Remove the line again, re-run, expect PASS. (A gate that was never seen red is `not_run`.)

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check bazi_engine/synastry tests/test_synastry_policy.py tests/test_synastry_factors.py tests/fixtures/synastry_charts.py tests/test_import_hierarchy.py
uv run mypy bazi_engine --ignore-missing-imports
git add bazi_engine/synastry tests/fixtures/synastry_charts.py tests/test_synastry_policy.py tests/test_synastry_factors.py tests/test_import_hierarchy.py
git commit -m "feat(synastry): policy data, factor extraction and layer registration"
```

---

### Task 2: Cross aspects with the synastry orb table

**Files:**
- Create: `bazi_engine/synastry/aspects.py`
- Test: `tests/test_synastry_aspects.py`

**Interfaces:**
- Consumes: `policy.SYNASTRY_ASPECTS`, `policy.factor_weight`.
- Produces:
  - `aspects.AspectHit(NamedTuple)`: `type: str`, `exact_angle: float`, `orb: float` (unrounded), `orb_limit: float`
  - `aspects.angular_separation(lon1: float, lon2: float) -> float` in [0, 180]
  - `aspects.classify_aspect(lon_from: float, lon_to: float) -> Optional[AspectHit]`
  - `aspects.cross_aspects(factors_from: Mapping[str, float], factors_to: Mapping[str, float], *, from_person: str, to_person: str) -> List[Dict[str, Any]]` — row keys: `from_person, from_factor, to_person, to_factor, type, exact_angle, orb (4 dp), exact, from_weight, to_weight, weight (6 dp)`; order = from-factor order, then to-factor order.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_synastry_aspects.py`:

```python
"""Synastry cross aspects (spec §3, D1, D7)."""
from __future__ import annotations

import pytest

from bazi_engine.synastry.aspects import angular_separation, classify_aspect, cross_aspects

# (aspect, separation exactly at the orb limit, separation just beyond it)
BOUNDARIES = [
    ("conjunction", 8.0, 8.01),
    ("sextile", 64.0, 64.01),
    ("sextile", 56.0, 55.99),
    ("square", 96.0, 96.01),
    ("square", 84.0, 83.99),
    ("trine", 126.0, 126.01),
    ("trine", 114.0, 113.99),
    ("opposition", 172.0, 171.99),
]


@pytest.mark.parametrize("aspect, at_limit, beyond", BOUNDARIES)
def test_orb_limit_is_inclusive_and_just_beyond_is_out(aspect: str, at_limit: float, beyond: float) -> None:
    hit = classify_aspect(0.0, at_limit)
    assert hit is not None
    assert hit.type == aspect
    assert classify_aspect(0.0, beyond) is None


def test_every_aspect_type_has_a_boundary_fixture() -> None:
    assert {b[0] for b in BOUNDARIES} == {"conjunction", "sextile", "square", "trine", "opposition"}


def test_separation_wraps_over_the_aries_point() -> None:
    assert angular_separation(355.0, 3.0) == 8.0
    hit = classify_aspect(355.0, 3.0)
    assert hit is not None and hit.type == "conjunction" and hit.orb == 8.0


def test_direction_does_not_change_the_hit() -> None:
    assert classify_aspect(10.0, 130.5) == classify_aspect(130.5, 10.0)


@pytest.mark.parametrize("lon_to, exact", [(4.0, True), (4.01, False), (62.0, True), (62.01, False)])
def test_exact_means_orb_within_half_the_limit(lon_to: float, exact: bool) -> None:
    rows = cross_aspects({"Sun": 0.0}, {"Moon": lon_to}, from_person="person_a", to_person="person_b")
    assert len(rows) == 1
    assert rows[0]["exact"] is exact


def test_row_shape_and_weights() -> None:
    rows = cross_aspects(
        {"Sun": 0.0},
        {"Moon": 8.0, "Venus": 8.01, "Mars": 180.0, "Pluto": 120.0},
        from_person="person_a",
        to_person="person_b",
    )
    assert rows == [
        {
            "from_person": "person_a", "from_factor": "Sun", "to_person": "person_b", "to_factor": "Moon",
            "type": "conjunction", "exact_angle": 0.0, "orb": 8.0, "exact": False,
            "from_weight": 1.0, "to_weight": 1.0, "weight": 1.0,
        },
        {
            "from_person": "person_a", "from_factor": "Sun", "to_person": "person_b", "to_factor": "Mars",
            "type": "opposition", "exact_angle": 180.0, "orb": 0.0, "exact": True,
            "from_weight": 1.0, "to_weight": 0.3, "weight": 0.3,
        },
        {
            "from_person": "person_a", "from_factor": "Sun", "to_person": "person_b", "to_factor": "Pluto",
            "type": "trine", "exact_angle": 120.0, "orb": 0.0, "exact": True,
            "from_weight": 1.0, "to_weight": 0.027, "weight": 0.027,
        },
    ]


def test_full_cross_matrix_not_only_i_lt_j() -> None:
    rows = cross_aspects(
        {"Sun": 0.0, "Moon": 0.0}, {"Sun": 0.0, "Moon": 0.0}, from_person="person_a", to_person="person_b",
    )
    assert [(r["from_factor"], r["to_factor"]) for r in rows] == [
        ("Sun", "Sun"), ("Sun", "Moon"), ("Moon", "Sun"), ("Moon", "Moon"),
    ]


def test_angles_take_the_same_orbs_and_mc_weighs_one() -> None:
    rows = cross_aspects({"Venus": 0.0}, {"Ascendant": 8.0, "MC": 64.0}, from_person="person_a", to_person="person_b")
    assert [(r["to_factor"], r["type"], r["weight"]) for r in rows] == [
        ("Ascendant", "conjunction", 0.3), ("MC", "sextile", 0.3),
    ]


def test_tier_products_are_rounded_free_of_float_noise() -> None:
    rows = cross_aspects({"Venus": 0.0}, {"Saturn": 0.0}, from_person="person_a", to_person="person_b")
    assert rows[0]["weight"] == 0.027  # 0.3 * 0.09 = 0.026999999999999996 unrounded
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synastry_aspects.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'bazi_engine.synastry.aspects'`.

- [ ] **Step 3: Implement**

Create `bazi_engine/synastry/aspects.py`:

```python
"""synastry/aspects.py — aspects between two charts (spec §3).

Full cross matrix A×B (not i<j), five major aspects, orb table
``synastry-orbs-v1``, at most one aspect per pair. Inclusion and ``exact`` are
decided on unrounded values; ``orb`` is rounded for output only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, NamedTuple, Optional

from .policy import SYNASTRY_ASPECTS, factor_weight


class AspectHit(NamedTuple):
    type: str
    exact_angle: float
    orb: float
    orb_limit: float


def angular_separation(lon1: float, lon2: float) -> float:
    """Shortest angular distance between two ecliptic longitudes (0–180°)."""
    diff = abs(lon1 - lon2) % 360.0
    return min(diff, 360.0 - diff)


def classify_aspect(lon_from: float, lon_to: float) -> Optional[AspectHit]:
    """The one aspect whose orb window contains the separation, else None."""
    separation = angular_separation(lon_from, lon_to)
    for name, angle, orb_limit in SYNASTRY_ASPECTS:
        deviation = abs(separation - angle)
        if deviation <= orb_limit:
            return AspectHit(name, angle, deviation, orb_limit)
    return None


def _aspect_row(
    from_person: str, from_factor: str, to_person: str, to_factor: str, hit: AspectHit,
) -> Dict[str, Any]:
    _, from_weight = factor_weight(from_factor)
    _, to_weight = factor_weight(to_factor)
    return {
        "from_person": from_person,
        "from_factor": from_factor,
        "to_person": to_person,
        "to_factor": to_factor,
        "type": hit.type,
        "exact_angle": hit.exact_angle,
        "orb": round(hit.orb, 4),
        "exact": hit.orb <= hit.orb_limit / 2.0,
        "from_weight": from_weight,
        "to_weight": to_weight,
        "weight": round(from_weight * to_weight, 6),
    }


def cross_aspects(
    factors_from: Mapping[str, float],
    factors_to: Mapping[str, float],
    *,
    from_person: str,
    to_person: str,
) -> List[Dict[str, Any]]:
    """Every aspect between a factor of ``factors_from`` and one of ``factors_to``."""
    rows: List[Dict[str, Any]] = []
    for from_factor, lon_from in factors_from.items():
        for to_factor, lon_to in factors_to.items():
            hit = classify_aspect(lon_from, lon_to)
            if hit is not None:
                rows.append(_aspect_row(from_person, from_factor, to_person, to_factor, hit))
    return rows
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_synastry_aspects.py -q`
Expected: all PASS (19 tests incl. parametrisations).

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check bazi_engine/synastry tests/test_synastry_aspects.py && uv run mypy bazi_engine --ignore-missing-imports
git add bazi_engine/synastry/aspects.py tests/test_synastry_aspects.py
git commit -m "feat(synastry): cross aspects with the synastry-orbs-v1 table"
```

---

### Task 3: House overlays with the missing-time gate

**Files:**
- Create: `bazi_engine/synastry/houses.py`
- Test: `tests/test_synastry_houses.py`

**Interfaces:**
- Consumes: `policy.PLANET_FACTORS`, `policy.STATUS_OK`, `policy.STATUS_MISSING_TIME`, `CalculationError`.
- Produces:
  - `houses.house_of(longitude: float, cusps: Mapping[str, float]) -> int` (1..12; a cusp belongs to the house it opens)
  - `houses.house_overlays(guest_factors: Mapping[str, float], host_chart: Mapping[str, Any], *, host_time_known: bool) -> List[Dict[str, Any]]` — one row per planet in `PLANET_FACTORS` order: `{"factor", "house": int | None, "status"}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_synastry_houses.py`:

```python
"""House overlays (spec §4, D6)."""
from __future__ import annotations

import pytest

from bazi_engine.exc import CalculationError
from bazi_engine.synastry.houses import house_of, house_overlays
from bazi_engine.synastry.policy import PLANET_FACTORS
from tests.fixtures.synastry_charts import BASE_A, make_chart

EQUAL_FROM_0 = {str(i + 1): 30.0 * i for i in range(12)}
EQUAL_FROM_350 = {str(i + 1): (350.0 + 30.0 * i) % 360.0 for i in range(12)}
UNEQUAL = {
    "1": 100.0, "2": 125.0, "3": 155.0, "4": 190.0, "5": 220.0, "6": 250.0,
    "7": 280.0, "8": 305.0, "9": 335.0, "10": 10.0, "11": 40.0, "12": 70.0,
}


@pytest.mark.parametrize("lon, house", [(0.0, 1), (29.999, 1), (30.0, 2), (185.0, 7), (359.9, 12)])
def test_equal_houses(lon: float, house: int) -> None:
    assert house_of(lon, EQUAL_FROM_0) == house


@pytest.mark.parametrize("lon, house", [(350.0, 1), (355.0, 1), (5.0, 1), (20.0, 2), (349.9, 12)])
def test_house_one_spanning_the_aries_point(lon: float, house: int) -> None:
    assert house_of(lon, EQUAL_FROM_350) == house


@pytest.mark.parametrize("lon, house", [(100.0, 1), (124.9, 1), (125.0, 2), (5.0, 9), (10.0, 10), (99.9, 12)])
def test_unequal_houses(lon: float, house: int) -> None:
    assert house_of(lon, UNEQUAL) == house


def test_degenerate_cusps_fail_visibly() -> None:
    with pytest.raises(CalculationError):
        house_of(10.0, {str(i + 1): 0.0 for i in range(12)})


def test_overlays_when_the_host_time_is_known() -> None:
    guest = {**BASE_A, "Ascendant": 5.0, "MC": 275.0}
    rows = house_overlays(guest, make_chart(BASE_A, cusp_start=0.0), host_time_known=True)
    assert [r["factor"] for r in rows] == list(PLANET_FACTORS)  # D6: no ASC/MC rows
    assert rows[0] == {"factor": "Sun", "house": 1, "status": "ok"}       # 10°
    assert rows[1] == {"factor": "Moon", "house": 4, "status": "ok"}      # 100°
    assert rows[4] == {"factor": "Mars", "house": 7, "status": "ok"}      # 200°


def test_overlays_are_gated_when_the_host_time_is_unknown() -> None:
    rows = house_overlays(BASE_A, make_chart(BASE_A), host_time_known=False)
    assert rows == [{"factor": f, "house": None, "status": "unavailable_missing_time"} for f in PLANET_FACTORS]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synastry_houses.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'bazi_engine.synastry.houses'`.

- [ ] **Step 3: Implement**

Create `bazi_engine/synastry/houses.py`:

```python
"""synastry/houses.py — one person's planets in the other person's houses (spec §4)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from ..exc import CalculationError
from .policy import PLANET_FACTORS, STATUS_MISSING_TIME, STATUS_OK


def house_of(longitude: float, cusps: Mapping[str, float]) -> int:
    """House (1–12) containing ``longitude``; a cusp belongs to the house it opens."""
    lon = longitude % 360.0
    for house in range(1, 13):
        start = float(cusps[str(house)]) % 360.0
        end = float(cusps[str(house % 12 + 1)]) % 360.0
        span = (end - start) % 360.0
        if span > 0.0 and (lon - start) % 360.0 < span:
            return house
    raise CalculationError("Longitude could not be placed in any house", detail={})


def house_overlays(
    guest_factors: Mapping[str, float],
    host_chart: Mapping[str, Any],
    *,
    host_time_known: bool,
) -> List[Dict[str, Any]]:
    """The guest's ten planets in the host's houses.

    Gate: without the host's birth time the host has no houses, so every row
    is ``unavailable_missing_time`` with ``house: None`` (no values).
    """
    if not host_time_known:
        return [{"factor": f, "house": None, "status": STATUS_MISSING_TIME} for f in PLANET_FACTORS]
    cusps = host_chart["houses"]
    return [
        {"factor": f, "house": house_of(guest_factors[f], cusps), "status": STATUS_OK}
        for f in PLANET_FACTORS
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_synastry_houses.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check bazi_engine/synastry tests/test_synastry_houses.py && uv run mypy bazi_engine --ignore-missing-imports
git add bazi_engine/synastry/houses.py tests/test_synastry_houses.py
git commit -m "feat(synastry): house overlays with the missing-time gate"
```

---

### Task 4: Sign layer (G1b)

**Files:**
- Create: `bazi_engine/synastry/signs.py`
- Test: `tests/test_synastry_signs.py`

**Interfaces:**
- Consumes: `policy.ZODIAC_SIGNS`, `policy.SIGN_RELATIONS`, `policy.SIGN_LAYER_FACTORS`, `policy.PERSON_A/B`, `bazi_engine.wuxing.constants.SIGN_ELEMENT`.
- Produces:
  - `signs.sign_entry(factor: str, longitude: float) -> Dict[str, Any]` — `{"factor", "sign", "sign_index", "west_element", "degree"}` (degree in sign, 4 dp)
  - `signs.sign_relation(index_a: int, index_b: int) -> str`
  - `signs.element_relation(element_a: str, element_b: str) -> str` — `"same" | "complementary" | "other"`
  - `signs.sign_layer(factors_a: Mapping[str, float], factors_b: Mapping[str, float]) -> Dict[str, Any]` — `{"factors": {"person_a": [entry…], "person_b": [entry…]}, "pairs": [{"factor_a", "factor_b", "sign_relation", "element_relation"}…]}`; pairs = full cross product in `SIGN_LAYER_FACTORS` order.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_synastry_signs.py`:

```python
"""Sign layer (spec §5, D8)."""
from __future__ import annotations

import pytest

from bazi_engine.synastry.signs import element_relation, sign_entry, sign_layer, sign_relation


@pytest.mark.parametrize(
    "lon_b, relation",
    [
        (5.0, "same_sign"),
        (35.0, "semi_sextile"),
        (65.0, "sextile"),
        (95.0, "square"),
        (125.0, "trine"),
        (155.0, "quincunx"),
        (185.0, "opposition"),
    ],
)
def test_all_seven_sign_distance_classes(lon_b: float, relation: str) -> None:
    a = sign_entry("Sun", 5.0)
    b = sign_entry("Moon", lon_b)
    assert sign_relation(a["sign_index"], b["sign_index"]) == relation


def test_sign_distance_is_the_shorter_way_round() -> None:
    assert sign_relation(11, 0) == "semi_sextile"
    assert sign_relation(0, 7) == "quincunx"
    assert sign_relation(0, 10) == "sextile"
    assert sign_relation(2, 9) == sign_relation(9, 2)


def test_sign_entry() -> None:
    assert sign_entry("Venus", 245.5) == {
        "factor": "Venus", "sign": "Schütze", "sign_index": 8, "west_element": "Feuer", "degree": 5.5,
    }
    assert sign_entry("Sun", 0.0)["sign"] == "Widder"
    assert sign_entry("Sun", 359.5)["sign"] == "Fische"


@pytest.mark.parametrize(
    "a, b, relation",
    [
        ("Feuer", "Feuer", "same"),
        ("Wasser", "Wasser", "same"),
        ("Feuer", "Luft", "complementary"),
        ("Luft", "Feuer", "complementary"),
        ("Erde", "Wasser", "complementary"),
        ("Wasser", "Erde", "complementary"),
        ("Feuer", "Wasser", "other"),
        ("Erde", "Luft", "other"),
        ("Feuer", "Erde", "other"),
        ("Luft", "Wasser", "other"),
    ],
)
def test_element_relations(a: str, b: str, relation: str) -> None:
    assert element_relation(a, b) == relation


def test_sign_layer_shape_without_an_ascendant_for_b() -> None:
    a = {"Sun": 5.0, "Moon": 40.0, "Mercury": 70.0, "Venus": 100.0, "Mars": 130.0, "Ascendant": 160.0,
         "Jupiter": 1.0, "MC": 2.0}
    b = {"Sun": 185.0, "Moon": 215.0, "Mercury": 250.0, "Venus": 280.0, "Mars": 310.0, "Jupiter": 3.0}
    layer = sign_layer(a, b)
    assert [e["factor"] for e in layer["factors"]["person_a"]] == ["Sun", "Moon", "Mercury", "Venus", "Mars", "Ascendant"]
    assert [e["factor"] for e in layer["factors"]["person_b"]] == ["Sun", "Moon", "Mercury", "Venus", "Mars"]
    assert len(layer["pairs"]) == 30
    assert layer["pairs"][0] == {
        "factor_a": "Sun", "factor_b": "Sun", "sign_relation": "opposition", "element_relation": "complementary",
    }
    assert all(p["factor_b"] != "Ascendant" for p in layer["pairs"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synastry_signs.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'bazi_engine.synastry.signs'`.

- [ ] **Step 3: Implement**

Create `bazi_engine/synastry/signs.py`:

```python
"""synastry/signs.py — the sign layer of the synastry (G1b, spec §5)."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from ..wuxing.constants import SIGN_ELEMENT
from .policy import PERSON_A, PERSON_B, SIGN_LAYER_FACTORS, SIGN_RELATIONS, ZODIAC_SIGNS

# Elements that share a polarity: Feuer–Luft (active), Erde–Wasser (receptive).
_COMPLEMENTARY = (frozenset({"Feuer", "Luft"}), frozenset({"Erde", "Wasser"}))


def sign_entry(factor: str, longitude: float) -> Dict[str, Any]:
    lon = longitude % 360.0
    index = int(lon // 30.0) % 12
    return {
        "factor": factor,
        "sign": ZODIAC_SIGNS[index],
        "sign_index": index,
        "west_element": SIGN_ELEMENT[index],
        "degree": round(lon - 30.0 * index, 4),
    }


def sign_relation(index_a: int, index_b: int) -> str:
    distance = abs(index_a - index_b) % 12
    return SIGN_RELATIONS[min(distance, 12 - distance)]


def element_relation(element_a: str, element_b: str) -> str:
    if element_a == element_b:
        return "same"
    if frozenset({element_a, element_b}) in _COMPLEMENTARY:
        return "complementary"
    return "other"


def _entries(factors: Mapping[str, float]) -> List[Dict[str, Any]]:
    return [sign_entry(f, factors[f]) for f in SIGN_LAYER_FACTORS if f in factors]


def sign_layer(factors_a: Mapping[str, float], factors_b: Mapping[str, float]) -> Dict[str, Any]:
    entries_a = _entries(factors_a)
    entries_b = _entries(factors_b)
    pairs = [
        {
            "factor_a": a["factor"],
            "factor_b": b["factor"],
            "sign_relation": sign_relation(a["sign_index"], b["sign_index"]),
            "element_relation": element_relation(a["west_element"], b["west_element"]),
        }
        for a in entries_a
        for b in entries_b
    ]
    return {"factors": {PERSON_A: entries_a, PERSON_B: entries_b}, "pairs": pairs}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_synastry_signs.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check bazi_engine/synastry tests/test_synastry_signs.py && uv run mypy bazi_engine --ignore-missing-imports
git add bazi_engine/synastry/signs.py tests/test_synastry_signs.py
git commit -m "feat(synastry): sign layer with sign-distance and element relations (G1b)"
```

---

### Task 5: Wu-Xing translation through the consensus matrix

**Files:**
- Create: `bazi_engine/synastry/wuxing_layer.py`
- Test: `tests/test_synastry_wuxing.py`

**Interfaces:**
- Consumes: sign entries from `signs.sign_entry` (`factor`, `west_element`); `policy.factor_weight`; `wuxing.constants.WEST_ELEMENT_TO_WUXING`, `WUXING_ORDER`, `WESTERN_MAPPING_ID`.
- Produces:
  - `wuxing_layer.factor_vector(west_element: str) -> List[float]` — 5 floats in `WUXING_ORDER`, sum 1
  - `wuxing_layer.person_wuxing(entries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]` — `{"factors": [{"factor", "west_element", "weight", "vector"}], "vector": [5 floats, 6 dp, sum 1]}`
  - `wuxing_layer.wuxing_pair_factors(entries_a, entries_b) -> Dict[str, Any]` — `{"order": WUXING_ORDER, "person_a": person_wuxing(...), "person_b": person_wuxing(...), "mapping_version": "sign-element-consensus-v1"}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_synastry_wuxing.py`:

```python
"""Wu-Xing translation of the sign layer (spec §6, D3)."""
from __future__ import annotations

import pytest

from bazi_engine.provenance import WUXING_PARAMETER_SET
from bazi_engine.synastry.signs import sign_entry
from bazi_engine.synastry.wuxing_layer import factor_vector, person_wuxing, wuxing_pair_factors
from bazi_engine.wuxing import calculate_wuxing_vector_from_planets_with_ledger
from bazi_engine.wuxing.constants import SIGN_ELEMENT, WESTERN_MAPPING_ID, WUXING_ORDER


@pytest.mark.parametrize("element", ["Feuer", "Erde", "Luft", "Wasser"])
def test_each_factor_vector_sums_to_one(element: str) -> None:
    assert sum(factor_vector(element)) == pytest.approx(1.0, abs=1e-12)


def test_vector_is_in_wuxing_order() -> None:
    assert WUXING_ORDER == ["Holz", "Feuer", "Erde", "Metall", "Wasser"]
    assert factor_vector("Feuer") == [0.452, 0.548, 0.0, 0.0, 0.0]
    assert factor_vector("Wasser") == [0.0, 0.0, 0.306, 0.101, 0.593]


@pytest.mark.parametrize("lon", [5.0, 35.0, 65.0, 95.0])
def test_same_matrix_as_the_fusion_vector(lon: float) -> None:
    # A lone Sun (tier 1, weight 1.0) in the Fusion ledger distributes exactly
    # one matrix row; the synastry factor vector must be that row.
    _, ledger = calculate_wuxing_vector_from_planets_with_ledger({"Sun": {"longitude": lon}})
    expected = [ledger[0]["distribution"].get(p, 0.0) for p in WUXING_ORDER]
    assert factor_vector(SIGN_ELEMENT[int(lon // 30)]) == pytest.approx(expected, abs=1e-9)


def test_person_vector_is_the_tier_weighted_mean() -> None:
    entries = [sign_entry("Sun", 5.0), sign_entry("Mars", 35.0)]  # Feuer w=1.0, Erde w=0.3
    out = person_wuxing(entries)
    fire, earth = factor_vector("Feuer"), factor_vector("Erde")
    expected = [round((1.0 * f + 0.3 * e) / 1.3, 6) for f, e in zip(fire, earth)]
    assert out["vector"] == expected
    assert out["factors"] == [
        {"factor": "Sun", "west_element": "Feuer", "weight": 1.0, "vector": fire},
        {"factor": "Mars", "west_element": "Erde", "weight": 0.3, "vector": earth},
    ]


def test_person_vector_sums_to_one() -> None:
    entries = [sign_entry(f, lon) for f, lon in
               [("Sun", 5.0), ("Moon", 100.0), ("Mercury", 200.0), ("Venus", 300.0), ("Mars", 50.0), ("Ascendant", 170.0)]]
    assert sum(person_wuxing(entries)["vector"]) == pytest.approx(1.0, abs=1e-5)


def test_mapping_version_is_the_one_fusion_attests() -> None:
    out = wuxing_pair_factors([sign_entry("Sun", 5.0)], [sign_entry("Sun", 95.0)])
    assert out["mapping_version"] == "sign-element-consensus-v1"
    assert out["mapping_version"] == WESTERN_MAPPING_ID
    assert out["mapping_version"] == WUXING_PARAMETER_SET["western_mapping_id"]
    assert out["order"] == WUXING_ORDER
    assert set(out) == {"order", "person_a", "person_b", "mapping_version"}  # no comparison number
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synastry_wuxing.py -q`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'bazi_engine.synastry.wuxing_layer'`.

- [ ] **Step 3: Implement**

Create `bazi_engine/synastry/wuxing_layer.py`:

```python
"""synastry/wuxing_layer.py — Wu-Xing translation of the sign layer (spec §6, D3).

Each sign-layer factor is spread over the five phases by the consensus matrix
``sign-element-consensus-v1`` (the Fusion vector's matrix). The person vector
is the tier-weighted mean of the factor vectors (sum 1). No comparison number
between the two persons is computed (G1).
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from ..wuxing.constants import WEST_ELEMENT_TO_WUXING, WESTERN_MAPPING_ID, WUXING_ORDER
from .policy import PERSON_A, PERSON_B, factor_weight


def factor_vector(west_element: str) -> List[float]:
    shares = WEST_ELEMENT_TO_WUXING[west_element]
    return [shares[phase] for phase in WUXING_ORDER]


def person_wuxing(entries: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    factors: List[Dict[str, Any]] = []
    totals = [0.0] * len(WUXING_ORDER)
    weight_sum = 0.0
    for entry in entries:
        _, weight = factor_weight(entry["factor"])
        vector = factor_vector(entry["west_element"])
        factors.append({"factor": entry["factor"], "west_element": entry["west_element"],
                        "weight": weight, "vector": vector})
        totals = [t + weight * v for t, v in zip(totals, vector)]
        weight_sum += weight
    return {"factors": factors, "vector": [round(t / weight_sum, 6) for t in totals]}


def wuxing_pair_factors(
    entries_a: Sequence[Mapping[str, Any]], entries_b: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    return {
        "order": list(WUXING_ORDER),
        PERSON_A: person_wuxing(entries_a),
        PERSON_B: person_wuxing(entries_b),
        "mapping_version": WESTERN_MAPPING_ID,
    }
```

(`weight_sum` is never 0: the Sun is always a sign-layer factor, weight 1.0.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_synastry_wuxing.py -q`
Expected: all PASS.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check bazi_engine/synastry tests/test_synastry_wuxing.py && uv run mypy bazi_engine --ignore-missing-imports
git add bazi_engine/synastry/wuxing_layer.py tests/test_synastry_wuxing.py
git commit -m "feat(synastry): Wu-Xing translation via sign-element-consensus-v1"
```

---

### Task 6: Engine composition, provenance and warnings

**Files:**
- Create: `bazi_engine/synastry/engine.py`
- Modify: `bazi_engine/synastry/__init__.py`
- Test: `tests/test_synastry_engine.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5; `bazi_engine.__version__`; `wuxing.constants.WESTERN_MAPPING_ID`, `WESTERN_WEIGHTING_ID`.
- Produces:
  - `engine.SynastryPersonInput(chart: Mapping[str, Any], birth_time_known: bool)` (frozen dataclass)
  - `engine.compute_synastry(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> Dict[str, Any]` with top-level keys exactly `aspects, house_overlays, sign_layer, wuxing_pair_factors, provenance`.
  - `provenance` keys exactly: `engine_version, ephemeris_mode, zodiac_mode ("tropical"), house_system_used {"person_a": str|None, "person_b": str|None}, orb_policy_id, weighting_id ("synastry-weights-v1"), base_weighting_id ("body-tier-q0.3-v1"), mapping_version, warnings [{"code", "person", "detail"}]`.
  - Both re-exported from `bazi_engine.synastry`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_synastry_engine.py`:

```python
"""compute_synastry on synthetic charts: determinism, symmetry, time gate (spec acceptance)."""
from __future__ import annotations

import json

import pytest

from bazi_engine import __version__
from bazi_engine.exc import CalculationError
from bazi_engine.synastry import SynastryPersonInput, compute_synastry
from tests.fixtures.synastry_charts import BASE_A, BASE_B, assert_mirrored, make_chart


def _a(**kw: object) -> SynastryPersonInput:
    return SynastryPersonInput(chart=make_chart(BASE_A, asc=15.0, mc=280.0, cusp_start=15.0), **kw)  # type: ignore[arg-type]


def _b(**kw: object) -> SynastryPersonInput:
    return SynastryPersonInput(chart=make_chart(BASE_B, asc=200.0, mc=110.0, cusp_start=200.0), **kw)  # type: ignore[arg-type]


def test_top_level_shape() -> None:
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=True))
    assert set(out) == {"aspects", "house_overlays", "sign_layer", "wuxing_pair_factors", "provenance"}
    assert out["aspects"], "fixture must produce at least one aspect"


def test_deterministic() -> None:
    first = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=True))
    second = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=True))
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


@pytest.mark.parametrize("known_a, known_b", [(True, True), (True, False), (False, True), (False, False)])
def test_swapping_a_and_b_mirrors_the_result(known_a: bool, known_b: bool) -> None:
    ab = compute_synastry(_a(birth_time_known=known_a), _b(birth_time_known=known_b))
    ba = compute_synastry(_b(birth_time_known=known_b), _a(birth_time_known=known_a))
    assert_mirrored(ab, ba)


def test_birth_time_gate_for_b() -> None:
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=False))
    # no overlays in B's houses
    assert all(r["house"] is None and r["status"] == "unavailable_missing_time" for r in out["house_overlays"]["a_in_b"])
    # overlays in A's houses still present
    assert all(isinstance(r["house"], int) and r["status"] == "ok" for r in out["house_overlays"]["b_in_a"])
    # no ascendant / MC of B anywhere
    assert all(r["to_factor"] not in ("Ascendant", "MC") for r in out["aspects"])
    assert "Ascendant" not in [e["factor"] for e in out["sign_layer"]["factors"]["person_b"]]
    assert "Ascendant" not in [f["factor"] for f in out["wuxing_pair_factors"]["person_b"]["factors"]]
    # A keeps its angles
    assert "Ascendant" in [e["factor"] for e in out["sign_layer"]["factors"]["person_a"]]
    assert out["provenance"]["house_system_used"] == {"person_a": "placidus", "person_b": None}
    assert {"code": "birth_time_unknown", "person": "person_b",
            "detail": "Ascendant, MC and houses are not used; the Moon position rests on the supplied clock time."} \
        in out["provenance"]["warnings"]


def test_provenance() -> None:
    out = compute_synastry(_a(birth_time_known=True), _b(birth_time_known=True))
    assert out["provenance"] == {
        "engine_version": __version__,
        "ephemeris_mode": "SWIEPH",
        "zodiac_mode": "tropical",
        "house_system_used": {"person_a": "placidus", "person_b": "placidus"},
        "orb_policy_id": "synastry-orbs-v1",
        "weighting_id": "synastry-weights-v1",
        "base_weighting_id": "body-tier-q0.3-v1",
        "mapping_version": "sign-element-consensus-v1",
        "warnings": [],
    }


def test_house_system_fallback_is_warned_without_coordinates() -> None:
    a = SynastryPersonInput(chart=make_chart(BASE_A, house_system_used="porphyry", fallback=True), birth_time_known=True)
    out = compute_synastry(a, _b(birth_time_known=True))
    assert out["provenance"]["house_system_used"]["person_a"] == "porphyry"
    assert out["provenance"]["warnings"] == [
        {"code": "house_system_fallback", "person": "person_a", "detail": "Placidus undefined; porphyry used."},
    ]


def test_mixed_ephemeris_modes_fail_visibly() -> None:
    a = SynastryPersonInput(chart=make_chart(BASE_A, ephemeris_mode="MOSEPH"), birth_time_known=True)
    with pytest.raises(CalculationError):
        compute_synastry(a, _b(birth_time_known=True))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synastry_engine.py -q`
Expected: collection ERROR, `ImportError: cannot import name 'SynastryPersonInput' from 'bazi_engine.synastry'`.

- [ ] **Step 3: Implement the engine**

Create `bazi_engine/synastry/engine.py`:

```python
"""synastry/engine.py — compose the synastry layers from two western charts.

Pure: takes two ``compute_western_chart`` results, returns plain dicts. No
timestamp is added (D10), so equal inputs give byte-identical responses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from .. import __version__
from ..exc import CalculationError
from ..wuxing.constants import WESTERN_MAPPING_ID, WESTERN_WEIGHTING_ID
from .aspects import cross_aspects
from .factors import extract_factors
from .houses import house_overlays
from .policy import PERSON_A, PERSON_B, SYNASTRY_ORB_POLICY_ID, SYNASTRY_WEIGHTING_ID
from .signs import sign_layer
from .wuxing_layer import wuxing_pair_factors

_TIME_UNKNOWN_DETAIL = (
    "Ascendant, MC and houses are not used; the Moon position rests on the supplied clock time."
)


@dataclass(frozen=True)
class SynastryPersonInput:
    """One person: a ``compute_western_chart`` result and the birth-time gate."""

    chart: Mapping[str, Any]
    birth_time_known: bool


def compute_synastry(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> Dict[str, Any]:
    factors_a = extract_factors(person_a.chart, birth_time_known=person_a.birth_time_known)
    factors_b = extract_factors(person_b.chart, birth_time_known=person_b.birth_time_known)
    signs = sign_layer(factors_a, factors_b)
    return {
        "aspects": cross_aspects(factors_a, factors_b, from_person=PERSON_A, to_person=PERSON_B),
        "house_overlays": {
            "a_in_b": house_overlays(factors_a, person_b.chart, host_time_known=person_b.birth_time_known),
            "b_in_a": house_overlays(factors_b, person_a.chart, host_time_known=person_a.birth_time_known),
        },
        "sign_layer": signs,
        "wuxing_pair_factors": wuxing_pair_factors(signs["factors"][PERSON_A], signs["factors"][PERSON_B]),
        "provenance": _provenance(person_a, person_b),
    }


def _house_system_used(person: SynastryPersonInput) -> Optional[str]:
    if not person.birth_time_known:
        return None
    return str(person.chart["quality_flags"]["house_system_used"])


def _ephemeris_mode(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> str:
    modes = {str(p.chart["quality_flags"]["ephemeris_mode"]) for p in (person_a, person_b)}
    if len(modes) != 1:
        raise CalculationError("The two charts were computed with different ephemeris modes", detail={})
    return modes.pop()


def _warnings(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> List[Dict[str, str]]:
    warnings: List[Dict[str, str]] = []
    for label, person in ((PERSON_A, person_a), (PERSON_B, person_b)):
        if not person.birth_time_known:
            warnings.append({"code": "birth_time_unknown", "person": label, "detail": _TIME_UNKNOWN_DETAIL})
        elif person.chart["quality_flags"]["house_system_fallback"]:
            used = person.chart["quality_flags"]["house_system_used"]
            # The chart's own fallback reason names the latitude — never copied (D9).
            warnings.append({"code": "house_system_fallback", "person": label,
                             "detail": f"Placidus undefined; {used} used."})
    return warnings


def _provenance(person_a: SynastryPersonInput, person_b: SynastryPersonInput) -> Dict[str, Any]:
    return {
        "engine_version": __version__,
        "ephemeris_mode": _ephemeris_mode(person_a, person_b),
        "zodiac_mode": "tropical",
        "house_system_used": {PERSON_A: _house_system_used(person_a), PERSON_B: _house_system_used(person_b)},
        "orb_policy_id": SYNASTRY_ORB_POLICY_ID,
        "weighting_id": SYNASTRY_WEIGHTING_ID,
        "base_weighting_id": WESTERN_WEIGHTING_ID,
        "mapping_version": WESTERN_MAPPING_ID,
        "warnings": _warnings(person_a, person_b),
    }
```

Replace `bazi_engine/synastry/__init__.py` with:

```python
"""bazi_engine/synastry — western pair facts for two charts (G1 + G1b).

Level 4. Pure functions over two ``compute_western_chart`` results: no
ephemeris calls, no BaZi, no routers. No interpretation and no score.
Decisions: docs/superpowers/specs/2026-11-08-synastry-g1-design.md.
"""
from .engine import SynastryPersonInput, compute_synastry
from .factors import extract_factors
from .policy import (
    FACTOR_ORDER,
    SIGN_LAYER_FACTORS,
    SYNASTRY_ASPECTS,
    SYNASTRY_ORB_POLICY_ID,
    SYNASTRY_WEIGHTING_ID,
    factor_weight,
)

__all__ = [
    "FACTOR_ORDER",
    "SIGN_LAYER_FACTORS",
    "SYNASTRY_ASPECTS",
    "SYNASTRY_ORB_POLICY_ID",
    "SYNASTRY_WEIGHTING_ID",
    "SynastryPersonInput",
    "compute_synastry",
    "extract_factors",
    "factor_weight",
]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_synastry_*.py tests/test_import_hierarchy.py -q`
Expected: all PASS.

- [ ] **Step 5: Canary the symmetry check**

Temporarily change `cross_aspects(factors_a, factors_b, …)` in `engine.py` to iterate only `dict(list(factors_a.items())[:-1])`. Run `uv run pytest tests/test_synastry_engine.py -q -k mirrors`; expect FAIL. Revert; expect PASS.

- [ ] **Step 6: Lint, complexity and commit**

```bash
uv run ruff check bazi_engine/synastry tests/test_synastry_engine.py && uv run mypy bazi_engine --ignore-missing-imports
uv run python scripts/check_complexity.py --check
git add bazi_engine/synastry tests/test_synastry_engine.py
git commit -m "feat(synastry): compose layers, provenance and warnings in compute_synastry"
```

---

### Task 7: HTTP endpoint `/v1/relationship/synastry`

**Files:**
- Create: `bazi_engine/routers/relationship.py`
- Modify: `bazi_engine/routers/registry.py` (import list + one `Mount` row after the `match` row)
- Modify: `bazi_engine/openapi_ext.py` (tag list, after the `"Hehun"` entry)
- Create: `tests/fixtures/synastry_payloads.py`, `tests/test_synastry_endpoint.py`
- Regenerate: `tests/golden/route_table.json`, `spec/openapi/openapi.json`

**Interfaces:**
- Consumes: `compute_synastry`, `SynastryPersonInput` (Task 6); `bazi_engine.western.compute_western_chart(birth_utc_dt, lat, lon, ...)`; `bazi_engine.time_utils.resolve_local_iso(date, tz, *, ambiguous, nonexistent) -> (datetime, status)`; `AmbiguousTimeChoice`, `NonexistentTimePolicy`; `bazi_engine.match.privacy.log_consent_decision(request_id: str, consent_confirmed: bool) -> str`; `bazi_engine.limiter.limiter`, `tier_limit`.
- Produces: `routers.relationship.router` (prefix `/relationship`, tag `Relationship`), models `SynastryRequest`, `SynastryPerson`, `SynastryOptions`, `SynastryResponse` (+ nested `Synastry*` models). Fixtures `PAIR_A`, `PAIR_B`, `VALID_SYNASTRY_REQUEST`, `SYNASTRY_PATH = "/v1/relationship/synastry"`.

- [ ] **Step 1: Write the payload fixtures**

Create `tests/fixtures/synastry_payloads.py`:

```python
"""HTTP payloads for /v1/relationship/synastry tests (synthetic people, no real persons)."""
from __future__ import annotations

import copy
from typing import Any, Dict

SYNASTRY_PATH = "/v1/relationship/synastry"

PAIR_A: Dict[str, Any] = {"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52}
PAIR_B: Dict[str, Any] = {"date": "1992-11-03T08:15:00", "tz": "Europe/Vienna", "lon": 16.3738, "lat": 48.2082}

VALID_SYNASTRY_REQUEST: Dict[str, Any] = {
    "person_a": {**PAIR_A, "display_label": "A."},
    "person_b": {**PAIR_B, "display_label": "B."},
    "options": {"second_person_consent_confirmed": True},
}


def request_with(**overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Deep copy of the valid request with per-person/options field overrides."""
    body = copy.deepcopy(VALID_SYNASTRY_REQUEST)
    for key, fields in overrides.items():
        body[key].update(fields)
    return body


def swapped(body: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(body)
    out["person_a"], out["person_b"] = out["person_b"], out["person_a"]
    return out
```

- [ ] **Step 2: Write the failing endpoint tests**

Create `tests/test_synastry_endpoint.py`:

```python
"""POST /v1/relationship/synastry through the assembled app (TestClient boundary)."""
from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app
from tests.fixtures.synastry_charts import assert_mirrored
from tests.fixtures.synastry_payloads import SYNASTRY_PATH, VALID_SYNASTRY_REQUEST, request_with, swapped

client = TestClient(app)


def _post(body: dict) -> dict:
    resp = client.post(SYNASTRY_PATH, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_response_shape() -> None:
    out = _post(VALID_SYNASTRY_REQUEST)
    assert set(out) == {"aspects", "house_overlays", "sign_layer", "wuxing_pair_factors", "provenance", "subjects"}
    assert out["subjects"] == {
        "person_a": {"display_label": "A.", "birth_time_known": True},
        "person_b": {"display_label": "B.", "birth_time_known": True},
    }
    assert out["provenance"]["orb_policy_id"] == "synastry-orbs-v1"
    assert out["provenance"]["ephemeris_mode"] in {"SWIEPH", "MOSEPH"}
    assert len(out["house_overlays"]["a_in_b"]) == 10
    assert len(out["sign_layer"]["pairs"]) == 36


def test_identical_requests_give_byte_identical_bodies() -> None:
    first = client.post(SYNASTRY_PATH, json=VALID_SYNASTRY_REQUEST)
    second = client.post(SYNASTRY_PATH, json=VALID_SYNASTRY_REQUEST)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_swapping_persons_mirrors_the_response() -> None:
    ab = _post(VALID_SYNASTRY_REQUEST)
    ba = _post(swapped(VALID_SYNASTRY_REQUEST))
    assert_mirrored(ab, ba)
    assert ba["subjects"]["person_a"] == ab["subjects"]["person_b"]


def test_birth_time_gate_for_person_b() -> None:
    out = _post(request_with(person_b={"birth_time_known": False}))
    assert all(r["house"] is None and r["status"] == "unavailable_missing_time" for r in out["house_overlays"]["a_in_b"])
    assert all(1 <= r["house"] <= 12 and r["status"] == "ok" for r in out["house_overlays"]["b_in_a"])
    assert all(r["to_factor"] not in ("Ascendant", "MC") for r in out["aspects"])
    assert [e["factor"] for e in out["sign_layer"]["factors"]["person_b"]] == ["Sun", "Moon", "Mercury", "Venus", "Mars"]
    assert out["provenance"]["house_system_used"]["person_b"] is None
    assert any(w["code"] == "birth_time_unknown" and w["person"] == "person_b" for w in out["provenance"]["warnings"])


def test_v1_only_no_legacy_mount() -> None:
    assert client.post("/relationship/synastry", json=VALID_SYNASTRY_REQUEST).status_code == 404


@pytest.mark.parametrize("consent_options", [{}, {"second_person_consent_confirmed": False}])
def test_consent_is_required(consent_options: dict) -> None:
    body = copy.deepcopy(VALID_SYNASTRY_REQUEST)
    body["options"] = consent_options
    resp = client.post(SYNASTRY_PATH, json=body)
    assert resp.status_code == 422
    if consent_options:
        assert resp.json()["error"] == "consent_required"


def test_options_object_is_required() -> None:
    body = copy.deepcopy(VALID_SYNASTRY_REQUEST)
    del body["options"]
    assert client.post(SYNASTRY_PATH, json=body).status_code == 422


@pytest.mark.parametrize("field", ["date", "tz", "lon", "lat"])
def test_birth_fields_are_required(field: str) -> None:
    body = copy.deepcopy(VALID_SYNASTRY_REQUEST)
    del body["person_b"][field]
    assert client.post(SYNASTRY_PATH, json=body).status_code == 422


def test_unknown_person_fields_are_rejected() -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_a={"zodiac_mode": "sidereal_lahiri"}))
    assert resp.status_code == 422


@pytest.mark.parametrize("label, ok", [
    ("Anna", True), ("A.", True), ("Jean-Luc", True), ("Mary Ann", True), ("Zoë", True),
    ("A1", False), ("1990", False), ("anna@example.org", False), ("x" * 41, False), ("", False),
])
def test_display_label_is_first_name_or_initial(label: str, ok: bool) -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_a={"display_label": label}))
    assert (resp.status_code == 200) is ok, resp.text


def test_nonexistent_local_time_is_a_422() -> None:
    resp = client.post(SYNASTRY_PATH, json=request_with(person_b={"date": "2021-03-28T02:30:00", "tz": "Europe/Berlin"}))
    assert resp.status_code == 422


@pytest.mark.swieph
def test_real_ephemeris_is_attested() -> None:
    out = _post(VALID_SYNASTRY_REQUEST)
    assert out["provenance"]["ephemeris_mode"] == "SWIEPH"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_synastry_endpoint.py -q 2>&1 | tail -5`
Expected: FAIL — every test that posts to the path gets `404` (route does not exist); `test_v1_only_no_legacy_mount` passes vacuously. That one is re-proven non-vacuous in Step 6.

- [ ] **Step 4: Implement the router**

Create `bazi_engine/routers/relationship.py`:

```python
"""routers/relationship.py — POST /v1/relationship/synastry (G1 + G1b).

Level 5 HTTP seam over the Level-4 ``bazi_engine.synastry`` package. Mounted at
/v1 ONLY (like Hehun): a new B2B surface never gets a legacy unauthenticated
twin. Both charts come from the existing ``compute_western_chart`` (no own
ephemeris). No score, no interpretation. Consent parity with Hehun (D4).
Birth data and display labels never reach a log line; the only log record on
the success path is the consent hash with the request id.
Decisions: docs/superpowers/specs/2026-11-08-synastry-g1-design.md.
"""
from __future__ import annotations

import logging
from datetime import timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import Request

from ..exc import BaziEngineError
from ..limiter import limiter, tier_limit
from ..match.privacy import log_consent_decision
from ..synastry import SynastryPersonInput, compute_synastry
from ..time_utils import AmbiguousTimeChoice, NonexistentTimePolicy, resolve_local_iso
from ..western import compute_western_chart

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/relationship", tags=["Relationship"])

# Letters with single inner separators; no digits, no "@" (first name or initial only).
_LABEL_PATTERN = r"^[^\W\d_]+(?:[ .'\-][^\W\d_]+)*\.?$"

_CONSENT_DESCRIPTION = (
    "Confirms the second person has agreed to their birth data being used for this "
    "one-off synastry. Required: the request is rejected when this is false or absent. "
    "No data is persisted."
)

PersonLabel = Literal["person_a", "person_b"]
AspectType = Literal["conjunction", "sextile", "square", "trine", "opposition"]
SignRelation = Literal["same_sign", "semi_sextile", "sextile", "square", "trine", "quincunx", "opposition"]
ElementRelation = Literal["same", "complementary", "other"]
OverlayStatus = Literal["ok", "unavailable_missing_time"]
WestElement = Literal["Feuer", "Erde", "Luft", "Wasser"]


# ── Request ──────────────────────────────────────────────────────────────────
class SynastryPerson(BaseModel):
    """One person — the /calculate/western birth fields, but date/tz/lon/lat are required (D5)."""

    model_config = ConfigDict(extra="forbid")

    date: str = Field(..., description="Local ISO8601 datetime")
    tz: str = Field(..., description="IANA timezone name")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude in degrees")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in degrees")
    ambiguousTime: AmbiguousTimeChoice = Field("earlier")
    nonexistentTime: NonexistentTimePolicy = Field("error")
    birth_time_known: bool = Field(
        True, description="False if the birth time is unknown: no ascendant, MC or houses for this person.",
    )
    display_label: Optional[str] = Field(
        None, min_length=1, max_length=40, pattern=_LABEL_PATTERN,
        description="Optional first name or initial, echoed in `subjects`. Never logged.",
    )


class SynastryOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    second_person_consent_confirmed: bool = Field(..., description=_CONSENT_DESCRIPTION)


class SynastryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {
        "person_a": {"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52,
                     "display_label": "A."},
        "person_b": {"date": "1992-11-03T08:15:00", "tz": "Europe/Vienna", "lon": 16.3738, "lat": 48.2082,
                     "display_label": "B."},
        "options": {"second_person_consent_confirmed": True},
    }})

    person_a: SynastryPerson
    person_b: SynastryPerson
    options: SynastryOptions


# ── Response ─────────────────────────────────────────────────────────────────
class SynastryAspect(BaseModel):
    from_person: PersonLabel
    from_factor: str
    to_person: PersonLabel
    to_factor: str
    type: AspectType
    exact_angle: float
    orb: float = Field(..., description="Deviation from the exact angle in degrees (4 dp)")
    exact: bool = Field(..., description="True when the orb is at most half the orb limit")
    from_weight: float
    to_weight: float
    weight: float = Field(..., description="from_weight × to_weight (tier weights, synastry-weights-v1)")


class SynastryHouseOverlay(BaseModel):
    factor: str
    house: Optional[int] = Field(None, ge=1, le=12)
    status: OverlayStatus


class SynastryHouseOverlays(BaseModel):
    a_in_b: List[SynastryHouseOverlay]
    b_in_a: List[SynastryHouseOverlay]


class SynastrySignFactor(BaseModel):
    factor: str
    sign: str
    sign_index: int = Field(..., ge=0, le=11)
    west_element: WestElement
    degree: float


class SynastrySignFactors(BaseModel):
    person_a: List[SynastrySignFactor]
    person_b: List[SynastrySignFactor]


class SynastrySignPair(BaseModel):
    factor_a: str
    factor_b: str
    sign_relation: SignRelation
    element_relation: ElementRelation


class SynastrySignLayer(BaseModel):
    factors: SynastrySignFactors
    pairs: List[SynastrySignPair]


class SynastryWuXingFactor(BaseModel):
    factor: str
    west_element: WestElement
    weight: float
    vector: List[float] = Field(..., min_length=5, max_length=5)


class SynastryWuXingPerson(BaseModel):
    factors: List[SynastryWuXingFactor]
    vector: List[float] = Field(..., min_length=5, max_length=5, description="Tier-weighted mean, sums to 1")


class SynastryWuXingPairFactors(BaseModel):
    order: List[str]
    person_a: SynastryWuXingPerson
    person_b: SynastryWuXingPerson
    mapping_version: str


class SynastryWarning(BaseModel):
    code: Literal["birth_time_unknown", "house_system_fallback"]
    person: PersonLabel
    detail: str


class SynastryHouseSystems(BaseModel):
    person_a: Optional[str] = None
    person_b: Optional[str] = None


class SynastryProvenance(BaseModel):
    engine_version: str
    ephemeris_mode: str
    zodiac_mode: Literal["tropical"]
    house_system_used: SynastryHouseSystems
    orb_policy_id: str
    weighting_id: str
    base_weighting_id: str
    mapping_version: str
    warnings: List[SynastryWarning]


class SynastrySubject(BaseModel):
    display_label: Optional[str] = None
    birth_time_known: bool


class SynastrySubjects(BaseModel):
    person_a: SynastrySubject
    person_b: SynastrySubject


class SynastryResponse(BaseModel):
    aspects: List[SynastryAspect]
    house_overlays: SynastryHouseOverlays
    sign_layer: SynastrySignLayer
    wuxing_pair_factors: SynastryWuXingPairFactors
    provenance: SynastryProvenance
    subjects: SynastrySubjects


# ── Handler ──────────────────────────────────────────────────────────────────
def _person_input(person: SynastryPerson) -> SynastryPersonInput:
    dt_local, _ = resolve_local_iso(
        person.date, person.tz, ambiguous=person.ambiguousTime, nonexistent=person.nonexistentTime,
    )
    chart = compute_western_chart(dt_local.astimezone(timezone.utc), person.lat, person.lon)
    return SynastryPersonInput(chart=chart, birth_time_known=person.birth_time_known)


def _subject(person: SynastryPerson) -> Dict[str, Any]:
    return {"display_label": person.display_label, "birth_time_known": person.birth_time_known}


@router.post("/synastry", response_model=SynastryResponse)
@limiter.limit(tier_limit)
def synastry_endpoint(request: Request, req: SynastryRequest) -> Dict[str, Any]:
    """Western synastry facts for two people: cross aspects (synastry-orbs-v1), house overlays, sign layer and its Wu-Xing translation (sign-element-consensus-v1). Deterministic; no interpretation and no compatibility rating of any kind. Second-person consent is required; birth data is never logged or persisted."""
    request_id = getattr(request.state, "request_id", "unknown")
    log_consent_decision(request_id, req.options.second_person_consent_confirmed)
    if not req.options.second_person_consent_confirmed:
        raise HTTPException(status_code=422, detail={
            "error": "consent_required",
            "message": "Second-person consent is required for this synastry and must be confirmed (true).",
            "detail": {"code": "consent_required", "field": "options.second_person_consent_confirmed"},
        })
    try:
        result = compute_synastry(_person_input(req.person_a), _person_input(req.person_b))
    except BaziEngineError:
        raise
    except Exception:
        _log.exception("synastry calculation failed request_id=%s", request_id)
        raise HTTPException(status_code=500, detail={
            "error": "calculation_error", "message": "Internal calculation error", "detail": {},
        })
    result["subjects"] = {"person_a": _subject(req.person_a), "person_b": _subject(req.person_b)}
    return result
```

- [ ] **Step 5: Mount it and declare the tag**

In `bazi_engine/routers/registry.py`, add `relationship,` to the `from . import (...)` list (alphabetical, between `personalize,` and `superglue,`), and directly after the `Mount(match.router, legacy_prefix=None),` row add:

```python
    # Western synastry (G1 + G1b, docs/relationship/01_synastry.md). /v1 ONLY,
    # like the match router: a new B2B pair surface never gets a legacy
    # unauthenticated twin. Protected by the default API key.
    Mount(relationship.router, legacy_prefix=None),
```

In `bazi_engine/openapi_ext.py`, directly after the `{"name": "Hehun", ...},` entry, add:

```python
        {"name": "Relationship", "description": "Western synastry for two people: cross aspects (orb policy synastry-orbs-v1), house overlays gated on the house owner's birth time, the sign layer and its Wu-Xing translation via the consensus matrix sign-element-consensus-v1. Deterministic raw facts — no interpretation and no compatibility rating of any kind; second-person consent is required and birth data is never logged or persisted."},
```

- [ ] **Step 6: Run the endpoint tests to verify they pass**

Run: `uv run pytest tests/test_synastry_endpoint.py -q`
Expected: all PASS (the `swieph` test runs or skips depending on whether SE1 files sit in `~/.cache/bazi_engine/swisseph`).
Run: `SE_EPHE_PATH=/tmp/ephe uv run pytest tests/test_synastry_endpoint.py -q`
Expected: all PASS including `test_real_ephemeris_is_attested`.

Non-vacuity of the legacy check: temporarily change the row to `Mount(relationship.router)` and run `uv run pytest tests/test_synastry_endpoint.py -q -k legacy` → expect FAIL (200 ≠ 404). Revert, expect PASS.

If `test_display_label_is_first_name_or_initial` fails for `Zoë` or `Mary Ann`, the Rust regex engine rejected the pattern semantics — fix the pattern, never drop the case.

- [ ] **Step 7: Regenerate the contract artefacts and run the composition gates**

```bash
uv run python tests/golden/regen_route_table.py
uv run python scripts/export_openapi.py
git diff --stat tests/golden/route_table.json spec/openapi/openapi.json
```
Expected: the route golden gains exactly one row `["/v1/relationship/synastry", ["POST"], true, true]`; `git diff tests/golden/route_table.json` shows no other change. The OpenAPI diff adds the path, the `Relationship` tag and the `Synastry*` schemas only:
```bash
git diff spec/openapi/openapi.json | grep '^-' | grep -v '^---' | wc -l
```
Expected: a small number of removed lines (only list-closing commas/brackets around the insertion points). Inspect every removed line; any removed property or path is a defect.

```bash
uv run pytest tests/test_app_composition.py tests/test_rate_limit_coverage.py tests/test_openapi_*.py tests/test_import_hierarchy.py -q
uv run python scripts/export_openapi.py --check
```
Expected: all PASS, `--check` exits 0.

Codegen survival (the CI codegen job): `npm ci` once, then
```bash
npx --no-install redocly lint spec/openapi/openapi.json --skip-rule security-defined --skip-rule no-path-trailing-slash
```
Expected: exit 0, no new errors. If Docker is available, also run the TS generation + `tsc` exactly as in `.github/workflows/ci.yml` lines 291–313; otherwise record "TS codegen not run locally" in the Task 9 summary.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check bazi_engine/ tests/ scripts/ && uv run mypy bazi_engine --ignore-missing-imports
uv run python scripts/check_complexity.py --check
git add bazi_engine/routers/relationship.py bazi_engine/routers/registry.py bazi_engine/openapi_ext.py \
        tests/fixtures/synastry_payloads.py tests/test_synastry_endpoint.py \
        tests/golden/route_table.json spec/openapi/openapi.json
git commit -m "feat(api): POST /v1/relationship/synastry (G1 + G1b), /v1-only, consent-gated"
```

---

### Task 8: Contract tests — no score field, no birth data in logs

**Files:**
- Create: `tests/test_synastry_contract.py`

**Interfaces:**
- Consumes: the assembled `app`, `SYNASTRY_PATH`, `VALID_SYNASTRY_REQUEST`, `request_with` (Task 7); `tests.fixtures.match_payloads.SENTINEL_A`, `SENTINEL_B` (distinctive birth data, already used by the Hehun privacy tests).
- Produces: nothing for later tasks (pure test increment — must pass with **zero** production change; a failure is a defect to report, not a test to bend).

- [ ] **Step 1: Write the tests**

Create `tests/test_synastry_contract.py`:

```python
"""Synastry contract: no score-like field (schema + live body) and no birth data in logs."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterator, Set

from fastapi.testclient import TestClient

from bazi_engine.app import app
from tests.fixtures.match_payloads import SENTINEL_A, SENTINEL_B
from tests.fixtures.synastry_payloads import SYNASTRY_PATH, VALID_SYNASTRY_REQUEST, request_with

client = TestClient(app)

_BANNED_KEY = re.compile(r"score|compat|percent|rating|points|ranking", re.IGNORECASE)
_LABEL_A, _LABEL_B = "Zephyrine", "Quillon"
_NONEXISTENT = {"date": "2021-03-28T02:31:00", "tz": "Europe/Berlin"}
_TOKENS = (
    SENTINEL_A["date"], SENTINEL_A["tz"], str(SENTINEL_A["lon"]), str(SENTINEL_A["lat"]),
    SENTINEL_B["date"], SENTINEL_B["tz"], str(SENTINEL_B["lon"]), str(SENTINEL_B["lat"]),
    "07:31", "22:04", _NONEXISTENT["date"], _LABEL_A, _LABEL_B,
)


def _refs(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value.rsplit("/", 1)[-1]
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for value in node:
            yield from _refs(value)


def _reachable_components(openapi: Dict[str, Any]) -> Dict[str, Any]:
    components = openapi["components"]["schemas"]
    todo = list(_refs(openapi["paths"][SYNASTRY_PATH]["post"]))
    seen: Set[str] = set()
    while todo:
        name = todo.pop()
        if name not in seen:
            seen.add(name)
            todo.extend(_refs(components[name]))
    return {name: components[name] for name in seen}


def _property_names(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                yield from value.keys()
            yield from _property_names(value)
    elif isinstance(node, list):
        for value in node:
            yield from _property_names(value)


def _keys(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _keys(value)


def test_schema_graph_has_no_score_like_property() -> None:
    reachable = _reachable_components(app.openapi())
    assert {"SynastryRequest", "SynastryResponse", "SynastryAspect"} <= set(reachable)  # non-vacuous
    names = {n for schema in reachable.values() for n in _property_names(schema)}
    assert "weight" in names and "aspects" in names
    assert sorted(n for n in names if _BANNED_KEY.search(n)) == []


def test_live_response_has_no_score_like_key_and_no_percent_value() -> None:
    resp = client.post(SYNASTRY_PATH, json=VALID_SYNASTRY_REQUEST)
    assert resp.status_code == 200
    assert sorted(k for k in _keys(resp.json()) if _BANNED_KEY.search(k)) == []
    assert "%" not in resp.text


def _sentinel_request(**extra: Dict[str, Any]) -> Dict[str, Any]:
    body = request_with(
        person_a={**SENTINEL_A, "display_label": _LABEL_A},
        person_b={**SENTINEL_B, "display_label": _LABEL_B},
    )
    for key, fields in extra.items():
        body[key].update(fields)
    return body


def _log_blob(records: list) -> str:
    return "\n".join(f"{r.name} {r.getMessage()} {r.exc_text or ''}" for r in records)


def test_no_birth_data_or_labels_in_logs(caplog: Any) -> None:
    with caplog.at_level(logging.DEBUG):
        ok = client.post(SYNASTRY_PATH, json=_sentinel_request())
        gap = client.post(SYNASTRY_PATH, json=_sentinel_request(person_b=_NONEXISTENT))
        no_consent = client.post(SYNASTRY_PATH, json=_sentinel_request(options={"second_person_consent_confirmed": False}))
        bad_label = client.post(SYNASTRY_PATH, json=_sentinel_request(person_a={"display_label": _LABEL_A + "1"}))
    assert [ok.status_code, gap.status_code, no_consent.status_code, bad_label.status_code] == [200, 422, 422, 422]
    assert any(r.name == "bazi_engine.match.privacy" for r in caplog.records)  # non-vacuous: consent hash logged
    blob = _log_blob(caplog.records)
    assert [t for t in _TOKENS if t in blob] == []


def test_error_bodies_do_not_echo_birth_data_or_labels() -> None:
    for body in (
        _sentinel_request(person_b=_NONEXISTENT),
        _sentinel_request(options={"second_person_consent_confirmed": False}),
        _sentinel_request(person_a={"display_label": _LABEL_A + "1"}),
        _sentinel_request(person_a={"zodiac_mode": "sidereal_lahiri"}),
    ):
        resp = client.post(SYNASTRY_PATH, json=body)
        assert resp.status_code == 422
        assert [t for t in _TOKENS if t in resp.text] == [], resp.text
```

- [ ] **Step 2: Run the tests**

Run: `uv run pytest tests/test_synastry_contract.py -q`
Expected: all PASS with zero production change. If a privacy test fails, the failing token names the leak: trace which logger emitted it (`r.name` in the blob) and fix the emitter (router, error handler or `time_utils`) — never shrink `_TOKENS`.

- [ ] **Step 3: Canary both gates**

1. Add `score: Optional[float] = None` to `SynastryResponse` → `uv run pytest tests/test_synastry_contract.py -q -k schema` → expect FAIL listing `score`. Revert.
2. Add `_log.info("synastry person_a=%s", req.person_a.date)` as the first line of `synastry_endpoint` → `uv run pytest tests/test_synastry_contract.py -q -k logs` → expect FAIL listing `1988-06-04T07:31:00`. Revert.
3. `git diff --stat bazi_engine/` → expect empty.

- [ ] **Step 4: Commit**

```bash
uv run ruff check tests/test_synastry_contract.py
git add tests/test_synastry_contract.py
git commit -m "test(synastry): score-absence and log-privacy contract tests"
```

---

### Task 9: Documentation, example response, task row, full gate run

**Files:**
- Create: `scripts/gen_synastry_example.py`, `tests/test_synastry_example.py`
- Create: `docs/relationship/01_synastry.md`, `docs/relationship/examples/synastry_example_request.json`, `docs/relationship/examples/synastry_example_response.json` (the two JSON files are generated)
- Modify: `3-code/tasks.md` (new section at the end)

**Interfaces:**
- Consumes: the live endpoint (Task 7); `SE_EPHE_PATH=/tmp/ephe`.
- Produces: the documented example pair; `scripts/gen_synastry_example.py [--check]` (exit 0 = up to date / written, 1 = stale, 2 = no SWIEPH).

- [ ] **Step 1: Write the example generator**

Create `scripts/gen_synastry_example.py`:

```python
"""Write or check the documented synastry example (docs/relationship/examples/).

The example is produced by the live app on the real Swiss Ephemeris, never by
hand. Regenerate after any change to the synastry output or the engine build
label:

    SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py
    SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py --check   # exit 1 when stale
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "docs" / "relationship" / "examples"
REQUEST_FILE = EXAMPLES / "synastry_example_request.json"
RESPONSE_FILE = EXAMPLES / "synastry_example_response.json"

# Synthetic test pair (no real persons).
REQUEST: Dict[str, Any] = {
    "person_a": {"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52,
                 "display_label": "A."},
    "person_b": {"date": "1992-11-03T08:15:00", "tz": "Europe/Vienna", "lon": 16.3738, "lat": 48.2082,
                 "display_label": "B."},
    "options": {"second_person_consent_confirmed": True},
}


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def build_response() -> str:
    from fastapi.testclient import TestClient

    from bazi_engine.app import app

    resp = TestClient(app).post("/v1/relationship/synastry", json=REQUEST)
    if resp.status_code != 200:
        raise SystemExit(f"synastry request failed: {resp.status_code} {resp.text}")
    return _dump(resp.json())


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 when the files are stale")
    args = parser.parse_args(argv)
    if not os.environ.get("SE_EPHE_PATH") or os.environ.get("EPHEMERIS_MODE", "SWIEPH").upper() != "SWIEPH":
        print("needs SE_EPHE_PATH and SWIEPH (the example documents the real ephemeris)", file=sys.stderr)
        return 2
    request_text, response_text = _dump(REQUEST), build_response()
    if args.check:
        stale = [p.name for p, text in ((REQUEST_FILE, request_text), (RESPONSE_FILE, response_text))
                 if not p.exists() or p.read_text(encoding="utf-8") != text]
        if stale:
            print(f"stale: {', '.join(stale)} — regenerate", file=sys.stderr)
            return 1
        return 0
    EXAMPLES.mkdir(parents=True, exist_ok=True)
    REQUEST_FILE.write_text(request_text, encoding="utf-8")
    RESPONSE_FILE.write_text(response_text, encoding="utf-8")
    print(f"wrote {REQUEST_FILE.relative_to(ROOT)} and {RESPONSE_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write the example test**

Create `tests/test_synastry_example.py`:

```python
"""The documented synastry example equals the live output (SWIEPH)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

pytestmark = pytest.mark.swieph

EXAMPLES = Path(__file__).resolve().parents[1] / "docs" / "relationship" / "examples"


def test_docs_example_matches_the_live_response() -> None:
    request = json.loads((EXAMPLES / "synastry_example_request.json").read_text(encoding="utf-8"))
    expected = json.loads((EXAMPLES / "synastry_example_response.json").read_text(encoding="utf-8"))
    resp = TestClient(app).post("/v1/relationship/synastry", json=request)
    assert resp.status_code == 200
    assert resp.json() == expected, "regenerate: SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py"
```

Run: `SE_EPHE_PATH=/tmp/ephe uv run pytest tests/test_synastry_example.py -q`
Expected: FAIL with `FileNotFoundError` (examples not generated yet).

- [ ] **Step 3: Generate the example and verify**

```bash
SE_EPHE_PATH=/tmp/ephe uv run python scripts/gen_synastry_example.py
SE_EPHE_PATH=/tmp/ephe uv run python scripts/gen_synastry_example.py --check; echo "rc=$?"
SE_EPHE_PATH=/tmp/ephe uv run pytest tests/test_synastry_example.py -q
```
Expected: files written; `rc=0`; test PASS. Open `docs/relationship/examples/synastry_example_response.json` with the Read tool and check by eye: `provenance.ephemeris_mode == "SWIEPH"`, `house_system_used` both `"placidus"`, warnings `[]`, at least one aspect, 10 + 10 overlay rows, 36 sign pairs, both person vectors with 5 values.

- [ ] **Step 4: Write the documentation**

Create `docs/relationship/01_synastry.md`:

````markdown
# Synastry — `POST /v1/relationship/synastry` (G1 + G1b)

Deterministic western pair facts for two people: aspects between the two charts, house
overlays, axis contacts (ascendant/MC), the sign layer and its translation into the five
Wu-Xing phases. **No interpretation and no compatibility rating of any kind** — no field
called or containing `score`, `compatibility`, `percent`, `rating` or `points` exists
(contract test `tests/test_synastry_contract.py`).

Spec and decisions: `docs/superpowers/specs/2026-11-08-synastry-g1-design.md` (D1–D11).
Code: `bazi_engine/synastry/` (Level 4, pure) and `bazi_engine/routers/relationship.py`.

## Surface

- `/v1` only, API key required, rate limited by key tier. No legacy path exists.
- Both charts come from the existing `compute_western_chart` (Swiss Ephemeris, tropical,
  Placidus with the existing Porphyry → Whole-Sign fallback). Times are converted to UTC
  exactly like `/calculate/western`; the BaZi time standard (TLST) does not apply.

## Request

| Field | Type | Notes |
|-------|------|-------|
| `person_a`, `person_b` | object, required | `date` (local ISO 8601), `tz` (IANA), `lon`, `lat` — all **required**, no Berlin default; `ambiguousTime` (`earlier`/`later`), `nonexistentTime` (`error`/`shift_forward`), `birth_time_known` (default `true`), optional `display_label` |
| `display_label` | string, optional | first name or initial, max 40 characters, letters with single inner `space . ' -`; no digits, no `@`. Echoed in `subjects`, never logged |
| `options.second_person_consent_confirmed` | bool, required | absent → 422 `validation_error`; `false` → 422 `consent_required`. The decision is logged as a hash with the request id only |

Unknown keys anywhere (e.g. `zodiac_mode`) are rejected with 422.

## Calculation

**Factors.** Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto; plus
Ascendant and MC only when that person's birth time is known.

**Weights** (`synastry-weights-v1` = Fusion tiers `body-tier-q0.3-v1`, MC tier 1):

| Tier | Weight | Factors |
|------|--------|---------|
| 1 | 1.0 | Sun, Moon, Ascendant, MC |
| 2 | 0.3 | Mercury, Venus, Mars |
| 3 | 0.09 | Jupiter, Saturn |
| 4 | 0.027 | Uranus, Neptune, Pluto |

Each aspect carries `from_weight`, `to_weight` and `weight = from_weight × to_weight`.

**Aspects** (`synastry-orbs-v1`, Astro-Noctum orbs, same for ASC/MC partners):

| Aspect | Angle | Orb limit |
|--------|-------|-----------|
| conjunction | 0° | 8° |
| sextile | 60° | 4° |
| square | 90° | 6° |
| trine | 120° | 6° |
| opposition | 180° | 8° |

Full cross matrix person_a → person_b (every A factor against every B factor), at most one
aspect per pair (the windows do not overlap). The limit is inclusive. `orb` = deviation from
the exact angle (4 dp); `exact` = orb ≤ half the limit. Order: A factor, then B factor, in
the factor order above.

**House overlays.** The ten planets of A in B's houses (`a_in_b`) and of B in A's houses
(`b_in_a`); a cusp belongs to the house it opens. Gate: when the **house owner's** birth time
is unknown, every row is `{"house": null, "status": "unavailable_missing_time"}`.

**Sign layer (G1b).** Sun, Moon, Mercury, Venus, Mars and (time known) Ascendant per person:
German sign name, `sign_index` (0 = Widder), western element (`Feuer/Erde/Luft/Wasser`),
degree in sign. `pairs` = every A factor × every B factor with
`sign_relation` by sign distance — `same_sign` (0), `semi_sextile` (1), `sextile` (2),
`square` (3), `trine` (4), `quincunx` (5), `opposition` (6) — and `element_relation`:
`same`, `complementary` (Feuer–Luft, Erde–Wasser) or `other`.

**Wu-Xing translation.** Each sign-layer factor's element is spread over
`["Holz", "Feuer", "Erde", "Metall", "Wasser"]` by the consensus matrix
`sign-element-consensus-v1` — the same matrix as the Fusion vector
(`docs/fusion/12_west_element_mapping.md`). Per person: one vector per factor (sums to 1)
and a person vector = tier-weighted mean of the factor vectors (sums to 1). No comparison
number between the persons.

## Response

`aspects[]`, `house_overlays {a_in_b[], b_in_a[]}`, `sign_layer {factors {person_a[], person_b[]}, pairs[]}`,
`wuxing_pair_factors {order, person_a, person_b, mapping_version}`, `provenance`, `subjects`.

`provenance`: `engine_version`, `ephemeris_mode`, `zodiac_mode` (`tropical`),
`house_system_used` per person (`null` without birth time), `orb_policy_id`,
`weighting_id`, `base_weighting_id`, `mapping_version`, `warnings[]`
(`birth_time_unknown` — the Moon then rests on the supplied clock time;
`house_system_fallback`). No timestamp: identical requests return byte-identical bodies.

## Example

Request `examples/synastry_example_request.json`, response
`examples/synastry_example_response.json` (synthetic pair, real Swiss Ephemeris).
Both are generated, never hand-edited:

```bash
SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py          # write
SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py --check  # exit 1 when stale
```

`tests/test_synastry_example.py` (swieph) fails when the example drifts from the live
output — regenerate after any synastry change or engine build-label bump.

## Privacy

No birth field and no `display_label` reaches a log line; error bodies do not echo them
(`tests/test_synastry_contract.py`). Nothing is persisted.

## Not in scope

Composite charts, relationship transits, minor aspects, Chiron, lunar nodes, interpretation
text, cross resonance (G3), BaZi branch combinations (G2).
````

- [ ] **Step 5: Add the task row**

Append to the end of `3-code/tasks.md`:

```markdown

## Relationship — G-track

| ID | Task | Priority | Status | Req | Dependencies | Updated | Notes |
|----|------|----------|--------|-----|--------------|---------|-------|
| REL-G1-001 | Western synastry endpoint `POST /v1/relationship/synastry` (G1 + G1b): cross aspects `synastry-orbs-v1`, house overlays with missing-time gate, sign layer, Wu-Xing via `sign-element-consensus-v1`; no score | P1 | In Review | REQ-REL-G1 | FBP-WX-002 | 2026-11-08 | Branch `feat/synastry-g1` (local, not pushed). Spec + decisions D1–D11: `docs/superpowers/specs/2026-11-08-synastry-g1-design.md`; doc `docs/relationship/01_synastry.md`. |
```

- [ ] **Step 6: Full gate run (CI-equivalent, local)**

```bash
cd /Users/benjaminpoersch/FUFIRE/FUFIRE_API_lunar-wt-synastry
SE_EPHE_PATH=/tmp/ephe uv run pytest -q 2>&1 | tail -3
uv run ruff check bazi_engine/ tests/ scripts/ --output-format=github
uv run mypy bazi_engine --ignore-missing-imports
uv run python scripts/check_complexity.py --check
uv run python scripts/export_openapi.py --check
uv run python scripts/gen_tlst_reference_corpus.py --check
uv run python scripts/assert_toolchain_versions.py
SE_EPHE_PATH=/tmp/ephe uv run python scripts/gen_synastry_example.py --check; echo "rc=$?"
SE_EPHE_PATH=/tmp/ephe uv run pytest -q --cov=bazi_engine --cov-fail-under=75 2>&1 | tail -3
```
Expected: pytest green (passed count = Task 1 baseline + the new synastry tests, no new failures, skip count unchanged — with `SE_EPHE_PATH` set no swieph test may skip). Note: this Mac also has SE1 files in `~/.cache/bazi_engine/swisseph`, so a run without `SE_EPHE_PATH` is *not* a MOSEPH run; do not report it as one. ruff, mypy, complexity, all `--check`s and the toolchain assert exit 0; `rc=0`; coverage ≥ 75 %.
Report every command's actual tail output verbatim in the completion summary. If any differs from the expectation, report the actual value and stop.

- [ ] **Step 7: Verify the whole change set**

```bash
git diff --stat origin/master..HEAD
git status --short
```
Expected: only the files listed in this plan's File Structure table; `git status` clean after the commit below. Grep for leftovers:
```bash
rg -n "TODO|TBD|FIXME" bazi_engine/synastry bazi_engine/routers/relationship.py docs/relationship
```
Expected: no output.

- [ ] **Step 8: Commit (local only — no push, no PR)**

```bash
git add scripts/gen_synastry_example.py tests/test_synastry_example.py docs/relationship 3-code/tasks.md
git commit -m "docs(synastry): endpoint doc, generated example pair and task row REL-G1-001"
git log --oneline origin/master..HEAD
```
Stop here. Push, PR and deploy need Ben's explicit approval.

---

## Spec coverage (self-review)

| Spec item | Task |
|-----------|------|
| `/v1`-only mount like Hehun | 7 (Mount row, legacy-404 test + canary) |
| Request fields = /calculate/western + `display_label`, never logged | 7 (models), 8 (log + error-body scans) |
| §1 charts via existing western function, no own ephemeris | 7 (`_person_input` → `compute_western_chart`) |
| §2 factors, tier weights, `weight`, ASC/MC only with known time | 1, 2 (D1/D2) |
| §3 full cross matrix, five majors, orbs, one aspect per pair, `exact` | 1 (non-overlap), 2 |
| §4 overlays both directions, missing-time gate | 3, 6, 7 |
| §5 sign layer, seven distance classes, element relation | 4 |
| §6 Wu-Xing via consensus matrix, version, no comparison number | 5 |
| Response fields + provenance list | 6, 7 |
| No score field (contract test) | 8 |
| Acceptance: determinism | 6 (engine), 7 (byte-identical HTTP) |
| Acceptance: symmetry | 6, 7 (`assert_mirrored`) |
| Acceptance: orb limits at / just beyond, per aspect type | 2 |
| Acceptance: birth-time gate for B | 6, 7 |
| Acceptance: all seven sign distance classes | 4 |
| Acceptance: vector per factor sums to 1, mapping_version = Fusion | 5 |
| Acceptance: privacy in logs | 8 |
| Acceptance: existing suite green (SWIEPH) | 1 Step 0 baseline, 9 Step 6 |
| DoD: OpenAPI updated, doc, example response | 7 Step 7, 9 |
| DoD: no push/deploy without Ben | Global Constraints, 9 Step 8 |
| Consent parity (D4) | 7, 8 |
