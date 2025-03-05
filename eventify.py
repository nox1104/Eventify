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
    def __init__(self, title, date, time, description, roles):
        self.title = title
        self.date = date
        self.time = time
        self.description = description
        self.roles = roles
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

    async def on_submit(self, interaction: discord.Interaction):
        description = self.description_input.value
        roles = [role.strip() for role in self.roles_input.value.splitlines()]

        event = Event(
            title=self.title,
            date=self.date,
            time=self.time,
            description=description,
            roles=roles
        )

        channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
        event_message = f"**Event:** {event.title}\n**Datum:** {event.date}\n**Zeit:** {event.time}\n**Beschreibung:** {event.description}\n**Rollen:** {', '.join(event.roles)}"
        event_post = await channel.send(event_message)

        thread = await event_post.create_thread(name=event.title)
        await thread.send("Reagiere mit einer Zahl, um dich für eine Rolle anzumelden. Tippe '-' um dich abzumelden.")

        def check(message):
            return message.channel == thread and message.author != interaction.client.user

        while True:
            try:
                message = await interaction.client.wait_for('message', check=check)
                content = message.content.strip()

                if content.startswith('-'):
                    if content == '-':
                        if message.author.id in event.participants:
                            del event.participants[message.author.id]
                            await thread.send(f"{message.author.mention} hat sich abgemeldet.")
                        else:
                            await thread.send(f"{message.author.mention}, du bist für keine Rolle angemeldet.")
                    else:
                        role_index = int(content[1:]) - 1
                        if role_index in range(len(event.roles)):
                            if message.author.id in event.participants and event.participants[message.author.id] == event.roles[role_index]:
                                del event.participants[message.author.id]
                                await thread.send(f"{message.author.mention} hat sich von der Rolle '{event.roles[role_index]}' abgemeldet.")
                            else:
                                await thread.send(f"{message.author.mention}, du bist nicht für die Rolle '{event.roles[role_index]}' angemeldet.")
                else:
                    try:
                        role_index = int(content) - 1
                        if role_index in range(len(event.roles)):
                            event.participants[message.author.id] = event.roles[role_index]
                            await thread.send(f"{message.author.mention} hat sich für die Rolle '{event.roles[role_index]}' angemeldet.")
                        else:
                            await thread.send(f"{message.author.mention}, diese Rolle existiert nicht.")
                    except ValueError:
                        await thread.send(f"{message.author.mention}, bitte gib eine gültige Zahl oder '-' zum Abmelden ein.")
            except Exception as e:
                await thread.send(f"Ein Fehler ist aufgetreten: {str(e)}")

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
        await interaction.response.send_message("Ungültiges Datum oder Zeitformat! Bitte verwende DDMMYYYY für das Datum und HHMM für die Zeit.", ephemeral=True)
        return

    formatted_date = parsed_date.strftime("%d.%m.%Y")
    formatted_time = parsed_time.strftime("%H:%M")

    modal = MyModal(title, formatted_date, formatted_time)
    await interaction.response.send_modal(modal)

@bot.tree.command(name="list", description="List all events")
async def list_events(interaction: discord.Interaction):
    await interaction.response.send_message("Hier sind die aktuellen Events: ...", ephemeral=True)

@bot.tree.command(name="propose", description="Propose a new role")
async def propose_role(interaction: discord.Interaction, role_name: str):
    await interaction.response.send_message(f"Rolle '{role_name}' vorgeschlagen!", ephemeral=True)

bot.run(DISCORD_TOKEN)