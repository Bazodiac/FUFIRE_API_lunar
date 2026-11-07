# 12 — Westen → Wu Xing: Zuordnung über das Zeichen-Element (sign-element-consensus-v1)

**Stand:** 2026-11-07 · **Module:** `bazi_engine/wuxing/constants.py` (`SIGN_ELEMENT`, `WEST_ELEMENT_TO_WUXING`, `WESTERN_MAPPING_ID`, `WESTERN_BODY_TIER`, `WESTERN_TIER_WEIGHT`, `WESTERN_WEIGHTING_ID`), `bazi_engine/wuxing/analysis.py` · **Mapping-Version:** `fufire-wuxing-map-v3`

Dieses Dokument ersetzt für den Fusion-Layer die Planet-Element-Tabelle aus [01](01_wuxing_constants.md). `PLANET_TO_WUXING` bleibt bestehen und wird weiter von Impact/Transit genutzt.

## Warum

Die alte Fusion ordnete jedem Körper fest ein Element nach seinem **Namen** zu (Sonne = Feuer, Jupiter = Holz …). Weil jedes Horoskop dieselben Körper enthält, war der westliche Vektor fast konstant:

| Messung (300 Zufallsgeburten Berlin 1950–2008, Seed 23, über `/v1/calculate/fusion`) | alt | neu |
|---|---|---|
| führendes West-Element Holz / Feuer / Erde / Metall / Wasser | 294 / 0 / 0 / 0 / 6 | 43 / 74 / 34 / 84 / 65 |
| Streuung je Phase (sd des normierten Vektors) | 0,02–0,07 | 0,09–0,17 |
| `sigma_above` Mittel / sd / min / max | 0,07 / 0,78 / −2,18 / 1,57 | 0,00 / 0,92 / −3,47 / 1,52 |

Die Fusion verglich BaZi damit faktisch mit einem festen Profil.

## Wie

Jeder Körper trägt über das klassische Element seines **Zeichens** (Triplizitäten: Widder/Löwe/Schütze Feuer, Stier/Jungfrau/Steinbock Erde, Zwillinge/Waage/Wassermann Luft, Krebs/Skorpion/Fische Wasser) und wird mit dieser Matrix auf die fünf Phasen verteilt. Jeder Körper zählt mit dem Gewicht seiner Stufe (siehe unten).

| West | Holz | Feuer | Erde | Metall | Wasser |
|---|---|---|---|---|---|
| Feuer | 0,452 | 0,548 | – | – | – |
| Erde | – | – | 0,095 | 0,699 | 0,206 |
| Luft | 0,348 | 0,252 | 0,400 | – | – |
| Wasser | – | – | 0,306 | 0,101 | 0,593 |

Zeilen summieren auf 1; jede Phase erhält über alle vier Elemente 0,8.

## Herleitung

1. **Gemeinsamer Merkmalsraum.** Vier unabhängige Forschungsläufe kodierten die vier westlichen Elemente und die fünf Phasen auf Dimensionen, die beide Traditionen beschreiben: warm–kalt und feucht–trocken (Aristoteles, *De gen. et corr.* II.2–3; im Suwen 5 die Klimata Wind, Hitze, Feuchte, Trockenheit, Kälte), Bewegung auf–ab (Aristoteles, *De caelo* IV.4; Shangshu *Hongfan*: 炎上 / 潤下), Ausdehnen–Sammeln und Aktivität (Jahreslehre 生長收藏; WHO-Terminologie zur TCM 2022).
2. **Ähnlichkeit** je Lauf aus den offengelegten Kodierungen (Kosinus bzw. normierte Profildistanz), positive Werte über einer Schwelle, Zeilen normiert. Ohne Jahreszeit: Die Jahreszeit der Säftelehre (Luft = Frühling …) ist eine Eigenschaft des Elements, nicht der Lage eines Zeichens; alle Läufe zeigen, dass der Kern ohne sie gleich bleibt.
3. **Konsens:** Mittel der vier Läufe (ein Lauf aus seinen eigenen Kodierungen nachgerechnet, weil seine berichtete Matrix nicht aus ihnen folgte).
4. **Ausgleich** (Sinkhorn, Zeilen 1, Spalten 0,8): Die Wu-Xing-Erde hat im Westen keinen eigenen Pol. Ohne Ausgleich könnte sie im Westen nie führen, und jedes Reading mit BaZi-Erde-Dominanz (≈ 31 %) zeigte automatisch Spannung bei Erde.

**Überliefert** sind die Qualitäten, Bewegungen, Klimata und Jahreszeiten. **Setzung** sind der Merkmalsraum, die Stufen der Kodierung, die Mittelung und der Ausgleich.

## Robuste Befunde (alle Läufe)

- Westliches Feuer → Feuer mit Holz-Anteil (Spannweite zwischen Läufen ±0,03).
- Westliche Erde → **Metall** dominant: kalt-trocken, Herbst; die chinesische Erde ist dagegen Feuchte.
- Westliches Wasser → Wasser, dazu Erde.
- Luft verteilt sich auf Holz, Feuer, Erde (größte Streuung zwischen den Läufen).
- Die Konvention „Luft → Metall“ hat keine Quelle und erhält die Beziehungsstruktur am schlechtesten (3 von 6).

## Gewichte der Körper (body-tier-q0.3-v1, seit 2026-11-07)

| Stufe | Körper | Gewicht |
|---|---|---|
| 1 | Sonne, Mond, Aszendent (nur bei bekannter Geburtszeit) | 1 |
| 2 | Merkur, Venus, Mars | 0,3 |
| 3 | Jupiter, Saturn | 0,09 |
| 4 | Uranus, Neptun, Pluto, Chiron, Lilith, Mondknoten | 0,027 |

- Der Mondknoten zählt einmal (`NorthNode`, mittlerer Knoten); `TrueNorthNode` wird nicht addiert (`WESTERN_EXCLUDED_BODIES`).
- Rückläufigkeit zählt nicht extra (vorher 1,3: ohne Quelle, im Prüfstand ohne messbare Wirkung). Die Option `use_retrograde_weight` existiert weiter, steht aber auf `False`.
- Der Ledger nennt je Körper `weight_tier` und `weight`; `provenance.parameter_set` (Version 1.2.0) nennt Tabelle und IDs.

**Warum:** Vorher zählte jeder Körper gleich, der Mondknoten doppelt. Langsame Körper stellten so mehr als die Hälfte des Gewichts, und der Geburtsjahrgang erklärte 50–52 % der Streuung des westlichen Vektors.

**Rangfolge (Überlieferung):** Ptolemaios, Tetrabiblos III.10 (Sonne, Mond, Aszendent, Glückslos als Orte größter Autorität) und III.11 (Temperament aus Osthorizont, dessen Herrschern und dem Mond); Lilly, *Christian Astrology* (1647), Buch III, Kap. CVI, S. 532–533.

**Faktor 0,3 (Messung, Setzung im Band):** Jede Stufe zählt das 0,3-Fache der Stufe darüber. Abnahmekriterien vorab: Jahrgangsanteil möglichst klein, Streuung in der Größenordnung der BaZi-Seite, keine eingebaute Kopplung, Rangfolge erhalten. Mit den Schwellen Jahrgangsanteil ≤ 2 %, Streuung ≥ 0,185, jede Phase führt in ≥ 7 %, |z| ≤ 0,05 ergibt sich an 7100 Zufallsgeburten das Band q = 0,27–0,39 (ohne Aszendent) bzw. 0,15–0,32 (mit); 0,3 liegt in beiden.

| Kennzahl (3 Stichproben, 17 150 Geburten) | vorher | 0,3 ohne Asc | 0,3 mit Asc |
|---|---|---|---|
| Jahrgangsanteil am westlichen Vektor | 50–52 % | 0,7–1,2 % | 0,5–1,0 % |
| Streuung je Phase (BaZi 0,205) | 0,138–0,139 | 0,202–0,203 | 0,188–0,189 |
| seltenste führende Phase | Erde 13 % | Holz 7–8 % | Holz 10–11 % |
| Kopplung mit der Jahressäule (z) | −0,09 bis −0,12 | −0,01 bis −0,02 | −0,01 bis −0,02 |

**Kosten:** Der Westen wird von den Lichtern bestimmt (62 % des Gewichts, mit Aszendent 71 %). Holz führt seltener, weil es in keiner Matrixzeile den größten Anteil hat.

## Kalibrierung

Die Zelle `(dense, medium)` der Baseline-Tabelle — die Zelle aller vollständigen Horoskope — stammt aus vertauschten echten Zufallsgeburten (`scripts/calibrate_baselines.py --null births`), siehe [11](11_ground_truth_integrity.md). Mit den Gewichten seit 2026-11-07: 0,7974 / sd 0,1282 (Seeds 7/42/99: 0,7958 / 0,7974 / 0,7988). Horoskope ohne Aszendenten liegen im Mittel etwa 0,015 tiefer; `sigma_above` ist dort um rund −0,1 verschoben.

## Grenzen

- Die Rechnung ist reproduzierbar, die Kodierung bleibt Deutung. Die Gewichte erfüllen die vorab festgelegten Kriterien; ob sie richtig sind, zeigt das nicht.
- `/chart` (Legacy) und der Forschungs-Datensatzgenerator übergeben keinen Aszendenten; dort fehlt der Aszendenten-Term.
- `services/soulprint.py` verteilt die Phasen seit PR #79 über dieselbe Matrix (transponiert, `wuxing_sector_mapping` = `sign-element-consensus-v1 transposed`).
- `ASTROLOGEN_LEITFADEN.md` (1.1) liest die Lage seit PR #79 aus `calibration.sigma_above`, nicht mehr aus rohen H-Schwellen.
