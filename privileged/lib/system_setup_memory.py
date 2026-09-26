"""Opt-in mutable-distribution memory setup, with independent swap/TTM restore.

Never edits fstab, boot arguments, partitions, existing ZRAM devices or user swap.
Unsupported kernel/filesystem capabilities fail before writes.

Every policy is a complete, reversible profile rather than a single switch:

* ``zram`` — a 4 GiB (at most half of RAM) compressed RAM swap with an
  explicit algorithm, plus the virtual-memory tuning in-memory swap needs.
* ``swap-16`` / ``swap-32`` — a dedicated, fully allocated disk swapfile.
* ``zswap-16`` / ``zswap-32`` — that swapfile behind a tuned ZSWAP cache
  (compressor, pool size, allocator, shrinker) re-applied at every boot.
* ``restore`` — every value this setup changed goes back to the value it
  found, live and at boot; nothing it did not create is removed.

Each original value is journalled before it is changed, so an interrupted
transaction is always restorable.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from system_setup_common import HELPER, STATE, Host, SetupError

GIB = 1024 ** 3
SWAP_SUBDIR = "bc250-control-center-swap"
SWAP_DIR = "/var/lib/" + SWAP_SUBDIR
SWAP = SWAP_DIR + "/swapfile"
UNIT = "var-lib-bc250\\x2dcontrol\\x2dcenter\\x2dswap-swapfile.swap"
UNIT_PATH = "/etc/systemd/system/" + UNIT
SERVICE = "bc250-memory-setup.service"
SERVICE_PATH = "/etc/systemd/system/" + SERVICE
ZRAM = "/etc/systemd/zram-generator.conf.d/90-bc250.conf"
TTM = "/sys/module/ttm/parameters/pages_limit"
ZSWAP = "/sys/module/zswap/parameters/enabled"
POLICIES = {"preserve", "restore", "swap-16", "swap-32", "zram", "zswap-16", "zswap-32"}

ZSWAP_PARAMETERS = "/sys/module/zswap/parameters"
#: Applied in this order, each only if the kernel exposes it. The first
#: candidate the kernel accepts wins: lz4 is what the reference BC-250
#: toolkits settled on for zswap (lowest latency on the Zen 2 cores), zstd and
#: lzo-rle are the fallbacks every distribution kernel carries.
ZSWAP_TUNING = (
    ("compressor", ("lz4", "zstd", "lzo-rle")),
    ("zpool", ("zsmalloc",)),
    ("max_pool_percent", ("25",)),
    ("shrinker_enabled", ("Y",)),
)
SYSCTL = "/etc/sysctl.d/90-bc250-memory.conf"
VM = "/proc/sys/vm"
#: Virtual-memory tuning per profile. In-memory swap (zram) is cheaper than
#: dropping page cache, so it wants a swappiness above 100 and no readahead;
#: zswap with a disk behind it wants anonymous and file pages weighed evenly.
#: A plain disk swap keeps the distribution's own values.
SYSCTL_PROFILES = {
    "zram": (("swappiness", "180"), ("page-cluster", "0"),
             ("watermark_boost_factor", "0"), ("watermark_scale_factor", "125")),
    "zswap": (("swappiness", "100"),),
}
#: Free space a swapfile must leave on its filesystem: 2 GiB, or 5 % of the
#: filesystem when that is more, so a large disk is never filled to the edge.
MIN_FREE_AFTER_SWAP = 2 * 1024 ** 3
MIN_FREE_FRACTION = 0.05
ZRAM_ALGORITHMS = ("zstd", "lz4", "lzo-rle")

# Same reviewed pattern already used for Bazzite's independent zswap flow
# (bazzite_memory_tuning.py): a Condition drop-in on the foreign zram-generator
# unit plus a marker file, never touching the distribution's own config. The
# device keeps running until the next boot; only the generator is told not to
# recreate it, which is what makes this reversible without guessing at
# someone else's zram-generator.conf.
FOREIGN_ZRAM_MARKER = "/etc/bc250-control-center/zram-disabled"


def _profile(policy: str) -> str:
    if policy == "zram":
        return "zram"
    if policy.startswith("zswap-"):
        return "zswap"
    return ""


def apply_zswap_tuning(host: Host, state: dict) -> dict[str, str]:
    """Tune ZSWAP before enabling it; journal every original first.

    Returns what was applied. A parameter the running kernel does not expose
    is skipped, and a value it refuses falls through to the next candidate:
    the pool still works on the kernel's own default.
    """
    originals = state.setdefault("zswap_tuning_original", {})
    applied: dict[str, str] = {}
    for name, candidates in ZSWAP_TUNING:
        path = f"{ZSWAP_PARAMETERS}/{name}"
        if not host.writable_parameter(path):
            continue
        current = host.read(path)
        originals.setdefault(name, current)
        host.save("memory", state)
        for value in candidates:
            try:
                host.parameter(path, value)
            except (SetupError, OSError):
                continue
            applied[name] = value
            break
    state["zswap_tuning"] = applied
    host.save("memory", state)
    return applied


def restore_zswap_tuning(host: Host, state: dict) -> None:
    for name, original in (state.get("zswap_tuning_original") or {}).items():
        path = f"{ZSWAP_PARAMETERS}/{name}"
        if original and host.writable_parameter(path):
            try:
                host.parameter(path, original)
            except (SetupError, OSError):
                pass  # The kernel refused its own previous value; nothing else to do.
    state.pop("zswap_tuning_original", None)
    state.pop("zswap_tuning", None)
    host.save("memory", state)


def apply_sysctl_profile(host: Host, state: dict, profile: str) -> None:
    """Write the managed sysctl drop-in and apply it live, journalling first."""
    settings = SYSCTL_PROFILES.get(profile)
    if not settings:
        return
    originals = state.setdefault("sysctl_original", {})
    for key, _value in settings:
        originals.setdefault(key, host.read(f"{VM}/{key}"))
    state["owns_sysctl"] = True
    host.save("memory", state)
    host.managed(SYSCTL, "".join(f"vm.{key} = {value}\n" for key, value in settings))
    for key, value in settings:
        path = f"{VM}/{key}"
        if host.writable_parameter(path):
            host.parameter(path, value)


def restore_sysctl_profile(host: Host, state: dict) -> None:
    if not state.get("owns_sysctl"):
        return
    host.remove_managed(SYSCTL)
    for key, original in (state.get("sysctl_original") or {}).items():
        path = f"{VM}/{key}"
        if original and host.writable_parameter(path):
            try:
                host.parameter(path, original)
            except (SetupError, OSError):
                pass
    state.pop("owns_sysctl", None)
    state.pop("sysctl_original", None)
    host.save("memory", state)


def zram_algorithm(host: Host) -> str:
    """The first algorithm the running kernel can load, or "" for its default."""
    crypto = host.read("/proc/crypto")
    loaded = set(re.findall(r"^name\s*:\s*(\S+)", crypto, re.M))
    release = host.read("/proc/sys/kernel/osrelease")
    for algorithm in ZRAM_ALGORITHMS:
        if algorithm in loaded:
            return algorithm
        module = algorithm.replace("-", "_")
        if release and any(host.path(f"/lib/modules/{release}/kernel/crypto").glob(f"{module}*")):
            return algorithm
    return ""


def zram_config(host: Host) -> str:
    algorithm = zram_algorithm(host)
    lines = ["[zram0]", "zram-size = min(ram / 2, 4096)"]
    if algorithm:
        lines.append(f"compression-algorithm = {algorithm}")
    lines += ["swap-priority = 100", "fs-type = swap"]
    return "\n".join(lines) + "\n"


def live_memory(host: Host) -> dict:
    """Read-only snapshot of what the kernel is doing right now."""
    devices = []
    for line in host.read("/proc/swaps").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 5 and fields[2].isdigit() and fields[3].isdigit():
            try:
                priority = int(fields[4])
            except ValueError:
                priority = 0
            devices.append({"path": fields[0], "size": int(fields[2]) * 1024,
                            "used": int(fields[3]) * 1024, "priority": priority})
    zram = []
    for device in sorted(host.path("/sys/block").glob("zram*")):
        stat_fields = (device / "mm_stat").read_text().split() if (device / "mm_stat").is_file() else []
        algorithm = ""
        if (device / "comp_algorithm").is_file():
            match = re.search(r"\[([^\]]+)\]", (device / "comp_algorithm").read_text())
            algorithm = match.group(1) if match else ""
        original = int(stat_fields[0]) if stat_fields[:1] and stat_fields[0].isdigit() else 0
        compressed = int(stat_fields[1]) if stat_fields[1:2] and stat_fields[1].isdigit() else 0
        zram.append({"name": device.name, "algorithm": algorithm,
                     "original_bytes": original, "compressed_bytes": compressed})
    zswap = {name: host.read(f"{ZSWAP_PARAMETERS}/{name}")
             for name in ("enabled", "compressor", "zpool", "max_pool_percent", "shrinker_enabled")
             if host.path(f"{ZSWAP_PARAMETERS}/{name}").exists()}
    vm = {key: host.read(f"{VM}/{key}") for key in ("swappiness", "page-cluster")
          if host.path(f"{VM}/{key}").exists()}
    return {"swap_devices": devices, "zram_devices": zram, "zswap": zswap, "vm": vm}


def swap_dir_for_target(mountpoint: str) -> str:
    """The dedicated BC250 directory under a chosen mount point.

    Never the mount point itself: a shared root like ``/mnt/games`` keeps
    its own layout untouched, exactly as ``/var/lib`` does for the default.
    """
    return mountpoint.rstrip("/") + "/" + SWAP_SUBDIR


def swaps(host: Host) -> dict[str, int]:
    result = {}
    for line in host.read("/proc/swaps").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[3].isdigit():
            result[fields[0]] = int(fields[3]) * 1024
    return result


def _escape_unit_path(path: str) -> str:
    """Reimplements systemd-escape --path so no subprocess is needed.

    Matches the fixed ``UNIT`` constant for the default swap directory
    exactly (verified by test), which is what let that constant stay
    hand-written instead of computed until now.
    """
    stripped = path.strip("/")
    if not stripped:
        return "-"
    segments = []
    for segment in stripped.split("/"):
        chars = []
        for index, char in enumerate(segment):
            if char.isalnum() or (char in "_:." and not (index == 0 and char == ".")):
                chars.append(char)
            else:
                chars.append(f"\\x{ord(char):02x}")
        segments.append("".join(chars))
    return "-".join(segments)


def swap_paths(host: Host, state: dict) -> tuple[str, str, str, str]:
    """The directory, swapfile, unit name and unit path currently in effect.

    A custom ``swap_dir`` (chosen via :func:`candidate_swap_targets`) gets
    its own unit name, escaped the same way Bazzite's own zswap flow escapes
    its swapfile path.
    """
    directory = state.get("swap_dir") or SWAP_DIR
    swapfile = directory.rstrip("/") + "/swapfile"
    unit = _escape_unit_path(swapfile) + ".swap"
    return directory, swapfile, unit, "/etc/systemd/system/" + unit


def candidate_swap_targets(host: Host) -> dict[str, int]:
    """Locally mounted Ext4/Btrfs targets with room for a swapfile.

    ``/var/lib`` — the historical default — is always checked first so
    existing installs keep seeing it even if it is not its own mount point.
    """
    if not host.command("findmnt"):
        return {}
    targets: dict[str, int] = {}
    var_lib_fs = host.run("findmnt", "-n", "-o", "FSTYPE", "--target", "/var/lib")
    if var_lib_fs in {"ext4", "btrfs"}:
        try:
            free = shutil.disk_usage(host.path("/var/lib")).free
        except OSError:
            free = 0
        if free > GIB:
            targets["/var/lib"] = free
    try:
        listing = json.loads(host.run("findmnt", "--json", "--real", "-o", "TARGET,FSTYPE"))
    except (SetupError, ValueError):
        return targets
    for entry in listing.get("filesystems", []) or []:
        target = entry.get("target")
        if not target or target in targets or entry.get("fstype") not in {"ext4", "btrfs"}:
            continue
        try:
            free = shutil.disk_usage(host.path(target)).free
        except OSError:
            continue
        if free > GIB:
            targets[target] = free
    return targets


def zram_idle(host: Host, name: str) -> bool:
    """A zram block device with no disk configured behind it.

    Loading the zram module creates ``zram0`` on its own. That empty device
    is exactly what remains after a foreign ZRAM has been told to stand down
    for ZSWAP: it neither swaps nor competes with ZSWAP. Counting it as an
    active ZRAM failed the boot worker on every start (seen on a CachyOS
    BC-250, 2026-09), so the ZSWAP tuning was never applied again. Only an
    explicit ``initstate`` of 0 counts as idle; anything else stays active.
    """
    return host.read(f"/sys/block/{name}/initstate") == "0"


def zram_present(host: Host) -> bool:
    return (any(name.startswith("/dev/zram") for name in swaps(host))
            or any(not zram_idle(host, device.name)
                   for device in host.path("/sys/block").glob("zram*")))


def foreign_zram_units(host: Host) -> list[str]:
    """Device names (``zram0``, ...) behind an existing, non-BC250 ZRAM.

    Only devices this setup did not create — ``owns_zram`` tracks ours
    separately and is never touched here.
    """
    names = {name.rsplit("/", 1)[-1] for name in swaps(host) if name.startswith("/dev/zram")}
    names.update(path.name for path in host.path("/sys/block").glob("zram*"))
    return sorted(names)


def zram_takeover_available(host: Host, state: dict) -> bool:
    """A foreign ZRAM can be told to stand down so ZSWAP can take its place.

    Requires systemd-zram-generator: the Condition drop-in this relies on
    only intercepts units that generator creates. A device from a legacy
    zram-tools/zram-config manager or a hand-written udev rule is left
    alone, same as ``zram_foreign_config`` already treats it — there is no
    single foreign unit this could safely disable for those.

    Never offered for our own ZRAM (``restore`` already covers that) nor
    when the kernel has no writable ZSWAP knob to switch to in its place.
    """
    generator = any(host.path(p).is_file() for p in (
        "/usr/lib/systemd/system-generators/zram-generator",
        "/lib/systemd/system-generators/zram-generator"))
    return bool(generator and host.writable_parameter(ZSWAP) and not state.get("owns_zram")
                and not legacy_zram_manager_present(host)
                and (zram_present(host) or zram_foreign_config(host)))


def disable_foreign_zram(host: Host, state: dict) -> None:
    """Stop a foreign ZRAM from coming back, without editing its own files.

    The live device is swapped off now; systemd is only told, through a
    Condition drop-in, not to recreate it after the next boot. Nothing that
    belongs to the distribution or another tool is modified.
    """
    units = foreign_zram_units(host) or ["zram0"]
    host.managed(FOREIGN_ZRAM_MARKER, "")
    for name in units:
        host.managed(
            f"/etc/systemd/system/systemd-zram-setup@{name}.service.d/90-bc250-zswap.conf",
            f"[Unit]\nConditionPathExists=!{FOREIGN_ZRAM_MARKER}\n",
        )
    for name in units:
        if f"/dev/{name}" in swaps(host):
            try:
                host.run("swapoff", f"/dev/{name}")
            except SetupError:
                pass
    host.run("systemctl", "daemon-reload")
    state["foreign_zram_units"] = units
    state["foreign_zram_disabled"] = True
    host.save("memory", state)


def restore_foreign_zram(host: Host, state: dict) -> None:
    if not state.get("foreign_zram_disabled"):
        return
    for name in state.get("foreign_zram_units", []):
        host.remove_managed(
            f"/etc/systemd/system/systemd-zram-setup@{name}.service.d/90-bc250-zswap.conf"
        )
    host.remove_managed(FOREIGN_ZRAM_MARKER)
    host.run("systemctl", "daemon-reload")
    state.pop("foreign_zram_disabled", None)
    state.pop("foreign_zram_units", None)
    host.save("memory", state)


def legacy_zram_manager_present(host: Host) -> bool:
    """A zram-tools/zram-config/udev setup — not systemd-zram-generator.

    These do not create a ``systemd-zram-setup@*.service`` unit, so the
    Condition drop-in :func:`disable_foreign_zram` relies on cannot reach
    them; takeover is never offered while one of these is present.
    """
    managers = (
        # Debian/Ubuntu zram-tools and the older zram-config package.
        "/etc/default/zramswap", "/etc/default/zram-config",
        "/etc/init.d/zramswap", "/etc/init.d/zram-config",
        "/lib/systemd/system/zramswap.service", "/usr/lib/systemd/system/zramswap.service",
        # Common Arch/community and local service configurations.
        "/etc/conf.d/zram-init", "/etc/systemd/system/zramswap.service",
        "/etc/systemd/system/zram.service", "/usr/lib/systemd/system/zram.service",
    )
    if any(host.path(path).exists() for path in managers):
        return True
    # Hand-written udev based ZRAM setups as well.
    return any(host.path("/etc/udev/rules.d").glob("*zram*.rules"))


def zram_foreign_config(host: Host) -> bool:
    for directory in ("/etc", "/usr/lib", "/usr/local/lib", "/run"):
        base = host.path(directory + "/systemd")
        for path in [base / "zram-generator.conf", *base.glob("zram-generator.conf.d/*.conf")]:
            if path.exists() and path != host.path(ZRAM):
                return True
    return legacy_zram_manager_present(host)


def status(host: Host) -> dict:
    supported = host.mutable_systemd() and host.bc250()
    state = host.state("memory")
    active = swaps(host)
    generator = any(host.path(p).is_file() for p in (
        "/usr/lib/systemd/system-generators/zram-generator",
        "/lib/systemd/system-generators/zram-generator"))
    zram_available = supported and generator and not zram_foreign_config(host) and not zram_present(host)
    zswap_available = (supported and host.writable_parameter(ZSWAP)
                       and not zram_present(host) and not zram_foreign_config(host))
    restore_available = bool(state.get("owns_swap") or state.get("owns_zram")
                             or state.get("zswap_original") is not None
                             or state.get("phase") == "incomplete")
    policies = ["preserve"] if supported else []
    if supported and restore_available:
        policies.append("restore")
    swap_commands = all(host.command(c) for c in ("findmnt", "mkswap", "swapon", "swapoff", "systemctl"))
    if supported and swap_commands:
        policies += ["swap-16", "swap-32"]
        if zswap_available:
            policies += ["zswap-16", "zswap-32"]
    if (zram_available or (supported and state.get("owns_zram") and not zram_foreign_config(host))) and host.read(ZSWAP).lower() not in {"y", "1"}:
        policies += ["zram"]
    pages = host.read(TTM)
    policy_reasons = {}
    if supported and not swap_commands:
        policy_reasons.update({key: "Required disk-swap tools are not installed" for key in
                               ("swap-16", "swap-32", "zswap-16", "zswap-32")})
    if supported and "zram" not in policies:
        policy_reasons["zram"] = ("An existing ZRAM configuration or device is preserved"
                                   if zram_foreign_config(host) or zram_present(host)
                                   else "systemd-zram-generator is not installed"
                                   if not generator else "Disable ZSWAP before selecting ZRAM")
    takeover_available = supported and swap_commands and zram_takeover_available(host, state)
    if supported and "zswap-16" not in policies and swap_commands:
        reason = ("Apply to disable the existing ZRAM and switch to ZSWAP (takes effect after reboot)"
                  if takeover_available
                  else "An existing ZRAM configuration or device is preserved"
                  if zram_foreign_config(host) or zram_present(host)
                  else "The running kernel does not expose writable ZSWAP control")
        policy_reasons.update({"zswap-16": reason, "zswap-32": reason})
    if supported and not restore_available:
        policy_reasons["restore"] = "No BC250 memory changes are recorded"
    _, current_swap, _, _ = swap_paths(host, state)
    family = host.distro_family()
    immutable = host.immutable_image()
    if immutable:
        reason = "Immutable/image-based systems require their dedicated adapter"
    elif family == "unsupported":
        reason = "Distribution is outside the supported Arch, Debian/Ubuntu and Fedora families"
    elif not host.path("/run/systemd/system").is_dir():
        reason = "This adapter requires systemd as the running service manager"
    elif not host.bc250():
        reason = "BC250 PCI hardware was not detected"
    else:
        reason = ""
    return {"supported": supported, "policies": policies, "policy_reasons": policy_reasons,
            "distro_family": family, "immutable_image": immutable,
            "restore_available": restore_available,
            "ttm_available": supported and host.writable_parameter(TTM) and pages.isdigit(),
            "ttm_current_pages": int(pages) if pages.isdigit() else None,
            "swap_active": current_swap in active, "swap_used_bytes": active.get(current_swap, 0),
            "swap_dir": state.get("swap_dir", SWAP_DIR),
            "configured_policy": state.get("policy", "preserve"),
            "phase": state.get("phase", "none"), "restore_pending": state.get("restore_pending", False),
            "configured_ttm_pages": state.get("ttm_pages"),
            "ttm_restore_available": "ttm_original" in state,
            "zram_pending": state.get("zram_pending", False),
            "zram_restore_pending": state.get("zram_restore_pending", False),
            "zram_takeover_available": takeover_available,
            "zswap_pending": state.get("zswap_pending", False),
            "direct_switches": sorted(direct_switches(state.get("policy", "preserve"))) if supported else [],
            "zswap_tuning": dict(state.get("zswap_tuning") or {}),
            "sysctl_profile": _profile(state.get("policy", "preserve")) if state.get("owns_sysctl") else "",
            "live": live_memory(host),
            "reason": reason}


def direct_switches(current: str) -> set[str]:
    """Policies reachable from ``current`` without restoring first.

    The same swapfile serves ``swap-N`` and ``zswap-N``: adding or removing
    the compressed cache in front of it needs no new file and no swapoff.
    Every other change of size or kind goes through restore.
    """
    if current.startswith(("swap-", "zswap-")):
        size = current.rsplit("-", 1)[1]
        return {f"swap-{size}", f"zswap-{size}"} - {current}
    return set()


def install_service(host: Host) -> None:
    host.managed(SERVICE_PATH, "[Unit]\nDescription=BC250 memory settings\n"
                 "After=systemd-modules-load.service swap.target\nBefore=display-manager.service\n"
                 "[Service]\nType=oneshot\n" + f"ExecStart={HELPER} memory-boot\n"
                 "[Install]\nWantedBy=multi-user.target\n")
    host.run("systemctl", "daemon-reload")
    host.run("systemctl", "enable", SERVICE)


def _required_free(usage) -> int:
    total = int(getattr(usage, "total", 0) or 0)
    return max(MIN_FREE_AFTER_SWAP, int(total * MIN_FREE_FRACTION))


def _allocate(path: Path, size: int) -> None:
    """Allocate every page up front: no sparse or truncated swapfiles."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.posix_fallocate(fd, 0, size)
        os.fsync(fd)
    finally:
        os.close(fd)


def _btrfs_swapfile(host: Host, swap_file: str, path: Path, size: int) -> None:
    """``btrfs filesystem mkswapfile``, or its manual equivalent.

    btrfs-progs before 6.1 has no ``mkswapfile``. The kernel's own rules for a
    Btrfs swapfile are what it does: an empty file marked No-COW before any
    byte is written, then fully allocated, then formatted.
    """
    try:
        host.run("btrfs", "filesystem", "mkswapfile", "--size", str(size), swap_file)
        return
    except SetupError:
        if path.exists():
            path.unlink()
    if not host.command("chattr"):
        raise SetupError("Btrfs swap needs btrfs-progs 6.1 or newer, or chattr (e2fsprogs)")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    host.run("chattr", "+C", swap_file)
    fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW)
    try:
        os.posix_fallocate(fd, 0, size)
        os.fsync(fd)
    finally:
        os.close(fd)
    host.run("mkswap", swap_file)


def _active_size_matches(host: Host, swap_file: str, size: int) -> bool:
    """The kernel reports the whole file minus its header page, in KiB.

    ``swaps()`` answers with the bytes in *use*; the size is the column
    before it.
    """
    for line in host.read("/proc/swaps").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 3 and fields[0] == swap_file and fields[2].isdigit():
            return int(fields[2]) * 1024 >= size - 1024 ** 2
    return False


def _discard_new_swapfile(host: Host, state: dict, swap_file: str, directory: Path,
                          created_directory: bool) -> None:
    """Undo a swapfile this call created and could not activate."""
    if swap_file in swaps(host):
        return  # Never remove an active swapfile, whatever went wrong.
    path = host.path(swap_file)
    if path.exists():
        path.unlink()
    if created_directory:
        try:
            directory.rmdir()
        except OSError:
            host.run("btrfs", "subvolume", "delete", str(directory), check=False)
    for key in ("owns_swap", "owns_swap_dir", "swap_dir", "swap_mount"):
        state.pop(key, None)
    host.save("memory", state)


def create_swap(host: Host, size: int, state: dict, target_mount: str | None = None) -> None:
    """``target_mount`` is one of :func:`candidate_swap_targets`'s keys.

    The swapfile always lives in its own subdirectory under that mount —
    never at the mount's root — matching how the default ``/var/lib``
    target has always worked. A swapfile created here that the kernel does
    not activate at full size is removed again before the error is reported.
    """
    mount = target_mount or state.get("swap_mount") or "/var/lib"
    requested = swap_dir_for_target(mount)
    swap_file = requested.rstrip("/") + "/swapfile"
    path = host.safe(swap_file)
    directory = host.safe(requested)
    created_here = False
    created_directory = False
    # Ownership is recorded before creation, so an interrupted setup is recoverable.
    if path.exists():
        if not state.get("owns_swap") or state.get("swap_dir", SWAP_DIR) != requested or path.stat().st_size != size:
            raise SetupError("Existing swapfile is not owned by this setup or has a different size; restore it first")
    else:
        filesystem = host.run("findmnt", "-n", "-o", "FSTYPE", "--target", mount)
        if filesystem not in {"ext4", "btrfs"}:
            raise SetupError("Disk swap currently requires Ext4 or Btrfs")
        usage = shutil.disk_usage(host.path(mount))
        reserve = _required_free(usage)
        if usage.free < size + reserve:
            raise SetupError(
                f"Insufficient disk space: a {size // GIB} GiB swapfile must still leave "
                f"{max(1, reserve // GIB)} GiB free on {mount}"
            )
        if directory.exists() and not (state.get("owns_swap") or state.get("owns_swap_dir")):
            raise SetupError("Existing swap directory is not managed by BC250")
        if filesystem == "btrfs" and not host.command("btrfs"):
            raise SetupError("btrfs-progs is required for Btrfs swap")
        state["owns_swap"] = True
        state["owns_swap_dir"] = True
        state["swap_dir"] = requested
        state["swap_mount"] = mount
        host.save("memory", state)
        created_here = True
        try:
            if not directory.exists():
                created_directory = True
                if filesystem == "btrfs":
                    # Its own subvolume: snapshots of the parent never carry
                    # gigabytes of swap, and Btrfs refuses swap in a snapshot.
                    host.run("btrfs", "subvolume", "create", requested)
                else:
                    directory.mkdir(mode=0o700, parents=True)
            directory.chmod(0o700)
            if filesystem == "btrfs":
                _btrfs_swapfile(host, swap_file, path, size)
            else:
                _allocate(path, size)
                host.run("mkswap", swap_file)
        except (SetupError, OSError):
            _discard_new_swapfile(host, state, swap_file, directory, created_directory)
            raise
    path.chmod(0o600)
    try:
        if swap_file not in swaps(host):
            host.run("swapon", "--priority", "-2", swap_file)
        if swap_file not in swaps(host):
            raise SetupError("The kernel did not activate the backing swapfile")
        if not _active_size_matches(host, swap_file, size):
            raise SetupError("The kernel activated the swapfile at a smaller size than was allocated")
    except SetupError:
        if created_here:
            if swap_file in swaps(host):
                host.run("swapoff", swap_file, check=False)
            _discard_new_swapfile(host, state, swap_file, directory, created_directory)
        raise
    _, _, unit, unit_path = swap_paths(host, state)
    host.managed(unit_path, "[Unit]\nDescription=BC250 disk swap fallback\n"
                 f"[Swap]\nWhat={swap_file}\nOptions=pri=-2\n[Install]\nWantedBy=swap.target\n")
    host.run("systemctl", "daemon-reload")
    host.run("systemctl", "enable", unit)


def restore_zswap(host: Host, state: dict) -> None:
    """Switch ZSWAP back to what it was, then its tuning, in that order."""
    if state.get("zswap_original") is not None:
        host.parameter(ZSWAP, state["zswap_original"])
        state.pop("zswap_original")
        state.pop("zswap_pending", None)
        host.save("memory", state)
    restore_zswap_tuning(host, state)


def restore_swap(host: Host, state: dict) -> None:
    restore_sysctl_profile(host, state)
    restore_foreign_zram(host, state)
    restore_zswap(host, state)
    if state.get("owns_zram"):
        host.remove_managed(ZRAM)
        host.run("systemctl", "daemon-reload")
        # Do not swapoff a live ZRAM device; generator removes it on reboot.
        state["zram_restore_pending"] = zram_present(host)
        state.pop("owns_zram")
        state.pop("zram_pending", None)
        host.save("memory", state)
    if state.get("owns_swap"):
        swap_dir, swap_file, unit, unit_path = swap_paths(host, state)
        if host.path(unit_path).exists():
            if not host.read(unit_path).startswith("# Managed by BC250 Control Center"):
                raise SetupError("Foreign swap unit preserved")
            host.run("systemctl", "disable", unit)
        active = swaps(host)
        if swap_file in active:
            match = re.search(r"^MemAvailable:\s+(\d+)", host.read("/proc/meminfo"), re.M)
            enough = match and int(match[1]) * 1024 > active[swap_file] + GIB
            if enough:
                try:
                    host.run("swapoff", swap_file)
                except SetupError:
                    pass
            if swap_file in swaps(host):
                state["restore_pending"] = True
                state["policy"] = "restore"
                host.save("memory", state)
                install_service(host)
                return
        # Never unlink an active swapfile, even after a failed swapoff.
        if host.safe(swap_file).exists():
            host.path(swap_file).unlink()
        host.remove_managed(unit_path)
        try:
            host.path(swap_dir).rmdir()
        except OSError:
            pass  # Not empty, or already gone; nothing left to preserve here.
        state.pop("owns_swap")
        state.pop("swap_dir", None)
        state.pop("swap_mount", None)
        state.pop("restore_pending", None)
    state["policy"] = "preserve"


def settle_service(host: Host, state: dict) -> None:
    """Do not leave an enabled worker once every BC250 setting is restored."""
    needed = (state.get("policy", "preserve") != "preserve" or "ttm_pages" in state
              or state.get("restore_pending") or state.get("zram_restore_pending"))
    if not needed and host.path(SERVICE_PATH).exists():
        if not host.read(SERVICE_PATH).startswith("# Managed by BC250 Control Center"):
            raise SetupError("Foreign memory service preserved")
        host.run("systemctl", "disable", SERVICE)
        host.remove_managed(SERVICE_PATH)
        host.run("systemctl", "daemon-reload")


def apply(host: Host, policy: str = "preserve", ttm_gib: int = 0,
          takeover_zram: bool = False, target_mount: str | None = None) -> dict:
    if policy not in POLICIES or type(ttm_gib) is not int or ttm_gib not in {-1, 0, 8, 10, 12}:
        raise SetupError("Invalid memory request")
    host.require_host()
    host.safe(STATE)
    available = status(host)
    state = host.state("memory")
    permitted = set(available["policies"])
    if (takeover_zram and policy.startswith("zswap-") and available["zram_takeover_available"]):
        permitted.add(policy)
    if policy not in permitted:
        raise SetupError("Selected memory policy is unavailable; existing compression configuration was preserved")
    if target_mount is not None and target_mount not in candidate_swap_targets(host):
        raise SetupError("Selected swap location is unavailable")
    current = state.get("policy", "preserve")
    if (policy not in {"preserve", "restore", current} and current != "preserve"
            and policy not in direct_switches(current)):
        raise SetupError("Restore the current BC250 memory policy before choosing another")
    if ttm_gib and not available["ttm_available"]:
        raise SetupError("This kernel does not expose a writable TTM pages_limit parameter")
    page_size = os.sysconf("SC_PAGE_SIZE")
    if GIB % page_size:
        raise SetupError("Unsupported page size")
    if ttm_gib == -1 and "ttm_original" not in state:
        raise SetupError("No BC250 TTM change to restore")
    if ttm_gib > 0:
        total = re.search(r"^MemTotal:\s+(\d+)", host.read("/proc/meminfo"), re.M)
        if not total or ttm_gib * GIB > int(total[1]) * 1024:
            raise SetupError("TTM target exceeds the RAM visible to the running kernel")
    # Preflight managed files before any hardware write.
    _, _, _, current_unit_path = swap_paths(host, state)
    for name in (SERVICE_PATH, current_unit_path, ZRAM, SYSCTL):
        if host.safe(name).exists() and not host.read(name).startswith("# Managed by BC250 Control Center"):
            raise SetupError(f"Foreign file preserved: {name}")
    state["phase"] = "preparing"
    host.save("memory", state)
    try:
        # Ensure the boot worker exists before changing sysfs or swap.
        install_service(host)
        if policy == "restore":
            restore_swap(host, state)
        elif policy.startswith(("swap-", "zswap-")):
            # Reaching here with a live/foreign ZRAM in the way means the
            # permission check above already required takeover_zram=True.
            if policy.startswith("zswap-") and (zram_present(host) or zram_foreign_config(host)):
                disable_foreign_zram(host, state)
            if policy.startswith("swap-") and current.startswith("zswap-"):
                # Same swapfile, no cache in front of it any more.
                restore_sysctl_profile(host, state)
                restore_zswap(host, state)
            create_swap(host, int(policy.rsplit("-", 1)[1]) * GIB, state, target_mount)
            if policy.startswith("zswap-"):
                state.setdefault("zswap_original", host.read(ZSWAP))
                host.save("memory", state)
                # Tune the pool before it takes its first page.
                apply_zswap_tuning(host, state)
                if zram_present(host):
                    # The foreign device is only fully gone after the reboot
                    # that lets the Condition drop-in take effect.
                    state["zswap_pending"] = True
                else:
                    host.parameter(ZSWAP, "1")
                    state.pop("zswap_pending", None)
                apply_sysctl_profile(host, state, "zswap")
            state["policy"] = policy
        elif policy == "zram":
            state["owns_zram"] = True
            host.save("memory", state)
            host.managed(ZRAM, zram_config(host))
            apply_sysctl_profile(host, state, "zram")
            state["policy"] = policy
            state["zram_pending"] = True
        if ttm_gib > 0:
            state.setdefault("ttm_original", host.read(TTM))
            state["ttm_pages"] = ttm_gib * GIB // page_size
            host.save("memory", state)
            host.parameter(TTM, str(state["ttm_pages"]))
        elif ttm_gib == -1:
            host.parameter(TTM, state["ttm_original"])
            state.pop("ttm_original")
            state.pop("ttm_pages", None)
        state["phase"] = "configured"
        host.save("memory", state)
        host.run("systemctl", "daemon-reload")
        settle_service(host, state)
    except Exception:
        state["phase"] = "incomplete"
        host.save("memory", state)
        raise
    return status(host)


def boot(host: Host) -> dict:
    host.require_host()
    host.safe(STATE)
    state = host.state("memory")
    if state.get("phase") != "configured":
        raise SetupError("Incomplete memory setup; restore or retry from Control Center")
    if state.get("restore_pending"):
        restore_swap(host, state)
    if state.get("policy", "").startswith("zswap-"):
        _, swap_file, _, _ = swap_paths(host, state)
        if swap_file not in swaps(host) or zram_present(host):
            raise SetupError("ZSWAP not enabled: backing swap missing or ZRAM is active")
        # Module parameters reset at every boot; the tuning goes back first.
        for name, value in (state.get("zswap_tuning") or {}).items():
            path = f"{ZSWAP_PARAMETERS}/{name}"
            if host.writable_parameter(path):
                try:
                    host.parameter(path, value)
                except (SetupError, OSError):
                    pass
        host.parameter(ZSWAP, "1")
        state.pop("zswap_pending", None)
    if state.get("ttm_pages") is not None:
        # TTM can be a module on some kernels.  Try loading it once after the
        # modules-load ordering point, then still require the exact sysfs knob.
        if not host.path(TTM).exists() and host.command("modprobe"):
            host.run("modprobe", "ttm", check=False)
        host.parameter(TTM, str(state["ttm_pages"]))
    state["zram_pending"] = state.get("owns_zram", False) and not zram_present(host)
    if not zram_present(host):
        state.pop("zram_restore_pending", None)
    host.save("memory", state)
    settle_service(host, state)
    return status(host)
