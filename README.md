# FuFirE — Fusion Firmament Engine

Deterministic astronomical calculation engine for Chinese astrology (BaZi / Four Pillars of Destiny) with Western astrology integration. Calculates Year/Month/Day/Hour pillars based on precise solar-term boundaries using Swiss Ephemeris, and measures the mathematical coherence between Eastern and Western systems via a calibrated Coherence Index.

## Key Features

- **BaZi (Four Pillars):** Year/Month/Day/Hour pillars with LiChun-aware year transitions, Zi-hour boundary handling, and True Solar Time correction
- **Western Astrology:** Planetary positions, house cusps, aspects, angles (tropical and sidereal support)
- **Wu-Xing Fusion:** Both systems projected into a shared Five-Element vector space with Monte Carlo-calibrated Coherence Index
- **Real-Time Transits:** Live planetary positions, timelines, narrative generation
- **Canonical Lunar State V2:** Geocentric Sun/Moon state, illumination, true-new-moon events, and corrected eight-phase classification
- **Contract-First Validation:** JSON Schema Draft-07 validation for engine configurations
- **Deterministic:** Same input = same output, always. 1500+ regression tests, 200 bit-stable snapshot vectors

## Quickstart

```bash
# Setup
cd BAFE
python3.10 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Start API server
uvicorn bazi_engine.app:app --reload
```

```bash
# Calculate BaZi pillars
curl -s -X POST http://localhost:8080/v1/calculate/bazi \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ff_free_yourkey" \
  -d '{"date":"1990-06-15T14:30:00","tz":"Europe/Berlin","lon":13.405,"lat":52.52}' | python -m json.tool
```

## CLI

```bash
python -m bazi_engine.cli 2024-02-10T14:30:00 --tz Europe/Berlin --lon 13.405 --lat 52.52
python -m bazi_engine.cli 2024-02-10T14:30:00 --json   # JSON output
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/calculate/bazi` | Four Pillars calculation |
| POST | `/v1/calculate/western` | Western planetary chart |
| POST | `/v1/calculate/fusion` | Wu-Xing + Western fusion analysis |
| POST | `/v1/calculate/wuxing` | Five Elements vector |
| POST | `/v1/calculate/tst` | True Solar Time |
| GET | `/v1/transit/now` | Live planetary positions |
| GET | `/v1/transit/timeline` | Transit timeline |
| POST | `/v1/validate` | Contract-first validator |
| GET | `/v1/health` | Health check |
| POST | `/v2/astronomy/lunar-state` | Canonical geocentric lunar state and moon phase |

All `/v1/*` and `/v2/*` business endpoints require an API key (`X-API-Key` header). See [Developer API Reference](docs/api/01_developer_api_reference.md) for full details.

## Documentation

| Document | Description |
|----------|-------------|
| [Developer API Reference](docs/api/01_developer_api_reference.md) | Complete endpoint schemas, auth, examples |
| [How Fusion Works (EN)](docs/marketing/how-fusion-works-en.md) | The math behind the Coherence Index |
| [Wie Fusion funktioniert (DE)](docs/marketing/how-fusion-works-de.md) | Deutsche Version |
| [Fusion Whitepaper](docs/marketing/whitepaper-fusion-mathematics.md) | Technical whitepaper (TWP-001) |
| [OpenAPI Spec](spec/openapi/openapi.json) | OpenAPI 3.1 source of truth |
| [Lunar State V2](docs/api/03_lunar_state_v2.md) | Request, response, phase boundaries, precision, and failure semantics |
| [Error Codes](docs/ERROR_CODES.md) | Contract-bound error codes |

## Testing

```bash
pytest -q                                # Quick run (1500+ tests)
pytest -v --cov=bazi_engine              # With coverage (88%)
python scripts/check_complexity.py       # Complexity gate (CC>15)
python scripts/calibrate_baselines.py    # Monte Carlo calibration (5000 trials)
```

## Deployment

- **Production:** Railway (auto-deploys on push to `main` via `Dockerfile` + `railway.toml`)
- **Docker:** `docker build -t fufire . && docker run -p 8080:8080 fufire`
- **Mock Server:** `python tests/mock_server.py --port 8081` (no ephemeris needed)

## Swiss Ephemeris Setup (Local Dev)

The engine requires four Swiss Ephemeris data files to calculate planetary positions. **Docker handles this automatically** — the multi-stage build downloads and SHA256-verifies all files at build time.

For local development without Docker:

```bash
# Required files (download from https://www.astro.com/swisseph/)
sepl_18.se1   # main planets
semo_18.se1   # Moon
seas_18.se1   # asteroids
seplm06.se1   # outer planets (pre-1800)

# Place them in a directory and set the env var
mkdir -p ~/.swisseph
# copy files there
export SE_EPHE_PATH=~/.swisseph

# Verify the engine can find them
uvicorn bazi_engine.app:app --reload --port 8080
curl -s http://localhost:8080/v1/health | python -m json.tool
# "ephemeris": {"status": "ok"} = files found
```

**`503 ephemeris_unavailable` in local dev** means the ephemeris files are missing or `SE_EPHE_PATH` is not set — this is not a bug. See [`docs/runbooks/ephemeris-local-setup.md`](docs/runbooks/ephemeris-local-setup.md) for step-by-step instructions.

## Contract-First Validation

POST `/v1/validate` validates engine configurations against JSON Schema Draft-07:

```json
{
  "validate_level": "FULL",
  "engine_config": {
    "engine_version": "1.0.0-rc2-20261016",
    "parameter_set_id": "standard",
    "deterministic": true,
    "compliance_mode": "RELAXED",
    "bazi_ruleset_id": "standard_bazi_2026"
  }
}
```

Schemas: [`spec/schemas/`](spec/schemas/) | Ruleset: [`spec/rulesets/standard_bazi_2026.json`](spec/rulesets/standard_bazi_2026.json)

## License

Proprietary. See LICENSE for details.
