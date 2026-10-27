"""Is the machine running on battery? (Linux sysfs, ``pmset`` on a Mac; anything unreadable counts as mains power.)"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .system import IS_MAC

_SUPPLIES = Path("/sys/class/power_supply")


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _mac_on_battery() -> bool:
    try:
        out = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "'Battery Power'" in out


def on_battery() -> bool:
    """True when a system battery is discharging and no mains/USB-PD source is online."""
    if IS_MAC:
        return _mac_on_battery()
    try:
        supplies = list(_SUPPLIES.iterdir())
    except OSError:
        return False
    mains_online = discharging = False
    for supply in supplies:
        kind = _read(supply / "type")
        if kind == "Battery":
            if _read(supply / "scope") == "Device":   # a mouse or headset, not the laptop itself
                continue
            discharging = discharging or _read(supply / "status") == "Discharging"
        elif kind in ("Mains", "USB", "USB_C", "USB_PD", "USB_DCP", "USB_CDP", "Wireless"):
            mains_online = mains_online or _read(supply / "online") == "1"
    return discharging and not mains_online
