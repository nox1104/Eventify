# Eventify – Your Simple Discord Event Manager 

Eventify is a lightweight and user-friendly Discord bot designed to simplify event planning within your server. With intuitive **slash commands** and interactive **modals** for the description and roles, Eventify allows users to quickly create, manage, and join events without any hassle.  

## Features  

### Event Creation and Management
- **Easy Event Creation** – Use `/eventify` to set up an event with title, date, time, description, and roles
- **Direct Creation** – Create events in a single command with all parameters, using `\n` for line breaks
- **Modal Alternative** – Optionally use an interactive form for description and roles
- **Role Mentions** – Optionally mention specific Discord roles when creating an event
- **Section Headers** – Group roles using headers in parentheses, e.g., "(Core)", "(DPS)"
- **FillALL System** – Special role for flexible participants who can fill multiple positions
- **Participant-Only Mode** – Create events with a simple participant list using `roles: none`
- **Event Cancellation** – Cancel events with `/cancel` and automatically notify all participants
- **Image Support** – Add an image to your event using the `image_url` parameter
- **Intelligent Role Counter** – Automatic tracking of filled/total role slots with smart FillALL handling

### Participant Management
- **Self-Registration** – Users can sign up for roles using simple numbers
- **Role Comments** – Add comments to role registrations, truncated to 30 characters for clarity
- **Role Proposals** – Users can suggest new roles using `/propose`
- **Admin Commands** – Event creators can manage participants with `/add` and `/remove`

### Communication
- **Automatic Thread Creation** – Each event gets its own thread for discussions
- **Event Listing** – Overview of upcoming events with clickable links
- **Reminder System** – Send reminders to all participants using `/remind`
- **PN Notifications** – Participants receive private messages about role assignments and removals
- **Cancellation Notifications** – All participants are automatically notified when an event is canceled

### Channel Management
- **Automatic Cleanup** – Automatically removes:
  - after 30 minutes:
    - Event threads
  - after 12 days:
    - System messages and notifications 
    - Old event listings
    - Regular messages older than 12 days
  - Creates daily backups of the event file and keeps the latest 42 backups

### Security Features
- **Server Authorization** – Bot automatically leaves unauthorized servers
- **Channel Restriction** – Cleanup operations only run in the designated event channel
- **Error Logging** – Comprehensive logging for troubleshooting
- **Permission Checking** – Bot verifies it has the necessary permissions before attempting actions

### Data Security
- The bot is designed for single-server operation to maintain data privacy
- Backups are stored locally and rotated (keeps the most recent 42 backups)
- Logs contain diagnostic information and are kept for troubleshooting

---

## Setup Instructions

### Required Folders
Create these folders in the bot's root directory:
- `./logs/` - For error and activity logs
- `./backups/` - For daily event data backups

### Environment Configuration
Create a `.env` file in the root directory with the following variables:
```
DISCORD_TOKEN=your_bot_token_here
AUTHORIZED_GUILD_ID=your_server_id_here
CHANNEL_ID_EVENT=your_event_channel_id_here
```

- **DISCORD_TOKEN**: Your Discord bot token from the Discord Developer Portal
- **AUTHORIZED_GUILD_ID**: ID of the Discord server where the bot is allowed to operate
- **CHANNEL_ID_EVENT**: ID of the channel where events should be posted

For security, set the file permissions with `chmod 600 .env` on Unix-like systems.

### Discord Integration
When adding the bot to your server, restrict its channel access to only the channels it needs to operate in.

### Link (Scopes and Permissions)
https://discord.com/oauth2/authorize?client_id=1346542782189273129&permissions=328565255232&integration_type=0&scope=applications.commands+bot

#### OAuth2-Scopes
- bot
- applications.commands

#### Bot Permissions
- General Permissions
  - View Channels

- Text Permissions
  - Send Messages
  - Create Public Threads
  - Send Messages in Threads
  - Manage Messages
  - Manage Threads
  - Embed Links
  - Attach Files
  - Read Message History
  - Mention Everyone
  - Add Reactions
  - Use Slash Commands

- Required Intents 
  - message_content (Privileged Intent)

### Discord Channel Permissions
To restrict Eventify's channel access:
1. Go to Server Settings
2. Click on Integrations
3. Select Eventify
4. Under Channels, deselect "All channels"
5. Add the channel where Eventify should operate by clicking the "Add channel" button

### Set Eventify Cyan
1. Go to Server Settings
2. Navigate to Roles
3. Select the Eventify role
4. Click Display
5. Under Role Colour, select Custom Colour
6. Enter hex code: `#0dceda`

### Start eventify.py

![Eventify](https://github.com/nox1104/Eventify/blob/main/pictures/Eventify.png?raw=true)