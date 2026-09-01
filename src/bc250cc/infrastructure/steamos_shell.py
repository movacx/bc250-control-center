from __future__ import annotations

import os
import shlex
from pathlib import Path


def steamos_writable_root_wrapper() -> Path:
    """Locate the SteamOS root guard in source and installed layouts."""

    relative = Path(
        "packaging/common/os-scripts/common/with-steamos-writable-root.sh"
    )
    candidates: list[Path] = []
    configured_root = os.environ.get("BC250_CONTROL_CENTER_DIR", "").strip()
    if configured_root:
        candidates.append(Path(configured_root).expanduser() / relative)

    # The repository and both installers keep ``src`` and ``packaging`` under
    # the same application root.
    candidates.append(Path(__file__).resolve().parents[3] / relative)
    candidates.extend(
        root / relative
        for root in (
            Path.home() / ".local/share/bc250-control-center",
            Path("/usr/share/bc250-control-center"),
            Path("/usr/local/share/bc250-control-center"),
        )
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    # Keep the failure deterministic and point at the expected packaged file.
    return candidates[0]


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
