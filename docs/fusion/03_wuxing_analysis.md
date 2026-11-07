# 03 — Vektorextraktion: Planeten und Vier Pfeiler → ℝ⁵

> **Veraltet für die Fusion (Stand 2026-11-07):** Gewichte, Rückläufigkeit 1,3 und die Merkur-Tag/Nacht-Regel unten beschreiben die alte Namenszuordnung. Aktuell: [12_west_element_mapping.md](12_west_element_mapping.md).

**Modul:** `bazi_engine/wuxing/analysis.py`  
**Level:** 4 (Domain-Logik, importiert nur wuxing-interne Module)

---

## Übersicht: Zwei Extraktionspfade

Das Modul enthält zwei komplementäre Funktionen, die aus verschiedenen
astrologischen Eingangsdaten denselben Ausgabetyp (`WuXingVector`) erzeugen:

```
Weg A: Planetenpositionen → calculate_wuxing_vector_from_planets() → WuXingVector
Weg B: Vier Pfeiler        → calculate_wuxing_from_bazi()           → WuXingVector
```

Erst durch diese Parallelität wird der Vergleich möglich.

---

## Weg A: Planetenextraktion

### Funktion: `calculate_wuxing_vector_from_planets()`

```python
def calculate_wuxing_vector_from_planets(
    bodies: Dict[str, Dict[str, Any]],
    use_retrograde_weight: bool = True,
) -> WuXingVector
```

**Eingabe:** Dict der Planetenpositionen aus `compute_western_chart()`:
```json
{
    "Sun":    {"longitude": 321.5, "is_retrograde": false},
    "Mars":   {"longitude": 150.0, "is_retrograde": true},
    "Saturn": {"longitude": 340.0, "is_retrograde": false}
}
```

**Algorithmus:**

```
1. Bestimme Tag/Nacht-Status aus Sonnenlänge + Aszendent (→ is_night_chart)
2. Für jeden Planeten ohne "error"-Key:
   a. Bestimme Element via planet_to_wuxing(planet, night)
   b. Bestimme Gewicht: 1.3 wenn retrograd UND use_retrograde_weight=True, sonst 1.0
   c. Addiere Gewicht zur entsprechenden Element-Achse
3. Gib WuXingVector der Rohwerte zurück (nicht normalisiert)
```

**Retrograd-Gewichtung (+30%):**

Rückläufige Planeten gelten in der westlichen Tradition als "verinnerlicht" —
ihre Energie wirkt nach innen, nicht nach außen. Im Wu-Xing-Kontext:
ein retrograder Mars ist nicht schwächer, sondern intensiver in seiner
inneren Feuerwirkung. Die 30%-Erhöhung ist eine heuristisch begründete
Näherung, keine kanonische Formel.

**Tag/Nacht-Unterscheidung (`is_night_chart`):**

```python
def is_night_chart(sun_longitude: float, ascendant: Optional[float] = None) -> bool
```

Wenn der Aszendent bekannt ist:
```
DSC = (ASC + 180°) % 360°

Nacht = Sonne befindet sich zwischen DSC und ASC (Häuser 1–6, unter dem Horizont)

Geometrisch: Sonne liegt im "unteren" Halbkreis des Horoskops
```

Ohne Aszendent → Default: Tagkarte.

Relevanz: Nur für Merkur (Erde-Tag / Metall-Nacht). Für alle anderen
Planeten ist der Tag/Nacht-Status ohne Effekt.

---

## Weg B: BaZi-Extraktion

### Funktion: `calculate_wuxing_from_bazi()`

```python
def calculate_wuxing_from_bazi(
    pillars: Dict[str, Dict[str, str]]
) -> WuXingVector
```

**Eingabe:** Die vier Pfeiler als Dict:
```json
{
    "year":  {"stem": "Jia",  "branch": "Chen"},
    "month": {"stem": "Bing", "branch": "Yin"},
    "day":   {"stem": "Jia",  "branch": "Chen"},
    "hour":  {"stem": "Xin",  "branch": "Wei"}
}
```

**Algorithmus:**

```
Für jeden Pfeiler:
  1. Himmelssstamm (stem) → direkte Elementzuordnung, Gewicht 1.0
  2. Erdzweig (branch)    → verborgene Stämme (藏干) mit Qi-Gewichten
```

### Die verborgenen Stämme (藏干 — Cáng gān)

Das ist das hermeneutisch reichste Konzept der gesamten Berechnung.
Jeder Erdzweig enthält **mehrere Elemente** mit abgestuften Gewichten,
die aus der klassischen Qi-Lehre stammen:

```
Main Qi  (主气, Zhǔ qì)   → Gewicht 1.0  — dominantes Element
Middle Qi (中气, Zhōng qì) → Gewicht 0.5  — sekundäres Element
Residual Qi (余气, Yú qì)  → Gewicht 0.3  — Restenergie des Vorgängers
```

**Vollständige Tabelle der verborgenen Stämme:**

| Zweig | Tier | Main Qi (1.0) | Middle Qi (0.5) | Residual Qi (0.3) |
|---|---|---|---|---|
| Zi 子 | Ratte | Wasser | — | — |
| Chou 丑 | Ochse | Erde | Wasser | Metall |
| Yin 寅 | Tiger | Holz | Feuer | Erde |
| Mao 卯 | Hase | Holz | — | — |
| Chen 辰 | Drache | Erde | Holz | Wasser |
| Si 巳 | Schlange | Feuer | Metall | Erde |
| Wu 午 | Pferd | Feuer | Erde | — |
| Wei 未 | Ziege | Erde | Feuer | Holz |
| Shen 申 | Affe | Metall | Wasser | Erde |
| You 酉 | Hahn | Metall | — | — |
| Xu 戌 | Hund | Erde | Metall | Feuer |
| Hai 亥 | Schwein | Wasser | Holz | — |

**Was diese Gewichtung bedeutet:**

Zi (Ratte) und Mao (Hase) sind "reine" Zweige — sie enthalten nur ein Element.
Chen (Drache) und Xu (Hund) sind "gemischte" Zweige — sie enthalten die
Energie dreier Elemente und gelten in der BaZi-Tradition als besonders
komplex und mächtig.

Die Qi-Gewichte (1.0 / 0.5 / 0.3) sind **nicht empirisch kalibriert** —
sie folgen der klassischen Qi-Theorie, die dem Haupt-Qi dreimal soviel
Gewicht gibt wie dem Residual-Qi. Diese Verhältnisse sind in der
Forschungsliteratur konventionell, nicht universell festgelegt.

### Berechnung für ein Beispiel-BaZi

**Geburt: Jia-Chen / Bing-Yin / Jia-Chen / Xin-Wei**

```
Jahr-Stamm  Jia  → Holz  × 1.0 = +1.0 Holz
Jahr-Zweig  Chen → Erde  × 1.0 = +1.0 Erde
                   Holz  × 0.5 = +0.5 Holz
                   Wasser× 0.3 = +0.3 Wasser

Monat-Stamm Bing → Feuer × 1.0 = +1.0 Feuer
Monat-Zweig Yin  → Holz  × 1.0 = +1.0 Holz
                   Feuer × 0.5 = +0.5 Feuer
                   Erde  × 0.3 = +0.3 Erde

Tag-Stamm   Jia  → Holz  × 1.0 = +1.0 Holz
Tag-Zweig   Chen → (wie Jahr-Zweig)
                   +1.0 Erde, +0.5 Holz, +0.3 Wasser

Stunde-Stamm Xin → Metall× 1.0 = +1.0 Metall
Stunde-Zweig Wei → Erde  × 1.0 = +1.0 Erde
                   Feuer × 0.5 = +0.5 Feuer
                   Holz  × 0.3 = +0.3 Holz

Summen:
  Holz:   1.0 + 0.5 + 1.0 + 0.5 + 1.0 + 0.3 = 4.3
  Feuer:  1.0 + 0.5 + 0.5                    = 2.0
  Erde:   1.0 + 0.3 + 1.0 + 1.0              = 3.3
  Metall: 1.0                                 = 1.0
  Wasser: 0.3 + 0.3                           = 0.6

v_bazi = (4.3, 2.0, 3.3, 1.0, 0.6)
‖v_bazi‖ = √(18.49 + 4.0 + 10.89 + 1.0 + 0.36) = √34.74 ≈ 5.89
v̂_bazi ≈ (0.730, 0.340, 0.560, 0.170, 0.102)
```

---

## Harmony-Hilfsfunktionen

### `interpret_harmony(h: float) → str`

Schwellenwertbasierte Textlabels für den Harmony Index:

| Bereich | Label |
|---|---|
| h ≥ 0.8 | Starke Resonanz |
| h ≥ 0.6 | Gute Harmonie |
| h ≥ 0.4 | Moderate Balance |
| h ≥ 0.2 | Gespannte Harmonie |
| h < 0.2 | Divergenz |

Diese Schwellen sind heuristisch gewählt. Sie entsprechen grob der
Cosinus-Ähnlichkeit:
- 0.8+ entspricht einem Winkel ≤ 37° → sehr ähnliche Richtungen
- 0.6–0.8: 37°–53° → vergleichbare Profilstruktur
- 0.4–0.6: 53°–66° → merklicher Richtungsunterschied
- 0.2–0.4: 66°–78° → starke Divergenz
- <0.2: >78° → fast orthogonale Energiefelder

---

## Deutungsraum: Was diese Extraktion bedeutet

### Die Asymmetrie zwischen West und BaZi

**Westliche Extraktion:** Alle Planeten gleichwertig (1.0), Retrograd = 1.3.
Kein Haus, kein Aspekt, keine Dignität.

**BaZi-Extraktion:** Verborgene Stämme mit dreistufigen Qi-Gewichten.
Die Tiefenstruktur der Zweige wird erfasst — ein Zi-Zweig ist elementar
simpler als ein Xu-Zweig.

Diese Asymmetrie ist strukturell bedeutsam: Die BaZi-Extraktion bildet
**verborgene Komplexität** ab (was der Zweig innen trägt), die westliche
Extraktion bildet **sichtbare Planetendichte** ab.

Wenn man diese Asymmetrie als Aussage liest:
> Die BaZi-Karte zeigt die innere Struktur, das Erbgut des Moments.  
> Die westliche Karte zeigt das aktuelle Erscheinungsbild des Himmels.

Das ist der Beginn einer eigenständigen Deutungslogik.

### Anschlussfähigkeit zu den Traditionen

**BaZi-Tradition:**
Die Verwendung der 藏干 (verborgenen Stämme) ist vollständig kanonisch.
In der klassischen Vier-Pfeiler-Analyse sind die verborgenen Stämme
nicht optional — sie sind die Grundlage für die Stärkeberechnung des
Tag-Stamms (日主) und die Analyse von Günstigkeitsgott (用神) und
Schädlichkeitsgott (忌神).

**Westliche Astrologie:**
Die Gleichgewichtung aller Planeten in der westlichen Extraktion ist
simplifizierend — traditionell hat die Sonne mehr Gewicht als Pluto.
Eine verfeinerte Gewichtung könnte eingeführt werden, ist aber
ein Trade-off zwischen Komplexität und Interpretierbarkeit.
