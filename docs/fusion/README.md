# Fusion Astrology — Dokumentationsübersicht

Dieses Verzeichnis dokumentiert das **Fusion Astrology**-Modell des BaZi Engine:
ein mathematisches Framework, das westliche Planetenastrologie und chinesische
BaZi-Vierparameterberechnung in einem gemeinsamen Symbolraum verbindet.

## Inhalt

| Datei | Thema |
|---|---|
| [01_wuxing_constants.md](01_wuxing_constants.md) | Die fünf Elemente als Koordinatensystem — Mapping, Grundlagen, Traditionsanschluss |
| [02_wuxing_vector.md](02_wuxing_vector.md) | WuXingVector — Die Geometrie des Elementarfeldes |
| [03_wuxing_analysis.md](03_wuxing_analysis.md) | Vektorextraktion aus Planeten und Vier Pfeilern |
| [04_solar_time.md](04_solar_time.md) | Zeitkorrektur — Wahre Sonnenzeit und Zeitgleichung |
| [05_harmony_index.md](05_harmony_index.md) | Der Harmony Index — Cosinus-Ähnlichkeit als Deutungsmaß |
| [06_fusion_orchestration.md](06_fusion_orchestration.md) | compute_fusion_analysis() — Die Gesamtarchitektur |
| [07_deutungsraume.md](07_deutungsraume.md) | Deutungsräume: Resonanzachse, Spannungsfeld, Archetypen |
| [08_deutungslogiken.md](08_deutungslogiken.md) | Zwei Deutungslogiken: narrativ vs. diagnostisch (Logik B v3, exklusiv/hierarchisch) |
| [09_nutzertest_design.md](09_nutzertest_design.md) | A/B-Testdesign und Fragebogen |
| [10_sheng_zyklus.md](10_sheng_zyklus.md) | Sheng-Zyklus: Struktur vs. Messung vs. Interpretation; Ke-Zyklus als nächste Erweiterung |
| [12_west_element_mapping.md](12_west_element_mapping.md) | Westen → Wu Xing über das Zeichen-Element (sign-element-consensus-v1, seit 2026-11-06) |


## Konzept in einem Satz

> Die Fusion-Berechnung misst den Winkel zwischen zwei Vektoren
> im fünfdimensionalen Elementarraum — einer aus den Planeten des
> Geburtsmoments, einer aus den Vier Pfeilern des Schicksals —
> und macht daraus eine lesbare Aussage über kosmische Kongruenz.

## Architektonische Einordnung

```
Level 0: exc.py, constants.py
Level 2: solar_time.py          ← Zeitkorrektur (reine Mathematik)
Level 4: wuxing/constants.py    ← Element-Mapping (reine Daten)
          wuxing/vector.py       ← WuXingVector (reine Geometrie)
          wuxing/analysis.py     ← Vektorextraktion + Harmony Index
          fusion.py              ← Orchestrierung + Textgenerierung
Level 5: routers/fusion.py      ← HTTP-Endpunkt
```

Kein Level greift nach oben. Alle Berechnungen sind deterministisch und
zustandslos — identische Eingaben erzeugen identische Ausgaben.
