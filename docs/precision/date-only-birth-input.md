# Birth input without a clock time (`date_only_noon`)

**Status:** engine build label `1.0.0-rc12-20261118` · **Module:** `bazi_engine/birth_time.py`
· **Tests:** `tests/test_birth_time_unknown.py`, `tests/test_date_only_day_pillar_sweep.py`

## Rule

The birth endpoints accept `date` as a full local date-time (`1985-08-02T14:30:00`) or as a
bare calendar date (`1985-08-02`). Until build `1.0.0-rc11-20261111` a bare date was read
as **00:00** local time. Under the TLST default that moment is, for most of Europe, still
the previous true-solar day, so a date-only request returned the **previous day's day
pillar** (Munich, 1985-08-02: 壬申 instead of 癸酉).

Since `1.0.0-rc12-20261118`:

| Request | Computed at | `precision.birth_time_known` | Marked |
|---|---|---|---|
| bare `date` | **12:00 civil local time** | `false` (whatever the flag says) | `reference_time_policy: "date_only_noon"` in `precision` (and in `derivation_trace.time_resolution` on `/bazi`), warning `BIRTH_TIME_UNKNOWN` |
| `date` with time, `birth_time_known: false` | exactly that time | `false` | warning `BIRTH_TIME_UNKNOWN`, `provisional_fields` |
| `date` with time, `birth_time_known: true` (default) | exactly that time | `true` | nothing new; the response is unchanged |

A date with a time and `birth_time_known: false` computes the **same values** as with
`true`; only `precision` and `warnings` differ. A client that knows a time window can
therefore sample concrete times and compare.

If 12:00 does not exist locally (the whole calendar day was skipped, e.g. `Pacific/Apia`
on 2011-12-30), the request is a `422`; noon is never shifted, whatever `nonexistentTime`
says, because a shifted noon would no longer be the documented reference time.

### Endpoints

Applies to: `/calculate/bazi`, `/calculate/bazi/trace`, `/calculate/bazi/natal`,
`/calculate/bazi/wuxing`, `/calculate/western`, `/calculate/fusion`,
`/calculate/fusion/vector-map`, `/calculate/bazi/dayun` (legacy and `/v1`).
`/calculate/bazi/dayun` and `/calculate/fusion/vector-map` gained a `birth_time_known`
request field (default `true`).

Unchanged on purpose — a bare date there means a whole day or a day boundary, not a birth:
`/calculate/tst`, `/calculate/wuxing`, transits, daily, `/experience/*`, `/personalize`,
`/chronometry/resolve`, `/chart`, `/v1/match/bazi-hehun`, synastry. They still read a bare
date as 00:00 (`time_utils.resolve_local_iso`).

## Why 12:00

The engine computes the day pillar from the true-solar day under TLST. At civil noon the
true-solar time differs from noon by the zone offset minus `lon / 15` hours (plus the
equation of time, ≤ 17 min). As long as that difference is below 12 hours the true-solar
day is the calendar day — everywhere except zones east of the date line at western
longitudes.

Measured with `tests/test_date_only_day_pillar_sweep.py` (1170 seeded dates 1900–2030, nine
places, expected value from an independent `(JDN + 49) mod 60`):

| Place | CIVIL | TLST |
|---|---|---|
| Berlin, Madrid, London, Kashgar (Asia/Shanghai), Anchorage, Honolulu, Sydney | 130/130 each | 130/130 each |
| Pacific/Apia (172° W, UTC+13/+14 since 2011-12-31) | 130/130 | 112/130 |
| Pacific/Kiritimati (157° W, UTC+14 since 1995) | 130/130 | 100/130 |
| **Total** | **1170/1170 (100 %)** | **1122/1170 (95.9 %)** |

Every TLST miss is a date in Apia from 2011-12-31 or in Kiritimati from 1995: there the
whole civil day is the previous true-solar day, at every hour. That is a property of TLST,
not of the reference time — no civil time of day would put those days on the calendar
date. The test encodes it as the documented exception (calendar day − 1). Clients that
want the calendar day in those zones send `standard: "CIVIL"`.

## `provisional_fields`

With an unknown birth time `precision.provisional_fields` lists what can change within the
civil day. The engine compares the two ends of the civil day (00:00:00, and the later
23:59:59 on a fall-back day; a midnight in a DST gap moves to the first valid minute):

| Endpoint | Always | When it changes during that day |
|---|---|---|
| `/bazi`, `/bazi/trace`, `/bazi/wuxing`, `/bazi/natal` | `hour` | `year` (Li Chun day), `month` (jie 节 day), `day` (the day boundary of the requested standard falls inside the civil day — under TLST almost every day) |
| `/western` | `ascendant`, `houses`, `mc` | every body (named as in `bodies`) whose sign changes |
| `/fusion`, `/fusion/vector-map` | `signature`, `hour`, `ascendant`, `houses` | the pillars and bodies above |
| `/bazi/dayun` | `start`, `cycles.age_start`, `cycles.age_end`, `cycles.date_start`, `cycles.date_end`, `current` | `cycles.pillar` (month pillar changes), `direction` (year pillar changes and `direction_method` is `year_stem_yinyang_and_sex`) |

With a known time the block stays `{"birth_time_known": true, "provisional_fields": []}`
(dayun: plus `direction_basis`), and `reference_time_policy` and `warnings` are absent, so
known-time responses are byte-identical to the previous build.

Under TLST the `day` entry is the normal case for a date-only request: the true-solar
midnight of a place lies inside its civil day unless zone offset and longitude coincide.

## Fusion

With an unknown birth time `/calculate/fusion` and `/fusion/vector-map` leave the
ascendant and the hour pillar out of both vectors by default; see
[`docs/fusion/13_exclude_time_dependent.md`](../fusion/13_exclude_time_dependent.md).
