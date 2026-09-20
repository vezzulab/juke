"""Turn "any web address" into a playable radio stream.

    stream = await resolve_stream_url("https://my-station.com/player")
    # -> {"stream_url": ..., "title": ..., "favicon": ..., ...}

Step A  direct detection: the address itself is a stream (.mp3/.aac/.m3u8...), a Shoutcast/Icecast
        mount (:8000/stream), or a .pls/.m3u playlist whose first valid entry is taken. Addresses
        that give no hint are probed: an audio Content-Type or ``icy-*`` headers mean "stream".
Step B  a normal web page goes to yt-dlp (``bestaudio/best``); if it finds nothing, the page's own
        <audio>/<source> tags and embedded stream links are tried.
Step C  the station name comes from the ICY headers (``icy-name``) or the page title, the icon from
        the page's <link rel="icon">.
"""

from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urljoin, urlparse

from .. import __version__

USER_AGENT = f"Juke/{__version__}"
DIRECT_EXTENSIONS = (".mp3", ".aac", ".aacp", ".m3u8", ".ogg", ".oga", ".opus", ".flac")
PLAYLIST_EXTENSIONS = (".pls", ".m3u")
PAGE_EXTENSIONS = (".html", ".htm", ".php", ".asp", ".aspx", ".jsp")
STREAM_PORTS = frozenset({7000, 7100, 8000, 8001, 8002, 8003, 8004, 8005, 8006, 8008, 8010, 8080, 8090, 8100, 8110,
                          8200, 8443, 8500, 8800, 8888, 9000, 9010, 9100, 9200, 9300})
VIDEO_EXTENSIONS = (".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv", ".m4v", ".wmv")
STREAM_PATH_WORDS = ("stream", "live", "listen", "radio", "audio", "autodj", "play", "mp3", "aac", "hls", ";")
GENERIC_NAMES = {"unnamed server", "no name", "noname", "default name", "stream", "audio stream", "icecast", "shoutcast",
                 "this is my server name", "sonicpanel", "unknown", "live stream", "radio", "my radio", "azuracast"}
PLAYLIST_TYPES = {"audio/x-mpegurl", "audio/mpegurl", "audio/x-scpls", "audio/scpls", "application/pls+xml"}
HLS_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl", "application/vnd.apple.mpegurl.audio"}
TEXT_LIKE = ("text/", "application/xhtml", "application/json", "application/xml")
BODY_LIMIT = 512 * 1024
YTDLP_TIMEOUT = 45.0


class ResolveError(Exception):
    """``code`` is one of bad_url, unreachable, no_audio (the GUI turns it into a translated message)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(slots=True)
class Probe:
    url: str
    content_type: str
    headers: dict[str, str]
    body: bytes
    status: int = 200


# -- helpers that need no network ---------------------------------------------------------------
def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ResolveError("bad_url")
    if "://" not in url:
        # "javascript:...", "mailto:...", "data:..." are not addresses; "host:8000/stream" (a port) is
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:(?!\d+(?:/|$))", url):
            raise ResolveError("bad_url")
        url = "https://" + url
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ResolveError("bad_url")
    return url


def classify_url(url: str) -> str:
    """"playlist" | "direct" | "unknown", judging by the address alone (step A)."""
    parts = urlparse(url)
    path = parts.path.lower()
    if path.endswith(PLAYLIST_EXTENSIONS):
        return "playlist"
    if path.endswith(DIRECT_EXTENSIONS):
        return "direct"
    # urlparse() moves a trailing ";" (Shoutcast's "/;") into .params, so look at the raw text after the host
    rest = url.split("://", 1)[-1].split("?", 1)[0].split("#", 1)[0]
    raw_path = rest[rest.find("/"):].lower() if "/" in rest else ""
    if parts.port in STREAM_PORTS and raw_path not in ("", "/") and not raw_path.endswith(PAGE_EXTENSIONS):
        return "direct"                       # http://host:8000/stream, http://host:8000/;
    if parts.port and parts.port not in (80, 443) and not raw_path.endswith(PAGE_EXTENSIONS):
        first = raw_path.strip("/").split("/", 1)[0].split(";", 1)[0] or (";" if ";" in raw_path else "")
        if first in STREAM_PATH_WORDS or raw_path.endswith("/;"):
            return "direct"                   # http://host:8146/stream on a port nobody standardised
    return "unknown"


def classify_probe(probe: Probe) -> str:
    """"audio" | "hls" | "playlist" | "html" | "other" from what the server answered."""
    headers = {k.lower(): v for k, v in probe.headers.items()}
    content_type = probe.content_type.split(";")[0].strip().lower()
    head = probe.body[:4096]
    if any(key.startswith("icy-") for key in headers):
        return "audio"
    if b"#EXT-X-" in head:                    # HLS, whatever content type the server claims
        return "hls"
    if content_type in PLAYLIST_TYPES or content_type in HLS_TYPES:
        return "playlist"
    if content_type.startswith("audio/") or content_type in ("application/ogg", "video/ogg"):
        return "audio"
    if head.lstrip()[:5].lower() == b"[play" or head.startswith(b"#EXTM3U"):
        return "playlist"
    if content_type in ("text/html", "application/xhtml+xml") or head.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        return "html"
    return "other"


def parse_playlist(text: str, base_url: str = "") -> list[tuple[str, str]]:
    """(title, url) entries of a .pls or .m3u playlist, http(s) only, in order, without duplicates."""
    lines = [line.strip() for line in text.replace("\r", "").split("\n") if line.strip()]
    raw: list[tuple[str, str]] = []
    if any(line.lower().startswith("[playlist]") for line in lines):
        files: dict[str, str] = {}
        titles: dict[str, str] = {}
        for line in lines:
            match = re.match(r"(?i)^(file|title)(\d+)\s*=\s*(.*)$", line)
            if match:
                (files if match.group(1).lower() == "file" else titles)[match.group(2)] = match.group(3).strip()
        raw = [(titles.get(n, ""), files[n]) for n in sorted(files, key=int)]
    else:
        title = ""
        for line in lines:
            if line.startswith("#EXTINF"):
                title = line.partition(",")[2].strip()
            elif not line.startswith("#"):
                raw.append((title, line))
                title = ""
    entries, seen = [], set()
    for title, url in raw:
        url = urljoin(base_url, "http://" + url[6:] if url.lower().startswith("icy://") else url)
        if urlparse(url).scheme in ("http", "https") and url not in seen:
            seen.add(url)
            entries.append((clean_title(title), url))
    return entries


def pick_title(icy_name: str, page_title: str, fallback: str = "") -> str:
    """The station name: the ICY header if it says something, else the page title, else ``fallback``."""
    icy = clean_title(icy_name)
    if icy and icy.lower() not in GENERIC_NAMES:
        return icy
    return clean_title(page_title) or icy or clean_title(fallback)


def clean_title(text: str, limit: int = 80) -> str:
    text = re.sub(r"\s+", " ", html.unescape(text or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


_TAG = re.compile(r"<(meta|link)\b([^>]*)>", re.I)
_ATTR = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))""")


def _attrs(fragment: str) -> dict[str, str]:
    return {m.group(1).lower(): html.unescape(next(g for g in m.groups()[1:] if g is not None)) for m in _ATTR.finditer(fragment)}


def page_meta(text: str, base_url: str) -> dict[str, str]:
    """Station name and icon from a web page (step C)."""
    match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    page_title = clean_title(match.group(1)) if match else ""
    meta: dict[str, str] = {}
    icons: dict[str, str] = {}
    for tag, fragment in _TAG.findall(text[:400_000]):
        attrs = _attrs(fragment)
        if tag.lower() == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and "content" in attrs:
                meta.setdefault(key, attrs["content"])
        elif attrs.get("href"):
            rels = attrs.get("rel", "").lower().split()
            if "icon" in rels or "apple-touch-icon" in rels:
                icons.setdefault("apple" if "apple-touch-icon" in rels else "icon", attrs["href"])
    title = clean_title(meta.get("og:site_name") or meta.get("og:title") or page_title)
    icon = icons.get("icon") or icons.get("apple") or "/favicon.ico"
    return {"title": title, "favicon": urljoin(base_url, icon), "homepage": base_url}


def scan_page(text: str, base_url: str) -> list[str]:
    """Candidate stream addresses inside a page, best first."""
    text = text.replace("\\/", "/").replace("&amp;", "&")
    found: list[tuple[int, str]] = []

    def add(rank: int, url: str) -> None:
        url = urljoin(base_url, html.unescape(url.strip()))
        if urlparse(url).scheme in ("http", "https") and all(url != u for _, u in found):
            found.append((rank, url))

    for tag in re.findall(r"<(?:audio|source)\b[^>]*>", text, re.I):
        attrs = _attrs(tag)
        src = attrs.get("src", "")
        if src and not attrs.get("type", "").lower().startswith("video/") and not urlparse(src).path.lower().endswith(VIDEO_EXTENSIONS):
            add(0, src)
    for tag, fragment in _TAG.findall(text[:400_000]):
        attrs = _attrs(fragment)
        if tag.lower() == "meta" and (attrs.get("property") or "").lower() in ("og:audio", "og:audio:url", "og:audio:secure_url"):
            add(0, attrs.get("content", ""))
    # links written relative to the page ("/groovesalad256.pls", "streams/live.mp3")
    for match in re.finditer(r"""["'(]((?!https?:)[^"'\s<>()]+?\.(?:pls|m3u8?|mp3|aac|aacp|ogg|opus)(?:\?[^"'\s<>()]*)?)["')]""", text, re.I):
        target = match.group(1)                      # keeps a ?token=... query: it is often what makes the link work
        path = target.lower().split("?", 1)[0]
        add(3 if path.endswith((".pls", ".m3u")) else 2 if path.endswith(".m3u8") else 1, urljoin(base_url, target))
    for match in re.finditer(r"""https?://[^\s"'<>\\)]+""", text):
        url = match.group(0).rstrip(".,;")
        path = urlparse(url).path.lower()
        if path.endswith((".mp3", ".aac", ".aacp", ".ogg", ".opus")):
            add(1, url)
        elif path.endswith(".m3u8"):
            add(2, url)
        elif path.endswith(PLAYLIST_EXTENSIONS):
            add(3, url)
        elif classify_url(url) == "direct":
            add(4, url)
    return [url for _, url in sorted(found, key=lambda item: item[0])]


def codec_from_type(content_type: str) -> str:
    kind = content_type.split(";")[0].strip().lower()
    if kind in ("audio/mpeg", "audio/mp3"):
        return "MP3"
    if kind in ("audio/aac", "audio/aacp", "audio/x-aac", "audio/mp4"):
        return "AAC"
    if "ogg" in kind or kind == "audio/opus":
        return "OGG"
    if kind == "audio/flac":
        return "FLAC"
    return "HLS" if kind in HLS_TYPES else ""


def _stream_info(url: str, probe: Probe | None, fallback_title: str = "", source: str = "direct") -> dict:
    headers = {k.lower(): v for k, v in (probe.headers if probe else {}).items()}
    host = urlparse(url).hostname or url
    bitrate = headers.get("icy-br", "").split(",")[0].strip()
    codec = codec_from_type(probe.content_type) if probe else ""
    if url.lower().split("?")[0].endswith(".m3u8"):
        codec = "HLS"
    # A station never ends: it sends icy-* headers, or no Content-Length. A finite file (a jingle, a podcast) does.
    live = codec == "HLS" or any(k.startswith("icy-") for k in headers) or (probe is not None and "content-length" not in headers)
    return {
        "stream_url": url,
        "live": live,
        "icy_name": clean_title(headers.get("icy-name", "")),
        "title": pick_title(headers.get("icy-name", ""), fallback_title, host),   # step C: the ICY-Header name
        "favicon": "",
        "homepage": headers.get("icy-url", ""),
        "tags": clean_title(headers.get("icy-genre", ""), 60),
        "codec": codec,
        "bitrate": int(bitrate) if bitrate.isdigit() else 0,
        "source": source,
    }


# -- network ---------------------------------------------------------------------------------------
async def _probe(client, url: str) -> Probe:
    import httpx

    try:
        async with client.stream("GET", url, headers={"Icy-MetaData": "1", "Accept": "*/*"}) as response:
            content_type = response.headers.get("content-type", "")
            body = b""
            if content_type.lower().startswith(TEXT_LIKE) or content_type.split(";")[0].strip().lower() in PLAYLIST_TYPES | HLS_TYPES \
                    or not content_type:
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) >= BODY_LIMIT:
                        break
            if response.status_code >= 400:
                raise ResolveError("unreachable", f"HTTP {response.status_code}")
            return Probe(str(response.url), content_type, dict(response.headers), body, response.status_code)
    except httpx.RemoteProtocolError:      # Shoutcast v1 answers "ICY 200 OK", which HTTP parsers reject
        return await _probe_raw(url)
    except httpx.HTTPError as exc:
        raise ResolveError("unreachable", str(exc) or exc.__class__.__name__) from exc


async def _probe_raw(url: str, timeout: float = 10.0) -> Probe:
    parts = urlparse(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(parts.hostname, port, ssl=parts.scheme == "https" or None), timeout)
        try:
            writer.write((f"GET {path} HTTP/1.0\r\nHost: {parts.netloc}\r\nUser-Agent: {USER_AGENT}\r\n"
                          "Icy-MetaData: 1\r\nAccept: */*\r\nConnection: close\r\n\r\n").encode())
            await writer.drain()
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
        finally:
            writer.close()
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        raise ResolveError("unreachable", str(exc) or exc.__class__.__name__) from exc
    lines = raw.decode("latin-1").split("\r\n")
    headers = {k.strip().lower(): v.strip() for k, _, v in (line.partition(":") for line in lines[1:]) if k.strip()}
    status = int(m.group(1)) if (m := re.search(r"\b(\d{3})\b", lines[0])) else 200
    if status >= 400:
        raise ResolveError("unreachable", f"HTTP {status}")
    return Probe(url, headers.get("content-type", "audio/mpeg"), headers, b"", status)


class _QuietLogger:
    """yt-dlp prints "ERROR: Unsupported URL" to the terminal even with quiet=True; swallow it."""

    def debug(self, message): pass

    def info(self, message): pass

    def warning(self, message): pass

    def error(self, message): pass


def _ytdlp_extract(url: str) -> dict | None:
    """Step B. Runs in a worker thread (yt-dlp is synchronous). None if yt-dlp is missing or finds nothing."""
    try:
        import yt_dlp
    except ImportError:
        return None
    options = {"format": "bestaudio/best", "extract_flat": False, "quiet": True, "no_warnings": True, "noplaylist": True,
               "skip_download": True, "socket_timeout": 10, "cachedir": False, "logger": _QuietLogger()}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:  # yt-dlp raises DownloadError/ExtractorError for pages it does not understand
        return None
    if info and info.get("entries"):
        info = next((e for e in info["entries"] if e), None)
    if not info:
        return None
    stream = info.get("url") or next((f["url"] for f in reversed(info.get("formats") or []) if f.get("url") and f.get("acodec") != "none"), "")
    if not stream:
        return None
    # A radio is endless. yt-dlp's generic extractor also "finds" the intro clip or a promo video a web
    # page happens to embed: a finite video file is not a station.
    if not info.get("is_live") and urlparse(stream).path.lower().endswith(VIDEO_EXTENSIONS):
        return None
    return {"stream_url": stream, "title": info.get("title") or "", "favicon": info.get("thumbnail") or ""}


async def _direct(client, url: str, fallback_title: str = "") -> dict:
    return _stream_info(url, await _probe(client, url), fallback_title)


async def _from_playlist_text(client, text: str, base_url: str, depth: int) -> dict:
    for title, candidate in parse_playlist(text, base_url)[:5]:
        try:
            if classify_url(candidate) == "playlist" and depth < 2:
                nested = await _probe(client, candidate)
                return await _from_playlist_text(client, nested.body.decode("utf-8", "replace"), candidate, depth + 1)
            return await _direct(client, candidate, title)
        except ResolveError:
            continue
    raise ResolveError("no_audio")


async def _resolve(client, url: str, depth: int, ytdlp: Callable[[str], dict | None]) -> dict:
    kind = classify_url(url)
    if kind == "playlist":                                            # step A: .pls / .m3u
        probe = await _probe(client, url)
        return await _from_playlist_text(client, probe.body.decode("utf-8", "replace"), probe.url, depth)
    if kind == "direct":                                              # step A: .mp3/.aac/.m3u8, :8000/stream
        return await _direct(client, url)
    probe = await _probe(client, url)                                 # no hint in the address: ask the server
    found = classify_probe(probe)
    if found in ("audio", "hls"):
        return _stream_info(probe.url, probe, source="direct")
    if found == "playlist":
        return await _from_playlist_text(client, probe.body.decode("utf-8", "replace"), probe.url, depth)

    text = probe.body.decode("utf-8", "replace")                      # a normal web page
    meta = page_meta(text, probe.url)
    candidates = scan_page(text, probe.url)[:12]

    async def from_candidate(candidate: str) -> dict | None:
        if depth >= 2:
            return None
        try:
            result = await _resolve(client, candidate, depth + 1, lambda _u: None)
        except ResolveError:
            return None
        result["title"] = pick_title(result.get("icy_name", ""), meta["title"], meta["title"])
        result["favicon"], result["homepage"], result["source"] = meta["favicon"], meta["homepage"], "page"
        return result

    static_fallback: dict | None = None      # a finite audio file (jingle, podcast): only if nothing live turns up

    async def best_of(group: list[str]) -> dict | None:
        nonlocal static_fallback
        for candidate in group:
            result = await from_candidate(candidate)
            if result and result.get("live", True):
                return result
            static_fallback = static_fallback or result
        return None

    # step A applied to what the page links to: real stream addresses (:8146/stream, .m3u8, .pls...) win
    strong = [c for c in candidates if classify_url(c) in ("direct", "playlist")]
    weak = [c for c in candidates if c not in strong]
    found = await best_of(strong[:6])
    if found:
        return found
    info = None
    try:                                                              # step B: yt-dlp
        info = await asyncio.wait_for(asyncio.to_thread(ytdlp, url), YTDLP_TIMEOUT)
    except (asyncio.TimeoutError, Exception):
        info = None
    if info and info.get("stream_url"):
        return {"stream_url": info["stream_url"], "title": clean_title(info.get("title") or meta["title"]),
                "favicon": info.get("favicon") or meta["favicon"], "homepage": meta["homepage"], "tags": "",
                "codec": "", "bitrate": 0, "source": "yt-dlp", "live": True}
    found = await best_of(weak[:5])                                   # <audio> tags without a telltale address
    if found:
        return found
    if static_fallback:
        return static_fallback
    raise ResolveError("no_audio")


async def resolve_stream_url(url: str, *, transport=None, timeout: float = 12.0,
                             ytdlp: Callable[[str], dict | None] = _ytdlp_extract) -> dict:
    """See the module docstring. Raises ResolveError(bad_url | unreachable | no_audio)."""
    import httpx

    url = normalize_url(url)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, transport=transport,
                                 headers={"User-Agent": USER_AGENT}) as client:
        result = await _resolve(client, url, 0, ytdlp)
    result.setdefault("favicon", "")
    return result
