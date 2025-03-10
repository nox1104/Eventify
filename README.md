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

### Participant Management
- **Self-Registration** – Users can sign up for roles using simple numbers
- **Role Comments** – Add comments to role registrations
- **Role Proposals** – Users can suggest new roles using `/propose`
- **Admin Commands** – Event creators can manage participants with `/add` and `/remove`

### Communication
- **Automatic Thread Creation** – Each event gets its own thread for discussions
- **Event Listing** – Overview of upcoming events with clickable links
- **Reminder System** – Send reminders to all participants using `/remind`
- **PN Notifications** – Participants receive private messages about role assignments and removals

### Channel Management
- **Auto-Cleanup** – Automatically removes:
  - Past event posts
  - Event threads (15 minutes after event start)
  - System messages and notifications
  - Old event listings
- **14-Day Limit** – Events should be created maximum 13 days in advance due to Discord's message deletion restrictions

![Eventify](https://github.com/nox1104/Eventify/blob/main/pictures/Eventify.png?raw=true)