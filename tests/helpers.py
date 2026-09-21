"""Isolate every test run in a throw-away XDG tree (must be imported before juke.config)."""

import os
import tempfile

_ROOT = tempfile.mkdtemp(prefix="juke-test-")
for name, sub in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
    os.environ[name] = os.path.join(_ROOT, sub)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = _ROOT

# no test may look at (or wait for) a phone that happens to be plugged into the computer running it
from juke.devices import mtp as _mtp  # noqa: E402

_mtp._libmtp = False
