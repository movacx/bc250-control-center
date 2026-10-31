"""Run with unittest as well as pytest; all source edits stay in a temp tree."""
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/system/bc250-gfx1013-source.sh'
FUNCTION = SCRIPT.read_text().split('adapt_drm_exec() {', 1)[1].split('\nprepare_meson()', 1)[0]
FUNCTION = 'adapt_drm_exec() {' + FUNCTION


class DrmCompatibilityTest(unittest.TestCase):
    def run_adaptation(self, arity, layout="flat"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build = root
            common = root
            if layout != "flat":
                build = root / 'modules/kernel/build'
                common = root / 'linux-headers-common'
                build.mkdir(parents=True)
                if layout == "source-link":
                    (build.parent / 'source').symlink_to(common)
                else:
                    (build / 'Makefile').write_text(f'include {common}/Makefile\n')
            header = common / 'include/drm/drm_exec.h'
            header.parent.mkdir(parents=True)
            args = {2: 'exec, obj', 3: 'exec, index, obj', 4: 'a, b, c, d'}[arity]
            header.write_text(''.join(
                f'#define {name}({args}) body\n' for name in (
                    'drm_exec_for_each_locked_object',
                    'drm_exec_for_each_locked_object_reverse',
                )
            ))
            source = root / 'driver.c'
            original = ('drm_exec_for_each_locked_object(&p->exec, index, obj) { use(obj); }\n'
                        'drm_exec_for_each_locked_object_reverse(exec, i, bo) { use(bo); }\n')
            source.write_text(original)
            result = subprocess.run(
                ['bash', '-c', FUNCTION + '\nadapt_drm_exec "$1" "$2"', 'test', str(build), str(root)],
                capture_output=True, text=True, check=False,
            )
            return result, source.read_text(), original

    def test_two_argument_headers(self):
        result, changed, _ = self.run_adaptation(2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('(&p->exec, obj) { use(obj); }', changed)
        self.assertIn('(exec, bo) { use(bo); }', changed)

    def test_three_argument_headers(self):
        result, changed, original = self.run_adaptation(3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(changed, original)

    def test_debian_split_headers_via_source_link(self):
        result, changed, _ = self.run_adaptation(2, "source-link")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('(&p->exec, obj) { use(obj); }', changed)

    def test_debian_split_headers_via_build_makefile(self):
        result, changed, _ = self.run_adaptation(2, "makefile")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('(&p->exec, obj) { use(obj); }', changed)

    def test_unknown_signature_is_rejected(self):
        result, changed, original = self.run_adaptation(4)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Unsupported DRM iterator signature', result.stderr)
        self.assertEqual(changed, original)


if __name__ == '__main__':
    unittest.main()
