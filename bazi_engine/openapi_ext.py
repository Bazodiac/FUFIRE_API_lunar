"""
openapi_ext.py — OpenAPI post-processing extracted from app.py (Phase 3, Task 3.21).

Pure move: patches the generated OpenAPI schema with contract schemas and
shared metadata. Single public entry point: ``install_custom_openapi(app)``.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from bazi_engine.resource_loader import load_json_object_resource

_DESCRIPTION = """\
FuFirE (**Fusion Firmament Engine**) is a deterministic, astronomically precise calculation engine
for **BaZi (Four Pillars of Destiny)** and **Western Astrology** with **Wu-Xing fusion**.

## Authentication

`/v1/*` and `/v2/*` business endpoints require an API key passed via the `X-API-Key` header.

```
X-API-Key: ff_pro_<your-secret>
```

Keys are **tier-based** — the key prefix encodes the tier:

| Key prefix | Tier | Requests/min |
|---|---|---|
| `ff_free_` | free | 5 |
| `ff_starter_` | starter | 20 |
| `ff_pro_` | pro | 100 |
| `ff_enterprise_` | enterprise | unlimited (safety cap: 10 000/min) |

Public endpoints (`/v1/health`, `/v1/ready`, `/v1/build`, `/v1/api`, `/v1/info/*`) require no key.

## Rate Limiting

Per-minute tier limits are enforced per API key. Daily quota metering is planned but not yet
implemented — until it ships, only the per-minute limits above are enforced. Responses include:

- `X-RateLimit-Limit` — requests allowed per minute for the key's tier
- `X-RateLimit-Remaining` — remaining requests in the current minute window (present only when a
  Redis backend is active; in-memory mode may omit this header)

When the limit is exceeded the API returns **HTTP 429** with `Retry-After: 60`.

## Standard Response Headers

Every response carries:

- `X-Request-ID` — UUID correlation ID (client-provided value is echoed when present)
- `X-API-Version` — engine build version
- `X-Response-Time-ms` — server processing time in milliseconds

## Error Envelope

All error responses use a consistent JSON envelope:

```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "detail": {},
  "status": 422,
  "path": "/v1/<endpoint-path>",
  "timestamp": "<ISO-8601 timestamp>",
  "request_id": "<UUIDv4 request id>"
}
```
"""


def _openapi_tags() -> list[dict[str, str]]:
    return [
        {"name": "Info", "description": "Health checks, build info, and public metadata endpoints. No API key required."},
        {"name": "BaZi", "description": "Four Pillars of Destiny (BaZi) calculation. Returns Year/Month/Day/Hour pillars based on precise solar-term boundaries using Swiss Ephemeris."},
        {"name": "BaZi Trace (beta)", "description": "BETA — BaZi calculation with the full derivation trace always attached. Thin alias for /calculate/bazi (forces include_trace=true); reuses the same engine and trace builder, exposing the real trace shape {year, month, day, hour, time_resolution, provenance_ids}."},
        {"name": "Western Astrology", "description": "Western planetary positions, house cusps, aspects, and angles. Supports tropical and sidereal zodiac systems with automatic house system fallback for extreme latitudes."},
        {"name": "Fusion / Wu-Xing", "description": "Wu-Xing (Five Elements) fusion analysis combining BaZi and Western astrology. Includes Harmony Index, elemental vectors, True Solar Time, and equation-of-time corrections."},
        {"name": "Fusion Vector-Map (beta)", "description": "BETA — Wu-Xing fusion vector inspection: exposes the deterministic fusion engine as three views per system (raw / sum_l1 / l2_cosine, German element keys) plus harmony components (elemental_overlap_h = dot of sum_l1 vectors; cosine_similarity = the engine's cosmic_state). No new metaphysical math; trig_coherence is intentionally deferred. Numbers equal the in-process calculation exactly."},
        {"name": "Transit", "description": "Real-time and historical planetary transit snapshots, timelines, state analysis, and narrative generation."},
        {"name": "Dayun", "description": "Luck pillars (Da Yun / 大運): decade-long fortune cycles derived from the natal month pillar and birth-time direction."},
        {"name": "Natal", "description": "Natal per-pillar analysis for a single birth chart: hidden stems (with Qi roles and weights), Ten Gods relative to the day master (pillar stems and hidden stems), and the month command (Yue Ling). Purely additive exposure of facts the engine already computes internally; no seasonal-strength, day-master-strength or rooting derivation is emitted (unsourced — never fabricated)."},
        {"name": "Experience", "description": "Consumer-facing experience endpoints: daily forecasts, bootstrap payloads, and signature-delta calculations for app integrations."},
        {"name": "Validation", "description": "Contract-first validation against JSON Schema Draft-07 rulesets. Validates engine configurations, reference data policies, and time models."},
        {"name": "Chart", "description": "Chart rendering and ElevenLabs agent webhook integration."},
        {"name": "Webhooks", "description": "Webhook endpoints for third-party agent integrations (ElevenLabs)."},
        {"name": "Impact", "description": "Active-planet natal impact calculations (PRD P0-3 dashboard). Returns active planets, harmony index, and BaZi resonance for the current moment."},
        {"name": "Superglue", "description": "Proxy endpoints for ElevenLabs/Bazodiac frontend integration. Mirrors profile, daily, and chart endpoints through the Superglue gateway."},
        {"name": "Admin", "description": "Administrative key-management endpoints. Requires elevated API credentials."},
        {"name": "Chronometry (beta)", "description": "BETA — Time/ephemeris inspection: resolves a birth instant into Julian Day, ΔT, equation of time, longitude correction, true solar time, live solar longitude, the corresponding solar term, and Li Chun boundary flags. Exposes the deterministic engine; numbers equal the in-process calculation exactly."},
        {"name": "Geocode", "description": "Place name → coordinates via the free Open-Meteo geocoding API. Returns lat/lon/timezone/country with a v1 confidence score, and fails loud (422 ambiguous_place) on ambiguous matches instead of silently picking the top hit."},
        {"name": "Personalize", "description": "Aggregates internal engine compute (geocoding, BaZi, Wu-Xing, BaZi trace, chronometry) into the flat prompt variables a downstream template needs (animal, element, birth_year, dominant_element) with provenance, issues, and verbatim caveats. Never invents data: a missing source yields a null variable plus a PROMPT_VARIABLE_SOURCE_MISSING issue. domain_extras carries the real bazi_trace and chronometry engine outputs."},
        {"name": "Hehun", "description": "Deterministic BaZi-Hehun pair-chart analysis (合婚). Returns raw, source-labelled facts — the three MVP pair layers (day-master comparison, spouse-palace/day-branch, Wu-Xing vector comparison), per-person individual analysis and an evidence ledger. No compatibility rating of any kind is computed or returned; server-side consent is required and birth data is never echoed or persisted."},
        {"name": "ZWDS", "description": "Zi Wei Dou Shu (紫微斗数) core-seed natal charts. Deterministic natal-chart computation (POST /calculate/zwds) and immutable, hash-locked ruleset metadata (GET /metadata/zwds/rulesets/{ruleset_id}). Source tables are core-seed (SOURCE_NEEDED) and not practitioner-reviewed — every response and metadata read advertises that a human domain review is still required."},
        {"name": "Astronomy v2", "description": "Canonical UTC/JD-rooted astronomy contracts. Lunar State returns geocentric Sun/Moon positions, physical phase metrics, true-new-moon events, and corrected phase-centred eight-phase classification without changing frozen V1 semantics."},
    ]


def _openapi_servers() -> list[dict[str, str]]:
    # Production server URLs — Railway (the old Fly.io deploy is decommissioned).
    return [
        {"url": "https://api.fufire.space", "description": "Production"},
        {"url": "https://bafe-production.up.railway.app", "description": "Production (Railway direct)"},
        {"url": "http://localhost:8080", "description": "Local development"},
    ]


def _standard_headers() -> dict[str, dict[str, Any]]:
    return {
        "X-Request-ID": {"description": "UUID correlation ID — client-provided value is echoed when present.", "schema": {"type": "string", "format": "uuid"}},
        "X-API-Version": {"description": "Engine build version.", "schema": {"type": "string"}},
        "X-Response-Time-ms": {"description": "Server processing time in milliseconds.", "schema": {"type": "string"}},
    }


def _quota_headers() -> dict[str, dict[str, Any]]:
    return {
        "X-RateLimit-Limit": {"description": "Requests per minute allowed for the key's tier. `unlimited` for enterprise.", "schema": {"type": "string"}},
        "X-RateLimit-Remaining": {"description": "Remaining quota in the current window. Currently reflects the full tier limit (persistent per-key counters are not yet implemented).", "schema": {"type": "string"}},
    }


def _http_methods() -> set[str]:
    return {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def _iter_openapi_operations(schema: dict[str, Any]):
    methods_filter = _http_methods()
    for path, methods in schema.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() in methods_filter and isinstance(op, dict):
                yield path, method.lower(), op


def _add_standard_response_headers(schema: dict[str, Any]) -> None:
    std_headers = _standard_headers()
    quota_headers = _quota_headers()
    for path, _method, op in _iter_openapi_operations(schema):
        for resp in op.get("responses", {}).values():
            if not isinstance(resp, dict):
                continue
            headers = resp.setdefault("headers", {})
            headers.update(std_headers)
            if path.startswith(("/v1/", "/v2/")):
                headers.update(quota_headers)


def _rewrite_refs(obj: Any) -> Any:
    """Recursively rewrite #/definitions/X → #/components/schemas/X."""
    if isinstance(obj, dict):
        return {
            k: (v.replace("#/definitions/", "#/components/schemas/") if k == "$ref" and isinstance(v, str) else _rewrite_refs(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_rewrite_refs(item) for item in obj]
    return obj


def _load_contract_schemas(schema: dict[str, Any]) -> dict[str, Any]:
    all_schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    for name in ("ValidateRequest", "ValidateResponse"):
        raw = load_json_object_resource(
            "bazi_engine.resources", "schemas", f"{name}.schema.json"
        )
        raw.pop("$schema", None)
        raw.pop("$id", None)
        for def_name, def_schema in raw.pop("definitions", {}).items():
            all_schemas.setdefault(def_name, _rewrite_refs(def_schema))
        all_schemas[name] = _rewrite_refs(raw)
    return all_schemas


def _patch_validate_routes(schema: dict[str, Any]) -> None:
    validate_responses = {
        "200": {"description": "Validation result", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ValidateResponse"}}}},
        "422": {"description": "Request schema violation", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}}},
        "500": {"description": "Internal validation error", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}}},
    }
    request_body = {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ValidateRequest"}}},
    }
    for route in ("/validate", "/v1/validate"):
        validate_path = schema.get("paths", {}).get(route, {}).get("post")
        if validate_path:
            validate_path["requestBody"] = request_body
            validate_path["responses"] = validate_responses


def _add_response_examples(all_schemas: dict[str, Any]) -> None:
    examples = {
        "HealthResponse": {"status": "ok", "version": "1.0.0-rc2-20261016"},
        "ErrorEnvelope": {
            "error": "validation_error",
            "message": "Request validation failed",
            "detail": {},
            "status": 422,
            "path": "/v1/calculate/bazi",
            "timestamp": "2026-03-17T00:00:00Z",
            "request_id": "550e8400-e29b-41d4-a716-446655440000",
        },
    }
    for schema_name, example in examples.items():
        if schema_name in all_schemas:
            all_schemas[schema_name]["example"] = example


def _patch_error_envelope_schema(schema: dict[str, Any]) -> None:
    all_schemas = schema.setdefault("components", {}).setdefault("schemas", {})
    err_raw = load_json_object_resource(
        "bazi_engine.resources", "schemas", "ErrorEnvelope.schema.json"
    )
    err_raw.pop("$schema", None)
    err_raw.pop("$id", None)
    err_raw.pop("examples", None)
    if "example" in all_schemas.get("ErrorEnvelope", {}):
        err_raw["example"] = all_schemas["ErrorEnvelope"]["example"]
    all_schemas["ErrorEnvelope"] = err_raw


def _common_error_responses() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    ref = {"$ref": "#/components/schemas/ErrorEnvelope"}
    common = {
        "401": {"description": "Unauthorized — missing or invalid API key", "content": {"application/json": {"schema": ref}}},
        "429": {"description": "Too Many Requests — rate limit exceeded", "content": {"application/json": {"schema": ref}}},
        "500": {"description": "Internal Server Error", "content": {"application/json": {"schema": ref}}},
        "503": {"description": "Service Unavailable — ephemeris or external dependency not configured", "content": {"application/json": {"schema": ref}}},
    }
    override_422 = {"description": "Request validation error", "content": {"application/json": {"schema": ref}}}
    return common, override_422


def _operation_is_protected(op: dict[str, Any]) -> bool:
    return bool(op.get("security")) or any(
        isinstance(p, dict) and p.get("name") == "X-API-Key"
        for p in op.get("parameters", [])
    )


def _inject_common_error_responses(schema: dict[str, Any]) -> None:
    common, override_422 = _common_error_responses()
    for _path, _method, op in _iter_openapi_operations(schema):
        responses = op.setdefault("responses", {})
        if _operation_is_protected(op):
            for code, resp_obj in common.items():
                responses.setdefault(code, dict(resp_obj))
            responses["422"] = dict(override_422)
        elif "422" in responses:
            responses["422"] = dict(override_422)


def _deprecate_legacy_operations(schema: dict[str, Any]) -> None:
    """Legacy surface: the unversioned twin of every /v1 route is
    deprecated — clients must use /v1. Marked here (schema layer)
    so ALL routers inherit it without per-route decorators.

    Rule: every operation outside "/" and the /v1 family is deprecated.
    The landingpage repo mirrors this fail-closed
    (tests/unit/openapi-legacy-deprecated.test.ts).
    """
    for path, _method, op in _iter_openapi_operations(schema):
        if path != "/" and not path.startswith(("/v1", "/v2")):
            op["deprecated"] = True


def install_custom_openapi(app: FastAPI) -> None:
    """Install the customized OpenAPI generator on ``app`` (sets ``app.openapi``)."""

    def _custom_openapi():
        """Patch generated OpenAPI with contract schemas and shared metadata."""
        if app.openapi_schema:
            return app.openapi_schema

        from fastapi.openapi.utils import get_openapi

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
            contact={"name": "FuFirE Support", "url": "https://github.com/DYAI2025/FuFirE"},
            license_info={"name": "Proprietary", "identifier": "LicenseRef-proprietary"},
        )
        schema["tags"] = _openapi_tags()
        schema["servers"] = _openapi_servers()
        _add_standard_response_headers(schema)

        all_schemas = _load_contract_schemas(schema)
        _patch_validate_routes(schema)
        _add_response_examples(all_schemas)
        _patch_error_envelope_schema(schema)
        _inject_common_error_responses(schema)
        _deprecate_legacy_operations(schema)

        app.openapi_schema = schema
        return schema

    app.openapi = _custom_openapi  # type: ignore[method-assign]
