"""Resolve a track row to a playable URL. Only called when Play is pressed."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..db.database import SOURCE_AIRSONIC, SOURCE_LOCAL, Track


class SourceError(Exception):
    """The track cannot be played right now (missing file, server not configured...)."""


class SourceResolver:
    def __init__(self, airsonic_provider: Callable[[], object | None]) -> None:
        self._airsonic = airsonic_provider

    def resolve(self, track: Track) -> str:
        if track.source_type == SOURCE_LOCAL:
            path = Path(track.location)
            if not path.is_file():
                raise SourceError(track.location)
            return path.resolve().as_uri()  # file:///...
        if track.source_type == SOURCE_AIRSONIC:
            client = self._airsonic()
            if client is None:
                raise SourceError("airsonic")
            return client.stream_url(track.location)  # http(s)://.../rest/stream.view?...
        raise SourceError(track.source_type)
