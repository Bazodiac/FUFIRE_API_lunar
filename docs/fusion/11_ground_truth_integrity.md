# 11 — Ground-Truth-Integrität: Diagnose, Fixes, Architektur

Dieses Dokument beschreibt die **strukturellen Probleme** der ursprünglichen
Fusion-Implementierung, die diagnostizierten Ursachen, und die implementierten
Lösungen. Es ist die technische Grundlage für alle nachfolgenden
Deutungserweiterungen.

---

## Problem 1: H-Kompressionsartefakt (kritisch)

### Diagnose

Der rohe Kohärenz-Index H = cos(θ) liegt empirisch **immer in [0.50, 1.0]**,
weil alle Wu-Xing-Vektorkomponenten ≥ 0 sind (positiver Orthant von ℝ⁵).

```python
# Empirische Messung (10.000 Simulationen, seed=42):
# Zufällige Vektoren im R^5+:
#   Erwarteter Winkel: 37.7°   →   H_erwartet = cos(37.7°) = 0.79
#   Minimaler H-Wert: ~0.26   (extrem selten)
#   Typische Range: [0.60, 0.98]
```

Die Deutungsschwellen der ursprünglichen `interpret_harmony()`-Funktion
(0.2 / 0.4 / 0.6 / 0.8) sind damit faktisch unerreichbar:

| Label | Schwelle | Empirisch erreichbar? |
|---|---|---|
| Divergenz | H < 0.2 | Nein — in der Praxis nie |
| Gespannte Harmonie | H < 0.4 | Sehr selten (<1%) |
| Moderate Balance | H < 0.6 | Selten (~10%) |
| Gute Harmonie | H < 0.8 | Häufig |
| Starke Resonanz | H ≥ 0.8 | ~70% aller Charts |

**Konsequenz:** 70% aller Nutzer bekämen "Starke Resonanz" — was die
Deutung bedeutungslos macht.

### Ursache

Alle Wu-Xing-Gewichte sind ≥ 0. Das ist korrekt (kein Planet hat
"negatives Feuer"). Aber es führt dazu, dass zwei zufällige
elementare Profile immer einen spitzen Winkel (< 90°) haben.

Mit 7 Planeten (westlich) und 4 × ~4 Qi-Beiträgen (BaZi = ~16 Beiträge)
werden alle 5 Achsen immer mittelstark besetzt — was zu einem hohen
Basis-Cosinus führt, unabhängig vom "echten" Signal.

### Lösung: H_calibrated (Kontrastverhältnis)

```python
H_calibrated = max(0.0, (H_raw - H_baseline) / (1.0 - H_baseline))
```

Wobei `H_baseline` der empirische Erwartungswert für die gegebene
Eingabedichte (Anzahl Planeten × Pfeiler) ist.

**Ergebnis nach Kalibrierung:**
```
H_calibrated: mean=0.32  std=0.29  min=0.00  max=0.97
```
Der volle [0, 1]-Bereich ist jetzt nutzbar.

**Nachtrag 2026-11-06:** Das synthetische Nullmodell (gleichverteilte Würfe, Gewicht 1,0, n_west = 11) bildet echte Horoskope nicht ab (real: 14 Körper, Retro-Gewicht, Qi-Gewichte 1,0/0,5/0,3). Die Zelle `(dense, medium)` stammt deshalb aus vertauschten echten Zufallsgeburten (`scripts/calibrate_baselines.py --null births`, 3000 Geburten, Seed 42; Mittel 0,8358, sd 0,1023). Siehe [12](12_west_element_mapping.md).

**Implementation:** `bazi_engine/wuxing/calibration.py`  
**Eingang:** H_raw + n_west + n_bazi_contributions + Rohvektoren  
**Ausgang:** `CalibrationResult` mit h_calibrated, quality, sigma_above

---

## Problem 2: Qualitätsflag fehlt

### Diagnose

Die ursprüngliche Pipeline hatte keine Unterscheidung zwischen:
- **Normales Chart** (7+ Planeten, 4 Pfeiler)
- **Sparse-Chart** (1-2 Planeten, 1 Pfeiler)
- **Degeneriertes Chart** (Nullvektor)

Ein Nullvektor erzeugt H = 0.0 mit der Interpretation "Divergenz" —
das ist inhaltlich falsch (kein Signal ≠ maximale Divergenz).

### Lösung

```python
class QualityFlag(Literal):
    "ok"          # normale Eingabe, Kalibrierung valide
    "sparse"      # zu wenige Daten, H unzuverlässig
    "degenerate"  # Nullvektor, H undefiniert → CalibrationResult zeigt 0.0
```

Degenerate-Charts werden als "kein Signal" interpretiert, nicht als
"maximale Divergenz". Die Ausgabe enthält explizit:
```json
{"h_calibrated": 0.0, "quality": "degenerate", "interpretation_band": "Undefiniert — kein Signal"}
```

---

## Problem 3: Keine externe Periodikreferenz

### Diagnose

Archetypen entstanden aus Individualdaten — das erzeugt beliebige,
nicht-reproduzierbare "Phasen". Es gab keine realweltlich referenzierbare
Periodikeinteilung.

### Lösung: 24 Jieqi als primäre externe Achse

```
24 Jieqi (节气) × 15° Sonnenlänge = 360°
Periode: ~15.2 Tage
```

Warum Jieqi?
1. **Astronomisch präzise**: Jede Phase = exakt 15° Sonnenlänge
2. **BaZi-konform**: Jieqi definieren die Monatsgrenzen der Vier Pfeiler
3. **Deterministisch**: Aus UTC-Zeitpunkt + Sonnenlänge eindeutig bestimmbar
4. **Traditionsgebunden**: In beiden Traditionen (West + Ost) referenzierbar
5. **Testbar**: Statistische Muster bei echten Daten validierbar

Sekundäre Achse: 8 Mondphasen (45° Mond-Sonne-Winkel, ~3.7 Tage/Phase)

**Implementation:** `bazi_engine/phases/jieqi_phase.py`, `lunar_phase.py`

---

## Problem 4: Keine methodische Absicherung gegen Scheinkorrelationen

### Diagnose

Ohne statistischen Test kann jede Phase-Interpretation als "signifikant"
erscheinen — auch wenn sie rein zufällig ist.

### Lösung: Empirisches Analysewerkzeug mit Anti-Bias-Tests

```
bazi_engine/research/
  dataset_generator.py  — stratifizierte Zufallsdatensätze
  pattern_analysis.py   — Kruskal-Wallis + Bonferroni + Effektstärke
```

**Validierungsprinzip:**
> Jede behauptete Phase-Qualität muss in einem Kruskal-Wallis-Test
> mit echten Geburtsdaten p_bonferroni < 0.05 **und** η² ≥ 0.06 zeigen.
> Für synthetische Zufallsdaten darf kein Test signifikant sein.

**Implementierter Nachweis:**
```python
# Mit 480 synthetischen Charts, seed=42:
KW h_calibrated~Jieqi: p_bonf=1.00, η²=0.003 → NICHT signifikant ✓
KW diff[Feuer]~Jieqi:  p_bonf=1.00, η²=0.000 → NICHT signifikant ✓
```

Der Anti-Bias-Test ist als CI-Test in `tests/test_research.py::TestNoSpuriousCorrelation` dauerhaft eingebaut.

---

## Architektur: Neue Modulebenen

```
Level 0:  exc.py, constants.py
Level 1:  types.py
Level 2:  ephemeris.py, time_utils.py, solar_time.py
          phases/jieqi_phase.py    ← NEU: externe Periodik
          phases/lunar_phase.py    ← NEU: Mondphasen
Level 3:  jieqi.py
Level 4:  bazi.py, western.py, fusion.py
          wuxing/constants.py, wuxing/vector.py, wuxing/analysis.py
          wuxing/zones.py          (Logik B)
          wuxing/calibration.py    ← NEU: H-Kalibrierung
Level 5:  app.py, cli.py, bafe/*, routers/*, services/*
          research/                ← NEU: Analyse-Tools
```

---

## Signal-Inventar (Ground-Truth-Status)

| Signal | Quelle | GROUND? | Deutungsebene |
|---|---|---|---|
| H_raw | cos(θ) der normierten Vektoren | ✅ | Strukturell komprimiert → nutze H_calibrated |
| H_calibrated | H_raw kalibriert vs Baseline | ✅ | Hauptdeutungssignal |
| d_i | west_norm_i − bazi_norm_i | ✅ | Elementare Differenz |
| r_i | west_norm_i × bazi_norm_i | ✅ | Resonanzachse |
| Zonen | f(d_i, west_i, bazi_i) | ✅ | Logik B Klassifikation |
| Jieqi-Phase | Sonnenlänge (extern) | ✅ | Zeitqualität |
| Mondphase | Mond-Sonne-Winkel (extern) | ✅ | Zyklische Energie |
| Sheng-Zyklus | Konstante C₅-Ordnung | ✅ Konstante | Nur als Leitfragen-Struktur |
| Ke-Zyklus | Kontrollzyklus (nicht berechnet) | ❌ (todo) | Noch kein Signal |
| Archetypen | Aus H_calibrated + r_i | ⚠️ Interpretation | Muss empirisch validiert werden |

---

## Offene Arbeiten

### Nächste Priorität: H_calibrated in Fusion-Output integrieren

Aktuell wird `calibrate_harmony()` nicht automatisch in `compute_fusion_analysis()`
aufgerufen. Das ist der nächste Implementierungsschritt:

```python
# In compute_fusion_analysis():
calibration = calibrate_harmony(
    h_raw, western_bodies, bazi_pillars, western_wuxing, bazi_wuxing
)
# → Zum Rückgabe-Dict hinzufügen:
result["h_calibrated"] = calibration.h_calibrated
result["quality"] = calibration.quality
result["sigma_above_baseline"] = calibration.sigma_above
```

### Mittelfristig: Empirische Validierung mit echten Daten

Das `research/`-Paket ist bereit für echte Geburtsdaten. Sobald ein
Datensatz mit mindestens 2400 Geburten (100 pro Jieqi-Phase) vorliegt,
kann der Kruskal-Wallis-Test auf echte Muster getestet werden.

Erst wenn dort p_bonf < 0.05 + η² ≥ 0.06 für ein Feature auftaucht,
ist ein Muster "empirisch gefunden" — nicht vorher.

### Langfristig: Ke-Zyklus als berechneter Signalkanal

Sobald die d_i-Differenzen stabil sind, kann der Ke-Zyklus als
echter Berechnungskanal eingeführt werden:
```python
ke_tension_score = sum(diffs[KE[e]] * (1 if diffs[e] < 0 else -1) for e in tension_elements)
```
Das wäre dann kein Interpretations-Signal, sondern ein GROUND-Signal.
