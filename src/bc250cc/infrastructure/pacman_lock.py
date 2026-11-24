"""pacman's database lock: whether it is held, by whom, and how to release it.

pacman creates ``db.lck`` in its database folder for the length of a
transaction and removes it at the end. An update that is cut off (power loss,
a closed terminal, a crash) leaves it behind, and from then on every install
fails with "unable to lock database" until someone removes it by hand
(R-1bf75324, R-d8d8dc3d, R-48d27e43).

The check here only reads: the lock file, the processes in /proc and the boot
time. Removing the lock is a terminal workflow that checks again as root and
refuses while a package manager is running.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

DEFAULT_LOCK = Path("/var/lib/pacman/db.lck")
#: Programs that open pacman's database and hold its lock while they change
#: packages. The GUI front-ends (pamac, Octopi, PackageKit) use libalpm
#: directly, so no ``pacman`` process shows while they work; an idle one holds
#: nothing, but nothing outside it can tell, so it is named and the release
#: waits for it unless the lock is older than this boot.
PACKAGE_MANAGERS = (
    "pacman", "pamac", "pamac-daemon", "pamac-manager", "packagekitd", "octopi",
    "octopi-helper", "yay", "paru", "pikaur", "trizen", "aura",
)

FREE = "free"            # no lock file
IN_USE = "in-use"        # lock file and a package manager running
STALE = "stale"          # lock file and nothing that could hold it
NOT_APPLICABLE = "not-applicable"  # no pacman on this system


@lru_cache(maxsize=1)
def lock_path() -> Path:
    """The lock in pacman's configured database folder (SteamOS: /usr/lib/holo/pacmandb)."""
    pacman_conf = shutil.which("pacman-conf")
    if pacman_conf:
        try:
            result = subprocess.run(
                [pacman_conf, "DBPath"], capture_output=True, text=True, timeout=5, check=False
            )
            folder = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        except (OSError, subprocess.SubprocessError, IndexError):
            folder = ""
        if folder.startswith("/"):
            return Path(folder) / "db.lck"
    return DEFAULT_LOCK


# Match complete argv entries. Unknown switches and refreshes stay busy.
_READ_ONLY = (
    rb"[^\0]+\0(?:"
    rb"(?:-Q[cegiklmnpqstudo]*|--query)|(?:-F[lqox]*|--files)|"
    rb"(?:-T|--deptest|-V|--version)|"
    rb"(?:-S[islpgq]*[islpg][islpgq]*|(?:-S|--sync)\0(?:-[islpg]+|--(?:info|search|list|print|groups)))"
    rb")\0(?:([^-\0][^\0]*|-[iqslpg]+|--(?:info|search|list|print|groups|quiet))\0)*"
)


def _pacman_query(entry: Path) -> bool:
    try:
        return re.fullmatch(_READ_ONLY, (entry / "cmdline").read_bytes()) is not None
    except OSError:
        return False


def running_package_managers(proc: Path = Path("/proc")) -> tuple[str, ...]:
    """The package managers running now, by process name, each once."""
    found: list[str] = []
    try:
        entries = list(proc.iterdir())
    except OSError:
        return ()
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if name == "pacman" and _pacman_query(entry):
            continue
        if name in PACKAGE_MANAGERS and name not in found:
            found.append(name)
    return tuple(found)


def boot_time(proc: Path = Path("/proc")) -> float | None:
    try:
        for line in (proc / "stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def lock_state(
    lock: Path | None = None,
    *,
    proc: Path = Path("/proc"),
    pacman_present: bool | None = None,
) -> dict:
    """``{"state", "path", "holders", "from_previous_boot"}`` for the card and the notice."""
    if pacman_present is None:
        pacman_present = shutil.which("pacman") is not None
    path = lock if lock is not None else (lock_path() if pacman_present else DEFAULT_LOCK)
    result = {"state": NOT_APPLICABLE, "path": str(path), "holders": (), "from_previous_boot": False}
    if not pacman_present:
        return result
    try:
        modified = path.stat().st_mtime
    except FileNotFoundError:
        result["state"] = FREE
        return result
    except OSError:
        # Unreadable is not "free": say nothing rather than guess.
        result["state"] = NOT_APPLICABLE
        return result
    holders = running_package_managers(proc)
    booted = boot_time(proc)
    previous_boot = booted is not None and modified < booted
    result["holders"] = holders
    result["from_previous_boot"] = previous_boot
    # A lock older than this boot was not made by anything running now, but
    # pacman itself still must not be running while it goes.
    if "pacman" in holders or (holders and not previous_boot):
        result["state"] = IN_USE
    else:
        result["state"] = STALE
    return result


def release_command(lock: Path | None = None) -> str:
    """The terminal workflow that removes a stale lock, checking again as root first.

    It fails closed: no pgrep, an unexpected path or a running package manager
    stops it with nothing removed.
    """
    path = lock if lock is not None else lock_path()
    text = str(path)
    if not text.startswith("/") or path.name != "db.lck":
        raise ValueError("Unexpected pacman lock path")
    quoted = shlex.quote(text)
    managers = "|".join(PACKAGE_MANAGERS)
    # The terminal may run outside the app's Python environment.
    query_check = shlex.quote(
        "import re,sys; from pathlib import Path; "
        f"sys.exit(0 if re.fullmatch({_READ_ONLY!r}, Path(sys.argv[1]).read_bytes()) else 1)"
    )
    script = "; ".join((
        "set -u",
        f"bc250_lock={quoted}",
        'echo "== pacman database lock: $bc250_lock =="',
        'if [ ! -e "$bc250_lock" ]; then echo "OK: pacman is not locked; nothing was changed."; exit 0; fi',
        "command -v pgrep >/dev/null 2>&1 || "
        '{ echo "ERROR: pgrep is missing, so a running package manager cannot be ruled out; the lock was left in place."; exit 1; }',
        'exec 3< "$bc250_lock" || exit 1',
        'bc250_boot="$(awk \'/^btime /{print $2}\' /proc/stat 2>/dev/null)"',
        'bc250_mtime="$(stat -Lc %Y /dev/fd/3 2>/dev/null)" || exit 1',
        'bc250_old=0; [ -n "$bc250_boot" ] && [ "$bc250_mtime" -lt "$bc250_boot" ] && bc250_old=1',
        'for bc250_try in 1 2 3 4; do bc250_running=; bc250_busy=0; '
        f"bc250_list=$(pgrep -x -l '{managers}') || {{ [ \"$?\" -eq 1 ] || exit 1; }}; "
        'while read -r pid name; do [ -n "$name" ] || continue; '
        f'if [ "$name" = pacman ] && python3 -I -c {query_check} "/proc/$pid/cmdline" 2>/dev/null; then continue; fi; '
        'bc250_running="${bc250_running:+$bc250_running }$name"; '
        '[ "$name" = pacman ] || [ "$bc250_old" -eq 0 ] || continue; bc250_busy=1; '
        'done <<< "$bc250_list"; [ "$bc250_busy" -eq 1 ] || break; '
        '[ "$bc250_try" -eq 4 ] || sleep 1; done',
        'if [ "$bc250_busy" -eq 1 ]; then '
        'echo "ERROR: A package manager is still running ($bc250_running), so pacman is busy. '
        'Nothing was removed: let it finish or close it, then check again."; exit 1; fi',
        '[ -n "$bc250_running" ] && echo "[INFO] $bc250_running is open, but the lock is older than this boot, so it was left by an interrupted update."',
        # A transaction may have replaced the original lock during the wait.
        'if [ "$bc250_lock" -ef /dev/fd/3 ]; then rm -f -- "$bc250_lock"; fi',
        'if [ -e "$bc250_lock" ]; then echo "ERROR: The lock could not be removed."; exit 1; fi',
        'echo "OK: The pacman lock was removed. Run sudo pacman -Syu once to finish the interrupted update, then try the action again."',
    ))
    return "sudo bash -c " + shlex.quote(script)
