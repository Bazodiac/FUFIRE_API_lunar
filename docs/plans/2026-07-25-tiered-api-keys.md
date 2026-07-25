# Tiered, self-service API keys (Test / Standard / Premium)

**Status:** Phase 0 complete, Phase 1 in progress
**Trigger:** a live enterprise-tier key was found committed in plaintext in this
public repository (`docs/plans/2026-04-06-superglue-proxy-endpoints.md:486`) and
rotated on 2026-07-25.
**Goal:** real customers can obtain and pay for API keys at three levels, and
every issued key survives a redeploy, can be revoked, and is capped.

## Decisions (2026-07-25)

| Question | Decision |
| --- | --- |
| Source of truth for customer keys | **Engine + Postgres.** `PostgresKeyStore` in `bazi_engine/key_store.py`. The engine owns tier, limits, validation, revocation. The BFF's Supabase `api_keys` path is **not** pursued. |
| Tier mapping | Test = `free` · Standard = `starter` · Premium = `pro`. `enterprise` stays **internal** (the BFF's service credential) and is never sold, so no customer ever holds an uncapped key. |
| Billing | Stripe self-service: checkout → webhook → issue/upgrade. Free keeps the existing double-opt-in email flow. |

## Current state

```
Browser SPA
  └─ BFF  astro.fufire.space  (repo DYAI2025/FuFire_API_LIVE, base /api/v1)
       ├─ /keys/request + /keys/confirm   LIVE — double opt-in, mints tier=free
       │    └─> POST api.fufire.space/v1/admin/keys  (X-Admin-Token)
       ├─ /keys/list|create|rotate|revoke  503 — Supabase unconfigured (not pursued)
       └─ /proxy/*  → engine, injecting the single enterprise service key
Engine  api.fufire.space  (this repo)
       ├─ FUFIRE_API_KEYS      — env list; now holds only the BFF service key
       ├─ KEY_STORE_BACKEND=memory  — issued keys die on every redeploy
       └─ POST /v1/admin/keys  — free tier only
```

## Phases

### Phase 0 — Contain the leak ✅ (2026-07-25)

- [x] Mint a replacement enterprise key.
- [x] Zero-downtime rotation: engine `FUFIRE_API_KEYS = old,new` → BFF
      `FUFIRE_API_KEY = new` → engine `= new`. Each step verified by HTTP status,
      not by Railway's deploy label.
- [x] Verified: leaked key → `401`; new key → authenticated; BFF proxy → `200`.
- [x] Remove the literal from the doc; add `tests/test_no_committed_secrets.py`
      (PR #22).
- [ ] Purge the key from git history (`git filter-repo` + force push). Dead key,
      so hygiene rather than exposure.

### Phase 1 — Durable key storage (blocks everything else)

Today's `KEY_STORE_BACKEND=memory` means the live free-key flow emails users keys
that stop working at the next deploy. Keys already sent are already dead.

- [ ] `PostgresKeyStore` in `key_store.py`. Store **SHA-256 hashes**, never
      plaintext — a DB dump must not yield working keys.
- [ ] Schema (`api_keys`): `id`, `key_hash` UNIQUE, `key_prefix` (display),
      `tier`, `label`, `owner_email`, `jti` UNIQUE, `status`
      (`active`/`revoked`), `created_at`, `revoked_at`, `last_used_at`.
      Applied idempotently at startup — the repo has no migration tool.
- [ ] Link the existing Postgres service: `DATABASE_URL=${{Postgres.DATABASE_URL}}`
      on `FUFIRE_API_lunar`; set `KEY_STORE_BACKEND=postgres`.
- [ ] Add `psycopg[binary]` to `pyproject.toml` **and** `requirements.lock`
      (the Dockerfile installs from the lock, not from pyproject).
- [ ] Update `tests/test_key_store_backend_policy.py`, which asserts the literal
      string `"Supported backends: none, memory"`.

**Behaviour change — reveal-once.** Hash-only storage cannot return a previously
issued key, so `issue()` can no longer be idempotent *returning the same
plaintext*. A repeat `jti` returns `409 already_issued` carrying `key_prefix`
only. The BFF's `/keys/confirm` must map that to a friendly
"already sent — check your inbox" page instead of `/key-error.html`. This
matches how Stripe/GitHub/AWS treat key material and is the reason a leaked key
cannot be re-read out of the database.

### Phase 2 — Revocation and honest quotas

- [ ] `POST /v1/admin/keys/revoke` — sets `status='revoked'`; validation rejects
      immediately. There is currently **no** way to kill a customer key.
- [ ] Enforce `requests_per_day`. `TIER_LIMITS` has declared it since day one and
      nothing has ever enforced it; `openapi_ext.py` already tells clients the
      `X-RateLimit-Remaining` value is not real. Needs a shared counter.
- [ ] Add Redis (`REDIS_URL`). Without it, slowapi counters live in process
      memory and reset on every deploy, so per-minute limits are unenforceable
      across replicas. Note `limiter.py` already refuses to silently fall back.

### Phase 3 — Paid tiers

- [ ] Widen `_ALLOWED_ISSUANCE_TIERS` in `routers/admin.py` from `{free}`, gated
      so `starter`/`pro` require a verified payment rather than a bare admin
      token. `_MINTABLE_TIERS` in `key_store.py` is a format check, **not** the
      authorization boundary.
- [ ] Stripe products/prices for Standard and Premium.
- [ ] Stripe webhook (`checkout.session.completed`,
      `customer.subscription.deleted`) → issue, upgrade, or revoke. Signature
      verified; idempotent on the Stripe event id, reusing the `jti` column.
- [ ] Pricing + checkout UI on `astro.fufire.space`.

### Phase 4 — Self-service management

- [ ] Let a customer list, rotate, and revoke their own keys, keyed by
      `owner_email`. Decide then whether to reuse the BFF's existing Supabase
      session or add engine-side magic-link auth.

## Risks

- Rotating the BFF service key again requires touching two services in order;
  doing it in one step black-holes `astro.fufire.space` until both deploy.
- `railway.toml` sets `noCache = true`, so every variable change triggers a full
  Docker rebuild including the ephemeris download. Budget minutes, not seconds.
- The engine currently trusts `FUFIRE_API_KEYS` **and** the store. Keep the env
  list as the break-glass path for the BFF service key only; customer keys must
  never be added to it, or revocation stops working.
