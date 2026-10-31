"""Accept only directly attached home networks, never forwarded header claims."""
from __future__ import annotations

import ipaddress
import json
import re
import shutil
import socket
import subprocess

from bc250cc.infrastructure.remote_access import _VIRTUAL_LINKS, addresses

HOME_RANGES = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def local_hostname() -> str:
    """Offer mDNS only when it resolves to this board, without changing DNS."""
    label = socket.gethostname().lower().removesuffix(".local")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label):
        return ""
    resolver = shutil.which("avahi-resolve-host-name")
    if not resolver:
        return ""
    name = f"{label}.local"
    try:
        result = subprocess.run([resolver, "-4", "-n", name], capture_output=True, text=True, timeout=2, check=True)
        fields = result.stdout.strip().split()
        if len(fields) == 2 and fields[0].lower() == name and fields[1] in addresses():
            return name
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def home_networks() -> list[str]:
    try:
        result = subprocess.run(["ip", "-j", "-4", "addr", "show", "up", "scope", "global"],
                                capture_output=True, text=True, timeout=4, check=True)
        interfaces = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return []  # Fail closed: loopback remains available.
    networks = set()
    for interface in interfaces:
        if str(interface.get("ifname", "")).startswith((*_VIRTUAL_LINKS, "tun", "tap", "wg")):
            continue
        for item in interface.get("addr_info", []):
            try:
                address = ipaddress.ip_interface(f"{item['local']}/{item['prefixlen']}")
            except (KeyError, ValueError):
                continue
            if any(address.network.subnet_of(private) for private in HOME_RANGES):
                networks.add(str(address.network))
    return sorted(networks)


def allows(address: str, networks: list[str]) -> bool:
    try:
        peer = ipaddress.ip_address(address)
        return peer.is_loopback or any(peer in ipaddress.ip_network(network) for network in networks)
    except ValueError:
        return False
