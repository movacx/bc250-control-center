"""Read-only ownership checks before overlapping Real Toolkit operations."""
from __future__ import annotations

from pathlib import Path

from .steamos_graphics_ownership import invoking_home

NATIVE_COMPONENTS = ('cpu', 'gpu', 'cu', 'cores', 'fans', 'acpi', 'audio', 'video', 'cec')
BULK_COMPONENTS = NATIVE_COMPONENTS[:-1]  # Upstream bulk flows do not configure CEC.


def native_conflicts(component: str, root: Path = Path('/'), *, home: Path | None = None) -> tuple[str, ...]:
    """Identify configured native controllers, not merely installed helpers.

    The checked unit contents/drop-ins are Control Center ownership evidence.
    Their presence protects disabled persistence too; disabling a service must
    not make its configuration available for another installer's deletion.
    """
    if component not in {*NATIVE_COMPONENTS, 'performance', 'all'}:
        raise ValueError('Unknown toolkit conflict component: ' + str(component))
    components = {'cpu', 'gpu', 'cu'} if component == 'performance' else (
        set(BULK_COMPONENTS) if component == 'all' else {component})
    home = Path(home) if home is not None else (invoking_home() if root == Path('/') else root / 'home')
    units = {
        'cpu': ('bc250-smu-oc.service',),
        'gpu': ('cyan-skillfish-governor-smu.service', 'oberon-governor.service'),
        'cu': ('bc250-cu-live-manager.service',),
        'cores': ('bc250-core-unlock.service',),
        'fans': ('bc250-fan-control.service', 'bc250-fan-pwm-restore.service'),
    }
    found = []
    artifacts = {
        'acpi': (root / 'etc/default/grub.d/92-bc250-acpi.cfg',),
        'audio': (root / 'etc/udev/rules.d/91-bc250-control-center-hdmi-ac3.rules',
                  root / 'etc/wireplumber/wireplumber.conf.d/90-bc250-control-center-hdmi-ac3.conf',
                  home / '.config/wireplumber/wireplumber.conf.d/90-bc250-control-center-hdmi-ac3.conf'),
        'video': (root / 'etc/environment.d/90-bc250-control-center-vaapi.conf',
                  root / 'etc/profile.d/zz-bc250-control-center-vaapi.sh',
                  root / 'etc/X11/Xsession.d/95bc250-vaapi'),
        'cec': (root / 'etc/udev/rules.d/60-bc250-control-center-cec.rules',
                root / 'etc/systemd/system/bc250-control-center-cec-poweroff.service',
                home / '.config/cecd/config.d/50-bc250-control-center.toml',
                home / '.config/systemd/user/bc250-control-center-cec-wake.service'),
    }
    for item in sorted(components):
        for unit in units.get(item, ()):
            for directory in ('etc/systemd/system', 'usr/lib/systemd/system'):
                path = root / directory / unit
                try:
                    content = path.read_text(encoding='utf-8')
                except FileNotFoundError:
                    continue
                if ('bc250-control-center/' in content
                        or item == 'cores' and '/var/lib/bc250-core-unlock/bin/bc250-core-unlock' in content):
                    found.append('/' + str(path.relative_to(root)))
        if item == 'gpu':
            config = root / 'etc/cyan-skillfish-governor-smu/config.toml'
            dropin = root / 'etc/systemd/system/cyan-skillfish-governor-smu.service.d/91-bc250-control-center-overlay-preflight.conf'
            if config.exists() and dropin.exists():
                found.append('/' + str(dropin.relative_to(root)))
        for path in artifacts.get(item, ()):
            try:
                content = path.read_text(encoding='utf-8')
            except FileNotFoundError:
                continue
            if content.startswith('# Managed by BC250 Control Center'):
                found.append('/' + str(path.relative_to(root)) if path.is_relative_to(root) else str(path))
    return tuple(found)


def require_no_native_conflicts(component: str, root: Path = Path('/'), *, home: Path | None = None) -> None:
    conflicts = native_conflicts(component, root, home=home)
    if conflicts:
        raise RuntimeError(
            'Control Center manages this component. Use its existing controls; '
            'the Real Toolkit operation was stopped before replacing native configuration: '
            + ', '.join(conflicts))
