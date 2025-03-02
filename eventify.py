import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv

# Lade Umgebungsvariablen
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Event Modal Popup
class EventModal(discord.ui.Modal, title="Event Details"):
    def __init__(self, event_title: str):
        super().__init__()
        self.event_title = event_title

    event_date = discord.ui.TextInput(
        label="Datum (DD-MM-YYYY)",
        style=discord.TextStyle.short,
        placeholder="z.B. 31-12-2025"
    )
    event_time = discord.ui.TextInput(
        label="Uhrzeit (HH:MM)",
        style=discord.TextStyle.short,
        placeholder="z.B. 18:30"
    )
    description = discord.ui.TextInput(
        label="Kurze Beschreibung",
        style=discord.TextStyle.long,
        placeholder="Beschreibe dein Event kurz..."
    )
    roles = discord.ui.TextInput(
        label="Verfügbare Rollen (jede Rolle in einer neuen Zeile)",
        style=discord.TextStyle.long,
        required=False,
        placeholder="Beispiel:\n1: Tankealer DPS\n2: Range DPS"
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            event_date_obj = datetime.strptime(self.event_date.value, "%d-%m-%Y")
        except ValueError:
            await interaction.response.send_message("Das Datum muss im Format DD-MM-YYYY eingegeben werden.", ephemeral=True)
            return

        # Event Embed
        embed = discord.Embed(title=self.event_title, description=self.description.value, color=0x00ff00)
        embed.add_field(name="Datum", value=self.event_date.value, inline=True)
        embed.add_field(name="Uhrzeit", value=self.event_time.value, inline=True)
        
        roles_text = self.roles.value if self.roles.value else "Keine Rollen angegeben"
        embed.add_field(name="Verfügbare Rollen", value=roles_text, inline=False)

        events_channel = discord.utils.get(interaction.guild.text_channels, name='events')
        if events_channel:
            post_message = await events_channel.send(embed=embed)
            thread = await post_message.create_thread(name=f"{self.event_title} - Diskussion")
        else:
            await interaction.response.send_message("Kein 'events'-Channel gefunden.", ephemeral=True)
            return

        await interaction.response.send_message("Event wurde erstellt!", ephemeral=True)

# EventifyBot Klasse
class EventifyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Befehl zur Slash-Command-Registrierung
        self.tree.add_command(create_event)
        try:
            await self.tree.sync()  # Synchronisieren der Slash-Befehle
            print("Slash-Commands erfolgreich synchronisiert!")
        except Exception as e:
            print(f"Fehler bei der Synchronisierung der Slash-Commands: {e}")
        await super().setup_hook()

bot = EventifyBot()

# Der Create Event Befehl
@app_commands.command(name="create_event", description="Erstelle ein neues Event")
async def create_event(interaction: discord.Interaction, title: str):
    # EventModal öffnen
    modal = EventModal(title)
    await interaction.response.send_modal(modal)

bot.run(TOKEN)
