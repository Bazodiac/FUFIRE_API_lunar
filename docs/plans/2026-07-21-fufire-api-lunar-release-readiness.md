# FUFIRE_API_lunar Release-Ready Integration Implementation Plan

Plan path: `docs/plans/2026-07-21-fufire-api-lunar-release-readiness.md`  
Status: in-execution (release blocked)  
Owner/Executor: mixed (backend, platform, QA, security, product/domain reviewer)  
Last updated: 2026-07-21

<!-- GOAL_START -->
Goal: FUFIRE_API_lunar als überprüfbaren Production Release Candidate integrieren

Ziel. Der Live-Stand `DYAI2025/FUFIRE_API_lunar` wird so integriert, dass Branch- und Release-Automation, vollständige Tests, OpenAPI/Mock-Verträge, Ephemeriden, Auth/Rate-Limits, Docker/Railway-Readiness sowie Staging-Promotion und Rollback eine zusammenhängende Freigabekette bilden. Der Lunar-V2-Endpunkt wird mit realen, gepinnten SWIEPH-Daten und fachlich definierten Toleranzen verifiziert. Die aktuelle Releaseentscheidung bleibt BLOCKED, bis alle P0-Gates und die für den gewählten Scope relevanten Conditional Gates geschlossen sind.

Scope. Zielbranch ist `main`; betroffen sind `.github/workflows/*`, Release-Metadaten, `config/claude/lib/gate_contracts.py`, Python-Package-Resources und Wheel/sdist-Smokes, Ephemeris-Lock/Fetch, Dockerfiles, Runtime-Readiness/Auth/Limiter, Mock/OpenAPI, Lunar-V2-Tests, Railway-Dokumentation und Release-Evidence. Bestehende Legacy-/V1-Verträge bleiben kompatibel; V2 bleibt additiv.

Bedingungen (hart).
- Keine erfundene Historie, kein stiller Snapshot-Refresh und kein mutable Ephemeris-Fallback im Release-Gate.
- Kein Production-Promote ohne grünen atomaren `release-gate`, SWIEPH-Evidenz, Auth-/Readiness-Smoke und rollbackfähige Build-Identität.
- release-please-Bot-PRs durchlaufen dieselben Required Checks wie normale PRs.
- Das getestete Wheel/sdist enthält alle Runtime-Schemas, Rulesets und Daten und ist ohne Source-Checkout importierbar.
- Fachlich bedingte Flächen (ZWDS, Key-Issuance, MOSEPH, Multi-Replica-Rate-Limits) werden explizit freigegeben oder deaktiviert.

Akzeptanzkriterien.
- `main` ist Default-Branch; CI und release-please laufen auf PR/Push; Head besitzt einen grünen Required Check `release-gate`.
- pytest sammelt vollständig; Python 3.10/3.11/3.12, Ruff, Mypy, Complexity, Security, Docker und Codegen sind grün.
- Ein Clean-Install aus Wheel und sdist kann Paket, App, BAFE, ZWDS, Affinity und OpenAPI ohne Repository-Root laden.
- CI und Docker verwenden denselben geprüften Ephemeris-Lock; Release-CI schreibt keine Snapshots.
- `/ready` liefert 503 bei Ephemeris- oder required-Redis-Degradation; Railway prüft `/ready`.
- Production-Profil startet ohne Auth-Konfiguration nicht; gültige/ungültige Keys und CORS-Policy sind im Staging bewiesen.
- Lunar-V2 besteht SWIEPH-Referenz-, Grenz- und Contract-Tests; Precision- und Datumsbereich sind ehrlich spezifiziert.
- Release-PR erzeugt die genehmigte Version; Staging und Production lassen sich auf Commit/Build zurückführen; Rollback ist geprobt.

Explizit out-of-scope.
- Kein Re-Write der BaZi-/Western-/Fusion-Domänen.
- Keine neue astrologische Interpretation oder Produktfunktion außerhalb der Releasekorrekturen.
- Keine PyPI-Veröffentlichung; der interne Wheel/sdist-Distribution-Contract und Clean-Install-Smoke bleiben dennoch Pflicht.
- Kein persistenter KeyStore, falls Runtime-Key-Issuance für diesen Release deaktiviert wird.
- Keine rückwirkend erfundene Git-Historie.

Done-Definition. Ein genehmigter Release-PR und ein immutable identifizierbarer Release Candidate erfüllen alle verpflichtenden Gates; Staging-Smoke, Performance-Baseline, Promotion und Rollback sind mit Commit-/Deployment-ID dokumentiert. `05_VERIFICATION_REPORT.md` kann danach von BLOCKED auf RELEASE geändert werden.

Reference-Doc: `01_RELEASE_BLOCKER_AUDIT.md`, `02_ARCHITECTURAL_DEPENDENCY_MAP.md`
<!-- GOAL_END -->

## Evidence and source boundary

- **Provided evidence:** hochgeladener Lunar-ZIP-Snapshot; vorheriger FuFirE-main-Vergleichsstand; Repository-Dokumentation, Tests, Workflows und OpenAPI.
- **Inspected evidence:** Live-GitHub-Metadaten/Dateien, 134 Python-Module, 77 Runtime-Routen, 72 OpenAPI-Operationen, lokale Test-/Static-Check-Ausgaben und Blocker-Reproduktionen.
- **Inspected legal evidence:** Projektlizenz (`LICENSE`: MIT), README-Claim (`Proprietary`), installierte `pyswisseph`-Metadaten (AGPLv3-Classifier) und die offizielle Swiss-Ephemeris-Lizenzseite von Astrodienst.
- **Not inspected / unavailable:** Railway-Projektsettings und Secrets, Branch Protection, Docker-Runtime lokal, SE1-Dateien lokal, Bandit/pip-audit lokal, Produktionslogs/-metriken, fachlicher ZWDS-Sign-off.

## Assumptions, missing information, open questions, blockers

### ASSUMPTION

- Zielversion ist **1.6.0**, weil 1.5.0 als Wu-Xing-Baseline rekonstruiert und Lunar-V2 additiv ist. Product Owner bestätigt dies in TASK-005.
- `main` soll kanonischer Default-Branch werden; diese Wahl minimiert Repository-Änderungen, weil Workflows und Dokumentation bereits `main` erwarten.
- Produktion ist SWIEPH-only; MOSEPH bleibt Development/Test, solange kein eigener Fallback-Produktvertrag beschlossen wird.
- Runtime-Key-Issuance ist nicht erforderlich; statische, sicher verwaltete API-Keys reichen für den ersten Release.

### MISSING

- Aktuelle Railway Service-/Environment-Konfiguration, Replika-Anzahl und Redis-Vertrag.
- Branch-Protection-Regeln und verfügbare GitHub-App/PAT-Infrastruktur.
- Genehmigte Performance-Schwellen und Rollback-Zeit.
- Autoritative Referenzquelle/Toleranzen für alle Lunar-Hauptereignisse.
- Rechtsverbindlicher Nachweis einer Swiss-Ephemeris-Professional-Lizenz oder eine genehmigte AGPL-kompatible Gesamtfreigabe.

### OPEN QUESTION

- Muss ZWDS im Zielrelease öffentlich bleiben, obwohl GATE-1 noch pending ist?
- Muss `/v1/admin/keys` produktiv aktiv sein?
- Ist die öffentliche BaZi-Hehun-Landingpage/Marketingfreigabe Teil dieses Releases?
- Kann Railway denselben Build/dieselbe Deployment-Identität von Staging nach Production promoten, oder wird commit-identische Neu-Build-Evidenz benötigt?

### BLOCKER

- Alle P0-Befunde RB-001 bis RB-011, RB-014, RB-016 und RB-017.
- RB-012, RB-013 und RB-015 vor Production Promotion.
- RB-C01 bis RB-C05, sobald der betreffende Scope aktiviert wird.

## Requirements

| ID | Type | Statement | Source | Verification |
|---|---|---|---|---|
| REQ-A-001 | architecture | Ein kanonischer Default-/Release-Branch steuert CI, release-please und Deployment. | RB-001 | GitHub metadata + Test-PR |
| REQ-NF-001 | non-functional | Ein atomarer Required Check `release-gate` aggregiert alle Pflichtjobs. | RB-005 | Failure injection + branch protection review |
| REQ-F-001 | functional | pytest collection und vollständige Matrix laufen ohne fehlende Dateien. | RB-002 | collect-only + full matrix |
| REQ-A-002 | architecture | Release-Baseline, Manifest, Changelog, Bootstrap-SHA und Tagziel sind konsistent. | RB-003 | release-please test PR |
| REQ-S-001 | security | release-please-PRs erreichen mit minimal privilegierter Identität oder auditiertem Approval dieselben Required Checks wie normale PRs. | RB-004 | Bot PR carries required checks |
| REQ-D-001 | data | Eine Ephemeris-Lockdatei ist alleinige Autorität für Commit, Dateien und Hashes. | RB-006 | tamper tests + CI/Docker parity |
| REQ-NF-002 | non-functional | Release-CI ist snapshot-read-only; Updates erfolgen separat und reviewpflichtig. | RB-007 | delete snapshot -> gate fails |
| REQ-O-001 | observability | Railway nutzt `/ready`; jede kritische Dependency-Degradation liefert 503. | RB-008/RB-009 | dependency outage tests |
| REQ-S-002 | security | Production startet nur mit explizitem Auth-/CORS-/Secret-Profil. | RB-010 | container/staging negative tests |
| REQ-F-002 | functional | Mock und OpenAPI decken alle bewusst unterstützten Integrationspfade ab. | RB-011 | mock contract suite |
| REQ-A-004 | architecture | Wheel und sdist enthalten alle Runtime-Ressourcen und funktionieren ohne Source-Checkout. | RB-016 | clean-install resource smoke |
| REQ-F-003 | functional | Lunar-V2 liefert SWIEPH-verifizierte Werte innerhalb genehmigter Toleranzen. | RB-012 | reference corpus |
| REQ-NF-003 | non-functional | Build- und Codegen-Inputs sind versions-/digestgepinnt und auditierbar. | RB-013 | tool version + SBOM checks |
| REQ-O-002 | observability | Release Candidate, Staging und Production sind auf Commit/Build/Deployment-ID rückführbar. | RB-014 | /build + artifact ledger |
| REQ-NF-004 | non-functional | Staging erfüllt genehmigte Latenz-, Fehler- und Ressourcen-Schwellen. | RB-015 | load report |
| REQ-S-003 | security | Runtime-Key-Issuance ist deaktiviert oder persistent/restartfest. | RB-C01 | 503 policy or persistence tests |
| REQ-S-004 | legal/security | Vor Distribution oder öffentlicher Serviceaktivierung ist die Swiss-Ephemeris-Lizenzwahl belegt und mit Repository-/Artefaktlizenzen konsistent. | RB-017 | Legal approval + license artifact inventory |
| REQ-A-003 | architecture | Multi-Replica-Produktion nutzt global konsistente Rate-Limit-Storage. | RB-C02 | cross-replica quota test |
| REQ-DOC-001 | documentation | ZWDS-, MOSEPH-, BaZi-Hehun-Public-Launch- und Release-Scope sind explizit entschieden. | RB-C03/RB-C04/RB-C05 | ADR/feature matrix |

### Zentrale Given/When/Then-Akzeptanzszenarien

1. **Release-PR:** Given ein von release-please geöffneter PR, when der PR erstellt oder aktualisiert wird, then laufen alle Pflichtjobs und genau der atomare `release-gate` blockiert oder erlaubt den Merge.
2. **Distribution:** Given ein frisch gebautes Wheel oder sdist in einer leeren Umgebung ohne Repository-Checkout, when Paket, App, BAFE, ZWDS, Affinity und OpenAPI geladen werden, then sind alle genehmigten Runtime-Ressourcen verfügbar und kein Pfad verlässt das installierte Paket.
3. **Readiness:** Given eine als required konfigurierte Ephemeris- oder Redis-Abhängigkeit ist degraded/unavailable, when `/ready` aufgerufen wird, then antwortet der Dienst mit 503, while `/health` als Liveness 200 liefern darf.
4. **Production Auth:** Given `FUFIRE_ENV=production` und keine gültige Auth-Quelle, when der Prozess startet, then bricht der Start fail-closed ab; given gültige Konfiguration, then no/invalid key wird abgewiesen und valid key akzeptiert.
5. **Lunar-V2:** Given ein genehmigter SWIEPH-Referenzvektor innerhalb des unterstützten Datumsbereichs, when `/v2/astronomy/lunar-state` aufgerufen wird, then liegen alle geprüften Werte innerhalb der dokumentierten Toleranzen und Response-Provenance nennt den erwarteten Provider/Lock.

## Architecture and file boundaries

### Current architecture facts

- `bazi_engine.app` ist dünner Composition Root.
- `routers.registry` montiert Legacy, V1, V2 und Internal in definierter Reihenfolge.
- Lunar-V2 ist auf `/v2/astronomy/lunar-state` beschränkt.
- `limiter` ist ein hochzentraler Querschnitt; Änderungen benötigen breite Tests.
- `ephemeris` ist Daten- und Attestationsgrenze für mehrere Domänen.
- Mehrere Loader verlassen heute das installierte Paket in Richtung `spec/`; Package Data enthält die benötigten JSON-Ressourcen nicht.

### Target architecture constraints

1. Control Plane und Runtime Plane bleiben getrennt.
2. Ephemeris-Lock ist unveränderliche Input-Autorität; Runtime lädt keine Dateien nach.
3. Liveness (`/health`) und Readiness (`/ready`) haben unterschiedliche Semantik.
4. Production-Konfiguration ist fail-closed.
5. Release baut/identifiziert genau den getesteten Commit.
6. Legacy-/V1-Verträge werden nicht opportunistisch umgebaut.
7. Alle Runtime-Ressourcen werden paketintern über `importlib.resources` aufgelöst; keine Repository-Root-Abhängigkeit bleibt im installierten Artefakt.

### Files and modules

- Governance: `.github/workflows/*.yml`, `release-please-config.json`, `.release-please-manifest.json`, `CHANGELOG.md`, `pyproject.toml`.
- Missing gate: `config/claude/lib/gate_contracts.py`, `tests/test_gate_contracts.py`.
- Distribution/Resources: `pyproject.toml`, `bazi_engine/bafe/service.py`, `bazi_engine/bafe/ruleset_loader.py`, `bazi_engine/openapi_ext.py`, `bazi_engine/routers/zwds.py`, `bazi_engine/zwds/ruleset_repository.py`, `bazi_engine/services/quiz_affinity.py`, paketinterne Resource-Verzeichnisse, Wheel/sdist-Smokes.
- Ephemeris: `ephemeris.lock.json` (neu), `scripts/fetch_ephemeris.py` (neu), `Dockerfile`, `Dockerfile.ephe-base`, `bazi_engine/ephemeris.py`, Snapshot-/Attestationstests.
- Runtime: `bazi_engine/limiter.py`, `bazi_engine/routers/info.py`, `bazi_engine/config_guard.py`, `bazi_engine/auth.py`, `bazi_engine/app.py`, `railway.toml`, `docs/railway.md`.
- Contracts: `tests/mock_server.py`, `tests/test_mock_contract.py`, `spec/openapi/openapi.json`.
- Lunar: `bazi_engine/lunar_state.py`, `bazi_engine/routers/astronomy.py`, Lunar-Tests und Referenzfixtures.

### Prohibited changes

- Keine Legacy-Route entfernen oder Antwortfelder ändern ohne separaten Kompatibilitätsplan.
- Keine Snapshots in der Release-CI aktualisieren.
- Keine Secrets in Repository, Logs oder Artefakte schreiben.
- Keine Releaseversion direkt „zurechtbiegen“, ohne Bootstrap-/release-please-Vertrag.
- Keine wissenschaftliche Genauigkeitsbehauptung ohne Referenz und Toleranz.

## Implementation phases

### Phase 1: Control-Plane und Testbaseline

Branch, Required Gates, Gate-Datei und release-please-Bootstrap reparieren.

### Phase 2: Deterministische Daten- und Buildbasis

Package-Resource-Grenze, Clean-Install-Artefakt, Ephemeris-Lock, Snapshot-Policy, Toolchain- und Containerinputs stabilisieren.

### Phase 3: Runtime-Safety und Contracts

Readiness, Redis/Auth/CORS, Mock/OpenAPI und bedingte Flächen schließen.

### Phase 4: Lunar-Fachverifikation

SWIEPH-Referenzkorpus, Precision-/Range-Vertrag und Edge-/Property-Tests.

### Phase 5: Release Candidate, Staging und Promotion

Vollständige Matrix, Artefaktidentität, Smoke, Last, Approval und Rollback.

## Tasks

### TASK-001: Evidence-Baseline einfrieren und Integration-Branch anlegen

**Objective:** Reproduzierbaren Startpunkt und unveränderliches Evidence Ledger schaffen.  
**Requirements:** REQ-A-001, REQ-NF-001.  
**Scope:** GitHub metadata, `evidence/`, `docs/plans/`, keine Produktlogik.

**TDD/Steps:**
1. Head-SHA, Branches, Tags, Workflow Runs, Branch Protection und Railway-Source-Branch exportieren.
2. Prüftest/Script schreiben, das erwarteten Head und alle P0-IDs im Plan findet; zunächst gegen fehlende Artefakte rot laufen lassen.
3. `release/readiness-integration` vom Live-Head erstellen.
4. Evidence Ledger und Plan committen.

**Acceptance:** Head und externe Konfiguration sind datiert dokumentiert; keine unklare Baseline.  
**Validation:** `git status --short`; `git rev-parse HEAD`; Artifact validator.  
**Rollback:** Branch löschen; Default-Branch unverändert lassen.

### TASK-002: Default-Branch kontrolliert auf `main` normalisieren

**Objective:** Branch-Wiring aller Delivery-Systeme vereinheitlichen.  
**Requirements:** REQ-A-001.  
**Scope:** GitHub settings, README/CLAUDE/SDLC, Railway source branch.

**TDD/Steps:**
1. Vor Änderung einen Workflow-Dispatch-Test definieren, der auf aktuellem Zustand fehlende `main`-Erreichbarkeit zeigt.
2. Default-Branch `master` → `main` umbenennen; Redirect belassen.
3. Repository-Dokumente und externe Integrationen auf `main` prüfen.
4. Test-PR erstellen und Push-/PR-Events beobachten.

**Acceptance:** `main` ist Default; CI und release-please laufen; kein aktiver Consumer zeigt auf `master`.  
**Validation:** GitHub branch metadata, workflow run IDs, Railway staging build commit.  
**Rollback:** Default-Branch zurücksetzen und Workflows temporär auf `master` retargeten.

**Status 2026-10-18:** Phase A (CI `workflow_dispatch`, getesteter Branch-Wiring-Vertrag, Runbook) als PR; Schritt 1 rot belegt (Dispatch auf `main` abgelehnt). Phasen B/C und der Blocker `RELEASE_PLEASE_TOKEN` siehe `docs/runbooks/default-branch-migration.md`.

### TASK-003: Atomaren `release-gate` und Branch Protection einführen

**Objective:** Eine einzige verpflichtende Freigabe über alle CI-Jobs.  
**Requirements:** REQ-NF-001.  
**Scope:** `.github/workflows/ci.yml` oder neue `release-gate.yml`, GitHub ruleset.

**TDD/Steps:**
1. Failure-Injection-PR erstellen: ein ungefährlicher Job schlägt kontrolliert fehl; aktuell darf kein falsches Grün möglich sein.
2. `release-gate` mit `needs` auf test, typecheck, lint, complexity, security, docker-build, codegen, contract-artifact implementieren; `if: always()` und explizite Resultprüfung.
3. Ruleset: PR, Review, conversation resolution, no force push, Required Check `release-gate`.
4. Failure Injection wiederholen; danach vollständig grünen PR ausführen.

**Acceptance:** Jeder Pflichtjob ist transitiv required; skipped/failed blockiert Merge.  
**Validation:** GitHub Check Suite + Ruleset Export.  
**Rollback:** Ruleset auf vorherigen Export zurück; Workflow-Revert.

### TASK-004: `gate_contracts.py` aus der verifizierten Baseline wiederherstellen

**Objective:** Vollständige pytest-Collection herstellen.  
**Requirements:** REQ-F-001.  
**Scope:** `config/claude/lib/gate_contracts.py`, `tests/test_gate_contracts.py`.

**TDD/Steps:**
1. Bestehenden Collect-Lauf rot dokumentieren.
2. Datei aus dem bereitgestellten 1.5.0-Stand übernehmen; SHA und Herkunft in PR beschreiben.
3. Fokustest, Collect-only und breitere Tests ausführen.

**Acceptance:** kein Collection-Fehler; 3 Gate-Tests grün.  
**Validation:** `python -m pytest --collect-only -q`; `pytest tests/test_gate_contracts.py -q`.  
**Rollback:** Commit revert; Release bleibt blockiert.

### TASK-005: Release-Baseline und Versionsziel entscheiden

**Objective:** Historisch korrekte Paketbaseline ohne erfundene Git-Historie.  
**Requirements:** REQ-A-002.  
**Scope:** `CHANGELOG.md`, `.release-please-manifest.json`, Decision Record.

**TDD/Steps:**
1. Contract-Test schreiben, der 1.5.0-Baseline im Manifest/Changelog und erreichbaren Bootstrap fordert.
2. Product Owner bestätigt Zielversion; Standardvorschlag 1.6.0.
3. 1.5.0-Changelog-Eintrag aus kanonischem Stand übernehmen, Herkunftsrepo transparent lassen.
4. Bootstrap-Commit erstellen; dessen SHA als Bootstrap-Marker verwenden oder nach erfolgreicher erster Release-PR entfernen.
5. Einmaligen `Release-As: 1.6.0`-Mechanismus für den Lunar-Release festlegen.

**Acceptance:** keine Versionsregression; Zielrelease eindeutig.  
**Validation:** release-please auf Testbranch erzeugt genau erwartete Diff/Version.  
**Rollback:** Bootstrap-PR vor Merge schließen; keine Tags löschen.

### TASK-006: release-please-Botidentität und PR-CI schließen

**Objective:** Bot-PRs durchlaufen normale Required Checks.  
**Requirements:** REQ-S-001, REQ-A-002.  
**Scope:** `.github/workflows/release-please.yml`, GitHub App/PAT secret oder dokumentierter Approval-Pfad.

**TDD/Steps:**
1. Testworkflow dokumentiert das tatsächliche Default-GITHUB_TOKEN-Verhalten: kein Lauf, approval-required oder automatisch.
2. Für unbeaufsichtigte CI eine minimal berechtigte GitHub App bevorzugen; alternativ fein granularen PAT mit Rotation oder einen expliziten manuellen Approval-Pfad wählen.
3. Gewählte Identität explizit an release-please übergeben beziehungsweise Approval-Schritt dokumentieren; Permissions reduzieren.
4. Test-Release-PR erzeugen und Required Checks prüfen.

**Acceptance:** release-please-PR erreicht ohne stillen Bypass den verpflichtenden `release-gate`; notwendige Approval-Schritte sind dokumentiert; Secret erscheint nirgends.  
**Validation:** Check Run IDs, audit log, secret scan.  
**Rollback:** Bot-Token widerrufen; Release-Workflow deaktivieren.

### TASK-007: Kanonischen Ephemeris-Lock und Verifier einführen

**Objective:** Eine Datenautorität für CI, Docker und Runtime.  
**Requirements:** REQ-D-001.  
**Scope:** neues `ephemeris.lock.json`, neues `scripts/fetch_ephemeris.py`, Tests.

**TDD/Steps:**
1. Tests für falschen Commit, fehlende Datei, falsche Größe/Hash und HTML-Payload rot schreiben.
2. Lock mit approved upstream commit, vier Dateinamen, Größen und SHA256 erstellen.
3. Deterministisches Fetch/Verify-Script ohne Fallback implementieren.
4. Lock-ID/Hash als Provenance-Metadatum verfügbar machen.

**Acceptance:** jede Abweichung blockiert; korrekter Satz wird einmalig verifiziert.  
**Validation:** Unit tests + offline fixture tests + SWIEPH runner.  
**Rollback:** vorherige Docker/CI-Logik wiederherstellen, Release blockiert lassen.

### TASK-008: CI, Docker und Ephemeris-Base auf denselben Lock migrieren

**Objective:** Datenparität über Buildgrenzen.  
**Requirements:** REQ-D-001, REQ-NF-003.  
**Scope:** `.github/workflows/ci.yml`, `Dockerfile`, `Dockerfile.ephe-base`, `build-ephe-base.yml`.

**TDD/Steps:**
1. Paritätstest schreibt die von allen Pfaden verwendete Lock-ID aus und schlägt aktuell rot fehl.
2. CI und Docker rufen denselben Verifier auf.
3. `master`-Fallback entfernen; Cache-Key auf Lock-Hash setzen.
4. Base-Image-Workflow entweder entfernen oder immutable per Digest konsumieren; `latest` nicht als Releaseinput verwenden.

**Acceptance:** CI-/Docker-/Runtime-Lock-ID identisch.  
**Validation:** Clean CI build, tamper build, runtime `/build`/attestation.  
**Rollback:** Workflow-Revert; kein Production Promote.

### TASK-009: Snapshot-Orakel read-only machen und MOSEPH-Policy schließen

**Objective:** Expected Results dürfen nicht im Release-Gate entstehen.  
**Requirements:** REQ-NF-002, REQ-DOC-001.  
**Scope:** CI snapshot step, snapshot update script/workflow, MOSEPH snapshots.

**TDD/Steps:**
1. Snapshot in Testbranch löschen; Release-CI muss rot sein.
2. Auto-Generate-Step aus Release-CI entfernen.
3. Separaten manual workflow erzeugen: lock-bound, diff artifact, mandatory review.
4. MOSEPH als dev/test-only dokumentieren oder dessen Snapshots kontrolliert aktualisieren und Security-Testprofil trennen.

**Acceptance:** fehlende/driftende Snapshots blockieren; Updates sind eigenständige Review-PRs.  
**Validation:** negative deletion test + update workflow artifact.  
**Rollback:** Snapshot-Update-PR schließen; keine Expected-Daten mergen.

### TASK-010: Readiness- und Rate-Limiter-Semantik korrigieren

**Objective:** Traffic nur bei funktionsfähigen kritischen Dependencies.  
**Requirements:** REQ-O-001.  
**Scope:** `bazi_engine/routers/info.py`, `bazi_engine/limiter.py`, `railway.toml`, Tests.

**TDD/Steps:**
1. Tests rot: configured Redis returns degraded -> `/ready` muss 503; missing ephemeris -> 503; `/health` bleibt 200 liveness.
2. Dependency-Policy zentralisieren (`ok` vs `degraded/unavailable`).
3. `/ready` auf alle required Dependencies anwenden.
4. Railway `healthcheckPath=/ready` setzen.

**Acceptance:** degradierte Pflichtdependency = 503; gesunder Zustand = 200.  
**Validation:** focused pytest + built-container smoke.  
**Rollback:** Railway probe auf vorherigen Wert nur bei gleichzeitigem Traffic-Stopp; Code-Revert.

### TASK-011: Produktionsprofil für Auth, CORS, Secrets und Redis erzwingen

**Objective:** Fehlkonfiguration blockiert Start/Promotion.  
**Requirements:** REQ-S-002, REQ-A-003.  
**Scope:** config guard, deployment preflight, Railway variables/docs.

**TDD/Steps:**
1. Negative Container-/App-Tests für fehlendes FUFIRE_ENV, Keys, CORS und required Redis schreiben.
2. `FUFIRE_ENV=production`, `FUFIRE_REQUIRE_API_KEYS=true`, explizite CORS-Allowlist als Pflichtprofil definieren.
3. Multi-Replica: Redis required; Single-Replica: harte documented invariant.
4. Secrets rotieren und redaction/log tests ausführen.

**Acceptance:** kein dev-mode in Production; no/invalid key blockiert; valid key funktioniert; CORS nur genehmigte Origins; Rate-Limits global konsistent.  
**Validation:** staging negative/positive smoke, log scan.  
**Rollback:** vorheriges Deployment reaktivieren; neue Secrets widerrufen.

### TASK-012: Mock-/OpenAPI-Vertrag reparieren

**Objective:** Integrationsmock entspricht bewusst unterstützter API-Oberfläche.  
**Requirements:** REQ-F-002.  
**Scope:** `tests/mock_server.py`, `tests/test_mock_contract.py`, OpenAPI.

**TDD/Steps:**
1. Bestehenden roten Test konservieren.
2. `/calculate/bazi/wuxing` und `/v1`-Mirror ergänzen oder begründete Exclusion definieren.
3. V2-Lunar-Mockentscheidung treffen und Contract-Test erweitern.
4. OpenAPI drift/codegen prüfen.

**Acceptance:** Mock-Suite grün, keine unbegründeten Pfadlücken.  
**Validation:** `pytest tests/test_mock_contract.py -q`; `python scripts/export_openapi.py --check`; codegen.  
**Rollback:** Mock-only Commit revert.

### TASK-013: Python-Distribution und Runtime-Resources selbstständig machen

**Objective:** Wheel, sdist und Runtime-Container laden dieselben vollständigen Ressourcen ohne Source-Checkout.  
**Requirements:** REQ-A-004, REQ-NF-003.  
**Scope:** `pyproject.toml`, BAFE-/ZWDS-/OpenAPI-/Affinity-Loader, paketinterne Resource-Verzeichnisse, Distribution-Smokes, Dockerfile.

**TDD/Steps:**
1. Failing Clean-Install-Tests konservieren: Wheel und sdist in leere Temp-Umgebung installieren; `import bazi_engine`, App-Import, BAFE-Schema-/Ruleset-Laden, ZWDS-Ruleset, Affinity-Map und OpenAPI müssen aktuell rot sein.
2. Inventar aller runtime-notwendigen Dateien erstellen; jede Datei einem fachlichen Package-Resource-Owner zuordnen. Keine pauschale Aufnahme des gesamten `spec/`-Baums.
3. Benötigte Schemas, Rulesets und Daten in stabile paketinterne Resource-Verzeichnisse überführen beziehungsweise als Package Data aufnehmen.
4. Repository-relative `Path(...).parents[...] / "spec"`-Zugriffe durch `importlib.resources.files(...)`/`as_file(...)` oder eine zentrale Resource-Abstraktion ersetzen.
5. Das Build-Frontend als Dev-/Tool-Abhängigkeit versionieren und locken; Wheel und sdist bauen, Inhalt gegen Allowlist prüfen und Clean-Install-Smokes auf Python 3.10/3.11/3.12 ausführen.
6. Docker-Runtime aus dem gebauten Wheel installieren; paralleles `COPY spec/` nur behalten, wenn ein separat dokumentierter Nicht-Runtime-Zweck existiert.
7. Fehlende/korruptierte Resource-Negativtests ergänzen; kein stiller uniform-/default-Fallback für releasekritische Daten.

**Acceptance:** Beide Distributionen enthalten genau die genehmigten Runtime-Ressourcen; alle Clean-Install-Smokes bestehen ohne Source-Checkout; Docker nutzt dasselbe geprüfte Wheel.  
**Validation:** `python -m build --wheel --sdist`; Wheel/sdist inventory; temp-venv install; app/resource/OpenAPI smoke; Docker build/run.  
**Rollback:** Resource-Migrations-PR revertieren; bisheriges Source-Tree-Deployment nur als nicht releasefähigen Fallback markieren.

### TASK-014: Lunar-V2 mit realem SWIEPH fachlich release-gaten

**Objective:** Ehrlicher und stabiler V2-Vertrag.  
**Requirements:** REQ-F-003.  
**Scope:** `lunar_state.py`, `routers/astronomy.py`, Fixtures/Tests, OpenAPI.

**TDD/Steps:**
1. Referenztests rot für Neu-/Vollmond, erstes/letztes Viertel, Phasenübergänge, DST, Zeitzonen, Jahresgrenzen und mehrere Epochen.
2. Toleranzen und Referenzherkunft dokumentieren.
3. `precision_grade` vor Erstveröffentlichung auf `high_precision|degraded` oder providerbezogene Werte ändern.
4. Unterstützten Datumsbereich definieren und validieren.
5. Random/property corpus für Lunationsinvarianten; bracketed fallback nur implementieren, wenn Konvergenztest scheitert.
6. OpenAPI und SDK neu generieren.

**Acceptance:** SWIEPH-Korpus grün; keine `exact`-Überbehauptung; Range-/Error-Vertrag stabil.  
**Validation:** dedicated `@pytest.mark.swieph` suite + OpenAPI/codegen.  
**Rollback:** V2 bleibt unveröffentlicht; keine Legacyänderung.

### TASK-015: Conditional Surfaces per ADR freigeben oder deaktivieren

**Objective:** Keine stillen Scope-Blocker.  
**Requirements:** REQ-S-003, REQ-A-003, REQ-DOC-001.  
**Scope:** Key issuance, ZWDS, MOSEPH, BaZi-Hehun Public Launch, BaZi-Precision-V2-Default und deployment flags.

**TDD/Steps:**
1. Sechs ADR-Entscheidungen als testbare Feature-Matrix formulieren.
2. Empfohlener Minimalpfad: Key-Issuance disabled, Redis required für Multi-Replica, ZWDS feature-gated bis Sign-off, MOSEPH dev/test-only, BaZi-Hehun-Landingpage/Marketing off, kein BaZi-Precision-V2-Default-Switch.
3. Route/OpenAPI/Startup-/Visibility-Tests für jede Entscheidung ergänzen.

**Acceptance:** Jede bedingte Fläche hat Owner, Status, Route-/Deployment-Verhalten und Test.  
**Validation:** feature-matrix test + docs review.  
**Rollback:** Feature flags auf sichere Defaultwerte.

### TASK-016: Toolchain und Container-Supply-Chain härten

**Objective:** Auditierbare, immutable Buildinputs.  
**Requirements:** REQ-NF-003.  
**Scope:** lockfiles, Dockerfile, workflows, Node codegen.

**TDD/Steps:**
1. Versions-Assertion-Script schreiben; aktuell unpinned Inputs melden.
2. Kanonischen Python-Lock wählen (`uv.lock --frozen` oder hash-locked requirements).
3. pip/setuptools/wheel, Redocly, TypeScript und Radon explizit pinnen; Shell-Quoting korrigieren.
4. Container-Base-Images und releasekritische Actions auf Digests/Commit-SHAs pinnen.
5. Runtime-Image non-root; SBOM und Dependency-Report als Artefakte.

**Acceptance:** Clean Build nutzt ausschließlich genehmigte Inputs; SBOM vorhanden; Container läuft non-root.  
**Validation:** version assertion, Docker inspect, SBOM validation, pip-audit/Bandit.  
**Rollback:** Pin-Commit revert; altes Image verfügbar halten.

### TASK-016A: Swiss-Ephemeris-Lizenzgate schließen

**Objective:** Eine rechtlich belegte und artefaktweit konsistente Lizenzbasis vor Distribution oder öffentlicher Serviceaktivierung herstellen.  
**Requirements:** REQ-S-004.  
**Scope:** Swiss Ephemeris/pyswisseph, SE1-Daten, Repository- und Distributionsmetadaten; keine eigenmächtige Lizenzentscheidung durch Engineering.

**TDD/Steps:**
1. Lokale Lizenzclaims, Dependency-Metadaten und offizielle Astrodienst-Lizenzbedingungen in einem prüfbaren Gate-Dokument erfassen.
2. Legal/Product Owner entscheidet zwischen belegter Professional-Lizenz und einer ausdrücklich genehmigten AGPL-kompatiblen Gesamtfreigabe.
3. Gewählte Lizenz in `LICENSE`, README, Package-Metadaten, Container/SBOM und Release-Hinweisen konsistent umsetzen.
4. Lizenznachweis-ID und Geltungsbereich im Evidence Ledger dokumentieren; keine vertraulichen Vertragsinhalte committen.

**Acceptance:** Legal Approval und Lizenznachweis-ID liegen vor; Repository-, Package- und Containerclaims widersprechen sich nicht; der genehmigte Nutzungsumfang umfasst den angebotenen Service.  
**Validation:** Legal review + SBOM/license inventory + Distribution-Inspection.  
**Rollback:** Distribution/Production-Aktivierung stoppen; kein Tag oder Promote.

### TASK-017: Vollständigen Release-Candidate-Gate ausführen

**Objective:** Alle statischen, Test-, Contract- und Buildgates auf unterstützten Runtimes schließen.  
**Requirements:** REQ-F-001, REQ-NF-001, REQ-NF-003, REQ-O-002.  
**Scope:** GitHub CI/Runners, Wheel/sdist, SWIEPH assets, OpenAPI/SDK, Docker image, SBOM und Evidence Bundle.

**Steps:**
1. Python 3.10/3.11/3.12 full pytest mit SWIEPH und Coverage ≥75.
2. Ruff, Mypy, Complexity, pip-audit, Bandit.
3. OpenAPI drift, Redocly, TypeScript client compile.
4. Docker build, non-root run, ephemeris attestation.
5. Evidence bundle mit commit, lock hash, dependency/tool versions, SBOM, image/build identity.

**Acceptance:** atomarer `release-gate` grün; keine skipped Pflichtgates.  
**Validation:** GitHub run URL/IDs + signed evidence manifest.  
**Rollback:** RC verwerfen; kein Tag/Promote.

### TASK-018: Staging-Smoke, Security- und Performance-Gate ausführen

**Objective:** Real-boundary Evidenz vor Production.  
**Requirements:** REQ-O-001, REQ-S-002, REQ-NF-004, REQ-O-002.  
**Scope:** Railway Staging, real-boundary API-Smokes, Dependency-Failure-Injection, Logs/Metriken und Lastprofil.

**Steps:**
1. Staging auf RC-Commit/Build deployen; `/build` Identität prüfen.
2. `/ready`, Auth positive/negative, CORS, Rate-Limits, Request-ID, Error Redaction testen.
3. Lunar SWIEPH Referenzrequests über HTTP ausführen.
4. Dependency-Ausfälle simulieren: SE1/Redis -> unready.
5. Genehmigte Lastmatrix; P95/P99, Fehlerquote, CPU/RAM, Redis messen.

**Acceptance:** alle Smoke- und Betriebsgrenzen grün; keine Secret-/PII-Leaks; Schwellen erfüllt.  
**Validation:** staging report + logs/metrics snapshot.  
**Rollback:** Staging auf vorherigen Build zurück.

### TASK-019: Release-PR, Tag, Promotion und Rollback abschließen

**Objective:** Kontrollierter, reversibler Production Release.  
**Requirements:** REQ-A-002, REQ-O-002.  
**Scope:** release-please PR, Tag/GitHub Release, Railway Production Promotion, Production-Smoke, Rollback- und Evidence-Artefakte.

**Steps:**
1. release-please-PR prüfen: genehmigte Version, Changelog, pyproject, Manifest.
2. Required Checks und Approval abwarten; PR mergen; Tag/GitHub Release prüfen.
3. Genehmigten RC nach Production promoten.
4. `/build`, `/ready`, Auth und Lunar Smoke prüfen.
5. Rollback auf vorherigen Deployment-Stand pro Probe ausführen oder in isolierter Produktionssimulation beweisen.
6. Verification Report auf RELEASE ändern; Residual Risks dokumentieren.

**Acceptance:** Tag, Release, Production und Evidence Ledger zeigen denselben genehmigten Commit/Build; Rollback-Nachweis vorhanden.  
**Validation:** production smoke + release metadata + rollback report.  
**Rollback:** vorherigen Deployment-Stand aktivieren; neuen Release als zurückgezogen markieren, keine Historie umschreiben.

## Validation strategy

### Focused tests

```bash
python -m pytest --collect-only -q
pytest tests/test_gate_contracts.py -q
pytest tests/test_mock_contract.py -q
pytest tests/test_lunar_state_v2.py tests/test_lunar_state_endpoint.py -q
pytest tests/test_production_profile.py tests/test_b2b_infra.py tests/test_key_issuance.py -q
python scripts/export_openapi.py --check
python -m build --wheel --sdist
# install each artifact into an empty temporary environment and run resource/app smokes
ruff check bazi_engine tests scripts
mypy bazi_engine --ignore-missing-imports
python scripts/check_complexity.py --check
```

### Broader regression checks

- Python 3.10, 3.11, 3.12 full pytest with pinned SWIEPH assets and coverage ≥75%.
- Wheel und sdist bauen, Inventar prüfen, jeweils ohne Source-Checkout installieren und App-/Resource-Smokes ausführen.
- `pip-audit -r <canonical-lock> --strict` und `bandit -r bazi_engine -ll`.
- Docker build/run, non-root assertion, `/ready`, `/build`, auth and endpoint smoke.
- OpenAPI lint + TypeScript codegen compile.
- Snapshot deletion/tamper negative tests.
- Release-please Test-PR mit Required Checks.

### Manual review checklist

- [ ] Branch/Ruleset/Token-Änderungen von Platform + Security reviewed.
- [ ] SemVer-Ziel und Changelog von Product Owner akzeptiert.
- [ ] Package-Resource-Inventar und Clean-Install-Wheel/sdist-Smoke reviewed.
- [ ] Ephemeris Lock und Lunar-Toleranzen fachlich reviewed.
- [ ] Swiss-Ephemeris-Lizenzwahl und Geltungsbereich rechtlich freigegeben.
- [ ] Conditional Surfaces explizit entschieden.
- [ ] Staging-/Performance-/Rollback-Evidence vorhanden.
- [ ] Keine Secrets, absoluten lokalen Pfade oder ungeprüften Genauigkeitsclaims in Artefakten.

## Rollback and safety

- Änderungen in kleinen PR-Slices mergen; Control Plane vor Domain Contract.
- Kein Tag vor grünem RC-Gate; kein Production Promote vor Staging.
- Vor Branch-Rename Settings/Integrationen exportieren.
- Vor Precision-/Schemaänderung bestätigen, dass V2 noch nicht öffentlich stabil genutzt wird.
- Alte Production-Deployment-ID und Secrets bis nach erfolgreichem Beobachtungsfenster behalten.
- Snapshots und Changelog nie durch Force-Push/History Rewrite „reparieren“.

## Execution handoff

- **Start with:** TASK-001 bis TASK-004. Danach TASK-013 als Distribution-Baseline, bevor RC-, Container- und Promotion-Gates als bestanden gelten.
- **Stop and ask if:** Branch-Rename externe Consumer bricht; 1.5.0 nicht die genehmigte Baseline ist; Key-Issuance zwingend benötigt wird; ZWDS ohne Sign-off öffentlich bleiben muss; Railway keinen kontrollierten Staging→Production-Pfad bietet; SWIEPH-Referenzen widersprechen; kein gültiger Swiss-Ephemeris-Lizenznachweis vorliegt.
- **Commit strategy:** je TASK oder eng gekoppeltem Slice ein Conventional-Commit/PR; squash merge; keine gemischten Domain-/Infra-Megacommits.
- **Expected final artifacts:** grüne `release-gate`-Run-ID, release-please-PR, ephemeris lock, SBOM, OpenAPI/SDK, Staging-/Performance-/Rollback-Bericht, aktualisiertes Evidence Ledger.

## Plausibility and truth self-check

- Goal length: wird durch `scripts/validate_artifacts.py` gegen <4000 Zeichen geprüft.
- Unsupported claims removed or labeled: yes.
- Strongest counterargument: Ein reiner Lunar-Patch könnte schneller erscheinen, aber er würde das nicht importierbare Distribution-Artefakt sowie die bestätigten Control-Plane- und Runtime-Gates nicht schließen und wäre daher kein belastbarer Repository-Release.
- Failure-mode chain: Wenn nur der Branch korrigiert wird, dann läuft release-please zwar, aber seine GITHUB_TOKEN-PR erhält möglicherweise keine oder nur approval-required CI; wird dieses Gate umgangen, kann Railway ungeprüften Code deployen. Mitigation: TASK-002, TASK-003 und TASK-006 als zusammenhängendes Gate abschließen; TASK-013 stellt sicher, dass anschließend genau das ausgelieferte Resource-Artefakt geprüft wird.
- Bias risks: Scope inflation durch vorhandene Altlasten; mitigiert durch Conditional Gates, Minimalpfad und ausdrückliche Nicht-Blocker.
- Final readiness: ready-for-execution; current repository release decision remains blocked.
