"""Pinned Real Toolkit entrypoint contract.

The upstream is a root TUI, not a sourceable library. Insert an allowlisted
dispatch immediately before its main loop, keeping the upstream component
functions and their interactive choices. Guard overlapping component functions
to preserve native Control Center ownership. Preparation never executes upstream.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

REPOSITORY = "https://github.com/rpf16rj/bc250-steamos-real-toolkit"
REVISION = "88abd200170c8855f45cc6883e72d243151ceb7a"
VERSION = "1.12.0"
CHANGELOG_URL = f"{REPOSITORY}/blob/{REVISION}/CHANGELOG.md"
# SteamOS /var can be only a few hundred MiB. Keep archive, verified source
# and build caches on the large /home filesystem, outside every user's home.
STATE_ROOT = Path('/home/.bc250-control-center/real-toolkit')
WORKSPACE = STATE_ROOT / 'workspace'
INSTALLED_RUNTIME_ROOT = Path('/usr/libexec/bc250-control-center')
PERSISTENT_RUNTIME_ROOT = STATE_ROOT / 'runtime'
ENTRYPOINT_SHA256 = "a48357c83af9e59f7d02e29706cffc24ef8e171cff18c0e848d82f932186f747"
ARCHIVE_URL = f"https://codeload.github.com/rpf16rj/bc250-steamos-real-toolkit/tar.gz/{REVISION}"
ARCHIVE_SHA256 = "e019a4d5ddb8701cb3cea7681e7eef00ff8f474b1194a3a67e8521015707b813"
_MAIN_LOOP = "while true; do\n    show_menu\n"
_GUARD_BOUNDARY = 'ensure_desktop_shortcut || true\n'
CONFLICT_CHECK_COMMAND = (
    '/usr/bin/python3', '-I',
    str(PERSISTENT_RUNTIME_ROOT / 'bc250-steamos-toolkit-check'),
)
# Wrapping the component functions also covers calls from bulk/nested menus.
GUARDED_FUNCTIONS = {
    'run_install_all': 'all', 'run_revert_all': 'all',
    'run_cpu_governor': 'cpu', 'cpu_governor_setup': 'cpu',
    'run_revert_cpu_governor': 'cpu', 'install_cpu': 'cpu',
    'oc_edit_cpu_config_nano': 'cpu', 'oc_run_bc250_detect': 'cpu',
    'run_gpu_governor': 'gpu', 'gpu_governor_setup': 'gpu',
    'run_revert_gpu_governor': 'gpu', 'run_revert_gpu_governor_files': 'gpu',
    'install_gpu': 'gpu', 'oc_edit_gpu_config_nano': 'gpu',
    'run_overclock_menu': 'performance', 'run_cu_live_manager': 'cu',
    'install_core_unlock': 'cores', 'run_revert_core_unlock': 'cores',
    'install_combined_fix': 'graphics', 'run_revert_gfx1013_fix': 'graphics',
    'install_vaapi_driver': 'video', 'run_revert_vaapi_driver': 'video',
    'install_sensors_readonly': 'fans', 'install_sensors_pwm': 'fans',
    'ensure_sensors_pwm_installed': 'fans', 'run_revert_sensors': 'fans',
    'install_acpi_fix': 'acpi', 'run_revert_acpi_fix': 'acpi',
    'install_ac3_surround': 'audio', 'run_revert_ac3_surround': 'audio',
    'install_dual_audio': 'audio', 'run_revert_dual_audio': 'audio',
    'run_cec_menu': 'cec',
}


def _guard_shell() -> str:
    return '\n'.join(
        f'{function}() {{ {shlex.join(CONFLICT_CHECK_COMMAND)} {component} || return $?; '
        f'bc250cc_original_{function} "$@"; }}'
        for function, component in GUARDED_FUNCTIONS.items()) + '\n'


@dataclass(frozen=True)
class ToolkitAction:
    key: str
    function: str
    category: str


# Keep upstream menus for choices requiring interaction; never feed canned
# answers or set AUTO=1. Individual install/revert routes support native UI.
_GROUPS = {
    "toolkit": {"install-all": "run_install_all", "manual": "run_install_manual",
                "revert-all": "run_revert_all", "verify": "run_status"},
    "performance": {"profiles": "run_overclock_menu", "cpu-install": "run_cpu_governor",
                    "cpu-revert": "run_revert_cpu_governor", "gpu-install": "run_gpu_governor",
                    "gpu-revert": "run_revert_gpu_governor", "cu": "run_cu_live_manager",
                    "cores-install": "install_core_unlock", "cores-revert": "run_revert_core_unlock"},
    "memory": {"swap": "run_swap_menu", "swap-revert": "run_revert_swap",
               "zswap-install": "run_zram_zswap_toggle", "zswap-revert": "run_revert_zram_zswap",
               "uma-install": "install_ram_split", "uma-revert": "run_revert_ram_split"},
    "system": {"mitigations-disable": "run_disable_mitigations", "mitigations-restore": "run_revert_mitigations",
               "acpi-install": "install_acpi_fix", "acpi-revert": "run_revert_acpi_fix",
               "recovery": "run_recovery_menu", "keyring": "run_repair_pacman_keyring"},
    "graphics": {"combined-install": "install_combined_fix", "combined-revert": "run_revert_gfx1013_fix",
                 "proton-install": "install_fsr4_proton", "proton-revert": "revert_fsr4_proton",
                 "video-install": "install_vaapi_driver", "video-revert": "run_revert_vaapi_driver"},
    "audio": {"ac3-install": "install_ac3_surround", "ac3-revert": "run_revert_ac3_surround",
              "dual-install": "install_dual_audio", "dual-revert": "run_revert_dual_audio", "cec": "run_cec_menu"},
    "accessories": {"sensors": "run_sensors_menu", "coolercontrol": "run_coolercontrol_menu",
                    "sensors-readonly": "install_sensors_readonly", "sensors-pwm": "install_sensors_pwm",
                    "sensors-revert": "run_revert_sensors",
                    "aic8800": "run_aic8800_menu", "be200": "run_be200_menu",
                    "dualsense": "run_ds5_bridge_menu", "xbox-adapter": "run_xbox_adapter_menu",
                    "openlinkhub-install": "install_openlinkhub", "openlinkhub-revert": "run_revert_openlinkhub"},
    "extras": {"extras": "run_extras_menu", "emulators": "run_emulators_menu",
               "launch-coach-install": "bc250cc_install_launch_coach",
               "decky-install": "install_toolkit_steamos_control_plugin",
               "decky-plugin-only": "bc250cc_decky_plugin_only",
               "fsr4-launch-options-install": "install_fsr4_launch_options_plugin",
               "kyty-install": "install_kyty", "kyty-status": "run_kyty_status", "kyty-revert": "revert_kyty",
               "lichii-install": "install_lichii", "lichii-shortcut": "lichii_game_shortcut",
               "lichii-revert": "revert_lichii", "emudeck-install": "install_emudeck"},
}
ACTIONS = tuple(ToolkitAction(key, function, category)
                for category, entries in _GROUPS.items() for key, function in entries.items())


def launch_command(action: str) -> str:
    """Use installed code under sudo, never import the desktop user's checkout."""
    action_for(action)
    return ('sudo /usr/bin/python3 -I '
            '/usr/libexec/bc250-control-center/bc250-steamos-toolkit '
            + shlex.quote(action))


def action_for(key: str) -> ToolkitAction:
    for action in ACTIONS:
        if action.key == key:
            return action
    raise ValueError("Unknown SteamOS Real Toolkit action")


CEC_ACTIONS = {
    'cec-setup': ('setup',), 'cec-status': ('status',),
    'cec-wake-install': ('boot-wake', 'install'), 'cec-wake-remove': ('boot-wake', 'remove'),
    'cec-poweroff-install': ('shutdown-standby', 'install'), 'cec-poweroff-remove': ('shutdown-standby', 'remove'),
    'cec-clear-overrides': ('clear-overrides',),
}
ACTIONS += tuple(ToolkitAction(key, 'bc250cc_' + key.replace('-', '_'), 'audio') for key in CEC_ACTIONS)


def guarded_component(key: str) -> str | None:
    action = action_for(key)
    if key in CEC_ACTIONS and key != 'cec-status':
        return 'cec'
    return GUARDED_FUNCTIONS.get(action.function)


def _cec_dispatch():
    helper = '''bc250cc_cec() {
  local uid
  if [[ "${1:-}" != status ]]; then
    ''' + shlex.join(CONFLICT_CHECK_COMMAND) + ''' cec || return $?
  fi
  uid="$(id -u "$REAL_USER")"
  runuser --pty -u "$REAL_USER" -- env HOME="$REAL_HOME" XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" /usr/bin/bash "$SCRIPT_DIR/external/bc250-steamos/bc250-cec.sh" "$@"
}
'''
    return helper + '\n'.join('bc250cc_' + key.replace('-', '_') + '() { bc250cc_cec '
                              + shlex.join(arguments) + '; }' for key, arguments in CEC_ACTIONS.items()) + '\n'


def dispatch_shell() -> str:
    """Dispatch a validated symbolic action, preserving the function's status."""
    cases = "\n".join(f"    {shlex.quote(action.key)}) {action.function} ;;" for action in ACTIONS)
    return _cec_dispatch() + ('bc250cc_install_launch_coach() {\n'
            '  sudo -u "$REAL_USER" -H /usr/bin/bash "$SCRIPT_DIR/extras/bc250-launch-coach/install.sh"\n'
            '}\n'
            'bc250cc_decky_plugin_only() {\n'
            '  [[ -d "$REAL_HOME/homebrew/plugins" ]] || { echo "ERROR: Decky must already be installed" >&2; return 69; }\n'
            '  install_toolkit_steamos_control_plugin\n'
            '}\n'
            'if [[ "${1:-}" == "--bc250cc-action" ]]; then\n'
            '  [[ $# == 2 ]] || { echo "ERROR: expected exactly one toolkit action" >&2; exit 64; }\n'
            '  AUTO=0\n'
            '  case "$2" in\n' + cases + '\n'
            '    *) echo "ERROR: unknown toolkit action" >&2; exit 64 ;;\n'
            '  esac\n  exit $?\nfi\n\n')


def prepare_entrypoint(source: bytes) -> bytes:
    """Attest the exact revision before adding dispatch and component guards."""
    if hashlib.sha256(source).hexdigest() != ENTRYPOINT_SHA256:
        raise ValueError("Real Toolkit entrypoint differs from the reviewed revision")
    text = source.decode("utf-8")
    if text.count(_MAIN_LOOP) != 1:
        raise ValueError("Real Toolkit main-loop contract changed")
    if text.count(_GUARD_BOUNDARY) != 1:
        raise ValueError('Real Toolkit startup/recovery contract changed')
    functions = set(re.findall(r"^([A-Za-z_][A-Za-z_0-9]*)\(\)\s*\{", text, re.MULTILINE))
    absent = {action.function for action in ACTIONS} - functions - {'bc250cc_install_launch_coach', 'bc250cc_decky_plugin_only'} - {
        'bc250cc_' + key.replace('-', '_') for key in CEC_ACTIONS}
    if absent:
        raise ValueError("Real Toolkit action functions are absent: " + ", ".join(sorted(absent)))
    from .steamos_real_toolkit_recovery import (
        adapt_recovery_ctl,
        adapt_recovery_flag,
        adapt_revert_all,
    )
    text = adapt_revert_all(text)
    text = adapt_recovery_flag(text)
    if 'recovery_write_ctl' in functions:
        text = adapt_recovery_ctl(text, CONFLICT_CHECK_COMMAND)
    for function in GUARDED_FUNCTIONS:
        pattern = rf'^{function}\(\)(\s*\{{)'
        text, count = re.subn(pattern, rf'bc250cc_original_{function}()\1', text, flags=re.MULTILINE)
        if count != 1:
            raise ValueError('Real Toolkit guarded function contract changed: ' + function)
    # Recovery flags are handled before the main loop. Define the wrappers
    # before those top-level calls, too, or a renamed function is unavailable
    # to --revert-all and a recovery launch bypasses the ownership checks.
    text = text.replace(_GUARD_BOUNDARY, _guard_shell() + _GUARD_BOUNDARY, 1)
    return text.replace(_MAIN_LOOP, dispatch_shell() + _MAIN_LOOP, 1).encode("utf-8")


def prepare_snapshot(archive: Path, destination: Path) -> Path:
    """Prepare a fresh attested tree atomically, without running toolkit code.

    The caller chooses the staging parent/ownership boundary. Never merge into
    an existing installation: build caches and live provider state need their
    own lifecycle rather than being overwritten by an archive operation.
    """
    archive, destination = Path(archive), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Real Toolkit snapshot destination already exists")
    with archive.open("rb") as source:
        payload = source.read(512 * 1024**2 + 1)
    if len(payload) > 512 * 1024**2:
        raise ValueError("Real Toolkit source archive exceeds the download size limit")
    if hashlib.sha256(payload).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Real Toolkit source archive differs from the reviewed snapshot")
    prefix = f"bc250-steamos-real-toolkit-{REVISION}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".real-toolkit-stage-", dir=destination.parent))
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as bundle:
            members = bundle.getmembers()
            if sum(member.size for member in members) > 2 * 1024**3:
                raise ValueError("Real Toolkit source archive expands beyond the size limit")
            seen = set()
            for member in members:
                path = PurePosixPath(member.name)
                if (path.is_absolute() or ".." in path.parts or not path.parts
                        or path.parts[0] != prefix or "\\" in member.name
                        or not (member.isdir() or member.isfile())):
                    raise ValueError("Unexpected Real Toolkit archive member")
                relative = Path(*path.parts[1:])
                if relative in seen:
                    raise ValueError("Duplicate Real Toolkit archive member")
                seen.add(relative)
            for member in members:
                relative = Path(*PurePosixPath(member.name).parts[1:])
                target = temporary / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.extractfile(member) as source, target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                    target.chmod(0o755 if member.mode & 0o111 else 0o644)
        entrypoint = temporary / "start.sh"
        entrypoint.write_bytes(prepare_entrypoint(entrypoint.read_bytes()))
        from .steamos_real_toolkit_decky import adapt_decky_payload
        for name in ('main.py', 'fan_manager.py'):
            payload = temporary / 'extras/toolkit-steamos-control' / name
            if payload.exists():
                payload.write_bytes(adapt_decky_payload(name, payload.read_bytes()))
        syntax = subprocess.run(["/usr/bin/bash", "-n", str(entrypoint)], capture_output=True, timeout=15)
        if syntax.returncode:
            raise ValueError("Adapted Real Toolkit entrypoint failed Bash syntax validation")
        (temporary / ".bc250cc-provider.json").write_text(json.dumps({
            "repository": REPOSITORY, "revision": REVISION, "version": VERSION,
            "archive_sha256": ARCHIVE_SHA256,
        }) + "\n", encoding="utf-8")
        # mkdtemp's 0700 permission protects an unfinished snapshot. Published
        # code needs traversal for upstream's explicitly unprivileged builders.
        temporary.chmod(0o755)
        os.rename(temporary, destination)
        return destination
    except BaseException:
        shutil.rmtree(temporary)
        raise
