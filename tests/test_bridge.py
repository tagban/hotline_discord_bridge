"""The Hotline side of the bridge, against HIM's test server, with Discord stubbed out."""
import asyncio
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

import hl_bridge

MOCK = Path(os.environ.get("HOTLINE_MOCK", str(Path.home() / "Documents/GitHub/him/target/debug/mock-server")))


def test_lines_are_split_and_made_plain():
    lines = hl_bridge.hotline_lines("Discord | Pat: ", "word " * 100)
    assert all(len(l) <= hl_bridge.HOTLINE_LINE_MAX for l in lines) and len(lines) > 1
    assert hl_bridge.hotline_text("hi 😀 <:blob:123>") == "hi :D https://cdn.discordapp.com/emojis/123.webp?size=48"


@pytest.fixture
def mock():
    if not MOCK.exists():
        pytest.skip("HIM's test server isn't built")
    port = 31000 + os.getpid() % 2000
    p = subprocess.Popen([str(MOCK), str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                break
        time.sleep(0.05)
    yield port
    p.terminate()


def test_relay_both_ways_and_reconnect(mock):
    import hotline

    async def run():
        c = {"discord_token": "x", "discord_channel_id": 1, "discord_webhook_url": "x", "hotline_host": "127.0.0.1",
             "hotline_port": mock, "bridge_nickname": "Relay", "hotline_icon": 4, "filtered_words": ["@here"]}
        b = hl_bridge.Bridge(c)
        posted = []

        async def to_discord(author, source, text):
            posted.append((author, source, text))
        b.to_discord = to_discord
        task = asyncio.create_task(b.hotline_forever())
        heard = asyncio.Queue()

        async def h(kind, d):
            if kind == "chat":
                await heard.put(d["text"])
        pat = hotline.Client("127.0.0.1", mock, "", "", nickname="Pat", icon=191, classic=True, on_event=h)
        await pat.connect()
        for _ in range(100):
            if b.hl and b.icons.get("Pat") == 191:
                break
            await asyncio.sleep(0.05)
            if b.hl and "Pat" not in b.icons:
                await b.refresh_users()
        pat.send_chat("hello discord")
        pat.send_chat("spam @here")
        for _ in range(100):
            if posted:
                break
            await asyncio.sleep(0.05)
        assert posted == [("Pat", "Hotline", "hello discord")]
        assert b.icons["Pat"] == 191
        await b.relay("Sam", "Discord", "hi from discord 😀", 134)
        while True:
            t = await asyncio.wait_for(heard.get(), 5)
            if "Discord | Sam" in t:
                assert "hi from discord :D" in t
                break
        # the Hotline side drops: messages from Discord wait, then go through after the reconnect
        await b.hl.close()
        for _ in range(100):
            if b.hl is None:
                break
            await asyncio.sleep(0.05)
        await b.relay("Sam", "Discord", "while you were out", 134)
        assert b.outbox
        while True:
            t = await asyncio.wait_for(heard.get(), 20)
            if "while you were out" in t:
                break
        task.cancel()
        await pat.close()

    asyncio.run(run())


def test_faces_both_ways():
    assert hl_bridge.discord_text("hi :) see http://x.com :/ and <3") == "hi 🙂 see http://x.com 😕 and ❤️"
    assert hl_bridge.discord_text("a:b c:)d") == "a:b c:)d"
    assert hl_bridge.hotline_text("nice 👍 😂") == "nice (Y) XD"


def test_our_names_leave_discord_py_alone():
    """discord.Client keeps its own attributes (http, loop, ...): the bridge's must not replace them."""
    import discord
    c = {"discord_token": "x", "discord_channel_id": 1, "discord_webhook_url": "x", "hotline_host": "h"}
    b = hl_bridge.Bridge(c)
    assert isinstance(b.http, discord.http.HTTPClient)
    plain = discord.Client(intents=discord.Intents.none())
    ours = set(vars(b)) - set(vars(plain))
    clash = {n for n in ours if hasattr(discord.Client, n)}
    assert ours and not clash, clash
