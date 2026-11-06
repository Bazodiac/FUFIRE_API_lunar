# BaZi in True Local Solar Time — `/v2` (opt-in)

`POST /v2/calculate/bazi` and `POST /v2/calculate/bazi/natal` compute a BaZi
chart with **True Local Solar Time (TLST)** as an explicit, auditable choice.
Both run the existing engine (`compute_bazi`, `time_context`) — the same code
the v1 `standard: "TLST"` option runs — and report the time basis it used.

Work item: FU-TLST-POLICY / INC-1 (provisional slice name, no Jira ID).

## Release boundary

- **Opt-in only.** `standard` must be `"TLST"`. `/calculate/bazi`,
  `/v1/calculate/bazi` and the natal twins keep their `CIVIL` default and are
  unchanged.
- **Not a verified production standard.** The sexagenary day-cycle anchor of
  the shipped ruleset is `unverified` (`policy.day_anchor_verification`);
  domain sign-off (FBP-02-002/003, DEV-2026-004) is pending. Swiss Ephemeris
  confirms the apparent solar time, not the day-cycle anchor.
- Errors use the frozen `ErrorEnvelope` (`{"error", "message", "detail", …}`),
  as on `/v2/astronomy/lunar-state`. RFC 9457 for `/v2` (FBP-03-006) is still
  only planned.

## Time flow

```
local wall-clock + IANA zone
  → explicit DST resolution (ambiguous → ambiguousTime required; gap → 422 or shift_forward)
  → exact UTC instant
  → TLST = UTC + longitude × 4 min + equation of time (Meeus 1998)
  → hour branch from the TLST hour (half-open, Zi = [23, 1))
  → day pillar from the apparent-solar date (boundary "midnight")
     or advanced at TLST 23:00 (boundary "zi")
```

Year and month pillars depend on the instant only (LiChun / jie crossings in
UTC), not on the time standard.

## Request

| field | required | notes |
|---|---|---|
| `date` | yes | local ISO 8601 wall-clock, **no** UTC offset; seconds and microseconds allowed |
| `tz` | yes | IANA zone; unknown zone → 422 |
| `lat` | yes | −90…90, finite |
| `lon` | yes | −180…180, finite, degrees east |
| `standard` | yes | only `"TLST"` |
| `boundary` | yes | `"midnight"` or `"zi"` |
| `ambiguousTime` | when ambiguous | `"earlier"` (fold 0) / `"later"` (fold 1); omitted on an ambiguous time → 422 |
| `nonexistentTime` | no | `"error"` (default, → 422) or `"shift_forward"` |
| `birth_time_known` | no | default `true`; `false` marks the hour pillar provisional |

Unknown fields are rejected. There are no location defaults.

## Example (executable)

Start a local engine (`uvicorn bazi_engine.app:app --port 8080`, with
`SE_EPHE_PATH` pointing at the verified ephemeris) and run:

```bash
curl -s http://localhost:8080/v2/calculate/bazi \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $FUFIRE_API_KEY" \
  -d '{"date": "1990-07-15T15:44:00", "tz": "Europe/Berlin",
       "lat": 52.3759, "lon": 9.732,
       "standard": "TLST", "boundary": "midnight"}'
```

(`X-API-Key` is required when `FUFIRE_API_KEYS` is configured; a local dev run
without keys accepts the request without it.) The natal route takes the same
body at `/v2/calculate/bazi/natal`.

Response excerpt (real output, SWIEPH, engine label `1.0.0-rc8-20261106`):

```json
"pillars": {"year": "Geng-Wu", "month": "Gui-Wei", "day": "Xin-Si", "hour": "Yi-Wei"},
"time_basis": {
  "standard": "TLST",
  "input_local": "1990-07-15T15:44:00",
  "resolved_local": "1990-07-15T15:44:00+02:00",
  "timezone": "Europe/Berlin",
  "fold": 0,
  "local_time_status": "ok",
  "utc_offset_minutes": 120,
  "utc": "1990-07-15T13:44:00+00:00",
  "tlst_hours": 14.283511,
  "tlst_date": "1990-07-15",
  "tlst_date_rollover": 0,
  "eot_minutes": -5.9173,
  "eot_source": "meeus_1998",
  "hour_branch_basis": "tlst_hours",
  "day_boundary": "midnight",
  "day_boundary_rule": "tlst_solar_midnight",
  "zi_start_hour": 23.0,
  "day_pillar_date": "1990-07-15",
  "uncertainty": {
    "status": "clear",
    "tlst_edge": {"edge_hours": 15.0, "kinds": ["hour_branch"], "distance_minutes": 42.9893,
                  "tolerance_minutes": 0.1, "status": "clear"},
    "solar_term": {"nearest_boundary_utc": "1990-07-07T09:00:28.590430+00:00",
                   "distance_seconds": 708211.41, "accuracy_seconds": 1.0, "status": "clear"}
  }
},
"policy": {
  "time_standard": "TLST", "opt_in": true, "v1_default_standard": "CIVIL",
  "ruleset_id": "standard_bazi_2026", "ruleset_version": "1.0.0",
  "day_anchor_id": "standard_bazi_2026:jdn_2419451_unverified",
  "day_anchor_verification": "unverified"
}
```

Civil 15:44 MESZ is the Shen hour; the apparent solar time at Hannover is
14:17, so the TLST hour pillar is `Yi-Wei`.

## `time_basis.uncertainty`

- `tlst_edge` — distance of the published `tlst_hours` to the nearest edge at
  which a pillar decision flips: the hour-branch edges (odd hours), plus the
  zi day start (`boundary: "zi"`) or apparent solar midnight
  (`boundary: "midnight"`). `within_eot_tolerance` when ≤ 0.1 min — the
  documented agreement bound of the Meeus equation of time with Swiss
  Ephemeris. Inside that band a decision cannot be confirmed by the EoT model.
- `solar_term` — distance of the instant to the nearest jie boundary (incl.
  LiChun); `within_accuracy` when ≤ the engine's crossing-search accuracy.
- `status` is `boundary_within_tolerance` when either sub-status is not
  `clear`.

## Response blocks

`/v2/calculate/bazi`: the v1 BaZi blocks (`pillars`, `chinese`, `dates`,
`transition`, `solar_terms_count`, `provenance`, `quality_flags`,
`precision`), the **always-present** `derivation_trace`, plus `input`,
`time_basis`, `policy`.

`/v2/calculate/bazi/natal`: the v1 natal blocks (`pillars` with hidden stems
and Ten Gods, `day_master`, `month_command`, `provenance`, `precision`,
`warnings`) plus the same `input`, `time_basis`, `policy`. For identical input
both routes return identical four pillars and an identical `time_basis`. No
day-master strength, yong shen or seasonal-strength field is emitted.

## Verification

- `tests/test_v2_bazi_tlst.py` — HTTP contract, validation, DST, boundary
  matrix against Swiss Ephemeris, BaZi/natal parity.
- `tests/test_v1_time_standard_contract.py` — v1/legacy defaults and pillars
  pinned.
- `tests/test_tlst_monte_carlo.py` + `scripts/tlst_monte_carlo.py` — seed
  20261106, ≥ 5 000 samples vs `swe.lmt_to_lat`.
- `scripts/tlst_grid_check.py` — 18 432-sample grid vs `swe.lmt_to_lat`.
