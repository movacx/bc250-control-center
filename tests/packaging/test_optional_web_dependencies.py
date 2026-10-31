"""The GUI must install with distro packages, even when distro Cheroot is older."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_native_package_dependencies_do_not_force_a_web_server_version():
    for filename, pattern in (
        ('build-deb.sh', r'^Depends: (.+)$'),
        ('build-rpm.sh', r'^Requires: +(.+)$'),
        ('build-local-pkg.sh', r'^depend = (.+)$'),
    ):
        source = (ROOT / 'packaging/scripts' / filename).read_text()
        dependencies = re.findall(pattern, source, re.MULTILINE)
        assert dependencies, filename
        assert all('cheroot' not in value for value in dependencies), filename
        assert any('pip' in value for value in dependencies), filename
        assert any('openssl' in value for value in dependencies), filename
        assert any('ca-certificates' in value for value in dependencies), filename
    assert 'python3-pyqt6.qtsvg' in (ROOT / 'packaging/scripts/build-deb.sh').read_text()


def test_a_failed_gui_dependency_recheck_keeps_the_installed_application(tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    fake = {
        'python3': '#!/bin/sh\nif [ "$1" = -c ]; then exit 0; fi\ncat >/dev/null\nexit 1\n',
        'apt-get': '#!/bin/sh\nexit 0\n',
        'apt-cache': '#!/bin/sh\nexit 0\n',
        'sudo': '#!/bin/sh\nexec "$@"\n',
    }
    for name, source in fake.items():
        path = bindir / name
        path.write_text(source)
        path.chmod(0o755)
    prefix = tmp_path / 'prefix'
    app = prefix / 'share/bc250-control-center'
    app.mkdir(parents=True)
    sentinel = app / 'VERSION'
    sentinel.write_text('previous-working-version')
    home = tmp_path / 'home'
    home.mkdir()
    environment = {**os.environ, 'PATH': f'{bindir}:{os.environ["PATH"]}', 'HOME': str(home),
                   'PREFIX': str(prefix), 'BC250_SKIP_PRIVILEGED_HELPER': '1',
                   'BC250_SKIP_DEPENDENCY_INSTALL': '0', 'BC250_INSTALL_PROFILE': 'desktop'}
    result = subprocess.run(['bash', str(ROOT / 'scripts/install-local.sh')], env=environment,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 2, result.stdout + result.stderr
    assert 'No installed application code was replaced' in result.stderr
    assert sentinel.read_text() == 'previous-working-version'
