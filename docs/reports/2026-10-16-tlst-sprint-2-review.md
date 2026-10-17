# TLST Sprint 2 — Review-Report (S-4, Entscheidung E8 = R3)

**Datum:** 2026-10-16 · **Review-Bereich:** `git diff 03c471c..HEAD` (T1–T4, S-1–S-3; `bazi_engine/{time_context,solar_time,bazi,types,chronometry}.py`, `routers/{bazi,fusion,chart,chronometry}.py`, `zwds/seed.py`, Korpus-Generator, alle neuen Tests) · **Plan:** `docs/plans/2026-10-16-tlst-fix-sprint-2.md` §6

## 1. Durchführung

| Runde | Quelle | Setup |
|---|---|---|
| R1-a | `/code-review` (Level high, alle Findings) über den kumulierten Diff | eigener Kontext, Repo-Zugriff |
| R1-b | Adversarialer Subagent | **nur** Diff, `docs/fusion/04_solar_time.md`, Korpus-JSON und die Quelldateien; keine Pläne/Schlussfolgerungen des Autors; durfte Hypothesen gegen pyswisseph ausführen (29 Tool-Aufrufe, Probe-Skripte außerhalb des Repos) |
| R2 | Codex (externes Review) | **offen** — Prompt in Plan §6.3; wird vom Owner auf dem S-4-PR angestoßen |

Triage-Regel (CLAUDE.md): jedes Finding ist eine Behauptung, die gegen einen realen Aufrufpfad verifiziert wird; Fix nur bei realem Pfad und proportionalem Aufwand.

## 2. Findings

| ID | Quelle | Datei | Befund | Schwere | Verifikation | Entscheidung |
|---|---|---|---|---|---|---|
| F1 | R1-a #1, R1-b F1 | `routers/bazi.py:287` | `derivation_trace.hour.branch_index`/`local_hour` kamen aus der *zivilen* Uhr; unter `standard=TLST` widersprach der Trace der Headline-Stundensäule (Madrid 2024-02-22 02:20 CET: Trace Chou, Headline Zi; Hannover: Trace Shen, Headline Wei). Geschwister von GT6 — die Tagessäule war gefixt, die Stunde nicht. | **major** | bestätigt per TestClient | **Fix:** Trace nutzt `res.pillars.hour.branch_index` (die Engine-Entscheidung); `local_hour = int(tlst_hours)` unter TLST. Tests: `test_trace_hour_matches_headline_hour` (21 Fälle × 3 Standards), Invariante im `_day_pillar`-Helper. |
| F2 | R1-a #3 | `solar_time.py:103` | Meeus-Kurzform 25.8 (`−0.00478°·sin Ω`) ist bereits der führende Nutationsterm; zusätzlich zu Δψ addiert → Nutation doppelt. | minor (innerhalb 0,1-min-Schranke, aber Formelfehler; Docstring „< 0,05 min" war falsch) | bestätigt: max \|Δ\| vs `swe.time_equ` 1950–2030 0,0581 → 0,0375 min nach Entfernen | **Fix:** Term entfernt, Docstring 0,038 min, Pin-Test auf dem 2029-Worst-Case, Fern-Epochen-Tests (Jahre 1–3000 ≤ 0,08 min). Snapshots regeneriert, Label `1.0.0-rc6-20261016`. |
| F3 | R1-a #2, R1-b F9 | `bazi.py:126` | Ohne Ruleset (oder ohne `time_standard_for_day_rollover == "TLST"`) fiel TLST+zi auf `apply_day_boundary` zurück: ziviler +1-h-Regel auf dem *solaren* Datum — Mischregel, Rollover doppelt gezählt (UTC lon 30 23:30 → 06-17 statt 06-16). | minor (mit dem ausgelieferten Ruleset nicht erreichbar; stille Degradation widerspricht der Fail-closed-Policy) | bestätigt per Monkeypatch `_load_ruleset_or_none → None` | **Fix:** zi-Entscheidung für TLST immer über `tlst_hours ≥ zi_start` (Ruleset parametrisiert nur `zi_start_hour`). Test `test_tlst_zi_rule_does_not_depend_on_ruleset_presence`. |
| F4 | R1-a #8, R1-b F5 | `time_context.py:150` | `round(tlst_hours, 6)` hebt Wanduhren in den letzten ~2 ms des Tages auf 24.0 → `[0, 24)`-Vertrag verletzt, `/calculate/tst` formatierte „24:00". | minor (p ≈ 2e-11 bei Sekundeneingabe; trivial mit Mikrosekunden) | bestätigt: `2024-06-16T00:00:43.539846Z`, lon 0 → 24.0 | **Fix:** Clamp auf 23.999999 (Datum/Rollover bleiben konsistent). Test `test_tlst_hours_never_reaches_24_after_rounding`. |
| F5 | R1-a #4 | `scripts/minimize_snapshot_diff.py:49` | `git diff --name-only` ignoriert gestagte Dateien; Baseline ist aber `HEAD:` → gestagte Regeneration wird still nicht minimiert. | minor | Code-Lesung | **Fix:** `git diff --name-only HEAD --`. |
| F6 | R1-a #5 | `scripts/minimize_snapshot_diff.py:63` | Bei additiver Schemaänderung (neuer Key) wurde der ganze Teilbaum verbatim übernommen → alle Float-Geschwister „material", Report kollabiert auf `/x`. | minor | bestätigt: S-2-Report zeigte `/derivation_trace/time_resolution` statt der Felder | **Fix:** Merge über gemeinsame Keys/Listenpräfix, neue Keys verbatim, Report nennt `(added)/(removed)`. Nach dem Fix zeigt die S-4-Regeneration exakt `eot_minutes`, `tlst_hours`, `equation_of_time`, `true_solar_time`, Label. Unit-Tests ergänzt. |
| F7 | R1-a #6 | `types.py:92` | `BaziResult.chart_day_dt` statt des ganzen `EffectiveTimeContext`; Trace rechnet den Kontext erneut. | minor (Design) | — | **Kein Fix:** `types.py` ist Level 1, `time_context` Level 2 — der Kontext darf dort nicht importiert werden. F1 wird stattdessen über `pillars.hour` (die Engine-Entscheidung selbst) gelöst; die zweite Kontext-Berechnung im Trace ist deterministisch und ~µs. |
| F8 | R1-a #7 | `routers/fusion.py:307` | Additive Pflichtfelder `eot_source` auf vier Antworten; `/calculate/wuxing.true_solar_time` ändert Semantik um den Zonen-Offset. | info | — | **Kein Fix:** `eot_source` ist Owner-Entscheidung E6 (additiv, kein Pfad/Strukturbruch); die wuxing-Semantik ist der DEV-2026-008-Fix (T4, #57). Beides steht in CHANGELOG-relevanten Conventional-Commits. Hinweis für Downstream: strikte Parser müssen das neue Feld kennen. |
| F9 | R1-b F2 | `bafe/time_model.py:139` | `/validate` (Degraded-Pfad, Spencer) und `/calculate/tst` (Meeus) kippen den Stundenzweig an Binkanten (2024-11-29 00:48:32 UTC lon 0: 1.0039 h vs 0.9933 h). | minor (dokumentiert „degraded", `eot_provenance = spencer_1971`) | bestätigt | **Kein Fix in S-4** — bewusste Designgrenze von `/validate`; Owner-Entscheidung, ob `/validate` auf den Kontext migriert (würde FQ-ATT-Attestierung für `/validate` berühren). Offen als Folgeaufgabe. |
| F10 | R1-b F3 | `chronometry.py:218` | `/chronometry/resolve` und `/personalize` kennen kein `ambiguousTime`; fold=1 wird still auf fold=0 aufgelöst (Berlin 2024-10-27 02:30 „later": andere Oberflächen 01:30Z, Chronometrie 00:30Z, ohne Warnung). | minor (vor dem Sprint vorhanden; Request-Modell-Erweiterung = API-Änderung) | bestätigt | **Kein Fix in S-4** — Owner-Entscheidung: `ambiguousTime`/`nonexistentTime` additiv ins Chronometrie-Request-Modell aufnehmen (OpenAPI/Codegen). Empfehlung: ja, als eigener kleiner PR. |
| F11 | R1-b F4 | `chronometry.py:227` | Frame meldet `julian_day_number` des *zivilen* Datums neben einem TST, der auf dem Vortag liegt; kein Rollover-Feld (auch nicht in `TimeResolutionTrace`). | minor | bestätigt (Madrid 00:30 CET) | **Kein Fix in S-4** — `julian_day_number` ist als „JDN of the resolved civil date" dokumentiert. Empfehlung: additives Feld `tlst_date_rollover` auf Trace und Frame (Owner-Entscheidung, OpenAPI). |
| F12 | R1-b F6 | `time_context.py:120/132` | `OverflowError` → HTTP 500 für Jahre 1/9999 mit großen Längen-/EoT-Offsets (Geschwister: `time_utils._roundtrip_ok`). | minor | bestätigt | **Kein Fix in S-4** — vorbestehend; Folgeaufgabe: `OverflowError` im Error-Handler auf 422 abbilden. |
| F13 | R1-b F7 | `docs/fusion/04_solar_time.md` | Doku behauptete `date_rollover ∈ {−1, 0, +1}`; −2 tritt in UTC+13/+14-Zonen mit weit westlicher Länge auf (Pacific/Apia). Engine korrekt. | minor (Doku) | bestätigt | **Fix:** Doku korrigiert; Apia als dritte Site in der Boundary-Matrix (`test_bazi_tlst_day_pillar.py`). |
| F14 | R1-b F8 | Tests | Veraltete Docstrings („still the day-of-year approximation", „engine currently reports 16:17"). | trivial | — | **Fix.** |

Testlücken (R1-b, Punkt 7) und ihre Abdeckung in S-4: Trace-Stunde == Headline (F1-Tests); fold=1 auf der TLST-Tagessäule (`test_fold_changes_the_zi_day_pillar_when_tlst_straddles_23h`, America/Nome, Folds liegen beiderseits 23:00 TLST); Rollover −2 (Apia-Site); zi + Rollover +1; Meeus-Fern-Epochen; Ruleset-frei. Nicht adressiert (Owner-Entscheidung, s. o.): `/validate`-vs-`/tst`-Schranke, Korpus-Fälle vor 1950.

Durch R1-b **ausgeschlossen** (getestet, nicht reproduziert): Vorzeichen/Wrap der Meeus-Formel; `jd_ut_from_datetime` vs `swe.julday` (µs, nicht-UTC-aware, Jahre 1/1500/3000); 4 000 zufällige Zone×Länge×Jahr-Samples gegen `swe.lmt_to_lat` (0 Verstöße); exotische Zonen (Etc/GMT+12 lon −179.9, Auckland +179.9, Kiritimati, Kathmandu, Kolkata, St_Johns, Urumqi) für Tages- und Stundensäule; historische krumme Offsets (Amsterdam 1930, Berlin 1850, Kolkata 1900, Apia 1930); fold=1/shift_forward auf `/calculate/bazi`, `/calculate/tst`, `/chart`; LMT- und TLST-Datum verschieden (E5-A-Verhalten, Traces je selbstkonsistent); Zi-Regel exakt bei 23:00/00:00; keine verbliebenen Produktionsaufrufe von `true_solar_time`/`equation_of_time(day_of_year)` außer `/validate`.

## 2b. R2 — Codex (externes Review, 2026-10-16, Range `03c471c..af62e90`)

Ergebnis: **kein Blocker.** Zwei bestätigte Minor-Findings, beide an Sub-Millisekunden-Kanten der 6-/4-Dezimal-Darstellung; eine Beobachtung außerhalb des Review-Bereichs.

| ID | Datei | Befund | Schwere | Verifikation | Entscheidung |
|---|---|---|---|---|---|
| TLST-1 | `time_context.py:135–146`, `bazi.py:125–127, 251–255` | `2024-06-16T23:00:56.243413Z`, lon 0, TLST/zi: TLST ist 22:59:59.9995 (Meeus) bzw. 22:59:59.953 (swe); `round(…, 6)` macht daraus 23.000000 → Stundenzweig Zi statt Hai und zi-Tagesvorsprung. | minor | bestätigt (ctx = 23.0 reproduziert) | **Fix (S-5):** `tlst_hours` wird aus dem ganzzahligen Mikrosekundenzähler auf 6 Dezimalen *abgeschnitten*, nie gerundet — jede Entscheidung (Zweig, zi, Rollover) bleibt auf der richtigen Seite ihrer Kante; der S-4-Clamp wird damit überflüssig. HTTP-Test am Fall. |
| TLST-2 | `routers/fusion.py:249, 344` | `2024-06-16T00:00:43.800000Z`, lon 0: Kontext 23.999999, aber `/calculate/tst` und `/calculate/wuxing` serialisieren `round(…, 4)` = 24.0 (`/chart` und Trace: 23.999999). | minor | bestätigt | **Fix (S-5):** 4-Dezimal-Anzeigewert auf 23.9999 begrenzt (`_tlst_hours_4dp`); Test für beide Endpunkte. |
| — (außerhalb) | `time_utils.py:141–159` | Pacific/Apia `2011-12-30T12:00` (übersprungener Kalendertag), `nonexistentTime=shift_forward` → 422: der Resolver sucht nur 180 min vorwärts, die nächste gültige Ortszeit liegt 720 min später. | info | von Codex bestätigt; Code im Review-Bereich unverändert | **Owner-Entscheidung** (Folgeaufgabe, nicht TLST-spezifisch): Suchfenster auf 24 h erweitern oder 422 mit erklärender Meldung beibehalten. |

Von Codex ausgeschlossen: Kiritimati-Rollover −2 (korrekt), Berlin-Folds (Instants erhalten), Frühjahrslücke `shift_forward`, Meeus 1800–3000 monatlich max 0,0445 min, keine weiteren Aufrufer der Tagesformel außer `/validate`.

## 3. Grid-Lauf (Plan §6.4)

`SE_EPHE_PATH=/tmp/ephe python scripts/tlst_grid_check.py` (neu, Review-Evidenz; 16 Zonen × 12 Daten 1950–2030 × 96 Viertelstunden, beide Folds bei Mehrdeutigkeit):

| Samples | max \|Δ TLST\| | Stundenabweichung > 0,1 min | Datumsabweichung | Zweigabweichung | an Binkante ausgeschlossen |
|---|---|---|---|---|---|
| 18 442 | 0,02 min | 0 | 0 | 0 | 20 |

Vor dem Sprint (Plan vom 2026-10-15, gleiches Raster): 85,4 % falscher Stundenzweig, 21,4 % falsches TLST-Datum, max. 12 h.

## 4. Gesamtsuite nach S-5 (R1- und R2-Fixes)

| Backend | Ergebnis |
|---|---|
| SWIEPH (`SE_EPHE_PATH=/tmp/ephe`) | 4174 passed, 102 skipped (Vollsuite, echte Ephemeriden) |
| MOSEPH (Fallback) | 3629 passed, 597 skipped, 1 bekannter umgebungsabhängiger Fehler (`test_security_findings::test_ephemeris_unavailable_503_does_not_leak_resolved_path`) |

Gates: ruff, mypy, `check_complexity.py --check`, `export_openapi.py --check`, `assert_toolchain_versions.py`, `gen_tlst_reference_corpus.py --check` — sauber.

## 5. Offene Owner-Entscheidungen

1. F9: `/validate` auf den gemeinsamen Zeitkontext migrieren (Meeus statt Spencer) — berührt die Attestierungsregeln für `/validate`.
2. ~~F10: `ambiguousTime`/`nonexistentTime` additiv ins `/chronometry/resolve`-Request-Modell~~ — **freigegeben und umgesetzt** (2026-10-16, Label `1.0.0-rc7-20261016`): `BirthContext.ambiguousTime`/`nonexistentTime`, durchgereicht an `resolve_chronometry(…, ambiguous_time, nonexistent_time)`; Tests `tests/test_chronometry_dst_policy_and_rollover.py`.
3. ~~F11: additives Feld `tlst_date_rollover` auf `TimeResolutionTrace` und `ChronometryFrame`~~ — **freigegeben und umgesetzt** (2026-10-16): `tlst_date_rollover` auf Trace `time_resolution` (int), `ChronometryFrame`/`/chronometry/resolve`/`/personalize` (int, `null` bei unbekannter Geburtszeit); `julian_day_number` bleibt vertragsgemäß das zivile Datum.
4. ~~F12: `OverflowError` → 422~~ — **freigegeben und umgesetzt** (2026-10-17): `time_utils._roundtrip_ok` und `time_context` fangen `OverflowError` an der Quelle und werfen `LocalTimeError`/`InputError` (422, ohne PII-Echo); Tests `tests/test_time_range_and_skipped_day.py`.
5. ~~Suchfenster für `shift_forward` (180 min)~~ — **freigegeben und umgesetzt** (2026-10-17): `time_utils.SHIFT_FORWARD_MAX_MINUTES = 48 h`; Samoa 2011-12-30 12:00 → 2011-12-31 00:00+14:00 (+720 min); normale DST-Lücken unverändert.
