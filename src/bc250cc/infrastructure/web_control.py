"""Control of the local web interface: its settings, access key, and the user service that keeps it up.

The server itself is ``frontends/web``. This module is what the desktop page
and the server share: ``web.json`` (0600, owner only) holds the access key and
the options, and an optional systemd user service starts the server with the
session. A user service lives in the user manager, which Bazzite's Game Mode
leaves running, so the page stays reachable after switching modes.
Nothing here needs root.
"""

from __future__ import annotations

import hashlib
import json
import os
import pwd
import secrets
import shlex
import signal
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

from bc250cc.infrastructure.blackbox_control import systemd_available
from bc250cc.infrastructure.persistence.config_paths import app_config_dir
from bc250cc.infrastructure.remote_access import addresses
from bc250cc.shared.errors import ActionNeeded, BoundaryError, ErrorDetail

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
            "lan_password": bool(data.get("lan_password", False)), "tls": bool(data.get("tls", True))}


def ssh_target() -> dict:
    """Pin loopback SSH to host keys read from the local, root-owned SSH configuration."""
    from bc250cc.infrastructure.remote_access import _port

    port = _port()
    keys = []
    for path in Path("/etc/ssh").glob("ssh_host_*_key.pub"):
        try:
            if path.stat().st_uid != 0 or path.stat().st_mode & 0o022:
                continue
            fields = path.read_text(encoding="ascii").split()
            if len(fields) >= 2:
                keys.append(f"[127.0.0.1]:{port} {fields[0]} {fields[1]}\n")
                if port == 22:
                    keys.append(f"127.0.0.1 {fields[0]} {fields[1]}\n")
        except (OSError, UnicodeError):
            continue
    if not keys:
        raise BoundaryError(ErrorDetail("BC250-CMD-001",
                                        "No SSH server is installed. Install the openssh-server package first."))
    return {"port": port, "user": pwd.getpwuid(os.getuid()).pw_name, "known_hosts": "".join(keys),
            "root": str(APP_ROOT), "pythonpath": f"{APP_ROOT / 'src'}:{APP_ROOT}", "python": sys.executable}


def tls_certificate() -> tuple[Path, Path]:
    from bc250cc.infrastructure.web_tls import certificate
    return certificate()


def pairing_svg(url: str) -> bytes:
    from bc250cc._vendor.qrcodegen import QrCode

    qr = QrCode.encode_text(url, QrCode.Ecc.MEDIUM)
    size = qr.get_size()
    squares = "".join(f"M{x+4},{y+4}h1v1h-1z" for y in range(size) for x in range(size) if qr.get_module(x, y))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size+8} {size+8}">'
            f'<rect width="100%" height="100%" fill="white"/><path d="{squares}" fill="black"/></svg>').encode()


def certificate_fingerprint() -> str:
    try:
        pem = (app_config_dir() / "web-tls" / "certificate.pem").read_text(encoding="ascii")
        digest = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest().upper()
        return ":".join(digest[i:i+2] for i in range(0, len(digest), 2))
    except (OSError, ValueError):
        return ""


def _pid_path(port: int | None = None) -> Path:
    name = f"bc250-web-{port}.pid" if port is not None and port != options()["port"] else "bc250-web.pid"
    return Path(os.environ.get("XDG_RUNTIME_DIR") or app_config_dir()) / name


def write_pid(port: int | None = None) -> None:
    _pid_path(port).write_text(str(os.getpid()), encoding="utf-8")


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
    scheme = "https" if opts["tls"] else "http"
    from bc250cc.infrastructure import web_devices, web_network, web_tls
    return {"devices": web_devices.devices(), "networks": web_network.home_networks() if opts["lan"] else [],
            "trust_fingerprint": web_tls.fingerprint(web_tls.folder() / "authority.crt"),
            **opts, "running": _listening(opts["port"]), "key": access_key(), "addresses": host,
            "urls": [f"{scheme}://{ip}:{opts['port']}" for ip in host] if opts["lan"] else [],
            "local_url": f"{scheme}://127.0.0.1:{opts['port']}", "autostart": autostart_state(),
            "tls_fingerprint": certificate_fingerprint() if opts["tls"] else ""}


def start() -> dict:
    if _listening(options()["port"]):
        return {"started": False}
    import importlib.util
    if importlib.util.find_spec("cheroot") is None:
        raise ActionNeeded("The web interface requires Cheroot. Install requirements-web.txt with this Python interpreter, or the distribution's python3-cheroot package.")
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
