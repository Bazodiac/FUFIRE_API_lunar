# TLST Fix-Sprint 2 — T5, T6, T7 und abschließendes Code-Review

**Datum:** 2026-10-16
**Vorgänger:** `docs/plans/2026-10-15-true-solar-time-remediation.md` (T1–T4 gemerged: #55, #56, #57; Engine-Label `1.0.0-rc3-20261016`)
**Status:** Entscheidungen gefallen (Owner, 2026-10-16): **E5 = A**, **E6 = E6-M (Meeus)**, **E7 = ja**, **E8 = R3**. S-1 umgesetzt (dieser PR); S-2, S-3, S-4 folgen.
**Branch-Regel:** jeder Sprint-PR startet neu von `origin/master` auf `claude/vibrant-faraday-ki071b` (Session-Regel); nach jedem Merge Reset.

---

## 0. Sprint-Ziel und Definition of Done

**Ziel:** Die TLST-Pipeline ist in allen drei Dimensionen vollständig: Stunde (✅ T3), Datum der Tagessäule (T5), Zeitgleichung ohne Näherungsbudget (T6). Danach bleibt kein `xfail(strict)` im Referenzkorpus, kein TLST-Pfad außerhalb des gemeinsamen Kontexts, und ein unabhängiges Review hat den Gesamtdiff seit `03c471c` (#55) gelesen.

**DoD (alle müssen erfüllt sein):**

| # | Kriterium | Nachweis |
|---|---|---|
| D1 | `tests/test_tlst_reference_corpus.py` enthält **kein** `xfail` mehr | `grep -c xfail` = 0 |
| D2 | Boundary-Matrix Tagessäule (§3.1) grün auf SWIEPH und MOSEPH | neue Testdatei `tests/test_bazi_tlst_day_pillar.py` |
| D3 | EoT-Abweichung Engine vs. `swe.time_equ` ≤ 0,1 min über 1950–2030 (statt 0,8 min) | `test_eot_approximation_bound_full_year_vs_swisseph` mit verschärfter Toleranz |
| D4 | Alle fünf TST-Oberflächen gleich (bestehender Wächter) **und** `eot_source` auf `/calculate/tst` + Trace sichtbar | `test_all_tst_surfaces_agree`, OpenAPI-Drift-Check |
| D5 | CLI akzeptiert `--standard TLST`; Korpus-`--check` läuft im CI-Lint-Job | `python -m bazi_engine.cli … --standard TLST`, `ci.yml` |
| D6 | Register: DEV-2026-011 Resolved; `3-code/tasks.md` FBP-TST-005…007 Done; Plan §9 nachgetragen | Diff |
| D7 | Unabhängiges Review (§5) durchgeführt, Findings triagiert, blockierende behoben | `docs/reports/2026-10-xx-tlst-sprint-2-review.md` |
| D8 | CI `release-gate` grün auf jedem Sprint-PR; `test_regression_v1_compatibility` byte-identisch für CIVIL/LMT | CI |

---

## 1. Entscheidungen, die vor dem Start fallen müssen

### E5 — Datum der Tagessäule unter `standard=TLST` (blockiert T5)

**Frage:** Soll unter `standard=TLST` das Kalenderdatum, aus dem die Tagessäule abgeleitet wird, dem **apparenten Sonnendatum** folgen (Datum des TLST-Instants, `civil_date + date_rollover`), oder weiterhin dem **zivilen Datum**?

Konkret für Madrid, 2024-02-22 **00:30 CET**, Längengrad −3,70°: TLST ist **23:01 am 21.02.** Heute liefert die Engine die Tagessäule des **22.02.** (ziviles Datum). Unter Option A wäre es die des **21.02.**

| Option | Regel | Konsequenz |
|---|---|---|
| **A — solares Datum (Empfehlung)** | Tag = `civil_date + date_rollover`; bei `boundary=zi` zusätzlich +1, wenn `tlst_hours ≥ 23` | Westlich des Zonenmeridians fällt der Zeitraum zwischen solarer und ziviler Mitternacht auf den Vortag; östlich (z. B. Auckland NZDT, −81 min Zonenversatz; Chengdu −64 min) analog. Konsistent mit dem **LMT-Pfad**, der heute schon das LMT-Datum nimmt (`to_chart_local`). Entspricht der klassischen 真太阳时-Praxis: das ganze Chart in Sonnenzeit. |
| B — ziviles Datum (Status quo) | Tag aus dem zivilen Datum, nur die Stunde aus TLST | Intern widersprüchlich: TLST 23:01 (Zi-Stunde des Vortags) wird mit dem Datum des Folgetags kombiniert. Unter `boundary=zi` kommt heute sogar `civil + 1` heraus, also TLST-Datum **+2**. Diese Inkonsistenz ist DEV-2026-011. |

**Gegenargument zu A:** Für Konsumenten, die TLST nur für die Stunde wollten, ändert sich bei Geburten in dem Fenster auch die Tagessäule. Antwort: Das Fenster ist exakt der Bereich, in dem das zivile Datum astronomisch falsch ist; wer das zivile Datum will, hat `CIVIL`. A ist die einzige Variante, die TLST und LMT dieselbe Datumsregel gibt.

**Benötigt:** „A“ oder „B“ (plus ggf. abweichende Zi-Regel).

### E6 — Quelle der exakten Zeitgleichung (T6)

Heute: Spencer/NOAA-Näherung nach Tag-des-Jahres, Fehler bis 0,77 min (gemessen gegen `swe.time_equ`, 1950–2026). Das entscheidet an 2-h-Binkanten in < 1 min Abstand.

| Option | Beschreibung | Bewertung |
|---|---|---|
| **E6-M — Meeus in `solar_time.py` (Empfehlung)** | Zeitgleichung nach Meeus, *Astronomical Algorithms* Kap. 28 (mittlere Sonnenlänge, Obliquität, Exzentrizität als Polynome in julianischen Jahrhunderten), Eingabe JD UT, reine Mathematik, stdlib-only. Erwartete Abweichung zu swisseph < 0,05 min. | Erhält die Reinheitsregel von `solar_time.py` (`test_solar_time_has_no_internal_imports`) **und** die am 2026-07-01 beschlossene Invariante „`/calculate/tst` macht keine Swiss-Ephemeris-Arbeit“ (Spy-Test `tests/test_attestation_contract.py` F3). Kein Layer-, kein Attestierungs-Umbau. |
| E6-S — `swe.time_equ` via `ephemeris.py` | Exakt per Definition (gleicher Oracle wie der Korpus). | Bricht den F3-Spy-Test und die 2026-07-01-Entscheidung; `/tst` bräuchte `quality_flags.ephemeris_mode`; `time_context` bekäme eine pyswisseph-Abhängigkeit. Mehr Umbau für ≤ 0,05 min Gewinn gegenüber E6-M. |

**Benötigt:** „E6-M“ oder „E6-S“.

### E7 — Snapshot-Regenerationsverfahren dokumentieren (T7, keine Blockade)

In #56 und #57 wurden die SWIEPH-Snapshots lokal mit den SHA-verifizierten Ephemeriden regeneriert und per Skript auf materielle Felder reduziert, statt über den manuellen Workflow. Vorschlag: dieses Verfahren als zweiten sanktionierten Weg in `CLAUDE.md` und als Skript `scripts/minimize_snapshot_diff.py` festschreiben. Alternative: Verfahren verwerfen und künftig strikt den Workflow nutzen. **Benötigt:** ja/nein (Default: ja, da bereits zweimal reviewt und gemerged).

### E8 — Review-Modus (§5)

| Option | Was passiert |
|---|---|
| **R1 — Selbst-Review in dieser Session (Empfehlung als Minimum)** | `/code-review` mit Level `high` über den kumulierten Diff `03c471c..HEAD` plus ein adversarialer Subagent mit eigenem Kontext (kein Zugriff auf meine Schlussfolgerungen, nur Code + Korpus). Findings werden als Review-Kommentare auf dem Sprint-PR hinterlegt. |
| R2 — Codex (extern) | Du startest Codex auf dem Repo mit dem Prompt aus §5.3. Findings kommen als PR-Review zurück; ich triagiere und fixe. |
| R3 — beides | R1 zuerst, dann R2 auf dem bereinigten Stand. |

**Benötigt:** R1, R2 oder R3.

---

## 2. Sprint-Struktur: drei PRs, eine Review-Schleife

| PR | Inhalt | Wire-Änderung | Engine-Label | Abhängigkeit |
|---|---|---|---|---|
| **S-1** | T5: TLST-Datum der Tagessäule (DEV-2026-011) | ja, nur `standard=TLST`-Requests im Mitternachtsfenster | `1.0.0-rc4-20261016` | E5 |
| **S-2** | T6: exakte Zeitgleichung + `eot_source`-Provenance | ja: alle TLST-Werte verschieben sich ≤ 0,8 min; neues Feld `eot_source` | `1.0.0-rc5-2026MMDD` | E6, S-1 gemerged |
| **S-3** | T7: Hygiene (CLI, CI-Korpus-Check, ZWDS-Konsistenztest, Doku E7, Snapshot-Skript) | nein | unverändert | S-2 gemerged |
| **S-4** | Review-Findings (nur falls nötig) | je nach Finding | je nach Finding | E8, S-3 gemerged |

Alternative (kleinerer Snapshot-Churn): S-1 und S-2 in einem PR mit einem Label-Bump. Nachteil: zwei verschiedene Semantikänderungen in einem Review. Empfehlung: getrennt lassen; der Label-Diff ist mit dem Minimierungsskript pro Datei eine Zeile.

Jeder PR durchläuft dieselbe Gate-Liste: ruff · mypy · `check_complexity --check` · `export_openapi --check` · Gesamtsuite SWIEPH (`SE_EPHE_PATH=/tmp/ephe`) · Gesamtsuite MOSEPH · Snapshot-Verify ohne Update · Korpus `--check` · `test_regression_v1_compatibility`.

---

## 3. S-1 — T5: Tagessäule folgt dem TLST-Datum (FBP-TST-005)

### 3.1 Spezifikation (Option A)

```
base_date      = civil_date + ctx.date_rollover          # Datum des TLST-Instants
if boundary == "zi" and policy.time_standard_for_day_rollover == "TLST":
    chart_date = base_date + (1 if ctx.tlst_hours >= policy.zi_start_hour else 0)
else:                                                    # midnight
    chart_date = base_date
```

Nur `_dt_for_day_pillar` in `bazi_engine/bazi.py` ändert sich; `to_chart_local` bleibt unangetastet (FBP-01-004-Guard `test_to_chart_local_treats_tlst_as_civil_fallthrough` bleibt gültig: TLST ist weiterhin keine tzinfo). Der Trace folgt automatisch über `BaziResult.chart_day_dt` (GT6-Mechanik aus #56).

Jahr- und Monatssäule bleiben instant-basiert (Jieqi-Vergleich) und sind nicht betroffen.

### 3.2 Testmatrix (test-first)

Neue Datei `tests/test_bazi_tlst_day_pillar.py`, Referenzwerte aus dem Korpus-Generator (swisseph), **nicht** aus der Engine:

| TLST-Stunde | westlich (Madrid −3,70°, CET) | östlich (Auckland 174,76°, NZDT) | Erwartung midnight | Erwartung zi |
|---|---|---|---|---|
| 22:59 | ja | ja | TLST-Datum | TLST-Datum |
| 23:00 | ja | ja | TLST-Datum | TLST-Datum + 1 |
| 23:59 | ja | ja | TLST-Datum | TLST-Datum + 1 |
| 00:00 | ja | ja | TLST-Datum | TLST-Datum |
| 00:59 | ja | ja | TLST-Datum | TLST-Datum |
| 01:00 | ja | ja | TLST-Datum | TLST-Datum |

Plus: Madrid 00:30 CET (Rollover −1), Berlin GT6 23:30 CET (Rollover 0, zi feuert), ein Fall mit `date_rollover = +1` (UTC-Zone, lon +30°, 23:30), und die Invariante „TLST- und LMT-Tagessäule stimmen überein, wenn LMT und TLST auf derselben Seite der Grenze liegen“. Jeder Fall vergleicht gegen die Tagessäule eines CIVIL-Requests am erwarteten Datum um 12:00 (gleiches Orakel wie der Tripwire `test_tlst_day_pillar_uses_tlst_date_before_solar_midnight`, der zum Regressionstest wird).

### 3.3 Blast Radius

- Betroffen: nur `standard=TLST` im Fenster zwischen solarer und ziviler Mitternacht (bzw. 23:00-Grenze). CIVIL/LMT byte-identisch — Beweis: `tests/test_regression_v1_compatibility.py` + Snapshots (alle CIVIL; Diff nur `engine_version`).
- Baseline `tests/fixtures/bazi_baseline_v1.json`, Kategorie `tlst_neighborhood`: nutzt LMT → unberührt.
- `routers/natal.py`, `dayun.py`, `match.py` erben die Änderung über `compute_bazi`; keine eigene Logik.
- Docs: DEV-2026-011 → Resolved; `tests/test_bazi_zi_day_boundary.py` Docstrings prüfen (Erwartungen bleiben, da Madrid 23:00 → TLST 21:31 kein Rollover).

---

## 4. S-2 — T6: exakte Zeitgleichung + Provenance (FBP-TST-006)

### 4.1 Implementierung (E6-M)

- `solar_time.py`: neue Funktion `equation_of_time_jd(jd_ut: float) -> float` (Minuten), Meeus Kap. 28 (L0, e, M, ε nach Kap. 25/22; `E = y·sin2L0 − 2e·sinM + 4ey·sinM·cos2L0 − ½y²·sin4L0 − 5/4·e²·sin2M`). Reine Mathematik; die bestehende `equation_of_time(day_of_year)` bleibt für `/validate` (`bafe/time_model.py`, Degraded-Pfad) erhalten und bekommt einen Docstring-Hinweis.
- `time_context.py`: `jd_ut` aus `utc` (stdlib-Formel, keine swisseph-Abhängigkeit; `ephemeris.datetime_utc_to_jd_ut` nutzt `swe.julday` — deshalb eigene Berechnung oder Verschiebung dieser Hilfsfunktion nach `solar_time`), `eot_minutes = equation_of_time_jd(jd_ut)`, neues Feld `EffectiveTimeContext.eot_source: str = "meeus_1998"` (frozen, additiv).
- Oberflächen: `/calculate/tst` Response + `TimeResolutionTrace` + `ChronometryFrame` bekommen `eot_source` (additiv) → `export_openapi.py`, `redocly`/TS-Codegen (CI).
- `bafe/time_model.py` setzt `eot_prov = "approx_formula"` bereits; Wert dort auf `"spencer_1971"` harmonisieren (nur Label; Validate-Pfad bleibt Degraded).

### 4.2 Tests

- `tests/test_solar_time.py`: `equation_of_time_jd` gegen `swe.time_equ` über 1950–2030 alle 6 h: max |Δ| ≤ 0,1 min (Ziel < 0,05); Monotonie-/Stetigkeitsprüfung über Jahreswechsel; Rundung.
- Korpus: `HOURS_TOL_APPROX` von 0,8 min auf 0,1 min senken; Fixture-Referenzen bleiben unverändert (Orakel ist swisseph).
- `test_attestation_contract.py` F3-Spy bleibt unverändert grün (kein swisseph-Aufruf auf dem `/tst`-Pfad) — das ist der Beweis für E6-M.
- HTTP: `eot_source == "meeus_1998"` auf `/calculate/tst`, Trace, Chronometrie.

### 4.3 Blast Radius

- Alle TLST-Werte verschieben sich um ≤ 0,8 min (37 bazi-Snapshots `tlst_hours`, 48 wuxing `true_solar_time`, `equation_of_time` in wuxing, chronometry `equation_of_time_minutes`/`true_solar_time` auf Minutenraster evtl. ±1 min). Stundenzweig kann in Einzelfällen an Binkanten kippen — das ist der Zweck.
- Snapshots regenerieren (verifizierte Ephemeriden, minimierter Diff), Label-Bump, OpenAPI.
- `zwds/seed.py` konsumiert `ctx.eot_minutes` → ZWDS-TLST-Offset verschiebt sich ebenfalls ≤ 0,8 min; `tests/zwds/test_seed_pipeline.py::test_tlst_uses_apparent_solar_offset_anchored_to_utc` pinnt `7.8787 ± 1e-3` h → Erwartung aus swisseph neu ableiten.

---

## 5. S-3 — T7: Hygiene (FBP-TST-007)

| Punkt | Änderung | Test |
|---|---|---|
| CLI | `--standard` Choices um `TLST` erweitern (`bazi_engine/cli.py`) | `tests/test_cli.py` (falls vorhanden, sonst neu): `--standard TLST` liefert Hannover → Wei |
| CI | `uv run python scripts/gen_tlst_reference_corpus.py --check` im Lint-Job (`ci.yml` zwischen ruff und toolchain-assert) | CI grün; `assert_toolchain_versions.py` unverändert (kein Action-Pin betroffen) |
| ZWDS | Konsistenztest: `resolve_chronometry(..., "TLST").day_boundary_offset_hours · 60 == lon·4 + ctx.eot_minutes` | `tests/zwds/test_seed_pipeline.py` |
| Snapshot-Verfahren (E7) | `scripts/minimize_snapshot_diff.py` (aus den Ad-hoc-Skripten von #56/#57) + Abschnitt in `CLAUDE.md` Testing | `--check`-Modus des Skripts in einem Unit-Test |
| Doku | `docs/fusion/04_solar_time.md` um Meeus-Abschnitt ergänzen; `docs/precision/deviations.md` Abschluss; `3-code/tasks.md`; Plan §9 | Diff |

---

## 6. S-4 — Code-Review-Schleife (E8)

### 6.1 Umfang

Kumulierter Diff `03c471c..master` nach S-3 (vier Merges + Sprint-PRs): `time_context.py`, `solar_time.py`, `bazi.py`, `types.py`, `chronometry.py`, `routers/{bazi,fusion,chart}.py`, `zwds/seed.py`, alle neuen Tests, Korpus-Generator.

### 6.2 R1 — Selbst-Review (Minimum)

1. `/code-review --max-findings all` auf Level `high` über den kumulierten Diff.
2. Zusätzlich ein Subagent mit **eigenem** Kontext (bekommt nur: Diff, `docs/fusion/04_solar_time.md`, Korpus-JSON; **nicht** meine Pläne/Schlussfolgerungen), Auftrag: adversarial Pfade suchen, bei denen TLST, LMT und CIVIL inkonsistent werden (Fold, Schaltsekunden, Datumsgrenze, Längengrad ±180°, Zonen mit Offset > 12 h, historische Zonen mit krummen Offsets, Jahr < 1900).
3. Triage nach Repo-Regel: jedes Finding ist eine Behauptung, die gegen einen realen Aufrufpfad verifiziert wird; blockierende Findings → S-4-PR; Nicht-Findings werden mit Begründung im Review-Report abgelegt.

### 6.3 R2 — Codex-Prompt (zum Kopieren)

```
Repository: Bazodiac/FUFIRE_API_lunar, Branch master, Review-Bereich: git diff 03c471c..HEAD.
Kontext: True Local Solar Time (TLST) = UTC + longitude*4min + equation_of_time; definiert in
docs/fusion/04_solar_time.md; Referenzorakel tests/fixtures/tlst_reference_corpus_v1.json (Swiss Ephemeris).
Aufgabe: Adversariales Korrektheits-Review, keine Stil-Findings.
Suche konkret nach: (1) Pfaden, auf denen CIVIL, LMT und TLST für denselben Instant inkonsistente
Datum/Stunde liefern; (2) DST-Fold/Gap-Verlust zwischen resolve_local_iso und compute_effective_time_context_from_instant;
(3) Fehlern an Datumsgrenzen (date_rollover ±1, zi-Rollover bei 23:00 TLST) und bei Längengraden nahe ±180° /
Zonen-Offsets > 12 h; (4) Stellen, die noch solar_time.true_solar_time oder equation_of_time direkt aufrufen
statt time_context; (5) Trace-Felder, die der Headline-Antwort widersprechen können; (6) Testlücken in
tests/test_tlst_reference_corpus.py und tests/test_bazi_tlst_day_pillar.py.
Für jedes Finding: Datei:Zeile, konkreter Input, erwarteter vs. tatsächlicher Wert, Schweregrad (blocker/major/minor).
Keine Änderungen pushen; Findings als PR-Review auf dem offenen Sprint-PR hinterlegen.
```

### 6.4 Abschlussreport

`docs/reports/2026-10-xx-tlst-sprint-2-review.md`: Findings-Tabelle (ID, Quelle R1/R2, Schweregrad, Entscheidung, Commit), erneuter Grid-Lauf (18 432 Samples × 16 Zonen gegen `swe.lmt_to_lat`: Zweig-, Datums- und Stundenabweichung = 0 bei Toleranz 0,1 min), Gesamtsuite-Zahlen beider Backends.

---

## 7. Reihenfolge, Gates, Rollback

| Schritt | Gate vor Merge | Rollback |
|---|---|---|
| S-1 | DoD D2, D8; Korpus-Tripwire DEV-011 → grün; Register | Revert des Squash-Commits (Snapshots inklusive) |
| S-2 | DoD D3, D4, D8; F3-Spy grün; ZWDS-Seed-Test neu abgeleitet | Revert; `equation_of_time(doy)` bleibt im Code, Umschalten ist ein Einzeiler in `time_context` |
| S-3 | DoD D5, D6; CI-Lint mit Korpus-Check grün | Revert |
| S-4 | DoD D7; alle blockierenden Findings behoben oder begründet abgelehnt | — |

Risiken: (1) E6-M-Genauigkeit unter 0,1 min nicht erreicht → Fallback E6-S mit Attestierungs-Umbau, vorher Owner-Rückfrage. (2) Codex nicht verfügbar → R1 allein, im Report vermerkt. (3) Snapshot-Churn durch zwei Label-Bumps → mit Minimierungsskript eine Zeile pro Datei.

Aufwand (Netto-Arbeitszeit in dieser Session, inklusive Suiten auf beiden Backends): S-1 ≈ 1 h, S-2 ≈ 1,5 h, S-3 ≈ 45 min, S-4 ≈ 1 h plus Codex-Laufzeit.

---

## 8. Umsetzungsstand

| PR | Stand |
|---|---|
| S-1 (T5) | **Umgesetzt** (2026-10-16). `bazi.py::_dt_for_day_pillar`: TLST-Pfad nimmt `chart_local_dt + date_rollover` als Basis, Zi-Regel +1 bei `tlst_hours ≥ 23`. Neue Testdatei `tests/test_bazi_tlst_day_pillar.py`: Boundary-Matrix (Madrid west / Auckland ost × 22:58, 23:02, 23:58, 00:02, 00:58, 01:02 × midnight/zi), Orakel per `swe.lat_to_lmt`-Inversion, Erwartung = CIVIL-Säule am erwarteten Datum; Rollover −1/+1-Fälle; TLST==LMT-Invariante; CIVIL/LMT-Regressionsguard. Korpus ohne `xfail` (DoD D1). Label `1.0.0-rc4-20261016`. `scripts/minimize_snapshot_diff.py` (E7) eingeführt und für die Snapshot-Regeneration genutzt. |
| S-2 (T6) | **Umgesetzt** (2026-10-16). `solar_time.equation_of_time_jd(jd_ut)` nach Meeus (1998) Kap. 28 (Gl. 28.1 mit Sonnenposition Kap. 25, Nutation/Schiefe Kap. 22), rein stdlib; `jd_ut_from_datetime` (stdlib-JD, bit-identisch zu `ephemeris.datetime_utc_to_jd_ut`). Gemessen gegen `swe.time_equ`: max \|Δ\| = 0,058 min über 118 340 Stichproben 1950–2030 (6 h), Mittel −0,006 min, kein systematischer Offset; Stichprobe 1800–2200 ≤ 0,04 min. `EffectiveTimeContext.eot_source = "meeus_1998"`, additiv auf `/calculate/tst`, `TimeResolutionTrace`, `ChronometryFrame`/`/chronometry/resolve`/`/personalize`; bafe-Label `spencer_1971`. Korpus-Toleranz 0,8 → 0,1 min (Leaf `true_solar_time()` behält 0,8). ZWDS-Seed-Erwartung aus `swe.time_equ` abgeleitet (7,8726 h). F3-Spy unverändert grün. Label `1.0.0-rc5-20261016`, Snapshots regeneriert + minimiert (material: `equation_of_time`, `true_solar_time`, `time_resolution.eot_source`, Label; keine Säulenkippung in den Snapshot-Fällen). Hinweis: der Hannover-Fall formatiert jetzt `14:16` (14:16:59,7 Meeus vs. 14:17:00,5 swisseph — 0,8 s an der Minutenkante, Floor-Formatter); die HTTP-Tests prüfen die Formatierung toleranzbewusst. |
| S-3 (T7) | offen (CLAUDE.md-Abschnitt zu E7 folgt hier) |
| S-4 | offen |

