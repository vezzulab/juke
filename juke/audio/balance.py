"""Stereo balance through PulseAudio/PipeWire.

libVLC has no balance control, so the per-channel volume of our own playback
stream is adjusted with ``pactl`` (works on PulseAudio and pipewire-pulse).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess


def _pactl(*args: str) -> str | None:
    try:
        done = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=2, check=True)
        return done.stdout
    except (OSError, subprocess.SubprocessError):
        return None


class StreamBalance:
    def __init__(self) -> None:
        self.supported = shutil.which("pactl") is not None

    def _own_sink_input(self) -> dict | None:
        out = _pactl("-f", "json", "list", "sink-inputs")
        if not out:
            return None
        try:
            inputs = json.loads(out)
        except ValueError:
            return None
        pid = str(os.getpid())
        for item in inputs:
            if item.get("properties", {}).get("application.process.id") == pid:
                return item
        return None

    def apply(self, balance: float) -> bool:
        """``balance`` in [-1, 1] (left .. right). Returns False if no stream is active yet."""
        if not self.supported:
            return False
        item = self._own_sink_input()
        if item is None:
            return False
        channels = item.get("volume", {})
        if not channels:
            return False
        base = max(ch.get("value", 0) for ch in channels.values())
        if base <= 0:
            return False
        left = 1.0 if balance <= 0 else 1.0 - balance
        right = 1.0 if balance >= 0 else 1.0 + balance
        volumes = []
        for name in channels:
            gain = right if ("right" in name or name.endswith("-r")) else left if ("left" in name or name.endswith("-l")) else 1.0
            volumes.append(f"{int(round(base * gain))}")
        return _pactl("set-sink-input-volume", str(item["index"]), *volumes) is not None
