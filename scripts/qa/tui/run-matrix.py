#!/usr/bin/env python3
"""Reproduce the TUI userspace matrix without touching the host package manager."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PROFILES = {
    'arch': 'docker.io/library/archlinux:base',
    'cachyos': 'docker.io/cachyos/cachyos:latest',
    'manjaro': 'docker.io/manjarolinux/base:latest',
    'artix': 'docker.io/artixlinux/artixlinux:base-openrc',
    'alpine': 'docker.io/library/alpine:latest',
    'gentoo': 'docker.io/gentoo/stage3:latest',
    'bazzite': 'ghcr.io/ublue-os/bazzite:stable',
    'debian': 'docker.io/library/debian:stable-slim',
    'kali': 'docker.io/kalilinux/kali-rolling:latest',
    'parrot': 'docker.io/parrotsec/core:latest',
    'devuan': 'docker.io/devuan/devuan:stable',
    'kubuntu': 'docker.io/library/ubuntu:24.04',
    'xubuntu': 'docker.io/library/ubuntu:24.04',
    'lubuntu': 'docker.io/library/ubuntu:24.04',
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--profile', action='append', choices=PROFILES)
    parser.add_argument('--allow-network', action='store_true')
    parser.add_argument('--pull', action='store_true', help='explicitly allow downloading base images')
    parser.add_argument('--prepared', action='store_true', help='reuse localhost/bc250-tui-PROFILE-ready')
    parser.add_argument('--output', type=Path, default=Path.home() / '.cache/bc250-tui-matrix')
    args = parser.parse_args(argv)
    if args.list:
        print(json.dumps(PROFILES, indent=2))
        return 0
    if not args.allow_network:
        parser.error('package and test dependency operations require --allow-network')
    if os.geteuid() == 0:
        parser.error('run Podman rootless, as the normal user')
    if not shutil.which('podman'):
        parser.error('podman is required')
    if shutil.disk_usage(ROOT).free < 15 * 2**30:
        parser.error('at least 15 GiB of free container storage is required')
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for name in args.profile or list(PROFILES):
        image = PROFILES[name]
        ready = f'localhost/bc250-tui-{name}-ready'
        stamp = f'{os.getpid()}-{time.time_ns()}'
        log_path = args.output / f'{name}.log'
        with log_path.open('w') as log:
            def run(command):
                return subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False).returncode

            status = 0
            if not args.prepared:
                if args.pull:
                    status = run(['podman', 'pull', image])
                container = f'bc250-tui-{name}-prepare-{stamp}'
                if not status:
                    status = run(['podman', 'run', '--name', container, '--pull=never', '--network=pasta',
                                  '--security-opt', 'label=disable', '--entrypoint', '/bin/sh',
                                  '-e', 'BC250_TUI_QA_CONTAINER=1', '-v', f'{ROOT}:/repo:ro', image,
                                  '/repo/scripts/qa/tui/bootstrap-container.sh', name])
                if not status:
                    status = run(['podman', 'commit', container, ready])
                run(['podman', 'rm', container])
            if not status:
                status = run(['podman', 'run', '--rm', '--pull=never', '--network=pasta',
                              '--security-opt', 'label=disable', '--entrypoint', '/bin/bash',
                              '-e', 'BC250_TUI_QA_CONTAINER=1', '-v', f'{ROOT}:/repo:ro', ready,
                              '/repo/scripts/qa/tui/check-container.sh', name])
            results.append({'profile': name, 'image': image, 'returncode': status, 'log': str(log_path)})
            print(f'{name}: {"PASS" if status == 0 else "FAIL"} ({log_path})', flush=True)
    (args.output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(row['returncode'] for row in results))


if __name__ == '__main__':
    raise SystemExit(main())
