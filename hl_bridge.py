#!/usr/bin/env python3
# coding=utf-8
import asyncio
import re
import socket
import binascii
import logging
import threading
import time
from typing import Optional
import aiohttp
import discord
from discord.ext import commands
import emoji

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
DISCORD_TOKEN = "INSERT_BOT_TOKEN_BETWEEN_QUOTES"  # Discord bot token string
DISCORD_CHANNEL_ID = 1325831976392986696  # Discord channel ID INT (Must be an integer)
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/ID1234567" # Webhook URL for dynamic sender names
HOTLINE_HOST = "127.0.0.1"
HOTLINE_PORT = 5500

# --- Emoji mapping ---
CATEGORY_MAP = {
    'Smileys & Emotion': ':)',
    'People & Body': '*person*',
    'Animals & Nature': '*animal*',
    'Food & Drink': '*food*',
    'Travel & Places': '*place*',
    'Activities': '*activity*',
    'Objects': '*object*',
    'Symbols': '*symbol*',
    'Flags': '*flag*'
}

EMOJI_MAP = {}
COMMON_FACES = {
    "😀": ":)", "😃": ":D", "😄": ":D", "😁": ":D", "😆": "XD", "😅": "XD",
    "😂": ":'D", "🤣": ":'D", "😊": ":)", "😇": "O:)", "🙂": ":)", "🙃": ":P",
    "😉": ";)", "😌": ":)", "😍": "<3", "😘": ":*", "😗": ":*", "😙": ":*",
    "😚": ":*", "😋": ":P", "😛": ":P", "😝": ":P", "😜": ";P", "🤪": ";P",
    "🤨": ":/", "🧐": ":/", "🤓": "B)", "😎": "8)", "🤩": "*star*",
    "🥳": "*party*", "😏": ":)", "😒": ":|", "😞": ":(", "😔": ":(", "😟": ":(",
    "😕": ":/", "🙁": ":(", "☹️": ":(", "😣": ":'(", "😖": ":'(", "😫": ":'(",
    "😩": ":'(", "🥺": ":'(", "😢": ":'(", "😭": ":'(", "😤": ">:(", "😠": ">:(",
    "😡": ">:(", "🤬": ">:(", "🤯": ":O", "😳": ":O", "🥵": ":O", "🥶": ":O",
    "😱": ":O", "😨": ":O", "😰": ":O", "😥": ":(", "😓": ":(", "🤗": ":)",
    "🤔": ":/", "🤭": ":)", "🤫": ":)", "🤥": ":/", "😶": ":|", "😐": ":|",
    "😑": ":|", "😬": ":S", "🙄": ":/", "😯": ":O", "😦": ":O", "😧": ":O",
    "😮": ":O", "😲": ":O", "🥱": ":|", "😴": "-_-", "🤤": ":P", "😪": ":|",
    "😵": "X_X", "🤐": ":|", "🥴": ":S", "🤢": ":S", "🤮": ":S", "🤧": ":S",
    "😷": ":S", "🤒": ":S", "🤕": ":S", "🤑": ":$", "🤠": ":)", "😈": "]:)",
    "👿": ">:)", "👹": ">:)", "👺": ">:)", "💀": "*skull*", "☠️": "*skull*",
    "👻": "*ghost*", "👽": "*alien*", "👾": "*alien*", "🤖": "*robot*", "💩": "*poop*",
    "😺": ":)", "😸": ":D", "😹": ":'D", "😻": "<3", "😼": ":)", "😽": ":*",
    "🙀": ":O", "😿": ":'(", "😾": ">:(", "👍": "(y)", "👎": "(n)", "👊": "*punch*",
    "✊": "*punch*", "🤛": "*punch*", "🤜": "*punch*", "👏": "*clap*", "🙌": "*yay*",
    "👐": "*hands*", "🤲": "*hands*", "🙏": "*pray*", "💪": "*muscle*",
    "💃": "*dance*", "🕺": "*dance*", "🧍": "*stand*", "🧎": "*kneel*",
    "💖": "<3", "💗": "<3", "💓": "<3", "💘": "<3", "💝": "<3", "💞": "<3",
    "✨": "*sparkle*", "🎉": "*party*", "🎊": "*party*", "🔥": "*fire*", "⭐": "*star*",
    "🌟": "*star*", "💫": "*sparkle*", "☀️": "*sun*", "🌙": "*moon*", "☁️": "*cloud*",
    "🌈": "*rainbow*", "⚡": "*zap*", "❄️": "*snow*", "💧": "*drop*", "🌊": "*wave*",
    # Add more as needed
}

for emj in emoji.EMOJI_DATA:
    if emj in COMMON_FACES:
        EMOJI_MAP[emj] = COMMON_FACES[emj]
    else:
        category = emoji.EMOJI_DATA[emj].get('category', '')
        EMOJI_MAP[emj] = CATEGORY_MAP.get(category, '*emoji*')

ASCII_TO_EMOJI = {v: k for k, v in EMOJI_MAP.items()}

def convert_emojis_to_ascii(text: str) -> str:
    for emj, ascii_eq in EMOJI_MAP.items():
        text = text.replace(emj, ascii_eq)
    return text

def convert_ascii_to_emojis(text: str) -> str:
    for ascii_eq, emj in ASCII_TO_EMOJI.items():
        pattern = rf'(?<!\w){re.escape(ascii_eq)}(?!\w)'
        text = re.sub(pattern, emj, text)
    return text

def sanitize_string(input_string):
    return ''.join(c for c in input_string if 32 <= ord(c) <= 126)

# --- Hotline Client ---
class HotlineClient:
    def __init__(self, host: str, port: int, discord_bot):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.discord_bot = discord_bot
        self.connected = False
        self.message_counter = 1
        self.running = False

    def connect(self):
        try:
            logger.info(f"Connecting to Hotline {self.host}:{self.port}...")
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.host, self.port))
            logger.info("TCP connection established")

            # Handshake
            self.socket.send(bytes.fromhex("54525450484F544C00010002"))
            logger.info("Handshake sent")

            # Login packet (bot appears as 'Discord')
            login_msg = bytes.fromhex(
                "0000006B00000001000000000000001300000013000200660007446973636F72640068000207D00000012C00000002000000000000000200000002000000000065000000030000000000000002000000020000"
            )
            self.socket.send(login_msg)
            logger.info("Login packet sent. Bot should appear in userlist.")

            time.sleep(0.1)  # Give server a moment to register

            self.connected = True
            return True
        except Exception as e:
            logger.exception("Hotline connect failed")
            self.connected = False
            return False

    def disconnect(self):
        self.running = False
        if self.socket:
            self.socket.close()
            self.socket = None
        self.connected = False
        logger.info("Disconnected from Hotline server")

    def send_chat_message(self, message: str):
        if not self.connected or not self.socket:
            logger.error("Not connected to Hotline server")
            return False
        try:
            message = sanitize_string(message)
            message_bytes = message.encode("utf-8")
            msg_len = len(message_bytes)
            newermsglen = msg_len.to_bytes(2, byteorder="big")
            newpacklen = msg_len + 6
            newerpacklen = newpacklen.to_bytes(4, byteorder="big")
            hex_data = binascii.hexlify(message_bytes)
            test1 = binascii.hexlify(b'\x00\x00\x00\x69\x00\x00\x00\xFF\x00\x00\x00\x00')
            test2 = binascii.hexlify(b'\x00\x01\x00\x65')
            test3 = binascii.hexlify(newermsglen)
            test4 = binascii.hexlify(newerpacklen)
            finalpacket = test1 + test4 + test4 + test2 + test3 + hex_data
            self.socket.send(binascii.unhexlify(finalpacket))
            self.message_counter += 1
            return True
        except Exception as e:
            logger.warning(f"Failed to send chat message: {e}")
            return False

    def listen_for_messages(self):
        self.running = True
        logger.info("Hotline listener thread started")
        while self.running and self.connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    continue
                hex_data = data.hex()
                if hex_data[:8] == '0000006a':
                    try:
                        text_data_hex = hex_data[54:]
                        actual_message = bytes.fromhex(text_data_hex).decode('utf-8', errors='ignore').strip()
                        if actual_message:
                            try:
                                actual_message = convert_ascii_to_emojis(actual_message)
                            except Exception as e:
                                logger.warning(f"Emoji conversion failed: {e}")
                            asyncio.run_coroutine_threadsafe(
                                self.discord_bot.send_to_discord(actual_message),
                                self.discord_bot.loop
                            )
                    except Exception as e:
                        logger.warning(f"Failed to parse Hotline message: {e}")
            except socket.timeout:
                continue  # Ignore timeout, keep listening
            except Exception as e:
                logger.exception(f"Unexpected error receiving data from Hotline: {e}")
                break
        logger.info("Hotline listener thread stopped")

# --- Discord Bot ---
class DiscordBot(commands.Bot):
    def __init__(self, hotline_host, hotline_port, discord_channel_id, webhook_url):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        self.hotline_client = HotlineClient(hotline_host, hotline_port, self)
        self.discord_channel_id = discord_channel_id
        self.webhook_url = webhook_url
        self.hotline_thread = None

    def start_hotline_listener(self):
        def supervisor():
            while True:
                if not self.hotline_client.connected:
                    logger.warning("Hotline not connected. Trying to reconnect...")
                    if not self.hotline_client.connect():
                        time.sleep(5)
                        continue
                try:
                    self.hotline_client.listen_for_messages()
                except Exception as e:
                    logger.exception(f"Listener crashed: {e}")
                logger.warning("Listener thread stopped unexpectedly. Restarting in 2 seconds...")
                time.sleep(2)
        thread = threading.Thread(target=supervisor, daemon=True)
        thread.start()
        self.hotline_thread = thread

    async def on_ready(self):
        logger.info(f'{self.user} connected to Discord!')
        self.start_hotline_listener()

    async def on_message(self, message):
        if message.author == self.user or message.webhook_id:
            return
        if message.channel.id != self.discord_channel_id:
            return

        text_content = message.content.strip() if message.content else ""
        for att in message.attachments:
            if hasattr(att, "url"):
                safe_url = att.url[:200]
                text_content += f"\n{safe_url}"

        if not text_content:
            return

        if self.hotline_client.connected:
            try:
                text_content = convert_emojis_to_ascii(text_content)
                max_len = 240
                lines = text_content.split("\n")
                for line in lines:
                    prefix = f"{message.author.display_name}: "
                    while len(prefix.encode("utf-8")) + len(line.encode("utf-8")) > max_len:
                        split_point = max_len - len(prefix.encode("utf-8")) - 1
                        part = line[:split_point]
                        self.hotline_client.send_chat_message(prefix + part)
                        line = line[split_point:]
                        prefix = f"{message.author.display_name}: "
                    if line:
                        self.hotline_client.send_chat_message(prefix + line)
            except Exception as e:
                logger.warning(f"Failed to forward Discord message to Hotline: {e}")
        else:
            await message.channel.send("❌ Not connected to Hotline server")

        await self.process_commands(message)

    async def send_to_discord(self, message: str):
        match = re.match(r"([^:]+):\s*(.*)", message)
        username = match.group(1).strip() if match else "Hotline System"
        content = match.group(2).strip() if match else message.strip()
        content = convert_ascii_to_emojis(content)
        payload = {"username": username, "content": content}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status != 204:
                        resp_text = await response.text()
                        logger.warning(f"Webhook failed: {response.status} - {resp_text}")
            except Exception as e:
                logger.warning(f"Failed to send Discord webhook: {e}")

    @commands.command(name='hotline_status')
    async def hotline_status(self, ctx):
        status = "✅ Connected" if self.hotline_client.connected else "❌ Disconnected"
        await ctx.send(f"Hotline Server Status: {status}")

    @commands.command(name='hotline_reconnect')
    async def hotline_reconnect(self, ctx):
        if self.hotline_client.connected:
            self.hotline_client.disconnect()
        if self.hotline_client.connect():
            if self.hotline_thread and self.hotline_thread.is_alive():
                self.hotline_thread.join(timeout=1)
            self.start_hotline_listener()
            await ctx.send("✅ Reconnected to Hotline server")
        else:
            await ctx.send("❌ Failed to reconnect to Hotline server")

# --- Main ---
def main():
    bot = DiscordBot(HOTLINE_HOST, HOTLINE_PORT, DISCORD_CHANNEL_ID, DISCORD_WEBHOOK_URL)
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        if bot.hotline_client.connected:
            bot.hotline_client.disconnect()

if __name__ == "__main__":
    main()

