"""Repair the Avahi to NSS bridge without replacing the host resolver."""
from __future__ import annotations

import configparser
import json
from contextlib import contextmanager
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


AVAHI_CONFIG = "/etc/avahi/avahi-daemon.conf"
STEAMOS_KEEP = "/etc/atomic-update.conf.d/bc250-control-center-mdns.conf"


def _restart_avahi(host):
    if host.path("/run/systemd/system").is_dir():
        host.run("systemctl", "restart", "avahi-daemon.service")
    elif host.openrc():
        host.run("rc-service", "avahi-daemon", "restart")
    else:
        raise SetupError("The Avahi service manager is unsupported. The numeric address remains available.")


@contextmanager
def _publication_transaction(host):
    """Enable SteamOS user publication; undo configuration on any failed check."""
    change = {"changed": False, "backup": ""}
    if not host.steamos() or not host.path(AVAHI_CONFIG).exists():
        yield change
        return
    path = host.safe(AVAHI_CONFIG)
    original = path.read_text(encoding="utf-8")
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#", ";"))
    try:
        parser.read_string(original)
        disabled = {key for key in ("disable-publishing", "disable-user-service-publishing")
                    if parser.getboolean("publish", key, fallback=False)}
    except (configparser.Error, ValueError) as exc:
        raise SetupError("Avahi configuration is ambiguous or invalid; it was preserved.") from exc
    if not disabled:
        yield change
        return
    mode = path.stat().st_mode & 0o777
    section = ""
    lines = []
    for line in original.splitlines(keepends=True):
        header = re.match(r"^\s*\[([^]]+)\]", line)
        if header:
            section = header[1].strip()
        if section == "publish":
            for key in disabled:
                line = re.sub(r"^(\s*" + re.escape(key) + r"\s*=\s*)(yes|true|1)(?=\s|$)",
                              r"\g<1>no", line, flags=re.IGNORECASE)
        lines.append(line)
    updated = "".join(lines)
    if updated == original:
        raise SetupError("Avahi publishing settings could not be updated safely; configuration was preserved.")
    keep = host.safe(STEAMOS_KEEP)
    keep_before = keep.read_text(encoding="utf-8") if keep.exists() else None
    if keep_before is not None and not host.owns(STEAMOS_KEEP):
        raise SetupError("The SteamOS mDNS keep list belongs to another tool; it was preserved.")
    backup = f"{STATE}/avahi-daemon.conf.before-mdns"
    if not host.safe(backup).exists():
        host.write(backup, original, mode=0o600)
    try:
        host.write(AVAHI_CONFIG, updated, mode=mode)
        _restart_avahi(host)
        change.update(changed=True, backup=backup)
        host.managed(STEAMOS_KEEP, AVAHI_CONFIG + "\n/etc/nsswitch.conf\n")
        yield change
    except Exception:
        host.write(AVAHI_CONFIG, original, mode=mode)
        if keep_before is None:
            if keep.exists():
                keep.unlink()
        else:
            host.write(STEAMOS_KEEP, keep_before)
        _restart_avahi(host)
        raise


HOSTS = "/etc/hosts"
HOSTS_KEEP = "/etc/atomic-update.conf.d/bc250-control-center-web-host.conf"
HOSTS_ALIAS = "127.0.0.1 bc250cc.local # BC250 Control Center local web address"


@contextmanager
def _local_hosts_transaction(host, own):
    """Let Flatpak/browser resolvers reach this host without an NSS mDNS module."""
    change = {"changed": False, "backup": ""}
    if not host.steamos():
        yield change
        return
    path = host.safe(HOSTS)
    original = path.read_text(encoding="utf-8") if path.exists() else None
    for line in (original or "").splitlines():
        fields = line.partition("#")[0].split()
        if len(fields) > 1 and "bc250cc.local" in [name.lower() for name in fields[1:]]:
            if fields[0] not in own | {"127.0.0.1", "::1"}:
                raise SetupError("An existing hosts entry sends bc250cc.local to another device; it was preserved.")
            yield change
            return
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    backup = f"{STATE}/hosts.before-mdns"
    if original is not None and not host.safe(backup).exists():
        host.write(backup, original, mode=0o600)
    keep = host.safe(HOSTS_KEEP)
    keep_before = keep.read_text(encoding="utf-8") if keep.exists() else None
    if keep_before is not None and not host.owns(HOSTS_KEEP):
        raise SetupError("The local web address keep list belongs to another tool; it was preserved.")
    try:
        text = original or ""
        host.write(HOSTS, text + ("" if not text or text.endswith("\n") else "\n") + HOSTS_ALIAS + "\n", mode=mode)
        host.managed(HOSTS_KEEP, HOSTS + "\n")
        change.update(changed=True, backup=backup if original is not None else "")
        yield change
    except Exception:
        if original is None:
            path.unlink(missing_ok=True)
        else:
            host.write(HOSTS, original, mode=mode)
        if keep_before is None:
            keep.unlink(missing_ok=True)
        else:
            host.write(HOSTS_KEEP, keep_before)
        raise


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
    with _publication_transaction(host) as publication:
        advertised = _prepare(host).split()
        interfaces = json.loads(host.run("ip", "-j", "-4", "addr", "show"))
        own = {item.get("local") for link in interfaces for item in link.get("addr_info", [])}
        if len(advertised) != 2 or advertised[0] != "bc250cc.local" or advertised[1] not in own:
            raise SetupError("The local name belongs to another device or is not advertised. Resolver settings were preserved.")
        with _local_hosts_transaction(host, own) as local_hosts:
            updated = original[:match.start()] + body + ((" #" + comment) if separator else "") + original[match.end():]
            backup = f"{STATE}/nsswitch.conf.before-mdns"
            if updated != original:
                if not host.safe(backup).exists():
                    host.write(backup, original, mode=0o600)
                host.write("/etc/nsswitch.conf", updated, mode=path.stat().st_mode & 0o777)
            try:
                resolved = host.run("getent", "ahostsv4", "bc250cc.local", timeout=8).splitlines()
                resolved_addresses = {row.split()[0] for row in resolved if row.split()}
                if not resolved_addresses or not resolved_addresses <= own | {"127.0.0.1", "::1"}:
                    raise SetupError("The local name still does not resolve to the advertised address.")
            except (SetupError, OSError):
                if updated != original:
                    host.write("/etc/nsswitch.conf", original, mode=path.stat().st_mode & 0o777)
                raise
            return {"verified": True, "changed": updated != original or publication["changed"] or local_hosts["changed"],
                    "backup": backup if updated != original else "",
                    "publication_backup": publication["backup"], "hosts_backup": local_hosts["backup"]}
