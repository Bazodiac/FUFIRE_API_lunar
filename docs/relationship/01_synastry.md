# Synastry — `POST /v1/relationship/synastry` (G1 + G1b)

Deterministic western pair facts for two people: aspects between the two charts, house
overlays, axis contacts (ascendant/MC), the sign layer and its translation into the five
Wu-Xing phases. **No interpretation and no compatibility rating of any kind** — no field
called or containing `score`, `compatibility`, `percent`, `rating` or `points` exists
(contract test `tests/test_synastry_contract.py`).

Spec and decisions: `docs/superpowers/specs/2026-11-08-synastry-g1-design.md` (D1–D16).
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
(midnight can fall in a DST gap). See `moon_range_deg` below.

**Day uncertainty** (D16). The same two bound charts (local 00:00 and 23:59, same DST
policies) give the longitudes of **every** planet of an unknown-time person at both ends of
the day; no further chart is computed. Each value in the response is still the 12:00 value;
the bounds only mark it: `time_sensitive` on aspects and house overlays, `sign_certain` on
the sign layer and the Wu-Xing factors (see below). Element, weight and every Wu-Xing vector
stay at the 12:00 value; nothing is redistributed. Aspects that exist only at another time of
that day are not output. **Consumers treat `time_sensitive: true` and `sign_certain: false`
as not reliable.** Every aspect window, sign and house is one convex arc of longitude, and
over one day each planet moves monotonically (apart from a station, where it moves less than
1 arcminute), so agreement at both bounds and at 12:00 means the value holds over the whole
day.

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

`time_sensitive` (D15, D16): for a row with at least one endpoint of an unknown-time person,
each such endpoint is evaluated at its two day bounds (2 combinations, or all 4 corners when
both times are unknown); it is true when any combination gives another aspect type or none.
Rows between two known-time persons: `false`.

**House overlays.** The ten planets of A in B's houses (`a_in_b`) and of B in A's houses
(`b_in_a`); a cusp belongs to the house it opens. Row: `{factor, house, status,
time_sensitive}`. Gate: when the **house owner's** birth time is unknown, every row is
`{"house": null, "status": "unavailable_missing_time", "time_sensitive": false}`.
`time_sensitive` (D16): for an unknown-time guest in a known-time host it is true when the
guest factor's house at local 00:00 or 23:59 differs from its 12:00 house (the host cusps are
the host's fixed chart); a known-time guest: `false`.

**Sign layer (G1b).** Sun, Moon, Mercury, Venus, Mars and (time known) Ascendant per person:
German sign name, `sign_index` (0 = Widder), western element (`Feuer/Erde/Luft/Wasser`),
degree in sign. `pairs` = every A factor × every B factor with
`sign_relation` by sign distance — `same_sign` (0), `semi_sextile` (1), `sextile` (2),
`square` (3), `trine` (4), `quincunx` (5), `opposition` (6) — and `element_relation`:
`same`, `complementary` (Feuer–Luft, Erde–Wasser) or `other`.

Every sign entry also has `sign_certain` and `moon_range_deg`. `sign_certain` (D16) is set on
every entry of an unknown-time person (Sun, Moon, Mercury, Venus, Mars): true exactly when the
factor's longitudes at local 00:00 and 23:59, rounded to 4 dp, fall in the same sign.
`moon_range_deg` is set on the Moon entry of an unknown-time person only: `[start, end]`, the
Moon longitude at local 00:00 and 23:59 (4 dp, in [0, 360), forward direction — the Moon is
never retrograde, so `end` < `start` means the range crosses 0°). A known-time person carries
`null` for both on every entry.

| Field | Where | Known time | Unknown time (D15, D16) |
|-------|-------|------------|-------------------------|
| `aspects[].time_sensitive` | every aspect | `false` (both known) | true when the aspect type is not the same at every bound combination |
| `house_overlays.*[].time_sensitive` | every overlay row | `false` (known guest) | unknown guest, known host: true when a bound house differs from the 12:00 house; unknown host: `false` (gated) |
| `sign_layer.factors.*[].sign_certain` | every sign entry | `null` | true when both bounds fall in the same sign |
| `sign_layer.factors.*[].moon_range_deg` | Moon entry | `null` | `[start, end]` at 00:00 and 23:59 |
| `wuxing_pair_factors.*.factors[].sign_certain` | every Wu-Xing factor | `null` (also the Ascendant) | same value as the factor's sign entry |

**Wu-Xing translation.** Each sign-layer factor's element is spread over
`["Holz", "Feuer", "Erde", "Metall", "Wasser"]` by the consensus matrix
`sign-element-consensus-v1` — the same matrix as the Fusion vector
(`docs/fusion/12_west_element_mapping.md`). Per person: one vector per factor (sums to 1)
and a person vector = tier-weighted mean of the factor vectors (sums to 1). No comparison
number between the persons. Each factor is `{factor, west_element, weight, vector,
sign_certain}`; `sign_certain` is the value of that factor's sign entry (D16), while element,
weight and vectors stay at the 12:00 value.

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
