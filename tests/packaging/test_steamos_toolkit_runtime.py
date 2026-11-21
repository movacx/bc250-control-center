"""Installed root entrypoints work without the desktop tree or optional libraries."""
import os
import runpy
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_generated_runtime_matches_current_sources_and_has_no_application_facade():
    generator = runpy.run_path(str(ROOT / 'scripts/development/generate_steamos_toolkit_runtime.py'))
    artifact = ROOT / 'privileged/lib/bc250_steamos_toolkit_runtime.zip'
    assert artifact.read_bytes() == generator['build_payload']()
    with zipfile.ZipFile(artifact) as archive:
        assert 'bc250cc/application/__init__.py' not in archive.namelist()
        for module in generator['MODULES']:
            assert archive.read('bc250cc/' + module) == (ROOT / 'src/bc250cc' / module).read_bytes()


def test_both_installed_entrypoints_import_only_the_standalone_runtime(tmp_path):
    helpers = tmp_path / 'usr/libexec/bc250-control-center'
    (helpers / 'lib').mkdir(parents=True)
    shutil.copyfile(ROOT / 'privileged/lib/bc250_steamos_toolkit_runtime.zip',
                    helpers / 'lib/bc250_steamos_toolkit_runtime.zip')
    (helpers / 'lib/bc250_steamos_toolkit_runtime.zip').chmod(0o644)
    poison = tmp_path / 'poison/bc250cc'
    poison.mkdir(parents=True)
    (poison / '__init__.py').write_text('raise RuntimeError("USER_IMPORT_MUST_NOT_RUN")')
    for source, installed, argument, expected_status in [
        ('run-steamos-real-toolkit.py', 'bc250-steamos-toolkit', 'invalid-action', 1),
        ('check-steamos-toolkit-conflicts.py', 'bc250-steamos-toolkit-check', 'invalid-component', 79),
    ]:
        target = helpers / installed
        shutil.copyfile(ROOT / 'scripts/system' / source, target)
        result = subprocess.run(['/usr/bin/python3', '-I', '-S', str(target), argument],
                                env=dict(os.environ, PYTHONPATH=str(poison.parent)),
                                capture_output=True, text=True)
        assert result.returncode == expected_status
        assert 'Unknown' in result.stderr
        assert 'USER_IMPORT_MUST_NOT_RUN' not in result.stderr
        assert 'ModuleNotFoundError' not in result.stderr


def test_local_install_and_uninstall_use_the_same_protected_files_as_packages():
    local = (ROOT / 'scripts/install-local.sh').read_text()
    package = (ROOT / 'packaging/scripts/stage-package-root.sh').read_text()
    uninstall = (ROOT / 'scripts/uninstall-local.sh').read_text()
    for name in ['bc250-steamos-toolkit', 'bc250-steamos-toolkit-check', 'bc250_steamos_toolkit_runtime.zip']:
        assert name in local and name in package and name in uninstall
    assert '"$SYSTEM_STEAMOS_TOOLKIT_RUNTIME"' in local


def test_cached_checker_stays_importable_after_global_helper_removal(tmp_path):
    from bc250cc.infrastructure.steamos_real_toolkit_runtime import cache_guard_runtime

    installed, cached = tmp_path / 'installed', tmp_path / 'cached'
    (installed / 'lib').mkdir(parents=True)
    checker = installed / 'bc250-steamos-toolkit-check'
    shutil.copyfile(ROOT / 'scripts/system/check-steamos-toolkit-conflicts.py', checker)
    checker.chmod(0o755)
    archive = installed / 'lib/bc250_steamos_toolkit_runtime.zip'
    shutil.copyfile(ROOT / 'privileged/lib/bc250_steamos_toolkit_runtime.zip', archive)
    archive.chmod(0o644)
    cache_guard_runtime(installed, cached)
    shutil.rmtree(installed)
    result = subprocess.run(['/usr/bin/python3', '-I', '-S',
                             str(cached / 'bc250-steamos-toolkit-check'), 'invalid-component'],
                            capture_output=True, text=True)
    assert result.returncode == 79
    assert 'Unknown toolkit conflict component' in result.stderr
    assert 'ModuleNotFoundError' not in result.stderr


@pytest.mark.parametrize('component,expected', [
    ('all', [('graphics', 'real-toolkit', True), ('native', 'all')]),
    ('graphics', [('graphics', 'real-toolkit', False)]),
    ('alternative-graphics', [('graphics', 'keyboardspecialist', False)]),
])
def test_installed_checker_uses_all_kernel_scope_only_for_bulk_recovery(tmp_path, monkeypatch, component, expected):
    from bc250cc.infrastructure import (
        steamos_graphics_ownership,
        steamos_toolkit_conflicts,
    )

    (tmp_path / 'lib').mkdir()
    shutil.copyfile(ROOT / 'privileged/lib/bc250_steamos_toolkit_runtime.zip',
                    tmp_path / 'lib/bc250_steamos_toolkit_runtime.zip')
    (tmp_path / 'lib/bc250_steamos_toolkit_runtime.zip').chmod(0o644)
    target = tmp_path / 'checker'
    shutil.copyfile(ROOT / 'scripts/system/check-steamos-toolkit-conflicts.py', target)
    calls = []
    monkeypatch.setattr(steamos_graphics_ownership, 'require_graphics_provider',
                        lambda provider, **kwargs: calls.append(('graphics', provider, kwargs.get('all_kernels', False))))
    monkeypatch.setattr(steamos_toolkit_conflicts, 'require_no_native_conflicts',
                        lambda value: calls.append(('native', value)))
    monkeypatch.setattr(sys, 'argv', [str(target), component])
    monkeypatch.setattr(sys, 'path', list(sys.path))
    runpy.run_path(str(target), run_name='__main__')
    assert calls == expected


def test_local_uninstall_opens_the_steamos_root_for_its_own_helpers_and_closes_it_again():
    """Removing /usr/libexec helpers needs the same writable window the installer used.

    Without it every helper was kept as a "read-only system file" and the closing
    message blamed a system package that does not exist.
    """
    uninstall = (ROOT / 'scripts/uninstall-local.sh').read_text()
    unlock = uninstall.index('bc250_steamos_unlock_root')
    assert uninstall.index('trap steamos_uninstall_restore EXIT') < unlock
    assert unlock < uninstall.index('remove_managed_privileged_file "$APP_DIR/privileged/helpers/bc250-fan-pwm-helper"')
    assert 'STEAMOS_ROOT_HELPER="$SCRIPT_DIR/system/steamos-root.sh"' in uninstall
    assert 'bc250_steamos_restore_root "$status"' in uninstall
    # Only when there is something of ours to remove, never for a dry run or a package.
    assert '"$KEEP_PRIVILEGED" -eq 0 && "$DRY_RUN" -eq 0' in uninstall
    assert '! package_owner "$SYSTEM_PRIV_HELPER"' in uninstall
    assert 'they are on a read-only system file system' in uninstall
    # The helper it sources is shipped next to it by the local installer.
    installer = (ROOT / 'scripts/install-local.sh').read_text()
    assert 'cp -a -- "$ROOT_DIR/scripts/system" "$APP_STAGE/scripts/system"' in installer
    assert (ROOT / 'scripts/system/steamos-root.sh').is_file()


def test_the_launcher_and_the_installed_checker_agree_on_the_refusal_status():
    from bc250cc.infrastructure.steamos_real_toolkit import CONFLICT_STATUS

    checker = (ROOT / 'scripts/system/check-steamos-toolkit-conflicts.py').read_text()
    assert f'raise SystemExit({CONFLICT_STATUS})' in checker
