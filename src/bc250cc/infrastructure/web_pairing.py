"""One-time pairing tokens for the QR code shown on the board's own screen.

The QR used to carry the permanent access key. It now carries a short-lived
token that works once: whoever can see the screen can pair a phone, and a
photo of the QR is useless a few minutes later or after the first scan.

Only SHA-256 digests are stored (0600, owner only), shared between the desktop
page that shows the QR and the web server that redeems it.
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import secrets
import time
from contextlib import contextmanager

from bc250cc.infrastructure.persistence.config_paths import app_config_dir
from bc250cc.infrastructure.web_devices import write_durably

TTL_SECONDS = 10 * 60
#: A token is replaced before it expires, so a QR left on screen never goes stale.
RENEW_SECONDS = 8 * 60
MAX_OUTSTANDING = 4


def _digest(token: str) -> str:
    return hashlib.sha256(str(token or "").encode()).hexdigest()


@contextmanager
def _store():
    folder = app_config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "web-pairing.json"
    fd = os.open(folder / "web-pairing.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            except (OSError, ValueError):
                data = {}
            if not isinstance(data, dict):
                data = {}
            before = json.dumps(data, sort_keys=True)
            now = time.time()
            data = {k: v for k, v in data.items() if isinstance(v, dict) and float(v.get("expires") or 0) > now}
            yield data
            if json.dumps(data, sort_keys=True) != before or not path.exists():
                # Same durable replace as the session registry: a power cut
                # must not leave an empty file behind.
                write_durably(folder, path, data)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def issue() -> str:
    """Create a token valid for ``TTL_SECONDS``; the oldest outstanding one is dropped past the cap."""
    token = secrets.token_urlsafe(18)
    now = time.time()
    with _store() as data:
        data[_digest(token)] = {"created": now, "expires": now + TTL_SECONDS}
        for stale in sorted(data, key=lambda key: data[key]["created"])[:-MAX_OUTSTANDING]:
            data.pop(stale, None)
    return token


def valid(token: str) -> bool:
    """Whether ``token`` could still be redeemed (does not consume it)."""
    if not token:
        return False
    with _store() as data:
        return any(hmac.compare_digest(key, _digest(token)) for key in data)


def age(token: str) -> float | None:
    """Seconds since ``token`` was issued, or ``None`` if it is gone."""
    with _store() as data:
        entry = data.get(_digest(token))
        return None if entry is None else time.time() - float(entry["created"])


def consume(token: str) -> bool:
    """Redeem ``token``: true once, false for every later attempt."""
    if not token:
        return False
    with _store() as data:
        return data.pop(_digest(token), None) is not None
