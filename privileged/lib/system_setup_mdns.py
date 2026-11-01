"""Repair the Avahi to NSS bridge without replacing the host resolver."""
from __future__ import annotations

import json
import re

from system_setup_common import STATE, SetupError


def _module_installed(host):
    return any(list(host.path(base).glob("libnss_mdns4_minimal.so.2")) or
               list(host.path(base).glob("*/libnss_mdns4_minimal.so.2"))
               for base in ("/usr/lib", "/usr/lib64", "/lib", "/lib64"))


def _prepare(host):
    if not host.command("avahi-resolve-host-name") or not _module_installed(host):
        if host.immutable_image():
            raise SetupError("The system image lacks Avahi or its mDNS resolver. Prepare the system components and reboot before retrying; the numeric address remains available.")
        commands = {
            "arch": ("pacman", "-S", "--needed", "--noconfirm", "avahi", "nss-mdns"),
            "debian": ("apt-get", "install", "-y", "avahi-daemon", "avahi-utils", "libnss-mdns"),
            "fedora": ("dnf", "install", "-y", "avahi", "avahi-tools", "nss-mdns"),
        }
        command = commands.get(host.distro_family())
        if not command:
            raise SetupError("Automatic mDNS dependency installation is unavailable on this distribution. The numeric address remains available.")
        host.run(*command, timeout=180)
        if not host.command("avahi-resolve-host-name") or not _module_installed(host):
            raise SetupError("The mDNS packages are not available after installation. The numeric address remains available.")
    # Preserve the current service policy when Avahi already answers.
    try:
        return host.run("avahi-resolve-host-name", "-4", "bc250cc.local", timeout=5)
    except SetupError:
        if host.path("/run/systemd/system").is_dir():
            host.run("systemctl", "enable", "--now", "avahi-daemon.service")
        elif host.openrc():
            host.run("rc-update", "add", "avahi-daemon", "default")
            host.run("rc-service", "avahi-daemon", "start")
        else:
            raise SetupError("The Avahi service manager is unsupported. The numeric address remains available.") from None
        # LanAlias refreshes every two seconds; the resolver waits for its reply.
        return host.run("avahi-resolve-host-name", "-4", "bc250cc.local", timeout=8)


def repair(host):
    # Validate the file before installing packages or changing service policy.
    path = host.safe("/etc/nsswitch.conf")
    original = path.read_text(encoding="utf-8")
    if any(token in original.lower() for token in ("authselect", "automatically generated", "do not edit")):
        raise SetupError("The resolver configuration is managed by another system tool; it was preserved. Use the numeric address.")
    matches = list(re.finditer(r"^hosts:[^\n]*", original, re.MULTILINE))
    if len(matches) != 1 or "\\" in matches[0].group():
        raise SetupError("The hosts resolver configuration is ambiguous; it was preserved.")
    match = matches[0]
    line = match.group()
    # Remove existing mDNS modules and their action clauses before inserting
    # the bridge ahead of resolve, which can otherwise stop with NOTFOUND.
    body, separator, comment = line.partition("#")
    body = re.sub(r"\bmdns(?:4|6)?(?:_minimal)?\b(?:[ \t]+\[[^]\n]*\])?", "", body)
    body = re.sub(r"[ \t]+", " ", body).rstrip()
    body = body.replace("hosts: ", "hosts: mdns4_minimal [NOTFOUND=return] ", 1)
    if not body.startswith("hosts: mdns4_minimal "):
        raise SetupError("The hosts resolver configuration is unsupported; it was preserved.")
    advertised = _prepare(host).split()
    interfaces = json.loads(host.run("ip", "-j", "-4", "addr", "show"))
    own = {item.get("local") for link in interfaces for item in link.get("addr_info", [])}
    if len(advertised) != 2 or advertised[0] != "bc250cc.local" or advertised[1] not in own:
        raise SetupError("The local name belongs to another device or is not advertised. Resolver settings were preserved.")
    updated = original[:match.start()] + body + ((" #" + comment) if separator else "") + original[match.end():]
    backup = f"{STATE}/nsswitch.conf.before-mdns"
    if updated != original:
        if not host.safe(backup).exists():
            host.write(backup, original, mode=0o600)
        host.write("/etc/nsswitch.conf", updated, mode=path.stat().st_mode & 0o777)
    try:
        resolved = host.run("getent", "ahostsv4", "bc250cc.local", timeout=8).splitlines()
        if len(advertised) != 2 or not any(row.split() and row.split()[0] == advertised[1] for row in resolved):
            raise SetupError("The local name still does not resolve to the advertised address.")
    except (SetupError, OSError):
        if updated != original:
            host.write("/etc/nsswitch.conf", original, mode=path.stat().st_mode & 0o777)
        raise
    return {"verified": True, "changed": updated != original, "backup": backup if updated != original else ""}
