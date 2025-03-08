# Eventify - Benutzerhandbuch

## Für Volans (Teilnehmer)

Als Volan kannst du dich für Events anmelden und abmelden. Hier ist, wie du den Bot nutzen kannst:

### Für eine Rolle anmelden

1. Gehe in den Event-Thread
2. Schreibe die Nummer der Rolle, für die du dich anmelden möchtest (z.B. `1` für die erste Rolle)
3. Optional kannst du einen Kommentar hinzufügen, indem du nach der Nummer einen Text schreibst 
   - z.B. `1 Komme etwas später` oder `15 mh, irh`
   - @-Zeichen in Kommentaren werden automatisch entfernt, um Discord-erwähnungen zu vermeiden
4. Wenn du bereits für eine andere Rolle angemeldet bist, wirst du automatisch von dieser abgemeldet und für die neue Rolle angemeldet

### Für FillALL anmelden

1. Gehe in den Event-Thread
2. Schreibe die Nummer der FillALL-Rolle (normalerweise die letzte Nummer in der Liste)
3. Du wirst als flexibler Teilnehmer eingetragen und kannst bei Bedarf verschiedene Rollen übernehmen
4. Die FillALL-Anmeldung bleibt bestehen, auch wenn du dich für eine andere Rolle an- oder abmeldest

### Von einer Rolle abmelden

1. Gehe in den Event-Thread
2. Schreibe oder `-`, um dich von allen Rollen abzumelden
3. Oder schreibe `-X`, wobei X die Nummer der Rolle ist, von der du dich abmelden möchtest

---

## Für Event-Ersteller

Als Event-Ersteller kannst du neue Events planen und verwalten. Hier ist, wie du den Bot nutzen kannst:

### Event erstellen

1. Verwende den Slash-Befehl `/eventify` im Event-Kanal
2. Gib die folgenden Informationen ein:
   - `title`: Der Titel deines Events
   - `date`: Das Datum im Format DDMMYYYY (z.B. 31122025 für den 31.12.2025) oder DD.MM.YYYY
   - `time`: Die Uhrzeit im Format HHMM (z.B. 1300 für 13:00 Uhr)
   - `mention_role` (optional): Die Discord-Rolle, die beim Event erwähnt werden soll

3. Nach dem Absenden öffnet sich ein Modal, in dem du folgende Informationen eingeben kannst:
   - **Beschreibung**: 
     - Detaillierte Informationen zum Event
     - Falls eine Rolle ausgewählt wurde, wird diese automatisch am Anfang der Beschreibung erwähnt
     - 1020 Zeichen Platz, danach wird der Text mit "..." abgeschnitten
   - **Rollen**: 
     - Liste der verfügbaren Rollen, eine pro Zeile
     - Leerzeilen werden ignoriert
     - Mit Text in Klammern, z.B. "(Core)" setzt man Abschnittsüberschriften

### Teilnehmer erinnern

Als Event-Ersteller kannst du allen eingetragenen Teilnehmern eine Erinnerung schicken:

1. Gehe in den Event-Thread
2. Verwende den Slash-Befehl `/remind`
   - Optional kannst du eine zusätzliche Nachricht mit `message:` hinzufügen
   - Beispiel: `/remind message: Denkt an eure Buffs und Tränke!`
3. Der Bot sendet dann:
   - Eine private Nachricht an alle eingetragenen Teilnehmer mit:
     - Event-Titel
     - Datum und Uhrzeit
     - Deine zusätzliche Nachricht (falls angegeben)
     - Link zum Event
   - Eine Bestätigung an dich, wie viele Erinnerungen erfolgreich versendet wurden

Nur der Event-Ersteller kann diesen Befehl verwenden.

### Teilnehmer verwalten (für Event-Ersteller)

Als Event-Ersteller kannst du andere Teilnehmer hinzufügen oder entfernen:

#### Teilnehmer hinzufügen:
1. Verwende im Event-Thread den Befehl `/add`
2. Gib folgende Parameter ein:
   - `user`: Der Discord-Benutzer, den du hinzufügen möchtest (per Autocomplete)
   - `role_number`: Die Nummer der Rolle, z.B. 1 für die erste Rolle
   - `comment` (optional): Ein Kommentar, der neben dem Namen angezeigt wird
3. Der hinzugefügte Teilnehmer erhält automatisch eine private Nachricht mit:
   - Event-Titel
   - Zugewiesene Rolle
   - Datum und Uhrzeit
   - Kommentar (falls angegeben)
   - Link zum Event

#### Teilnehmer entfernen:
1. Verwende im Event-Thread den Befehl `/remove`
2. Gib folgende Parameter ein:
   - `user`: Der Discord-Benutzer, den du entfernen möchtest (per Autocomplete)
   - `role_number` (optional): Die Nummer der Rolle. Wenn nicht angegeben, wird der Teilnehmer aus allen Rollen entfernt
3. Der entfernte Teilnehmer erhält automatisch eine private Nachricht mit:
   - Event-Titel
   - Entfernte Rolle(n)
   - Datum und Uhrzeit
   - Link zum Event

Nur der Event-Ersteller kann diese Befehle verwenden. Die automatischen DM-Benachrichtigungen helfen den Teilnehmern, über Änderungen ihrer Rollenzuweisung informiert zu bleiben.

### Rollenformatierung

- **Normale Rollen**: Einfach den Namen der Rolle eingeben (z.B. "Tank", "Heiler", "DPS")
- **Abschnittsüberschriften**: In Klammern setzen, z.B. "(Core)" oder "(DPS)"
  - Abschnittsüberschriften werden fett dargestellt und zählen nicht bei der Nummerierung
  - Sie helfen, die Rollen übersichtlich zu gruppieren
- **FillALL-Rolle**: Eine Rolle mit dem Namen "Fill" oder "FillALL" wird automatisch als flexible Rolle erkannt
  - Diese Rolle wird immer ans Ende der Liste verschoben
  - Spieler können sich für FillALL zusätzlich zu einer normalen Rolle anmelden
- **Leere Zeilen**: Werden ignoriert und haben keinen Einfluss auf die Nummerierung

### Event verwalten

- Der Bot erstellt automatisch einen Thread für dein Event
- Im Thread kannst du weitere Informationen teilen und mit den Teilnehmern kommunizieren
- Das Event wird automatisch in der Event-Liste angezeigt
- Dein Name wird als Ersteller unter dem Titel des Events angezeigt

### Nutzung von Links in Discord

Um Links in Discord klickbar zu machen, verwende die folgende Markdown-Syntax:

- **Klickbarer Link**: `[Linktext](https://example.com)`
- `[builds](https://docs.google.com/spreadsheets/d/1pNt74V...)`
- `[Bildbeschreibung](https://de.wikipedia.org/wiki/Fliegender_Fisch_(Sternbild)#/media/Datei:Uranometria_Pavo_et_al.png)`
- Achte darauf, dass keine Leerzeichen zwischen den Klammern sind

### Rollen vorschlagen

Als Teilnehmer kannst du zusätzliche Rollen für ein Event vorschlagen:

1. Verwende im Event-Thread den Befehl `/propose`
2. Gib den Namen der neuen Rolle ein:
   - `role_name`: Der Name der Rolle, die du vorschlagen möchtest

Der Event-Ersteller erhält dann eine Nachricht mit deinem Vorschlag und kann diesen:
- Annehmen: Die Rolle wird vor der FillALL-Rolle zum Event hinzugefügt
- Ablehnen: Die Rolle wird nicht hinzugefügt

Du erhältst eine Benachrichtigung, wenn dein Vorschlag angenommen oder abgelehnt wurde.

---

## Beispiele

### Event erstellen
```
/eventify title: Ava Dungeon date: 31122025 time: 1900 mention_role: @Tank
```

### Rollen-Liste Beispiel
```