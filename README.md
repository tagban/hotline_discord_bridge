# BigRedH Hotline-Discord Bridge

Relays one Hotline server's public chat and one Discord channel, both ways:

- **Hotline → Discord** through the channel's webhook, as the speaker (`Name [Hotline]`)
  with their Hotline icon as the picture (from the hlwiki icon set).
- **Discord → Hotline** as chat lines: `Discord | Name: message`.
- **Emoticons:** Discord's emoji become the old ASCII faces Hotline can show (😀 `:D`,
  😂 `XD`, 👍 `(Y)`); custom Discord emoji become image links; Hotline's faces show as
  emoji on Discord (`:)` 🙂). `@everyone` and `@here` never go through, and `@Name` from
  Hotline pings that Discord member.
- **Optional web monitor:** chat and who's online in MySQL, for the PHP pages in
  `website/`, which can also post into the chat.

It runs in Docker and stays up on its own:

- It speaks the Hotline protocol properly (`hotline.py`, the client from
  [HIM](https://github.com/tagban/him)): a real sign-on that accepts the agreement, whole
  transactions, and the user list with icons.
- It checks the Hotline connection every few minutes and reconnects when it drops,
  holding Discord's messages meanwhile.
- Nothing blocks Discord's connection, so its heartbeat never stalls. If Discord still
  isn't connected after ten minutes, the bridge exits and Docker starts it fresh.

## Setup

**Discord:**

1. In the [Developer Portal](https://discord.com/developers/applications), make an
   application.
2. Under **Bot**, reset and copy the token, and turn on **Message Content Intent** and
   **Server Members Intent**.
3. Invite the bot with permission to read and send messages in the channel.
4. In the channel's settings (**Integrations → Webhooks**), make a webhook and copy its URL.

**Config:** copy `config.example.json` to `config.json` and fill it in:

| Key | |
|---|---|
| `discord_token`, `discord_webhook_url` | From above. Secrets: `config.json` is ignored by git |
| `discord_channel_id`, `discord_guild_id` | Right-click → Copy ID (with Developer Mode on) |
| `discord_status`, `discord_activity_type`, `discord_activity_name` | The bot's presence, e.g. `watching` `hotline://your-server` |
| `hotline_host`, `hotline_port` | The Hotline server |
| `hotline_login`, `hotline_password` | An account there; empty joins as a guest |
| `bridge_nickname`, `hotline_icon` | Its name and icon in the Hotline user list |
| `use_hotline_icons`, `icon_url_base` | Speakers' Hotline icons as their Discord pictures |
| `translate_hotline_faces` | `:)` → 🙂 on the way to Discord |
| `filtered_words` | Lines containing any of these aren't relayed |
| `use_web_features`, `webhook_port`, `web_secret_key`, `mysql_*` | The web monitor (see below) |

Any key can also come from the environment, upper-cased (`DISCORD_TOKEN`, `HOTLINE_PASSWORD`, ...).

## Running it

On a server with Docker, as root:

```bash
curl -fsSL https://raw.githubusercontent.com/tagban/hotline_discord_bridge/main/deploy/vps-setup.sh -o /tmp/bridge-setup.sh
bash /tmp/bridge-setup.sh
```

It installs into `/opt/docker/hotline-discord-bridge`, and wants your `config.json` there
first (the first run puts the example there if there isn't one). Run it again any time to
update. Logs: `docker compose -f /opt/docker/hotline-discord-bridge/docker-compose.yml logs -f`.

Or anywhere with Python 3.10+:

```bash
pip install -r requirements.txt
python hl_bridge.py config.json
```

## Web monitor (optional)

Run `website/setup.sql` in MySQL, set `use_web_features` and the `mysql_*` keys, and put
`website/` on a PHP host (its `config.php` points at the same database). The page posts
visitors' chat to the bridge at `webhook_port` with `web_secret_key`. In Docker, publish
that port in `docker-compose.yml`.

## Tests

```bash
pip install pytest && python -m pytest
```

They run the Hotline side against HIM's test server (`HOTLINE_MOCK=/path/to/mock-server`,
built from the HIM repo with `cargo build -p hotline-im --features mock-server --bin mock-server`).
