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

        async def to_discord(author, source, text, image=None):
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


def test_square_icons():
    import io
    from PIL import Image

    def png(w, h):
        out = io.BytesIO()
        Image.new("RGBA", (w, h), (255, 0, 0, 255)).save(out, "PNG")
        return out.getvalue()

    for w, h in ((232, 18), (267, 18), (16, 16), (32, 32), (20, 16)):
        im = Image.open(io.BytesIO(hl_bridge.square_icon(png(w, h))))
        assert im.size == (128, 128)
    # a banner keeps only its left end, centered: the top row is transparent padding
    im = Image.open(io.BytesIO(hl_bridge.square_icon(png(232, 18))))
    assert im.getpixel((64, 0))[3] == 0 and im.getpixel((64, 64))[3] == 255


def test_discord_mentions_reach_hotline_as_names():
    import discord

    async def run():
        c = {"discord_token": "x", "discord_channel_id": 1, "discord_webhook_url": "x", "hotline_host": "h"}
        b = hl_bridge.Bridge(c)
        relayed = []

        async def relay(author, source, text, icon, attachments=()):
            relayed.append((author, text))
        b.relay = relay
        user = {"id": "123456789012345678", "username": "alice", "discriminator": "0", "avatar": None}
        msg = discord.Message(state=b._connection, channel=discord.Object(1), data={
            "id": "2", "channel_id": "1", "type": 0, "content": "<@123456789012345678>  icons up.",
            "author": {"id": "3", "username": "Tagban", "discriminator": "0", "avatar": None},
            "mentions": [user], "attachments": [], "embeds": [], "pinned": False, "mention_everyone": False,
            "tts": False, "timestamp": "2026-10-09T08:07:57+00:00", "edited_timestamp": None,
        })
        await b.on_message(msg)
        assert relayed == [("Tagban", "@alice  icons up.")]

    asyncio.run(run())


def test_discord_names_hotline_cannot_show_and_pings_it_must_still_drop():
    """clean_content hides @everyone behind a zero-width space and can leave a bare "@"."""
    import discord

    def message(b, content, mentions=()):
        return discord.Message(state=b._connection, channel=discord.Object(1), data={
            "id": "2", "channel_id": "1", "type": 0, "content": content,
            "author": {"id": "3", "username": "Tagban", "discriminator": "0", "avatar": None},
            "mentions": list(mentions), "attachments": [], "embeds": [], "pinned": False,
            "mention_everyone": False, "tts": False,
            "timestamp": "2026-10-09T08:07:57+00:00", "edited_timestamp": None,
        })

    async def run():
        c = {"discord_token": "x", "discord_channel_id": 1, "discord_webhook_url": "x",
             "hotline_host": "h", "filtered_words": ["@here", "@everyone"]}
        b = hl_bridge.Bridge(c)
        sent = []
        b.hl = type("H", (), {"closed": type("E", (), {"is_set": staticmethod(lambda: False)})(),
                              "send_chat": lambda self, line, media=None: sent.append(line)})()

        # A nickname with no ASCII in it would strip to "@": use the account handle instead.
        yuki = {"id": "123456789012345678", "username": "yuki", "global_name": "\u3086\u304d",
                "discriminator": "0", "avatar": None}
        await b.on_message(message(b, "<@123456789012345678> ping", [yuki]))
        assert sent == ["Discord | Tagban: @yuki ping"]

        # filtered_words still catches a ping, despite clean_content's zero-width escape.
        sent.clear()
        await b.on_message(message(b, "@everyone raid the hotline server"))
        assert sent == []

    asyncio.run(run())


def media_server(sent: list, chats=(), chunk=None):
    """A Hotline server with inline media: it sends `chats` (each with handle h1) after login,
    serves h1 as b"PNG-BYTES" in two parts, and keeps the uploads and chat it gets in `sent`."""
    import hotline
    from hotline import F, Transaction, Tx
    uploads = {}

    async def serve(r, w):
        assert await r.readexactly(12) == b"TRTPHOTL\x00\x01\x00\x00"
        w.write(b"TRTP\0\0\0\0")
        wire = hotline.Wire(r, w)
        while True:
            t = await wire.read()
            reply = Transaction(t.ty, id=t.id, is_reply=True)
            if t.ty == Tx.LOGIN:
                reply.fields = [hotline.u16(F.CAPABILITIES, hotline.CAP_TEXT_ENCODING | hotline.CAP_INLINE_MEDIA),
                                (F.CHAT_MEDIA_MAX_BYTES, (100).to_bytes(4, "big"))]
                if chunk:
                    reply.fields.append((F.CHAT_MEDIA_CHUNK_SIZE, chunk.to_bytes(4, "big")))
            elif t.ty == Tx.DOWNLOAD_MEDIA:
                part = t.uint(F.CHAT_MEDIA_PART_INDEX) or 0
                reply.fields = [(F.CHAT_MEDIA_PAYLOAD, [b"PNG-", b"BYTES"][part]), (F.CHAT_MEDIA_TYPE, b"image/png"),
                                hotline.u16(F.CHAT_MEDIA_PART_COUNT, 2)]
            elif t.ty == Tx.UPLOAD_MEDIA:
                token = t.get(F.CHAT_MEDIA_UPLOAD_TOKEN)
                if token:
                    assert t.uint(F.CHAT_MEDIA_PART_INDEX) == len(uploads[token]) // chunk
                else:
                    token = b"t%d" % len(uploads)
                    assert t.uint(F.CHAT_MEDIA_PART_COUNT) or t.uint(F.CHAT_MEDIA_PART_FINAL)
                uploads[token] = uploads.get(token, b"") + t.get(F.CHAT_MEDIA_PAYLOAD)
                reply.fields = [(F.CHAT_MEDIA_UPLOAD_TOKEN, token)]
                if t.uint(F.CHAT_MEDIA_PART_FINAL):
                    sent.append(("upload", uploads.pop(token)))
                    reply.fields = [(F.CHAT_MEDIA_ID, b"up1"), (F.CHAT_MEDIA_TYPE, b"image/png")]
            elif t.ty == Tx.SEND_CHAT:
                sent.append(("chat", t.get(F.DATA).decode(), t.get(F.CHAT_MEDIA_ID)))
            await wire.write(reply)
            if t.ty == Tx.LOGIN:
                for text in chats:
                    await wire.write(Transaction(Tx.CHAT_MSG, [(F.DATA, text.encode()), (F.CHAT_MEDIA_ID, b"h1"),
                                                                (F.CHAT_MEDIA_TYPE, b"image/png")]))
    return asyncio.start_server(serve, "127.0.0.1", 0)


async def bridge_on(server, posted: list) -> tuple:
    c = {"discord_token": "x", "discord_channel_id": 1, "discord_webhook_url": "x", "hotline_host": "127.0.0.1",
         "hotline_port": server.sockets[0].getsockname()[1]}
    b = hl_bridge.Bridge(c)

    async def to_discord(author, source, text, image=None):
        posted.append((author, text, image))
    b.to_discord = to_discord
    return b, asyncio.create_task(b.hotline_forever())


def test_hotline_images_reach_discord():
    """A capable client gets the media handle on chat 106 and fetches the bytes with 751, in chunks."""
    async def run():
        posted = []
        server = await media_server([], chats=("\r          Pat:  [image]", "\r          Pat:  look"))
        b, task = await bridge_on(server, posted)
        for _ in range(100):
            if len(posted) == 2:
                break
            await asyncio.sleep(0.05)
        task.cancel()
        server.close()
        assert posted == [("Pat", "", (b"PNG-BYTES", "image/png")), ("Pat", "look", (b"PNG-BYTES", "image/png"))]

    asyncio.run(run())


def test_discord_images_reach_hotline():
    """An image within the server's limits is uploaded with 750, in chunks, and sent with its link as
    the text; one over the limit, or a file that isn't an image, goes as a link only."""
    class Attachment:
        def __init__(self, url, data, content_type="image/png"):
            self.url, self.data, self.content_type, self.size = url, data, content_type, len(data)
            self.filename = url.rsplit("/", 1)[-1]
            self.width = self.height = 16

        def is_spoiler(self):
            return False

        async def read(self):
            return self.data

    async def run():
        sent = []
        server = await media_server(sent, chunk=4)
        b, task = await bridge_on(server, [])
        for _ in range(100):
            if b.hl:
                break
            await asyncio.sleep(0.05)
        await b.relay("Sam", "Discord", "look", 134, [
            Attachment("https://cdn/a.png", b"0123456789"), Attachment("https://cdn/big.png", b"x" * 101),
            Attachment("https://cdn/notes.txt", b"hi", "text/plain")])
        for _ in range(100):
            if len(sent) == 3:
                break
            await asyncio.sleep(0.05)
        task.cancel()
        server.close()
        assert sent == [("upload", b"0123456789"),
                        ("chat", "Discord | Sam: look https://cdn/big.png https://cdn/notes.txt", None),
                        ("chat", "Discord | Sam: https://cdn/a.png", b"up1")]

    asyncio.run(run())


class FakeHotline:
    """Enough of hotline.Client for relay(): it takes images and records what it is sent."""

    def __init__(self):
        self.inline_media = True
        self.media_max_bytes, self.media_max_dimension, self.media_max_pixels = 10 ** 6, 2048, 2048 * 2048
        self.closed = asyncio.Event()
        self.sent: list = []
        self.uploads = 0

    def send_chat(self, text, emote=False, media=None):
        self.sent.append((text, media))

    async def upload_media(self, data, mime):
        self.uploads += 1
        return b"up%d" % self.uploads


class Img:
    def __init__(self, url, data=b"png", content_type="image/png", width=16, height=16, read=None):
        self.url, self.data, self.content_type, self.size = url, data, content_type, len(data)
        self.filename = url.rsplit("/", 1)[-1]
        self.width, self.height, self._read = width, height, read

    def is_spoiler(self):
        return False

    async def read(self):
        if self._read:
            await self._read()
        return self.data


def bridge_with(hl, **extra):
    b = hl_bridge.Bridge({"discord_token": "x", "discord_channel_id": 1, "discord_webhook_url": "x",
                          "hotline_host": "h", **extra})
    b.hl = hl
    return b


def test_one_discord_message_is_one_flood_budget():
    """hotline_lines caps each block it is given; ten images used to mean ten uncapped extra lines."""
    async def run():
        hl = FakeHotline()
        b = bridge_with(hl)
        images = [Img(f"https://cdn/{i}.png") for i in range(10)]
        await b.relay("Sam", "Discord", "a long caption " * 20, 134, images)
        assert len(hl.sent) <= 6, f"{len(hl.sent)} chat lines for one message"
        assert hl.sent[-1][0].endswith("(message cut short)")

    asyncio.run(run())


def test_a_slow_cdn_does_not_hold_up_the_room():
    """The Discord read happens before the Hotline lock, so one stalled image cannot stop the chat."""
    async def run():
        hl = FakeHotline()
        b = bridge_with(hl)
        stuck, reading = asyncio.Event(), asyncio.Event()

        async def hang():
            reading.set()
            await stuck.wait()

        first = asyncio.create_task(b.relay("Sam", "Discord", "photo", 134,
                                            [Img("https://cdn/slow.png", read=hang)]))
        await reading.wait()                      # the image fetch is now in progress
        await b.relay("Pat", "Discord", "urgent", 134)   # must not wait behind it
        assert [t for t, _ in hl.sent] == ["Discord | Pat: urgent"]
        stuck.set()
        await first
        assert any("slow.png" in t for t, _ in hl.sent)

    asyncio.run(run())


def test_a_mislabelled_or_prelogin_attachment_goes_as_a_link():
    """Discord sizes real images; and before login the client offers no media at all."""
    import hotline

    why = hl_bridge.Bridge.why_not_inline
    hl = FakeHotline()
    assert why(hl, Img("https://cdn/a.png")) == ""
    # A .exe that Discord labelled image/png carries no dimensions.
    assert "mislabelled" in why(hl, Img("https://cdn/x.png", width=None, height=None))
    assert "keeps no" in why(hl, Img("https://cdn/n.txt", content_type="text/plain"))
    assert "will fetch" in why(hl, Img("https://cdn/huge.png", data=b"x" * (13 * 1024 * 1024)))
    fresh = hotline.Client("h", 5500, "guest", "", nickname="Relay")
    assert "no inline images" in why(fresh, Img("https://cdn/a.png"))


def test_an_oversized_screenshot_is_shrunk_to_fit():
    """256 KiB and 2048 px exclude every real screenshot, so what is over them gets scaled down."""
    import io

    from PIL import Image

    def shot(w, h):
        im = Image.new("RGB", (w, h))
        px = im.load()
        for y in range(0, h, 2):  # noise, so it cannot just compress away
            for x in range(0, w, 2):
                px[x, y] = ((x * 7) % 256, (y * 13) % 256, (x * y) % 256)
        b = io.BytesIO()
        im.save(b, "PNG")
        return b.getvalue()

    big = shot(2880, 1800)
    assert len(big) > 262144 and 2880 > 2048, "the fixture must actually be over the limits"
    out = hl_bridge.hotline_image(big, "image/png", 2880, 1800, 262144, 2048, 4194304)
    assert out is not None, "an oversized screenshot must still reach Hotline as an image"
    data, mime = out
    assert len(data) <= 262144
    im = Image.open(io.BytesIO(data))
    assert max(im.size) <= 2048 and im.size[0] * im.size[1] <= 4194304

    # One already within the limits is passed through byte for byte, not re-encoded.
    small = shot(64, 64)
    assert hl_bridge.hotline_image(small, "image/png", 64, 64, 262144, 2048, 4194304) == (small, "image/png")

    # Not an image at all, whatever Discord labelled it.
    assert hl_bridge.hotline_image(b"MZ\x90" + b"x" * 300000, "image/png", 99, 99,
                                   262144, 2048, 4194304) is None

    # An oversized animated GIF keeps its animation by staying a link.
    frames = [Image.new("P", (900, 900), i) for i in range(3)]
    b = io.BytesIO()
    frames[0].save(b, "GIF", save_all=True, append_images=frames[1:])
    assert hl_bridge.hotline_image(b.getvalue(), "image/gif", 900, 900, 1000, 2048, 4194304) is None
