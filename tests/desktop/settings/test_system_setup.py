"""Optional setup tested against a private filesystem and command simulator.

Nothing in this suite invokes systemctl, swapon, bootctl, GRUB or real sysfs.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

LIB = Path(__file__).resolve().parents[3] / "privileged/lib"
sys.path.insert(0, str(LIB))
import system_setup_acpi as acpi  # noqa: E402
import system_setup_memory as memory  # noqa: E402
from acpi_payload import SHA256, archive  # noqa: E402
from system_setup_common import MARKER, STATE, Host, SetupError  # noqa: E402


class Sandbox:
    def __init__(self, root):
        self.calls = []
        self.fail = None
        self.fs = "ext4"
        self.host = Host(root, runner=self.run)
        self.put("/etc/os-release", 'ID="arch"\n')
        self.host.path("/run/systemd/system").mkdir(parents=True)
        self.put("/sys/bus/pci/devices/0000:01:00.0/vendor", "0x1002")
        self.put("/sys/bus/pci/devices/0000:01:00.0/device", "0x13fe")
        self.put("/proc/meminfo", "MemTotal: 16000000 kB\nMemAvailable: 12000000 kB\n")
        self.put("/proc/swaps", "Filename Type Size Used Priority\n/dev/user-swap partition 10000 0 -1\n")
        self.put("/proc/sys/kernel/random/boot_id", "boot-one")
        self.put(memory.TTM, "12345")
        self.put(memory.ZSWAP, "N")
        self.host.path("/var/lib").mkdir(parents=True)
        self.put("/proc/config.gz", gzip.compress(b"CONFIG_ACPI_TABLE_UPGRADE=y\n"))
        self.put("/sys/firmware/acpi/tables/SSDT1", self.table())

    def table(self, name="AMD CPU", revision=1, oem="AMD"):
        header = bytearray(36)
        header[:4] = b"SSDT"
        struct.pack_into("<I", header, 4, 36)
        header[10:16] = oem.ljust(6, "\0").encode()
        header[16:24] = name.ljust(8, "\0").encode()
        struct.pack_into("<I", header, 24, revision)
        return bytes(header)

    def put(self, name, data):
        path = self.host.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode() if isinstance(data, str) else data)
        return path

    def run(self, *args, check=True):
        self.calls.append(args)
        if self.fail and self.fail(args):
            raise SetupError("Simulated command failure")
        if args[0] == "findmnt":
            if "--json" in args:
                return json.dumps({"filesystems": [{"target": "/", "fsroot": "/", "uuid": "aaa-bbb", "fstype": self.fs}]})
            return self.fs
        if args[0] == "swapon":
            self.put("/proc/swaps", self.host.read("/proc/swaps") + f"\n{memory.SWAP} file 16777216 0 -2\n")
        if args[0] == "swapoff":
            self.put("/proc/swaps", "\n".join(line for line in self.host.read("/proc/swaps").splitlines()
                                              if not line.startswith(memory.SWAP)) + "\n")
        if args[:3] == ("btrfs", "subvolume", "create"):
            self.host.path(args[3]).mkdir()
        if args[:3] == ("btrfs", "filesystem", "mkswapfile"):
            with self.host.path(args[-1]).open("wb") as stream:
                stream.truncate(int(args[-2]))
        if args[0] == "bootctl":
            self.efi("LoaderEntryDefault", args[-1])
        if args[0] == "grub-mkconfig":
            self.put(acpi.GRUB_OUTPUT, self.grub_original + "\n" + self.host.read(acpi.GRUB_SCRIPT))
        return ""

    def efi(self, key, value):
        self.put(f"/sys/firmware/efi/efivars/{key}-{acpi.EFI_GUID}", b"\0" * 4 + (value + "\0").encode("utf-16-le"))

    def systemd_boot(self):
        self.put("/sys/firmware/efi/efivars/SecureBoot-test", b"\0" * 5)
        self.efi("LoaderEntrySelected", "arch.conf")
        self.efi("LoaderEntryDefault", "arch.conf")
        self.put("/boot/vmlinuz-linux", b"kernel")
        self.put("/boot/initramfs-linux.img", b"original initramfs")
        self.put("/boot/amd-ucode.img", b"microcode")
        self.put("/boot/loader/entries/arch.conf", "title Arch\nlinux /vmlinuz-linux\ninitrd /amd-ucode.img\ninitrd /initramfs-linux.img\noptions root=UUID=aaa-bbb rw\n")

    def grub(self):
        self.grub_original = "menuentry 'Arch' {\n linux /boot/vmlinuz-linux root=UUID=aaa-bbb rw\n initrd /boot/amd-ucode.img /boot/initramfs-linux.img\n}\n"
        self.put(acpi.GRUB_OUTPUT, self.grub_original)
        self.put(acpi.GRUB_CONFIG, "# User settings\nGRUB_DEFAULT=0\nGRUB_TIMEOUT=5\n")
        self.put("/proc/cmdline", "BOOT_IMAGE=/boot/vmlinuz-linux root=UUID=aaa-bbb rw")
        for image in ("vmlinuz-linux", "amd-ucode.img", "initramfs-linux.img"):
            self.put("/boot/" + image, b"original")


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    box = Sandbox(tmp_path)
    # Sparse files are ONLY a simulation in the test root, never production.
    monkeypatch.setattr(memory.os, "posix_fallocate", lambda fd, offset, size: os.ftruncate(fd, size))
    monkeypatch.setattr(memory.shutil, "disk_usage", lambda path: SimpleNamespace(free=64 * memory.GIB))
    return box


@pytest.mark.parametrize("distro", ["arch", "cachyos", "manjaro", "ubuntu", "debian", "fedora", "nobara"])
def test_mutable_distributions_offer_capability_checked_memory(sandbox, distro):
    sandbox.put("/etc/os-release", f"ID={distro}\n")
    data = memory.status(sandbox.host)
    assert data["supported"] and data["ttm_available"]
    assert {"swap-16", "swap-32", "zswap-16"} <= set(data["policies"])
    assert "restore" not in data["policies"]
    assert "zram" not in data["policies"]  # Do not guess an installed generator.
    assert sandbox.calls == []


@pytest.mark.parametrize("release,family", [
    ("ID=endeavouros\nID_LIKE=arch\n", "arch"),
    ("ID=garuda\nID_LIKE='arch'\n", "arch"),
    ("ID=linuxmint\nID_LIKE='ubuntu debian'\n", "debian"),
    ("ID=pop\nID_LIKE=ubuntu\n", "debian"),
    ("ID=ultramarine\nID_LIKE='fedora'\n", "fedora"),
])
def test_mutable_derivatives_are_routed_by_os_release_family(sandbox, release, family):
    sandbox.put("/etc/os-release", release)
    data = memory.status(sandbox.host)
    assert data["supported"]
    assert data["distro_family"] == family
    assert not data["immutable_image"]
    assert sandbox.calls == []


@pytest.mark.parametrize("distro", ["steamos", "bazzite", "alpine", "unknown"])
def test_unsupported_images_are_read_only(sandbox, distro):
    sandbox.put("/etc/os-release", f"ID={distro}")
    assert not memory.status(sandbox.host)["supported"]
    with pytest.raises(SetupError):
        memory.apply(sandbox.host, "swap-16")
    assert sandbox.calls == []


@pytest.mark.parametrize("release", [
    "ID=bazzite\nID_LIKE=fedora\nVARIANT_ID=bazzite-deck\n",
    "ID=steamos\nID_LIKE=arch\nVARIANT_ID=steamdeck\n",
    "ID=fedora\nID_LIKE=fedora\nVARIANT_ID=silverblue\n",
    "ID=fedora\nID_LIKE=fedora\nVARIANT_ID=kinoite\n",
])
def test_image_based_derivatives_never_fall_through_to_mutable_adapter(sandbox, release):
    sandbox.put("/etc/os-release", release)
    data = memory.status(sandbox.host)
    assert not data["supported"] and data["immutable_image"]
    assert "dedicated adapter" in data["reason"]


def test_supported_family_without_running_systemd_is_read_only(sandbox):
    sandbox.host.path("/run/systemd/system").rmdir()
    data = memory.status(sandbox.host)
    assert not data["supported"]
    assert "requires systemd" in data["reason"]


def test_ostree_fedora_and_non_bc250_are_not_mutable_targets(sandbox):
    sandbox.put("/run/ostree-booted", "")
    assert not memory.status(sandbox.host)["supported"]
    sandbox.host.path("/run/ostree-booted").unlink()
    sandbox.put("/sys/bus/pci/devices/0000:01:00.0/device", "0x1234")
    assert not memory.status(sandbox.host)["supported"]


@pytest.mark.parametrize("ttm", [8, 10, 12])
def test_ttm_live_apply_boot_and_independent_restore(sandbox, ttm):
    host = sandbox.host
    original_swaps = host.read("/proc/swaps")
    data = memory.apply(host, "preserve", ttm)
    assert data["ttm_current_pages"] == ttm * memory.GIB // os.sysconf("SC_PAGE_SIZE")
    assert data["ttm_restore_available"]
    sandbox.put(memory.TTM, "100")
    memory.boot(host)
    assert host.read(memory.TTM) == str(data["ttm_current_pages"])
    memory.apply(host, "preserve", -1)
    assert host.read(memory.TTM) == "12345"
    assert host.read("/proc/swaps") == original_swaps
    assert not host.path(memory.SERVICE_PATH).exists()


@pytest.mark.parametrize("policy,ttm", [("shell;id", 0), ("preserve", True), ("swap-16", 20), ("preserve", -1)])
def test_invalid_requests_do_not_write(sandbox, policy, ttm):
    with pytest.raises(SetupError):
        memory.apply(sandbox.host, policy, ttm)
    assert not sandbox.host.path(STATE).exists()


def test_readonly_or_small_ram_ttm_rejected(sandbox):
    sandbox.host.path(memory.TTM).chmod(0o444)
    with pytest.raises(SetupError, match="writable"):
        memory.apply(sandbox.host, "preserve", 8)
    sandbox.host.path(memory.TTM).chmod(0o644)
    sandbox.put("/proc/meminfo", "MemTotal: 4000000 kB\n")
    with pytest.raises(SetupError, match="exceeds"):
        memory.apply(sandbox.host, "preserve", 8)


@pytest.mark.parametrize("filesystem", ["ext4", "btrfs"])
def test_swap_install_idempotence_restore_and_reinstall(sandbox, filesystem):
    host = sandbox.host
    sandbox.fs = filesystem
    first = memory.apply(host, "swap-16")
    assert first["swap_active"]
    assert host.path(memory.SWAP).stat().st_size == 16 * memory.GIB
    assert host.path(memory.SWAP).stat().st_mode & 0o777 == 0o600
    assert host.read(memory.UNIT_PATH).startswith(MARKER.strip())
    memory.apply(host, "swap-16")
    assert sum(args[0] == "swapon" for args in sandbox.calls) == 1
    memory.apply(host, "restore")
    assert not host.path(memory.SWAP).exists()
    assert "/dev/user-swap" in memory.swaps(host)
    memory.apply(host, "swap-16")
    assert memory.status(host)["swap_active"]
    if filesystem == "btrfs":
        assert any(args[:3] == ("btrfs", "filesystem", "mkswapfile") for args in sandbox.calls)


def test_restore_defers_under_pressure_and_never_unlinks_live_swap(sandbox):
    host = sandbox.host
    memory.apply(host, "swap-16")
    sandbox.put("/proc/meminfo", "MemAvailable: 32 kB\n")
    restored = memory.apply(host, "restore")
    assert restored["restore_pending"] and host.path(memory.SWAP).exists()
    assert not any(args[0] == "swapoff" for args in sandbox.calls)
    sandbox.put("/proc/swaps", "Filename Type Size Used Priority\n/dev/user-swap partition 10000 0 -1\n")
    assert not memory.boot(host)["restore_pending"]
    assert not host.path(memory.SWAP).exists()
    assert not host.path(memory.SERVICE_PATH).exists()


def test_swapoff_failure_preserves_file_and_pending_journal(sandbox):
    memory.apply(sandbox.host, "swap-16")
    sandbox.fail = lambda args: args[0] == "swapoff"
    assert memory.apply(sandbox.host, "restore")["restore_pending"]
    assert sandbox.host.path(memory.SWAP).exists()


@pytest.mark.parametrize("obstacle", ["foreign-file", "symlink", "filesystem", "disk-full", "foreign-unit"])
def test_swap_preflight_and_failures_preserve_foreign_data(sandbox, monkeypatch, obstacle):
    host = sandbox.host
    if obstacle == "foreign-file":
        sandbox.put(memory.SWAP, "not BC250")
    elif obstacle == "symlink":
        target = sandbox.put("/user-important", "keep")
        host.path(memory.SWAP_DIR).symlink_to(target.parent)
    elif obstacle == "filesystem":
        sandbox.fs = "xfs"
    elif obstacle == "disk-full":
        monkeypatch.setattr(memory.shutil, "disk_usage", lambda path: SimpleNamespace(free=1))
    else:
        sandbox.put(memory.UNIT_PATH, "foreign unit")
    with pytest.raises(SetupError):
        memory.apply(host, "swap-16")
    assert not any(args[0] == "swapon" for args in sandbox.calls)
    if obstacle == "foreign-file":
        assert host.read(memory.SWAP) == "not BC250"
    if obstacle == "symlink":
        assert host.read("/user-important") == "keep"


def test_partial_failure_is_not_reported_as_success(sandbox):
    sandbox.fail = lambda args: args[0] == "swapon"
    with pytest.raises(SetupError):
        memory.apply(sandbox.host, "swap-16")
    assert sandbox.host.state("memory")["phase"] == "incomplete"
    with pytest.raises(SetupError, match="Incomplete"):
        memory.boot(sandbox.host)
    sandbox.fail = None
    assert memory.apply(sandbox.host, "restore")["configured_policy"] == "preserve"


def test_zswap_and_ttm_restore_independently(sandbox):
    host = sandbox.host
    memory.apply(host, "zswap-16", 8)
    assert host.read(memory.ZSWAP) == "1"
    memory.apply(host, "restore")
    assert host.read(memory.ZSWAP) == "N"
    assert memory.status(host)["configured_ttm_pages"] is not None
    memory.apply(host, "preserve", -1)
    assert host.read(memory.TTM) == "12345"


def test_existing_zram_is_preserved_and_blocks_redundant_compression(sandbox):
    host = sandbox.host
    sandbox.put("/usr/lib/systemd/system-generators/zram-generator", "generator")
    sandbox.put("/usr/lib/systemd/zram-generator.conf", "[zram0]\n")
    data = memory.status(host)
    assert "zram" not in data["policies"] and "zswap-16" not in data["policies"]
    assert "swap-16" in data["policies"]
    assert "preserved" in data["policy_reasons"]["zram"]
    with pytest.raises(SetupError, match="unavailable"):
        memory.apply(host, "zram")
    assert host.read("/usr/lib/systemd/zram-generator.conf") == "[zram0]"


@pytest.mark.parametrize("manager", [
    "/etc/default/zramswap",
    "/lib/systemd/system/zramswap.service",
    "/etc/conf.d/zram-init",
    "/etc/udev/rules.d/99-zram.rules",
])
def test_cross_distribution_zram_managers_are_preserved(sandbox, manager):
    sandbox.put("/usr/lib/systemd/system-generators/zram-generator", "generator")
    sandbox.put(manager, "foreign zram manager")
    data = memory.status(sandbox.host)
    assert "zram" not in data["policies"]
    assert "zswap-16" not in data["policies"]
    assert "swap-16" in data["policies"]


def test_zram_install_requires_reboot_and_restore_leaves_active_device(sandbox):
    host = sandbox.host
    sandbox.put("/usr/lib/systemd/system-generators/zram-generator", "generator")
    assert memory.apply(host, "zram")["zram_pending"]
    sandbox.put("/sys/block/zram0/size", "123")
    assert not memory.boot(host)["zram_pending"]
    result = memory.apply(host, "restore")
    assert result["zram_restore_pending"]
    assert not host.path(memory.ZRAM).exists()
    assert not any(args[0] == "swapoff" for args in sandbox.calls)


def test_payload_integrity_and_exact_postboot_table_verification(sandbox):
    raw = archive()
    assert hashlib.sha256(raw).hexdigest() == SHA256
    sandbox.host.path("/sys/firmware/acpi/tables/SSDT1").unlink()
    offset, index = 0, 2
    while offset + 110 <= len(raw):
        header = raw[offset:offset + 110]
        length, namesize = int(header[54:62], 16), int(header[94:102], 16)
        if raw[offset + 110:offset + 110 + namesize - 1] == b"TRAILER!!!":
            break
        start = (offset + 110 + namesize + 3) & ~3
        data = raw[start:start + length]
        offset = (start + length + 3) & ~3
        if length:
            assert sum(data) % 256 == 0
            sandbox.put(f"/sys/firmware/acpi/tables/SSDT{index}", data)
            index += 1
    assert acpi.table_status(sandbox.host)[0] == "active"
    sandbox.put("/sys/firmware/acpi/tables/SSDT2", sandbox.table(revision=2))
    assert acpi.table_status(sandbox.host)[0] == "foreign"


@pytest.mark.parametrize("backend", ["systemd_boot", "grub"])
def test_acpi_separate_entry_and_exact_restore(sandbox, backend):
    getattr(sandbox, backend)()
    host = sandbox.host
    original = host.path("/boot/initramfs-linux.img").read_bytes()
    config = host.path(acpi.GRUB_CONFIG).read_bytes() if backend == "grub" else host.path("/boot/loader/entries/arch.conf").read_bytes()
    assert acpi.status(host)["available"]
    result = acpi.install(host)
    assert result["status"] == "pending-reboot"
    assert host.path("/boot/initramfs-linux.img").read_bytes() == original
    if backend == "systemd_boot":
        content = host.read("/boot/loader/entries/bc250-acpi.conf")
        assert content.index("initrd /bc250-acpi.cpio") < content.index("initrd /amd-ucode.img")
        assert host.path("/boot/loader/entries/arch.conf").read_bytes() == config
    else:
        assert sandbox.grub_original.strip() in host.read(acpi.GRUB_OUTPUT)
        assert "GRUB_DEFAULT=bc250-acpi" in host.read(acpi.GRUB_CONFIG)
    assert acpi.uninstall(host)["status"] == "removed-pending-reboot"
    assert not host.path("/boot/bc250-acpi.cpio").exists()
    if backend == "grub":
        assert host.path(acpi.GRUB_CONFIG).read_bytes() == config
    else:
        assert acpi.efi_string(host, "LoaderEntryDefault") == "arch.conf"


@pytest.mark.parametrize("obstacle", ["secureboot", "lockdown", "uki", "foreign", "kernel", "fedora", "unknown"])
def test_acpi_rejects_unqualified_hosts_without_writes(sandbox, obstacle):
    sandbox.systemd_boot()
    host = sandbox.host
    if obstacle == "secureboot":
        sandbox.put("/sys/firmware/efi/efivars/SecureBoot-test", b"\0\0\0\0\1")
    elif obstacle == "lockdown":
        sandbox.put("/sys/kernel/security/lockdown", "none [integrity] confidentiality")
    elif obstacle == "uki":
        sandbox.efi("LoaderEntrySelected", "arch.efi")
    elif obstacle == "foreign":
        sandbox.put("/etc/initcpio/acpi_override/other.aml", b"custom")
    elif obstacle == "kernel":
        sandbox.put("/proc/config.gz", gzip.compress(b"# CONFIG_ACPI_TABLE_UPGRADE is not set"))
    elif obstacle == "fedora":
        sandbox.put("/etc/os-release", "ID=fedora")
    else:
        sandbox.put("/sys/firmware/acpi/tables/SSDT1", sandbox.table(revision=2))
    assert not acpi.status(host)["available"]
    with pytest.raises(SetupError):
        acpi.install(host)
    assert not host.path(STATE).exists()


def test_acpi_failed_bootctl_rolls_back_its_files(sandbox):
    sandbox.systemd_boot()
    sandbox.fail = lambda args: args[0] == "bootctl"
    with pytest.raises(SetupError):
        acpi.install(sandbox.host)
    assert not sandbox.host.path("/boot/bc250-acpi.cpio").exists()
    assert sandbox.host.path("/boot/loader/entries/arch.conf").exists()
    assert not sandbox.host.state("acpi")


def test_acpi_accepts_firmware_that_does_not_implement_secure_boot(sandbox):
    sandbox.systemd_boot()
    for path in sandbox.host.path("/sys/firmware/efi/efivars").glob("SecureBoot-*"):
        path.unlink()
    assert acpi.status(sandbox.host)["available"]


def test_acpi_reports_chainloaded_uki_instead_of_secure_boot(sandbox):
    sandbox.grub()
    sandbox.host.path("/sys/firmware/efi/efivars").mkdir(parents=True)
    sandbox.efi("StubInfo", "systemd-stub 261")
    sandbox.efi("LoaderImageIdentifier", r"\EFI\Linux\arch-linux.efi")
    result = acpi.status(sandbox.host)
    assert not result["available"]
    assert "EFI/UKI" in result["reason"]
    assert "Secure Boot" not in result["reason"]
    requirements = {item["id"]: item for item in result["requirements"]}
    assert not requirements["boot"]["passed"]
    assert "external initramfs" in requirements["boot"]["resolution"]
    assert requirements["secure-boot"]["passed"]


def test_acpi_requirement_report_explains_every_result_and_links_upstream(sandbox):
    sandbox.systemd_boot()
    result = acpi.status(sandbox.host)
    report = acpi.requirements_report(result)
    assert "BC250 ACPI FIX · COMPATIBILITY CHECK" in report
    assert "✓ Hardware and system:" in report
    assert "READY · 8/8 requirements passed" in report
    assert "Read-only inspection" in report
    assert acpi.UPSTREAM_URL in report


def test_acpi_requirement_report_gives_novice_fixes_for_blocked_host(sandbox):
    sandbox.grub()
    sandbox.host.path("/sys/firmware/efi/efivars").mkdir(parents=True)
    sandbox.efi("StubInfo", "systemd-stub 261")
    sandbox.efi("LoaderImageIdentifier", r"\EFI\Linux\arch-linux.efi")
    result = acpi.status(sandbox.host)
    report = acpi.requirements_report(result)
    assert "BLOCKED · 7/8 requirements passed" in report
    assert "✕ Boot layout:" in report
    assert "WHAT YOU NEED TO FIX" in report
    assert "Keep the current UKI as a recovery option" in report
    assert "Install only when the result is READY" in report


def test_acpi_modified_payload_is_preserved(sandbox):
    sandbox.systemd_boot()
    acpi.install(sandbox.host)
    sandbox.put("/boot/bc250-acpi.cpio", b"changed")
    with pytest.raises(SetupError, match="Modified"):
        acpi.uninstall(sandbox.host)
    assert sandbox.host.read("/boot/bc250-acpi.cpio") == "changed"
    assert sandbox.host.state("acpi")


def test_desktop_acpi_check_cache_expires_after_reboot_and_never_authorizes_install(sandbox, monkeypatch):
    sandbox.systemd_boot()
    assert acpi.check(sandbox.host)["available"]
    monkeypatch.setattr(acpi.os, "geteuid", lambda: 1000)
    sandbox.put("/proc/config.gz", gzip.compress(b"CONFIG_ACPI_TABLE_UPGRADE=n"))
    assert acpi.status(sandbox.host)["cached_probe"]
    with pytest.raises(SetupError, match="ACPI_TABLE_UPGRADE"):
        acpi.install(sandbox.host)
    sandbox.put("/proc/sys/kernel/random/boot_id", "boot-two")
    assert not acpi.status(sandbox.host)["available"]


def test_bridge_rejects_arbitrary_arguments_and_uses_one_finite_helper():
    from bc250cc.infrastructure.system_setup import command
    assert command("memory-apply", "swap-16", 8).count("sudo ") == 1
    for action, policy, ttm in (("sh", "preserve", 0), ("memory-apply", "$(id)", 0), ("memory-apply", "preserve", True)):
        with pytest.raises(ValueError):
            command(action, policy, ttm)
