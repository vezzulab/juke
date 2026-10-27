"""Which system Juke is running on, so the few places that differ can say so in one word."""

from __future__ import annotations

import sys

IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
