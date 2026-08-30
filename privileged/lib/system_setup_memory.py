"""Opt-in mutable-distribution memory setup, with independent swap/TTM restore.

Never edits fstab, boot arguments, partitions, existing ZRAM devices or user swap.
Unsupported kernel/filesystem capabilities fail before writes.
"""
from __future__ import annotations

import os
import re
import shutil

from system_setup_common import HELPER, STATE, Host, SetupError

GIB = 1024 ** 3
SWAP_DIR = "/var/lib/bc250-control-center-swap"
SWAP = SWAP_DIR + "/swapfile"
UNIT = "var-lib-bc250\\x2dcontrol\\x2dcenter\\x2dswap-swapfile.swap"
UNIT_PATH = "/etc/systemd/system/" + UNIT
SERVICE = "bc250-memory-setup.service"
SERVICE_PATH = "/etc/systemd/system/" + SERVICE
ZRAM = "/etc/systemd/zram-generator.conf.d/90-bc250.conf"
TTM = "/sys/module/ttm/parameters/pages_limit"
ZSWAP = "/sys/module/zswap/parameters/enabled"
POLICIES = {"preserve", "restore", "swap-16", "swap-32", "zram", "zswap-16", "zswap-32"}


def swaps(host: Host) -> dict[str, int]:
    result = {}
    for line in host.read("/proc/swaps").splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[3].isdigit():
            result[fields[0]] = int(fields[3]) * 1024
    return result


def zram_present(host: Host) -> bool:
    return (any(name.startswith("/dev/zram") for name in swaps(host))
            or any(host.path("/sys/block").glob("zram*")))


def zram_foreign_config(host: Host) -> bool:
    for directory in ("/etc", "/usr/lib", "/usr/local/lib", "/run"):
        base = host.path(directory + "/systemd")
        for path in [base / "zram-generator.conf", *base.glob("zram-generator.conf.d/*.conf")]:
            if path.exists() and path != host.path(ZRAM):
                return True
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
    # Preserve hand-written udev based ZRAM setups as well.
    return any(host.path("/etc/udev/rules.d").glob("*zram*.rules"))


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
    if supported and "zswap-16" not in policies and swap_commands:
        reason = ("An existing ZRAM configuration or device is preserved"
                  if zram_foreign_config(host) or zram_present(host)
                  else "The running kernel does not expose writable ZSWAP control")
        policy_reasons.update({"zswap-16": reason, "zswap-32": reason})
    if supported and not restore_available:
        policy_reasons["restore"] = "No BC250 memory changes are recorded"
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
            "swap_active": SWAP in active, "swap_used_bytes": active.get(SWAP, 0),
            "configured_policy": state.get("policy", "preserve"),
            "phase": state.get("phase", "none"), "restore_pending": state.get("restore_pending", False),
            "configured_ttm_pages": state.get("ttm_pages"),
            "ttm_restore_available": "ttm_original" in state,
            "zram_pending": state.get("zram_pending", False),
            "zram_restore_pending": state.get("zram_restore_pending", False),
            "reason": reason}


def install_service(host: Host) -> None:
    host.managed(SERVICE_PATH, "[Unit]\nDescription=BC250 memory settings\n"
                 "After=systemd-modules-load.service swap.target\nBefore=display-manager.service\n"
                 "[Service]\nType=oneshot\n" + f"ExecStart={HELPER} memory-boot\n"
                 "[Install]\nWantedBy=multi-user.target\n")
    host.run("systemctl", "daemon-reload")
    host.run("systemctl", "enable", SERVICE)


def create_swap(host: Host, size: int, state: dict) -> None:
    path = host.safe(SWAP)
    directory = host.safe(SWAP_DIR)
    # Ownership is recorded before creation, so an interrupted setup is recoverable.
    if path.exists():
        if not state.get("owns_swap") or path.stat().st_size != size:
            raise SetupError("Existing swapfile is not owned by this setup or has a different size; restore it first")
    else:
        filesystem = host.run("findmnt", "-n", "-o", "FSTYPE", "--target", "/var/lib")
        if filesystem not in {"ext4", "btrfs"}:
            raise SetupError("Disk swap currently requires Ext4 or Btrfs")
        if shutil.disk_usage(host.path("/var/lib")).free < size + GIB:
            raise SetupError("Insufficient disk space; at least 1 GiB must remain free")
        if directory.exists() and not (state.get("owns_swap") or state.get("owns_swap_dir")):
            raise SetupError("Existing swap directory is not managed by BC250")
        if filesystem == "btrfs" and not host.command("btrfs"):
            raise SetupError("btrfs-progs is required for Btrfs swap")
        state["owns_swap"] = True
        state["owns_swap_dir"] = True
        host.save("memory", state)
        if not directory.exists():
            if filesystem == "btrfs":
                host.run("btrfs", "subvolume", "create", SWAP_DIR)
            else:
                directory.mkdir(mode=0o700)
        directory.chmod(0o700)
        if filesystem == "btrfs":
            host.run("btrfs", "filesystem", "mkswapfile", "--size", str(size), SWAP)
        else:
            # posix_fallocate allocates every page; no sparse/truncated swapfiles.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                os.posix_fallocate(fd, 0, size)
                os.fsync(fd)
            finally:
                os.close(fd)
            host.run("mkswap", SWAP)
    path.chmod(0o600)
    if SWAP not in swaps(host):
        host.run("swapon", "--priority", "-2", SWAP)
    if SWAP not in swaps(host):
        raise SetupError("The kernel did not activate the backing swapfile")
    host.managed(UNIT_PATH, "[Unit]\nDescription=BC250 disk swap fallback\n"
                 f"[Swap]\nWhat={SWAP}\nOptions=pri=-2\n[Install]\nWantedBy=swap.target\n")
    host.run("systemctl", "daemon-reload")
    host.run("systemctl", "enable", UNIT)


def restore_swap(host: Host, state: dict) -> None:
    if state.get("zswap_original") is not None:
        host.parameter(ZSWAP, state["zswap_original"])
        state.pop("zswap_original")
        host.save("memory", state)
    if state.get("owns_zram"):
        host.remove_managed(ZRAM)
        host.run("systemctl", "daemon-reload")
        # Do not swapoff a live ZRAM device; generator removes it on reboot.
        state["zram_restore_pending"] = zram_present(host)
        state.pop("owns_zram")
        state.pop("zram_pending", None)
        host.save("memory", state)
    if state.get("owns_swap"):
        if host.path(UNIT_PATH).exists():
            if not host.read(UNIT_PATH).startswith("# Managed by BC250 Control Center"):
                raise SetupError("Foreign swap unit preserved")
            host.run("systemctl", "disable", UNIT)
        active = swaps(host)
        if SWAP in active:
            match = re.search(r"^MemAvailable:\s+(\d+)", host.read("/proc/meminfo"), re.M)
            enough = match and int(match[1]) * 1024 > active[SWAP] + GIB
            if enough:
                try:
                    host.run("swapoff", SWAP)
                except SetupError:
                    pass
            if SWAP in swaps(host):
                state["restore_pending"] = True
                state["policy"] = "restore"
                host.save("memory", state)
                install_service(host)
                return
        # Never unlink an active swapfile, even after a failed swapoff.
        if host.safe(SWAP).exists():
            host.path(SWAP).unlink()
        host.remove_managed(UNIT_PATH)
        state.pop("owns_swap")
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


def apply(host: Host, policy: str = "preserve", ttm_gib: int = 0) -> dict:
    if policy not in POLICIES or type(ttm_gib) is not int or ttm_gib not in {-1, 0, 8, 10, 12}:
        raise SetupError("Invalid memory request")
    host.require_host()
    host.safe(STATE)
    available = status(host)
    state = host.state("memory")
    if policy not in available["policies"]:
        raise SetupError("Selected memory policy is unavailable; existing compression configuration was preserved")
    if policy not in {"preserve", "restore", state.get("policy")} and state.get("policy", "preserve") != "preserve":
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
    for name in (SERVICE_PATH, UNIT_PATH, ZRAM):
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
            create_swap(host, int(policy.rsplit("-", 1)[1]) * GIB, state)
            if policy.startswith("zswap-"):
                state.setdefault("zswap_original", host.read(ZSWAP))
                host.save("memory", state)
                host.parameter(ZSWAP, "1")
            state["policy"] = policy
        elif policy == "zram":
            state["owns_zram"] = True
            host.save("memory", state)
            host.managed(ZRAM, "[zram0]\nzram-size = min(ram / 2, 4096)\nswap-priority = 100\n")
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
        if SWAP not in swaps(host) or zram_present(host):
            raise SetupError("ZSWAP not enabled: backing swap missing or ZRAM is active")
        host.parameter(ZSWAP, "1")
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
