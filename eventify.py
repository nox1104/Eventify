import discord
from discord import app_commands
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID_EVENT = int(os.getenv("CHANNEL_ID_EVENT"))
CHANNEL_ID_EVENT_LISTING = int(os.getenv("CHANNEL_ID_EVENT_LISTING"))

intents = discord.Intents.default()
intents.guilds = True  # Wichtig für Slash-Command-Sync

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
        self.datetime = datetime_obj  # Speichern des datetime-Objekts
        self.participants = {}  # Dictionary for participants and their roles

class MyModal(discord.ui.Modal, title="Eventify"):
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
        self.full_datetime = None  # Speicherplatz für das datetime-Objekt

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
            datetime_obj=self.full_datetime  # Übergeben des datetime-Objekts
        )

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
        await thread.send("Reagiere mit einer Zahl, um dich für eine Rolle anzumelden. Tippe '-' um dich abzumelden.")

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

@bot.tree.command(name="eventify", description="Start to eventify")
async def create_event(interaction: discord.Interaction, title: str, date: str, time: str):
    parsed_date = parse_date(date)
    parsed_time = parse_time(time)

    if not parsed_date or not parsed_time:
        await interaction.response.send_message("Ungültiges Datum oder Zeitformat! \nBitte verwende DDMMYYYY (31122025 für den 31.12.2025) für das Datum und HHMM (1230 für 12:30 Uhr) für die Zeit.", ephemeral=True)
        return

    # Kombinieren von date und time zu einem datetime-Objekt
    full_datetime = datetime.combine(parsed_date, parsed_time)
    
    formatted_date = parsed_date.strftime("%d.%m.%Y")
    formatted_time = parsed_time.strftime("%H:%M")

    modal = MyModal(title, formatted_date, formatted_time)
    modal.full_datetime = full_datetime  # Speichern des datetime-Objekts im Modal
    await interaction.response.send_modal(modal)

bot.run(DISCORD_TOKEN)
