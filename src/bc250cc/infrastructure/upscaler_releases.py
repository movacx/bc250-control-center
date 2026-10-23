"""Keep HelixSR's and OptiScaler Client's release lists fresh, in the background.

Both projects publish often. Their lists used to be read only when the user
pressed Check for new releases, so a new release went unnoticed until then.
This reads them on its own, under the same rules as ``release_check``:

* **HTTPS, two fixed URLs**, the same ones the terminal workflow reads.
* **Bounded.** Six seconds, no retries, at most the size the terminal
  workflow accepts.
* **Only for what is installed.** A tool the user never set up is not asked
  about.
* **Nothing sent.** No cookies, no query beyond the fixed one, a plain
  product name as the user agent.
* **Silent.** No exception leaves this module; a failure keeps the list there
  was.
* **Cached.** A list younger than ``MAX_AGE_SECONDS`` is not read again, and
  one attempt per tool per run of the application at most.

What is kept is exactly what Check for new releases keeps (the tag, the
pre-release flag and each asset's name, size and digest), in the same file,
so the version pickers and everything after them work as before.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

#: Half a day: a release reaches the user the same day, at two small
#: requests per tool per day at most.
MAX_AGE_SECONDS = 12 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 6.0
USER_AGENT = "bc250-control-center"

_lock = threading.Lock()
_attempted: set[str] = set()
_running = False


def _sources() -> list[tuple[str, Path, str, int]]:
    """(name, releases.json, URL, size limit) for each tool that is installed."""
    from . import bc250_opticlient, helixsr

    sources = []
    for name, root, url, limit in (
        ("helixsr", helixsr.helixsr_root(), helixsr.HELIXSR_RELEASES_API, helixsr._RELEASES_LIMIT),
        ("opticlient", bc250_opticlient.opticlient_root(), bc250_opticlient.OPTICLIENT_RELEASES_API,
         bc250_opticlient._RELEASES_LIMIT),
    ):
        if root.is_dir():
            sources.append((name, root / "releases.json", url, limit))
    return sources


def _age(path: Path, now: float) -> float:
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return now - float(saved.get("time") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return float("inf")


def _fetch(url: str, limit: int) -> list | None:
    if not url.startswith("https://api.github.com/"):
        return None
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json", "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
            if not str(response.geturl()).startswith("https://"):
                return None
            body = response.read(limit + 1)
    except (OSError, urllib.error.URLError, ValueError):
        return None
    if len(body) > limit:
        return None
    try:
        listed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return listed if isinstance(listed, list) else None


def _kept(listed: list) -> list[dict]:
    """What Check for new releases keeps of each release."""
    kept = []
    for entry in listed[:200]:
        if not isinstance(entry, dict):
            continue
        kept.append({
            "tag_name": str(entry.get("tag_name") or ""),
            "draft": bool(entry.get("draft")),
            "prerelease": bool(entry.get("prerelease")),
            "assets": [
                {"name": str(asset.get("name") or ""), "size": asset.get("size"),
                 "digest": str(asset.get("digest") or "")}
                for asset in entry.get("assets") or () if isinstance(asset, dict)
            ],
        })
    return kept


def refresh_release_lists(*, now: float | None = None, fetch=None) -> list[str]:
    """Read every stale list once; the names of the tools whose list changed."""
    moment = time.time() if now is None else now
    fetch = fetch or _fetch
    changed = []
    try:
        sources = _sources()
    except Exception:  # noqa: BLE001 - never let a probe break the caller
        logger.debug("Could not list the upscalers to check", exc_info=True)
        return changed
    for name, path, url, limit in sources:
        with _lock:
            if name in _attempted or _age(path, moment) < MAX_AGE_SECONDS:
                continue
            _attempted.add(name)
        listed = fetch(url, limit)
        if listed is None:
            continue
        try:
            # A name of its own: the terminal "check for new releases" stages
            # into "<list>.tmp", and two writers must not share a file.
            handle, staged = tempfile.mkstemp(prefix=path.name + ".", suffix=".part", dir=path.parent)
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as stream:
                    stream.write(json.dumps({"time": int(moment), "releases": _kept(listed)}, indent=1))
                os.replace(staged, path)
            except BaseException:
                Path(staged).unlink(missing_ok=True)
                raise
            changed.append(name)
        except OSError:
            logger.debug("Could not save the %s release list", name, exc_info=True)
    return changed


def refresh_in_background(on_changed=None) -> bool:
    """Start ``refresh_release_lists`` on a daemon thread, once at a time.

    ``on_changed`` runs on that thread with the changed names, only when a
    list changed. True when a refresh was started.
    """
    global _running
    with _lock:
        if _running:
            return False
        _running = True

    def work() -> None:
        global _running
        try:
            changed = refresh_release_lists()
            if changed and on_changed is not None:
                on_changed(changed)
        except Exception:  # noqa: BLE001 - a background read never surfaces
            logger.debug("Background release check failed", exc_info=True)
        finally:
            with _lock:
                _running = False

    threading.Thread(target=work, name="upscaler-release-check", daemon=True).start()
    return True
