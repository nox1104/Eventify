#Always communicate with users in German
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
CHANNEL_ID_EVENT = int(os.getenv("CHANNEL_ID_EVENT"))
CHANNEL_ID_EVENT_LISTING = int(os.getenv("CHANNEL_ID_EVENT_LISTING"))
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
        print(f"Logged in as {self.user}")
        await self.tree.sync()
        print("Slash commands synchronized!")
        print("Bot is ready and listening for messages.")
        
        # Start the loops
        self.delete_old_event_threads.start()
        self.cleanup_event_channel.start()  # New loop added

    async def on_message(self, message):
        logger.info(f"Message received: {message.content} in channel: {message.channel.name if hasattr(message.channel, 'name') else 'Unknown'}")
        
        # Ignore messages from the bot itself
        if message.author == self.user:
            logger.info("Ignoring message from self")
            return

        # Check if the message is in a thread
        if isinstance(message.channel, discord.Thread):
            event_title = message.channel.name
            
            # Load events from JSON for role index conversion
            events = load_upcoming_events()
            event = next((e for e in events if e['title'] == event_title), None)
            
            if not event:
                logger.warning(f"No event found matching thread name: {event_title}")
                # Only respond if user is attempting command
                if message.content.strip() and (message.content.strip()[0].isdigit() or message.content.strip() == "-" or 
                                               (message.content.strip().startswith("-") and message.content.strip()[1:].isdigit())):
                    await message.channel.send("Anmeldungen für dieses Event sind nicht möglich.")
                return
            
            # Check for digit at the beginning (sign up for role)
            if message.content.strip() and message.content.strip()[0].isdigit():
                # Extract the role number (everything until the first non-digit)
                role_number_str = ""
                for char in message.content.strip():
                    if char.isdigit():
                        role_number_str += char
                    else:
                        break
                
                if role_number_str:
                    # Convert to int and process the role signup
                    display_role_number = int(role_number_str)
                    logger.info(f"Processing role signup in thread: {message.channel.name}, content: {message.content}")
                    
                    # Conversion of displayed role number to actual index
                    actual_role_index = self.role_number_to_index(event, display_role_number)
                    
                    if actual_role_index >= 0:
                        # Process role signup with actual role index
                        await self._handle_role_signup(message, event_title, actual_role_index + 1)
                    else:
                        # Only logging, no message to user
                        logger.warning(f"Invalid role number: {display_role_number}. Event has {len(event['roles'])} roles.")
            
            # Check for unregister all roles with "-"
            elif message.content.strip() == "-":
                logger.info(f"Processing unregister from all roles: {message.channel.name}, user: {message.author.name}")
                await self._handle_unregister(message, False)
            
            # Check for unregister from specific role with "-N"
            elif message.content.strip().startswith("-") and message.content.strip()[1:].isdigit():
                display_role_number = int(message.content.strip()[1:])
                logger.info(f"Processing unregister from role {display_role_number}: {message.channel.name}, user: {message.author.name}")
                
                # Conversion of displayed role number to actual index
                actual_role_index = self.role_number_to_index(event, display_role_number)
                
                if actual_role_index >= 0:
                    # Process unregister with actual role index
                    await self._handle_unregister(message, True, actual_role_index)
                else:
                    # Only logging, no message to user
                    logger.warning(f"Invalid role number: {display_role_number}. Event has {len(event['roles'])} roles.")
        else:
            logger.debug("Message is not in a thread.")

    async def _handle_role_signup(self, message, event_title, role_number):
        try:
            role_index = role_number - 1
            
            # Load events from JSON
            events = load_upcoming_events()
            logger.info(f"Loaded {len(events)} events from JSON")
            
            # Find the event that matches the thread name
            event = next((e for e in events if e['title'] == event_title), None)

            if event:
                logger.info(f"Found matching event: {event['title']}")
                
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
                            await self._update_event_and_save(message, event, events)
                            await message.add_reaction('✅')  # Add confirmation reaction
                        else:
                            # Just acknowledge if no comment to update
                            logger.info(f"{player_name} already assigned to role {role_name} at index {role_index}")
                            await message.add_reaction('ℹ️')  # Info reaction
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
                                await self._update_event_and_save(message, event, events)
                                await message.add_reaction('✅')  # Add confirmation reaction
                            else:
                                # This is a regular Fill role (not FillALL) or participant_only_mode
                                # Add new entry with timestamp and comment
                                if comment:
                                    event['participants'][role_key].append((player_name, player_id, current_time, comment))
                                else:
                                    event['participants'][role_key].append((player_name, player_id, current_time))
                                
                                logger.info(f"Added {player_name} to Fill role or participant_only_mode")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events)
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
                                await self._update_event_and_save(message, event, events)
                                await message.add_reaction('✅')  # Add confirmation reaction
                            else:
                                # Add new entry with timestamp and comment
                                if comment:
                                    event['participants'][role_key].append((player_name, player_id, current_time, comment))
                                else:
                                    event['participants'][role_key].append((player_name, player_id, current_time))
                                
                                logger.info(f"Added {player_name} to role {role_name}")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events)
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

    async def _handle_unregister(self, message, is_specific_role=False, role_index=None):
        try:
            # Load events from JSON
            events = load_upcoming_events()
            
            # Find the event that matches the thread name
            event = next((e for e in events if e['title'] == message.channel.name), None)

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
                        await self._update_event_and_save(message, event, events)
                        await message.add_reaction('✅')  # Add confirmation reaction
                    else:
                        await message.add_reaction('❓')  # Player wasn't registered
                else:
                    # This is a specific role unregister
                    if 0 <= role_index < len(event['roles']):
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
                                await self._update_event_and_save(message, event, events)
                                await message.add_reaction('✅')  # Add confirmation reaction
                            else:
                                logger.info(f"{player_name} was not registered for role {role_name}")
                                await message.add_reaction('❓')  # Player wasn't registered
                        else:
                            logger.info(f"Role {role_name} has no participants")
                            await message.add_reaction('❓')  # Info reaction
                    else:
                        logger.warning(f"Invalid role index: {role_index}. Event has {len(event['roles'])} roles.")
                        # No message to the user
            else:
                logger.warning(f"No event found matching thread name: {message.channel.name}")
                await message.channel.send("Kein passendes Event für diesen Thread gefunden.")
        except Exception as e:
            logger.error(f"Error processing unregister: {e}")
            await message.channel.send(f"Fehler bei der Verarbeitung deiner Anfrage: {str(e)}")

    async def _update_event_and_save(self, message, event, events):
        try:
            # Find the event by ID if available, otherwise by title
            event_id = event.get("event_id")
            if event_id:
                # Find the event in the events list by ID
                for e in events:
                    if e.get("event_id") == event_id:
                        # Update the event
                        e.update(event)
                        break
            else:
                # Fallback to title for backward compatibility
                for e in events:
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
            
            # Create the embed with CYAN color
            title = event.get('title') if isinstance(event, dict) else event.title
            embed = discord.Embed(title=f"__**{title}**__", color=0x0dceda)  # Wichtig: Cyan statt Grün
            
            # Add caller information directly under the title
            caller_id = event.get('caller_id') if isinstance(event, dict) else getattr(event, 'caller_id', None)
            if caller_id:
                embed.add_field(name="Erstellt von", value=f"<@{caller_id}>", inline=False)
            
            # Add mention role if available
            mention_role_id = event.get('mention_role_id') if isinstance(event, dict) else getattr(event, 'mention_role_id', None)
            if mention_role_id:
                embed.add_field(name="Für", value=f"<@&{mention_role_id}>", inline=False)
            
            # Add event details
            date = event.get('date') if isinstance(event, dict) else getattr(event, 'date', '')
            time = event.get('time') if isinstance(event, dict) else getattr(event, 'time', '')
            embed.add_field(name="Date", value=date, inline=True)
            embed.add_field(name="Time", value=time, inline=True)
            
            # Add description
            description = event.get('description') if isinstance(event, dict) else getattr(event, 'description', '')
            if len(description) > 1020:  # Leave room for ellipsis
                description = description[:1020] + "..."
            embed.add_field(name="Description", value=description, inline=False)
            
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
                                    participants_text += f"<@{p[1]}> - {p[3]}\n"
                                else:
                                    participants_text += f"<@{p[1]}>\n"
                        
                        # Add the field
                        embed.add_field(name=participant_title, value=participants_text or "\u200b", inline=False)
                    else:
                        # Empty participant list
                        embed.add_field(name=participant_title, value="\u200b", inline=False)
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
                        # Add a line break if it's not the first header
                        if field_content:
                            field_content += "\n"
                        # Remove parentheses from section header
                        header_text = role_name.strip()[1:-1]  # Remove first and last character
                        field_content += f"**{header_text}**\n"
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
                                    field_content += f" {p_data[3]}"
                                
                                field_content += "\n"
                            else:
                                field_content += f"{role_counter}. {role_name}\n"
                        else:
                            field_content += f"{role_counter}. {role_name}\n"
                        
                        # Increment the role counter for actual roles
                        role_counter += 1

                # Add all regular roles as a single field
                if field_content:
                    embed.add_field(name="\u200b", value=field_content, inline=False)

                # Add Fill role section
                if fill_index is not None:
                    # Add Fill role header
                    fill_text = f"{role_counter}. {roles[fill_index]}"
                    
                    # Get participants for Fill role
                    fill_key = f"{fill_index}:{roles[fill_index]}"
                    fill_participants = participants.get(fill_key, [])
                    
                    if fill_participants:
                        # Sort participants by timestamp
                        sorted_fill = sorted(fill_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                        
                        # Display all participants for FillALL
                        fill_players_text = "\n".join([f"<@{p[1]}>" for p in sorted_fill if len(p) >= 2])
                        
                        # Add Fill role to embed
                        embed.add_field(name=fill_text, value=fill_players_text or "\u200b", inline=False)
                    else:
                        # Display empty Fill role
                        embed.add_field(name=fill_text, value="\u200b", inline=False)
            
            # Add image if available (new function)
            image_url = event.get('image_url') if isinstance(event, dict) else getattr(event, 'image_url', None)
            if image_url:
                embed.set_image(url=image_url)
            
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
        """Löscht Threads von Events, die vor mehr als 15 Minuten begonnen haben"""
        try:
            now = datetime.now()
            logger.info(f"{now} - Überprüfe alte Event-Threads...")
            
            # Load all events
            events = load_upcoming_events()
            
            for event in events:
                try:
                    # Get the event_id
                    event_id = event.get('event_id')
                    if not event_id:
                        logger.warning(f"Keine event_id für Event '{event.get('title')}' gefunden.")
                        continue
                    
                    # Extract date and time from event_id (Format: YYYYMMDDHHmm-uuid)
                    datetime_str = event_id.split('-')[0]  # Take the part before the hyphen
                    try:
                        event_datetime = datetime.strptime(datetime_str, "%Y%m%d%H%M")
                        
                        # Check if the event started more than 15 minutes ago
                        if event_datetime < now - timedelta(minutes=15):
                            logger.info(f"Event '{event['title']}' (ID: {event_id}) hat vor mehr als 15 Minuten begonnen. Lösche Thread...")
                            
                            # We need the thread that is connected to this event
                            if 'message_id' in event and event['message_id']:
                                for guild in self.guilds:
                                    # Search both in the event channel and directly after the thread
                                    channel = guild.get_channel(CHANNEL_ID_EVENT)
                                    if channel:
                                        try:
                                            # Check first if we can find the message
                                            try:
                                                message = await channel.fetch_message(int(event['message_id']))
                                                
                                                # Check if there is a thread for this message
                                                if hasattr(message, 'thread') and message.thread:
                                                    # Thread found, delete it
                                                    await message.thread.delete()
                                                    logger.info(f"Thread für Event '{event['title']}' gelöscht.")
                                                    
                                                    # Send notification to the event channel
                                                    await channel.send(
                                                        f"Der Thread für das Event '{event['title']}' wurde automatisch gelöscht, "
                                                        f"da das Event bereits begonnen hat.", 
                                                        delete_after=300
                                                    )
                                                else:
                                                    logger.warning(f"Kein Thread an Nachricht für Event '{event['title']}' gefunden.")
                                            except discord.NotFound:
                                                # Message not found, try to find thread directly
                                                logger.info(f"Message for Event '{event['title']}' not found. Try to find thread directly...")
                                            
                                            # Alternative method: Search for thread with event title
                                            thread_found = False
                                            for thread in channel.threads:
                                                if thread.name == event['title']:
                                                    await thread.delete()
                                                    logger.info(f"Thread mit Namen '{event['title']}' gelöscht.")
                                                    thread_found = True
                                                    
                                                    # Send notification to the event channel
                                                    await channel.send(
                                                        f"Der Thread für das Event '{event['title']}' wurde automatisch gelöscht, "
                                                        f"da das Event bereits begonnen hat.", 
                                                        delete_after=300
                                                    )
                                                    break
                                            
                                            # Try to search archived threads
                                            if not thread_found:
                                                async for archived_thread in channel.archived_threads():
                                                    if archived_thread.name == event['title']:
                                                        await archived_thread.delete()
                                                        logger.info(f"Archivierter Thread mit Namen '{event['title']}' gelöscht.")
                                                        
                                                        # Send notification to the event channel
                                                        await channel.send(
                                                            f"Der Thread für das Event '{event['title']}' wurde automatisch gelöscht, "
                                                            f"da das Event bereits begonnen hat.", 
                                                            delete_after=300
                                                        )
                                                        break
                                        except Exception as e:
                                            logger.error(f"Fehler beim Löschen des Threads: {e}")
                            else:
                                logger.warning(f"Keine message_id für Event '{event['title']}' gefunden.")
                                
                    except ValueError as e:
                        logger.error(f"Fehler beim Parsen der event_id {event_id}: {e}")
                        
                except Exception as e:
                    logger.error(f"Fehler bei der Verarbeitung des Events: {e}")
                    
        except Exception as e:
            logger.error(f"Fehler bei der Thread-Überprüfung: {e}")

    # Wait until the bot is ready before starting the loop
    @delete_old_event_threads.before_loop
    async def before_delete_old_event_threads(self):
        await self.wait_until_ready()

    @tasks.loop(hours=6)  
    async def cleanup_event_channel(self):
        """
        Räumt den Event-Kanal vorsichtig auf. Löscht nur:
        - Vergangene Event-Posts (bestätigt durch events.json)
        - System-Nachrichten (z.B. "Bot ist online")
        Alle anderen Nachrichten bleiben erhalten.
        """
        logger.info(f"{datetime.now()} - Starte vorsichtiges Aufräumen des Event-Kanals...")
        
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
                
            # Load active events
            try:
                with open('events.json', 'r') as f:
                    events_data = json.load(f)
                    id_to_event = {str(event['message_id']): event['event_id'] 
                                 for event in events_data if 'message_id' in event and 'event_id' in event}
            except FileNotFoundError:
                logger.error("events.json nicht gefunden! Breche Aufräumen ab.")
                return
            except Exception as e:
                logger.error(f"Kritischer Fehler beim Laden der Events: {e}")
                return

            # Counter for logging
            counter = {
                "system": 0,      # System messages
                "past_event": 0,  # Past events
                "protected": 0,   # Protected messages
                "skipped": 0      # Skipped messages
            }
            
            # List of messages to delete
            to_delete = []
            
            # Collect messages to delete
            async for message in channel.history(limit=1000):
                try:
                    # PROTECTED: Skip messages with threads
                    if message.thread:
                        logger.info(f"GESCHÜTZT: Nachricht {message.id} hat aktiven Thread")
                        counter["protected"] += 1
                        continue

                    # PROTECTED: Skip messages from other bots (except ourselves)
                    if message.author.bot and message.author.id != bot.user.id:
                        logger.info(f"GESCHÜTZT: Nachricht {message.id} ist von anderem Bot")
                        counter["protected"] += 1
                        continue

                    # PROTECTED: Skip messages with attachments
                    if message.attachments:
                        logger.info(f"GESCHÜTZT: Nachricht {message.id} hat Anhänge")
                        counter["protected"] += 1
                        continue

                    # Check event posts
                    message_id_str = str(message.id)
                    if message_id_str in id_to_event:
                        event_id = id_to_event[message_id_str]
                        event_datetime_str = event_id.split('-')[0]
                        try:
                            event_datetime = datetime.strptime(event_datetime_str, '%Y%m%d%H%M')
                            event_datetime = event_datetime.replace(tzinfo=timezone.utc)
                            
                            # Only delete if event is at least 1 hour old
                            if event_datetime + timedelta(hours=1) < datetime.now(timezone.utc):
                                logger.info(f"Mark vergangenes Event zur Löschung: {message.id}")
                                to_delete.append(message)
                                counter["past_event"] += 1
                            else:
                                logger.info(f"GESCHÜTZT: Event {message.id} ist noch aktiv oder zu neu")
                                counter["protected"] += 1
                        except ValueError as e:
                            logger.error(f"Fehler beim Parsen des Event-Datums {event_datetime_str}: {e}")
                            counter["skipped"] += 1
                            continue
                    
                    # Check system messages from our bot
                    elif message.author.id == bot.user.id and not message.embeds:
                        # List of known system messages
                        system_messages = [
                            "bot on",
                            "bot off",
                            "Bot ist online",
                            "Bot ist offline",
                            "Thread wurde gelöscht"
                        ]
                        
                        if any(msg in message.content for msg in system_messages):
                            logger.info(f"Markiere System-Nachricht zur Löschung: {message.id}")
                            to_delete.append(message)
                            counter["system"] += 1
                        else:
                            logger.info(f"GESCHÜTZT: Unbekannte Bot-Nachricht: {message.id}")
                            counter["protected"] += 1
                    else:
                        logger.info(f"GESCHÜTZT: Sonstige Nachricht: {message.id}")
                        counter["protected"] += 1

                except Exception as e:
                    logger.error(f"Fehler bei Nachricht {message.id}: {e}")
                    counter["skipped"] += 1
                    continue

            # SAFETY: Check again the number of messages to be deleted
            if len(to_delete) > 100:
                logger.warning(f"Ungewöhnlich viele Nachrichten ({len(to_delete)}) zum Löschen markiert!")
                logger.warning("Lösche nur die ersten 100 zur Sicherheit.")
                to_delete = to_delete[:100]

            # Delete the marked messages
            deleted = 0
            for message in to_delete:
                try:
                    await message.delete()
                    deleted += 1
                    await asyncio.sleep(1.2)  # Großzügige Pause zwischen Löschungen
                except Exception as e:
                    logger.error(f"Fehler beim Löschen von Nachricht {message.id}: {e}")

            # Final log
            logger.info(f"Aufräumen abgeschlossen:")
            logger.info(f"- {counter['past_event']} vergangene Events markiert")
            logger.info(f"- {counter['system']} System-Nachrichten markiert")
            logger.info(f"- {counter['protected']} Nachrichten geschützt")
            logger.info(f"- {counter['skipped']} Nachrichten übersprungen")
            logger.info(f"- {deleted} Nachrichten erfolgreich gelöscht")

    # Wait until the bot is ready before starting the loop
    @cleanup_event_channel.before_loop
    async def before_cleanup_event_channel(self):
        await self.wait_until_ready()

class Event:
    def __init__(self, title, date, time, description, roles, datetime_obj=None, caller_id=None, caller_name=None, participant_only_mode=False):
        self.title = title
        self.date = date
        self.time = time
        self.description = description
        self.roles = roles
        self.participants = {}
        self.datetime_obj = datetime_obj
        self.caller_id = caller_id  # Discord ID of the creator
        self.caller_name = caller_name  # Name of the creator
        self.message_id = None  # Message ID of the event post
        self.participant_only_mode = participant_only_mode  # Flag for participant-only mode
        
        # Generate a unique ID for the event
        timestamp = datetime_obj.strftime("%Y%m%d%H%M") if datetime_obj else datetime.now().strftime("%Y%m%d%H%M")
        random_string = str(uuid.uuid4())[:8]  # Use first 8 characters of UUID
        self.event_id = f"{timestamp}-{random_string}"
    
    def get(self, attr, default=None):
        """Emulates dictionary-like get method to maintain compatibility."""
        return getattr(self, attr, default)
    
    def to_dict(self):
        """Convert the event to a dictionary for JSON serialization"""
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
            "participant_only_mode": self.participant_only_mode  # Store the flag for participant-only mode
        }

class EventModal(discord.ui.Modal, title="Eventify"):
    def __init__(self, title: str, date: str, time: str, caller_id: str, caller_name: str, mention_role: discord.Role = None, image_url: str = None):
        super().__init__()

        self.description_input = discord.ui.TextInput(label="Beschreibung", style=discord.TextStyle.paragraph,
                                                      placeholder="Gib eine Beschreibung für das Event ein.",
                                                      required=True)
        self.add_item(self.description_input)

        self.roles_input = discord.ui.TextInput(label="Rollen (getrennt durch Zeilenumbrüche)",
                                                 style=discord.TextStyle.paragraph,
                                                 placeholder="Gib die Rollen ein oder schreibe 'none' für eine einfache Teilnehmerliste.",
                                                 required=True)
        self.add_item(self.roles_input)

        self.title = title
        self.date = date
        self.time = time
        self.full_datetime = None  # Storage for the datetime object
        self.caller_id = caller_id  # Discord ID des Erstellers
        self.caller_name = caller_name  # Name des Erstellers
        self.mention_role = mention_role
        self.image_url = image_url

    async def on_submit(self, interaction: discord.Interaction):
        print("on_submit method called.")
        try:
            description = self.description_input.value
            
            # Get roles from input, filter out empty lines
            raw_roles_input = self.roles_input.value.strip()
            
            # Check if "none", "nan" or similar inputs were made (case-insensitive)
            is_participant_only_mode = raw_roles_input.lower() in ["none", "nan", "null", "keine", "nix", "nö"]
            fill_index = None  # Initialize fill_index outside the condition
            
            if is_participant_only_mode:
                # For "none" only create a "Participants" role
                roles = ["Participants"]
            else:
                # Normal mode with Fill role
                roles = [role.strip() for role in raw_roles_input.splitlines() if role.strip()]
                
                # Find the Fill role - case insensitive check
                fill_index = next((i for i, role in enumerate(roles) if role.lower() in ["fill", "fillall"]), None)
                if fill_index is None:
                    # If no Fill role found, add one
                    fill_index = len(roles)
                    roles.append("FillALL")
                
                # Ensure FillALL always appears as the last role
                if fill_index < len(roles) - 1:
                    # Remove FillALL from its current position
                    fill_role = roles.pop(fill_index)
                    # Add it back at the end
                    roles.append(fill_role)
                    # Update the fill_index to match the new position
                    fill_index = len(roles) - 1
            
            event = Event(
                title=self.title,
                date=self.date,
                time=self.time,
                description=description,
                roles=roles,
                datetime_obj=self.full_datetime,
                caller_id=self.caller_id,
                caller_name=self.caller_name,
                participant_only_mode=is_participant_only_mode
            )

            # Store the mention role ID separately in the event object
            if self.mention_role:
                event.mention_role_id = str(self.mention_role.id)
                
            # Add the image URL if available
            if self.image_url:
                event.image_url = self.image_url
                
            # Save the event to JSON
            save_event_to_json(event)
            print("Event saved to JSON.")

            # Silently close the modal without sending a message
            await interaction.response.defer()

            channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
            
            # Create embed with horizontal frames
            embed = discord.Embed(title=f"__**{event.title}**__", color=0x0dceda)
            
            # Add caller information directly under the title
            if event.caller_id:
                embed.add_field(name="Erstellt von", value=f"<@{event.caller_id}>", inline=False)
            
            # Add the mention role as a separate field if it exists
            if self.mention_role:
                embed.add_field(name="Für", value=f"<@&{self.mention_role.id}>", inline=False)
            
            # Add event details
            embed.add_field(name="Date", value=event.date, inline=True)
            embed.add_field(name="Time", value=event.time, inline=True)
            
            # Truncate description if it's too long (Discord limit is 1024 characters per field)
            description_text = event.description
            if len(description_text) > 1020:  # Leave room for ellipsis
                description_text = description_text[:1020] + "..."
            embed.add_field(name="Description", value=description_text, inline=False)
            
            # Extract regular roles (everything except FillALL)
            regular_roles = []
            section_headers = []
            for i, role in enumerate(roles):
                if i != fill_index:  # Everything except the FillALL role
                    # Check if it's a section header (text in parentheses)
                    if role.strip().startswith('(') and role.strip().endswith(')'):
                        section_headers.append((i, role))
                    else:
                        regular_roles.append((i, role))

            # Creation of the content for all regular roles
            field_content = ""
            current_section = None
            role_counter = 1  # Counter for actual roles (excluding section headers)

            # Go through all roles and section headers in the original order
            all_items = section_headers + regular_roles
            all_items.sort(key=lambda x: x[0])  # Sort by the original index

            for role_idx, role_name in all_items:
                # Check if it's a section header
                if role_name.strip().startswith('(') and role_name.strip().endswith(')'):
                    # Add a blank line if it's not the first header
                    if field_content:
                        field_content += "\n"
                    # Remove parentheses from section header
                    header_text = role_name.strip()[1:-1]  # Remove first and last character
                    field_content += f"**{header_text}**\n"
                else:
                    # This is a normal role
                    field_content += f"{role_counter}. {role_name}\n"
                    role_counter += 1

            # Add all regular roles as a single field
            if field_content:
                embed.add_field(name="\u200b", value=field_content, inline=False)
            
            # Add Fill role section
            if fill_index is not None:
                # Add Fill role header
                fill_text = f"{role_counter}. {roles[fill_index]}"
                embed.add_field(name=fill_text, value="", inline=False)
            
            # Send the event post and create a thread
            event_post = await channel.send(embed=embed)
            thread = await event_post.create_thread(name=event.title)
            
            # Save the message ID
            event.message_id = event_post.id
            save_event_to_json(event)
            
            welcome_embed = discord.Embed(
                title="Das Event wurde erfolgreich erstellt.",
                description="Hier findest du alle wichtigen Informationen:",
                color=0x0dceda  # Eventify Cyan
            )

            welcome_embed.add_field(
                name="Benutzerhandbuch",
                value="Im [Benutzerhandbuch](https://github.com/nox1104/Eventify/blob/main/Benutzerhandbuch.md) findest du Anleitungen zur Anmeldung für Rollen, zur Event-Verwaltung und zur Benutzung des Bots im Allgemeinen.",
                inline=False
            )

            welcome_embed.add_field(
                name="Teilnehmer-Tipps",
                value="**Anmelden**: Schreibe einfach die Nummer der gewünschten Rolle\n"
                      "**Abmelden**: Schreibe `-` (von allen Rollen) oder `-X` (von Rolle X)\n"
                      "**Kommentar hinzufügen**: Schreibe nach der Rollennummer deinen Kommentar (z.B. 3 mh, dps)",
                inline=False
            )

            welcome_embed.add_field(
                name="Event-Ersteller Befehle",
                value="• `/remind` - Erinnerung an alle Teilnehmer senden\n"
                      "• `/add` - Teilnehmer zu einer Rolle hinzufügen\n"
                      "• `/remove` - Teilnehmer aus Rollen entfernen",
                inline=False
            )

            welcome_embed.add_field(name="Support", value="Fragen, Bugs oder Feature-Vorschläge gehen an <@778914224613228575>", inline=False)

            await thread.send(embed=welcome_embed)
            print("Event message and thread created.")
            
            # Create the event listing after the event is created
            await create_event_listing(interaction.guild)
            
        except Exception as e:
            print(f"Error creating event message or thread: {e}")
            # Since we already responded to the interaction, we can't use interaction.response again
            try:
                # Try to send a follow-up message instead
                await interaction.followup.send(f"Ein Fehler ist aufgetreten: {str(e)}", ephemeral=True)
            except Exception as follow_up_error:
                print(f"Couldn't send follow-up error message: {follow_up_error}")

async def create_event_listing(guild):
    """Erstellt ein Event Listing mit allen anstehenden Events"""
    try:
        # Load all upcoming events
        events = load_upcoming_events()
        
        if not events:
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
        for event in events:
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
                # Here we could also remove the event from the JSON
                continue
        
        # Update the events.json to remove orphaned events
        if len(valid_events) < len(events):
            logger.info(f"Remove {len(events) - len(valid_events)} orphaned events from the JSON.")
            save_events_to_json(valid_events)
        
        if not valid_events:
            logger.info("No valid events with existing posts found.")
            return
        
        # Use only valid events for the overview
        events = valid_events
        
        # Sort events by date and time
        try:
            # Sort by datetime_obj, if available
            events_with_datetime = []
            for event in events:
                # Try to convert date and time to a datetime object
                if 'datetime_obj' in event and event['datetime_obj']:
                    # datetime_obj is already stored as a string, convert it back
                    dt_str = event['datetime_obj']
                    dt_obj = datetime.fromisoformat(dt_str)
                    events_with_datetime.append((event, dt_obj))
                else:
                    # Fallback: Try to create a datetime object from the date and time
                    try:
                        date_str = event['date']
                        time_str = event['time']
                        # Convert German date format (dd.mm.yyyy) to datetime
                        day, month, year = map(int, date_str.split('.'))
                        hour, minute = map(int, time_str.split(':'))
                        dt_obj = datetime(year, month, day, hour, minute)
                        events_with_datetime.append((event, dt_obj))
                    except (ValueError, KeyError) as e:
                        logger.error(f"Error parsing date/time for event {event.get('title', 'unknown')}: {e}")
                        # Add the event with the current timestamp so it is displayed
                        events_with_datetime.append((event, datetime.now()))
            
            # Sort the events by timestamp
            events_with_datetime.sort(key=lambda x: x[1])
            sorted_events = [event for event, _ in events_with_datetime]
        except Exception as e:
            logger.error(f"Error sorting events: {e}")
            sorted_events = events  # Fallback: Unsorted events
        
        # Group events by date
        events_by_date = {}
        for event in sorted_events:
            date = event.get('date', 'Unknown date')
            if date not in events_by_date:
                events_by_date[date] = []
            events_by_date[date].append(event)
        
        # Create the embed
        embed = discord.Embed(
            title="Event overview",
            color=0x0dceda  # Eventify Cyan
        )
        
        # Add each date with its events
        for date, date_events in events_by_date.items():
            # Create the description for this date
            date_description = ""
            for event in date_events:
                title = event.get('title', 'Unbekanntes Event')
                time = event.get('time', '')
                caller_id = event.get('caller_id', None)
                message_id = event.get('message_id')
                
                # Add time, caller and title
                if caller_id:
                    if message_id and message_id != "None" and message_id != None:
                        date_description += f"{time} <@{caller_id}> [#{title}](https://discord.com/channels/{guild_id}/{CHANNEL_ID_EVENT}/{message_id})\n"
                    else:
                        date_description += f"{time} <@{caller_id}> {title}\n"
                else:
                    if message_id and message_id != "None" and message_id != None:
                        date_description += f"{time} [#{title}](https://discord.com/channels/{guild_id}/{CHANNEL_ID_EVENT}/{message_id})\n"
                    else:
                        date_description += f"{time} {title}\n"
            
            # Add the field with this date
            embed.add_field(
                name=f"{date}",
                value=date_description,
                inline=False
            )
        
        # Send the embed to the event channel
        channel = guild.get_channel(CHANNEL_ID_EVENT)
        await channel.send(embed=embed)
        logger.info("Event listing created successfully.")
    except Exception as e:
        logger.error(f"Error creating event listing: {e}")

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

def save_event_to_json(event):
    try:
        # Check if file exists, create it if not
        if not os.path.exists(EVENTS_JSON_FILE):
            with open(EVENTS_JSON_FILE, 'w') as f:
                json.dump({"events": []}, f, indent=4)
        
        # Load existing events
        with open(EVENTS_JSON_FILE, 'r') as f:
            try:
                events_data = json.load(f)
            except json.JSONDecodeError:
                # File is corrupted, reset it
                logger.error(f"JSON file is corrupted. Resetting {EVENTS_JSON_FILE}")
                events_data = {"events": []}
        
        # Validate format
        if not isinstance(events_data, dict) or "events" not in events_data:
            events_data = {"events": []}
        
        # Clean old events (past events)
        events_data = clean_old_events(events_data)
        
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
            
            if isinstance(event, dict):
                event["event_id"] = event_id
            else:
                event.event_id = event_id
        
        # Search for the event by the ID
        for i, e in enumerate(events_data["events"]):
            if e.get("event_id") == event_id:
                # Update existing event
                if hasattr(event, 'to_dict'):
                    events_data["events"][i] = event.to_dict()
                else:
                    events_data["events"][i] = event
                event_exists = True
                break
        
        # If the event is not found, search for the title (for backwards compatibility)
        if not event_exists:
            for i, e in enumerate(events_data["events"]):
                if e["title"] == (event["title"] if isinstance(event, dict) else event.title):
                    # Update existing event
                    if hasattr(event, 'to_dict'):
                        events_data["events"][i] = event.to_dict()
                    else:
                        events_data["events"][i] = event
                    event_exists = True
                    break
                
        # If event doesn't exist, add it
        if not event_exists:
            if hasattr(event, 'to_dict'):
                events_data["events"].append(event.to_dict())
            else:
                events_data["events"].append(event)
        
        # Save back to file
        with open(EVENTS_JSON_FILE, 'w') as f:
            json.dump(events_data, f, indent=4)
        
        return True
    except Exception as e:
        logger.error(f"Error saving event to JSON: {e}")
        return False

def clean_old_events(events_data):
    """Remove events that are in the past"""
    now = datetime.now()
    
    # Ensure the events_data has the expected format
    if not isinstance(events_data, dict) or "events" not in events_data:
        # Convert from old format to new format if needed
        if isinstance(events_data, list):
            events_data = {"events": events_data}
        else:
            events_data = {"events": []}
    
    # Filter out past events
    future_events = []
    removed_count = 0
    
    for event in events_data["events"]:
        keep_event = True
        
        # Check if event has datetime_obj field (new format)
        if "datetime_obj" in event and event["datetime_obj"]:
            try:
                event_dt = datetime.fromisoformat(event["datetime_obj"])
                if event_dt <= now:
                    keep_event = False
                    removed_count += 1
            except (ValueError, TypeError):
                # If datetime parsing fails, try to parse from date and time
                pass
        
        # If no datetime_obj or parsing failed, try to parse from date and time fields
        if keep_event and "date" in event and "time" in event:
            try:
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
                
                # Keep only future events
                if event_dt <= now:
                    keep_event = False
                    removed_count += 1
            except (ValueError, TypeError, IndexError) as e:
                logger.warning(f"Failed to parse date/time for event: {event.get('title', 'unknown')}, error: {e}")
        
        if keep_event:
            future_events.append(event)
    
    if removed_count > 0:
        logger.info(f"Removed {removed_count} past events")
    
    events_data["events"] = future_events
    return events_data

def load_upcoming_events():
    """Load upcoming events from the JSON file"""
    if not os.path.exists(EVENTS_JSON_FILE):
        # Create the file with an empty events list if it doesn't exist
        with open(EVENTS_JSON_FILE, 'w') as f:
            json.dump({"events": []}, f, indent=4)
        return []
    
    try:
        # Check if file is empty
        if os.path.getsize(EVENTS_JSON_FILE) == 0:
            # File is empty, initialize with empty events list
            with open(EVENTS_JSON_FILE, 'w') as f:
                json.dump({"events": []}, f, indent=4)
            return []
            
        with open(EVENTS_JSON_FILE, 'r') as f:
            try:
                events_data = json.load(f)
            except json.JSONDecodeError:
                # File is corrupted, reset it
                logger.error(f"JSON file is corrupted. Resetting {EVENTS_JSON_FILE}")
                with open(EVENTS_JSON_FILE, 'w') as f:
                    json.dump({"events": []}, f, indent=4)
                return []
        
        # Handle different data formats
        if isinstance(events_data, dict) and "events" in events_data:
            events = events_data["events"]
        elif isinstance(events_data, list):
            # Old format, convert it
            events = events_data
            # Save in new format
            with open(EVENTS_JSON_FILE, 'w') as f:
                json.dump({"events": events}, f, indent=4)
        else:
            # Invalid format, return empty list and reset file
            logger.error(f"Invalid JSON format in {EVENTS_JSON_FILE}. Resetting file.")
            events = []
            with open(EVENTS_JSON_FILE, 'w') as f:
                json.dump({"events": []}, f, indent=4)
        
        # Clean old events
        events_data = {"events": events}
        cleaned_data = clean_old_events(events_data)
        
        return cleaned_data["events"]
    except Exception as e:
        logger.error(f"Error loading upcoming events: {e}")
        # Reset the file in case of error
        try:
            with open(EVENTS_JSON_FILE, 'w') as f:
                json.dump({"events": []}, f, indent=4)
        except Exception as write_error:
            logger.error(f"Error resetting events file: {write_error}")
        return []

def save_events_to_json(events):
    """Save events to JSON file"""
    try:
        # Ensure we have the right format
        if isinstance(events, list):
            # Sort the events by event_id
            sorted_events = sorted(events, key=lambda x: x.get('event_id', ''))
            events_data = {"events": sorted_events}
        elif isinstance(events, dict) and "events" in events:
            # Sort the events by event_id
            sorted_events = sorted(events['events'], key=lambda x: x.get('event_id', ''))
            events_data = {"events": sorted_events}
        else:
            events_data = {"events": []}
            logger.error("Invalid events format for save_events_to_json")
        
        with open(EVENTS_JSON_FILE, 'w') as f:
            json.dump(events_data, f, indent=4)
        return True
    except Exception as e:
        logger.error(f"Error saving events to JSON: {e}")
        # Try to reset the file in case of severe corruption
        try:
            with open(EVENTS_JSON_FILE, 'w') as f:
                json.dump({"events": []}, f, indent=4)
        except Exception as write_error:
            logger.error(f"Error resetting events file: {write_error}")
        return False

@bot.tree.command(name="eventify", description="Erstelle ein Event")
@app_commands.describe(
    title="Der Titel des Events",
    date="Das Datum des Events (TT.MM.JJJJ)",
    time="Die Uhrzeit des Events (HH:mm)",
    description="Optional: Die Beschreibung des Events (\\n für Zeilenumbrüche)",
    roles="Optional: Die Rollen (mit \\n getrennt, oder 'none' für Teilnehmer-only Modus)",
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

        if description is not None and roles is not None:
            # Direct event creation without modal
            # Replace literal \n with actual line breaks
            description = description.replace('\\n', '\n')
            roles_input = roles.replace('\\n', '\n').strip()
            
            # Check if we're in participant-only mode
            is_participant_only_mode = roles_input.lower() in ["none", "nan", "null", "keine"]
            fill_index = None
            
            if is_participant_only_mode:
                # For "none"/"nan", create only a "Teilnehmer" role
                roles_list = ["Teilnehmer"]
            else:
                # Normal mode with Fill role
                roles_list = [role.strip() for role in roles_input.splitlines() if role.strip()]
                
                # Find the Fill role - case insensitive check
                fill_index = next((i for i, role in enumerate(roles_list) if role.lower() in ["fill", "fillall"]), None)
                if fill_index is None:
                    # If no Fill role found, add one
                    fill_index = len(roles_list)
                    roles_list.append("FillALL")
                
                # Make sure FillALL is always the last role
                if fill_index < len(roles_list) - 1:
                    # Remove FillALL from its current position
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
            
            # Add caller information directly under the title
            if event.caller_id:
                embed.add_field(name="Erstellt von", value=f"<@{event.caller_id}>", inline=False)
            
            # Add the role mention as a separate field if available
            if mention_role:
                embed.add_field(name="Für", value=f"<@&{mention_role.id}>", inline=False)
            
            # Add event details
            embed.add_field(name="Date", value=event.date, inline=True)
            embed.add_field(name="Time", value=event.time, inline=True)
            
            # Truncate description if it's too long (Discord limit is 1024 characters per field)
            description_text = event.description
            if len(description_text) > 1020:  # Leave room for ellipsis
                description_text = description_text[:1020] + "..."
            embed.add_field(name="Description", value=description_text, inline=False)
            
            # Extract regular roles (everything except FillALL)
            regular_roles = []
            section_headers = []
            for i, role in enumerate(roles_list):
                if i != fill_index:  # Everything except the FillALL role
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
                    # Add a blank line if it's not the first header
                    if field_content:
                        field_content += "\n"
                    # Remove parentheses from section header
                    header_text = role_name.strip()[1:-1]  # Remove first and last character
                    field_content += f"**{header_text}**\n"
                else:
                    # This is a normal role
                    field_content += f"{role_counter}. {role_name}\n"
                    role_counter += 1

            # Add all regular roles as a single field
            if field_content:
                embed.add_field(name="\u200b", value=field_content, inline=False)
            
            # Add Fill role section
            if fill_index is not None:
                # Add Fill role header
                fill_text = f"{role_counter}. {roles_list[fill_index]}"
                embed.add_field(name=fill_text, value="", inline=False)
            
            # Send the event post and create a thread
            event_post = await channel.send(embed=embed)
            thread = await event_post.create_thread(name=event.title)
            
            # Save the message ID
            event.message_id = event_post.id
            save_event_to_json(event)
            
            welcome_embed = discord.Embed(
                title="Das Event wurde erfolgreich erstellt.",
                description="Hier findest du alle wichtigen Informationen:",
                color=0x0dceda  # Eventify Cyan
            )

            welcome_embed.add_field(
                name="Benutzerhandbuch",
                value="Im ❗[Benutzerhandbuch]❗(https://github.com/nox1104/Eventify/blob/main/Benutzerhandbuch.md) findest du Anleitungen zur Anmeldung für Rollen, zur Event-Verwaltung und zur Benutzung des Bots im Allgemeinen.",
                inline=False
            )

            welcome_embed.add_field(
                name="Teilnehmer-Tipps",
                value="**Anmelden**: Schreibe einfach die Nummer der gewünschten Rolle\n"
                      "**Abmelden**: Schreibe `-` (von allen Rollen) oder `-X` (von Rolle X)\n"
                      "**Kommentar hinzufügen**: Schreibe nach der Rollennummer deinen Kommentar (z.B. 3 mh, dps)",
                inline=False
            )

            welcome_embed.add_field(
                name="Event-Ersteller Befehle",
                value="• `/remind` - Erinnerung an alle Teilnehmer senden\n"
                      "• `/add` - Teilnehmer zu einer Rolle hinzufügen\n"
                      "• `/remove` - Teilnehmer aus Rollen entfernen",
                inline=False
            )

            welcome_embed.add_field(name="Support", value="Fragen, Bugs oder Feature-Vorschläge gehen an <@778914224613228575>", inline=False)

            await thread.send(embed=welcome_embed)
            
            # Create the event listing after creating the event
            await create_event_listing(interaction.guild)
            
            # Send a follow-up message to confirm event creation
            await interaction.followup.send("Event wurde erfolgreich erstellt!", ephemeral=True)
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

        # Load the event
        events = load_upcoming_events()
        event = next((e for e in events if e['title'] == interaction.channel.name), None)

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
                        reminder_message += f"\n🔗 [Zum Event]({event_link})"
                    
                    await user.send(reminder_message)
                    success_count += 1
            except Exception as e:
                logger.error(f"Failed to send reminder to user {participant_id}: {e}")
                

    except Exception as e:
        logger.error(f"Error in remind_participants: {e}")
        await interaction.response.send_message(
            "Ein Fehler ist beim Versenden der Erinnerungen aufgetreten.", 
            ephemeral=True
        )

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

        # Load the event
        events = load_upcoming_events()
        event = next((e for e in events if e['title'] == interaction.channel.name), None)

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
                    f"\n🔗 [Zum Event]({event_link})"
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
                dm_message += f"\n🔗 [Zum Event]({event_link})"
                
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

        # Load the event
        events = load_upcoming_events()
        event = next((e for e in events if e['title'] == interaction.channel.name), None)

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
                        f"\n🔗 [Zum Event]({event_link})"
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
                            f"\n🔗 [Zum Event]({event_link})"
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

        # Load the event
        events = load_upcoming_events()
        event = next((e for e in events if e['title'] == interaction.channel.name), None)

        if not event:
            await interaction.response.send_message("Kein passendes Event für diesen Thread gefunden.", ephemeral=True)
            return
        
        # Check if the role already exists
        if role_name in event['roles']:
            await interaction.response.send_message(f"Die Rolle '{role_name}' existiert bereits in diesem Event.", ephemeral=True)
            return
        
        # Create the confirmation components
        class RoleProposalView(discord.ui.View):
            def __init__(self, proposer_id, proposer_name, proposed_role):
                super().__init__(timeout=86400)  # 24 Stunden Timeout
                self.proposer_id = proposer_id
                self.proposer_name = proposer_name
                self.proposed_role = proposed_role
                
            @discord.ui.button(label="Annehmen", style=discord.ButtonStyle.green)
            async def accept_button(self, button_interaction: discord.Interaction, button: discord.ui.Button):
                # Check if the reacting user is the event caller
                if str(button_interaction.user.id) != event.get('caller_id'):
                    await button_interaction.response.send_message("Nur der Event-Ersteller kann diesen Vorschlag annehmen.", ephemeral=True)
                    return
                
                # Find the FillALL role
                fill_index = next((i for i, role in enumerate(event['roles']) if role.lower() in ["fill", "fillall"]), None)
                
                # Ensure that fill_index has a value
                if fill_index is None:
                    # If no FillALL role is found, add the new role to the end
                    event['roles'].append(self.proposed_role)
                    new_role_index = len(event['roles']) - 1
                else:
                    # Add the new role before the FillALL role
                    event['roles'].insert(fill_index, self.proposed_role)
                    new_role_index = fill_index
                    # Update the FillALL index, since we added a role before it
                    fill_index += 1
                
                # Create role_key for the new role
                new_role_key = f"{new_role_index}:{self.proposed_role}"
                
                # Initialize participants dict for the new role if necessary
                if 'participants' not in event:
                    event['participants'] = {}
                if new_role_key not in event['participants']:
                    event['participants'][new_role_key] = []
                
                # Automatically add the proposer to the new role
                dm_sent = False
                proposer_id = str(self.proposer_id)
                proposer_name = self.proposer_name
                current_time = datetime.now().timestamp()
                
                # Check if the user is already registered in another role (except FillALL)
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
                
                # Add the player to the new role
                event['participants'][new_role_key].append((proposer_name, proposer_id, current_time))
                
                # Update event and save
                save_event_to_json(event)
                
                # Update the event message
                await bot.update_event_message(button_interaction.channel, event)
                
                # Disable all buttons
                for child in self.children:
                    child.disabled = True
                
                # Inform the proposer
                try:
                    proposer = await button_interaction.guild.fetch_member(self.proposer_id)
                    if proposer:
                        event_link = f"https://discord.com/channels/{button_interaction.guild.id}/{CHANNEL_ID_EVENT}/{event.get('message_id')}"
                        dm_message = (
                            f"**Dein Rollenvorschlag '{self.proposed_role}' wurde angenommen!**\n"
                            f"Event: {event['title']}\n"
                            f"Datum: {event['date']}\n"
                            f"Uhrzeit: {event['time']}\n"
                            f"Du wurdest automatisch in diese Rolle eingetragen.\n"
                            f"\n🔗 [Zum Event]({event_link})"
                        )
                        await proposer.send(dm_message)
                        dm_sent = True
                except Exception as e:
                    logger.error(f"Failed to send DM to proposer {self.proposer_id}: {e}")
                
                # Update the message with disabled buttons and DM info
                dm_info = " und hat eine DM erhalten" if dm_sent else ""
                await button_interaction.response.edit_message(
                    content=f"✅ Rolle '{self.proposed_role}' wurde zum Event hinzugefügt! {self.proposer_name} wurde automatisch auf die neue Rolle umgebucht{dm_info}.", 
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
                    proposer = await button_interaction.guild.fetch_member(self.proposer_id)
                    if proposer:
                        await proposer.send(f"Dein Rollenvorschlag '{self.proposed_role}' für das Event '{event['title']}' wurde abgelehnt.")
                        dm_sent = True
                except Exception as e:
                    logger.error(f"Failed to send DM to proposer {self.proposer_id}: {e}")
                
                # Update the message with disabled buttons and DM info
                dm_info = " und hat eine DM erhalten" if dm_sent else ""
                await button_interaction.response.edit_message(
                    content=f"❌ Rollenvorschlag '{self.proposed_role}' wurde abgelehnt. {self.proposer_name} wurde informiert{dm_info}.", 
                    view=self
                )
        
        # Create the view with the buttons
        view = RoleProposalView(interaction.user.id, interaction.user.display_name, role_name)
        
        # Send the proposal message with buttons
        caller_mention = f"<@{event['caller_id']}>" if event.get('caller_id') else "Event-Ersteller"
        
        await interaction.response.send_message(
            f"{caller_mention}, {interaction.user.mention} schlägt eine neue Rolle vor: **{role_name}**\n"
            f"Möchtest du diese Rolle zum Event hinzufügen?",
            view=view
        )
        
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
            