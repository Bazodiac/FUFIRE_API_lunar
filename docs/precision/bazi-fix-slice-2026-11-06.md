# FuFirE BaZi Fix – Teilumsetzung / Freigabestatus

**Datum:** 2026-11-06  
**Eingang:** Nutzer-ZIP `FUFIRE_API_lunar-master (4).zip`, isolierte Kopie  
**Status:** `PARTIAL_IMPLEMENTATION / NOT_RELEASED`  
**WIP:** 1 (BaZi-Natal-Fakten und unabhängige Tageskalibrierungsprüfung)

## Was tatsächlich geändert wurde

1. `bazi_engine/match/natal_facts.py` (NEU): rein deterministische Auflistung verborgener Stämme, die dem Day-Master-Stamm exakt entsprechen bzw. zur gleichen Wu-Xing-Phase gehören, aber ein anderer Stamm sind. Sichtbare Stämme werden nicht als verborgen ausgegeben. Bei unbekannter Geburtszeit gelten Einträge der Stundensäule als vorläufig. Ein falsches Stammes-/Phasenelement im Input löst einen Fehler aus.
2. `bazi_engine/routers/natal.py`: additiver JSON-Baustein `hidden_stem_affinities` im Natal-Endpunkt. **Wichtig:** `tong_gen_assessment` bleibt `NEEDS_DOMAIN_REVIEW`, `blocked_by: MISSING-003`. Es erfolgt ausdrücklich keine Tong-Gen-, Day-Master-Stärke- oder Yong-Shen-Interpretation.
3. `schemas/calculate/bazi/natal.response.schema.json` und `spec/openapi/openapi.json`: Struktur des neuen Feldes aufgenommen. **OpenAPI nur als struktureller Snapshot aktualisiert; Generierungsparität konnte wegen fehlender Abhängigkeit nicht geprüft werden.**
4. Neue Unit- und strukturelle Tests sowie 2 zusätzliche HTTP-Regressionstests (HTTP-Tests konnten lokal nicht importiert werden).
5. 6 von veröffentlichten Kalenderseiten abgelesene, mit URL belegte sexagenäre Tagesdaten als getrennte externe Prüffälle: 1912-02-18 甲子, 1949-10-01 甲子, 1984-02-02 丙寅, 2000-01-01 戊午, 2024-02-10 甲辰, 2026-11-06 甲申. Sie stimmen für die Zivildatums-Berechnung mit `(JDN + 49) % 60` überein. **Externe Almanach-Korroboration ist keine formale Fachfreigabe.**

## Tagesanker – Befund und Quellen

Der ursprüngliche Ruleset-Anker `anchor_jdn=2419451`, `anchor_sexagenary_index_0based=0` und der Konstantenwert `DAY_OFFSET=49` sind rechnerisch konsistent; die sechs externen Fälle stützen den Offset. Der Status `anchor_verification="unverified"` bleibt unverändert. Datumskonventionen für Tageswechsel um 23 Uhr, wahre Sonnenzeit und Grenzfälle benötigen eigene freigegebene Oracles. Es ist **kein** bestätigter Konstantenfehler festgestellt worden.

- 1912-02-18: https://www.rili.com.cn/wannianli/1912/0218.html ; https://www.nongli.info/huangli/days/index.php?date=18&month=2&year=1912
- 1949-10-01: https://www.chinesecalendaronline.com/zh/1949/10/1.htm ; https://www.rili.com.cn/wannianli/1949/1001.html
- 1984-02-02: https://www.calend.jp/1984/02/02
- 2000-01-01: https://www.rili.com.cn/wannianli/2000/0101.html
- 2024-02-10: https://www.calc-site.com/search_dates/2/10/2024
- 2026-11-06: https://nihonkoyomi.com/2026/11/6/ ; https://tianji.hurricanesoft.com.tw/huangli/2026-11-06

**Quellenkritik:** Diese Websites können gemeinsame Kalenderdaten oder Algorithmen verwenden. Sie sind nicht mit einer historisch-edierten, unabhängig datierten Primärquelle gleichzusetzen. Die Testfälle enthalten zunächst ausschließlich Tagzyklen ohne schwierige Zonen-/Sonnenzeitgrenzen.

## Testnachweise (isolierte Umgebung)

- `EPHEMERIS_MODE=MOSEPH python -m pytest --noconftest -q` auf 11 ausgewählten Testmodulen: **172 PASS, 1 SKIP**. Die Skip-Ursache ist die fehlende Swiss-Ephemeris-SE1-Datei. Vollständiger Befehl und Ausgabe: `qa/passing_core_tests.log` im begleitenden Patch-Paket.
- Zusätzliche Strukturprüfung: JSON Schema Draft 2020-12 valide, versioniertes OpenAPI-Dokument enthält das neue Feld, Kompilierung der geänderten Python-Dateien erfolgreich.
- Echter HTTP-Test `tests/test_natal_endpoint.py`: **BLOCKED at collection**, `ModuleNotFoundError: slowapi`, nicht bestanden/nicht fehlgeschlagen. Protokoll im Paket.
- `python scripts/export_openapi.py --check`: **BLOCKED**, derselbe fehlende Import. Die Schema-/OpenAPI-Parität ist deshalb nur strukturell, nicht durch offiziellen Generator bestätigt.
- `python -m pip install --target ... slowapi redis`: **BLOCKED** durch fehlenden Paketindex-/Netzwerkzugang, kein autorisierter Abkürzungs-Fallback.
- Host ist **Python 3.13.5**, während `pyproject.toml` **`>=3.10,<3.13`** fordert. Test-PASS unter dieser Umgebung ist kein unterstützter Release-Nachweis.
- **Keine SWIEPH-Neuberechnung**, keine Live-API, keine vollständige Testsuite, kein Merge/Deploy.

## Noch ausstehend – zwingende Freigabesperren

| Gate | Offen | Nächster fachlich zulässiger Schritt |
|---|---|---|
| Kalenderanker | Fachlich genehmigte autoritative Referenz, 23-Uhr-/TLST-Grenzen | Primär-/autoritative Almanachquelle mit Ausgabedatum und konkreten Grenzfällen; abgleichen, dann Review |
| Klassische saisonale Stärke | Benanntes Zi-Ping-Auslegungssystem mit tabellierten Wang/Xiang/Xiu/Qiu/Si-Definitionen | Versionierte Quellen-/Regelmatrix; keine freie Ableitung aus fünf Summen |
| Tong Gen / DMS | Klassische Bewertung der Verwurzelung, Stärke und Sonderfälle | Auf den jetzt vorhandenen reinen Vorkommensdaten aufbauen, Grenzfälle + Fach-Oracle definieren |
| Yong Shen | Schulgebundene (u.a. 格局 vs. 旺衰) Auswahl- und Ausnahmevorschriften | Explizit die Deutungsschule wählen; keine universelle numerische Formel behaupten |
| Integration/Release | Unterstützte Python-Version, reale Abhängigkeiten, `SWIEPH`-Daten und HTTP-/OpenAPI-/Regressionstests | In Python 3.10–3.12 reprovisionieren; offizielle Generator- und HTTP-Tests ausführen |

**Freigabeentscheidung:** Der Patch kann als Review-Vorlage genutzt werden. Er stellt **keine vollständige klassische BaZi-Berechnung** bereit. `MISSING-003` und `anchor_verification="unverified"` wurden nicht irreführend geschlossen. API-Contract-Review, Laufzeitverifikation und Quellenfreigabe sind vor Merge und Produktion erforderlich.
