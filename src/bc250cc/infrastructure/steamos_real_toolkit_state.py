"""Read Real Toolkit installation evidence without executing toolkit scripts.

Configured files do not prove that a driver or profile is active in this boot.
Keep that distinction explicit; opening the dashboard never installs a provider.
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from .steamos_graphics_ownership import (
    graphics_conflicts,
    graphics_prefix_present,
    vulkan_driver_selections,
)
from .steamos_real_toolkit import REPOSITORY, WORKSPACE, valid_revision
from .steamos_toolkit_conflicts import NATIVE_COMPONENTS, native_conflicts

#: The glibc the toolkit's downloaded Python is made for (see R-6d239d09).
_TOOLKIT_GLIBC = (2, 44)


def _old_glibc() -> bool:
    """Whether the toolkit's downloaded build tools are too new for this system."""
    try:
        numbers = os.confstr('CS_GNU_LIBC_VERSION').split()[1].split('.')
        return tuple(int(part) for part in numbers[:2]) < _TOOLKIT_GLIBC
    except (AttributeError, IndexError, OSError, ValueError):
        return False


def _alternative_kernel(kernel: str | None) -> bool:
    """Whether the pinned keyboardspecialist backend has a patch set for this kernel.

    Its build (bc250-audio-fix, read at the pinned revision) takes Python and
    glibc from the stable image's own channels, so the mismatch above is not there.
    """
    from .steamos_amdgpu import SUPPORTED_KERNEL_BASES

    release = str(kernel or platform.release())
    return any(release.startswith(base + '.') for base in SUPPORTED_KERNEL_BASES)


def _text(path: Path) -> str:
    try:
        with path.open(encoding='utf-8') as stream:
            return stream.read(131072)
    except (OSError, UnicodeError):
        return ''


def _icd_valid(path: Path, prefix: Path, root: Path) -> bool:
    try:
        content = json.loads(_text(path))
        library = Path(content['ICD']['library_path'])
        library = (root / str(library).lstrip('/') if library.is_absolute() else path.parent / library).resolve()
        if not library.is_relative_to(prefix.resolve()):
            return False
        with library.open('rb') as stream:
            return stream.read(4) == b'\x7fELF'
    except (OSError, ValueError, KeyError, TypeError):
        return False


def probe_real_toolkit(*, root: Path = Path('/'), home: Path | None = None,
                       kernel: str | None = None) -> dict:
    root, home = Path(root), Path.home() if home is None else Path(home)
    kernel = platform.release() if kernel is None else kernel
    state_root = root / str(WORKSPACE).lstrip('/')
    try:
        metadata = json.loads(_text(state_root / '.bc250cc-provider.json'))
    except (ValueError, TypeError):
        metadata = {}
    prepared = (isinstance(metadata, dict) and metadata.get('repository') == REPOSITORY
                and valid_revision(str(metadata.get('revision') or ''))
                and (state_root / 'start.sh').is_file())
    revision = str(metadata.get('revision')) if prepared else ''
    prefix = root / 'opt/bc250-gfx1013'
    descriptors = list(prefix.glob('*/share/vulkan/icd.d/radeon_icd.x86_64.json'))
    valid = [path for path in descriptors if _icd_valid(path, prefix, root)]
    selections = vulkan_driver_selections(_text(root / 'etc/environment'))
    activation = (selections[-1].paths or ()) if selections else ()
    activated = [path for path in valid if '/' + str(path.relative_to(root)) in activation]
    try:
        prefix_present = graphics_prefix_present(prefix)
    except OSError:
        prefix_present = None
    selection_present = any('/opt/bc250-gfx1013/' in selection.raw for selection in selections)
    graphics_state = ('configured' if activated else
                      'incomplete' if descriptors or prefix_present or selection_present else
                      'unknown' if prefix_present is None else 'not-installed')
    module_root = root / 'usr/lib/modules' / kernel / 'updates'
    modules = [str(p) for p in module_root.glob('amdgpu.ko*') if p.is_file()]
    marker = home / '.local/share/Steam/compatibilitytools.d/.bc250-fsr4-marker'
    proton_tools = []
    proton_incomplete = False
    for line in _text(marker).splitlines():
        if not line.strip():
            continue
        fields = line.split(':')
        if len(fields) == 2 and fields[0] and fields[1] and '/' not in fields[1] and fields[1] not in {'.', '..'}:
            tool = marker.parent / fields[1]
            launcher = tool / 'proton'
            if (tool / 'compatibilitytool.vdf').is_file() and launcher.is_file() and os.access(launcher, os.X_OK):
                if fields[1] not in proton_tools:
                    proton_tools.append(fields[1])
                continue
        proton_incomplete = True
    # The toolkit's own FSR4 Proton precondition, word for word: it refuses
    # unless /etc/environment names its patched RADV (keyboardspecialist's
    # Mesa does not count). Read here so the row says so before the password.
    environment = _text(root / 'etc/environment')
    radv_ready = 'VK_DRIVER_FILES' in environment and 'bc250-gfx1013' in environment
    components = {
        'cpu': (root / 'etc/bc250-smu-oc.conf').is_file(),
        'gpu': (root / 'etc/cyan-skillfish-governor-smu/config.toml').is_file(),
        'core-unlock': (root / 'etc/systemd/system/bc250-core-unlock.service').is_file(),
        # Its removal keeps the archive as a cache; the service goes with it.
        'acpi': ((root / 'var/lib/bc250-acpi-fix/acpi_override.cpio').is_file()
                 and (root / 'etc/systemd/system/bc250-acpi-heal.service').is_file()),
        'video': ((root / 'var/lib/bc250/dri/bc250_drv_video.so').is_file()
                  and (root / 'etc/environment.d/99-bc250-vaapi.conf').is_file()),
        'dual-audio': ((home / '.config/wireplumber/wireplumber.conf.d/50-bc250-audio.conf').is_file()
                       and (home / '.config/pipewire/pipewire.conf.d/60-bc250-ac3-output.conf').is_file()
                       # The two in the system go with a SteamOS update.
                       and (root / 'etc/alsa/conf.d/61-bc250-a52.conf').is_file()
                       and (root / 'usr/local/share/wireplumber/scripts/90-bc250-audio-mode.lua').is_file()),
        'recovery': (root / 'etc/grub.d/42_bc250-recovery').is_file(),
    }
    native_ownership = {}
    for component in NATIVE_COMPONENTS:
        try:
            native_ownership[component] = list(native_conflicts(component, root, home=home))
        except OSError:
            # An unreadable ownership record is unknown. The privileged
            # checker still rechecks/fails closed at operation time.
            native_ownership[component] = None
    try:
        # The same check the privileged runtime makes before the combined fix:
        # read here so the row says so instead of failing after the password.
        foreign_graphics = list(graphics_conflicts('real-toolkit', root=root, home=home, kernel=kernel))
    except (OSError, ValueError):
        foreign_graphics = None
    return {
        'provider': REPOSITORY, 'reviewed_revision': revision, 'prepared': bool(prepared),
        'foreign_graphics': foreign_graphics,
        'old_glibc': _old_glibc(),
        'alternative_kernel': _alternative_kernel(kernel),
        'workspace': str(state_root), 'components': components,
        'native_ownership': native_ownership,
        'graphics': {'state': graphics_state, 'icds': [str(p) for p in valid],
                     'activation_configured': bool(activated), 'active': None,
                     'kernel_override_installed': bool(modules), 'kernel_modules': modules},
        'proton': {'state': 'installed' if proton_tools and not proton_incomplete else
                   'incomplete' if marker.exists() else 'not-installed',
                   'tools': proton_tools, 'radv_ready': radv_ready},
    }
