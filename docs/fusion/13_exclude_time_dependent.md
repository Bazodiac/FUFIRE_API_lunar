# 13 — Zeitabhängige Beiträge ausschließen (`exclude_time_dependent`)

**Stand:** 2026-11-18 · **Build:** `1.0.0-rc12-20261118` · **Module:** `bazi_engine/fusion.py`
(`compute_fusion_analysis`, `split_time_dependent_pillars`), `bazi_engine/wuxing/analysis.py`
(`include_ascendant`), `bazi_engine/routers/fusion.py` · **Tests:**
`tests/test_fusion_exclude_time_dependent.py`

## Schalter

`POST /calculate/fusion` und `POST /calculate/fusion/vector-map` (Legacy und `/v1`) haben
das Feld `exclude_time_dependent: bool | null` (Standard `null`).

| `exclude_time_dependent` | `birth_time_known` | Ausschluss |
|---|---|---|
| `null` / weggelassen | `true` | nein (Verhalten wie bisher) |
| `null` / weggelassen | `false` (oder `date` ohne Uhrzeit) | **ja** |
| `true` | beliebig | ja |
| `false` | beliebig | nein |

Ein expliziter Wert gewinnt immer. Ein Client, der mit unbekannter Zeit trotzdem den
vollen Vektor will, sendet `false`.

## Was ausgeschlossen wird

- **Westen:** der Aszendent (Tier 1, Gewicht 1,0). Der MC trägt unter
  `sign-element-consensus-v1` / `body-tier-q0.3-v1` nie bei; es gibt nichts auszuschließen.
- **BaZi:** die ganze Stundensäule — Stamm und alle Hidden Stems des Zweigs. Das gilt auch,
  wenn der Client `bazi_pillars` mitschickt.

Alles Abgeleitete wird aus den reduzierten Vektoren berechnet: `wu_xing_vectors`,
`elemental_comparison`, `harmony_index`, `cosmic_state`, Interpretation und
`calibration` (`calibrate_harmony` bekommt die reduzierten Säulen; `n_bazi_contributions`
zählt nur die verbleibenden Beiträge).

## Antwort

- `contribution_ledger.western` / `.bazi` enthalten keine Aszendent- und keine
  Stunden-Einträge mehr.
- `contribution_ledger.excluded` listet sie: zuerst der Aszendent, dann die
  Stunden-Einträge, jeweils mit `system` (`western`/`bazi`) und `reason: "time_dependent"`.
  Ohne Ausschluss fehlt das Feld.
- `contribution_ledger.chart_type_quality` und `quality_flags.chart_type_quality`:
  neuer Wert `"time_excluded"` (OpenAPI-Enum `exact | assumed_day | time_excluded`).
- `provenance.parameter_set.time_dependent_excluded: true` (fehlt ohne Ausschluss).
- Vector-Map: `metadata.time_dependent_excluded: true` (fehlt ohne Ausschluss);
  `precision` und `warnings` nur bei `birth_time_known: false`.

Ohne Ausschluss und mit bekannter Zeit ist die Antwort byte-gleich zum vorigen Build
(bis auf Zeitstempel und das Build-Label).

## Tag/Nacht

`is_night_chart` wird weiter mit dem echten Aszendenten ausgewertet — nur um im
`strict`-Modus einen fehlenden Aszendenten zu melden. Kein Beitrag hängt vom Ergebnis ab:
unter `sign-element-consensus-v1` zählt nur das Zeichen-Element jedes Körpers, ohne
Sekten-Regel. `test_day_night_changes_no_contribution` prüft das mit einer Tag- und einer
Nacht-Konstellation.

## Kalibrierung mit weniger BaZi-Beiträgen

Ohne Stundensäule hat die BaZi-Seite 6–12 statt 8–16 Beiträge (je Säule 1 Stamm + 1–3
Hidden Stems). `n_bazi ≤ 8` fällt in den Bucket `sparse`, darunter `n_bazi < 8` setzt
`calibration.quality = "sparse"`. Alle neun Zellen von `_BASELINE_TABLE` existieren; es
wird nichts umgangen oder umgebogen. Einschränkung: die Baseline-Zellen wurden auf
vollständigen Charts (mit Stunde und Aszendent) bestimmt. `sigma_above` eines reduzierten
Charts misst also gegen Charts mit gleich vielen Beiträgen, nicht gegen eine eigene
Baseline für reduzierte Charts. Ob es eine eigene Baseline braucht, ist offen.

## Konsistenz `/fusion` ↔ `/bazi`

`/fusion` rechnet die Säulen mit demselben Standard-Default wie `/bazi` (TLST).
`test_fusion_and_bazi_agree_without_standard` prüft das an 00:30 Uhr München, wo CIVIL
und TLST verschiedene Tagessäulen ergeben.
