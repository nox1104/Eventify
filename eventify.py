import discord
from discord import app_commands
from dotenv import load_dotenv
import os
from datetime import datetime, time, timedelta, timezone
import json
import logging
import uuid  # For generating random IDs
from discord.ext import tasks
import asyncio
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import glob
import copy
import re
from zoneinfo import ZoneInfo

"""
LANGUAGE POLICY:
- All code, logs, and code comments (# comments) must be in English
- All user-facing messages (Discord output) must be in German
- This ensures maintainability for developers while keeping the bot accessible to German-speaking users
- When adding new features or messages, follow this policy strictly
"""

# Logging configuration
def setup_logging():
    # Create logs folder if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Create formatter for consistent log format
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Use TimedRotatingFileHandler to rotate at midnight UTC
    log_filename = 'logs/eventify.log'
    file_handler = TimedRotatingFileHandler(
        log_filename,
        when='midnight',     # Rotate at midnight
        interval=1,          # Rotate every day
        backupCount=42,      # Keep 42 days of logs
        encoding='utf-8',
        utc=True             # Use UTC time for rotation
    )
    # Set a custom suffix with date
    file_handler.suffix = "%Y%m%d"  # This will append date to the rotated log files
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console Handler (for terminal output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Configure Discord logger
    discord_logger = logging.getLogger('discord')
    discord_logger.setLevel(logging.INFO)

    # Create custom logger for Eventify
    eventify_logger = logging.getLogger('eventify')
    eventify_logger.setLevel(logging.INFO)

    return eventify_logger

# Call at the beginning of the script
logger = setup_logging()

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
AUTHORIZED_GUILD_ID = int(os.getenv("AUTHORIZED_GUILD_ID", "0"))  # Default to 0 if not set
CHANNEL_ID_EVENT = int(os.getenv("CHANNEL_ID_EVENT"))
EVENTS_JSON_FILE = "events.json"

# Set up proper intents
intents = discord.Intents.default()
intents.guilds = True  # Important for slash command sync
intents.messages = True  # Allow the bot to see messages
intents.message_content = True  # Allow the bot to read message content

# Definiere europäische Zeitzone (CET/CEST)
EUROPE_BERLIN = ZoneInfo("Europe/Berlin")

# UTC conversion helper functions
def local_to_utc(local_dt, is_date_time_string=False, date_str=None, time_str=None):
    """
    Konvertiert CET/CEST zu UTC mit korrekter Behandlung von Sommer/Winterzeit
    
    Args:
        local_dt: Lokales Datetime-Objekt oder None wenn Strings verwendet werden
        is_date_time_string: True wenn separate Datums- und Zeitstrings verwendet werden
        date_str: Datumsstring im Format "DD.MM.YYYY" oder "DDMMYYYY"
        time_str: Zeitstring im Format "HH:MM" oder "HHMM"
    """
    # Bei Verwendung von Strings für Datum/Zeit (über Slash-Befehle oder Modal)
    if is_date_time_string and date_str and time_str:
        try:
            # Parse date (format: DD.MM.YYYY or DDMMYYYY)
            if "." in date_str:
                day, month, year = map(int, date_str.split("."))
            else:
                day = int(date_str[:2])
                month = int(date_str[2:4])
                year = int(date_str[4:])
            
            # Parse time (format: HH:MM or HHMM)
            if ":" in time_str:
                hour, minute = map(int, time_str.split(":"))
            else:
                hour = int(time_str[:2])
                minute = int(time_str[2:])
            
            # Erstelle Datetime mit Europe/Berlin Zeitzone
            # Dies berücksichtigt automatisch, ob das Datum in Sommer- oder Winterzeit fällt
            local_dt = datetime(year, month, day, hour, minute, tzinfo=EUROPE_BERLIN)
            logger.info(f"Converted local time {local_dt} (Europe/Berlin) to UTC")
            return local_dt.astimezone(timezone.utc)
        except Exception as e:
            logger.error(f"Error converting date/time strings to UTC: {e}")
            return None
    
    # Bei Verwendung eines vorhandenen Datetime-Objekts
    if local_dt:
        if local_dt.tzinfo is None:
            # Setze Zeitzone auf Europe/Berlin
            local_dt = local_dt.replace(tzinfo=EUROPE_BERLIN)
        return local_dt.astimezone(timezone.utc)
    
    return None

def utc_to_local(utc_dt):
    """Konvertiert UTC zu CET/CEST basierend auf dem Datum"""
    if utc_dt is None:
        return None
        
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    
    # Konvertiere nach Europe/Berlin, berücksichtigt automatisch DST
    return utc_dt.astimezone(EUROPE_BERLIN)

def format_local_datetime(utc_dt):
    """Formatiert UTC-Zeit zur lokalen Anzeige in CET/CEST"""
    local_dt = utc_to_local(utc_dt)
    if local_dt is None:
        return {
            "date": None,
            "time": None,
            "datetime": None
        }
    return {
        "date": local_dt.strftime("%d.%m.%Y"),
        "time": local_dt.strftime("%H:%M"),
        "datetime": local_dt
    }

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        """Called when the bot is online"""
        logger.info(f"{self.user} is now online.")
        
        # Check and leave unauthorized servers
        if AUTHORIZED_GUILD_ID == 0:
            logger.warning("AUTHORIZED_GUILD_ID not set in .env file. Bot will run on any server.")
        else:
            for guild in self.guilds:
                if guild.id != AUTHORIZED_GUILD_ID:
                    logger.warning(f"Leaving unauthorized server: {guild.name} (ID: {guild.id})")
                    
                    # Try to send a message to the server owner
                    try:
                        owner = guild.owner
                        if owner:
                            leave_message = (
                                f"Hello {owner.name},\n\n"
                                f"I am a specialized event management bot exclusively developed for a specific community. "
                                f"Since I'm not configured for use on other servers, I need to leave this server.\n\n"
                                f"If you're interested in this bot or have any questions, "
                                f"please contact my developer on Discord: **nox1104**\n\n"
                                f"Thank you for your understanding."
                            )
                            await owner.send(leave_message)
                            logger.info(f"Sent farewell message to {owner.name} on server {guild.name}")
                    except Exception as e:
                        logger.error(f"Could not send message to server owner: {e}")
                    
                    # After attempting to send the message, leave the server
                    await guild.leave()
                else:
                    logger.info(f"Bot is on authorized server: {guild.name} (ID: {guild.id})")
                    
        print(f"Logged in as {self.user}")
        await self.tree.sync()
        print("Slash commands synchronized!")
        print("Bot is ready and listening for messages.")
        
        # Sofort beim Start Events überprüfen und bereinigen
        try:
            # Überprüfe Ereignisse sofort
            logger.info("Checking for expired events at startup...")
            events_data = load_upcoming_events(include_expired=True, include_cleaned=False)
            updated_data = clean_old_events(events_data)
            
            # Speichern und Übersicht aktualisieren
            save_events_to_json(updated_data)
            
            # Aktualisiere die Eventübersicht in allen Guilds
            for guild in self.guilds:
                await create_event_listing(guild)
                
            logger.info("Initial event checks and cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during initial event cleanup: {e}")
        
        # Start the loops
        self.check_expired_events.start()
        self.cleanup_event_channel.start()  # New loop added

    async def on_message(self, message):
        try:
            # Ignore messages from the bot itself
            if message.author == self.user:
                logger.info(f"Ignoring message from self")
                return

            # Get the channel name for logging
            channel_name = message.channel.name if hasattr(message.channel, 'name') else 'Unknown'
            logger.info(f"Message received: {message.content} in channel: {channel_name}")

            # Check if message is in a thread
            if not isinstance(message.channel, discord.Thread):
                return

            thread_id = message.channel.id
            
            # Load events from JSON (auch abgelaufene Events einschließen, damit Anmeldungen nach Eventstart möglich sind)
            events_data = load_upcoming_events(include_expired=True)
            if not events_data or "events" not in events_data:
                return
                
            # Find the event for this thread
            event = next((e for e in events_data["events"] if str(e.get('thread_id')) == str(thread_id)), None)
            
            if not event:
                return
                
            # Prüfe, ob mehr als 1 Stunde seit Eventbeginn vergangen ist
            try:
                # Event-Zeit direkt aus datetime_obj verwenden
                event_dt = datetime.fromisoformat(event.get('datetime_obj'))
                now = datetime.now(timezone.utc)
                
                # Wenn mehr als 1 Stunde seit Eventbeginn vergangen ist, keine Zahlenanmeldungen mehr zulassen
                if now > event_dt + timedelta(hours=1):
                    # Nur Zahlenanmeldungen blockieren
                    if message.content.strip().isdigit() or (message.content.strip() and message.content.strip()[0].isdigit()):
                        await message.add_reaction('❌')  # Zeitsymbol als Reaktion
                        await message.add_reaction('⏱️')  # Zeitsymbol als Reaktion
                        await message.author.send(f"Anmeldungen für das Event **{event.get('title')}** sind nicht mehr möglich, da das Event vor über einer Stunde begonnen hat.")
                        logger.info(f"Blocked registration from {message.author.name} - event {event.get('title')} started more than 1 hour ago")
                        return
                    
                    # Für Abmeldungen (- oder -X) ebenfalls blockieren
                    if message.content.strip() == '-' or (message.content.strip().startswith('-') and message.content.strip()[1:].isdigit()):
                        await message.add_reaction('❌')  # Zeitsymbol als Reaktion
                        await message.add_reaction('⏱️')  # Zeitsymbol als Reaktion
                        await message.author.send(f"Abmeldungen für das Event **{event.get('title')}** sind nicht mehr möglich, da das Event vor über einer Stunde begonnen hat.")
                        logger.info(f"Blocked unregistration from {message.author.name} - event {event.get('title')} started more than 1 hour ago")
                        return
            except Exception as e:
                logger.error(f"Error checking event time for registration limit: {e}")
                # Im Fehlerfall Anmeldungen dennoch erlauben

            # Process role signup (single digit number)
            if message.content.strip().isdigit():
                await self._handle_role_signup(message, event['title'], int(message.content))
                
            # Process role signup with comment (number followed by text)
            elif message.content.strip() and message.content.strip()[0].isdigit():
                # Extract the number part
                parts = message.content.strip().split(' ', 1)
                if parts[0].isdigit():
                    await self._handle_role_signup(message, event['title'], int(parts[0]))
                
            # Process role unregister
            elif message.content.strip() == '-':
                await self._handle_unregister(message)
                
            # Process specific role unregister (e.g., "-2" to unregister from role 2)
            elif message.content.strip().startswith('-') and message.content[1:].isdigit():
                role_number = int(message.content[1:])
                await self._handle_unregister(message, is_specific_role=True, role_number=role_number)
                
        except Exception as e:
            logger.error(f"Error in on_message: {e}")
            logger.exception("Full traceback:")

    async def _handle_role_signup(self, message, event_title, role_number):
        try:
            # Zunächst Standard-Berechnung
            visual_role_number = role_number
            
            # Load events from JSON (auch abgelaufene Events einschließen, damit Anmeldungen nach Eventstart möglich sind)
            events_data = load_upcoming_events(include_expired=True)
            logger.info(f"Loaded events data from JSON")
            
            # First try to find the event by thread_id (most reliable)
            thread_id = message.channel.id
            event = next((e for e in events_data["events"] if e.get('thread_id') == thread_id), None)
            
            # Fallback: try to find by title (for backwards compatibility)
            if not event:
                event = next((e for e in events_data["events"] if e.get('title') == event_title), None)
            
            if event:
                # Prüfe, ob das Event abgesagt wurde
                if event.get('status') == "canceled" or "[ABGESAGT]" in event.get('title', ''):
                    await message.add_reaction('❌')
                    await message.author.send(f"Dieses Event wurde bereits abgesagt. Anmeldungen sind nicht mehr möglich.")
                    return
                
                # Prüfe, ob mehr als 1 Stunde seit Eventbeginn vergangen ist
                try:
                    # Event-Zeit direkt aus datetime_obj verwenden
                    event_dt = datetime.fromisoformat(event.get('datetime_obj'))
                    now = datetime.now(timezone.utc)
                    
                    # Wenn mehr als 1 Stunde seit Eventbeginn vergangen ist, Anmeldungen blockieren
                    if now > event_dt + timedelta(hours=1):
                        # Benutzer informieren
                        await message.add_reaction('❌')
                        await message.author.send(f"Anmeldungen sind nicht mehr möglich, da das Event vor über einer Stunde begonnen hat.")
                        logger.info(f"Blocked role signup from {message.author.name} - event {event.get('title')} started more than 1 hour ago")
                        return
                except Exception as e:
                    logger.error(f"Error checking event time for role signup: {e}")
                    # Im Fehlerfall Anmeldung trotzdem erlauben
                
                # Berechne den korrekten Rollenindex unter Berücksichtigung der Überschriften
                role_index = -1
                header_count = 0
                
                for i, role in enumerate(event['roles']):
                    # Überschriften in Klammern überspringen
                    if role.startswith('(') and role.endswith(')'):
                        header_count += 1
                        continue
                    
                    # Zählen der normalen Rollen
                    if (i - header_count + 1) == visual_role_number:
                        role_index = i
                        break
                
                if role_index == -1:
                    logger.warning(f"Invalid role number: {visual_role_number}. Event has {len(event['roles']) - header_count} roles.")
                    await message.channel.send(f"Ungültige Rollennummer: {visual_role_number}. Das Event hat {len(event['roles']) - header_count} Rollen.", delete_after=10)
                    return
                
                logger.info(f"Found matching event: {event['title']} (ID: {event.get('event_id', 'unknown')})")
                
                # Check if we're in participant_only_mode
                is_participant_only = event.get('participant_only_mode', False)
                
                # Check if this is the "Fill" role by name instead of position
                is_fill_role = False
                if 0 <= role_index < len(event['roles']):
                    is_fill_role = event['roles'][role_index].lower() == "fill" or event['roles'][role_index].lower() == "fillall"
                
                # In participant_only_mode, treat the participant role like Fill (but NOT like FillALL)
                # This allows comments in participant_only_mode
                if is_participant_only:
                    is_fill_role = True
                    # Don't set FillALL to allow comments
                    is_fillall_role = False
                
                if 0 <= role_index < len(event['roles']):
                    role_name = event['roles'][role_index]
                    player_name = message.author.name
                    player_id = str(message.author.id)
                    current_time = datetime.now().timestamp()  # For sorting by signup time

                    # Extract optional comment if any
                    # Look for the first space after the role number
                    if ' ' in message.content:
                        # The comment is everything after the first space
                        comment = message.content.split(' ', 1)[1].strip()
                        # Remove all @ characters from comments
                        comment = comment.replace('@', '')
                        logger.info(f"Extracted comment: '{comment}'")
                    else:
                        comment = ""
                    
                    logger.info(f"Assigning {player_name} to role {role_name} at index {role_index} with comment: {comment}")
                    
                    # Initialize participants dict if needed
                    if 'participants' not in event:
                        event['participants'] = {}
                        
                    # Use role_index as part of the key for participants to handle duplicate role names
                    role_key = f"{role_index}:{role_name}"
                    
                    if role_key not in event['participants']:
                        event['participants'][role_key] = []
                    
                    # Check if player is already signed up for this role
                    existing_entry = next((i for i, entry in enumerate(event['participants'][role_key]) 
                                         if entry[1] == player_id), None)
                    
                    if existing_entry is not None:
                        # Player is already signed up, update comment if provided
                        existing_data = event['participants'][role_key][existing_entry]
                        existing_comment = existing_data[3] if len(existing_data) > 3 else None
                        
                        # If comment is different or provided when none existed before, update it
                        if comment != existing_comment:
                            # Update with comment (name, id, timestamp, comment)
                            event['participants'][role_key][existing_entry] = (existing_data[0], existing_data[1], existing_data[2], comment)
                            await self._update_event_and_save(message, event, events_data)
                            await message.add_reaction('✅')  # Add confirmation reaction
                        else:
                            # Just acknowledge if no change in comment status
                            logger.info(f"{player_name} already assigned to role {role_name} at index {role_index}")
                            await message.add_reaction('ℹ️')  # Info reaction
                            # Send a joke message as DM instead of in channel
                            try:
                                event_link = f"https://discord.com/channels/{message.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                                dm_message = (
                                    f"Für die Rolle **{role_name}** bist du doch schon angemeldet, du Pappnase!\n"
                                    f"Ändere doch wenigstens den Kommentar ;)\n"
                                    f"Event: {event['title']}\n"
                                    f"Datum: {event['date']}\n"
                                    f"Uhrzeit: {event['time']}\n"
                                    f"[Zum Event]({event_link})"
                                )
                                await message.author.send(dm_message)
                            except Exception as e:
                                logger.error(f"Failed to send DM to user {message.author.id}: {e}")
                    else:
                        # For Fill role, no limit on players and can be added even if already registered for another role
                        if is_fill_role:
                            # Check if the role is specifically FillALL (not for participant_only_mode)
                            if not is_participant_only:
                                is_fillall_role = event['roles'][role_index].lower() == "fillall"
                            else:
                                is_fillall_role = False  # In participant_only_mode we allow comments
                            
                            # For FillALL role
                            if is_fillall_role:
                                # Check if player is already signed up for another role (and remove them from it)
                                for r_idx, r_name in enumerate(event['roles']):
                                    # Skip FILLALL roles and headers in the check
                                    if (r_name.lower() == "fill" or r_name.lower() == "fillall" or 
                                        (r_name.startswith('(') and r_name.endswith(')'))):
                                        continue
                                    
                                    r_key = f"{r_idx}:{r_name}"
                                    if r_key in event.get('participants', {}):
                                        # Find and remove the player if present
                                        initial_count = len(event['participants'][r_key])
                                        event['participants'][r_key] = [p for p in event['participants'][r_key] if p[1] != player_id]
                                        if initial_count > len(event['participants'][r_key]):
                                            logger.info(f"Removed {player_name} from role {r_name} when signing up for FILLALL")
                                
                                # Add player to FILLALL role
                                if comment:
                                    # Limit comment to 30 characters for FILLALL roles
                                    if len(comment) > 30:
                                        comment = comment[:30] + "..."
                                    event['participants'][role_key].append((player_name, player_id, current_time, comment))
                                    logger.info(f"Adding {player_name} to FillALL role with comment: '{comment}'")
                                else:
                                    event['participants'][role_key].append((player_name, player_id, current_time))
                                    logger.info(f"Added {player_name} to FillALL role")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events_data)
                                await message.add_reaction('✅')  # Add confirmation reaction
                            else:
                                # This is a regular Fill role (not FillALL) or participant_only_mode
                                # Add new entry with timestamp and comment
                                if comment:
                                    event['participants'][role_key].append((player_name, player_id, current_time, comment))
                                    logger.info(f"Adding {player_name} to role {role_name} with comment: '{comment}'")
                                else:
                                    event['participants'][role_key].append((player_name, player_id, current_time))
                                
                                logger.info(f"Added {player_name} to Fill role or participant_only_mode")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events_data)
                                await message.add_reaction('✅')  # Add confirmation reaction
                        else:
                            # For normal roles, check if player is already signed up for FILLALL and remove them
                            fillall_removed = False
                            for r_idx, r_name in enumerate(event['roles']):
                                if r_name.lower() == "fill" or r_name.lower() == "fillall":
                                    r_key = f"{r_idx}:{r_name}"
                                    if r_key in event.get('participants', {}):
                                        # Find and remove the player if present
                                        initial_count = len(event['participants'][r_key])
                                        event['participants'][r_key] = [p for p in event['participants'][r_key] if p[1] != player_id]
                                        if initial_count > len(event['participants'][r_key]):
                                            logger.info(f"Removed {player_name} from FILLALL when signing up for role {role_name}")
                                            fillall_removed = True
                            
                            # The rest of the normal role signup continues as before...
                            
                            # Check if player is already signed up for another role (except Fill)
                            already_signed_up = False
                            player_current_role = None
                            player_current_role_key = None
                            
                            for r_idx, r_name in enumerate(event['roles']):
                                if r_name.lower() == "fill" or r_name.lower() == "fillall":
                                    continue  # Skip Fill and FillALL roles
                                
                                r_key = f"{r_idx}:{r_name}"
                                if r_key in event.get('participants', {}):
                                    for entry_idx, entry in enumerate(event['participants'][r_key]):
                                        if entry[1] == player_id:
                                            already_signed_up = True
                                            player_current_role = r_name
                                            player_current_role_key = r_key
                                            player_current_entry_idx = entry_idx
                                            break
                                    if already_signed_up:
                                        break
                            
                            if already_signed_up:
                                # Automatically unregister from previous role
                                logger.info(f"Automatically unregistering {player_name} from role {player_current_role}")
                                
                                # Check if the new role already has participants (except for Fill roles)
                                if not is_fill_role and len(event['participants'][role_key]) > 0:
                                    logger.info(f"Role {role_name} already has a participant, rejecting registration from {player_name}")
                                    await message.add_reaction('ℹ️')  # Rejection reaction
                                    # Send as DM instead of in channel
                                    try:
                                        event_link = f"https://discord.com/channels/{message.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                                        
                                        # Get current role holder info
                                        current_holder = event['participants'][role_key][0]
                                        current_holder_id = current_holder[1]
                                        current_holder_name = current_holder[0]
                                        
                                        dm_message = (
                                            f"Nene, so geht das nicht. Die Rolle **{role_name}** hat sich bereits **{current_holder_name}** ausgesucht, du Schlingel.\n"                                            f"Event: {event['title']}\n"
                                            f"Datum: {event['date']}\n"
                                            f"Uhrzeit: {event['time']}\n"
                                            f"[Zum Event]({event_link})"
                                        )
                                        await message.author.send(dm_message)
                                    except Exception as e:
                                        logger.error(f"Failed to send DM to user {message.author.id}: {e}")
                                    return
                                
                                # Remove player from previous role
                                event['participants'][player_current_role_key].pop(player_current_entry_idx)
                                
                                # Add player to new role
                                if comment:
                                    event['participants'][role_key].append((player_name, player_id, current_time, comment))
                                else:
                                    event['participants'][role_key].append((player_name, player_id, current_time))
                                
                                logger.info(f"Added {player_name} to role {role_name}")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events_data)
                                await message.add_reaction('✅')  # Add confirmation reaction
                            else:
                                # Check if role already has participants (except for Fill roles)
                                if len(event['participants'][role_key]) > 0:
                                    logger.info(f"Role {role_name} already has a participant, rejecting registration from {player_name}")
                                    await message.add_reaction('ℹ️')  # Rejection reaction
                                    # Send as DM instead of in channel
                                    try:
                                        event_link = f"https://discord.com/channels/{message.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                                        
                                        # Get current role holder info
                                        current_holder = event['participants'][role_key][0]
                                        current_holder_id = current_holder[1]
                                        
                                        
                                        dm_message = (
                                            f"Nene, so geht das nicht. Die Rolle **{role_name}** hat sich bereits <@{current_holder_id}> ausgesucht, du Schlingel.\n"
                                            f"Event: {event['title']}\n"
                                            f"Datum: {event['date']}\n"
                                            f"Uhrzeit: {event['time']}\n"
                                            f"[Zum Event]({event_link})"
                                        )
                                        await message.author.send(dm_message)
                                    except Exception as e:
                                        logger.error(f"Failed to send DM to user {message.author.id}: {e}")
                                    return
                                
                                # Add new entry with timestamp and comment
                                if comment:
                                    event['participants'][role_key].append((player_name, player_id, current_time, comment))
                                    logger.info(f"Adding {player_name} to role {role_name} with comment: '{comment}'")
                                else:
                                    event['participants'][role_key].append((player_name, player_id, current_time))
                                
                                logger.info(f"Added {player_name} to role {role_name}")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events_data)
                                await message.add_reaction('✅')  # Add confirmation reaction
                else:
                    logger.warning(f"Invalid role index: {role_index}. Event has {len(event['roles'])} roles.")
                    # No message to user
            else:
                logger.warning(f"No event found matching thread name: {event_title}")
                await message.channel.send("Kein passendes Event für diesen Thread gefunden.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error processing role assignment: {e}")
            await message.channel.send(f"Fehler bei der Verarbeitung deiner Anfrage: {str(e)}", ephemeral=True)

    async def _handle_unregister(self, message, is_specific_role=False, role_number=None, role_index=None):
        try:
            # Load events from JSON (auch abgelaufene Events einschließen, damit Abmeldungen nach Eventstart möglich sind)
            events_data = load_upcoming_events(include_expired=True)
            
            # First try to find the event by thread_id (most reliable)
            thread_id = message.channel.id
            event = next((e for e in events_data["events"] if e.get('thread_id') == thread_id), None)
            
            # Fallback: try to find by title (for backwards compatibility)
            if not event:
                event_title = message.channel.name
                event = next((e for e in events_data["events"] if e.get('title') == event_title), None)
            
            if not event:
                await message.add_reaction('⚠️')
                await message.channel.send("Kein passendes Event für diesen Thread gefunden.")
                return
            
            # Prüfe, ob das Event abgesagt wurde
            if event.get('status') == "canceled" or "[ABGESAGT]" in event.get('title', ''):
                await message.add_reaction('❌')
                await message.author.send(f"Dieses Event wurde bereits abgesagt. Abmeldungen sind nicht mehr möglich.")
                return
            
            # Prüfe, ob mehr als 1 Stunde seit Eventbeginn vergangen ist
            try:
                # Event-Zeit direkt aus datetime_obj verwenden
                event_dt = datetime.fromisoformat(event.get('datetime_obj'))
                now = datetime.now(timezone.utc)
                
                # Wenn mehr als 1 Stunde seit Eventbeginn vergangen ist, Abmeldungen blockieren
                if now > event_dt + timedelta(hours=1):
                    # Benutzer informieren
                    await message.add_reaction('❌')
                    await message.author.send(f"Abmeldungen sind nicht mehr möglich, da das Event vor über einer Stunde begonnen hat.")
                    logger.info(f"Blocked unregister from {message.author.name} - event {event.get('title')} started more than 1 hour ago")
                    return
            except Exception as e:
                logger.error(f"Error checking event time for unregister: {e}")
                # Im Fehlerfall Abmeldung trotzdem erlauben
            
            player_name = message.author.name
            player_id = str(message.author.id)
            removed_count = 0
            
            # If it's a general unregister from all roles (-)
            if not is_specific_role:
                # Keep track of how many roles the player was removed from
                removed_count = 0
                
                # Check all roles
                for r_idx, r_name in enumerate(event['roles']):
                    r_key = f"{r_idx}:{r_name}"
                    if r_key in event.get('participants', {}):
                        # Check if player is in this role
                        initial_count = len(event['participants'][r_key])
                        event['participants'][r_key] = [p for p in event['participants'][r_key] if p[1] != player_id]
                        removed_count += initial_count - len(event['participants'][r_key])
                
                logger.info(f"Removed {player_name} from {removed_count} roles in event {event['title']}")
                
                # Only reply if player was actually removed from something
                if removed_count > 0:
                    # Update the event message
                    await self._update_event_and_save(message, event, events_data)
                    await message.add_reaction('✅')  # Add confirmation reaction
                else:
                    await message.add_reaction('❓')  # Player wasn't registered
            else:
                # This is a specific role unregister
                # If role_number is provided, convert it to role_index
                if role_number is not None:
                    role_index = self.role_number_to_index(event, role_number)
                
                if role_index is not None and 0 <= role_index < len(event['roles']):
                    role_name = event['roles'][role_index]
                    role_key = f"{role_index}:{role_name}"
                    
                    logger.info(f"Unregistering {player_name} from role {role_name} at index {role_index}")
                    
                    if role_key in event.get('participants', {}):
                        # Find and remove the player from the role
                        initial_count = len(event['participants'][role_key])
                        event['participants'][role_key] = [p for p in event['participants'][role_key] if p[1] != player_id]
                        removed_count = initial_count - len(event['participants'][role_key])
                        
                        if removed_count > 0:
                            logger.info(f"Removed {player_name} from role {role_name}")
                            
                            # Update the event message and save to JSON
                            await self._update_event_and_save(message, event, events_data)
                            await message.add_reaction('✅')  # Add confirmation reaction
                        else:
                            logger.info(f"{player_name} was not registered for role {role_name}")
                            await message.add_reaction('❓')  # Player wasn't registered
                    else:
                        logger.info(f"Role {role_name} has no participants")
                        await message.add_reaction('❓')  # Info reaction
                else:
                    logger.warning(f"Invalid role index: {role_index}. Event has {len(event['roles'])} roles.")
                    await message.add_reaction('❓')  # Invalid role
        except Exception as e:
            logger.error(f"Error processing unregister: {e}")
            await message.channel.send(f"Fehler bei der Verarbeitung deiner Anfrage: {str(e)}", ephemeral=True)

    async def _update_event_and_save(self, message, event, events):
        try:
            # Ensure events is a dictionary with an "events" key
            if isinstance(events, list):
                events = {"events": events}
            elif not isinstance(events, dict) or "events" not in events:
                logger.error("Invalid events format in _update_event_and_save")
                return False

            # If event is a dictionary, recalculate the role counts
            if isinstance(event, dict):
                # Berechne Rollenanzahl über die zentrale Hilfsfunktion
                filled_slots, total_slots = calculate_role_counts(event.get('roles', []), event.get('participants', {}))
                
                # Update the counts
                event['total_slots'] = total_slots
                event['filled_slots'] = filled_slots

            # Find the event by ID if available, otherwise by title
            event_id = event.get("event_id")
            if event_id:
                # Find the event in the events list by ID
                for e in events["events"]:
                    if e.get("event_id") == event_id:
                        # Update the event
                        e.update(event)
                        break
            else:
                # Fallback to title for backward compatibility
                for e in events["events"]:
                    if e["title"] == event["title"]:
                        # Update the event
                        e.update(event)
                        break
            
            # Save the updated events
            save_events_to_json(events)
            
            # Update the event message
            thread = message.channel
            await self.update_event_message(thread, event)
            
            # Also refresh the event overview
            if thread.guild:
                await create_event_listing(thread.guild)
            
            return True
        except Exception as e:
            logger.error(f"Error updating event: {e}")
            await message.channel.send(f"Fehler beim Aktualisieren des Events: {e}")
            return False

    async def update_event_message(self, thread, event):
        try:
            logger.info(f"Updating event message for event: {event.get('title') if isinstance(event, dict) else event.title}")
            
            # Get guild and channel
            guild = thread.guild
            event_channel = guild.get_channel(CHANNEL_ID_EVENT)
            
            if not event_channel:
                logger.error(f"Event channel not found in guild {guild.name}")
                return False
            
            # Get the event message
            try:
                if isinstance(event, dict):
                    message_id = event.get("message_id")
                else:
                    message_id = getattr(event, "message_id", None)
                    
                if not message_id:
                    logger.error("No message_id found in event")
                    return False
                    
                event_message = await event_channel.fetch_message(int(message_id))
            except (discord.NotFound, discord.HTTPException) as e:
                logger.error(f"Error fetching event message: {e}")
                return False
            
            # Create the embed with CYAN color - Titel bleibt unterstrichen
            title = event.get('title') if isinstance(event, dict) else event.title
            embed = discord.Embed(title=f"__**{title}**__", color=0x0dceda)
            
            # Get date, time and weekday
            date = event.get('date') if isinstance(event, dict) else getattr(event, 'date', '')
            time = event.get('time') if isinstance(event, dict) else getattr(event, 'time', '')
            weekday = get_weekday_abbr(date)
            
            # Add date and time as inline fields (only these two in the first row)
            embed.add_field(name="Datum", value=f"{date} ({weekday})", inline=True)
            embed.add_field(name="Uhrzeit", value=time, inline=True)
            # Add a blank field to ensure only 2 fields in the first row
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Add creator and mention role as inline fields (in the second row)
            caller_id = event.get('caller_id') if isinstance(event, dict) else getattr(event, 'caller_id', None)
            mention_role_id = event.get('mention_role_id') if isinstance(event, dict) else getattr(event, 'mention_role_id', None)
            
            creator_mention = f"<@{caller_id}>" if caller_id else "Unbekannt"
            
            embed.add_field(name="Von", value=creator_mention, inline=True)
            
            if mention_role_id:
                embed.add_field(name="Für", value=f"<@&{mention_role_id}>", inline=True)
            else:
                # Add an empty field to maintain alignment
                embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Add a blank field to ensure only 2 fields in the second row
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Add description
            description = event.get('description') if isinstance(event, dict) else getattr(event, 'description', '')
            if description:
                if len(description) > 1020:  # Leave room for ellipsis
                    description = description[:1020] + "..."
                embed.add_field(name="Beschreibung", value=description, inline=False)
            
            # Add image if available (direkt nach der Beschreibung)
            image_url = event.get('image_url') if isinstance(event, dict) else getattr(event, 'image_url', None)
            if image_url:
                embed.set_image(url=image_url)
            
            # ===== Role display based on v0.3.4 =====
            roles = event.get('roles', []) if isinstance(event, dict) else getattr(event, 'roles', [])
            participants = event.get('participants', {}) if isinstance(event, dict) else getattr(event, 'participants', {})

            # Check for participant_only_mode
            is_participant_only = event.get('participant_only_mode', False) if isinstance(event, dict) else getattr(event, 'participant_only_mode', False)
            
            # In participant_only mode, we should only display the participant role
            if is_participant_only:
                # In participant_only mode, we show only the first role (should be "Participant")
                if len(roles) > 0:
                    role_idx = 0
                    role_name = roles[0]
                    role_key = f"{role_idx}:{role_name}"
                    
                    # Combine role name and number
                    participant_title = f"1. {role_name}"
                    
                    # Get participant list
                    role_participants = participants.get(role_key, [])
                    
                    # Count unique participants
                    unique_participants = set()
                    for p in role_participants:
                        if len(p) >= 2:
                            unique_participants.add(p[1])
                    participant_count = len(unique_participants)
                    
                    # Combine role name and number with participant count
                    participant_title = f"1. {role_name} ({participant_count})"
                    
                    # If participants are present, format them with comments (different from FillALL)
                    if role_participants:
                        # Sort participants by timestamp
                        sorted_participants = sorted(role_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                        
                        # Display with comments (different from FillALL)
                        participants_text = ""
                        for p in sorted_participants:
                            if len(p) >= 2:
                                # Check if a comment is present
                                if len(p) >= 4 and p[3]:
                                    # Truncate comment to 30 characters if necessary
                                    comment = p[3]
                                    if len(comment) > 30:
                                        comment = comment[:30] + "..."
                                    participants_text += f"<@{p[1]}> {comment}\n"
                                else:
                                    participants_text += f"<@{p[1]}>\n"
                        
                        # Add the field - Teilnehmer role with signup instruction
                        embed.add_field(name=f"{participant_title}", value=participants_text or "\u200b", inline=False)
                    else:
                        # Empty participant list - Teilnehmer role with signup instruction
                        embed.add_field(name=f"{participant_title}", value="\u200b", inline=False)
            else:
                # Standard mode with multiple roles
                # Find the Fill role - case insensitive check
                fill_index = next((i for i, role in enumerate(roles) if role.lower() in ["fill", "fillall"]), None)
                
                # Extract regular roles (all except FillALL)
                regular_roles = []
                section_headers = []
                for i, role in enumerate(roles):
                    if i != fill_index:  # All except FillALL role
                        # Check if it's a section header (text in parentheses)
                        if role.strip().startswith('(') and role.strip().endswith(')'):
                            section_headers.append((i, role))
                        else:
                            regular_roles.append((i, role))

                # Creation of content for all regular roles
                field_content = ""
                role_counter = 1  # Counter for actual roles (excluding section headers)
                filled_roles = 0  # Counter for filled roles
                total_roles = 0   # Counter for total roles (excluding section headers)
                
                # Go through all roles and section headers in the original order
                all_items = section_headers + regular_roles
                all_items.sort(key=lambda x: x[0])  # Sort by original index

                for role_idx, role_name in all_items:
                    # Check if it's a section header
                    if role_name.strip().startswith('(') and role_name.strip().endswith(')'):
                        # Remove parentheses from section header
                        header_text = role_name.strip()[1:-1]  # Remove first and last character
                        field_content += f"*-----{header_text}-----*\n"
                    else:
                        # This is a normal role
                        total_roles += 1
                        # Display role and participants
                        role_key = f"{role_idx}:{role_name}"
                        role_participants = participants.get(role_key, [])
                        
                        if role_participants:
                            filled_roles += 1
                            
                            # Sort participants by timestamp and show only the first
                            sorted_participants = sorted(role_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                            p_data = sorted_participants[0]
                            
                            if len(p_data) >= 2:  # Ensure we have at least name and ID
                                p_id = p_data[1]
                                
                                # Role and player in one line
                                field_content += f"{role_counter}. {role_name} <@{p_id}>"
                                
                                # Comment if available
                                if len(p_data) >= 4 and p_data[3]:
                                    # Truncate comment to 30 characters if necessary
                                    comment = p_data[3]
                                    if len(comment) > 30:
                                        comment = comment[:30] + "..."
                                    field_content += f" {comment}"
                                    logger.info(f"Including comment for role {role_name}: '{p_data[3]}'")
                                
                                field_content += "\n"
                            else:
                                field_content += f"{role_counter}. {role_name}\n"
                        else:
                            field_content += f"{role_counter}. {role_name}\n"
                        
                        # Increment the role counter for actual roles
                        role_counter += 1

                # Add all regular roles as a single field with occupancy count
                if field_content:
                    # Count all FILLALL participants (no longer need to check for regular roles overlap)
                    fillall_count = 0
                    if fill_index is not None:
                        fill_key = f"{fill_index}:{roles[fill_index]}"
                        fill_participants = participants.get(fill_key, [])
                        if fill_participants:
                            fillall_count = len([p for p in fill_participants if len(p) >= 2])
                    
                    # Add occupancy count in the field name
                    embed.add_field(name=f"Rollen ({filled_roles + fillall_count}/{total_roles})", value=field_content, inline=True)

                # Add Fill role section
                if fill_index is not None:
                    fill_text = f"{role_counter}. {roles[fill_index]}"
                    
                    # Get participants for Fill role
                    fill_key = f"{fill_index}:{roles[fill_index]}"
                    fill_participants = participants.get(fill_key, [])
                    
                    if fill_participants:
                        # Sort participants by timestamp
                        sorted_fill = sorted(fill_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                        
                        # Display all FILLALL participants (no need to filter)
                        fill_players_text = fill_text + "\n" + "\n".join([f"<@{p[1]}>" + (f" {p[3][:30] + '...' if len(p) > 3 and p[3] and len(p[3]) > 30 else p[3]}" if len(p) > 3 and p[3] else "") for p in sorted_fill if len(p) >= 2])
                        
                        
                        # Add Fill role to embed with empty name to reduce spacing
                        embed.add_field(name="", value=fill_players_text or fill_text, inline=False)
                    else:
                        # Display empty Fill role with empty name to reduce spacing
                        embed.add_field(name="", value=fill_text, inline=False)
            
            # Update the message
            await event_message.edit(embed=embed)
            logger.info(f"Event message updated successfully with {len(embed.fields)} fields.")
            return True
        except Exception as e:
            logger.error(f"Error updating event message: {e}")
            await thread.send(f"Fehler beim Aktualisieren der Event-Nachricht: {str(e)}")
            return False

    def role_number_to_index(self, event, role_number):
        """
        Converts a role number to its corresponding index in the event's roles list.
        Returns -1 if the role number is invalid.
        """
        regular_roles = event.get("roles", [])
        fill_index = None
        
        # Find the index of the FillALL role if it exists
        for i, role in enumerate(regular_roles):
            # Check if role is a string or a dictionary
            if isinstance(role, dict) and role.get("name") == "FILLALL":
                fill_index = i
                break
            elif isinstance(role, str) and role.lower() in ["fill", "fillall"]:
                fill_index = i
                break
        
        if role_number <= len(regular_roles):
            # Regular role number
            return role_number - 1
        elif role_number == len(regular_roles) + 1 and fill_index is not None:
            # If the role_number is for the FillALL role
            return fill_index
        else:
            # Invalid role number
            return -1

    @tasks.loop(hours=1)  
    async def cleanup_event_channel(self):
        """
        Cleans up the event channel based on status and age:
        - Keeps active events
        - Removes expired events after 1 day
        - Removes regular messages after 1 day
        """
        logger.info(f"{datetime.now()} - Starting event channel cleanup...")
        
        # Backup erstellen bevor Änderungen vorgenommen werden
        self.create_backup()
        
        DAYS_TO_KEEP = 1
        
        for guild in self.guilds:
            channel = guild.get_channel(CHANNEL_ID_EVENT)
            if not channel:
                logger.warning(f"Event-Kanal in Guild {guild.name} nicht gefunden.")
                continue

            # Security check: Check permissions
            permissions = channel.permissions_for(guild.me)
            if not permissions.manage_messages:
                logger.error("Bot hat keine Berechtigung zum Löschen von Nachrichten!")
                continue
                
            try:
                # Events laden
                events_data = load_upcoming_events(include_expired=True, include_cleaned=True)
                events_to_keep = []
                original_events_count = len(events_data.get("events", []))
                
                # IDs der AKTIVEN Event-Nachrichten sammeln
                active_event_message_ids = set()
                for event in events_data["events"]:
                    if event.get("status") == "active" and event.get("message_id"):
                        active_event_message_ids.add(int(event["message_id"]))
                
                # Events nach Status/Alter sortieren
                current_time = datetime.now(timezone.utc)
                for event in events_data["events"]:
                    if event.get("status") == "active":
                        events_to_keep.append(event)
                    else:
                        try:
                            event_time = datetime.fromisoformat(event["datetime_obj"])
                            # Stelle sicher, dass es UTC ist
                            if event_time.tzinfo is None:
                                event_time = event_time.replace(tzinfo=timezone.utc)
                            days_difference = (current_time - event_time).days
                            
                            if days_difference > DAYS_TO_KEEP:
                                # Alte abgelaufene Events nicht behalten
                                pass
                            else:
                                events_to_keep.append(event)
                        except (ValueError, KeyError) as e:
                            logger.error(f"Fehler beim Verarbeiten des Events {event.get('title', 'Unbekannt')}: {e}")
                            events_to_keep.append(event)  # Im Zweifelsfall behalten
                
                # Bereinigung aller alten Nachrichten (inkl. abgelaufener Events)
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=DAYS_TO_KEEP)
                
                def should_delete_message(message):
                    # Aktive Events schützen
                    if message.id in active_event_message_ids:
                        return False
                    # Neue Nachrichten schützen
                    if message.created_at > cutoff_date:
                        return False
                    # Alte Nachrichten löschen
                    return True
                
                # Purge mit Filter ausführen
                try:
                    deleted_msgs = await channel.purge(check=should_delete_message, limit=10000)
                    logger.info(f"Guild {guild.id}: {len(deleted_msgs)} alte Nachrichten gelöscht")
                except Exception as e:
                    logger.error(f"Fehler beim Purge: {e}")
                
                # Events-Datei aktualisieren
                events_data["events"] = events_to_keep
                save_events_to_json(events_data)
                
                removed_count = original_events_count - len(events_to_keep)
                logger.info(f"Event-Bereinigung abgeschlossen: {removed_count} Events entfernt, {len(events_to_keep)} Events behalten")
                
            except Exception as e:
                logger.error(f"Fehler bei der Bereinigung des Event-Kanals: {e}")

    def create_backup(self):
        """Erstellt ein tägliches Backup der Events-Datei."""
        try:
            # Backup-Ordner erstellen falls nicht vorhanden
            os.makedirs("backups", exist_ok=True)
            
            # Heutiges Datum für Dateinamen
            today = datetime.now().strftime("%Y%m%d")
            backup_path = os.path.join("backups", f"events_backup_{today}.json")
            
            # Daten kopieren
            events_data = load_upcoming_events(include_expired=True, include_cleaned=True)
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(events_data, f, ensure_ascii=False, indent=4)
            
            logger.info(f"Backup erstellt: {backup_path}")
                
            # Alte Backups löschen (nur 42 behalten)
            self.rotate_backups()
            
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Backups: {e}")
    
    def rotate_backups(self):
        """Behält nur die neuesten 42 Backups."""
        try:
            MAX_BACKUPS = 42
            backup_files = sorted(glob.glob(os.path.join("backups", "events_backup_*.json")))
            
            # Wenn mehr als MAX_BACKUPS Dateien, lösche die ältesten
            if len(backup_files) > MAX_BACKUPS:
                files_to_delete = backup_files[:-MAX_BACKUPS]
                for file in files_to_delete:
                    os.remove(file)
                logger.info(f"{len(files_to_delete)} alte Backups gelöscht. {MAX_BACKUPS} Backups behalten.")
        except Exception as e:
            logger.error(f"Fehler bei der Backup-Rotation: {e}")

    # Wait until the bot is ready before starting the loop
    @cleanup_event_channel.before_loop
    async def before_cleanup_event_channel(self):
        await self.wait_until_ready()

    async def fetch_thread(self, guild, thread_id):
        """Helper method to fetch a thread by ID, checking both active and archived threads"""
        try:
            # First try getting from guild threads (active threads)
            thread_id = int(thread_id)  # Ensure it's an integer
            thread = guild.get_thread(thread_id)
            if thread:
                logger.info(f"Found active thread with ID {thread_id}")
                return thread
                
            # If not found, check all channels for threads
            for channel in guild.text_channels:
                # Check permissions
                if not channel.permissions_for(guild.me).read_messages:
                    continue
                    
                # Check active threads
                for thread in channel.threads:
                    if thread.id == thread_id:
                        logger.info(f"Found active thread with ID {thread_id} in channel {channel.name}")
                        return thread
                
                # Check archived threads
                try:
                    async for archived_thread in channel.archived_threads():
                        if archived_thread.id == thread_id:
                            logger.info(f"Found archived thread with ID {thread_id} in channel {channel.name}")
                            return archived_thread
                except Exception as e:
                    logger.error(f"Error checking archived threads in channel {channel.name}: {e}")
                    
            logger.warning(f"No thread found with ID {thread_id}")
            return None
        except Exception as e:
            logger.error(f"Error fetching thread by ID {thread_id}: {e}")
            return None

    async def on_guild_join(self, guild):
        """Called when the bot joins a new server"""
        if AUTHORIZED_GUILD_ID != 0 and guild.id != AUTHORIZED_GUILD_ID:
            logger.warning(f"Leaving unauthorized server: {guild.name} (ID: {guild.id})")
            
            # Try to send a message to the server owner
            try:
                owner = guild.owner
                if owner:
                    leave_message = (
                        f"Hello {owner.name},\n\n"
                        f"Thank you for your interest in my event management bot! Unfortunately, I'm exclusively "
                        f"developed for a specific community and not configured for use on other servers.\n\n"
                        f"If you're interested in this bot or have any questions, "
                        f"please contact my developer on Discord: **nox1104**\n\n"
                        f"Thank you for your understanding."
                    )
                    await owner.send(leave_message)
                    logger.info(f"Sent farewell message to {owner.name} on server {guild.name}")
            except Exception as e:
                logger.error(f"Could not send message to server owner: {e}")
            
            # After attempting to send the message, leave the server
            await guild.leave()
        else:
            logger.info(f"Bot joined authorized server: {guild.name}")

    @tasks.loop(minutes=5)
    async def check_expired_events(self):
        """Überprüft alle 5 Minuten, ob Events als expired markiert werden müssen"""
        try:
            logger.info("Checking for expired events...")
            # Events laden
            events_data = load_upcoming_events(include_expired=True, include_cleaned=False)
            
            # Status aktualisieren - Achtung: clean_old_events wird bereits durch load_upcoming_events aufgerufen
            # Dies stellt sicher, dass alle abgelaufenen Events jetzt als "expired" markiert werden
            updated_data = clean_old_events(events_data)
            
            # Prüfen ob sich etwas geändert hat
            events_changed = False
            if len(updated_data.get("events", [])) != len(events_data.get("events", [])):
                events_changed = True
            else:
                # Prüfe, ob sich event.status geändert hat bei mindestens einem Event
                for i, event in enumerate(updated_data.get("events", [])):
                    if i < len(events_data.get("events", [])):
                        if event.get("status") != events_data["events"][i].get("status"):
                            events_changed = True
                            break
            
            # Wenn sich etwas geändert hat, speichern und Übersicht aktualisieren
            if events_changed:
                logger.info("Events updated, saving changes and updating event listing")
                save_events_to_json(updated_data)
                # Aktualisiere die Eventübersicht in allen Guilds
                for guild in self.guilds:
                    try:
                        await create_event_listing(guild)
                        logger.info(f"Event listing updated for guild: {guild.name}")
                    except Exception as guild_error:
                        logger.error(f"Error updating event listing for guild {guild.name}: {guild_error}")
            else:
                logger.info("No expired events found, event listing not updated")
    
        except Exception as e:
            logger.error(f"Error in check_expired_events: {e}")
            import traceback
            logger.error(traceback.format_exc())

    @check_expired_events.before_loop
    async def before_check_expired_events(self):
        await self.wait_until_ready()

# Füge die Hilfsfunktion direkt vor der Event-Klasse ein
def calculate_role_counts(roles, participants):
    """
    Berechnet die Anzahl der besetzten und insgesamt verfügbaren Rollen für ein Event.
    
    Args:
        roles: Liste der Rollen im Event
        participants: Dictionary mit den Teilnehmern pro Rolle
    
    Returns:
        Tuple (filled_slots, total_slots)
    """
    filled_slots = 0
    total_slots = 0
    
    # Count regular roles (excluding headers and FILLALL)
    for i, role in enumerate(roles):
        # Überschriften und FILL/FILLALL-Rollen überspringen
        if (isinstance(role, str) and 
            ((role.strip().startswith('(') and role.strip().endswith(')')) or 
             role.lower() in ["fill", "fillall"])):
            continue
            
        # Als Slot zählen
        total_slots += 1
        
        # Prüfen ob dieser Slot besetzt ist
        role_key = f"{i}:{role}"
        if role_key in participants and len(participants[role_key]) > 0:
            filled_slots += 1
    
    # FILLALL-Teilnehmer zählen (jetzt einfach alle, da keine Überschneidung möglich)
    fill_index = None
    for i, role in enumerate(roles):
        if isinstance(role, str) and role.lower() in ["fill", "fillall"]:
            fill_index = i
            break
    
    if fill_index is not None:
        fill_key = f"{fill_index}:{roles[fill_index]}"
        if fill_key in participants:
            for participant in participants[fill_key]:
                if len(participant) >= 2:
                    filled_slots += 1
    
    return filled_slots, total_slots

class Event:
    def __init__(self, title, date, time, description, roles, datetime_obj=None, caller_id=None, caller_name=None, participant_only_mode=False, event_id=None):
        self.title = title
        self.date = date
        self.time = time
        self.description = description
        self.roles = roles
        self.participants = {}
        self.caller_id = caller_id  # Discord ID of the creator
        self.caller_name = caller_name  # Name of the creator
        self.message_id = None  # Message ID of the event post
        self.thread_id = None  # Thread ID of the event thread
        self.participant_only_mode = participant_only_mode  # Flag for participant-only mode
        self.mention_role_id = None  # Add mention_role_id field
        self.status = "active"  # Neues Statusfeld: "active", "expired" oder "cleaned"
        self.image_url = None  # Attribut für Bild-URL hinzufügen
        
        # Konvertiere datetime_obj zu einem tatsächlichen UTC datetime-Objekt
        if datetime_obj is None:
            try:
                # Versuche, aus Datum und Uhrzeit ein datetime-Objekt zu erstellen und in UTC zu konvertieren
                dt_str = f"{date} {time}"
                local_dt = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
                # Lokale Zeit zu UTC konvertieren
                self.datetime_obj = local_to_utc(local_dt)
            except:
                # Fallback auf aktuelle Zeit in UTC
                self.datetime_obj = datetime.now(timezone.utc)
                logger.warning(f"Konnte kein datetime-Objekt aus Datum '{date}' und Zeit '{time}' erstellen. Verwende aktuelle UTC-Zeit.")
        elif isinstance(datetime_obj, str):
            try:
                # Versuche, den String in ein datetime-Objekt zu konvertieren
                local_dt = datetime.fromisoformat(datetime_obj)
                # In UTC konvertieren
                self.datetime_obj = local_to_utc(local_dt)
            except:
                # Fallback auf aktuelle Zeit in UTC
                self.datetime_obj = datetime.now(timezone.utc)
                logger.warning(f"Konnte kein datetime-Objekt aus String '{datetime_obj}' erstellen. Verwende aktuelle UTC-Zeit.")
        else:
            # Stelle sicher, dass es UTC ist
            self.datetime_obj = local_to_utc(datetime_obj)
        
        # Use provided event_id or generate a new one
        if event_id:
            self.event_id = event_id
            logger.info(f"Using provided event_id: {event_id} for event: {title}")
        else:
            # Generate a unique ID for the event that includes the UTC timestamp
            timestamp = self.datetime_obj.strftime("%Y%m%d%H%M")
            random_string = str(uuid.uuid4())[:8]  # Use first 8 characters of UUID
            self.event_id = f"{timestamp}-{random_string}"
            logger.info(f"Generated new event_id: {self.event_id} for event: {title}")
    
    def get(self, attr, default=None):
        """Emulates dictionary-like get method to maintain compatibility."""
        return getattr(self, attr, default)
    
    @staticmethod
    def get_datetime_from_event_id(event_id):
        """Extrahiert den Zeitstempel aus der Event-ID und gibt ein datetime-Objekt zurück."""
        try:
            # Extrahiere den Zeitstempel-Teil (vor dem Bindestrich)
            timestamp_str = event_id.split('-')[0]
            # Konvertiere zu datetime mit UTC-Zeitzone
            dt = datetime.strptime(timestamp_str, "%Y%m%d%H%M")
            return dt.replace(tzinfo=timezone.utc)
        except:
            # Bei Fehlern None zurückgeben
            return None
    
    def to_dict(self):
        """Convert the event to a dictionary for JSON serialization"""
        # Convert datetime_obj to ISO format string for JSON serialization
        datetime_str = None
        if hasattr(self, 'datetime_obj') and self.datetime_obj:
            try:
                datetime_str = self.datetime_obj.isoformat()
            except:
                logger.warning(f"Could not convert datetime_obj to ISO format for event: {self.title}")
        
        # Get local date and time for display
        local_format = None
        if hasattr(self, 'datetime_obj') and self.datetime_obj:
            try:
                local_format = format_local_datetime(self.datetime_obj)
                self.date = local_format["date"]
                self.time = local_format["time"]
            except:
                logger.warning(f"Could not format local datetime for event: {self.title}")
        
        # Berechne Rollenanzahl über die zentrale Hilfsfunktion
        filled_slots, total_slots = calculate_role_counts(self.roles, self.participants)
        
        return {
            "title": self.title,
            "date": self.date,
            "time": self.time,
            "description": self.description,
            "roles": self.roles,
            "participants": self.participants,
            "event_id": self.event_id,  # Store the unique ID
            "caller_id": self.caller_id,  # Store the creator's ID
            "caller_name": self.caller_name,  # Store the creator's name
            "message_id": self.message_id,  # Store the event post's message ID
            "thread_id": self.thread_id,  # Store the event thread's ID
            "participant_only_mode": self.participant_only_mode,  # Store the flag for participant-only mode
            "mention_role_id": self.mention_role_id,  # Store the mention role ID
            "datetime_obj": datetime_str,  # Store the datetime as ISO format string
            "status": getattr(self, 'status', 'active'),  # Store the status, default to "active" if not set
            "image_url": self.image_url,  # Store the image URL
            "total_slots": total_slots,  # Store total role slots
            "filled_slots": filled_slots  # Store filled role slots
        }

class EventModal(discord.ui.Modal, title="Eventify"):
    def __init__(self, title: str, date: str, time: str, caller_id: str, caller_name: str, mention_role: discord.Role = None, image_url: str = None):
        super().__init__()
        self.title = title
        self.date = date
        self.time = time
        self.caller_id = caller_id
        self.caller_name = caller_name
        self.mention_role = mention_role
        self.image_url = image_url
        
        # Add input fields
        self.description = discord.ui.TextInput(
            label="Beschreibung",
            placeholder="Beschreibe dein Event...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=4000
        )
        self.roles = discord.ui.TextInput(
            label="Rollen",
            placeholder="Gib die Rollen ein (oder frei lassen für den Nur-Teilnehmer-Modus)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=1000
        )
        
        self.add_item(self.description)
        self.add_item(self.roles)
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Sofort die Interaktion beantworten, bevor irgendetwas anderes passiert
            await interaction.response.defer(ephemeral=True)
            
            # Verwende die verbesserte Methode für die Zeitumrechnung
            event_datetime = local_to_utc(None, is_date_time_string=True, 
                                          date_str=self.date, time_str=self.time)
            
            if not event_datetime:
                # Ohne Fallback direkt Fehler melden
                await interaction.followup.send("Ungültiges Datum oder ungültige Zeit. Bitte verwende die Formate DD.MM.YYYY und HH:MM.", ephemeral=True)
                return
            
            # Log the date/time conversion
            logger.info(f"Created event datetime: {event_datetime.isoformat()} (UTC) from {self.date} {self.time} (Europe/Berlin)")
            
            # Format date and time for display (local time)
            local_format = format_local_datetime(event_datetime)
            formatted_date = local_format["date"]
            formatted_time = local_format["time"]
            
            # Check if we're in participant-only mode
            roles_input = self.roles.value.strip() if self.roles.value else ""
            is_participant_only_mode = not roles_input
            
            # Set roles based on mode
            if is_participant_only_mode:
                # Bei leerer Eingabe nur eine "Teilnehmer"-Rolle erstellen
                roles = ["Teilnehmer"]
            else:
                # Normaler Modus mit Rollen aus der Eingabe
                roles = [role.strip() for role in roles_input.splitlines() if role.strip()]
            
            # Process section headers to ensure they're consistent
            for i, role in enumerate(roles):
                # Check if it's a section header (text in parentheses)
                if role.strip().startswith('(') and role.strip().endswith(')'):
                    # Remove parentheses and make sure it's stored without them
                    header_text = role.strip()[1:-1].strip()  # Remove first and last character and any whitespace
                    roles[i] = f"({header_text})"  # Store in a consistent format
            
            # Find the Fill role - case insensitive check
            fill_index = next((i for i, role in enumerate(roles) if role.lower() in ["fill", "fillall"]), None)
            if fill_index is None:
                # If no Fill role found, add one
                fill_index = len(roles)
                roles.append("FILLALL")
            else:
                # Make sure it's consistently named "FILLALL"
                roles[fill_index] = "FILLALL"
            
            # Make sure FILLALL is always the last role
            if fill_index < len(roles) - 1:
                # Remove FILLALL from its current position
                fill_role = roles.pop(fill_index)
                # Add it back at the end
                roles.append(fill_role)
                # Update the fill_index to match the new position
                fill_index = len(roles) - 1
            
            # Create event object - always generate a new event_id
            event = Event(
                title=self.title,
                date=formatted_date,  # Verwende formatiertes Datum für Anzeige
                time=formatted_time,  # Verwende formatierte Zeit für Anzeige
                description=self.description.value,
                roles=roles,
                datetime_obj=event_datetime,
                caller_id=self.caller_id,
                caller_name=self.caller_name,
                participant_only_mode=is_participant_only_mode
            )
            
            # Store the mention role ID separately in the event object
            if self.mention_role:
                event.mention_role_id = str(self.mention_role.id)
                
            # Add the image URL if provided
            if self.image_url:
                event.image_url = self.image_url
                
            # Create embed
            embed = discord.Embed(
                title=f"__**{event.title}**__",
                color=0x0dceda
            )
            
            # Get weekday abbreviation
            weekday = get_weekday_abbr(event.date)
            
            # Add date and time as inline fields (only these two in the first row)
            embed.add_field(name="Datum", value=f"{event.date} ({weekday})", inline=True)
            embed.add_field(name="Uhrzeit", value=event.time, inline=True)
            # Add a blank field to ensure only 2 fields in the first row
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Add creator and mention role as inline fields (in the second row)
            creator_mention = f"<@{event.caller_id}>" if event.caller_id else "Unbekannt"
            
            embed.add_field(name="Von", value=creator_mention, inline=True)
            
            if event.mention_role_id:
                embed.add_field(name="Für", value=f"<@&{event.mention_role_id}>", inline=True)
            else:
                # Add an empty field to maintain alignment
                embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Add a blank field to ensure only 2 fields in the second row
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Add description if available
            if event.description:
                if len(event.description) > 1020:  # Leave room for ellipsis
                    description = event.description[:1020] + "..."
                else:
                    description = event.description
                embed.add_field(name="Beschreibung", value=description, inline=False)
            
            # Add image if provided (direkt nach der Beschreibung)
            if self.image_url:
                embed.set_image(url=self.image_url)
            
            # Add roles if not in participant-only mode
            if not event.participant_only_mode:
                # Extract regular roles (everything except FILLALL)
                regular_roles = []
                section_headers = []
                fill_index = None
                
                # Find the Fill role - case insensitive check
                fill_index = next((i for i, role in enumerate(event.roles) if role.lower() in ["fill", "fillall"]), None)
                
                for i, role in enumerate(event.roles):
                    if i != fill_index:  # Everything except the FILLALL role
                        # Check if it's a section header (text in parentheses)
                        if role.strip().startswith('(') and role.strip().endswith(')'):
                            section_headers.append((i, role))
                        else:
                            regular_roles.append((i, role))
                
                # Create content for all regular roles
                field_content = ""
                role_counter = 1  # Counter for actual roles (excluding section headers)
                
                # Go through all roles and section headers in the original order
                all_items = section_headers + regular_roles
                all_items.sort(key=lambda x: x[0])  # Sort by original index
                
                for role_idx, role_name in all_items:
                    # Check if it's a section header
                    if role_name.strip().startswith('(') and role_name.strip().endswith(')'):
                        # Remove parentheses from section header
                        header_text = role_name.strip()[1:-1]  # Remove first and last character
                        field_content += f"*-----{header_text}-----*\n"
                    else:
                        # This is a normal role
                        field_content += f"{role_counter}. {role_name}\n"
                        role_counter += 1
                
                # Add all regular roles as a single field
                if field_content:
                    # Count total roles (excluding section headers and FILLALL)
                    total_roles = len([r for r in event.roles if not (r.strip().startswith('(') and r.strip().endswith(')')) and r.lower() not in ["fill", "fillall"]])
                    embed.add_field(name=f"Rollen (0/{total_roles})", value=field_content, inline=False)
                
                if fill_index is not None:
                    fill_text = f"{role_counter}. {event.roles[fill_index]}"
                    embed.add_field(name="", value=fill_text, inline=False)
            else:
                # Im Teilnehmer-only Modus, zeige die Teilnehmer-Rolle an
                embed.add_field(name="Rollen (0)", value="1. Teilnehmer", inline=False)
            
            # Send event post and create thread
            channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
            event_post = await channel.send(embed=embed)
            logger.info(f"Event post created for '{event.title}' with message ID: {event_post.id}")
            
            try:
                logger.info(f"Attempting to create thread for '{event.title}'")
                logger.info(f"Event post exists with ID: {event_post.id}, channel ID: {event_post.channel.id}")
                logger.info(f"Thread creation parameters: name='{event.title}'")
                logger.info(f"Bot permissions in channel: {channel.permissions_for(interaction.guild.me).value}")
                logger.info(f"Channel type: {type(channel).__name__}")
                logger.info(f"Event post type: {type(event_post).__name__}")
                logger.info(f"Guild ID: {interaction.guild.id}, Channel ID: {channel.id}")
                
                # Detailed logging before thread creation attempt
                logger.info(f"[Thread Creation] Starting thread creation attempt for event '{event.title}'")
                logger.info(f"[Thread Creation] Discord API state before attempt: Session ID: N/A")
                logger.info(f"[Thread Creation] Event message creation timestamp: {event_post.created_at}")
                
                # Add retry mechanism for thread creation
                max_retries = 3
                retry_delay = 2  # seconds
                thread = None
                
                for retry_count in range(max_retries):
                    try:
                        logger.info(f"[Thread Creation] Attempt {retry_count + 1}/{max_retries} to create thread")
                        thread = await event_post.create_thread(name=event.title)
                        logger.info(f"[Thread Creation] Thread creation API call completed successfully on attempt {retry_count + 1}")
                        break  # Exit loop on success
                    except discord.HTTPException as e:
                        logger.error(f"[Thread Creation] HTTP exception during thread creation attempt {retry_count + 1}: {str(e)}")
                        if retry_count < max_retries - 1:
                            logger.info(f"[Thread Creation] Waiting {retry_delay} seconds before retry...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            logger.error(f"[Thread Creation] All {max_retries} thread creation attempts failed")
                            raise  # Re-raise after all retries fail
                    except Exception as e:
                        logger.error(f"[Thread Creation] Exception during thread creation API call: {str(e)}")
                        raise  # Non-HTTP exceptions are immediately re-raised
                
                if not thread:
                    error_msg = f"Konnte keinen Thread für '{event.title}' nach {max_retries} Versuchen erstellen"
                    logger.error(f"[Thread Creation] {error_msg}")
                    raise Exception(error_msg)
                
                logger.info(f"Thread successfully created for '{event.title}' with thread ID: {thread.id}")
                logger.info(f"Thread details: name='{thread.name}', owner_id={thread.owner_id}, parent_id={thread.parent_id}, archived={thread.archived}, locked={thread.locked}")
                logger.info(f"Thread type: {type(thread).__name__}")
                logger.info(f"Thread channel ID: {thread.channel.id if hasattr(thread, 'channel') else 'N/A'}")
                
                # Save both message ID and thread ID
                event.message_id = event_post.id
                event.thread_id = thread.id
                logger.info(f"Saving event with thread_id: {thread.id} and message_id: {event_post.id}")
                
                # Save event to JSON
                save_event_to_json(event)
                logger.info(f"[Thread Creation] Event saved to JSON with thread_id: {thread.id}")
                
                # Send welcome information to the thread
                welcome_embed = discord.Embed(
                    description="Bei Fragen hilft dir das [Benutzerhandbuch](https://github.com/nox1104/Eventify/blob/main/Benutzerhandbuch.md).",
                    color=0x0dceda  # Eventify Cyan
                )

                # Log thread state before sending message
                logger.info(f"[Thread Creation] Thread state before welcome message: archived={thread.archived}, locked={thread.locked}, type={type(thread).__name__}")
                
                try:
                    welcome_msg = await thread.send(embed=welcome_embed)
                    logger.info(f"[Thread Creation] Welcome message sent successfully with ID: {welcome_msg.id}")
                except Exception as e:
                    logger.error(f"[Thread Creation] Failed to send welcome message: {str(e)}")
                    # Continue despite welcome message failure
                
                # Send a separate mention message if a mention role is specified
                if event.mention_role_id:
                    try:
                        # Send mention but delete it right after (will still notify users)
                        mention_msg = await thread.send(f"<@&{event.mention_role_id}> - {event.title}, {event.date}, {event.time}", delete_after=0.1)
                        logger.info(f"[Thread Creation] Mention message sent successfully with ID: {mention_msg.id}")
                    except Exception as e:
                        logger.error(f"[Thread Creation] Failed to send mention message: {str(e)}")
                        # Continue despite mention message failure
                
                # Verify event data is properly stored
                try:
                    # Reload events from JSON to verify the event was properly saved
                    verification_events = load_upcoming_events(include_expired=True)
                    verification_event = next((e for e in verification_events["events"] if e.get('thread_id') == thread.id), None)
                    
                    if verification_event:
                        logger.info(f"[Thread Creation] Event verification successful - found event in JSON with thread_id: {thread.id}")
                    else:
                        logger.error(f"[Thread Creation] Event verification FAILED - could not find event in JSON with thread_id: {thread.id}")
                        # Try to save again
                        logger.info(f"[Thread Creation] Attempting to save event again...")
                        save_event_to_json(event)
                except Exception as e:
                    logger.error(f"[Thread Creation] Error during event verification: {str(e)}")
                
                # Aktualisiere die Eventübersicht
                try:
                    await create_event_listing(interaction.guild)
                    logger.info(f"[Thread Creation] Event listing updated successfully")
                except Exception as e:
                    logger.error(f"[Thread Creation] Failed to update event listing: {str(e)}")
                    # Continue despite event listing failure
                
                # Send ephemeral confirmation message
                await interaction.followup.send("Dein Event wurde erstellt.", ephemeral=True)
                
                # Erstelle einen Eventify-Befehl als Vorlage für das nächste Mal
                template_command = f"/eventify title:{event.title} date: time:"
                
                # Beschreibung mit korrekten Zeilenumbrüchen hinzufügen
                if event.description:
                    # Ersetze tatsächliche Zeilenumbrüche durch \n für die Vorlage
                    escaped_description = event.description.replace("\n", "\\n")
                    template_command += f" description:{escaped_description}"
                
                # Rollen hinzufügen, falls es keine Teilnehmer-only Veranstaltung ist
                if not event.participant_only_mode and event.roles:
                    # Entferne FILLALL aus der Rollenliste für die Vorlage, da es automatisch hinzugefügt wird
                    roles_list = [role for role in event.roles if role.lower() != "fillall"]
                    roles_text = "\\n".join(roles_list)
                    template_command += f" roles:{roles_text}"
                
                # Mention-Rolle mit angeben, wenn vorhanden
                if hasattr(event, 'mention_role_id') and event.mention_role_id:
                    try:
                        mention_role = interaction.guild.get_role(int(event.mention_role_id))
                        if mention_role:
                            template_command += f" mention_role:@{mention_role.name}"
                    except Exception as e:
                        logger.error(f"Failed to get mention role for template: {e}")
                        # Fallback: nur den Parameter hinzufügen
                        template_command += " mention_role:"
                
                # Bild-URL hinzufügen, falls vorhanden
                if hasattr(event, 'image_url') and event.image_url:
                    template_command += f" image_url:{event.image_url}"
                
                # Sende die Vorlage als direkte Nachricht an den Event-Ersteller
                try:
                    user = await interaction.client.fetch_user(int(event.caller_id))
                    if user:
                        # Erstelle einen Link zum Event-Kanal
                        channel_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}"
                        
                        # Event-Link für die erste Nachricht
                        event_link = channel_link
                        if event.message_id:
                            event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.message_id}"
                        
                        # Befehl ohne Codeblöcke senden und in einer separaten Nachricht, damit er auf mobilen Geräten
                        # leicht kopiert werden kann, ohne dass die Formatierung mitkopiert wird
                        dm_intro = (
                            f"Hier ist eine Vorlage für dein Event **{event.title}**, die du für das nächste Mal verwenden kannst.\n"
                            f"Kopiere den Befehl und füge ihn im [Eventify-Kanal]({event_link}) ein.\n"
                        )
                        
                        # Zuerst Intro-Nachricht senden
                        await user.send(dm_intro)
                        
                        # Dann den reinen Befehl ohne Formatierung senden
                        await user.send(f"{template_command}")
                        
                        logger.info(f"Template message sent as DM to user {event.caller_id}")
                except Exception as e:
                    # Fehler beim Senden der DM loggen, aber nicht den Benutzer stören
                    logger.error(f"Failed to send template as DM to user {event.caller_id}: {e}")
            except discord.Forbidden as e:
                error_msg = f"Keine Berechtigung zum Erstellen des Threads für '{event.title}': {str(e)}"
                logger.error(error_msg)
                # Try to delete the event post since we couldn't create a thread
                try:
                    await event_post.delete()
                    logger.info(f"Deleted event post for '{event.title}' due to thread creation failure")
                except:
                    logger.error(f"Failed to delete event post for '{event.title}' after thread creation failure")
                
                # Try to send error message
                try:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                except:
                    try:
                        await interaction.followup.send(error_msg, ephemeral=True)
                    except:
                        logger.error("Couldn't send error message to user")
            except discord.HTTPException as e:
                error_msg = f"Discord API Fehler beim Erstellen des Threads für '{event.title}': {str(e)}"
                logger.error(error_msg)
                # Try to delete the event post since we couldn't create a thread
                try:
                    await event_post.delete()
                    logger.info(f"Deleted event post for '{event.title}' due to thread creation failure")
                except:
                    logger.error(f"Failed to delete event post for '{event.title}' after thread creation failure")
                
                # Try to send error message
                try:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                except:
                    try:
                        await interaction.followup.send(error_msg, ephemeral=True)
                    except:
                        logger.error("Couldn't send error message to user")
            except Exception as e:
                error_msg = f"Unerwarteter Fehler beim Erstellen des Threads für '{event.title}': {str(e)}"
                logger.error(error_msg)
                logger.error("Stack trace:", exc_info=True)
                
                # Save diagnostic information about the failure
                save_thread_failure_info(event.title, event_post.id, {"error_type": type(e).__name__, "error_message": str(e)})
                
                # Try to delete the event post since we couldn't create a thread
                try:
                    await event_post.delete()
                    logger.info(f"Deleted event post for '{event.title}' due to thread creation failure")
                except:
                    logger.error(f"Failed to delete event post for '{event.title}' after thread creation failure")
                
                # Try to send error message
                try:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                except:
                    try:
                        await interaction.followup.send(error_msg, ephemeral=True)
                    except:
                        logger.error("Couldn't send error message to user")
        except discord.errors.NotFound:
            # Wenn die Interaktion bereits abgelaufen ist, loggen wir das
            logger.error(f"Interaction already expired when handling event creation for {self.title}")
        except Exception as e:
            # Allgemeine Fehlerbehandlung
            error_msg = f"Es gab einen Fehler beim Erstellen des Events: {str(e)}"
            logger.error(f"Error in EventModal on_submit: {str(e)}")
            logger.error(f"Full traceback:", exc_info=True)
            
            # Versuche Followup zu senden, falls möglich
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg, ephemeral=True)
                else:
                    await interaction.followup.send(error_msg, ephemeral=True)
            except:
                # Falls auch das Followup nicht funktioniert, nur loggen
                logger.error("Couldn't send error message to user")

# Global Lock für die Event-Übersicht, um Race Conditions zu vermeiden
event_listing_lock = asyncio.Lock()

async def create_event_listing(guild):
    # Lock zur Vermeidung paralleler Ausführungen
    async with event_listing_lock:
        # Lösche alte Übersicht
        channel = guild.get_channel(CHANNEL_ID_EVENT)
        old_message_id = load_overview_id()
        
        if channel and old_message_id:
            try:
                old_message = await channel.fetch_message(int(old_message_id))
                await old_message.delete()
                logger.info(f"Alte Eventübersicht gelöscht: {old_message_id}")
            except discord.NotFound:
                logger.info(f"Alte Übersichtsnachricht existiert nicht mehr")
            except discord.HTTPException as e:
                logger.warning(f"Konnte alte Übersicht nicht löschen: {e}")
        
        # Lade nur aktive Events (keine abgelaufenen oder bereinigten)
        events_data = load_upcoming_events(include_expired=False, include_cleaned=False)
        
        # Create base embed
        base_embed = discord.Embed(
            title="Eventübersicht",
            color=0xe076ed  # Eventify Pink
        )
        
        if not events_data or not events_data.get("events"):
            logger.info("No upcoming events to list.")
            base_embed.description = "Aktuell sind keine Events geplant."
            message = await channel.send(embed=base_embed)
            save_overview_id(message.id)
            return message
        
        # Get the guild ID for links
        guild_id = guild.id
        event_channel = guild.get_channel(CHANNEL_ID_EVENT)
        
        if not event_channel:
            logger.error(f"Event channel not found in guild {guild.name}")
            return
        
        # Filter events where no corresponding event post exists and ensure only active events are shown
        valid_events = []
        for event in events_data["events"]:
            if not isinstance(event, dict):
                logger.warning(f"Invalid event format: {event}")
                continue
                
            message_id = event.get("message_id")
            status = event.get("status", "active")
            
            # Skip events without message_id or non-active events
            if not message_id:
                logger.warning(f"Event {event.get('title')} has no message_id and will be skipped.")
                continue
                
            if status != "active":
                logger.info(f"Event {event.get('title')} has status '{status}' and will be skipped from overview.")
                continue
                
            valid_events.append(event)
        
        # Update the events.json to remove orphaned events
        if len(valid_events) < len(events_data["events"]):
            logger.info(f"Remove {len(events_data['events']) - len(valid_events)} orphaned events from the JSON.")
            save_events_to_json({"events": valid_events})
        
        if not valid_events:
            logger.info("No valid events with existing posts found.")
            base_embed.description = "Aktuell sind keine Events geplant."
            message = await channel.send(embed=base_embed)
            save_overview_id(message.id)
            return message
        
        # Sort events by date and time
        try:
            # Sort by datetime_obj, if available
            events_with_datetime = []
            for event in valid_events:
                # Try to convert date and time to a datetime object
                if 'datetime_obj' in event and event['datetime_obj']:
                    try:
                        dt_obj = datetime.fromisoformat(event['datetime_obj'])
                        # Stelle sicher, dass es UTC ist
                        if dt_obj.tzinfo is None:
                            dt_obj = dt_obj.replace(tzinfo=timezone.utc)
                        events_with_datetime.append((event, dt_obj))
                    except (ValueError, TypeError):
                        # If datetime_obj parsing fails, try date and time fields
                        dt_obj = None
                else:
                    dt_obj = None
                
                # If datetime_obj is not available or invalid, parse date and time
                if dt_obj is None:
                    try:
                        date_str = event['date']
                        time_str = event['time']
                        # Convert German date format (dd.mm.yyyy) to datetime
                        day, month, year = map(int, date_str.split('.'))
                        hour, minute = map(int, time_str.split(':'))
                        # Lokale Zeit zu UTC konvertieren
                        local_dt = datetime(year, month, day, hour, minute)
                        dt_obj = local_to_utc(local_dt)
                    except (ValueError, KeyError) as e:
                        logger.error(f"Error parsing date/time for event {event.get('title', 'unknown')}: {e}")
                        # Add the event with the current timestamp so it is displayed
                        dt_obj = datetime.now(timezone.utc)
                    
                    events_with_datetime.append((event, dt_obj))
            
            # Sort the events by timestamp
            events_with_datetime.sort(key=lambda x: x[1])
            sorted_events = [event for event, _ in events_with_datetime]
        except Exception as e:
            logger.error(f"Error sorting events: {e}")
            sorted_events = valid_events  # Fallback: Unsorted events
        
        # Group events by date
        events_by_date = {}
        for event in sorted_events:
            date = event.get('date', 'Unknown date')
            if date not in events_by_date:
                events_by_date[date] = []
            events_by_date[date].append(event)
        
        # Create embeds with a max of 25 fields each (Discord limit)
        embeds = []
        current_embed = discord.Embed(
            title="Eventübersicht",
            color=0xe076ed  # Eventify Pink
        )
        field_count = 0
        max_fields_per_embed = 25  # Discord limit
        
        # Process each date and its events
        for date, date_events in events_by_date.items():
            # Create event descriptions, potentially splitting into multiple fields if too long
            all_descriptions = []
            current_description = ""
            
            for event in date_events:
                title = event.get('title', 'Unbekanntes Event')
                time = event.get('time', '')
                caller_id = event.get('caller_id', None)
                caller_name = event.get('caller_name', None)  # Get the caller's name
                message_id = event.get('message_id')
                
                # Berechne die Rollenanzahl neu für die korrekte Anzeige
                # Falls keine Rollen im Event sind, bleiben die Werte bei 0
                filled_slots, total_slots = calculate_role_counts(event.get('roles', []), event.get('participants', {}))
                
                # Create role count display
                role_count_display = ""
                if event.get('participant_only_mode', False):
                    # Für Nur-Teilnehmer-Modus zählen wir einfach die Anzahl der Teilnehmer
                    participant_count = 0
                    if event.get('roles', []) and event.get('participants', {}):
                        # Im participant_only_mode ist nur die erste Rolle relevant (Index 0)
                        role_key = f"0:{event['roles'][0]}"
                        if role_key in event['participants']:
                            # Zähle die eindeutigen Teilnehmer
                            unique_participants = set()
                            for participant in event['participants'][role_key]:
                                if len(participant) >= 2:
                                    unique_participants.add(participant[1])
                            participant_count = len(unique_participants)
                    role_count_display = f" ({participant_count})"
                elif total_slots > 0:
                    role_count_display = f" ({filled_slots}/{total_slots})"
                
                # Create event line
                event_line = ""
                if caller_id:
                    # We always have a message_id if we have a caller_id
                    event_line = f"{time}  [**{title}**](https://discord.com/channels/{guild_id}/{CHANNEL_ID_EVENT}/{message_id}){role_count_display}\n"
                else:
                    if message_id and message_id != "None" and message_id != None:
                        event_line = f"{time}  [**{title}**](https://discord.com/channels/{guild_id}/{CHANNEL_ID_EVENT}/{message_id}){role_count_display}\n"
                    else:
                        event_line = f"{time}  {title}{role_count_display}\n"
                
                # Check if adding this line would exceed Discord's limit
                if len(current_description) + len(event_line) > 1000:  # Leave some buffer below 1024
                    # This field is full, add it to the list and start a new one
                    all_descriptions.append(current_description)
                    current_description = event_line
                else:
                    # Add to current field
                    current_description += event_line
            
            # Don't forget the last batch
            if current_description:
                all_descriptions.append(current_description)
            
            # Add fields for this date, potentially multiple if there were a lot of events
            for i, description in enumerate(all_descriptions):
                # Check if we need to create a new embed (max 25 fields per embed)
                if field_count >= max_fields_per_embed:
                    # Current embed is full, add it to the list and create a new one
                    embeds.append(current_embed)
                    current_embed = discord.Embed(
                        title="Eventübersicht (Fortsetzung)",
                        color=0xe076ed  # Eventify Pink
                    )
                    field_count = 0
                
                # Zeige Datumsnamen nur beim ersten Feld, 
                # für Fortsetzungen verwende einen leeren String mit Unicode Zero Width Space
                # um das Feld in Discord korrekt darzustellen
                field_name = f"{date} ({get_weekday_abbr(date)})" if i == 0 else "Oha, an diesem Tag ist viel geplant..."
                
                current_embed.add_field(
                    name=field_name,
                    value=description,
                    inline=False
                )
                field_count += 1
        
        # Don't forget to add the last embed
        if field_count > 0:
            embeds.append(current_embed)
        
        # Send the embeds to the event channel and store the ID of the first message
        channel = guild.get_channel(CHANNEL_ID_EVENT)
        first_message = None
        
        for i, embed in enumerate(embeds):
            message = await channel.send(embed=embed)
            if i == 0:  # Store the ID of the first message only
                first_message = message
        
        if first_message:
            # Speichere die ID der ersten Übersichtsnachricht
            save_overview_id(first_message.id)
            logger.info(f"Neue Eventübersicht erstellt: {first_message.id}")
        
        logger.info(f"Event listing created successfully with {len(embeds)} embeds.")
        return first_message

bot = MyBot()

def parse_date(date_str: str):
    """Parse date from string in format DDMMYYYY or DD.MM.YYYY"""
    try:
        # Try to parse with dots
        if "." in date_str:
            day, month, year = date_str.split(".")
        else:
            # Try to parse without dots (DDMMYYYY)
            day = date_str[:2]
            month = date_str[2:4]
            year = date_str[4:]
        
        return datetime(int(year), int(month), int(day)).date()
    except Exception as e:
        print(f"Error parsing date: {e}")
        return None

def parse_time(time_str: str):
    """Parse time from string in format HHMM or HH:MM"""
    try:
        # Try to parse with colon
        if ":" in time_str:
            hour, minute = time_str.split(":")
        else:
            # Try to parse without colon (HHMM)
            hour = time_str[:2]
            minute = time_str[2:]
        
        return time(int(hour), int(minute))
    except Exception as e:
        print(f"Error parsing time: {e}")
        return None

def get_weekday_abbr(date_str: str):
    """
    Returns the German weekday abbreviation for a date in format DD.MM.YYYY.
    Returns the abbreviation in parentheses like '(Mo)', '(Di)', etc.
    """
    try:
        # Parse the date from DD.MM.YYYY format
        day, month, year = map(int, date_str.split('.'))
        date_obj = datetime(int(year), int(month), int(day))
        weekday = date_obj.weekday()
        
        # German abbreviations for weekdays
        weekday_abbrs = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
        return f"{weekday_abbrs[weekday]}"
    except Exception as e:
        logger.error(f"Error getting weekday: {e}")
        return ""

def save_event_to_json(event):
    try:
        # Check if file exists, create it if not
        if not os.path.exists(EVENTS_JSON_FILE):
            logger.info(f"Creating new events file: {EVENTS_JSON_FILE}")
            with open(EVENTS_JSON_FILE, 'w') as f:
                json.dump({"events": []}, f, indent=4)
        
        # Load existing events
        with open(EVENTS_JSON_FILE, 'r') as f:
            try:
                events_data = json.load(f)
                logger.info(f"Loaded {len(events_data.get('events', []))} existing events from {EVENTS_JSON_FILE}")
            except json.JSONDecodeError:
                # File is corrupted, reset it
                logger.error(f"JSON file is corrupted. Resetting {EVENTS_JSON_FILE}")
                events_data = {"events": []}
        
        # Validate format
        if not isinstance(events_data, dict) or "events" not in events_data:
            logger.warning(f"Invalid format in {EVENTS_JSON_FILE}, resetting to empty events list")
            events_data = {"events": []}
        
        # Falls das Event ein Dictionary ist, berechne die Rollenanzahl neu
        if isinstance(event, dict) and not hasattr(event, 'to_dict'):
            # Berechne filled_slots und total_slots direkt hier
            filled_slots, total_slots = calculate_role_counts(event.get('roles', []), event.get('participants', {}))
            event['filled_slots'] = filled_slots
            event['total_slots'] = total_slots
            
            # Stelle sicher, dass der Status auf "active" gesetzt ist, falls es ein neues Event ist
            if 'status' not in event:
                event['status'] = "active"
                logger.info(f"Setting initial status 'active' for event: {event.get('title', 'Unknown')}")
            
            logger.info(f"Updated role counts for event: {event.get('title', 'Unknown')}, slots: {filled_slots}/{total_slots}, status: {event.get('status', 'active')}")
        
        # Check if the event already exists by the event_id
        event_exists = False
        event_id = None
        
        # Extract the event_id
        if isinstance(event, dict):
            event_id = event.get("event_id")
        else:
            event_id = getattr(event, "event_id", None)
        
        # If no event_id is present (for older events), generate one
        if not event_id:
            timestamp = datetime.now().strftime("%Y%m%d%H%M")
            random_string = str(uuid.uuid4())[:8]
            event_id = f"{timestamp}-{random_string}"
            logger.info(f"Generated new event_id: {event_id} for event: {event.get('title') if isinstance(event, dict) else event.title}")
            
            if isinstance(event, dict):
                event["event_id"] = event_id
            else:
                event.event_id = event_id
        
        # Search for the event by the ID only - this is the unique identifier
        for i, e in enumerate(events_data["events"]):
            if e.get("event_id") == event_id:
                # Update existing event
                logger.info(f"Updating existing event with ID: {event_id}")
                if hasattr(event, 'to_dict'):
                    events_data["events"][i] = event.to_dict()
                else:
                    events_data["events"][i] = event
                event_exists = True
                break
        
        # If event doesn't exist, add it as a new event
        # We no longer check for title match - this allows multiple events with the same title
        if not event_exists:
            event_title = event["title"] if isinstance(event, dict) else event.title
            logger.info(f"Adding new event: {event_title} with ID: {event_id}")
            
            # Stelle sicher, dass neue Events immer den Status "active" haben
            if hasattr(event, 'to_dict'):
                event_dict = event.to_dict()
                # Überprüfe und setze den Status für neue Events
                if event_dict.get('status') != "active":
                    logger.info(f"Ensuring new event '{event_title}' has status 'active' instead of '{event_dict.get('status')}'")
                    event_dict['status'] = "active"
                events_data["events"].append(event_dict)
            else:
                # Überprüfe und setze den Status für neue Events
                if isinstance(event, dict) and event.get('status') != "active":
                    logger.info(f"Ensuring new event '{event_title}' has status 'active' instead of '{event.get('status')}'")
                    event['status'] = "active"
                events_data["events"].append(event)
        
        # Save back to file
        with open(EVENTS_JSON_FILE, 'w') as f:
            json.dump(events_data, f, indent=4)
        
        logger.info(f"Successfully saved events to {EVENTS_JSON_FILE}, total events: {len(events_data.get('events', []))}")
        return True
    except Exception as e:
        logger.error(f"Error saving event to JSON: {e}")
        return False

def clean_old_events(events_data):
    """Markiert Events als abgelaufen (expired), wenn sie seit mehr als einer Stunde begonnen haben (UTC)."""
    updated_events = []
    expired_count = 0
    already_expired = 0
    
    # Aktuelle Zeit in UTC
    now = datetime.now(timezone.utc)
    
    for event in events_data["events"]:
        current_status = event.get("status", "active")
        event_title = event.get("title", "Unknown Event")
        
        # Überspringe bereits bereinigte Events ("cleaned")
        if current_status == "cleaned":
            updated_events.append(event)
            continue
            
        # Prüfe bereits abgelaufene Events
        if current_status == "expired":
            already_expired += 1
            updated_events.append(event)
            continue
            
        try:
            # Verwende das datetime_obj (ist bereits in UTC)
            if "datetime_obj" in event and event["datetime_obj"]:
                event_dt = datetime.fromisoformat(event["datetime_obj"])
                if event_dt.tzinfo is None:
                    event_dt = event_dt.replace(tzinfo=timezone.utc)
                
                # Prüfe ob Event seit mehr als einer Stunde läuft (alles in UTC)
                if now > event_dt + timedelta(hours=1) and current_status == "active":
                    event["status"] = "expired"
                    expired_count += 1
                    logger.info(f"Event expired (UTC): {event_title} (Started: {event_dt}, Current: {now}")
            
        except Exception as e:
            logger.error(f"Error processing event {event_title}: {e}")
        
        updated_events.append(event)
    
    if expired_count > 0:
        logger.info(f"Marked {expired_count} events as expired")
    
    if already_expired > 0:
        logger.info(f"Found {already_expired} events already marked as expired")
    
    events_data["events"] = updated_events
    return events_data

def load_upcoming_events(include_expired=False, include_cleaned=False):
    """
    Lade Events aus der JSON-Datei mit optionaler Statusfilterung
    
    Args:
        include_expired: Wenn True, werden auch abgelaufene Events (status="expired") zurückgegeben
        include_cleaned: Wenn True, werden auch bereinigte Events (status="cleaned") zurückgegeben
        
    Returns:
        Dictionary mit Events, gefiltert nach Status
    """
    try:
        # Use absolute path from the script's location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        events_file = os.path.join(script_dir, 'events.json')
        
        if not os.path.exists(events_file):
            logger.info("events.json nicht gefunden - erstelle neue Datei")
            # Create the file with empty events list
            with open(events_file, 'w', encoding='utf-8') as f:
                json.dump({"events": []}, f, indent=4)
            return {"events": []}
            
        with open(events_file, 'r', encoding='utf-8') as f:
            events = json.load(f)
            if not isinstance(events, dict):
                logger.error("Invalid events format in events.json")
                return {"events": []}
            if "events" not in events:
                logger.error("Missing 'events' key in events.json")
                return {"events": []}
            
            # Aktualisiere Status der Events
            events = clean_old_events(events)
            
            # Speichere die aktualisierten Status zurück
            with open(events_file, 'w', encoding='utf-8') as f:
                json.dump(events, f, indent=4)
            
            # Filtere nach Status, falls erforderlich
            if not include_expired and not include_cleaned:
                # Nur aktive Events für die Anzeige
                filtered_events = {"events": []}
                
                for event in events["events"]:
                    if event.get("status", "active") == "active":
                        filtered_events["events"].append(event)
                
                logger.info(f"Loaded {len(filtered_events['events'])} active events from events.json")
                return filtered_events
            elif not include_cleaned:
                # Aktive und abgelaufene Events (für Thread-Management)
                filtered_events = {"events": []}
                
                for event in events["events"]:
                    if event.get("status", "active") != "cleaned":
                        filtered_events["events"].append(event)
                
                logger.info(f"Loaded {len(filtered_events['events'])} non-cleaned events from events.json")
                return filtered_events
            else:
                # Alle Events (für administrative Zwecke)
                logger.info(f"Loaded all {len(events['events'])} events from events.json")
                return events
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding events.json: {e}")
        return {"events": []}
    except Exception as e:
        logger.error(f"Unexpected error loading events: {e}")
        return {"events": []}

def save_events_to_json(events):
    """Save events to JSON file"""
    try:
        # Ensure we have the right format
        if isinstance(events, list):
            events_data = {"events": events}
        elif isinstance(events, dict) and "events" in events:
            events_data = events
        else:
            logger.error("Invalid events format for save_events_to_json")
            return False
            
        # Aktualisiere Rollenanzahl für alle Dictionary-Events
        for event in events_data.get("events", []):
            if isinstance(event, dict) and not hasattr(event, 'to_dict'):
                # Berechne filled_slots und total_slots
                filled_slots, total_slots = calculate_role_counts(event.get('roles', []), event.get('participants', {}))
                event['filled_slots'] = filled_slots
                event['total_slots'] = total_slots
            
        # Aktualisiere Event-Status (markiere abgelaufene Events)
        events_data = clean_old_events(events_data)
            
        # Use absolute path from the script's location
        script_dir = os.path.dirname(os.path.abspath(__file__))
        events_file = os.path.join(script_dir, 'events.json')
        
        with open(events_file, 'w', encoding='utf-8') as f:
            json.dump(events_data, f, indent=4)
        logger.info(f"Successfully saved events to events.json, total events: {len(events_data['events'])}")
        return True
    except Exception as e:
        logger.error(f"Error saving events to JSON: {e}")
        return False

@bot.tree.command(name="eventify", description="Erstelle ein Event")
@app_commands.describe(
    title="Der Titel des Events",
    date="Das Datum des Events (DDMMYYYY)",
    time="Die Uhrzeit des Events (HHMM)",
    description="Optional: Die Beschreibung des Events (\\n für Zeilenumbrüche)",
    roles="Optional: Gib die Rollen ein (diesen Parameter weglassen für Nur-Teilnehmer-Modus)",
    mention_role="Optional: Eine Rolle, die beim Event erwähnt werden soll",
    image_url="Optional: Ein Link zu einem Bild, das im Event angezeigt werden soll"
)
async def eventify(
    interaction: discord.Interaction, 
    title: str,
    date: str,
    time: str,
    mention_role: discord.Role,
    description: str = None,
    roles: str = None,
    image_url: str = None
):
    try:
        # Check title length (max 40 characters)
        if len(title) > 40:
            await interaction.response.send_message("Der Titel darf maximal 40 Zeichen lang sein.", ephemeral=True)
            return

        # Verwende die verbesserte Funktion für Zeitzonen-Konvertierung
        full_datetime = local_to_utc(None, is_date_time_string=True, date_str=date, time_str=time)
        
        if not full_datetime:
            await interaction.response.send_message("Ungültiges Datum oder ungültige Zeit. Bitte verwende die Formate DDMMYYYY und HHMM.", ephemeral=True)
            return
        
        # Check if the date is in the future
        if full_datetime < datetime.now(timezone.utc):
            await interaction.response.send_message("Das Datum muss in der Zukunft liegen.", ephemeral=True)
            return

        # Format date and time for display (local time)
        local_format = format_local_datetime(full_datetime)
        formatted_date = local_format["date"]
        formatted_time = local_format["time"]
        
        logger.info(f"Creating event: {title} at {formatted_date} {formatted_time} (UTC: {full_datetime.isoformat()})")

        if description is not None:
            # Direct event creation without modal
            # Replace literal \n with actual line breaks
            description = description.replace('\\n', '\n')
            # Behandle roles=None als leeren String (für Teilnehmer-only Modus)
            roles_input = roles.replace('\\n', '\n').strip() if roles else ""
            
            # Check if we're in participant-only mode
            is_participant_only_mode = not roles_input
            fill_index = None
            
            if is_participant_only_mode:
                # For empty input, create only a "Teilnehmer" role
                roles_list = ["Teilnehmer"]
            else:
                # Normal mode with Fill role
                roles_list = [role.strip() for role in roles_input.splitlines() if role.strip()]
                
                # Process section headers to ensure they're consistent
                for i, role in enumerate(roles_list):
                    # Check if it's a section header (text in parentheses)
                    if role.strip().startswith('(') and role.strip().endswith(')'):
                        # Remove parentheses and make sure it's stored without them
                        header_text = role.strip()[1:-1].strip()  # Remove first and last character and any whitespace
                        roles_list[i] = f"({header_text})"  # Store in a consistent format
                
                # Find the Fill role - case insensitive check
                fill_index = next((i for i, role in enumerate(roles_list) if role.lower() in ["fill", "fillall"]), None)
                if fill_index is None:
                    # If no Fill role found, add one
                    fill_index = len(roles_list)
                    roles_list.append("FILLALL")
                else:
                    # Make sure it's consistently named "FILLALL"
                    roles_list[fill_index] = "FILLALL"
                
                # Make sure FILLALL is always the last role
                if fill_index < len(roles_list) - 1:
                    # Remove FILLALL from its current position
                    fill_role = roles_list.pop(fill_index)
                    # Add it back at the end
                    roles_list.append(fill_role)
                    # Update the fill_index to match the new position
                    fill_index = len(roles_list) - 1
            
            # Create event object
            event = Event(
                title=title,
                date=formatted_date,
                time=formatted_time,
                description=description,
                roles=roles_list,
                datetime_obj=full_datetime,
                caller_id=str(interaction.user.id),
                caller_name=interaction.user.display_name,
                participant_only_mode=is_participant_only_mode
            )
            
            # Store the mention role ID separately in the event object
            if mention_role:
                event.mention_role_id = str(mention_role.id)
                
            # Add the image URL if provided
            if image_url:
                event.image_url = image_url
                
            # Save the event to JSON
            save_event_to_json(event)
            
            # Respond to interaction to avoid timeout
            await interaction.response.defer(ephemeral=True, thinking=False)
            
            channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
            
            # Create embed with horizontal frames
            embed = discord.Embed(title=f"__**{event.title}**__", color=0x0dceda)
            
            # Get weekday abbreviation
            weekday = get_weekday_abbr(event.date)
            
            # Add date and time as inline fields (only these two in the first row)
            embed.add_field(name="Datum", value=f"{event.date} ({weekday})", inline=True)
            embed.add_field(name="Uhrzeit", value=event.time, inline=True)
            # Add a blank field to ensure only 2 fields in the first row
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Add creator and mention role as inline fields (in the second row)
            creator_mention = f"<@{event.caller_id}>" if event.caller_id else "Unbekannt"
            
            embed.add_field(name="Von", value=creator_mention, inline=True)
            
            if event.mention_role_id:
                embed.add_field(name="Für", value=f"<@&{event.mention_role_id}>", inline=True)
            else:
                # Add an empty field to maintain alignment
                embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Add a blank field to ensure only 2 fields in the second row
            embed.add_field(name="\u200b", value="\u200b", inline=True)
            
            # Truncate description if it's too long (Discord limit is 1024 characters per field)
            description_text = event.description
            if description_text:
                if len(description_text) > 1020:  # Leave room for ellipsis
                    description_text = description_text[:1020] + "..."
                embed.add_field(name="Beschreibung", value=description_text, inline=False)
            
            # Add image if provided (direkt nach der Beschreibung)
            if image_url:
                embed.set_image(url=image_url)
            
            # Extract regular roles (everything except FILLALL)
            regular_roles = []
            section_headers = []
            for i, role in enumerate(roles_list):
                if i != fill_index:  # Everything except the FILLALL role
                    # Check if it's a section header (text in parentheses)
                    if role.strip().startswith('(') and role.strip().endswith(')'):
                        section_headers.append((i, role))
                    else:
                        regular_roles.append((i, role))

            # Create content for all regular roles
            field_content = ""
            role_counter = 1  # Counter for actual roles (excluding section headers)

            # Go through all roles and section headers in the original order
            all_items = section_headers + regular_roles
            all_items.sort(key=lambda x: x[0])  # Sort by original index

            for role_idx, role_name in all_items:
                # Check if it's a section header
                if role_name.strip().startswith('(') and role_name.strip().endswith(')'):
                    # Remove parentheses from section header
                    header_text = role_name.strip()[1:-1]  # Remove first and last character
                    field_content += f"*-----{header_text}-----*\n"
                else:
                    # This is a normal role
                    field_content += f"{role_counter}. {role_name}\n"
                    role_counter += 1

            # Add all regular roles as a single field
            if field_content:
                # Count total roles (excluding section headers and FILLALL)
                total_roles = len([r for r in roles_list if not (r.strip().startswith('(') and r.strip().endswith(')')) and r.lower() not in ["fill", "fillall"]])
                if is_participant_only_mode:
                    embed.add_field(name="Rollen (0)", value=field_content, inline=False)
                else:
                    embed.add_field(name=f"Rollen (0/{total_roles})", value=field_content, inline=False)
            
            # Add Fill role section
            if fill_index is not None:
                fill_text = f"{role_counter}. {roles_list[fill_index]}"
                
                # Get participants for Fill role
                fill_key = f"{fill_index}:{roles_list[fill_index]}"
                fill_participants = event.participants.get(fill_key, [])
                
                if fill_participants:
                    # Sort participants by timestamp
                    sorted_fill = sorted(fill_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                    
                    # Display all participants for FillALL without extra newline
                    fill_players_text = fill_text + "\n" + "\n".join([f"<@{p[1]}>" + (f" {p[3][:30] + '...' if len(p) > 3 and p[3] and len(p[3]) > 30 else p[3]}" if len(p) > 3 and p[3] else "") for p in sorted_fill if len(p) >= 2])
                    
                    # Add Fill role to embed with empty name to reduce spacing
                    embed.add_field(name="", value=fill_players_text or fill_text, inline=False)
                else:
                    # Display empty Fill role with empty name to reduce spacing
                    embed.add_field(name="", value=fill_text, inline=False)
            
            # Send the event post and create a thread
            # Create a simplified embed without image for initial posting
            temp_embed = discord.Embed(
                title=f"__**{event.title}**__",
                color=0x0dceda
            )
            # Add only essential information
            temp_embed.add_field(name="Datum", value=f"{event.date} ({weekday})", inline=True)
            temp_embed.add_field(name="Uhrzeit", value=event.time, inline=True)
            
            # Send the temporary event post without the image
            event_post = await channel.send(embed=temp_embed)
            logger.info(f"Temporary event post created for '{event.title}' with message ID: {event_post.id}")
            
            try:
                logger.info(f"Attempting to create thread for '{event.title}'")
                logger.info(f"Event post exists with ID: {event_post.id}, channel ID: {event_post.channel.id}")
                logger.info(f"Thread creation parameters: name='{event.title}'")
                logger.info(f"Bot permissions in channel: {channel.permissions_for(interaction.guild.me).value}")
                
                # Create thread directly without retries
                logger.info(f"[Thread Creation] Starting thread creation attempt for event '{event.title}'")
                thread = await event_post.create_thread(name=event.title)
                logger.info(f"[Thread Creation] Thread creation successful with thread ID: {thread.id}")
                
                # Now update the original message with the complete embed including image
                await event_post.edit(embed=embed)
                logger.info(f"Updated event post with complete embed including image")
                
                logger.info(f"Thread successfully created for '{event.title}' with thread ID: {thread.id}")
                logger.info(f"Thread details: name='{thread.name}', owner_id={thread.owner_id}, parent_id={thread.parent_id}, archived={thread.archived}, locked={thread.locked}")
                
                # Save both message ID and thread ID
                event.message_id = event_post.id
                event.thread_id = thread.id
                logger.info(f"Saving event with thread_id: {thread.id} and message_id: {event_post.id}")
                save_event_to_json(event)
                logger.info(f"[Thread Creation] Event saved to JSON with thread_id: {thread.id}")
                
                # Debug-Log hinzufügen
                logger.info(f"Event created: {event.title}, thread_id: {thread.id}, message_id: {event_post.id}")
                
                welcome_embed = discord.Embed(
                    description="Bei Fragen hilft dir das [Benutzerhandbuch](https://github.com/nox1104/Eventify/blob/main/Benutzerhandbuch.md).",
                    color=0x0dceda  # Eventify Cyan
                )

                # Log thread state before sending message
                logger.info(f"[Thread Creation] Thread state before welcome message: archived={thread.archived}, locked={thread.locked}, type={type(thread).__name__}")
                
                try:
                    welcome_msg = await thread.send(embed=welcome_embed)
                    logger.info(f"[Thread Creation] Welcome message sent successfully with ID: {welcome_msg.id}")
                except Exception as e:
                    logger.error(f"[Thread Creation] Failed to send welcome message: {str(e)}")
                    # Continue despite welcome message failure
                
                # Send a separate mention message if a mention role is specified
                if event.mention_role_id:
                    try:
                        # Send mention but delete it right after (will still notify users)
                        mention_msg = await thread.send(f"<@&{event.mention_role_id}> - {event.title}, {event.date}, {event.time}", delete_after=0.1)
                        logger.info(f"[Thread Creation] Mention message sent successfully with ID: {mention_msg.id}")
                    except Exception as e:
                        logger.error(f"[Thread Creation] Failed to send mention message: {str(e)}")
                        # Continue despite mention message failure
                
                # Verify event data is properly stored
                try:
                    # Reload events from JSON to verify the event was properly saved
                    verification_events = load_upcoming_events(include_expired=True)
                    verification_event = next((e for e in verification_events["events"] if e.get('thread_id') == thread.id), None)
                    
                    if verification_event:
                        logger.info(f"[Thread Creation] Event verification successful - found event in JSON with thread_id: {thread.id}")
                    else:
                        logger.error(f"[Thread Creation] Event verification FAILED - could not find event in JSON with thread_id: {thread.id}")
                        # Try to save again
                        logger.info(f"[Thread Creation] Attempting to save event again...")
                        save_event_to_json(event)
                except Exception as e:
                    logger.error(f"[Thread Creation] Error during event verification: {str(e)}")
                
                # Aktualisiere die Eventübersicht
                try:
                    await create_event_listing(interaction.guild)
                    logger.info(f"[Thread Creation] Event listing updated successfully")
                except Exception as e:
                    logger.error(f"[Thread Creation] Failed to update event listing: {str(e)}")
                    # Continue despite event listing failure
                
                # Send ephemeral confirmation message
                await interaction.followup.send("Dein Event wurde erstellt.", ephemeral=True)
            except discord.Forbidden as e:
                error_msg = f"Keine Berechtigung zum Erstellen des Threads für '{event.title}': {str(e)}"
                logger.error(error_msg)
                # Try to delete the event post since we couldn't create a thread
                try:
                    await event_post.delete()
                    logger.info(f"Deleted event post for '{event.title}' due to thread creation failure")
                except:
                    logger.error(f"Failed to delete event post for '{event.title}' after thread creation failure")
                
                # Try to send error message
                try:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                except:
                    try:
                        await interaction.followup.send(error_msg, ephemeral=True)
                    except:
                        logger.error("Couldn't send error message to user")
            except discord.HTTPException as e:
                error_msg = f"Discord API Fehler beim Erstellen des Threads für '{event.title}': {str(e)}"
                logger.error(error_msg)
                # Try to delete the event post since we couldn't create a thread
                try:
                    await event_post.delete()
                    logger.info(f"Deleted event post for '{event.title}' due to thread creation failure")
                except:
                    logger.error(f"Failed to delete event post for '{event.title}' after thread creation failure")
                
                # Try to send error message
                try:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                except:
                    try:
                        await interaction.followup.send(error_msg, ephemeral=True)
                    except:
                        logger.error("Couldn't send error message to user")
            except Exception as e:
                error_msg = f"Unerwarteter Fehler beim Erstellen des Threads für '{event.title}': {str(e)}"
                logger.error(error_msg)
                logger.error("Stack trace:", exc_info=True)
                
                # Save diagnostic information about the failure
                save_thread_failure_info(event.title, event_post.id, {"error_type": type(e).__name__, "error_message": str(e)})
                
                # Try to delete the event post since we couldn't create a thread
                try:
                    await event_post.delete()
                    logger.info(f"Deleted event post for '{event.title}' due to thread creation failure")
                except:
                    logger.error(f"Failed to delete event post for '{event.title}' after thread creation failure")
                
                # Try to send error message
                try:
                    await interaction.response.send_message(error_msg, ephemeral=True)
                except:
                    try:
                        await interaction.followup.send(error_msg, ephemeral=True)
                    except:
                        logger.error("Couldn't send error message to user")
        else:
            # Create and show the modal
            modal = EventModal(
                title=title, 
                date=formatted_date, 
                time=formatted_time,
                caller_id=str(interaction.user.id),
                caller_name=interaction.user.display_name,
                mention_role=mention_role,
                image_url=image_url
            )
            modal.full_datetime = full_datetime
            await interaction.response.send_modal(modal)
    except Exception as e:
        print(f"Error in create_event: {e}")
        await interaction.response.send_message(f"Ein Fehler ist aufgetreten: {str(e)}", ephemeral=True)

@bot.tree.command(name="remind", description="Sende eine Erinnerung an alle eingetragenen Teilnehmer")
@app_commands.guild_only()
async def remind_participants(interaction: discord.Interaction, comment: str = None):
    try:
        # Check if the command is executed in a thread
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("Dieser Befehl kann nur in einem Event-Thread verwendet werden.", ephemeral=True)
            return

        # Load the event (auch abgelaufene Events einschließen)
        events_data = load_upcoming_events(include_expired=True)
        # First try to find the event by thread_id (most reliable)
        thread_id = interaction.channel.id
        event = next((e for e in events_data["events"] if e.get('thread_id') == thread_id), None)
        
        # Fallback: try to find by title (for backwards compatibility)
        if not event:
            event = next((e for e in events_data["events"] if e.get('title') == interaction.channel.name), None)

        if not event:
            await interaction.response.send_message("Kein passendes Event für diesen Thread gefunden.", ephemeral=True)
            return
            
        # Prüfe, ob das Event abgesagt wurde
        if event.get('status') == "canceled" or "[ABGESAGT]" in event.get('title', ''):
            await interaction.response.send_message("Dieses Event wurde abgesagt. Erinnerungen können nicht mehr versendet werden.", ephemeral=True)
            return

        # Prüfe, ob mehr als 1 Stunde seit Eventbeginn vergangen ist
        try:
            # Event-Zeit direkt aus datetime_obj verwenden
            event_dt = datetime.fromisoformat(event.get('datetime_obj'))
            now = datetime.now(timezone.utc)
            
            # Wenn mehr als 1 Stunde seit Eventbeginn vergangen ist, Slash-Befehl blockieren
            if now > event_dt + timedelta(hours=1):
                # Benutzer informieren (ephemeral im Thread)
                await interaction.response.send_message("Erinnerungen sind nicht mehr möglich, da das Event vor über einer Stunde begonnen hat.", ephemeral=True)
                logger.info(f"Blocked /remind command from {interaction.user.name} - event {event.get('title')} started more than 1 hour ago")
                return
        except Exception as e:
            logger.error(f"Error checking event time for /remind command: {e}")
            # Im Fehlerfall Command dennoch erlauben

        # Remove the check that restricts to event creator
        # if str(interaction.user.id) != event.get('caller_id'):
        #     await interaction.response.send_message("Nur der Event-Ersteller kann Erinnerungen versenden.", ephemeral=True)
        #     return

        # Create the event link
        message_id = event.get('message_id')
        guild_id = interaction.guild.id
        event_link = f"https://discord.com/channels/{guild_id}/{CHANNEL_ID_EVENT}/{message_id}" if message_id else None

        # Collect all unique participants
        participant_ids = set()
        for role_key, participants in event.get('participants', {}).items():
            for participant in participants:
                if len(participant) >= 2:  # Ensure we have an ID
                    participant_ids.add(participant[1])  # participant[1] is the Discord ID

        # Send DMs to all participants
        success_count = 0
        failed_count = 0
        for participant_id in participant_ids:
            try:
                user = await interaction.client.fetch_user(int(participant_id))
                if user:
                    reminder_message = (
                        f"**Erinnerung** an Event: {event['title']}\n"
                        f"Datum: {event['date']} ({get_weekday_abbr(event['date'])})\n"
                        f"Uhrzeit: {event['time']}\n"
                    )
                    
                    # Add the custom message if it exists
                    if comment:
                        reminder_message += f"Kommentar: **{comment}**\n"
                    
                    if event_link:
                        reminder_message += f"[Zum Event]({event_link})"
                    
                    await user.send(reminder_message)
                    success_count += 1
            except Exception as e:
                logger.error(f"Failed to send reminder to user {participant_id}: {e}")
                failed_count += 1
        
        # Add message in thread about the reminder
        comment_text = ""
        if comment:
            comment_text = f"\nKommentar: **{comment}**"
        await interaction.response.send_message(
            f"**{interaction.user.display_name}** hat alle Teilnehmer per DN an das Event erinnert.{comment_text}"
        )

    except Exception as e:
        logger.error(f"Error in remind_participants: {e}")
        await interaction.response.send_message(
            "Ein Fehler ist beim Versenden der Erinnerungen aufgetreten.", 
            ephemeral=True
        )

@bot.tree.command(name="cancel", description="Sagt ein Event ab und benachrichtigt alle Teilnehmer")
@app_commands.describe(
    reason="Optional: Der Grund für die Absage des Events"
)
@app_commands.guild_only()
async def cancel_event(interaction: discord.Interaction, reason: str = None):
    """Sagt ein Event ab, benachrichtigt Teilnehmer und aktualisiert die Eventübersicht."""
    try:
        # Überprüfen, ob der Befehl in einem Event-Thread verwendet wird
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("Dieser Befehl kann nur in einem Event-Thread verwendet werden.", ephemeral=True)
            return
        
        thread = interaction.channel
        
        # Events laden
        events_data = load_upcoming_events()
        if not events_data or "events" not in events_data:
            await interaction.response.send_message("Keine Events gefunden.", ephemeral=True)
            return
        
        # Event finden
        event = None
        for e in events_data["events"]:
            if str(e.get("thread_id")) == str(thread.id):
                event = e
                break
        
        if not event:
            await interaction.response.send_message("Kein zugehöriges Event gefunden.", ephemeral=True)
            return
        
        # Überprüfen, ob der Benutzer der Event-Ersteller ist
        if str(interaction.user.id) != str(event.get("caller_id")):
            await interaction.response.send_message("Du kannst nur Events absagen, die du selbst erstellt hast.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        # Event als abgesagt markieren
        event["title"] = f"[ABGESAGT] {event['title']}"
        event["status"] = "canceled"  # Setze den Status auf abgesagt
        
        # Event-Nachricht aktualisieren
        try:
            channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
            message_id = event.get("message_id")
            if channel and message_id:
                message = await channel.fetch_message(int(message_id))
                if message:
                    # Embed bearbeiten
                    embeds = message.embeds
                    if embeds:
                        embed = embeds[0]
                        embed.title = f"__**{event['title']}**__"
                        await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Event-Nachricht: {e}")
        
        # Erstelle Event-Link
        event_link = None
        try:
            guild_id = interaction.guild.id
            message_id = event.get("message_id")
            if message_id:
                event_link = f"https://discord.com/channels/{guild_id}/{CHANNEL_ID_EVENT}/{message_id}"
        except Exception as e:
            logger.error(f"Fehler beim Erstellen des Event-Links: {e}")

        # Alle Teilnehmer benachrichtigen
        participants = []
        notified_user_ids = set()  # Track user IDs that have already been notified
        for role_key, role_participants in event.get("participants", {}).items():
            for participant in role_participants:
                if len(participant) >= 2:
                    user_id = int(participant[1])
                    if user_id not in notified_user_ids:
                        participants.append(participant)
                        notified_user_ids.add(user_id)
        
        # Erstelle die Absage-Nachricht
        cancel_message = f"**Event abgesagt:** {event['title']}\nDatum: {event['date']} \nZeit: {event['time']}"
        if reason:
            cancel_message += f"\nGrund: **{reason}**"
        if event_link:
            cancel_message += f"\n[Zum Event]({event_link})"
        
        # Sende Nachricht an alle Teilnehmer
        sent_count = 0
        for participant_data in participants:
            try:
                user_id = int(participant_data[1])
                user = await interaction.client.fetch_user(user_id)
                if user:
                    await user.send(cancel_message)
                    sent_count += 1
            except Exception as e:
                logger.error(f"Error sending cancellation DM to {user_id}: {e}")

        # Event speichern (nicht mehr löschen)
        save_events_to_json(events_data)
        
        # Neue Eventübersicht erstellen
        await create_event_listing(interaction.guild)
        
        # Thread-Nachricht senden und Thread-Name aktualisieren wenn möglich
        if reason:
            thread_message = f"Event wurde abgesagt. Grund: **{reason}**\nAn- und Abmeldungen sowie weitere Aktionen sind nicht mehr möglich."
        else:
            thread_message = f"**Event wurde abgesagt.**\nAn- und Abmeldungen sowie weitere Aktionen sind nicht mehr möglich."

        # Bestätigung senden
        await interaction.followup.send(f"Event wurde abgesagt. {sent_count} Benutzer wurden benachrichtigt. Der Thread bleibt für Diskussionen erhalten.")
        
        # Versuche, den Thread-Namen zu aktualisieren (wenn möglich)
        try:
            await thread.edit(name=f"[ABGESAGT] {thread.name}")
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Thread-Namens: {e}")
            
        # Thread-Nachricht senden nachdem der Thread-Name aktualisiert wurde
        await thread.send(thread_message)
    except Exception as e:
        logger.error(f"Fehler bei der Event-Absage: {e}")
        await interaction.followup.send(f"Ein Fehler ist aufgetreten: {str(e)}")

@bot.tree.command(name="add", description="Füge einen Teilnehmer zu einer Rolle hinzu")
@app_commands.guild_only()
async def add_participant(
    interaction: discord.Interaction, 
    user: discord.Member, 
    role_number: int, 
    comment: str = None
):
    try:
        # Check if the command is executed in a thread
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("Dieser Befehl kann nur in einem Event-Thread verwendet werden.", ephemeral=True)
            return

        # Load the event (auch abgelaufene Events einschließen)
        events_data = load_upcoming_events(include_expired=True)
        # First try to find the event by thread_id (most reliable)
        thread_id = interaction.channel.id
        event = next((e for e in events_data["events"] if e.get('thread_id') == thread_id), None)
        
        # Fallback: try to find by title (for backwards compatibility)
        if not event:
            event = next((e for e in events_data["events"] if e.get('title') == interaction.channel.name), None)

        if not event:
            await interaction.response.send_message("Kein passendes Event für diesen Thread gefunden.", ephemeral=True)
            return
        
        # Prüfe, ob das Event abgesagt wurde
        if event.get('status') == "canceled" or "[ABGESAGT]" in event.get('title', ''):
            await interaction.response.send_message("Dieses Event wurde abgesagt. Anmeldungen sind nicht mehr möglich.", ephemeral=True)
            return
        
        # Prüfe, ob mehr als 1 Stunde seit Eventbeginn vergangen ist
        try:
            # Event-Zeit direkt aus datetime_obj verwenden
            event_dt = datetime.fromisoformat(event.get('datetime_obj'))
            now = datetime.now(timezone.utc)
            
            # Wenn mehr als 1 Stunde seit Eventbeginn vergangen ist, Slash-Befehl blockieren
            if now > event_dt + timedelta(hours=1):
                # Benutzer informieren (ephemeral im Thread)
                await interaction.response.send_message("Teilnehmer können nicht mehr hinzugefügt werden, da das Event vor über einer Stunde begonnen hat.", ephemeral=True)
                logger.info(f"Blocked /add command from {interaction.user.name} - event {event.get('title')} started more than 1 hour ago")
                return
        except Exception as e:
            logger.error(f"Error checking event time for /add command: {e}")
            # Im Fehlerfall Command dennoch erlauben

        # Remove the check that restricts to event creator
        # if str(interaction.user.id) != event.get('caller_id'):
        #     await interaction.response.send_message("Nur der Event-Ersteller kann Teilnehmer hinzufügen.", ephemeral=True)
        #     return
        
        # Convert the displayed role number to the actual index
        actual_role_index = bot.role_number_to_index(event, role_number)
        
        if actual_role_index < 0:
            await interaction.response.send_message(f"Ungültige Rollennummer: {role_number}", ephemeral=True)
            return
            
        # Get the role name
        role_name = event['roles'][actual_role_index]
        role_key = f"{actual_role_index}:{role_name}"
        
        # Initialisiere participants dict falls nötig
        if 'participants' not in event:
            event['participants'] = {}
            
        if role_key not in event['participants']:
            event['participants'][role_key] = []
            
        # Check if the participant is already registered for this role
        player_name = user.display_name
        player_id = str(user.id)
        current_time = datetime.now().timestamp()
        
        existing_entry = next((i for i, entry in enumerate(event['participants'][role_key]) 
                              if entry[1] == player_id), None)
                              
        if existing_entry is not None:
            # Participant is already registered, update only the comment if it exists
            if comment:
                # Limit comment to 30 characters
                if len(comment) > 30:
                    comment = comment[:30] + "..."
                existing_data = event['participants'][role_key][existing_entry]
                if len(existing_data) >= 4:
                    event['participants'][role_key][existing_entry] = (existing_data[0], existing_data[1], existing_data[2], comment)
                else:
                    event['participants'][role_key][existing_entry] = (existing_data[0], existing_data[1], existing_data[2], comment)
                
                await interaction.response.send_message(f"Kommentar für **{player_name}** in Rolle **{role_name}** aktualisiert.\nNeuer Kommentar: **{comment}**")
            else:
                await interaction.response.send_message(f"{player_name} ist bereits für Rolle **{role_name}** eingetragen.")
            
            # Inform the participant about the comment update
            try:
                event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                dm_message = (
                    f"**{event['caller_name']}** hat deinen Kommentar für die Rolle **{role_name}** aktualisiert.\n"
                    f"Event: {event['title']}\n"
                    f"Datum: {event['date']} ({get_weekday_abbr(event['date'])})\n"
                    f"Uhrzeit: {event['time']}\n"
                    f"Neuer Kommentar: **{comment}**\n"

                    f"[Zum Event]({event_link})"
                )
                await user.send(dm_message)
            except Exception as e:
                logger.error(f"Failed to send DM to user {user.id}: {e}")
                
        else:
            # Check if we're in participant_only_mode - in that case, we can add multiple people to the same role
            is_participant_only = event.get('participant_only_mode', False)
            
            # Check if this is the "Fill" role by name
            is_fill_role = role_name.lower() == "fill" or role_name.lower() == "fillall"
            is_fillall_role = role_name.lower() == "fillall"
            
            # FILLALL special handling - if adding to FILLALL, remove from regular roles
            if is_fillall_role:
                removed_roles = []
                
                # First remove user from any regular roles
                for r_idx, r_name in enumerate(event['roles']):
                    # Skip FILLALL roles and headers in the check
                    if (r_name.lower() == "fill" or r_name.lower() == "fillall" or 
                        (r_name.startswith('(') and r_name.endswith(')'))):
                        continue
                    
                    r_key = f"{r_idx}:{r_name}"
                    if r_key in event.get('participants', {}):
                        # Find and remove the player if present
                        initial_count = len(event['participants'][r_key])
                        event['participants'][r_key] = [p for p in event['participants'][r_key] if p[1] != player_id]
                        if initial_count > len(event['participants'][r_key]):
                            removed_roles.append(r_name)
                            logger.info(f"Removed {player_name} from role {r_name} when adding to FILLALL")
                
                # Modify thread message to include removed roles information
                thread_message = f"**{interaction.user.display_name}** hat **{player_name}** zur Rolle **{role_name}** hinzugefügt."
                if removed_roles:
                    thread_message += f" (Automatisch entfernt aus: **{', '.join(removed_roles)}**)"
                if comment:
                    thread_message += f"\nKommentar: **{comment}**"
                await interaction.response.send_message(thread_message)
                
                # Notify the user about the role assignment and removals
                try:
                    event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                    dm_message = f"Du wurdest von **{interaction.user.display_name}** für die Rolle **{role_name}** eingetragen.\n"
                    
                    if removed_roles:
                        dm_message += f"(Automatisch entfernt aus: **{', '.join(removed_roles)}**)\n"
                    
                    dm_message += (
                        f"Event: {event['title']}\n"
                        f"Datum: {event['date']} ({get_weekday_abbr(event['date'])})\n"
                        f"Uhrzeit: {event['time']}\n"
                    )
                    if comment:
                        dm_message += f"Kommentar: **{comment}**\n"
                    dm_message += f"[Zum Event]({event_link})"
                    await user.send(dm_message)
                except Exception as e:
                    logger.error(f"Failed to send DM to user {user.id}: {e}")
                
                # Add the participant to the FILLALL role
                entry = [player_name, player_id, current_time]
                if comment:
                    # Limit comment to 30 characters
                    if len(comment) > 30:
                        comment = comment[:30] + "..."
                    entry.append(comment)
                event['participants'][role_key].append(tuple(entry))
                
                # Update the event and save to JSON
                save_event_to_json(event)
                await bot.update_event_message(interaction.channel, event)
                return
            
            # For regular roles, check if player is in FILLALL and remove them
            elif not is_fill_role:
                fillall_removed = False
                fillall_role_name = None
                
                for r_idx, r_name in enumerate(event['roles']):
                    if r_name.lower() in ["fill", "fillall"]:
                        fillall_role_name = r_name
                        r_key = f"{r_idx}:{r_name}"
                        if r_key in event.get('participants', {}):
                            # Find and remove the player if present
                            initial_count = len(event['participants'][r_key])
                            event['participants'][r_key] = [p for p in event['participants'][r_key] if p[1] != player_id]
                            if initial_count > len(event['participants'][r_key]):
                                logger.info(f"Removed {player_name} from {r_name} when adding to role {role_name}")
                                fillall_removed = True
            
            # Continue with existing role assignment logic
            
            # Check if the role already has participants (except for Fill roles or participant_only_mode)
            if not is_fill_role and not is_participant_only and len(event['participants'][role_key]) > 0:
                # Get current role holder info
                current_holder = event['participants'][role_key][0]
                current_holder_id = current_holder[1]
                current_holder_name = current_holder[0]
                
                await interaction.response.send_message(
                    f"Die Rolle {role_name} ist bereits von {current_holder_name} besetzt. "
                    f"Entferne zunächst diesen Teilnehmer mit `/remove`, bevor du einen neuen hinzufügst.", 
                    ephemeral=True
                )
                return
            
            # NEW CODE: Check if user is already assigned to another role in this event (except Fill/FillALL)
            if not is_fill_role:  # Only check for regular roles
                already_in_role = None
                already_in_role_index = None
                already_in_role_key = None
                already_in_entry_idx = None
                
                for r_idx, r_name in enumerate(event['roles']):
                    # Skip Fill/FillALL roles in the check
                    if r_name.lower() == "fill" or r_name.lower() == "fillall":
                        continue
                    
                    r_key = f"{r_idx}:{r_name}"
                    if r_key in event.get('participants', {}):
                        for entry_idx, entry in enumerate(event['participants'][r_key]):
                            if entry[1] == player_id:
                                already_in_role = r_name
                                already_in_role_index = r_idx
                                already_in_role_key = r_key
                                already_in_entry_idx = entry_idx
                                break
                        
                        if already_in_role:
                            break
                
                if already_in_role:
                    # Remove player from previous role
                    event['participants'][already_in_role_key].pop(already_in_entry_idx)
                    
                    # Post a message in the thread
                    thread_message = f"**{interaction.user.display_name}** hat **{player_name}** aus der Rolle **{already_in_role}** entfernt und zur Rolle **{role_name}** hinzugefügt."
                    if comment:
                        thread_message += f"\nKommentar: **{comment}**"
                    await interaction.response.send_message(thread_message)
                    
                    # Notify the user about being moved to a different role
                    try:
                        event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                        dm_message = (
                            f"Du wurdest von **{interaction.user.display_name}** aus der Rolle **{already_in_role}** in die Rolle **{role_name}** verschoben.\n"
                        )
                        if comment:
                            dm_message += f"Kommentar: **{comment}**\n"
                        dm_message += (
                            f"Event: {event['title']}\n"
                            f"Datum: {event['date']} ({get_weekday_abbr(event['date'])})\n"
                            f"Uhrzeit: {event['time']}\n"
                            f"[Zum Event]({event_link})"
                        )
                        await user.send(dm_message)
                    except Exception as e:
                        logger.error(f"Failed to send DM to user {user.id}: {e}")
                else:
                    # Post a message in the thread
                    thread_message = f"**{interaction.user.display_name}** hat **{player_name}** zur Rolle **{role_name}** hinzugefügt."
                    if comment:
                        thread_message += f"\nKommentar: **{comment}**"
                    await interaction.response.send_message(thread_message)
                    
                    # Regular notification for new role assignment
                    try:
                        event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                        dm_message = (
                            f"Du wurdest von **{interaction.user.display_name}** in die Rolle **{role_name}** eingetragen.\n"
                        )
                        dm_message += (
                            f"Event: {event['title']}\n"
                            f"Datum: {event['date']} ({get_weekday_abbr(event['date'])})\n"
                            f"Uhrzeit: {event['time']}\n"
                        )
                        if comment:
                            dm_message += f"Kommentar: **{comment}**\n"
                        dm_message += f"[Zum Event]({event_link})"
                        await user.send(dm_message)
                    except Exception as e:
                        logger.error(f"Failed to send DM to user {user.id}: {e}")
            else:
                # For Fill/FillALL roles, post a message in the thread
                thread_message = f"**{interaction.user.display_name}** hat **{player_name}** zur Rolle **{role_name}** hinzugefügt."
                if comment:
                    thread_message += f"\nKommentar: **{comment}**"
                await interaction.response.send_message(thread_message)
                
                # Notify the user about the role assignment
                try:
                    event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                    dm_message = (
                        f"Du wurdest von **{interaction.user.display_name}** für die Rolle **{role_name}** eingetragen.\n"
                    )
                    dm_message += (
                        f"Event: {event['title']}\n"
                        f"Datum: {event['date']} ({get_weekday_abbr(event['date'])})\n"
                        f"Uhrzeit: {event['time']}\n"
                    )
                    if comment:
                        dm_message += f"Kommentar: **{comment}**\n"
                    dm_message += f"[Zum Event]({event_link})"
                    await user.send(dm_message)
                except Exception as e:
                    logger.error(f"Failed to send DM to user {user.id}: {e}")
            
            # Add the participant to the role - always do this last to avoid issues if something fails above
            entry = [player_name, player_id, current_time]
            if comment:
                # Limit comment to 30 characters
                if len(comment) > 30:
                    comment = comment[:30] + "..."
                entry.append(comment)
            event['participants'][role_key].append(tuple(entry))
        
        # Update the event and save to JSON
        save_event_to_json(event)
        await bot.update_event_message(interaction.channel, event)
        
        # Also refresh the event overview
        await create_event_listing(interaction.guild)
            
    except Exception as e:
        logger.error(f"Error in add_participant: {e}")
        await interaction.response.send_message("Ein Fehler ist beim Hinzufügen des Teilnehmers aufgetreten.", ephemeral=True)

@bot.tree.command(name="remove", description="Entferne einen Teilnehmer aus dem Event")
@app_commands.guild_only()
async def remove_participant(
    interaction: discord.Interaction, 
    user: discord.Member, 
    comment: str = None
):
    """Entfernt einen Teilnehmer aus dem Event."""
    try:
        # Prüfe, ob der Command in einem Thread ausgeführt wird
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("Dieser Command kann nur in Event-Threads verwendet werden.", ephemeral=True)
            return
        
        # Lade Event-Daten
        events_data = load_upcoming_events(include_expired=True)
        event = None
        for e in events_data["events"]:
            if e.get('thread_id') == interaction.channel.id:
                event = e
                break
        
        if not event:
            await interaction.response.send_message("Kein Event in diesem Thread gefunden.", ephemeral=True)
            return
        
        # Prüfe, ob das Event abgesagt wurde
        if event.get('canceled'):
            await interaction.response.send_message("Dieses Event wurde bereits abgesagt.", ephemeral=True)
            return
        
        # Prüfe, ob das Event bereits vor mehr als einer Stunde gestartet ist
        event_datetime = datetime.strptime(f"{event['date']} {event['time']}", "%d.%m.%Y %H:%M")
        if datetime.now() > event_datetime + timedelta(hours=1):
            await interaction.response.send_message("Das Event ist bereits vor mehr als einer Stunde gestartet.", ephemeral=True)
            return
        
        player_id = str(user.id)
        player_name = user.display_name
        
        # Suche den Benutzer in allen Rollen
        removed = False
        removed_role_name = None
        is_fillall = False
        
        for role_idx, role_name in enumerate(event['roles']):
            role_key = f"{role_idx}:{role_name}"
            if role_key in event.get('participants', {}):
                # Prüfe, ob der Benutzer in dieser Rolle ist
                initial_count = len(event['participants'][role_key])
                event['participants'][role_key] = [p for p in event['participants'][role_key] if p[1] != player_id]
                removed = initial_count - len(event['participants'][role_key]) > 0
                
                if removed:
                    removed_role_name = role_name
                    is_fillall = role_name.lower() in ["fill", "fillall"]
                    break
        
        if not removed:
            await interaction.response.send_message(f"{player_name} ist in keinem Event eingetragen.", ephemeral=True)
            return
        
        # Speichere das aktualisierte Event
        save_event_to_json(event)
        
        # Sende eine DM an den entfernten Benutzer
        try:
            event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
            dm_message = (
                f"Du wurdest von **{interaction.user.display_name}** aus dem Event **{event['title']}** entfernt.\n"
                f"Rolle: {removed_role_name}\n"
                f"Datum: {event['date']}\n"
                f"Uhrzeit: {event['time']}\n"
            )
            if comment:
                dm_message += f"Kommentar: {comment}\n"
            dm_message += f"[Zum Event]({event_link})"
            
            await user.send(dm_message)
        except Exception as e:
            logger.error(f"Failed to send DM to {player_id}: {e}")
        
        # Aktualisiere die Event-Nachricht im Thread
        try:
            guild = bot.get_guild(interaction.guild.id)
            if guild:
                thread = await bot.fetch_thread(guild, interaction.channel.id)
                if thread:
                    await bot.update_event_message(thread, event)
                    
                    # Sende eine Nachricht im Thread
                    thread_message = f"**{interaction.user.display_name}** hat **{player_name}** aus dem Event entfernt."
                    if comment:
                        thread_message += f"\nKommentar: **{comment}**"
                    await thread.send(thread_message)
                    
                    # Aktualisiere die Event-Übersicht
                    await create_event_listing(guild)
        except Exception as e:
            logger.error(f"Failed to update thread: {e}")
        
        await interaction.response.send_message(f"{player_name} wurde aus dem Event entfernt.", ephemeral=True)
        
    except Exception as e:
        logger.error(f"Error in remove_participant: {e}")
        await interaction.response.send_message("Ein Fehler ist beim Entfernen des Teilnehmers aufgetreten.", ephemeral=True)

@bot.tree.command(name="propose", description="Schlage eine neue Rolle für das Event vor")
@app_commands.guild_only()
async def propose_role(interaction: discord.Interaction, role_name: str):
    try:
        # Check if the command is executed in a thread
        if not isinstance(interaction.channel, discord.Thread):
            await interaction.response.send_message("Dieser Befehl kann nur in einem Event-Thread verwendet werden.", ephemeral=True)
            return

        # Load the event (auch abgelaufene Events einschließen)
        events_data = load_upcoming_events(include_expired=True)
        # First try to find the event by thread_id (most reliable)
        thread_id = interaction.channel.id
        event = next((e for e in events_data["events"] if e.get('thread_id') == thread_id), None)
        
        # Fallback: try to find by title (for backwards compatibility)
        if not event:
            event = next((e for e in events_data["events"] if e.get('title') == interaction.channel.name), None)

        if not event:
            await interaction.response.send_message("Kein passendes Event für diesen Thread gefunden.", ephemeral=True)
            return
        
        # Prüfe, ob das Event abgesagt wurde
        if event.get('status') == "canceled" or "[ABGESAGT]" in event.get('title', ''):
            await interaction.response.send_message("Dieses Event wurde bereits abgesagt. Neue Rollenvorschläge sind nicht mehr möglich.", ephemeral=True)
            return
        
        # Prüfe, ob mehr als 1 Stunde seit Eventbeginn vergangen ist
        try:
            # Event-Zeit direkt aus datetime_obj verwenden
            event_dt = datetime.fromisoformat(event.get('datetime_obj'))
            now = datetime.now(timezone.utc)
            
            # Wenn mehr als 1 Stunde seit Eventbeginn vergangen ist, Slash-Befehl blockieren
            if now > event_dt + timedelta(hours=1):
                # Benutzer informieren (ephemeral im Thread)
                await interaction.response.send_message("Neue Rollen können nicht mehr vorgeschlagen werden, da das Event vor über einer Stunde begonnen hat.", ephemeral=True)
                logger.info(f"Blocked /propose command from {interaction.user.name} - event {event.get('title')} started more than 1 hour ago")
                return
        except Exception as e:
            logger.error(f"Error checking event time for /propose command: {e}")
            # Im Fehlerfall Command dennoch erlauben
        
        # Check if the event is in participant_only_mode
        is_participant_only = event.get('participant_only_mode', False)
        if is_participant_only:
            await interaction.response.send_message("Rollenvorschläge sind für Events im Nur-Teilnehmer-Modus nicht verfügbar.", ephemeral=True)
            return
        
        # Check if the role already exists
        if role_name in event['roles']:
            await interaction.response.send_message(f"Die Rolle '{role_name}' existiert bereits in diesem Event.", ephemeral=True)
            return
        
        # Create the confirmation components
        class RoleProposalView(discord.ui.View):
            def __init__(self, proposer_id, proposer_name, proposed_role, guild_id, thread_id):
                super().__init__(timeout=86400)  # 24 Stunden Timeout
                self.proposer_id = proposer_id
                self.proposer_name = proposer_name
                self.proposed_role = proposed_role
                self.guild_id = guild_id
                self.thread_id = thread_id
                
            @discord.ui.button(label="Annehmen", style=discord.ButtonStyle.green)
            async def accept_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                # Check if the reacting user is the event caller
                if str(button_interaction.user.id) != event.get('caller_id'):
                    await button_interaction.response.send_message("Nur der Event-Ersteller kann diesen Vorschlag annehmen.", ephemeral=True)
                    return
                
                # Load the most current version of the event to ensure we have the latest changes
                current_events_data = load_upcoming_events(include_expired=True)
                # First try to find the event by thread_id (most reliable)
                thread_id = self.thread_id
                current_event = next((e for e in current_events_data["events"] if e.get('thread_id') == thread_id), None)
                
                # Fallback: try to find by title (for backwards compatibility)
                if not current_event:
                    current_event = next((e for e in current_events_data["events"] if e.get('title') == event.get('title')), None)

                if not current_event:
                    await button_interaction.response.send_message("Das Event konnte nicht gefunden werden. Möglicherweise wurde es gelöscht.", ephemeral=True)
                    return
                
                # Find the FILLALL role in the current event state
                fill_index = next((i for i, role in enumerate(current_event['roles']) if role.lower() in ["fill", "fillall"]), None)
                
                # Ensure that fill_index has a value
                if fill_index is None:
                    # If no FILLALL role is found, add the new role to the end
                    current_event['roles'].append(self.proposed_role)
                    new_role_index = len(current_event['roles']) - 1
                else:
                    # Store the current state of participants before changes
                    old_participants = copy.deepcopy(current_event.get('participants', {}))
                    
                    # Add the new role before the FILLALL role
                    current_event['roles'].insert(fill_index, self.proposed_role)
                    new_role_index = fill_index
                    
                    # Update the FILLALL index, since we added a role before it
                    fill_index += 1
                    
                    # Update all role indices that come after the inserted role
                    if 'participants' in current_event:
                        new_participants = {}
                        for role_key, participants_list in old_participants.items():
                            try:
                                idx, role_name = role_key.split(':', 1)
                                idx = int(idx)
                                
                                # If this role comes after the inserted role, increment its index
                                if idx >= new_role_index and role_name.lower() not in ['fill', 'fillall']:
                                    new_idx = idx + 1
                                    new_key = f"{new_idx}:{role_name}"
                                    new_participants[new_key] = participants_list
                                # If this is the FILLALL/FILL role that was shifted
                                elif role_name.lower() in ['fill', 'fillall'] and idx == new_role_index:
                                    new_key = f"{fill_index}:{role_name}"
                                    new_participants[new_key] = participants_list
                                # Otherwise keep the key as is
                                else:
                                    new_participants[role_key] = participants_list
                            except ValueError:
                                # If role_key is not in expected format, keep it as is
                                new_participants[role_key] = participants_list
                        
                        # Update the participants dictionary
                        current_event['participants'] = new_participants
                
                # Create role_key for the new role
                new_role_key = f"{new_role_index}:{self.proposed_role}"
                
                # Initialize participants dict for the new role if necessary
                if 'participants' not in current_event:
                    current_event['participants'] = {}
                if new_role_key not in current_event['participants']:
                    current_event['participants'][new_role_key] = []
                
                # Automatically add the proposer to the new role with comment
                proposer_id = str(self.proposer_id)
                proposer_name = self.proposer_name
                current_time = datetime.now().timestamp()
                
                # Check if the user is already registered in another role (except FILLALL)
                for r_idx, r_name in enumerate(current_event['roles']):
                    if r_name.lower() == "fill" or r_name.lower() == "fillall":
                        continue  # Ignore Fill roles
                    
                    r_key = f"{r_idx}:{r_name}"
                    if r_key in current_event.get('participants', {}):
                        for entry_idx, entry in enumerate(current_event['participants'][r_key]):
                            if entry[1] == proposer_id:
                                # Remove the player from the old role
                                current_event['participants'][r_key].pop(entry_idx)
                                break
                
                # Add the player to the new role with comment "selbst vorgeschlagen"
                current_event['participants'][new_role_key].append((proposer_name, proposer_id, current_time, "selbst vorgeschlagen"))
                
                # Update event and save
                save_event_to_json(current_event)
                
                # Try to update the event message in the thread
                try:
                    # Find the guild and thread
                    guild = bot.get_guild(self.guild_id)
                    if guild:
                        thread = await bot.fetch_thread(guild, self.thread_id)
                        if thread:
                            await bot.update_event_message(thread, current_event)
                            
                            # Send message to thread about the accepted proposal
                            await thread.send(f"**{self.proposer_name}** hat die Rolle **{self.proposed_role}** vorgeschlagen und der Vorschlag wurde angenommen.")
                            
                            # Also refresh the event overview
                            await create_event_listing(guild)
                except Exception as e:
                    logger.error(f"Failed to update thread after role proposal: {e}")
                
                # Disable all buttons
                for child in self.children:
                    child.disabled = True
                
                # Inform the proposer
                dm_sent = False
                try:
                    guild = bot.get_guild(self.guild_id)
                    if guild:
                        proposer = await guild.fetch_member(self.proposer_id)
                        if proposer:
                            event_link = f"https://discord.com/channels/{self.guild_id}/{CHANNEL_ID_EVENT}/{current_event.get('message_id')}"
                            dm_message = (
                                f"Dein Rollenvorschlag **{self.proposed_role}** wurde angenommen!\n"
                                f"Du wurdest automatisch in diese Rolle eingetragen.\n"
                                f"Event: {current_event['title']}\n"
                                f"Datum: {current_event['date']}\n"
                                f"Uhrzeit: {current_event['time']}\n"
                                f"[Zum Event]({event_link})"
                            )
                            await proposer.send(dm_message)
                            dm_sent = True
                except Exception as e:
                    logger.error(f"Failed to send DN to proposer {self.proposer_id}: {e}")
                
                # Update the original message with disabled buttons only
                await button_interaction.response.edit_message(
                    content=f"Rollenvorschlag: **{self.proposed_role}** von **{self.proposer_name}**", 
                    view=self
                )
                
                # Send additional message to event creator with detailed info
                additional_message = f"Rolle **{self.proposed_role}** wurde zum Event hinzugefügt.\n{self.proposer_name} wurde automatisch auf die neue Rolle eingetragen.\n"
                if dm_sent:
                    additional_message += f"{self.proposer_name} wurde per DN informiert.\n"
                additional_message += f"[Zum Event]({event_link})"
                
                await button_interaction.followup.send(content=additional_message)
            
            @discord.ui.button(label="Ablehnen", style=discord.ButtonStyle.red)
            async def reject_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                # Check if the reacting user is the event caller
                if str(button_interaction.user.id) != event.get('caller_id'):
                    await button_interaction.response.send_message("Nur der Event-Ersteller kann diesen Vorschlag ablehnen.", ephemeral=True)
                    return
                
                # Disable all buttons
                for child in self.children:
                    child.disabled = True
                
                # Inform the proposer
                dm_sent = False
                try:
                    guild = bot.get_guild(self.guild_id)
                    if guild:
                        proposer = await guild.fetch_member(self.proposer_id)
                        if proposer:
                            event_link = f"https://discord.com/channels/{self.guild_id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                            dm_message = (
                                f"Dein Rollenvorschlag **{self.proposed_role}** für das Event **{event['title']}** wurde abgelehnt.\n"
                                f"Sorry, ich war das nicht, wallah! Das war **{event['caller_name']}**\n"
                                f"[Zum Event]({event_link})"
                            )
                            await proposer.send(dm_message)
                            dm_sent = True
                except Exception as e:
                    logger.error(f"Failed to send DN to proposer {self.proposer_id}: {e}")
                
                # Update the message with disabled buttons and rejection info
                info_message = f"Rollenvorschlag **{self.proposed_role}** wurde abgelehnt.\n"
                if dm_sent:
                    info_message += f" Der Vorschlagende wurde per DN informiert.\n"
                
                event_link = f"https://discord.com/channels/{self.guild_id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                info_message += f"[Zum Event]({event_link})"
                
                await button_interaction.response.edit_message(
                    content=f"Rollenvorschlag: **{self.proposed_role}** von **{self.proposer_name}**", 
                    view=self
                )
                
                # Send additional message with rejection details
                additional_message = f"Rollenvorschlag **{self.proposed_role}** wurde abgelehnt.\n"
                if dm_sent:
                    additional_message += f"{self.proposer_name} wurde per DN informiert.\n"
                additional_message += f"[Zum Event]({event_link})"
                
                await button_interaction.followup.send(content=additional_message)
        
        # Create the view with the buttons for DM
        view = RoleProposalView(interaction.user.id, interaction.user.display_name, role_name, interaction.guild.id, interaction.channel.id)
        
        # Send ephemeral confirmation to the proposer in the thread
        await interaction.response.send_message(
            f"Dein Rollenvorschlag **{role_name}** wurde an den Event-Ersteller gesendet. "
            f"Du wirst benachrichtigt, sobald eine Entscheidung getroffen wurde.",
            ephemeral=True
        )
        
        # Send DM to the event creator with buttons
        try:
            # Find the event creator
            caller_id = event.get('caller_id')
            if not caller_id:
                await interaction.channel.send("Der Event-Ersteller konnte nicht gefunden werden.")
                return
            
            caller = await interaction.guild.fetch_member(int(caller_id))
            if not caller:
                await interaction.channel.send("Der Event-Ersteller konnte nicht gefunden werden.")
                return
            
            # Send DM with buttons
            event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
            await caller.send(
                f"**{interaction.user.display_name}** schlägt eine neue Rolle für dein Event **{event['title']}** vor: **{role_name}**\n"
                f"Möchtest du **{interaction.user.display_name}** mit dieser Rolle zum Event hinzufügen?\n"
                f"[Zum Event]({event_link})",
                view=view
            )
            
        except Exception as e:
            logger.error(f"Error sending DM to event creator: {e}")
            await interaction.channel.send("Der Rollenvorschlag konnte nicht an den Event-Ersteller gesendet werden.")
        
    except Exception as e:
        logger.error(f"Error in propose_role: {e}")
        await interaction.response.send_message("Ein Fehler ist beim Vorschlagen der Rolle aufgetreten.", ephemeral=True)

async def process_batch_deletion(channel, messages, counter):
    """Löscht Nachrichten in einem Batch und behandelt mögliche Fehler."""
    if not messages:
        return
    
    try:
        await channel.delete_messages(messages)
        logger.info(f"Batch von {len(messages)} Nachrichten erfolgreich gelöscht.")
        await asyncio.sleep(2)  # Short pause between batches
    except discord.errors.HTTPException as e:
        if e.status == 429:  # Rate limit
            retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
            logger.warning(f"Rate limit erreicht. Warte {retry_after} Sekunden.")
            await asyncio.sleep(retry_after)
            # Recursive call with smaller batch size
            if len(messages) > 10:
                mid = len(messages) // 2
                await process_batch_deletion(channel, messages[:mid], counter)
                await asyncio.sleep(1)
                await process_batch_deletion(channel, messages[mid:], counter)
            else:
                # For very small batches: Individual deletions
                await process_individual_deletions(messages, counter)
        else:
            logger.error(f"Fehler beim Batch-Löschen: {e}")
            # For other errors: Try individual deletions
            await process_individual_deletions(messages, counter)

async def process_individual_deletions(messages, counter):
    """Löscht Nachrichten einzeln mit angemessenen Pausen."""
    if not messages:
        return
    
    for message in messages:
        try:
            await message.delete()
            content_preview = message.content[:30] + "..." if message.content and len(message.content) > 30 else message.content
            logger.info(f"Einzelnachricht gelöscht: {content_preview or 'Embed'}")
            await asyncio.sleep(1.2)  # Reasonable pause between individual deletions
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limit
                retry_after = e.retry_after if hasattr(e, 'retry_after') else 5
                logger.warning(f"Rate limit beim einzelnen Löschen erreicht. Warte {retry_after} Sekunden.")
                await asyncio.sleep(retry_after)
                try:
                    await message.delete()  # Try again
                except Exception as inner_e:
                    logger.error(f"Nachricht konnte auch nach dem Warten nicht gelöscht werden: {inner_e}")
            elif e.status == 404:  # Message already deleted
                logger.info("Nachricht bereits gelöscht.")
            else:
                logger.error(f"Fehler beim Löschen einer einzelnen Nachricht: {e}")
        except Exception as e:
            logger.error(f"Unerwarteter Fehler beim Löschen einer einzelnen Nachricht: {e}")
        finally:
            # Additional small pause after each deletion attempt
            await asyncio.sleep(0.3)

def save_overview_id(message_id):
    """Speichert die ID der aktuellen Event-Übersicht"""
    filepath = "overview.json"
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"message_id": message_id}, f)
        
        logger.info(f"Event-Übersichts-ID gespeichert: {message_id}")
        return True
    except Exception as e:
        logger.error(f"Fehler beim Speichern der Übersichts-ID: {e}")
        return False

def load_overview_id():
    """Lädt die ID der aktuellen Event-Übersicht"""
    filepath = "overview.json"
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("message_id")
        return None
    except Exception as e:
        logger.error(f"Fehler beim Laden der Übersichts-ID: {e}")
        return None

def save_thread_failure_info(event_title, message_id, error_info):
    """Log information about a failed thread creation attempt for diagnostic purposes"""
    try:
        error_type = error_info.get("error_type", "Unknown")
        error_message = error_info.get("error_message", "No message")
        
        # Log directly in a readable format
        logger.error(f"THREAD_FAILURE: Event: '{event_title}', Message ID: {message_id}, Error: {error_type} - {error_message}")
        return True
    except Exception as e:
        logger.error(f"Error logging thread failure information: {e}")
        return False

def get_thread_failure_stats():
    """Get statistics about thread creation failures from logs"""
    try:
        return {
            "message": "Thread failure statistics are now logged directly. Please check the log files."
        }
    except Exception as e:
        logger.error(f"Error getting thread failure statistics: {e}")
        return {"error": str(e)}

@bot.tree.command(name="refresh", description="Aktualisiert die Eventübersicht manuell")
async def refresh_overview(interaction: discord.Interaction):
    """Aktualisiert die Eventübersicht manuell"""
    try:
        # Defer die Antwort, da die Operation länger dauern könnte
        await interaction.response.defer(ephemeral=True)
        
        # Nur für autorisierte Server erlauben
        if AUTHORIZED_GUILD_ID != 0 and interaction.guild.id != AUTHORIZED_GUILD_ID:
            await interaction.followup.send("Dieser Befehl ist auf diesem Server nicht verfügbar.", ephemeral=True)
            return
            
        # Erstelle neue Übersicht
        await create_event_listing(interaction.guild)
        
        # Bestätigungsnachricht senden um die "denkt nach" Nachricht zu beenden
        await interaction.followup.send("✅ Eventübersicht wurde aktualisiert.", ephemeral=True)
            
    except Exception as e:
        error_msg = f"Fehler beim Aktualisieren der Eventübersicht: {str(e)}"
        logger.error(error_msg)
        logger.error("Stack trace:", exc_info=True)
        
        try:
            await interaction.followup.send(error_msg, ephemeral=True)
        except:
            logger.error("Konnte Fehlermeldung nicht senden")

bot.run(DISCORD_TOKEN)
            
            