"""Asynchronous Subsonic / Airsonic REST client (API 1.16.1) built on httpx.

Authentication uses the token scheme: every request carries a fresh random salt
``s`` and ``t = md5(password + salt)``, so the password is never sent.
"""

from __future__ import annotations

import asyncio
import hashlib
import posixpath
import secrets
from typing import Any, Callable
from urllib.parse import urlencode

import httpx

from .. import __version__

API_VERSION = "1.16.1"
CLIENT_NAME = "juke"


class AirsonicError(Exception):
    """Server, network or protocol failure (message is safe to show to the user)."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url.endswith("/rest"):
        url = url[:-5]
    if url and "://" not in url:
        url = "http://" + url
    return url


def song_to_row(song: dict) -> dict:
    """Map a Subsonic ``child`` element to the unified track columns."""
    cover = song.get("coverArt")
    # "path" is the file's location inside the server's music folder: its directory is the
    # folder the user sees when browsing the server.
    folder = posixpath.dirname(str(song.get("path") or "").replace("\\", "/")).strip("/")
    return {
        "folder": folder,
        "source_type": "airsonic",
        "location": str(song["id"]),
        "title": song.get("title") or song.get("name") or "",
        "artist": song.get("artist") or "",
        "album": song.get("album") or "",
        "genre": song.get("genre") or "",
        "year": int(song.get("year") or 0),
        "track_no": int(song.get("track") or 0),
        "duration": float(song.get("duration") or 0),
        "bitrate": int(song.get("bitRate") or 0),
        "cover_key": f"as_{cover}" if cover else "",
        "size": int(song.get("size") or 0),
    }


class AirsonicClient:
    def __init__(self, base_url: str, username: str, password: str, *, timeout: float = 20.0,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = normalize_base_url(base_url)
        self.username = username
        self._password = password
        self._http = httpx.AsyncClient(
            timeout=timeout, transport=transport, follow_redirects=True,
            headers={"User-Agent": f"Juke/{__version__}"},
        )

    # -- request plumbing ------------------------------------------------------
    def _auth_params(self) -> dict[str, str]:
        salt = secrets.token_hex(8)
        token = hashlib.md5((self._password + salt).encode("utf-8")).hexdigest()  # noqa: S324 - protocol mandated
        return {"u": self.username, "t": token, "s": salt, "v": API_VERSION, "c": CLIENT_NAME}

    def _endpoint(self, name: str) -> str:
        return f"{self.base_url}/rest/{name}"

    def build_url(self, name: str, **params: Any) -> str:
        query = {**self._auth_params(), "f": "json", **{k: v for k, v in params.items() if v is not None}}
        return f"{self._endpoint(name)}?{urlencode(query)}"

    async def _request(self, name: str, **params: Any) -> dict:
        query = {**self._auth_params(), "f": "json", **{k: v for k, v in params.items() if v is not None}}
        try:
            response = await self._http.get(self._endpoint(name), params=query)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise AirsonicError(f"HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise AirsonicError(str(exc) or exc.__class__.__name__) from exc
        except ValueError as exc:
            raise AirsonicError("The server did not answer with Subsonic JSON") from exc
        body = payload.get("subsonic-response") if isinstance(payload, dict) else None
        if not isinstance(body, dict):
            raise AirsonicError("Unexpected server response")
        if body.get("status") != "ok":
            err = body.get("error") or {}
            raise AirsonicError(err.get("message", "Request failed"), err.get("code"))
        return body

    # -- API calls -------------------------------------------------------------
    async def ping(self) -> str:
        """Returns the server's API version; raises AirsonicError on any failure."""
        body = await self._request("ping.view")
        return str(body.get("version", ""))

    async def get_indexes(self) -> dict:
        return (await self._request("getIndexes.view")).get("indexes", {})

    async def get_music_directory(self, directory_id: str) -> dict:
        return (await self._request("getMusicDirectory.view", id=directory_id)).get("directory", {})

    async def sync_library(self, progress: Callable[[int], None] | None = None,
                           concurrency: int = 8) -> list[dict]:
        """Walk getIndexes -> getMusicDirectory and return every song as a track row."""
        indexes = await self.get_indexes()
        songs: dict[str, dict] = {}
        roots: list[str] = []
        for index in _as_list(indexes.get("index")):
            for artist in _as_list(index.get("artist")):
                roots.append(str(artist["id"]))
        for child in _as_list(indexes.get("child")):
            if not child.get("isDir") and not child.get("isVideo"):
                songs[str(child["id"])] = child
        gate = asyncio.Semaphore(concurrency)
        visited: set[str] = set()

        async def visit(directory_id: str) -> None:
            if directory_id in visited:
                return
            visited.add(directory_id)
            async with gate:
                directory = await self.get_music_directory(directory_id)
            children = []
            for child in _as_list(directory.get("child")):
                if child.get("isDir"):
                    children.append(visit(str(child["id"])))
                elif not child.get("isVideo"):
                    songs[str(child["id"])] = child
            if progress:
                progress(len(songs))
            if children:
                await asyncio.gather(*children)

        await asyncio.gather(*(visit(r) for r in roots))
        return [song_to_row(s) for s in songs.values()]

    def stream_url(self, song_id: str) -> str:
        """Direct streaming URL (fresh salt/token each call) — nothing is downloaded up front."""
        return self.build_url("stream.view", id=song_id, estimateContentLength="true")

    def cover_art_url(self, cover_id: str, size: int = 320) -> str:
        return self.build_url("getCoverArt.view", id=cover_id, size=size)

    async def get_cover_art(self, cover_id: str, size: int = 320) -> bytes:
        try:
            response = await self._http.get(self.cover_art_url(cover_id, size))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AirsonicError(str(exc) or exc.__class__.__name__) from exc
        return response.content

    async def scrobble(self, song_id: str, submission: bool = True, when_ms: int | None = None) -> None:
        await self._request("scrobble.view", id=song_id, submission=str(submission).lower(), time=when_ms)

    async def aclose(self) -> None:
        await self._http.aclose()
