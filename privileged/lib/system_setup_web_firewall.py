"""Bounded LAN firewall rules for the web service; never disable a firewall."""
from __future__ import annotations

import ipaddress
import json
import re

from system_setup_common import SetupError

PRIVATE = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
EXCLUDED = ("lo", "docker", "podman", "veth", "virbr", "br-", "cni", "flannel", "tailscale", "tun", "tap", "wg")
COMMENT = "BC250 Control Center LAN"


def validate_port(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise SetupError("Invalid web service port")


def lan_links(host):
    links = set()
    try:
        interfaces = json.loads(host.run("ip", "-j", "-4", "addr", "show", "up", "scope", "global", timeout=4))
        for interface in interfaces:
            name = str(interface.get("ifname", ""))
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,31}", name) or name.startswith(EXCLUDED):
                continue
            for item in interface.get("addr_info", []):
                try:
                    address = ipaddress.ip_interface(f"{item['local']}/{item['prefixlen']}")
                except (KeyError, ValueError):
                    continue
                if address.version == 4 and any(address.network.subnet_of(private) for private in PRIVATE):
                    links.add((str(address.network), name))
    except (SetupError, ValueError, TypeError, AttributeError) as error:
        raise SetupError("Could not detect the connected home networks") from error
    return sorted(links)


def _read_command(host, *args):
    try:
        return host.run(*args, timeout=4)
    except (SetupError, OSError):
        return ""


def _service_active(host, name):
    if host.path("/run/systemd/system").is_dir():
        return _read_command(host, "systemctl", "is-active", name) == "active"
    if host.openrc():
        # OpenRC returns a nonzero status for stopped services.
        return "started" in _read_command(host, "rc-service", name, "status").lower()
    return False


def _port_matches(destination, port):
    if destination == "Anywhere":
        return True
    match = re.fullmatch(r"([0-9,:]+)(?:/(tcp|udp))?", destination)
    if not match or match[2] == "udp":
        return False
    for item in match[1].split(","):
        bounds = item.split(":")
        if len(bounds) <= 2 and all(value.isdecimal() for value in bounds):
            if int(bounds[0]) <= port <= int(bounds[-1]):
                return True
    return False


def ufw_rules(text, network, port):
    """First applicable rule wins; partial denials must not be reported ready."""
    target = ipaddress.ip_network(network)
    first = None
    any_allow = False
    for line in text.splitlines():
        if "(v6)" in line:
            continue
        match = re.fullmatch(r"\s*(.*?)\s+(ALLOW(?: IN)?|DENY(?: IN)?|REJECT(?: IN)?|LIMIT(?: IN)?)\s+([^#]+?)(?:\s+#.*)?\s*", line)
        if not match or not _port_matches(match[1].strip(), port):
            continue
        source = match[3].strip()
        try:
            origin = ipaddress.ip_network("0.0.0.0/0" if source == "Anywhere" else source, strict=False)
        except ValueError:
            continue
        if origin.version != 4 or not target.overlaps(origin):
            continue
        allow = match[2].startswith("ALLOW")
        if allow and target.subnet_of(origin):
            any_allow = True
            if first is None:
                first = True
        elif not allow and first is None:
            first = False
    return first, any_allow


def _ufw_config_rules(host):
    """Read-only fallback when UFW requires root even for its status command."""
    import shlex

    lines = []
    text = host.read("/etc/ufw/user.rules")
    if not text:
        return ""
    for line in text.splitlines():
        if not line.startswith("-A ufw-user-input "):
            continue
        try:
            words = shlex.split(line)
            def value(flag, default):
                return words[words.index(flag) + 1] if flag in words else default
            # Complex rules need the privileged live check; don't guess them.
            if any(flag in words for flag in ("-i", "-o", "-d", "--sport", "--sports", "--tcp-flags")):
                return ""
            action = {"ACCEPT": "ALLOW", "DROP": "DENY", "REJECT": "REJECT"}.get(value("-j", ""))
            if action is None:
                return ""
            port = value("--dport", value("--dports", "Anywhere"))
            protocol = value("-p", "")
            if protocol and protocol != "tcp":
                continue
            lines.append(f"{port + '/' + protocol if port != 'Anywhere' and protocol else port}  {action} IN  {value('-s', 'Anywhere')}")
        except (ValueError, IndexError):
            return ""
    return "\n".join(lines) or "# No user rules"


def _zone(host, interface):
    zone = _read_command(host, "firewall-cmd", f"--get-zone-of-interface={interface}")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", zone):
        zone = host.run("firewall-cmd", "--get-default-zone", timeout=4)
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", zone):
        raise SetupError("Could not determine the firewall zone")
    return zone


def _rich_rule(network, port):
    return f'rule family="ipv4" source address="{network}" port port="{port}" protocol="tcp" accept'


def _firewalld_allowed(host, zone, network, port, *, permanent=False):
    prefix = ("firewall-cmd", f"--zone={zone}", *(("--permanent",) if permanent else ()))
    return (_read_command(host, *prefix, "--get-target") == "ACCEPT"
            or _read_command(host, *prefix, f"--query-port={port}/tcp") == "yes"
            or _read_command(host, *prefix, f"--query-rich-rule={_rich_rule(network, port)}") == "yes")


def status(host, port):
    validate_port(port)
    result = {"port": port, "backend": "", "state": "unknown", "verified": False, "repairable": False, "networks": []}
    try:
        links = lan_links(host)
    except SetupError as error:
        return {**result, "state": "no_network", "reason": str(error)}
    result["networks"] = sorted({network for network, _ in links})
    if not links:
        return {**result, "state": "no_network"}
    ufw_text = _read_command(host, "ufw", "status", "verbose") if host.command("ufw") else ""
    ufw_live = ufw_text.startswith("Status: active")
    ufw_hint = not ufw_text and bool(re.search(r"^ENABLED=yes\s*$", host.read("/etc/ufw/ufw.conf"), re.MULTILINE))
    firewalld = host.command("firewall-cmd") and _read_command(host, "firewall-cmd", "--state") == "running"
    if _service_active(host, "nftables") or (ufw_live or ufw_hint) and firewalld:
        return {**result, "state": "unsupported", "backend": "multiple/custom"}
    if ufw_live or ufw_hint:
        result.update(backend="ufw", verified=ufw_live, repairable=True)
        rules = ufw_text if ufw_live else _ufw_config_rules(host)
        if not rules:
            return {**result, "state": "needs_check"}
        default_allow = "Default: allow (incoming)" in ufw_text if ufw_live else bool(re.search(
            r'^DEFAULT_INPUT_POLICY=["\']?ACCEPT["\']?\s*$', host.read("/etc/default/ufw"), re.MULTILINE))
        allowed = [ufw_rules(rules, network, port)[0] for network in result["networks"]]
        ready = all(value is True or value is None and default_allow for value in allowed)
        return {**result, "state": "ready" if ready else "blocked", "repairable": not ready}
    if firewalld:
        try:
            ready = all(all(_firewalld_allowed(host, _zone(host, interface), network, port, permanent=permanent)
                            for permanent in (False, True)) for network, interface in links)
            return {**result, "backend": "firewalld", "state": "ready" if ready else "blocked", "verified": True, "repairable": not ready}
        except SetupError as error:
            return {**result, "backend": "firewalld", "reason": str(error)}
    if _service_active(host, "firewalld"):
        return {**result, "backend": "firewalld", "state": "unsupported"}
    # A native ruleset without a supported owner must not be overwritten.
    if host.command("nft"):
        ruleset = _read_command(host, "nft", "list", "ruleset")
        if ruleset:
            return {**result, "backend": "custom", "state": "unsupported"}
    if ufw_text.startswith("Status: inactive"):
        return {**result, "backend": "ufw", "state": "inactive", "verified": True}
    return result


def repair(host, port):
    validate_port(port)
    before = status(host, port)
    if before["state"] in {"ready", "inactive"}:
        return {**before, "changed": False}
    if not before["verified"] or before["backend"] not in {"ufw", "firewalld"}:
        raise SetupError("The active firewall could not be verified. Its existing rules were preserved.")
    links = lan_links(host)
    if not links:
        raise SetupError("No connected home network was found")
    added = []
    try:
        if before["backend"] == "ufw":
            text = host.run("ufw", "status", "verbose", timeout=4)
            for network in before["networks"]:
                allowed, existing_allow = ufw_rules(text, network, port)
                if allowed is True:
                    continue
                if existing_allow:
                    raise SetupError("Conflicting UFW rules require review; existing rules were preserved.")
                rule = ("allow", "from", network, "to", "any", "port", str(port), "proto", "tcp", "comment", COMMENT)
                response = host.run("ufw", "insert", "1", *rule, timeout=20)
                if "Skipping" in response:
                    raise SetupError("UFW preserved an existing rule; no duplicate was added.")
                added.append(("ufw", "--force", "delete", *rule))
        else:
            for network, interface in links:
                zone = _zone(host, interface)
                for permanent in (False, True):
                    if _firewalld_allowed(host, zone, network, port, permanent=permanent):
                        continue
                    prefix = ("firewall-cmd", f"--zone={zone}", *(("--permanent",) if permanent else ()))
                    rule = _rich_rule(network, port)
                    host.run(*prefix, f"--add-rich-rule={rule}", timeout=20)
                    added.append((*prefix, f"--remove-rich-rule={rule}"))
        after = status(host, port)
        if after["state"] != "ready" or not after["verified"]:
            raise SetupError("The LAN firewall rule could not be verified")
        return {**after, "changed": bool(added)}
    except (SetupError, OSError) as error:
        failed = []
        for undo in reversed(added):
            try:
                host.run(*undo, timeout=20)
            except (SetupError, OSError):
                failed.append(undo)
        if failed:
            raise SetupError(f"{error}. Some new LAN rules could not be reverted; check firewall status.") from error
        raise
