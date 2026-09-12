"""Validated read boundary for Quick Access CPU live state.

The privileged CPU helper keeps detector evidence private.  It publishes only
the small, non-authorizing live profile needed by the desktop UI so both
surfaces can describe the same current session without a Polkit prompt.
"""

from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path

from bc250cc.infrastructure.cpu_oc_config import estimated_vid

CPU_RUNTIME_STATE = Path("/run/bc250-control-center/cpu-live-state.json")
CPU_RUNTIME_SCHEMA = 1
CPU_RUNTIME_HELPER_PROTOCOL = 8
CPU_RUNTIME_MAX_BYTES = 16 * 1024
BOOT_ID_PATH = Path("/proc/sys/kernel/random/boot_id")


def _safe_metadata(path: Path):
    try:
        directory = path.parent.lstat()
        payload = path.lstat()
    except OSError:
        return None
    if not (
        stat.S_ISDIR(directory.st_mode)
        and not stat.S_ISLNK(directory.st_mode)
        and directory.st_uid == 0
        and stat.S_IMODE(directory.st_mode) == 0o755
        and stat.S_ISREG(payload.st_mode)
        and not stat.S_ISLNK(payload.st_mode)
        and payload.st_uid == 0
        and stat.S_IMODE(payload.st_mode) == 0o644
        and 0 < payload.st_size <= CPU_RUNTIME_MAX_BYTES
    ):
        return None
    return payload


def _read_bytes(path: Path, expected) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        opened = os.fstat(descriptor)
        if not (
            stat.S_ISREG(opened.st_mode)
            and opened.st_uid == 0
            and stat.S_IMODE(opened.st_mode) == 0o644
            and 0 < opened.st_size <= CPU_RUNTIME_MAX_BYTES
            and opened.st_dev == expected.st_dev
            and opened.st_ino == expected.st_ino
        ):
            return None
        data = os.read(descriptor, CPU_RUNTIME_MAX_BYTES + 1)
        return data if 0 < len(data) <= CPU_RUNTIME_MAX_BYTES else None
    finally:
        os.close(descriptor)


def _boot_id(path: Path) -> str:
    try:
        value = path.read_text(encoding="ascii", errors="strict").strip()
    except (OSError, UnicodeError):
        return ""
    pattern = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"
    return value if re.fullmatch(pattern, value) else ""


def read_cpu_runtime_snapshot(
    path: Path = CPU_RUNTIME_STATE,
    boot_id_path: Path = BOOT_ID_PATH,
    *,
    now_unix_ms: int | None = None,
) -> dict[str, object] | None:
    """Return a validated same-boot live profile, never persistence authority."""
    metadata = _safe_metadata(path)
    current_boot = _boot_id(boot_id_path)
    if metadata is None or not current_boot:
        return None
    raw = _read_bytes(path, metadata)
    if raw is None:
        return None
    try:
        payload = json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    observed = payload.get("observed_at_unix_ms")
    action_observed = payload.get("action_observed_at_unix_ns")
    now = time.time_ns() // 1_000_000 if now_unix_ms is None else int(now_unix_ms)
    if (
        type(payload.get("schema")) is not int
        or payload.get("schema") != CPU_RUNTIME_SCHEMA
        or payload.get("producer") != "bc250-cpu-smu-helper"
        or type(payload.get("helper_protocol")) is not int
        or payload.get("helper_protocol") != CPU_RUNTIME_HELPER_PROTOCOL
        or payload.get("boot_id") != current_boot
        or type(observed) is not int
        or type(action_observed) is not int
        or observed < 0
        or action_observed < 0
        or action_observed > (now + 60_000) * 1_000_000
        or observed > now + 60_000
    ):
        return None
    profile = payload.get("active_profile")
    if not isinstance(profile, dict):
        return None
    required = ("frequency", "scale", "temperature", "estimated_vid", "reference_scale", "observed_at")
    if any(type(profile.get(key)) is not int for key in required):
        return None
    mode = profile.get("mode")
    frequency = profile["frequency"]
    scale = profile["scale"]
    temperature = profile["temperature"]
    reference_scale = profile["reference_scale"]
    if (
        mode not in {"automatic", "manual"}
        or not 3100 <= frequency <= 4200
        or not -50 <= scale <= 0
        or temperature != 90
        or not -50 <= reference_scale <= 0
        or profile["estimated_vid"] != estimated_vid(frequency, scale)
        or profile["observed_at"] < 0
        or profile.get("persistable") is not True
    ):
        return None
    return {
        "available": True,
        "source": "Quick Access verified snapshot",
        "source_kind": "quick_access",
        "observed_at_unix_ms": observed,
        "action_observed_at_unix_ns": action_observed,
        "active_profile": dict(profile),
    }
