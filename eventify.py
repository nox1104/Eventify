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
from logging.handlers import RotatingFileHandler
import glob

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

    # Rotating file handler (limits file size and keeps old logs)
    log_filename = f'logs/eventify_{datetime.now().strftime("%Y%m%d")}.log'
    file_handler = RotatingFileHandler(
        log_filename,
        maxBytes=5*1024*1024,  # 5 MB per file
        backupCount=42,         # Keep 42 old log files
        encoding='utf-8'
    )
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
        
        # Start the loops
        self.delete_old_event_threads.start()
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

            # Process role signup (single digit number)
            if message.content.strip().isdigit():
                await self._handle_role_signup(message, event, int(message.content))
                
            # Process role signup with comment (number followed by text)
            elif message.content.strip() and message.content.strip()[0].isdigit():
                # Extract the number part
                parts = message.content.strip().split(' ', 1)
                if parts[0].isdigit():
                    await self._handle_role_signup(message, event, int(parts[0]))
                
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
                        if comment:
                            existing_data = event['participants'][role_key][existing_entry]
                            # Update with comment (name, id, timestamp, comment)
                            if len(existing_data) >= 4:
                                event['participants'][role_key][existing_entry] = (existing_data[0], existing_data[1], existing_data[2], comment)
                            else:
                                event['participants'][role_key][existing_entry] = (existing_data[0], existing_data[1], existing_data[2], comment)
                            await self._update_event_and_save(message, event, events_data)
                            await message.add_reaction('✅')  # Add confirmation reaction
                        else:
                            # Just acknowledge if no comment to update
                            logger.info(f"{player_name} already assigned to role {role_name} at index {role_index}")
                            await message.add_reaction('ℹ️')  # Info reaction
                            # Send a joke message without auto-deletion
                            await message.channel.send(f"{message.author.mention} Für die Rolle '{role_name}' bist du doch schon angemeldet, du Pappnase!")
                    else:
                        # For Fill role, no limit on players and can be added even if already registered for another role
                        if is_fill_role:
                            # Check if the role is specifically FillALL (not for participant_only_mode)
                            if not is_participant_only:
                                is_fillall_role = event['roles'][role_index].lower() == "fillall"
                            else:
                                is_fillall_role = False  # In participant_only_mode we allow comments
                            
                            # For FillALL, we ignore comments and allow multiple roles
                            if is_fillall_role:
                                # Add new entry with timestamp (ignore comment for FillALL)
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
                await message.channel.send("Kein passendes Event für diesen Thread gefunden.")
        except Exception as e:
            logger.error(f"Error processing role assignment: {e}")
            await message.channel.send(f"Fehler bei der Verarbeitung deiner Anfrage: {str(e)}")

    async def _handle_unregister(self, message, is_specific_role=False, role_number=None, role_index=None):
        try:
            # Load events from JSON (auch abgelaufene Events einschließen, damit Abmeldungen nach Eventstart möglich sind)
            events_data = load_upcoming_events(include_expired=True)
            
            # First try to find the event by thread_id (most reliable)
            thread_id = message.channel.id
            event = next((e for e in events_data["events"] if e.get('thread_id') == thread_id), None)
            
            # Fallback: try to find by title (for backwards compatibility)
            if not event:
                event = next((e for e in events_data["events"] if e.get('title') == message.channel.name), None)

            if event:
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
            else:
                logger.warning(f"No event found matching thread name: {message.channel.name}")
                await message.channel.send("Kein passendes Event für diesen Thread gefunden.")
        except Exception as e:
            logger.error(f"Error processing unregister: {e}")
            await message.channel.send(f"Fehler bei der Verarbeitung deiner Anfrage: {str(e)}")

    async def _update_event_and_save(self, message, event, events):
        try:
            # Ensure events is a dictionary with an "events" key
            if isinstance(events, list):
                events = {"events": events}
            elif not isinstance(events, dict) or "events" not in events:
                logger.error("Invalid events format in _update_event_and_save")
                return False

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
                                    # Truncate comment to 20 characters if necessary
                                    comment = p[3]
                                    if len(comment) > 20:
                                        comment = comment[:20] + "..."
                                    participants_text += f"<@{p[1]}> - {comment}\n"
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

                # Go through all roles and section headers in the original order
                all_items = section_headers + regular_roles
                all_items.sort(key=lambda x: x[0])  # Sort by original index

                for role_idx, role_name in all_items:
                    # Check if it's a section header
                    if role_name.strip().startswith('(') and role_name.strip().endswith(')'):
                        # Remove parentheses from section header
                        header_text = role_name.strip()[1:-1]  # Remove first and last character
                        field_content += f"*{header_text}*\n"
                    else:
                        # This is a normal role
                        # Display role and participants
                        role_key = f"{role_idx}:{role_name}"
                        role_participants = participants.get(role_key, [])
                        
                        if role_participants:
                            # Sort participants by timestamp and show only the first
                            sorted_participants = sorted(role_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                            p_data = sorted_participants[0]
                            
                            if len(p_data) >= 2:  # Ensure we have at least name and ID
                                p_id = p_data[1]
                                
                                # Role and player in one line
                                field_content += f"{role_counter}. {role_name} <@{p_id}>"
                                
                                # Comment if available
                                if len(p_data) >= 4 and p_data[3]:
                                    # Truncate comment to 20 characters if necessary
                                    comment = p_data[3]
                                    if len(comment) > 20:
                                        comment = comment[:20] + "..."
                                    field_content += f" {comment}"
                                    logger.info(f"Including comment for role {role_name}: '{p_data[3]}'")
                                
                                field_content += "\n"
                            else:
                                field_content += f"{role_counter}. {role_name}\n"
                        else:
                            field_content += f"{role_counter}. {role_name}\n"
                        
                        # Increment the role counter for actual roles
                        role_counter += 1

                # Add all regular roles as a single field
                if field_content:
                    embed.add_field(name="Rollen", value=field_content, inline=False)

                # Add Fill role section
                if fill_index is not None:
                    fill_text = f"{role_counter}. {roles[fill_index]}"
                    
                    # Get participants for Fill role
                    fill_key = f"{fill_index}:{roles[fill_index]}"
                    fill_participants = participants.get(fill_key, [])
                    
                    if fill_participants:
                        # Sort participants by timestamp
                        sorted_fill = sorted(fill_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                        
                        # Display all participants for FillALL without extra newline
                        fill_players_text = fill_text + "\n" + "\n".join([f"<@{p[1]}>" for p in sorted_fill if len(p) >= 2])
                        
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
        Wandelt die fortlaufende Rollennummer (1, 2, 3...) in den tatsächlichen Index in der Rollenliste um.
        
        Args:
            event: Das Event-Objekt
            role_number: Die angezeigte Rollennummer (1-basiert)
        
        Returns:
            Der tatsächliche Index der Rolle im event['roles'] Array
        """
        # Get roles from event
        roles = event.get('roles', []) if isinstance(event, dict) else getattr(event, 'roles', [])
        
        # Check if we are in participant_only_mode
        is_participant_only = event.get('participant_only_mode', False) if isinstance(event, dict) else getattr(event, 'participant_only_mode', False)
        
        # In participant_only_mode it's simple: there is only one role (Participant) at position 0
        if is_participant_only:
            if role_number == 1:  # Since there is only one role, the number must be 1
                return 0
            else:
                return -1  # Ungültige Rollennummer
        
        # In normal mode proceed as before
        # Find the Fill role index
        fill_index = next((i for i, role in enumerate(roles) if role.lower() in ["fill", "fillall"]), None)
        
        # Get all regular roles (excluding FillALL and section headers)
        regular_roles = []
        for i, role in enumerate(roles):
            if i != fill_index:  # Alles außer die FillALL-Rolle
                # Ignoriere Abschnittsüberschriften (Texte in Klammern)
                if not (role.strip().startswith('(') and role.strip().endswith(')')):
                    regular_roles.append((i, role))
        
        # Check if role_number is within range of regular roles
        if 1 <= role_number <= len(regular_roles):
            # Return the actual index of the role in the original roles array
            return regular_roles[role_number-1][0]
        elif role_number == len(regular_roles) + 1 and fill_index is not None:
            # If the role_number is for the FillALL role
            return fill_index
        else:
            # Invalid role number
            return -1

    @tasks.loop(minutes=5)
    async def delete_old_event_threads(self):
        """Löscht Threads für abgelaufene Events nach 30-Minuten-Wartezeit"""
        try:
            now = datetime.now()
            logger.info(f"{now} - Checking for old event threads...")
            
            # Lade Events mit Status "expired" (abgelaufen, aber Thread noch aktiv)
            events_data = load_upcoming_events(include_expired=True, include_cleaned=False)
            
            # Filtere nur nach Events mit Status "expired"
            expired_events = [e for e in events_data.get("events", []) if e.get("status") == "expired"]
            logger.info(f"Found {len(expired_events)} expired events to check for thread deletion")
            
            events_cleaned = 0
            
            for event in expired_events:
                try:
                    event_title = event.get('title', 'Unknown Event')
                    event_id = event.get('event_id')
                    
                    if not event_id:
                        logger.warning(f"No event_id found for event '{event_title}'")
                        continue
                    
                    try:
                        # Extrahiere Datum und Zeit aus dem Event
                        if "datetime_obj" in event and event["datetime_obj"]:
                            try:
                                event_dt = datetime.fromisoformat(event["datetime_obj"])
                            except (ValueError, TypeError):
                                # Fallback auf Datum und Zeit aus den Feldern
                                day, month, year = map(int, event["date"].split("."))
                                hour, minute = map(int, event["time"].split(":"))
                                event_dt = datetime(year, month, day, hour, minute)
                        else:
                            # Datum und Zeit aus den Feldern
                            day, month, year = map(int, event["date"].split("."))
                            hour, minute = map(int, event["time"].split(":"))
                            event_dt = datetime(year, month, day, hour, minute)
                        
                        # Prüfe, ob 30 Minuten seit Eventbeginn vergangen sind
                        if now < event_dt + timedelta(minutes=30):
                            logger.info(f"Event '{event_title}' still within 30-minute grace period, skipping")
                            continue
                        
                        logger.info(f"Event '{event_title}' expired and 30-minute grace period passed, cleaning thread")
                        
                        # Hole die Thread-ID
                        thread_id = event.get('thread_id')
                        if not thread_id:
                            logger.warning(f"No thread_id found for expired event '{event_title}'")
                            continue
                        
                        # Lösche den Thread
                        for guild in self.guilds:
                            thread = await self.fetch_thread(guild, thread_id)
                            if thread:
                                try:
                                    await thread.delete()
                                    logger.info(f"Successfully deleted thread for expired event '{event_title}'")
                                    
                                    # Markiere Event als "cleaned"
                                    event["status"] = "cleaned"
                                    events_cleaned += 1
                                    break
                                except Exception as e:
                                    logger.error(f"Error deleting thread for event '{event_title}': {e}")
                    
                    except (ValueError, KeyError) as e:
                        logger.error(f"Error parsing date/time for event '{event_title}': {e}")
                
                except Exception as e:
                    logger.error(f"Error processing event: {e}")
            
            # Wenn Events als "cleaned" markiert wurden, speichere die Änderungen
            if events_cleaned > 0:
                logger.info(f"Marked {events_cleaned} events as cleaned")
                save_events_to_json(events_data)
                
        except Exception as e:
            logger.error(f"Error in delete_old_event_threads: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # Wait until the bot is ready before starting the loop
    @delete_old_event_threads.before_loop
    async def before_delete_old_event_threads(self):
        await self.wait_until_ready()

    @tasks.loop(hours=6)  
    async def cleanup_event_channel(self):
        """
        Cleans up the event channel based on status and age:
        - Keeps active events
        - Removes expired events after 12 days
        - Removes regular messages after 12 days
        """
        logger.info(f"{datetime.now()} - Starting event channel cleanup...")
        
        # Backup erstellen bevor Änderungen vorgenommen werden
        self.create_backup()
        
        DAYS_TO_KEEP = 12
        
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
                events_to_remove = []
                
                # IDs der AKTIVEN Event-Nachrichten sammeln
                active_event_message_ids = set()
                for event in events_data["events"]:
                    if event.get("status") == "active" and event.get("message_id"):
                        active_event_message_ids.add(int(event["message_id"]))
                
                # Events nach Status/Alter sortieren
                current_time = datetime.now()
                for event in events_data["events"]:
                    if event.get("status") == "active":
                        events_to_keep.append(event)
                    else:
                        try:
                            event_time = datetime.fromisoformat(event["datetime_obj"])
                            days_difference = (current_time - event_time).days
                            
                            if days_difference > DAYS_TO_KEEP:
                                events_to_remove.append(event)
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
                    deleted_msgs = await channel.purge(check=should_delete_message, limit=100)
                    logger.info(f"Guild {guild.id}: {len(deleted_msgs)} alte Nachrichten gelöscht")
                except Exception as e:
                    logger.error(f"Fehler beim Purge: {e}")
                
                # Events-Datei aktualisieren
                events_data["events"] = events_to_keep
                save_events_to_json(events_data)
                
                logger.info(f"Event-Bereinigung abgeschlossen: {len(events_to_remove)} Events entfernt, {len(events_to_keep)} Events behalten")
                
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
        
        # Konvertiere datetime_obj zu einem tatsächlichen datetime-Objekt, falls es ein String ist
        if datetime_obj is None:
            try:
                # Versuche, aus Datum und Uhrzeit ein datetime-Objekt zu erstellen
                dt_str = f"{date} {time}"
                self.datetime_obj = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
            except:
                # Fallback auf aktuelle Zeit
                self.datetime_obj = datetime.now()
                logger.warning(f"Konnte kein datetime-Objekt aus Datum '{date}' und Zeit '{time}' erstellen. Verwende aktuelle Zeit.")
        elif isinstance(datetime_obj, str):
            try:
                # Versuche, den String in ein datetime-Objekt zu konvertieren
                self.datetime_obj = datetime.strptime(datetime_obj, "%d.%m.%Y %H:%M")
            except:
                # Fallback auf aktuelle Zeit
                self.datetime_obj = datetime.now()
                logger.warning(f"Konnte kein datetime-Objekt aus String '{datetime_obj}' erstellen. Verwende aktuelle Zeit.")
        else:
            # Bereits ein datetime-Objekt
            self.datetime_obj = datetime_obj
        
        # Use provided event_id or generate a new one
        if event_id:
            self.event_id = event_id
            logger.info(f"Using provided event_id: {event_id} for event: {title}")
        else:
            # Generate a unique ID for the event that includes the timestamp
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
            # Konvertiere zu datetime
            return datetime.strptime(timestamp_str, "%Y%m%d%H%M")
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
            "image_url": self.image_url  # Store the image URL
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
            
            # Parse date and time to create a datetime object
            try:
                date_parts = self.date.split('.')
                time_parts = self.time.split(':')
                
                if len(date_parts) == 3 and len(time_parts) == 2:
                    day, month, year = map(int, date_parts)
                    hour, minute = map(int, time_parts)
                    event_datetime = datetime(year, month, day, hour, minute)
                else:
                    # Fallback to current time if parsing fails
                    event_datetime = datetime.now()
                    logger.warning(f"Konnte kein datetime-Objekt aus Datum '{self.date}' und Zeit '{self.time}' erstellen. Verwende aktuelle Zeit.")
            except Exception as e:
                event_datetime = datetime.now()
                logger.warning(f"Fehler beim Erstellen des datetime-Objekts: {e}. Verwende aktuelle Zeit.")
            
            # Check if we're in participant-only mode
            roles_input = self.roles.value.strip() if self.roles.value else ""
            is_participant_only_mode = not roles_input
            
            # Set roles based on mode
            if is_participant_only_mode:
                # Bei leerer Eingabe nur eine "Teilnehmer"-Rolle erstellen
                roles = ["Teilnehmer"]
            else:
                # Normaler Modus mit Rollen aus der Eingabe
                roles = roles_input.split('\n')
            
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
                date=self.date,
                time=self.time,
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
                        field_content += f"*{header_text}*\n"
                    else:
                        # This is a normal role
                        field_content += f"{role_counter}. {role_name}\n"
                        role_counter += 1
                
                # Add all regular roles as a single field
                if field_content:
                    embed.add_field(name="Rollen", value=field_content, inline=False)
                
                if fill_index is not None:
                    fill_text = f"{role_counter}. {event.roles[fill_index]}"
                    embed.add_field(name="\u200b", value=fill_text, inline=False)
            else:
                # Im Teilnehmer-only Modus, zeige die Teilnehmer-Rolle an
                embed.add_field(name="Rollen", value="1. Teilnehmer", inline=False)
            
            # Send event post and create thread
            channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
            event_post = await channel.send(embed=embed)
            thread = await event_post.create_thread(name=event.title)
            
            # Save both message ID and thread ID
            event.message_id = event_post.id
            event.thread_id = thread.id
            
            # Save event to JSON
            save_event_to_json(event)
            
            # Send welcome information to the thread
            welcome_embed = discord.Embed(
                description="Bei Fragen hilft dir das [Benutzerhandbuch](https://github.com/nox1104/Eventify/blob/main/Benutzerhandbuch.md).",
                color=0x0dceda  # Eventify Cyan
            )

            await thread.send(embed=welcome_embed)
            
            # Send a separate mention message if a mention role is specified
            if event.mention_role_id:
                # Send mention but delete it right after (will still notify users)
                await thread.send(f"<@&{event.mention_role_id}> - {event.title}, {event.date}, {event.time}", delete_after=0.1)
            
            # Aktualisiere die Eventübersicht
            await create_event_listing(interaction.guild)
            
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

async def create_event_listing(guild):
    """Erstellt ein Event Listing mit allen anstehenden Events"""
    try:
        # Lade nur aktive Events (keine abgelaufenen oder bereinigten)
        events_data = load_upcoming_events(include_expired=False, include_cleaned=False)
        
        if not events_data or not events_data.get("events"):
            logger.info("No upcoming events to list.")
            return
        
        # Get the guild ID for links
        guild_id = guild.id
        event_channel = guild.get_channel(CHANNEL_ID_EVENT)
        
        if not event_channel:
            logger.error(f"Event channel not found in guild {guild.name}")
            return
        
        # Filter events where no corresponding event post exists
        valid_events = []
        for event in events_data["events"]:
            if not isinstance(event, dict):
                logger.warning(f"Invalid event format: {event}")
                continue
                
            message_id = event.get("message_id")
            
            # Skip events without message_id
            if not message_id:
                logger.warning(f"Event {event.get('title')} has no message_id and will be skipped.")
                continue
                
            # Check if the event post still exists
            try:
                await event_channel.fetch_message(int(message_id))
                # If no error, add the event to the valid list
                valid_events.append(event)
            except (discord.NotFound, discord.HTTPException, ValueError) as e:
                logger.warning(f"Event-Post für '{event.get('title')}' (ID: {message_id}) existiert nicht mehr: {e}")
                continue
        
        # Update the events.json to remove orphaned events
        if len(valid_events) < len(events_data["events"]):
            logger.info(f"Remove {len(events_data['events']) - len(valid_events)} orphaned events from the JSON.")
            save_events_to_json({"events": valid_events})
        
        if not valid_events:
            logger.info("No valid events with existing posts found.")
            return
        
        # Sort events by date and time
        try:
            # Sort by datetime_obj, if available
            events_with_datetime = []
            for event in valid_events:
                # Try to convert date and time to a datetime object
                if 'datetime_obj' in event and event['datetime_obj']:
                    try:
                        dt_obj = datetime.fromisoformat(event['datetime_obj'])
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
                        dt_obj = datetime(year, month, day, hour, minute)
                    except (ValueError, KeyError) as e:
                        logger.error(f"Error parsing date/time for event {event.get('title', 'unknown')}: {e}")
                        # Add the event with the current timestamp so it is displayed
                        dt_obj = datetime.now()
                    
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
            color=0x0dceda  # Eventify Cyan
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
                message_id = event.get('message_id')
                
                # Create event line
                event_line = ""
                if caller_id:
                    if message_id and message_id != "None" and message_id != None:
                        event_line = f"{time}  [#{title}](https://discord.com/channels/{guild_id}/{CHANNEL_ID_EVENT}/{message_id}) mit <@{caller_id}>\n"
                    else:
                        event_line = f"{time}  {title} mit <@{caller_id}>\n"
                else:
                    if message_id and message_id != "None" and message_id != None:
                        event_line = f"{time}  [#{title}](https://discord.com/channels/{guild_id}/{CHANNEL_ID_EVENT}/{message_id})\n"
                    else:
                        event_line = f"{time}  {title}\n"
                
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
                        color=0x0dceda  # Eventify Cyan
                    )
                    field_count = 0
                
                # Zeige Datumsnamen nur beim ersten Feld, 
                # für Fortsetzungen verwende einen leeren String mit Unicode Zero Width Space
                # um das Feld in Discord korrekt darzustellen
                field_name = f"{date}" if i == 0 else "Oha, an diesem Tag ist viel geplant..."
                
                current_embed.add_field(
                    name=field_name,
                    value=description,
                    inline=False
                )
                field_count += 1
        
        # Don't forget to add the last embed
        if field_count > 0:
            embeds.append(current_embed)
        
        # Send the embeds to the event channel
        channel = guild.get_channel(CHANNEL_ID_EVENT)
        for embed in embeds:
            await channel.send(embed=embed)
        
        logger.info(f"Event listing created successfully with {len(embeds)} embeds.")
    except Exception as e:
        logger.error(f"Error creating event listing: {e}")
        logger.exception("Full traceback:")

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
        
        # Clean old events (past events)
        events_data = clean_old_events(events_data)
        logger.info(f"After cleaning old events, {len(events_data.get('events', []))} events remain")
        
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
            if hasattr(event, 'to_dict'):
                events_data["events"].append(event.to_dict())
            else:
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
    """Markiert Events als abgelaufen (expired), wenn sie begonnen haben."""
    if not isinstance(events_data, dict) or "events" not in events_data:
        logger.error("Invalid events_data format in clean_old_events")
        return {"events": []}
        
    now = datetime.now()
    expired_count = 0
    cleaned_count = 0
    
    # Neue Liste für Events, die nicht als "cleaned" markiert sind
    updated_events = []
    
    for event in events_data["events"]:
        if not isinstance(event, dict):
            logger.warning(f"Invalid event format: {event}")
            continue
            
        # Entferne Events, die bereits als "cleaned" markiert sind
        if event.get("status") == "cleaned":
            cleaned_count += 1
            logger.debug(f"Removing cleaned event: {event.get('title', 'Unknown Event')}")
            continue
            
        event_title = event.get("title", "Unknown Event")
        
        try:
            # Try to use datetime_obj first if available
            if "datetime_obj" in event:
                try:
                    event_dt = datetime.fromisoformat(event["datetime_obj"])
                except (ValueError, TypeError):
                    event_dt = None
            else:
                event_dt = None
            
            # If datetime_obj is not available or invalid, parse date and time
            if event_dt is None:
                # Parse date (format: DD.MM.YYYY)
                if "." in event["date"]:
                    day, month, year = map(int, event["date"].split("."))
                else:
                    # Try to parse without dots (DDMMYYYY)
                    date_str = event["date"]
                    day = int(date_str[:2])
                    month = int(date_str[2:4])
                    year = int(date_str[4:])
                
                # Parse time (format: HH:MM)
                if ":" in event["time"]:
                    hour, minute = map(int, event["time"].split(":"))
                else:
                    # Try to parse without colon (HHMM)
                    time_str = event["time"]
                    hour = int(time_str[:2])
                    minute = int(time_str[2:])
                
                # Create datetime object
                event_dt = datetime(year, month, day, hour, minute)
            
            # Wenn das Event begonnen hat und noch "active" ist, setze auf "expired"
            if event_dt < now and event.get("status") == "active":
                event["status"] = "expired"
                expired_count += 1
                logger.info(f"Marking event as expired: {event_title} (Date: {event.get('date', 'N/A')}, Time: {event.get('time', 'N/A')})")
                
        except (ValueError, TypeError, KeyError, IndexError) as e:
            logger.warning(f"Failed to parse date/time for event {event_title}: {e}")
        
        # Füge das Event zur aktualisierten Liste hinzu (unabhängig vom Status, solange nicht "cleaned")
        updated_events.append(event)
    
    if expired_count > 0:
        logger.info(f"Marked {expired_count} events as expired")
    
    if cleaned_count > 0:
        logger.info(f"Removed {cleaned_count} cleaned events")
    
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
                filtered_events = {"events": [e for e in events["events"] 
                                           if e.get("status", "active") == "active"]}
                logger.info(f"Loaded {len(filtered_events['events'])} active events from events.json")
                return filtered_events
            elif not include_cleaned:
                # Aktive und abgelaufene Events (für Thread-Management)
                filtered_events = {"events": [e for e in events["events"] 
                                           if e.get("status", "active") != "cleaned"]}
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
    date="Das Datum des Events (TT.MM.JJJJ)",
    time="Die Uhrzeit des Events (HH:mm)",
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
    description: str = None,
    roles: str = None,
    mention_role: discord.Role = None,
    image_url: str = None
):
    try:
        # Parse date and time
        parsed_date = parse_date(date)
        parsed_time = parse_time(time)

        if not parsed_date or not parsed_time:
            await interaction.response.send_message("Ungültiges Datum oder ungültige Zeit. Bitte verwende die Formate DD.MM.YYYY und HH:MM.", ephemeral=True)
            return

        # Combine date and time into a datetime object
        full_datetime = datetime.combine(parsed_date, parsed_time)
        
        # Check if the date is in the future
        if full_datetime < datetime.now():
            await interaction.response.send_message("Das Datum muss in der Zukunft liegen.", ephemeral=True)
            return

        # Format date and time for display
        formatted_date = parsed_date.strftime("%d.%m.%Y")
        formatted_time = parsed_time.strftime("%H:%M")

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
            await interaction.response.defer(ephemeral=True)
            
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
                    field_content += f"*{header_text}*\n"
                else:
                    # This is a normal role
                    field_content += f"{role_counter}. {role_name}\n"
                    role_counter += 1

            # Add all regular roles as a single field
            if field_content:
                embed.add_field(name="Rollen", value=field_content, inline=False)
            
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
                    fill_players_text = fill_text + "\n" + "\n".join([f"<@{p[1]}>" for p in sorted_fill if len(p) >= 2])
                    
                    # Add Fill role to embed with empty name to reduce spacing
                    embed.add_field(name="", value=fill_players_text or fill_text, inline=False)
                else:
                    # Display empty Fill role with empty name to reduce spacing
                    embed.add_field(name="", value=fill_text, inline=False)
            
            # Send the event post and create a thread
            event_post = await channel.send(embed=embed)
            thread = await event_post.create_thread(name=event.title)
            
            # Save both the message ID and thread ID
            event.message_id = event_post.id
            event.thread_id = thread.id
            save_event_to_json(event)
            
            # Debug-Log hinzufügen
            logger.info(f"Event created: {event.title}, thread_id: {thread.id}, message_id: {event_post.id}")
            
            welcome_embed = discord.Embed(
                description="Bei Fragen hilft dir das [Benutzerhandbuch](https://github.com/nox1104/Eventify/blob/main/Benutzerhandbuch.md).",
                color=0x0dceda  # Eventify Cyan
            )

            await thread.send(embed=welcome_embed)
            
            # Send a separate mention message if a mention role is specified
            if event.mention_role_id:
                # Send mention but delete it right after (will still notify users)
                await thread.send(f"<@&{event.mention_role_id}> - {event.title}, {event.date}, {event.time}", delete_after=0.1)
            
            # Create the event listing after creating the event
            await create_event_listing(interaction.guild)
            
            # Removing the confirmation message
            # await interaction.followup.send("Event wurde erfolgreich erstellt!", ephemeral=True)
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

@bot.tree.command(name="remind", description="Sende eine Erinnerung an alle eingetragenen Teilnehmer (nur für Event-Ersteller)")
@app_commands.guild_only()
async def remind_participants(interaction: discord.Interaction, message: str = None):
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

        # Check if the user is the event caller
        if str(interaction.user.id) != event.get('caller_id'):
            await interaction.response.send_message("Nur der Event-Ersteller kann Erinnerungen versenden.", ephemeral=True)
            return

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
                        f"**Erinnerung an Event: {event['title']}**\n"
                        f"Datum: {event['date']}\n"
                        f"Uhrzeit: {event['time']}\n"
                    )
                    
                    # Add the custom message if it exists
                    if message:
                        reminder_message += f"\n{message}\n"
                    
                    if event_link:
                        reminder_message += f"\n[Zum Event]({event_link})"
                    
                    await user.send(reminder_message)
                    success_count += 1
            except Exception as e:
                logger.error(f"Failed to send reminder to user {participant_id}: {e}")
                failed_count += 1
        
        # Send confirmation
        await interaction.response.send_message(
            f"Erinnerung an {success_count} Teilnehmer gesendet. {failed_count} fehlgeschlagen.", 
            ephemeral=True
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
        event["title"] = f"{event['title']} [ABGESAGT]"
        
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
        for role_key, role_participants in event.get("participants", {}).items():
            for participant in role_participants:
                if participant not in participants and len(participant) >= 2:
                    participants.append(participant)
        
        # Erstelle die Absage-Nachricht
        cancel_message = f"**Event abgesagt:** {event['title']}\n**Datum:** {event['date']} {event['time']}"
        if reason:
            cancel_message += f"\n**Grund:** {reason}"
        if event_link:
            cancel_message += f"\n[Zum Event-Post]({event_link})"
        
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

        # Event aus der Liste entfernen und speichern
        event_id = event.get("event_id")
        for i, e in enumerate(events_data["events"]):
            if e.get("event_id") == event_id:
                del events_data["events"][i]
                break
        save_events_to_json(events_data)
        
        # Neue Eventübersicht erstellen
        await create_event_listing(interaction.guild)
        
        # Bestätigung senden und Thread sofort löschen
        await interaction.followup.send(f"Event wurde abgesagt. {sent_count} Benutzer wurden benachrichtigt. Der Thread wird jetzt gelöscht.")
        
        try:
            await thread.delete()
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Event-Threads: {e}")
            await interaction.followup.send("Der Thread konnte nicht gelöscht werden, versuche es später nochmal.", ephemeral=True)
    except Exception as e:
        logger.error(f"Fehler bei der Event-Absage: {e}")
        await interaction.followup.send(f"Ein Fehler ist aufgetreten: {str(e)}")

@bot.tree.command(name="add", description="Füge einen Teilnehmer zu einer Rolle hinzu (nur für Event-Ersteller)")
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

        # Check if the user is the event caller
        if str(interaction.user.id) != event.get('caller_id'):
            await interaction.response.send_message("Nur der Event-Ersteller kann Teilnehmer hinzufügen.", ephemeral=True)
            return
        
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
                existing_data = event['participants'][role_key][existing_entry]
                if len(existing_data) >= 4:
                    event['participants'][role_key][existing_entry] = (existing_data[0], existing_data[1], existing_data[2], comment)
                else:
                    event['participants'][role_key][existing_entry] = (existing_data[0], existing_data[1], existing_data[2], comment)
                
                await interaction.response.send_message(f"Kommentar für {player_name} in Rolle {role_name} aktualisiert.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{player_name} ist bereits für Rolle {role_name} eingetragen.", ephemeral=True)
            
            # Inform the participant about the comment update
            try:
                event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                dm_message = (
                    f"**Update zu Event: {event['title']}**\n"
                    f"Der Eventersteller hat deinen Kommentar für die Rolle {role_name} aktualisiert.\n"
                    f"Datum: {event['date']}\n"
                    f"Uhrzeit: {event['time']}\n"
                    f"Neuer Kommentar: {comment}\n"
                    f"\n[Zum Event]({event_link})"
                )
                await user.send(dm_message)
            except Exception as e:
                logger.error(f"Failed to send DM to user {user.id}: {e}")
                
        else:
            # Check if the participant is already registered for another role
            is_fill_role = role_name.lower() == "fill" or role_name.lower() == "fillall"
            
            if not is_fill_role:
                # For normal roles: Check if the player is already registered in another role
                for r_idx, r_name in enumerate(event['roles']):
                    if r_name.lower() == "fill" or r_name.lower() == "fillall":
                        continue  # Ignore Fill roles
                        
                    r_key = f"{r_idx}:{r_name}"
                    if r_key in event.get('participants', {}):
                        for entry_idx, entry in enumerate(event['participants'][r_key]):
                            if entry[1] == player_id:
                                # Remove player from old role
                                event['participants'][r_key].pop(entry_idx)
                                break
            
            # Add the player to the new role
            if comment:
                event['participants'][role_key].append((player_name, player_id, current_time, comment))
            else:
                event['participants'][role_key].append((player_name, player_id, current_time))
                
            await interaction.response.send_message(f"{player_name} wurde zu Rolle \"{role_name}\" hinzugefügt und hat eine DN erhalten.")
            
            # Inform the participant about the role assignment
            try:
                event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                dm_message = (
                    f"**Du wurdest einem Event hinzugefügt: {event['title']}**\n"
                    f"Rolle: {role_name}\n"
                    f"Datum: {event['date']}\n"
                    f"Uhrzeit: {event['time']}\n"
                )
                if comment:
                    dm_message += f"Kommentar: {comment}\n"
                dm_message += f"\n[Zum Event]({event_link})"
                
                await user.send(dm_message)
            except Exception as e:
                logger.error(f"Failed to send DM to user {user.id}: {e}")
        
        # Update the event
        save_event_to_json(event)
        await bot.update_event_message(interaction.channel, event)
        
    except Exception as e:
        logger.error(f"Error in add_participant: {e}")
        await interaction.response.send_message("Ein Fehler ist beim Hinzufügen des Teilnehmers aufgetreten.", ephemeral=True)

@bot.tree.command(name="remove", description="Entferne einen Teilnehmer aus einer oder allen Rollen (nur für Event-Ersteller)")
@app_commands.guild_only()
async def remove_participant(
    interaction: discord.Interaction, 
    user: discord.Member, 
    role_number: int = None
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

        # Check if the user is the event caller
        if str(interaction.user.id) != event.get('caller_id'):
            await interaction.response.send_message("Nur der Event-Ersteller kann Teilnehmer entfernen.", ephemeral=True)
            return
            
        player_id = str(user.id)
        player_name = user.display_name
        removed_count = 0
        
        # If no role number is specified, remove from all roles
        if role_number is None:
            # Collect the names of the roles from which the participant was removed
            removed_roles = []
            for r_idx, r_name in enumerate(event['roles']):
                r_key = f"{r_idx}:{r_name}"
                if r_key in event.get('participants', {}):
                    if any(p[1] == player_id for p in event['participants'][r_key]):
                        removed_roles.append(r_name)
                    initial_count = len(event['participants'][r_key])
                    event['participants'][r_key] = [p for p in event['participants'][r_key] if p[1] != player_id]
                    removed_count += initial_count - len(event['participants'][r_key])
            
            if removed_count > 0:
                # Inform the participant about the removal from all roles
                try:
                    event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                    dm_message = (
                        f"**Du wurdest aus einem Event entfernt: {event['title']}**\n"
                        f"Du wurdest aus folgenden Rollen entfernt: {', '.join(removed_roles)}\n"
                        f"Datum: {event['date']}\n"
                        f"Uhrzeit: {event['time']}\n"
                        f"\n[Zum Event]({event_link})"
                    )
                    await user.send(dm_message)
                    await interaction.response.send_message(f"{player_name} wurde aus {removed_count} Rollen entfernt und hat eine DN erhalten.")
                except Exception as e:
                    logger.error(f"Failed to send DM to user {user.id}: {e}")
                    await interaction.response.send_message(f"{player_name} wurde aus {removed_count} Rollen entfernt. Eine DN konnte nicht gesendet werden!")
            else:
                await interaction.response.send_message(f"{player_name} war für keine Rolle eingetragen.", ephemeral=True)
        else:
            # Remove from a specific role
            actual_role_index = bot.role_number_to_index(event, role_number)
            
            if actual_role_index < 0:
                await interaction.response.send_message(f"Ungültige Rollennummer: {role_number}", ephemeral=True)
                return
                
            role_name = event['roles'][actual_role_index]
            role_key = f"{actual_role_index}:{role_name}"
            
            if role_key in event.get('participants', {}):
                initial_count = len(event['participants'][role_key])
                # Check first if the player is in the role
                was_in_role = any(p[1] == player_id for p in event['participants'][role_key])
                event['participants'][role_key] = [p for p in event['participants'][role_key] if p[1] != player_id]
                removed_count = initial_count - len(event['participants'][role_key])
                
                if removed_count > 0:
                    # Inform the participant about the removal from the specific role
                    try:
                        event_link = f"https://discord.com/channels/{interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                        dm_message = (
                            f"**Du wurdest aus einer Rolle entfernt: {event['title']}**\n"
                            f"Rolle: {role_name}\n"
                            f"Datum: {event['date']}\n"
                            f"Uhrzeit: {event['time']}\n"
                            f"\n[Zum Event]({event_link})"
                        )
                        await user.send(dm_message)
                        await interaction.response.send_message(f"{player_name} wurde aus Rolle \"{role_name}\" entfernt und hat eine DN erhalten.")
                    except Exception as e:
                        logger.error(f"Failed to send DM to user {user.id}: {e}")
                        await interaction.response.send_message(f"{player_name} wurde aus Rolle \"{role_name}\" entfernt.")
                else:
                    await interaction.response.send_message(f"{player_name} war nicht für Rolle \"{role_name}\" eingetragen.")
            else:
                await interaction.response.send_message(f"Rolle {role_name} hat keine Teilnehmer.", ephemeral=True)
        
        # Update the event only if something was changed
        if removed_count > 0:
            save_event_to_json(event)
            await bot.update_event_message(interaction.channel, event)
            
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
                
                # Find the FILLALL role
                fill_index = next((i for i, role in enumerate(event['roles']) if role.lower() in ["fill", "fillall"]), None)
                
                # Ensure that fill_index has a value
                if fill_index is None:
                    # If no FILLALL role is found, add the new role to the end
                    event['roles'].append(self.proposed_role)
                    new_role_index = len(event['roles']) - 1
                else:
                    # Add the new role before the FILLALL role
                    event['roles'].insert(fill_index, self.proposed_role)
                    new_role_index = fill_index
                    # Update the FILLALL index, since we added a role before it
                    fill_index += 1
                
                # Create role_key for the new role
                new_role_key = f"{new_role_index}:{self.proposed_role}"
                
                # Initialize participants dict for the new role if necessary
                if 'participants' not in event:
                    event['participants'] = {}
                if new_role_key not in event['participants']:
                    event['participants'][new_role_key] = []
                
                # Automatically add the proposer to the new role with comment
                proposer_id = str(self.proposer_id)
                proposer_name = self.proposer_name
                current_time = datetime.now().timestamp()
                
                # Check if the user is already registered in another role (except FILLALL)
                for r_idx, r_name in enumerate(event['roles']):
                    if r_name.lower() == "fill" or r_name.lower() == "fillall":
                        continue  # Ignore Fill roles
                    
                    r_key = f"{r_idx}:{r_name}"
                    if r_key in event.get('participants', {}):
                        for entry_idx, entry in enumerate(event['participants'][r_key]):
                            if entry[1] == proposer_id:
                                # Remove the player from the old role
                                event['participants'][r_key].pop(entry_idx)
                                break
                
                # Add the player to the new role with comment "selbst vorgeschlagen"
                event['participants'][new_role_key].append((proposer_name, proposer_id, current_time, "selbst vorgeschlagen"))
                
                # Update event and save
                save_event_to_json(event)
                
                # Try to update the event message in the thread
                try:
                    # Find the guild and thread
                    guild = bot.get_guild(self.guild_id)
                    if guild:
                        thread = await bot.fetch_thread(guild, self.thread_id)
                        if thread:
                            await bot.update_event_message(thread, event)
                            
                            # Send message to thread about the accepted proposal
                            await thread.send(f"{self.proposer_name} hat die Rolle **{self.proposed_role}** vorgeschlagen und der Vorschlag wurde angenommen.")
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
                            event_link = f"https://discord.com/channels/{self.guild_id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                            dm_message = (
                                f"Dein Rollenvorschlag **{self.proposed_role}** wurde angenommen!\n"
                                f"Event: {event['title']}\n"
                                f"Datum: {event['date']}\n"
                                f"Uhrzeit: {event['time']}\n"
                                f"Du wurdest automatisch in diese Rolle eingetragen.\n"
                                f"[Zum Event]({event_link})"
                            )
                            await proposer.send(dm_message)
                            dm_sent = True
                except Exception as e:
                    logger.error(f"Failed to send DN to proposer {self.proposer_id}: {e}")
                
                # Update the message with disabled buttons and confirmation
                info_message = f"Rolle **{self.proposed_role}** wurde zum Event hinzugefügt. {self.proposer_name} wurde automatisch auf die neue Rolle umgebucht."
                if dm_sent:
                    info_message += f" Der Vorschlagende wurde per DN informiert."
                info_message += f"\n[Zum Event]({event_link})"
                
                await button_interaction.response.edit_message(
                    content=info_message, 
                    view=self
                )
            
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
                                f"Dein Rollenvorschlag '**{self.proposed_role}**' für das Event '{event['title']}' wurde abgelehnt.\n[Zum Event]({event_link})"
                            )
                            await proposer.send(dm_message)
                            dm_sent = True
                except Exception as e:
                    logger.error(f"Failed to send DN to proposer {self.proposer_id}: {e}")
                
                # Update the message with disabled buttons and rejection info
                info_message = f"Rollenvorschlag **{self.proposed_role}** wurde abgelehnt."
                if dm_sent:
                    info_message += f" Der Vorschlagende wurde per DN informiert."
                
                event_link = f"https://discord.com/channels/{self.guild_id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                info_message += f"\n[Zum Event]({event_link})"
                
                await button_interaction.response.edit_message(
                    content=info_message, 
                    view=self
                )
        
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
                f"{interaction.user.display_name} schlägt eine neue Rolle für dein Event '{event['title']}' vor: **{role_name}**\n"
                f"Möchtest du diese Rolle zum Event hinzufügen?\n"
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

bot.run(DISCORD_TOKEN)
            