# FuFirE Lunar V2 — Live Production Readiness Completion Plan

Status: **BLOCKED — implementation-prepared; production promotion is not authorized**  
Last updated: 2026-07-22  
Engine repository: `DYAI2025/FUFIRE_API_lunar`  
Portal repository: `DYAI2025/FuFire_API_LIVE`  
Machine-readable gate state: `evidence/release-readiness/live-production-gates.json`

This repository-local plan operationalizes the approved Lunar V2 readiness intake. It is not a release approval and must not be used to infer that Railway, DNS, Legal, Product, Security, SRE, Portal, staging, production, or rollback evidence exists.

<!-- GOAL_START -->
Goal: release Lunar V2 only after the complete `Browser/Developer Portal -> BFF/Proxy -> api.fufire.space -> POST /v2/astronomy/lunar-state -> SWIEPH` path is evidenced against one approved commit and immutable image digest. Production readiness requires closed contract, security, ephemeris, performance, observability, legal, deployment, domain, promotion, and rollback gates. Existing V1 contracts remain compatible and Lunar remains V2-only. Missing values are never estimated, required live tests never silently skip, and no secret, API key, personal request data, or confidential license content may enter logs or evidence. The final release decision may become `RELEASE` only when every mandatory gate is `CLOSED`, the public OpenAPI and `/build` identity match the approved artifact, the portal browser path works without mocks, and rollback to the previous healthy digest has been rehearsed.
<!-- GOAL_END -->

## SMART-CONTEXT

### Current situation

- The Lunar endpoint, V2 mount, repository OpenAPI, locked ephemeris inputs, SWIEPH reference tests, readiness policy, and atomic CI gate exist in the Engine repository.
- On 2026-07-22, `main` was safely fast-forwarded to `master`; both now point to `d51df762746591aa6928edec9459fff18aa606fc`.
- GitHub still reports `master` as the default branch. Railway source-branch, current deployment identity, staging, domain, branch rules, release identity, legal approval, performance, observability, and rollback evidence are not available in this repository.
- Stale PRs #6 and #16 were closed as superseded. Production promotion remains blocked.

### System boundary

In scope: Engine code and contracts, GitHub control plane, immutable image/SBOM/attestation, Railway staging and production, `api.fufire.space`, auth/CORS/Redis/readiness, SWIEPH verification, portal OpenAPI mirror, explicit V2 catalog support, BFF request validation, browser E2E, monitoring, promotion, and rollback.

Out of scope: new interpretation features, topocentric Moon calculations, rise/set calculations, broad BaZi/Western/Fusion/ZWDS rewrites, unrelated portal redesign, PyPI publication, or a public container release outside the approved license path.

## Non-negotiable release invariants

1. No production release while license, astronomy tolerance, performance thresholds, branch protection, release identity, staging evidence, or rollback evidence is missing.
2. Build once; deploy Staging and Production by the same immutable digest.
3. Commit SHA, image digest, OpenAPI SHA, SBOM, attestation, release version, and ephemeris lock ID must be mutually traceable.
4. Repository or CI existence is not live evidence. The public domain and portal mirror must contain the Lunar operation.
5. Production must be fail-closed for API keys, explicit CORS, SWIEPH, required Redis policy, and dependency readiness.
6. Required direct, BFF, browser, failure-boundary, load, and rollback checks may not skip silently.
7. Evidence must not contain secrets, API keys, request bodies, birth/local-time data, or confidential license terms.

## Verified Engine baseline

| Item | State | Evidence class |
|---|---|---|
| V2 Lunar route and typed contract | present | source-inspected / integration |
| Locked ephemeris inputs and SWIEPH tests | present | integration |
| Python 3.10/3.11/3.12 CI and atomic release gate | present | integration |
| Docker/runtime hardening and readiness logic | present | source-inspected / integration |
| `main` and `master` SHA convergence | complete at `d51df762746591aa6928edec9459fff18aa606fc` | production-observed GitHub metadata |
| Default branch switched to `main` | not done; default remains `master` | production-observed GitHub metadata |
| Railway source/deployment identity | MISSING | unknown |
| Release decision | `BLOCKED` | repository evidence |

## Mandatory blocker register

| ID | Priority | Gate | Current status | Closure evidence |
|---|---|---|---|---|
| LR-001 | P0 | Canonical branch/default converge on `main` (Railway source dropped: VPS-only target, ADR-006, 2026-10-19) | PARTIAL | GitHub default-branch export; same-SHA `/build` proof on the VPS after the ETBZ cutover |
| LR-002 | P0 | Protected branch rules with required checks and no bypass | MISSING | Ruleset export and check-suite IDs |
| LR-003 | P0 | Least-privilege release-please identity | MISSING | Successful bot PR and audit/check evidence; never token value |
| LR-004 | P0 | Swiss Ephemeris license path approved | BLOCKED | Legal approval/evidence ID and artifact license inventory |
| LR-005 | P0 | Astronomy tolerance and supported range approved | BLOCKED | Domain-owner approval ID and measured reference report |
| LR-006 | P0 | Public release/version authority approved | BLOCKED | Product approval and version ADR/tests |
| LR-007 | P0 | Merged review findings resolved | PARTIAL | Python 3.10 fix, readiness 503 contract, version policy, zero unresolved threads |
| LR-008 | P0 | Public runtime proves SWIEPH and exact lock ID | MISSING | `/ready`, Lunar response, failure injection, deployment identity |
| LR-009 | P0 | Auth/CORS/Redis/rate-limit/key-rotation proven at real boundary | MISSING | Staging negative/positive matrix and sanitized logs |
| LR-010 | P0 | `/ready` 503 schema explicitly governed | PARTIAL | ADR, runtime tests, generated OpenAPI 503 schema test |
| LR-011 | P0 | Immutable image built once and promoted by digest | MISSING | Registry digest and Railway deployment records |
| LR-012 | P0 | Verifiable image/SBOM/release provenance | MISSING | Attestation verification and complete evidence manifest |
| LR-013 | P0 | Isolated production-equivalent Engine Staging | MISSING | Environment/config/deployment report |
| LR-014 | P0 | Approved performance/burst/soak thresholds pass | MISSING | Signed load report with p95/p99/error/resource values |
| LR-015 | P0 | Monitoring, alerts, owner, retention, observation window | MISSING | Alert tests, dashboard links/IDs, on-call record |
| LR-016 | P0 | Rollback rehearsal succeeds | MISSING | Previous digest, timestamps, RTO, post-rollback smokes |
| LR-017 | P0 | Public domain maps to approved Engine artifact | MISSING | DNS/TLS/service binding, `/build`, OpenAPI SHA, Lunar smoke |
| LR-018 | P0 | Portal mirror contains exact approved Lunar contract | MISSING | Portal contract SHA and authority/live-diff checks |
| LR-019 | P0 | Portal explicitly allowlists and presents Lunar V2 | MISSING | Catalog/navigation/flag tests |
| LR-020 | P0 | Direct/BFF/browser Lunar proof blocks release and cannot skip | MISSING | Required green release-candidate check with zero skips |
| LR-021 | P1; P0 if promised | Product quota claims match real enforcement | MISSING | Contract/copy alignment or implemented quota evidence |
| LR-022 | P0 | Ordered two-repository promotion and compatibility rollback | MISSING | Engine-first/portal-second rehearsal and rollback matrix |

## Implementation phases and task state

| Task | Objective | Engine-repo status on 2026-07-22 | Next owner/action |
|---|---|---|---|
| TASK-001 | Freeze two-repository baseline and disposition stale work | PARTIAL: Engine SHAs recorded; PR #6/#16 closed; Portal/live deployment IDs missing | Portal/Platform export remaining heads, tags, runs, deployment IDs |
| TASK-002 | Converge delivery on canonical `main` | PARTIAL: `main` fast-forwarded to `master`; default still `master`; Railway unknown | Repository admin changes default; Platform changes Railway source; verify `/build` |
| TASK-003 | Enforce branch rules and release identity | BLOCKED external | Repository admin/Security configure ruleset and least-privilege token |
| TASK-004 | Close Swiss Ephemeris license gate | BLOCKED external | Legal/Product provide approval ID and permitted-use scope |
| TASK-005 | Approve precision, range, and version policy | BLOCKED external | Astronomy owner and Product owner approve explicit values |
| TASK-006 | Resolve merged review findings | IN PROGRESS: Python 3.10 compatibility patched; readiness/version closure still gated | Engine maintainer completes ADR/OpenAPI/version work after approvals |
| TASK-007 | Create exact Engine RC | BLOCKED by TASK-002..006 | Release owner creates bounded RC only after gates close |
| TASK-008 | Build/attest immutable Engine image | BLOCKED by RC and registry/platform decision | Platform/Security add pinned workflow and verify attestation |
| TASK-009 | Provision isolated Engine Staging | BLOCKED external | Platform deploys exact digest with Redis and SWIEPH |
| TASK-010 | Direct security/contract/failure-boundary tests | BLOCKED by Staging | QA/Security execute real HTTP matrix |
| TASK-011 | Performance, burst, and soak tests | BLOCKED by thresholds and Staging | Product/SRE approve numbers; QA executes |
| TASK-012 | Observability and on-call proof | BLOCKED external | SRE configures and tests alerts/dashboards |
| TASK-013 | Engine rollback rehearsal | BLOCKED by immutable deployments | Platform/SRE restore previous digest and record RTO |
| TASK-014 | Bind and verify public Engine domain | BLOCKED by approved artifact | Platform verifies DNS/TLS/service/OpenAPI/build identity |
| TASK-015 | Sync Portal to approved Engine contract | BLOCKED by approved live/RC contract | Portal maintainer syncs exact SHA and makes drift fail closed |
| TASK-016 | Explicit Lunar V2 catalog/navigation behind flag | BLOCKED by Portal work and Product copy | Portal maintainer adds allowlist, category, flag, tests |
| TASK-017 | Prove BFF V2 forwarding/validation | BLOCKED by Portal mirror | Portal maintainer adds exact-path and negative tests |
| TASK-018 | Make live Lunar proof release-blocking | BLOCKED by Staging credentials and workflow settings | Portal/QA add non-skippable direct/BFF/browser job |
| TASK-019 | Deploy and verify Portal Staging | BLOCKED by TASK-015..018 | Platform/Portal deploy immutable artifact and run browser proof |
| TASK-020 | Promote Engine | BLOCKED by LR-001..LR-016 | Release owner promotes exact digest only |
| TASK-021 | Promote Portal and close pipeline | BLOCKED by Engine production observation | Release owner enables approved Portal artifact and closes ledger |

## Smallest robust implementation slice

The only implementation slice authorized before external approvals is:

1. Freeze and validate the repository-local gate state.
2. Remove stale PR ambiguity and safely synchronize `main` with `master` without force-push.
3. Fix source-level defects that do not infer missing policy values.
4. Add fail-closed machine validation: `RELEASE` is invalid whenever a mandatory gate is not `CLOSED`.
5. Open a bounded PR and use CI as integration evidence. Do not merge or tag based solely on local/source evidence.

## Required validation sequence after external gates close

### Engine

- Frozen dependency install and Python 3.10/3.11/3.12 full test suite with locked SWIEPH.
- Focused Lunar, readiness, runtime-config, release-evidence, workflow-contract, security, distribution, Docker, OpenAPI, and codegen checks.
- Exact image digest, CycloneDX SBOM, and independently verified provenance.
- Staging direct HTTP matrix, dependency failure injection, approved load profiles, alerts, and rollback rehearsal.

### Portal

- Exact Engine OpenAPI SHA sync.
- Explicit allowlisted V2 Lunar catalog and feature flag.
- BFF request validation and exact V2 forwarding tests.
- Non-skippable direct Engine, BFF, and Playwright browser tests without mocks.

### Production

1. Promote Engine digest.
2. Verify public `/build`, `/ready`, OpenAPI SHA, auth/error cases, and Lunar reference request.
3. Observe Engine-only window.
4. Promote Portal artifact with Lunar flag on.
5. Run full browser-to-SWIEPH smoke and joint observation window.
6. Change evidence decision from `BLOCKED` to `RELEASE` only after every mandatory gate is closed.

## Rollback order

1. Disable Lunar or restore the previous Portal artifact.
2. Restore the previous Engine digest if required.
3. Verify `/build`, `/ready`, auth, contract, and reference smoke.
4. Record deployment IDs, timestamps, recovery time, and final state without secrets.

## Release decision

**BLOCKED.** Branch-content convergence is complete, but default-branch cutover and the external legal, domain, release-identity, staging, performance, observability, public-domain, portal, promotion, and rollback gates are not evidenced. No tag, release, image promotion, DNS cutover, or production-final claim is authorized by this plan state.
