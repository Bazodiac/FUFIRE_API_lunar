# Synastry — `POST /v1/relationship/synastry` (G1 + G1b)

Deterministic western pair facts for two people: aspects between the two charts, house
overlays, axis contacts (ascendant/MC), the sign layer and its translation into the five
Wu-Xing phases. **No interpretation and no compatibility rating of any kind** — no field
called or containing `score`, `compatibility`, `percent`, `rating` or `points` exists
(contract test `tests/test_synastry_contract.py`).

Spec and decisions: `docs/superpowers/specs/2026-11-08-synastry-g1-design.md` (D1–D15).
Code: `bazi_engine/synastry/` (Level 4, pure) and `bazi_engine/routers/relationship.py`.

## Surface

- `/v1` only, API key required, rate limited by key tier. No legacy path exists.
- Both charts come from the existing `compute_western_chart` (Swiss Ephemeris, tropical,
  Placidus with the existing Porphyry → Whole-Sign fallback). Times are converted to UTC
  exactly like `/calculate/western`; the BaZi time standard (TLST) does not apply.

## Request

| Field | Type | Notes |
|-------|------|-------|
| `person_a`, `person_b` | object, required | `date` (local ISO 8601), `tz` (IANA), `lon`, `lat` — all **required**, no Berlin default; `ambiguousTime` (`earlier`/`later`), `nonexistentTime` (`error`/`shift_forward`), `birth_time_known` (default `true`), optional `display_label` (first name or initial, max 40 characters, letters with single inner `space . ' -`; no digits, no `@`; echoed in `subjects`, never logged) |
| `options.second_person_consent_confirmed` | bool, required | absent → 422 `validation_error`; `false` → 422 `consent_required`. The decision is logged as a hash with the request id only |

Unknown keys anywhere (e.g. `zodiac_mode`) are rejected with 422. A `date` without a time part (`YYYY-MM-DD`) is rejected with 422 `validation_error` while `birth_time_known` is true (no silent midnight chart).

**Unknown birth time** (`birth_time_known: false`, D14; Confluence BG 62259202, FUF-163..165).
The calendar day `YYYY-MM-DD` (the first ten characters of `date`) is authoritative: the
chart is computed at local **12:00:00** of that day in the person's `tz`, with the person's
`ambiguousTime` policy. When local 12:00:00 of that day does not exist (e.g. the skipped
calendar day Pacific/Apia 2011-12-30) the request is a 422 `dst_time_error` whatever
`nonexistentTime` says, because a shifted chart would make the stated assumption false. A
time part sent anyway is discarded and never used, but it must still be a valid ISO 8601
time (an offset or `Z` is accepted). A `date` whose first ten characters are not a real
calendar date `YYYY-MM-DD`, or whose time part is not valid ISO 8601, is a 422
`validation_error` (the value is not echoed). The assumption is visible in the response: `subjects.person_x.assumed_local_time`
= `"12:00:00"`, `assumption_reason` = `"birth_time_unknown"`, and the `birth_time_unknown`
warning names it (plus "The supplied clock time was discarded." when a time part was sent).
There is no silent midnight or noon default.

**Moon range** (D15). For an unknown-time person the Moon is also computed at local
`00:00:00` and `23:59:00` of that day, with fixed DST policies from `MOON_RANGE_DST_POLICIES`:
the start takes `ambiguousTime: earlier`, the end `ambiguousTime: later` (on a fall-back day
23:59 occurs twice and the day ends at the later one), both `nonexistentTime: shift_forward`
(midnight can fall in a DST gap). See `sign_certain`, `moon_range_deg` and `time_sensitive`
below. Only the Moon is assessed over the day (`time_sensitive`, `sign_certain`): other
planets are not marked even though they also move during the day, aspects or contacts reached
only at another time of that day are not listed, and the house overlays and the Moon's
Wu-Xing element use the 12:00 chart.

## Calculation

**Factors.** Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto; plus
Ascendant and MC only when that person's birth time is known.

**Weights** (`synastry-weights-v1` = Fusion tiers `body-tier-q0.3-v1`, MC tier 1):

| Tier | Weight | Factors |
|------|--------|---------|
| 1 | 1.0 | Sun, Moon, Ascendant, MC |
| 2 | 0.3 | Mercury, Venus, Mars |
| 3 | 0.09 | Jupiter, Saturn |
| 4 | 0.027 | Uranus, Neptune, Pluto |

Each aspect carries `from_weight`, `to_weight` and `weight = from_weight × to_weight`.

**Aspects** (`synastry-orbs-v1`, Astro-Noctum orbs, same for ASC/MC partners):

| Aspect | Angle | Orb limit |
|--------|-------|-----------|
| conjunction | 0° | 8° |
| sextile | 60° | 4° |
| square | 90° | 6° |
| trine | 120° | 6° |
| opposition | 180° | 8° |

Full cross matrix person_a → person_b (every A factor against every B factor), at most one
aspect per pair (the windows do not overlap). The limit is inclusive. `orb` = deviation from
the exact angle, rounded to 4 dp first; inclusion and `tight` (orb ≤ half the limit; `exact_angle` is the aspect's exact angle) are decided on that rounded orb, so the response is self-consistent. Order: A factor, then B factor, in
the factor order above.

`time_sensitive` (D15): for a row with the Moon of an unknown-time person the aspect is
evaluated at the Moon's two day bounds (at all four corners for Moon–Moon when both times
are unknown); it is true when any combination gives another aspect type or none. Each aspect
window is one convex arc of longitude and the Moon moves forward over one short arc, so
agreement at the bounds means the aspect holds over the whole day. Every other row: `false`.

**House overlays.** The ten planets of A in B's houses (`a_in_b`) and of B in A's houses
(`b_in_a`); a cusp belongs to the house it opens. Gate: when the **house owner's** birth time
is unknown, every row is `{"house": null, "status": "unavailable_missing_time"}`.

**Sign layer (G1b).** Sun, Moon, Mercury, Venus, Mars and (time known) Ascendant per person:
German sign name, `sign_index` (0 = Widder), western element (`Feuer/Erde/Luft/Wasser`),
degree in sign. `pairs` = every A factor × every B factor with
`sign_relation` by sign distance — `same_sign` (0), `semi_sextile` (1), `sextile` (2),
`square` (3), `trine` (4), `quincunx` (5), `opposition` (6) — and `element_relation`:
`same`, `complementary` (Feuer–Luft, Erde–Wasser) or `other`.

Every sign entry also has `sign_certain` and `moon_range_deg`. They are set only on the
Moon entry of an unknown-time person: `moon_range_deg = [start, end]`, the Moon longitude at
local 00:00 and 23:59 (4 dp, in [0, 360), forward direction — the Moon is never retrograde,
so `end` < `start` means the range crosses 0°), and `sign_certain` = true exactly when both
ends fall in the same sign. Every other entry, including the Moon of a known-time person,
carries `null` for both.

**Wu-Xing translation.** Each sign-layer factor's element is spread over
`["Holz", "Feuer", "Erde", "Metall", "Wasser"]` by the consensus matrix
`sign-element-consensus-v1` — the same matrix as the Fusion vector
(`docs/fusion/12_west_element_mapping.md`). Per person: one vector per factor (sums to 1)
and a person vector = tier-weighted mean of the factor vectors (sums to 1). No comparison
number between the persons.

## Response

`aspects[]`, `house_overlays {a_in_b[], b_in_a[]}`, `sign_layer {factors {person_a[], person_b[]}, pairs[]}`,
`wuxing_pair_factors {order, person_a, person_b, mapping_version}`, `provenance`, `subjects`.

`provenance`: `engine_version`, `ephemeris_mode`, `zodiac_mode` (`tropical`),
`house_system_used` per person (`null` without birth time), `orb_policy_id`,
`weighting_id`, `base_weighting_id`, `mapping_version`, `warnings[]`
(`birth_time_unknown` — names the 12:00:00 assumption and, when sent, the discarded clock
time; `house_system_fallback`).

`subjects.person_x`: `display_label`, `birth_time_known`, `assumed_local_time` (`"12:00:00"`
when the birth time is unknown, else `null`), `assumption_reason` (`"birth_time_unknown"`
when unknown, else `null`). No timestamp: identical requests return byte-identical bodies.

## Example

Request `examples/synastry_example_request.json`, response
`examples/synastry_example_response.json` (synthetic pair, real Swiss Ephemeris).
Both are generated, never hand-edited:

```bash
SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py          # write
SE_EPHE_PATH=/tmp/ephe python scripts/gen_synastry_example.py --check  # exit 1 when stale
```

Exit codes: 0 ok, 1 stale, 2 no SWIEPH, 3 the request to the app failed.

`tests/test_synastry_example.py` (swieph) fails when the example drifts from the live
output — regenerate after any synastry change or engine build-label bump.

## Privacy

No birth field and no `display_label` reaches a log line; error bodies do not echo them
(`tests/test_synastry_contract.py`). Nothing is persisted.

## Not in scope

Composite charts, relationship transits, minor aspects, Chiron, lunar nodes, interpretation
text, cross resonance (G3), BaZi branch combinations (G2).
