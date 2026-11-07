# Astrologenberater-Leitfaden
## Fusion Astrology — Anwendung der zwei Deutungslogiken in der Praxis

**Version:** 1.1 (2026-11-07) · **Zielgruppe:** Praktizierende Astrologen mit Grundkenntnissen  
in westlicher Astrologie und/oder BaZi · **Sprache der API:** Deutsch

> **Stand 2026-11-07:** Die Gesamtlage wird nicht mehr aus dem rohen Kohärenz-Index H
> gelesen, sondern aus `calibration.sigma_above`: dem Abstand der Übereinstimmung zu
> vertauschten echten Geburtspaaren, in Standardabweichungen. Rohes H liegt bei
> vollständigen Horoskopen fast immer zwischen 0,6 und 1,0 (Erwartungswert ≈ 0,80) und
> taugt nicht als Skala. Die westliche Seite entsteht über das Element des Tierkreiszeichens,
> nach Stufen gewichtet (Sonne, Mond, Aszendent zuerst); Planeten haben keine feste
> Wandlungsphase mehr ([12_west_element_mapping.md](12_west_element_mapping.md)).

---

## Einleitung: Was dieses System leistet — und was nicht

Die Fusion-Analyse verbindet zwei vollständige astrologische Systeme über
einen gemeinsamen Symbolraum: die **fünf Wandlungsphasen (Wu Xing)**. Das
Ergebnis ist keine neue Astrologie — es ist ein **Übersetzungsraum**, in dem
westliche Planetendaten und chinesische Vier-Pfeiler-Daten geometrisch
verglichen werden können.

**Was das System liefert:**
- Die relative Elementarstruktur beider Systeme (normierte Vektoren)
- Den Winkel zwischen beiden Strukturen (Kohärenz-Index)
- Eine Topografie der Übereinstimmungen und Spannungen (Zonenklassifikation)
- Strukturierte Reflexionsfragen (Leitfragen)

**Was das System nicht liefert:**
- Vorhersagen oder Prognosen
- Eine Zusammenführung der Deutungsinhalte (was "Feuer im BaZi" bedeutet
  vs. was "Feuer im westlichen Chart" bedeutet, bleibt systemspezifisch)
- Ersatz für die klassische Interpretation beider Systeme

Der erfahrene Astrologe nutzt das Fusion-System als **dritten Blick** —
nachdem er das westliche Horoskop und das BaZi separat gelesen hat.

---

## Teil I: Logik A — Die narrative Deutung

### Wann Logik A einsetzen?

Logik A ist geeignet für Klienten, die:
- eine Geschichte über sich hören möchten (nicht eine Analyse)
- astrologische Vorkenntnisse haben, aber nicht zwingend BaZi kennen
- einen emotionalen Zugang zu ihrer Biographie suchen
- in einer Lebensphase der Orientierungsfindung sind

### Die drei Grundbausteine der narrativen Deutung

**Baustein 1: Der Archetypus**

Aus der Gesamtlage (`sigma_above`) und der dominanten Resonanzachse (welches
Element trägt die Kongruenz am stärksten?) ergibt sich ein Archetypus:

```
Schritt 1: Gesamtlage aus sigma_above bestimmen (calibration.sigma_above)
  σ ≥ +1,0         → Starke Kohärenz
  +0,5 ≤ σ < +1,0  → Gute Ausrichtung
  −0,5 < σ < +0,5  → Produktive Spannung (Ausgleich, gewöhnliche Lage)
  −1,0 < σ ≤ −0,5  → Kreative Dissonanz
  σ ≤ −1,0         → Integrationsauftrag
  quality ≠ "ok"   → Gesamtlage nicht deuten

Schritt 2: Resonanzachse bestimmen
  → Für welches Element ist (west_norm[i] × bazi_norm[i]) am größten?
  → Das ist die Achse, die die Kongruenz "trägt"

Schritt 3: Archetypus aus Matrix
  → Tabelle Dok 07_deutungsraume.md
```

| | Holz | Feuer | Erde | Metall | Wasser |
|---|---|---|---|---|---|
| σ ≥ +1 | Der Visionär | Der Leuchtturm | Der Anker | Der Meister | Der Tiefenschwimmer |
| +0,5 bis +1 | Der Wachstumstreiber | Der Kommunikator | Der Strukturgeber | Der Differenzierer | Der Intuitive |
| −0,5 bis +0,5 | Der Alchemist | Der Alchemist | Der Alchemist | Der Alchemist | Der Alchemist |
| −1 bis −0,5 | Der Wanderer | Der Flackernde | Der Sucher | Der Zweifler | Der Rückgezogene |
| σ ≤ −1 | Brückenbauer | Brückenbauer | Brückenbauer | Brückenbauer | Brückenbauer |

**Praxistipp:** Der Archetypus ist eine Einladung, keine Diagnose. Formuliere
ihn als Frage: *"Erkennst du in dir den Zug zum Leuchtturm — das Bedürfnis,
konsistent und sichtbar zu sein?"*

---

**Baustein 2: Die Dreisatz-Erzählung**

Jede narrative Deutung folgt demselben Dreisatz:

```
1. Wer du bist       → dominant_bazi_element: innere Grundstruktur
2. Was der Moment bringt → dominant_western_element: kosmischer Kontext
3. Wie sich beides verhält → sigma_above + Differenzfeld: Kongruenz oder Spannung
```

**Mustertext (sigma_above = +0,6, Resonanzachse Feuer, d_Holz = −0,38):**

> *"Dein BaZi zeigt eine ausgeprägte Feuerstruktur — Vitalität, Präsenz
> und das Bedürfnis nach Verbindung sind in deiner Zeitstruktur angelegt.
> Das Holzelement darunter (Stämme und verborgene Zweig-Qi) gibt diesem
> Feuer Nahrung: du wächst, um zu leuchten.*
>
> *Der Himmel deiner Geburt bestätigt das: Sonne und Mond stehen in Feuerzeichen,
> und Feuer trägt nach der Bazodiac-Übersetzung Feuer und Holz. Kosmisch und
> strukturell sprichst du eine ähnliche Sprache — beide Systeme stimmen hier
> deutlicher überein als bei zufälligen Geburtspaaren.*
>
> *Die Spannung liegt im Holz: deine innere Holzstruktur übersteigt das
> Himmelsangebot deutlich (−38 Indexpunkte). Das bedeutet: Wachstumsantrieb
> kommt bei dir primär von innen. Du brauchst keinen kosmischen Rückenwind —
> aber du brauchst Räume, in denen diese innere Kraft sichtbar werden kann."*

**Praxistipp:** Halte den Dreisatz unter 200 Wörtern. Was der Klient
mitnehmen soll, ist ein einziger prägnanter Satz — nicht die vollständige
Analyse.

---

**Baustein 3: Die Entwicklungsfrage**

Das Element mit der höchsten absoluten Differenz `|d_i|` ist das
Entwicklungsfeld der Sitzung. Es wird als offene Frage formuliert:

```
Wenn d < 0 (BaZi > West — innere Kraft sucht Ausdruck):
  "Was würde sich verändern, wenn diese [Element]-Kraft
   nach außen sichtbar werden dürfte?"

Wenn d > 0 (West > BaZi — kosmischer Impuls übersteigt innere Struktur):
  "Was hält dich davon ab, den [Element]-Impuls, den die
   Welt dir anbietet, vollständig anzunehmen?"
```

**Praxistipp:** Diese Frage ist der Abschluss der Deutung, nicht der Anfang.
Sie öffnet in die Reflexion — nicht in weitere Erklärung.

---

### Häufige Fehler in der narrativen Deutung

**Fehler 1: Den Archetypus als Wahrheit formulieren**

❌ *"Du bist der Leuchtturm."*  
✅ *"Der Archetypus, der in deiner Fusion-Struktur aufscheint, ist der
Leuchtturm. Erkennst du das in dir?"*

**Fehler 2: Feuer im westlichen Chart = Feuer im BaZi gleichsetzen**

Das ist die häufigste konzeptuelle Falle. Das System misst **Elementargewichte**,
nicht Bedeutungen. Feuer als westliche Mars-Energie (Antrieb, Durchsetzung) ist
nicht dasselbe wie Feuer als BaZi-Stammenergie (Bing = expansives Feuer der
Sonne, Ding = intimes Feuer der Kerze). Die narrative Deutung verbindet die
Gewichte — nicht die Bedeutungsinhalte.

**Fehler 3: Den Kohärenz-Index als Qualitätsurteil lesen**

❌ *"Dein Wert ist niedrig, deine Energie ist nicht ausgerichtet."*  
✅ *"Beide Systeme beschreiben deinen Moment hier in verschiedenen Sprachen.
Das ist kein Defekt — es ist eine Komplexität."* (Ein negatives `sigma_above`
heißt nur: weniger Übereinstimmung als bei zufälligen Paaren.)

**Fehler 4: Sheng-Aussagen als Fakten formulieren**

❌ *"Weil du so viel Holz hast, stärkt das automatisch dein Feuer."*  
✅ *"Im Sheng-Zyklus folgt auf Holz Feuer. Das ist eine Frage:
Würde ein bewusster Schritt in Richtung mehr Ausdruck (Feuer) helfen,
deine innere Holzkraft sichtbarer zu machen?"*

---

## Teil II: Logik B — Die diagnostische Karte

### Wann Logik B einsetzen?

Logik B ist geeignet für Klienten, die:
- strukturierte Selbstreflexion bevorzugen
- analytisch oder wissenschaftlich denkend sind
- keine astrologischen Vorkenntnisse haben oder bewusst davon Abstand nehmen
- eine konkrete Orientierungshilfe suchen (nicht eine Geschichte)
- das Ergebnis selbst deuten und eigene Schlüsse ziehen möchten

### Die vier Zonen verstehen

```
TENSION      — |Δ| > 15 Pkt.:  Energie in Bewegung, Innen ≠ Außen
STRENGTH     — beide > 20, |Δ| ≤ 15:  Stabiles Doppelfundament
DEVELOPMENT  — beide < 15:  Unentwickelter Raum, kein Druck
NEUTRAL      — keines der obigen:  Im Hintergrund, kein aktives Thema
```

**Wichtig für die Kommunikation mit dem Klienten:**

Die Werte sind **L2-Indexpunkte** (L2-Koordinate × 100), keine prozentualen
Anteile. Sage nie "Du hast 61% Feuer" — das ist mathematisch falsch und
erzeugt falsche Erwartungen. Sage stattdessen: "Feuer hat in deinem westlichen
Chart einen Index von 61 Punkten."

Die Zahlen summieren sich nicht zu 100. Sie beschreiben, wie stark jede Achse
in einem fünfdimensionalen Raum ausgeprägt ist.

---

### Die diagnostische Karte in der Sitzung lesen

**Schritt 1: Überblick verschaffen (30 Sekunden)**

Lies zuerst nur die Zonen, nicht die Werte:
- Wie viele Tension-Elemente gibt es? (0–5)
- Gibt es Strength-Elemente? (Fundament)
- Gibt es Development-Elemente? (blinde Flecken)

```
Kein Tension, viel Strength → ruhiges, konsolidiertes Profil
Viel Tension, wenig Strength → viele aktive Themen, hohe Energie
Viel Development → unentwickelte Potenzialfelder
```

**Schritt 2: Tension-Richtung lesen (die wichtigste Information)**

Für jedes Tension-Element:

```
Δ positiv (West > BaZi, d.h. West dominiert):
  → Was die Welt anbietet, übersteigt die innere Struktur
  → Leitfrage: "Was nimmst du von dem, was dir das Leben anbietet, noch nicht an?"

Δ negativ (BaZi > West, d.h. BaZi dominiert):
  → Die innere Struktur ist stärker als das kosmische Angebot
  → Leitfrage: "Wo findet diese Stärke in deinem Leben keinen Ausdruck?"
```

**Schritt 3: Development-Elemente einordnen**

Development-Elemente sind nicht per se problematisch. Sie zeigen einen
**Bereich mit niedrigem Grundton** — und damit einem potenziell hohen
Hebelwert: wenig Input, viel Wirkung.

In der klassischen BaZi-Lesart wäre das das "fehlende Element" (缺, quē)
und wäre Ausgangspunkt für Empfehlungen zu Farben, Richtungen, Berufsfeldern,
die dieses Element stärken.

In der Fusion-Lesart formulierst du es als Möglichkeit:  
*"Wasser ist in beiden Systemen schwach vertreten. Was würde sich verändern,
wenn du mehr Raum für Rückzug, Stille und Intuition schaffst?"*

**Schritt 4: Die Sheng-Leitfragen einsetzen (optional)**

Die `[Sheng-Frage]` ist ein Interpretationsangebot, kein Fakt. Setze sie
ein, wenn der Klient offen für zyklisches Denken ist:

> *"Im Wu-Xing-Denken nährt Holz das Feuer. Das ist keine Vorhersage —
> aber eine Frage: Wenn du mehr in deine Wachstumskraft (Holz) investierst,
> was könnte das für deinen Ausdruckswillen (Feuer) bedeuten?"*

Wenn der Klient analytisch ist, lasse die Sheng-Fragen weg und bleibe
bei den datengebundenen Kernfragen.

---

### Der Report in der Sitzung

Zeige dem Klienten nicht den vollständigen Rohdaten-Report. Destilliere:

**Was du zeigst:** Nur die drei aktiven Sektionen (Stärke, Spannung, Entwicklung)  
**Was du weglässt:** Die Neutral-Elemente und die technischen Indexwerte  
**Was du betonst:** Die Leitfragen am Ende des Reports  

**Empfohlene Sitzungsstruktur (45 Minuten):**

```
0–5 Min:   Kontext klären (was sucht der Klient?)
5–15 Min:  Stärkefelder vorstellen ("Was läuft von selbst?")
15–30 Min: Tension-Elemente besprechen (Richtung + Leitfrage)
30–40 Min: Development-Felder ansprechen (Möglichkeit, nicht Defizit)
40–45 Min: Synthese — eine Hauptfrage mitgeben
```

---

## Teil III: Beide Logiken kombinieren

### Das empfohlene Standardformat

```
1. Diagnostische Karte (Logik B, 5 Minuten)
   → Gibt dem Klienten Orientierung: "Wo stehe ich?"

2. Narrative Deutung (Logik A, 10–15 Minuten)
   → Gibt der Karte eine Geschichte: "Wer bin ich in dieser Konstellation?"

3. Eine Hauptfrage (aus dem stärksten Tension-Element)
   → Geht mit dem Klienten mit: "Was nehme ich mit?"
```

### Wie die Logiken sich gegenseitig stützen

Die diagnostische Karte zeigt **was** — die narrative Deutung erzählt **warum**.

*Beispiel: Metall ist Tension-Element, Δ+35 (West dominiert)*

**Logik B (diagnostisch):**  
*"Metall hat in deinem westlichen Chart einen Index von 52, in deinem BaZi
nur 17. Die Welt stellt hohe Anforderungen an Klarheit und Distinktion —
deine innere Struktur ist dort weniger entwickelt."*

**Logik A (narrativ):**  
*"Metall ist das Element der Form, der Klinge, der klaren Grenze. Der Kosmos
deiner Geburt bringt Metall stark — durch Sonne und Aszendent in Erdzeichen,
die nach der Bazodiac-Übersetzung vor allem Metall tragen.
Dein BaZi trägt das weniger. Das könnte heißen: Du bist jemand, dem
andere Klarheit und Grenzen abfordern, bevor du sie dir selbst gegeben hast.
Der Weg des Meisters — das ist der Metall-Archetypus bei einem sigma_above von +0,7 —
ist, sich diese Distinktionsfähigkeit selbst anzueignen, statt sie
vom Leben abgefordert zu bekommen."*

---

## Teil IV: Anschlussfähigkeit zu den Traditionen

### Wenn der Klient westlich ausgebildet ist

Erkläre den Kohärenz-Index als **Systemaspekt** — analog zu einem Aspekt
zwischen zwei vollständigen Horoskopen, nicht zwischen zwei Planeten.  
Ein `sigma_above` ab etwa +1 bedeutet: Die Elementarstruktur deines Geburtsmoments
(westlich und östlich gelesen) stimmt deutlich mehr überein als bei zufälligen
Geburtspaaren, wie in einer Konjunktion. Ab etwa −1 überwiegt die Spannung, wie in
einem Quadrat — produktive Spannung, nicht Versagen.

### Wenn der Klient BaZi-Vorkenntnisse hat

Erkläre die westliche Seite als **externe Qi-Konfiguration** zum Zeitpunkt
der Geburt — analog zu Jahres- und Monatspfeilern, die auf den Lebensführer
(日主, rì zhǔ) einwirken. Die Planeten liefern eine externe Elementarkonfiguration;
das BaZi liefert die interne Grundstruktur. Der Kohärenz-Index misst, wie
kongruent diese externe Konfiguration mit der internen ist.

### Wenn der Klient keine Vorkenntnisse hat

Beginne ohne Fachbegriffe. Das Wichtigste:

> *"Wir haben zwei Systeme, die den Moment deiner Geburt beschreiben —
> eines aus der westlichen Astrologie, eines aus der chinesischen.
> Beide übersetzen wir in eine gemeinsame Sprache: fünf Elementarqualitäten.
> Dann schauen wir: Sagen beide dasselbe? Oder beschreiben sie
> denselben Moment aus verschiedenen Blickwinkeln?"*

---

## Teil V: Qualitätssicherung in der Deutung

### Drei Prüffragen vor jeder Aussage

Bevor du eine Deutung formulierst, stelle dir diese drei Fragen:

1. **Ist die Aussage aus den Zahlen ableitbar?**  
   Wenn du "Feuer ist dominant" sagst — kannst du auf den Indexwert zeigen?

2. **Ist die Aussage eine Frage oder eine Behauptung?**  
   Behauptungen über das Innenleben des Klienten sind problematisch.
   Fragen öffnen; Behauptungen schließen.

3. **Vermischst du Systemebenen?**  
   "Dein westliches Feuer (Mars) bedeutet dasselbe wie dein BaZi-Feuer (Bing)"
   — das ist eine Gleichsetzung, die das System nicht erlaubt. Beide sind
   Feuer im Elementarraum; was Feuer für den Klienten *bedeutet*, ergibt
   sich aus der Gesamtdeutung, nicht aus dem Mapping.

### Was das System nicht deutet

Das Fusion-System deutet **keine**:
- Lebensabschnitte oder Zeitpfeiler (Dekaden, Jahrespfeiler)
- Partnerschaftssynastrie (Vergleich zweier Personen)
- Karmaische oder transpersonale Strukturen
- Gesundheitliche Themen
- Berufs- oder Finanzprognosen

Für alle diese Felder gelten die klassischen Methoden der jeweiligen Tradition.

---

## Anhang: Schnellreferenz für die Sitzung

### Kohärenz-Index — auf einen Blick

| sigma_above | Archetypisches Label | Sitzungsimpuls |
|---|---|---|
| ≥ +1 | Starke Kohärenz | "Was brauchst du, um diese Stimmigkeit zu erhalten?" |
| +0,5 bis +1 | Gute Ausrichtung | "Wo spürst du, dass Innen und Außen übereinstimmen?" |
| −0,5 bis +0,5 | Produktive Spannung | "Welche Spannung in dir ist eigentlich eine Ressource?" |
| −1 bis −0,5 | Kreative Dissonanz | "Wie lebst du mit zwei verschiedenen inneren Rhythmen?" |
| ≤ −1 | Integrationsauftrag | "Was wäre ein erster Schritt zur inneren Verbindung?" |

### Tension-Richtung — auf einen Blick

| Richtung | Bedeutung | Kernfrage |
|---|---|---|
| West > BaZi (Δ > 0) | Äußeres Angebot übersteigt innere Struktur | "Was nimmst du noch nicht an?" |
| BaZi > West (Δ < 0) | Innere Stärke übersteigt äußeres Angebot | "Wo findet das keinen Ausdruck?" |

### Sheng-Zyklus — Schnellreferenz

| Element | genährt von (prev) | nährt (next) | kontrolliert | wird kontrolliert von |
|---|---|---|---|---|
| Holz | Wasser | Feuer | Erde | Metall |
| Feuer | Holz | Erde | Metall | Wasser |
| Erde | Feuer | Metall | Wasser | Holz |
| Metall | Erde | Wasser | Holz | Feuer |
| Wasser | Metall | Holz | Feuer | Erde |

*Der Kontrollzyklus (Ke) ist im aktuellen System nicht automatisch berechnet —
er kann als Interpretationsstruktur für Leitfragen verwendet werden.*

---

## Versionierung

| Version | Datum | Änderungen |
|---|---|---|
| 1.0 | März 2026 | Erstveröffentlichung |

*Für Rückmeldungen aus der Praxis: bitte als GitHub Issue im FuFirE-Repository.*
