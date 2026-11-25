"""Whether bc250_memory loads by itself at boot, and the steps that decide it.

The copy Control Center builds with DKMS names the board in its aliases, so
udev loads it at every boot whatever the kernel command line says. Only a
denylist entry stops that; loading it by name still works. These are plain
workflow steps, so the switch works with any version of the root helper.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

MODULE = "bc250_memory"
DENYLIST = "/etc/modprobe.d/bc250-control-center-memory.conf"
MARKER = "# Managed by BC250 Control Center"
DIRECTORIES = ("/etc/modprobe.d", "/run/modprobe.d", "/usr/local/lib/modprobe.d", "/usr/lib/modprobe.d")
_ENTRY = re.compile(r"^\s*(?:blacklist\s+bc250[_-]memory\s*|install\s+bc250[_-]memory\s+\S*/(?:true|false)\b.*)$", re.M)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def loaded(root: Path = Path("/")) -> bool:
    return (root / "sys/module" / MODULE).exists()


def loads_by_alias(root: Path = Path("/"), release: str = "") -> bool:
    """The running kernel's module matches this board by an alias."""
    aliases = _read(root / "usr/lib/modules" / (release or os.uname().release) / "modules.alias")
    return any("BC-250" in line and line.split()[-1:] == [MODULE] for line in aliases.splitlines() if MODULE in line)


def denied_by(root: Path = Path("/")) -> str:
    """The file that keeps it from loading by itself, or an empty string."""
    for directory in DIRECTORIES:
        for item in sorted((root / directory.lstrip("/")).glob("*.conf")):
            if _ENTRY.search(_read(item)):
                return f"{directory}/{item.name}"
    return ""


def corrected(options: dict, option: str, root: Path = Path("/")) -> dict:
    """The helper's kernel options, with the memory driver's row as it really is."""
    arguments = options.get("arguments")
    if not isinstance(arguments, dict) or option not in arguments or not loads_by_alias(root):
        return options
    loads = not denied_by(root)
    row = {**dict(arguments[option] or {}), "configured": loads, "managed": loads, "external": False, "active": loaded(root)}
    return {**options, "arguments": {**arguments, option: row}}


def steps(wanted: bool, root: Path = Path("/")) -> str:
    """Shell that makes it so; empty when there is nothing to change."""
    if not loads_by_alias(root):
        return ""
    blocked = denied_by(root)
    path = shlex.quote(DENYLIST)
    if wanted:
        if not blocked:
            return ""
        if blocked != DENYLIST:
            return f"echo 'ERROR: {MODULE} is blocked by {blocked}, which Control Center did not write. It was left as it is.' >&2; exit 65\n"
        return f"sudo rm -f -- {path}\necho 'OK: {MODULE} loads again at the next boot.'\n"
    if blocked:
        return ""
    return (
        f"printf '%s\\n' {shlex.quote(MARKER)} 'blacklist {MODULE}' | sudo tee {path} >/dev/null\n"
        f"sudo chmod 0644 {path}\n"
        f"sudo modprobe -r {MODULE} 2>/dev/null || true\n"
        f"if [ -d /sys/module/{MODULE} ]; then\n"
        f"  echo 'OK: {MODULE} no longer loads at boot. It is in use now: restart to unload it.'\n"
        f"else\n"
        f"  echo 'OK: {MODULE} is unloaded and no longer loads at boot.'\n"
        f"fi\n"
        f"echo 'The change it made to the SMU lasts until the board is switched off completely.'\n"
    )
