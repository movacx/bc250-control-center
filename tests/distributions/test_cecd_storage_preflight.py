"""Exercise the generated storage gate without Podman or real disk writes."""
import ast
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from bc250cc.shared import error_catalog  # noqa: E402 - requires the source path configured above

SOURCE = ROOT / 'src/bc250cc/infrastructure/accessories/hdmi_cec.py'
node = next(n for n in ast.parse(SOURCE.read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == '_container_storage_lines')
namespace = {}
exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
GATE = '\n'.join(namespace['_container_storage_lines']())


class CecStorageTest(unittest.TestCase):
    def check_gate(self, free):
        script = '''set -euo pipefail
podman() { echo /fake/container-store; }
df() { echo "disk 10000000 100 $TEST_FREE 1% /"; }
bc250_podman=podman
bc250_stage=/fake/stage
''' + GATE + '\necho BUILD_ALLOWED\n'
        return subprocess.run(['bash', '-c', script], capture_output=True, text=True,
                              env={**os.environ, 'TEST_FREE': free}, check=False)

    def test_full_disk_stops_before_build(self):
        result = self.check_gate('792576')
        self.assertEqual(result.returncode, 73, result.stderr)
        self.assertIn('/fake/container-store', result.stdout)
        self.assertNotIn('BUILD_ALLOWED', result.stdout)
        self.assertEqual(error_catalog.for_marker(result.stdout).code, 'BC250-STORAGE-001')

    def test_enough_space_allows_build(self):
        result = self.check_gate('8388608')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('BUILD_ALLOWED', result.stdout)

    def test_unreadable_disk_usage_is_rejected(self):
        self.assertEqual(self.check_gate('unknown').returncode, 74)

    def test_podman_storage_failure_has_specific_diagnosis(self):
        text = 'writing blob: processing tar file: no space left on device'
        self.assertEqual(error_catalog.for_marker(text).code, 'BC250-STORAGE-001')


if __name__ == '__main__':
    unittest.main()
