"""keyboardspecialist's Mesa / RADV after a SteamOS factory reset.

The reset erases /home and keeps the system partition: the driver and the
environment generator stay, the install record in /home does not. The
provider's uninstall refuses without that record and the Real Toolkit refuses
to install over the files, so Control Center removes them itself, after
proving each one is the provider's. R-20261118-045245.
"""
import os
import subprocess

import pytest

from bc250cc.infrastructure.steamos_graphics_runtime import (
    orphan_cleanup_command,
    orphaned_runtime,
)

GENERATOR_TEXT = """#!/usr/bin/env bash
set -u
DRIVER='/usr/lib/libvulkan_radeon_driconf.so'
ICD="$HOME/radeon_driconf_icd.x86_64.json"
MANIFEST="$HOME/.local/share/bc250-mesh-shader/install.conf"
exit 0
"""


def _system(tmp_path, *, generator=GENERATOR_TEXT, driver=b'\x7fELF\x02\x01\x01' + b'\0' * 64):
    usr = tmp_path / 'usr'
    (usr / 'lib/systemd/user-environment-generators').mkdir(parents=True)
    driver_path = usr / 'lib/libvulkan_radeon_driconf.so'
    generator_path = usr / 'lib/systemd/user-environment-generators/60-bc250-gfx1013'
    driver_path.write_bytes(driver)
    generator_path.write_text(generator)
    home = tmp_path / 'home'
    (home / '.local/share').mkdir(parents=True)
    return home, driver_path, generator_path


def test_leftovers_are_orphaned_only_while_the_install_record_is_missing(tmp_path):
    home, driver, generator = _system(tmp_path)
    assert orphaned_runtime(home, driver_path=driver, generator_path=generator) == (str(driver), str(generator))
    record = home / '.local/share/bc250-mesh-shader/install.conf'
    record.parent.mkdir(parents=True)
    record.write_text('VERSION=1\n')
    # With its record, the provider's own uninstall owns the removal.
    assert orphaned_runtime(home, driver_path=driver, generator_path=generator) == ()


def test_nothing_installed_is_not_orphaned(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    assert orphaned_runtime(home, driver_path=tmp_path / 'none.so', generator_path=tmp_path / 'none') == ()


def test_the_cleanup_command_is_valid_bash():
    command = orphan_cleanup_command()
    assert subprocess.run(['bash', '-n'], input=command, text=True).returncode == 0
    assert '--adopt' not in command and 'rm -rf' not in command


def _run(tmp_path, home, driver, generator, *, keep_modes=False):
    """Run the cleanup with sudo, pacman, the writable-root guard and file ownership faked."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / 'sudo').write_text('#!/bin/bash\nexec "$@"\n')
    (bin_dir / 'pacman').write_text('#!/bin/bash\nexit 1\n')  # no package owns either file
    (bin_dir / 'systemctl').write_text('#!/bin/bash\nexit 0\n')
    # stat -c %u must answer 0 (root) for these test files owned by the runner.
    (bin_dir / 'stat').write_text(
        '#!/bin/bash\nif [ "$1" = -c ] && [ "$2" = %u ]; then echo 0; else exec /usr/bin/stat "$@"; fi\n')
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    for path in (driver, generator):
        if not keep_modes:
            path.chmod(0o755)
    command = orphan_cleanup_command(driver_path=driver, generator_path=generator)
    # The writable-root wrapper needs SteamOS; run what it wraps directly.
    start = command.index('/usr/bin/bash ')
    command = command[:start] + f'sudo rm -f -- {driver} {generator}' + command[command.index("'; ", start) + 1:]
    env = {**os.environ, 'HOME': str(home), 'PATH': f'{bin_dir}:{os.environ["PATH"]}'}
    return subprocess.run(['bash', '-c', 'set -Eeuo pipefail; ' + command], env=env, text=True,
                          capture_output=True)


def test_the_providers_files_are_removed(tmp_path):
    home, driver, generator = _system(tmp_path)
    icd = home / 'radeon_driconf_icd.x86_64.json'
    icd.write_text('{}')
    result = _run(tmp_path, home, driver, generator)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not driver.exists() and not generator.exists() and not icd.exists()
    assert '[OK]' in result.stdout


@pytest.mark.parametrize('change', ['generator', 'driver', 'record'])
def test_any_doubt_removes_nothing(tmp_path, change):
    home, driver, generator = _system(tmp_path)
    if change == 'generator':
        generator.write_text('#!/bin/sh\necho someone else\n')
    elif change == 'driver':
        driver.write_bytes(b'not a library')
    else:
        record = home / '.local/share/bc250-mesh-shader/install.conf'
        record.parent.mkdir(parents=True)
        record.write_text('VERSION=1\n')
    result = _run(tmp_path, home, driver, generator)
    assert result.returncode != 0
    assert driver.exists() and generator.exists()
    assert 'nothing was removed' in result.stdout or 'install record exists' in result.stdout


def test_a_file_others_can_write_is_not_trusted(tmp_path):
    home, driver, generator = _system(tmp_path)
    driver.chmod(0o777)
    result = _run(tmp_path, home, driver, generator, keep_modes=True)
    assert result.returncode != 0
    assert driver.exists() and generator.exists()


def test_uninstall_takes_the_orphan_route_without_staging_the_provider(monkeypatch):
    from bc250cc.infrastructure import dependencias_steamos

    recorded = []

    class Repo(dependencias_steamos.SteamosDependenciesMixin):
        estado_herramientas_cache = None

        def _os_repository(self):
            return type('R', (), {'info': type('I', (), {'family': 'steamos'})()})()

        @staticmethod
        def _join_shell_commands(commands):
            return '; '.join(commands)

        def _abrir_terminal(self, command, title=''):
            recorded.append(command)

        def _steamos_alternative_stage_command(self, destination):
            raise AssertionError('an orphan cleanup must not download or stage the provider')

    monkeypatch.setattr(dependencias_steamos, 'orphaned_runtime', lambda: ('/usr/lib/libvulkan_radeon_driconf.so',))
    Repo().gestionar_graficos_steamos_alternativo('uninstall')
    assert recorded and 'install record in /home is gone' in recorded[0]
