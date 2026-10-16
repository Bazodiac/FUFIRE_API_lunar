# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**FuFirE — Fusion Firmament Engine** is a deterministic astronomical calculation engine for Chinese astrology (Four Pillars of Destiny / BaZi) with Western astrology integration. Calculates Year/Month/Day/Hour pillars based on precise solar-term boundaries using Swiss Ephemeris.

Two engines live here: the mature BaZi/Western fusion engine, and a second, independent **Zi Wei Dou Shu (ZWDS) engine** (`bazi_engine/zwds/`, feature-flagged, core-seed phase). Engine separation is test-enforced — see Architecture.

**Key Characteristics:**
- Deterministic: No randomness, purely astronomical calculations
- Immutable: All dataclasses use `frozen=True`
- Type-safe: Complete type hint coverage (Python 3.10+)
- Functional: Pure functions with no side effects
- Contract-first: JSON Schema (Draft-07) validation for `/validate` endpoint

### Repo Lineage & Branches

- This repo (DYAI2025/FUFIRE_API_lunar) is a fresh "Lunar" cut of the canonical DYAI2025/FuFirE repo. Git history starts at `fe8f019` ("Initial commit" — the `bootstrap-sha` in `release-please-config.json`). CHANGELOG entries ≤ 1.5.0 link to commits in the **upstream** repo; those SHAs do not exist here — a failing `git show` on them is not corruption.
- **`master` is the default AND deployed branch.** Railway deploys master; CI runs on both master and main (commit 9d19a3e: "cover master with full CI while it remains deployed"). `main` is a periodically synced mirror, currently behind master. The master→main normalization is a planned task (TASK-002 in `docs/plans/2026-07-21-fufire-api-lunar-release-readiness.md`); next release is fixed at 1.6.0.

### Versioning (two independent axes)

1. **Package/release version** in `pyproject.toml` — owned by [release-please](https://github.com/googleapis/release-please) in **manifest mode**: `.release-please-manifest.json` must stay consistent with pyproject and `CHANGELOG.md`, and the workflow needs the `RELEASE_PLEASE_TOKEN` secret (fails closed without it). Never hand-edit the version in only one of these files. Caveat: release-please watches `main` only, so while work lands on master the automation is **dormant** — it has never actually cut a release here; 1.5.0 was a hand-seeded baseline reconstructed from upstream.
2. **Engine build label** `bazi_engine/__init__.py` `__version__` (e.g. `1.0.0-rc5-20261016`) — used in API responses, the OpenAPI spec, and golden snapshot fixtures. Bumped manually, deliberately, alongside a snapshot regeneration. Regenerate the OpenAPI spec (`python scripts/export_openapi.py`) after changing it.

### Current State

Task-progress source of truth: **`3-code/tasks.md`** (TASK-* and FBP-* status tables). Update that file when completing/re-scoping tasks — this summary is derived from it.

- Implementation plan (34 tasks, 2026-04-13): Phases 1–4 ✅ complete; Phase 5 (enterprise differentiation) 4/5.
- **BAZI-PRECISION-V2** (44 tasks, phased, test-first, review-gated): Phase 0 ✅ 8/8; Phase 1 ✅ 5/5 (Effective Time Model CIVIL/LMT/TLST); Phase 2 — 2/8 (FBP-02-002/003/007 need domain reviewer — DEV-2026-004); Phase 3 — 5/6 done (only FBP-03-006 open); Phases 4–7 not started.
- Recently shipped (CHANGELOG 1.1.0–1.5.0, July 2026): dayun solar-years + interpretation, ZWDS core-seed natal engine, natal-analysis endpoint, canonical BaZi Wu-Xing endpoint, release-readiness work toward 1.6.0.

> ⚠️ **Stale sibling docs:** `AGENTS.md`, `SDLC.md`, and `ARCHITECTURE_DE.md` are outdated snapshots (Fly.io deploy targets, pre-router-refactor architecture, wrong webhook paths, 3-of-4 ephemeris files). Fly.io is decommissioned; Railway is the sole deployment target. On any conflict, this file plus the repo itself win.

## Development Commands

```bash
# Setup — local convenience (CI does NOT install this way; see lock contract below)
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# CI-faithful install instead:
#   python -m pip install pip==26.1.2 uv==0.11.29 && uv sync --frozen --extra dev

# Ephemeris for a CI-equivalent run (otherwise the suite silently runs on MOSEPH — see Testing)
python scripts/fetch_ephemeris.py --destination /tmp/ephe   # SHA256-verified vs ephemeris.lock.json
SE_EPHE_PATH=/tmp/ephe pytest -q

# Run tests
pytest -q                                     # Quick run
pytest tests/test_golden.py                   # Golden vectors only
pytest -k "test_name"                         # Pattern matching
pytest -v --cov=bazi_engine --cov-fail-under=75   # Coverage (CI threshold)

# Lint & typecheck — CI lints all three trees; bazi_engine/ alone can pass locally and fail CI
ruff check bazi_engine/ tests/ scripts/ --output-format=github
mypy bazi_engine --ignore-missing-imports
python scripts/check_complexity.py --check    # CI gate: new functions must have CC ≤ 15

# Start API server
uvicorn bazi_engine.app:app --reload --port 8080

# CLI usage
python -m bazi_engine.cli 2024-02-10T14:30:00 --tz Europe/Berlin --lon 13.405 --lat 52.52
python -m bazi_engine.cli 2024-02-10T14:30:00 --json

# OpenAPI contract
python scripts/export_openapi.py              # Regenerate after endpoint changes
python scripts/export_openapi.py --check      # CI drift check
python tests/golden/regen_route_table.py      # Regenerate route-mount golden after ANY mount/route change
python scripts/gen_tlst_reference_corpus.py --check   # CI lint: TLST corpus vs Swiss-Ephemeris oracle (backend-agnostic)

# Docker — FUFIRE_ENV is mandatory (image bakes FUFIRE_REQUIRE_EXPLICIT_ENV=1; omitting it crashes startup)
docker build -t bazi_engine . && docker run -e FUFIRE_ENV=dev -p 8080:8080 bazi_engine

# Deploy: push to MASTER (Railway auto-deploys; railway.toml noCache=true → every build is full/uncached)
git push origin master
# Railway healthcheck = GET /ready (503 when a required dependency is degraded); /health = liveness only
# Verify the live commit after deploy: GET /build (exposes RAILWAY_GIT_COMMIT_SHA when EXPOSE_BUILD_METADATA=1)
```

### Dependency & Toolchain Lock Contract (fail-closed)

- **Three lock files are mandatory and validated:** `pyproject.toml` + `uv.lock` (canonical resolver output, must stay revision-3; CI installs `uv sync --frozen`, Docker installs `uv export --frozen … --require-hashes`) + `requirements.lock` (exact `==` pins only). Changing any dependency in pyproject.toml requires regenerating **both** locks, or every CI job fails on `--frozen` drift.
- `scripts/assert_toolchain_versions.py` (run in CI lint; mirrored by `tests/test_toolchain_pinning.py`, so plain `pytest` also catches drift) enforces: exact-pinned dev/build deps, SHA-pinned GitHub Actions, digest-pinned Docker base images (the main Dockerfile must be `python:3.12-slim@sha256:…`), and **identical** build-bootstrap pins (`setuptools==80.9.0`, `wheel==0.47.0`, `pip==26.1.2`, `uv==0.11.29`, Node 22.21.1) across pyproject `[build-system]`, the Dockerfile, and `ci.yml`. Bumping any of these requires lockstep edits to all three files in one commit — a single-file dependabot bump is exactly what broke the Railway build (repaired in 9d19a3e).
- `Dockerfile.ephe-base` builds a separate GHCR ephemeris base image (manual workflow). The main Dockerfile does **not** consume it, but the toolchain validator checks both files — do not delete it as "dead code".

### CI Release Gate

Branch protection is the single fail-closed `release-gate` job, which requires **all** of: test (3.10/3.11/3.12, real SWIEPH ephemeris), lint+mypy+toolchain-assert, complexity (`check_complexity.py --check`), security (`pip-audit --strict` + `bandit -r bazi_engine -ll` + SBOM validation), distribution (wheel+sdist build, `scripts/verify_distribution.py`, clean-install smoke), docker-build (incl. non-root uid-10001 ephemeris-read check), and codegen (`redocly lint` on the OpenAPI spec, TypeScript-fetch client generation, `tsc` compile). Green local pytest+ruff+mypy does **not** imply green CI — complexity, dep bumps, and OpenAPI changes are the usual extra failures.

## Architecture

### Module Hierarchy (import direction: top → bottom only)

The authoritative layer map is the `LAYERS` dict in `tests/test_import_hierarchy.py` — **modules not registered there are silently skipped** ("not registered in layer map"), so every new module must be added to `LAYERS` or its layer contract is unchecked.

```
Level 0: constants.py              # STEMS, BRANCHES, DAY_OFFSET=49
         exc.py                    # Exception hierarchy — zero internal deps
         resource_loader.py        # Stdlib-only fail-closed importlib.resources boundary for packaged data
Level 1: types.py                  # Pillar, FourPillars, BaziInput, BaziResult (frozen)
         provenance.py             # Provenance/audit trail — only imports __version__
Level 2: ephemeris.py              # SwissEphBackend, EphemerisBackend protocol
         time_utils.py             # parse_local_iso, LocalTimeError
         solar_time.py             # True Solar Time calculations
         time_context.py           # FBP-01-002: EffectiveTimeContext (CIVIL/LMT/TLST; TLST deliberately not a tzinfo)
         lunar_state.py            # Canonical UTC/JD geocentric Sun/Moon state — backs /v2 astronomy;
                                   #   deliberately SEPARATE from legacy phases.lunar_phase (both exist on purpose)
         phases/                   # Lunar/Jieqi phase calculations (legacy approximation)
         bafe.ruleset_loader,      # Formally Layer 2 (no longer an informal carve-out): pure data loaders
         bafe.mapping              #   via the Layer-0 resource boundary / stdlib-only math
Level 3: jieqi.py                  # Solar term calculations, find_crossing() bisection
         bazi_rules.py             # FBP-02-001: typed ruleset accessors (day_offset_from_ruleset, …) —
                                   #   the canonical path for ruleset-driven knobs; extend it, don't hardcode
Level 4: bazi.py                   # compute_bazi() — main 9-step pipeline
         western.py, fusion.py, transit.py, aspects.py, narrative.py
         dignities.py, decanates_terms.py, fixed_stars.py   # Phase-5 pure lookup/detection modules
         impact.py, impact_harmony.py, impact_resonance.py, impact_types.py
         chronometry.py            # Pure domain module (no FastAPI) behind /chronometry/resolve AND /personalize;
                                   #   hard rule: no silent noon default for unknown birth time
         wuxing/                   # constants, vector, analysis, calibration, zones, ke_cycle
         match/                    # BaZi-Hehun pair analysis — imports Levels 0–4 only
         dayun/                    # DaYun luck-cycle SUBPACKAGE (start_age, direction, jiazi, dates,
                                   #   interpretation, …) — routers/dayun.py is only the HTTP layer;
                                   #   zwds/decadal.py also imports dayun.direction
         zwds/                     # Independent second engine (Zi Wei Dou Shu) — see below
         synergy/                  # Placeholder: the ONLY sanctioned home for cross-engine BaZi+ZWDS code
Level 5: app.py                    # Thin factory: assert_runtime_config → app → middleware → handlers → mount_all → openapi
         openapi_ext.py, error_handlers.py, config_guard.py
         auth.py                   # V1 API-key dependency require_api_key (Layer 5 — imports key_store)
         key_store.py              # Pluggable store for runtime-minted keys (KEY_STORE_BACKEND=none|memory)
         features.py               # FEATURE_MATRIX release flags (key_issuance, zwds) — env-resolved per request
         cli.py, middleware.py, limiter.py
         routers/                  # registry.py = declarative mount table
         services/                 # auth (webhook HMAC!), geocoding, soulprint, daily_*, zwds_service, …
         bafe/ (rest), research/
```

**Critical Rule:** Lower-level modules must never import higher-level modules.

**Engine separation (ZWDS-P0-03):** `FORBIDDEN_EDGES` in the hierarchy test bans `zwds/*` ↔ `bazi`/`western`/`fusion`/`impact` imports in **both** directions (checked even in `__init__.py` re-export hubs). `synergy/` may import both engines but never `routers/` or `app`.

**Packaged data vs `spec/`:** the deployed runtime is **source-free** — it loads rulesets/schemas from `bazi_engine/resources/` via `resource_loader` (fail-closed: errors on missing data, never substitutes defaults). `spec/` is the repo-side authoring mirror; **editing only `spec/` changes nothing at runtime.** `scripts/verify_distribution.py` fails the build if `spec/` leaks into the wheel. ZWDS ruleset data lives in `bazi_engine/data/zwds/rulesets/` (immutable, hash-locked).

### Router Structure (`bazi_engine/routers/`)

`app.py` is a thin factory: `assert_runtime_config()` (import time!) → `FastAPI(...)` → middleware/CORS → `register_exception_handlers` → `mount_all` → `install_custom_openapi`. No business logic in `app.py`.

`registry.py` mounts in **four ordered phases** — legacy public, `/v1`, `/v2`, then schema-hidden internal — and mount order is load-bearing (route matching and OpenAPI path ordering follow registration order; legacy mounts are frozen for Bazodiac compatibility). Mount rows can carry a `feature_flag` (from `features.py` `FEATURE_MATRIX`): when disabled, requests get `404 {"error": "feature_disabled"}` and the mount is hidden from the OpenAPI schema.

| Router | Endpoints |
|--------|-----------|
| `bazi.py` | `/calculate/bazi`, `/calculate/bazi/trace` (beta), `/calculate/bazi/wuxing` (canonical BaZi Five-Element distribution) |
| `natal.py` | `/calculate/bazi/natal` — per-pillar hidden stems (DECISION-003 Qi weights), Ten Gods, month command. Deliberately emits NO seasonal-strength/day-master-strength/yong_shen fields (anti-fabrication AC-005c). Own schemas in `schemas/calculate/bazi/` |
| `dayun.py` | `/calculate/bazi/dayun` (HTTP layer over the `dayun/` subpackage) |
| `western.py` | `/calculate/western` (only route) |
| `fusion.py` | `/calculate/fusion`, `/calculate/wuxing` (Wu-Xing from WESTERN positions — distinct from `/calculate/bazi/wuxing`), `/calculate/tst`, `/calculate/fusion/vector-map` (beta) |
| `transit.py` | `/transit/now`, `/transit/timeline`, `/transit/state`, `/transit/narrative` |
| `experience.py` | `/experience/bootstrap`, `/experience/signature-delta`, `/experience/daily` |
| `impact.py` | `/impact/active` (PRD P0-3 dashboard) |
| `geocode.py` | `/geocode` |
| `personalize.py` | `/personalize` — aggregates bazi+western+fusion+geocode |
| `chronometry.py` | `/chronometry/resolve` (beta) |
| `superglue.py` | Legacy `/api/profile`, `/api/daily`, `/api/profile/{user_id}/chart`, … (ElevenLabs/Bazodiac proxy); v1 twins at plain `/v1/profile` etc. — NOT `/v1/api/*`, and no path contains "superglue" |
| `validate.py` | `/validate` |
| `chart.py` | `/chart` — legacy-only, no `/v1` alias |
| `admin.py` | `/v1`-only, `protected=False` — NOT behind `require_api_key`; has its own `X-Admin-Token` gate and feature flag `key_issuance` (`FUFIRE_ENABLE_KEY_ISSUANCE`, default off; 503 when unconfigured) |
| `match.py` | `/v1/match/bazi-hehun` — `/v1`-only per DECISION-001 (`docs/plans/2026-07-02-bazi-hehun.md`) |
| `zwds.py` | `/v1`-only + feature flag `zwds` (`FUFIRE_ENABLE_ZWDS`, default off): `POST /v1/calculate/zwds`, `GET /v1/metadata/zwds/rulesets/{ruleset_id}`. Their absence from `openapi.json` is intentional (flag off), not drift |
| `astronomy.py` | `POST /v2/astronomy/lunar-state` — the ONLY `/v2` mount, deliberately `/v2`-only: its UTC-root and corrected eight-phase semantics must NEVER get a `/v1` or legacy alias (`docs/api/03_lunar_state_v2.md`) |
| `info.py` | `/`, `/health`, `/ready`, `/build`, `/api`, `/info/wuxing-mapping` — `protected=False`, no API key even under `/v1` |
| `webhooks.py` | `/internal/api/webhooks/*`, `include_in_schema=False`, HMAC-verified |
| `shared.py` | Shared Pydantic models/deps (not a router) |

**Endpoint-change checklist** (full version: `docs/adding-an-endpoint.md`): registry `Mount(...)` row → `python scripts/export_openapi.py` → `python tests/golden/regen_route_table.py` (`test_app_composition.py` diffs `tests/golden/route_table.json`) → `@limiter.limit(...)` on the route (`test_rate_limit_coverage.py` fails protected routes without one; there is **no default limit** — undecorated = unlimited) → responses use the frozen ErrorEnvelope `{"error", "message", "detail"}` (codes in `docs/ERROR_CODES.md`) → survives `redocly lint` + TS codegen (CI codegen job).

### BAFE Subpackage (Contract-First Core)

`bazi_engine/bafe/` implements JSON Schema Draft-07 validation for `/validate`:
- `service.py` — Main `validate_request()` orchestrator
- `mapping.py` — Branch coordinate conventions (Layer 2, stdlib-only)
- `refdata.py` — Reference data policy checks
- `time_model.py` — Time evaluation
- `ruleset_loader.py` — Loads the **packaged** ruleset copy from `bazi_engine/resources/rulesets/` via `resource_loader` (Layer 2); `spec/rulesets/standard_bazi_2026.json` is the repo-side mirror
- `canonical_json.py` — Deterministic config fingerprints
- `kernel.py` — Soft branch weights
- `harmonics.py` — Harmonic analysis utilities
- `errors.py` — Contract-bound error codes and issue factory

### ZWDS Subpackage (`bazi_engine/zwds/`)

Independent Zi Wei Dou Shu engine (`__zwds_engine_version__ = "0.1.0-core-seed"`): `engine.py` orchestrator plus palace/bureau/stars/transformations/decadal/seed/calendar_provider/ruleset_repository/validation/trace modules. Data-driven from the immutable, hash-locked ruleset in `bazi_engine/data/zwds/rulesets/` — ruleset edits change chart output and break hash locks. Tests: `tests/zwds/` (22 files, 11 golden charts, lunisolar boundary corpus); the full-chart path is `swieph`-marked.

## Critical Domain Concepts

### Year Boundary (LiChun)
- Year changes at 315° solar longitude (~Feb 3-5), not Jan 1
- Birth before LiChun uses previous year's pillar
- Timezone-sensitive: Berlin LiChun ≠ Beijing LiChun

### Day Pillar Calibration
```python
# Pre-FBP-02-001 source of truth (kept as a Phase-1 baseline reference):
DAY_OFFSET = 49  # in constants.py

# FBP-02-001 (Phase 2) — the canonical engine path now derives the
# offset from the ruleset's day_cycle_anchor:
from bazi_engine.bazi_rules import day_offset_from_ruleset, load_default_ruleset
calculated_offset = day_offset_from_ruleset(load_default_ruleset())
# yields 49 for the shipped standard_bazi_2026 ruleset; will change
# automatically when FBP-02-002 verifies/corrects the anchor.
```
Formula: `sexagenary_day_index = (JDN + 49) % 60`

### DST Handling
- `LocalTimeError` raised for nonexistent/ambiguous times when `strict_local_time=True`
- Use `fold=0`/`fold=1` for ambiguous fall-back times
- Set `strict_local_time=False` for lenient mode

### Swiss Ephemeris
- Required files (all four): sepl_18.se1, semo_18.se1, seas_18.se1, seplm06.se1
- Default path when `SE_EPHE_PATH` is unset: `~/.cache/bazi_engine/swisseph` (`/usr/local/share/swisseph` is only the Docker image's baked ENV — files placed there locally without exporting `SE_EPHE_PATH` do nothing)
- Supply-chain locked by `ephemeris.lock.json` (pinned upstream git commit + per-file size + SHA256 + lock_id); fetch/verify with `scripts/fetch_ephemeris.py`. Copies of the lock also ship inside the package (`bazi_engine/resources/`) and image. Updating ephemeris data means regenerating the lock everywhere — hand-editing one copy fails build-time validation
- A local `503 ephemeris_unavailable` means missing files, not a bug (runbook: `docs/runbooks/ephemeris-local-setup.md`; contract mock server without ephemeris: `python tests/mock_server.py --port 8081`)
- Transit calculations use `TTLCache` (1-hour TTL) — `ADR-1`. `ensure_ephemeris_files` is deliberately NOT `lru_cache`d (hardening, FQ-ATT-01); the `cache_clear` stub exists for compat — don't "fix" either

### Auth, Config Guard & Rate Limiting
- The V1 API-key FastAPI dependency `require_api_key` lives in **top-level `bazi_engine/auth.py`** (reads `FUFIRE_API_KEYS` comma-list; `FUFIRE_REQUIRE_API_KEYS=true` forces fail-closed; empty env = dev-mode bypass). **`bazi_engine/services/auth.py` is ONLY ElevenLabs webhook HMAC verification** — the exact inverse of what the names suggest.
- `app.py` calls `config_guard.assert_runtime_config()` at import time. `FUFIRE_ENV` must be set whenever `FUFIRE_REQUIRE_EXPLICIT_ENV=1` (always true in the Docker image). `FUFIRE_ENV ∈ {production, prod, staging}` additionally requires: `FUFIRE_REQUIRE_API_KEYS=true`, an explicit non-local `CORS_ALLOWED_ORIGINS` allowlist, a positive `FUFIRE_REPLICA_COUNT`, Redis (`REDIS_URL`/`REDIS_PRIVATE_URL`) when replicas > 1 or `FUFIRE_REQUIRE_REDIS`, `EPHEMERIS_MODE=SWIEPH`, and the release feature policy (`FUFIRE_ENABLE_KEY_ISSUANCE` forbidden; `FUFIRE_ENABLE_ZWDS` needs `FUFIRE_ZWDS_SIGNOFF_ID`). Missing any ⇒ crash at startup; on Railway that means ≤ 3 restarts (`restartPolicyMaxRetries = 3`) then a dead deploy — read railway logs for the `RuntimeError` text.
- Rate limiting (`limiter.py`): storage resolves `REDIS_URL` then `REDIS_PRIVATE_URL` (Railway's Redis plugin exposes the latter). In-memory fallback only when Redis is not required; a required-but-missing Redis never silently falls back — the limiter reports degraded and `/ready` flips to 503. V1 routes rate-keyed by API key; legacy routes by remote IP.
- Feature flags: `features.py` `FEATURE_MATRIX` (`key_issuance`, `zwds`) — resolved from env per request, not cached.

## Testing

CI runs on Python 3.10–3.12, installs with `uv sync --frozen --extra dev`, fetches locked ephemeris to `/tmp/ephe` (GitHub cache keyed on `ephemeris.lock.json`), and runs pytest with `SE_EPHE_PATH=/tmp/ephe` — i.e. **CI runs real SWIEPH**.

**Local asymmetry — MOSEPH fallback, not skips:** without SE1 files, `tests/conftest.py` sets `EPHEMERIS_MODE=MOSEPH` and the bulk of the suite runs green on the built-in Moshier ephemeris (subtly different numbers). Only `@pytest.mark.swieph` tests skip. A swieph-marked test you never ran locally can fail for the first time in CI — use the `fetch_ephemeris.py` recipe above for a CI-equivalent run.

**Conventions (2026-07-08, from the WS-A PII-leak retro):**
- Claims about HTTP response bodies (PII scrubbing, error envelopes, field presence/absence)
  MUST be asserted at the real boundary via `TestClient` on `resp.text`/`resp.json()`.
  Unit-level assertions on the exception object (`str(excinfo.value)`) do NOT count as
  boundary proof — that exact gap let a live PII leak survive two "product-wide" fixes
  (see `tests/test_dst_pii_http.py` for the pattern).
- Tests must never depend on local git ref names (`git show main:...`) — PR CI checkouts
  are detached/shallow without a `main` ref. Use a ref fallback chain plus a visible
  `pytest.skip`, as in `tests/test_match_service_boundary.py`.

Mechanics:
- Markers: `swieph` (registered dynamically in conftest — deliberately NOT duplicated in pyproject; add it to any SE1-dependent test) and `integration` (needs a reachable LeanDeep service; auto-skips).
- Autouse conftest fixtures reset transit caches and the in-memory rate limiter between tests — don't re-add per-test resets or worry about TestClient tests tripping limits.
- Snapshots: `tests/snapshots/{moseph,swieph}/` chosen by active backend. Never hand-edit snapshot JSON. **Regeneration procedure (owner decision E7, 2026-10-16):** regenerate *both* backends locally against the SHA-verified ephemeris, then minimise the diff so only material changes remain (a raw regeneration rewrites every float in the 8th–10th decimal and produces a ~1 200-line diff nobody can review):
  ```bash
  python scripts/fetch_ephemeris.py --destination /tmp/ephe
  SE_EPHE_PATH=/tmp/ephe UPDATE_SNAPSHOTS=1 pytest -q tests/test_snapshot_stability.py tests/test_snapshot_math_endpoints.py
  python scripts/minimize_snapshot_diff.py --backend swieph --report
  env -u SE_EPHE_PATH UPDATE_SNAPSHOTS=1 pytest -q tests/test_snapshot_stability.py tests/test_snapshot_math_endpoints.py
  python scripts/minimize_snapshot_diff.py --backend moseph --report
  SE_EPHE_PATH=/tmp/ephe pytest -q tests/test_snapshot_stability.py tests/test_snapshot_math_endpoints.py   # verify, no update
  ```
  `--report` lists the JSON paths that still differ — every one of them must be explained by the change (and the engine build label bump). The manual `update-swieph-snapshots.yml` workflow (review-only patch artifact) remains available as an alternative for the swieph baselines.
- TLST reference corpus: `tests/fixtures/tlst_reference_corpus_v1.json` is generated from Swiss Ephemeris (`swe.time_equ`, `swe.lmt_to_lat`) by `scripts/gen_tlst_reference_corpus.py`; CI lint runs its `--check`. Add cases to the script's `CASES` table and regenerate — never hand-edit the fixture.
- Scale: ~183 top-level test files + 22 in `tests/zwds/`. Dedicated suites beyond the basics: match (14 files + sentinel payloads), dayun (13), impact, ephemeris supply-chain governance (`test_ephemeris_*`), release/toolchain gates (`test_release_*`, `test_toolchain_pinning.py`, `test_requirements_lock.py`, `test_sbom_validation.py`), lunar state (USNO reference fixture), natal, golden vectors, `test_import_hierarchy.py`, `test_openapi_contract.py`, `test_app_composition.py` (route-table golden).

## OpenAPI Contract

**`spec/openapi/openapi.json`** is the source of truth.
- CI checks drift: `python scripts/export_openapi.py --check`; regenerate after any endpoint/model change
- Changes must ALSO pass the CI codegen job: `redocly lint` + TypeScript-fetch client generation + `tsc` compile — an enum or schema the generator rejects fails CI despite a clean drift check
- `bazi_engine.__version__` is the single source for version strings
- **Endpoints are frozen** — do not change paths or response structures (downstream services depend on them)
- ZWDS routes are intentionally absent while their feature flag is off — do not "fix" this as drift

## Deployment Runtime

- `start.py` (repo root) is the Docker `CMD` entrypoint; `railway.toml`'s `startCommand` overrides it with an equivalent inline uvicorn call — startup changes (workers, log level, port) must be applied to **both**.
- 3-stage Dockerfile: **ephe** (fetch + SHA-verify ephemeris) → **builder** (compiles pyswisseph from sdist, installs `uv export --frozen --require-hashes` deps, builds the wheel, gates it with `verify_distribution.py`) → **runtime** (source-free, non-root uid 10001: only site-packages, ephemeris, the lock, and start.py). There is no repo checkout in the image — anything needed at runtime must be package-data under `bazi_engine/` and pass `verify_distribution.py`.
- The top-level `config/` directory is Plumbline SDLC gate tooling, **not** runtime/deployment configuration — nothing in `bazi_engine` or the Docker build reads it.

## Gotchas

1. **Import hierarchy:** enforced by `test_import_hierarchy.py` **only for modules registered in its LAYERS dict** — register new modules there or the contract is silently unchecked. `zwds` ↔ `bazi`/`western`/`fusion`/`impact` imports are banned outright (FORBIDDEN_EDGES); cross-engine code goes in `synergy/` only
2. **Immutability:** Never remove `frozen=True` from dataclasses
3. **DAY_OFFSET:** Changing breaks day pillar accuracy for all historical dates
4. **Router architecture:** Business logic belongs in domain modules, not in `routers/` or `app.py`
5. **DST:** Always handle `LocalTimeError` in API endpoints
6. **Ephemeris:** local runs without SE1 files fall back to MOSEPH (different numbers, not skips); Docker verifies SHA256s at build — upstream file changes fail the build
7. **Endpoint changes:** run the full checklist (OpenAPI export + route-table golden regen + limiter decorator + ErrorEnvelope + redocly/TS-codegen survival) — the drift check alone is not enough
8. **Experience router:** `routers/experience.py` orchestrates `bazi`, `western`, `fusion`, and `services/soulprint.py` — changes cascade widely
9. **Two `auth` modules, inverted from what the names suggest:** the V1 API-key dependency is in top-level `bazi_engine/auth.py`; `bazi_engine/services/auth.py` is webhook-HMAC-only
10. **Daily v2 endpoints:** `services/daily_{eastern,western,fusion}.py` are composed by `services/daily_templates.py` — the template layer owns the public response shape
11. **Geocode confidence/candidates:** `services/geocoding.py` is the single source of truth; `routers/geocode.py` and `routers/personalize.py` both call into it — extend there
12. **Two lunar implementations coexist on purpose:** legacy `phases.lunar_phase` (historical buckets) vs `lunar_state.py` (canonical, V2 contract). Do not deduplicate them or route V2 astronomy through the legacy path
13. **`spec/` is not runtime:** the deployed engine reads `bazi_engine/resources/` — a spec-only edit ships nothing
14. **Dependency/toolchain bumps:** regenerate `uv.lock` + `requirements.lock`; toolchain pins need lockstep pyproject + Dockerfile + ci.yml edits (`assert_toolchain_versions.py` is the contract)
