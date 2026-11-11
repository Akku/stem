<div align="center">

<img src="docs/assets/stem-header.jpg" alt="STEM" width="960">

**An Agile Agentic Coding Harness**

**Version 1.17.0** · ![License](https://img.shields.io/badge/license-MIT-green) ![Claude Code](https://img.shields.io/badge/Claude%20Code-getestet-green) ![Codex](https://img.shields.io/badge/Codex-getestet-green)

[🇬🇧 English](README.md) · [Warum](#warum-stem) · [Evolution](#wie-stem-sich-weiterentwickelt) · [Für dich?](#ist-stem-etwas-für-dich) · [Loslegen](#loslegen) · [Inhalt](#inhalt)

</div>

STEM ist ein Template-Harness, mit dem du dein Projekt schnell startest. Es setzt auf dem Coding-Agenten auf, den du schon nutzt (am besten Claude Code), und braucht nur ein Modell wie Sonnet mit mittlerem Denkaufwand, du musst also kein Geld für die teuersten Modelle ausgeben.

## Warum STEM

**Humor-Warnung:** Der Name STEM ist von der KI im Film „Upgrade“ (2018) abgeleitet.

| Annahme                                                                                                                                         | Was STEM bietet                                                                                                                                                                                                                                                                                                                      |
| ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Menschen sind schlecht darin, Anforderungen zu spezifizieren**, und ein Agent füllt die Lücken mit Vermutungen. Allzu menschlich. | **Alignment:** [Backlog.md](https://github.com/MrLesk/Backlog.md) hält Vision, Meilensteine und Tasks. Das SETUP hilft bei der Installation, und der Skill `alignment` befragt dich, damit du nicht effizient das falsche Ergebnis bekommst. |
| **Automatisierung ist verlässlicher** als ein Agent, der Regeln in Prosa interpretiert. | **Determinismus zuerst:** Skripte und Hooks übernehmen, was sich automatisieren lässt (Sitzungsstart, Minimierung großer Lesezugriffe, Logs nur punktuell lesen usw.). Jede Regel steht an genau einer Stelle, das LLM muss also weniger interpretieren. |
| Du weißt jetzt, was du bauen willst – aber **wenn du die Ergebnisse siehst, ändern sich die Anforderungen**. Immer.                             | **Dünne Scheiben:** Meilensteine (Vertical Slice, MVP, 1.0, ...); kleine Tasks mit Akzeptanzkriterien, die wirklich geprüft werden; Arbeitspakete werden dir vorgeschlagen.                                                                                                                                                          |
| **Qualität sinkt**<sup>[1](https://arxiv.org/abs/2402.14848)</sup>, Stimmung sinkt, Fehler fressen mehr Tokens, **wenn der Kontext wächst**.<sup>[2](https://arxiv.org/pdf/2611.05306)</sup> | **Kleine Sitzungen:** Regeln werden nur bei Bedarf geladen, lange Logs/Dateien werden nur gegrept / angespitzt und bleiben aus dem Kontext. Wird der Kontext schwer, wird der Skill `handoff` automatisch empfohlen. Wie jede gute KI es täte. STEM schaltet MCP-Server und Skills ab, die du nicht brauchst. |
| Kleine Sitzungen müssen Zustand übergeben. **Kontext-Komprimierung ist verlustbehaftet** und macht vollständiges Neulesen nötig. | **Kontinuität:** Der Stand lebt nur in Dateien: Backlog-Tasks, Entscheidungen und kurze Übergabenotizen. Neue Sitzungen werden nach `handoff` automatisch erzeugt und lesen den Stand aus gut organisierten Dateien. |
| Agenten machen Vorschläge, aber **Richtungsentscheidungen bleiben beim Menschen**. Also braucht der Mensch jede Unterstützung, die möglich ist. | **Menschliche Arbeit zählt:** Berichte in einfacher Sprache nach jeder Phase, Fragen mit Optionen und Empfehlung, ein direkter Link oder Befehl für alles, was du prüfen oder entscheiden sollst. Du behältst die Kontrolle. |
| **Ein Agent** meldet „fertig“. Ist es aber nicht. Er **arbeitet nicht-deterministisch**.                                                        | **Nachvollziehbarkeit:** Jede Änderung ist ein Task mit Plan, Akzeptanzkriterien und festgehaltenen Belegen; unbelegte Kriterien bleiben offen.                                                                                                                                                                                      |
| **Agenten reflektieren sich nicht, wenn sie nicht dazu aufgefordert werden.** Und du? | **Kontinuierliches Lernen:** Das Harness entwickelt sich weiter, indem es regelmäßig den Skill `retro` vorschlägt. Er reflektiert über gespeicherte Fragen mit einem unabhängigen Prüfer sowie über protokollierte Messwerte, Probleme und deine Eingaben. Mit `promote-learning` kannst du das Harness sogar für alle anderen verbessern. |

Doku für Menschen gibt es auf Englisch und Deutsch, Agenten-Anweisungen sind englisch, und der Agent spricht mit dir in deiner Sprache.

## Wie STEM sich weiterentwickelt

STEM folgt dem Prinzip *evolutionäres Lernen*: Es verändert sich in kleinen Schritten, anhand dessen, was im echten Einsatz passiert, nicht nach einem großen Plan. Fünf Quellen fließen ein:

- **Retros:** Der Skill `retro` wird regelmäßig angeboten. Er betrachtet Messwerte, Probleme und deine Eingaben. Jede Retro nimmt außerdem die nächsten Fragen aus einem vorbereiteten Satz von Reflexionsfragen (Regeln, Skills, Kontextkosten, neue Agenten-Funktionen und mehr), sodass jede Retro neue Verbesserungen aufdecken kann. Aus den Ergebnissen werden kleine Änderungen, die eine spätere Retro überprüft.
- **Andere Projekte:** Projekte, die mit STEM gebaut werden, können zurückmelden, was sie gelernt haben (Field Reports, `promote-learning`), und erhalten Verbesserungen über `stem-update`.
- **Dogfooding:** STEM wird mit STEM selbst entwickelt, in einem eigenen Projekt. Die meisten Änderungen werden dort zuerst ausprobiert.
- **Aufräumen:** Retros messen, wie viel Kontext die Arbeit verbraucht und welche Regeln geladen werden. Regeln, die sich nicht lohnen, werden zusammengelegt oder entfernt. Ziel sind mit der Zeit weniger, bessere Regeln.
- **Die LLM-Szene:** Der Maintainer verfolgt die LLM- und Coding-Agent-Community, testet neue Verbesserungsideen und bringt sie in STEM ein, wo sie helfen.

## Ist STEM etwas für dich?

STEM ist gebaut für eine Person, die mit Claude Code an einem Projekt über viele Sitzungen arbeitet, ab mittlerer Größe. Für kleine Aufgaben und Einmal-Skripte kostet der Ablauf mehr, als er bringt: nimm den Agenten pur ([STEM oder der Agent pur?](#stem-oder-der-agent-pur)). Teams mit eigenem Prozess, CI und Review passen nicht.

<p align="center"><code>[ You ]──▶[ STEM ]──▶[ More YOU ]</code></p>

## Loslegen

1. [ZIP herunterladen](https://github.com/Akku/stem/archive/refs/heads/main.zip) und entpacken. Den ganzen Ordner einschließlich versteckter Dateien verwenden.
2. Diesen Ordner in deinem Coding-Agenten öffnen (zum Beispiel in der Claude-Desktop-App, Tab Code).
3. Diesen Prompt einfügen und den Platzhalter durch deine Idee ersetzen:

```text
Richte dieses Projekt ein: Folge SETUP.md. Arbeite in meiner Sprache und installiere alles, was fehlt, selbst (ich genehmige die Schritte).

Was ich entwickeln will, ist folgendes:
<deine Idee: was, für wen, woran erkennt man „fertig“ – ein paar Sätze>
```

Beantworte die Rückfragen des Agenten und genehmige nötige Installationsschritte. Er richtet mit dir Werkzeuge, Vision, Meilensteine und erste Tasks ein. Gib nie Passwörter oder Geheimnisse in einen Chat ein.

**Technisch Versierte:** auf GitHub **Use this template** wählen oder das Repository klonen, dann derselbe Prompt. Die [ausführliche Anleitung](STARTE_HIER.md) bietet weitere Hilfe.

<details>
<summary>Teststand der Agenten und Plattformen</summary>

Claude Code ist im praktischen Einsatz getestet. Codex ist durch einen automatisierten Testlauf getestet (Einrichtung eines neuen Projekts, native Skill-Liste, Abstimmungsgespräch, eine Aufgabe bis Done) sowie in einem bestehenden Projekt mit dokumentierten Umgehungslösungen; Projekt-Hooks, die Codex-Oberfläche, Codex Cloud und das Verhalten bei langem Kontext sind nicht abgedeckt. Die [Codex-Hinweise](docs/agent/CODEX.md) erklären Voraussetzungen, Sitzungsstart, Sandbox-Zugriff und das Vorgehen ohne Kontextwarnung (Agentenhinweise auf Englisch). Für DeutschlandGPT Code gibt es einen Adapter (`dgpt.md`, Skill-Verweis), geschrieben nach dessen Dokumentation; er ist noch nicht getestet, und diese App führt keine STEM-Hooks aus.

macOS ist getestet. Auf anderen Systemen, Agenten oder Modellen passt der Skill `port-check` STEM als Overlay an, misst das Ergebnis und berichtet es (Angebot beim Session-Start).

</details>

Drei Kurven aus der Nutzung von STEM an sich selbst (Dogfooding-Daten, kein Benchmark): [Ergebnisseite](docs/RESULTS.md), auf Englisch.

## Optional: Claude Code in einer Docker-Sandbox

Wer Claude Code vollständig vom eigenen Rechner trennen will, startet es mit `scripts/sandbox.sh` in einem Docker-Container. Das Projekt liegt nur in einem Docker-Volume (kein Ordner des Rechners wird eingebunden); nötig ist nur Docker.

```bash
scripts/sandbox.sh new meinprojekt      # klont die STEM-Vorlage in eine neue Sandbox und startet Claude
scripts/sandbox.sh new meinprojekt --repo https://github.com/du/dein-repo.git   # stattdessen dein eigenes Repo
scripts/sandbox.sh start meinprojekt    # später fortsetzen; außerdem: stop, export, reset, list
```

- **Anmeldung:** `ANTHROPIC_API_KEY` aus der Umgebung oder Kontoanmeldung in der Sandbox (`/login`, bleibt im Volume; sie gehört zu dieser einen Sandbox, jede neue Sandbox fragt erneut: eine Sandbox für mehrere Projekte nutzen (darin klonen) oder den API-Key setzen).
- **Rückweg:** Push nach GitHub (`GH_TOKEN` mit einem nur für dieses Repo gültigen Token; wird nur per Namen durchgereicht, nie gespeichert) oder `scripts/sandbox.sh export meinprojekt [ordner]` (tar.gz und Git-Bundle; Standardordner `~/stem-sandbox-exports`, nie der aktuelle Ordner). Das Image enthält `git` und `gh` (GitHub CLI, nutzt `GH_TOKEN`).
- **Netz:** ausgehend offen, eingehend nichts. `--strict` erlaubt nur Claude-API, GitHub, npm und PyPI (`--allow HOST` für weitere). `--port 8080` leitet einen Container-Port auf localhost.
- **Image:** neueste Ubuntu-LTS beim ersten Start (`--ubuntu TAG` überschreibt; wird mit der Sandbox gespeichert).
- **Grenzen:** Projekte, die selbst Docker brauchen, laufen darin nicht (bewusst kein Docker-Socket); Windows nur mit WSL2; der erste Start baut das Image (einige Minuten).

## Aktuell bleiben

Zu Beginn jeder Sitzung prüft der Agent (einmal pro Tag), ob es eine neuere STEM-Version gibt, und sagt dir Bescheid. Mit deiner Zustimmung liest der Skill `stem-update` das [Changelog](CHANGELOG.md), wählt aus, was deinem Projekt nützt, und übernimmt es, ohne projektspezifische Inhalte zu überschreiben. Auch der Skill `retro` prüft STEM.

STEM-Releases tragen Versionsnummern nach dem Muster `MAJOR.MINOR.PATCH`; Umbenennungen und Entfernungen stehen mit Migrationshinweis im Changelog. Dein Projekt hat eine eigene Version, beginnend bei 0.1.0, unabhängig von der STEM-Version in `STEM_VERSION`: Nach einem abgeschlossenen Arbeitspaket schlägt der Agent einen Patch-, Minor- oder Major-Sprung vor und setzt ihn nur mit deiner Zustimmung um.

## STEM oder der Agent pur?

Coding-Agenten wie Claude Code oder Codex funktionieren auch allein gut. STEM legt einen Arbeitsablauf darum, und der kostet zusätzliche Schritte. Eine grobe Orientierung:

| Deine Situation | Agent pur | Mit STEM |
| --- | --- | --- |
| Einmal-Skript oder schneller Prototyp | Reicht meist | Setup und Task-Schritte kosten mehr, als sie bringen |
| Ein Projekt über viele Sitzungen | Du erklärst den Stand neu oder führst eigene Notizen | Übergabenotiz und Zustandsüberblick, in der nächsten Sitzung automatisch gelesen |
| Du hast keinen technischen Hintergrund | Du installierst und konfigurierst die Werkzeuge selbst | Der Agent installiert und erklärt die Werkzeuge; eine Freigabe pro Installationsschritt |
| Du willst sehen, was der Agent getan hat und ob es fertig ist | Du liest den Chat und die Änderungen | Ein Task mit Akzeptanzkriterien und Nachweisen; eine Prüfung pro Task |
| Dein Setup soll mit der Zeit besser werden | Änderungen passieren nebenbei | Retros machen aus Reibung Regeländerungen; alle paar Tasks eine Retro |
| Ein Team mit eigenem Prozess, eigener CI und Review | Der Agent fügt sich in euren Prozess | Der STEM-Prozess würde euren doppeln; passt nicht |

Getestete Agenten und Plattformen: siehe *Teststand der Agenten und Plattformen* unter [Loslegen](#loslegen).

**Andere Ansätze.** Mehrere Open-Source-Projekte geben Coding-Agenten ebenfalls Struktur; die Stärken überschneiden sich.

- **Spec-first-Werkzeuge** (zum Beispiel [Spec Kit](https://github.com/github/spec-kit), [OpenSpec](https://github.com/Fission-AI/OpenSpec)): stark darin, jede Änderung vor dem Code in eine abgestimmte Spezifikation, einen Plan und Tasks zu fassen. STEM schärft die Idee einmal beim Setup und legt den Schwerpunkt auf die projektweite Schleife aus Backlog, Übergabe und Retro.
- **Skill-Bibliotheken** (zum Beispiel [Superpowers](https://github.com/obra/superpowers)): stark in der Engineering-Disziplin pro Arbeitspaket, etwa Entwurf, testgetriebene Entwicklung, Review und Verifikation. STEM schreibt diese Engineering-Schritte nicht vor; sein Schwerpunkt ist die Kontinuität über Sitzungen.
- **Rollenbasierte agile Methoden** (zum Beispiel [BMad Method](https://github.com/bmad-code-org/BMAD-METHOD)): stark in strukturierter Planung mit Rollen-Agenten, Backlog und Retrospektiven; am nächsten an STEM. STEM ist kleiner und richtet das geführte Setup auf Menschen ohne technischen Hintergrund aus.

Stand laut eigener Dokumentation der Projekte, November 2026; diese Projekte ändern sich schnell.

## Inhalt

<details>
<summary>Alle Dateien anzeigen</summary>

| Datei | Zweck |
| --- | --- |
| `STARTE_HIER.md` / `START_HERE.md` | Anleitung für Menschen (DE/EN) |
| `.claude/skills/` | Skills: `retro`, `alignment`, `handoff`, `promote-learning`, `stem-update`, `port-check`; optionales Modul (Auswahl beim Setup): `market-analysis` |
| `.agents/skills` | Verweis auf `.claude/skills/` für gemeinsame Codex-Skill-Quellen; Codex listet diese Skills nativ (automatisierter Testlauf) |
| `dgpt.md`, `.deutschlandgpt/skills` | Adapter für DeutschlandGPT Code: Verweis auf `AGENTS.md` und auf `.claude/skills/` (ungetestet) |
| `.claude/agents/` | Agenten: `ux-designer` (optionales Modul, für Projekte mit Oberfläche) |
| `SETUP.md` | Einmalige Setup-Anleitung für den Agenten (wird nach dem Setup gelöscht) |
| `AGENTS.md` | Gemeinsame Kernregeln (Codex & kompatible Tools) |
| `CLAUDE.md` | Dünner Adapter, verweist auf `AGENTS.md` |
| `scripts/githooks/pre-commit`, `pre-push` | Schutz für jeden Agenten: keine vertraulichen Quelldokumente oder gängigen Secrets in einem Commit; kein Force-Push und kein Löschen von Remote-Branches (wird beim Setup aktiviert) |
| `STEM_VERSION`, `CHANGELOG.md` | STEM-Version, auf der das Projekt basiert; Änderungen je Version |
| `.claude/settings.json` | Claude Code: sichere Befehle vorab freigegeben, Sitzungsstart-Hook |
| `LICENSE`, `CITATION.cff` | MIT (STEM), citation data; `.github/stem-check.py` + Workflow prüfen STEM selbst |
| `scripts/check-backlog.sh`, `scripts/retro-metrics.sh`, `scripts/promote-check.sh` | Backlog-Konsistenzprüfung (auch im Pre-commit-Hook); Messwerte für Retros; Learnings, die STEM teilen kann |
| `docs/agent/stacks/` | Stack-spezifische Hinweise, nur bei passendem Stack geladen |
| `scripts/context-report.py` | Optionales Retro-Werkzeug (Claude Code): wohin der Kontext floss, längste Sitzungen; nur Zahlen |
| `scripts/context-check.py` | Claude-Code-Hook: warnt bei großem Kontext, dass eine neue Sitzung fällig ist |
| `scripts/hooks/manifest.json`, `scripts/hooks-sync.py`, `scripts/hooklib.py`, `docs/agent/HOOKS.md` | Eine Quelle für die Hooks: Das Manifest nennt jeden Schutzmechanismus und seine Verdrahtung je Agent; der Generator schreibt die Konfigurationsdateien der Agenten und die Übersichtstabelle; der gemeinsame Leser verarbeitet die Hook-Eingaben der Agenten |
| `scripts/run.sh` | Kompakte Ausgabe für Tests/CI/CLI (Exitcode bleibt erhalten, Volllog im git-ignorierten `.agent-logs/`, `evidence:`-Verweis für Task-Notizen; nicht zitierte Logs älter als 30 Tage werden gelöscht) |
| `scripts/session-start.sh` | Zustandsüberblick zum Sitzungsstart (Branch, Änderungen, Tasks, Übergabe); ändert keine Projektdateien, `STEM_OFFLINE=1` ohne Netzwerk |
| `docs/agent/OPERATING_MODEL.md` | Regeln mit stabilen IDs (`R-*`), gezielt per ID geladen |
| `docs/agent/ADVANCED.md` | Selten gebrauchte Regeln (Parallelität, Messung, Routing, lokale Modelle) |
| `docs/agent/EXPERIMENTS.md` | Hypothesen, Messgrößen, Basislinien und Evidenzgrade für dauerhaft kostenwirksame Regeln |
| `docs/agent/NEXT_RETRO.md` | Alles für die nächste Retro an einem Ort: fällige Prüfungen, Beobachtungen, Punkte für die erste Retro |
| `docs/agent/PITFALLS.md` | Wachsende Liste technischer Stolperfallen |
| `docs/agent/PROCESS_IMPROVEMENTS.md` | Retro-Behandlung und Rückfluss in STEM |

</details>

## Beitragen

Bewährte Learnings aus Projekten bitte per Pull Request einbringen (Muster: Problem, Muster, Geltungsbereich, Evidenz – siehe `docs/agent/PROCESS_IMPROVEMENTS.md`). Keine Projekt- oder Firmeninterna, keine Zugangsdaten – das Repository ist öffentlich. Ablauf und Checkliste (englisch): [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits und Lizenz

STEM wird von Tim Dellas ([akku](https://github.com/Akku)) und Mitwirkenden erstellt und gepflegt. Es steht unter der [MIT-Lizenz](LICENSE): frei nutzbar, kopierbar und anpassbar, auch kommerziell. Einzige Bedingung: Copyright-Hinweis und Lizenztext bleiben bei Kopien oder wesentlichen Teilen erhalten. Wenn STEM deiner Arbeit hilft, freue ich mich über eine Erwähnung oder einen Stern; Zitierdaten stehen in [CITATION.cff](CITATION.cff).
