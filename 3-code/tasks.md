# Tasks — FuFirE Implementation Plan

## Status Legend

| Symbol | Meaning |
|--------|---------|
| Todo | Ready to start |
| In Progress | Currently being worked on |
| Done | Completed |
| Blocked | Waiting on dependency |
| Cancelled | No longer needed |

## Priority Legend

| Priority | Meaning |
|----------|---------|
| P0 | Must-have — blocks launch |
| P1 | Should-have — quality improvement |
| P2 | Could-have — future differentiation |

---

## Phase 1 — P0: Correctness & Consistency ✅ COMPLETE

| ID | Task | Priority | Status | Req | Dependencies | Updated | Notes |
|----|------|----------|--------|-----|--------------|---------|-------|
| TASK-outer-planet-transits | Add Uranus/Neptune/Pluto to TRANSIT_PLANETS and PLANET_WEIGHTS | P0 | Done | REQ-F-outer-planet-transits | - | 2026-03-28 | |
| TASK-outer-planet-golden-tests | Golden vector tests for transit outer planets | P0 | Done | REQ-F-outer-planet-transits | TASK-outer-planet-transits | 2026-03-28 | |
| TASK-differentiated-orbs | Per-planet base orb system + aspect factor in aspects.py | P0 | Done | REQ-F-differentiated-orbs | - | 2026-03-28 | |
| TASK-provenance-orb-table | Update WUXING_PARAMETER_SET with new orb table + weights | P0 | Done | REQ-F-differentiated-orbs | TASK-differentiated-orbs | 2026-03-28 | |
| TASK-orb-tests | Aspect orb tests: Sun-Moon wide, Chiron-Pluto narrow, formula | P0 | Done | REQ-F-differentiated-orbs | TASK-differentiated-orbs | 2026-03-28 | |
| TASK-precise-jieqi-daily | Replace month approximation with Swiss Ephemeris solar longitude | P0 | Done | REQ-F-precise-jieqi-daily | - | 2026-03-28 | |
| TASK-jieqi-boundary-tests | 18 Jieqi boundary tests for daily eastern | P0 | Done | REQ-F-precise-jieqi-daily | TASK-precise-jieqi-daily | 2026-03-28 | |
| TASK-remove-null-deltas-decision | Decision: Remove delta fields + dominance_shift from schema | P0 | Done | REQ-F-remove-null-deltas | - | 2026-03-28 | Option A chosen |
| TASK-remove-null-deltas-impl | Remove delta from TRANSIT_STATE, bump to v2 | P0 | Done | REQ-F-remove-null-deltas | TASK-remove-null-deltas-decision | 2026-03-28 | |

---

## Phase 2 — P1: Billing Infrastructure & Transparency ✅ COMPLETE

| ID | Task | Priority | Status | Req | Dependencies | Updated | Notes |
|----|------|----------|--------|-----|--------------|---------|-------|
| TASK-redis-storage-backend | Redis storage backend for rate limiting | P1 | Done | REQ-F-persistent-rate-limits | - | 2026-03-28 | |
| TASK-health-rate-limiter | /health reports rate_limiter dependency status | P1 | Done | REQ-F-persistent-rate-limits | TASK-redis-storage-backend | 2026-03-28 | |
| TASK-provenance-soulprint | Add soulprint weights + Wu-Xing sector mapping to provenance | P1 | Done | REQ-F-provenance-soulprint-weights | - | 2026-03-28 | |
| TASK-openapi-regen-phase2 | Regenerate OpenAPI spec, --check confirms up-to-date | P0 | Done | - | - | 2026-03-28 | |

---

### Engine

| ID | Task | Priority | Status | Req | Dependencies | Updated | Notes |
|----|------|----------|--------|-----|--------------|---------|-------|
| TASK-impact-data-model | Define Pydantic models: ActivePlanet, BaziResonance, ImpactResponse, ImpactRequest | P0 | Done | PRD-P0-3 | - | 2026-04-13 | |
| TASK-impact-natal-transit-calc | Implement natal-vs-transit aspect matching (orb ≤ 8°, strength classification) | P0 | Done | PRD-P0-3 | TASK-impact-data-model | 2026-04-13 | |
| TASK-impact-bazi-resonance | Implement BaZi resonance per planet (element, type, intensity from day master) | P0 | Done | PRD-P0-3 | TASK-impact-data-model | 2026-04-13 | |
| TASK-impact-harmony-index | Compute harmony_index, day_mode, intensity, drivers from Wu-Xing cosine | P0 | Done | PRD-P0-3 | TASK-impact-natal-transit-calc, TASK-impact-bazi-resonance | 2026-04-13 | |
| TASK-aspect-weighted-wuxing | Aspect tightness amplifies Wu-Xing element weight in fusion vector | P1 | Done | - | TASK-impact-harmony-index | 2026-04-13 | Phase 4 |
| TASK-house-based-weighting | Angular/cadent house multipliers for planet weights | P1 | Done | - | - | 2026-04-13 | Phase 4 |
| TASK-minor-aspects | Add quincunx (150°) and semi-sextile (30°) to aspect calculations | P1 | Done | - | - | 2026-04-13 | Phase 4 |
| TASK-planetary-dignities | Implement domicile, detriment, exaltation, fall per planet/sign | P2 | Done | - | - | 2026-04-14 | Phase 5 |
| TASK-decanates-terms | Add decanate and term subdivisions for planet positions | P2 | Done | - | - | 2026-05-01 | Phase 5 |
| TASK-fixed-star-conjunctions | Fixed star conjunction detection against natal/transit positions | P2 | Done | - | - | 2026-05-19 | Phase 5 |
| TASK-ke-cycle-wuxing | Add Ke-cycle (相剋) destructive relationships to Wu-Xing fusion | P2 | Done | - | - | 2026-05-19 | Phase 5 |

### API

| ID | Task | Priority | Status | Req | Dependencies | Updated | Notes |
|----|------|----------|--------|-----|--------------|---------|-------|
| TASK-impact-active-router | Create POST /impact/active router with rate limiting and auth | P0 | Done | PRD-P0-3 | TASK-impact-harmony-index, TASK-impact-space-weather | 2026-04-13 | |
| TASK-impact-active-tests | Golden vector tests + integration tests for /impact/active | P0 | Done | PRD-P0-3 | TASK-impact-active-router | 2026-04-13 | |
| TASK-experience-daily-v2 | Extend POST /experience/daily with include=["impact"] (backwards compatible) | P0 | Done | PRD-P0-4 | TASK-impact-active-router | 2026-04-13 | |
| TASK-experience-daily-v2-tests | Tests for v2: with/without include param, evidence traceability | P0 | Done | PRD-P0-4 | TASK-experience-daily-v2 | 2026-04-13 | |
| TASK-openapi-regen-phase3 | Regenerate OpenAPI spec, verify drift check | P0 | Done | - | TASK-experience-daily-v2 | 2026-04-13 | |

### Services

| ID | Task | Priority | Status | Req | Dependencies | Updated | Notes |
|----|------|----------|--------|-----|--------------|---------|-------|
| TASK-impact-space-weather | Integrate NOAA space weather fetch with partial=true fallback on 503 | P0 | Done | PRD-P0-3 | - | 2026-04-13 | |
| TASK-daily-template-variants | Expand daily horoscope templates (per relation × jieqi × weekday) | P1 | Done | - | - | 2026-04-14 | Phase 4 |

### Deploy & Operations

| ID | Task | Priority | Status | Req | Dependencies | Updated | Notes |
|----|------|----------|--------|-----|--------------|---------|-------|
| TASK-phase3-manual-testing | Create runbook for /impact/active and /experience/daily v2 testing | P0 | Done | - | TASK-openapi-regen-phase3 | 2026-04-13 | |
| TASK-phase4-manual-testing | Update runbook for enhanced fusion validation | P1 | Done | - | TASK-minor-aspects | 2026-04-14 | Phase 4 |
| TASK-phase5-manual-testing | Update runbook for enterprise features | P2 | Todo | - | TASK-ke-cycle-wuxing | 2026-04-13 | Phase 5 |

---

## Execution Plan

### Phase 1: Correctness & Consistency ✅ COMPLETE (2026-03-28)

**Capabilities delivered:**
- Outer planet transits (Uranus, Neptune, Pluto)
- Differentiated per-planet orb system
- Precise Jieqi daily calculations via Swiss Ephemeris
- Clean transit state schema (v2, no null deltas)

**Tasks:** TASK-outer-planet-transits → TASK-outer-planet-golden-tests → TASK-differentiated-orbs → TASK-provenance-orb-table → TASK-orb-tests → TASK-precise-jieqi-daily → TASK-jieqi-boundary-tests → TASK-remove-null-deltas-decision → TASK-remove-null-deltas-impl

### Phase 2: Billing Infrastructure & Transparency ✅ COMPLETE (2026-03-28)

**Capabilities delivered:**
- Persistent rate limiting via Redis (with in-memory fallback)
- Health endpoint reports rate limiter dependency
- Full provenance chain including soulprint weights

**Tasks:** TASK-redis-storage-backend → TASK-health-rate-limiter → TASK-provenance-soulprint → TASK-openapi-regen-phase2

### Phase 3: Impact & Daily v2 API

**Capabilities delivered:**
- `POST /impact/active` — natal-relative planet impacts with BaZi resonance, harmony index, space weather (PRD P0-3)
- `POST /experience/daily` v2 with `include=impact` — single API call for Daily Chart (PRD P0-4)
- Frontend can load all Daily Chart data in one request (US-8, US-9)

**Tasks:**
1. TASK-impact-data-model
2. TASK-impact-natal-transit-calc
3. TASK-impact-bazi-resonance
4. TASK-impact-harmony-index
5. TASK-impact-space-weather
6. TASK-impact-active-router
7. TASK-impact-active-tests
8. TASK-experience-daily-v2
9. TASK-experience-daily-v2-tests
10. TASK-openapi-regen-phase3
11. TASK-phase3-manual-testing

### Phase 4: Enhanced Fusion Quality

**Capabilities delivered:**
- Aspect-weighted Wu-Xing contributions (tight aspects amplify element weight)
- House-based planet weighting (angular ×1.3, cadent ×0.8)
- Minor aspects (quincunx 150°, semi-sextile 30°)
- Expanded daily horoscope template variants

**Tasks:**
1. TASK-aspect-weighted-wuxing
2. TASK-house-based-weighting
3. TASK-minor-aspects
4. TASK-daily-template-variants
5. TASK-phase4-manual-testing

### Phase 5: Enterprise Differentiation

**Capabilities delivered:**
- Planetary dignities (domicile, detriment, exaltation, fall)
- Decanates and terms
- Fixed star conjunctions
- Ke-cycle (相剋) analysis in Wu-Xing fusion

**Tasks:**
1. TASK-planetary-dignities
2. TASK-decanates-terms
3. TASK-fixed-star-conjunctions
4. TASK-ke-cycle-wuxing
5. TASK-phase5-manual-testing

---

## Phase BAZI-PRECISION-V2 — High Precision BaZi/Fusion Update

**Status:** Phase 0 in progress (2026-05-14). High-risk SDLC change —
phased, test-first, review-gated. Default-behavior changes blocked
until migration report is accepted (see
`docs/release/bazi_precision_release_gate.md`).

**Authoritative documents:**
- Pre-audit baseline: `docs/audits/fufire_bazi_precision_pre_audit.md`
- Deviation register: `docs/precision/deviations.md`
- Release & stop-gate policy: `docs/release/bazi_precision_release_gate.md`
- Golden case schema: `spec/golden/bazi_case.schema.json`

**Compatibility:** `/v1` and `/v1/*` are **frozen**. New semantics ship
opt-in or under `/v2`. CIVIL, LMT, and TLST are three distinct time
standards and must never be aliased.

| ID | Task | Priority | Status | Req | Dependencies | Updated | Notes |
|----|------|----------|--------|-----|--------------|---------|-------|
| FBP-00-001 | Store FuFirE BaZi precision pre-audit as baseline | P0 | Done | REQ-BAZI-PRECISION | - | 2026-05-14 | Docs only; `docs/audits/fufire_bazi_precision_pre_audit.md`. |
| FBP-00-002 | Append SDLC implementation plan and phase gates | P0 | Done | REQ-BAZI-PRECISION | FBP-00-001 | 2026-05-14 | This block + `docs/release/bazi_precision_release_gate.md`. |
| FBP-00-003 | Add Golden Case schema with source_type labels | P0 | Done | REQ-GOLDEN-ORACLE | FBP-00-001 | 2026-05-14 | `spec/golden/bazi_case.schema.json`; ENGINE_BASELINE vs EXTERNAL_ORACLE vs DOMAIN_REVIEW_REQUIRED. |
| FBP-00-004 | Export v1 engine baseline snapshots | P0 | Done | REQ-V1-COMPAT | FBP-00-003 | 2026-05-17 | `scripts/export_bazi_baseline.py` + `tests/fixtures/bazi_baseline_v1.json`. Regenerated under SWIEPH (was MOSEPH); pillar values unchanged. |
| FBP-00-005 | Separate engine baseline vs external oracle in goldens | P0 | Done | REQ-GOLDEN-ORACLE | FBP-00-003 | 2026-05-17 | `tests/golden_reference_cases.py` + `tests/test_golden.py` updated; split_by_source_type + per-type test policies in place. |
| FBP-00-006 | Introduce deviation register | P0 | Done | REQ-BAZI-PRECISION | FBP-00-001 | 2026-05-14 | `docs/precision/deviations.md`; 7 seeded entries. |
| FBP-00-007 | Document release- and stop-gates | P0 | Done | REQ-RELEASE-GATE | FBP-00-001 | 2026-05-14 | `docs/release/bazi_precision_release_gate.md`. |
| FBP-00-008 | Rewrite `test_day_offset_reference_examples` | P0 | Done | REQ-DAY-ANCHOR | FBP-00-006 | 2026-05-14 | `tests/test_invariants.py`; no literal `49`, reads ruleset anchor instead. |
| FBP-01-001 | Add TLST as explicit time standard without v1 default change | P0 | Done | REQ-TIME-POLICY | FBP-00-004 | 2026-05-14 | Router-clamp (Option 2): TLST accepted; engine uses LMT semantics; trace records `time_standard_requested`/`time_standard_used`. |
| FBP-01-002 | Add `EffectiveTimeContext` for CIVIL/LMT/TLST | P0 | Done | REQ-TIME-POLICY | FBP-01-001 | 2026-05-14 | `bazi_engine/time_context.py`; TLST is `tlst_hours` + `date_rollover`, not a tzinfo (covers FBP-01-006). |
| FBP-01-003 | Make `/calculate/tst` consistent with core TLST | P0 | Done | REQ-TLST-CONSISTENCY | FBP-01-002 | 2026-05-14 | Endpoint delegates to `compute_effective_time_context`; consistency test pins agreement. |
| FBP-01-004 | Keep `to_chart_local()` backward compatible | P0 | Done | REQ-TIME-POLICY | FBP-01-002 | 2026-05-14 | TLST in `to_chart_local` falls through to CIVIL (router clamp prevents the path in practice); guard test pinned. |
| FBP-01-005 | Confirm `solar_time.py` purity | P0 | Done | REQ-TIME-POLICY | FBP-01-002 | 2026-05-14 | `test_import_hierarchy::test_solar_time_has_no_internal_imports` green; `time_context.py` imports `solar_time` (Level 2 → Level 2 is allowed). |
| FBP-02-001 | Introduce ruleset adapter for core BaZi | P0 | Done | REQ-RULESET-SOT | FBP-01-002 | 2026-05-14 | `bazi_engine/bazi_rules.py` — `day_offset_from_ruleset()` derives the day-cycle offset from `day_cycle_anchor` instead of the hardcoded `DAY_OFFSET` constant. Value-equivalent today (yields 49 from the shipped anchor); `test_bazi_rules.py` pins the equivalence; v1 regression suite green. Other ruleset-driven knobs (year/month boundaries, zi policy) are FBP-02-004 / FBP-02-006. |
| FBP-02-002 | Replace hardcoded day offset truth with ruleset anchor policy | P0 | Todo | REQ-DAY-ANCHOR | FBP-02-001 | 2026-05-14 | Human review required (DEV-2026-004). |
| FBP-02-003 | Enforce anchor verification gate | P0 | Todo | REQ-DAY-ANCHOR | FBP-02-002 | 2026-05-14 | Unverified blocks v2 default. |
| FBP-02-004 | Implement effective-time Zi-day boundary | P0 | Todo | REQ-ZI-BOUNDARY | FBP-02-002 | 2026-05-14 | Boundary tests required for 22:59/23:00/00:59/01:00 × CIVIL/LMT/TLST. |
| FBP-02-005 | Route hour branch through effective time policy | P0 | Todo | REQ-HOUR-PILLAR | FBP-02-004 | 2026-05-14 | TLST half-open bins; aligns with BAFE. |
| FBP-02-006 | Clarify or deprecate `month_boundary_scheme` | P1 | Done | REQ-MONTH-BOUNDARY | FBP-02-001 | 2026-05-17 | Deprecated: field kept for v1 compat; non-default emits DeprecationWarning; no effect on pillars; removal in /v2. |
| FBP-02-007 | Add LiChun / Jieqi external golden cases | P0 | Todo | REQ-GOLDEN-ORACLE | FBP-00-005 | 2026-05-14 | Each boundary case has external citation. |
| FBP-02-008 | Derive Day Master with anchor evidence | P1 | Todo | REQ-HOUR-PILLAR | FBP-02-005 | 2026-05-14 | Day Master = Day Pillar Stem; trace must show anchor. |
| FBP-03-001 | Add typed derivation trace | P0 | Done | REQ-TRACEABILITY | FBP-01-002 | 2026-05-17 | Pydantic models (BaziDerivationTrace, sub-models) replace Dict[str,Any]. hour_branch_time_policy Optional[str]=None pending FBP-02-005. Snapshots regenerated. |
| FBP-03-002 | Fix `true_solar_time_used` semantics (DEV-2026-001) | P0 | Done | REQ-TRACEABILITY | FBP-03-001 | 2026-05-17 | true_solar_time_used now TLST-only; lmt_used bool added. DEV-2026-001 closed. |
| FBP-03-003 | Add `civil_local`, `utc`, `lmt`, `tlst_hours`, `eot`, `tz_offset`, `effective_standard` to trace | P0 | Done | REQ-TRACEABILITY | FBP-03-001 | 2026-05-18 | TimeResolutionTrace sub-model added; always computed for all 3 standards; 8 new tests; snapshots+OpenAPI regenerated. |
| FBP-03-004 | Add provenance model IDs | P0 | Done | REQ-PROVENANCE | FBP-03-001 | 2026-05-18 | ProvenanceIds sub-model added; 7 new tests; DEV-2026-007 partially closed (vector_model_id surfaced). |
| FBP-03-005 | Extract `ErrorEnvelope.schema.json` (DEV-2026-006) | P0 | Done | REQ-API-V2 | FBP-03-001 | 2026-05-18 | Inline → file under `spec/schemas/`. |
| FBP-03-006 | Plan RFC 9457 Problem Details for /v2 | P1 | Todo | REQ-API-V2 | FBP-03-005 | 2026-05-14 | v1 ErrorEnvelope tests stay green. |
| FBP-04-001 | Separate raw, weighted, L2-normalized Wu-Xing vectors | P0 | Todo | REQ-FUSION-VERSIONING | FBP-03-004 | 2026-05-14 | No semantic mixing. |
| FBP-04-002 | Add Vector / Normalization Model IDs | P0 | Todo | REQ-FUSION-VERSIONING | FBP-04-001 | 2026-05-14 | Resolves DEV-2026-007. |
| FBP-04-003 | Unify hidden-stem source of truth | P0 | Todo | REQ-HIDDEN-STEM-LEDGER | FBP-04-001 | 2026-05-14 | Drift check between core and BAFE. |
| FBP-04-004 | Exclude Ten Gods / DMS from mass vector | P0 | Todo | REQ-FUSION-VERSIONING | FBP-04-001 | 2026-05-14 | Vector contamination test. |
| FBP-04-005 | Run Fusion v1/v2 in parallel | P0 | Todo | REQ-FUSION-MIGRATION | FBP-04-002 | 2026-05-14 | No default switch before report. |
| FBP-04-006 | Build migration / delta report | P0 | Todo | REQ-FUSION-MIGRATION | FBP-04-005 | 2026-05-14 | `docs/migration/fusion_score_deltas.md`. |
| FBP-04-007 | Recalibrate only after golden tests pass | P1 | Todo | REQ-FUSION-MIGRATION | FBP-04-006 | 2026-05-14 | No new baseline without delta distribution. |
| FBP-05-001 | Add Classical Interpretation package skeleton | P1 | Todo | REQ-CLASSICAL-LAYER | FBP-02-005 | 2026-05-14 | Not vector input. |
| FBP-05-002 | Add Hidden Stem Ledger from ruleset | P1 | Todo | REQ-HIDDEN-STEM-LEDGER | FBP-05-001 | 2026-05-14 | Source ledger. |
| FBP-05-003 | Add Ten Gods as separate interpretation feature | P2 | Todo | REQ-TEN-GODS | FBP-05-002 | 2026-05-14 | Must not change vector. |
| FBP-05-004 | Add Day Master Strength as separate versioned feature | P2 | Todo | REQ-DMS | FBP-05-002 | 2026-05-14 | Domain review required. |
| FBP-05-005 | Specify Branch/Stem interactions | P2 | Todo | REQ-CLASSICAL-LAYER | FBP-05-002 | 2026-05-14 | Separate relations list. |
| FBP-05-006 | Classical API surface (v2 / include=) | P1 | Todo | REQ-API-V2 | FBP-05-002 | 2026-05-14 | No v1 breaking change. |
| FBP-05-007 | Narrative stays read-only | P1 | Todo | REQ-CLASSICAL-LAYER | FBP-05-006 | 2026-05-14 | Reads classical features; never modifies core/fusion. |
| FBP-06-001 | Add `/v2` bazi/fusion contracts | P0 | Todo | REQ-API-V2 | FBP-04-006, FBP-03-006 | 2026-05-14 | v1 frozen; only after migration gate. |
| FBP-07-001 | Cleanup duplicate constants, obsolete snapshots, docs | P0 | Todo | REQ-CLEANUP | FBP-06-001 | 2026-05-14 | Review required. |
| FBP-07-002 | Final code, domain, contract review | P0 | Todo | REQ-RELEASE-GATE | FBP-07-001 | 2026-05-14 | Release blocker. |
| FBP-TST-000 | TLST reference corpus + strict-xfail tripwires (DEV-2026-009…012) | P0 | Done | REQ-TLST-CONSISTENCY | FBP-01-002 | 2026-10-15 | `scripts/gen_tlst_reference_corpus.py`, `tests/fixtures/tlst_reference_corpus_v1.json`, `tests/test_tlst_reference_corpus.py` (178 green / 44 xfail-strict). Plan: `docs/plans/2026-10-15-true-solar-time-remediation.md`. |
| FBP-TST-001 | Remove/fix `fusion.true_solar_time_from_civil` (DEV-2026-012) | P2 | Done | REQ-TLST-CONSISTENCY | FBP-TST-000 | 2026-10-16 | Helper removed (E4); no wire impact. |
| FBP-TST-002 | Fold-faithful `EffectiveTimeContext` (DEV-2026-010) | P1 | Done | REQ-TIME-POLICY | FBP-TST-000 | 2026-10-16 | `compute_effective_time_context_from_instant(civil_local, lon)` + `fold=` kwarg; all callers pass the resolved aware instant. |
| FBP-TST-003 | TLST on UTC axis in `time_context.py` + GT6 trace/day consistency (DEV-2026-009) | P0 | Done | REQ-TLST-CONSISTENCY | FBP-TST-002 | 2026-10-16 | E1 approved by owner 2026-10-16. **Wire change** shipped: `tlst_hours`, `/calculate/tst`, chronometry `true_solar_time`; engine label `1.0.0-rc2-20261016`; GT6 fixed via `BaziResult.chart_day_dt`; OpenAPI regenerated (GT6 caveat dropped); swieph snapshots regenerated with SHA-verified ephemeris (material diff = `engine_version` + `tlst_hours` only), moseph snapshots refreshed (were stale since Phase 3). Madrid fixture re-based to 02:20 (true EoT divergence). |
| FBP-TST-004 | `/calculate/wuxing` + `/chart` TLST via shared context (DEV-2026-008) | P1 | Todo | REQ-TLST-CONSISTENCY | FBP-TST-003 | 2026-10-15 | Cross-endpoint equality test; 50 swieph wuxing snapshots. Supersedes the v2 deferral in DEV-2026-008. |
| FBP-TST-005 | TLST chart date for the day pillar (DEV-2026-011) | P1 | Todo | REQ-ZI-BOUNDARY | FBP-TST-003 | 2026-10-15 | Domain sign-off (plan decision E5); boundary matrix tests. |
| FBP-TST-006 | Exact equation of time via `swe.time_equ` + `eot_source` provenance | P2 | Todo | REQ-TRACEABILITY | FBP-TST-003 | 2026-10-15 | Approximation error measured ≤ 0.77 min; revisit FQ-ATT-02 for `/tst`. |
| FBP-TST-007 | Hygiene: CLI `--standard TLST`, corpus `--check` in CI lint, ZWDS seed consumes context | P3 | Todo | REQ-CLEANUP | FBP-TST-003 | 2026-10-15 | |
