# 12 — Westen → Wu Xing: Zuordnung über das Zeichen-Element (sign-element-consensus-v1)

**Stand:** 2026-11-06 · **Module:** `bazi_engine/wuxing/constants.py` (`SIGN_ELEMENT`, `WEST_ELEMENT_TO_WUXING`, `WESTERN_MAPPING_ID`), `bazi_engine/wuxing/analysis.py` · **Mapping-Version:** `fufire-wuxing-map-v2`

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

Jeder Körper trägt über das klassische Element seines **Zeichens** (Triplizitäten: Widder/Löwe/Schütze Feuer, Stier/Jungfrau/Steinbock Erde, Zwillinge/Waage/Wassermann Luft, Krebs/Skorpion/Fische Wasser) und wird mit dieser Matrix auf die fünf Phasen verteilt. Rückläufige Körper zählen weiter 1,3-fach.

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

## Kalibrierung

Die Zelle `(dense, medium)` der Baseline-Tabelle — die Zelle aller vollständigen Horoskope — stammt jetzt aus vertauschten echten Zufallsgeburten (`scripts/calibrate_baselines.py --null births`), siehe [11](11_ground_truth_integrity.md). Ergebnis an 300 Berliner Geburten: `sigma_above` Mittel 0,00, Standardabweichung 0,92.

## Grenzen

- Die Rechnung ist reproduzierbar, die Kodierung bleibt Deutung.
- `services/soulprint.py` nutzt weiterhin eine eigene Sektor-Zuordnung (`wuxing_sector_mapping`); nicht angeglichen.
- `ASTROLOGEN_LEITFADEN.md` nennt noch rohe H-Schwellen; nicht angeglichen.
