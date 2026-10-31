"""Regression checks runnable with unittest without desktop dependencies."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "privileged/lib"))
import system_setup_kernel_args as kernel
from system_setup_common import Host, SetupError


class RefindBootOptions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.host = Host(Path(self.temp.name))
        self.host.write(kernel.CMDLINE, r"ro root=UUID=test initrd=boot\initrd.img-7.2")
        variables = "/sys/firmware/efi/efivars/"
        self.host.write(variables + "BootCurrent-test", b"\x07\x00\x00\x00\x0a\x00")
        self.host.write(variables + "Boot000A-test", b"\x07\x00\x00\x00" + "rEFInd Boot Manager".encode("utf-16-le"))

    def test_detect_direct_boot_and_exclude_grub_chainload(self):
        self.assertTrue(kernel._refind_direct(self.host))
        self.host.write(kernel.CMDLINE, "BOOT_IMAGE=/boot/vmlinuz root=UUID=test")
        self.assertFalse(kernel._refind_direct(self.host))

    def test_write_update_restore_and_automatic_initrd_selection(self):
        kernel._write(self.host, "refind", ["nosmt"], [])
        config = self.host.read(kernel.REFIND_CONFIG)
        self.assertIn("root=UUID=test nosmt", config)
        self.assertNotIn("initrd=", config)
        kernel._write(self.host, "refind", ["loglevel=0"], ["nosmt"])
        config = self.host.read(kernel.REFIND_CONFIG)
        self.assertNotIn("nosmt", config)
        self.assertIn("loglevel=0", config)
        kernel._write(self.host, "refind", [], ["loglevel=0"])
        self.assertFalse(self.host.path(kernel.REFIND_CONFIG).exists())

    def test_migrate_grub_state_and_clear_reboot_after_matching_boot(self):
        self.host.write("/etc/os-release", "ID=debian\n")
        self.host.write("/sys/bus/pci/devices/0000:01:00.0/vendor", "0x1002")
        self.host.write("/sys/bus/pci/devices/0000:01:00.0/device", "0x13fe")
        wanted = ["mitigations=off", "nosmt", "loglevel=0"]
        self.host.save("kernel-options", {"backend": "grub", "arguments": wanted})
        result = kernel.apply(self.host, wanted)
        self.assertEqual(result["backend"], "refind")
        self.assertTrue(result["reboot_required"])
        self.host.write(kernel.CMDLINE, r"ro root=UUID=test initrd=boot\initrd.img-7.2 " + " ".join(wanted))
        self.assertFalse(kernel.status(self.host)["reboot_required"])

    def test_foreign_menu_is_never_replaced(self):
        self.host.write(kernel.REFIND_CONFIG, '"My boot" "root=UUID=test"')
        with self.assertRaises(SetupError):
            kernel._write(self.host, "refind", ["nosmt"], [])

    def test_saved_grub_options_are_stale_for_direct_refind(self):
        saved = {"arguments": ["nosmt"]}
        self.host.write(kernel.GRUB_DROPIN, 'GRUB_CMDLINE_LINUX_DEFAULT="nosmt"')
        self.assertEqual(kernel._stale(self.host, "refind", saved), {"nosmt"})


if __name__ == "__main__":
    unittest.main()
