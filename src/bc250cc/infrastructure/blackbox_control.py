"""Start, stop and read the black box from the interface.

``blackbox.record`` is the recorder (the CLI's ``black-box``). This module is
what the window uses around it: whether it is recording, a way to start it that
survives closing the application, a way to stop it that lets it write the
"stopped" line, the rows it has written, and an optional user service that
starts it with the session.

Nothing here needs root. systemd's user manager is used where there is one, so
a recording started in Desktop Mode keeps running into Game Mode (the README's
``systemd-run --user`` recipe); anywhere else the recorder is a detached
process.
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from bc250cc.infrastructure import blackbox
from bc250cc.shared.errors import ActionNeeded

UNIT = "bc250-black-box"
UNIT_FILE_NAME = f"{UNIT}.service"
UNIT_MARKER = "# Managed by BC250 Control Center"

Runner = Callable[..., subprocess.CompletedProcess]


def unit_path(home: Path | None = None) -> Path:
    config = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(config) if config else (home or Path.home()) / ".config"
    return base / "systemd" / "user" / UNIT_FILE_NAME


def systemd_available(system_dir: Path = Path("/run/systemd/system")) -> bool:
    """A systemd user manager to hand the recorder to (systemd must be PID 1)."""
    return system_dir.is_dir() and shutil.which("systemctl") is not None


def recorder_command() -> list[str]:
    """What runs the recorder: this interpreter, on the very code that shows the window.

    The installed ``bc250-control-center-cli`` may be an older release than the
    window that started it (a checkout run with ./run.sh beside an installed
    package): its recorder writes no pid file, so the window could not tell
    that it was recording.
    """
    return [sys.executable, "-m", "bc250cc.infrastructure.blackbox"]


def _environment() -> dict[str, str]:
    """The environment the recorder needs when this code is not installed system-wide."""
    package_parent = str(Path(blackbox.__file__).resolve().parents[2])
    existing = os.environ.get("PYTHONPATH", "")
    if package_parent in existing.split(":"):
        return {"PYTHONPATH": existing}
    return {"PYTHONPATH": f"{package_parent}:{existing}" if existing else package_parent}


def _systemctl(*args: str, runner: Runner = subprocess.run) -> subprocess.CompletedProcess:
    return runner(
        ["systemctl", "--user", *args],
        capture_output=True, text=True, timeout=15, check=False,
    )


def _unit_active(runner: Runner = subprocess.run) -> bool:
    try:
        return _systemctl("is-active", "--quiet", UNIT_FILE_NAME, runner=runner).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def autostart_state(*, home: Path | None = None, runner: Runner = subprocess.run) -> dict:
    """Whether the user service that starts it with the session is there."""
    supported = systemd_available()
    path = unit_path(home)
    exists = path.is_file()
    ours = False
    if exists:
        try:
            ours = path.read_text(encoding="utf-8").startswith(UNIT_MARKER)
        except OSError:
            ours = False
    enabled = False
    if supported and ours:
        try:
            enabled = _systemctl("is-enabled", "--quiet", UNIT_FILE_NAME, runner=runner).returncode == 0
        except (OSError, subprocess.SubprocessError):
            enabled = False
    return {"supported": supported, "enabled": enabled, "foreign": exists and not ours}


def status(*, rows: int | None = None, directory: Path | None = None, home: Path | None = None,
           runner: Runner = subprocess.run) -> dict:
    """Everything the page shows, in one read."""
    directory = directory or blackbox.log_directory()
    pid = blackbox.running_pid(directory)
    unit_on = systemd_available() and _unit_active(runner)
    running = pid is not None or unit_on or blackbox.recently_written(directory)
    session = blackbox.read_session(directory, lines=rows)
    parsed = [sample for sample in map(blackbox.parse_sample, session["rows"]) if sample]
    sensors = blackbox.Sensors()
    return {
        "supported": bool(sensors.device),
        "running": running,
        "pid": pid,
        "autostart": autostart_state(home=home, runner=runner),
        "directory": str(directory),
        "state": session["state"],
        "state_text": session["text"],
        "header": session["header"],
        # Newest first: the end of a recording is the part that matters.
        "rows": list(reversed(parsed)),
    }


def start(*, directory: Path | None = None, runner: Runner = subprocess.run,
          popen: Callable[..., object] = subprocess.Popen) -> dict:
    """Start recording, unless it already is. Survives closing the application."""
    directory = directory or blackbox.log_directory()
    if blackbox.running_pid(directory) is not None or (systemd_available() and _unit_active(runner)):
        return {"started": False, "reason": "already-recording"}
    if not blackbox.Sensors().device:
        raise RuntimeError("The BC-250 GPU (1002:13fe) was not found in /sys/class/drm.")
    if systemd_available():
        if unit_path().is_file():
            # The service this app installed: start that one, under its own name.
            result = _systemctl("start", UNIT_FILE_NAME, runner=runner)
        else:
            environment = [f"--setenv={key}={value}" for key, value in _environment().items()]
            result = runner(
                ["systemd-run", "--user", f"--unit={UNIT}", "--collect", *environment, *recorder_command()],
                capture_output=True, text=True, timeout=15, check=False,
            )
        if result.returncode != 0:
            raise RuntimeError(
                "systemd could not start the black box: " + (result.stderr or result.stdout or "").strip()
            )
        return {"started": True, "via": "systemd"}
    popen(
        recorder_command(),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, env={**os.environ, **_environment()},
    )
    return {"started": True, "via": "process"}


def _recording(directory: Path, runner: Runner) -> bool:
    return (
        blackbox.running_pid(directory) is not None
        or bool(blackbox.recorder_pids())
        or (systemd_available() and _unit_active(runner))
    )


def stop(*, directory: Path | None = None, runner: Runner = subprocess.run,
         kill: Callable[[int, int], None] = os.kill, wait: float = 3.0) -> dict:
    """Stop every recorder so that the file ends with its "stopped" line.

    SIGINT is what Ctrl+C sends and every release of the recorder ends cleanly
    on it; SIGTERM, which systemd's stop sends, is only handled from this
    release on. So the unit is asked with SIGINT first and stopped properly
    only if it stays.
    """
    directory = directory or blackbox.log_directory()
    unit_on = systemd_available() and _unit_active(runner)
    pids = sorted(set(blackbox.recorder_pids()) | ({blackbox.running_pid(directory)} - {None}))
    if not pids and not unit_on:
        if blackbox.recently_written(directory):
            raise RuntimeError(
                "The black box is recording, but its process could not be found from here. "
                "Stop it with Ctrl+C in the terminal that started it."
            )
        return {"stopped": False, "reason": "not-recording"}
    if unit_on:
        _systemctl("kill", "--signal=SIGINT", UNIT_FILE_NAME, runner=runner)
    for pid in pids:
        try:
            kill(pid, signal.SIGINT)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and _recording(directory, runner):
        time.sleep(0.05)
    if unit_on and systemd_available() and _unit_active(runner):
        _systemctl("stop", UNIT_FILE_NAME, runner=runner)
        time.sleep(0.2)
    return {"stopped": not _recording(directory, runner)}


def _unit_text() -> str:
    command = " ".join(shlex.quote(part) for part in recorder_command())
    environment = "".join(f'Environment="{key}={value}"\n' for key, value in _environment().items())
    return (
        f"{UNIT_MARKER}\n"
        "[Unit]\nDescription=BC250 Control Center black box (GPU log kept for the next report)\n\n"
        f"[Service]\nExecStart={command}\n{environment}Restart=on-failure\nRestartSec=5\n\n"
        "[Install]\nWantedBy=default.target\n"
    )


def set_autostart(enabled: bool, *, home: Path | None = None, runner: Runner = subprocess.run) -> dict:
    """Start the black box with the session (a systemd user service), or stop doing so."""
    if not systemd_available():
        raise ActionNeeded("Starting with the session needs systemd; this system uses another init.")
    path = unit_path(home)
    if path.is_file():
        try:
            ours = path.read_text(encoding="utf-8").startswith(UNIT_MARKER)
        except OSError:
            ours = False
        if not ours:
            raise ActionNeeded(
                f"{path} already exists and is not managed by Control Center; it was left as it is."
            )
    if enabled:
        # A recording started by hand runs under this very unit name.
        if blackbox.running_pid() is not None and not path.is_file():
            stop(runner=runner)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(_unit_text(), encoding="utf-8")
        os.replace(temporary, path)
        for args in (("daemon-reload",), ("enable", "--now", UNIT_FILE_NAME)):
            result = _systemctl(*args, runner=runner)
            if result.returncode != 0:
                raise RuntimeError(f"systemctl --user {' '.join(args)} failed: {(result.stderr or '').strip()}")
    elif path.is_file():
        _systemctl("disable", "--now", UNIT_FILE_NAME, runner=runner)
        path.unlink()
        _systemctl("daemon-reload", runner=runner)
    return autostart_state(home=home, runner=runner)
