"""Kernel options on plain Limine (Arch without CachyOS' limine-mkinitcpio).

The options go straight onto every ``cmdline:`` line of limine.conf on the
boot partition and come off again byte for byte. Nothing here touches a real
boot partition: every path lives under a temporary root.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[2] / "privileged/lib"
sys.path.insert(0, str(LIB))
import system_setup_kernel_args as kernel_args  # noqa: E402
import system_setup_ttm as ttm  # noqa: E402
from system_setup_common import Host, SetupError  # noqa: E402

CONF = """timeout: 3

/Arch Linux
    protocol: linux
    path: boot():/vmlinuz-linux
    cmdline: root=PARTUUID=1bd6 zswap.enabled=0 rw rootfstype=ext4
    module_path: boot():/initramfs-linux.img

/Arch Linux (fallback)
    protocol: linux
    path: boot():/vmlinuz-linux
    cmdline: root=PARTUUID=1bd6 rw rootfstype=ext4
    module_path: boot():/initramfs-linux-fallback.img
"""


@pytest.fixture
def host(tmp_path):
    host = Host(tmp_path, runner=lambda *args, check=True: "")

    def put(name, text):
        path = host.path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    put("/etc/os-release", 'ID="arch"\n')
    host.path("/run/systemd/system").mkdir(parents=True)
    put("/sys/bus/pci/devices/0000:01:00.0/vendor", "0x1002")
    put("/sys/bus/pci/devices/0000:01:00.0/device", "0x13fe")
    put("/proc/cmdline", "root=PARTUUID=1bd6 zswap.enabled=0 rw rootfstype=ext4\n")
    put("/proc/sys/kernel/random/boot_id", "boot-one")
    put("/proc/meminfo", "MemTotal: 16000000 kB\n")
    put("/boot/limine.conf", CONF)
    host.path("/var/lib").mkdir(parents=True)
    host.put = put
    return host


def _cmdlines(host) -> list[str]:
    return [line.strip() for line in host.path("/boot/limine.conf").read_text().splitlines()
            if line.strip().startswith("cmdline:")]


def test_plain_limine_is_recognised_and_offered(host):
    assert kernel_args.backend(host) == "limine-conf"
    status = kernel_args.status(host)
    assert status["available"] is True
    assert ttm.backend(host) == ("limine-conf", "")


def test_grub_booted_machine_with_a_stray_limine_conf_is_not_limine(host):
    host.put("/proc/cmdline", "BOOT_IMAGE=/vmlinuz-linux root=PARTUUID=1bd6 rw\n")
    assert kernel_args.backend(host) != "limine-conf"


def test_switches_go_on_every_kernel_line_and_come_off_byte_for_byte(host):
    kernel_args.apply(host, ["mitigations=off", "nosmt"])
    lines = _cmdlines(host)
    assert len(lines) == 2
    assert all(line.endswith(" mitigations=off nosmt") for line in lines)
    assert kernel_args.status(host)["arguments"]["nosmt"]["configured"] is True
    kernel_args.apply(host, ["nosmt"])
    assert all(line.endswith("rootfstype=ext4 nosmt") for line in _cmdlines(host))
    kernel_args.apply(host, [])
    assert host.path("/boot/limine.conf").read_text() == CONF
    # The file as it was before the first change is kept for recovery.
    assert any(host.path("/var/lib").rglob("limine.conf.before-bc250"))


def test_gpu_memory_limit_is_set_and_removed_on_its_own(host):
    kernel_args.apply(host, ["mitigations=off"])
    kernel_args.set_value(host, "ttm.pages_limit", "3145728")
    assert all(line.endswith(" mitigations=off ttm.pages_limit=3145728") for line in _cmdlines(host))
    kernel_args.set_value(host, "ttm.pages_limit", None)
    assert all(line.endswith(" mitigations=off") for line in _cmdlines(host))
    kernel_args.apply(host, [])
    assert host.path("/boot/limine.conf").read_text() == CONF


def test_a_word_the_owner_moved_is_still_taken_out(host):
    kernel_args.apply(host, ["nosmt"])
    text = host.path("/boot/limine.conf").read_text().replace(
        "root=PARTUUID=1bd6 zswap.enabled=0 rw rootfstype=ext4 nosmt",
        "root=PARTUUID=1bd6 nosmt zswap.enabled=0 rw rootfstype=ext4",
    )
    host.put("/boot/limine.conf", text)
    kernel_args.apply(host, [])
    assert all("nosmt" not in line for line in _cmdlines(host))


def test_a_conf_without_kernel_lines_is_refused_and_left_alone(host):
    host.put("/boot/limine.conf", "timeout: 3\n")
    with pytest.raises(SetupError):
        kernel_args.apply(host, ["nosmt"])
    assert host.path("/boot/limine.conf").read_text() == "timeout: 3\n"


def test_cachyos_limine_tooling_still_wins(host):
    host.put("/etc/default/limine", 'KERNEL_CMDLINE[default]="quiet"\n')
    assert kernel_args.backend(host) == "limine"


def test_limine_is_recognised_from_its_loader_info_without_root(host):
    # Limine started through EFI/BOOT/BOOTX64.EFI: the boot entry is "UEFI OS",
    # but the Boot Loader Interface variable names the loader.
    path = host.path(kernel_args.LOADER_INFO)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x06\x00\x00\x00" + "Limine 12.9.6\0".encode("utf-16-le"))
    assert kernel_args._limine_entry_booted(host) is True
