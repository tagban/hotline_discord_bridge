#!/usr/bin/env python3
"""BigRedH Hotline-Discord Bridge: one Hotline server's public chat and one Discord
channel, relayed both ways (and, optionally, a web page through MySQL).

Hotline -> Discord: through the channel's webhook, as the speaker with their Hotline
icon as the picture. Discord -> Hotline: as chat lines, "Discord | Name: message".

It speaks the Hotline protocol properly (hotline.py, from HIM): whole transactions,
a real sign-on (accepting the agreement), the user list with icons, and a check
every few minutes that the connection is still alive. When the Hotline side drops, it
reconnects on its own and holds Discord's messages until it's back. Discord's own
reconnects never start a second relay.

Settings: config.json (see config.example.json). Secrets can come from the
environment instead: DISCORD_TOKEN, DISCORD_WEBHOOK_URL, HOTLINE_PASSWORD,
MYSQL_PASSWORD, WEB_SECRET_KEY (and any other key, upper-cased, as an override).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import sys
import time
from collections import deque

import io
from collections import OrderedDict

import aiohttp
import discord
from aiohttp import web

import hotline

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bridge")

# Discord's emoji, as the text faces Hotline clients understand.
EMOJI_MAP = {
    "😀": ":D", "😄": ":D", "😁": ":D", "😅": ":P", "😂": "XD", "🤣": "XD", "🙂": ":)", "🙃": "(:",
    "😉": ";)", "😊": ":)", "😇": "o:)", "🥰": "<3", "😍": "<3", "🤩": ":O", "😘": ":*", "😗": ":*",
    "☺️": ":)", "😚": ":*", "😙": ":*", "😋": ":P", "😛": ":P", "😜": ";P", "🤪": "8P", "😝": "xP",
    "🤑": "$", "🤗": "\\o/", "🤭": ":X", "🤫": ":X", "🤔": ":?", "🤐": ":X", "🤨": "o.O", "😐": ":|",
    "😑": "-_-", "😶": ":|", "😏": ";)", "😒": ":/", "🙄": "o.O", "😬": ":S", "🤥": ":L", "😌": ":)",
    "😔": ":(", "😪": ":|", "😴": "zzZ", "😷": ":S", "🤒": ":S", "🤕": ":S", "🤢": ":S", "🤮": ":O",
    "🤧": ":S", "🥵": "!!", "🥶": "??", "🥴": "8S", "😵": "Xo", "🤯": ":O", "🤠": "8)", "🥳": "\\o/",
    "😎": "8)", "🤓": "B)", "🧐": "8.", "😕": ":/", "😟": ":(", "🙁": ":(", "😮": ":O", "😯": ":O",
    "😲": ":O", "😳": ":O", "🥺": ":(", "😦": ":O", "😧": ":O", "😨": ":O", "😰": ":S", "😥": ":(",
    "😢": ":(", "😭": "=(", "😱": ":O", "😖": ":S", "😣": ":S", "😞": ":(", "😓": ":(", "😩": "X(",
    "😫": "X(", "🥱": ":O", "😤": ">:(", "😡": ">:(", "😠": ">:(", "🤬": ":@", "😈": " >:) ",
    "👿": " >:( ", "💀": " [x] ", "💩": " (p) ", "👍": "(Y)", "👎": "(N)", "❤️": "<3", "❤": "<3",
}

# And the other way: Hotline's text faces as Discord emoji. A face counts only when it
# stands on its own (so "http://" and "a:b" are left alone), longest first.
FACES = {
    ":-)": "🙂", ":)": "🙂", "=)": "🙂", ";-)": "😉", ";)": "😉", ":-D": "😀", ":D": "😀", "XD": "😆",
    "xD": "😆", ":-(": "🙁", ":(": "🙁", "=(": "😢", ":'(": "😢", ":-P": "😛", ":P": "😛", ":p": "😛",
    ";P": "😜", ":-O": "😮", ":O": "😮", ":o": "😮", ":-*": "😘", ":*": "😘", "8-)": "😎", "8)": "😎",
    "B)": "🤓", ":-/": "😕", ":/": "😕", ":|": "😐", ":-|": "😐", ":S": "😖", ">:(": "😠", ":@": "🤬",
    "o:)": "😇", "O:)": "😇", "<3": "❤️", "</3": "💔", "(Y)": "👍", "(y)": "👍", "(N)": "👎", "\\o/": "🙌",
    "-_-": "😑", "o.O": "🤨", "O.o": "🤨", "zzZ": "😴",
}
_FACE_RE = re.compile(r"(?<!\S)(" + "|".join(re.escape(f) for f in sorted(FACES, key=len, reverse=True))
                      + r")(?=$|\s|[.,!?])")


def discord_text(text: str) -> str:
    """Hotline's text faces as emoji, for Discord."""
    return _FACE_RE.sub(lambda m: FACES[m[1]], text)


# "\r%13s:  message" for a chat line; "\r *** name action" for an emote.
CHAT_LINE = re.compile(r"^\s*(.{1,31}?):\s{1,2}(.*)$", re.S)
EMOTE_LINE = re.compile(r"^\s*\*{3}\s+(\S+)\s+(.*)$", re.S)
HOTLINE_LINE_MAX = 240  # longer lines are split; old clients cut them off
ICON_DISCORD, ICON_WEB, ICON_DEFAULT = 134, 131, 128


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        c = json.load(f)
    # Anything in the environment wins: secrets can stay out of the file.
    for k in list(c):
        v = os.environ.get(k.upper())
        if v is not None:
            c[k] = type(c[k])(v) if isinstance(c[k], (int, float)) and not isinstance(c[k], bool) else \
                (v.lower() in ("1", "true", "yes") if isinstance(c[k], bool) else v)
    for k, env in (("discord_token", "DISCORD_TOKEN"), ("discord_webhook_url", "DISCORD_WEBHOOK_URL")):
        if os.environ.get(env):
            c[k] = os.environ[env]
    return c


def square_icon(data: bytes, size: int = 128) -> bytes:
    """A Hotline icon as a square Discord avatar. The wide ones (232-267 x 18) are banners
    whose icon is the left end, about 26 pixels: that part, centered in a square. Small
    square ones are just enlarged. Pixels stay sharp (nearest neighbor), as drawn."""
    from PIL import Image
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    w, h = im.size
    if w > h * 2:
        im = im.crop((0, 0, min(w, round(h * 1.45)), h))
        w, h = im.size
    if w != h:
        side = max(w, h)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.paste(im, ((side - w) // 2, (side - h) // 2))
        im = canvas
    out = io.BytesIO()
    im.resize((size, size), Image.NEAREST).save(out, "PNG")
    return out.getvalue()


def hotline_text(text: str) -> str:
    """What the Hotline side can show: plain ASCII, with emoji as faces."""
    text = re.sub(r"<(a?):([A-Za-z0-9_]+):([0-9]+)>",
                  lambda m: f"https://cdn.discordapp.com/emojis/{m[3]}.{'gif' if m[1] else 'webp'}?size=48", text)
    for char, face in EMOJI_MAP.items():
        text = text.replace(char, face)
    return text.encode("ascii", "ignore").decode("ascii")


def hotline_lines(prefix: str, text: str) -> list[str]:
    """One message as Hotline chat lines, each short enough for every client."""
    out = []
    for para in text.splitlines() or [""]:
        para = para.strip()
        while para:
            room = HOTLINE_LINE_MAX - len(prefix)
            if len(para) <= room:
                out.append(prefix + para)
                break
            cut = para[:room].rsplit(" ", 1)[0] or para[:room]
            out.append(prefix + cut)
            para = para[len(cut):].strip()
    if len(out) > 6:
        out = out[:5] + [prefix + "(message cut short)"]
    return out


class Database:
    """The web monitor's tables (setup.sql): chat_logs and online_users. Optional."""

    def __init__(self, c: dict):
        self.c = c
        self.enabled = bool(c.get("use_web_features"))
        self.pool = None

    async def connect(self) -> None:
        if not self.enabled or self.pool:
            return
        import aiomysql
        try:
            self.pool = await aiomysql.create_pool(host=self.c["mysql_host"], user=self.c["mysql_user"],
                                                   password=self.c["mysql_password"], db=self.c["mysql_db"],
                                                   autocommit=True, pool_recycle=3600)
            log.info("MySQL connected")
        except Exception as e:
            log.error("MySQL: %s (the web monitor won't be updated)", e)

    async def _run(self, sql: str, args: tuple) -> None:
        if not self.pool:
            await self.connect()
        if not self.pool:
            return
        try:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, args)
        except Exception as e:
            log.warning("MySQL: %s", e)

    async def seen(self, name: str, source: str, icon: int | None) -> None:
        if not self.enabled:
            return
        if icon is None:  # keep the icon we know
            await self._run("INSERT INTO online_users (username, source, last_seen) VALUES (%s, %s, NOW()) "
                            "ON DUPLICATE KEY UPDATE last_seen=NOW(), source=%s", (name, source, source))
        else:
            await self._run("INSERT INTO online_users (username, source, icon_id, last_seen) VALUES (%s, %s, %s, NOW()) "
                            "ON DUPLICATE KEY UPDATE last_seen=NOW(), icon_id=%s, source=%s",
                            (name, source, icon, icon, source))

    async def said(self, source: str, author: str, message: str) -> None:
        if self.enabled:
            await self._run("INSERT INTO chat_logs (source, author, timestamp, message, processed) "
                            "VALUES (%s, %s, NOW(), %s, 0)", (source, author, message))


class Bridge(discord.Client):
    def __init__(self, c: dict):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # for turning "@Name" from Hotline into a Discord mention
        activity = None
        kind = {"playing": discord.ActivityType.playing, "listening": discord.ActivityType.listening,
                "watching": discord.ActivityType.watching, "competing": discord.ActivityType.competing}
        if c.get("discord_activity_name"):
            activity = discord.Activity(type=kind.get(str(c.get("discord_activity_type", "watching")).lower(),
                                                      discord.ActivityType.watching),
                                        name=c["discord_activity_name"])
        status = getattr(discord.Status, str(c.get("discord_status", "online")).lower(), discord.Status.online)
        super().__init__(intents=intents, activity=activity, status=status)
        self.c = c
        self.db = Database(c)
        self.channel_id = int(c["discord_channel_id"])
        self.nick = c.get("bridge_nickname", "Relay")
        self.hl: hotline.Client | None = None
        self.icons: dict[str, int] = {}  # Hotline name -> icon
        self.outbox: deque = deque(maxlen=50)  # Discord -> Hotline while Hotline is down: (time, line)
        self.session: aiohttp.ClientSession | None = None
        self.filtered = [w.lower() for w in c.get("filtered_words", [])]
        self.squares: OrderedDict[int, bytes] = OrderedDict()  # icon -> square PNG, most recent last

    # ---- start-up: runs once, however often Discord reconnects ----

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        await self.db.connect()
        if self.c.get("use_web_features"):
            app = web.Application()
            app.router.add_post("/webhook", self.web_chat)
            runner = web.AppRunner(app)
            await runner.setup()
            await web.TCPSite(runner, "0.0.0.0", int(self.c.get("webhook_port", 54230))).start()
            log.info("Web relay listening on port %s", self.c.get("webhook_port", 54230))
        if self.c.get("icon_public_url"):
            app = web.Application()
            app.router.add_get("/icons/{icon}.png", self.icon_square)
            runner = web.AppRunner(app)
            await runner.setup()
            port = int(self.c.get("icon_server_port", 54232))
            await web.TCPSite(runner, "0.0.0.0", port).start()
            log.info("Square icons served on port %s as %s", port, self.c["icon_public_url"])
        self.loop.create_task(self.hotline_forever())
        self.loop.create_task(self.watchdog())

    async def watchdog(self) -> None:
        """discord.py reconnects by itself; if the gateway still isn't healthy after ten
        minutes, something is stuck, so exit and let Docker (restart: unless-stopped) start
        a fresh process. A half-alive bridge is worse than a restarted one."""
        bad_since = None
        while not self.is_closed():
            await asyncio.sleep(60)
            lat = self.latency
            healthy = self.is_ready() and lat == lat and lat != float("inf") and lat < 30
            if healthy:
                bad_since = None
                continue
            bad_since = bad_since or time.time()
            log.warning("Discord: not connected (%d min)", (time.time() - bad_since) // 60)
            if time.time() - bad_since > 600:
                log.error("Discord: stuck for 10 minutes; exiting so the container restarts")
                os._exit(3)

    async def on_ready(self) -> None:
        log.info("Discord: connected as %s", self.user)

    async def close(self) -> None:
        if self.hl:
            await self.hl.close()
        if self.session:
            await self.session.close()
        await super().close()

    # ---- the Hotline side ----

    async def hotline_forever(self) -> None:
        wait = 5
        while not self.is_closed():
            started = time.time()
            try:
                await self.hotline_session()
            except (hotline.HotlineError, OSError, asyncio.TimeoutError) as e:
                log.error("Hotline: %s", e)
            except Exception:
                log.exception("Hotline: unexpected error")
            self.hl = None
            if time.time() - started > 300:
                wait = 5  # it had been up a while: straight back
            log.info("Hotline: reconnecting in %ds", wait)
            await asyncio.sleep(wait + random.random() * 3)
            wait = min(wait * 2, 300)

    async def hotline_session(self) -> None:
        c = self.c
        hl = hotline.Client(c["hotline_host"], int(c.get("hotline_port", 5500)), c.get("hotline_login", ""),
                            c.get("hotline_password", ""), nickname=self.nick, icon=int(c.get("hotline_icon", 128)),
                            classic=True, app_string="BigRedH Bridge", on_event=self.on_hotline)
        await hl.connect()
        self.hl = hl
        log.info("Hotline: in %s's chat as %s (%s)", hl.server_name or c["hotline_host"], self.nick, hl.transport)
        await self.refresh_users()
        # Messages from Discord that waited while Hotline was down (the last five minutes' worth).
        while self.outbox:
            at, line = self.outbox.popleft()
            if time.time() - at < 300:
                hl.send_chat(line)
                await asyncio.sleep(0.4)
        # Every few minutes: the user list, which also proves the connection is alive.
        while not hl.closed.is_set():
            try:
                await asyncio.wait_for(hl.closed.wait(), 240)
            except asyncio.TimeoutError:
                try:
                    await self.refresh_users()
                except Exception as e:
                    log.warning("Hotline: no answer (%s); reconnecting", e)
                    await hl.close()
                    break
        log.warning("Hotline: disconnected: %s", hl.close_reason or "connection lost")

    async def refresh_users(self) -> None:
        assert self.hl
        users = await asyncio.wait_for(self.hl.get_users(), 30)
        for uid, name in users.items():
            icon = self.hl.icons.get(uid, ICON_DEFAULT)
            self.icons[name] = icon
            await self.db.seen(name, "Hotline", icon)

    async def on_hotline(self, kind: str, d: dict) -> None:
        if kind == "chat":
            await self.from_hotline_chat(d["text"])
        elif kind == "user_changed":
            self.icons[d["name"]] = d.get("icon") or ICON_DEFAULT
            await self.db.seen(d["name"], "Hotline", self.icons[d["name"]])
        elif kind == "private" and self.hl:
            self.hl.send_private(d["id"], f"I'm the relay between this chat and Discord. "
                                          f"Say something in the main chat and Discord will see it.")

    async def from_hotline_chat(self, raw: str) -> None:
        line = raw.lstrip("\r\n")
        m = CHAT_LINE.match(line)
        emote = False
        if not m:
            m = EMOTE_LINE.match(line)
            emote = bool(m)
            if not m:
                return  # a server notice
        who, text = m[1].strip(), m[2].strip()
        if not text or who.lower() == self.nick.lower():
            return  # ourselves (including what we relayed from Discord)
        if any(w in text.lower() for w in self.filtered):
            return
        await self.db.seen(who, "Hotline", self.icons.get(who))
        await self.db.said("Hotline", who, text)
        if self.c.get("translate_hotline_faces", True):
            text = discord_text(text)
        await self.to_discord(who, "Hotline", f"*{text}*" if emote else text)

    # ---- square icons, for Discord's avatars ----

    async def icon_square(self, request: web.Request) -> web.Response:
        """/icons/<n>.png: icon n from icon_url_base, squared (see square_icon). Kept in memory."""
        try:
            n = int(request.match_info["icon"])
        except ValueError:
            raise web.HTTPNotFound()
        if not 0 <= n <= 65535:
            raise web.HTTPNotFound()
        png = self.squares.get(n)
        if png is None:
            base = self.c.get("icon_url_base", "http://hlwiki.com/ik0ns/")
            assert self.session
            try:
                async with self.session.get(f"{base}{n}.png") as r:
                    if r.status != 200:
                        raise web.HTTPNotFound()
                    data = await r.content.read(512 * 1024)
                png = await asyncio.to_thread(square_icon, data)
            except web.HTTPException:
                raise
            except Exception as e:
                log.warning("Icon %s: %s", n, e)
                raise web.HTTPNotFound()
            self.squares[n] = png
            while len(self.squares) > 1000:
                self.squares.popitem(last=False)
        self.squares.move_to_end(n)
        return web.Response(body=png, content_type="image/png",
                            headers={"Cache-Control": "public, max-age=604800"})

    def avatar_for(self, author: str) -> str:
        icon = self.icons.get(author, ICON_DEFAULT)
        if self.c.get("icon_public_url"):
            return f"{self.c['icon_public_url'].rstrip('/')}/{icon}.png"
        return f"{self.c.get('icon_url_base', 'http://hlwiki.com/ik0ns/')}{icon}.png"

    # ---- the Discord side ----

    async def on_message(self, msg: discord.Message) -> None:
        if msg.author == self.user or msg.webhook_id or msg.channel.id != self.channel_id:
            return
        content = msg.content + "".join(f" {a.url}" for a in msg.attachments)
        if content.strip():
            await self.relay(msg.author.display_name, "Discord", content, ICON_DISCORD)

    async def web_chat(self, request: web.Request) -> web.Response:
        if not self.c.get("web_secret_key") or request.headers.get("X-Bridge-Key") != self.c["web_secret_key"]:
            return web.Response(status=403)
        data = await request.json()
        await self.relay(str(data.get("author", "Web"))[:40], "Web", str(data.get("message", ""))[:1000], ICON_WEB)
        return web.Response(text="OK")

    async def relay(self, author: str, source: str, text: str, icon: int) -> None:
        """From Discord or the web: to Hotline (and, from the web, to Discord too)."""
        if any(w in text.lower() for w in self.filtered):
            return
        await self.db.seen(author, source, icon)
        await self.db.said(source, author, text)
        if source != "Discord":
            await self.to_discord(author, source, text)
        safe = hotline_text(text)
        if not safe.strip():
            return
        for line in hotline_lines(f"{source} | {author}: ", safe):
            if self.hl and not self.hl.closed.is_set():
                self.hl.send_chat(line)
                await asyncio.sleep(0.3)  # keep Hotline's flood protection happy
            else:
                self.outbox.append((time.time(), line))

    async def to_discord(self, author: str, source: str, text: str) -> None:
        text = text.replace("@everyone", "everyone").replace("@here", "here")
        users = []
        if "@" in text:
            guild = self.get_guild(int(self.c.get("discord_guild_id", 0) or 0))
            for member in guild.members if guild else []:
                tag = f"@{member.display_name}"
                if tag in text:
                    text = text.replace(tag, member.mention)
                    users.append(member.id)
        payload = {"username": f"{author} [{source}]"[:80], "content": text[:2000],
                   "allowed_mentions": {"parse": [], "users": users[:100]}}
        if self.c.get("use_hotline_icons", True) and source == "Hotline":
            payload["avatar_url"] = self.avatar_for(author)
        assert self.session
        for attempt in (1, 2):
            try:
                async with self.session.post(self.c["discord_webhook_url"], json=payload) as r:
                    if r.status == 429:  # Discord's rate limit: wait as told, once
                        await asyncio.sleep(float((await r.json()).get("retry_after", 1)))
                        continue
                    if r.status >= 400:
                        log.error("Discord webhook: HTTP %s %s", r.status, (await r.text())[:200])
                    return
            except Exception as e:
                log.warning("Discord webhook: %s", e)
                await asyncio.sleep(2)


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BRIDGE_CONFIG", "config.json")
    c = load_config(path)
    missing = [k for k in ("discord_token", "discord_channel_id", "discord_webhook_url", "hotline_host")
               if not c.get(k) or str(c.get(k)).startswith("INSERT")]
    if missing:
        raise SystemExit(f"{path}: fill in {', '.join(missing)}")
    Bridge(c).run(c["discord_token"], log_handler=None)


if __name__ == "__main__":
    main()
