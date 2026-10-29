"""Control of the local web interface: its settings, access key, and the user service that keeps it up.

The server itself is ``frontends/web``. This module is what the desktop page
and the server share: ``web.json`` (0600, owner only) holds the access key and
the options, and an optional systemd user service starts the server with the
session. A user service lives in the user manager, which Bazzite's Game Mode
leaves running, so the page stays reachable after switching modes.
Nothing here needs root.
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from bc250cc.infrastructure.blackbox_control import systemd_available
from bc250cc.infrastructure.persistence.config_paths import app_config_dir
from bc250cc.infrastructure.remote_access import addresses
from bc250cc.shared.errors import ActionNeeded

UNIT_FILE_NAME = "bc250-web.service"
UNIT_MARKER = "# Managed by BC250 Control Center"
DEFAULT_PORT = 8250
#: No 0/O/1/I/L: the key is read off a screen and typed with a thumb.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
APP_ROOT = Path(__file__).resolve().parents[3]


def settings_path() -> Path:
    return app_config_dir() / "web.json"


def read_settings() -> dict:
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def save_settings(**changes) -> dict:
    data = {**read_settings(), **changes}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(temporary, path)
    return data


def new_pin() -> str:
    code = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return f"{code[:4]}-{code[4:]}"


def access_key(*, renew: bool = False) -> str:
    """The key the page asks for. There is no way to run the server without one."""
    key = read_settings().get("pin", "")
    if renew or not key:
        key = new_pin()
        save_settings(pin=key)
    return key


def options() -> dict:
    data = read_settings()
    return {"port": int(data.get("port") or DEFAULT_PORT), "lan": bool(data.get("lan", False)),
            "lan_password": bool(data.get("lan_password", False))}


def _pid_path() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or app_config_dir()) / "bc250-web.pid"


def write_pid() -> None:
    _pid_path().write_text(str(os.getpid()), encoding="utf-8")


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=15, check=False)


def _unit_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".config") / "systemd" / "user" / UNIT_FILE_NAME


def _command() -> list[str]:
    return [sys.executable, "-m", "frontends.web"]


def _environment() -> dict[str, str]:
    return {"PYTHONPATH": f"{APP_ROOT / 'src'}:{APP_ROOT}"}


def autostart_state() -> dict:
    path = _unit_path()
    ours = path.is_file() and path.read_text(encoding="utf-8").startswith(UNIT_MARKER)
    enabled = systemd_available() and ours and _systemctl("is-enabled", "--quiet", UNIT_FILE_NAME).returncode == 0
    return {"supported": systemd_available(), "enabled": enabled, "foreign": path.is_file() and not ours}


def status() -> dict:
    """Everything the desktop page shows. The key is only revealed here, to the owner's own session."""
    opts = options()
    host = sorted(addresses())
    return {**opts, "running": _listening(opts["port"]), "key": access_key(), "addresses": host,
            "urls": [f"http://{ip}:{opts['port']}" for ip in host] if opts["lan"] else [],
            "local_url": f"http://127.0.0.1:{opts['port']}", "autostart": autostart_state()}


def start() -> dict:
    if _listening(options()["port"]):
        return {"started": False}
    access_key()
    if autostart_state()["enabled"]:
        _systemctl("start", UNIT_FILE_NAME)
    else:
        subprocess.Popen(  # nosec B603 - this interpreter, on the code that shows the window
            _command(), cwd=APP_ROOT, env={**os.environ, **_environment()}, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"started": True}


def stop() -> dict:
    if autostart_state()["enabled"]:
        _systemctl("stop", UNIT_FILE_NAME)
    try:
        os.kill(int(_pid_path().read_text(encoding="utf-8")), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    for _ in range(30):  # a restart right after must find the port free
        if not _listening(options()["port"]):
            break
        time.sleep(0.1)
    return {"stopped": True}


def set_autostart(enabled: bool) -> dict:
    if not systemd_available():
        raise ActionNeeded("Starting with the session needs systemd; this system uses another init.")
    path = _unit_path()
    if path.is_file() and not path.read_text(encoding="utf-8").startswith(UNIT_MARKER):
        raise ActionNeeded(f"{path} already exists and is not managed by Control Center; it was left as it is.")
    if enabled:
        access_key()
        path.parent.mkdir(parents=True, exist_ok=True)
        environment = "".join(f'Environment="{key}={value}"\n' for key, value in _environment().items())
        path.write_text(
            f"{UNIT_MARKER}\n[Unit]\nDescription=BC250 Control Center local web interface\n\n"
            f"[Service]\nWorkingDirectory={APP_ROOT}\nExecStart={' '.join(map(shlex.quote, _command()))}\n"
            f"{environment}Restart=on-failure\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n",
            encoding="utf-8")
        for args in (("daemon-reload",), ("enable", "--now", UNIT_FILE_NAME)):
            result = _systemctl(*args)
            if result.returncode != 0:
                raise RuntimeError(f"systemctl --user {' '.join(args)} failed: {(result.stderr or '').strip()}")
    elif path.is_file():
        _systemctl("disable", "--now", UNIT_FILE_NAME)
        path.unlink()
        _systemctl("daemon-reload")
    return autostart_state()
