from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess

from .detector import read_os_release
from .factory import create_os_repository


class StandaloneHost:
    def _os_release(self):
        return read_os_release()

    def _command_path(self, name: str) -> str:
        return shutil.which(name) or ''

    def _tool_dir(self) -> Path:
        return Path.home() / '.local' / 'share' / 'bc250-control-center' / 'ResourceTools'


def main() -> int:
    parser = argparse.ArgumentParser(description='BC250 Control Center OS dependency strategy runner')
    parser.add_argument('--component', choices=('all', 'runtime', 'governor', 'stress', 'sensors', 'umr'), default='all')
    parser.add_argument('--cu-manager-script', default='')
    parser.add_argument('--runtime', action='store_true', help='Compatibility alias for --component all')
    args = parser.parse_args()

    host = StandaloneHost()
    repository = create_os_repository(host)
    command = repository.prepare_dependencies_command(
        'all' if args.runtime else args.component,
        cu_manager_script=args.cu_manager_script,
    )
    completed = subprocess.run(['bash', '-lc', command], check=False)
    return completed.returncode


if __name__ == '__main__':
    raise SystemExit(main())
