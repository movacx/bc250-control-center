"""SteamOS' read-only root: read it, remember what it was, put it back.

The Real Toolkit lifts the protection itself (``steamos-readonly disable``) and
turns it back on blindly afterwards, whatever the root was before. Control
Center runs it as a child and answers for the state it leaves behind, so this
module covers the cases around that:

* ``steamos-readonly status`` prints the state and exits 1 while the root is
  writable. The text is the answer; the exit status is not.
* The state before the run is written to disk before the toolkit starts. A
  power cut, a killed terminal or a reboot skips every ``finally``; the next
  run (or the interface) finds that note, sees the root still unlocked and
  puts the original state back instead of adopting the leak as the original.
* Restoring is verified and retried, and when it still fails the exact command
  is printed.
* ``/var`` on SteamOS is a small partition that package installs fill.

Nothing here needs more than the standard library, because the privileged
runtime that imports it is a zipped copy with a closed module list.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .steamos_readonly import _state_from

READONLY_COMMAND = '/usr/bin/steamos-readonly'
SESSION_FILE = 'root-session.json'
BOOT_ID = Path('/proc/sys/kernel/random/boot_id')

#: Below this a package install stops half way and blames "/etc too full".
VAR_REFUSE_MB = 40
#: It works, but the next install may not.
VAR_WARN_MB = 250

PROTECTED, WRITABLE, UNKNOWN, UNAVAILABLE = 'enabled', 'disabled', 'unknown', 'unavailable'
KNOWN = (PROTECTED, WRITABLE)


@dataclass(frozen=True)
class RootReading:
    state: str
    status: int | None = None
    detail: str = ''


def read_root(*, runner: Callable[..., subprocess.CompletedProcess] | None = None,
              command: str = READONLY_COMMAND, attempts: int = 2, timeout: float = 10,
              sleep: Callable[[float], None] = time.sleep) -> RootReading:
    """The root's state from what ``steamos-readonly status`` says.

    ``unavailable`` when the command does not exist. An answer that names
    neither state is retried once (the command can be slow while systemd is
    busy) and then reported as ``unknown`` with what it said.
    """
    reading = RootReading(UNKNOWN)
    for attempt in range(max(1, attempts)):
        try:
            # Looked up now, not at import: callers and tests may replace it.
            result = (runner or subprocess.run)([command, 'status'], check=False, capture_output=True, text=True,
                            timeout=timeout, env={**os.environ, 'LANG': 'C', 'LC_ALL': 'C'})
        except FileNotFoundError:
            return RootReading(UNAVAILABLE, None, command + ' was not found')
        except (OSError, subprocess.SubprocessError) as error:
            reading = RootReading(UNKNOWN, None, type(error).__name__ + ': ' + str(error))
        else:
            text = (result.stdout or '') + '\n' + (result.stderr or '')
            reading = RootReading(_state_from(text), result.returncode, ' '.join(text.split()))
            if reading.state in KNOWN:
                return reading
        if attempt + 1 < attempts:
            sleep(0.5)
    return reading


def explain_unreadable(reading: RootReading) -> str:
    """Why an action did not start, with what the command actually said."""
    if reading.state == UNAVAILABLE:
        return ('steamos-readonly was not found, so the SteamOS root state cannot be read; '
                'the toolkit action was not started. This action is for SteamOS.')
    said = reading.detail[:200] or 'nothing'
    code = 'no exit status' if reading.status is None else 'exit status ' + str(reading.status)
    return ('Cannot determine SteamOS read-only mode; the toolkit action was not started. '
            "`steamos-readonly status` said (" + code + '): ' + repr(said) + '. '
            "Run it in a terminal; if it answers 'enabled' or 'disabled', try the action again.")


# --- the note that outlives the process --------------------------------------------------

def boot_id() -> str:
    try:
        return BOOT_ID.read_text(encoding='ascii').strip()
    except OSError:
        return ''


def _start_ticks(pid: int) -> str:
    """Field 22 of /proc/PID/stat: tells a process from a later one with the same PID."""
    try:
        stat = Path('/proc', str(pid), 'stat').read_text(encoding='ascii', errors='replace')
        return stat.rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return ''


def write_session(state_root: Path, *, initial: str, action: str, pid: int | None = None) -> None:
    """Record the state to restore, before anything can change it."""
    if initial not in KNOWN:
        raise ValueError('Only a known root state can be recorded')
    pid = os.getpid() if pid is None else pid
    payload = {'initial': initial, 'action': action, 'pid': pid, 'start_ticks': _start_ticks(pid),
               'boot_id': boot_id(), 'started': int(time.time())}
    state_root.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix='.session-', dir=state_root)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(payload, output)
        os.chmod(name, 0o644)
        os.replace(name, state_root / SESSION_FILE)
    finally:
        Path(name).unlink(missing_ok=True)


def read_session(state_root: Path) -> dict | None:
    try:
        payload = json.loads((Path(state_root) / SESSION_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get('initial') not in KNOWN:
        return None
    return payload


def clear_session(state_root: Path) -> None:
    (Path(state_root) / SESSION_FILE).unlink(missing_ok=True)


def session_running(session: Mapping[str, object] | None) -> bool:
    """True while the process that wrote the note is the one running now."""
    if not session:
        return False
    try:
        pid = int(session.get('pid') or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or str(session.get('boot_id') or '') != boot_id():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    ticks = str(session.get('start_ticks') or '')
    return not ticks or ticks == _start_ticks(pid)


def initial_state(current: RootReading, session: Mapping[str, object] | None) -> tuple[str, str]:
    """The state to give back, and a sentence when this is not simply "what it is now".

    Only one case overrides what is read: an earlier run died without restoring
    (its process is gone), it began with the root protected, and the root is
    writable now. Then the writable state is its leftover, not the user's choice.
    """
    if (session and not session_running(session) and session.get('initial') == PROTECTED
            and current.state == WRITABLE):
        return PROTECTED, ('An earlier toolkit action (' + str(session.get('action') or 'unknown')
                           + ') ended without locking the system again; its protection will be restored.')
    return current.state, ''


def interrupted(read: RootReading, session: Mapping[str, object] | None) -> bool:
    """For the interface: an action died and the root is still unlocked."""
    return bool(session) and not session_running(session) and \
        session.get('initial') == PROTECTED and read.state == WRITABLE


def session_summary(state_root: Path, read: RootReading | None = None) -> dict[str, object]:
    session = read_session(state_root)
    running = session_running(session)
    return {
        'running': running,
        'action': str((session or {}).get('action') or ''),
        'restore_pending': bool(read is not None and interrupted(read, session)),
    }


# --- space -------------------------------------------------------------------

def var_space(statvfs: Callable[[str], os.statvfs_result] = os.statvfs) -> tuple[int | None, str]:
    """Free MB on /var and ``ok``, ``low`` or ``critical`` (``unknown`` if unreadable)."""
    try:
        stats = statvfs('/var')
    except OSError:
        return None, 'unknown'
    free = int(stats.f_bavail * stats.f_frsize // (1024 * 1024))
    return free, 'critical' if free < VAR_REFUSE_MB else 'low' if free < VAR_WARN_MB else 'ok'


#: SteamOS' system partition is about 5 GB and arrives nearly full. Packages the
#: toolkit installs there (headers, build tools, drivers) stop half way when it fills.
ROOT_WARN_MB = 300


def root_space(statvfs: Callable[[str], os.statvfs_result] = os.statvfs) -> tuple[int | None, str]:
    """Free MB on the system partition (/) and ``ok`` or ``low`` (``unknown`` if unreadable).

    Only a warning: actions that write /etc, /boot or /home need no room here.
    """
    try:
        stats = statvfs('/')
    except OSError:
        return None, 'unknown'
    free = int(stats.f_bavail * stats.f_frsize // (1024 * 1024))
    return free, 'low' if free < ROOT_WARN_MB else 'ok'


VAR_HELP = (
    "SteamOS keeps /var small, and a full /var breaks package installs half way. To free space:\n"
    "  sudo pacman -Scc                     # downloaded packages; answer y\n"
    "  sudo rm -rf /var/cache/fwupd/*       # firmware metadata; fwupd downloads it again\n"
    "  sudo journalctl --vacuum-size=20M    # system logs\n"
    "Control Center does the same with Free /var space, under SteamOS read-only mode in Preparation."
)
