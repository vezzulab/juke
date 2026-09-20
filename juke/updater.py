"""Update check against GitHub Releases, and in-place replacement of a running AppImage.

Privacy: the check is one HTTPS GET to api.github.com (at most once a day, and it can be switched
off in Settings). The only things sent are the program name and version in the User-Agent.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import __version__, integration

# JUKE_UPDATE_URL points the check at another server (used by the tests and by anyone developing the updater).
API_LATEST = os.environ.get("JUKE_UPDATE_URL") or "https://api.github.com/repos/vezzulab/juke/releases/latest"
CHECK_INTERVAL_S = 24 * 3600


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


def release_from_json(data: dict, arch: str = "x86_64") -> ReleaseInfo | None:
    """The stable release described by GitHub's ``releases/latest`` payload (drafts/pre-releases are ignored)."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = str(data.get("tag_name") or "")
    if parse_version(tag) is None:
        return None
    release = ReleaseInfo(tag=tag, version=".".join(map(str, parse_version(tag))), notes=str(data.get("body") or "").strip(),
                          page_url=str(data.get("html_url") or "https://github.com/vezzulab/juke/releases"))
    wanted = f"Juke-{arch}.AppImage"
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
        return release_from_json(response.json())


async def download_asset(release: ReleaseInfo, directory: Path, progress: Callable[[int], None] | None = None,
                         *, transport=None) -> Path:
    """Download the AppImage next to its final home (so the swap is an atomic rename) and verify it."""
    import httpx

    if not release.asset_url:
        raise UpdateError("This release has no AppImage attached.")
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
        if release.asset_sha256 and digest.hexdigest() != release.asset_sha256:
            raise UpdateError("checksum")
        os.chmod(part, 0o755)
        return part
    except BaseException:
        part.unlink(missing_ok=True)   # never leave a half-downloaded (or cancelled) file behind
        raise


def install_update(downloaded: Path, target: Path) -> None:
    """Swap the new AppImage in. A running AppImage stays valid: it keeps its old inode open."""
    os.replace(downloaded, target)


def self_update_target() -> Path | None:
    """The AppImage file Juke is running from, if it can replace it (else the user updates by hand)."""
    path = integration.appimage_path()
    if path is not None and os.access(path.parent, os.W_OK) and os.access(path, os.W_OK):
        return path
    return None
