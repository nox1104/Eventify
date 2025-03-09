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

## Für Event-Ersteller

Als Event-Ersteller kannst du neue Events planen und verwalten. Hier ist, wie du den Bot nutzen kannst:

### Event erstellen

Mit dem Befehl `/eventify` kannst du ein neues Event erstellen. Folgende Parameter sind verfügbar:

- `title`: Der Titel des Events
- `date`: Das Datum des Events im Format TT.MM.JJJJ
- `time`: Die Uhrzeit des Events im Format HH:mm
- `description`: Die Beschreibung des Events
- `mention_role` (optional): Eine Rolle, die beim Event erwähnt werden soll
- `image_url` (optional): Ein Link zu einem Bild, das im Event angezeigt werden soll
  - Das Bild wird unter der Beschreibung angezeigt
  - Unterstützte Bildformate: PNG, JPG, GIF
  - Der Link muss direkt zum Bild führen

3. Nach dem Absenden öffnet sich ein Modal, in dem du folgende Informationen eingeben kannst:
   - **Beschreibung**: 
     - Detaillierte Informationen zum Event
     - Falls eine Rolle ausgewählt wurde, wird diese automatisch am Anfang der Beschreibung erwähnt
     - 1020 Zeichen Platz, danach wird der Text mit "..." abgeschnitten
   - **Rollen**: 
     - Liste der verfügbaren Rollen, eine pro Zeile
     - Leerzeilen werden ignoriert
     - Mit Text in Klammern, z.B. "(Core)" setzt man Abschnittsüberschriften
     - Schreibe einfach "none" für Events ohne spezifische Rollen (z.B. Gildenversammlungen, Gatherevents) - es wird dann automatisch eine einfache Teilnehmerliste erstellt

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

Nur der Event-Ersteller kann diese Befehle verwenden. Die automatischen PN-Benachrichtigungen helfen den Teilnehmern, über Änderungen ihrer Rollenzuweisung informiert zu bleiben.

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
- Event-Threads werden 15 Minuten nach Eventbeginn automatisch gelöscht
  - Eine kurze Benachrichtigung wird gesendet, wenn ein Thread gelöscht wurde
  - Diese Nachricht verschwindet nach 5 Minuten automatisch

### Nutzung von Links in Discord

Um Links in Discord klickbar zu machen, verwende die folgende Markdown-Syntax:

- **Klickbarer Link**: `[Linktext](https://example.com)`
  - `[builds](https://docs.google.com/spreadsheets/d/1pNt74V...)`
  - `[Bildbeschreibung](https://de.wikipedia.org/wiki/Fliegender_Fisch_(Sternbild)#/media/Datei:Uranometria_Pavo_et_al.png)`
- Achte darauf, dass keine Leerzeichen zwischen den Klammern sind
- Um ein Bild in deinem Event anzuzeigen, kannst du die `image_url` Option beim `/eventify` Befehl nutzen.

### Event-Kanal Verwaltung

Der Bot hält den Event-Kanal automatisch sauber und übersichtlich:

- **Aufräum-Intervall**: Alle 6 Stunden werden überprüft und entfernt:
  - Normale Nachrichten
  - Event-Übersichten
  - Event-Posts von vergangenen Events
  - Benachrichtigungen und System-Nachrichten

- **Event-Posts bleiben erhalten** solange:
  - Das Event noch nicht stattgefunden hat
  - Der Thread noch aktiv ist (wird 15 Minuten nach Eventbeginn gelöscht)

**Wichtiger Hinweis zur Planung**: 
Aufgrund der Discord-Beschränkung, dass Nachrichten älter als 14 Tage nicht mehr gelöscht werden können, wird darum gebeten, Events nicht weiter als 13 Tage in die Zukunft zu planen. Dies stellt sicher, dass:
- Der Bot alte Event-Posts automatisch entfernen kann
- Keine "verwaisten" Event-Posts zurückbleiben

Events, die weiter in der Zukunft liegen, sollten erst später erstellt werden, um die automatische Kanalpflege zu gewährleisten.

## Beispiele

### Event erstellen
```
/eventify title: Ava Dungeon date: 31122025 time: 1900 mention_role: @Tank image_url: https://example.com/ava-dungeon-builds.png
```

### Rollen-Liste Beispiel
```
(Core)
Stofftank
Plattenhealer
kein Schaden
Spirithunter
Occult
Support
(DPS)
DPS
DPS
DPS
DPS
DPS
DPS
DPS
Partyheal
(Blödsinn)
Zipfelklatscher
DefTank
Irgendwas
Orangenblätter
Cursed
```
