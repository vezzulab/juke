"""Update check against GitHub Releases, and in-place replacement of a running AppImage or (on a Mac) of Juke.app.

Privacy: the check is one HTTPS GET to api.github.com when Juke starts and every 30 minutes while it
stays open (it can be switched off in Settings). The only things sent are the program name and
version in the User-Agent.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__, integration
from .config import CACHE_DIR
from .system import IS_MAC

# JUKE_UPDATE_URL points the check at another server (used by the tests and by anyone developing the updater).
API_LATEST = os.environ.get("JUKE_UPDATE_URL") or "https://api.github.com/repos/vezzulab/juke/releases/latest"
RECHECK_INTERVAL_S = 30 * 60    # while Juke stays open; it also checks at every start
SNOOZE_S = 24 * 3600            # "Later" silences that version for a day


class UpdateError(Exception):
    """Download or verification failure; the message is safe to show to the user."""


@dataclass(slots=True)
class ReleaseInfo:
    tag: str
    version: str
    notes: str
    page_url: str
    asset_url: str = ""
    asset_size: int = 0
    asset_sha256: str = ""
    installed_sha256: str = ""      # the AppImage running now ("" when not running from one)
    asset_build: str = ""           # a Mac has no file to hash: the build id the release notes announce...
    installed_build: str = ""       # ...and the one inside the running Juke.app

    @property
    def asset_id(self) -> str:
        if self.installed_build and not self.installed_sha256:       # a Mac compares build ids with build ids, never with the file's hash
            return self.asset_build
        return self.asset_sha256 or self.asset_build

    @property
    def installed_id(self) -> str:
        return self.installed_sha256 or self.installed_build

    @property
    def is_rebuild(self) -> bool:
        """Same version number, different file: a fix published without raising the version."""
        return bool(self.asset_id and self.installed_id and self.asset_id != self.installed_id and not is_newer(self.version))

    @property
    def key(self) -> str:
        """What "Later" and "Skip" remember: the version, plus the build when it is a rebuild of the same version."""
        return f"{self.version}+{self.asset_id[:8]}" if self.is_rebuild else self.version


def is_update(release: ReleaseInfo | None) -> bool:
    """A newer version, or a new build of this very version (told apart by the file's SHA-256, its signature)."""
    return release is not None and (is_newer(release.version) or (parse_version(release.version) == parse_version(__version__) and release.is_rebuild))


_build_cache: dict[tuple, str] = {}
_BUILD_MARK = re.compile(r"<!--\s*juke-build:mac=(\d+)\s*-->")


def running_build_id() -> str:
    """The build id inside the running Juke.app ("" from source or on Linux)."""
    bundle = mac_bundle()
    if bundle is None:
        return ""
    try:
        import plistlib

        return str(plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes()).get("JukeBuild") or "")
    except (OSError, ValueError):
        return ""


def running_build_sha256() -> str:
    """SHA-256 of the AppImage this Juke is running from ("" when it is not an AppImage). Hashed once per run."""
    path = integration.appimage_path()
    if path is None:
        return ""
    try:
        stat = path.stat()
        identity = (str(path), stat.st_mtime_ns, stat.st_size)
        if identity not in _build_cache:
            digest = hashlib.sha256()
            with open(path, "rb") as image:
                for chunk in iter(lambda: image.read(1 << 20), b""):
                    digest.update(chunk)
            _build_cache[identity] = digest.hexdigest()
        return _build_cache[identity]
    except OSError:
        return ""


def parse_version(text: str) -> tuple[int, ...] | None:
    """"v1.2.3-beta" -> (1, 2, 3); None if it does not look like a version."""
    match = re.match(r"^\s*v?(\d+(?:\.\d+){0,3})", text or "")
    return tuple(int(part) for part in match.group(1).split(".")) if match else None


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, old = parse_version(candidate), parse_version(current)
    if new is None or old is None:
        return False
    width = max(len(new), len(old))
    return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))


MAC_ASSET = "Juke-macos-arm64.dmg"


def release_from_json(data: dict, arch: str = "x86_64", mac: bool = False) -> ReleaseInfo | None:
    """The stable release described by GitHub's ``releases/latest`` payload (drafts/pre-releases are ignored)."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    if parse_version(tag) is None:
        return None
    release = ReleaseInfo(tag=tag, version=".".join(map(str, parse_version(tag))), notes=str(data.get("body") or "").strip(),
                          page_url=str(data.get("html_url") or "https://github.com/vezzulab/juke/releases"))
    wanted = MAC_ASSET if mac else f"Juke-{arch}.AppImage"
    marked = _BUILD_MARK.search(str(data.get("body") or ""))
    if mac and marked:
        release.asset_build = marked.group(1)
    release.notes = _BUILD_MARK.sub("", release.notes).strip()
    for asset in data.get("assets") or []:
        if asset.get("name") == wanted:
            release.asset_url = str(asset.get("browser_download_url") or "")
            release.asset_size = int(asset.get("size") or 0)
            digest = str(asset.get("digest") or "")
            if digest.startswith("sha256:"):
                release.asset_sha256 = digest[7:].lower()
    return release


async def fetch_latest(*, transport=None, timeout: float = 10.0) -> ReleaseInfo | None:
    """The newest published release, or None if there is none yet."""
    import httpx

    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"Juke/{__version__}"}
    async with httpx.AsyncClient(headers=headers, timeout=timeout, transport=transport, follow_redirects=True) as client:
        response = await client.get(API_LATEST)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        release = release_from_json(response.json(), mac=IS_MAC)
    if release is not None:
        release.installed_sha256 = await asyncio.to_thread(running_build_sha256)
        release.installed_build = running_build_id()
    return release


async def download_asset(release: ReleaseInfo, directory: Path, progress: Callable[[int], None] | None = None,
                         *, transport=None) -> Path:
    """Download the AppImage next to its final home (so the swap is an atomic rename) and verify it."""
    import httpx

    if not release.asset_url:
        raise UpdateError("This release has no file for this computer attached.")
    part = Path(directory) / ".Juke-update.part"
    digest = hashlib.sha256()
    done = last = 0
    try:
        async with httpx.AsyncClient(headers={"User-Agent": f"Juke/{__version__}"}, follow_redirects=True,
                                     timeout=httpx.Timeout(20.0, read=60.0), transport=transport) as client:
            async with client.stream("GET", release.asset_url) as response:
                response.raise_for_status()
                total = int(response.headers.get("content-length") or release.asset_size or 0)
                with open(part, "wb") as out:
                    async for chunk in response.aiter_bytes(1 << 16):
                        out.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        percent = int(done * 100 / total) if total else 0
                        if progress and percent != last:
                            last = percent
                            progress(percent)
        if release.asset_size and done != release.asset_size:
            raise UpdateError("The download was incomplete.")
        if not release.asset_sha256 or digest.hexdigest() != release.asset_sha256:
            raise UpdateError("checksum")
        os.chmod(part, 0o755)
        return part
    except BaseException:
        part.unlink(missing_ok=True)   # never leave a half-downloaded (or cancelled) file behind
        raise


def install_update(downloaded: Path, target: Path) -> None:
    """Swap the new AppImage in. A running AppImage stays valid: it keeps its old inode open."""
    os.replace(downloaded, target)


def mac_bundle() -> Path | None:
    """The Juke.app this process runs from (None when run from source)."""
    if not (IS_MAC and getattr(sys, "frozen", False)):
        return None
    for parent in Path(sys.executable).resolve().parents:
        if parent.suffix == ".app":
            return parent
    return None


def download_dir(target: Path) -> Path:
    """Where the download goes: next to an AppImage (so the swap is one rename), in the cache for a disk image."""
    if target.suffix == ".app":
        directory = CACHE_DIR / "update"
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    return target.parent


def stage_mac_app(dmg: Path, target: Path) -> Path:
    """Open the downloaded disk image, copy the new Juke.app next to the one that runs and check its signature.
    Nothing is replaced yet: that happens when Juke closes (``swap_app_after_exit``)."""
    mount = Path(tempfile.mkdtemp(prefix="juke-update-"))
    staged = target.parent / ".Juke-update.app"
    try:
        shutil.rmtree(staged, ignore_errors=True)
        attach = subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-noverify", "-mountpoint", str(mount), str(dmg)],
                                capture_output=True, text=True)
        if attach.returncode != 0:
            raise UpdateError("The disk image could not be opened.")
        try:
            source = mount / "Juke.app"
            if not source.is_dir():
                raise UpdateError("The disk image has no Juke.app.")
            if subprocess.run(["ditto", str(source), str(staged)], capture_output=True).returncode != 0:
                raise UpdateError("The new Juke could not be copied next to the old one.")
        finally:
            subprocess.run(["hdiutil", "detach", "-force", "-quiet", str(mount)], capture_output=True)
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(staged)], capture_output=True)
        if subprocess.run(["codesign", "--verify", "--deep", "--strict", str(staged)], capture_output=True).returncode != 0:
            raise UpdateError("checksum")
        return staged
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(mount, ignore_errors=True)
        dmg.unlink(missing_ok=True)


_SWAP = r"""
while kill -0 "$1" 2>/dev/null; do sleep 0.3; done
old="$2"; new="$3"; backup="$(dirname "$old")/.Juke-old.app"
rm -rf "$backup"
if mv "$old" "$backup"; then
  if mv "$new" "$old"; then rm -rf "$backup"; else mv "$backup" "$old"; fi
fi
[ "$4" = 1 ] && open "$old"
exit 0
"""


def swap_app_after_exit(staged: Path, target: Path, open_after: bool, pid: int | None = None) -> subprocess.Popen:
    """Once this Juke has quit, put the new Juke.app where the old one was (and open it, if asked)."""
    return subprocess.Popen(["/bin/sh", "-c", _SWAP, "juke-update", str(pid or os.getpid()), str(target), str(staged), "1" if open_after else "0"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def self_update_target() -> Path | None:
    """The AppImage file (or Juke.app on a Mac) Juke is running from, if it can replace it (else the user updates by hand)."""
    bundle = mac_bundle()
    if bundle is not None:
        return bundle if os.access(bundle.parent, os.W_OK) and os.access(bundle, os.W_OK) else None
    path = integration.appimage_path()
    if path is not None and os.access(path.parent, os.W_OK) and os.access(path, os.W_OK):
        return path
    return None
