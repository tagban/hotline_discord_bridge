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
            # Handshake (TRTPHOTL)
            self.socket.send(bytes.fromhex("54525450484F544C00010002"))
            # Login Transaction (0x6b)
            login = bytes.fromhex("0000006B00000001000000000000001300000013000200660007446973636F72640068000207D00000012C00000002000000000000000200000002000000000065000000030000000000000002000000020000")
            self.socket.send(login)
            time.sleep(1)
            self.connected = True
            logger.info("✅ Hotline Connected")
            return True
        except Exception as e:
            logger.error(f"❌ Connection Error: {e}")
            return False

    def send_chat(self, message):
        if not self.connected: return
        try:
            # Clean and cache to prevent echos
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
                data = self.socket.recv(16384)
                if not data: break
                hex_d = data.hex()
                
                # Chat Packet Marker (0000006a)
                if "0000006a" in hex_d:
                    pos = hex_d.find("0000006a") // 2
                    raw = data[pos+20:].decode('utf-8', errors='ignore').strip()
                    if ":" in raw:
                        user = raw.split(":", 1)[0].strip().split()[-1]
                        msg_raw = raw.split(":", 1)[1].strip()
                        # Extract only printable ASCII
                        msg_match = re.match(r"^([ -~]+)", msg_raw)
                        msg = msg_match.group(1).strip() if msg_match else ""
                        
                        # --- FILTERS ---
                        # 1. User is not 'Discord'
                        # 2. Message is not in our recent sent cache
                        # 3. Message doesn't start with ! (Ignoring command echos)
                        if user.lower() != "discord" and not msg.startswith("!") and msg not in self.msg_cache:
                            asyncio.run_coroutine_threadsafe(self.bot.send_to_discord(user, msg), self.bot.loop)
            except: continue
        self.connected = False

class DiscordBot(discord.Client):
    def __init__(self, config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True # Required for Icon Matching
        super().__init__(intents=intents)
        self.config = config
        self.hl = HotlineClient(config, self)

    async def on_ready(self):
        print(f"--- BRIDGE ONLINE ---\nUser: {self.user}")
        threading.Thread(target=self.hotline_worker, daemon=True).start()

    def hotline_worker(self):
        while True:
            if not self.hl.connected: 
                if self.hl.connect():
                    self.hl.listen()
            time.sleep(10)

    async def on_message(self, message):
        # Prevent self-relay and webhook echos
        if message.author == self.user or message.webhook_id: return
        # Limit to target channel
        if message.channel.id != self.config['discord_channel_id']: return
        # Ignore commands
        if message.content.startswith('!'): return

        self.hl.send_chat(f"{message.author.display_name}: {message.content}")

    async def send_to_discord(self, user, msg):
        # Default: Use the Bot's own avatar as fallback
        avatar = str(self.user.display_avatar.url)
        
        # Search for matching Discord user to steal their icon
        chan = self.get_channel(self.config['discord_channel_id'])
        if chan:
            match = discord.utils.find(lambda m: m.display_name.lower() == user.lower() or m.name.lower() == user.lower(), chan.guild.members)
            if match:
                avatar = str(match.display_avatar.url)

        async with aiohttp.ClientSession() as sess:
            payload = {
                "username": user, 
                "content": msg, 
                "avatar_url": avatar
            }
            await sess.post(self.config['discord_webhook_url'], json=payload)

if __name__ == "__main__":
    with open("config.json", 'r') as f: config = json.load(f)
    bot = DiscordBot(config)
    bot.run(config['discord_token'])
