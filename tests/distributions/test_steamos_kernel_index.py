import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path('scripts/system/repair-steamos-kernel-index.py')
spec = importlib.util.spec_from_file_location('kernel_index_repair', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def git(tree, *args):
    return subprocess.run(['git', '-C', str(tree), *args], check=True,
                          capture_output=True, text=True).stdout


@pytest.mark.parametrize('parked', [False, True])
@pytest.mark.parametrize('damage', ['empty', 'truncated', 'missing', 'healthy'])
def test_index_recovery_preserves_sources_and_supports_upstream_cleanup(tmp_path, monkeypatch, parked, damage):
    monkeypatch.setattr(module.os, 'getuid', lambda: 1000)
    tree = tmp_path / 'valve-kernel'
    tree.mkdir()
    git(tree, 'init')
    source = tree / 'Makefile'
    source.write_text('VERSION = 7\n')
    git(tree, 'add', '.')
    git(tree, '-c', 'user.name=Test', '-c', 'user.email=test@example.org', 'commit', '-m', 'kernel')
    gitdir = tree / '.git'
    if parked:
        target = Path(f'{tree}-dot-git')
        gitdir.rename(target)
        gitdir = target
    index = gitdir / 'index'
    original = index.read_bytes()
    if damage == 'missing':
        index.unlink()
    elif damage != 'healthy':
        index.write_bytes(b'' if damage == 'empty' else original[:17])
    source.write_text('modified by previous build\n')
    cache = tmp_path / 'headers.pkg.tar.zst'
    cache.write_bytes(b'cached download')
    module.repair(tree)
    assert source.read_text() == 'modified by previous build\n'
    assert cache.read_bytes() == b'cached download'
    if damage == 'healthy':
        assert index.read_bytes() == original
    subprocess.run(['git', f'--git-dir={gitdir}', f'--work-tree={tree}',
                    'checkout', '-qf', '--', '.'], check=True)
    assert source.read_text() == 'VERSION = 7\n'


def test_failed_reconstruction_keeps_existing_index(tmp_path, monkeypatch):
    monkeypatch.setattr(module.os, 'getuid', lambda: 1000)
    tree = tmp_path / 'valve-kernel'
    tree.mkdir()
    git(tree, 'init')
    index = tree / '.git/index'
    index.write_bytes(b'broken')
    with pytest.raises(subprocess.CalledProcessError):
        module.repair(tree)
    assert index.read_bytes() == b'broken'
    assert not list(index.parent.glob('bc250-index-*'))


def test_generated_workflow_recovers_corrupt_index_and_retries_drift(tmp_path):
    """Execute the application's generated build segment, without privileged actions."""
    from bc250cc.infrastructure.dependencias_steamos import SteamosDependenciesMixin

    class Repository(SteamosDependenciesMixin):
        def _tool_dir(self):
            return tmp_path

        def _clone_or_update_commit_command(self, *args):
            return ':'

    audio = tmp_path / 'bc250-steamos/bc250-audio-fix'
    tree = audio / 'valve-kernel'
    tree.mkdir(parents=True)
    git(tree, 'init')
    (tree / 'Makefile').write_text('VERSION = 7\n')
    git(tree, 'add', '.')
    git(tree, '-c', 'user.name=Test', '-c', 'user.email=test@example.org',
        'commit', '-m', 'kernel')
    parked = Path(f'{tree}-dot-git')
    (tree / '.git').rename(parked)
    (parked / 'index').write_bytes(b'')
    (tree / 'Makefile').write_text('old toolkit patch\n')
    (audio / 'fetch-sources-bc250cc.sh').write_text('exit 0\n')
    (audio / 'build-bc250cc.sh').write_text(
        'cd "$(dirname "$0")"\n'
        'if ! grep -q "^VERSION = 7$" valve-kernel/Makefile; then exit 75; fi\n'
        'echo BUILD_OK\n'
    )
    (audio / 'clean.sh').write_text(
        'cd "$(dirname "$0")"\n'
        'git --git-dir="$PWD/valve-kernel-dot-git" '
        '--work-tree="$PWD/valve-kernel" checkout -qf -- .\n'
    )
    command = Repository()._steamos_compatibility_stage_command(install=True)
    start = command.index(f'/usr/bin/bash {audio}/fetch-sources-bc250cc.sh')
    from bc250cc.infrastructure.steamos_shell import steamos_writable_root_wrapper
    end = command.index(f'/usr/bin/bash {steamos_writable_root_wrapper()}', start)
    result = subprocess.run(['bash', '-Eeuo', 'pipefail', '-c', command[start:end]],
                            capture_output=True, text=True, env=os.environ.copy())
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Recovering the SteamOS kernel Git index' in result.stdout
    assert 'cleaning it and building again' in result.stdout
    assert 'BUILD_OK' in result.stdout
