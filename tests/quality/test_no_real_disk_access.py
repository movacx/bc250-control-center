"""The suite-wide guard: no test may mount, unmount, format or write a real disk."""

import subprocess

import pytest

from tests.conftest import disk_command


@pytest.mark.parametrize("argv", [
    ["umount", "/dev/sda1"], ["sudo", "mount", "/dev/sda1", "/mnt"], ["pkexec", "/usr/bin/wipefs", "-a", "/dev/sda"],
    ["mkfs.vfat", "/dev/sdb1"], ["dd", "if=/dev/zero", "of=/dev/sdb"], ["udisksctl", "unmount", "-b", "/dev/sda1"],
    ["busctl", "--system", "call", "org.freedesktop.UDisks2", "/org/freedesktop/UDisks2/block_devices/sda1",
     "org.freedesktop.UDisks2.Filesystem", "Unmount", "a{sv}", "0"],
])
def test_disk_commands_fail_the_test_instead_of_running(argv):
    assert disk_command(argv)
    with pytest.raises(AssertionError, match="a test tried to"):
        subprocess.run(argv, check=False)


def test_reading_udisks_and_ordinary_commands_still_work():
    assert not disk_command(["busctl", "--system", "get-property", "org.freedesktop.UDisks2", "/x", "i", "Size"])
    assert subprocess.run(["true"], check=False).returncode == 0


def test_writing_a_block_device_from_python_fails():
    with pytest.raises(AssertionError, match="a test tried to"):
        open("/dev/sdz", "wb")  # noqa: SIM115
