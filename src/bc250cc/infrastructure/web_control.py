"""Control of the local web interface: its settings, access key, and the user service that keeps it up.

The server itself is ``frontends/web``. This module is what the desktop page
and the server share: ``web.json`` (0600, owner only) holds the access key and
the options, and an optional systemd user service or XDG desktop autostart
entry starts the server with the session. A user service lives in the user manager, which Bazzite's Game Mode
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
from bc250cc.infrastructure.persistence.config_paths import app_config_dir, app_data_dir
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
        # On disk before the rename: a power cut must not leave an empty file.
        handle.flush()
        os.fsync(handle.fileno())
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


def _desktop_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".config") / "autostart" / "bc250-web.desktop"


def _desktop_quote(value: str) -> str:
    # Desktop Exec syntax is not shell syntax. Escape reserved characters and
    # literal percent signs (field codes), including paths containing spaces.
    if any(c in value for c in "\n\r\x00"):
        raise ValueError("Invalid desktop autostart argument")
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%') + '"'


def _command() -> list[str]:
    # Packaged installs use the system runtime. Source installs can keep web
    # dependencies in their own stable environment, without altering system Python.
    candidates = [Path(sys.executable), app_data_dir() / "web-runtime" / "bin" / "python"]
    for interpreter in dict.fromkeys(candidates):
        if not interpreter.is_file():
            continue
        try:
            probe = subprocess.run([str(interpreter), "-c", "import frontends.web.server"],
                                   cwd=APP_ROOT, env={**os.environ, **_environment()},
                                   capture_output=True, timeout=10, check=False)
            if probe.returncode == 0:
                return [str(interpreter), "-m", "frontends.web"]
        except (OSError, subprocess.SubprocessError):
            continue
    from bc250cc.infrastructure.web_runtime import prepare

    interpreter = prepare(APP_ROOT, app_data_dir() / "web-runtime")
    try:
        probe = subprocess.run([str(interpreter), "-c", "import frontends.web.server"],
                               cwd=APP_ROOT, env={**os.environ, **_environment()},
                               capture_output=True, timeout=10, check=False)
        if probe.returncode == 0:
            return [str(interpreter), "-m", "frontends.web"]
    except (OSError, subprocess.SubprocessError):
        pass
    raise ActionNeeded("The web server dependencies are unavailable after runtime preparation. Reinstall BC250 Control Center.")


def _environment() -> dict[str, str]:
    return {"PYTHONPATH": f"{APP_ROOT / 'src'}:{APP_ROOT}"}


def autostart_state() -> dict:
    systemd = systemd_available()
    path = _unit_path() if systemd else _desktop_path()
    ours = path.is_file() and path.read_text(encoding="utf-8").startswith(UNIT_MARKER)
    enabled = ours and (_systemctl("is-enabled", "--quiet", UNIT_FILE_NAME).returncode == 0
                        if systemd else "Hidden=true" not in path.read_text(encoding="utf-8"))
    return {"supported": True, "enabled": enabled, "foreign": path.is_file() and not ours,
            "backend": "systemd" if systemd else "xdg"}


def status() -> dict:
    """Everything the desktop page shows. The key is only revealed here, to the owner's own session."""
    opts = options()
    host = sorted(addresses())
    scheme = "https" if opts["tls"] else "http"
    from bc250cc.infrastructure import web_devices, web_firewall, web_network, web_tls
    running = _listening(opts["port"])
    local_name = web_network.local_hostname() if opts["lan"] and running else ""
    # Pairing offers the application's alias and the numeric fallback. The OS
    # hostname can still be valid for TLS, but must not replace this alias while
    # its publisher is stopped or is still starting.
    if local_name != web_network.LOCAL_ALIAS:
        local_name = ""
    urls = [f"{scheme}://{ip}:{opts['port']}" for ip in host] if opts["lan"] else []
    name_health = web_network.alias_health(published=local_name == web_network.LOCAL_ALIAS) if opts["lan"] and running else {"status": "disabled", "repairable": False}
    if local_name and name_health["status"] == "ready":
        urls.insert(0, f"{scheme}://{local_name}:{opts['port']}")
    return {"devices": web_devices.devices(), "networks": web_network.home_networks() if opts["lan"] else [],
            "trust_fingerprint": web_tls.fingerprint(web_tls.folder() / "authority.crt"),
            **opts, "running": running, "key": access_key(), "addresses": host,
            "urls": urls, "name_health": name_health,
            "firewall": web_firewall.inspect(opts["port"]) if opts["lan"] else {"state": "disabled"},
            "local_url": f"{scheme}://127.0.0.1:{opts['port']}", "autostart": autostart_state(),
            "tls_fingerprint": certificate_fingerprint() if opts["tls"] else ""}


#: What the owner reads when even the automatic repairs did not bring the
#: server up. Plain words: the technical cause is in the log, and the log is
#: in the problem report.
START_FAILED = (
    "Remote access could not start, even after Control Center tried to repair it. "
    "Restart the computer and try again. If it still does not start, send a problem "
    "report from Black Box: it includes the details."
)
PORT_TAKEN = (
    "Remote access could not start because another program is using its port. "
    "Close that program or restart the computer, then try again."
)


def _launch(command: list[str]) -> tuple[bool, object]:
    """Start the server once; (listening and alive, process or None)."""
    if systemd_available() and autostart_state()["enabled"]:
        set_autostart(True)  # Refresh ExecStart if the interpreter changed.
        process = None
    else:
        # Its output goes to a log, not to /dev/null: a server that died on
        # start used to leave nothing but "did not start" to go on.
        log = server_log_path()
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w", encoding="utf-8") as output:
            process = subprocess.Popen(  # nosec B603 - this interpreter, on the code that shows the window
                command, cwd=APP_ROOT, env={**os.environ, **_environment()}, start_new_session=True,
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            break
        # Listening and still alive: a server that binds and then dies on
        # its next line must not be reported as started.
        if _listening(options()["port"]) and (process is None or process.poll() is None):
            return True, process
        time.sleep(0.1)
    if process is not None and process.poll() is None:
        process.terminate()
    return False, process


def _repair_state_files() -> list[str]:
    """Set aside remote-access state that cannot be read; return what moved.

    Each of these is read as "nothing yet" when it is missing, so moving an
    unreadable one away is always safe: browsers pair again, a new key is made.
    """
    moved = []
    folder = app_config_dir()
    for name in ("web.json", "web-devices.json", "web-pairing.json"):
        path = folder / name
        try:
            raw = path.read_text(encoding="utf-8") if path.is_file() else None
        except OSError:
            raw = ""
        if raw is None:
            continue
        try:
            valid = not raw.strip() or isinstance(json.loads(raw), dict)
        except ValueError:
            valid = False
        if not valid:
            try:
                os.replace(path, path.with_name(f"{name}.corrupt-{int(time.time())}"))
                moved.append(name)
            except OSError:
                continue
    return moved


def _record_recovery(note: str) -> None:
    """Append what the automatic repair did, so a report shows it."""
    try:
        with open(server_log_path(), "a", encoding="utf-8") as log:
            log.write(f"\n[Control Center] {note}\n")
    except OSError:
        pass


def start() -> dict:
    """Start the server; repair what is known to stop it, and retry once.

    The owner presses one button and is not expected to read a traceback: a
    port held by an old copy of this same server is freed, a missing runtime
    is prepared again, unreadable state files are set aside. Only what is
    left after that is reported, in plain words.
    """
    if _listening(options()["port"]):
        return {"started": False}
    command = _command()  # Preflight before touching a running service or its unit.
    access_key()
    started, process = _launch(command)
    if started:
        return {"started": True}

    log = _server_log_text() if process is not None else ""
    if "Address already in use" in log or "Errno 98" in log:
        stop()  # Only our own pid file and unit: never another program.
        _record_recovery("port in use: stopped an earlier copy of this server and retried")
        if _listening(options()["port"]):
            raise ActionNeeded(PORT_TAKEN)
    elif "ModuleNotFoundError" in log or "ImportError" in log:
        from bc250cc.infrastructure.web_runtime import prepare

        prepare(APP_ROOT, app_data_dir() / "web-runtime")
        command = _command()
        _record_recovery("missing module: prepared the web runtime again and retried")
    else:
        moved = _repair_state_files()
        _record_recovery(
            "set aside unreadable " + ", ".join(moved) + " and retried" if moved else "retried once"
        )
    first_attempt = log
    started, process = _launch(command)
    if started:
        return {"started": True, "repaired": True}
    if first_attempt:
        _record_recovery("the first attempt ended with: " + _last_line(first_attempt))
    raise ActionNeeded(START_FAILED)


def _server_log_text() -> str:
    try:
        return server_log_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _last_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()[:300]
    return ""


def server_log_path() -> Path:
    return app_data_dir() / "web-server.log"


def last_server_error() -> str:
    """The last line the server printed, usually the exception that stopped it."""
    return _last_line(_server_log_text())


def configure(**changes) -> dict:
    """Validate a restart before stopping the working endpoint; restore on failure."""
    if set(changes) - {"lan", "tls"} or any(not isinstance(value, bool) for value in changes.values()):
        raise ValueError("Invalid web network option")
    previous = options()
    running = _listening(previous["port"])
    if running:
        _command()  # Missing dependencies must not bring down the live service.
        if changes.get("tls"):
            tls_certificate()
        stop()
    save_settings(**changes)
    try:
        if running:
            start()
    except Exception:
        save_settings(**{key: previous[key] for key in changes})
        try:
            start()
        except Exception:
            raise ActionNeeded("The web server could not restart. Its previous network settings were restored; check the runtime dependencies.") from None
        raise
    return options()


def stop() -> dict:
    if systemd_available() and autostart_state()["enabled"]:
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
        path = _desktop_path()
        if path.exists() and not path.read_text(encoding="utf-8").startswith(UNIT_MARKER):
            raise ActionNeeded(f"{path} already exists and is not managed by Control Center; it was left as it is.")
        if enabled:
            command = ["/usr/bin/env", *(f"{key}={value}" for key, value in _environment().items()), *_command()]
            entry = (f"{UNIT_MARKER}\n[Desktop Entry]\nType=Application\n"
                     "Name=BC250 web access\nTerminal=false\n"
                     f"Exec={' '.join(_desktop_quote(arg) for arg in command)}\n"
                     f"Path={APP_ROOT}\n")
            access_key()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(entry, encoding="utf-8")
        elif path.is_file():
            path.unlink()
        return autostart_state()
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
        # Enabling boot persistence must not start a second instance beside a
        # manually launched server or interrupt its authenticated browsers.
        enable_args = ("enable", UNIT_FILE_NAME) if _listening(options()["port"]) else \
            ("enable", "--now", UNIT_FILE_NAME)
        for args in (("daemon-reload",), enable_args):
            result = _systemctl(*args)
            if result.returncode != 0:
                raise RuntimeError(f"systemctl --user {' '.join(args)} failed: {(result.stderr or '').strip()}")
    elif path.is_file():
        # This switch controls future sessions; Stop web access owns shutdown.
        _systemctl("disable", UNIT_FILE_NAME)
        path.unlink()
        _systemctl("daemon-reload")
    return autostart_state()


def repair_local_name() -> dict:
    """Only the installed, protected helper may change resolver configuration."""
    from bc250cc.infrastructure.system_setup import HELPER

    if not HELPER.is_file() or '"mdns-repair"' not in HELPER.read_text(encoding="utf-8"):
        raise ActionNeeded("Update or reinstall Control Center to install the local name repair helper.")
    result = subprocess.run(["pkexec", str(HELPER), "mdns-repair"], capture_output=True,
                            text=True, timeout=240, check=False)
    if result.returncode:
        raise ActionNeeded(result.stderr.strip() or "Local name repair was cancelled or failed.")
    from bc250cc.infrastructure.web_network import alias_health

    health = alias_health()
    if health["status"] != "ready":
        raise ActionNeeded("Local name resolution is still unavailable. Use the numeric address.")
    return health


def repair_firewall() -> dict:
    from bc250cc.infrastructure.web_firewall import repair

    return repair(options()["port"])
