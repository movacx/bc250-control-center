#!/usr/bin/env python3
"""Adapt the reviewed user-space build to the installed SteamOS branch.

Never execute as root or replace host libraries. Original toolkit scripts and
its protected installation/ABI checks remain unchanged. Generated build copies
use a separate dependency cache so rolling main-channel packages cannot leak in.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path


def steam_branch(release: Path) -> str:
    values = {}
    for line in release.read_text(encoding='utf-8').splitlines():
        key, sep, value = line.partition('=')
        if sep:
            values[key.strip()] = value.strip().strip('\"\'')
    if values.get('ID') not in {'steamos', 'holo'}:
        raise RuntimeError('this build runtime is only available on SteamOS')
    match = re.fullmatch(r'(3\.[0-9]+)(?:\.[0-9]+)*', values.get('VERSION_ID', ''))
    if not match:
        raise RuntimeError('cannot determine the installed SteamOS package branch')
    return match[1]


def replace_once(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise RuntimeError('reviewed toolkit build layout changed; refusing an unverified adaptation')
    return text.replace(before, after, 1)


def prepare(audio: Path, branch: str) -> None:
    if not re.fullmatch(r'3\.[0-9]+', branch):
        raise RuntimeError('invalid SteamOS package branch')
    audio = audio.resolve(strict=True)
    cache = f'deps-bc250cc-{branch}'
    sources = {}
    for name in ('fetch-sources.sh', 'build-env.sh', 'build.sh'):
        path = audio / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f'unsafe or missing toolkit build script: {name}')
        sources[name] = path.read_text(encoding='utf-8')
    fetch = replace_once(sources['fetch-sources.sh'], 'DEP_REPOS=(extra-main core-main)',
                         f'DEP_REPOS=(extra-{branch} core-{branch})')
    fetch = replace_once(fetch, 'DEPS=$HERE/deps', f'DEPS=$HERE/{cache}')
    fetch = replace_once(fetch, 'source "$HERE/build-env.sh"', 'source "$HERE/build-env-bc250cc.sh"')
    build = replace_once(sources['build.sh'], 'source "$HERE/build-env.sh"',
                         'source "$HERE/build-env-bc250cc.sh"')
    environment = replace_once(sources['build-env.sh'], 'pwd)/deps"', f'pwd)/{cache}"')
    environment += '''
# Existence on PATH does not prove these tools can load against the host libc.
if ! python3 -I -c 'import math, selectors, subprocess; assert math.sqrt(4) == 2'; then
    echo 'ERROR: STEAMOS_BUILD_RUNTIME_INCOMPATIBLE: Python cannot load its standard library against this SteamOS. System libraries were not changed.' >&2
    return 65
fi
for bc250_tool in pahole bc perl flex bison msgfmt; do
    if ! "$bc250_tool" --version >/dev/null 2>&1; then
        echo "ERROR: STEAMOS_BUILD_RUNTIME_INCOMPATIBLE: $bc250_tool cannot run against this SteamOS. System libraries were not changed." >&2
        return 65
    fi
done
unset bc250_tool
'''
    generated = {'fetch-sources-bc250cc.sh': fetch, 'build-env-bc250cc.sh': environment,
                 'build-bc250cc.sh': build}
    # Validate every generated script before publishing any build adapter.
    for text in generated.values():
        subprocess.run(['/usr/bin/bash', '-n'], input=text, text=True, check=True)
    for name, text in generated.items():
        destination = audio / name
        if destination.is_symlink():
            raise RuntimeError(f'refusing a symlinked build adapter: {name}')
        fd, temporary = tempfile.mkstemp(prefix='.bc250-build-', dir=audio)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                stream.write(text)
            os.chmod(temporary, 0o700)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    print(f'[INFO] SteamOS build dependencies: extra-{branch}, core-{branch}; isolated cache: {cache}', flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio_root', type=Path)
    parser.add_argument('--os-release', type=Path, default=Path('/etc/os-release'))
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error('prepare the kernel build runtime as the desktop user, never root')
    try:
        prepare(args.audio_root, steam_branch(args.os_release))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(65, f'ERROR: STEAMOS_BUILD_RUNTIME_INCOMPATIBLE: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
