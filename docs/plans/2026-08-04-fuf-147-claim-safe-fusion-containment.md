# FUF-147 — Rohwert-Narration sofort fail-closed eindämmen (Containment Slice)

Jira: https://dyai2026.atlassian.net/browse/FUF-147 (Sub-Task of FUF-55, P0, labels:
claim-safety, consumer-contract, fusion-1, golden-fixture, regression-fix)

## Goal

No production-visible Fusion or Daily standard path derives **positive harmony /
compatibility / relationship prose** from `H_raw`, raw cosine, or distance before the
full calibrated card-pair model exists. Raw metrics remain available, but only labeled
as expert diagnostics. An automated regression test permanently prevents a raw-value
fallback.

## Non-Goals (stay in FUF-55B)

- Full migration of calibration version, coverage, uncertainty and all consumers.
- Changing the `/impact/active` + `/experience/daily` `day_mode` classifier
  (`impact_harmony.classify_day_mode`). It maps raw dot-product to a mode enum
  (`calm|active|tense|pulse`), which is part of the frozen public contract and is not
  harmony/compatibility/relationship *prose*. Documented in the consumer matrix below;
  migration decision belongs to FUF-55B.
- Removing raw numeric fields from frozen response shapes (endpoints are frozen; we
  change **content/labeling**, never remove fields or change types).
- `bazi_engine/research/*` (offline analysis tooling, not production-visible).
- `wuxing/zones.py` `format_report_b` (not mounted by any router/service — verified
  by grep; report generator only used in tests).

## Root cause (evidence)

`bazi_engine/wuxing/calibration.py` header: raw `H = cos(θ)` lies empirically in
[0.50, 1.0] (positive orthant of R^5); two **random** charts have expected H ≈
0.72–0.79. The thresholds 0.2/0.4/0.6/0.8 used by `interpret_harmony()` and
`generate_fusion_interpretation()` are therefore de-facto unreachable on the low end —
nearly every user receives "Starke Resonanz / ergänzen sich harmonisch" prose.
Calibrated machinery (`CalibrationResult.h_calibrated`, `.quality`,
`.interpretation_band`) already exists and is claim-safe.

## Violation inventory (production-visible standard paths)

| ID | Location | Violation | Consumer |
|----|----------|-----------|----------|
| V1 | `bazi_engine/fusion.py:172` `generate_fusion_interpretation()` | Positive prose ("starker Resonanz", "ergänzen sich harmonisch") from raw `harmony_index`; also embeds `interpret_harmony(raw)` | `/calculate/fusion` (`fusion_interpretation`), webhook voice profile (`fusion.interpretation`) |
| V2 | `bazi_engine/wuxing/analysis.py:305` `interpret_harmony()` via `calculate_harmony_index()["interpretation"]` | Raw→judgment label ("Starke Resonanz — … perfekter Harmonie") | `/calculate/fusion` (`harmony_index.interpretation`), webhook (`harmonyInterpretation`), `/api/chart` (indirect via `calculate_harmony_index`) |
| V3 | `bazi_engine/routers/webhooks.py:250-265` | `harmonyIndex` = raw, `harmonyInterpretation` = raw prose, `summary.harmonie` = raw percent — spoken to end users by ElevenLabs agent | ElevenLabs voice agent (HMAC webhook) |
| V4 | `bazi_engine/routers/experience.py:432` | Raw-value fallback: `cal.get("h_calibrated", harmony_raw.get("harmony_index", 0.5))` — if calibration key ever missing, raw silently becomes the user-facing `harmony_index` | `/experience/bootstrap`, signature blueprint |

Reviewed, no prose violation (documented for FUF-55B):
- `impact_harmony.py` (`compute_harmony_index` → `day_mode`/`drivers`): raw dot-product →
  enum labels, no harmony prose. `/impact/active`, `/experience/daily`.
- `services/daily_fusion.py` / `daily_templates.py`: text selection keyed on categorical
  BaZi resonance types and weekday, not on numeric harmony.
- `services/signature_blueprint.py`: uses harmony numerically for geometry (orbit count),
  no prose; receives calibrated value once V4 is fixed.
- `routers/chart.py:277`: emits numeric `harmony_index` only (no prose field).
- `routers/fusion.py` `/calculate/wuxing`: emits `elemental_overlap_h`/`cosine_similarity`
  as numeric metrics with explicit metric names, no judgment prose.

## Preconditions / constraints

- **Start-Gate (from Jira comment):** no breaking change of the public contract.
  Satisfied: all changes are content-of-string / value-source changes plus additive
  fields; no field removed, no type changed. OpenAPI drift check must pass.
- Local checkout `~/FuFirE-lunar` has divergent squashed history — **never push from
  it**. Delivery via fresh clone of `DYAI2025/FUFIRE_API_lunar` (branch + PR).
- Tests run via `uv sync --extra dev && uv run pytest` (venv lacks pytest; shell hook
  rewrites bare `pytest`).
- Ephemeris-dependent tests must skip gracefully; the new golden fixture must be
  ephemeris-free (synthetic `western_bodies` + `bazi_pillars` dicts — `calibrate_harmony`
  and vector math are pure).
- `DYAI2025/FuFire_API_LIVE`: inspect remotely for the same code; patch only if the
  violation exists there (T8).

## Design decision (fail-closed output)

`generate_fusion_interpretation` gains an optional `calibration: CalibrationResult | None`
parameter (backward-compatible signature).

- With calibration: text reports `H_calibrated` percent + `interpretation_band` +
  `quality`, dominances, and `H_raw` **only** under an explicit
  "Expertendiagnostik (unkalibrierter Rohwert — kein Nutzerurteil)" label.
- Without calibration (or `quality == "degenerate"`): fully fail-closed — diagnostic-only
  text, no congruence band, no judgment sentence.
- The three raw-threshold judgment sentences (lines 193–201) are deleted, not gated.

`interpret_harmony(h)` becomes a claim-safe raw diagnostic label: constant-form string
naming the value as an uncalibrated raw metric for expert diagnostics, no judgment
wording, for every input value. (Kept exported for backward import compatibility.)

Webhook voice profile: `harmonyIndex` → `h_calibrated`; `harmonyInterpretation` →
`interpretation_band`; `summary.harmonie` → calibrated percent; additive field
`harmonyIndexRaw` (labeled diagnostic) preserves the raw number for experts.

Experience profile: `harmony_index = cal["h_calibrated"]` with **neutral 0.5** fallback —
never raw.

Forbidden-claim list (single source in the new test module, reused by all claim-safety
tests): `"Starke Resonanz"`, `"starker Resonanz"`, `"perfekter Harmonie"`,
`"Gute Harmonie"`, `"ergänzen sich harmonisch"`, `"unterstützen sich gegenseitig"`.

## Tasks

### T1 — Claim-safety regression tests (write first, must fail before fix)
- REQ: AK-1 (no standard path uses `harmony_index` directly as user judgment),
  AK-2 (golden fixture yields no positive harmony statement), AK-3 (contract/consumer
  tests prevent raw fallback).
- Files: new `tests/test_claim_safety_fusion.py`.
- Tests:
  1. **Sweep:** `generate_fusion_interpretation(h, …)` for h in {0.0,…,1.0 step .05}
     with no/neutral calibration contains no forbidden claim.
  2. **Golden fixture (ephemeris-free):** synthetic dense chart (≥9 non-error planets,
     ≥17 bazi Qi contributions) constructed so `h_raw ≥ 0.75` while dense/dense baseline
     0.7958 ⇒ `h_calibrated ≈ 0` ("Keine messbare Kongruenz"): full
     `compute_fusion_analysis`-level path via direct vector+calibration composition;
     assert `h_raw ≥ 0.75`, `h_calibrated ≤ 0.15`, and no forbidden claim in
     `fusion_interpretation` **and** `harmony_index.interpretation`.
  3. **Raw-fallback guard (boundary, WS-A convention):** monkeypatch
     `compute_fusion_analysis` in `routers.experience` to return a fusion dict with
     high raw harmony and **no** `h_calibrated` key → `_compute_astro_profile` /
     bootstrap uses 0.5, never the raw value.
  4. **HTTP boundary (`TestClient`, skip w/o ephemeris):** POST `/calculate/fusion` →
     assert `resp.text` contains no forbidden claim; `harmony_index.interpretation`
     contains "Rohwert"/diagnostic marker.
  5. **Webhook shape:** voice-profile fusion block uses calibrated values (unit test on
     the builder path or via monkeypatched fusion result): `harmonyIndex ==
     h_calibrated`, `harmonyInterpretation == interpretation_band`, `harmonie` percent
     derived from `h_calibrated`, `harmonyIndexRaw` present.
- Acceptance evidence: run tests → all new tests fail (red) before T2–T5, pass after.

### T2 — `interpret_harmony` → claim-safe diagnostic label
- Files: `bazi_engine/wuxing/analysis.py` (`interpret_harmony`,
  `calculate_harmony_index` docstring).
- Update coupled tests: `tests/test_fusion.py:180-194,344`,
  `tests/test_wuxing_analysis.py` (label assertions), `tests/test_integration_fusion.py`.
- Acceptance: sweep test 1 passes for the label; no forbidden claim reachable.

### T3 — `generate_fusion_interpretation` calibration-aware fail-closed
- Files: `bazi_engine/fusion.py` (signature + body; `compute_fusion_analysis` passes
  `cal`), delete raw-threshold prose.
- Update coupled tests: `tests/test_fusion.py:392-407`,
  `tests/test_integration_fusion.py:125,217-249`, `tests/test_endpoints.py:238` region.
- Acceptance: tests 1, 2, 4 pass.

### T4 — Webhook voice profile claim-safe
- Files: `bazi_engine/routers/webhooks.py` (fusion block + `VoiceProfileFusion`-model:
  additive `harmonyIndexRaw`, value-source switch).
- Acceptance: test 5 passes; response model still validates; no field removed.

### T5 — Remove raw fallback in experience profile
- Files: `bazi_engine/routers/experience.py:431-433`.
- Acceptance: test 3 passes.

### T6 — Full verification
- `uv run pytest -q` (whole suite), `uv run ruff check bazi_engine/`,
  `uv run mypy bazi_engine --ignore-missing-imports`,
  `uv run python scripts/export_openapi.py --check` (regen + commit spec only if the
  additive webhook model field changes the spec — webhooks are `include_in_schema=False`,
  so expect no drift).
- Acceptance evidence: command outputs captured in execution log.

### T7 — Delivery (fresh clone; local checkout must not push)
- `git clone https://github.com/DYAI2025/FUFIRE_API_lunar.git` (scratchpad), branch
  `fuf-147-claim-safe-fusion-containment`, apply diff, re-run pytest there, push, open
  PR referencing FUF-147 with AK checklist + rollback note.
- Acceptance: PR URL; CI green.

### T8 — `FuFire_API_LIVE` inventory
- Inspect `DYAI2025/FuFire_API_LIVE` for `generate_fusion_interpretation` /
  `interpret_harmony` copies. Document result in PR/Jira; if the same violation exists,
  file follow-up (or replicate patch if trivially identical).
- Acceptance: documented finding.

### T9 — Jira evidence
- Comment on FUF-147: consumer matrix, test evidence, PR link, rollback note.

## Risks

- **Consumer wording dependencies:** Bazodiac frontend or ElevenLabs prompts may pattern-
  match old strings ("Starke Resonanz"). Mitigation: fields/types unchanged; text change
  is the *point* of the ticket; consumer matrix documented; rollback is a single revert.
- **Semantics of `harmonyIndex` (webhook) change raw→calibrated:** value will typically
  drop (~0.8 → ~0.1). Intentional per ticket; raw preserved in `harmonyIndexRaw`.
  Called out explicitly in PR + Jira.
- **Test-string churn:** several suites assert old labels; all updated in T2/T3 — grep
  for forbidden claims across `tests/` at the end must return only the forbidden-list
  definition itself.

## Rollback

Single revert of the PR merge commit restores prior behavior; no data, schema, or config
migration involved. Webhook consumers regain raw-value prose immediately after revert —
acceptable because that is the pre-existing state being contained.
