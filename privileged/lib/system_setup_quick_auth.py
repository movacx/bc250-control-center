"""Let one account run the CPU, CU, GPU and fan helpers without its password.

Opt-in and off by default. Two managed files are written: a sudoers drop-in (web and terminal interface) and
a polkit rule (desktop). They name only root-owned helpers with closed, validated arguments and the exact
service commands of the two GPU governors. The core unlock helper runs code from the user's folder and the
setup, maintenance and GDDR6 helpers change the system, so none of them is here: they keep asking.
"""
from __future__ import annotations

import os
import pwd
import re
import tempfile

from system_setup_common import MARKER, SetupError

SUDOERS = "/etc/sudoers.d/zz-bc250-control-center"  # last: the last matching entry wins
POLKIT = "/etc/polkit-1/rules.d/49-bc250-control-center.rules"
POLKIT_MARKER = "// " + MARKER.removeprefix("# ")
STEAMOS_KEEP = "/etc/atomic-update.conf.d/bc250-control-center-quick-auth.conf"
LIBEXEC = "/usr/libexec/bc250-control-center/"
ACTION = "io.github.movacx.bc250-control-center."
HELPERS = {
    "bc250-cpu-smu-helper": "cpu-smu", "bc250-cu-helper": "compute-units",
    "bc250-fan-pwm-helper": "fan-pwm", "bc250-governor-config-helper": "governor-config",
    "bc250-service-helper": "service-control", "bc250-openrc-service-helper": "openrc-service",
}
GOVERNORS = ("cyan-skillfish-governor-smu", "oberon-governor")
SYSTEMCTL = ("unmask", "reset-failed", "enable --now", "disable --now", "restart", "start", "stop")
EXACT = (
    "/usr/bin/systemctl daemon-reload",
    "/usr/bin/udevadm trigger --action=change --subsystem-match=drm",
    "/usr/bin/udevadm settle --timeout=30",
    "/usr/bin/busctl --system call org.freedesktop.DBus /org/freedesktop/DBus org.freedesktop.DBus ReloadConfig",
)


def account(environment=None) -> str:
    """The person who authorized this, never a name taken from a request."""
    env = os.environ if environment is None else environment
    for name in ("PKEXEC_UID", "SUDO_UID"):
        value = str(env.get(name, "")).strip()
        if value.isdigit() and int(value) > 0:
            try:
                user = pwd.getpwuid(int(value)).pw_name
            except KeyError:
                break
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", user):
                return user
            raise SetupError("This account name cannot be written safely in the authorization rules")
    raise SetupError("Run this from Control Center with your own account")


def installed(host) -> list[str]:
    """The helpers that are really there and that only root can change."""
    ready = []
    for name in HELPERS:
        path = host.path(LIBEXEC + name)
        if not path.is_file():
            continue
        host.safe(LIBEXEC + name)
        ready.append(name)
    if not ready:
        raise SetupError("Update or reinstall Control Center to install its protected helpers")
    return ready


def commands(host) -> list[str]:
    lines = [LIBEXEC + name for name in installed(host)]
    if host.openrc():
        # Alpine and Gentoo keep it in different places; only the ones that exist are named.
        services = [f"{place} {name} {verb}" for place in ("/sbin/rc-service", "/usr/sbin/rc-service", "/usr/bin/rc-service")
                    if host.path(place).exists() for name in GOVERNORS for verb in ("restart", "start", "stop")]
        return lines + services
    services = [f"/usr/bin/systemctl {verb} {name}.service" for name in GOVERNORS for verb in SYSTEMCTL]
    return lines + services + list(EXACT)


def sudoers_text(host, user: str) -> str:
    escaped = [re.sub(r"([,:=\\])", r"\\\1", line) for line in commands(host)]
    return MARKER + "".join(f"{user} ALL=(root) NOPASSWD: {line}\n" for line in escaped)


def polkit_text(host, user: str) -> str:
    actions = ", ".join(f'"{ACTION}{HELPERS[name]}"' for name in installed(host))
    return (POLKIT_MARKER + "polkit.addRule(function(action, subject) {\n"
            f"    var allowed = [{actions}];\n"
            f'    if (subject.user == "{user}" && allowed.indexOf(action.id) >= 0) {{\n'
            "        return polkit.Result.YES;\n    }\n});\n")


def _remove(host, name: str, marker: str) -> None:
    path = host.safe(name)
    if not path.exists():
        return
    if not host.read(name).startswith(marker.strip()):
        raise SetupError(f"Foreign configuration preserved: {name}")
    path.unlink()


def _check_syntax(host, text: str) -> None:
    """A wrong sudoers file can lock everybody out of sudo: nothing is installed before visudo accepts it."""
    if not host.command("visudo"):
        raise SetupError("visudo is required to check the new rules; nothing was changed")
    fd, name = tempfile.mkstemp(prefix="bc250-sudoers-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.chmod(name, 0o440)
        host.run("visudo", "-cf", name, timeout=20)
    finally:
        os.unlink(name)


def status(host) -> dict:
    """Readable without root: the rules themselves live in folders only root can list."""
    state = host.state("quick-auth")
    return {"supported": host.path("/etc/sudoers.d").is_dir(), "enabled": bool(state.get("user")),
            "user": str(state.get("user") or "")}


def enable(host, user: str | None = None) -> dict:
    user = user or account()
    if not host.path("/etc/sudoers.d").is_dir():
        raise SetupError("This system does not read /etc/sudoers.d; nothing was changed")
    for name, marker in ((SUDOERS, MARKER), (POLKIT, POLKIT_MARKER)):
        if host.safe(name).exists() and not host.read(name).startswith(marker.strip()):
            raise SetupError(f"Existing configuration belongs to another tool: {name}")
    sudoers, polkit = sudoers_text(host, user), polkit_text(host, user)
    _check_syntax(host, sudoers)
    try:
        host.write(SUDOERS, sudoers, mode=0o440)
        host.run("visudo", "-c", timeout=20)
        listed = host.run("sudo", "-n", "-l", "-U", user, timeout=20)
        if installed(host)[0] not in listed:
            raise SetupError("sudo does not read the new rules on this system")
        if host.path("/etc/polkit-1/rules.d").is_dir():
            try:
                host.write(POLKIT, polkit)
            except SetupError as error:
                # Some distributions give this folder to polkitd: then only the desktop keeps asking.
                print(f"WARNING: the desktop will keep asking: {error}")
        if host.steamos():
            host.managed(STEAMOS_KEEP, f"{SUDOERS}\n{POLKIT}\n")
        host.save("quick-auth", {"user": user})
    except (SetupError, OSError):
        disable(host)
        raise
    return status(host)


def disable(host) -> dict:
    _remove(host, SUDOERS, MARKER)
    _remove(host, POLKIT, POLKIT_MARKER)
    host.remove_managed(STEAMOS_KEEP)
    host.save("quick-auth", {})
    return status(host)
