"""
test_personalize_endpoint.py — Acceptance spec for REQ-002 POST /personalize
(+ /v1/personalize) and REQ-003 domain_extras.

These are BLACK-BOX acceptance tests for an endpoint that does NOT exist yet, so
the whole module is RED until the coder lands routers/personalize.py and mounts
it in app.py. Failure now is expected and correct (it drives the build, exactly
like test_geocode_endpoint.py did for REQ-001).

Contract: docs/plans/2026-06-18-req-002-personalize.md (Option A — 4 flat
prompt-vars + provenance + issues + caveats + domain_extras).
Parity semantics (EV-002-Parität): the old TS consumer interpreter
  Sizhu_middleware/server/services/fufireResponseInterpreter.ts
  + its tests fufire.responseInterpreter.test.ts
  + the captured samples docs/contracts/fufire-samples/{bazi,wuxing}.response.json.

──────────────────────────────────────────────────────────────────────────────
THE MOCK SEAM (read this — it is the contract for the coder, T3)
──────────────────────────────────────────────────────────────────────────────
The endpoint aggregates INTERNAL compute (NOT HTTP self-calls): geocode (REQ-001)
+ bazi + wuxing + bazi/trace + chronometry. The parity mapping operates on the
ASSEMBLED engine RESPONSE shapes — `bazi.pillars.year.tier`,
`bazi.chinese.year.animal`, `bazi.transition.solar_year`,
`bazi.derivation_trace.day.day_anchor_evidence.anchor_verification`,
`wuxing.dominant_element` — i.e. exactly the shape captured in the TS samples.
Those flat dict shapes are produced by the router-level builders, NOT by the
low-level engine primitives (`compute_bazi` returns a `BaziResult` of indices;
`format_pillar`/`_compute_bazi_response` build the dict; the wuxing dict is
assembled inline in `calculate_wuxing_endpoint`). So patching `compute_bazi`
would force every test to re-implement the engine's dict assembly and couple to
the coder's private wiring.

Cleanest seam, chosen deliberately: patch the personalize router's OWN
aggregation boundary by name. The coder MUST route the aggregation through these
four module-level callables in `bazi_engine.routers.personalize` (this naming IS
the T2↔T3 contract — adjust here only by agreement with the coder):

    _compute_bazi_for(req)       -> dict   # the bazi response shape (pillars/chinese/transition/derivation_trace)
    _compute_wuxing_for(req)     -> dict   # the wuxing response shape (must carry "dominant_element")
    _compute_chronometry_for(req)-> dict   # the chronometry frame shape (domain_extras.chronometry)
    _resolve_location(req)       -> dict   # {"lat","lon","tz"} — wraps services.geocoding.geocode_candidates (REQ-001 conf rule)

Each test patches the subset it needs and feeds controlled, captured-sample-shaped
payloads, so the mapping/provenance/issues/caveats logic is exercised
deterministically with NO engine math and NO network. The mount-reality anchor and
the RUN_LIVE smoke deliberately use NO mocks (they exercise the assembled path).

Why this is honest (Kritische semantische Glättung — BOUNDARY feature):
  These:      "the endpoint exists, returns 200, the 4 vars are populated."
  Gegenthese: the router is built but never include_router'd into `app` (mocked
              tests stay green against a hand-built harness while the real app
              404s); OR a missing source is silently DEFAULTED instead of
              null+flagged (green because a value is always present, but the
              customer gets invented BaZi meaning); OR domain_extras are
              present-but-empty (REQ-003 "migration" looks done, real data absent).
  Schärfung:  (1) mount-reality anchor via TestClient(app) — 422 not unmapped-404
              on BOTH routes; (2) missing-source → null + PROMPT_VARIABLE_SOURCE_MISSING,
              never a guess; (3) domain_extras asserted POPULATED from mocked compute;
              (4) RUN_LIVE EV-004 smoke through the assembled endpoint, no mocks.

Evidence class: hermetic (mocked compute) for the default suite + ONE RUN_LIVE
live smoke (skipped by default) that touches real internal compute end-to-end.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bazi_engine.app import app

client = TestClient(app)

# The aggregation boundary the coder must expose (see module docstring).
PERSONALIZE_MODULE = "bazi_engine.routers.personalize"
SEAM_BAZI = f"{PERSONALIZE_MODULE}._compute_bazi_for"
SEAM_WUXING = f"{PERSONALIZE_MODULE}._compute_wuxing_for"
SEAM_CHRONO = f"{PERSONALIZE_MODULE}._compute_chronometry_for"
SEAM_LOCATION = f"{PERSONALIZE_MODULE}._resolve_location"

# The literal token the parity contract greps for (must byte-match the TS const).
PROMPT_VARIABLE_SOURCE_MISSING = "PROMPT_VARIABLE_SOURCE_MISSING"


# ── Captured TS parity samples (single source of truth shared with the TS suite) ─
# These are the EXACT files the TS interpreter test reads. Loading them here (not
# re-typing fixtures) is what makes this a true parity port: same input → same
# 4 vars, same issues, same caveat. If the sibling repo is not checked out, the
# parity tests SKIP (they cannot prove parity without the authoritative samples)
# rather than silently pass on an invented fixture.
_TS_SAMPLES_DIR = Path(
    "/Users/benjaminpoersch/Projects/SaaS/Sizhu/Sizhu_middleware/"
    "docs/contracts/fufire-samples"
)
_BAZI_SAMPLE_PATH = _TS_SAMPLES_DIR / "bazi.response.json"
_WUXING_SAMPLE_PATH = _TS_SAMPLES_DIR / "wuxing.response.json"
_SAMPLES_AVAILABLE = _BAZI_SAMPLE_PATH.exists() and _WUXING_SAMPLE_PATH.exists()

requires_samples = pytest.mark.skipif(
    not _SAMPLES_AVAILABLE,
    reason=f"TS parity samples not found under {_TS_SAMPLES_DIR} — cannot prove parity",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _bazi_sample() -> dict:
    return copy.deepcopy(_load(_BAZI_SAMPLE_PATH)) if _SAMPLES_AVAILABLE else {}


def _wuxing_sample() -> dict:
    return copy.deepcopy(_load(_WUXING_SAMPLE_PATH)) if _SAMPLES_AVAILABLE else {}


# Deterministic chronometry frame (REQ-003 domain_extras.chronometry) — matches
# the ChronometryFrameResponse shape from routers/chronometry.py.
def _chronometry_sample() -> dict:
    return {
        "julian_day": 2448058.0208333335,
        "julian_day_number": 2448058,
        "delta_t_seconds": 56.9,
        "equation_of_time_minutes": -0.027,
        "eot_source": "meeus_1998",
        "longitude_correction_minutes": 53.62,
        "true_solar_time": "13:23",
        "tlst_date_rollover": 0,
        "solar_longitude_degrees": 84.31,
        "solar_term": "Mangzhong",
        "boundary_flags": {
            "lichun_jd_ut": 2447926.59,
            "is_before_lichun": False,
            "near_lichun": False,
            "days_from_lichun": 131.4,
        },
        "precision": {
            "grade": "exact",
            "warnings": [],
            "algorithm_version": "test-1.0.0",
        },
    }


# Berlin coords the bazi sample's `input` carries (the "real subject").
BERLIN = {"lat": 52.52, "lon": 13.405, "tz": "Europe/Berlin"}

# A standard request body. Location given via explicit coords (oneOf branch B).
COORDS_BODY = {
    "birth_datetime": "1990-06-15T14:30:00",
    "lat": 52.52,
    "lon": 13.405,
    "tz": "Europe/Berlin",
    "birth_time_known": True,
    "locale": "en",
}

# A request body using the `place` branch (oneOf branch A → internal geocode).
PLACE_BODY = {
    "birth_datetime": "1990-06-15T14:30:00",
    "place": "Berlin, DE",
    "birth_time_known": True,
    "locale": "en",
}


def _post(body: dict, path: str = "/personalize", headers: dict | None = None):
    return client.post(path, json=body, headers=headers or {})


def _patch_all_compute(
    *,
    bazi: dict | None = None,
    wuxing: dict | None = None,
    chrono: dict | None = None,
    location: dict | None = None,
):
    """Context-manager stack patching the four aggregation seams at once.

    Returns a list of patchers the caller enters via ``with contextlib...`` —
    but for readability the tests just nest the explicit ``patch`` calls. This
    helper is provided for the multi-seam tests below.
    """
    return [
        patch(SEAM_BAZI, return_value=bazi if bazi is not None else _bazi_sample()),
        patch(SEAM_WUXING, return_value=wuxing if wuxing is not None else _wuxing_sample()),
        patch(SEAM_CHRONO, return_value=chrono if chrono is not None else _chronometry_sample()),
        patch(SEAM_LOCATION, return_value=location if location is not None else dict(BERLIN)),
    ]


import contextlib  # noqa: E402  (kept beside its sole user for clarity)


@contextlib.contextmanager
def _all_compute(**kwargs):
    with contextlib.ExitStack() as stack:
        for p in _patch_all_compute(**kwargs):
            stack.enter_context(p)
        yield


# ════════════════════════════════════════════════════════════════════════════
# TEST 1 — Determinism: full response shape from controlled mocked compute
# ════════════════════════════════════════════════════════════════════════════

@requires_samples
def test_full_response_shape_is_deterministic_from_mocked_compute():
    """All compute mocked → a stable, fully-typed PersonalizeResponse.

    Proves the response envelope exists with every contract key, independent of
    any engine math or network (determinism = the mocked seam fully controls it).
    """
    with _all_compute():
        r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    data = r.json()

    for key in (
        "animal",
        "element",
        "birth_year",
        "dominant_element",
        "sources",
        "issues",
        "caveats",
        "domain_extras",
    ):
        assert key in data, f"missing contract key: {key} in {data}"

    assert isinstance(data["sources"], dict)
    assert isinstance(data["issues"], list)
    assert isinstance(data["caveats"], list)
    assert isinstance(data["domain_extras"], dict)


@requires_samples
def test_deterministic_repeat_identical_output():
    """Identical mocked input → byte-identical output (no hidden nondeterminism)."""
    with _all_compute():
        r1 = _post(COORDS_BODY)
        r2 = _post(COORDS_BODY)
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
    assert r1.json() == r2.json()


# ════════════════════════════════════════════════════════════════════════════
# TEST 2 — PARITY (the core, EV-002): ported from fufire.responseInterpreter.test.ts
# ════════════════════════════════════════════════════════════════════════════
# Ported TS cases:
#   - "resolves animal/element/birth_year ... records the matched source path" (en)
#   - "locale=de selects pillars.year.tier ('Pferd')"
#   - "missing required source blocks, never guesses" (delete transition.solar_year)
#   - "day-pillar 'unverified' caveat surfaced, not laundered"
# Contract mapping (docs/plans §"Parity mapping"):
#   animal           ← de: bazi.pillars.year.tier / en: bazi.chinese.year.animal
#   element          ← bazi.pillars.year.element
#   birth_year       ← bazi.transition.solar_year
#   dominant_element ← wuxing.dominant_element
# (NOTE: this Python contract maps dominant_element ← wuxing.dominant_element —
#  the WESTERN top-level value. There is NO fusion/eastern_dominant in REQ-002,
#  so the TS fusion/eastern_dominant cases are intentionally NOT ported.)

@requires_samples
def test_parity_happy_mapping_en_locale():
    """en locale → animal 'Horse', element 'Metall', birth_year 1990, dominant 'Holz'."""
    with _all_compute():
        r = _post({**COORDS_BODY, "locale": "en"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["animal"] == "Horse"  # en → bazi.chinese.year.animal
    assert data["element"] == "Metall"  # bazi.pillars.year.element
    assert data["birth_year"] == 1990  # bazi.transition.solar_year
    assert data["dominant_element"] == "Holz"  # wuxing.dominant_element

    # Provenance recorded (the matched source path, not a guess).
    sources = json.dumps(data["sources"])
    assert "chinese.year.animal" in sources
    assert "pillars.year.element" in sources
    assert "transition.solar_year" in sources
    assert "dominant_element" in sources

    # Happy path: no missing-source issues for the four mapped vars.
    issues = json.dumps(data["issues"])
    assert PROMPT_VARIABLE_SOURCE_MISSING not in issues, data["issues"]


@requires_samples
def test_parity_happy_mapping_de_locale_uses_tier_never_mixes():
    """de locale → animal 'Pferd' (pillars.year.tier); never the en 'Horse'."""
    with _all_compute():
        r = _post({**COORDS_BODY, "locale": "de"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["animal"] == "Pferd"  # de → bazi.pillars.year.tier
    assert data["animal"] != "Horse"
    # The matched animal source must be the tier path, not the en path.
    assert "pillars.year.tier" in json.dumps(data["sources"])


@requires_samples
def test_parity_missing_wuxing_dominant_yields_null_and_issue_never_guesses():
    """No wuxing.dominant_element → dominant_element NULL + PROMPT_VARIABLE_SOURCE_MISSING.

    The True-Line "no invented data" boundary: a missing source must be nulled
    and flagged, NEVER silently defaulted to a plausible element.
    """
    broken_wuxing = _wuxing_sample()
    broken_wuxing.pop("dominant_element", None)
    with _all_compute(wuxing=broken_wuxing):
        r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    data = r.json()

    # Must be null — never a guessed element.
    assert data["dominant_element"] is None, (
        f"missing source must be null, not a guessed value: {data['dominant_element']!r}"
    )
    # And it must be flagged.
    issues = json.dumps(data["issues"])
    assert PROMPT_VARIABLE_SOURCE_MISSING in issues
    assert "dominant_element" in issues
    # The other (present) vars still resolve — the missing one is isolated.
    assert data["animal"] == "Horse"
    assert data["birth_year"] == 1990


@requires_samples
def test_parity_missing_birth_year_source_yields_null_and_issue():
    """Delete bazi.transition.solar_year → birth_year null + PROMPT_VARIABLE_SOURCE_MISSING.

    Direct port of the TS "missing required source blocks, never guesses" case.
    """
    broken_bazi = _bazi_sample()
    broken_bazi["transition"].pop("solar_year", None)
    with _all_compute(bazi=broken_bazi):
        r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["birth_year"] is None, (
        f"missing solar_year must be null, not guessed: {data['birth_year']!r}"
    )
    issues = json.dumps(data["issues"])
    assert PROMPT_VARIABLE_SOURCE_MISSING in issues
    assert "birth_year" in issues


@requires_samples
def test_parity_day_anchor_caveat_surfaced_verbatim_unverified():
    """day-pillar anchor_verification 'unverified' surfaced VERBATIM in caveats.

    Port of the TS "day-pillar 'unverified' caveat surfaced, not laundered" case.
    The sample carries anchor_verification == 'unverified'; the contract requires
    caveats == ["day-pillar anchor_verification: unverified"] (verbatim value).
    """
    sample = _bazi_sample()
    # Sanity: the authoritative sample really carries 'unverified'.
    assert (
        sample["derivation_trace"]["day"]["day_anchor_evidence"]["anchor_verification"]
        == "unverified"
    )
    with _all_compute(bazi=sample):
        r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    data = r.json()

    caveats = data["caveats"]
    assert any("day-pillar anchor_verification" in c for c in caveats), caveats
    # The verbatim provider value must be carried, never relabeled "verified".
    joined = " ".join(caveats).lower()
    assert "unverified" in joined, caveats
    # Anti-laundering: the caveat for the day pillar must not assert "verified"
    # (without the "un" prefix). Guard against a relabel.
    anchor_caveats = [c for c in caveats if "anchor_verification" in c]
    for c in anchor_caveats:
        assert "unverified" in c.lower(), f"day-anchor caveat laundered: {c!r}"


@requires_samples
def test_parity_day_anchor_verified_value_surfaced_verbatim_too():
    """A 'verified' anchor value is surfaced verbatim too (never invented/relabeled).

    Guards the read-the-value-verbatim contract in BOTH directions: the caveat
    must echo whatever the engine reports, not a hardcoded 'unverified'.
    """
    sample = _bazi_sample()
    sample["derivation_trace"]["day"]["day_anchor_evidence"]["anchor_verification"] = "verified"
    with _all_compute(bazi=sample):
        r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    caveats = data_caveats = r.json()["caveats"]
    anchor_caveats = [c for c in data_caveats if "anchor_verification" in c]
    assert anchor_caveats, caveats
    assert any("verified" in c.lower() for c in anchor_caveats)
    # It echoed the engine's "verified" — not a stale hardcoded "unverified".
    assert all("unverified" not in c.lower() for c in anchor_caveats), anchor_caveats


# ════════════════════════════════════════════════════════════════════════════
# TEST 3 — Input oneOf (OQ-003): place vs explicit coords vs neither/both
# ════════════════════════════════════════════════════════════════════════════

@requires_samples
def test_place_branch_resolves_via_internal_geocode():
    """place given → _resolve_location (geocode) is invoked and its coords are used.

    The geocode seam is mocked to Berlin; the request must succeed and the
    location resolution must be exercised (proves the place→geocode wiring).
    """
    with patch(SEAM_LOCATION, return_value=dict(BERLIN)) as loc, \
        patch(SEAM_BAZI, return_value=_bazi_sample()), \
        patch(SEAM_WUXING, return_value=_wuxing_sample()), \
        patch(SEAM_CHRONO, return_value=_chronometry_sample()):
        r = _post(PLACE_BODY)
    assert r.status_code == 200, r.text
    assert loc.called, "place branch must call the internal geocode resolver"


def test_place_branch_geocode_candidates_seam_is_open_meteo_service():
    """When place is given, the underlying geocode goes through services.geocoding.

    This pins the REQ-001 reuse: the coder must resolve `place` via
    geocode_candidates (Open-Meteo), not invent a new geocoder. We patch the
    service seam (same one test_geocode_endpoint uses) and assert a 200 — proving
    the place path is wired to the real REQ-001 service when the router-level
    _resolve_location seam is NOT itself stubbed.
    """
    from unittest.mock import AsyncMock, MagicMock

    berlin = [{
        "name": "Berlin", "latitude": 52.52, "longitude": 13.405,
        "timezone": "Europe/Berlin", "country_code": "DE", "population": 3426354,
    }]
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": berlin}
    mock_resp.raise_for_status = MagicMock()
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    # Only the bazi/wuxing/chrono compute is stubbed; location flows through the
    # REAL geocode service (httpx mocked at the same seam as REQ-001).
    with patch("bazi_engine.services.geocoding.httpx.AsyncClient", return_value=mock_client), \
        patch(SEAM_BAZI, return_value=_bazi_sample() if _SAMPLES_AVAILABLE else {}), \
        patch(SEAM_WUXING, return_value=_wuxing_sample() if _SAMPLES_AVAILABLE else {}), \
        patch(SEAM_CHRONO, return_value=_chronometry_sample()):
        from bazi_engine.services.geocoding import clear_geocode_cache
        clear_geocode_cache()
        r = _post(PLACE_BODY)
        clear_geocode_cache()
    # If samples are missing the mapping may flag issues, but the place→geocode
    # path itself must NOT be a routing/validation error.
    assert r.status_code == 200, r.text


@requires_samples
def test_explicit_coords_branch_used_directly_no_geocode():
    """Explicit lat/lon/tz → coords used directly; geocode resolver NOT called."""
    with patch(SEAM_LOCATION) as loc, \
        patch(SEAM_BAZI, return_value=_bazi_sample()), \
        patch(SEAM_WUXING, return_value=_wuxing_sample()), \
        patch(SEAM_CHRONO, return_value=_chronometry_sample()):
        r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    assert not loc.called, (
        "explicit coords must NOT trigger the internal geocode resolver"
    )


def test_oneof_neither_place_nor_coords_returns_422():
    """Neither place nor (lat+lon+tz) → 422 (exactly-one-of violated)."""
    body = {"birth_datetime": "1990-06-15T14:30:00", "locale": "en"}
    r = _post(body)
    assert r.status_code == 422, r.text


def test_oneof_both_place_and_coords_returns_422():
    """Both place AND coords → 422 (exactly-one-of violated)."""
    body = {
        "birth_datetime": "1990-06-15T14:30:00",
        "place": "Berlin, DE",
        "lat": 52.52,
        "lon": 13.405,
        "tz": "Europe/Berlin",
        "locale": "en",
    }
    r = _post(body)
    assert r.status_code == 422, r.text


def test_partial_coords_lat_lon_without_tz_returns_422():
    """Coords branch requires lat+lon+tz together; lat+lon without tz → 422."""
    body = {
        "birth_datetime": "1990-06-15T14:30:00",
        "lat": 52.52,
        "lon": 13.405,
        "locale": "en",
    }
    r = _post(body)
    assert r.status_code == 422, r.text


# ════════════════════════════════════════════════════════════════════════════
# TEST 4 — domain_extras (REQ-003): bazi_trace + chronometry present + POPULATED
# ════════════════════════════════════════════════════════════════════════════
# Gegenthese guard: present-but-empty domain_extras would make the REQ-003
# "migration" look done while the real engine data never flows. Assert POPULATED.

@requires_samples
def test_domain_extras_present_and_populated_from_mocked_compute():
    """domain_extras.bazi_trace + domain_extras.chronometry present AND populated.

    REQ-003: these are REAL engine outputs now (NOT render-blocked), so they must
    NOT carry PROMPT_VARIABLE_SOURCE_MISSING, and must echo the mocked compute.
    """
    bazi = _bazi_sample()
    chrono = _chronometry_sample()
    with _all_compute(bazi=bazi, chrono=chrono):
        r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    extras = r.json()["domain_extras"]

    assert "bazi_trace" in extras, extras
    assert "chronometry" in extras, extras

    # Populated, not empty.
    assert extras["bazi_trace"], "bazi_trace must be populated (REQ-003 real data)"
    assert extras["chronometry"], "chronometry must be populated (REQ-003 real data)"

    # bazi_trace must carry the real engine trace shape (the day anchor evidence
    # is the load-bearing field the caveat is read from).
    trace = extras["bazi_trace"]
    trace_json = json.dumps(trace)
    assert "day_anchor_evidence" in trace_json or "anchor_verification" in trace_json, (
        f"bazi_trace must expose the real derivation trace, got: {trace}"
    )

    # chronometry must echo the mocked frame numbers (proves real data flows, not
    # a hardcoded stub).
    assert extras["chronometry"]["julian_day_number"] == chrono["julian_day_number"]
    assert extras["chronometry"]["solar_term"] == chrono["solar_term"]


@requires_samples
def test_domain_extras_never_flagged_as_missing_source():
    """REQ-003: bazi_trace/chronometry are real → NO PROMPT_VARIABLE_SOURCE_MISSING for them.

    The old TS interpreter render-blocked these as 'no real sample'; this endpoint
    provides the REAL data — that IS the migration. So issues must not mention them.
    """
    with _all_compute():
        r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    issues_joined = json.dumps(r.json()["issues"]).lower()
    assert "bazi_trace" not in issues_joined, r.json()["issues"]
    assert "chronometry" not in issues_joined, r.json()["issues"]


# ════════════════════════════════════════════════════════════════════════════
# TEST 5 — Mount-reality anchor: empty body → 422 on BOTH routes (not unmapped 404)
# ════════════════════════════════════════════════════════════════════════════
# Kritische semantische Glättung / Gegenthese: every mocked test can be green while
# the router is built but never include_router'd into `app`. This fails loudly in
# that case — an UNMOUNTED route returns 404 for the path; a MOUNTED route with a
# bad body returns 422 (validation). No mocks here: this exercises the assembled app.

def test_route_mounted_unprefixed_empty_body_is_422_not_unmapped_404():
    """Empty body on /personalize → 422 validation, NOT an unmapped-route 404."""
    r = _post({})
    assert r.status_code != 404, (
        f"/personalize appears UNMOUNTED (404) — router not wired into app: {r.text}"
    )
    assert r.status_code == 422, f"expected validation 422, got {r.status_code}: {r.text}"


def test_route_mounted_v1_empty_body_is_422_not_unmapped_404():
    """Empty body on /v1/personalize → 422 validation, NOT an unmapped-route 404."""
    r = _post({}, path="/v1/personalize")
    assert r.status_code != 404, (
        f"/v1/personalize appears UNMOUNTED (404) — router not wired into app: {r.text}"
    )
    assert r.status_code == 422, f"expected validation 422, got {r.status_code}: {r.text}"


@requires_samples
def test_v1_route_returns_same_mapping_as_unprefixed():
    """/v1/personalize resolves to the same handler/mapping as /personalize."""
    with _all_compute():
        r_bare = _post(COORDS_BODY)
        r_v1 = _post(COORDS_BODY, path="/v1/personalize")
    assert r_bare.status_code == 200, r_bare.text
    assert r_v1.status_code == 200, r_v1.text
    # Same 4 vars from the same mocked compute.
    for key in ("animal", "element", "birth_year", "dominant_element"):
        assert r_bare.json()[key] == r_v1.json()[key]


# ════════════════════════════════════════════════════════════════════════════
# TEST 6 — Auth: no key with auth enabled → 401 (mirrors test_geocode_endpoint)
# ════════════════════════════════════════════════════════════════════════════
# Default test env has no FUFIRE_API_KEYS → dev-mode bypass, so the mocked tests
# above need no key. To prove the route IS protected, turn auth ON.

def test_no_api_key_returns_401_when_auth_enabled():
    """With auth configured, a request without X-API-Key → 401 (require_api_key)."""
    from bazi_engine.auth import _load_keys

    os.environ["FUFIRE_REQUIRE_API_KEYS"] = "true"
    os.environ["FUFIRE_API_KEYS"] = "ff_pro_testsecret"
    _load_keys.cache_clear()
    try:
        # Mock compute anyway so a regression that computes before auth is still
        # deterministic; auth must reject first regardless.
        with _all_compute():
            r = _post(COORDS_BODY)
    finally:
        os.environ.pop("FUFIRE_REQUIRE_API_KEYS", None)
        os.environ.pop("FUFIRE_API_KEYS", None)
        _load_keys.cache_clear()

    assert r.status_code == 401, (
        f"expected 401 without API key, got {r.status_code}: {r.text}"
    )


def test_valid_api_key_passes_auth():
    """A valid X-API-Key passes the gate (proves it's the auth, not the route, that 401s)."""
    from bazi_engine.auth import _load_keys

    os.environ["FUFIRE_REQUIRE_API_KEYS"] = "true"
    os.environ["FUFIRE_API_KEYS"] = "ff_pro_testsecret"
    _load_keys.cache_clear()
    try:
        with _all_compute():
            r = _post(COORDS_BODY, headers={"X-API-Key": "ff_pro_testsecret"})
    finally:
        os.environ.pop("FUFIRE_REQUIRE_API_KEYS", None)
        os.environ.pop("FUFIRE_API_KEYS", None)
        _load_keys.cache_clear()

    assert r.status_code != 401, f"valid key was rejected: {r.status_code} {r.text}"
    if _SAMPLES_AVAILABLE:
        assert r.status_code == 200, r.text


# ════════════════════════════════════════════════════════════════════════════
# TEST 6b — REGRESSION (B1): real model→dict boundary BELOW the _compute_bazi_for seam
# ════════════════════════════════════════════════════════════════════════════
# WHY THE MOCKED SUITE WAS BLIND TO B1:
#   Every test above patches `_compute_bazi_for` and feeds a FULLY-DICT sample
#   (loaded from JSON). But the REAL `_compute_bazi_for` calls
#   `bazi._compute_bazi_response`, which returns `derivation_trace` as a
#   **Pydantic model instance** (`BaziDerivationTrace`), NOT a dict. The parity
#   mapping reads the day-anchor caveat via `_read_path`, which requires
#   `isinstance(current, dict)` at every segment — so against the REAL return
#   shape `derivation_trace.day.day_anchor_evidence.anchor_verification` is
#   UNREADABLE: the verbatim caveat is DROPPED and a spurious
#   PROMPT_VARIABLE_SOURCE_MISSING is emitted on every real call. Same defect
#   makes domain_extras.bazi_trace carry a model, not a dict (M1).
#
#   This regression patches the REAL lower function (`_compute_bazi_response`)
#   to return the live shape (model-instance derivation_trace) and leaves
#   `_compute_bazi_for` UNPATCHED, so the model→dict conversion (the fix) is the
#   thing under test. RED before the fix; GREEN after.

def _real_derivation_trace_model(anchor_verification: str = "unverified"):
    """Build a minimal-but-valid real `BaziDerivationTrace` MODEL INSTANCE.

    This is the load-bearing point: the object returned is a Pydantic model
    (NOT a dict), exactly like the live `_compute_bazi_response` return — its
    nested `day.day_anchor_evidence.anchor_verification` is unreadable by the
    dict-only `_read_path` until the bazi response is `model_dump`-ed.
    """
    from bazi_engine.routers.bazi import (
        BaziDerivationTrace,
        DayAnchorEvidence,
        DayDerivationTrace,
        HourDerivationTrace,
        MonthDerivationTrace,
        ProvenanceIds,
        TimeResolutionTrace,
        YearDerivationTrace,
    )

    return BaziDerivationTrace(
        year=YearDerivationTrace(
            lichun_crossing_utc="1990-02-04T08:14:00+00:00",
            is_before_lichun=False,
            solar_longitude_lichun=315.0,
        ),
        month=MonthDerivationTrace(
            jieqi_crossing_utc="1990-06-06T00:00:00+00:00",
            solar_longitude_deg=84.31,
            month_branch_index=6,
        ),
        day=DayDerivationTrace(
            julian_day_number=2448058,
            sexagenary_index=12,
            day_offset_used=0,
            day_master_stem="Geng",
            day_anchor_evidence=DayAnchorEvidence(
                ruleset_id="standard_bazi_2026",
                ruleset_version="1.0.0",
                anchor_jdn=2448058,
                anchor_sex_idx=12,
                anchor_verification=anchor_verification,
            ),
        ),
        hour=HourDerivationTrace(
            local_hour=14,
            branch_index=7,
            true_solar_time_used=False,
            lmt_used=False,
            time_standard_requested="CIVIL",
            time_standard_used="CIVIL",
            hour_branch_time_policy=None,
        ),
        time_resolution=TimeResolutionTrace(
            civil_local="1990-06-15T14:30:00+02:00",
            utc="1990-06-15T12:30:00+00:00",
            lmt="1990-06-15T13:23:00+01:00",
            tlst_hours=14.38,
            eot_minutes=-0.027,
            eot_source="meeus_1998",
            tlst_date_rollover=0,
            tz_offset_minutes=120,
            effective_standard="CIVIL",
        ),
        provenance_ids=ProvenanceIds(
            ruleset_id="standard_bazi_2026",
            ruleset_version="1.0.0",
            time_policy_id="civil_midnight",
            day_anchor_id="standard_bazi_2026:jdn_2448058_verified",
            vector_model_id="wuxing_v1.1.0",
        ),
    )


def _bazi_response_with_model_trace(anchor_verification: str = "unverified") -> dict:
    """A `_compute_bazi_response`-shaped payload whose `derivation_trace` is a
    real MODEL INSTANCE (the live return shape) — everything else plain dicts.

    Mirrors the assembled dict built in `bazi._compute_bazi_response` (line 382)
    so `_compute_bazi_for` can run unpatched: the four prompt-var sources
    (pillars/chinese/transition) are present, and `derivation_trace` is the
    model object, NOT a dict (this is exactly what drops the caveat pre-fix).
    """
    return {
        "input": {
            "date": "1990-06-15T14:30:00",
            "tz": "Europe/Berlin",
            "lon": 13.405,
            "lat": 52.52,
            "standard": "CIVIL",
            "boundary": "midnight",
            "ambiguousTime": "earlier",
            "nonexistentTime": "error",
            "birth_time_known": True,
        },
        "pillars": {
            "year": {"stamm": "Geng", "zweig": "Wu", "tier": "Pferd", "element": "Metall"},
            "month": {"stamm": "Ren", "zweig": "Wu", "tier": "Pferd", "element": "Wasser"},
            "day": {"stamm": "Geng", "zweig": "Shen", "tier": "Affe", "element": "Metall"},
            "hour": {"stamm": "Jia", "zweig": "Shen", "tier": "Affe", "element": "Holz"},
        },
        "chinese": {
            "year": {"stem": "Geng", "branch": "Wu", "animal": "Horse"},
            "month_master": "Ren",
            "day_master": "Geng",
            "hour_master": "Jia",
        },
        "dates": {
            "birth_local": "1990-06-15T14:30:00+02:00",
            "birth_utc": "1990-06-15T12:30:00+00:00",
            "lichun_local": "1990-02-04T09:14:00+01:00",
        },
        "transition": {
            "solar_year": 1990,
            "is_before_lichun": False,
            "lichun_year_start": "1990-02-04T09:14:00+01:00",
            "lichun_next": "1991-02-04T15:08:00+01:00",
        },
        "solar_terms_count": 24,
        "provenance": {},
        "precision": {"birth_time_known": True, "provisional_fields": []},
        # THE LOAD-BEARING POINT: a MODEL INSTANCE, not a dict (live shape).
        "derivation_trace": _real_derivation_trace_model(anchor_verification),
    }


def test_regression_b1_real_model_trace_surfaces_caveat_and_dict_extras():
    """B1/M1 regression: a MODEL-INSTANCE derivation_trace (the live shape) must
    still surface the verbatim day-anchor caveat and expose a plain-dict
    bazi_trace — exercising the model→dict conversion in `_compute_bazi_for`.

    `_compute_bazi_for` is LEFT UNPATCHED; only the REAL lower function
    `bazi._compute_bazi_response` is patched to return the model-trace shape.
    Pre-fix this FAILS (caveat dropped + spurious PROMPT_VARIABLE_SOURCE_MISSING
    + bazi_trace is not a dict). Post-fix it passes.
    """
    with patch(
        "bazi_engine.routers.bazi._compute_bazi_response",
        return_value=_bazi_response_with_model_trace("unverified"),
    ), patch(SEAM_WUXING, return_value={"dominant_element": "Holz"}), \
        patch(SEAM_CHRONO, return_value=_chronometry_sample()), \
        patch(SEAM_LOCATION, return_value=dict(BERLIN)):
        r = _post(COORDS_BODY)

    assert r.status_code == 200, r.text
    data = r.json()

    # (a) The verbatim day-pillar caveat must surface from the MODEL trace.
    assert "day-pillar anchor_verification: unverified" in data["caveats"], (
        f"day-anchor caveat dropped against the real model-instance trace "
        f"(B1): caveats={data['caveats']!r}"
    )

    # (b) NO spurious PROMPT_VARIABLE_SOURCE_MISSING for the day anchor.
    issues_joined = json.dumps(data["issues"])
    assert "anchor_verification" not in issues_joined, (
        f"spurious missing-source issue for the day anchor (B1): {data['issues']!r}"
    )
    assert PROMPT_VARIABLE_SOURCE_MISSING not in issues_joined, data["issues"]

    # The four prompt vars still resolve from the (dict-shaped) sources.
    assert data["animal"] == "Horse"
    assert data["element"] == "Metall"
    assert data["birth_year"] == 1990
    assert data["dominant_element"] == "Holz"

    # (c) domain_extras.bazi_trace is a PLAIN DICT exposing day_anchor_evidence (M1).
    trace = data["domain_extras"]["bazi_trace"]
    assert isinstance(trace, dict), f"bazi_trace must be a plain dict, got {type(trace)}"
    assert "day_anchor_evidence" in trace["day"], trace
    assert (
        trace["day"]["day_anchor_evidence"]["anchor_verification"] == "unverified"
    ), trace


# ════════════════════════════════════════════════════════════════════════════
# TEST 7 — RUN_LIVE live smoke (EV-004): real internal compute, NO mocks (skipped)
# ════════════════════════════════════════════════════════════════════════════
# The only test exercising the assembled endpoint against REAL internal compute
# (bazi + wuxing + chronometry + geocode), with NO mocks. SKIPPED by default;
# runs only with RUN_LIVE=1 (same env-gate convention as test_geocode_endpoint
# EV-001). It kills the "green against a fake, broken against reality"
# counter-thesis: the 4 vars must actually resolve and domain_extras be present
# when the real engine runs end-to-end.

RUN_LIVE = os.environ.get("RUN_LIVE") == "1"


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="live end-to-end personalize smoke (EV-004) — set RUN_LIVE=1 to run",
)
def test_live_personalize_end_to_end_smoke():
    """EV-004: real birth input through the assembled endpoint, real internal compute.

    No mocks. Asserts the 4 prompt vars resolve to real values and domain_extras
    are present + populated — the assembled system delivers the customer value.
    """
    # Explicit coords avoid a live geocode dependency; the metaphysics engine is
    # the real subject under test here.
    r = _post(COORDS_BODY)
    assert r.status_code == 200, r.text
    data = r.json()

    # The four prompt vars must resolve to real (non-null) values for a known,
    # well-formed birth input.
    assert data["animal"], f"animal did not resolve: {data}"
    assert data["element"], f"element did not resolve: {data}"
    assert isinstance(data["birth_year"], int) and data["birth_year"] > 0, data
    assert data["dominant_element"], f"dominant_element did not resolve: {data}"

    # For a 1990 birth the solar year is 1990 (LiChun already passed in June).
    assert data["birth_year"] == 1990, data

    # domain_extras carry REAL engine output.
    extras = data["domain_extras"]
    assert extras.get("bazi_trace"), "live bazi_trace must be populated"
    assert extras.get("chronometry"), "live chronometry must be populated"

    # The day-anchor caveat is surfaced verbatim from the real engine trace.
    assert any("anchor_verification" in c for c in data["caveats"]), data["caveats"]
