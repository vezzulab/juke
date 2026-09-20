"""Radio-Browser (radio-browser.info) client: the community directory behind "Explore Radio",
plus saving station icons. Only contacted when the user opens Explore or adds a station."""

from __future__ import annotations

import hashlib
from pathlib import Path

from dataclasses import replace

from .. import __version__
from ..config import COVERS_DIR
from ..db.database import Station

MIRRORS = ("https://de1.api.radio-browser.info", "https://nl1.api.radio-browser.info", "https://at1.api.radio-browser.info")
USER_AGENT = f"Juke/{__version__}"
ICON_LIMIT = 512 * 1024


class RadioBrowserError(Exception):
    """No Radio-Browser server answered."""


def station_from_api(item: dict) -> Station | None:
    """Map one Radio-Browser record to a Station (None if it has no usable http(s) stream)."""
    url = str(item.get("url_resolved") or item.get("url") or "").strip()
    name = " ".join(str(item.get("name") or "").split())
    if not name or not url.lower().startswith(("http://", "https://")):
        return None
    tags = ", ".join([t.strip() for t in str(item.get("tags") or "").split(",") if t.strip()][:4])
    return Station(id=0, name=name[:100], stream_url=url, homepage=str(item.get("homepage") or ""),
                   favicon=str(item.get("favicon") or ""), tags=tags, country=str(item.get("country") or ""),
                   codec=str(item.get("codec") or "").upper(), bitrate=int(item.get("bitrate") or 0),
                   uuid=str(item.get("stationuuid") or ""))


def icon_path(favicon_url: str) -> Path:
    return COVERS_DIR / f"radio_{hashlib.sha1(favicon_url.encode()).hexdigest()[:20]}.png"


class RadioBrowserClient:
    def __init__(self, *, transport=None, timeout: float = 10.0, mirrors: tuple[str, ...] = MIRRORS) -> None:
        self._transport, self._timeout, self._mirrors = transport, timeout, list(mirrors)
        self._http_client = None

    @property
    def _http(self):
        if self._http_client is None:
            import httpx

            self._http_client = httpx.AsyncClient(timeout=self._timeout, transport=self._transport, follow_redirects=True,
                                                  headers={"User-Agent": USER_AGENT})
        return self._http_client

    async def _get(self, path: str, params: dict) -> list[dict]:
        import httpx

        last: Exception | None = None
        for base in list(self._mirrors):
            try:
                response = await self._http.get(base + path, params=params)
                response.raise_for_status()
                data = response.json()
                self._mirrors.remove(base)
                self._mirrors.insert(0, base)          # keep using the server that answered
                return data if isinstance(data, list) else []
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
        raise RadioBrowserError(str(last) or "no server answered")

    async def search(self, name: str = "", tag: str = "", limit: int = 60) -> list[Station]:
        """Working stations ordered by popularity; ``name`` and ``tag`` narrow them down."""
        params = {"limit": limit, "hidebroken": "true", "order": "clickcount", "reverse": "true"}
        if name.strip():
            params["name"] = name.strip()
        if tag.strip():
            params["tag"] = tag.strip()
            params["tagExact"] = "true"
        stations, seen = [], set()
        for item in await self._get("/json/stations/search", params):
            station = station_from_api(item)
            if station and station.stream_url not in seen:
                seen.add(station.stream_url)
                stations.append(station)
        return stations

    async def by_uuid(self, uuid: str) -> Station | None:
        """One station by its Radio-Browser id, with its *current* stream address."""
        for item in await self._get(f"/json/stations/byuuid/{uuid}", {}):
            station = station_from_api(item)
            if station:
                return station
        return None

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()


async def refresh_station(station: Station, *, transport=None) -> Station | None:
    """A saved station stopped working (they change their stream address all the time): find where it
    lives now. Radio-Browser stations are looked up by id; ones added from a page or playlist are
    resolved again from that page. Returns the station with its new address, or None if nothing new."""
    if station.uuid:
        client = RadioBrowserClient(transport=transport)
        try:
            fresh = await client.by_uuid(station.uuid)
        except RadioBrowserError:
            fresh = None
        finally:
            await client.aclose()
        if fresh and fresh.stream_url != station.stream_url:
            return replace(station, stream_url=fresh.stream_url, codec=fresh.codec or station.codec,
                           bitrate=fresh.bitrate or station.bitrate)
    if station.source_url:
        from .radio_resolver import ResolveError, resolve_stream_url

        try:
            found = await resolve_stream_url(station.source_url, transport=transport)
        except ResolveError:
            return None
        if found["stream_url"] != station.stream_url:
            return replace(station, stream_url=found["stream_url"], codec=found.get("codec") or station.codec,
                           bitrate=int(found.get("bitrate") or 0) or station.bitrate, favicon=found.get("favicon") or station.favicon)
    return None


async def fetch_icon(url: str, *, transport=None) -> bool:
    """Download a station icon into the cover cache (scaled PNG). False if it could not be used."""
    import httpx
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    if not url.lower().startswith(("http://", "https://")):
        return False
    target = icon_path(url)
    if target.exists():
        return True
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True, transport=transport,
                                     headers={"User-Agent": USER_AGENT}) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                data = b""
                async for chunk in response.aiter_bytes():
                    data += chunk
                    if len(data) > ICON_LIMIT:
                        return False
    except httpx.HTTPError:
        return False
    image = QImage.fromData(data)
    if image.isNull():
        return False
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    return image.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation).save(str(target), "PNG")
