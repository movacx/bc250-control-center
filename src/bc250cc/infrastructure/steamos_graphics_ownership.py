"""Provider-specific graphics evidence and non-mutating conflict checks."""
from __future__ import annotations

import os
import platform
import pwd
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from bc250cc.shared.errors import ActionNeeded


@dataclass(frozen=True)
class VulkanDriverSelection:
    raw: str
    paths: tuple[str, ...] | None


def vulkan_driver_selections(text: str) -> tuple[VulkanDriverSelection, ...]:
    """Read assignments in order; retain invalid later values as unknown.

    Do not execute or expand shell expressions from the environment file.
    Consumers must not fall back to an earlier valid value after a malformed
    later assignment. The raw value also identifies dangling provider paths.
    """
    selections = []
    for line in text.splitlines():
        match = re.fullmatch(r'\s*(?:export\s+)?VK_DRIVER_FILES\s*=\s*(.*)', line)
        if not match:
            continue
        raw = match.group(1)
        try:
            values = shlex.split(raw, comments=True)
            paths = tuple(values[0].split(':')) if len(values) == 1 else None
        except ValueError:
            paths = None
        selections.append(VulkanDriverSelection(raw, paths))
    return tuple(selections)


def graphics_prefix_present(prefix: Path) -> bool:
    """Include partial copies and broken links, but not an empty directory."""
    return (prefix.is_symlink() or prefix.is_file()
            or prefix.is_dir() and any(prefix.iterdir()))


def invoking_home() -> Path:
    uid = os.environ.get('SUDO_UID', '')
    if uid.isdecimal() and int(uid) > 0:
        return Path(pwd.getpwuid(int(uid)).pw_dir)
    return Path.home()


def _kernel_conflicts(provider: str, root: Path, kernel: str | None, all_kernels: bool) -> list[Path]:
    release = platform.release() if kernel is None else kernel
    if release in {'.', '..'} or not re.fullmatch(r'[A-Za-z0-9._+-]+', release):
        raise ValueError('Unsafe kernel release for graphics ownership check')
    modules = root / 'usr/lib/modules'
    directories = sorted(modules.glob('*/updates')) if all_kernels else [modules / release / 'updates']
    conflicts = []
    for updates in directories:
        gfx = updates / '.bc250-gfx1013-fix'
        gfx_present = gfx.exists() or gfx.is_symlink()
        common = [updates / name for name in ('.bc250-audio-fix', '.bc250-metrics-fix')]
        if provider == 'real-toolkit':
            # Alternative rollback retains this marker until its initramfs
            # rebuild succeeds, even if the on-disk override is already gone.
            if gfx_present:
                conflicts.append(gfx)
            for marker in common:
                if not marker.exists() and not marker.is_symlink():
                    continue
                if marker.is_symlink() or not re.fullmatch(r'[0-9a-f]{64}', marker.read_text().strip()):
                    conflicts.append(marker)
            telemetry = updates / '.bc250-control-center-telemetry-oc-2400'
            overrides = [updates / ('amdgpu.ko' + suffix) for suffix in ('', '.zst', '.xz', '.gz')]
            if (telemetry.exists() or telemetry.is_symlink()) and any(path.exists() or path.is_symlink() for path in overrides):
                conflicts.append(telemetry)
        elif gfx.is_symlink():
            conflicts.append(gfx)
        elif not gfx_present:
            # Current alternative markers have a hash plus composition tag;
            # Real Toolkit and older installs use a shared hash-only marker.
            # Do not silently adopt those through the alternative installer.
            for marker in common:
                if not marker.exists() and not marker.is_symlink():
                    continue
                fields = [] if marker.is_symlink() else marker.read_text().split()
                if not (len(fields) == 2 and re.fullmatch(r'[0-9a-f]{64}', fields[0])
                        and fields[1] == 'smu-8core-metrics-r1'):
                    conflicts.append(marker)
    return conflicts


def graphics_conflicts(provider: str, *, root: Path = Path('/'), home: Path | None = None,
                       kernel: str | None = None, all_kernels: bool = False) -> tuple[str, ...]:
    home = invoking_home() if home is None else Path(home)
    environment = root / 'etc/environment'
    try:
        text = environment.read_text(encoding='utf-8')
    except FileNotFoundError:
        text = ''
    selections = vulkan_driver_selections(text)
    if provider == 'real-toolkit':
        paths = [root / 'usr/lib/libvulkan_radeon_driconf.so',
                 root / 'usr/lib/systemd/user-environment-generators/60-bc250-gfx1013',
                 home / '.local/share/bc250-mesh-shader/install.conf']
        for selection in selections:
            entries = selection.paths or ()
            own_entries = [entry for entry in entries if entry.startswith('/opt/bc250-gfx1013/')
                           and '..' not in Path(entry).parts]
            if (not own_entries or any(entry not in own_entries
                                      and entry != '/usr/share/vulkan/icd.d/radeon_icd.i686.json'
                                      for entry in entries)):
                paths.append(environment)
                break
    elif provider == 'keyboardspecialist':
        # A partial copy can contain libraries before its ICD is published;
        # the environment can also outlive the prefix. Both need the original
        # provider's repair/removal. A downloaded source tree proves nothing.
        prefix = root / 'opt/bc250-gfx1013'
        paths = []
        if graphics_prefix_present(prefix):
            paths.append(prefix)
        if any('/opt/bc250-gfx1013/' in selection.raw for selection in selections):
            paths.append(environment)
    else:
        raise ValueError('Unknown SteamOS graphics provider: ' + str(provider))
    paths.extend(_kernel_conflicts(provider, root, kernel, all_kernels))
    return tuple(str(path) for path in paths if path.exists() or path.is_symlink())


def require_graphics_provider(provider: str, *, root: Path = Path('/'), home: Path | None = None,
                              kernel: str | None = None, all_kernels: bool = False) -> None:
    conflicts = graphics_conflicts(provider, root=root, home=home, kernel=kernel, all_kernels=all_kernels)
    if conflicts:
        other = ('keyboardspecialist / Control Center' if provider == 'real-toolkit'
                 else 'Real Toolkit / GFX1013 or legacy kernel')
        raise ActionNeeded('Existing ' + other + ' graphics artifacts were found. Use that provider to '
                           'inspect and remove its installation before changing the graphics backend: '
                           + ', '.join(conflicts))


def alternative_guard_command() -> str:
    return shlex.join(('/usr/bin/python3', '-I',
                       '/usr/libexec/bc250-control-center/bc250-steamos-toolkit-check',
                       'alternative-graphics'))
