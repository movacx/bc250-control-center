"""Exercise dependency routing without installing packages on the host."""
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path('packaging/common/os-scripts/arch/prepare-dependencies.sh')


@pytest.mark.parametrize(
    ('installed', 'available', 'install_status', 'expected', 'status'),
    [
        (True, False, 0, 'verified', 0),
        (False, True, 0, 'repository\nverified', 0),
        (False, False, 0, 'source\nverified', 0),
        (False, True, 9, 'repository', 9),
    ],
)
def test_stress_install_routes(installed, available, install_status, expected, status):
    source = SCRIPT.read_text()
    function = source[source.index('install_stress() {'):source.index('\ninstall_sensors()')]
    command = f'''set -e
have() {{ {'true' if installed else 'false'}; }}
pacman() {{ {'true' if available else 'false'}; }}
as_root() {{ echo repository; return {install_status}; }}
install_stress_from_source() {{ echo source; }}
verify_command() {{ echo verified; }}
warn() {{ :; }}
{function}
install_stress
'''
    result = subprocess.run(['bash', '-c', command], capture_output=True, text=True)
    assert result.returncode == status, result.stderr
    assert result.stdout.strip() == expected
