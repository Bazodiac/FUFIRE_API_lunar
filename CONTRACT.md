# CONTRACT.md — BaZi Engine API Contract

## Source of Truth

**`spec/openapi/openapi.json`** is the API contract. All integrations (clients, code generators, documentation) derive from this file.

> The implementation must conform to the OpenAPI spec — not the other way around.

## Contract Artifacts

| Artifact | Path | Format |
|----------|------|--------|
| OpenAPI Spec | `spec/openapi/openapi.json` | OpenAPI 3.1 (JSON) |
| ValidateRequest Schema | `spec/schemas/ValidateRequest.schema.json` | JSON Schema Draft-07 |
| ValidateResponse Schema | `spec/schemas/ValidateResponse.schema.json` | JSON Schema Draft-07 |
| BaZi Ruleset | `spec/rulesets/standard_bazi_2026.json` | Custom JSON |

## Versioning

- `info.version` in OpenAPI is coupled to `bazi_engine.__version__`
- Version format: `MAJOR.MINOR.PATCH-prerelease-YYYYMMDD`
- Current: `1.0.0-rc1-20260220`

## CI Drift Prevention

The CI pipeline includes an **OpenAPI drift check**:

```bash
python scripts/export_openapi.py --check
```

This regenerates the spec from `app.openapi()` and fails if it differs from the committed version. Any endpoint or schema change requires an explicit spec update:

```bash
python scripts/export_openapi.py   # Regenerate
git diff spec/openapi/             # Review changes
```

## Endpoints (Frozen)

All endpoints are mounted twice: once at the legacy unprefixed path and once at `/v1/*` (API-key-authenticated public surface). The table below shows unique logical endpoints; each exists at both `<path>` and `/v1<path>` unless noted.

### Info / Utility (no API key required)

| Method | Path | Response |
|--------|------|----------|
| GET | `/` | `RootResponse` |
| GET | `/health` | `HealthResponse` |
| GET | `/ready` | `ReadyResponse` |
| GET | `/build` | `BuildResponse` |
| GET | `/api` | `ApiResponse` |
| GET | `/info/wuxing-mapping` | `WuxingMappingResponse` |

#### Runtime source identity on `GET /build`

`BuildResponse` carries a provider-neutral, immutable identity of the build that
is answering, so a consumer can attest WHICH source revision it talked to:

| Field | Meaning |
|---|---|
| `source_revision` | 40 lower-case hex git object id, or `null`. Never a version, tag or date. |
| `source_revision_provider` | `northflank` \| `railway` \| `null` |
| `source_revision_kind` | `deployment_git_sha` \| `null` |
| `source_revision_status` | `available` \| `unavailable` \| `invalid` \| `ambiguous` |

The value is read only from a variable the deployment platform injects itself
(`NF_DEPLOYMENT_SHA`, `RAILWAY_GIT_COMMIT_SHA`); an application-owned environment
value can never produce one. It is reported unconditionally — deployment
provenance is not infrastructure detail — while the Railway/Fly deploy
identifiers stay behind `EXPOSE_BUILD_METADATA`. One platform's SHA is never
published under another platform's field name. Fail-closed states
(`unavailable`, `invalid`, `ambiguous`) carry no revision at all.

### Calculation (v1 — API key required)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/calculate/bazi` | `BaziRequest` | `BaziResponse` |
| POST | `/calculate/bazi/natal` | `NatalRequest` (`schemas/calculate/bazi/natal.request.schema.json`) | `NatalResponse` (`schemas/calculate/bazi/natal.response.schema.json`; errors: `natal.error.schema.json`) |
| POST | `/calculate/western` | `WesternRequest` | `WesternResponse` |
| POST | `/calculate/fusion` | `FusionRequest` | `FusionResponse` |
| POST | `/calculate/wuxing` | `WxRequest` | `WxResponse` |
| POST | `/calculate/tst` | `TSTRequest` | `TSTResponse` |
| POST | `/validate` | `ValidateRequest` (Draft-07) | `ValidateResponse` (Draft-07) |

### Transit (v1 — API key required)

| Method | Path | Response |
|--------|------|----------|
| GET | `/transit/now` | `TransitNowResponse` |
| GET | `/transit/timeline` | `TransitTimelineResponse` |
| POST | `/transit/state` | `TransitStateResponse` |
| POST | `/transit/narrative` | `TransitNarrativeResponse` |

### Experience (v1 — API key required)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/experience/bootstrap` | `BootstrapRequest` | `BootstrapResponse` |
| POST | `/experience/daily` | `DailyRequest` | `DailyResponse` |
| POST | `/experience/signature-delta` | `SignatureDeltaRequest` | `SignatureDeltaResponse` |

### Impact (v1 — API key required)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/impact/active` | `ImpactRequest` | `ImpactActiveResponse` |

### Superglue Proxy (API key required)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/profile` | Mirrors Superglue profile endpoint |
| GET | `/api/profile/{user_id}` | Profile by user ID |
| GET | `/api/daily` | Daily forecast via Superglue |
| GET | `/api/daily/{user_id}` | Daily forecast for user |
| POST | `/api/profile/{user_id}/chart` | Chart generation via Superglue |

### Chart & Webhooks (legacy paths only)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/chart` | `ChartRequest` | `ChartResponse` |
| POST | `/internal/api/webhooks/chart` | `ElevenLabsChartRequest` | `WebhookChartResponse` |

### Astronomy V2 (API key required)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| POST | `/v2/astronomy/lunar-state` | `LunarStateRequest` | `LunarStateResponse` |

The lunar-state contract is V2-only. It has no unversioned or `/v1` alias and
does not modify any frozen V1 calculation or response shape.

## Error Responses

All endpoints use the `ErrorEnvelope` schema for error responses:

```json
{
  "error": "error_code",
  "message": "Human-readable message",
  "detail": {}
}
```

Standard HTTP codes: `422` (input), `500` (internal), `503` (ephemeris unavailable), `501` (not supported).

## `/validate` Endpoint — Dual Schema Model

The `/validate` endpoint uses **JSON Schema Draft-07** for runtime validation (via `jsonschema.Draft7Validator`), while the same schemas are **referenced in OpenAPI** for documentation and codegen. This is intentional:

- Runtime: Draft-07 (`spec/schemas/*.schema.json`)
- Documentation: Embedded in OpenAPI `components.schemas` (Draft-07 meta-keys stripped)
- Future: Draft-07 → 2020-12 migration is a Phase 2 concern
