"""Read the "now playing" title of an Icecast/Shoutcast stream (ICY metadata).

libVLC 3 only asks for ICY metadata on plain http:// streams, not on https:// ones, and most stations
are https now. So Juke asks itself: one short request with ``Icy-MetaData: 1``, reading only as far as
the first metadata block (a few dozen KB), then closing.
"""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urlparse

from .. import __version__

HEADER_LIMIT = 1 << 16
_TITLE = re.compile(rb"StreamTitle='(.*?)';", re.S)
PLACEHOLDERS = ("info goes here", "now playing", "no title", "unknown", "n/a", "loading")


def clean_stream_title(raw: str, station_name: str = "") -> str:
    """The song text, or "" for placeholders (stations often send "Now Playing info goes here")."""
    title = " ".join(raw.split())
    low = title.lower().strip(" -–—")
    if not low or low == station_name.strip().lower() or any(p in low for p in PLACEHOLDERS) and len(low) < 40:
        return ""
    return title


def parse_metadata_block(block: bytes) -> str:
    match = _TITLE.search(block)
    if not match:
        return ""
    raw = match.group(1)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


async def read_stream_title(url: str, timeout: float = 10.0) -> str:
    """The stream's current title ("Artist - Song"), or "" if it sends none. Never raises."""
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(parts.hostname, port, ssl=parts.scheme == "https" or None, limit=HEADER_LIMIT), timeout)
        writer.write((f"GET {path} HTTP/1.0\r\nHost: {parts.netloc}\r\nUser-Agent: Juke/{__version__}\r\n"
                      "Icy-MetaData: 1\r\nAccept: */*\r\nConnection: close\r\n\r\n").encode())
        await writer.drain()
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
        headers = {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in head.decode("latin-1").split("\r\n")[1:])}
        metaint = int(headers.get("icy-metaint", "0") or 0)
        if metaint <= 0:
            return ""
        await asyncio.wait_for(reader.readexactly(metaint), timeout)            # audio up to the first metadata block
        length = (await asyncio.wait_for(reader.readexactly(1), timeout))[0] * 16
        if not length:
            return ""
        return parse_metadata_block(await asyncio.wait_for(reader.readexactly(length), timeout))
    except (OSError, ValueError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        return ""
    finally:
        if writer is not None:
            writer.close()
