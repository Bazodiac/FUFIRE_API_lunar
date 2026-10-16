# FuFirE BaZi Precision — Deviation Register

**Purpose:** Track every defect, divergence, or open question identified
by the `BAZI-PRECISION-V2` initiative. Every deviation has an ID,
severity, evidence, owner, decision, and current status.

**Severity legend (per plan §15):**

| Sev | Definition |
|-----|------------|
| P0  | Blocker — authenticity, precision, or API contract directly at risk. |
| P1  | High — result still usable, but trust / trace gap. |
| P2  | Medium — domain depth missing; core remains correct. |
| P3  | Low — cleanup / docs / ergonomics. |

**Status legend:** `Open`, `In Review`, `Mitigated (v1)`, `Resolved
(v2)`, `Wontfix (justified)`, `Superseded`.

**Template** (do not delete; new entries copy this block):

```
## DEV-YYYY-NNN — Short title

- Component:
- Expected:
- Actual:
- Evidence:
- Severity: P0|P1|P2|P3
- Affected endpoints:
- Affected tests:
- User-visible impact:
- Migration impact:
- Owner:
- Decision:
- Status:
- Review gate:
```

---

## DEV-2026-001 — `true_solar_time_used` is true when LMT is selected

- Component: `bazi_engine/routers/bazi.py` (derivation trace)
- Expected: Field `true_solar_time_used == true` only when the request
  uses *True* Local Solar Time (TLST = LMT + equation_of_time).
- Actual: `bazi_engine/routers/bazi.py:152` sets the field true whenever
  `time_standard == "LMT"`. LMT is *mean* solar, not true solar.
- Evidence: `bazi_engine/routers/bazi.py:152`; cross-checked against
  `bazi_engine/solar_time.py:17-60` which clearly distinguishes the two.
- Severity: P0
- Affected endpoints: `/calculate/bazi`, `/v1/calculate/bazi`,
  `/chart` (if it embeds the trace).
- Affected tests: `tests/test_pillar_trace.py` (currently asserts the
  field exists but not its semantic correctness).
- User-visible impact: API consumers reading the trace will believe a
  more precise time standard was used than was actually applied.
- Migration impact: Backward-compatible fix requires *adding* a
  separate `lmt_used` flag and correcting `true_solar_time_used` to be
  true only for TLST. The literal field value will change for any
  client currently calling with `time_standard=LMT`.
- Owner: Backend / API contracts (FBP-03-002 / FBP-03-003).
- Decision: Keep field for backward compatibility but document the
  bugfix in v1 release notes; correct semantics under v2.
- Status: Resolved (2026-05-17, FBP-03-002)
- Resolution: `true_solar_time_used` now true only for TLST; `lmt_used` bool added to
  `HourDerivationTrace`. Snapshots and OpenAPI spec regenerated. 2233 tests pass.

## DEV-2026-002 — Provenance `ruleset_id` default does not match ruleset filename

- Component: `bazi_engine/provenance.py` (default args) and
  `spec/rulesets/`.
- Expected: `ruleset_id` emitted in provenance corresponds 1:1 with a
  loadable ruleset file in `spec/rulesets/`.
- Actual: `bazi_engine/provenance.py:142` defaults to
  `"traditional_bazi_2026"`. The actual ruleset file is
  `spec/rulesets/standard_bazi_2026.json`. No
  `traditional_bazi_2026.json` exists.
- Evidence: `bazi_engine/provenance.py:142`; `ls spec/rulesets/`.
- Severity: P1
- Affected endpoints: All `/calculate/*` (provenance block).
- Affected tests: `tests/test_provenance.py` (must be checked against
  the actual loaded ruleset, not the string).
- User-visible impact: Provenance claims an identity that does not map
  to a loadable artifact. Audit trail integrity reduced.
- Migration impact: Either rename the ruleset file or change the
  default. Renaming the file is a downstream-visible change; changing
  the default is internal but requires regenerating snapshots.
- Owner: Provenance / ruleset team (FBP-03-004).
- Decision: Pending — defer until ruleset loader is wired through
  Phase 2 (FBP-02-001), then align both ends.
- Status: Open
- Review gate: FBP-02-001 + FBP-03-004.

## DEV-2026-003 — Engine version drift between `__init__.py` and `pyproject.toml`

- Component: `bazi_engine/__init__.py` vs `pyproject.toml`.
- Expected: Both report the same engine version, or `__version__` is
  derived from `pyproject.toml` at import time.
- Actual: prior to the mitigation, `bazi_engine/__init__.py:18` =
  `"1.0.0-rc1-20260220"` while `pyproject.toml:version` = `"1.0.0rc0"`
  — different rc levels.
- Evidence: see above; `CLAUDE.md` already documents this dual-source
  pattern and the requirement to bump both.
- Severity: P1
- Affected endpoints: All; the API exposes `__version__` via
  `/health`, `/api`, OpenAPI `info.version`, and provenance.
- Affected tests: `tests/test_rebrand.py` (version-string assertions),
  `tests/test_version_sources_aligned.py` (new regression guard).
- User-visible impact: OpenAPI advertised version differed from PyPI /
  installed package version.
- Migration impact: `pyproject.toml` bumped from `1.0.0rc0` →
  `1.0.0rc1` so the rc level matches `__init__.py`. The trailing
  `-20260220` build-identifier suffix is intentionally not on the
  PyPI side (PEP 440 would require `+20260220` local-version syntax;
  not worth the churn for this one bump). The two sources now share
  the rc level, which the new test pins.
- Owner: Release management.
- Decision: Mitigated for v1 by aligning rc levels. Full single-
  source-of-truth (e.g. `importlib.metadata.version()` driving
  `__version__`) is deferred to FBP-06-001.
- Status: Mitigated (v1) — 2026-05-14, commit pending.
- Review gate: FBP-06-001.

**Superseded — 2026-07-13:** The "keep both in lockstep" mitigation is
replaced, not fulfilled. `pyproject.toml`'s `version` is now owned by
[release-please](https://github.com/googleapis/release-please)
(`release-please-config.json`), bumped automatically from Conventional
Commit messages on every merge to `main` — it is no longer a value a human
(or this repo) hand-edits to match `__init__.py`. `bazi_engine.__version__`
remains a separate, manually-curated engine-build label (API responses,
OpenAPI `info.version`, golden snapshot fixtures) with no required
relationship to the package version. `tests/test_version_sources_aligned.py`
no longer cross-checks the two; only `__version__`'s own shape is still
guarded there, and `tests/test_openapi_spec_version.py` guards
`__version__` against the OpenAPI spec. This intentionally makes
FBP-06-001's original framing ("drive `__version__` from `pyproject.toml`")
moot — the two are deliberately two different axes, not one that needs
single-sourcing.
- Status: **Superseded** (2026-07-13) — see release-please decoupling above.

## DEV-2026-008 — `/calculate/wuxing` and `/calculate/tst` use different TLST formulas

- Component: `bazi_engine/routers/fusion.py` `/calculate/wuxing`
  endpoint (line 211) vs `/calculate/tst` (post-Phase-1, delegating
  to `bazi_engine.time_context.compute_effective_time_context`).
- Expected: Both endpoints emit the same "true solar time" value for
  the same `(date, tz, lon)` input. The CIVIL → TLST conversion is
  defined as `UTC + longitude × 4 min + equation_of_time`
  (`docs/fusion/04_solar_time.md`). **Correction 2026-10-15:** this
  entry originally stated `civil_local + longitude/15h + equation_of_time`
  and declared `/calculate/tst` the correct reference. That formula omits
  the zone offset and is itself DEV-2026-009 — both surfaces are wrong,
  in different ways (`wuxing` = civil + EoT; `tst` = civil + lon + EoT;
  correct = civil − tz + lon + EoT). See
  `docs/plans/2026-10-15-true-solar-time-remediation.md` (Task T4) and
  the HTTP tripwires `test_calculate_wuxing_true_solar_time_hannover` /
  `test_chart_time_scales_tlst_hours_hannover` in
  `tests/test_tlst_reference_corpus.py`. The v2-deferral decision below
  is superseded by that plan's decision E1 (loud v1 fix) pending owner
  sign-off.
- Actual: `/calculate/wuxing` calls
  `true_solar_time(civil_time_hours, req.lon, day_of_year)` without
  passing `timezone_offset_hours`. The `else` branch in
  `bazi_engine/solar_time.py:91-92` then treats the civil hours as
  if they were already LMT and only adds EoT. Effectively:
  `wuxing.true_solar_time = civil_hours + EoT_hours`
  `tst.true_solar_time_hours = civil_hours + lon/15 + EoT_hours`
  — the longitude correction is missing on the wuxing side.
- Evidence: `bazi_engine/routers/fusion.py:211`;
  `bazi_engine/solar_time.py:88-95` (the `if timezone_offset_hours is
  not None` branch); `bazi_engine/time_context.py:_compute_…`.
- Severity: P1 (cross-endpoint inconsistency; consumer-visible value
  drift for any non-zero longitude — ~6 min in Berlin, more
  elsewhere).
- Affected endpoints: `/calculate/wuxing`. `/calculate/tst` post-Phase-1
  is treated as the correct reference.
- Affected tests: none current — neither `tests/test_provenance.py`
  nor `tests/test_snapshot_stability.py` pins the exact
  `true_solar_time` numeric value at the wuxing endpoint.
- User-visible impact: For non-meridian longitudes the wuxing
  endpoint's `true_solar_time` field is offset from the tst
  endpoint's `true_solar_time_hours`. Downstream consumers that
  compare the two surfaces (or compute their own TLST off the wuxing
  value) see a silent drift.
- Migration impact: Fixing in `/v1` would change a numeric response
  field — a wire-breaking change for any client reading
  `equation_of_time` / `true_solar_time` on the wuxing endpoint. The
  Phase-0 freeze says "no silent v1 behavior change". So either:
  (a) ship the fix only under `/v2/calculate/wuxing` (FBP-06-001 era),
      keeping `/v1` numerically reproducible, or
  (b) deprecate the wuxing `true_solar_time` / `equation_of_time`
      fields in v1 (mark deprecated in OpenAPI; remove in v2) and
      direct callers to `/calculate/tst` for the canonical value.
  The Decision field below selects option (a); option (b) is recorded
  here for future review.
- Owner: API contracts (FBP-06-001 / wuxing v2).
- Decision: ~~Defer to Phase 6 (`/v2/calculate/wuxing`)~~ — superseded by
  plan decision E1 (owner-approved 2026-10-16): fixed in v1, loudly.
- Status: **Resolved (v1, loud)** — 2026-10-16, FBP-TST-004. `/calculate/wuxing`
  and `/chart` `time_scales` consume `compute_effective_time_context_from_instant`;
  engine build label `1.0.0-rc3-20261016`; 50 swieph `*__wuxing.json`
  regenerated (only `true_solar_time` / `equation_of_time` / `engine_version`
  changed). Permanent drift guard: `test_all_tst_surfaces_agree`.
- Review gate: FBP-TST-004.

## DEV-2026-004 — Day-cycle anchor unverified

- Component: `bazi_engine/constants.py:DAY_OFFSET`,
  `bazi_engine/bazi.py:sexagenary_day_index_from_date`,
  `spec/rulesets/standard_bazi_2026.json:day_cycle_anchor`.
- Expected: A single, verified anchor (date or JDN ↔ sexagenary index)
  cited from a domain-authoritative source, consumed by both core and
  `/validate`.
- Actual: Core uses hardcoded `DAY_OFFSET = 49` with comment "1949-10-01
  is Jia-Zi (0)"; ruleset has a parallel `anchor_jdn = 2419451` flagged
  `"anchor_verification": "unverified"` and label "Assumed JiaZi day
  (verify!)". The two are independent. Neither is verified.
- Evidence: `bazi_engine/constants.py:22`;
  `spec/rulesets/standard_bazi_2026.json:22-27,353`.
- Severity: P0 (blocker for v2 default switch).
- Affected endpoints: `/calculate/bazi`, `/calculate/fusion`, `/v1/*`,
  any derived feature (impact, daily, experience).
- Affected tests: `tests/test_invariants.py:16-18` (asserts literal
  `49` and two reference dates),
  `tests/test_constants.py:83-128` (multiple bounds and identity tests),
  `tests/test_golden.py` (indirectly through pillar values).
- User-visible impact: If the anchor is wrong, every day pillar is
  wrong by the corresponding offset; downstream signatures and
  fusion harmony scores all shift. The user has no way to detect this
  from the response today.
- Migration impact: Cannot be silently changed. Any anchor correction
  requires a migration report quantifying signature deltas
  (FBP-04-006). Until then, `/v1` is frozen and `/v2` is not opened.
- Owner: Domain expert + backend (FBP-02-002, FBP-02-003).
- Decision: Pending — `DOMAIN_REVIEW_REQUIRED`. Phase 2 may not change
  defaults; it may only add a `verified` track gated behind opt-in.
- Status: Open
- Review gate: FBP-02-003.

## DEV-2026-005 — `DAY_OFFSET == 49` asserted as truth in additional test file

- Component: `tests/test_constants.py:83-128`.
- Expected: Day-anchor tests reference an anchor ID / verification
  status, not the literal integer.
- Actual: Multiple assertions including `assert DAY_OFFSET == 49`,
  `> 0`, `< 60`, and "1949-10-01 should be Jia-Zi day with DAY_OFFSET=49".
- Evidence: see component.
- Severity: P1 (follow-up to FBP-02-002).
- Affected endpoints: None directly; pure invariant test.
- Affected tests: As component.
- User-visible impact: None; internal test brittleness.
- Migration impact: When FBP-02-002 ruleset-drives the anchor, these
  tests will fail-fast unless rewritten. Plan only explicitly covers
  `tests/test_invariants.py`.
- Owner: Test / domain (FBP-02-002 follow-up).
- Decision: Rewrite alongside FBP-02-002, retaining the bounds checks
  (`isinstance int`, `0 ≤ offset < 60`) but moving the literal 49 and
  the date-pinned cases to ruleset-driven equivalents.
- Status: Open
- Review gate: FBP-02-002.

## DEV-2026-006 — `ErrorEnvelope` is inlined in `app.py` rather than versioned in `spec/schemas/`

- Component: `bazi_engine/app.py:515,530` vs `spec/schemas/`.
- Expected: `spec/schemas/ErrorEnvelope.schema.json` exists; the
  application references it.
- Actual: The envelope is defined inline inside the OpenAPI
  customization function. There is no standalone schema file.
- Evidence: `ls spec/schemas/` shows only `refdata_manifest`,
  `ValidateRequest`, `ValidateResponse`.
- Severity: P2
- Affected endpoints: All (every error path).
- Affected tests: `tests/test_error_handling.py`,
  `tests/test_error_sanitization.py`,
  `tests/test_openapi_contract.py` (if it currently asserts the inline
  shape).
- User-visible impact: No runtime effect; reduces auditability and
  blocks RFC 9457 v2 planning.
- Migration impact: Extract is purely additive in v1; v2 may add
  Problem Details fields per RFC 9457.
- Owner: API contracts (FBP-03-005 / FBP-03-006).
- Decision: Extract under FBP-03-005, then add v2-only Problem Details
  fields under FBP-03-006. Existing inline copy retained for v1
  contract reproducibility.
- Status: Open
- Review gate: FBP-03-005.

## DEV-2026-007 — Wu-Xing model versioning collapsed into one `parameter_set.version` field

- Component: `bazi_engine/provenance.py:17-62`.
- Expected: Separate `vector_model_id`, `normalization_model_id`,
  `fusion_model_id`, `harmony_model_id`, `calibration_model_id` so
  v1/v2 parallel operation (FBP-04-005) is meaningful.
- Actual: Only a single `version: "1.1.0"` string on the
  `WUXING_PARAMETER_SET` dict.
- Evidence: `bazi_engine/provenance.py:18`.
- Severity: P1 (precondition for FBP-04-005).
- Affected endpoints: `/calculate/fusion`, `/calculate/wuxing`,
  `/impact/active`, `/experience/daily`.
- Affected tests: `tests/test_provenance.py`,
  `tests/test_fusion.py`, `tests/test_contribution_ledger.py`.
- User-visible impact: Cannot distinguish v1 vs v2 fusion output
  without a version-shaped contract.
- Migration impact: Additive at first (introduce new fields keyed
  alongside existing `parameter_set.version`); breaking only if the
  string is removed (don't).
- Owner: Fusion / Wu-Xing (FBP-04-002).
- Decision: Add new fields in FBP-03-004 and FBP-04-002. Keep
  `parameter_set.version` as deprecated alias until v2 fully replaces
  v1 default.
- Status: Partially resolved (2026-05-18, FBP-03-004)
  - `vector_model_id` surfaced in derivation trace `provenance_ids` block.
  - Remaining: per-sub-model IDs (normalization, fusion, harmony, calibration) tracked in FBP-04-002.
- Review gate: FBP-04-002.

---

## Security Findings Register

### SEC-2026-001: IDOR-1 — Superglue proxy accepts any user_id (Accepted)

| Field | Value |
|---|---|
| ID | SEC-2026-001 |
| Severity | Low |
| Evidence | `bazi_engine/routers/superglue.py` — all proxy routes accept `user_id` path/query param validated only by regex, not by API key ownership |
| Owner | Engineering |
| Status | Accepted |

**Rationale:** The Superglue proxy routes are called exclusively by ElevenLabs service agents using service-level API keys, not by end users. There is no user-to-key binding in this trust model — the caller IS the service, acting on behalf of any user. Adding ownership checks would require a user registry that does not exist and would break the ElevenLabs integration.

**Mitigations in place:** Route-level rate limiting, API key authentication, Superglue-side authorization on the upstream service.

---

### SEC-2026-002: CREDS-1 — Superglue token in URL query string (Accepted)

| Field | Value |
|---|---|
| ID | SEC-2026-002 |
| Severity | Low |
| Evidence | `bazi_engine/services/superglue_client.py` — token appended to URL as `?token=...` |
| Owner | Engineering |
| Status | Accepted |

**Rationale:** The Superglue API requires the token as a URL query parameter. This cannot be changed without a Superglue platform modification. The token is a server-side secret in the `SUPERGLUE_TOKEN` environment variable and is never exposed to clients. TLS in transit prevents interception; server-side logs are the only exposure surface.

**Mitigations in place:** Token stored as env var (not hardcoded), TLS enforced on Railway deployment, Superglue token is a service credential with no user data access.

---

## Closed deviations

*(none yet)*

---

## Decisions

### DECISION-DAYUN-002 — 2026-07-13 — Da-Yun decade dates: 360-day ritual year → real Gregorian years

The previous 360-day ritual-year date model — documented as "intentional" in `bazi_engine/routers/dayun.py` — is superseded. Decade `date_start`/`date_end` now track real Gregorian years (leap-aware) via `bazi_engine/dayun/dates.add_real_years`, because those fields are declared `format: date` in the response schema and were consumed downstream as real dates, where the old 3600-day decade drifted ~52 days per decade (~1.1 years by decade 8). `select_current` was aligned to the same real mean-year divisor (365.2425) so current-cycle selection agrees with the emitted dates. `start_age` (classical 3-days = 1-year) and the `age_start`/`age_end` real-year decimals are unchanged; the response shape is unchanged and `provenance.ruleset_id` stays `dayun_v1`.

### DECISION-ZWDS-001 — 2026-07-14 — ZWDS core-seed ruleset status, fixed policies, and PENDING GATE-1 practitioner review

The Zi Wei Dou Shu (ZWDS) natal engine ships as an explicit **core-seed**, not a universal or complete ZWDS engine. The `zwds.fufire.core-seed.v1` ruleset declares `source_status=SOURCE_NEEDED`, `school_label=null`, and is labelled `core-seed`: its output is engine-deterministic truth (byte-stable per fixed `(request, request_id, generated_at)` with a fixed ephemeris), **not** a practitioner- or historically-validated chart. The following policies are fixed and disclosed in every response's ruleset envelope: calendar `local-civil-day.v1` (swisseph-native 時憲曆 — day boundary follows the chart's effective-local frame; core-seed resolves in the `CIVIL` time standard); leap-month interpretation `split-after-day-15.guide-v1`; year-cycle basis `lunar-year.guide-v1` (year stem/branch from the lunar new year, not LiChun); Four-Transformations table `guide-four-transformations.v1` (the mainstream, iztro-corroborated tabulation, flagged `SOURCE_NEEDED` with the **contested** `GENG.HUA_KE` / `REN.HUA_KE` cells). The natal golden corpus (`tests/zwds/goldens/`, generated by `scripts/zwds/gen_natal_goldens.py`, locked by `tests/zwds/test_zwds_golden.py`) covers all 5 bureaus, all 10 year-stem transformation rows, leap-month, late-Zi, both direction methods + omit, and a non-CST birth — but comparator (`iztro`) agreement is recorded only as a `crosscheck` MATCH and is explicitly **not** historical proof. **GATE-1 human practitioner review of the natal charts is PENDING** (see `docs/zwds/golden-review.md`, the sole unchecked release-gate item). No fusion, dynamics, or interpretation layer is built on top of the natal chart until GATE-1 passes.

## DEV-2026-009 — `EffectiveTimeContext.tlst_hours` adds the longitude correction to CIVIL time instead of UTC

- Component: `bazi_engine/time_context.py::compute_effective_time_context`
  (`raw_tlst = civil_hours + delta_t_long + eot`). Consumers:
  `bazi.py` (TLST hour pillar, TLST zi-rollover), `routers/bazi.py`
  (`derivation_trace.time_resolution.tlst_hours` for ALL standards),
  `routers/fusion.py` `/calculate/tst`, `chronometry.py`
  (`/chronometry/resolve`, `/personalize`), `routers/natal.py`,
  `routers/dayun.py`, `routers/match.py` (TLST input).
- Expected: `TLST = UTC + longitude × 4 min + EoT` (definition in
  `docs/fusion/04_solar_time.md`; oracle `swe.lmt_to_lat`). Hannover
  1990-07-15 15:44 MESZ → TLST 14:17 (hour branch Wei), equal to the
  engine's own LMT (14:22) plus EoT (−5.9 min).
- Actual: `tlst_hours` = civil + lon·4min + EoT = 16:17 (Shen): off by
  exactly the zone's UTC offset for every non-UTC zone. `date_rollover`
  is derived from the same wrong raw value. Grid of 18 432 samples × 16
  zones against swisseph: 85.4 % wrong hour branch, 21.4 % wrong TLST
  date, max error 12 h (UTC+12/13). `ctx.lmt_local` is correct, so the
  context contradicts itself (`TLST − LMT ≠ EoT`).
- Evidence: `tests/test_tlst_reference_corpus.py` (strict xfail
  tripwires `test_ctx_tlst_hours_matches_reference[*]`,
  `test_ctx_tlst_is_invariant_under_zone_relabeling`,
  `test_ctx_tlst_minus_lmt_equals_eot`, HTTP: `test_calculate_tst_endpoint_hannover`,
  `test_chronometry_endpoint_hannover`, `test_calculate_bazi_trace_tlst_hours_hannover`);
  fixture `tests/fixtures/tlst_reference_corpus_v1.json`. Origin: the formula was
  copied from the pre-FBP inline `/calculate/tst` code and pinned by
  `tests/test_bazi_time_context.py::test_tlst_formula_matches_calculate_tst_endpoint`
  (consistency was tested, correctness never — audit §11). `zwds/seed.py`
  documents the defect in its docstring and works around it locally.
- Severity: P0 (wrong hour pillar for `standard=TLST`; wrong published
  TLST on four endpoints).
- Affected endpoints: `/calculate/tst`, `/calculate/bazi` (+`/trace`,
  `/natal`, `/dayun`), `/chronometry/resolve`, `/personalize`,
  `/v1/match/bazi-hehun`.
- Affected tests: `tests/test_bazi_time_context.py::test_tlst_formula_matches_calculate_tst_endpoint`
  (pins the bug), `tests/test_bazi_tlst_hour_pillar.py` (Madrid 02:00
  fixture diverges only because of the bug; correct replacement
  02:20), `tests/test_bazi_trace_endpoint.py::test_trace_day_pillar_matches_headline_tlst_zi`
  (GT6 strict xfail flips to XPASS with the fix), 50 SWIEPH
  `*__bazi.json` snapshots (`tlst_hours`), `chronometry_canonical.json`.
- User-visible impact: any TLST-based chart for a non-UTC zone has the
  wrong hour pillar whenever the zone offset crosses a 2-hour bin
  (most births); `/calculate/tst` and chronometry publish a solar time
  that is off by the zone offset.
- Migration impact: numeric wire values change (loud v1 fix per plan
  decision E1; engine build label bump + CHANGELOG + snapshot regeneration).
- Owner: BaZi precision (BAZI-PRECISION-V2).
- Decision: Fix in v1 as Task T3 of
  `docs/plans/2026-10-15-true-solar-time-remediation.md`, together with GT6.
- Status: **Resolved (v1, loud)** — 2026-10-16, FBP-TST-003 (+GT6). `time_context.py` computes TLST on the UTC axis via `compute_effective_time_context_from_instant`; engine build label bumped to `1.0.0-rc2-20261016`; 50 swieph `*__bazi.json` + `chronometry_canonical.json` regenerated (only `tlst_hours` / `true_solar_time` / `engine_version` changed; CIVIL/LMT pillars byte-identical). Former tripwires now run as regression tests.
- Review gate: FBP-TST-003.

## DEV-2026-010 — `compute_effective_time_context` drops the DST fold

- Component: `bazi_engine/time_context.py` (naive ISO in,
  `replace(tzinfo=ZoneInfo(tz))` with implicit `fold=0`); callers pass
  `BaziInput.birth_local` without `BaziInput.fold`.
- Expected: for an ambiguous fall-back time resolved with `fold=1`
  (e.g. `ambiguousTime="later"`), `ctx.utc` equals the resolved
  instant (Berlin 2024-10-27 02:30 fold=1 → 01:30Z).
- Actual: fold=1 is recomputed as fold=0 → UTC, LMT and TLST 1 h early.
- Evidence: `tests/test_tlst_reference_corpus.py::test_ctx_fold1_cannot_be_expressed_and_is_resolved_as_fold0`
  (strict xfail); corpus cases `berlin_dst_fallback_fold0/1`.
- Severity: P1 (only the second occurrence of ambiguous times).
- Affected endpoints: every consumer listed under DEV-2026-009 when
  `ambiguousTime="later"` / `fold=1`.
- Affected tests: none pin the wrong value.
- Decision: Task T2 — aware-datetime entry point
  (`compute_effective_time_context_from_instant`) + `fold` parameter.
- Status: **Resolved** — 2026-10-16, FBP-TST-002. All engine callers (`bazi.py`, `routers/bazi.py` trace, `routers/fusion.py` `/tst`, `chronometry.py`, `zwds/seed.py`) hand over the resolved aware instant.

## DEV-2026-011 — TLST day pillar ignores `EffectiveTimeContext.date_rollover`

- Component: `bazi_engine/bazi.py::_dt_for_day_pillar` /
  `to_chart_local` (TLST falls through to CIVIL; FBP-01-004 guard).
- Expected: under `standard=TLST` the chart date is the apparent-solar
  date: `civil_date + date_rollover` (+1 under `zi` when
  `tlst_hours ≥ 23`). Madrid 2024-02-22 00:30 CET has TLST 23:01 on
  02-21 → day pillar of 02-21.
- Actual: the civil date is used; `date_rollover` is computed but never
  read anywhere in `bazi_engine/`.
- Evidence: `tests/test_tlst_reference_corpus.py::test_tlst_day_pillar_uses_tlst_date_before_solar_midnight`
  (strict xfail); `grep -rn date_rollover bazi_engine/` → only the producer.
- Severity: P1 (wrong day pillar for TLST births between solar and
  civil midnight, west of the zone meridian).
- Decision: Task T5, needs domain sign-off (plan decision E5).
- Status: Open — tripwire in place (2026-10-15).

## DEV-2026-012 — `fusion.true_solar_time_from_civil` inverts the longitude sign and is DST-blind

- Component: `bazi_engine/fusion.py::true_solar_time_from_civil`
  (`civil + 4·(standard_meridian − longitude) + EoT`;
  `standard_meridian = round(lon/15)·15`).
- Expected: Berlin (13.405°E, meridian 15°E) runs ~6.4 min *behind*
  zone time: TST(12:00 CET, day 180) ≈ 11.84 h.
- Actual: 12.05 h (correction added instead of subtracted); the
  auto-meridian ignores DST (+15°) and non-integer zones.
- Evidence: `tests/test_tlst_reference_corpus.py::test_true_solar_time_from_civil_sign_convention`
  (strict xfail). No production caller (`grep` → only `tests/test_fusion.py`).
- Severity: P2 (dead-but-exported wrong math).
- Decision: Task T1 — remove (or delegate to `solar_time.true_solar_time`
  with an explicit zone offset + DeprecationWarning).
- Status: **Resolved** — 2026-10-16, FBP-TST-001: helper removed from `bazi_engine/fusion.py` (no production caller; `tests/test_fusion.py` class dropped, regression test asserts absence).
