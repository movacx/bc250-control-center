"""Read the published VERSION file and remember the answer.

This is the only place the desktop application itself reaches the network.
Everything else that touches the internet does so inside a shell workflow the
user launched and can watch, so this one is held to a few rules:

* **HTTPS, one host, one path.** The URL is a constant. A redirect away from
  https is refused rather than followed.
* **Bounded.** Four seconds, no retries, and at most
  ``MAX_VERSION_TEXT_BYTES`` read from the body. A published version is a dozen
  characters; refusing to read more is how a request that landed on an error
  page or a captive portal fails closed instead of being parsed.
* **Nothing sent.** No cookies, no query string, no identifying header beyond a
  plain product name. Nothing about the machine goes out.
* **Silent.** No exception leaves this module and no failure is shown to the
  user. Not reaching GitHub is not a problem worth interrupting anyone for.
* **Cached.** The answer is kept for ``CACHE_SECONDS``, so opening the
  dashboard repeatedly asks the network once.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from bc250cc.domain.updates import MAX_VERSION_TEXT_BYTES, UpdateStatus
from bc250cc.infrastructure.persistence.config_paths import app_cache_dir
from bc250cc.shared.version import application_version

logger = logging.getLogger(__name__)

RELEASE_VERSION_URL = (
    "https://raw.githubusercontent.com/movacx/bc250-control-center/main/VERSION"
)
RELEASES_PAGE_URL = "https://github.com/movacx/bc250-control-center/releases"

REQUEST_TIMEOUT_SECONDS = 4.0
# Fifteen minutes, not hours.
#
# The published file is a handful of bytes behind a CDN, so asking costs
# almost nothing; being wrong costs the user not hearing about a release they
# could already have. A six-hour window made the check indistinguishable from
# a hardcoded answer: publish a version, open the dashboard, and nothing
# happens for the rest of the afternoon.
CACHE_SECONDS = 15 * 60
CACHE_FILENAME = "release-check.json"
# A plain product name. Nothing here identifies the machine, the distribution
# or the user.
USER_AGENT = "BC250-Control-Center"


class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only while it stays on https."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        if not str(newurl).lower().startswith("https://"):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _cache_path(*, cache_dir: Path | None = None) -> Path:
    base = cache_dir if cache_dir is not None else app_cache_dir()
    return Path(base) / CACHE_FILENAME


def _read_cache(path: Path) -> tuple[str, float] | None:
    try:
        if path.stat().st_size > 4096:
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        # Valid JSON is not the same as the shape expected: a list or a bare
        # string parses fine and then has no ``get``.
        return None
    published = payload.get("published")
    checked_at = payload.get("checked_at_unix")
    if not isinstance(published, str) or not isinstance(checked_at, (int, float)):
        return None
    # A clock that moved backwards must not freeze the cache forever.
    if checked_at > time.time() + 60:
        return None
    return published, float(checked_at)


def _write_cache(path: Path, published: str, checked_at: float) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"published": published, "checked_at_unix": checked_at}),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as error:
        logger.debug("Could not cache the release check: %s", error)


def fetch_published_version(*, url: str = RELEASE_VERSION_URL, timeout: float = REQUEST_TIMEOUT_SECONDS) -> str:
    """The published version string, or ``""`` if it could not be read."""
    if not url.lower().startswith("https://"):
        return ""
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
    )
    opener = urllib.request.build_opener(_HttpsOnlyRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            if getattr(response, "status", 200) != 200:
                return ""
            # One byte more than a version can be, so a longer body is visibly
            # wrong rather than silently truncated into something parseable.
            raw = response.read(MAX_VERSION_TEXT_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as error:
        logger.debug("Release check could not reach %s: %s", url, error)
        return ""
    if len(raw) > MAX_VERSION_TEXT_BYTES:
        return ""
    try:
        return raw.decode("utf-8", "strict").strip()
    except UnicodeDecodeError:
        return ""


def check_for_update(
    *,
    installed: str | None = None,
    cache_dir: Path | None = None,
    now: float | None = None,
    force: bool = False,
) -> UpdateStatus:
    """Compare the published version with this build, using the cache first.

    Never raises, and never reports a problem: an unreachable network produces
    a status with ``reachable`` false, which the interface renders as nothing
    at all.
    """
    current = installed if installed is not None else application_version()
    moment = time.time() if now is None else now
    path = _cache_path(cache_dir=cache_dir)

    if not force:
        cached = _read_cache(path)
        if cached is not None:
            published, checked_at = cached
            if moment - checked_at < CACHE_SECONDS:
                return UpdateStatus(
                    installed=current,
                    published=published,
                    checked_at_unix=checked_at,
                    reachable=True,
                )

    published = fetch_published_version()
    if not published:
        return UpdateStatus(installed=current, checked_at_unix=moment, reachable=False)
    _write_cache(path, published, moment)
    return UpdateStatus(
        installed=current,
        published=published,
        checked_at_unix=moment,
        reachable=True,
    )
