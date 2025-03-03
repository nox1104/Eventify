import discord
from discord import app_commands
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
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
    def __init__(self):
        super().__init__()
        
        # Info block for the creator
        self.info = discord.ui.TextInput(label="Note", style=discord.TextStyle.paragraph, 
                                          placeholder="Please fill in all fields to create an event. "
                                                      "The date should be in the format YYYY-MM-DD and the time in the format HH:MM. "
                                                      "Roles should be entered separated by line breaks.",
                                          required=False)
        self.add_item(self.info)

        self.title_input = discord.ui.TextInput(label="Title")
        self.date_input = discord.ui.TextInput(label="Date (YYYY-MM-DD)")
        self.time_input = discord.ui.TextInput(label="Time (HH:MM)")
        self.description_input = discord.ui.TextInput(label="Description")
        self.roles_input = discord.ui.TextInput(label="Roles (separated by line breaks)")

        self.add_item(self.title_input)
        self.add_item(self.date_input)
        self.add_item(self.time_input)
        self.add_item(self.description_input)
        self.add_item(self.roles_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Create event
        event = Event(
            title=self.title_input.value,
            date=self.date_input.value,
            time=self.time_input.value,
            description=self.description_input.value,
            roles=[role.strip() for role in self.roles_input.value.splitlines()]  # Split by line breaks
        )

        # Send event information to the defined channel
        channel = interaction.guild.get_channel(CHANNEL_ID_EVENT)
        event_message = f"**Event:** {event.title}\n**Date:** {event.date}\n**Time:** {event.time}\n**Description:** {event.description}\n**Roles:** {', '.join(event.roles)}"
        event_post = await channel.send(event_message)

        # Create thread
        thread = await event_post.create_thread(name=event.title)

        # Role management in the thread
        await thread.send("React with a number to sign up for a role. Type '-' to unsubscribe.")

        # Participant management
        def check(message):
            return message.channel == thread and message.author != bot.user

        while True:
            try:
                message = await bot.wait_for('message', check=check)
                content = message.content.strip()

                if content.startswith('-'):
                    if content == '-':
                        # Unsubscribe without a number
                        if message.author.id in event.participants:
                            del event.participants[message.author.id]
                            await thread.send(f"{message.author.mention} has unsubscribed.")
                        else:
                            await thread.send(f"{message.author.mention}, you are not signed up for any role.")
                    else:
                        # Unsubscribe with a number
                        role_index = int(content[1:]) - 1
                        if role_index in range(len(event.roles)):
                            if message.author.id in event.participants and event.participants[message.author.id] == event.roles[role_index]:
                                del event.participants[message.author.id]
                                await thread.send(f"{message.author.mention} has unsubscribed from the role '{event.roles[role_index]}'.")
                            else:
                                await thread.send(f"{message.author.mention}, you are not signed up for the role '{event.roles[role_index]}'.")
                else:
                    # Sign up for a role
                    try:
                        role_index = int(content) - 1
                        if role_index in range(len(event.roles)):
                            event.participants[message.author.id] = event.roles[role_index]
                            await thread.send(f"{message.author.mention} has signed up for the role '{event.roles[role_index]}'.")
                        else:
                            await thread.send(f"{message.author.mention}, this role does not exist.")
                    except ValueError:
                        await thread.send(f"{message.author.mention}, please enter a valid number or '-' to unsubscribe.")

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))  # Synchronize only with the specified guild
        print("Slash commands synchronized!")

bot = MyBot()

@bot.tree.command(name="create", description="Start an event")
async def create_event(interaction: discord.Interaction):
    await interaction.response.send_modal(MyModal())

@bot.tree.command(name="list", description="List all events")
async def list_events(interaction: discord.Interaction):
    # Here you can add logic to retrieve and display the saved events
    await interaction.response.send_message("Here are the current events: ...", ephemeral=True)

@bot.tree.command(name="propose", description="Propose a new role")
async def propose_role(interaction: discord.Interaction, role_name: str):
    # Here you can add logic to propose a new role
    await interaction.response.send_message(f"Role '{role_name}' proposed!", ephemeral=True)

bot.run(TOKEN)
