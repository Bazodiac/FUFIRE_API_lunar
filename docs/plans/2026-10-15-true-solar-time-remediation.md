# True Solar Time (TLST) — Befund und Sanierungsplan

**Datum:** 2026-10-15
**Status:** Befund verifiziert, Plan freigabereif, Fix **nicht** angewendet (siehe §0)
**Auslöser:** 15:44 MESZ + Hannover-Koordinaten liefert intern widersprüchliche
Werte (LMT 14:22 vs. TLST 16:17 → Stundensäule Wei vs. Shen).
**Referenzsystem:** Swiss Ephemeris (`swe.time_equ`, `swe.lmt_to_lat`), Korpus
`tests/fixtures/tlst_reference_corpus_v1.json`, Tripwires
`tests/test_tlst_reference_corpus.py`.
**Deviation-Register:** DEV-2026-009 … DEV-2026-012 (+ Korrektur DEV-2026-008)
in `docs/precision/deviations.md`.

---

## 0. Kurzfassung

| Claim | Status | Beleg |
|---|---|---|
| `compute_effective_time_context().tlst_hours` ist für jede Zone mit UTC-Offset ≠ 0 um genau diesen Offset falsch (Hannover MESZ: +2 h). | **VERIFIED** | `scripts/`-Repro gegen `swe.lmt_to_lat`; Raster 18 432 Samples × 16 Zonen: 85,4 % falscher Stundenzweig, 21,4 % falsches TLST-Datum, max. Abweichung 12 h (Auckland). |
| Der LMT-Pfad (`to_chart_local`, `ctx.lmt_local`) ist korrekt. | **VERIFIED** | Korpus: alle 21 Fälle, Δ < 1e-3 h. |
| Das Blatt `solar_time.true_solar_time()` ist korrekt, **wenn** `timezone_offset_hours` übergeben wird; `/calculate/wuxing` und `/chart` übergeben ihn nicht. | **VERIFIED** | Korpus-Tests §1; DEV-2026-008 (bisher falsch diagnostiziert). |
| `fusion.true_solar_time_from_civil()` hat das Längengrad-Vorzeichen invertiert und schätzt den Zonenmeridian DST-blind. Kein Endpoint nutzt sie. | **VERIFIED** | Berlin 12:00 CET → 12.05 h statt 11.84 h. |
| Der DST-Fold geht in `compute_effective_time_context` verloren (fold=1 wird als fold=0 gerechnet → 1 h Fehler). | **VERIFIED** | Korpus-Fall `berlin_dst_fallback_fold1`. |
| `EffectiveTimeContext.date_rollover` wird berechnet, aber von `compute_bazi` nie konsumiert → TLST-Tagessäule bei Geburten vor dem solaren Mitternacht falsch. | **VERIFIED** (Code-Pfad) | `bazi.py::_dt_for_day_pillar`; Tripwire DEV-2026-011. |
| Zeitgleichungs-Näherung (`equation_of_time(day_of_year)`) weicht max. 0,77 min von `swe.time_equ` ab (1950–2026). | **VERIFIED** | Jahres-Sweep, 2 922 Samples; Test `test_eot_approximation_bound_full_year_vs_swisseph`. |
| ZWDS-Seed hat den Bug erkannt und **umgangen** statt gemeldet (Docstring `zwds/seed.py`). | **FACT** | Zeile „its own `tlst_hours` is not used because it adds the full longitude offset to the civil wall-clock“. |

**Konsequenz:** Jede Ausgabe, die auf `ctx.tlst_hours` beruht, ist für
Nicht-UTC-Zonen falsch: `/calculate/tst`, `/calculate/bazi` (Stundensäule bei
`standard=TLST`, Zi-Rollover bei `boundary=zi`, Trace `time_resolution.tlst_hours`
für **alle** Standards), `/chronometry/resolve`, `/personalize` (chronometry-Block),
`/calculate/bazi/natal`, `/dayun`, `/v1/match/bazi-hehun` (bei TLST-Input).
CIVIL- und LMT-Säulen sind **nicht** betroffen.

Der Fix ist bewusst nicht in diesem Increment angewendet: er ändert 50
SWIEPH-Snapshots (nur per manuellem Workflow regenerierbar), kippt zwei
bestehende Tests, deren Fixtures den Bug als Erwartung kodieren, und löst das
strikte GT6-xfail aus. Das gehört in einen eigenen, review-gated Schnitt (§4).

---

## 1. Architektur der Zeitpfade (Ist-Zustand)

```
                 resolve_local_iso / parse_local_iso  (DST, fold)
                                 │ aware civil datetime
         ┌───────────────────────┼─────────────────────────────┐
         ▼                       ▼                             ▼
 to_chart_local()        compute_effective_time_context()   true_solar_time()   [Layer 2 Blatt]
 (time_utils, L2)        (time_context, L2)                 (solar_time, L2)
   CIVIL → civil           civil, utc        ✓ korrekt         korrekt NUR mit tz-Offset
   LMT   → utc+lon·4min ✓  lmt_local         ✓ korrekt
   TLST  → civil (!)       tlst_hours        ✗ civil+lon·4min+EoT   (Offset fehlt)
                           date_rollover     ✗ aus falschem raw_tlst
                           fold              ✗ verloren (naive ISO rein)
         │                       │                             │
         ▼                       ▼                             ▼
 compute_bazi (L4)        routers/bazi trace        routers/fusion /wuxing  ✗ ohne Offset
   Jahr/Monat: Instant ✓   routers/fusion /tst  ✗   routers/chart time_scales ✗ ohne Offset
   Tag: chart_local_dt     chronometry.py     ✗   bafe/time_model (/validate) ✓ mit Offset
        (+zi: tlst≥23) ✗   → personalize      ✗   fusion.true_solar_time_from_civil ✗ Vorzeichen
   Stunde TLST: ctx ✗      zwds/seed.py       ~ (nutzt nur ctx.eot_minutes, rechnet selbst ab UTC ✓)
```

Es gibt **vier** unabhängige TST-Implementierungen mit drei verschiedenen
Ergebnissen für denselben Input. Die einzige korrekte, von einem Endpoint
genutzte Implementierung ist der `/validate`-Pfad (`bafe/time_model.py`).

### 1.1 Root Cause (DEV-2026-009)

`bazi_engine/time_context.py`:

```python
civil_hours = civil_local.hour + civil_local.minute / 60 + civil_local.second / 3600
delta_t_long = longitude_deg * 4 / 60
raw_tlst = civil_hours + delta_t_long + (eot_min / 60)     # ← tz-Offset fehlt
```

Korrekt ist `TLST = UTC + lon·4 min + EoT` (so dokumentiert in
`docs/fusion/04_solar_time.md`, so implementiert in `solar_time.true_solar_time`
mit Offset, so im ZWDS-Seed). Die Formel wurde in FBP-01-002 aus dem damals
schon falschen Inline-Code des `/calculate/tst`-Endpoints übernommen
(Plan `2026-05-14-phase1-effective-time-model.md`, Zeile 23: „This is the
formula `EffectiveTimeContext.tlst_hours` must match“) und per Test
`test_tlst_formula_matches_calculate_tst_endpoint` **festgepinnt**. FBP-01-003
hat anschließend den Endpoint auf dieselbe Funktion umgestellt — Konsistenz
wurde hergestellt, Korrektheit nie geprüft (Audit §11 nennt genau diese Lücke
als „not answered“).

Hannover-Repro (`1990-07-15T15:44:00`, `Europe/Berlin`, lon 9.732):

| Größe | Engine | Referenz (swisseph) |
|---|---|---|
| UTC | 13:44 | 13:44 |
| LMT | 14:22:55 | 14:22:55 |
| EoT | −5,78 min | −5,92 min |
| **TLST** | **16:17 (Shen)** | **14:17 (Wei)** |

### 1.2 Folgefehler

- **DEV-2026-010 (Fold):** Die Funktion nimmt einen *naiven* ISO-String und
  hängt die Zone mit `fold=0` an. Für die zweite Instanz einer doppelten
  Herbst-Uhrzeit (fold=1) ist UTC und damit LMT/TLST 1 h zu früh. `BaziInput.fold`
  trägt die Information, wird aber nicht durchgereicht.
- **DEV-2026-011 (TLST-Datum):** `date_rollover` existiert, wird aber weder
  für die Tagessäule (`_dt_for_day_pillar`) noch im Zi-Rollover berücksichtigt.
  Westlich des Zonenmeridians ist TLST zwischen Mitternacht und ~01:30 zivil
  noch am Vortag → falsche Tagessäule bei `standard=TLST`.
- **DEV-2026-008 (korrigierte Diagnose):** `/calculate/wuxing` und `/chart`
  rufen `true_solar_time(civil, lon, doy)` **ohne** Offset → civil wird als LMT
  behandelt. Der Register-Eintrag erklärt `/calculate/tst` zur Referenz — die
  ist aber selbst falsch. Beide Seiten sind falsch, auf verschiedene Art.
- **DEV-2026-012 (`true_solar_time_from_civil`):** Vorzeichen des Terms
  `(standard_meridian − longitude)` ist für Ost-Längen invertiert; außerdem
  `round(lon/15)*15` als Zonenmeridian ignoriert Sommerzeit und krumme Zonen.
  Keine Aufrufer außer `tests/test_fusion.py`.
- **GT6 (bekannt):** Trace-Tag via `apply_day_boundary` (+1 h) vs. Engine-Zi-
  Rollover via `ctx.tlst_hours`. Das strikte xfail in
  `tests/test_bazi_trace_endpoint.py` kippt mit dem Fix von DEV-2026-009 **ohne**
  dass GT6 gelöst wäre (Berlin 23:30 CET → TLST 23:09 → Rollover feuert → Trace
  und Headline stimmen zufällig überein). GT6 muss daher im selben Schnitt
  behoben werden.
- **Zeitgleichung:** Näherung nach Tag-des-Jahres ignoriert Jahr und Uhrzeit;
  Fehler ≤ 0,77 min. Kein Blocker, aber eine Präzisionslücke, die genau an
  2-h-Binkanten entscheidet. `swe.time_equ` liefert den exakten Wert auch im
  Moshier-Fallback (gemessene Differenz SE1 vs. Moshier < 1e-3 min).
- **CLI:** `--standard` kennt nur `CIVIL|LMT` (Ergonomie, P3).

### 1.3 Was korrekt ist (und so bleiben muss)

- `resolve_local_iso` / `parse_local_iso` (DST-Gap/Fold-Semantik).
- `to_chart_local` für CIVIL/LMT; `ctx.lmt_local`, `ctx.utc`, `ctx.tz_offset_minutes`.
- `hour_branch_index_from_tlst` (HALF_OPEN-Bins, Zi = [23, 1)).
- Jahres- und Monatsgrenzen (Instant-Vergleich gegen Jieqi, standardunabhängig).
- `bafe/time_model.py` (`/validate`): übergibt den Offset korrekt.
- `zwds/seed.py`: rechnet TLST selbst ab UTC; nutzt nur `ctx.eot_minutes`.

---

## 2. Referenzkorpus und Tests (in diesem Increment geliefert)

- `scripts/gen_tlst_reference_corpus.py` — Generator; Orakel ausschließlich
  `swe.time_equ` + `swe.lmt_to_lat`, kein Import aus `time_context`/`solar_time`.
  `--check` erkennt Drift (Toleranz 1e-3 für den SE1/Moshier-Rundungsunterschied).
- `tests/fixtures/tlst_reference_corpus_v1.json` — 21 Fälle: Hannover, Doku-Beispiel
  Berlin, Madrid (Fixture-Zwilling 02:00, echte EoT-Divergenz 02:20, Rollover −1
  um 00:30), GT6-Fixture, UTC-Identität, Rollover +1, Auckland (+13), Kathmandu
  (+5:45), St. John's (−3:30), Chengdu (Zonenmeridian 120° E), New York, Los
  Angeles, Teheran, Lissabon (Offset 0, lon −9), DST-Fold 0/1, London 1950,
  Singapur 1965 (+7:30).
- `tests/test_tlst_reference_corpus.py` — 222 Tests:
  - **178 grün heute:** Korpus-Reproduzierbarkeit gegen Live-swisseph, das
    Blatt `true_solar_time` mit Offset, LMT/UTC/Offset des Kontexts,
    EoT-Schranke (Jahres-Sweep), Binregel, Referenzfakten für die
    Fixture-Migration (§4.2), LMT-Kontrolle via HTTP (Hannover → Wei).
  - **44 `xfail(strict=True)`-Tripwires** (Konvention aus GT6): je Deviation
    pinnen sie die *korrekte* Erwartung und werden beim Fix rot → Marker und
    Register-Status sind im Fix-Commit zu entfernen. Enthalten: Engine-Kontext
    (Stunden, Zweig, Datum, Zonen-Invarianz, TLST−LMT=EoT), Fold, Vorzeichen,
    HTTP-Grenze (`/calculate/tst`, `/v1/chronometry/resolve`, `/calculate/bazi`
    Trace+Stundensäule, `/calculate/wuxing`, `/chart`), TLST-Tagessäule.

Verifikation: SWIEPH und MOSEPH jeweils `178 passed, 44 xfailed`; Gesamtsuite
unter SWIEPH grün; `ruff` und `check_complexity.py --check` bestanden.

---

## 3. Zielarchitektur (Soll)

**Ein** Pfad, Instant-basiert, Layer 2:

```python
# time_context.py (Soll-Skizze)
def compute_effective_time_context_from_instant(civil_local: datetime, longitude_deg: float) -> EffectiveTimeContext:
    utc = civil_local.astimezone(timezone.utc)
    lmt_local = utc.astimezone(_LongitudeMeanTime(longitude_deg))
    eot_min = equation_of_time_at(utc)            # s. Entscheidung E2
    tlst_instant = utc + timedelta(minutes=longitude_deg * 4 + eot_min)   # naive UTC-Achse, KEIN tzinfo
    tlst_hours = tlst_instant.hour + tlst_instant.minute/60 + tlst_instant.second/3600 + µs
    date_rollover = (tlst_instant.date() - civil_local.date()).days
    ...

def compute_effective_time_context(birth_local_iso, tz_name, longitude_deg, *, fold: int = 0):
    civil_local = datetime.fromisoformat(birth_local_iso).replace(tzinfo=ZoneInfo(tz_name), fold=fold)
    return compute_effective_time_context_from_instant(civil_local, longitude_deg)
```

Invarianten (als Tests formuliert, teils schon im Korpus):

1. Zonen-Invarianz: gleicher Instant, andere Zonenbezeichnung → gleiches `tlst_hours`.
2. `TLST − LMT ≡ EoT` (zirkulär, ±0,05 min).
3. `tlst_date == civil_date + date_rollover`, `date_rollover ∈ {−1, 0, +1}`.
4. Fold-Treue: `ctx.utc == civil_local.astimezone(UTC)` für fold 0 und 1.
5. FBP-01-006 bleibt: TLST ist keine `tzinfo` (keine `tlst_local`-Zone im Kontext).
6. Alle Endpoints, die „true solar time“ ausgeben, liefern für denselben
   Input dieselbe Zahl (±EoT-Näherungsbudget, nach E2 exakt).

**Entscheidungen (Empfehlung, Gegenargument, Freigabe durch Owner):**

- **E1 — Fix in `/v1` statt Deferral auf `/v2`.** DEV-2026-008 hat auf v2
  vertagt, um „Reproduzierbarkeit historischer Signaturen“ zu wahren.
  Gegenargument: ein um 2 h falscher Wert in einem Feld namens
  `true_solar_time` ist keine Signatur, sondern ein Defekt; die
  Phase-0-Regel verbietet *stille* v1-Änderungen, nicht korrigierende. Empfehlung:
  loud fix — Engine-Build-Label `__version__` bumpen, CHANGELOG-Eintrag
  „Behavior change“, OpenAPI-Beschreibungen anpassen, Snapshots regenerieren.
  Headline-Säulen für CIVIL/LMT bleiben byte-identisch (Regressionssuite
  `test_regression_v1_compatibility.py` als Beweis).
- **E2 — Zeitgleichung aus swisseph.** Option A (Minimalfix): Näherung
  beibehalten (≤ 0,77 min). Option B: `swe.time_equ(jd_ut)` via `ephemeris.py`
  (Layer 2 → Layer 2 erlaubt); liefert ±0 auch ohne SE1-Dateien. Kosten: die
  Attestierungs-Entscheidung FQ-ATT-02 („`/calculate/tst` berührt keine
  Swiss-Ephemeris-Funktion“) muss revidiert und der `/tst`-Quality-Block um
  `ephemeris_mode` ergänzt werden; `solar_time.py` bleibt reines Blatt
  (`test_solar_time_has_no_internal_imports`). Empfehlung: **A im Fix-Schnitt,
  B als Folge-Increment** mit Feld `eot_source: "spencer_1971" | "swisseph"` in
  Trace und `/tst`, damit die Umstellung nachvollziehbar ist.
- **E3 — `/calculate/wuxing.true_solar_time` und `/chart.time_scales.tlst_hours`**
  auf denselben Kontext umstellen (Minimal: Offset übergeben; besser: Kontext
  nutzen). Wire-Wert ändert sich — s. E1.
- **E4 — `fusion.true_solar_time_from_civil`** entfernen (einziger Aufrufer:
  Test). Falls Paket-API-Stabilität gewünscht: auf `true_solar_time(..., tz)`
  delegieren und `DeprecationWarning` emittieren. Empfehlung: entfernen.
- **E5 — TLST-Tagessäule:** Unter `standard=TLST` gilt das solare Datum:
  `chart_date = civil_date + date_rollover (+1 bei zi und tlst_hours ≥ 23)`.
  Das ist eine Domain-Entscheidung (DOMAIN_REVIEW_REQUIRED analog FBP-02-002);
  bis zur Freigabe als eigener Task mit Tripwire DEV-2026-011.

---

## 4. Umsetzungsplan (test-first, review-gated)

Reihenfolge ist Blast-Radius-sortiert: erst Blätter ohne Wire-Änderung, dann
der Kern, dann Snapshots/Contract.

### Task T1 — DEV-2026-012: `true_solar_time_from_civil` (P2, kein Wire-Impact)
- Entfernen (E4) oder Vorzeichen fixen + explizite `tz_offset`-Pflicht.
- Tests: `tests/test_fusion.py::TestTrueSolarTimeFromCivil` anpassen/entfernen;
  Tripwire `test_true_solar_time_from_civil_sign_convention` wird grün →
  xfail-Marker entfernen.
- Blast radius: nur `bazi_engine/fusion.py` Export; grep belegt keine Aufrufer.

### Task T2 — DEV-2026-010: Fold-treuer Kontext (P1, kein Wire-Impact für fold=0)
- `compute_effective_time_context(..., fold=0)` + `..._from_instant(civil_local, lon)`.
- Aufrufer durchreichen: `bazi.py::_effective_time_context_for_input` (`inp.fold`),
  `routers/bazi.py::_build_derivation_trace`, `chronometry.py`, `routers/fusion.py` `/tst`
  (aus `resolve_local_iso` kommt bereits ein aware `dt` → `_from_instant` nutzen).
- Tests: Korpus-Fold-Tripwire; neuer Test „fold=1 Trace zeigt +01:00 Offset“ an
  der HTTP-Grenze (`/calculate/bazi` mit `ambiguousTime="later"`).
- Blast radius: nur ambiguöse Herbst-Zeiten (fold=1); keine Snapshot-Fälle betroffen
  (geprüft: keine `dst`-Snapshot-Fixtures mit fold=1 und TLST).

### Task T3 — DEV-2026-009: Kernformel auf UTC-Achse (P0, **Wire-Impact**)
- `time_context.py` gemäß §3; `date_rollover` aus `tlst_instant`.
- Tests, die den Bug pinnen, **umschreiben** (nicht löschen):
  - `tests/test_bazi_time_context.py::test_tlst_formula_matches_calculate_tst_endpoint`
    → neue Erwartung `(utc_hours + lon·4/60 + EoT) % 24`, plus Zonen-Invarianz.
  - `tests/test_bazi_tlst_hour_pillar.py`: Fixture `02:00` → `02:20` Madrid
    (`madrid_feb_0220_cet`: LMT Chou vs. TLST Zi, echte EoT-Divergenz); der
    Docstring-Kommentar „TLST hours: 1.522“ ist der Bug-Wert und wird durch 0.860
    ersetzt.
  - `tests/test_bazi_zi_day_boundary.py`: Erwartungen bleiben gültig (Madrid 23:00
    → TLST 21:31 < 23; 02:00 Folgetag → anderer Tag), Kommentare auf Referenzwerte
    aktualisieren.
  - `tests/test_tst_endpoint_consistency.py`: bleibt (Konsistenz Endpoint↔Kontext),
    zusätzlich Absolutwert gegen Korpus.
  - Korpus-Tripwires DEV-2026-009 (36 Stück) → Marker entfernen.
- **GT6 im selben Schnitt** (sonst XPASS-strict-Rot): `_build_derivation_trace`
  darf den Tag nicht via `apply_day_boundary` neu ableiten; Engine stellt
  `dt_for_day`/`day_jdn` in `BaziResult` bereit (frozen, additiv) oder beide
  rufen `_dt_for_day_pillar`. xfail in `test_bazi_trace_endpoint.py` entfernen,
  OpenAPI-Beschreibung des `/trace`-Endpoints (Known-limitation-Absatz) streichen
  → `python scripts/export_openapi.py`, `redocly lint`, TS-Codegen.
- Snapshots: 50 × `tests/snapshots/swieph/*__bazi.json`
  (`derivation_trace.time_resolution.tlst_hours`, Säulen unverändert — alle 50
  sind `effective_standard: CIVIL`) und `chronometry_canonical.json` (beide
  Backends: `true_solar_time` „15:23“ → „13:23“) via **manuellem Workflow
  `update-swieph-snapshots.yml`** (review-only Patch), MOSEPH lokal mit
  `UPDATE_SNAPSHOTS=1`. Hinweis: die MOSEPH-Snapshots sind **heute schon** lokal
  rot (200 `test_snapshot_stability`-Fails vor jeder Änderung) — vorbestehende
  Drift, separat zu klären, nicht Teil dieses Fixes.
- `tests/test_personalize_endpoint.py::_chronometry_sample` („15:23“) ist ein
  statisches Mock → bewusst mit anpassen, damit das Sample nicht den Bug-Wert
  dokumentiert.
- Engine-Build-Label `bazi_engine/__init__.py::__version__` bumpen (Pflicht bei
  Snapshot-Regeneration), CHANGELOG „BREAKING (numeric): …“, `docs/precision/deviations.md`
  Status, `3-code/tasks.md`.
- Blast radius (Endpoints): `/calculate/tst`, `/calculate/bazi{,/trace,/natal,/dayun}`
  bei `standard=TLST` (Stundensäule, Zi-Rollover) und Trace für alle Standards,
  `/chronometry/resolve`, `/personalize`, `/v1/match/bazi-hehun` (TLST-Input),
  ZWDS **nicht** (eigener Pfad, nur `eot_minutes`). Bazodiac-Konsumenten: Felder
  bleiben, Werte ändern sich → Release-Note.

### Task T4 — DEV-2026-008: `/calculate/wuxing` + `/chart` auf Kontext (P1, Wire-Impact)
- Beide Stellen rufen `compute_effective_time_context_from_instant(dt, lon)`;
  `equation_of_time`/`true_solar_time` werden in Routern nicht mehr direkt genutzt.
- Tests: Korpus-Tripwires DEV-2026-008; Cross-Endpoint-Gleichheitstest
  (`/tst` == `/wuxing.true_solar_time` == `/chart.time_scales.tlst_hours` ==
  `/chronometry.true_solar_time`) als dauerhafter Drift-Wächter.
- Snapshots: 50 × `*__wuxing.json` (`true_solar_time`, `equation_of_time`).
- Register DEV-2026-008 auf „Resolved (v1, loud)“ setzen; Begründung E1.

### Task T5 — DEV-2026-011: TLST-Datum für die Tagessäule (P1, Domain-Review)
- Nach Freigabe E5: `_dt_for_day_pillar` nutzt `civil_date + ctx.date_rollover`
  (+ zi-Regel). Trace konsistent (T3/GT6-Mechanik).
- Tests: Boundary-Matrix 22:59/23:00/23:59/00:00/00:59/01:00 × {Ost/West des
  Meridians} × {midnight, zi}; Tripwire `test_tlst_day_pillar_uses_tlst_date_before_solar_midnight`.
- Blast radius: nur `standard=TLST` zwischen solarer und ziviler Mitternacht;
  Baseline `tlst_neighborhood` in `bazi_baseline_v1.json` ist LMT-only → unberührt.

### Task T6 — E2 Option B: exakte Zeitgleichung (P2, Folge-Increment)
- `ephemeris.py::equation_of_time_minutes(jd_ut)` (swe.time_equ) → Kontext nutzt
  sie; `solar_time.equation_of_time` bleibt als Blatt für `/validate`-Degraded-Pfad.
- Provenance-Feld `eot_source`; FQ-ATT-02-Revision; `/tst` quality-Block.
- Tests: Korpus-Toleranz von 0,8 min auf 1e-3 min senken (`HOURS_TOL_APPROX` → exakt).

### Task T7 — Hygiene (P3)
- CLI `--standard` um `TLST` erweitern.
- `docs/precision/deviations.md` DEV-2026-008 Expected-Formel korrigieren (in
  diesem Increment erledigt), Plan `2026-05-14-phase1-effective-time-model.md`
  Zeile 23 mit Hinweis versehen (erledigt), `docs/fusion/04_solar_time.md` ist
  bereits korrekt.
- `zwds/seed.py`: nach T3 kann der Seed `ctx.tlst_hours`/`date_rollover` direkt
  konsumieren; Konsistenztest ZWDS-Offset == Kontext hinzufügen.
- CI-Gate: `scripts/gen_tlst_reference_corpus.py --check` in den Lint-Job
  (Orakel-Drift bei pyswisseph-Bumps sichtbar machen).

### Reihenfolge / Gates

| Schritt | Gate |
|---|---|
| T1, T2 | Gesamtsuite grün; keine Snapshot-Änderung (prüfbar mit `test_snapshot_stability` unter SWIEPH). |
| T3 (+GT6) | Alle DEV-2026-009-Tripwires grün (Marker entfernt), `test_regression_v1_compatibility` byte-identisch für CIVIL/LMT, Snapshot-Patch aus Workflow reviewt, OpenAPI-Drift-Check + Codegen grün, `__version__` gebumpt, CHANGELOG. |
| T4 | Cross-Endpoint-Gleichheit grün; wuxing-Snapshots reviewt. |
| T5 | Domain-Sign-off (E5) dokumentiert; Boundary-Matrix grün. |
| T6 | `eot_source` im Trace; Attestierungs-Tests angepasst. |

Rollback-Pfad: T1–T2 sind rein additiv/lokal (Revert ohne Snapshot-Folgen).
T3/T4 werden als je **ein** Commit mit Snapshot-Patch geschnitten, damit ein
Revert die Snapshots mitnimmt.

---

## 5. Risiken und Gegenargumente

- **„Konsumenten hängen an den v1-Werten.“** Nur Felder, die explizit
  „true solar time“ heißen, ändern sich; CIVIL/LMT-Säulen nicht. Ein Konsument,
  der 16:17 statt 14:17 verbaut hat, hat einen Fehler verbaut. Mitigation: loud
  release (E1), Versions-Label, Release-Note mit Beispielwert.
- **„Fix könnte Monats-/Jahressäulen verändern.“** Nein — die vergleichen
  Instants gegen Jieqi-Instants; standardunabhängig. Beweis: Regressionssuite.
- **„Die Näherung reicht.“** Für Säulen fast immer; an Binkanten entscheidet
  < 1 min. Daher E2-B als Folge-Increment, nicht als Blocker.
- **Übersehene Pfade:** `grep` über `tlst|true_solar|equation_of_time|time_standard`
  ist vollständig im Plan abgebildet (bazi, routers/{bazi,fusion,chart,chronometry,
  personalize,natal,dayun,match}, chronometry, bafe/time_model, zwds/seed, cli).
  Services (`soulprint`, `daily_*`, `experience`) nutzen `time_standard="CIVIL"`
  fest → nicht betroffen.

---

## 6. Verifikationsstatus dieses Increments

| Prüfung | Ergebnis |
|---|---|
| `SE_EPHE_PATH=/tmp/ephe pytest tests/` (CI-äquivalent, vor Änderung) | 3769 passed, 102 skipped, 1 xfailed |
| `SE_EPHE_PATH=/tmp/ephe pytest tests/test_tlst_reference_corpus.py` | 178 passed, 44 xfailed |
| `pytest tests/test_tlst_reference_corpus.py` (MOSEPH) | 178 passed, 44 xfailed |
| `ruff check` neue Dateien | clean |
| `scripts/check_complexity.py --check` | passed |
| `scripts/gen_tlst_reference_corpus.py --check` (beide Backends) | OK |
| `pytest tests/` (MOSEPH, lokal) | 200 vorbestehende `test_snapshot_stability`-Fails + 1 env-abhängiger `test_security_findings`-Fail — unabhängig von dieser Änderung (identisch vor/nach) |
