# FuFirE API Reference

> **Fusion Firmament Engine** — Deterministic BaZi + Western Astrology + Wu-Xing Fusion  
> Version: `1.0.0-rc1-20260220` | Base URL: `https://bafe-2u0e2a.fly.dev`  
> Last updated: 2026-03-28

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Authentication](#2-authentication)
3. [Quick Start](#3-quick-start)
4. [Standard Headers](#4-standard-headers)
5. [Error Handling](#5-error-handling)
6. [Endpoints](#6-endpoints)
   - [Info](#61-info-endpoints)
   - [BaZi](#62-bazi-four-pillars)
   - [Western Astrology](#63-western-astrology)
   - [Fusion / Wu-Xing](#64-fusion--wu-xing)
   - [Transit](#65-transit)
   - [Experience](#66-experience)
   - [Chart](#67-chart-combined)
   - [Webhooks](#68-webhooks)
   - [Validation](#69-validation)
   - [Astronomy V2](#610-astronomy-v2)
7. [Data Models](#7-data-models)
8. [Rate Limiting](#8-rate-limiting)
9. [Changelog](#9-changelog)

---

## 1. Introduction

FuFirE is a deterministic astronomical calculation engine that combines:

- **BaZi (四柱命理)** — Four Pillars of Destiny using Swiss Ephemeris solar-term boundaries
- **Western Astrology** — 14 celestial bodies, house systems, aspects
- **Wu-Xing Fusion (五行)** — Five-Element vector mathematics unifying both systems

All calculations are pure, reproducible, and astronomically precise. No randomness, no AI hallucination — the same input always produces the same output.

### Base URLs

| Environment | URL |
|-------------|-----|
| Production | `https://bafe-2u0e2a.fly.dev` |
| Local development | `http://localhost:8080` |

### Versioned vs Legacy Routes

| Route prefix | Auth required | Description |
|-------------|---------------|-------------|
| `/v1/*` | ✅ API key | Business endpoints — use these |
| `/v2/*` | ✅ API key | Additive contracts with explicitly revised semantics |
| `/*` (no prefix) | ⚠️ When `FUFIRE_REQUIRE_API_KEYS=true` | Legacy routes for backward compatibility — also protected when key enforcement is active |

---

## 2. Authentication

All `/v1/*` and `/v2/*` business endpoints require an API key via the `X-API-Key` header.

### Key Format

```
X-API-Key: ff_<tier>_<random>
```

The key prefix encodes the access tier:

| Prefix | Tier | Requests/day | Requests/min |
|--------|------|-------------|-------------|
| `ff_free_` | Free | 100 | 5 |
| `ff_starter_` | Starter | 1,000 | 20 |
| `ff_pro_` | Pro | 10,000 | 100 |
| `ff_enterprise_` | Enterprise | Unlimited | Unlimited |

### Example

```bash
curl -X POST https://bafe-2u0e2a.fly.dev/v1/calculate/bazi \
  -H "X-API-Key: ff_pro_a1b2c3d4e5" \
  -H "Content-Type: application/json" \
  -d '{"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 13.405, "lat": 52.52}'
```

### Authentication Errors

| Status | Error | Cause |
|--------|-------|-------|
| 401 | `unauthorized` | Missing or invalid `X-API-Key` header |

Public endpoints (`/v1/health`, `/v1/ready`, `/v1/build`, `/v1/api`, `/v1/info/*`) require **no API key**.

---

## 3. Quick Start

### Get your first BaZi chart in 30 seconds

```bash
# 1. Check the service is healthy
curl https://bafe-2u0e2a.fly.dev/v1/health

# 2. Calculate BaZi pillars
curl -X POST https://bafe-2u0e2a.fly.dev/v1/calculate/bazi \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "1990-06-15T14:30:00",
    "tz": "Europe/Berlin",
    "lon": 13.405,
    "lat": 52.52
  }'
```

### Python Example

```python
import requests

BASE = "https://bafe-2u0e2a.fly.dev/v1"
KEY = "ff_pro_your_key_here"
HEADERS = {"X-API-Key": KEY, "Content-Type": "application/json"}

birth = {
    "date": "1990-06-15T14:30:00",
    "tz": "Europe/Berlin",
    "lon": 13.405,
    "lat": 52.52,
}

# BaZi Four Pillars
bazi = requests.post(f"{BASE}/calculate/bazi", json=birth, headers=HEADERS).json()
print(f"Day Master: {bazi['chinese']['day_master']}")
print(f"Year Animal: {bazi['pillars']['year']['tier']}")

# Western Chart
western = requests.post(f"{BASE}/calculate/western", json=birth, headers=HEADERS).json()
sun_sign = western["bodies"]["Sun"]["zodiac_sign"]  # 0=Aries, 1=Taurus, ...
print(f"Sun Sign Index: {sun_sign}")

# Full Fusion Analysis
fusion = requests.post(f"{BASE}/calculate/fusion", json=birth, headers=HEADERS).json()
print(f"Harmony Index: {fusion['harmony_index']['harmony_index']:.2%}")
print(f"Calibrated H: {fusion['calibration']['h_calibrated']}")
```

### JavaScript/TypeScript Example

```typescript
const BASE = "https://bafe-2u0e2a.fly.dev/v1";
const KEY = "ff_pro_your_key_here";

const birth = {
  date: "1990-06-15T14:30:00",
  tz: "Europe/Berlin",
  lon: 13.405,
  lat: 52.52,
};

const response = await fetch(`${BASE}/calculate/fusion`, {
  method: "POST",
  headers: { "X-API-Key": KEY, "Content-Type": "application/json" },
  body: JSON.stringify(birth),
});

const fusion = await response.json();
console.log(`Harmony: ${(fusion.harmony_index.harmony_index * 100).toFixed(1)}%`);
console.log(`Dominant West: ${Object.entries(fusion.wu_xing_vectors.western_planets)
  .sort(([,a],[,b]) => b - a)[0][0]}`);
```

---

## 4. Standard Headers

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `X-API-Key` | `/v1/*` only | API key for authentication |
| `Content-Type` | POST | `application/json` |
| `X-Request-ID` | Optional | UUID — echoed back for tracing |

### Response Headers (every response)

| Header | Description | Example |
|--------|-------------|---------|
| `X-Request-ID` | Correlation ID (client-provided or generated) | `550e8400-e29b-41d4-a716-446655440000` |
| `X-API-Version` | Engine build version | `1.0.0-rc1-20260220` |
| `X-Response-Time-ms` | Server processing time | `42.17` |
| `X-Content-Type-Options` | Security hardening | `nosniff` |
| `Strict-Transport-Security` | HSTS | `max-age=31536000; includeSubDomains` |

### Rate Limit Headers (`/v1/*` only)

| Header | Description | Example |
|--------|-------------|---------|
| `X-RateLimit-Limit` | Max requests per minute for tier | `100` or `unlimited` |
| `X-RateLimit-Remaining` | Remaining requests in current window — present only when Redis backend is active (`REDIS_URL` set); omitted in in-memory mode | `87` |

---

## 5. Error Handling

All errors use a consistent JSON envelope:

```json
{
  "error": "input_error",
  "message": "Nonexistent local time: 2026-03-29T02:30:00 in Europe/Berlin (DST gap)",
  "detail": {
    "parameter": "date",
    "timezone": "Europe/Berlin"
  },
  "status": 422,
  "path": "/v1/calculate/bazi",
  "timestamp": "2026-03-28T14:23:07Z",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Error Codes

| Status | Error Code | Meaning |
|--------|-----------|---------|
| 401 | `unauthorized` | Missing or invalid `X-API-Key` header |
| 422 | `input_error` | Invalid input (DST gap, bad coordinates, malformed date) |
| 422 | `validation_error` | Request schema violation (Pydantic) |
| 429 | `rate_limit_exceeded` | Too many requests — includes `Retry-After: 60` header |
| 500 | `calculation_error` | Internal numerical failure (report this as a bug) |
| 500 | `internal_error` | Unhandled exception (never leaks internals) |
| 501 | `not_supported` | Requested feature not yet implemented |
| 503 | `ephemeris_unavailable` | Swiss Ephemeris files missing — temporary outage |

### DST Handling

Birth times during DST transitions require explicit disambiguation:

| Parameter | Values | Behavior |
|-----------|--------|----------|
| `ambiguousTime` | `earlier` (default), `later` | Fall-back: which clock occurrence to use |
| `nonexistentTime` | `error` (default), `shift_forward` | Spring-forward gap: reject or shift |

---

## 6. Endpoints

---

### 6.1 Info Endpoints

No authentication required.

#### `GET /` — Root

```bash
curl https://bafe-2u0e2a.fly.dev/
```

```json
{
  "status": "ok",
  "service": "fufire",
  "version": "1.0.0-rc1-20260220"
}
```

---

#### `GET /health` — Health Check

Returns per-dependency health: ephemeris + rate limiter.

```json
{
  "status": "healthy",
  "engine": "FuFirE",
  "version": "1.0.0-rc1-20260220",
  "dependencies": {
    "ephemeris": {"status": "ok", "detail": null},
    "rate_limiter": {"status": "ok", "detail": "type=redis"}
  }
}
```

| `status` value | Meaning |
|---------------|---------|
| `healthy` | All dependencies operational |
| `degraded` | One or more dependencies unavailable — results may be limited |

---

#### `GET /ready` — Readiness Probe

Same as `/health` but returns **503** when degraded. Use this for load balancer probes.

---

#### `GET /build` — Build Metadata

```json
{
  "version": "1.0.0-rc1-20260220",
  "source_revision": "c914d5671257b3c3ec279da76715a9338313b2e1",
  "source_revision_provider": "northflank",
  "source_revision_kind": "deployment_git_sha",
  "source_revision_status": "available",
  "fly_alloc_id": "abc123",
  "fly_region": "ams"
}
```

`source_revision` is the immutable git object id of the build that is answering,
read from the variable the deployment platform injects itself
(`NF_DEPLOYMENT_SHA` on Northflank, `RAILWAY_GIT_COMMIT_SHA` on Railway) — never
from an application-owned value. It is always reported. Anything that is not 40
lower-case hex characters is refused: `source_revision` stays `null` and
`source_revision_status` says why (`unavailable`, `invalid`, `ambiguous`). The
mutable `version` string is not an identity.

The Fly.io/Railway deploy identifiers (`fly_alloc_id`, `fly_region`,
`railway_commit_sha`, `railway_deploy_id`) are only exposed when
`EXPOSE_BUILD_METADATA=1`.

---

#### `GET /api` — Sun Sign Lookup (Legacy)

```bash
curl "https://bafe-2u0e2a.fly.dev/api?datum=1990-06-15&zeit=14:30&tz=Europe/Berlin"
```

```json
{
  "sonne": "Zwillinge",
  "input": {"datum": "1990-06-15", "zeit": "14:30", "ort": null, "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405}
}
```

---

#### `GET /info/wuxing-mapping` — Wu-Xing Planet Mapping

Returns the canonical planet-to-element mapping used by the fusion engine.

```json
{
  "mapping": {
    "Sun": "Feuer",
    "Moon": "Wasser",
    "Mercury": ["Erde", "Metall"],
    "Venus": "Metall",
    "Mars": "Feuer",
    "Jupiter": "Holz",
    "Saturn": "Erde",
    "Uranus": "Holz",
    "Neptune": "Wasser",
    "Pluto": "Feuer",
    "Chiron": "Wasser",
    "Lilith": "Wasser",
    "NorthNode": "Holz",
    "TrueNorthNode": "Holz"
  },
  "order": ["Holz", "Feuer", "Erde", "Metall", "Wasser"],
  "description": {
    "PLANET_TO_WUXING": "Western planet to Chinese element mapping",
    "WUXING_ORDER": "Wu Xing cycle order: Holz -> Feuer -> Erde -> Metall -> Wasser"
  }
}
```

---

### 6.2 BaZi (Four Pillars)

#### `POST /v1/calculate/bazi`

Compute Year, Month, Day, and Hour pillars using precise solar-term boundaries from Swiss Ephemeris.

**Request:**

```json
{
  "date": "1990-06-15T14:30:00",
  "tz": "Europe/Berlin",
  "lon": 13.405,
  "lat": 52.52,
  "standard": "CIVIL",
  "boundary": "midnight",
  "ambiguousTime": "earlier",
  "nonexistentTime": "error",
  "birth_time_known": true
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `date` | string | **required** | ISO 8601 local datetime |
| `tz` | string | `Europe/Berlin` | IANA timezone identifier |
| `lon` | float | 13.405 | Geographic longitude (°, east positive) |
| `lat` | float | 52.52 | Geographic latitude (°) |
| `standard` | `CIVIL` \| `LMT` | `CIVIL` | Time standard — LMT uses longitude-based local mean time |
| `boundary` | `midnight` \| `zi` | `midnight` | Day boundary convention (zi = 23:00 starts new day) |
| `ambiguousTime` | `earlier` \| `later` | `earlier` | DST fall-back disambiguation |
| `nonexistentTime` | `error` \| `shift_forward` | `error` | DST spring-forward handling |
| `birth_time_known` | bool | `true` | When `false`, hour pillar is flagged provisional |

**Response (200):**

```json
{
  "input": { "..." },
  "pillars": {
    "year":  {"stamm": "Geng", "zweig": "Wu", "tier": "Pferd", "element": "Metall"},
    "month": {"stamm": "Ren",  "zweig": "Wu", "tier": "Pferd", "element": "Wasser"},
    "day":   {"stamm": "Xin",  "zweig": "Hai","tier": "Schwein","element": "Metall"},
    "hour":  {"stamm": "Yi",   "zweig": "Wei","tier": "Ziege", "element": "Holz"}
  },
  "chinese": {
    "year": {"stem": "Geng", "branch": "Wu", "animal": "Pferd"},
    "month_master": "Ren",
    "day_master": "Xin",
    "hour_master": "Yi"
  },
  "dates": {
    "birth_local": "1990-06-15T14:30:00+02:00",
    "birth_utc": "1990-06-15T12:30:00+00:00",
    "lichun_local": "1990-02-04T03:14:45+01:00"
  },
  "transition": {
    "solar_year": 1990,
    "is_before_lichun": false,
    "lichun_year_start": "1990-02-04T03:14:45+01:00",
    "lichun_next": "1991-02-04T09:08:12+01:00"
  },
  "solar_terms_count": 24,
  "provenance": {
    "engine_version": "1.0.0-rc1-20260220",
    "parameter_set_id": "default_v1",
    "ruleset_id": "traditional_bazi_2026",
    "ephemeris_id": "swieph_sepl18",
    "tzdb_version_id": "2024b",
    "house_system": "placidus",
    "zodiac_mode": "tropical",
    "computation_timestamp": "2026-03-28T14:00:00Z",
    "parameter_set": { "...": "see Data Models" }
  },
  "precision": {
    "birth_time_known": true,
    "provisional_fields": []
  },
  "derivation_trace": {
    "year":  {"lichun_crossing_utc": "...", "is_before_lichun": false, "solar_longitude_lichun": 315.0},
    "month": {"jieqi_crossing_utc": "...", "solar_longitude_deg": 75.0, "month_branch_index": 5},
    "day":   {"julian_day_number": 2448085, "sexagenary_index": 14, "day_offset_used": 49},
    "hour":  {"local_hour": 14, "branch_index": 7, "true_solar_time_used": false}
  }
}
```

**cURL:**

```bash
curl -X POST https://bafe-2u0e2a.fly.dev/v1/calculate/bazi \
  -H "X-API-Key: ff_pro_your_key" \
  -H "Content-Type: application/json" \
  -d '{"date":"1990-06-15T14:30:00","tz":"Europe/Berlin","lon":13.405,"lat":52.52}'
```

---

### 6.3 Western Astrology

#### `POST /v1/calculate/western`

Planetary positions, house cusps, Ascendant/MC, and aspects using Swiss Ephemeris.

**Request:**

```json
{
  "date": "1990-06-15T14:30:00",
  "tz": "Europe/Berlin",
  "lon": 13.405,
  "lat": 52.52,
  "birth_time_known": true,
  "zodiac_mode": "tropical"
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `zodiac_mode` | string | `tropical` | `tropical`, `sidereal_lahiri`, `sidereal_fagan_bradley`, `sidereal_raman` |

**14 Celestial Bodies:** Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto, Chiron, Lilith, NorthNode, TrueNorthNode.

**Response (200):**

```json
{
  "jd_ut": 2448085.0208,
  "house_system": "P",
  "bodies": {
    "Sun": {
      "longitude": 84.23,
      "latitude": 0.0001,
      "speed": 0.957,
      "distance": 1.0157,
      "is_retrograde": false,
      "zodiac_sign": 2,
      "degree_in_sign": 24.23
    },
    "Moon": { "..." },
    "Mercury": { "..." }
  },
  "houses": {"1": 245.3, "2": 268.1, "...": "..."},
  "angles": {"Ascendant": 245.3, "MC": 172.8, "Vertex": 72.4},
  "aspects": [
    {
      "planet1": "Sun",
      "planet2": "Mars",
      "type": "conjunction",
      "angle": 3.2,
      "orb": 3.2,
      "exact_angle": 0.0,
      "effective_orb": 8.5
    }
  ],
  "house_quality": {
    "flag": "exact",
    "system": "placidus",
    "requested": "placidus",
    "reason": null
  },
  "provenance": { "...": "..." },
  "precision": {"birth_time_known": true, "provisional_fields": []}
}
```

**Aspect Orb Model (v1.1.0 — differentiated):**

Effective orb = `(base_orb_A + base_orb_B) / 2 × aspect_factor`

| Planet | Base Orb |
|--------|----------|
| Sun, Moon | 10° |
| Mercury, Venus, Mars | 7° |
| Jupiter, Saturn | 8° |
| Uranus, Neptune, Pluto | 5° |
| Chiron | 3° |
| Lilith, NorthNode, TrueNorthNode | 2–3° |

| Aspect | Factor |
|--------|--------|
| Conjunction, Trine, Opposition | ×1.0 |
| Square | ×0.875 |
| Sextile | ×0.75 |

**House System Fallback:**

| Latitude | System | Quality Flag |
|----------|--------|-------------|
| Any | Placidus | `exact` |
| High (>~66°) | Porphyry fallback | `fallback` |
| Extreme | Whole Sign fallback | `fallback` |

---

### 6.4 Fusion / Wu-Xing

#### `POST /v1/calculate/fusion`

Full Wu-Xing + Western harmony analysis. This is the **core endpoint** of FuFirE.

**Request:**

```json
{
  "date": "1990-06-15T14:30:00",
  "tz": "Europe/Berlin",
  "lon": 13.405,
  "lat": 52.52,
  "birth_time_known": true,
  "bazi_pillars": null
}
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bazi_pillars` | object \| null | null | Pre-computed pillars — auto-calculated if omitted |

**Response (200):**

```json
{
  "input": {"date": "...", "tz": "...", "lon": 13.405, "lat": 52.52},
  "wu_xing_vectors": {
    "western_planets": {"Holz": 0.534, "Feuer": 0.612, "Erde": 0.267, "Metall": 0.356, "Wasser": 0.378},
    "bazi_pillars":    {"Holz": 0.312, "Feuer": 0.445, "Erde": 0.534, "Metall": 0.489, "Wasser": 0.423}
  },
  "harmony_index": {
    "harmony_index": 0.8234,
    "interpretation": "Starke Resonanz - ...",
    "method": "dot_product",
    "western_vector": {"Holz": 0.534, "...": "..."},
    "bazi_vector": {"Holz": 0.312, "...": "..."}
  },
  "calibration": {
    "h_raw": 0.8234,
    "h_calibrated": 0.1554,
    "h_baseline": 0.791,
    "h_sigma": 0.127,
    "sigma_above": 0.255,
    "quality": "ok",
    "interpretation_band": "Unterdurchschnittliche Kongruenz",
    "n_west": 14,
    "n_bazi_contributions": 18
  },
  "elemental_comparison": {
    "Holz":   {"western": 0.534, "bazi": 0.312, "difference": 0.222},
    "Feuer":  {"western": 0.612, "bazi": 0.445, "difference": 0.167},
    "Erde":   {"western": 0.267, "bazi": 0.534, "difference": -0.267},
    "Metall": {"western": 0.356, "bazi": 0.489, "difference": -0.133},
    "Wasser": {"western": 0.378, "bazi": 0.423, "difference": -0.045}
  },
  "cosmic_state": 0.8234,
  "fusion_interpretation": "Harmonie-Index: 82.34%\n...",
  "contribution_ledger": {
    "western": [
      {"planet": "Sun", "element": "Feuer", "weight": 1.0, "is_retrograde": false, "rationale": "Classical rulership", "category": "traditional"},
      {"planet": "Mercury", "element": "Erde", "weight": 1.0, "rationale": "Dual element — Erde (day chart)", "category": "traditional", "chart_type_quality": "exact"}
    ],
    "bazi": [
      {"pillar": "year", "source": "stem", "stem_name": "Geng", "element": "Metall", "weight": 1.0, "category": "traditional"},
      {"pillar": "year", "source": "hidden_main", "branch_name": "Wu", "element": "Feuer", "weight": 1.0, "category": "traditional"}
    ],
    "chart_type_quality": "exact"
  },
  "house_quality": {"flag": "exact", "system": "placidus"},
  "provenance": { "...": "..." },
  "precision": {"birth_time_known": true, "provisional_fields": []}
}
```

> **Key concept:** `h_raw` is the raw cosine similarity (always 0.5–1.0 due to positive orthant). `h_calibrated` is the **contrast-normalized** value (0.0–1.0) relative to the empirical baseline for charts of this density. Use `h_calibrated` for interpretation.

---

#### `POST /v1/calculate/wuxing`

Wu-Xing element vector from western planetary positions only.

**Response (200):**

```json
{
  "input": {"...": "..."},
  "wu_xing_vector": {"Holz": 0.534, "Feuer": 0.612, "Erde": 0.267, "Metall": 0.356, "Wasser": 0.378},
  "dominant_element": "Feuer",
  "equation_of_time": -3.42,
  "true_solar_time": 14.213,
  "contribution_ledger": {"western": ["..."]},
  "provenance": {"...": "..."}
}
```

---

#### `POST /v1/calculate/tst`

True Solar Time calculation with all intermediate values.

**Request:**

```json
{"date": "1990-06-15T14:30:00", "tz": "Europe/Berlin", "lon": 13.405}
```

**Response (200):**

```json
{
  "input": {"date": "...", "tz": "...", "lon": 13.405},
  "civil_time_hours": 14.5,
  "longitude_correction_hours": 0.8937,
  "equation_of_time_hours": -0.057,
  "true_solar_time_hours": 15.3367,
  "true_solar_time_formatted": "15:20",
  "provenance": {"...": "..."}
}
```

---

### 6.5 Transit

#### `GET /v1/transit/now`

Current positions of 10 planets (7 classical + Uranus, Neptune, Pluto).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `datetime` | string (query) | now | Optional UTC datetime in ISO format |

**Response (200):**

```json
{
  "computed_at": "2026-03-28T14:00:00Z",
  "planets": {
    "sun":     {"longitude": 7.5,   "sector": 0,  "sign": "aries",   "speed": 0.99},
    "moon":    {"longitude": 187.2, "sector": 6,  "sign": "libra",   "speed": 13.2},
    "mercury": {"longitude": 332.1, "sector": 11, "sign": "pisces",  "speed": 1.8},
    "venus":   {"longitude": 15.4,  "sector": 0,  "sign": "aries",   "speed": 1.2},
    "mars":    {"longitude": 112.8, "sector": 3,  "sign": "cancer",  "speed": 0.7},
    "jupiter": {"longitude": 78.3,  "sector": 2,  "sign": "gemini",  "speed": 0.08},
    "saturn":  {"longitude": 342.9, "sector": 11, "sign": "pisces",  "speed": 0.03},
    "uranus":  {"longitude": 51.2,  "sector": 1,  "sign": "taurus",  "speed": 0.01},
    "neptune": {"longitude": 359.5, "sector": 11, "sign": "pisces",  "speed": 0.005},
    "pluto":   {"longitude": 303.8, "sector": 10, "sign": "aquarius", "speed": 0.003}
  },
  "sector_intensity": [0.34, 0.30, 0.24, 0.16, 0.0, 0.0, 0.10, 0.0, 0.0, 0.0, 0.40, 1.0]
}
```

**Planet weights** (for sector intensity):

| Planet | Weight | Rationale |
|--------|--------|-----------|
| Sun | 1.0 | Luminary |
| Moon | 0.5 | Fast-moving |
| Mercury | 0.6 | Personal |
| Venus | 0.7 | Personal |
| Mars | 0.8 | Personal |
| Jupiter | 1.2 | Outer classical |
| Saturn | 1.5 | Outer classical |
| Uranus | 1.5 | Generational |
| Neptune | 1.8 | Transpersonal |
| Pluto | 2.0 | Transformative |

---

#### `POST /v1/transit/state`

Personalized transit state combining current transits with user profile.

**Request:**

```json
{
  "soulprint_sectors": [0.42, 0.31, 0.55, 0.67, 0.28, 0.19, 0.48, 0.35, 0.22, 0.15, 0.20, 0.61],
  "quiz_sectors":      [0.30, 0.25, 0.40, 0.35, 0.20, 0.15, 0.50, 0.30, 0.18, 0.10, 0.22, 0.45]
}
```

Both arrays must have exactly 12 elements in range [0, 1].

**Response (200):**

```json
{
  "schema": "TRANSIT_STATE_v2",
  "generated_at": "2026-03-28T14:00:00Z",
  "ring": {"sectors": [0.62, 0.41, ...]},
  "transit_contribution": {
    "sectors": [0.34, 0.30, ...],
    "transit_intensity": 0.42
  },
  "events": [
    {
      "type": "resonance_jump",
      "priority": 1,
      "sector": 11,
      "trigger_planet": "saturn",
      "description_de": "Saturn aktiviert dein Pisces-Feld",
      "personal_context": "Dein stärkstes Feld wird von Saturn berührt"
    }
  ]
}
```

**Event types:**

| Type | Priority | Trigger |
|------|----------|---------|
| `resonance_jump` | 1 | Planet sits on user's peak soulprint sector, impact ≥ 0.18 |
| `moon_event` | 2 | Moon sits on high-impact sector (≥ 0.5) |

---

#### `GET /v1/transit/timeline`

Multi-day transit forecast. Cached 24h.

| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `days` | int (query) | 7 | 1–30 |

---

#### `POST /v1/transit/narrative`

Template-based narrative generation from a transit state. Sync, <50ms.

**Request:**

```json
{
  "transit_state": {
    "schema": "TRANSIT_STATE_v2",
    "generated_at": "2026-03-28T14:00:00Z",
    "ring": {"sectors": [...]},
    "transit_contribution": {"sectors": [...], "transit_intensity": 0.42},
    "events": [{"type": "resonance_jump", "priority": 1, "sector": 11, "trigger_planet": "saturn", "description_de": "...", "personal_context": "..."}]
  }
}
```

**Response (200):**

```json
{
  "headline": "Saturn trifft dein Fische-Feld",
  "body": "Saturn steht aktuell in deinem Sektor 11 (Fische). ...",
  "advice": "Nutze die Saturn-Energie heute bewusst. ...",
  "pushworthy": true,
  "push_text": "Saturn trifft dein Fische-Feld"
}
```

---

### 6.6 Experience

Consumer-facing app integration endpoints.

#### `POST /v1/experience/bootstrap`

Full profile bootstrap from birth data. Returns soulprint, signature blueprint, and profile summary.

**Request:**

```json
{
  "birth": {
    "date": "1990-06-15",
    "time": "14:30:00",
    "tz": "Europe/Berlin",
    "lat": 52.52,
    "lon": 13.405,
    "place_label": "Berlin"
  },
  "locale": "de-DE"
}
```

**Response (200):**

```json
{
  "profile": {
    "sun_sign": "Zwillinge",
    "moon_sign": "Skorpion",
    "ascendant_sign": "Schuetze",
    "day_master": "Xin",
    "harmony_index": 0.4521
  },
  "soulprint_sectors": [0.12, 0.08, 0.15, 0.09, 0.14, 0.07, 0.11, 0.06, 0.05, 0.04, 0.03, 0.06],
  "signature_blueprint": {
    "seed": "sig_v1_a1b2c3d4e5f67890",
    "visual": {
      "symmetry": 0.72,
      "curvature": 0.45,
      "angularity": 0.38,
      "density": 0.61,
      "contrast": 0.53,
      "orbit_count": 4
    },
    "elements": {"Holz": 0.23, "Feuer": 0.31, "Erde": 0.18, "Metall": 0.15, "Wasser": 0.13}
  },
  "meta": {"engine_version": "1.0.0-rc1-20260220", "generated_at": "2026-03-28T14:00:00Z"}
}
```

---

#### `POST /v1/experience/signature-delta`

Incremental signature update from a quiz answer.

---

#### `POST /v1/experience/daily`

Daily horoscope combining Western, Eastern (BaZi), and Fusion layers. Rate-limited to 30/min.

**Request:**

```json
{
  "birth": {"date": "1990-06-15", "time": "14:30:00", "tz": "Europe/Berlin", "lat": 52.52, "lon": 13.405},
  "soulprint_sectors": [0.12, 0.08, ...],
  "quiz_sectors": [0.10, 0.15, ...],
  "target_date": "2026-03-28",
  "locale": "de-DE"
}
```

**Response (200):**

```json
{
  "date": "2026-03-28",
  "western": {
    "summary": "Fuer dich als Gemini stehen heute Kreativitaet, Ausdruck im Fokus.",
    "themes": ["Kreativitaet", "Ausdruck"],
    "caution": "Achte in Sektor 5 auf Ueberanstrengung.",
    "opportunity": "Sektor 4 bietet dir heute besonderes Potenzial.",
    "evidence": {"transit_sectors": [3, 4], "natal_focus": ["sun", "ascendant"]}
  },
  "eastern": {
    "summary": "Dein Day Master Xin kontrolliert die Tagesenergie. Solarterm: Chunfen.",
    "themes": ["Kontrolle", "Disziplin", "Fokus"],
    "caution": "...",
    "opportunity": "...",
    "evidence": {"day_master": "Xin", "daily_pillar": {"stem": "Bing", "branch": "Yin"}, "relation_to_day_master": "power"}
  },
  "fusion": {
    "summary": "Dein Fusionstag verbindet Kontrolle + Ausdruck aus beiden Systemen.",
    "synthesis": "...",
    "action": "...",
    "pushworthy": true,
    "push_text": "Dein Power-Tag: Kontrolle + Ausdruck ruft."
  },
  "meta": {"engine_version": "1.0.0-rc1-20260220", "generated_at": "2026-03-28T14:00:00Z"}
}
```

---

### 6.7 Chart (Combined)

#### `POST /chart`

All-in-one: Western positions + BaZi pillars + Time scales + Wu-Xing. Internal use.

---

### 6.8 Webhooks

#### `POST /internal/api/webhooks/chart`

ElevenLabs voice agent integration. Internal path — ElevenLabs integration only, not a public API surface. Requires `elevenlabs-signature` header or `X-API-Key` matching `ELEVENLABS_TOOL_SECRET`. Accepts `birthDate`, `birthTime`, `birthPlace` (with geocoding).

---

### 6.9 Validation

#### `POST /v1/validate`

Contract-first validation against JSON Schema Draft-07 rulesets.

---

### 6.10 Astronomy V2

#### `POST /v2/astronomy/lunar-state`

Resolves a local civil datetime into a fold-preserving UTC instant and returns
geocentric Sun/Moon state, illumination, corrected eight-phase classification,
and the preceding/following true-new-moon events. This endpoint has no V1 or
unversioned alias. See [Canonical Lunar State V2](api/03_lunar_state_v2.md) for
the complete contract and calculation semantics.

---

## 7. Data Models

### Provenance Block

Attached to every `/calculate/*` response. Documents exactly which parameters produced the result.

```json
{
  "engine_version": "1.0.0-rc1-20260220",
  "parameter_set_id": "default_v1",
  "ruleset_id": "traditional_bazi_2026",
  "ephemeris_id": "swieph_sepl18",
  "tzdb_version_id": "2024b",
  "house_system": "placidus",
  "zodiac_mode": "tropical",
  "computation_timestamp": "2026-03-28T14:00:00Z",
  "parameter_set": {
    "version": "1.1.0",
    "retrograde_weight": 1.3,
    "hidden_stem_main_qi": 1.0,
    "hidden_stem_middle_qi": 0.5,
    "hidden_stem_residual_qi": 0.3,
    "stem_weight": 1.0,
    "mercury_dual_rule": "earth_day_metal_night",
    "harmony_method": "dot_product",
    "aspect_orb_model": "differentiated_v1",
    "aspect_base_orbs": {
      "Sun": 10.0, "Moon": 10.0, "Mercury": 7.0, "Venus": 7.0, "Mars": 7.0,
      "Jupiter": 8.0, "Saturn": 8.0, "Uranus": 5.0, "Neptune": 5.0, "Pluto": 5.0,
      "Chiron": 3.0, "Lilith": 2.0, "NorthNode": 3.0, "TrueNorthNode": 3.0
    },
    "aspect_factors": {
      "conjunction": 1.0, "sextile": 0.75, "square": 0.875, "trine": 1.0, "opposition": 1.0
    },
    "soulprint_weights": {
      "sun": 1.0, "moon": 0.8, "ascendant": 0.6, "personal_planet": 0.4, "wuxing_sector": 0.5
    },
    "wuxing_sector_mapping": {
      "Holz": [3, 4], "Feuer": [4, 5], "Erde": [1, 7], "Metall": [6, 9], "Wasser": [8, 11]
    },
    "transit_planet_weights": {
      "sun": 1.0, "moon": 0.5, "mercury": 0.6, "venus": 0.7, "mars": 0.8,
      "jupiter": 1.2, "saturn": 1.5, "uranus": 1.5, "neptune": 1.8, "pluto": 2.0
    }
  }
}
```

### Precision Block

Indicates whether birth time was known. When `birth_time_known: false`, time-dependent outputs are flagged:

```json
{
  "birth_time_known": false,
  "provisional_fields": ["hour", "ascendant", "houses", "mc"]
}
```

### Pillar Detail

```json
{
  "stamm": "Geng",
  "zweig": "Wu",
  "tier": "Pferd",
  "element": "Metall"
}
```

| Field | Description |
|-------|-------------|
| `stamm` | Heavenly Stem (天干) — romanized Pinyin |
| `zweig` | Earthly Branch (地支) — romanized Pinyin |
| `tier` | Chinese zodiac animal (German) |
| `element` | Wu-Xing element of the stem (German) |

### Calibration Result

| Field | Description |
|-------|-------------|
| `h_raw` | Raw Harmony Index (cosine similarity, always 0.5–1.0) |
| `h_calibrated` | Contrast-normalized H relative to empirical baseline (0.0–1.0) |
| `h_baseline` | Expected H for random charts of this density |
| `h_sigma` | Baseline standard deviation |
| `sigma_above` | z-Score: how many σ above baseline |
| `quality` | `ok`, `sparse` (too few inputs), `degenerate` (null vector) |
| `interpretation_band` | Human-readable quality label |

---

## 8. Rate Limiting

### Tier Limits

| Tier | Requests/day | Requests/min |
|------|-------------|-------------|
| Free | 100 | 5 |
| Starter | 1,000 | 20 |
| Pro | 10,000 | 100 |
| Enterprise | Unlimited | Unlimited |

### Storage

Rate limits are tracked in Redis (when `REDIS_URL` is configured) for accurate cross-worker counting. Falls back to in-memory storage gracefully.

### Rate Limit Response (429)

```json
{
  "error": "rate_limit_exceeded",
  "message": "Rate limit exceeded",
  "detail": {"limit": "100 per 1 minute"},
  "status": 429,
  "path": "/v1/calculate/bazi",
  "timestamp": "2026-03-28T14:00:00Z",
  "request_id": "..."
}
```

Response includes `Retry-After: 60` header.

---

## 9. Changelog

### v1.1.0 (2026-03-28) — Paid API Readiness

**Accuracy Improvements:**
- **Differentiated aspect orbs**: Per-planet base orbs (Sun/Moon 10°, Chiron 3°, Lilith 2°) with aspect-specific factors. Eliminates false-positive aspects between minor bodies.
- **Outer planets in transits**: Uranus, Neptune, Pluto added to `/transit/now`, `/transit/state`, `/transit/timeline` with weights 1.5/1.8/2.0.
- **Precise Jieqi in daily eastern**: Swiss Ephemeris solar longitude lookup replaces month-based approximation. Correct on boundary days.

**Schema Changes:**
- Transit state schema bumped to `TRANSIT_STATE_v2`: `delta` field removed (was always null), `dominance_shift` event type removed.
- `provenance.parameter_set` expanded: `aspect_base_orbs`, `aspect_factors`, `soulprint_weights`, `wuxing_sector_mapping`, `transit_planet_weights`.
- Parameter set version bumped to `1.1.0`.

**Infrastructure:**
- Redis-backed rate limiting via `REDIS_URL` env var. In-memory fallback when Redis unavailable.
- `/health` endpoint reports `rate_limiter` dependency status alongside ephemeris.

### v1.0.0-rc1 (2026-02-20) — Initial Release

- BaZi Four Pillars with Swiss Ephemeris
- Western astrology (14 bodies, Placidus houses, 5 aspects)
- Wu-Xing Fusion with calibrated Harmony Index
- Transit API (now/state/timeline/narrative)
- Experience API (bootstrap/signature-delta/daily)
- Tier-based API key authentication
- BAFE contract validation
