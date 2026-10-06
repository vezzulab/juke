"""Song lyrics: where they come from, the synced (.lrc) format and the LRCLIB search.

A song's lyrics are looked for in this order: what the person saved in Juke, a ``.lrc`` file beside the song,
then the lyrics tag inside the file. Searching online only happens when the person asks, or has turned on the
automatic option in Settings; it sends the title, artist, album and length of the song, nothing else.

Songs are not only English ones, so the search asks several free services at once and merges what they find:
LRCLIB (open, worldwide, synced lyrics), NetEase Cloud Music (Chinese, Japanese, Korean and Southeast Asian pop,
synced) and lyrics.ovh (plain words, a lot of Latin, Arabic, Turkish and Indian music). None needs an account.
Titles are tried as written and then cleaned of "(feat. …)", "[Remastered]" and the like, in any script.
"""

from __future__ import annotations

import asyncio
import bisect
import difflib
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from . import __version__

LRCLIB = os.environ.get("JUKE_LYRICS_URL") or "https://lrclib.net/api"
NETEASE = os.environ.get("JUKE_NETEASE_URL") or "https://music.163.com/api"
LYRICS_OVH = os.environ.get("JUKE_OVH_URL") or "https://api.lyrics.ovh/v1"
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
    source: str = "LRCLIB"

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


# Older lyric files are not UTF-8. East Asian ones can be told apart by what they decode to (Shift-JIS has kana,
# EUC-KR hangul, GBK and Big5 ideographs); anything else that is not UTF-8 is read as Western Europe's code page.
_BOMS = (("utf-8-sig", b"\xef\xbb\xbf"), ("utf-32", b"\xff\xfe\x00\x00"), ("utf-32", b"\x00\x00\xfe\xff"),
         ("utf-16", b"\xff\xfe"), ("utf-16", b"\xfe\xff"))


def _share(text: str, low: int, high: int) -> float:
    wide = [ch for ch in text if ord(ch) > 127 and not ch.isspace()]
    return sum(low <= ord(ch) <= high for ch in wide) / len(wide) if wide else 0.0


def decode_text(raw: bytes) -> str:
    """Text from the bytes of a lyrics file, whatever alphabet or old encoding it was saved in."""
    for name, mark in _BOMS:
        if raw.startswith(mark):
            return raw.decode(name, errors="replace").strip()
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError:
        pass
    for name in ("shift_jis", "euc_kr", "gb18030", "big5"):
        try:
            text = raw.decode(name)
        except UnicodeDecodeError:
            continue
        kana = _share(text, 0x3040, 0x30FF)
        hangul = _share(text, 0xAC00, 0xD7A3)
        ideographs = _share(text, 0x4E00, 0x9FFF)
        if (name == "shift_jis" and kana > 0.15) or (name == "euc_kr" and hangul > 0.8) \
                or (name in ("gb18030", "big5") and ideographs > 0.9 and kana < 0.02):
            return text.strip()
    return raw.decode("cp1252", errors="replace").strip()


def read_sidecar(path: str) -> str:
    """The ``.lrc`` file that sits beside the song, if there is one."""
    try:
        candidate = Path(path).with_suffix(".lrc")
        if candidate.is_file() and candidate.stat().st_size < 1_000_000:
            return decode_text(candidate.read_bytes())
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


_NOISE = re.compile(
    r"\s*[\(\[（【「『][^\)\]）】」』]*(?:feat|ft\.|featuring|with|remaster|live|version|edit|mix|remix|acoustic|"
    r"explicit|deluxe|bonus|mono|stereo|karaoke|instrumental|official|video|audio|lyric|radio|en vivo|"
    r"remasteri[sz]ado|versión|ライブ|リマスター|现场|現場|라이브)[^\)\]）】」』]*[\)\]）】」』]", re.IGNORECASE)
_DASH_TAIL = re.compile(r"\s+[-–—]\s+(?:\d{4}\s+)?(?:remaster(?:ed)?|live|mono|stereo|single|radio|version|edit|remix|"
                        r"feat\.?|ft\.?|en vivo|remasteri[sz]ado).*$", re.IGNORECASE)
_TRACK_NO = re.compile(r"^\s*\d{1,3}\s*[-._)]\s+")


def clean_title(title: str) -> str:
    """The song's own name: no track number, "(feat. …)", "[Remastered 2011]" or "- Live" (works in any script)."""
    text = _TRACK_NO.sub("", title)
    text = _NOISE.sub("", text)
    text = _DASH_TAIL.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip() or title.strip()


def main_artist(artist: str) -> str:
    """The first artist of "A feat. B", "A & B", "A, B", "A / B"."""
    first = re.split(r"\s+(?:feat\.?|ft\.?|featuring|with|x|y|&|and|con|et|und)\s+|[,;/、，]", artist, maxsplit=1, flags=re.IGNORECASE)[0]
    return first.strip() or artist.strip()


_ENSEMBLE = re.compile(r"^(?:the|el|la|los|las|orquesta|orchestra|grupo|banda|conjunto)\s+", re.IGNORECASE)


def artist_core(artist: str) -> str:
    """The name of a group without "Orquesta", "Grupo", "La", "Los"…: services spell it "Orquesta La Solución",
    "La Solución" or just "Solución", and they are all the same group."""
    name = main_artist(artist)
    for _ in range(3):
        shorter = _ENSEMBLE.sub("", name)
        if shorter == name or not shorter:
            break
        name = shorter
    return name.strip()


def _client(transport, timeout: float):
    import httpx

    headers = {"User-Agent": f"Juke/{__version__} (https://github.com/vezzulab/juke)"}
    return httpx.AsyncClient(headers=headers, timeout=timeout, transport=transport, follow_redirects=True)


async def _get(client, url: str, params: dict, headers: dict | None = None):
    """GET that tries again when the service is busy (LRCLIB answers 503 "server busy" now and then) or drops the call."""
    import httpx

    response = None
    for attempt, pause in enumerate((0.0, 0.6, 1.4, 2.8)):
        if pause:
            await asyncio.sleep(pause)
        try:
            response = await client.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.TransportError):
            if attempt == 3:
                raise
            continue
        if response.status_code not in (429, 500, 502, 503, 504) or attempt == 3:
            return response
    return response


def _plain(text: str) -> str:
    """Lower case, no accents, no punctuation: "Cañita Más!" and "canita mas" are the same words."""
    base = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", " ", base.casefold()).strip()


def _similar(a: str, b: str) -> float:
    a, b = _plain(a), _plain(b)
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def relevance(found: Found, title: str, artist: str) -> tuple[float, float]:
    """(how much the result's title looks like the one asked for, how much title and artist do together)."""
    name = _similar(clean_title(found.title), clean_title(title))
    who = max(_similar(main_artist(found.artist), main_artist(artist)),
              _similar(artist_core(found.artist), artist_core(artist))) if artist and found.artist else 0.5
    return name, 0.75 * name + 0.25 * who


async def _lrclib(client, title: str, artist: str) -> list[Found]:
    """LRCLIB, asked several ways because it is busy at times and spells names its own way: the exact lookup (a lighter
    call than a search), the song by this artist, the group under its other spellings, and finally the same title by
    anyone, because the same song is covered by many (salsa, bachata, boleros) and the words are the same."""
    import httpx

    cleaned, lead, core = clean_title(title), main_artist(artist), artist_core(artist)
    exact = [{"track_name": title, "artist_name": artist}] if artist else []
    if artist and (cleaned, core) != (title, artist):
        exact.append({"track_name": cleaned, "artist_name": core})
    attempts = [{"track_name": title, **({"artist_name": artist} if artist else {})}]
    if (cleaned, lead) != (title, artist):
        attempts.append({"track_name": cleaned, **({"artist_name": lead} if lead else {})})
    if core and core != lead:
        attempts.append({"track_name": cleaned, "artist_name": core})
    attempts += [{"q": f"{cleaned} {core}".strip()}, {"track_name": cleaned}, {"q": cleaned}]

    out: list[Found] = []
    seen: set[tuple[str, str, int]] = set()
    answered, failure = False, None

    def take(item) -> None:
        f = _found(item)
        if f is not None:
            key = (_plain(f.title), _plain(f.artist), int(f.duration))
            if key not in seen:
                seen.add(key)
                out.append(f)

    for params in exact:
        try:
            response = await _get(client, f"{LRCLIB}/get", params)
            answered = answered or response.status_code in (200, 404)
            if response.status_code == 200:
                take(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            failure = exc
    for params in attempts:
        try:
            response = await _get(client, f"{LRCLIB}/search", params)
            if response.status_code == 404:
                answered = True
                continue
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:        # busy for this one: the other ways of asking may still work
            failure = exc
            continue
        answered = True
        for item in (data if isinstance(data, list) else []):
            take(item)
        if len(out) >= 8:
            break
    if not out and not answered and failure is not None:
        raise failure
    return out


def _netease_lines(text: str) -> str:
    """NetEase puts credit lines ("作词 : …") at the top of the file; they are not part of the song."""
    return "\n".join(line for line in text.splitlines()
                     if not re.match(r"^\[\d+:\d+(?:[.:]\d+)?\]\s*(?:作词|作曲|编曲|制作人|作詞|作曲|編曲|Lyrics by|Composed by|Arranged by)\s*[:：]", line))


async def _netease(client, title: str, artist: str) -> list[Found]:
    """NetEase Cloud Music: the biggest catalogue of Chinese, Japanese and Korean songs with synced lyrics."""
    query = f"{clean_title(title)} {main_artist(artist)}".strip()
    response = await _get(client, f"{NETEASE}/search/get", {"s": query, "type": 1, "limit": 6, "offset": 0},
                          {"Referer": "https://music.163.com/"})
    response.raise_for_status()
    songs = ((response.json().get("result") or {}).get("songs")) or []
    out: list[Found] = []
    for song in songs[:6]:
        song_id = song.get("id")
        if not song_id:
            continue
        if _similar(clean_title(str(song.get("name") or "")), clean_title(title)) < 0.55:
            continue                                   # a search for Spanish words finds Chinese songs: only what matches
        reply = await _get(client, f"{NETEASE}/song/lyric", {"id": song_id, "lv": 1, "kv": 1, "tv": -1},
                           {"Referer": "https://music.163.com/"})
        reply.raise_for_status()
        data = reply.json()
        synced = _netease_lines(str((data.get("lrc") or {}).get("lyric") or ""))
        synced = synced if is_synced(synced) else ""
        plain = "" if synced else plain_text(str((data.get("lrc") or {}).get("lyric") or ""))
        if not (synced or plain):
            continue
        artists = ", ".join(a.get("name", "") for a in song.get("artists", []) if isinstance(a, dict))
        out.append(Found(title=str(song.get("name") or ""), artist=artists, album=str((song.get("album") or {}).get("name") or ""),
                         duration=float(song.get("duration") or 0) / 1000, plain=plain, synced=synced, source="NetEase"))
    return out


async def _ovh(client, title: str, artist: str) -> list[Found]:
    """lyrics.ovh: plain words, needs an artist."""
    from urllib.parse import quote

    if not artist:
        return []
    response = await _get(client, f"{LYRICS_OVH}/{quote(main_artist(artist), safe='')}/{quote(clean_title(title), safe='')}", {})
    if response.status_code == 404:
        return []
    response.raise_for_status()
    text = str(response.json().get("lyrics") or "").strip()
    return [Found(title=clean_title(title), artist=main_artist(artist), album="", duration=0.0, plain=text, synced="",
                  source="lyrics.ovh")] if text else []


PROVIDERS = (_lrclib, _netease, _ovh)


SERVICE_NAMES = {"_lrclib": "LRCLIB", "_netease": "NetEase", "_ovh": "lyrics.ovh"}
CACHE_DAYS = 3                  # a search that found something is not repeated for this long (and is the plan B when offline)
CACHE_ENTRIES = 300


@dataclass(slots=True)
class Report:
    found: list[Found]
    failed: list[str]           # the services that did not answer: with nothing found, "try again in a moment"


def _variants(title: str, artist: str) -> list[tuple[str, str]]:
    """What the person typed, and what they probably meant: "Orquesta La Solucion - Ruina" in the title box is the artist,
    a dash and the song."""
    parts = re.split(r"\s+[-–—]\s+", title.strip(), maxsplit=1)
    asked = [(title, artist)]
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        left, right = parts[0].strip(), parts[1].strip()
        if not artist:
            guess = (right, left)
        elif _similar(artist_core(left), artist_core(artist)) >= 0.6 or _plain(artist_core(artist)) in _plain(left):
            guess = (right, artist)
        elif _similar(artist_core(right), artist_core(artist)) >= 0.6 or _plain(artist_core(artist)) in _plain(right):
            guess = (left, artist)
        else:
            guess = (right, left)
        asked = [guess, (title, artist)]
    return asked


def _cache_file() -> Path:
    from .config import CACHE_DIR

    return CACHE_DIR / "lyrics-search.json"


def _cache_load() -> dict:
    import json

    try:
        data = json.loads(_cache_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_store(key: str, found: list[Found]) -> None:
    import json
    import time
    from dataclasses import asdict

    cache = _cache_load()
    cache[key] = {"at": time.time(), "found": [asdict(f) for f in found[:30]]}
    if len(cache) > CACHE_ENTRIES:
        for old in sorted(cache, key=lambda k: cache[k].get("at", 0))[:len(cache) - CACHE_ENTRIES]:
            del cache[old]
    try:
        path = _cache_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def _cache_get(key: str, fresh_only: bool) -> list[Found]:
    import time

    entry = _cache_load().get(key)
    if not isinstance(entry, dict) or (fresh_only and time.time() - float(entry.get("at", 0)) > CACHE_DAYS * 86400):
        return []
    try:
        return [Found(**item) for item in entry.get("found", [])]
    except TypeError:
        return []


async def _ask(title: str, artist: str, transport, timeout: float) -> Report:
    async with _client(transport, timeout) as client:
        answers = await asyncio.gather(*(provider(client, title, artist) for provider in PROVIDERS), return_exceptions=True)
    results: list[Found] = []
    seen: dict[tuple[str, str], int] = {}
    for answer in answers:
        if isinstance(answer, BaseException):
            continue
        for item in answer:
            key = (clean_title(item.title).casefold(), main_artist(item.artist).casefold())
            at = seen.get(key)
            if at is None:
                seen[key] = len(results)
                results.append(item)
            elif item.is_synced and not results[at].is_synced:     # same song, but this one follows the music
                results[at] = item
    failed = [SERVICE_NAMES[p.__name__] for p, a in zip(PROVIDERS, answers) if isinstance(a, BaseException)]
    scored = [(relevance(f, title, artist), f) for f in results]
    scored = [(score, f) for score, f in scored if score[0] >= 0.6]           # another song entirely: not offered
    scored.sort(key=lambda item: (-round(item[0][1], 1), not item[1].is_synced))   # best match first, then synced ones
    return Report([f for _score, f in scored][:30], failed)


async def search_report(title: str, artist: str = "", *, transport=None, timeout: float = 12.0) -> Report:
    """Search every service (and the saved results of earlier searches when they are all down).

    Tries what was typed and then what was probably meant ("Artist - Song" in the title box). A result list is saved, so
    asking again is instant and still works when LRCLIB is down; with nothing saved the report says who did not answer.
    """
    key = f"{_plain(title)}|{_plain(artist)}"
    if transport is None:                                          # (tests pass a transport and want the real thing)
        saved = _cache_get(key, fresh_only=True)
        if saved:
            return Report(saved, [])
    last = Report([], [])
    for asked_title, asked_artist in _variants(title, artist):
        last = await _ask(asked_title, asked_artist, transport, timeout)
        if last.found:
            if transport is None:
                _cache_store(key, last.found)
            return last
    if last.failed and transport is None:
        stale = _cache_get(key, fresh_only=False)
        if stale:
            return Report(stale, last.failed)
    return last


async def search(title: str, artist: str = "", *, transport=None, timeout: float = 12.0) -> list[Found]:
    """Results from every service, best match first. Raises only when no service answered and nothing was found."""
    report = await search_report(title, artist, transport=transport, timeout=timeout)
    if not report.found and len(report.failed) == len(PROVIDERS):
        raise RuntimeError("no lyrics service answered: " + ", ".join(report.failed))
    return report.found


async def get_exact(title: str, artist: str, album: str, duration: float, *, transport=None, timeout: float = 12.0) -> Found | None:
    """The entry that matches this song: LRCLIB's exact match by length, else the best of the wider search."""
    async with _client(transport, timeout) as client:
        params = {"track_name": title, "artist_name": artist, "album_name": album}
        if duration:
            params["duration"] = str(int(round(duration)))
        response = await client.get(f"{LRCLIB}/get", params=params)
        if response.status_code != 404:
            response.raise_for_status()
            exact = _found(response.json())
            if exact is not None:
                return exact
    if not duration:
        return None
    # Not under that exact name (another language's spelling, a "(Remastered)" suffix): take a result of the same length.
    for item in await search(title, artist, transport=transport, timeout=timeout):
        if item.duration and abs(item.duration - duration) <= 3 and item.is_synced:
            return item
    return None
