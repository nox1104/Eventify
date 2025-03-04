import discord
from discord import app_commands
from dotenv import load_dotenv
import os

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))
CHANNEL_ID_EVENT = int(os.getenv("CHANNEL_ID_EVENT"))
CHANNEL_ID_EVENT_LISTING = int(os.getenv("CHANNEL_ID_EVENT_LISTING"))

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

        # Füge die Eingabefelder für Beschreibung und Rollen hinzu
        self.description_input = discord.ui.TextInput(label="Beschreibung", style=discord.TextStyle.paragraph, 
                                                      placeholder="Gib eine Beschreibung für das Event ein.", 
                                                      required=True)
        self.add_item(self.description_input)

        self.roles_input = discord.ui.TextInput(label="Rollen (getrennt durch Zeilenumbrüche)", 
                                                 style=discord.TextStyle.paragraph, 
                                                 placeholder="Gib die Rollen ein, die für das Event benötigt werden.", 
                                                 required=True)
        self.add_item(self.roles_input)

        # Speichere die übergebenen Werte
        self.title = title
        self.date = date
        self.time = time

    async def on_submit(self, interaction: discord.Interaction):
        # Extrahiere die Beschreibung und die Rollen
        description = self.description_input.value
        roles = [role.strip() for role in self.roles_input.value.splitlines()]  # Split by line breaks

        # Erstelle das Event
        event = Event(
            title=self.title,
            date=self.date,
            time=self.time,
            description=description,
            roles=roles
        )

        # Sende die Event-Informationen an den definierten Kanal
        channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
        event_message = f"**Event:** {event.title}\n**Date:** {event.date}\n**Time:** {event.time}\n**Description:** {event.description}\n**Roles:** {', '.join(event.roles)}"
        event_post = await channel.send(event_message)

        # Erstelle einen Thread
        thread = await event_post.create_thread(name=event.title)

        # Rollenverwaltung im Thread
        await thread.send("Reagiere mit einer Zahl, um dich für eine Rolle anzumelden. Tippe '-' um dich abzumelden.")

        # Teilnehmerverwaltung
        def check(message):
            return message.channel == thread and message.author != bot.user

        while True:
            try:
                message = await bot.wait_for('message', check=check)
                content = message.content.strip()

                if content.startswith('-'):
                    if content == '-':
                        # Abmelden ohne Nummer
                        if message.author.id in event.participants:
                            del event.participants[message.author.id]
                            await thread.send(f"{message.author.mention} hat sich abgemeldet.")
                        else:
                            await thread.send(f"{message.author.mention}, du bist für keine Rolle angemeldet.")
                    else:
                        # Abmelden mit einer Nummer
                        role_index = int(content[1:]) - 1
                        if role_index in range(len(event.roles)):
                            if message.author.id in event.participants and event.participants[message.author.id] == event.roles[role_index]:
                                del event.participants[message.author.id]
                                await thread.send(f"{message.author.mention} hat sich von der Rolle '{event.roles[role_index]}' abgemeldet.")
                            else:
                                await thread.send(f"{message.author.mention}, du bist nicht für die Rolle '{event.roles[role_index]}' angemeldet.")
                else:
                    # Anmelden für eine Rolle
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

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))  # Synchronisiere nur mit der angegebenen Gilde
        print("Slash commands synchronized!")

bot = MyBot()

@bot.tree.command(name="eventify", description="Start an event")
async def create_event(interaction: discord.Interaction, title: str, date: str, time: str):
    # Überprüfe das Format von Datum und Uhrzeit hier, falls nötig
    # Beispiel: if not is_valid_date(date) or not is_valid_time(time):
    #     await interaction.response.send_message("Bitte gib ein gültiges Datum und eine gültige Uhrzeit ein.", ephemeral=True)
    #     return

    # Erstelle das Modal für Beschreibung und Rollen
    modal = MyModal(title, date, time)
    await interaction.response.send_modal(modal)

@bot.tree.command(name="list", description="List all events")
async def list_events(interaction: discord.Interaction):
    # Hier kannst du Logik hinzufügen, um die gespeicherten Events abzurufen und anzuzeigen
    await interaction.response.send_message("Hier sind die aktuellen Events: ...", ephemeral=True)

@bot.tree.command(name="propose", description="Propose a new role")
async def propose_role(interaction: discord.Interaction, role_name: str):
    # Hier kannst du Logik hinzufügen, um eine neue Rolle vorzuschlagen
    await interaction.response.send_message(f"Rolle '{role_name}' vorgeschlagen!", ephemeral=True)

bot.run(DISCORD_TOKEN)
