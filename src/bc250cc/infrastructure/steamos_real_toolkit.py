"""Real Toolkit entrypoint contract, tracking the upstream's latest revision.

The upstream is a root TUI, not a sourceable library. Insert an allowlisted
dispatch immediately before its main loop, keeping the upstream component
functions and their interactive choices. Guard overlapping component functions
to preserve native Control Center ownership. Preparation never executes upstream.

No revision or digest is pinned: each run resolves the newest commit of the
tracked branch, so an upstream fix reaches users without a release of this
application. Trust is structural instead of by hash. The entrypoint must still
have the one main loop and startup boundary the adapter patches, every action
function we dispatch to, and every function we guard exactly once; otherwise
nothing is prepared or run and the cache is discarded.
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

from .steamos_readonly import STEAMOS_PASSWORD_GUARD

REPOSITORY = "https://github.com/rpf16rj/bc250-steamos-real-toolkit"
# The tracked branch, not a commit: the commit is resolved on every run and
# recorded in the workspace metadata (see steamos_real_toolkit_runtime).
BRANCH = "main"
REVISION = BRANCH
VERSION = "latest"
CHANGELOG_URL = f"{REPOSITORY}/blob/{BRANCH}/CHANGELOG.md"
REVISION_API = "https://api.github.com/repos/rpf16rj/bc250-steamos-real-toolkit/commits/" + BRANCH
ARCHIVE_URL_TEMPLATE = "https://codeload.github.com/rpf16rj/bc250-steamos-real-toolkit/tar.gz/{revision}"
_REVISION_PATTERN = re.compile(r"[0-9a-f]{40}")
# SteamOS /var can be only a few hundred MiB. Keep archive, verified source
# and build caches on the large /home filesystem, outside every user's home.
STATE_ROOT = Path('/home/.bc250-control-center/real-toolkit')
WORKSPACE = STATE_ROOT / 'workspace'
INSTALLED_RUNTIME_ROOT = Path('/usr/libexec/bc250-control-center')
PERSISTENT_RUNTIME_ROOT = STATE_ROOT / 'runtime'
_MAIN_LOOP = "while true; do\n    show_menu\n"
_GUARD_BOUNDARY = 'ensure_desktop_shortcut || true\n'
_GUARD_REPLACEMENT = ': # the desktop shortcut is not created for this copy\n'
# A tree without .git and without external/bc250_smu_oc counts upstream as a
# lone start.sh: it clones main from GitHub and execs *that* copy, which has no
# dispatch and no guards, as root. Never let the prepared entrypoint hand over
# to an unprepared one; refuse instead.
_STANDALONE_HANDOFF = 'exec bash "$TOOLKIT_REPO_DIR/start.sh" "$@"'
_STANDALONE_REFUSAL = ('echo "ERROR: the prepared toolkit tree is incomplete; Control Center does not run an '
                       'unprepared copy. Try the action again." >&2; exit 70')
_STANDALONE_MARKER = Path('external/bc250_smu_oc')
_FOREIGN_HANDOFF = re.compile(r'exec\s+(?:sudo\s+)?(?:/usr/bin/)?bash\s+"?\$TOOLKIT_REPO_DIR')
#: What the ownership checker exits with when it refuses (check-steamos-toolkit-conflicts.py).
CONFLICT_STATUS = 79
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
    # Its revert removes only its own AUR package, so only the install is guarded.
    'install_openlinkhub': 'openlinkhub',
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
    # Only what Control Center does not already do natively. GPU/CPU governors,
    # CU, core unlock, profiles, memory/swap, fans/sensors, CoolerControl,
    # mitigations (Kernel boot options) and the upstream extras are deliberately not exposed.
    "toolkit": {"verify": "run_status"},
    "system": {"acpi-install": "install_acpi_fix", "acpi-revert": "run_revert_acpi_fix",
               "recovery": "run_recovery_menu", "keyring": "run_repair_pacman_keyring"},
    "graphics": {"combined-install": "install_combined_fix", "combined-revert": "run_revert_gfx1013_fix",
                 "proton-install": "install_fsr4_proton", "proton-revert": "revert_fsr4_proton",
                 "video-install": "install_vaapi_driver", "video-revert": "run_revert_vaapi_driver"},
    "audio": {"ac3-install": "install_ac3_surround", "ac3-revert": "run_revert_ac3_surround",
              "dual-install": "install_dual_audio", "dual-revert": "run_revert_dual_audio", "cec": "run_cec_menu"},
    "drivers": {"aic8800": "run_aic8800_menu", "be200": "run_be200_menu",
                "dualsense": "run_ds5_bridge_menu", "xbox-adapter": "run_xbox_adapter_menu",
                "openlinkhub-install": "install_openlinkhub", "openlinkhub-revert": "run_revert_openlinkhub"},
}
ACTIONS = tuple(ToolkitAction(key, function, category)
                for category, entries in _GROUPS.items() for key, function in entries.items())


def launch_command(action: str) -> str:
    """Use installed code under sudo, never import the desktop user's checkout."""
    action_for(action)
    # The deck account has no password until its owner sets one, and sudo then
    # fails without saying why: say so first, as every other SteamOS workflow does.
    return (STEAMOS_PASSWORD_GUARD + '\nbc250_require_password\n'
            'sudo /usr/bin/python3 -I '
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


def valid_revision(value: str) -> bool:
    return bool(_REVISION_PATTERN.fullmatch(value or ""))


def archive_url(revision: str) -> str:
    if not valid_revision(revision):
        raise ValueError("Real Toolkit revision must be a full commit hash")
    return ARCHIVE_URL_TEMPLATE.format(revision=revision)


def prepare_entrypoint(source: bytes) -> bytes:
    """Check the structural contract, then add dispatch and component guards."""
    text = source.decode("utf-8")
    if text.count(_MAIN_LOOP) != 1:
        raise ValueError("Real Toolkit main-loop contract changed")
    if text.count(_GUARD_BOUNDARY) != 1:
        raise ValueError('Real Toolkit startup/recovery contract changed')
    if text.count(_STANDALONE_HANDOFF) > 1:
        raise ValueError('Real Toolkit standalone re-launch contract changed')
    text = text.replace(_STANDALONE_HANDOFF, _STANDALONE_REFUSAL, 1)
    if _FOREIGN_HANDOFF.search(text):
        raise ValueError('Real Toolkit standalone re-launch contract changed')
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
    # Its desktop shortcut would start this workspace without the lock, the
    # session note and the root restore; only Control Center starts this copy.
    text = text.replace(_GUARD_BOUNDARY, _guard_shell() + _GUARD_REPLACEMENT, 1)
    return text.replace(_MAIN_LOOP, dispatch_shell() + _MAIN_LOOP, 1).encode("utf-8")


def prepare_snapshot(archive: Path, destination: Path, revision: str) -> Path:
    """Prepare a fresh tree atomically, without running toolkit code.

    The caller chooses the staging parent/ownership boundary. Never merge into
    an existing installation: build caches and live provider state need their
    own lifecycle rather than being overwritten by an archive operation.
    """
    archive, destination = Path(archive), Path(destination)
    if not valid_revision(revision):
        raise ValueError("Real Toolkit revision must be a full commit hash")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Real Toolkit snapshot destination already exists")
    with archive.open("rb") as source:
        payload = source.read(512 * 1024**2 + 1)
    if len(payload) > 512 * 1024**2:
        raise ValueError("Real Toolkit source archive exceeds the download size limit")
    archive_digest = hashlib.sha256(payload).hexdigest()
    prefix = f"bc250-steamos-real-toolkit-{revision}"
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
        if not (temporary / _STANDALONE_MARKER).is_dir():
            # Without it start.sh treats itself as a lone script and fetches
            # another copy; the adapter above refuses that hand-over, so the
            # action could only fail. Say why now, before anything runs.
            raise ValueError("Real Toolkit archive layout changed: " + str(_STANDALONE_MARKER) + " is missing")
        original = entrypoint.read_bytes()
        entrypoint.write_bytes(prepare_entrypoint(original))
        syntax = subprocess.run(["/usr/bin/bash", "-n", str(entrypoint)], capture_output=True, timeout=15)
        if syntax.returncode:
            raise ValueError("Adapted Real Toolkit entrypoint failed Bash syntax validation")
        (temporary / ".bc250cc-provider.json").write_text(json.dumps({
            "repository": REPOSITORY, "branch": BRANCH, "revision": revision,
            "archive_sha256": archive_digest,
            "entrypoint_sha256": hashlib.sha256(original).hexdigest(),
        }) + "\n", encoding="utf-8")
        # mkdtemp's 0700 permission protects an unfinished snapshot. Published
        # code needs traversal for upstream's explicitly unprivileged builders.
        temporary.chmod(0o755)
        os.rename(temporary, destination)
        return destination
    except BaseException:
        shutil.rmtree(temporary)
        raise
