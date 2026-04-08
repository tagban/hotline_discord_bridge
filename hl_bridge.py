#!/usr/bin/env python3
# coding=utf-8
import asyncio, re, socket, binascii, logging, threading, time, json, discord, aiomysql, aiohttp
from datetime import datetime
from aiohttp import web

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Emoji Translation Map - Using double-backslashes for escape safety
EMOJI_MAP = {
    "😀": ":D", "😄": ":D", "😁": ":D", "😅": ":P",
    "😂": "XD", "🤣": "XD", "🙂": ":)", "🙃": "(:",
    "😉": ";)", "😊": ":)", "😇": "o:)", "🥰": "<3",
    "😍": "<3", "🤩": ":O", "😘": ":*", "😗": ":*",
    "☺️": ":)", "😚": ":*", "😙": ":*", "😋": ":P",
    "😛": ":P", "😜": ";P", "🤪": "8P", "😝": "xP",
    "🤑": "$", "🤗": "\\o/", "🤭": ":X", "🤫": ":X",
    "🤔": ":?", "🤐": ":X", "🤨": "o.O", "😐": ":|",
    "😑": "-_-", "😶": ":|", "😏": ";)", "😒": ":/",
    "🙄": "o.O", "😬": ":S", "🤥": ":L", "😌": ":)",
    "😔": ":(", "😪": ":|", "😴": "zzZ", "😷": ":S",
    "🤒": ":S", "🤕": ":S", "🤢": ":S", "🤮": ":O",
    "🤧": ":S", "🥵": "!!", "🥶": "??", "🥴": "8S",
    "😵": "Xo", "🤯": ":O", "🤠": "8)", "🥳": "\\o/",
    "😎": "8)", "🤓": "B)", "🧐": "8.", "😕": ":/",
    "😟": ":(", "🙁": ":(", "😮": ":O", "😯": ":O",
    "😲": ":O", "😳": ":O", "🥺": ":(", "😦": ":O",
    "😧": ":O", "😨": ":O", "😰": ":S", "😥": ":(",
    "😢": ":(", "😭": "=(", "😱": ":O", "😖": ":S",
    "😣": ":S", "😞": ":(", "😓": ":(", "😩": "X(",
    "😫": "X(", "🥱": ":O", "😤": ">:(", "😡": ">:(",
    "😠": ">:(", "🤬": ":@", "😈": " >:) ", "👿": " >:( ",
    "💀": " [x] ", "💩": " (p) ", "👍": "(Y)", "👎": "(N)"
}

class DatabaseLogger:
    def __init__(self, config):
        self.config = config
        self.pool = None
        self.enabled = config.get('use_web_features', False)

    async def connect(self):
        if not self.enabled: return
        try:
            self.pool = await aiomysql.create_pool(
                host=self.config['mysql_host'], user=self.config['mysql_user'],
                password=self.config['mysql_password'], db=self.config['mysql_db'],
                autocommit=True
            )
            logger.info("✅ MySQL Connected")
        except Exception as e:
            logger.error(f"❌ MySQL Connection Error: {e}")
            self.enabled = False 

    async def update_presence(self, username, source, icon_id=128):
        if not self.enabled or not self.pool: return
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT icon_id FROM online_users WHERE username = %s", (username,))
                    row = await cur.fetchone()
                    if row and icon_id == 128 and row[0] != 128:
                        await cur.execute("UPDATE online_users SET last_seen=NOW(), source=%s WHERE username=%s", (source, username))
                    else:
                        await cur.execute("""INSERT INTO online_users (username, source, icon_id, last_seen) 
                                           VALUES (%s, %s, %s, NOW()) 
                                           ON DUPLICATE KEY UPDATE last_seen=NOW(), icon_id=%s, source=%s""", 
                                           (username, source, icon_id, icon_id, source))
        except Exception as e:
            logger.error(f"❌ DB Presence Update Error: {e}")

class HotlineClient:
    def __init__(self, config, bot):
        self.config = config
        self.bot = bot
        self.socket = None
        self.connected = False
        self.connect_time = 0
        self.user_icons = {} 

    def get_login_hex(self):
        nick = self.config.get('bridge_nickname', 'Relay')
        icon_id = int(self.config.get('hotline_icon', 128))
        nick_bytes = nick.encode('ascii', errors='ignore')
        f_name = binascii.unhexlify("0066") + len(nick_bytes).to_bytes(2, 'big') + nick_bytes
        f_icon = binascii.unhexlify("00680002") + icon_id.to_bytes(2, 'big')
        field_data = f_name + f_icon
        header = binascii.unhexlify("0000006B0000000100000000")
        total_len = (len(field_data) + 2).to_bytes(4, 'big') 
        field_count = (2).to_bytes(2, 'big')
        return header + total_len + total_len + field_count + field_data

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            self.socket.settimeout(120)
            self.socket.connect((self.config['hotline_host'], self.config['hotline_port']))
            self.socket.send(bytes.fromhex("54525450484F544C00010002"))
            time.sleep(1.5) 
            self.socket.send(self.get_login_hex())
            self.connected = True
            self.connect_time = time.time()
            logger.info(f"✅ Hotline Connected as {self.config.get('bridge_nickname')}")
            return True
        except Exception as e:
            logger.error(f"❌ Hotline Connection: {e}")
            return False

    def send_chat(self, message):
        if not self.connected or not self.socket: return
        try:
            msg_bytes = message.encode("ascii", errors='ignore')
            m_len = (len(msg_bytes) + 6).to_bytes(4, 'big')
            pkt = binascii.unhexlify("00000069000000FF00000000") + m_len + m_len + binascii.unhexlify("00010065") + len(msg_bytes).to_bytes(2, 'big') + msg_bytes
            self.socket.send(pkt)
        except: self.connected = False

    def listen(self):
        nick = self.config.get('bridge_nickname', 'Relay').lower()
        while self.connected:
            try:
                data = self.socket.recv(65535)
                if not data: break
                if self.config.get('use_hotline_icons', True):
                    if b'\x00\x66' in data and b'\x00\x68\x00\x02' in data:
                        try:
                            n_idx = data.find(b'\x00\x66') + 2
                            n_len = int.from_bytes(data[n_idx:n_idx+2], 'big')
                            f_name = data[n_idx+2:n_idx+2+n_len].decode('ascii', errors='ignore').strip()
                            i_idx = data.rfind(b'\x00\x68\x00\x02') + 4
                            f_icon = int.from_bytes(data[i_idx:i_idx+2], 'big')
                            if f_name and f_icon > 0:
                                self.user_icons[f_name] = f_icon
                                if self.bot.db.enabled:
                                    asyncio.run_coroutine_threadsafe(self.bot.db.update_presence(f_name, "Hotline", f_icon), self.bot.loop)
                        except: pass

                if time.time() - self.connect_time > 4 and b'\x00\x65' in data:
                    try:
                        parts = data.split(b'\x00\x65', 1)[1]
                        clean = "".join([chr(b) if (31 < b < 127) else " " for b in parts])
                        if ":" in clean:
                            user = clean.split(":", 1)[0].strip().split()[-1]
                            msg = clean.split(":", 1)[1].strip()
                            msg = re.split(r'\s{2,}', msg)[0] 
                            if user.lower() not in [nick, "discord"] and "---" not in clean:
                                current_icon = self.user_icons.get(user, 128)
                                asyncio.run_coroutine_threadsafe(self.bot.sync_from_remote("Hotline", user, msg, current_icon), self.bot.loop)
                    except: pass
            except socket.timeout: continue
            except: break
        self.connected = False

class DiscordBot(discord.Client):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True 
        super().__init__(intents=intents)
        self.config = config
        self.hl = HotlineClient(config, self)
        self.db = DatabaseLogger(config)

    async def setup_hook(self):
        if self.config.get('use_web_features', False):
            app = web.Application()
            app.router.add_post('/webhook', self.handle_web_chat)
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, '0.0.0.0', self.config.get('webhook_port', 54230)).start()

    async def handle_web_chat(self, request):
        if request.headers.get('X-Bridge-Key') != self.config.get('web_secret_key'): return web.Response(status=403)
        data = await request.json()
        await self.sync_from_remote("Web", data.get('author', 'Web'), data.get('message', ''), 131)
        return web.Response(text="OK")

    async def on_ready(self):
        logger.info(f"--- BRIDGE OPERATIONAL: {self.user} ---")
        if self.db.enabled: await self.db.connect()
        threading.Thread(target=self.hotline_worker, daemon=True).start()

    def hotline_worker(self):
        while True:
            if not self.hl.connected:
                if self.hl.connect(): self.hl.listen()
            time.sleep(10)

    async def on_message(self, message):
        if message.author == self.user or message.webhook_id or message.channel.id != self.config['discord_channel_id']: return
        content = message.content
        for att in message.attachments: content += f" {att.url}"
        if content.strip(): 
            await self.sync_from_remote("Discord", message.author.display_name, content, 134)

    async def sync_from_remote(self, source, author, msg, icon_id=128):
        if source != "Discord":
            if "@everyone" in msg.lower() or "@here" in msg.lower():
                msg = msg.replace("@everyone", "everyone").replace("@here", "here")
        
        filtered = self.config.get('filtered_words', [])
        if any(t.lower() in msg.lower() for t in filtered): return

        final_msg = msg

        if source == "Hotline" and "@" in final_msg:
            guild = self.get_guild(int(self.config.get('discord_guild_id', 0)))
            if guild:
                for member in guild.members:
                    mention_tag = f"@{member.display_name}"
                    if mention_tag in final_msg:
                        final_msg = final_msg.replace(mention_tag, member.mention)

        if source == "Discord":
            final_msg = re.sub(r'<(a?):([a-zA-Z0-9_]+):([0-9]+)>', 
                               lambda m: f"https://cdn.discordapp.com/emojis/{m.group(3)}.{'gif' if m.group(1) else 'webp'}?size=48", 
                               final_msg)
            for char, ascii_art in EMOJI_MAP.items():
                final_msg = final_msg.replace(char, ascii_art)

        if self.db.enabled:
            await self.db.update_presence(author, source, icon_id)
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    sql = "INSERT INTO chat_logs (source, author, timestamp, message, processed) VALUES (%s, %s, NOW(), %s, 0)"
                    try: await cur.execute(sql, (source, author, final_msg))
                    except Exception as e: logger.error(f"❌ SQL Error: {e}")

        if source != "Discord":
            payload = {"username": f"{author} [{source}]", "content": final_msg}
            if self.config.get('use_hotline_icons', True):
                relay_icon = self.hl.user_icons.get(author, icon_id)
                base_url = self.config.get('icon_url_base', 'http://hlwiki.com/ik0ns/')
                payload["avatar_url"] = f"{base_url}{relay_icon}.png"
            
            async with aiohttp.ClientSession() as sess:
                await sess.post(self.config['discord_webhook_url'], json=payload)
        
        if source != "Hotline":
            hotline_safe = final_msg.encode("ascii", "ignore").decode("ascii")
            if hotline_safe.strip():
                self.hl.send_chat(f"{source} | {author}: {hotline_safe}")

if __name__ == "__main__":
    with open("config.json", 'r', encoding="utf-8") as f: config = json.load(f)
    bot = DiscordBot(config)
    bot.run(config['discord_token'])
