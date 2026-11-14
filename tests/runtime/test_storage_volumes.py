"""Which mounts count as disks, on the layouts each distribution really has."""

from __future__ import annotations

from collections import namedtuple

import pytest

from bc250cc.infrastructure.sensor_inventory import SensorInventory
from bc250cc.infrastructure.storage_volumes import decode_udev_label, list_real_disks

Part = namedtuple("Part", "device mountpoint fstype opts")
Usage = namedtuple("Usage", "total used free percent")

GIB = 1 << 30


def _usage(sizes):
    """A ``psutil.disk_usage`` stand-in: total GiB by mount point, 25 % used."""
    def read(mountpoint):
        if mountpoint not in sizes:
            raise OSError(5, "Input/output error")
        total = int(sizes[mountpoint] * GIB)
        return Usage(total, total // 4, total - total // 4, 25.0)
    return read


def _mounts(disks):
    return [disk["mountpoint"] for disk in disks]


ARCH = [
    Part("/dev/nvme0n1p2", "/", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p1", "/boot", "vfat", "rw,relatime,fmask=0022"),
    Part("/dev/loop0", "/var/lib/snapd/snap/core/1", "squashfs", "ro,nodev"),
]

# Fedora Atomic: composefs "/" and the btrfs device again at /sysroot, /etc
# and /var (a statvfs of the composefs "/" reports a full 6 MiB image).
BAZZITE = [
    Part("composefs", "/", "overlay", "ro,relatime"),
    Part("/dev/nvme0n1p3", "/sysroot", "btrfs", "ro,relatime,subvol=/root"),
    Part("/dev/nvme0n1p3", "/etc", "btrfs", "rw,relatime,subvol=/root"),
    Part("/dev/nvme0n1p3", "/var", "btrfs", "rw,relatime,subvol=/var"),
    Part("/dev/nvme0n1p3", "/var/home", "btrfs", "rw,relatime,subvol=/home"),
    Part("/dev/nvme0n1p2", "/boot", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p1", "/boot/efi", "vfat", "rw,relatime"),
]

# SteamOS: a read-only btrfs root per slot, a 256 MiB /var, and /home bound
# again at a dozen offload paths.
STEAMOS = [
    Part("/dev/nvme0n1p4", "/", "btrfs", "ro,noatime"),
    Part("/dev/nvme0n1p6", "/var", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p8", "/home", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p8", "/opt", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p8", "/root", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p8", "/srv", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p8", "/var/lib/flatpak", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p8", "/var/log", "ext4", "rw,relatime"),
    Part("/dev/nvme0n1p1", "/esp", "vfat", "rw,relatime"),
    Part("/dev/nvme0n1p2", "/efi", "vfat", "rw,relatime"),
]


def test_arch_lists_only_the_root_disk():
    disks = list_real_disks(ARCH, _usage({"/": 465, "/boot": 1}))

    assert _mounts(disks) == ["/"]
    assert disks[0]["kind"] == "system"
    assert disks[0]["label"] == "System"
    assert disks[0]["device"] == "/dev/nvme0n1p2"
    assert disks[0]["total"] == 465 * GIB


def test_bazzite_shows_the_system_btrfs_once_and_never_the_composefs_image():
    disks = list_real_disks(BAZZITE, _usage({"/var": 237, "/etc": 237, "/var/home": 237, "/boot": 1}))

    assert len(disks) == 1
    assert disks[0]["mountpoint"] == "/var/home"
    assert disks[0]["kind"] == "system"
    assert disks[0]["device"] == "/dev/nvme0n1p3"


def test_steamos_skips_the_read_only_root_and_the_small_var_and_shows_home_once():
    sizes = {"/var": 0.25, "/home": 220, "/opt": 220, "/root": 220, "/srv": 220, "/var/log": 220}
    disks = list_real_disks(STEAMOS, _usage(sizes))

    assert _mounts(disks) == ["/home"]
    assert disks[0]["kind"] == "home"
    assert disks[0]["label"] == "Home"


def test_an_external_usb_drive_gets_its_own_row_under_its_volume_label():
    parts = ARCH + [Part("/dev/sdb1", "/run/media/deck/0F3C-1A2B", "exfat", "rw,nosuid,nodev")]
    disks = list_real_disks(parts, _usage({"/": 465, "/run/media/deck/0F3C-1A2B": 0.5}), {"/dev/sdb1": "백업"})

    assert _mounts(disks) == ["/", "/run/media/deck/0F3C-1A2B"]
    usb = disks[1]
    assert usb["kind"] == "external"
    assert usb["external"] is True
    # Small external media stay; only internal plumbing partitions are cut.
    assert usb["total"] == GIB // 2
    assert usb["label"] == "백업"


def test_an_external_drive_without_a_label_is_named_after_its_mount_point():
    parts = STEAMOS + [Part("/dev/mmcblk0p1", "/run/media/mmcblk0p1", "ext4", "rw,nosuid")]
    disks = list_real_disks(parts, _usage({"/var": 0.25, "/home": 220, "/run/media/mmcblk0p1": 512}))

    assert [disk["label"] for disk in disks] == ["Home", "mmcblk0p1"]


def test_a_read_only_external_drive_is_still_shown():
    parts = ARCH + [Part("/dev/sdc1", "/run/media/user/Windows", "ntfs3", "ro,nosuid")]
    disks = list_real_disks(parts, _usage({"/": 465, "/run/media/user/Windows": 931}))

    assert _mounts(disks) == ["/", "/run/media/user/Windows"]


def test_unplugging_the_drive_drops_its_row_on_the_next_read():
    usb = Part("/dev/sdb1", "/media/user/Backup", "ext4", "rw")
    sizes = {"/": 465, "/media/user/Backup": 931}

    assert len(list_real_disks(ARCH + [usb], _usage(sizes))) == 2
    assert _mounts(list_real_disks(ARCH, _usage(sizes))) == ["/"]


def test_a_drive_that_vanished_mid_read_is_left_out_instead_of_raising():
    parts = ARCH + [Part("/dev/sdb1", "/media/user/Gone", "ext4", "rw")]
    assert _mounts(list_real_disks(parts, _usage({"/": 465}))) == ["/"]


def test_bind_mounts_and_repeated_devices_are_one_disk():
    parts = ARCH + [
        Part("/dev/sda1", "/mnt/games", "ext4", "rw"),
        Part("/dev/sda1", "/home/user/Games", "ext4", "rw"),
        Part("/dev/sda1", "/srv/games", "ext4", "rw"),
    ]
    sizes = {"/": 465, "/mnt/games": 931, "/home/user/Games": 931, "/srv/games": 931}
    disks = list_real_disks(parts, _usage(sizes))

    assert _mounts(disks) == ["/", "/mnt/games"]


def test_two_drives_with_the_same_name_are_told_apart_by_device():
    parts = ARCH + [
        Part("/dev/sdb1", "/media/a/Data", "ext4", "rw"),
        Part("/dev/sdc1", "/media/b/Data", "ext4", "rw"),
    ]
    disks = list_real_disks(parts, _usage({"/": 465, "/media/a/Data": 100, "/media/b/Data": 200}))

    assert [disk["label"] for disk in disks] == ["System", "Data (sdb1)", "Data (sdc1)"]


def test_a_separate_home_partition_follows_the_system_disk():
    parts = ARCH + [Part("/dev/nvme0n1p3", "/home", "ext4", "rw")]
    disks = list_real_disks(parts, _usage({"/": 60, "/home": 400}))

    assert [(disk["mountpoint"], disk["kind"]) for disk in disks] == [("/", "system"), ("/home", "home")]


@pytest.mark.parametrize("part", [
    Part("tmpfs", "/tmp", "tmpfs", "rw"),
    Part("server:/export", "/mnt/nas", "nfs4", "rw"),
    Part("//nas/share", "/mnt/share", "cifs", "rw"),
    Part("/dev/zram0", "/var/tmp", "ext4", "rw"),
    Part("/dev/sr0", "/run/media/user/DVD", "iso9660", "ro"),
    Part("/dev/loop3", "/run/media/user/image", "squashfs", "ro"),
])
def test_pseudo_network_and_image_mounts_are_not_disks(part):
    sizes = {"/": 465, part.mountpoint: 100}
    assert _mounts(list_real_disks(ARCH + [part], _usage(sizes))) == ["/"]


def test_zfs_datasets_of_one_pool_are_one_disk():
    parts = [
        Part("rpool/ROOT/ubuntu", "/", "zfs", "rw"),
        Part("rpool/USERDATA/home", "/home", "zfs", "rw"),
    ]
    disks = list_real_disks(parts, _usage({"/": 900, "/home": 900}))

    assert len(disks) == 1
    assert disks[0]["device"] == "rpool"


def test_udev_labels_are_decoded():
    assert decode_udev_label(r"My\x20Disk") == "My Disk"
    assert decode_udev_label(r"\xeb\xb0\xb1\xec\x97\x85") == "백업"


def test_every_disk_after_the_first_is_a_space_reading_in_the_sensor_list():
    readings = SensorInventory._storage_readings({
        "device": "nvme0n1",
        "usage_percent": 40.0,
        "volumes": [
            {"mountpoint": "/", "label": "System", "percent": 40.0},
            {"mountpoint": "/run/media/u/Backup", "label": "Backup", "percent": 71.5},
        ],
    })
    spaces = {reading.key: (reading.device, reading.value) for reading in readings if reading.key.startswith("disk/space")}

    assert spaces == {"disk/space": ("nvme0n1", 40.0), "disk/space//run/media/u/Backup": ("Backup", 71.5)}


def test_each_disk_gets_its_own_read_write_and_active_time():
    from bc250cc.infrastructure.sistema_repository import SistemaRepository

    Counter = namedtuple("Counter", "read_bytes write_bytes busy_time")
    repo = SistemaRepository.__new__(SistemaRepository)
    repo._metricas_rt_volumes = {}
    samples = iter([
        {"nvme0n1p2": Counter(0, 0, 0), "sdb1": Counter(0, 0, 0)},
        {"nvme0n1p2": Counter(1024, 0, 10), "sdb1": Counter(4 * 1024 ** 2, 2048, 500)},
    ])
    repo._contadores_por_disco = lambda: next(samples)

    def disks():
        return [{"mountpoint": "/", "device": "/dev/nvme0n1p2"},
                {"mountpoint": "/run/media/u/USB", "device": "/dev/sdb1"}]

    first = disks()
    repo._actividad_por_disco(first, 0.0)
    assert first[1]["read_bps"] == 0.0  # no rate before a second sample
    second = disks()
    repo._actividad_por_disco(second, 1.0)
    assert second[1]["io_device"] == "sdb1"
    assert second[1]["read_bps"] == 4 * 1024 ** 2
    assert second[1]["write_bps"] == 2048
    assert second[1]["active_percent"] == 50.0
    assert second[0]["read_bps"] == 1024

    # Unplugged: its counters are dropped with it.
    repo._contadores_por_disco = lambda: {"nvme0n1p2": Counter(2048, 0, 20)}
    repo._actividad_por_disco(disks()[:1], 1.0)
    assert set(repo._metricas_rt_volumes) == {"/"}
