"""Take the person out of a text before it leaves the machine.

A diagnosis is pasted into forums and chats, and sent to people nobody has
met. It must not say who the owner is, where they are, or which machine this
is. Everything that names a person or a unit comes out; everything a
maintainer needs to read a fault stays:

* removed: home folders and the account's name, the machine's own name, other
  people's accounts on it, the owner's real name, e-mail addresses, IPv4 and
  IPv6 addresses, MAC addresses, Wi-Fi network names, serial numbers,
  filesystem and partition UUIDs, the machine-id (and the folder named after it
  in the journal), Steam account ids, and the names of removable or extra
  volumes (they are chosen by the owner);
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
#: The kernel's own spelling for a USB device ("usb 3-2: SerialNumber: X").
#: "SerialNumber=3" is only the number of a text slot and stays.
_USB_SERIAL = re.compile(r"(\bSerialNumber:[ \t]*)(?!<serial>)([^\s\"\\]+)")
#: ``[   12.3] host systemd[1]:``, ``Nov 10 01:21:29 host kernel:`` and the ISO
#: stamp: the machine's name is a column. It may be one the machine no longer
#: has (a DHCP name with the address in it), which no lookup would find.
_STAMP = (
    r"(?:\[ *\d+\.\d+\]|[A-Z][a-z]{2} [ \d]\d \d\d:\d\d:\d\d(?:\.\d+)?"
    r"|\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?)"
)
_JOURNAL_HOST = re.compile(
    rf"(?m)^([ \t]*{_STAMP} )([A-Za-z0-9][\w.-]*)(?= (?:kernel|[A-Za-z_(][^\s:\[\]]*\[\d+\]):)"
)
_HOSTNAME_SET = re.compile(r"(?i)(\bhostname set to <)([^<>\s]+)(?=>)")
#: Where desktops and people mount extra disks. In ``df`` the name ends the line
#: and may hold spaces; in a path it ends at the next separator.
_DF_VOLUME = re.compile(r"(?m)(\d+%[ \t]+/(?:run/media|media|(?:var/)?mnt)/)(?!<)([^\n]+)$")
_VOLUME = re.compile(r"(?<![\w.])(/(?:run/media|media|mnt)/)(?!<)([^\s/\"'`:;,)\]]+)(/[^\s/\"'`:;,)\]]+)?")
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


_PRODUCT_NAMES = frozenset({"bc250", "bc250cc"})


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
        # A full name of "BC250" would rewrite every code and path in the report.
        "real": {name for name in slow["real"] if name.lower().replace("-", "") not in _PRODUCT_NAMES},
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


def _journal_hosts(text: str) -> str:
    """Names in the journal's host column, there and in the rest of the text."""
    names = {match[2] for match in _JOURNAL_HOST.finditer(text)}
    names |= {match[2] for match in _HOSTNAME_SET.finditer(text)}
    names = {name for name in names if name.lower() not in _GENERIC_HOSTS}
    if not names:
        return text

    def replace(match: re.Match) -> str:
        return match[0] if match[2].lower() in _GENERIC_HOSTS else f"{match[1]}<host>"

    text = _HOSTNAME_SET.sub(replace, _JOURNAL_HOST.sub(replace, text))
    for name in sorted(names, key=len, reverse=True):
        # A short name can be a word of the log; the column is enough for it.
        if len(name) >= 5 and any(character in name for character in "-.0123456789"):
            text = _word(name, "<host>", text, left=r"(?<![\w.-])", right=r"(?![\w-])")
    return text


def _volumes(text: str) -> str:
    def replace(match: re.Match) -> str:
        # /run/media/<user>/<volume>, /media/<user>/<volume>; /mnt/<volume>.
        if not match[1].endswith("mnt/") and match[3]:
            return f"{match[1]}<user>/<volume>"
        return f"{match[1]}<volume>" + (match[3] or "")

    return _VOLUME.sub(replace, _DF_VOLUME.sub(r"\1<volume>", text))


def redact_patterns(text: object) -> str:
    """What can be recognised by its shape alone, with no look at this machine.

    The part of ``redact_machine`` that also works on a text from another
    machine: the second layer for a report received from an older version.
    """
    text = _USB_SERIAL.sub(r"\1<serial>", _volumes(_journal_hosts(str(text))))
    text = _EMAIL.sub("<email>", text)
    text = _IPV4.sub("<ip>", text)
    text = _IPV6.sub(_ipv6, text)
    text = _MAC.sub("<mac>", text)
    text = _uuids(text)
    text = _JOURNAL_DIRECTORY.sub("<machine-id>", text)
    text = _STEAM_USERDATA.sub("<steam-id>", text)
    text = _STEAM_ID64.sub("<steam-id>", text)
    return _SERIAL.sub(lambda m: f"{m.group(1)}{m.group(2)}<serial>", text)


def redact_machine(text: object) -> str:
    """``redact`` plus everything that names the machine or its people."""
    # Volumes first: ``redact`` folds /run/media/<user> into "~" and the
    # volume's name would be left behind it.
    text = redact(_volumes(str(text)))
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
    machine_id = known["machine_id"]
    if len(machine_id) == 32:
        text = re.sub(re.escape(machine_id), "<machine-id>", text, flags=re.I)
    return redact_patterns(text)
