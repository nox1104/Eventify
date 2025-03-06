import discord
from discord import app_commands
from dotenv import load_dotenv
import os
from datetime import datetime
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
            
            # Check for digit (sign up for role)
            if message.content.isdigit():
                logger.info(f"Processing role signup in thread: {message.channel.name}, content: {message.content}")
                await self._handle_role_signup(message, event_title, int(message.content))
            
            # Check for unregister all roles with "-"
            elif message.content.strip() == "-":
                logger.info(f"Processing unregister from all roles: {message.channel.name}, user: {message.author.name}")
                await self._handle_unregister_all(message, event_title)
            
            # Check for unregister from specific role with "-N"
            elif message.content.strip().startswith("-") and message.content.strip()[1:].isdigit():
                role_number = int(message.content.strip()[1:])
                logger.info(f"Processing unregister from role {role_number}: {message.channel.name}, user: {message.author.name}")
                await self._handle_unregister_specific(message, event_title, role_number)
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
                    is_fill_role = event['roles'][role_index].lower() == "fill"
                
                if 0 <= role_index < len(event['roles']):
                    role_name = event['roles'][role_index]
                    player_name = message.author.name
                    player_id = str(message.author.id)
                    current_time = datetime.now().timestamp()  # For sorting by signup time

                    logger.info(f"Assigning {player_name} to role {role_name} at index {role_index}")
                    
                    # Initialize participants dict if needed
                    if 'participants' not in event:
                        event['participants'] = {}
                        
                    # Use role_index as part of the key for participants to handle duplicate role names
                    role_key = f"{role_index}:{role_name}"
                    
                    if role_key not in event['participants']:
                        event['participants'][role_key] = []
                    
                    # Check if player is already signed up for this role
                    existing_entry = next((i for i, entry in enumerate(event['participants'][role_key]) 
                                         if entry[0] == player_name), None)
                    
                    if existing_entry is not None:
                        # Player is already signed up, do nothing
                        logger.info(f"{player_name} already assigned to role {role_name} at index {role_index}")
                        await message.add_reaction('ℹ️')  # Info reaction
                    else:
                        # For Fill role, no limit on players
                        if is_fill_role:
                            # Add new entry with timestamp for sorting
                            event['participants'][role_key].append((player_name, player_id, current_time))
                            logger.info(f"Added {player_name} to Fill role")
                            
                            # Update the event message and save to JSON
                            await self._update_event_and_save(message, event, events)
                            await message.add_reaction('✅')  # Add confirmation reaction
                        else:
                            # For regular roles, check choice number and if that position is available
                            # First, calculate each player's choice order across all roles
                            player_choices = {}  # Player name -> list of roles in order of signup
                            
                            # Get all participants sorted by timestamp across all roles
                            all_participants = []
                            for r_idx, r_name in enumerate(event['roles']):
                                r_key = f"{r_idx}:{r_name}"
                                if r_key in event.get('participants', {}):
                                    for p_name, p_id, p_time in event['participants'][r_key]:
                                        all_participants.append((p_name, p_id, r_idx, p_time))
                            
                            # Sort all participants by timestamp to get the signup order
                            all_participants.sort(key=lambda x: x[3])  # Sort by timestamp
                            
                            # Build the player choice map
                            for p_name, _, r_idx, _ in all_participants:
                                if p_name not in player_choices:
                                    player_choices[p_name] = []
                                if r_idx not in [role_idx for role_idx in player_choices[p_name]]:
                                    player_choices[p_name].append(r_idx)
                            
                            # Determine player's current choice number (0=first, 1=second, 2=third)
                            choice_num = 0
                            if player_name in player_choices:
                                # Count only non-Fill roles
                                fill_roles = [i for i, r in enumerate(event['roles']) if r.lower() == 'fill']
                                non_fill_choices = [c for c in player_choices[player_name] if c not in fill_roles]
                                choice_num = len(non_fill_choices)
                            
                            # Don't allow more than 3 choices
                            if choice_num >= 3:
                                logger.warning(f"{player_name} already has 3 role choices")
                                await message.add_reaction('❌')  # Rejected reaction
                                await message.channel.send(f"Sorry, you already have 3 role choices. Please unregister from some roles first.")
                                return
                            
                            # Check if this position (color) is already taken in this role
                            position_taken = False
                            
                            # Get the roles' existing participants
                            participants = event.get('participants', {}).get(role_key, [])
                            
                            # Count how many players have each choice number for this role
                            first_choices = 0  # Green
                            second_choices = 0  # Yellow
                            third_choices = 0  # Orange
                            
                            for p_name, _, _ in participants:
                                if p_name in player_choices:
                                    try:
                                        # Find this role's position in the player's choices
                                        p_choice_num = player_choices[p_name].index(role_index)
                                        
                                        # Skip Fill role for counting choices
                                        fill_roles = [i for i, r in enumerate(event['roles']) if r.lower() == 'fill']
                                        non_fill_choices = [c for c in player_choices[p_name] if c not in fill_roles]
                                        if role_index in non_fill_choices:
                                            p_choice_num = non_fill_choices.index(role_index)
                                        
                                        if p_choice_num == 0:
                                            first_choices += 1
                                        elif p_choice_num == 1:
                                            second_choices += 1
                                        else:
                                            third_choices += 1
                                    except ValueError:
                                        # If role not in player's choices, count as first choice
                                        first_choices += 1
                            
                            # Check if the player's desired choice level is already taken
                            if choice_num == 0 and first_choices >= 1:
                                position_taken = True
                                await message.channel.send(f"Sorry, the first choice (green) for '{role_name}' is already taken.")
                            elif choice_num == 1 and second_choices >= 1:
                                position_taken = True
                                await message.channel.send(f"Sorry, the second choice (yellow) for '{role_name}' is already taken.")
                            elif choice_num == 2 and third_choices >= 1:
                                position_taken = True
                                await message.channel.send(f"Sorry, the third choice (orange) for '{role_name}' is already taken.")
                            
                            # Also check if role is full (max 3 players)
                            if len(participants) >= 3:
                                position_taken = True
                                await message.channel.send(f"Sorry, the role '{role_name}' already has the maximum of 3 players.")
                            
                            if position_taken:
                                await message.add_reaction('❌')  # Rejected reaction
                            else:
                                # Add new entry with timestamp for sorting
                                event['participants'][role_key].append((player_name, player_id, current_time))
                                logger.info(f"Added {player_name} to role {role_name} as choice #{choice_num+1}")
                                
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

    async def _handle_unregister_all(self, message, event_title):
        try:
            # Load events from JSON
            events = load_upcoming_events()
            
            # Find the event that matches the thread name
            event = next((e for e in events if e['title'] == event_title), None)

            if event:
                player_name = message.author.name
                removed_count = 0
                
                # Check all roles and remove the player
                if 'participants' in event:
                    # Make a copy of keys to avoid modification during iteration
                    role_keys = list(event['participants'].keys())
                    
                    for role_key in role_keys:
                        # Make a copy of participants list to safely modify
                        participants = event['participants'][role_key].copy()
                        
                        for i, entry in enumerate(participants):
                            # Check if entry has enough elements
                            if len(entry) >= 1 and entry[0] == player_name:
                                event['participants'][role_key].remove(entry)
                                removed_count += 1
                
                if removed_count > 0:
                    logger.info(f"Removed {player_name} from {removed_count} roles in event {event_title}")
                    
                    # Update the event message and save to JSON
                    await self._update_event_and_save(message, event, events)
                    await message.add_reaction('✅')  # Add confirmation reaction
                else:
                    logger.info(f"{player_name} was not registered for any roles in event {event_title}")
                    await message.add_reaction('ℹ️')  # Info reaction
            else:
                logger.warning(f"No event found matching thread name: {event_title}")
                await message.channel.send("No matching event found for this thread.")
        except Exception as e:
            logger.error(f"Error processing unregister: {e}")
            await message.channel.send(f"Error processing your request: {str(e)}")

    async def _handle_unregister_specific(self, message, event_title, role_number):
        try:
            role_index = role_number - 1
            
            # Load events from JSON
            events = load_upcoming_events()
            
            # Find the event that matches the thread name
            event = next((e for e in events if e['title'] == event_title), None)

            if event:
                if 0 <= role_index < len(event['roles']):
                    role_name = event['roles'][role_index]
                    player_name = message.author.name
                    
                    logger.info(f"Unregistering {player_name} from role {role_name} at index {role_index}")
                    
                    # Use role_index as part of the key for participants
                    role_key = f"{role_index}:{role_name}"
                    
                    if 'participants' in event and role_key in event['participants']:
                        # Find and remove the player from the role
                        for i, entry in enumerate(event['participants'][role_key]):
                            if entry[0] == player_name:  # Check player name (first element in tuple)
                                event['participants'][role_key].pop(i)
                                logger.info(f"Removed {player_name} from role {role_name} at index {role_index}")
                                
                                # Update the event message and save to JSON
                                await self._update_event_and_save(message, event, events)
                                await message.add_reaction('✅')  # Add confirmation reaction
                                return
                        
                        logger.info(f"{player_name} was not registered for role {role_name} at index {role_index}")
                        await message.add_reaction('ℹ️')  # Info reaction
                    else:
                        logger.info(f"Role {role_name} at index {role_index} has no participants")
                        await message.add_reaction('ℹ️')  # Info reaction
                else:
                    logger.warning(f"Invalid role index: {role_index}. Event has {len(event['roles'])} roles.")
                    await message.channel.send(f"Invalid role number. Please select a number between 1 and {len(event['roles'])}.")
            else:
                logger.warning(f"No event found matching thread name: {event_title}")
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
            
            # First, calculate each player's choice order across all roles
            player_choices = {}  # Player name -> list of roles in order of signup
            
            # Get all participants sorted by timestamp across all roles
            all_participants = []
            for r_idx, r_name in enumerate(event['roles']):
                r_key = f"{r_idx}:{r_name}"
                if r_key in event.get('participants', {}):
                    for p_name, p_id, p_time in event['participants'][r_key]:
                        all_participants.append((p_name, p_id, r_idx, p_time))
            
            # Sort all participants by timestamp to get the signup order
            all_participants.sort(key=lambda x: x[3])  # Sort by timestamp
            
            # Build the player choice map
            for p_name, _, r_idx, _ in all_participants:
                if p_name not in player_choices:
                    player_choices[p_name] = []
                if r_idx not in [role_idx for role_idx in player_choices[p_name]]:
                    player_choices[p_name].append(r_idx)

            # Prepare all players for each role
            role_players = {}
            fill_index = -1
            
            for i, role in enumerate(event['roles']):
                # Find the Fill role
                if role.lower() == "fill":
                    fill_index = i
                    continue  # Skip Fill for now
                    
                role_key = f"{i}:{role}"
                participants = event.get('participants', {}).get(role_key, [])
                
                if participants:
                    # Get the choice number for each player in this role
                    player_choices_in_role = {}  # player_name -> choice number (0=first, 1=second, 2=third)
                    
                    for p_name, _, _ in participants:
                        if p_name in player_choices:
                            try:
                                # Find this role's position in the player's choices
                                choice_num = player_choices[p_name].index(i)
                                # Skip Fill role for counting choices
                                if fill_index >= 0:
                                    # Adjust choice number to skip Fill role
                                    actual_choices = [c for c in player_choices[p_name] if c != fill_index]
                                    if i in actual_choices:
                                        choice_num = actual_choices.index(i)
                                player_choices_in_role[p_name] = choice_num
                            except ValueError:
                                player_choices_in_role[p_name] = 0
                    
                    # Organize players by their choice number
                    first_choice = []
                    second_choice = []
                    third_choice = []
                    
                    for p_name, _, _ in participants:
                        choice = player_choices_in_role.get(p_name, 0)
                        if choice == 0:
                            first_choice.append(p_name)
                        elif choice == 1:
                            second_choice.append(p_name)
                        else:
                            third_choice.append(p_name)
                    
                    role_players[i] = {
                        'first': first_choice,
                        'second': second_choice,
                        'third': third_choice
                    }
            
            # Now build the actual display
            table_rows = []
            
            # Process each role
            for i, role in enumerate(event['roles']):
                # Skip Fill for now
                if role.lower() == "fill":
                    continue
                    
                # Format role with number and name (with padding 0 for numbers < 10)
                role_number = f"{i+1:02d}"  # Format with leading zero if < 10
                role_text = f"{role_number}. **{role}**"  # Make role name bold
                
                # Add the role to the table
                table_rows.append(role_text)
                
                # Add participants hierarchically, sorted by choice (first, second, third)
                if i in role_players:
                    choices = role_players[i]
                    player_num = 1
                    
                    # Add first choice players (green)
                    for player in choices['first']:
                        table_rows.append(f"    {player_num}. {player}")
                        player_num += 1
                    
                    # Add second choice players (yellow)
                    for player in choices['second']:
                        table_rows.append(f"    {player_num}. 🟡 {player}")
                        player_num += 1
                    
                    # Add third choice players (orange)
                    for player in choices['third']:
                        table_rows.append(f"    {player_num}. 🟠 {player}")
                        player_num += 1
                
                # Add an empty line after each role for better readability
                table_rows.append("")
            
            # Add the Fill role if it exists
            if fill_index >= 0:
                fill_role = event['roles'][fill_index]
                fill_key = f"{fill_index}:{fill_role}"
                fill_participants = event.get('participants', {}).get(fill_key, [])
                
                # Format Fill role with number and name
                fill_number = f"{fill_index+1:02d}"  # Format with leading zero if < 10
                fill_text = f"{fill_number}. **{fill_role}**"  # Make Fill role bold
                
                # Add the Fill role to the table
                table_rows.append(fill_text)
                
                # Add all Fill participants in a flat list
                if fill_participants:
                    # Sort participants by timestamp
                    sorted_fill = sorted(fill_participants, key=lambda x: x[2] if len(x) > 2 else 0)
                    
                    # No limit for Fill role, list all participants
                    for idx, (name, _, _) in enumerate(sorted_fill):
                        table_rows.append(f"    {idx+1}. {name}")
            else:
                # If no Fill role found, add one
                fill_index = len(event['roles'])
                fill_number = f"{fill_index+1:02d}"  # Format with leading zero
                
                # Add Fill role
                table_rows.append(f"{fill_number}. **Fill**")  # Make Fill role bold
                
                # Add Fill role to the event
                event['roles'].append("Fill")
                # Save the updated event
                save_event_to_json(event)
            
            # DON'T wrap in a code block to preserve bold formatting
            table_text = "\n" + "\n".join(table_rows)
            
            # Improve date/time alignment using proper spacing
            event_message = (
                f"# {event['title']}\n\n"
                f"**Date:** `{event['date']}`\n"
                f"**Time:** `{event['time']}`\n\n"
                f"**Description:**\n{event['description']}\n\n"
                f"**Roles:**{table_text}"
            )

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
                await message_to_edit.edit(content=event_message)
                logger.info("Successfully updated event message")
                return True
            except Exception as e:
                logger.error(f"Error finding or editing message: {e}")
                # If we can't find the message to edit, send a new one in the thread
                await thread.send("Could not update the original post. Here's the updated information:")
                await thread.send(event_message)
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
            
            # Make sure "Fill" is not already in the roles list
            if not any(role.lower() == "fill" for role in roles):
                roles.append("Fill")  # Add Fill role automatically
            
            # Create table for initial display
            table_rows = []
            
            # Add regular roles
            fill_index = -1
            for i, role in enumerate(roles):
                if role.lower() == "fill":
                    fill_index = i
                    continue
                
                # Format role with number and name (with padding 0 for numbers < 10)
                role_number = f"{i+1:02d}"  # Format with leading zero if < 10
                role_text = f"{role_number}. **{role}**"  # Make role bold
                
                # Add the row to the table
                table_rows.append(role_text)
                # Add an empty line after each role
                table_rows.append("")
            
            # Add Fill role
            if fill_index >= 0:
                fill_number = f"{fill_index+1:02d}"  # Format with leading zero
                table_rows.append(f"{fill_number}. **{roles[fill_index]}**")  # Make role bold
            else:
                fill_index = len(roles) - 1
                fill_number = f"{fill_index+1:02d}"  # Format with leading zero
                table_rows.append(f"{fill_number}. **Fill**")  # Make role bold
            
            # Don't wrap in code block to preserve bold formatting
            table_text = "\n" + "\n".join(table_rows)
            
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
                event_message = (
                    f"# {event.title}\n\n"
                    f"**Date:** `{event.date}`\n"
                    f"**Time:** `{event.time}`\n\n"
                    f"**Description:**\n{event.description}\n\n"
                    f"**Roles:**{table_text}"
                )
                
                event_post = await channel.send(event_message)
                
                thread = await event_post.create_thread(name=event.title)
                await thread.send("Type a number to sign up for a role. Your first signup will be your 1st choice (green), second signup your 2nd choice (yellow), etc. Only one player per role can have the same choice level. Type `-` to unregister from all roles, or `-N` to unregister from a specific role.")
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
    try:
        return datetime.strptime(date_str, "%d%m%Y").date()
    except ValueError:
        return None

def parse_time(time_str: str):
    try:
        return datetime.strptime(time_str, "%H%M").time()
    except ValueError:
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
    
    # Add the new event
    events.append(event.to_dict())
    
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
    parsed_date = parse_date(date)
    parsed_time = parse_time(time)

    if not parsed_date or not parsed_time:
        await interaction.response.send_message("Ungültiges Datum oder Zeitformat! \nBitte verwende DDMMYYYY (31122025 für den 31.12.2025) für das Datum und HHMM (1200 für 12:00 Uhr) für die Zeit.", ephemeral=True)
        return

    # Combine date and time into a datetime object
    full_datetime = datetime.combine(parsed_date, parsed_time)
    
    formatted_date = parsed_date.strftime("%d.%m.%Y")
    formatted_time = parsed_time.strftime("%H:%M")

    modal = EventModal(title, formatted_date, formatted_time)
    modal.full_datetime = full_datetime  # Store the datetime object in the modal
    await interaction.response.send_modal(modal)

@bot.tree.command(name="upcoming_events", description="List all upcoming events")
async def list_upcoming_events(interaction: discord.Interaction):
    upcoming_events = load_upcoming_events()
    
    if not upcoming_events:
        await interaction.response.send_message("No upcoming events found.", ephemeral=True)
        return
    
    # Create a nice formatted list of upcoming events
    event_list = ["# Upcoming Events\n"]
    
    for i, event in enumerate(upcoming_events, 1):
        event_list.append(f"## {i}. {event['title']}")
        event_list.append(f"**Date:** {event['date']} | **Time:** {event['time']}")
        event_list.append(f"**Description:** {event['description'][:100]}..." if len(event['description']) > 100 else f"**Description:** {event['description']}")
        event_list.append("---")
    
    await interaction.response.send_message("\n".join(event_list), ephemeral=False)

bot.run(DISCORD_TOKEN)
