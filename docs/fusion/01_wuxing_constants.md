# 01 — Wu-Xing Konstanten: Die fünf Elemente als Koordinatensystem

> **Seit 2026-11-06:** Der Fusion-Layer ordnet westliche Körper nicht mehr nach Planetennamen zu, sondern über das Element ihres Zeichens (`WEST_ELEMENT_TO_WUXING`, siehe [12_west_element_mapping.md](12_west_element_mapping.md)). Die unten beschriebene Planet-Element-Tabelle gilt nur noch für Impact/Transit.

**Modul:** `bazi_engine/wuxing/constants.py`  
**Level:** 4 (reine Daten, keine Logik, keine Importe aus anderen Modulen)

---

## Was das Modul enthält

```python
PLANET_TO_WUXING: Dict[str, Union[str, List[str]]]
WUXING_ORDER:     List[str]          # ["Holz", "Feuer", "Erde", "Metall", "Wasser"]
WUXING_INDEX:     Dict[str, int]     # {"Holz": 0, "Feuer": 1, …}
```

Das ist der Brückentext zwischen zwei Kosmologien: Es übersetzt
westliche Planetensymbole in chinesische Elementzuordnungen und fixiert
die Reihenfolge für die Vektorkonstruktion.

---

## Die Mathematik der Zuordnung

### Vektorraumstruktur

Die fünf Elemente bilden die Basisvektoren eines ℝ⁵:

```
e₁ = Holz   = (1, 0, 0, 0, 0)
e₂ = Feuer  = (0, 1, 0, 0, 0)
e₃ = Erde   = (0, 0, 1, 0, 0)
e₄ = Metall = (0, 0, 0, 1, 0)
e₅ = Wasser = (0, 0, 0, 0, 1)
```

Jeder Planet wird genau einer dieser Achsen zugeordnet (Ausnahme: Merkur, dual).
Jedes Horoskop — western oder BaZi — wird als gewichtete Summe dieser Achsen dargestellt.

### Die Reihenfolge ist nicht arbiträr

`WUXING_ORDER = ["Holz", "Feuer", "Erde", "Metall", "Wasser"]`

Das ist der **Sheng-Zyklus (相生)** — der Erzeugungs-/Generierungszyklus:

```
Holz  → nährt → Feuer
Feuer → erzeugt → Erde (Asche)
Erde  → kondensiert zu → Metall
Metall → schmilzt zu → Wasser
Wasser → nährt → Holz
```

Diese Reihenfolge ist astronomisch relevant: Sie entspricht der traditionellen
Sequenz der Jahreszeiten (Frühling/Holz → Sommer/Feuer → Spätsommer/Erde →
Herbst/Metall → Winter/Wasser). Der Indexvektor hat damit eine immanente
Zyklusstruktur — benachbarte Elemente sind im Sheng-Zyklus verwandt.

---

## Die Planeten-Element-Zuordnung im Detail

| Planet | Element | Klassische Begründung | Westliche Entsprechung |
|---|---|---|---|
| Sonne | Feuer | Lebensenergie, Yang-Prinzip schlechthin | Vitalität, Identität, Lebenskraft |
| Mond | Wasser | Emotionen, Fluss, Yin-Prinzip | Unbewusstes, Reaktion, Empfindung |
| Merkur | Erde/Metall* | Kommunikation: Struktur (Tag) / Distinktion (Nacht) | Geist, Sprache, Verknüpfung |
| Venus | Metall | Form, Schönheit, Wertgebung | Ästhetik, Beziehung, Genuss |
| Mars | Feuer | Handlungsenergie, Yang-Aktivierung | Wille, Durchsetzung, Trieb |
| Jupiter | Holz | Wachstum, Expansion, Weisheit | Philosophie, Glück, Ausdehnung |
| Saturn | Erde | Begrenzung, Struktur, Disziplin | Pflicht, Zeit, Reife |
| Uranus | Holz | Durchbruch, Innovation, plötzliche Veränderung | Revolution, Unabhängigkeit |
| Neptun | Wasser | Träume, Spiritualität, Auflösung | Mystik, Illusion, Mitgefühl |
| Pluto | Feuer | Transformation durch Zerstörung und Wiedergeburt | Tod/Wiedergeburt, Macht |
| Chiron | Wasser | Heilung über Tiefgang und Verwundung | Der verwundete Heiler |
| Lilith | Wasser | Instinktives Unbewusstes, Schatten | Dunkle Weiblichkeit, Schatten-Ich |
| Mondknoten | Holz | Wachstumsrichtung, karmische Ausrichtung | Lebensaufgabe, Seelenziel |

*Merkur ist der einzige Doppelplanet — er wechselt mit dem Licht/Schattenverhältnis.

### Die Sonderstatus-Logik von Merkur

Merkur regiert in der westlichen Tradition **Zwillinge (Luft/Kommunikation)**
und **Jungfrau (Erde/Analyse)**. Im Wu-Xing-System wird diese Dualität
abgebildet als:

- **Tagkarte (Sonne über Horizont):** Merkur = Erde → analytisch, strukturierend
- **Nachtkarte (Sonne unter Horizont):** Merkur = Metall → distinktiv, präzisierend

Das ist eine kontextabhängige Projektion, keine Willkür. Sie folgt dem
klassischen BaZi-Prinzip, dass Elemente tagzeit-abhängig schwingen.

---

## Deutungsraum: Das Koordinatensystem als Symbolsprache

### Warum dieser Schritt entscheidend ist

Ohne das Mapping ist ein Horoskop ein String — mit dem Mapping ist es ein
Punkt im ℝ⁵. Erst die Projektion auf einen gemeinsamen Vektorraum ermöglicht
es, **Ost und West geometrisch zu vergleichen**.

Traditionell sind westliche und chinesische Astrologie inkommensurabel:
unterschiedliche Referenzsysteme, unterschiedliche Zeitbegriffe, unterschiedliche
Bedeutungslogiken. Die Wu-Xing-Projektion ist die **Übersetzungsschicht**,
die beide Systeme auf dieselbe Sprache hebt.

### Anschlussfähigkeit zu den Traditionen

**Westliche Astrologie:**
Das Mapping ehrt die klassischen Planetenrulerships. Es gibt keinen
westlichen Astrologen, der Mars nicht mit Energie/Feuer assoziiert oder
Saturn nicht mit Erde/Struktur. Die Zuordnungen sind intersubjektiv stabil.

**BaZi-Tradition:**
Die fünf Elemente sind das Herz aller chinesischen Kosmo-Divinationssysteme.
BaZi, I Ging, Feng Shui, TCM und Akupunktur arbeiten alle mit demselben
Grundvokabular. Die `WUXING_ORDER` in Sheng-Zyklus-Reihenfolge ist
traditionskonform und nicht interpretiert — sie ist kanonisch.

### Was dieser Raum *nicht* kodiert

Das Mapping ist absichtlich **elementar** gehalten:
- Keine Häusersystem-Gewichtung (welches Haus amplifies den Planeten?)
- Keine Aspekte (Konjunktion Sonne-Mars = doppelt Feuer?)
- Keine Jahrespillar-Gewichtung (Tag-Stamm > Jahres-Stamm im BaZi?)

Diese Vereinfachungen sind Designentscheidungen, keine Fehler.
Sie halten das Modell berechenbar und testbar. Tiefere Gewichtungslogiken
wären die nächste Entwicklungsstufe (→ `docs/fusion/09_erweiterungen.md`).
