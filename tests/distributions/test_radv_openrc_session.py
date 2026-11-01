"""The OpenRC login hook inherits the existing generator's boot safeguards."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/system/bc250-async-compute-radv.sh'


class RadvOpenrcSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        text = SCRIPT.read_text()
        values = {name: re.search(rf'^{name}=(.*)$', text, re.M)[1].strip('"')
                  for name in ('MARKER', 'CONF_DIR', 'PREFIX_ROOT', 'MIN_MAJOR', 'MIN_MINOR')}
        assignments = ''.join(f'{name}={value!r}\n' for name, value in values.items())
        body = re.search(r'<<GEN\n(.*?)\nGEN\n', text, re.S)[1]
        self.generator = self.root / 'generator'
        result = subprocess.run(['bash', '-c', assignments + 'cat <<GEN\n' + body + '\nGEN\n'],
                                capture_output=True, text=True, check=True)
        self.generator.write_text(result.stdout)
        self.generator.chmod(0o755)
        profile = re.search(r"<<'PROFILE'\n(.*?)\nPROFILE\n", text, re.S)[1]
        self.profile = self.root / 'profile.sh'
        self.profile.write_text(profile.replace('/run/openrc/softlevel', str(self.root / 'softlevel'))
                               .replace('/usr/lib/bc250cc-radv/session-environment', str(self.generator)))
        self.icd = '/opt/bc250cc-radv/26.2.3/share/vulkan/icd.d/radeon_icd.x86_64.json'
        for name, content in {
            self.icd: '{}', '/etc/bc250cc-radv/active.env': 'VERSION=26.2.3\n',
            '/etc/bc250cc-radv/enabled': '', '/proc/cmdline': 'quiet', '/softlevel': 'default',
        }.items():
            path = self.root / name.lstrip('/')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        (self.root / 'sys/module/amdgpu').mkdir(parents=True)

    def session(self, kernel='7.2.11-artix1-1'):
        env = {k: v for k, v in os.environ.items() if k not in ('VK_DRIVER_FILES', 'VK_ICD_FILENAMES')}
        env.update(BC250CC_TEST_ROOT=str(self.root), BC250CC_TEST_KERNEL=kernel)
        return subprocess.run(['sh', '-c', '. "$1"; printf "%s|%s" "${VK_DRIVER_FILES:-}" "${VK_ICD_FILENAMES:-}"',
                               'session', str(self.profile)], env=env, capture_output=True, text=True, check=True).stdout

    def test_openrc_login_exports_both_vulkan_variables(self):
        self.assertEqual(self.session(), f'{self.icd}|{self.icd}')

    def test_disabled_driver_is_not_exported(self):
        (self.root / 'etc/bc250cc-radv/enabled').unlink()
        self.assertEqual(self.session(), '|')

    def test_recovery_argument_and_old_kernel_keep_system_driver(self):
        self.assertEqual(self.session('7.1.8-artix1-3'), '|')
        (self.root / 'proc/cmdline').write_text('quiet bc250.async=0')
        self.assertEqual(self.session(), '|')

    def test_other_patched_kernel_keeps_its_own_driver(self):
        marker = self.root / 'run/bc250cc-gfx1013/loaded'
        marker.parent.mkdir(parents=True)
        marker.write_text('patched')
        self.assertEqual(self.session(), '|')


if __name__ == '__main__':
    unittest.main()
