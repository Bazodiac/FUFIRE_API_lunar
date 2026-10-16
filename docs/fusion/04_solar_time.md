# 04 — Wahre Sonnenzeit: Zeitkorrektur und Zeitgleichung

**Modul:** `bazi_engine/solar_time.py`  
**Level:** 2 (reine Mathematik, keine internen Importe)

---

## Warum Zeitkorrektur in der Astrologie?

Alle astrologischen Systeme beziehen sich auf die **tatsächliche Position der Sonne**
am Himmel — nicht auf die konventionelle Uhrzeit, die Zeitzonen und politische
Grenzen reflektiert.

**Das Problem:**
Die Mitteleuropäische Zeit (MEZ, UTC+1) legt fest, dass in Berlin und in Prag
dieselbe Uhrzeit gilt. Astronomisch ist das falsch: Berlin liegt bei 13,4°O,
Prag bei 14,4°O. Beide Städte befinden sich eine Sonnenstunde von der
Standardmeridian-Referenz (15°O für MEZ) entfernt — aber in verschiedene
Richtungen.

**Die Lösung:** Wahre Sonnenzeit (WSZ / True Solar Time):
```
WSZ = Bürgerliche Zeit - Zeitzonenkorrektur + Längenkorrektur + Zeitgleichung
```

---

## Funktion: `equation_of_time(day_of_year, use_precise=True)`

### Was die Zeitgleichung misst

Die Zeitgleichung (EoT) beschreibt die Differenz zwischen
**Apparenter Sonnenzeit** (echte Sonnenbewegung) und
**Mittlerer Sonnenzeit** (gleichförmige Referenzbewegung):

```
EoT = Apparente Sonnenzeit − Mittlere Sonnenzeit  [in Minuten]
```

Sie entsteht aus zwei überlagerten physikalischen Effekten:

**Effekt 1: Elliptizität der Erdbahn (Kepler)**  
Die Erde bewegt sich schneller, wenn sie der Sonne näher ist (Perihel, ~Jan 3),
und langsamer im Aphel (~Jul 4). Das erzeugt Schwankungen der Tageslänge
von bis zu ±7,7 Minuten mit einem Jahreszyklus.

**Effekt 2: Schiefe der Ekliptik (Obliquität)**  
Die Erdachse ist um 23,4° geneigt. Die Projektion der Sonnenbewegung
auf den Himmelsäquator ist nicht gleichförmig — an den Äquinoktien
bewegt sie sich schneller, an den Solstitien langsamer. Erzeugt
Schwankungen mit einem Halbjahreszyklus.

### Die präzise Formel (NOAA)

```python
gamma = 2π × (N - 1) / 365

EoT = 229.18 × (
    0.000075
    + 0.001868 × cos(γ)
    - 0.032077 × sin(γ)
    - 0.014615 × cos(2γ)
    - 0.040849 × sin(2γ)
)
```

**Rückgabe:** Minuten, mit Vorzeichen. Bereich: ca. −14,2 bis +16,4 Minuten.

**Referenzpunkte:**
| Tag | Datum (ca.) | EoT (Min) | Bedeutung |
|---|---|---|---|
| 1 | 1. Januar | +3,0 | Sonne läuft nach |
| 15 | 15. Januar | −9,0 | |
| 60 | 1. März | −12,5 | |
| 105 | 15. April | +0,0 | Nulldurchgang |
| 172 | 21. Juni | −1,5 | Sommersonnenwende |
| 180 | 29. Juni | −3,0 | Minimum der Überlagerung |
| 211 | 30. Juli | −6,5 | |
| 264 | 21. Sept | +0,0 | Nulldurchgang |
| 305 | 1. Nov | +16,4 | Maximum (Sonne läuft vor) |
| 355 | 21. Dez | +0,0 | Nulldurchgang |

### Die approximative Formel (Spencer)

```python
B = 360° × (N - 81) / 365
EoT ≈ 9.87 × sin(2B) − 7.53 × cos(B) − 1.5 × sin(B)
```

Genauigkeit: ±1 Minute. Ausreichend für die meisten astrologischen Zwecke,
die auf Minutenpräzision nicht angewiesen sind.

---

## Funktion: `true_solar_time(civil_time, longitude, day_of_year, tz_offset)`

### Formel

```
UTC = civil_time − tz_offset
LMT = UTC + longitude / 15          [Stunden; 15° ≡ 1 Stunde]
TST = LMT + EoT / 60
```

**Warum `longitude / 15`?**
Die Erde dreht sich 360° in 24 Stunden = 15° pro Stunde.
Ein Grad entspricht 4 Minuten Zeitdifferenz.
Berlin (13,4°O) liegt 1,6° westlich des MEZ-Meridians (15°O)
→ Korrektur: −6,4 Minuten relativ zur Standardzeit.

### Beispielrechnung: Berlin, 10. Februar 2024, 14:30 MEZ

```
N = 41 (41. Tag des Jahres)
EoT = 229.18 × (0.000075 + 0.001868×cos(γ) - ...) ≈ -14,1 Min

UTC           = 14:30 − 1:00 = 13:30 = 13.50 h
LMT           = 13.50 + 13.405/15 = 13.50 + 0.894 = 14.394 h
TST           = 14.394 + (−14.1)/60 = 14.394 − 0.235 = 14.159 h
             ≈ 14:09:32 WSZ
```

---

## Engine-Pfad: `time_context.compute_effective_time_context_from_instant()`

Der kanonische Pfad der Engine (BaZi-Stundensäule bei `TLST`, `/calculate/tst`,
Trace `time_resolution`, Chronometrie) ist seit FBP-TST-003 (2026-10-16)
`bazi_engine/time_context.py`. Er wendet dieselbe Definition wie oben als
eine einzige Zeitdifferenz auf den **UTC-Instant** an:

```
TLST_instant = UTC + (λ × 4 min + EoT)
tlst_hours   = Stunde des Tages von TLST_instant
date_rollover = Datum(TLST_instant) − Datum(zivil)        ∈ {−1, 0, +1}
```

**Zeitgleichung im Engine-Pfad (FBP-TST-006, seit 2026-10-16):** `EoT` ist
hier `solar_time.equation_of_time_jd(jd_ut)` — Meeus, *Astronomical
Algorithms* (1998), Gl. 28.1, ausgewertet am exakten UT-Instant, rein
stdlib (kein Swiss-Ephemeris-Aufruf; `/calculate/tst` bleibt
ephemeridenfrei). Abweichung zu `swe.time_equ`: max 0,058 min
(1950–2030). Die oben beschriebene NOAA/Spencer-Tagesformel
`equation_of_time(day_of_year)` (Fehler ≤ 0,8 min) ist **nicht** mehr der
Engine-Pfad; sie bleibt nur für den Degraded-Pfad von `/validate`
(`eot_provenance = "spencer_1971"`) bestehen. Jede Oberfläche, die
`eot_minutes` ausgibt, trägt das Provenance-Feld `eot_source`
(`"meeus_1998"`).

Der Einstieg erwartet ein zeitzonen-bewusstes `datetime` (DST-Fold bereits
aufgelöst); die String-Variante `compute_effective_time_context(iso, tz, lon,
fold=…)` delegiert dorthin. Referenzkorpus gegen Swiss Ephemeris
(`swe.lmt_to_lat`): `tests/fixtures/tlst_reference_corpus_v1.json`.

> **Historie (DEV-2026-009):** Bis FBP-TST-003 addierte dieser Pfad die
> Längenkorrektur auf die *zivile* Uhrzeit statt auf UTC und lag damit für
> jede Nicht-UTC-Zone um den Zonen-Offset daneben (Hannover 15:44 MESZ: 16:17
> statt 14:17). Die frühere Standardmeridian-Variante
> `fusion.true_solar_time_from_civil()` hatte zusätzlich ein invertiertes
> Längengrad-Vorzeichen und wurde entfernt (DEV-2026-012).

---

## Deutungsraum: Zeitkorrektur als astrologische Präzisionsaussage

### Warum das für die Deutung relevant ist

Die Ascendant-Berechnung ist hochgradig zeitempfindlich: 4 Minuten Zeitfehler
entsprechen einem Grad Aszendent-Verschiebung. In einem typischen Horoskop
wechselt das Aszendant-Zeichen alle 2 Stunden — bei zeitgrenznahen Geburten
entscheidet eine Zeitkorrektur von 14 Minuten über das Aszendant-Zeichen.

**Im BaZi:**  
Die Stundenpfeiler-Grenzen liegen alle 2 Stunden — weniger sensitiv als
der westliche Aszendent, aber bei Geburten nahe den Zi-Grenzen (23:00/01:00)
kann die korrekte Wahre Sonnenzeit das Ergebnis fundamental verändern.

### Das Problem des "toten Winkels"

Moderne Software verwendet meist Zonenzeit ohne Zeitgleichungskorrektur.
Das ist eine **systematische Ungenauigkeit von bis zu ±16 Minuten** —
die größte lösbare Fehlerquelle in der Geburtszeit-Kalkulation.

`solar_time.py` macht diese Korrektur explizit und testbar.
Sie ist damit der astrologie-technisch häufigste Unterschied
zwischen einem präzisen und einem approximativen Horoskop.

### Anschlussfähigkeit zu den Traditionen

**BaZi:**  
Die klassische Lehre verwendet die **Wahre Sonnenzeit** (真太阳时) —
nicht die Zonenzeit. Viele moderne BaZi-Apps vernachlässigen das.
Die Verwendung von `true_solar_time()` bei der Stundenberechnung
ist traditionell korrekt.

**Westliche Astrologie:**  
Die Zeitgleichungskorrektur ist in der modernen Computereastrologie
standardisiert (Swiss Ephemeris rechnet immer mit Sonnenzeit).
Sie ist daher eher eine Vollständigkeitsbedingung als eine Neuerung.
