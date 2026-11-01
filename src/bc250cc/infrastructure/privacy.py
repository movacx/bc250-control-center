"""Take the person out of a text before it leaves the machine.

A diagnosis is pasted into forums and chats, and sent to people nobody has
met. It must not say who the owner is, where they are, or which machine this
is. Everything that names a person or a unit comes out; everything a
maintainer needs to read a fault stays:

* removed: home folders and the account's name, the machine's own name, other
  people's accounts on it, the owner's real name, e-mail addresses, IPv4 and
  IPv6 addresses, MAC addresses, Wi-Fi network names, serial numbers,
  filesystem and partition UUIDs, the machine-id (and the folder named after it
  in the journal), and Steam account ids;
* kept: default host names of a distribution ("bazzite", "steamdeck"), the
  generic account names ("deck", "root"), and the identifiers of the graphics
  *driver* (``deviceUUID``, ``driverUUID``), which say which build runs, not
  whose it is.

A redacted text is redacted again unchanged, so the same text can pass through
several layers.
"""

from __future__ import annotations

import getpass
import ipaddress
import re
import socket
import subprocess
import time
from pathlib import Path

from bc250cc.shared.error_origins import redact

#: Default host names: replacing them would also erase the distribution's
#: name everywhere it is written ("Bazzite", "steamdeck"), and they say
#: nothing about the person.
_GENERIC_HOSTS = frozenset({
    "localhost", "bazzite", "steamdeck", "fedora", "cachyos", "cachyos-x8664",
    "archlinux", "ubuntu", "debian", "manjaro", "bc250", "bc-250", "linux",
})
#: Account names that say nothing about the person and are also words of
#: this app's own paths: with the account "bc250", every "bc250" of a report
#: (bc250-control-center, /tmp/bc250-helixsr) became "<user>".
_GENERIC_USERS = frozenset({
    "root", "deck", "bazzite", "bc250", "bc-250", "steam", "user", "gamer", "admin", "linux",
    "guest", "player", "ubuntu", "fedora", "arch", "cachyos", "manjaro", "debian",
})
_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
#: Not glued to a hyphen, letter, colon or dot: a package version such as
#: "2.4.11.1-1" or "1:2.0.0.1" is four numbers too, and was sent as "<ip>-1".
_IPV4 = re.compile(rf"(?<![\w.:-])(?!127\.0\.0\.1\b)(?:{_OCTET}\.){{3}}{_OCTET}(?![\w.-])")
#: Candidates only: ``ipaddress`` decides. A clock ("12:00:01"), a PCI address
#: ("0000:00:08.1") or a MAC is not a valid IPv6 address and is left to its own rule.
_IPV6 = re.compile(r"(?<![\w:.])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?:%[\w.-]+)?(?![\w:.])")
_MAC = re.compile(r"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
#: The graphics driver's own identifiers: which build, not whose.
_DRIVER_IDS = re.compile(r"^\s*(?:device|driver|pipelineCache)UUID\b")
_JOURNAL_DIRECTORY = re.compile(r"(?<=/var/log/journal/)[0-9a-f]{32}\b", re.I)
_STEAM_USERDATA = re.compile(r"(?<=userdata/)\d{5,}")
_STEAM_ID64 = re.compile(r"\b7656119\d{10}\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
#: ``Serial Number: X``, ``ID_SERIAL=X``, ``product_serial: X``: the value goes, the label stays.
_SERIAL = re.compile(
    r"(?i)\b((?:(?:product|board|chassis|system)[ _])?serial(?:[ _]number|[ _]no\.?)?|ID_SERIAL(?:_SHORT)?|S/N)"
    r"(\s*[:=]\s*)(?!<serial>)(\S[^\n]*)"
)
#: What is looked up on the machine, once in a while: it does not change every second.
_CACHE_SECONDS = 60.0
_cache: tuple[float, dict] | None = None


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _wifi_names() -> set[str]:
    """Saved Wi-Fi network names (a network's name often is the owner's)."""
    try:
        listing = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
            capture_output=True, text=True, timeout=4, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    names = set()
    for line in listing.splitlines():
        name, _, kind = line.rpartition(":")
        if "wireless" in kind and len(name.replace("\\", "")) >= 4:
            names.add(name.replace("\\:", ":").replace("\\\\", "\\"))
    return names


def _other_accounts() -> tuple[set[str], set[str]]:
    """(account names, real names) of the people who use this machine."""
    users: set[str] = set()
    real: set[str] = set()
    try:
        import pwd

        for entry in pwd.getpwall():
            if not (1000 <= entry.pw_uid < 65534):
                continue
            users.add(entry.pw_name)
            gecos = entry.pw_gecos.split(",")[0].strip()
            if len(gecos) >= 4 and any(character.isalpha() for character in gecos):
                real.add(gecos)
    except (ImportError, KeyError, OSError):
        pass
    return users, real


def _slow() -> dict:
    """What costs a lookup (other programs, the account database): kept a minute."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_SECONDS:
        return _cache[1]
    users, real = _other_accounts()
    found = {"users": users, "real": real, "wifi": _wifi_names()}
    _cache = (now, found)
    return found


def _personal() -> dict:
    """What identifies this machine and its people.

    The names of the machine and of the running user are read every time: they
    are cheap, and the text being cleaned has to be cleaned with what is true now.
    """
    slow = _slow()
    host = socket.gethostname().strip()
    hosts = {host, host.split(".", 1)[0], _read("/etc/hostname")}
    users = set(slow["users"])
    try:
        users.add(getpass.getuser().strip())
    except Exception:  # noqa: BLE001 - no name to remove
        pass
    return {
        "hosts": {name for name in hosts if len(name) >= 3 and name.lower() not in _GENERIC_HOSTS},
        "users": {name for name in users if len(name) >= 3 and name.lower() not in _GENERIC_USERS},
        "real": slow["real"],
        "wifi": slow["wifi"],
        "machine_id": _read("/etc/machine-id").lower(),
    }


def reset_cache() -> None:
    global _cache
    _cache = None


def _word(name: str, replacement: str, text: str, *, left: str = r"(?<![\w])", right: str = r"(?![\w])") -> str:
    return re.sub(f"{left}{re.escape(name)}{right}", replacement, text)


def _ipv6(match: re.Match) -> str:
    token = match.group(0)
    try:
        address = ipaddress.IPv6Address(token.split("%", 1)[0])
    except ValueError:
        return token
    # "::" and "::1" name no one.
    return token if address.is_unspecified or address.is_loopback else "<ip>"


def _uuids(text: str) -> str:
    """Filesystem, partition and boot ids, but not the graphics driver's own."""
    return "\n".join(
        line if _DRIVER_IDS.match(line) else _UUID.sub("<uuid>", line) for line in text.split("\n")
    )


def redact_machine(text: object) -> str:
    """``redact`` plus everything that names the machine or its people."""
    text = redact(text)
    known = _personal()
    # Hosts keep their old rule: not glued to a dot or hyphen, so a package called
    # like the machine is not mangled.
    for name in sorted(known["hosts"], key=len, reverse=True):
        text = _word(name, "<host>", text, left=r"(?<![\w.-])", right=r"(?![\w-])")
    for name in sorted(known["real"], key=len, reverse=True):
        text = re.sub(re.escape(name), "<name>", text, flags=re.I)
    # The account name also shows outside the home folder (/var/tmp/pamac-
    # build-<name>, "[sudo] password for <name>").
    for name in sorted(known["users"], key=len, reverse=True):
        text = _word(name, "<user>", text)
    for name in sorted(known["wifi"], key=len, reverse=True):
        text = re.sub(re.escape(name), "<network>", text)
    text = _EMAIL.sub("<email>", text)
    text = _IPV4.sub("<ip>", text)
    text = _IPV6.sub(_ipv6, text)
    text = _MAC.sub("<mac>", text)
    text = _uuids(text)
    machine_id = known["machine_id"]
    if len(machine_id) == 32:
        text = re.sub(re.escape(machine_id), "<machine-id>", text, flags=re.I)
    text = _JOURNAL_DIRECTORY.sub("<machine-id>", text)
    text = _STEAM_USERDATA.sub("<steam-id>", text)
    text = _STEAM_ID64.sub("<steam-id>", text)
    return _SERIAL.sub(lambda m: f"{m.group(1)}{m.group(2)}<serial>", text)
