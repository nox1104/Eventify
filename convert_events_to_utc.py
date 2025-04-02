#!/usr/bin/env python3
# convert_events_to_utc.py

import os
import json
from datetime import datetime, timezone
import glob
import logging
from zoneinfo import ZoneInfo

# Setup minimal logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("convert_to_utc")

# Definiere europäische Zeitzone (CET/CEST)
EUROPE_BERLIN = ZoneInfo("Europe/Berlin")

def local_to_utc(dt):
    """Konvertiert CET/CEST zu UTC"""
    if dt.tzinfo is None:
        # Setze Zeitzone explizit auf Europe/Berlin statt Systemzeitzone
        dt = dt.replace(tzinfo=EUROPE_BERLIN)
    return dt.astimezone(timezone.utc)

def create_backup():
    """Erstellt ein Backup der events.json vor der Konvertierung."""
    try:
        # Backup-Ordner erstellen falls nicht vorhanden
        os.makedirs("backups", exist_ok=True)
        
        # Aktueller Zeitstempel für Dateinamen
        timestamp = datetime.now().strftime("%Y%m%d%H%M")
        backup_path = os.path.join("backups", f"events_backup_pre_utc_conversion_{timestamp}.json")
        
        # Pfad zur events.json
        script_dir = os.path.dirname(os.path.abspath(__file__))
        events_file = os.path.join(script_dir, "events.json")
        
        # Datei kopieren
        with open(events_file, 'r', encoding='utf-8') as source:
            with open(backup_path, 'w', encoding='utf-8') as backup:
                backup.write(source.read())
        
        print(f"Backup erstellt: {backup_path}")
        return True
    except Exception as e:
        print(f"Fehler beim Erstellen des Backups: {e}")
        return False

def convert_events():
    print("Konvertiere Events zu UTC mit Europe/Berlin als Quellzeitzone...")
    
    # Backup erstellen
    if not create_backup():
        if input("Backup fehlgeschlagen. Trotzdem fortfahren? (j/N): ").lower() != "j":
            print("Abbruch.")
            return
    
    # Events laden
    script_dir = os.path.dirname(os.path.abspath(__file__))
    events_file = os.path.join(script_dir, "events.json")
    
    with open(events_file, "r", encoding="utf-8") as f:
        events_data = json.load(f)
    
    converted = 0
    updated_ids = 0
    date_time_converted = 0
    
    # Events konvertieren
    for event in events_data["events"]:
        title = event.get("title", "Unbekannt")
        
        # Zeitobjekt verarbeiten
        if "datetime_obj" in event and event["datetime_obj"]:
            try:
                dt = datetime.fromisoformat(event["datetime_obj"])
                if dt.tzinfo is None:
                    old_dt = dt
                    utc_dt = local_to_utc(dt)
                    event["datetime_obj"] = utc_dt.isoformat()
                    converted += 1
                    print(f"Konvertiert: {title}: {old_dt} -> {utc_dt}")
            except Exception as e:
                print(f"Fehler bei der Konvertierung von datetime_obj für {title}: {e}")
        
        # Falls datetime_obj fehlt, aus date und time versuchen
        elif "date" in event and "time" in event:
            try:
                date_str = event["date"]
                time_str = event["time"]
                
                # Date parsen
                if "." in date_str:
                    day, month, year = map(int, date_str.split("."))
                else:
                    try:
                        day = int(date_str[:2])
                        month = int(date_str[2:4])
                        year = int(date_str[4:])
                    except (ValueError, IndexError):
                        print(f"Ungültiges Datumsformat für {title}: {date_str}")
                        continue
                
                # Time parsen
                if ":" in time_str:
                    hour, minute = map(int, time_str.split(":"))
                else:
                    try:
                        hour = int(time_str[:2])
                        minute = int(time_str[2:])
                    except (ValueError, IndexError):
                        print(f"Ungültiges Zeitformat für {title}: {time_str}")
                        continue
                
                # DateTime mit Europe/Berlin Zeitzone erstellen
                local_dt = datetime(year, month, day, hour, minute, tzinfo=EUROPE_BERLIN)
                utc_dt = local_dt.astimezone(timezone.utc)
                
                # Zum Event hinzufügen
                event["datetime_obj"] = utc_dt.isoformat()
                date_time_converted += 1
                print(f"Aus Datum/Zeit konvertiert: {title}: {date_str} {time_str} -> {utc_dt}")
                
            except Exception as e:
                print(f"Fehler bei der Erstellung von datetime_obj aus Datum/Zeit für {title}: {e}")
        
        # Event-ID aktualisieren
        if "event_id" in event and "datetime_obj" in event:
            parts = event["event_id"].split("-")
            if len(parts) == 2 and len(parts[0]) == 12 and parts[0].isdigit():
                try:
                    # Neue event_id mit UTC-Timestamp erstellen
                    utc_dt = datetime.fromisoformat(event["datetime_obj"])
                    new_timestamp = utc_dt.strftime("%Y%m%d%H%M")
                    
                    if new_timestamp != parts[0]:
                        old_id = event["event_id"]
                        event["event_id"] = f"{new_timestamp}-{parts[1]}"
                        updated_ids += 1
                        print(f"ID aktualisiert: {title}: {old_id} -> {event['event_id']}")
                except Exception as e:
                    print(f"ID-Fehler bei {title}: {e}")
    
    # Speichern
    if converted > 0 or updated_ids > 0 or date_time_converted > 0:
        print(f"{converted} datetime_obj konvertiert, {date_time_converted} aus Datum/Zeit erstellt und {updated_ids} IDs aktualisiert.")
        with open(events_file, "w", encoding="utf-8") as f:
            json.dump(events_data, f, indent=4)
        print("Fertig!")
    else:
        print("Keine Änderungen notwendig.")

if __name__ == "__main__":
    convert_events() 