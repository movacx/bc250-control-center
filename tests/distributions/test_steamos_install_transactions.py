"""Exercise generated SteamOS transactions without touching host state."""
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bc250cc.infrastructure.dependencias_steamos import SteamosDependenciesMixin
from bc250cc.infrastructure.steamos_shell import steamos_writable_root_wrapper


class Repository(SteamosDependenciesMixin):
    def __init__(self, root):
        self.root = root

    def _tool_dir(self):
        return self.root

    def _clone_or_update_commit_command(self, *args):
        return ':'


class SteamOSTransactions(unittest.TestCase):
    def environment(self, root, initial):
        bindir = root / 'bin'
        bindir.mkdir()
        state = root / 'state'
        state.write_text(initial)
        scripts = {
            'steamos-readonly': 'case "$1" in status) cat "$TEST_STATE";; disable) echo disabled > "$TEST_STATE";; enable) echo enabled > "$TEST_STATE";; esac',
            'sudo': '''if [ "${1:-}" = -n ]; then exit 0; fi
if [ "$1" = install ]; then
  test "$(cat "$TEST_STATE")" = disabled || exit 88
  shift
  # Exercise the real copy without requiring root ownership in this fixture.
  exec /usr/bin/install -m 0644 "${@: -2}"
fi
exec "$@"''',
        }
        for name, body in scripts.items():
            target = bindir / name
            target.write_text('#!/bin/bash\nset -eu\n' + body + '\n')
            target.chmod(0o755)
        startup = root / 'bash-env'
        startup.write_text(f'export PATH={shlex.quote(str(bindir))}:"$PATH"\n')
        return os.environ | {'PATH': f'{bindir}:{os.environ["PATH"]}',
                             'BASH_ENV': str(startup), 'TEST_STATE': str(state),
                             'BC250_STEAMOS_WRITABLE_TEST_DIR': str(root),
                             'BC250_STEAMOS_VAR_DIR': str(root)}, state

    def test_artifact_transfer_and_installer_restore_root_on_success_and_failure(self):
        for initial in ('enabled', 'disabled'):
            for failure in (0, 37):
                with self.subTest(initial=initial, failure=failure), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    env, state = self.environment(root, initial)
                    audio = root / 'bc250-steamos/bc250-audio-fix'
                    audio.mkdir(parents=True)
                    protected = root / 'protected'
                    protected.mkdir()
                    for name in ('amdgpu.ko.zst', 'amdgpu.gfx1013.attestation'):
                        (audio / name).write_text('verified build product')
                        (audio / name).chmod(0o644)
                    (protected / 'install.sh').write_text(
                        'test "$(cat "$TEST_STATE")" = disabled || exit 89\n'
                        'test -f "$(dirname "$0")/amdgpu.ko.zst" || exit 90\n'
                        f'echo INSTALL_CALLED\nexit {failure}\n'
                    )
                    with patch('bc250cc.infrastructure.dependencias_steamos.STEAMOS_AMDGPU_AUDIO_FIX_ROOT', protected):
                        command = Repository(root)._steamos_compatibility_stage_command(install=True)
                    subprocess.run(['bash', '-n', '-c', command], check=True)
                    # Extract the exact generated inner command, keeping shell quoting intact.
                    tokens = shlex.split(command)
                    transfer = next(token for token in tokens if token.startswith('set -Eeuo pipefail; for artifact'))
                    result = subprocess.run(['bash', str(steamos_writable_root_wrapper()),
                                             'bash', '-lc', transfer], env=env,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, failure, result.stdout + result.stderr)
                    self.assertIn('INSTALL_CALLED', result.stdout)
                    self.assertEqual(state.read_text().strip(), initial)
                    self.assertEqual((protected / 'amdgpu.ko.zst').read_text(), 'verified build product')
                    # Compilation remains outside the short writable-root transaction.
                    self.assertNotIn('/build.sh', transfer)
                    self.assertNotIn('/fetch-sources.sh', transfer)

    def test_quick_access_generated_command_restores_root_even_after_failure(self):
        from bc250cc.infrastructure.dependencias_repository import (
            DependenciasRepository,
        )
        for initial in ('enabled', 'disabled'):
            for failure in (0, 23):
                with self.subTest(initial=initial, failure=failure), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    env, state = self.environment(root, initial)
                    installer = root / 'plugin-installer'
                    installer.write_text('#!/bin/bash\n'
                                         'test "$(cat "$TEST_STATE")" = disabled || exit 88\n'
                                         f'echo PLUGIN_CALLED\nexit {failure}\n')
                    installer.chmod(0o755)
                    fake = SimpleNamespace(
                        _os_repository=lambda: SimpleNamespace(info=SimpleNamespace(family='steamos')),
                        _quick_access_installer_path=lambda: installer,
                        _abrir_terminal=lambda command, title: command,
                    )
                    with patch('bc250cc.infrastructure.dependencias_repository.quick_access_inventory',
                               return_value=SimpleNamespace(decky_detected=True)):
                        command = DependenciasRepository.preparar_quick_access_steamos(fake, install_decky=False)
                    result = subprocess.run(['bash', '-Eeuo', 'pipefail', '-c', command],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, failure, result.stdout + result.stderr)
                    self.assertIn('PLUGIN_CALLED', result.stdout)
                    self.assertEqual(state.read_text().strip(), initial)


if __name__ == '__main__':
    unittest.main()
