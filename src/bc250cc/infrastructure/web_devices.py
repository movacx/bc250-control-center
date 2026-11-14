"""Owner-managed browser sessions. No cookies, passwords or CSRF secrets on disk."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager

from bc250cc.infrastructure.persistence.config_paths import app_config_dir

MAX_DEVICES = 16
IDLE_SECONDS = 30 * 60
MAX_SESSION_SECONDS = 365 * 24 * 3600
#: An approved device is trusted until the owner disconnects it or renews the access key.
PERMANENT_SECONDS = 50 * 365 * 24 * 3600
_PERMANENT = {"control": True, "permanent": True, "idle_seconds": None, "duration_seconds": None}


def identity(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _read_registry(path) -> dict:
    """The allow-list of browser sessions, or {} when it cannot be trusted.

    A power cut right after a write used to leave this file empty, and every
    start of the web server then died on it: remote access never came up
    again. The registry only lists sessions that are *allowed* (revoking one
    deletes it), so an unreadable one is read as empty -- no browser stays
    signed in, which fails closed. The bad file is kept beside it for a report.
    """
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict):
        return data
    try:
        os.replace(path, path.with_name(f"{path.name}.corrupt-{int(time.time())}"))
    except OSError:
        pass
    return {}


def write_durably(folder, path, data) -> None:
    """Replace ``path`` with ``data`` so that a power cut leaves either the
    old file or the new one, never an empty one: the bytes are on disk
    before the rename, and the rename is on disk before this returns."""
    with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False, encoding="utf-8") as output:
        temporary = output.name
        os.chmod(temporary, 0o600)
        json.dump(data, output)
        output.flush()
        os.fsync(output.fileno())
    try:
        os.replace(temporary, path)
        directory = os.open(folder, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def _store():
    folder = app_config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "web-devices.json"
    fd = os.open(folder / "web-devices.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            data = _read_registry(path)
            before = json.dumps(data, sort_keys=True)
            now = time.time()
            data = {k: v for k, v in data.items() if isinstance(v, dict)
                    and deadline(v) > now}
            yield data
            if before != json.dumps(data, sort_keys=True) or not path.exists():
                write_durably(folder, path, data)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def register(token: str, address: str, agent: str, lifetime: int, *, key_id: str = "",
             trusted: bool = False) -> str:
    """Register a browser session.

    ``trusted`` is a device paired by scanning the QR shown on this board's own
    screen: it gets hardware control and a session that never expires.
    """
    device = identity(token)
    with _store() as data:
        if len(data) >= MAX_DEVICES:
            raise PermissionError("Too many browser sessions. Revoke a device in Remote access.")
        now = time.time()
        data[device] = {"id": device, "address": address, "agent": agent[:160],
                        "created": now, "seen": now, "expires": now + lifetime, "control": False,
                        "idle_seconds": IDLE_SECONDS, "duration_seconds": None, "key_id": key_id}
        if trusted:
            data[device].update(_PERMANENT)
            data[device]["expires"] = now + PERMANENT_SECONDS
    return device


def is_permanent(device: dict) -> bool:
    return bool(device.get("permanent"))


def approve(device: str) -> None:
    """The desktop owner approves a device: hardware control and no session limit."""
    with _store() as data:
        if device not in data:
            raise ValueError("This browser session has expired")
        data[device].update(_PERMANENT)
        data[device]["expires"] = time.time() + PERMANENT_SECONDS


def deadline(device: dict) -> float:
    expiry = float(device.get("expires") or 0)
    idle = device.get("idle_seconds", IDLE_SECONDS)
    return expiry if idle is None else min(expiry, float(device.get("seen") or 0) + float(idle))


def set_lifetime(device: str, seconds: int) -> None:
    """The desktop owner chooses a fixed expiry from now, replacing the idle cap."""
    if isinstance(seconds, bool) or not isinstance(seconds, int) or not 60 <= seconds <= MAX_SESSION_SECONDS:
        raise ValueError("Choose a session duration between one minute and one year.")
    with _store() as data:
        if device not in data:
            raise ValueError("This browser session has expired")
        data[device].update(expires=time.time() + seconds, duration_seconds=seconds, idle_seconds=None)


def session(token: str) -> dict:
    with _store() as data:
        entry = data.get(identity(token)) or {}
        if entry and time.time() - entry["seen"] >= 10:
            entry["seen"] = time.time()
        return dict(entry)


def devices() -> list[dict]:
    with _store() as data:
        return sorted((dict(v) for v in data.values()), key=lambda v: v["created"], reverse=True)


def set_control(device: str, allowed: bool) -> None:
    with _store() as data:
        if device not in data:
            raise ValueError("This browser session has expired")
        data[device]["control"] = bool(allowed)


def revoke(device: str) -> None:
    with _store() as data:
        data.pop(device, None)


def revoke_all() -> None:
    with _store() as data:
        data.clear()
