#!/usr/bin/env python3
# coding=utf-8
import asyncio, re, socket, binascii, logging, threading, time, json, os, aiohttp, discord

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HotlineClient:
    def __init__(self, config, bot):
        self.host, self.port = config['hotline_host'], config['hotline_port']
        self.bot = bot
        self.socket, self.connected = None, False
        self.msg_cache = set()

    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port))
            
            # 1. TRTP Handshake
            self.socket.send(bytes.fromhex("54525450484F544C00010002"))
            
            # 2. Simplified Login (0x6b) - Static Guest Hex
            login = bytes.fromhex("0000006B00000001000000000000001300000013000200660007446973636F72640068000207D00000012C00000002000000000000000200000002000000000065000000030000000000000002000000020000")
            self.socket.send(login)
            
            self.socket.setblocking(False)
            self.connected = True
            logger.info("✅ Hotline Connected (Guest Mode)")
            return True
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")
            return False

    def send_chat(self, message):
        if not self.connected: return
        try:
            # Basic sanitization for Hotline's ASCII-only chat
            clean_text = "".join(c for c in message if 32 <= ord(c) <= 126)
            self.msg_cache.add(clean_text)
            if len(self.msg_cache) > 50: self.msg_cache.clear()
            
            msg_bytes = clean_text.encode("utf-8")
            pkt = binascii.unhexlify("00000069000000FF00000000") 
            m_len = (len(msg_bytes) + 6).to_bytes(4, "big")
            pkt += m_len + m_len + binascii.unhexlify("00010065") + len(msg_bytes).to_bytes(2, "big") + msg_bytes
            self.socket.send(pkt)
        except: pass

    def listen(self):
        while self.connected:
            try:
                time.sleep(0.1)
                try:
                    data = self.socket.recv(16384)
                except BlockingIOError: continue
                
                if not data: break
                hex_d = data.hex()

                if self.bot.config.get("debug_mode", False) and len(hex_d) > 20:
                    logger.info(f"DEBUG HEX: {hex_d}")

                # Chat parser (0x6a)
                if "0000006a" in hex_d:
                    pos = hex_d.find("0000006a") // 2
                    raw = data[pos+20:].decode('utf-8', errors='ignore').strip()
                    if ":" in raw:
                        user = raw.split(":", 1)[0].strip().split()[-1]
                        msg = raw.split(":", 1)[1].strip()
                        
                        is_admin = user.lower() in [a.lower() for a in self.bot.config.get("manual_admins", [])]
                        
                        if user.lower() != "discord" and msg not in self.msg_cache:
                            asyncio.run_coroutine_threadsafe(self.bot.send_to_discord(user, msg, is_admin), self.bot.loop)
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

    async def on_ready(self):
        print(f"--- BRIDGE ONLINE ---\nUser: {self.user}")
        threading.Thread(target=self.hotline_worker, daemon=True).start()

    def hotline_worker(self):
        while True:
            try:
                if not self.hl.connected:
                    if self.hl.connect():
                        self.hl.listen()
            except Exception as e:
                logger.error(f"Worker Error: {e}")
            time.sleep(10)

    async def on_message(self, message):
        if message.author == self.user or message.webhook_id: return
        if message.channel.id != self.config['discord_channel_id']: return
        self.hl.send_chat(f"{message.author.display_name}: {message.content}")

    async def send_to_discord(self, user, msg, is_admin=False):
        # 1. Filter restricted words
        for word in self.config.get('filtered_words', []):
            msg = re.compile(re.escape(word), re.IGNORECASE).sub("[filtered]", msg)
        
        # 2. Fetch style settings
        a_emoji = self.config.get('admin_emoji', "🛡️")
        u_emoji = self.config.get('user_emoji', "🌍")
        
        if is_admin:
            name_prefix = f"{a_emoji} " if self.config.get('show_admins', True) else ""
            c_prefix = self.config.get('admin_prefix', "")
            c_suffix = self.config.get('admin_suffix', "")
        else:
            name_prefix = f"{u_emoji} " if u_emoji else ""
            c_prefix = self.config.get('user_prefix', "")
            c_suffix = self.config.get('user_suffix', "")

        # 3. Format plain text body
        display_name = f"{name_prefix}{user}"
        formatted_content = f"{c_prefix}{msg}{c_suffix}"

        # 4. Handle Avatar
        avatar = str(self.user.display_avatar.url)
        chan = self.get_channel(self.config['discord_channel_id'])
        if chan:
            match = discord.utils.find(lambda m: m.display_name.lower() == user.lower() or m.name.lower() == user.lower(), chan.guild.members)
            if match: avatar = str(match.display_avatar.url)
            
        # 5. Send payload to Webhook
        payload = {
            "username": display_name,
            "avatar_url": avatar,
            "content": formatted_content
        }

        async with aiohttp.ClientSession() as sess:
            await sess.post(self.config['discord_webhook_url'], json=payload)

if __name__ == "__main__":
    try:
        with open("config.json", 'r', encoding="utf-8") as f: 
            config = json.load(f)
        bot = DiscordBot(config)
        bot.run(config['discord_token'])
    except Exception as e:
        print(f"CRITICAL STARTUP ERROR: {e}")
