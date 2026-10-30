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


def identity(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@contextmanager
def _store():
    folder = app_config_dir()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "web-devices.json"
    fd = os.open(folder / "web-devices.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            if not isinstance(data, dict):
                raise ValueError("Invalid browser session registry")
            before = json.dumps(data, sort_keys=True)
            now = time.time()
            data = {k: v for k, v in data.items() if isinstance(v, dict)
                    and float(v.get("expires", 0)) > now and now - float(v.get("seen", 0)) < IDLE_SECONDS}
            yield data
            if before != json.dumps(data, sort_keys=True) or not path.exists():
                with tempfile.NamedTemporaryFile(mode="w", dir=folder, delete=False, encoding="utf-8") as output:
                    temporary = output.name
                    json.dump(data, output)
                try:
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def register(token: str, address: str, agent: str, lifetime: int) -> str:
    device = identity(token)
    with _store() as data:
        if len(data) >= MAX_DEVICES:
            raise PermissionError("Too many browser sessions. Revoke a device in Remote access.")
        now = time.time()
        data[device] = {"id": device, "address": address, "agent": agent[:160],
                        "created": now, "seen": now, "expires": now + lifetime, "control": False}
    return device


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
