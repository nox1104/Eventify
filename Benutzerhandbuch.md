# Eventify Bot - Benutzerhandbuch

## Für Event-Ersteller

Als Event-Ersteller kannst du neue Events planen und verwalten. Hier ist, wie du den Bot nutzen kannst:

### Event erstellen

1. Verwende den Slash-Befehl `/eventify` im Event-Kanal
2. Gib die folgenden Informationen ein:
   - `title`: Der Titel deines Events
   - `date`: Das Datum im Format DDMMYYYY (z.B. 31122025 für den 31.12.2025) oder DD.MM.YYYY
   - `time`: Die Uhrzeit im Format HHMM (z.B. 1300 für 13:00 Uhr)

3. Nach dem Absenden öffnet sich ein Modal, in dem du folgende Informationen eingeben kannst:
   - **Beschreibung**: 
     - Detaillierte Informationen zum Event
     - 1020 Zeichen Platz, danach wird der Text mit "..." abgeschnitten
   - **Rollen**: 
     - Liste der verfügbaren Rollen, eine pro Zeile
     - Leerzeilen werden ignoriert
     - Mit Text in Klammern, z.B. "(Core)" setzt man Abschnittsüberschriften

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

## Für Volans (Teilnehmer)

Als Volan kannst du dich für Events anmelden und abmelden. Hier ist, wie du den Bot nutzen kannst:

### Für eine Rolle anmelden

1. Gehe in den Event-Thread
2. Schreibe die Nummer der Rolle, für die du dich anmelden möchtest (z.B. `1` für die erste Rolle)
3. Optional kannst du einen Kommentar hinzufügen, indem du nach der Nummer einen Text schreibst (z.B. `1 Komme etwas später` oder `15 mh, irh`)
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

### Event-Übersicht (geplant)

- Alle anstehenden Events werden im Event-Listing-Kanal angezeigt
- Klicke auf den Thread-Link, um direkt zum Event zu gelangen

## Beispiele

### Event erstellen
```
/eventify title: Ava Dungeon date: 31122025 time: 1900
```

### Rollen-Liste Beispiel
```
(Core)
Tank
Heiler
Damage
(Support)
Arcane
Frost
Nature
(DPS)
DPS
DPS
DPS
```

### Für eine Rolle anmelden
```
1
```
oder mit Kommentar:
```
1 Komme 5 Minuten später
```

### Abmelden
```
!unregister
```
oder
```
-
```
