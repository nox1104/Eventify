# Eventify - Benutzerhandbuch

## Für Volans (Teilnehmer)

Als Teilnehmer brauchst du nur die ersten paar Zeilen zu lesen. Lass dich nicht abschrecken. Es ist wirklich einfach.

### Für eine Rolle anmelden

1. Gehe in den Event-Thread
2. Schreibe die Nummer der Rolle, für die du dich anmelden möchtest (z.B. `1` für die erste Rolle)
3. Optional kannst du einen Kommentar hinzufügen, indem du nach der Nummer einen Text schreibst 
   - z.B. `1 Komme etwas später` oder `15 mh, irh`
   - @-Zeichen in Kommentaren werden automatisch entfernt, um Discord-erwähnungen zu vermeiden
4. Wenn du bereits für eine andere Rolle angemeldet bist, wirst du automatisch von dieser abgemeldet und für die neue Rolle angemeldet

### Für FillALL anmelden

1. Gehe in den Event-Thread
2. Schreibe die Nummer der FillALL-Rolle (die letzte Nummer in der Liste)
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

Mit dem Befehl `/eventify` kannst du ein neues Event erstellen. Du hast zwei Möglichkeiten:

1. **Slash-Befehl**: Gib alle Informationen direkt an (so kannst du dir Templates für wiederkehrende Events bauen, `\n` für Zeilenumbrüche)
   ```
   /eventify title: date: time: description: Wöchentlicher Raid\nBringt Buffs und Flasks mit\nSeid pünktlich! roles: Tank\nHealer\nDPS\nRanged DPS
   ```

2. **Modal-Formular**: Wenn du `description` und `roles` weglässt, öffnet sich ein Formular mit zusätzlichen Eingabefeldern
   ```
   /eventify title: date: time:
   ```

Folgende Parameter sind verfügbar:

- `title`: Der Titel des Events (maximale Länge: 40 Zeichen)
- `date`: Das Datum des Events im Format TT.MM.JJJJ
- `time`: Die Uhrzeit des Events im Format HH:mm
- `description` (optional): Die Beschreibung des Events (mit \n für Zeilenumbrüche)
  - Detaillierte Informationen zum Event
  - Falls eine Rolle ausgewählt wurde, wird diese automatisch am Anfang der Beschreibung erwähnt
  - 1020 Zeichen Platz, danach wird der Text mit "..." abgeschnitten
- `roles` (optional): Liste der Rollen, getrennt durch \n (für den Nur-Teilnehmer-Modus diesen Parameter weglassen, aber description setzen)
  - Liste der verfügbaren Rollen, eine pro Zeile
  - Leerzeilen werden ignoriert
  - Mit Text in Klammern, z.B. "(Core)" setzt man Abschnittsüberschriften
  - Lasse das "Rollen"-Feld einfach leer für Events ohne spezifische Rollen (z.B. Gildenversammlungen, Gatherevents) - es wird dann automatisch eine einfache Teilnehmerliste erstellt
- `mention_role` (optional): Eine Rolle, die beim Event erwähnt werden soll
- `image_url` (optional): Ein Link zu einem Bild, das im Event angezeigt werden soll
  - Das Bild wird unter der Beschreibung angezeigt
  - Unterstützte Bildformate: PNG, JPG, GIF
  - Der Link muss direkt zum Bild führen

In dieser Methode kommt es leider selten vor, dass der Thread nicht gebaut wird. Ich habe Logging implementiert, um die Ursache für diesen Fehler zu finden. 

### Nur-Teilnehmer-Modus

Der Nur-Teilnehmer-Modus ist für Events gedacht, bei denen keine spezifischen Rollen benötigt werden, sondern nur eine einfache Teilnehmerliste:

- **Wann verwenden?** Ideal für Gathern, Versammlungen, Meetings, soziale Treffen oder andere Events, bei denen alle Teilnehmer die gleiche Rolle haben
- **Wie aktivieren?** Lasse einfach das `roles`-Feld leer und fülle mindestens `description` zusätzlich zu den Pflichtfeldern aus
- **Wie funktioniert es?** 
  - Es wird automatisch eine einzelne Rolle namens "Teilnehmer" erstellt
  - Teilnehmer können sich mit der Nummer "1" für das Event anmelden
  - Kommentare sind wie bei normalen Rollen möglich (z.B. "1 komme später")
  - Jeder kann sich eintragen, ohne andere Teilnehmer zu verdrängen (ähnlich wie bei der Fill-Rolle)
- **Besonderheiten:**
  - Der `/propose`-Befehl zum Vorschlagen neuer Rollen ist im Nur-Teilnehmer-Modus nicht verfügbar
  - Die Anzeige ist übersichtlicher, da nur eine einzelne Teilnehmerliste angezeigt wird

### Teilnehmer erinnern

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

### Event absagen

1. Gehe in den Event-Thread
2. Verwende den Slash-Befehl `/cancel`
   - Optional kannst du einen Grund für die Absage mit `reason:` hinzufügen
   - Beispiel: `/cancel reason: Event muss wegen zu wenig Teilnehmern abgesagt werden`
3. Der Bot führt dann automatisch folgende Aktionen aus:
   - Der Titel des Events wird mit `[ABGESAGT]` markiert
   - Alle angemeldeten Teilnehmer erhalten eine private Nachricht mit:
     - Information über die Absage
     - Datum und Uhrzeit des abgesagten Events
     - Den angegebenen Grund (falls vorhanden)
     - Link zum Event-Post
   - Das Event wird aus der Eventübersicht entfernt
   - Eine neue Eventübersicht ohne das abgesagte Event wird erstellt
   - Der Event-Thread wird sofort gelöscht, um zu verhindern, dass sich weitere Teilnehmer anmelden

### Teilnehmer verwalten

Als Event-Ersteller kannst du andere Teilnehmer hinzufügen oder entfernen:

#### Teilnehmer hinzufügen:
1. Verwende im Event-Thread den Befehl `/add`
2. Gib folgende Parameter ein:
   - `user`: Der Discord-Benutzer, den du hinzufügen möchtest (per Autocomplete)
   - `role_number`: Die Nummer der Rolle, z.B. 1 für die erste Rolle
   - `comment` (optional): Ein Kommentar, der neben dem Namen angezeigt wird (auf 20 Zeichen begrenzt)
3. Der hinzugefügte Teilnehmer erhält automatisch eine private Nachricht mit:
   - Event-Titel
   - Zugewiesene Rolle
   - Kommentar (falls vorhanden)
   - Datum und Uhrzeit
   - Link zum Event

#### Teilnehmer entfernen:
1. Verwende im Event-Thread den Befehl `/remove`
2. Gib folgende Parameter ein:
   - `user`: Der Discord-Benutzer, den du entfernen möchtest (per Autocomplete)
   - `role_number` (optional): Die Nummer der Rolle. Wenn nicht angegeben, wird der Teilnehmer aus allen Rollen entfernt
3. Der entfernte Teilnehmer erhält automatisch eine private Nachricht mit:
   - Event-Titel
   - Entfernte Rolle(n)
   - Kommentar (falls vorhanden)
   - Datum und Uhrzeit
   - Link zum Event

### Rollenbesetzung anzeigen

Die Anzahl der besetzten Rollen wird automatisch am Anfang der Rollenliste angezeigt:
- Die erste Zahl zeigt, wie viele Rollen besetzt sind
- Die zweite Zahl zeigt die Gesamtzahl der verfügbaren Rollen
- Beispiel: "Rollen 4/5" bedeutet, dass 4 von 5 Rollen besetzt sind

Die Zählung berücksichtigt:
- Alle besetzten regulären Rollen
- FillALL-Teilnehmer, die nicht in einer regulären Rolle sind
- Teilnehmer, die sowohl in einer regulären Rolle als auch in FillALL sind, werden nur einmal gezählt



### Formatierung der Beschreibung

Discord erlaubt ja einige Formatierungsooptionen von Markdown. Leider sind in Embeds (also das, wo unsere Events drin angezeigt werden), Überschriften nicht nutzbar. Also `# Überschrift` wird leider genauso auch im Embed erscheinen. Lustigerweise kann man die Verkleinerung verwenden. '-# kleiner Text' wird dann also klein dargestellt. Frag nicht warum, das habe ich tatsächlich aufgegeben. Einige Restriktionen von Discord scheinen tatsächlich keinen Sinn zu ergeben.
[Hier](https://support.discord.com/hc/en-us/articles/210298617-Markdown-Text-101-Chat-Formatting-Bold-Italic-Underline) ist beschrieben, welche Formatierungen Discord uns erlaubt.

### Rollenformatierung

- **Normale Rollen**: Einfach den Namen der Rolle eingeben (z.B. "Tank", "Heiler", "DPS")
- **Abschnittsüberschriften**: In Klammern setzen, z.B. "(Core)" oder "(DPS)"
  - Abschnittsüberschriften werden fett dargestellt und zählen nicht bei der Nummerierung
  - Sie helfen, die Rollen übersichtlich zu gruppieren
- **FillALL-Rolle**: Eine Rolle mit dem Namen "Fill" oder "FillALL" wird automatisch als flexible Rolle erkannt
  - Diese Rolle wird immer ans Ende der Liste verschoben
  - Spieler können sich für FillALL zusätzlich zu einer normalen Rolle anmelden
- **Leere Zeilen**: Werden ignoriert und haben keinen Einfluss auf die Nummerierung
- **Zeilenumbrüche im Direktmodus**: Verwende `\n` für Zeilenumbrüche bei der direkten Eingabe über den `/eventify` Befehl
  - Beispiel für Rollen: `roles: Tank\nHealer\nDPS`
  - Beispiel für Beschreibung: `description: Zeile 1\nZeile 2\nZeile 3`

### Nutzung von Links in Discord

Um Links in Discord klickbar zu machen, verwende die folgende Markdown-Syntax:

- **Klickbarer Link**: `[Linktext](https://example.com)`
  - `[builds](https://docs.google.com/spreadsheets/d/1pNt74V...)`
  - `[Bildbeschreibung](https://de.wikipedia.org/wiki/Fliegender_Fisch_(Sternbild)#/media/Datei:Uranometria_Pavo_et_al.png)`
- Achte darauf, dass keine Leerzeichen zwischen den Klammern sind
- Um ein Bild in deinem Event anzuzeigen, kannst du die `image_url` Option beim `/eventify` Befehl nutzen.

### Event-Kanal Verwaltung

Der Bot hält den Event-Kanal automatisch sauber und übersichtlich:

- **Automatische Bereinigung** – Entfernt automatisch:
  - nach 30 Minuten
    - Event-Threads 
  - nach 12 Tagen:
    - Systemnachrichten und Benachrichtigungen
    - Alte Event-Listen
    - Reguläre Nachrichten, die älter als 12 Tage sind
  - Erstellt tägliche Backups der Event-Datei und behält die neuesten 42 Backups

## Beispiele

### Event erstellen mit der Modal-Methode (nur 'title', 'date' und 'time' ausfüllen)
```
/eventify title: date: time: description:
```

### Event nur per Prompt erstellen
```
/eventify title: date: time: description: Wöchentlicher Raid\nBringt Buffs und Flasks mit\nSeid pünktlich! roles: Tank\nHealer\nDPS\nRanged DPS
```
```
/eventify title:Testevent date: time:2000 description:Wöchentlicher Raid\nBringt Food und Pots mit. roles:(Core)\nTank\nHealer\nDPS\nRanged DPS\n(Additional)\nDPS\nDPS\n(Reserve)\nShadowcaller\nLC\nSpirithunter mention_role: image_url:https://historiasdeastronomia.es/vistas/images/artistic/volans.jpg 
```

### Event im Nur-Teilnehmer-Modus erstellen (ohne 'roles', aber mind. 'decription' zusätzlich zu 'title', 'date' und 'time')
```
/eventify title: date: time: description: Monatliches Meeting\nThemen:\n- Gildenbank\n- Events\n- Sonstiges
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
