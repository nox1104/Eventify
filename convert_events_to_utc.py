#!/usr/bin/env python3
# convert_events_to_utc.py

import os
import json
from datetime import datetime, timezone
import glob
import logging

# Setup minimal logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("convert_to_utc")

def local_to_utc(dt):
    """Konvertiert lokale Zeit zu UTC"""
    return dt.astimezone() if dt.tzinfo is None else dt.astimezone(timezone.utc)

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
    print("Konvertiere Events zu UTC...")
    
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
                print(f"Fehler bei {title}: {e}")
        
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
    if converted > 0 or updated_ids > 0:
        print(f"{converted} Events und {updated_ids} IDs konvertiert.")
        with open(events_file, "w", encoding="utf-8") as f:
            json.dump(events_data, f, indent=4)
        print("Fertig!")
    else:
        print("Keine Änderungen notwendig.")

if __name__ == "__main__":
    convert_events() 