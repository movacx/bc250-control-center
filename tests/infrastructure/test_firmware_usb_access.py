"""USB discovery through lsblk and drive changes through UDisks2.

Both talk to real hardware in the application; here every command goes to a
fake runner, so the tests pin what is asked for and how the answers are read
without a USB drive, a bus or any privilege.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from bc250cc.infrastructure.firmware import udisks as udisks_module
from bc250cc.infrastructure.firmware.udisks import UDisksClient, UDisksError, block_path
from bc250cc.infrastructure.firmware.usb_devices import (
    COLUMNS,
    LEGACY_COLUMNS,
    list_usb_drives,
    parse_lsblk,
)

GB = 1000 ** 3

LSBLK = {
    "blockdevices": [
        {
            "name": "sda", "path": "/dev/sda", "type": "disk", "tran": "usb", "rm": True,
            "ro": False, "size": 124780000000, "vendor": "VendorC ", "model": "ProductCode",
            "serial": "ABC123", "label": None, "fstype": None, "fsver": None,
            "mountpoints": [None],
            "children": [
                {"name": "sda1", "path": "/dev/sda1", "type": "part", "size": 124700000000,
                 "label": "Ventoy", "fstype": "exfat", "fsver": "1.0",
                 "mountpoints": ["/run/media/user/Ventoy"]},
                {"name": "sda2", "path": "/dev/sda2", "type": "part", "size": 33554432,
                 "label": "VTOYEFI", "fstype": "vfat", "fsver": "FAT16", "mountpoints": [None]},
            ],
        },
        {
            "name": "nvme0n1", "path": "/dev/nvme0n1", "type": "disk", "tran": "nvme", "rm": False,
            "ro": False, "size": 512000000000, "mountpoints": [None],
            "children": [{"name": "nvme0n1p2", "type": "part", "mountpoints": ["/", "/home"]}],
        },
        {"name": "sr0", "path": "/dev/sr0", "type": "rom", "tran": "usb", "size": 1024},
        {"name": "loop0", "path": "/dev/loop0", "type": "loop", "size": 1024},
    ]
}


def _completed(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


# ------------------------------------------------------------------ lsblk

def test_only_usb_disks_are_listed_with_their_partitions():
    drives = parse_lsblk(LSBLK)
    assert [drive.name for drive in drives] == ["sda"]
    drive = drives[0]
    assert drive.display_name == "VendorC ProductCode"
    assert drive.size == 124780000000
    assert drive.removable and not drive.read_only
    assert drive.volume_labels == ("Ventoy", "VTOYEFI")
    assert drive.all_mountpoints == ("/run/media/user/Ventoy",)
    assert drive.partitions[1].fsver == "FAT16"
    assert drive.eligible


def test_old_util_linux_output_is_understood():
    payload = {
        "blockdevices": [{
            "name": "sdb", "type": "disk", "tran": "usb", "rm": "1", "ro": "0",
            "size": "8000000000", "mountpoint": None,
            "children": [{"name": "sdb1", "size": "7999000000", "mountpoint": "/media/stick"}],
        }]
    }
    drive = parse_lsblk(payload)[0]
    assert drive.path == "/dev/sdb"
    assert drive.removable and not drive.read_only
    assert drive.size == 8 * GB
    assert drive.partitions[0].mountpoints == ("/media/stick",)


@pytest.mark.parametrize("payload", [None, [], {"blockdevices": None}, {"blockdevices": ["x", 3]}])
def test_malformed_output_lists_nothing(payload):
    assert parse_lsblk(payload) == []


def test_lsblk_is_asked_for_json_bytes_and_every_column():
    calls = []

    def runner(command, **options):
        calls.append((command, options))
        return _completed(json.dumps(LSBLK))

    assert [drive.name for drive in list_usb_drives(runner)] == ["sda"]
    command, options = calls[0]
    assert command == ["lsblk", "--json", "--bytes", "--output", ",".join(COLUMNS)]
    assert options["env"]["LC_ALL"] == "C"
    assert options["check"] is False and options["timeout"] > 0


def test_lsblk_without_the_plural_column_is_asked_again_the_old_way():
    calls = []

    def runner(command, **_options):
        calls.append(command[-1])
        if "MOUNTPOINTS" in command[-1]:
            return _completed(returncode=1, stderr="lsblk: unknown column: MOUNTPOINTS")
        return _completed(json.dumps(LSBLK))

    assert len(list_usb_drives(runner)) == 1
    assert calls == [",".join(COLUMNS), ",".join(LEGACY_COLUMNS)]


@pytest.mark.parametrize(
    "runner",
    [
        lambda *_a, **_k: _completed(returncode=1),
        lambda *_a, **_k: _completed("not json"),
        lambda *_a, **_k: (_ for _ in ()).throw(FileNotFoundError("lsblk")),
        lambda *_a, **_k: (_ for _ in ()).throw(subprocess.TimeoutExpired("lsblk", 10)),
    ],
)
def test_a_failing_lsblk_lists_no_drives_instead_of_crashing(runner):
    assert list_usb_drives(runner) == []


# ---------------------------------------------------------------- UDisks2

class _Bus:
    """Answers busctl the way UDisks2 would, and remembers every call."""

    def __init__(self, answers=None, failures=None):
        self.calls: list[list[str]] = []
        self.answers = answers or {}
        self.failures = failures or {}

    def __call__(self, command, **options):
        assert command[:3] == ["busctl", "--system", "--json=short"]
        assert options["check"] is False
        arguments = command[4:]
        self.calls.append(arguments)
        key = (arguments[0], arguments[2], arguments[4] if len(arguments) > 4 else "")
        if key in self.failures:
            return _completed(returncode=1, stderr=f"Call failed: {self.failures[key]}")
        if key in self.answers:
            return _completed(json.dumps({"type": "x", "data": self.answers[key]}))
        return _completed("")


ROOT = "/org/freedesktop/UDisks2/block_devices"


def test_block_paths_only_accept_kernel_names():
    assert block_path("sdb") == f"{ROOT}/sdb"
    assert block_path("nvme0n1") == f"{ROOT}/nvme0n1"
    for name in ("", "../sda", "sdb/..", "SDB", "sd b", "1sdb"):
        with pytest.raises(UDisksError):
            block_path(name)


def test_system_hint_and_bus_come_from_udisks_itself():
    bus = _Bus(answers={
        ("get-property", f"{ROOT}/sdb", "HintSystem"): False,
        ("get-property", f"{ROOT}/sdb", "Drive"): "/org/freedesktop/UDisks2/drives/Stick",
        ("get-property", "/org/freedesktop/UDisks2/drives/Stick", "ConnectionBus"): "usb",
    })
    client = UDisksClient(bus)
    assert client.is_system_device("sdb") is False
    assert client.connection_bus("sdb") == "usb"


def test_a_block_without_a_drive_has_no_bus():
    bus = _Bus(answers={("get-property", f"{ROOT}/loop0", "Drive"): "/"})
    assert UDisksClient(bus).connection_bus("loop0") == ""


def test_mount_points_are_decoded_from_byte_arrays():
    point = list(b"/run/media/user/BC250BIOS\0")
    bus = _Bus(answers={("get-property", f"{ROOT}/sdb1", "MountPoints"): [point]})
    assert UDisksClient(bus).mount_points("sdb1") == ["/run/media/user/BC250BIOS"]


def test_a_block_that_is_not_a_filesystem_has_no_mount_points():
    bus = _Bus(failures={("get-property", f"{ROOT}/sdb", "MountPoints"): "No such interface"})
    assert UDisksClient(bus).mount_points("sdb") == []


def test_erase_writes_an_empty_dos_table_tearing_down_mounts():
    bus = _Bus()
    UDisksClient(bus).erase_to_empty_mbr("sdb")
    assert bus.calls[-1] == [
        "call", "org.freedesktop.UDisks2", f"{ROOT}/sdb", "org.freedesktop.UDisks2.Block",
        "Format", "sa{sv}", "dos", "1", "tear-down", "b", "true",
    ]


def test_the_fat32_partition_starts_at_one_mib_with_type_0c_and_the_kit_label():
    bus = _Bus(answers={
        ("call", f"{ROOT}/sdb", "CreatePartitionAndFormat"): [f"{ROOT}/sdb1"],
    })
    assert UDisksClient(bus).create_fat32_partition("sdb", "BC250BIOS") == "sdb1"
    assert bus.calls[-1][4:] == [
        "CreatePartitionAndFormat", "ttssa{sv}sa{sv}",
        str(1024 * 1024), "0", "0x0c", "", "0",
        "vfat", "2", "label", "s", "BC250BIOS", "update-partition-type", "b", "true",
    ]


def test_a_partition_udisks_does_not_report_is_an_error():
    bus = _Bus(answers={("call", f"{ROOT}/sdb", "CreatePartitionAndFormat"): ["/somewhere/else"]})
    with pytest.raises(UDisksError, match="did not report the new partition"):
        UDisksClient(bus).create_fat32_partition("sdb", "BC250BIOS")


def test_mount_reuses_where_the_desktop_already_mounted_it():
    point = list(b"/run/media/user/BC250BIOS\0")
    bus = _Bus(answers={("get-property", f"{ROOT}/sdb1", "MountPoints"): [point]})
    assert UDisksClient(bus).mount("sdb1") == "/run/media/user/BC250BIOS"
    assert not any(call[0] == "call" for call in bus.calls)


def test_mount_asks_udisks_when_nothing_mounted_it():
    bus = _Bus(answers={
        ("get-property", f"{ROOT}/sdb1", "MountPoints"): [],
        ("call", f"{ROOT}/sdb1", "Mount"): ["/run/media/user/BC250BIOS"],
    })
    assert UDisksClient(bus).mount("sdb1") == "/run/media/user/BC250BIOS"


def test_mount_losing_the_race_to_an_automounter_uses_its_mount():
    class _Race(_Bus):
        def __call__(self, command, **options):
            result = super().__call__(command, **options)
            if command[4:][0] == "call":
                point = list(b"/run/media/user/BC250BIOS\0")
                self.answers[("get-property", f"{ROOT}/sdb1", "MountPoints")] = [point]
            return result

    bus = _Race(
        answers={("get-property", f"{ROOT}/sdb1", "MountPoints"): []},
        failures={("call", f"{ROOT}/sdb1", "Mount"): "Already mounted"},
    )
    assert UDisksClient(bus).mount("sdb1") == "/run/media/user/BC250BIOS"


def test_udisks_errors_carry_the_services_own_message():
    bus = _Bus(failures={("call", f"{ROOT}/sdb", "Format"): "Not authorized to perform operation"})
    with pytest.raises(UDisksError, match="^Not authorized to perform operation$"):
        UDisksClient(bus).erase_to_empty_mbr("sdb")


def test_an_unreadable_answer_is_an_error():
    def runner(*_args, **_options):
        return _completed("<xml/>")

    with pytest.raises(UDisksError, match="Unexpected answer"):
        UDisksClient(runner).property(f"{ROOT}/sdb", "x", "y")


def test_power_off_goes_to_the_drive_object():
    bus = _Bus(answers={("get-property", f"{ROOT}/sdb", "Drive"): "/org/freedesktop/UDisks2/drives/Stick"})
    UDisksClient(bus).power_off("sdb")
    assert bus.calls[-1][:5] == [
        "call", "org.freedesktop.UDisks2", "/org/freedesktop/UDisks2/drives/Stick",
        "org.freedesktop.UDisks2.Drive", "PowerOff",
    ]


def test_availability_needs_busctl_and_an_answering_service(monkeypatch):
    monkeypatch.setattr(udisks_module.shutil, "which", lambda _name: None)
    assert udisks_module.available(_Bus()) is False
    monkeypatch.setattr(udisks_module.shutil, "which", lambda _name: "/usr/bin/busctl")
    answering = _Bus(answers={("get-property", udisks_module.MANAGER, "Version"): "2.10.1"})
    assert udisks_module.available(answering) is True
    silent = _Bus(failures={("get-property", udisks_module.MANAGER, "Version"): "not activatable"})
    assert udisks_module.available(silent) is False
