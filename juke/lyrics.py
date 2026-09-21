"""Song lyrics: where they come from, the synced (.lrc) format and the LRCLIB search.

A song's lyrics are looked for in this order: what the person saved in Juke, a ``.lrc`` file beside the song,
then the lyrics tag inside the file. Searching LRCLIB (a free, open lyrics service that needs no account) only
happens when the person asks, or has turned on the automatic option in Settings; it sends the title, artist,
album and length of the song, nothing else.
"""

from __future__ import annotations

import bisect
import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import __version__

LRCLIB = os.environ.get("JUKE_LYRICS_URL") or "https://lrclib.net/api"
_STAMP = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
_WORD_STAMP = re.compile(r"<(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?>")      # enhanced LRC: <mm:ss.xx>word
_TAGLINE = re.compile(r"^\[(?:ar|ti|al|au|by|offset|re|ve|length):.*\]$", re.IGNORECASE)


@dataclass(slots=True)
class Found:
    """One LRCLIB result."""
    title: str
    artist: str
    album: str
    duration: float
    plain: str
    synced: str

    @property
    def text(self) -> str:
        return self.synced or self.plain

    @property
    def is_synced(self) -> bool:
        return bool(self.synced)


def parse_lrc(text: str) -> list[tuple[int, str]]:
    """``[mm:ss.xx] words`` lines as (milliseconds, words), in time order. Empty when the text has no time stamps."""
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stamps = list(_STAMP.finditer(raw))
        if not stamps:
            continue
        words = _WORD_STAMP.sub("", raw[stamps[-1].end():]).strip()
        for stamp in stamps:
            fraction = (stamp.group(3) or "0").ljust(3, "0")[:3]
            lines.append((int(stamp.group(1)) * 60_000 + int(stamp.group(2)) * 1000 + int(fraction), words))
    lines.sort(key=lambda item: item[0])
    return lines


@dataclass(slots=True)
class Line:
    """One line of a synced song: when it starts, what it says and, when the file has them, when each word starts."""
    start: int
    text: str
    words: list[tuple[int, str]]


def _stamp_ms(minutes: str, seconds: str, fraction: str | None) -> int:
    return int(minutes) * 60_000 + int(seconds) * 1000 + int((fraction or "0").ljust(3, "0")[:3])


def parse_lines(text: str) -> list[Line]:
    """The lines of a synced song for karaoke, with per-word times where the file gives them."""
    lines: list[Line] = []
    for raw in text.splitlines():
        stamps = list(_STAMP.finditer(raw))
        if not stamps:
            continue
        body = raw[stamps[-1].end():]
        words: list[tuple[int, str]] = []
        marks = list(_WORD_STAMP.finditer(body))
        for i, mark in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
            word = body[mark.end():end].strip()
            if word:
                words.append((_stamp_ms(*mark.groups()), word))
        spoken = _WORD_STAMP.sub("", body).strip()
        for stamp in stamps:
            lines.append(Line(_stamp_ms(*stamp.groups()), spoken, words))
    lines.sort(key=lambda line: line.start)
    return lines


LEAD_IN_MS = 3000            # the countdown dots start this long before a line
GAP_MS = 8000                # a silence at least this long between two lines is a break worth counting down


def sweep(lines: list[Line], index: int, position_ms: int) -> float:
    """How much of line ``index`` has been sung, 0..1: by its word times when it has them, otherwise evenly across
    the time until the next line (never slower than about 7 seconds)."""
    if not 0 <= index < len(lines):
        return 0.0
    line = lines[index]
    if line.words and line.text:
        total = sum(len(w) + 1 for _t, w in line.words)
        done = 0.0
        for i, (start, word) in enumerate(line.words):
            end = line.words[i + 1][0] if i + 1 < len(line.words) else (lines[index + 1].start if index + 1 < len(lines) else start + 600)
            if position_ms >= end:
                done += len(word) + 1
            elif position_ms > start:
                done += (len(word) + 1) * (position_ms - start) / max(1, end - start)
                break
            else:
                break
        return max(0.0, min(1.0, done / total))
    following = lines[index + 1].start if index + 1 < len(lines) else line.start + 5000
    span = max(800, min(following - line.start, 7000)) * 0.92
    return max(0.0, min(1.0, (position_ms - line.start) / span))


def countdown(lines: list[Line], index: int, position_ms: int) -> int:
    """3, 2 or 1 while the next line is about to start after a long enough silence (or the song's intro); else 0."""
    if not lines:
        return 0
    following = lines[index + 1].start if index + 1 < len(lines) else None
    if following is None:
        return 0
    quiet_since = lines[index].start if index >= 0 else 0
    if following - quiet_since < GAP_MS and index >= 0:
        return 0
    remaining = following - position_ms
    if 0 < remaining <= LEAD_IN_MS:
        return -(-remaining // 1000)          # 3, 2, 1
    return 0


def is_synced(text: str) -> bool:
    return len(parse_lrc(text)) >= 2


def plain_text(text: str) -> str:
    """The words only: time stamps and ``[ar:...]`` header lines removed."""
    out = []
    for raw in text.splitlines():
        line = _STAMP.sub("", raw).strip() if _STAMP.search(raw) else raw.rstrip()
        if _TAGLINE.match(raw.strip()):
            continue
        out.append(line)
    return "\n".join(out).strip("\n")


def line_at(timeline: list[tuple[int, str]], position_ms: int) -> int:
    """Index of the line being sung at ``position_ms`` (-1 before the first one)."""
    return bisect.bisect_right([ms for ms, _ in timeline], position_ms) - 1


def read_sidecar(path: str) -> str:
    """The ``.lrc`` file that sits beside the song, if there is one."""
    try:
        candidate = Path(path).with_suffix(".lrc")
        if candidate.is_file() and candidate.stat().st_size < 1_000_000:
            return candidate.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass
    return ""


def read_embedded(path: str) -> str:
    """Lyrics stored in the file's own tags (ID3 USLT/SYLT-less text, Vorbis/FLAC LYRICS, MP4 ©lyr)."""
    import mutagen

    try:
        audio = mutagen.File(path)
    except Exception:
        return ""
    tags = getattr(audio, "tags", None)
    if audio is None or tags is None:
        return ""
    try:
        getall = getattr(tags, "getall", None)
        if getall is not None:                                     # ID3
            for frame in getall("USLT"):
                if str(frame.text).strip():
                    return str(frame.text).strip()
        for key in ("\xa9lyr", "LYRICS", "UNSYNCEDLYRICS", "lyrics", "unsyncedlyrics"):
            if key in tags:
                value = tags[key]
                first = value[0] if isinstance(value, (list, tuple)) and value else value
                if first and str(first).strip():
                    return str(first).strip()
    except Exception:
        return ""
    return ""


def local_lyrics(path: str) -> str:
    """Lyrics that come with the song itself: the ``.lrc`` beside it, else the tag inside it."""
    return read_sidecar(path) or read_embedded(path)


def _found(item: dict) -> Found | None:
    if not isinstance(item, dict) or item.get("instrumental"):
        return None
    plain, synced = str(item.get("plainLyrics") or ""), str(item.get("syncedLyrics") or "")
    if not (plain or synced):
        return None
    return Found(title=str(item.get("trackName") or ""), artist=str(item.get("artistName") or ""),
                 album=str(item.get("albumName") or ""), duration=float(item.get("duration") or 0), plain=plain, synced=synced)


async def search(title: str, artist: str = "", *, transport=None, timeout: float = 12.0) -> list[Found]:
    """LRCLIB results for a title (and artist), best matches first."""
    import httpx

    headers = {"User-Agent": f"Juke/{__version__} (https://github.com/vezzulab/juke)"}
    params = {"track_name": title}
    if artist:
        params["artist_name"] = artist
    async with httpx.AsyncClient(headers=headers, timeout=timeout, transport=transport, follow_redirects=True) as client:
        response = await client.get(f"{LRCLIB}/search", params=params)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
    return [f for f in (_found(item) for item in (data if isinstance(data, list) else [])) if f is not None][:25]


async def get_exact(title: str, artist: str, album: str, duration: float, *, transport=None, timeout: float = 12.0) -> Found | None:
    """The one LRCLIB entry that matches this song, using its length to tell versions apart."""
    import httpx

    headers = {"User-Agent": f"Juke/{__version__} (https://github.com/vezzulab/juke)"}
    params = {"track_name": title, "artist_name": artist, "album_name": album}
    if duration:
        params["duration"] = str(int(round(duration)))
    async with httpx.AsyncClient(headers=headers, timeout=timeout, transport=transport, follow_redirects=True) as client:
        response = await client.get(f"{LRCLIB}/get", params=params)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return _found(response.json())
