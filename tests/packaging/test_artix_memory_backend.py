"""Artix integration using a private filesystem and simulated OS commands."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

LIB = Path(__file__).resolve().parents[2] / 'privileged/lib'
sys.path.insert(0, str(LIB))
import system_setup_memory as memory  # noqa: E402 - requires the source path configured above
import system_setup_ttm as ttm  # noqa: E402 - requires the source path configured above
from system_setup_common import Host, SetupError  # noqa: E402 - requires the source path configured above


class ArtixMemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls = []
        self.host = Host(Path(self.temp.name), runner=self.run_command)
        for name, text in {
            '/etc/os-release': 'ID=artix\n',
            '/run/openrc/softlevel': 'default',
            '/sys/bus/pci/devices/0000:01:00.0/vendor': '0x1002',
            '/sys/bus/pci/devices/0000:01:00.0/device': '0x13fe',
            '/proc/meminfo': 'MemTotal: 16000000 kB\nMemAvailable: 12000000 kB\n',
            '/proc/swaps': 'Filename Type Size Used Priority\n',
            '/proc/sys/kernel/random/boot_id': 'boot-one',
            memory.ZSWAP: 'N',
            memory.TTM: '12345',
        }.items():
            self.host.write(name, text)

    def run_command(self, *args, **kwargs):
        self.calls.append(args)
        self.assertNotEqual(args[0], 'systemctl')
        if args[0] == 'findmnt':
            return json.dumps({'filesystems': []}) if '--json' in args else 'ext4'
        if args[0] == 'zramctl':
            return '/dev/zram0'
        if args[0] == 'swapon':
            size = self.host.path(args[-1]).stat().st_size // 1024 if self.host.path(args[-1]).is_file() else 10000
            self.host.write('/proc/swaps', self.host.read('/proc/swaps') + f'\n{args[-1]} file {size} 0 -2\n')
        if args[0] == 'swapoff':
            self.host.write('/proc/swaps', '\n'.join(line for line in self.host.read('/proc/swaps').splitlines() if not line.startswith(args[-1])) + '\n')
        return ''

    def test_artix_profiles_are_available_without_systemd(self):
        state = memory.status(self.host)
        self.assertTrue(state['supported'])
        self.assertTrue({'zram', 'swap-16', 'zswap-16'} <= set(state['policies']))
        self.assertEqual(state['reason'], '')

    def test_openrc_backend_is_independent_of_supported_distribution_family(self):
        for distro in ('artix', 'arch', 'debian', 'ubuntu', 'fedora'):
            with self.subTest(distro=distro):
                self.host.write('/etc/os-release', f'ID={distro}\n')
                self.host.require_host(openrc=True)
                state = memory.status(self.host)
                self.assertTrue(state['supported'])
                self.assertIn('zram', state['policies'])
                memory.install_service(self.host)
                self.assertTrue(self.host.path(memory.OPENRC_SERVICE).exists())
        self.assertFalse(any(call[0] == 'systemctl' for call in self.calls))

    def test_zram_apply_boot_repeat_and_restore(self):
        state = memory.apply(self.host, 'zram')
        self.assertTrue(state['zram_pending'])
        script = self.host.read(memory.OPENRC_SERVICE)
        self.assertTrue(script.startswith('#!/sbin/openrc-run\n# Managed'))
        self.assertIn('memory-boot', script)
        self.assertFalse(self.host.path(memory.ZRAM).exists())
        memory.boot(self.host)
        memory.boot(self.host)
        self.assertEqual(sum(c[0] == 'zramctl' for c in self.calls), 1)
        memory.apply(self.host, 'restore')
        self.assertFalse(any(c[0] == 'swapoff' for c in self.calls))
        self.host.write('/proc/swaps', 'Filename Type Size Used Priority\n')
        self.host.write('/proc/sys/kernel/random/boot_id', 'boot-two')
        memory.boot(self.host)
        self.assertFalse(self.host.path(memory.OPENRC_SERVICE).exists())

    def test_foreign_zram_is_preserved(self):
        self.host.write('/etc/init.d/zram-init', '# foreign')
        self.assertNotIn('zram', memory.status(self.host)['policies'])
        with self.assertRaises(SetupError):
            memory.apply(self.host, 'zram')
        self.assertFalse(self.calls)

    def test_foreign_service_is_preserved(self):
        self.host.write(memory.OPENRC_SERVICE, '# foreign')
        with self.assertRaises(SetupError):
            memory.apply(self.host, 'zram')
        self.assertEqual(self.host.read(memory.OPENRC_SERVICE), '# foreign')

    def test_disk_swap_boot_and_zswap_reapply(self):
        self.host.write(memory.SWAP, 'fake swap', mode=0o600)
        state = {'phase': 'configured', 'policy': 'zswap-16', 'owns_swap': True,
                 'zswap_original': 'N'}
        self.host.save('memory', state)
        memory.boot(self.host)
        self.assertIn(('swapon', '--priority', '-2', memory.SWAP), self.calls)
        self.assertEqual(self.host.read(memory.ZSWAP), '1')

    def test_disk_swap_apply_and_restore_are_managed_by_openrc(self):
        from types import SimpleNamespace
        self.host.path('/var/lib').mkdir(parents=True)
        def simulate_allocation(path, size):
            with path.open('wb') as stream:
                stream.truncate(size)
            path.chmod(0o600)
        with patch.object(memory, '_allocate', simulate_allocation), patch.object(
                memory.shutil, 'disk_usage', return_value=SimpleNamespace(free=64 * memory.GIB)):
            state = memory.apply(self.host, 'swap-16')
        self.assertTrue(state['swap_active'])
        self.assertTrue(self.host.path(memory.OPENRC_SERVICE).exists())
        self.assertFalse(self.host.path(memory.UNIT_PATH).exists())
        memory.apply(self.host, 'restore')
        self.assertFalse(self.host.path(memory.SWAP).exists())
        self.assertFalse(self.host.path(memory.OPENRC_SERVICE).exists())

    def test_ttm_grub_apply_and_restore_without_systemd(self):
        import system_setup_kernel_args as kernel_args
        self.host.write('/etc/default/grub', 'GRUB_CMDLINE_LINUX_DEFAULT="quiet"\n')
        self.host.write('/boot/grub/grub.cfg', 'original')
        self.host.write('/proc/cmdline', 'quiet')
        self.host.write('/proc/iomem', '00000000-3ffffffff : System RAM\n')
        with patch.object(ttm, 'physical_ram', return_value=16 * memory.GIB):
            ttm.apply(self.host, 8)
            self.assertIn('ttm.pages_limit=', self.host.read(kernel_args.GRUB_DROPIN))
            ttm.apply(self.host, ttm.DEFAULT)
            self.assertFalse(self.host.path(kernel_args.GRUB_DROPIN).exists())


if __name__ == '__main__':
    unittest.main()
