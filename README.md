🛠️ Phase 1: Creating the Application
Log In: Go to the Discord Developer Portal and log in with your Discord account.
New Application: Click the "New Application" button in the top right.
Name It: Give your bot a name (e.g., BigRedH-Bridge) and agree to the terms.
Save Changes: You are now in the General Information tab. You can upload an icon here that will represent the bot in Discord.

🤖 Phase 2: Configuring the Bot User
Navigate to "Bot": On the left-hand sidebar, click the Bot tab.
Reset Token: Click "Reset Token" (or "Copy Token" if it's the first time) to generate your Bot Token.
⚠️ CRITICAL: This token is your bot's password. Copy it now and save it. You will paste this into your config.json as the discord_token. Never share this token.
Privileged Gateway Intents: Scroll down to the "Privileged Gateway Intents" section. You MUST toggle these to ON:
Presence Intent: (Helps track user status).
Server Members Intent: (Helps the bot see who is in the channel).
Message Content Intent: (MANDATORY). Without this, your bot can see that a message was sent, but it cannot read the text to relay it to Hotline.

🔗 Phase 3: Inviting the Bot to Your Server
OAuth2 URL Generator: On the left sidebar, go to OAuth2 -> URL Generator.
Select Scopes: Check the box for bot.
Select Permissions: A new list will appear. Select the following:
Read Messages/View Channels
Send Messages
Embed Links
Attach Files
Read Message History
Use External Emojis (Important for your custom emoji relay!)
Copy the Link: At the bottom, a URL will be generated. Copy this URL and paste it into your browser.
Authorize: Select the server you want the bridge to live in and click Authorize.

🪝 Phase 4: Setting Up the Webhook
Discord Webhooks are used by the bot to "impersonate" Hotline users (so they get their own name and icon).
Open Discord: Go to the channel where you want the bridge messages to appear.
Channel Settings: Click the Edit Channel (cog icon) next to the channel name.
Integrations: Go to Integrations -> Webhooks.
New Webhook: Click "Create Webhook".
Copy URL: Click on the new webhook and click "Copy Webhook URL".
This goes into your config.json (Python) as discord_webhook_url.

📂 Phase 5: Connecting the Python Script
Open your config.json file and ensure the IDs you gathered match up:

JSON
{
    "discord_token": "PASTE_TOKEN_FROM_PHASE_2",
    "discord_webhook_url": "PASTE_URL_FROM_PHASE_4",
    "discord_channel_id": 123456789012345678, 
    "bridge_nickname": "Relay",
    "hotline_host": "server.bigredh.com",
    "hotline_port": 5500
}
Pro-Tip: To get your discord_channel_id, enable Developer Mode in Discord (User Settings -> Advanced -> Developer Mode), then right-click your channel and select "Copy Channel ID".
