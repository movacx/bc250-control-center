"""The reviewed build must not mix rolling-main Python with SteamOS libc."""
import importlib.util
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path('scripts/system/prepare-steamos-build-runtime.py')
spec = importlib.util.spec_from_file_location('steamos_build_runtime', SCRIPT)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def fixture_toolkit(root):
    root.mkdir()
    originals = {
        'fetch-sources.sh': 'set -euo pipefail\nHERE=$(cd "$(dirname "$0")" && pwd)\nDEP_REPOS=(extra-main core-main)\nDEPS=$HERE/deps\necho "${DEP_REPOS[*]} $DEPS"\nsource "$HERE/build-env.sh"\n',
        'build.sh': 'set -euo pipefail\nHERE=$(cd "$(dirname "$0")" && pwd)\nsource "$HERE/build-env.sh"\necho BUILD_REACHED\n',
        'build-env.sh': 'DEPS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deps"\nexport PATH="$DEPS/usr/bin:$PATH"\nexport LD_LIBRARY_PATH="$DEPS/usr/lib"\n',
    }
    for name, text in originals.items():
        (root / name).write_text(text)
    return originals


def tools(root, python_body):
    directory = root / 'usr/bin'
    directory.mkdir(parents=True)
    for name in ('python3', 'pahole', 'bc', 'perl', 'flex', 'bison', 'msgfmt'):
        path = directory / name
        path.write_text('#!/bin/bash\n' + (python_body if name == 'python3' else 'exit 0\n'))
        path.chmod(0o755)


@pytest.mark.parametrize('version,branch', [('3.9.5', '3.9'), ('3.8.12', '3.8')])
def test_uses_installed_branch(version, branch, tmp_path):
    release = tmp_path / 'os-release'
    release.write_text(f'ID=steamos\nVERSION_ID="{version}"\n')
    assert runtime.steam_branch(release) == branch


@pytest.mark.parametrize('cached', [False, True])
def test_separate_cache_ignores_incompatible_main_python_and_preserves_sources(tmp_path, cached):
    audio = tmp_path / 'audio'
    originals = fixture_toolkit(audio)
    tools(audio / 'deps', 'echo "GLIBC_2.44 not found" >&2; exit 1\n')
    compatible = audio / 'deps-bc250cc-3.9'
    if cached:
        tools(compatible, f'exec {shlex.quote(sys.executable)} "$@"\n')
    runtime.prepare(audio, '3.9')
    if not cached:
        tools(compatible, f'exec {shlex.quote(sys.executable)} "$@"\n')
    # Execute the generated adapter, not a reimplementation of its path logic.
    result = subprocess.run(['bash', str(audio / 'build-bc250cc.sh')], capture_output=True, text=True,
                            env=os.environ | {'PYTHONPATH': '', 'PYTHONHOME': ''})
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'BUILD_REACHED' in result.stdout
    fetch = (audio / 'fetch-sources-bc250cc.sh').read_text()
    assert 'DEP_REPOS=(extra-3.9 core-3.9)' in fetch
    assert 'extra-main' not in fetch
    for name, original in originals.items():
        assert (audio / name).read_text() == original
    assert (audio / 'deps/usr/bin/python3').exists()


def test_preflight_checks_imports_not_just_python_existence(tmp_path):
    audio = tmp_path / 'audio'
    fixture_toolkit(audio)
    runtime.prepare(audio, '3.9')
    tools(audio / 'deps-bc250cc-3.9', 'echo "ImportError: libm.so.6: GLIBC_2.44 not found" >&2; exit 1\n')
    result = subprocess.run(['bash', str(audio / 'build-bc250cc.sh')], capture_output=True, text=True)
    assert result.returncode == 65
    assert 'STEAMOS_BUILD_RUNTIME_INCOMPATIBLE' in result.stderr
    assert 'BUILD_REACHED' not in result.stdout


def test_layout_drift_never_modifies_originals(tmp_path):
    audio = tmp_path / 'audio'
    originals = fixture_toolkit(audio)
    (audio / 'fetch-sources.sh').write_text('different upstream layout\n')
    with pytest.raises(RuntimeError, match='layout changed'):
        runtime.prepare(audio, '3.9')
    assert (audio / 'build-env.sh').read_text() == originals['build-env.sh']
    assert not (audio / 'build-bc250cc.sh').exists()
