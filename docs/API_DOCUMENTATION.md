# FuFirE API — Complete Reference

**Engine build:** `1.0.0-rc1-20260220` · **Verified live:** 2026-07-25 against
`https://api.fufire.space` and `https://astro.fufire.space`.

Every status code, header and payload below was captured from the running
services, not read off a spec file. Where the deployed behaviour and the
documentation disagree, this file follows the deployment and says so.

---

## 1. Two services, one product

```
                      ┌──────────────────────────────────────────┐
  Browser / SPA  ───►  │  BFF   astro.fufire.space                │
  Customer code  ───►  │  Node + Express, serves the SPA too      │
                      │  API base: /api/v1  (NOT /v1)            │
                      └───────────────┬──────────────────────────┘
                                      │ injects the single shared
                                      │ enterprise key, upstream
                                      ▼
                      ┌──────────────────────────────────────────┐
                      │  Engine  api.fufire.space                │
                      │  Python + FastAPI + Swiss Ephemeris      │
                      │  API base: /v1  (legacy alias: unprefixed)│
                      └──────────────────────────────────────────┘
                                      │
                      ┌───────────────┴──────────────────────────┐
                      │  Supabase  ykoijifgweoapitabgxx          │
                      │  public.api_keys — customer key plane    │
                      └──────────────────────────────────────────┘
```

| | Engine | BFF |
|---|---|---|
| Host | `api.fufire.space` | `astro.fufire.space` |
| Repo | `DYAI2025/FUFIRE_API_lunar` (public) | `DYAI2025/FuFire_API_LIVE` (private) |
| Base path | `/v1/…` | `/api/v1/…` |
| Auth | `X-API-Key: ff_<tier>_<hex>` | `Authorization: Bearer ff_live_<base62>` (optional today — see §7.1) |
| Paths | 69 | 22 |

**The `/api/v1` prefix is load-bearing.** `astro.fufire.space/v1/anything`
returns HTTP 200 with the SPA's `index.html`, not JSON — the SPA catch-all
serves it. A client that probes the wrong base sees a "successful" HTML
response and fails on parse. Only `/api/v1/*` reaches the BFF API.

---

## 2. Authentication

### 2.1 Engine (`api.fufire.space`)

Header: `X-API-Key`. Two independent validators, checked in order:

1. **Static env list** — `FUFIRE_API_KEYS`, comma-separated, compared with
   `hmac.compare_digest` in constant time.
2. **KeyStore** — only when `KEY_STORE_BACKEND` is set. Production currently
   runs `memory`, which is not durable (§7.2).

The tier is resolved from, in precedence order: the `FUFIRE_KEY_TIER_OVERRIDES`
env map → the key's `ff_<tier>_` prefix → the KeyStore → `free`.

| Prefix | Tier | Req/day | Req/min | Product name |
|---|---|---|---|---|
| `ff_free_` | free | 100 | 5 | Test |
| `ff_starter_` | starter | 1 000 | 20 | Standard |
| `ff_pro_` | pro | 10 000 | 100 | Premium |
| `ff_enterprise_` | enterprise | unlimited | unlimited | *internal only — never sold* |

> **`requests_per_day` is declared but enforced nowhere.** `TIER_LIMITS` in
> `bazi_engine/auth.py` carries the value; no code reads it. Only the per-minute
> limit is applied, via slowapi. The engine's own OpenAPI description states
> this honestly: *"Daily quota metering is planned but not yet [implemented]."*

**Dev-mode bypass.** With an empty `FUFIRE_API_KEYS` **and** no KeyStore, the
engine authenticates every request as a `dev` tier pseudo-key and logs
`auth.dev_mode`. `FUFIRE_REQUIRE_API_KEYS=true` turns that path into a `503`
instead, and `FUFIRE_ENV=production` makes the process refuse to boot at all
(`config_guard.assert_production_auth_config`). All three are set correctly in
production.

### 2.2 BFF (`astro.fufire.space`)

Customer keys are `ff_live_<40 base62 chars>` — a different format from the
engine's.

> **The BFF does NOT read `X-API-Key`.** `presentedCredential()` in
> `src/server/dev-key-auth.ts` looks at exactly two places, in order:
>
> 1. `Authorization: Bearer ff_live_…`
> 2. `customKey` in the JSON body
>
> A customer key sent as `X-API-Key` is **silently ignored** — the request then
> falls through to the anonymous path (§7.1) and is served with the shared
> enterprise key. It looks like the key worked; it did not. This trap is the
> single easiest way to be billed nothing and enforce nothing.

Lookup path (`src/server/dev-key-auth.ts`):

```
Authorization: Bearer ff_live_…  ─┐
   (or body.customKey)            ├─► sha256(secret) ──► RPC lookup_active_api_key(hash)
                                  ┘                        │
                    valid ◄────────────────────────────────  revoked_at IS NULL
                                                           OR revoked_at > now()  ← DB clock
```

The customer key is **never forwarded upstream**. On success the BFF strips it
from every channel and substitutes its own `FUFIRE_API_KEY`. Both the key body
and the `customKey` field are dropped, so the secret cannot leak upstream even
if a caller tries to smuggle it.

A key that carries the `ff_live_` prefix but is unknown, revoked or past its
grace window yields `401` with **zero** upstream calls — it never silently
falls through to the shared key. A request with **no** `ff_live_` prefix at all
does fall through (§7.1).

> Until PR #95, that `401` was in practice a **`500 auth_lookup_failed`**: the
> Supabase client could not even be constructed on Node 20 (§7.0), so the lookup
> never ran. Fail-closed, so nothing leaked — but the observable status was
> wrong.

### 2.3 Admin token

`X-Admin-Token` gates `POST /v1/admin/keys` on the engine. That endpoint is
**retired** (§7.3) and answers `404` regardless of the token.

---

## 3. Standard response contract

### 3.1 Headers on every engine response

| Header | Example | Notes |
|---|---|---|
| `X-Request-ID` | `16734037-70fd-…` | UUID; a client-supplied value is echoed. Must be a valid UUID or it is replaced. |
| `X-API-Version` | `1.0.0-rc1-20260220` | Engine build label. |
| `X-Response-Time-ms` | `3.75` | Server processing time. |
| `X-RateLimit-Limit` | `unlimited` | Per-minute allowance for the key's tier. |
| `X-RateLimit-Remaining` | *(often absent)* | Written by slowapi only on limited routes. **Do not treat absence as "no quota left".** |
| `X-Content-Type-Options` | `nosniff` | |
| `X-Frame-Options` | `DENY` | |

### 3.2 Error envelope

Every engine error uses one shape. Captured live:

```json
{
  "error": "unauthorized",
  "message": "Missing or invalid X-API-Key header",
  "detail": {},
  "status": 401,
  "path": "/v1/calculate/bazi",
  "timestamp": "2026-07-25T17:30:54.548606Z",
  "request_id": "77364c7b-7a1f-4e95-b042-5674cdec268c"
}
```

Validation errors put the failures in `detail.errors`:

```json
{
  "error": "validation_error",
  "message": "Request validation failed",
  "detail": { "errors": [
    { "type": "missing", "loc": ["body", "date"], "msg": "Field required" }
  ]},
  "status": 422,
  "path": "/v1/calculate/bazi",
  "timestamp": "2026-07-25T17:30:54.640783Z",
  "request_id": "90afeee1-a546-45d6-a750-4db1687f20da"
}
```

| Status | `error` | Cause |
|---|---|---|
| 400 | `tier_not_allowed` | Requested a tier the endpoint may not issue. |
| 401 | `unauthorized` | Missing/invalid `X-API-Key`. |
| 404 | `feature_disabled` | Route exists but its feature flag is off. `detail.feature` names it. |
| 422 | `validation_error` | Body failed schema validation. |
| 429 | *rate limited* | Per-minute tier limit exceeded. `Retry-After: 60`. |
| 500 | `internal_error` | Unhandled. Never carries internals. |
| 503 | `auth_configuration_error` · `issuance_not_configured` | Server misconfiguration, stated honestly rather than faked. |

**The BFF uses a different envelope** — RFC 7807 `application/problem+json`:

```json
{
  "type": "https://fufire.dev/problems/invalid_request",
  "title": "invalid_request",
  "status": 400,
  "detail": "email, name, and company are required.",
  "error": "invalid_request",
  "message": "email, name, and company are required.",
  "requestId": "71e5e22d-…"
}
```

A client talking to both services must handle both shapes. `error` and
`message` are present in both, so keying on those is the portable path.

---

## 4. Engine endpoints (`api.fufire.space`)

Every path is mounted **twice** — at `/v1/<path>` (the authenticated public
surface) and unprefixed at `/<path>` (legacy). New integrations use `/v1`
exclusively. Exceptions: `/v1/match/bazi-hehun` and `/v1/admin/*` are `/v1`-only;
`/api/chart` is legacy-only.

### 4.1 Public — no key required

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{status, engine, version, dependencies{ephemeris, rate_limiter}}` |
| GET | `/ready` | Readiness probe. |
| GET | `/build` | Build metadata (gated by `EXPOSE_BUILD_METADATA`). |
| GET | `/api` · `/` | Service descriptor. |
| GET | `/info/wuxing-mapping` | Static Wu-Xing reference table. |
| GET | `/openapi.json` | The full OpenAPI 3.1 document (69 paths). |

Live `/health`:

```json
{
  "status": "healthy",
  "engine": "FuFirE",
  "version": "1.0.0-rc1-20260220",
  "dependencies": {
    "ephemeris":    { "status": "ok", "required": true,  "detail": null },
    "rate_limiter": { "status": "ok", "required": false, "detail": "type=memory" }
  }
}
```

> `rate_limiter.detail = "type=memory"` is the field to watch: per-process
> counters, reset on every deploy (§7.4).

### 4.2 BaZi (Four Pillars)

#### `POST /v1/calculate/bazi`

The core endpoint. Request (`BaziRequest`):

| Field | Type | Req | Default | Notes |
|---|---|:--:|---|---|
| `date` | string | ✅ | — | Local ISO-8601, e.g. `2024-02-10T14:30:00`. **No offset** — `tz` supplies it. |
| `tz` | string | | `Europe/Berlin` | IANA name. |
| `lon` | number | | `13.405` | Degrees, east positive. |
| `lat` | number | | `52.52` | Degrees, north positive. |
| `standard` | `CIVIL`\|`LMT`\|`TLST` | | `CIVIL` | Time model. `TLST` = true local solar time. |
| `boundary` | `midnight`\|`zi` | | `midnight` | Day-boundary convention. |
| `ambiguousTime` | `earlier`\|`later` | | `earlier` | DST fall-back resolution. |
| `nonexistentTime` | `error`\|`shift_forward` | | `error` | DST spring-forward gap. |
| `birth_time_known` | boolean | | `true` | `false` marks hour-dependent output provisional. |
| `include_trace` | boolean | | `true` | `false` nulls `derivation_trace` — a much smaller payload. |

Response (`BaziResponse`), captured live:

```json
{
  "input": { "date": "2024-02-10T14:30:00", "tz": "Europe/Berlin",
             "lon": 13.405, "lat": 52.52, "standard": "CIVIL",
             "boundary": "midnight", "ambiguousTime": "earlier",
             "nonexistentTime": "error", "birth_time_known": true },
  "pillars": {
    "year":  { "stamm": "Jia", "zweig": "Chen", "tier": "Drache", "element": "Holz" },
    "month": { "stamm": "Bing","zweig": "Yin",  "tier": "Tiger",  "element": "Feuer" },
    "day":   { "stamm": "Jia", "zweig": "Chen", "tier": "Drache", "element": "Holz" },
    "hour":  { "stamm": "Xin", "zweig": "Wei",  "tier": "Ziege",  "element": "Metall" }
  },
  "chinese": { "year": { "stem": "Jia", "branch": "Chen", "animal": "Dragon" },
               "month_master": "Bing", "day_master": "Jia", "hour_master": "Xin" },
  "dates":   { "birth_local": "2024-02-10T14:30:00+01:00",
               "birth_utc":   "2024-02-10T13:30:00+00:00",
               "lichun_local":"2024-02-04T09:27:07.702993+01:00" },
  "transition": { "solar_year": 2024, "is_before_lichun": false,
                  "lichun_year_start": "2024-02-04T09:27:07.702993+01:00",
                  "lichun_next": "2025-02-03T…" },
  "solar_terms_count": 24,
  "provenance":    { "engine_version": "…", "ruleset_id": "…", "ephemeris_id": "…",
                     "tzdb_version_id": "…", "house_system": "…", "zodiac_mode": "…",
                     "computation_timestamp": "…" },
  "quality_flags": { "ephemeris_mode": "SWIEPH", "chart_type_quality": "exact" },
  "precision":     { "birth_time_known": true, "provisional_fields": [] },
  "derivation_trace": { }
}
```

**Mixed-language payload.** `pillars` uses German keys (`stamm`, `zweig`,
`tier`, `element`) with German values (`Drache`, `Holz`); the parallel `chinese`
block uses English (`stem`, `branch`, `animal` → `Dragon`). Both describe the
same pillars. This is frozen contract — downstream consumers depend on it — so
map it in your client rather than expecting it to change.

Other BaZi routes share `BaziRequest`:

| Path | Purpose |
|---|---|
| `POST /v1/calculate/bazi/trace` | Same, with the full step-by-step derivation. |
| `POST /v1/calculate/bazi/wuxing` | Wu-Xing distribution from the four pillars → `BaziWuXingResponse`. |
| `POST /v1/calculate/bazi/natal` | `NatalRequest` — `date`/`tz`/`lat`/`lon` **all required**, no defaults. |
| `POST /v1/calculate/bazi/dayun` | Decade luck cycles — see below. |

#### `POST /v1/calculate/bazi/dayun`

`DayunRequest` has stricter requirements and a conditional pair:

| Field | Type | Req | Notes |
|---|---|:--:|---|
| `date`, `tz`, `lat`, `lon` | | ✅ | All four mandatory. |
| `direction_method` | `explicit`\|`year_stem_yinyang_and_sex` | ✅ | Selects which of the next two is needed. |
| `flow_direction` | `forward`\|`backward` | ⚠️ | **Required iff** `direction_method="explicit"`. |
| `sex_at_birth` | `male`\|`female` | ⚠️ | **Required iff** `direction_method="year_stem_yinyang_and_sex"`. |
| `as_of_date` | string\|null | | Which decade counts as "current". Defaults to today (UTC). |
| `cycles` | integer | | Decades to return. Default `8`. |
| `boundary` | `midnight`\|`zi_hour` | | ⚠️ Note `zi_hour`, **not** `zi` as in `BaziRequest`. |
| `standard` | `CIVIL`\|`LMT`\|`TLST` | | |
| `start_age_method` | string | | Only `three_days_one_year` is implemented. |

> Two inconsistencies to code around: the `boundary` enum differs from every
> other endpoint (`zi_hour` vs `zi`), and the conditional requirement is not
> expressible in JSON Schema, so a wrong combination fails at runtime with 422
> rather than being caught by a generated client.

### 4.3 Western astrology

#### `POST /v1/calculate/western`

`WesternRequest` = `BaziRequest` minus `standard`/`boundary`/`include_trace`,
plus `zodiac_mode` (default `tropical`).

`WesternResponse`: `jd_ut`, `house_system`, `bodies`, `houses`, `angles`,
`aspects[]`, `house_quality`, `quality_flags`, `provenance`, `precision`.
`houses` and `angles` are `null` when `birth_time_known=false` — without a
birth time the ascendant and house cusps are undefined, and the API returns
null rather than a fabricated value.

| Path | Request | Purpose |
|---|---|---|
| `POST /v1/calculate/wuxing` | `WxRequest` | Wu-Xing vector from **western planetary** positions. |
| `POST /v1/calculate/fusion` | `FusionRequest` | Combines both systems (below). |
| `POST /v1/calculate/fusion/vector-map` | `VectorMapRequest` | Visual sector mapping. |
| `POST /v2/astronomy/lunar-state` | `LunarStateRequest` | Lunar phase/position. Note: **`/v2`**. |

#### `POST /v1/calculate/fusion`

`FusionRequest` requires `date`, `lon`, `lat`. Optional `bazi_pillars` skips
recomputation if you already hold them.

`FusionResponse`: `wu_xing_vectors`, `harmony_index`, `elemental_comparison`,
`cosmic_state` (number), `fusion_interpretation` (prose), plus optional
`calibration` and `contribution_ledger`, and the standard provenance trio.

### 4.4 Time

#### `POST /v1/calculate/tst` — True Solar Time

`TSTRequest`: `date` ✅, `lon` ✅, `tz`, DST policy fields. No latitude.

```json
{
  "input": { },
  "civil_time_hours": 14.5,
  "longitude_correction_hours": -0.106,
  "equation_of_time_hours": -0.234,
  "true_solar_time_hours": 14.16,
  "true_solar_time_formatted": "14:09:36",
  "provenance": { }
}
```

`POST /v1/chronometry/resolve` (beta) — `ChronometryResolveRequest{birth}` →
resolved instant across time scales.

### 4.5 Transit — the live sky

| Method | Path | Auth | Request |
|---|---|:--:|---|
| GET | `/v1/transit/now` | ✅ | query params |
| GET | `/v1/transit/timeline` | ✅ | query params |
| POST | `/v1/transit/state` | ✅ | `TransitStateRequest{soulprint_sectors[], quiz_sectors[]}` |
| POST | `/v1/transit/narrative` | ✅ | `NarrativeRequest{transit_state}` |

`TransitNowResponse`: `computed_at`, `planets`, `sector_intensity[]`,
`quality_flags`, `provenance`. Results are cached in a `TTLCache` with a
**one-hour TTL** (ADR-1) — two calls in the same hour return the identical
`computed_at`. That is intended, not a staleness bug.

### 4.6 Experience & dashboard

| Path | Request | Notes |
|---|---|---|
| `POST /v1/experience/bootstrap` | `BootstrapRequest{birth, locale}` | First-run payload. |
| `POST /v1/experience/daily` | `DailyRequest` | Requires `birth`, `soulprint_sectors[]`, `quiz_sectors[]`, `target_date`. |
| `POST /v1/experience/signature-delta` | `SignatureDeltaRequest` | Requires `soulprint_sectors[]`, `signature_blueprint`, `quiz_answer`. |
| `POST /v1/impact/active` | `ImpactRequest{birth, …}` | Dashboard impact engine. |

`ImpactResponse` is the dashboard's contract: `harmony_index`, `day_mode`
(`calm`\|`active`\|`tense`\|`pulse`), `intensity`, `active_planets[]`,
`space_weather` + `space_weather_score`, `drivers[]`, `resonance_badges[]`,
`top_sector` and `day_master` (both a Wu-Xing element), `evidence`, and a
`partial` flag. **Check `partial`** — `true` means a dependency (typically
space weather) was unavailable and the response is degraded but still served.

`BirthData` (used by impact) and `BirthInput` (used by experience) are *not*
the same schema: `BirthInput` requires `time` and adds `place_label` and
`birth_time_known`; `BirthData` has `time` optional.

### 4.7 Geocoding & personalisation

```http
POST /v1/geocode
{ "place": "Berlin, DE", "language": "de" }
→ { "lat": 52.52, "lon": 13.405, "resolved_name": "Berlin",
    "confidence": 0.95, "timezone": "Europe/Berlin", "country_code": "DE" }
```

`POST /v1/personalize` aggregates bazi + western + fusion + geocode.
`PersonalizeRequest` accepts **either** `place` **or** the `lat`+`lon`+`tz`
triple — mutually exclusive. Note `PersonalizeResponse` has **no required
fields**: every one is nullable, and `issues[]` / `caveats[]` explain what could
not be computed. Treat it as best-effort by design.

### 4.8 Matching

`POST /v1/match/bazi-hehun` — `/v1`-only by DECISION-001, deliberately breaking
the dual-mount idiom. `MatchRequest{mode, person_a, person_b, options}` where
each person is a `MatchPersonInput` (a `BaziRequest` plus optional
`gender: male|female|divers`).

`MatchResponse` is the largest payload in the API: `meta`, `request_context`,
`subjects`, `individual`, `pair`, `raw_analysis_text[]`, `warnings[]`,
`evidence_ledger[]`, `relationship_context`, `provenance`, `quality_flags`,
`precision`, `safety_and_language_policy`, `missing_and_blockers[]`.

### 4.9 Contract validation

`POST /v1/validate` — JSON Schema Draft-07 conformance checking.
`ValidateRequest` requires only `engine_config`; everything else
(`birth_event`, `ruleset_id` or `ruleset_inline`, `refdata_pack_id`,
various `*_override` fields, `validate_level: BASIC|FULL`) is optional.
Schemas live in `spec/schemas/`.

### 4.10 Retired / gated

| Path | State |
|---|---|
| `POST /v1/admin/keys` | **404 `feature_disabled`** — ADR-004. See §7.3. |
| `/v1/calculate/zwds`, `/v1/metadata/zwds/*` | Gated behind `FUFIRE_ENABLE_ZWDS`; production also demands `FUFIRE_ZWDS_SIGNOFF_ID`. |
| `/internal/api/webhooks/*` | HMAC-only, `include_in_schema=False`. Not part of the public contract. |

---

## 5. BFF endpoints (`astro.fufire.space/api/v1`)

### 5.1 Proxy — the money path

```http
POST /api/v1/proxy
Content-Type: application/json
X-API-Key: ff_live_<secret>        ← see §7.1: currently optional

{ "path": "/v1/calculate/bazi",
  "method": "POST",
  "body": { "date": "2024-02-10T14:30:00", "tz": "Europe/Berlin",
            "lon": 13.405, "lat": 52.52 } }
```

The upstream response body is returned **verbatim** — not wrapped. Provenance
travels in headers so neither the success shape nor the problem+json error
shape is mutated:

| Header | Meaning |
|---|---|
| `X-Upstream-Status` | The **real** upstream status, even when the BFF rewrites it (5xx → 502). Absent when no upstream call happened. |
| `X-Upstream-Latency-Ms` | Round-trip, integer ms. |
| `X-Endpoint-Provenance` | The upstream path the call resolved to. |
| `X-Owner-Id` | The key owner's UUID — only on an authenticated dev-key call. |
| `X-Request-Id` | Correlation. |

Security properties worth knowing as an integrator:

- **Path traversal is rejected before any upstream contact.** Dot segments and
  percent-encoded dots (`%2e`) fail closed. The reason is specific: the
  templated matcher compiles `{param}` to `[^/]+`, which also matches `..`, so
  `/v1/profile/../chart` would be *validated* against the profile schema but
  *forwarded* as `/v1/chart` after undici normalisation — a validate-X /
  forward-Y bypass.
- **CRLF in `path` is handled.** A control character in a provenance header
  value would make `res.setHeader` throw inside an async Express 4 handler,
  which does not route to error middleware — the request would hang until
  socket timeout. Such paths skip the header instead.
- **Request bodies are validated against the upstream contract** before
  forwarding, so a malformed body fails fast at the edge.

### 5.2 Key issuance — the double opt-in flow

```
POST /api/v1/keys/request      →  signed token, confirmation email
        │                          (no key issued yet)
        ▼   user clicks link
GET  /api/v1/keys/confirm?token=…
        │
        ├─ fresh    → mint into Supabase → email the key → 302 /key-confirmed.html
        ├─ re-click → recognise the jti  → NO email      → 302 /key-already-confirmed.html
        └─ failure  →                                    → 302 /key-error.html
```

#### `POST /api/v1/keys/request`

```json
{ "email": "dev@acme.test", "name": "Dev Person", "company": "Acme Corp",
  "usecase": "BaZi integration", "expectedCalls": "Under 5,000 / mo",
  "newsletterOptin": true }
```

| Status | Body | Meaning |
|---|---|---|
| 200 | `{status:"confirmation_sent"}` | Email dispatched. |
| 200 | `{status:"preview"}` | Email delivery not configured — **nothing was sent**, stated plainly rather than faked. |
| 400 | `invalid_request` | `email`, `name` and `company` are all required. |
| 502 | `email_send_failed` | Send failed; no false success. |
| 503 | `misconfigured` | `CONFIRM_TOKEN_SECRET` or `APP_URL` missing. `APP_URL` is mandatory in production so the confirm link can never be derived from spoofable headers. |

#### `GET /api/v1/keys/confirm?token=…`

Always a `302`, never a JSON body — **the key is only ever delivered by email
and never appears in a URL or on a page.**

Idempotency runs on `api_keys.jti`. A re-clicked link does **not** re-send:
keys are stored as SHA-256 only, so no plaintext can be reproduced, and
re-minting would hand one requester unlimited keys. That case redirects to
`/key-already-confirmed.html`, which says no new key was created and no email
was sent — `/key-confirmed.html` promises an inbound email and would be a lie.

The issued tier is **pinned to `free` in code**, never read from the request.
Defence in depth: `isConfirmPayload()` rejects any token whose `tier` is not
`"free"`, so even a leaked `CONFIRM_TOKEN_SECRET` cannot self-mint a paid key.

### 5.3 Key management (dashboard)

All four require a Supabase session (`Authorization: Bearer <jwt>`), validated
server-side via `supabase.auth.getUser(jwt)` — never a locally decoded token.
RLS, not application filtering, is the ownership boundary.

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/keys/list` | Metadata only. Returns `{keys[], rate_limit}`; `rate_limit` text is derived from the real limiter config so it cannot drift. |
| POST | `/api/v1/keys/create` | `{name}` → **201** with the plaintext `secret`, shown **once**, plus the row metadata. |
| POST | `/api/v1/keys/rotate` | `{id}` → new reveal-once key; the old one enters a **24-hour grace window**. |
| POST | `/api/v1/keys/revoke` | `{id}` → immediate. `revoked_at = now()` on the DB clock. |

`LIST_COLUMNS` = `id, name, key_prefix, created_at, last_used_at, status, request_count`.
The hash is never returned. `request_count` is an exact, unthrottled lifetime
count of authorised calls; `last_used_at` is throttled to ~5 minutes to avoid
one UPDATE per request.

| Status | Meaning |
|---|---|
| 401 `auth_error` | No/invalid session. The body includes `keys: []` so a client never confuses "signed out" with "you have zero keys". |
| 409 `key_collision` | `key_hash` UNIQUE violation — surfaced loudly rather than creating a second authenticating row. |
| 503 `supabase_unavailable` | Supabase not configured. |

### 5.4 Organisations (REQ-035)

| Method | Path | Notes |
|---|---|---|
| POST | `/api/v1/orgs` | Creator's `owner` membership is pinned server-side, never taken from the client. |
| GET | `/api/v1/orgs` | Orgs the caller belongs to. |
| GET | `/api/v1/orgs/:id/members` | |
| POST | `/api/v1/orgs/:id/invite` | Owner only. HMAC-signed token delivered only by email. |
| POST/GET | `/api/v1/orgs/accept` | Requires a **confirmed** email matching the invite; role pinned from the invite row. |

Orgs are a free grouping for shared key management — not seats, not billing.

### 5.5 Info & content

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/version` | `{name, version, commit, node}` |
| GET | `/api/v1/status` | Live upstream probe: `{status, message, latency, statusCode, lastChecked}` |
| GET | `/api/v1/config-status` | `{fufire_url, openapi, schema_contract_healthy, llm_provider, lead_adapter}` — booleans only, never values |
| GET | `/api/v1/openapi.json` | The upstream engine contract |
| GET | `/api/v1/bff-openapi.json` | The BFF's own contract |
| GET | `/llms.txt` | Machine-readable API summary for LLM agents |
| GET | `/docs` | Scalar API reference |
| POST | `/api/v1/explain` · `/api/v1/horoscope` | LLM-backed prose (Gemini) |
| GET | `/api/v1/transit` | Convenience transit read |

`GET /api/v1/status` live: `{"status":"Operational","latency":28,"statusCode":200}`.

---

## 6. Dependencies

### 6.1 Runtime

| Dependency | Used by | Failure mode |
|---|---|---|
| **Swiss Ephemeris** (`sepl_18.se1`, `semo_18.se1`, `seas_18.se1`, `seplm06.se1`) | Engine, all astronomy | `/health.dependencies.ephemeris` degrades. Falls back to Moshier (`MOSEPH`) — production forbids this via `EPHEMERIS_MODE=SWIEPH`. SHA-256 verified at Docker build. |
| **Supabase** `ykoijifgweoapitabgxx` | BFF key plane | `503 supabase_unavailable`, fail-closed. |
| **Brevo** | Confirmation + key emails | `502 email_send_failed`. Unconfigured → honest `{status:"preview"}`. |
| **Gemini** (`gemini-2.5-flash`) | `/explain`, `/horoscope` | Those two endpoints only. |
| **Redis** | Engine rate limiting | **Not configured** (§7.4). |
| **tzdata ≥ 2026.2** | Pinned so `_detect_tzdb_version()` can never report `"unknown"`. |

### 6.2 Database — `public.api_keys`

| Column | Notes |
|---|---|
| `id` uuid PK | |
| `user_id` uuid → `auth.users` | Cascade delete. |
| `name` text | 1–100 chars. |
| `key_prefix` text | First 8 chars of the random body. Display only. |
| `key_hash` text UNIQUE | `^[0-9a-f]{64}$`. SHA-256 of the full secret, no KDF, no salt — justified by ≥190 bits of entropy (ADR-002). |
| `tier` text | `free`\|`starter`\|`pro`. `enterprise` excluded by CHECK. |
| `jti` text UNIQUE | Email-flow idempotency. NULL for dashboard keys. |
| `status` text | `active`\|`rotated`\|`revoked`. |
| `revoked_at` timestamptz | The single expiry the auth path reads. Revoke → `now()`; rotate → `now() + 24h`. |
| `request_count` bigint | Exact lifetime authorised-call count. |
| `last_used_at` timestamptz | ~5-minute throttle. |
| `org_id` uuid | NULL = personal key. |

**Validity is always `revoked_at IS NULL OR revoked_at > now()`, evaluated on
the database clock** — never a JS `Date.now()`. A skewed application clock must
not be able to keep a revoked key alive or kill one still in its grace window.
The `key_hash` index is deliberately unconditional: a partial
`WHERE revoked_at IS NULL` would miss grace-window keys and silently break
rotation.

RLS is enabled **and forced** on all four tables. `anon` has no privileges
(§7.5). Keyless hot-path RPCs (`lookup_active_api_key`,
`touch_api_key_last_used`, `bump_api_key_usage`) are `service_role`-only.

---

## 7. Critical issues — current state

Ordered by impact. All verified live on 2026-07-25.

### 7.0 🔴 One unauthenticated request killed the BFF *(fixed, PR #95)*

```console
$ curl -s -o /dev/null -w '%{http_code}\n' \
    https://astro.fufire.space/api/v1/keys/list \
    -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJib2d1cyJ9.notreal"
502
```

`502 Application failed to respond` — the process died and the container
restarted. No valid credential was required; any bearer token did it.

From the production stack trace:

```
Error: Node.js 20 detected without native WebSocket support.
    at new RealtimeClient → createClient → userClient → requireUser
```

`@supabase/supabase-js` constructs a `RealtimeClient` inside every
`createClient()`, and `realtime-js` throws when the runtime has no global
`WebSocket`. That global landed in Node 22; the image is `node:20-slim`. The
throw escaped an async Express 4 handler — which does not route rejections to
error middleware — became an unhandled rejection, and Node exited.

The whole Supabase key plane was therefore non-functional in production: the
`ff_live_` dev-key path returned `500 auth_lookup_failed` (that one is caught),
and the dashboard routes crashed the process.

**1400 green tests missed it because tests run on Node 24, where the global
exists.** The regression test now deletes `globalThis.WebSocket` so the guard
holds on any Node version.

Fixed by supplying `ws` as the realtime transport (version-independent), plus
an `asyncRoute()` wrapper so a future throw degrades one request rather than
dropping the process. Node 20 is also EOL since April 2026 — moving to
`node:22-slim` is tracked separately.

### 7.1 🔴 The proxy is open to the internet

```console
$ curl -s -o /dev/null -w '%{http_code}\n' -X POST \
    https://astro.fufire.space/api/v1/proxy \
    -H 'content-type: application/json' \
    -d '{"path":"/v1/calculate/bazi","body":{"date":"2024-02-10T14:30:00",
         "tz":"Europe/Berlin","lon":13.405,"lat":52.52}}'
200
```

No key. Full engine access. The `devKeyAuth` middleware only challenges
requests that present an `ff_live_`-prefixed key; anything without that prefix
falls through by design (AC-032.7) and receives the shared **enterprise-tier**
upstream key. The only brake is an in-process IP limiter at **30 requests /
60 s**, which is per-instance and resets on deploy.

This is intentional for the landing page's live tester, but it means the paid
tiers are not enforceable while it stands: any customer can bypass their own
quota by calling `/api/v1/proxy` anonymously. **Fix before selling tiers** —
either require a key on `/proxy` and give the public tester its own narrow,
separately-limited route, or cap the anonymous path to a demo subset.

### 7.2 🔴 Engine-issued keys do not survive a deploy

`KEY_STORE_BACKEND=memory` in production. The store is a process-local dict.
Every key it ever issued is gone at the next restart. Combined with §7.3 the
engine currently issues nothing, so no live customer key is affected — but the
setting must not be left in place if the engine plane is ever re-enabled.

### 7.3 🔴 Engine key issuance is retired — and the flow still pointed at it

```console
$ curl -s -X POST https://api.fufire.space/v1/admin/keys \
    -H "X-Admin-Token: …" -H 'content-type: application/json' \
    -d '{"tier":"free","label":"probe","jti":"probe-1"}'
{"error":"feature_disabled","message":"This API capability is not enabled.",
 "detail":{"feature":"key_issuance"},"status":404,…}
```

ADR-004 (2026-07-21) retired the engine key plane: the route is `deprecated`,
gated behind `FUFIRE_ENABLE_KEY_ISSUANCE`, and `config_guard` makes the engine
**refuse to boot** in production if that flag is truthy.

The BFF's `/keys/confirm` still POSTed that endpoint, so every confirm click
redirected to `/key-error.html` — no user could obtain a key by any route, while
the landing page continued inviting them to request one. **Fixed** on branch
`feat/supabase-key-plane-issuance`: issuance now writes to the Supabase plane.

### 7.4 🟠 Rate limits are per-process and reset on deploy

`/health` reports `rate_limiter: {"detail": "type=memory"}`. No `REDIS_URL` is
set on either service. Consequences:

- Counters are per-instance. With more than one replica the effective limit is
  N × the configured value.
- Every deploy resets all counters.
- `X-RateLimit-Remaining` is often absent; the engine's own OpenAPI description
  admits the value "reflects the full tier limit" rather than a real count.
- `requests_per_day` is never enforced at all (§2.1).

`limiter.py` already refuses to silently fall back when Redis is *required*
(`FUFIRE_REQUIRE_REDIS`, or `FUFIRE_REPLICA_COUNT > 1`). Production runs one
replica, so it boots — but a scale-up without Redis will fail startup by
design. ADR-004 records this as *"implemented; Railway values MISSING"*.

### 7.5 🟠 Supabase grants were wider than designed *(fixed)*

Rolling the migrations onto hosted Supabase revealed that `REVOKE … FROM PUBLIC`
does not withhold EXECUTE from `anon`/`authenticated` there — the platform
grants those roles EXECUTE (and blanket table DML) *explicitly*, so a
PUBLIC-level revoke is a no-op against them. Measured immediately after:

```
anon EXECUTE on all 7 RPCs                     → true   (incl. lookup_active_api_key)
anon SELECT/INSERT/UPDATE/DELETE on 4 tables   → true
```

Nothing leaked — RLS is enabled *and forced* with no `anon` policy, so reads
returned zero rows and writes were denied; the two SECURITY DEFINER org RPCs
raise on a null `auth.uid()`. But RLS was the *only* barrier rather than the
last one. Closed by two per-role migrations. Verified at the HTTP boundary:

```
anon    GET /rest/v1/api_keys → 401 permission denied for table api_keys
service GET /rest/v1/api_keys → 200
```

### 7.6 🟠 A live enterprise key was committed to a public repository *(rotated)*

`ff_enterprise_5b6052…` sat in plaintext at
`docs/plans/2026-04-06-superglue-proxy-endpoints.md:486` in the **public**
`DYAI2025/FUFIRE_API_lunar`. Enterprise tier has no per-minute cap, so it
granted effectively unlimited access, and it was still valid when found.

Rotated 2026-07-25 zero-downtime: engine accepts `old,new` → BFF switches to
`new` → engine drops `old`. Verified: old key `401`, new key authenticates,
BFF proxy `200`. A `tests/test_no_committed_secrets.py` guard now scans every
git-tracked file. **Still open:** the dead key remains in git history; a
`filter-repo` purge has not been run.

### 7.7 🟡 Documentation points at a host that does not resolve

The key-delivery email and `llms.txt` tell developers to call
`https://api.fufire.dev/v1/calculate/bazi`. That domain **does not resolve**
(`curl` → `000`). The working hosts are `api.fufire.space` (engine) and
`astro.fufire.space/api/v1` (BFF). Every customer following the email lands on
a connection error.

### 7.8 🟡 Two API bases, one of which fails silently

`astro.fufire.space/v1/*` returns **200 with the SPA's HTML**, because the SPA
catch-all serves it. A client that guesses the engine's `/v1` convention on the
BFF host gets a success status and an HTML body. Only `/api/v1/*` is the BFF
API. Explicit routes (`/llms.txt`, `/docs`, the legal and key pages) are
registered *before* the catch-all specifically to avoid this shadowing — the
mechanism is sound; the trap is for callers who guess the base path.

### 7.9 🟡 Schema inconsistencies that break generated clients

| Where | Issue |
|---|---|
| `DayunRequest.boundary` | `zi_hour`, while every other endpoint uses `zi`. |
| `DayunRequest` | `flow_direction`/`sex_at_birth` are conditionally required on `direction_method` — not expressible in JSON Schema, so a generated client compiles and then 422s at runtime. |
| `BaziResponse.pillars` | German keys and values; the sibling `chinese` block is English. |
| `BirthData` vs `BirthInput` | Different required fields for the same concept, used by neighbouring endpoint families. |
| `PersonalizeResponse` | No required fields at all; everything nullable. |
| `/v2/astronomy/lunar-state` | The only `/v2` path in an otherwise `/v1` API. |

### 7.10 🟡 Two pre-existing test failures on the BFF

`npm audit --omit=dev` reports a HIGH/CRITICAL and an unresolved MODERATE
against the real lockfile. Present on `master` before any of this work; the
suite is otherwise 1381 passing.

---

## 8. Quick start

```bash
# 1. Request a key (double opt-in — you will get an email)
curl -X POST https://astro.fufire.space/api/v1/keys/request \
  -H 'content-type: application/json' \
  -d '{"email":"you@example.com","name":"Your Name","company":"Your Co",
       "usecase":"BaZi integration","expectedCalls":"Under 5,000 / mo",
       "newsletterOptin":false}'

# 2. Click the link in the email. The key arrives in a second email.
#    It is shown once and is never recoverable — store it immediately.

# 3. Call the engine directly
curl -X POST https://api.fufire.space/v1/calculate/bazi \
  -H "X-API-Key: $FUFIRE_API_KEY" \
  -H 'content-type: application/json' \
  -d '{"date":"2024-02-10T14:30:00","tz":"Europe/Berlin",
       "lon":13.405,"lat":52.52}'

# …or through the BFF proxy.
# NOTE the header: the BFF reads Authorization, NOT X-API-Key. A key sent as
# X-API-Key is ignored and the call is served anonymously (§2.2, §7.1).
curl -X POST https://astro.fufire.space/api/v1/proxy \
  -H "Authorization: Bearer $FUFIRE_LIVE_KEY" \
  -H 'content-type: application/json' \
  -d '{"path":"/v1/calculate/bazi","body":{"date":"2024-02-10T14:30:00",
       "tz":"Europe/Berlin","lon":13.405,"lat":52.52}}'
```

**Integration checklist**

1. Use `/v1/*` on `api.fufire.space`, `/api/v1/*` on `astro.fufire.space`. Never mix.
2. Different auth headers per host: `X-API-Key` on the engine,
   `Authorization: Bearer` on the BFF. Sending the BFF an `X-API-Key` does not
   fail — it is ignored, and you get an anonymous response that looks fine.
3. Send `date` as a local ISO-8601 string with **no** offset; `tz` carries the zone.
4. Handle `422` by reading `detail.errors[].loc` — it names the exact field path.
5. Handle both error envelopes (engine: flat JSON; BFF: `problem+json`).
6. Log `X-Request-ID` on every call. It is the only correlation handle in support.
7. Set `include_trace: false` unless you need the derivation — payloads shrink a lot.
8. Check `quality_flags.ephemeris_mode`: `MOSEPH` means degraded precision.
9. Check `precision.provisional_fields[]` when `birth_time_known` is false.
10. Do not build on `X-RateLimit-Remaining` until Redis lands (§7.4).
11. Treat a key as write-once: only a hash is stored, so it can never be resent.

---

## 9. Maintenance

`spec/openapi/openapi.json` in the engine repo is the source of truth.

```bash
python scripts/export_openapi.py           # regenerate after any endpoint change
python scripts/export_openapi.py --check   # CI drift gate
```

Adding an endpoint = one `Mount(...)` row in `bazi_engine/routers/registry.py`,
which mounts it at both `/<path>` and `/v1/<path>`. Full checklist in
`docs/adding-an-endpoint.md`.

**Endpoints are frozen.** Paths and response structures must not change —
downstream services depend on them. Additive changes only.

Customer-facing claims are machine-bound to proving tests in
`docs/governance/claims.json`, enforced by `npm run test:claims` as a blocking
predeploy step. Renaming a proof test fails the gate — deliberately.
