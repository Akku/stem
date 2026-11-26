# Tron-Modus: Anleitung (Vorschau)

[🇬🇧 English](TRON-GUIDE.md) · [README](../README.de.md#optional-tron-modus-ein-meilenstein-unbeaufsichtigt-gebaut)

Mit Tron bauen Agenten-Sitzungen einen freigegebenen Meilenstein, während du weg bist, zum Beispiel über Nacht. Tron baut den klar beschriebenen Teil und liefert einen Bericht mit allem, was dich braucht. Tron pusht, taggt und mergt nie: du entscheidest, was nach `main` kommt. Rechne mit sorgfältiger Vorbereitung.

## Passt es für dich?

- Ja, wenn ein Meilenstein Aufgaben mit klaren, prüfbaren Akzeptanzkriterien hat und du ihn in einer Sandbox laufen lassen kannst.
- Nein bei kleinen Projekten, vagen Zielen oder Aufgaben, die während des Laufs dein Urteil, echte Daten oder bezahlte Dienste brauchen. Tron ist standardmäßig aus, weil es sich noch in der Erprobungsphase befindet; sag dem Agenten „schalte Tron ein“, um das Modul `tron` zu aktivieren.

## 1. Vorbereiten (mit dem Agenten, etwa 15-30 Minuten)

Sag „lass Meilenstein X mit Tron laufen“. Der Skill `tron`:
1. Schickt **eine Setup-Nachricht** mit Vorschlägen: Reihenfolge der Aufgaben, Entscheidungsrahmen (was die Agenten allein entscheiden dürfen und was zu dir zurückkommt), Projekt-Invarianten, Abnahmeszenario (was du klicken oder ausführen würdest, um das Ergebnis zu beurteilen, auf einer Plattform), Limits, Modelle. Antworte knapp, z. B. `ok` oder `2b, 7: sonnet`.
2. Macht eine **Fragenrunde**: ein Planer liest den ganzen Meilenstein und entscheidet kleine Fragen vorab als Annahmen. Du legst per Nummer ein Veto ein (`Veto A2`) und beantwortest die wenigen echten Fragen. Kriterien, die dich brauchen, wandern in eigene Aufgaben, damit der Lauf nicht an ihnen hängen bleibt.
3. Prüft die **Umgebung**: jeder Dienst, jedes Werkzeug und jede Datei, die die Aufgaben brauchen, wird vor dem Lauf in der Sandbox geprüft, nicht erst mittendrin entdeckt.
4. Ruft `python3 scripts/tron.py check --milestone m-N` auf, bis `READY` erscheint.

## 2. Starten

Der Agent stellt eine Frage mit dem Startbefehl, dem **Budget** (`max_cost`, `max_hours`, `max_tasks`) und den erwarteten Kosten. Dein Ja gibt das Budget frei und startet den Lauf; es gibt keine zweite Bestätigung.

- **Sandbox:** im Docker-Sandbox-Container von STEM laufen lassen (`scripts/sandbox.sh`, siehe README) mit `--permission-mode bypassPermissions`, damit keine Berechtigungsabfrage den Lauf anhält und die Agenten deinen Rechner nicht berühren. Nie eine enge Werkzeug-Allowlist.
- **Budget:** der Lauf hält beim ersten erreichten Limit an; jede Evaluator-Sitzung ist ebenfalls begrenzt. Ein Lauf kostet echtes Geld.
- **Wach halten:** bei Läufen über eine Stunde fragt der Agent, ob der Mac wach bleiben soll (`scripts/sandbox.sh start <name> --keep-awake`).

## 3. Beobachten (optional)

Der Agent startet den Lauf im Hintergrund und beobachtet ihn selbst: nach 1-2 Minuten liest er den Anfang des Logs, um zu sehen, dass der Lauf wirklich arbeitet, danach prüft er etwa alle 2 Stunden den Stand. Du musst kein Terminal offen halten. Zum vorzeitigen Anhalten die Datei `docs/agent/tron/STOP` anlegen (der Lauf endet nach der laufenden Sitzung und kann fortgesetzt werden).

## 4. Bericht lesen

Wenn der Lauf endet, liest der Agent `docs/agent/tron/REPORT-<run>.md` und sagt dir: erledigte und blockierte Aufgaben, Befunde des Evaluators, Kosten und den Branch `tron/<milestone>`. Dann stellt er die **Fragen an dich** aus dem Bericht in einer nummerierten Nachricht (blockierte Aufgaben, Annahmen ohne Grundlage, Risiken, und ob du Fehler gefunden hast). Antworte knapp (`1a, 3b`). Danach:
- probiere das Ergebnis selbst aus (das Abnahmeszenario),
- merge den Branch, wenn du zufrieden bist,
- starte den Lauf erneut für beantwortete blockierte Aufgaben: er setzt dort fort, wo er angehalten hat.

Fehler, die du später findest, gehen als Nachweis zurück (`tron.py defect`), damit der Evaluator aus dem lernt, was er übersehen hat (nur mit deinem Ja).

## Wo die Details stehen

Regeln für die Agenten: `docs/agent/TRON.md` (`R-TRON`). Der Ablauf des Agenten Schritt für Schritt: der Skill `tron`. Änderungen pro Version: [CHANGELOG](../CHANGELOG.md) (Englisch).
