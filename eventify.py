import discord
from discord import app_commands
from dotenv import load_dotenv
import os
from datetime import datetime
import json

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_EVENT = int(os.getenv("CHANNEL_ID_EVENT"))
CHANNEL_ID_EVENT_LISTING = int(os.getenv("CHANNEL_ID_EVENT_LISTING"))
EVENTS_JSON_FILE = "events.json"

intents = discord.Intents.default()
intents.guilds = True  # Important for slash command sync

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        await self.tree.sync()
        print("Slash commands synchronized!")

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
        description = self.description_input.value
        roles = [role.strip() for role in self.roles_input.value.splitlines()]
        
        roles_block = "\n".join([f"{i+1}. {role}" for i, role in enumerate(roles)])
        
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

        channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
        event_message = (
            f"# {event.title}\n"
            f"**Datum:** `{event.date}`\n"
            f"**Zeit:** `{event.time}`\n\n"
            f"**Beschreibung:**\n```\n{event.description}\n```\n"
            f"**Rollen:**\n```\n{roles_block}\n```"
        )
        event_post = await channel.send(event_message)
        
        thread = await event_post.create_thread(name=event.title)
        await thread.send(f"**{event.title}**\nReagiere mit einer Zahl, um dich für eine Rolle anzumelden. Tippe `-` (Minus) um dich abzumelden.")

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
