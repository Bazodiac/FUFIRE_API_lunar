# FuFirE Spec: Synastrie-Endpunkt (G1 + G1b)

Stand: 2026-11-08 · Status: Entwurf zur Umsetzung · Repo: Bazodiac/FUFIRE_API_lunar (master 6557de2) · Umsetzung lokal, kein Push/PR ohne Freigabe.

> Part A is the spec as handed over by Ben (verbatim). Part B records the decisions that close
> the gaps the spec leaves open; four of them were answered by Ben on 2026-11-08, the rest are
> plan decisions that follow from the repository (each names its reason). The implementation plan is
> `docs/superpowers/plans/2026-11-08-synastry-endpoint.md`.

## Part A — Spec (verbatim)

### Ziel
FuFirE liefert für zwei Personen deterministische westliche Paar-Fakten: Aspekte zwischen den Charts, Hausüberlagerungen, Achsenkontakte und die Zeichen-Ebene inkl. Übersetzung in Wu Xing über die Konsensmatrix. Keine Deutung, kein Score.

### Endpunkt
POST /v1/relationship/synastry (nur unter /v1 mounten, wie Hehun).
Request: person_a, person_b mit denselben Feldern wie /calculate/western (date, tz, lon, lat, birth_time_known, ambiguousTime, nonexistentTime). Optional display_label je Person (nur Vorname/Initiale), nie im Log.

### Berechnung
1. Beide Charts über die bestehende Western-Funktion (Swiss Ephemeris, Placidus mit bestehendem Fallback). Kein Neuberechnen eigener Ephemeriden.
2. Faktoren: Sonne, Mond, Merkur, Venus, Mars, Jupiter, Saturn, Uranus, Neptun, Pluto; jeder Kontakt trägt das Körpergewicht wie im Fusion-Vektor (gestufte Gewichtung: Lichter und Aszendent stark, langsame Planeten schwach), Feld weight; dazu Aszendent und MC nur bei bekannter Geburtszeit der jeweiligen Person.
3. Aspekte A→B für jedes Faktorpaar (nicht nur i<j, sondern volle Kreuzmatrix). Fünf Hauptaspekte, Orben aus Astro-Noctum: Konjunktion und Opposition 8°, Trigon und Quadrat 6°, Sextil 4°. Für Aszendent/MC als Partner: gleiche Orben. Pro Paar höchstens ein Aspekt. Feld exact: Orb ≤ halber Orb.
4. Hausüberlagerungen in beide Richtungen: Planeten von A in den Häusern von B und umgekehrt. Gate: Ist die Geburtszeit des Hausbesitzers unbekannt, Status unavailable_missing_time, keine Werte.
5. Zeichen-Ebene (G1b): Für Sonne, Mond, Merkur, Venus, Mars, Aszendent beider Personen das Zeichen, sein westliches Element und die Zeichenbeziehung zwischen den Paarfaktoren nach Abstand der Zeichen: gleiches Zeichen, Sextil-Zeichen (2), Quadrat-Zeichen (3), Trigon-Zeichen (4), Opposition (6), Halbsextil (1), Quinkunx (5). Dazu Elementbeziehung (gleich / Feuer-Luft bzw. Erde-Wasser / sonst).
6. Wu-Xing-Übersetzung: Jedes Faktor-Element wird mit der Konsensmatrix sign-element-consensus-v1 (dieselbe wie im Fusion-Vektor, Version mitliefern) auf fünf Phasen verteilt. Ausgabe pro Person ein Paarfaktor-Vektor; keine Vergleichszahl in G1.

### Response
- aspects[]: from_person, from_factor, to_person, to_factor, type, exact_angle, orb, exact.
- house_overlays: a_in_b[], b_in_a[] je mit factor, house, status.
- sign_layer: factors je Person (factor, sign, sign_index, west_element, degree), pairs[] (factor_a, factor_b, sign_relation, element_relation).
- wuxing_pair_factors: person_a, person_b (Vektor in WUXING_ORDER), mapping_version.
- provenance: engine version, ephemeris mode, house system used, orb policy id synastry-orbs-v1, mapping version, warnings.
- Kein Feld score, compatibility, percent o. Ä.

### Nicht im Umfang
Composite, Beziehungstransite, Nebenaspekte, Chiron, Knoten, Deutungstexte, Kreuzresonanz (G3), BaZi-Zweigkombinationen (G2).

### Tests (Abnahme)
- Determinismus: gleiche Eingabe ergibt identische Antwort.
- Symmetrie: Tausch A/B spiegelt from/to und a_in_b/b_in_a exakt.
- Orb-Grenzen: Fixture mit Abstand genau an und knapp über der Grenze je Aspektart.
- Geburtszeit-Gate: B ohne Zeit → keine Overlays in B, kein Aszendent/MC von B, Overlays in A weiter vorhanden.
- Zeichenbeziehung: alle sieben Abstandsklassen mit Fixture.
- Konsensmatrix: Vektor je Faktor summiert auf 1; mapping_version stimmt mit Fusion überein.
- Kein Scorefeld im Schema (Contract-Test).
- Datenschutz: keine Geburtsdaten oder Labels in Logs.
- Bestehende Suite bleibt grün (SWIEPH).

### Definition of Done
Lokal grün inkl. neuer Tests, OpenAPI aktualisiert, Doku docs/relationship/01_synastry.md, Beispielantwort für ein Testpaar. Kein Push, kein Deploy ohne Bens Freigabe.

## Part B — Resolved decisions

| ID | Decision | Source |
|----|----------|--------|
| D1 | `aspects[].weight = from_weight × to_weight` (rounded to 6 decimals); `from_weight` and `to_weight` are emitted too. Sun–Moon 1.0, Sun–Pluto 0.027. | Ben, 2026-11-08 |
| D2 | MC gets tier 1 (weight 1.0), like the ascendant, through a synastry-only override table `SYNASTRY_TIER_OVERRIDES = {"MC": 1}`. The Fusion table `WESTERN_BODY_TIER` is not touched. Weighting id `synastry-weights-v1` (= `body-tier-q0.3-v1` + MC tier 1). | Ben, 2026-11-08 |
| D3 | `wuxing_pair_factors.person_x = {factors: [{factor, west_element, weight, vector[5]}], vector[5]}`. Each factor vector is the consensus-matrix row of its sign element (sums to 1). The person vector is the tier-weighted mean of the factor vectors, normalised to sum 1. Factor set = the sign-layer factors of step 5 (Sun, Moon, Mercury, Venus, Mars, Ascendant if the time is known). No comparison number between the persons. | Ben, 2026-11-08 (shape + weighting); factor set follows step 5 |
| D4 | Consent parity with Hehun: required `options.second_person_consent_confirmed`; absent → 422 `validation_error`, `false` → 422 `consent_required`; the decision is logged as a hash with the request id only (reuses `bazi_engine.match.privacy.log_consent_decision`). | Ben, 2026-11-08 |
| D5 | `date`, `tz`, `lon`, `lat` are **required** per person (no silent Europe/Berlin default as on `/calculate/western` — a silently defaulted second person would produce a wrong pair without an error). `extra="forbid"` on every request model: `zodiac_mode` is rejected, synastry is tropical only. | Plan: fail-visible rule (CLAUDE.md Development Principles) |
| D6 | House overlays cover the ten planets only (spec step 4 says "Planeten"); ASC/MC of the guest are not placed in the host's houses. A gated row is `{factor, house: null, status: "unavailable_missing_time"}`; an open row is `{factor, house: 1..12, status: "ok"}`. | Spec step 4 wording |
| D7 | Aspects are emitted once, from person_a to person_b, for the full cross matrix (every A factor × every B factor). Order: A factor order, then B factor order (`Sun … Pluto, Ascendant, MC`). `orb` is rounded to 4 decimals first; inclusion and `exact` are decided on that rounded orb, so the response is self-consistent (amended after final review). | Spec step 3 |
| D8 | Sign names are the German names the API already emits (`routers/shared.ZODIAC_SIGNS_DE`, copied as a literal into the Level-4 package and pinned equal by a test); `west_element` uses the existing `SIGN_ELEMENT` values `Feuer/Erde/Luft/Wasser`. `sign_relation ∈ {same_sign, semi_sextile, sextile, square, trine, quincunx, opposition}`, `element_relation ∈ {same, complementary, other}` (complementary = Feuer–Luft or Erde–Wasser). | Repo convention |
| D9 | `provenance.warnings[]` = `{code, person, detail}` with codes `birth_time_unknown` (Moon position then rests on the supplied clock time) and `house_system_fallback`. Warning text never carries coordinates (the western chart's own fallback reason contains the latitude and is not copied). | Privacy rule |
| D10 | The response carries no computation timestamp (the shared `build_provenance` adds one; it is not used), so two identical requests return byte-identical bodies. | Spec: determinism |
| D11 | `subjects.person_x = {display_label, birth_time_known}` echoes the label in the response (it exists so the caller can label the pair) — it never reaches a log line. `display_label`: max 40 characters, letters with single inner separators (space, `.`, `'`, `-`), no digits or `@`. | Spec: label optional, never logged |
| D12 | A `date` without a time part is rejected (422 `validation_error`, value not echoed) when `birth_time_known` is true; with `birth_time_known: false` it is accepted. | Final review: fail-visible rule, same reason as D5 |
