import discord
from discord import app_commands
from dotenv import load_dotenv
import os
from datetime import datetime, time
import json
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('eventify')

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

    async def on_message(self, message):
        logger.info(f"Message received: {message.content} in channel: {message.channel.name if hasattr(message.channel, 'name') else 'Unknown'}")
        
        # Ignore messages from the bot itself
        if message.author == self.user:
            logger.info("Ignoring message from self")
            return

        # Check if the message is in a thread
        if isinstance(message.channel, discord.Thread):
            event_title = message.channel.name
            
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
                    role_number = int(role_number_str)
                    logger.info(f"Processing role signup in thread: {message.channel.name}, content: {message.content}")
                    await self._handle_role_signup(message, event_title, role_number)
            
            # Check for unregister all roles with "-"
            elif message.content.strip() == "-":
                logger.info(f"Processing unregister from all roles: {message.channel.name}, user: {message.author.name}")
                await self._handle_unregister(message, False)
            
            # Check for unregister from specific role with "-N"
            elif message.content.strip().startswith("-") and message.content.strip()[1:].isdigit():
                role_number = int(message.content.strip()[1:])
                logger.info(f"Processing unregister from role {role_number}: {message.channel.name}, user: {message.author.name}")
                await self._handle_unregister(message, True, role_number - 1)
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
                
                # Check if this is the "Fill" role by name instead of position
                is_fill_role = False
                if 0 <= role_index < len(event['roles']):
                    is_fill_role = event['roles'][role_index].lower() == "fill" or event['roles'][role_index].lower() == "fillall"
                
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
                            logger.info(f"Updated comment for {player_name} in role {role_name}")
                        else:
                            # Just acknowledge if no comment to update
                            logger.info(f"{player_name} already assigned to role {role_name} at index {role_index}")
                            await message.add_reaction('ℹ️')  # Info reaction
                    else:
                        # For Fill role, no limit on players and can be added even if already registered for another role
                        if is_fill_role:
                            # Check if the role is specifically FillALL
                            is_fillall_role = event['roles'][role_index].lower() == "fillall"
                            
                            # For FillALL, we ignore comments and allow multiple roles
                            if is_fillall_role:
                                # Add new entry with timestamp (ignore comment for FillALL)
                                event['participants'][role_key].append((player_name, player_id, current_time))
                                logger.info(f"Added {player_name} to FillALL role")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events)
                                await message.add_reaction('✅')  # Add confirmation reaction
                            else:
                                # This is a regular Fill role (not FillALL)
                                # Add new entry with timestamp and comment
                                if comment:
                                    event['participants'][role_key].append((player_name, player_id, current_time, comment))
                                else:
                                    event['participants'][role_key].append((player_name, player_id, current_time))
                                
                                logger.info(f"Added {player_name} to Fill role")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events)
                                await message.add_reaction('✅')  # Add confirmation reaction
                        else:
                            # Check if player is already signed up for another role (except Fill)
                            already_signed_up = False
                            player_current_role = None
                            for r_idx, r_name in enumerate(event['roles']):
                                if r_name.lower() == "fill" or r_name.lower() == "fillall":
                                    continue  # Skip Fill and FillALL roles
                                
                                r_key = f"{r_idx}:{r_name}"
                                if r_key in event.get('participants', {}):
                                    if any(entry[1] == player_id for entry in event['participants'][r_key]):
                                        already_signed_up = True
                                        player_current_role = r_name
                                        break
                            
                            if already_signed_up:
                                logger.warning(f"{player_name} is already signed up for role {player_current_role}")
                                await message.channel.send(
                                    f"Sorry, you are already signed up for role '{player_current_role}'. "
                                    f"You can only sign up for one regular role. "
                                    f"You can additionally sign up for FillALL. "
                                    f"If you want to change your role, unregister first with `-` and then sign up for the new role. "
                                    f"You can add a comment to note your alternative roles."
                                )
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
                    await message.channel.send(f"Invalid role number. Please select a number between 1 and {len(event['roles'])}.")
            else:
                logger.warning(f"No event found matching thread name: {event_title}")
                await message.channel.send("No matching event found for this thread.")
        except Exception as e:
            logger.error(f"Error processing role assignment: {e}")
            await message.channel.send(f"Error processing your request: {str(e)}")

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
                        await message.channel.send(f"Invalid role number. Please select a number between 1 and {len(event['roles'])}.")
            else:
                logger.warning(f"No event found matching thread name: {message.channel.name}")
                await message.channel.send("No matching event found for this thread.")
        except Exception as e:
            logger.error(f"Error processing unregister: {e}")
            await message.channel.send(f"Error processing your request: {str(e)}")

    async def _update_event_and_save(self, message, event, events):
        try:
            # Update the event message
            await self.update_event_message(message.channel, event)
            logger.info("Updated event message")
            
            # Save updated events to JSON
            save_events_to_json(events)
            logger.info("Saved updated events to JSON")
        except Exception as e:
            logger.error(f"Error updating event or saving to JSON: {e}")
            await message.channel.send(f"Error updating event: {str(e)}")

    async def update_event_message(self, thread, event):
        try:
            logger.info(f"Updating event message for event: {event['title']}")
            
            # Create Discord Embed
            embed = discord.Embed(title=event['title'], color=0x0dceda)
            
            # Add event details
            embed.add_field(name="Date", value=event['date'], inline=True)
            embed.add_field(name="Time", value=event['time'], inline=True)
            embed.add_field(name="Description", value=event['description'], inline=False)
            
            # Find the Fill role - case insensitive check
            fill_index = next((i for i, role in enumerate(event['roles']) if role.lower() in ["fill", "fillall"]), None)
            if fill_index is None:
                # If no Fill role found, add one
                fill_index = len(event['roles'])
                event['roles'].append("FillALL")
                # Save the updated event
                save_event_to_json(event)
            
            # Stelle sicher, dass FillALL immer als letzte Rolle erscheint
            # Falls es nicht die letzte Rolle ist, verschiebe es ans Ende
            if fill_index < len(event['roles']) - 1:
                # Remove FillALL from its current position
                fill_role = event['roles'].pop(fill_index)
                # Add it back at the end
                event['roles'].append(fill_role)
                # Update the fill_index to match the new position
                fill_index = len(event['roles']) - 1
                # Save the updated event
                save_event_to_json(event)
            
            # Extrahiere reguläre Rollen (alles außer FillALL)
            regular_roles = []
            for i, role in enumerate(event['roles']):
                if i != fill_index:  # Alles außer die FillALL-Rolle
                    regular_roles.append((i, role))

            # Begrenze die Anzahl der Felder für reguläre Rollen
            max_role_fields = 23  # 24 fields total (23 + 1 for FillALL)

            # Wenn wir mehr als max_role_fields reguläre Rollen haben, müssen wir sie gruppieren
            if len(regular_roles) > max_role_fields:
                # Gruppiere je 3 Rollen in ein Feld
                role_groups = []
                for i in range(0, len(regular_roles), 3):
                    group = regular_roles[i:i+3]
                    role_groups.append(group)
                
                # Erstelle Felder für jede Gruppe
                for group_idx, group in enumerate(role_groups):
                    if group_idx < max_role_fields:  # Stelle sicher, dass wir nicht mehr als max_role_fields Felder erstellen
                        # Verwende keine Überschrift, einfach ein leeres Feld
                        field_name = "\u200b"  # Unsichtbares Zeichen als Feldname
                        field_content = ""
                        
                        for role_idx, role_name in group:
                            role_key = f"{role_idx}:{role_name}"
                            # Zeige die Rolle auf einer eigenen Zeile
                            line_title = f"{role_idx+1}. {role_name}"
                            field_content += line_title + "\n"
                            
                            # Player information
                            participants = event.get('participants', {}).get(role_key, [])
                            
                            if participants:
                                # Sort participants by timestamp and take only the first one (most recent)
                                sorted_participants = sorted(participants, key=lambda x: x[2] if len(x) > 2 else 0)
                                
                                # Only display the first player (most recent signup)
                                p_data = sorted_participants[0]
                                if len(p_data) >= 2:  # Make sure we have at least name and ID
                                    p_id = p_data[1]
                                    field_content += f"<@{p_id}>"
                                    
                                    # Add comment if exists, on a new line
                                    if len(p_data) >= 4 and p_data[3]:
                                        field_content += f"\n{p_data[3]}"
                                    
                                    field_content += "\n"  # Neue Zeile nach Spieler/Kommentar
                            else:
                                field_content += "-\n"  # Anzeigen von "-" wenn kein Spieler
                            
                            field_content += "\n"  # Extra spacing between roles
                        
                        # Füge das Feld zum Embed hinzu
                        embed.add_field(name=field_name, value=field_content, inline=True)
            else:
                # Wir haben weniger als max_role_fields Rollen, also können wir jede Rolle einzeln anzeigen
                for role_idx, role_name in regular_roles:
                    role_key = f"{role_idx}:{role_name}"
                    field_name = f"{role_idx+1}. {role_name}"
                    
                    # Player information
                    participants = event.get('participants', {}).get(role_key, [])
                    
                    # Erstelle den Feldinhalt
                    field_content = ""
                    
                    if participants:
                        # Sort participants by timestamp and take only the first one (most recent)
                        sorted_participants = sorted(participants, key=lambda x: x[2] if len(x) > 2 else 0)
                        
                        # Only display the first player (most recent signup)
                        p_data = sorted_participants[0]
                        if len(p_data) >= 2:  # Make sure we have at least name and ID
                            p_id = p_data[1]
                            field_content = f"<@{p_id}>"
                            
                            # Add comment if exists, on a new line
                            if len(p_data) >= 4 and p_data[3]:
                                field_content += f"\n{p_data[3]}"
                    else:
                        field_content = "-"
                    
                    # Füge das Feld zum Embed hinzu
                    embed.add_field(name=field_name, value=field_content, inline=True)
            
            # Add Fill role section
            fill_text = ""
            fill_players_text = ""

            if fill_index is not None:
                # Add Fill role header
                fill_text = f"{fill_index+1}. {event['roles'][fill_index]}"
                fill_players_text = ""
                
                # Get participants for Fill role
                fill_key = f"{fill_index}:{event['roles'][fill_index]}"
                fill_participants = event.get('participants', {}).get(fill_key, [])
                
                if fill_participants:
                    # Sort participants by timestamp
                    sorted_fill = sorted(fill_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                    
                    # Für FillALL alle Teilnehmer anzeigen, keine Begrenzung auf einen Spieler
                    for p_data in sorted_fill:
                        if len(p_data) >= 2:  # Sicherstellen, dass wir mindestens Name und ID haben
                            p_id = p_data[1]
                            fill_players_text += f"<@{p_id}>\n"
                else:
                    fill_players_text = "-\n"
                
                # Add Fill role to embed
                embed.add_field(name=fill_text, value=fill_players_text, inline=False)

            # No footer text as requested
            
            # Find the parent message of the thread
            try:
                # The more reliable way - if thread has starter_message attribute
                if hasattr(thread, 'starter_message') and thread.starter_message:
                    message_to_edit = thread.starter_message
                    logger.info("Found starter message through thread.starter_message")
                else:
                    # Try to get the message through the parent channel
                    channel = thread.parent
                    message_to_edit = await channel.fetch_message(thread.id)
                    logger.info("Found message through parent channel fetch")
                
                # Edit the message
                await message_to_edit.edit(content=None, embed=embed)
                logger.info("Successfully updated event message")
                return True
            except Exception as e:
                logger.error(f"Error finding or editing message: {e}")
                # If we can't find the message to edit, send a new one in the thread
                await thread.send("Could not update the original post. Here's the updated information:")
                await thread.send(embed=embed)
                return False
        except Exception as e:
            logger.error(f"Error in update_event_message: {e}")
            await thread.send(f"Error updating event message: {str(e)}")
            return False

class Event:
    def __init__(self, title, date, time, description, roles, datetime_obj=None):
        self.title = title
        self.date = date
        self.time = time
        self.description = description
        self.roles = roles
        self.datetime = datetime_obj  # Store the datetime object
        self.participants = {}  # Dictionary for participants and their roles
    
    def to_dict(self):
        """Convert the event to a dictionary for JSON serialization"""
        return {
            "title": self.title,
            "date": self.date,
            "time": self.time,
            "description": self.description,
            "roles": self.roles,
            "datetime": self.datetime.isoformat() if self.datetime else None,
            "participants": self.participants
        }

class EventModal(discord.ui.Modal, title="Eventify"):
    def __init__(self, title: str, date: str, time: str):
        super().__init__()

        self.description_input = discord.ui.TextInput(label="Beschreibung", style=discord.TextStyle.paragraph,
                                                      placeholder="Gib eine Beschreibung für das Event ein.",
                                                      required=True)
        self.add_item(self.description_input)

        self.roles_input = discord.ui.TextInput(label="Rollen (getrennt durch Zeilenumbrüche)",
                                                 style=discord.TextStyle.paragraph,
                                                 placeholder="Gib die Rollen ein, die für das Event benötigt werden.",
                                                 required=True)
        self.add_item(self.roles_input)

        self.title = title
        self.date = date
        self.time = time
        self.full_datetime = None  # Storage for the datetime object

    async def on_submit(self, interaction: discord.Interaction):
        print("on_submit method called.")
        try:
            description = self.description_input.value
            # Get roles from input and add the "Fill" role
            roles = [role.strip() for role in self.roles_input.value.splitlines()]
            
            # Find the Fill role - case insensitive check
            fill_index = next((i for i, role in enumerate(roles) if role.lower() in ["fill", "fillall"]), None)
            if fill_index is None:
                # If no Fill role found, add one
                fill_index = len(roles)
                roles.append("FillALL")
            
            # Stelle sicher, dass FillALL immer als letzte Rolle erscheint
            # Falls es nicht die letzte Rolle ist, verschiebe es ans Ende
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
                datetime_obj=self.full_datetime  # Pass the datetime object
            )

            # Save the event to JSON
            save_event_to_json(event)
            print("Event saved to JSON.")

            try:
                # First respond to the interaction to close the modal
                await interaction.response.send_message(f"Event '{self.title}' created successfully!", ephemeral=True)
                
                channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
                
                # Create embed with horizontal frames
                embed = discord.Embed(title=event.title, color=0x0dceda)  # Geänderte Embed-Farbe
                
                # Add event details
                embed.add_field(name="Date", value=event.date, inline=True)
                embed.add_field(name="Time", value=event.time, inline=True)
                embed.add_field(name="Description", value=event.description, inline=False)
                
                # Extrahiere reguläre Rollen (alles außer FillALL)
                regular_roles = []
                for i, role in enumerate(roles):
                    if i != fill_index:  # Alles außer die FillALL-Rolle
                        regular_roles.append((i, role))
                
                # Begrenze die Anzahl der Felder für reguläre Rollen
                max_role_fields = 23  # 24 fields total (23 + 1 for FillALL)

                # Wenn wir mehr als max_role_fields reguläre Rollen haben, müssen wir sie gruppieren
                if len(regular_roles) > max_role_fields:
                    # Gruppiere je 3 Rollen in ein Feld
                    role_groups = []
                    for i in range(0, len(regular_roles), 3):
                        group = regular_roles[i:i+3]
                        role_groups.append(group)
                    
                    # Erstelle Felder für jede Gruppe
                    for group_idx, group in enumerate(role_groups):
                        if group_idx < max_role_fields:  # Stelle sicher, dass wir nicht mehr als max_role_fields Felder erstellen
                            # Verwende keine Überschrift, einfach ein leeres Feld
                            field_name = "\u200b"  # Unsichtbares Zeichen als Feldname
                            field_content = ""
                            
                            for role_idx, role_name in group:
                                role_key = f"{role_idx}:{role_name}"
                                # Zeige die Rolle auf einer eigenen Zeile
                                line_title = f"{role_idx+1}. {role_name}"
                                field_content += line_title + "\n"
                                
                                # Player information
                                participants = getattr(event, 'participants', {}).get(role_key, [])
                                
                                if participants:
                                    # Sort participants by timestamp and take only the first one (most recent)
                                    sorted_participants = sorted(participants, key=lambda x: x[2] if len(x) > 2 else 0)
                                    
                                    # Only display the first player (most recent signup)
                                    p_data = sorted_participants[0]
                                    if len(p_data) >= 2:  # Make sure we have at least name and ID
                                        p_id = p_data[1]
                                        field_content += f"<@{p_id}>"
                                        
                                        # Add comment if exists, on a new line
                                        if len(p_data) >= 4 and p_data[3]:
                                            field_content += f"\n{p_data[3]}"
                                        
                                        field_content += "\n"  # Neue Zeile nach Spieler/Kommentar
                                else:
                                    field_content += "-\n"  # Anzeigen von "-" wenn kein Spieler
                                
                                field_content += "\n"  # Extra spacing between roles
                            
                            # Füge das Feld zum Embed hinzu
                            embed.add_field(name=field_name, value=field_content, inline=True)
                else:
                    # Wir haben weniger als max_role_fields Rollen, also können wir jede Rolle einzeln anzeigen
                    for role_idx, role_name in regular_roles:
                        role_key = f"{role_idx}:{role_name}"
                        field_name = f"{role_idx+1}. {role_name}"
                        
                        # Player information
                        participants = getattr(event, 'participants', {}).get(role_key, [])
                        
                        # Erstelle den Feldinhalt
                        field_content = ""
                        
                        if participants:
                            # Sort participants by timestamp and take only the first one (most recent)
                            sorted_participants = sorted(participants, key=lambda x: x[2] if len(x) > 2 else 0)
                            
                            # Only display the first player (most recent signup)
                            p_data = sorted_participants[0]
                            if len(p_data) >= 2:  # Make sure we have at least name and ID
                                p_id = p_data[1]
                                field_content = f"<@{p_id}>"
                                
                                # Add comment if exists, on a new line
                                if len(p_data) >= 4 and p_data[3]:
                                    field_content += f"\n{p_data[3]}"
                        else:
                            field_content = "-"
                        
                        # Füge das Feld zum Embed hinzu
                        embed.add_field(name=field_name, value=field_content, inline=True)
                
                # Add Fill role section
                fill_text = ""
                fill_players_text = ""

                if fill_index is not None:
                    # Add Fill role header
                    fill_text = f"{fill_index+1}. {roles[fill_index]}"
                    fill_players_text = ""
                    
                    # Get participants for Fill role
                    fill_key = f"{fill_index}:{roles[fill_index]}"
                    fill_participants = getattr(event, 'participants', {}).get(fill_key, [])
                    
                    if fill_participants:
                        # Sort participants by timestamp
                        sorted_fill = sorted(fill_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                        
                        # Für FillALL alle Teilnehmer anzeigen, keine Begrenzung auf einen Spieler
                        for p_data in sorted_fill:
                            if len(p_data) >= 2:  # Sicherstellen, dass wir mindestens Name und ID haben
                                p_id = p_data[1]
                                fill_players_text += f"<@{p_id}>\n"
                    else:
                        fill_players_text = "-\n"
                    
                    # Add Fill role to embed
                    embed.add_field(name=fill_text, value=fill_players_text, inline=False)

                event_post = await channel.send(embed=embed)
                
                thread = await event_post.create_thread(name=event.title)
                await thread.send("Instructions for the event will be posted here.")
                print("Event message and thread created.")
            except Exception as e:
                print(f"Error creating event message or thread: {e}")
                # Since we already responded to the interaction, we can't use interaction.response again
                try:
                    # Try to send a follow-up message instead
                    await interaction.followup.send("An error occurred while creating the event message or thread.", ephemeral=True)
                except:
                    # If that fails too, log the error
                    print("Could not send follow-up message.")
        except Exception as e:
            print(f"Error in on_submit: {e}")
            # Make sure we respond to the interaction to close the modal
            try:
                await interaction.response.send_message("An error occurred while processing your request.", ephemeral=True)
            except:
                # If we've already responded, try to send a follow-up
                try:
                    await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)
                except:
                    print("Could not send error message.")

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
    """Save an event to the JSON file"""
    # Try to load existing events
    events = []
    if os.path.exists(EVENTS_JSON_FILE):
        try:
            with open(EVENTS_JSON_FILE, 'r') as f:
                events = json.load(f)
        except json.JSONDecodeError:
            # If the file is corrupted, start with an empty list
            events = []

    # Clean up old events before adding new one
    events = clean_old_events(events)
    
    # Add the new event - prüfe, ob es ein Event-Objekt oder ein Dictionary ist
    if hasattr(event, 'to_dict'):
        # Es ist ein Event-Objekt
        events.append(event.to_dict())
    else:
        # Es ist bereits ein Dictionary
        events.append(event)
    
    # Save back to the file
    with open(EVENTS_JSON_FILE, 'w') as f:
        json.dump(events, f, indent=4)

def clean_old_events(events_data):
    """Remove events that have already passed"""
    if not events_data:
        return []
    
    now = datetime.now()
    current_events = []
    
    for event_data in events_data:
        # Keep events only if they have a valid datetime and it's in the future
        if event_data.get('datetime'):
            try:
                event_datetime = datetime.fromisoformat(event_data['datetime'])
                if event_datetime > now:
                    current_events.append(event_data)
            except (ValueError, TypeError):
                # Skip events with invalid datetime format
                pass
    
    return current_events

def load_upcoming_events():
    """Load all upcoming events from the JSON file"""
    if not os.path.exists(EVENTS_JSON_FILE):
        return []
    
    try:
        with open(EVENTS_JSON_FILE, 'r') as f:
            events_data = json.load(f)
        
        # Clean up the file while we're at it
        cleaned_events = clean_old_events(events_data)
        
        # If we removed any events, update the file
        if len(cleaned_events) < len(events_data):
            with open(EVENTS_JSON_FILE, 'w') as f:
                json.dump(cleaned_events, f, indent=4)
        
        # Sort by datetime
        cleaned_events.sort(key=lambda x: datetime.fromisoformat(x['datetime']))
        return cleaned_events
    
    except Exception as e:
        print(f"Error loading events: {e}")
        return []

def save_events_to_json(events):
    """Save all events to the JSON file"""
    with open(EVENTS_JSON_FILE, 'w') as f:
        json.dump(events, f, indent=4)

@bot.tree.command(name="eventify", description="Starte ein neues Event")
async def create_event(interaction: discord.Interaction, title: str, date: str, time: str):
    try:
        # Parse date and time
        parsed_date = parse_date(date)
        parsed_time = parse_time(time)
        
        if not parsed_date or not parsed_time:
            await interaction.response.send_message("Ungültiges Datum oder Zeitformat! \nBitte verwende DDMMYYYY (31122025 für den 31.12.2025) für das Datum und HHMM (1300 für 13:00 Uhr) für die Zeit.", ephemeral=True)
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
        
        # Create and show the modal
        modal = EventModal(title, formatted_date, formatted_time)
        modal.full_datetime = full_datetime  # Pass the datetime object to the modal
        await interaction.response.send_modal(modal)
    except Exception as e:
        print(f"Error in create_event: {e}")
        await interaction.response.send_message(f"Ein Fehler ist aufgetreten: {str(e)}", ephemeral=True)

bot.run(DISCORD_TOKEN)
