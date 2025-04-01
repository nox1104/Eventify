#!/usr/bin/env python3
# convert_events_to_utc.py

import os
import json
from datetime import datetime, timezone

def local_to_utc(local_dt):
    """Konvertiert lokale Zeit zu UTC"""
    if local_dt.tzinfo is None:
        # Wenn keine Zeitzone, als lokale Zeit betrachten
        local_dt = local_dt.astimezone()
    # Nach UTC konvertieren
    return local_dt.astimezone(timezone.utc)

def convert_events():
    print("Starte Konvertierung der Events von lokaler Zeit zu UTC...")
    
    # Pfad zur events.json
    script_dir = os.path.dirname(os.path.abspath(__file__))
    events_file = os.path.join(script_dir, "events.json")
    
    if not os.path.exists(events_file):
        print("events.json nicht gefunden!")
        return
    
    # Events laden
    try:
        with open(events_file, "r", encoding="utf-8") as f:
            events_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"FEHLER: events.json ist keine gültige JSON-Datei: {e}")
        return
    except Exception as e:
        print(f"FEHLER beim Laden von events.json: {e}")
        return
    
    if "events" not in events_data:
        print("FEHLER: events.json hat kein 'events' Feld!")
        return
    
    converted_count = 0
    updated_event_ids = 0
    
    # Events konvertieren
    for event in events_data["events"]:
        title = event.get("title", "Unbekanntes Event")
        
        # Zeitobjekt verarbeiten
        if "datetime_obj" in event and event["datetime_obj"]:
            try:
                # Zeit parsen und in UTC konvertieren
                dt = datetime.fromisoformat(event["datetime_obj"])
                
                # Falls keine Zeitzone, lokale Zeit annehmen und zu UTC konvertieren
                if dt.tzinfo is None:
                    old_dt = dt
                    utc_dt = local_to_utc(dt)
                    event["datetime_obj"] = utc_dt.isoformat()
                    converted_count += 1
                    print(f"Konvertiert: {title}: {old_dt} -> {utc_dt}")
                else:
                    print(f"Übersprungen: {title} hat bereits Zeitzone: {dt}")
            except Exception as e:
                print(f"FEHLER bei Event {title}: {e}")
        else:
            print(f"Übersprungen: {title} hat kein datetime_obj")
        
        # Event-ID aktualisieren, wenn nötig
        if "event_id" in event and event["datetime_obj"]:
            try:
                # Extrahiere Timestamp-Teil der event_id
                event_id = event["event_id"]
                parts = event_id.split("-")
                
                if len(parts) == 2:
                    timestamp_str, random_part = parts
                    
                    # Nur anpassen, wenn der Timestamp ein gültiges Format hat
                    if len(timestamp_str) == 12 and timestamp_str.isdigit():
                        # Parse datetime from event_id
                        try:
                            id_dt = datetime.strptime(timestamp_str, "%Y%m%d%H%M")
                            # UTC datetime aus dem aktualisierten datetime_obj
                            utc_dt = datetime.fromisoformat(event["datetime_obj"])
                            
                            # Neue event_id erstellen
                            new_timestamp = utc_dt.strftime("%Y%m%d%H%M")
                            
                            # Wenn sich der Timestamp geändert hat
                            if new_timestamp != timestamp_str:
                                event["event_id"] = f"{new_timestamp}-{random_part}"
                                updated_event_ids += 1
                                print(f"ID aktualisiert: {title}: {event_id} -> {new_timestamp}-{random_part}")
                        except Exception as e:
                            print(f"FEHLER bei ID-Aktualisierung von {title}: {e}")
            except Exception as e:
                print(f"FEHLER bei Event-ID Verarbeitung für {title}: {e}")
    
    # Events speichern
    if converted_count > 0 or updated_event_ids > 0:
        print(f"{converted_count} Events konvertiert, {updated_event_ids} Event-IDs aktualisiert. Speichere...")
        try:
            with open(events_file, "w", encoding="utf-8") as f:
                json.dump(events_data, f, indent=4)
            print("Konvertierung erfolgreich abgeschlossen!")
        except Exception as e:
            print(f"FEHLER beim Speichern: {e}")
    else:
        print("Keine Events zu konvertieren.")

if __name__ == "__main__":
    convert_events() 