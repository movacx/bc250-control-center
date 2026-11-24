"""Experimental real sleep from superkeka/bc250-sleep (GPL-2.0-only).

Only strings are built here: upstream installs kernel helpers, boot configuration
and services, and its boot check writes BIOS settings. Keep the original three
bytes before that check, because upstream deliberately leaves them on uninstall.
No command in this module requests a sleep or a reboot.
"""

from __future__ import annotations

import inspect
import json
import re
import shlex
from pathlib import Path

from ._shared import shell_header

UPSTREAM = "https://github.com/superkeka/bc250-sleep"
REVIEWED_REVISION = "9f1b0d2d48b0498d4e3406b0ec409189f09ac78c"
VERSION = "1.2.3"
FAMILIES = frozenset({"steamos", "bazzite", "cachyos"})
#: Why it is not offered, shown on its row (and translated there).
REASON_CORES = (
    "It needs to know which cores were unlocked and only knows the standard ones, "
    "so it is not offered while the extra cores are on."
)
REASON_CONFLICT = "Another sleep plugin or the ACPI fix uses the same files. Remove it first to use this one."
DIRECTORY = "/etc/bc250-sleep"
BACKUP = "/var/lib/bc250-control-center/real-sleep/bios-before"
BOOT_UNIT = "/etc/systemd/system/bc250-sleep-boot.service"
DROPIN = "/etc/systemd/system/systemd-suspend.service.d/bc250-sleep.conf"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


def _homes(root: Path) -> set[Path]:
    # passwd covers homes outside /home, including Bazzite's /var/home.
    homes = {root / "root"}
    for line in _read(root / "etc/passwd").splitlines():
        fields = line.split(":")
        if len(fields) == 7 and fields[5].startswith("/"):
            homes.add(root / fields[5].lstrip("/"))
    for base in (root / "home", root / "var/home"):
        try:
            homes.update(base.iterdir())
        except OSError:
            pass
    return homes


def inventory(family: str, *, root: Path = Path("/"), core_mask: int | None = None,
              logical_cpus: int | None = None) -> dict:
    """Unprivileged file inspection; root redirects every path for fixtures.

    Count present processors rather than the process affinity or online CPUs:
    upstream may already have taken its assumed spare threads offline.
    """
    family = str(family or "").strip().lower()
    root = Path(root)
    if logical_cpus is None:
        present = _read(root / "sys/devices/system/cpu/present")
        try:
            logical_cpus = sum(
                int(part.split("-")[-1]) - int(part.split("-")[0]) + 1
                for part in present.split(",")
            )
        except ValueError:
            logical_cpus = len(re.findall(r"^processor\s*:", _read(root / "proc/cpuinfo"), re.M))
    blocked = logical_cpus > 12 and core_mask != 0x77
    conflicts = []
    for home in _homes(root):
        try:
            plugin = json.loads(_read(home / "homebrew/plugins/bc250-sleep/plugin.json"))
        except ValueError:
            continue
        if isinstance(plugin, dict) and plugin.get("name") == "BC-250 Sleep" and plugin.get("author") == "lethe-bc250 contributors":
            conflicts.append("lethe")
            break
    if family == "steamos" and any((root / path).exists() for path in (
        "boot/bc250-acpi.cpio", "etc/default/grub.d/92-bc250-acpi.cfg",
    )):
        conflicts.append("acpi")
    directory = root / DIRECTORY.lstrip("/")
    mode = _read(directory / "mode")
    s3_supported = _read(root / "sys/class/dmi/id/bios_version") == "P3.00"
    footprint = [(root / path.lstrip("/")).is_file() for path in (BOOT_UNIT, DROPIN)]
    state, reason = "not-installed", ""
    if family not in FAMILIES or _read(root / "sys/class/dmi/id/board_name") != "AMD BC-250":
        state, reason = "unsupported", "Real sleep requires an AMD BC-250 running SteamOS, Bazzite or CachyOS."
    elif any(footprint):
        required = ("bc250-sleep", "bc250-update", "system.sh", "setvar.py", "src/bc250_pm.ko")
        if all(footprint) and all((directory / name).is_file() for name in required) and mode in {"s3", "hibernate"} and _read(directory / "VERSION") == VERSION:
            state = "installed"
        else:
            state, reason = "broken", "The real sleep installation is incomplete or has an unexpected version or mode."
    elif blocked:
        reason = REASON_CORES
    elif conflicts:
        reason = REASON_CONFLICT
    swaps = [line.split() for line in _read(root / "proc/swaps").splitlines()[1:]]
    return {
        "state": state, "reason": reason, "version": VERSION,
        "mode": mode if mode in {"s3", "hibernate"} else "",
        "s3_supported": s3_supported, "spare_cores_blocked": blocked,
        "conflicts": tuple(conflicts),
        "needs_swap": not any(row and "zram" not in row[0] for row in swaps),
    }


def _header(title: str) -> list[str]:
    return shell_header(title) + [
        "trap 'echo \"ERROR: real sleep command failed at line $LINENO.\" >&2' ERR",
    ]


def _board_check() -> str:
    return '[ "$(cat /sys/class/dmi/id/board_name)" = "AMD BC-250" ] || { echo "ERROR: this is not an AMD BC-250."; exit 64; }'


def _mode_check(mode: str) -> list[str]:
    if mode not in {"s3", "hibernate"}:
        raise ValueError("Sleep mode must be s3 or hibernate.")
    if mode == "s3":
        return ['[ "$(cat /sys/class/dmi/id/bios_version)" = P3.00 ] || { echo "ERROR: S3 requires BIOS P3.00."; exit 65; }']
    return []


def _checkout(family: str) -> list[str]:
    if str(family or "").strip().lower() not in FAMILIES:
        raise RuntimeError("Real sleep supports SteamOS, Bazzite and CachyOS only.")
    # A private user directory prevents other users from substituting scripts
    # before sudo reads them. Root necessarily retains access to it.
    return [
        'bc250_stage="$(umask 077; mktemp -d "${HOME}/.bc250-real-sleep.XXXXXX")"',
        'chmod 700 "$bc250_stage"',
        "trap 'rm -rf -- \"$bc250_stage\"' EXIT",
        f'git -c core.hooksPath=/dev/null clone --no-checkout {shlex.quote(UPSTREAM)} "$bc250_stage/source"',
        'cd "$bc250_stage/source"',
        f"git -c core.hooksPath=/dev/null checkout --detach {REVIEWED_REVISION}",
        f'[ "$(git rev-parse HEAD)" = {REVIEWED_REVISION} ] || {{ echo "ERROR: upstream revision did not match the reviewed commit."; exit 29; }}',
        f'[ "$(cat VERSION)" = {VERSION} ] || {{ echo "ERROR: unexpected upstream version."; exit 29; }}',
    ]


# Use the reviewed reader's output, never source the backup as shell code. The
# lock makes the first record survive concurrent installs; atomic replacement
# leaves no partial backup after interruption. Only these three bytes are saved.
_BIOS = r'''
import fcntl
import os
import re
import subprocess
import sys
from pathlib import Path

backup = Path("/var/lib/bc250-control-center/real-sleep/bios-before")
backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chown(backup.parent, 0, 0)
os.chmod(backup.parent, 0o700)
lock = os.open(backup.parent / "lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
fcntl.flock(lock, fcntl.LOCK_EX)
offsets = ("0x6f6", "0x6f7", "0x6f8")

def read_bytes():
    output = subprocess.check_output(["python3", "tools/setvar.py"], text=True)
    values = dict(re.findall(r"^setvar: (0x6f[678]) = (0x[0-9a-fA-F]{2})\b", output, re.M))
    if set(values) != set(offsets):
        sys.exit("ERROR: could not read the three original BIOS bytes.")
    return [f"{offset}={values[offset].lower()}" for offset in offsets]

def saved_bytes():
    if backup.is_symlink() or not backup.is_file() or backup.stat().st_uid != 0 or backup.stat().st_mode & 0o077:
        sys.exit("ERROR: BIOS backup must be a private root-owned regular file.")
    values = backup.read_text().splitlines()
    if len(values) != 3 or any(not re.fullmatch(offset + r"=0x[0-9a-fA-F]{2}", value)
                               for offset, value in zip(offsets, values)):
        sys.exit("ERROR: BIOS backup is invalid; refusing to guess original settings.")
    return [value.lower() for value in values]

p300 = Path("/sys/class/dmi/id/bios_version").read_text().strip() == "P3.00"
if sys.argv[1] == "record":
    if not p300:
        print("Not BIOS P3.00: the sleep program does not write its BIOS option here.")
    elif backup.exists() or backup.is_symlink():
        saved_bytes()
    else:
        values = read_bytes()
        temporary = backup.with_suffix(".new")
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write("\n".join(values) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(backup)
else:
    if not (backup.exists() or backup.is_symlink()):
        # Never guess: on another BIOS these bytes hold something else.
        print("No BIOS bytes were recorded by Control Center; the BIOS was left as it is.")
        sys.exit(0)
    values = saved_bytes()
    subprocess.run(["python3", "tools/setvar.py", *values], check=True)
    if read_bytes() != values:
        sys.exit("ERROR: restored BIOS bytes did not verify.")
    # A later install records what the BIOS holds then.
    backup.unlink()
'''


def _bios_command(action: str) -> str:
    return f"sudo python3 - {action} <<'BC250_BIOS'\n{_BIOS}\nBC250_BIOS"


def install_command(family: str, *, mode: str = "s3", core_mask: int | None = None) -> str:
    """Build an explicit install workflow; the caller supplies a known mask."""
    commands = _header(f"Experimental real sleep {VERSION}") + [_board_check()] + _mode_check(mode)
    # Embed the read-only probe so a terminal launched later checks live files,
    # rather than trusting stale inventory from the UI.
    probe = "import json, re\nfrom pathlib import Path\n"
    probe += f"REASON_CORES={REASON_CORES!r}\nREASON_CONFLICT={REASON_CONFLICT!r}\n"
    probe += f"VERSION={VERSION!r}\nFAMILIES={set(FAMILIES)!r}\nDIRECTORY={DIRECTORY!r}\nBOOT_UNIT={BOOT_UNIT!r}\nDROPIN={DROPIN!r}\n"
    probe += "\n".join(inspect.getsource(function) for function in (_read, _homes, inventory))
    probe += f"\ninfo = inventory({family.strip().lower()!r}, core_mask={core_mask!r})\n"
    probe += 'if info["spare_cores_blocked"] or info["conflicts"] or info["state"] == "unsupported":\n'
    probe += '    raise SystemExit("ERROR: " + (info["reason"] or "Resolve core mask and sleep conflicts before installing."))\n'
    commands += [f"python3 - <<'BC250_PREFLIGHT'\n{probe}\nBC250_PREFLIGHT"]
    commands += _checkout(family)
    commands += [_bios_command("record"), "sudo ./install.sh", f"sudo {DIRECTORY}/bc250-sleep mode {mode}",
                 "echo 'OK: real sleep installed. Review status before using Sleep; boot changes may require a manual restart.'"]
    return "\n".join(commands)


def remove_command(family: str) -> str:
    return "\n".join(_header("Remove experimental real sleep") + [_board_check()] + _checkout(family) + [
        "sudo ./install.sh --uninstall", _bios_command("restore"),
        "echo 'OK: real sleep removed. Upstream leaves configuration, logs and build dependencies in place.'",
    ])


def set_mode_command(mode: str) -> str:
    return "\n".join(_header("Real sleep mode") + [_board_check()] + _mode_check(mode) + [
        f"sudo {DIRECTORY}/bc250-sleep mode {mode}",
    ])


def status_command() -> str:
    # Always pass status: invoking the upstream program without an argument sleeps.
    return "\n".join(_header("Real sleep status") + [f"{DIRECTORY}/bc250-sleep status"])
