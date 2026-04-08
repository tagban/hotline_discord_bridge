This is the complete documentation for the **BigRedH Hotline-Discord Bridge**, formatted for a GitHub `README.md` file.

---

```markdown
# BigRedH Hotline-Discord Bridge

A robust, state-of-the-art bridge connecting retro Hotline Communications servers with modern Discord channels. This tool features deep packet scanning for icons, a real-time web monitor, and smart persistence for user identities.

## 🚀 Features
* **Bi-directional Chat:** Real-time relay between Hotline, Discord, and Web.
* **Icon Persistence:** Automatically caches and maps Hotline Icon IDs to Discord avatars.
* **Web Monitor:** Optional PHP-based live stream and user list for websites.
* **Stability:** Integrated socket keep-alive and 120-second idle timeouts.
* **Spam Filtering:** Built-in protection against login "ghost" messages and filtered words.

---

## 🛠️ Phase 1: Database Setup (Optional)
If you intend to use the **Web Monitor** features (`use_web_features: true`), run the following script in your MySQL manager (e.g., phpMyAdmin) to initialize your tables.

```sql
-- 1. Create the Chat Logs table
CREATE TABLE IF NOT EXISTS `chat_logs` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `source` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `author` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `timestamp` datetime DEFAULT CURRENT_TIMESTAMP,
  `message` text COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `processed` tinyint(1) DEFAULT 0,
  PRIMARY KEY (`id`),
  KEY `idx_timestamp` (`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Create the Online Users table
CREATE TABLE IF NOT EXISTS `online_users` (
  `username` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL,
  `source` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL,
  `icon_id` int(11) DEFAULT 128,
  `last_seen` datetime DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`username`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

## 🤖 Phase 2: Discord Configuration
1. **Create Application:** Visit the [Discord Developer Portal](https://discord.com/developers/applications) and create a New Application.
2. **Bot Token:** Go to the **Bot** tab, click **Reset Token**, and save the string.
3. **Privileged Intents:** You **MUST** scroll down to the "Privileged Gateway Intents" section and toggle **Message Content Intent** to **ON**.
4. **Invite Bot:** Under **OAuth2 -> URL Generator**, select `bot` and `Administrator` (or specific permissions for Webhooks/Messages) and use the link to invite the bot to your server.
5. **Webhook:** In your Discord Channel Settings, go to **Integrations -> Webhooks**, create a new one, and copy the **Webhook URL**.

---

## 📂 Phase 3: Installation & Configuration

1. **Requirements:**
   ```bash
   pip install discord.py aiomysql aiohttp
   ```
2. **Setup `config.json`:**
   Create a file named `config.json` in your bot directory:

```json
{
    "discord_token": "INSERT_BOT_TOKEN_HERE",
    "discord_channel_id": 0,
    "discord_guild_id": 0,
    "discord_webhook_url": "[https://discord.com/api/webhooks/](https://discord.com/api/webhooks/)...",
    "discord_status": "online",
    "discord_activity_type": "watching",
    "discord_activity_name": "hotline://your-server-address",

    "hotline_host": "0.0.0.0",
    "hotline_port": 5500,
    "bridge_nickname": "Relay",
    "use_hotline_icons": true,
    "icon_url_base": "[http://hlwiki.com/ik0ns/](http://hlwiki.com/ik0ns/)",

    "use_web_features": false,
    "mysql_host": "localhost",
    "mysql_user": "root",
    "mysql_password": "",
    "mysql_db": "bridge_db",
    "webhook_port": 54230,
    "web_secret_key": "RANDOM_SECRET_STRING",

    "filtered_words": ["@here", "@everyone"],
    "manual_admins": ["AdminName"]
}
```

---

## 🖥️ Phase 4: Web Monitor Setup (Optional)
1. Upload `index.php`, `fetch_chat.php`, `fetch_users.php`, and `config.php` to your web server.
2. Configure `config.php` with your MySQL credentials.
3. The web interface will automatically poll the database and display the chat using a "cache-buster" to ensure real-time updates.

---

## 🚦 Phase 5: Running the Bridge
Simply execute the Python script:
```bash
python bridge_bot.py
```
Check the console for connection confirmations:
* `✅ MySQL Connected` (If enabled)
* `✅ Hotline Connected`
* `--- BRIDGE OPERATIONAL ---`

Here is a clean, well-commented **`config.php`** file designed for a new user. It includes all the necessary logic to connect to the database and bridge the communication between the web interface and the Python bot.

---

### `config.php`

```php
<?php
/**
 * BigRedH Bridge - Web Configuration File
 * --------------------------------------
 * This file handles the database connection and global settings
 * for the Web Monitor interface.
 */

$web_config = [
    // --- DATABASE SETTINGS ---
    // The web interface reads chat logs and user lists from this database.
    'db_host'         => 'localhost',
    'db_user'         => 'DATABASE_USER',
    'db_pass'         => 'DATABASE_PASSWORD',
    'db_name'         => 'DATABASE_NAME',
    
    // --- WEBSITE IDENTITY ---
    'site_name'       => 'BigRedH - LIVE',
    'site_url'        => 'https://your-website.com/',
    'hotline_addr'    => 'your-hotline-server.com',
    'discord_invite'  => 'https://discord.gg/yourlink',

    // --- BOT CONNECTIVITY ---
    // This allows the website to talk back to the Python bot.
    // 'bot_url' should point to the IP/Port where bridge_bot.py is running.
    'bot_url'         => 'http://localhost:54230/webhook',
    'web_secret_key'  => 'PASTE_YOUR_WEB_SECRET_KEY_FROM_BOT_CONFIG_HERE',

    // --- UI SETTINGS ---
    'items_to_load'   => 100, // Number of chat messages to show
    'refresh_rate'    => 3000 // How often to poll for new data (in milliseconds)
];

// Map local config to global variable for the fetch scripts
$config = $web_config;

// Establish Database Connection
$conn = new mysqli(
    $config['db_host'], 
    $config['db_user'], 
    $config['db_pass'], 
    $config['db_name']
);

// Check for connection errors
if ($conn->connect_error) {
    header('HTTP/1.1 500 Internal Server Error');
    die("CRITICAL_FAILURE // DB_CONNECTION_LOST: " . $conn->connect_error);
}

// Set charset to utf8mb4 for full emoji and retro character support
$conn->set_charset("utf8mb4");

/**
 * PRO-TIP: 
 * Ensure the database user has SELECT, INSERT, and DELETE privileges 
 * on the chat_logs and online_users tables.
 */
?>
```

---

### 📋 Setup Instructions for the Web Side:

To get the website running, the user just needs to follow these three steps:

1.  **Upload Files:** Upload `index.php`, `fetch_chat.php`, `fetch_users.php`, `style.css`, and this `config.php` to their web server.
2.  **Configure Database:** Fill in the `db_` placeholders in `config.php`.
3.  **Sync Keys:** Ensure the `web_secret_key` in `config.php` matches the one in the bot's `config.json`. This acts as the "handshake" between the web server and the Python script.
---

## ⚖️ License
Distributed under the MIT License. See `LICENSE` for more information.
```
