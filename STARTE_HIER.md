# Starte hier

*STEM – An Evolving Agentic Coding Harness*

**Version 1.5.1** · 🇬🇧 **English version: [START_HERE.md](START_HERE.md)**

STEM ist ein Startpunkt für agentische Entwicklung mit Git und Backlog.md. Du gibst dem Agenten dein Projektziel; er installiert, was fehlt, richtet die Werkzeuge ein, passt die Regeln an dein Ziel an und arbeitet danach Task für Task. Im Standardweg installiert und erklärt der Agent die Werkzeuge für dich.

## Standardweg: ZIP herunterladen

1. **Lade** STEM **herunter**: [stem.zip](https://github.com/Akku/stem/archive/refs/heads/main.zip) (alternativ: grüner Button **Code** → **Download ZIP** auf der GitHub-Seite).
2. **Entpacke** es (macOS: Doppelklick; Windows: Rechtsklick → *Alle extrahieren*). Benenne den Ordner nach deinem Projekt um und lege ihn dort ab, wo du Projekte aufbewahrst. **Verwende den ganzen Ordner; kopiere keine einzelnen Dateien heraus**: Er enthält versteckte Elemente (Namen mit Punkt am Anfang, z. B. `.claude`), die der Finder standardmäßig ausblendet (macOS: Cmd+Shift+. blendet sie ein). Fehlt trotzdem etwas, stellt der Agent es wieder her.
3. **Öffne deinen Agenten** (z. B. die Claude-Desktop-App, Tab Code) und wähle diesen Ordner als Arbeitsordner.
4. **Gib dem Agenten diesen Prompt**, mit deinem Ziel:

   > Richte dieses Projekt ein: Folge `SETUP.md`. Arbeite in meiner Sprache und installiere alles, was fehlt, selbst (ich genehmige die Schritte). Was ich entwickeln will, ist folgendes: *<deine Idee: was, für wen, woran erkennt man „fertig“ – ein paar Sätze>*

5. **Beantworte die Rückfragen** (Technologie, welche Agenten du nutzt, GitHub ja/nein). Der Agent prüft, welche Werkzeuge fehlen (Git, Node.js, Backlog.md), und installiert sie für dich; du genehmigst jeden Schritt in der App (lehnst du ab, gibt er dir stattdessen eine Anleitung). Der Installer fragt eventuell nach deinem Computer-Passwort. Fragt ein Installer nach deinem Computer-Passwort, gib es selbst dort ein, niemals im Chat. Unter Windows brauchen die Hilfsskripte Git für Windows (enthält *Git Bash*); der Agent führt dich dabei.
6. **Am Ende** fasst der Agent zusammen, was angelegt wurde und welcher Task zuerst kommt. Sag ihm, dass er starten soll.

**Sicherheitshinweis:** Lade STEM nur aus dem offiziellen Repository (Link oben). Es enthält einen kleinen Start-Hook (`scripts/session-start.sh`, eingerichtet in `.claude/settings.json`); lies die Vertrauensabfrage deiner App, wenn sie fragt, ob du dem Ordner vertraust. STEM verhindert, dass `.env`-Dateien und gängige API-Token-Formate committet werden (keine Garantie für andere Formate), aber füge nie Passwörter in den Chat ein.

## Für technisch Versierte: über GitHub

- Klicke auf der GitHub-Seite auf **Use this template** (erzeugt ein eigenes Repository), klone es, öffne es in deinem Agenten und gib den Prompt aus Schritt 4. Oder: dieses Repository mit `git clone` holen und den Ordner `.git` löschen, um mit frischer Historie zu starten.
- `git`, `node` und `backlog` schon installiert? Der Agent erkennt das und überspringt die Installationsschritte.
- Verbesserungen und bewährte Learnings sind als Pull Request willkommen (Skill `promote-learning`).

## Was du bekommst

- Git, Backlog.md, ein Vision-Dokument, Meilensteine (Vertical Slice → MVP → Moonshot) und die ersten 3–7 Tasks aus deinem Ziel. Der Agent fragt dich, was du dir jeweils darunter vorstellst.
- Kurze Agentenregeln (`AGENTS.md`), die weitere Regeln nur bei Bedarf laden – darauf ausgelegt, den Kontext des Agenten klein zu halten.
- `scripts/run.sh` hält lange Test-/CI-Ausgaben aus dem Kontext; `scripts/session-start.sh` liefert beim Sitzungsstart einen kompakten Stand.
- Skills für wiederkehrende Aufgaben: `retro`, `handoff`, `promote-learning`, `testing-practices`, `stem-update`.

## Im Alltag

- Der Agent erklärt, was er tut und warum, fasst jeden Schritt zusammen und gibt dir einen direkten Link, wenn du etwas testen oder entscheiden sollst. Sag jederzeit „antworte knapper“; die erste Retro fragt, ob die Menge passte.
- Sind mehrere zusammengehörige Tasks bereit, bietet der Agent an, sie als Batch abzuarbeiten; du genehmigst einmal.
- Die Arbeit ist backlog-getrieben: jede Änderung ist ein Task mit Akzeptanzkriterien. Ansehen mit `backlog board` oder `backlog browser`.
- Meldet der Agent zu Sitzungsbeginn eine neuere STEM-Version, kann der Skill `stem-update` dein Projekt aktualisieren (nur mit deiner Zustimmung).
- Hat ein Meilenstein keine Tasks mehr, schlägt der Agent die nächsten vor; du entscheidest.
- Sagt der Agent, dass der Kontext groß ist, hat er das Handoff geschrieben; öffne eine neue Sitzung und sage „Mach mit dem Handoff weiter“ (die neue Sitzung startet informiert). Optional: Eine Statuszeile kann in Claude Code die Kontextnutzung anzeigen (siehe deren Dokumentation).
- Eine Sitzung endet mit dem Skill `handoff`; die nächste beginnt mit `docs/agent/HANDOFF.md`.
- Nach dem ersten Meilenstein: Retro (Skill `retro`). Sie prüft auch das Harness selbst, inklusive allem, was dafür in `docs/agent/NEXT_RETRO.md` gesammelt ist.
- Keine Zugangsdaten ins Repository.

## STEM an einem echten Projekt testen: worauf achten

- Hat der Agent zu Beginn nur `AGENTS.md` gelesen statt alles?
- Sind `backlog/` und die ersten Tasks da, und ist `AGENTS.md` unversehrt?
- Läuft die Verifikation über `scripts/run.sh`?
- Steht `Setup status: DONE` in `AGENTS.md` und ist alles committet?
- Macht eine zweite Sitzung über `scripts/session-start.sh` ohne Nachfragen weiter?
- Stolperstellen oder Unklarheiten notieren (oder den Agenten als `Learning:` festhalten lassen). Sie sind die Eingabe für die erste Retro.

## Sprache

Diese Dateien sind für Menschen (Englisch und Deutsch). Anweisungen für Agenten sind auf Englisch, aber Agenten sprechen mit dir in deiner Sprache.
