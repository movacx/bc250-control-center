#!/usr/bin/env python3
"""Recover the disposable toolkit kernel index before upstream clean.sh.

Only the index is replaced; HEAD, objects, sources and download caches survive.
Run as the build user, immediately before the explicit tree-drift cleanup.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def repair(tree: Path) -> None:
    if os.getuid() == 0:
        raise RuntimeError('kernel index recovery must run as the build user')
    live, parked = tree / '.git', Path(f'{tree}-dot-git')
    candidates = [path for path in (live, parked) if path.is_dir()]
    if len(candidates) != 1:
        raise RuntimeError('expected exactly one live or parked kernel Git directory')
    gitdir = candidates[0]
    index = gitdir / 'index'
    if gitdir.is_symlink() or index.is_symlink():
        raise RuntimeError('refusing a symlinked kernel Git directory or index')
    if (gitdir / 'index.lock').exists():
        raise RuntimeError('kernel Git index is locked; finish the other build first')
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith('GIT_'):
            del env[key]
    command = ['git', f'--git-dir={gitdir}', f'--work-tree={tree}']
    checked = subprocess.run(command + ['ls-files', '--stage'], env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if index.is_file() and checked.returncode == 0:
        return
    print('[INFO] Recovering the SteamOS kernel Git index from HEAD.', flush=True)
    fd, name = tempfile.mkstemp(prefix='bc250-index-', dir=gitdir)
    os.close(fd)
    temporary = Path(name)
    temporary.unlink()  # read-tree must create a valid index, not read an empty one
    try:
        subprocess.run(command + ['read-tree', 'HEAD'],
                       env=env | {'GIT_INDEX_FILE': str(temporary)}, check=True)
        if (gitdir / 'index.lock').exists():
            raise RuntimeError('kernel Git index became locked during recovery')
        os.replace(temporary, index)
    finally:
        temporary.unlink(missing_ok=True)
    print('[OK] Kernel Git index recovered; upstream can reset the build tree.', flush=True)


if __name__ == '__main__':
    try:
        repair(Path(sys.argv[1]).resolve())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        sys.exit(f'ERROR: SteamOS kernel index recovery failed: {exc}')
