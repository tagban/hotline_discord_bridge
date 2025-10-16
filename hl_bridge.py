# coding=utf-8
import asyncio
import re
import socket
import struct
import discord
import binascii
from discord.ext import commands
import logging
from typing import Optional
import threading
import aiohttp # <-- NEW IMPORT

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
# You MUST replace these placeholder values with your actual credentials and details.
# ⚠️ WARNING: Never share your Discord Bot Token!
DISCORD_TOKEN = "INSERT_BOT_TOKEN_BETWEEN_QUOTES"  # Discord bot token string
DISCORD_CHANNEL_ID = 13448314476444484496  # Discord channel ID INT (Must be an integer)
DISCORD_WEBHOOK_URL = "https://discord.com/api#####" # Webhook URL for dynamic sender names
HOTLINE_HOST = "127.0.0.1"  # Hotline server IP or hostname
HOTLINE_PORT = 5500  # Hotline port (default is 5500)
# ---------------------

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
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            logger.info(f"Connected to Hotline server {self.host}:{self.port}")
            
            # Send initial connection message
            connect_msg = bytes.fromhex("54525450484F544C00010002")
            self.socket.send(connect_msg)
            logger.info("Sent initial connection message")
            
            # Wait for server response
            response = self.socket.recv(1024)
            logger.info(f"Received response: {response.hex()}")
            
            # Send login message
            login_msg = bytes.fromhex("0000006B00000001000000000000001300000013000200660007446973636F72640068000207D00000012C00000002000000000000000200000002000000000065000000030000000000000002000000020000")
            self.socket.send(login_msg)
            logger.info("Sent login message")
            
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Hotline server"""
        self.running = False
        if self.socket:
            self.socket.close()
            self.socket = None
        self.connected = False
        logger.info("Disconnected from Hotline server")
    
    def send_chat_message(self, message: str):
        """Send chat message to Hotline server"""
        if not self.connected or not self.socket:
            logger.error("Not connected to Hotline server")
            return False
        message = sanitize_string(message)
        try:
            # Message format: 00000069 + counter + 00000000 + length + 00010065 + message
            message_bytes = message.encode('utf-8')
            message_length = len(message_bytes)
            
            # Calculate total length (00010065 + message length)
            #total_length = 3 + message_length  # 00010065 is 3 bytes + message
            print("message =" + message)
            newmsglen = len(message)
            newermsglen = newmsglen.to_bytes(2, byteorder='big')
            newpacklen = newmsglen + 6
            newerpacklen = newpacklen.to_bytes(4, byteorder='big')
            #newmsglen = newmsglen.hex()
            #newpacklen = newpacklen.hex()
            print(newerpacklen)
            print(newermsglen)
            message = message.replace("’","'")
            message = message.replace("“",'"')
            message = message.replace("”",'"')
            newhexchatmsg = message.encode('utf-8', errors='replace')
            hex_data = binascii.hexlify(newhexchatmsg)

            test1 = binascii.hexlify(b'\x00\x00\x00\x69\x00\x00\x00\xFF\x00\x00\x00\x00')
            test2 = binascii.hexlify(b'\x00\x01\x00\x65')
            test3 = binascii.hexlify(newermsglen)
            test4 = binascii.hexlify(newerpacklen)

            finalpacket = test1 + test4 + test4 + test2 + test3 + hex_data
            #print("Final Packet" + finalpacket)
            morefinalpacket = binascii.unhexlify(finalpacket)
            #print("finalpacket =" + morefinalpacket)

            # Build the packet
            packet = bytearray()
            self.socket.send(morefinalpacket)
            logger.info(f"Sent chat message: {message}")
            
            self.message_counter += 1
            return True
            
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False
    
    def listen_for_messages(self):
        """Listen for incoming messages from Hotline server"""
        self.running = True
        while self.running and self.connected:
            try:
                data = self.socket.recv(4096)
                if not data:
                    break
                
                # Parse incoming message (simplified parsing)
                if len(data) > 8:
                    # Look for chat message patterns
                    hex_data = data.hex()
                    logger.info(f"Received data: {hex_data}")
                    left_part = hex_data[:8]
                    print("left part =" + left_part)
                    if (left_part == '0000006a'):
                        
                        # --- MODIFIED BLOCK START ---
                        text_data_hex = hex_data[54:]
                        actual_message_with_user = bytes.fromhex(text_data_hex).decode('utf-8', errors='ignore').strip()
                        
                        print(f"Decoded Hotline Text: {actual_message_with_user}")
                        
                        if len(actual_message_with_user) > 3:
                            # Pass the full decoded string, e.g., "Username: This is the chat message"
                            asyncio.run_coroutine_threadsafe(
                                self.discord_bot.send_to_discord(f"{actual_message_with_user}"),
                                self.discord_bot.loop
                            )
                        # --- MODIFIED BLOCK END ---
                        
            except Exception as e:
                logger.error(f"Error receiving message: {e}")
                break
        
        logger.info("Stopped listening for Hotline messages")

class DiscordBot(commands.Bot):
    # Modified __init__ to accept webhook_url
    def __init__(self, hotline_host: str, hotline_port: int, discord_channel_id: int, webhook_url: str):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)
        
        self.hotline_client = HotlineClient(hotline_host, hotline_port, self)
        self.discord_channel_id = discord_channel_id
        self.webhook_url = webhook_url # <-- Store the webhook URL
        self.hotline_thread = None
        
    async def on_ready(self):
        logger.info(f'{self.user} has connected to Discord!')
        
        # Connect to Hotline server
        if self.hotline_client.connect():
            # Start listening thread
            self.hotline_thread = threading.Thread(target=self.hotline_client.listen_for_messages)
            self.hotline_thread.daemon = True
            self.hotline_thread.start()
            logger.info("Started Hotline message listener")
        else:
            logger.error("Failed to connect to Hotline server")
    
    async def on_message(self, message):
        # Ignore messages from the bot itself
        if message.author == self.user:
            return
        
        # Ignore messages sent by a webhook, which would be replies from Hotline
        if message.webhook_id:
            logger.info(f"Ignoring webhook message to prevent loop: {message.author.name}")
            return

        # Only process messages from the configured channel
        if message.channel.id != self.discord_channel_id:
            return
        
        # Send message to Hotline
        if self.hotline_client.connected:
            discord_message = f"{message.author.display_name}: {message.content}"
            success = self.hotline_client.send_chat_message(discord_message)
            if success:
                logger.info(f"Forwarded Discord message to Hotline: {discord_message}")
            else:
                await message.channel.send("❌ Failed to send message to Hotline server")
        else:
            await message.channel.send("❌ Not connected to Hotline server")
        
        await self.process_commands(message)
    
    # 🎯 MODIFIED to use aiohttp and the webhook URL for dynamic username display
    async def send_to_discord(self, message: str):
        if "Discord: " in message:
            print("Discarding message")
            return

        # The Hotline client is passing a string like "Username: Message Content"
        match = re.match(r"([^:]+):\s*(.*)", message)
        
        if match:
            username = match.group(1).strip()
            content = match.group(2).strip()
        else:
            # Fallback for unexpected format (e.g., system messages)
            username = "Hotline System"
            content = message.strip()

        # Webhook payload
        payload = {
            "username": f"{username}",
            "content": content
            # You can also add an avatar_url here if you have a Hotline icon
        }

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status == 204: # 204 No Content is the expected success code for webhooks
                        logger.info(f"Sent message to Discord via webhook: {username}: {content}")
                    else:
                        response_text = await response.text()
                        logger.error(f"Failed to send webhook message. Status: {response.status}, Response: {response_text}")
            except Exception as e:
                logger.error(f"Error sending message to Discord webhook: {e}")
    
    @commands.command(name='hotline_status')
    async def hotline_status(self, ctx):
        """Check Hotline connection status"""
        status = "✅ Connected" if self.hotline_client.connected else "❌ Disconnected"
        await ctx.send(f"Hotline Server Status: {status}")
    
    @commands.command(name='hotline_reconnect')
    async def hotline_reconnect(self, ctx):
        """Reconnect to Hotline server"""
        if self.hotline_client.connected:
            self.hotline_client.disconnect()
        
        if self.hotline_client.connect():
            if self.hotline_thread and self.hotline_thread.is_alive():
                self.hotline_thread.join(timeout=1)
            
            self.hotline_thread = threading.Thread(target=self.hotline_client.listen_for_messages)
            self.hotline_thread.daemon = True
            self.hotline_thread.start()
            
            await ctx.send("✅ Reconnected to Hotline server")
        else:
            await ctx.send("❌ Failed to reconnect to Hotline server")

# Removed duplicated config lines from the bottom
def sanitize_string(input_string):
    sanitized = ''.join(c for c in input_string if 32 <= ord(c) <= 126)
    return sanitized
def main():
    # Create and run the bot
    # Modified call to include the webhook URL
    bot = DiscordBot(HOTLINE_HOST, HOTLINE_PORT, DISCORD_CHANNEL_ID, DISCORD_WEBHOOK_URL)
    
    try:
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}")
    finally:
        if bot.hotline_client.connected:
            bot.hotline_client.disconnect()

if __name__ == "__main__":
    main()