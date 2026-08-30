from __future__ import annotations

import shlex
from pathlib import Path


def steamos_writable_root_wrapper() -> Path:
    return (
        Path(__file__).resolve().parent
        / "Os_repository"
        / "scripts"
        / "common"
        / "with-steamos-writable-root.sh"
    )


def wrap_steamos_writable_command(command: str, *, family: str) -> str:
    """Run one compound command while preserving SteamOS read-only state.

    Non-SteamOS callers are returned unchanged.  SteamOS callers execute the
    complete workflow inside one guard so nested helpers can modify /usr and
    /etc without repeatedly toggling the root filesystem.  The guard restores
    read-only mode only when Control Center disabled it itself.
    """

    text = str(command or "").strip()
    if not text or str(family or "").strip().lower() != "steamos":
        return text
    wrapper = steamos_writable_root_wrapper()
    return " ".join(
        (
            "/usr/bin/bash",
            shlex.quote(str(wrapper)),
            "/usr/bin/bash",
            "-lc",
            shlex.quote(text),
        )
    )
