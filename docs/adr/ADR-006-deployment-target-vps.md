# ADR-006: Deployment target for the Lunar engine is the Hostinger VPS only

- Status: accepted
- Date: 2026-10-19
- Decided by: Product Owner (Ben), answer "alles VPS" to REC-2026-10-18-01
- Related: TASK-002 (`docs/runbooks/default-branch-migration.md`), LR-001, FUF-107, Confluence ETBZ page 60784641

## Context

Repository documentation said "Railway deploys master" and "Railway is the sole deployment
target". The reconcile run of 2026-10-18 read the runtimes back:

- The only reachable live engine is the Docker container on the Hostinger VPS,
  `https://srv1308064.hstgr.cloud/lunar` (nginx `/lunar/` → `127.0.0.1:8110`). It reported
  engine label `1.0.0-rc1-20260220`, no `source_revision` in `/build`, and OpenAPI SHA-256
  `6c1db67207b4df71c9ee1a06d20458bede518962ba0a619788efade2d8ffc8da`.
- That container is rebuilt from an exact source SHA behind explicit human gates
  (ETBZ page 60784641: Gate A for an isolated candidate, Gate B for the cutover).
- `bafe-production.up.railway.app`, `fufireapilive-production.up.railway.app` and
  `api.fufire.space` returned Railway's `Application not found` edge 404, identical to a
  made-up `*.up.railway.app` host.

## Decision

1. The Hostinger VPS is the only deployment target for the Lunar engine. Railway is not a
   deployment target.
2. Deployment is not branch-driven. A merge or push to any branch deploys nothing.
   Promotion runs through the ETBZ human gates and is verified by readback of `/health`,
   `/ready`, `/build` and the live OpenAPI hash.
3. TASK-002 phase B has no runtime step. Only the GitHub default-branch switch remains.

## Consequences

- `CLAUDE.md`, `README.md` and the TASK-002 runbook describe the VPS as the target.
- LR-001 closure evidence no longer includes a Railway source export.
- Railway remnants remain in the repository and are a separate cleanup slice, because some
  of them are contract artifacts:
  - `bazi_engine/openapi_ext.py` publishes `https://bafe-production.up.railway.app` as a
    production server in the generated OpenAPI (contract change, needs regeneration and
    codegen survival);
  - `railway.toml`, `CNAME` and `.claude/commands/bafe-deploy.md`;
  - Railway wording in code comments (`config_guard.py`, `auth.py`, `key_store.py`,
    `app.py`) and in ADR-002 and ADR-004.
  - `/build` keeps its provider-neutral `source_revision` detection; Railway is one
    recognised provider there and needs no change.
- The public domain binding (FUF-107, `api.fufire.space`) must point at the VPS, not at a
  Railway service. That is an infrastructure task outside this repository.
- The VPS currently runs pre-#45 code without the TLST fixes #56–#64. Bringing them live
  requires the ETBZ Gate B cutover; this ADR does not authorize it.

## Revisit when

A second runtime (for example a managed platform for staging) is proposed. That needs a new
ADR; it must not be inferred from `railway.toml` or from CI success.
