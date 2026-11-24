"""Read Real Toolkit installation evidence without executing toolkit scripts.

Configured files do not prove that a driver or profile is active in this boot.
Keep that distinction explicit; opening the dashboard never installs a provider.
"""
from __future__ import annotations

import json
import os
import platform
import re
from pathlib import Path

from .steamos_graphics_ownership import graphics_conflicts
from .steamos_real_toolkit import (
    REPOSITORY,
    WORKSPACE,
    build_id,
    component_evidence,
    graphics_evidence,
    known_combined_failure,
    lost_after_update,
    old_glibc,
    read_install_record,
    read_toolkit_text,
    tracked_evidence,
    valid_revision,
)
from .steamos_real_toolkit_recovery import unsafe_recovery
from .steamos_toolkit_conflicts import NATIVE_COMPONENTS, native_conflicts


def _alternative_kernel(kernel: str | None) -> bool:
    """Whether the pinned keyboardspecialist backend has a patch set for this kernel.

    Its build (bc250-audio-fix, read at the pinned revision) takes Python and
    glibc from the stable image's own channels, so the mismatch above is not there.
    """
    from .steamos_amdgpu import SUPPORTED_KERNEL_BASES

    release = str(kernel or platform.release())
    return any(release.startswith(base + '.') for base in SUPPORTED_KERNEL_BASES)


def _alternative_proton(home: Path) -> bool:
    tool = home / '.local/share/Steam/compatibilitytools.d/protonge-latest-bc250'
    marker = tool / '.bc250-steamos-install'
    return bool(not tool.is_symlink() and not marker.is_symlink()
                and re.fullmatch(r'[0-9][0-9A-Za-z._-]* [0-9a-f]{64}', read_toolkit_text(marker).strip())
                and (tool / 'compatibilitytool.vdf').is_file() and os.access(tool / 'proton', os.X_OK))


def probe_real_toolkit(*, root: Path = Path('/'), home: Path | None = None,
                       kernel: str | None = None) -> dict:
    root, home = Path(root), Path.home() if home is None else Path(home)
    kernel = platform.release() if kernel is None else kernel
    state_root = root / str(WORKSPACE).lstrip('/')
    try:
        metadata = json.loads(read_toolkit_text(state_root / '.bc250cc-provider.json'))
    except (ValueError, TypeError):
        metadata = {}
    prepared = (isinstance(metadata, dict) and metadata.get('repository') == REPOSITORY
                and valid_revision(str(metadata.get('revision') or ''))
                and (state_root / 'start.sh').is_file())
    revision = str(metadata.get('revision')) if prepared else ''
    graphics = graphics_evidence(root, kernel)
    marker = home / '.local/share/Steam/compatibilitytools.d/.bc250-fsr4-marker'
    proton_tools = []
    proton_incomplete = False
    for line in read_toolkit_text(marker).splitlines():
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
    environment = read_toolkit_text(root / 'etc/environment')
    radv_ready = 'VK_DRIVER_FILES' in environment and 'bc250-gfx1013' in environment
    components = component_evidence(root, home, kernel)
    current_build = build_id(root)
    lost = lost_after_update(read_install_record(state_root.parent), current_build,
                             tracked_evidence(components, graphics), os.getuid())
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
        'old_glibc': old_glibc(),
        'combined_build_blocked': known_combined_failure(kernel),
        'alternative_kernel': _alternative_kernel(kernel),
        'alternative_proton': _alternative_proton(home),
        'workspace': str(state_root), 'components': components,
        'native_ownership': native_ownership,
        'unsafe_recovery': unsafe_recovery(root),
        'build_id': current_build, 'lost_after_update': lost,
        'graphics': graphics,
        'proton': {'state': 'installed' if proton_tools and not proton_incomplete else
                   'incomplete' if marker.exists() else 'not-installed',
                   'tools': proton_tools, 'radv_ready': radv_ready},
    }
