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
    - Beschreibung: 
        - Detaillierte Informationen zum Event
        - 1020 Zeichen Platz, danach wird der Text mit "..." abgeschnitten
    - Rollen: 
        - Liste der verfügbaren Rollen
        - eine Rolle pro Zeile
        - Leerzeilen werden ignoriert
        - Mit Text in Klammern, z.B. "(Core)" setzt man Überschriften

### Rollenformatierung

- **Normale Rollen**: Einfach den Namen der Rolle eingeben (z.B. "Tank", "Heiler", "DPS")
- **Abschnittsüberschriften**: In Klammern setzen, z.B. "(Core)" oder "(DPS)"
- **FillALL-Rolle**: Eine Rolle mit dem Namen "Fill" oder "FillALL" wird automatisch als flexible Rolle erkannt.
- **Leere Zeilen**: Werden ignoriert

### Event verwalten

- Der Bot erstellt automatisch einen Thread für dein Event
- Im Thread kannst du weitere Informationen teilen und mit den Teilnehmern kommunizieren
- Das Event wird automatisch in der Event-Liste angezeigt

## Für Volans (Teilnehmer)

Als Volan kannst du dich für Events anmelden und abmelden. Lies hier, wie das funktioniert.

### Für eine Rolle anmelden

1. Gehe in den Event-Thread
2. Schreibe die Nummer der Rolle, für die du dich anmelden möchtest (z.B. `1` für die erste Rolle)
3. Optional kannst du einen Kommentar hinzufügen, indem du nach der Nummer einen Text schreibst (z.B. `1 Komme etwas später` oder `15 mh, irh`)

### Von einer Rolle abmelden

1. Gehe in den Event-Thread
2. Schreibe `-` (Minus), um dich von allen Rollen abzumelden (z.B DPS und FillALL)
3. Oder schreibe `-X`, wobei X die Nummer der Rolle ist, von der du dich abmelden möchtest

## Tipps und Tricks

- Threads werden automatisch gelöscht, wenn das Event startet
- Wenn du dich für eine neue Rolle anmeldest, wirst du automatisch von deiner vorherigen Rolle abgemeldet
