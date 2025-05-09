# Eventify - Benutzerhandbuch

## Für Volans (Teilnehmer)

Als Teilnehmer brauchst du nur die ersten paar Zeilen zu lesen. Lass dich nicht abschrecken. Es ist wirklich einfach.

### Für eine Rolle anmelden

1. Gehe in den Event-Thread
2. Schreibe die Nummer der Rolle, für die du dich anmelden möchtest (z.B. `1` für die erste Rolle)
3. Optional kannst du einen Kommentar hinzufügen, indem du nach der Nummer einen Text schreibst 
   - z.B. `1 Komme etwas später` oder `15 mh, irh`
   - @-Zeichen in Kommentaren werden automatisch entfernt, um Discord-Erwähnungen zu vermeiden
4. Wenn du bereits für eine andere Rolle angemeldet bist, wirst du automatisch von dieser abgemeldet und für die neue Rolle angemeldet

### Für FillALL anmelden

1. Gehe in den Event-Thread
2. Schreibe die Nummer der FillALL-Rolle (die letzte Nummer in der Liste)
3. Wenn du dich für eine reguläre Rolle anmeldest, wirst du automatisch von FILLALL abgemeldet (und umgekehrt)

### Von einer Rolle abmelden

1. Gehe in den Event-Thread
2. Schreibe oder `-`, um dich von allen Rollen abzumelden

### Teilnehmer verwalten

Im Event-Thread kann jeder Benutzer andere Teilnehmer hinzufügen oder entfernen (bitte gehe damit verantwortungsvoll um):

#### Teilnehmer hinzufügen:
1. Verwende im Event-Thread den Befehl `/add`
2. Gib folgende Parameter ein:
   - `user`: Der Discord-Benutzer, den du hinzufügen möchtest (per Autocomplete)
   - `role_number`: Die Nummer der Rolle, z.B. 1 für die erste Rolle
   - `comment` (optional): Ein Kommentar, der neben dem Namen angezeigt wird (auf 30 Zeichen begrenzt)
3. Der hinzugefügte Teilnehmer erhält automatisch eine private Nachricht mit:
   - Zugewiesene Rolle
   - Event-Titel
   - Datum und Uhrzeit
   - Kommentar (falls vorhanden)
   - Link zum Event
4. Im Thread erscheint eine Nachricht

#### Teilnehmer entfernen:
1. Verwende im Event-Thread den Befehl `/remove`
2. Gib folgende Parameter ein:
   - `user`: Der Discord-Benutzer, den du entfernen möchtest
   - `comment` (optional): Ein Kommentar, der in der DM an den entfernten Benutzer gesendet wird
3. Der entfernte Teilnehmer erhält automatisch eine private Nachricht mit:
   - Event-Titel
   - Entfernte Rolle
   - Kommentar (falls vorhanden)
   - Datum und Uhrzeit
   - Link zum Event
4. Im Thread erscheint eine Nachricht

### Teilnehmer erinnern

1. Gehe in den Event-Thread
2. Verwende den Slash-Befehl `/remind`
   - Optional kannst du eine zusätzliche Nachricht mit `comment:` hinzufügen
   - Beispiel: `/remind comment: Denkt an eure Buffs und Tränke!`
3. Der Bot sendet dann:
   - Eine private Nachricht an alle eingetragenen Teilnehmer mit:
     - **Erinnerung** an Event: Titel
     - Datum und Uhrzeit
     - Deine zusätzliche Nachricht (falls angegeben)
     - Link zum Event
   - Eine Nachricht im Thread: "**user** hat alle Teilnehmer per DN an das Event erinnert."
   - Kommentar: (falls vorhanden)

### Rollen vorschlagen

Als Teilnehmer kannst du zusätzliche Rollen für ein Event vorschlagen:

1. Verwende im Event-Thread den Befehl `/propose`
2. Gib den Namen der neuen Rolle ein:
   - `role_name`: Der Name der Rolle, die du vorschlagen möchtest (`role_name: Plattenheiler`)

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

3. **Nur-Teilnehmer** siehe weiter unten (mit `description:` aber ohne `roles:`)
   ```
   /eventify title: date: time: description:
   ```

Folgende Parameter sind verfügbar:

- `title`: Der Titel des Events (maximale Länge: 40 Zeichen)
- `date`: Das Datum des Events im Format DDMMYYYY (oder DD.MM.YYYY)
- `time`: Die Uhrzeit des Events im Format HHMM (oder HH:MM)
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
    - Bei Bildern von GoogleDrive muss man sich leider selbst den Link zusammenfügen, da es sich sonst nicht um einen direkten Link handelt:
    - `https://drive.google.com/uc?id=DATEI-ID`

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

### Event bearbeiten

1. Gehe in den Event-Thread
2. Verwende den Slash-Befehl `/edit`
3. Im erscheinenden Formular kannst du folgende Aspekte deines Events bearbeiten:
   - Titel des Events
   - Beschreibung des Events
4. Nach dem Speichern wird das Event automatisch aktualisiert
5. Nur der Ersteller des Events kann diesen Befehl verwenden
6. Alle angemeldeten Teilnehmer erhalten eine Nachricht

### Event absagen

1. Gehe in den Event-Thread
2. Verwende den Slash-Befehl `/cancel`
   - Optional kannst du einen Grund für die Absage mit `reason:` hinzufügen
   - Beispiel: `/cancel reason: Event muss wegen Willes abgesagt werden`
3. Der Bot führt dann automatisch folgende Aktionen aus:
   - Der Titel des Events wird mit `[ABGESAGT]` markiert
   - Alle angemeldeten Teilnehmer erhalten eine private Nachricht mit:
     - **Event abgesagt:** Titel
     - Datum und Zeit
     - Den angegebenen Grund (falls vorhanden, dieser wird fett hervorgehoben)
     - Link zum Event-Post
   - Das Event wird aus der Eventübersicht entfernt

### Rollenbesetzung anzeigen

Die Anzahl der besetzten Rollen wird automatisch am Anfang der Rollenliste angezeigt:
- Die erste Zahl zeigt, wie viele Rollen besetzt sind
- Die zweite Zahl zeigt die Gesamtzahl der verfügbaren Rollen
- Beispiel: "Rollen 4/5" bedeutet, dass 4 von 5 Rollen besetzt sind
- Es können überzählige Personen angezeigt werden (8/7). Wer sich zusätzlich anmeldet ist somit auf der Ersatzbank.

Beachte: Ein Spieler kann entweder in einer regulären Rolle ODER in FILLALL eingetragen sein, nicht in beiden gleichzeitig.

### Zeitlimitierung nach Eventbeginn

Die Threads für Events bleiben für 3 Stunden nach dem Eventbeginn bestehen, damit ihr auch nach dem Event noch Bilder teilen und euch unterhalten könnt. Um jedoch ein versehentliches Anmelden für vergangene Events oder andere Missverständnisse zu vermeiden, geschieht Folgendes:

- **Zum Eventzeitpunkt** verschwinden Events aus der Eventübersicht.
- **Für 3 Stunden nach Eventbeginn** bleibt der Event-Thread zugänglich und Interaktionen sind weiterhin möglich:
  - Anmeldung per Zahl für eine Rolle (z.B. "1", "2 mit Kommentar")
  - Abmeldung per "-" oder "-2"
  - Verwendung aller Event-Befehle im Thread:
    - `/add` - Teilnehmer hinzufügen
    - `/remove` - Teilnehmer entfernen
    - `/remind` - Teilnehmer erinnern
    - `/propose` - Neue Rolle vorschlagen
- **3 Stunden nach Eventbeginn** wird der Event vollständig aus dem System entfernt.

Diese Zeitlimitierung sorgt für eine aufgeräumte Übersicht, die nur aktuelle und zukünftige Events anzeigt, während gleichzeitig genügend Zeit nach dem Event für Kommunikation und Organisation bleibt.

### Formatierung der Beschreibung

Discord erlaubt ja einige Formatierungsoptionen von Markdown. Leider sind in Embeds (also das, wo unsere Events drin angezeigt werden), Überschriften nicht nutzbar. Also `# Überschrift` wird leider genauso auch im Embed erscheinen. Lustigerweise kann man die Verkleinerung verwenden. '-# kleiner Text' wird dann also klein dargestellt. Frag nicht warum, das habe ich tatsächlich aufgegeben. Einige Restriktionen von Discord scheinen tatsächlich keinen Sinn zu ergeben.
[Hier](https://support.discord.com/hc/en-us/articles/210298617-Markdown-Text-101-Chat-Formatting-Bold-Italic-Underline) ist beschrieben, welche Formatierungen Discord uns erlaubt.

### Rollenformatierung

- **Normale Rollen**: Einfach den Namen der Rolle eingeben (z.B. "Tank", "Heiler", "DPS"). Im Modal getrennt durch einen Zeilenumbruch.
- **Abschnittsüberschriften**: In Klammern setzen, z.B. "(Core)" oder "(DPS)"
  - Abschnittsüberschriften werden fett dargestellt und zählen nicht bei der Nummerierung
  - Sie helfen, die Rollen übersichtlich zu gruppieren
- **FillALL-Rolle**: Eine Rolle mit dem Namen "Fill" oder "FillALL" wird automatisch als flexible Rolle erkannt
  - Diese Rolle wird immer ans Ende der Liste verschoben
- **Leere Zeilen**: Werden ignoriert und haben keinen Einfluss auf die Nummerierung
- **Zeilenumbrüche im Direktmodus**: Verwende `\n` für Zeilenumbrüche bei der direkten Eingabe über den `/eventify` Befehl
  - Beispiel für Rollen: `roles: Tank\nHealer\nDPS`
  - Beispiel für Beschreibung: `description: Zeile 1\nZeile 2\nZeile 3`

### Nutzung von Links in Discord

- **Klickbarer Link**: `[Linktext](https://example.com)`
  - `[builds](https://docs.google.com/spreadsheets/d/1pNt74V...)`
  - `[Bildbeschreibung](https://de.wikipedia.org/wiki/Fliegender_Fisch_(Sternbild)#/media/Datei:Uranometria_Pavo_et_al.png)`
  - Wenn der Linktext fett gedruckt sein soll, so sind die Sterne ganz vorn und ganz hinten zu setzen:
    - `**[Bildbeschreibung](https://de.wikipedia.org/wiki/Fliegender_Fisch_(Sternbild)#/media/Datei:Uranometria_Pavo_et_al.png)**`
  - Achte darauf, dass keine Leerzeichen zwischen den Klammern sind
  - Um ein Bild in deinem Event anzuzeigen, kannst du die `image_url` Option beim `/eventify` Befehl nutzen.
- Alternativ kannst du das Bild korrekt benannt ("Tankbuild") in einem Kanal des Servers posten und dann mit Rechtsklick den "Link kopieren" und dann in deine Eventbeschreibung einfügen.

### Event-Kanal Verwaltung

Der Bot hält den Event-Kanal automatisch sauber und übersichtlich:

- **Automatische Bereinigung** – Entfernt automatisch:
  - nach 3 Stunden:
    - Systemnachrichten und Benachrichtigungen
    - Alte Event-Listen
    - Reguläre Nachrichten, die älter als 3 Stunden sind

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

