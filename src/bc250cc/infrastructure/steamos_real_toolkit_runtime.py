"""Real Toolkit download, persistent workspace and explicit action launcher."""
from __future__ import annotations

import fcntl
import json
import os
import platform
import pwd
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import steamos_real_toolkit as provider
from . import steamos_root_guard as guard
from .hardware_identity import require_bc250_hardware
from .steamos_graphics_ownership import graphics_conflicts
from .steamos_real_toolkit_recovery import (
    RECOVERY_REFUSAL,
    RECOVERY_REMOVE,
    RECOVERY_UNSAFE,
    unsafe_boot_paths,
    unsafe_grub_recovery,
    unsafe_recovery,
)
from .steamos_toolkit_conflicts import native_conflicts

STATE_ROOT = provider.STATE_ROOT
READONLY_COMMAND = '/usr/bin/steamos-readonly'


def _read_root(attempts: int = 2) -> guard.RootReading:
    """The one place the launcher reads the root: state plus what the command said."""
    return guard.read_root(attempts=attempts)


def _root_mode(attempts: int = 1) -> str:
    """``enabled`` (read-only), ``disabled`` (writable) or ``unknown``.

    Read from the text of ``steamos-readonly status``: it exits 1 while the root
    is writable, so its exit status says nothing about the answer.
    """
    return _read_root(attempts).state


def _say(message: str, *, error: bool = False) -> None:
    """Print without ever failing: the terminal may already be gone (SIGHUP)."""
    try:
        print(message, file=sys.stderr if error else sys.stdout, flush=True)
    except (OSError, ValueError):
        pass


def _adopt_orphans() -> None:
    """Make processes the toolkit leaves behind children of this launcher.

    A signal sent to the launcher alone ends the top-level Bash, while a
    compiler under it goes on writing; orphaned, it could not be waited for.
    """
    try:
        import ctypes

        ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0)  # PR_SET_CHILD_SUBREAPER
    except (AttributeError, OSError):
        pass


def _children(pid: int | None = None) -> list[int]:
    pid = os.getpid() if pid is None else pid
    try:
        text = Path(f'/proc/{pid}/task/{pid}/children').read_text(encoding='ascii')
    except OSError:
        return []
    return [int(item) for item in text.split()]


#: Programs that must never be cut short: the package database, the modules'
#: index, the initramfs, the boot menu. The kernel keeps 15 letters of a name.
WRITERS = frozenset(name[:15] for name in (
    'pacman', 'pacman-key', 'rpm', 'rpm-ostree', 'dpkg', 'apt-get', 'dkms', 'depmod', 'ldconfig',
    'mkinitcpio', 'dracut', 'update-initramfs', 'grub-mkconfig', 'grub-install', 'update-grub',
    'grub-editenv', 'steamos-readonly', 'btrfs',
))


def _writer_in(pid: int) -> str:
    """The name of a writer that is ``pid`` or runs under it, or ''."""
    try:
        name = Path(f'/proc/{pid}/comm').read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return ''
    if name in WRITERS:
        return name
    return next((found for found in map(_writer_in, _children(pid)) if found), '')


def _end_descendants(seconds: float = 20.0) -> None:
    """After an interrupted action: nothing of it may still write to the system.

    Each process is asked to end once, and a compiler that does not is killed.
    One with a package or boot write under it is not signalled at all (sudo
    would pass the signal on to it): it is waited for, however long it takes.
    """
    deadlines: dict[int, float] = {}
    told = ''
    while True:
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            return
        for pid in _children():
            writer = _writer_in(pid)
            if writer:
                if writer != told:
                    _say('Interrupted. Waiting for ' + writer + ' to finish, so the system is not left half written.')
                    told = writer
                continue
            now = time.monotonic()
            try:
                if pid not in deadlines:
                    deadlines[pid] = now + seconds
                    os.kill(pid, signal.SIGTERM)
                elif now >= deadlines[pid]:
                    os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(0.2)


@contextmanager
def _interactive_signal_relay():
    """Keep terminal job control intact and defer parent termination to cleanup.

    The child inherits the foreground process group for interactive sudo/TUI
    input. Forward signals directed only at the launcher as well; terminal
    group signals may already have reached the child. Do not restore root
    while the top-level upstream process is still running.
    """
    child = None
    received = None
    previous = {}

    def forward(number, _frame):
        nonlocal received
        received = number
        if child is not None and child.poll() is None:
            try:
                child.send_signal(number)
            except ProcessLookupError:
                pass

    def execute(command):
        nonlocal child
        if received is not None:
            return 128 + received
        child = subprocess.Popen(command)
        # A signal can arrive during process creation, before assignment.
        if received is not None:
            forward(received, None)
        try:
            code = child.wait()
        except BaseException:
            # Unexpected Python failures must not leave an upstream writer
            # alive while the outer finally restores the filesystem mode.
            if child.poll() is None:
                try:
                    child.terminate()
                except ProcessLookupError:
                    pass
            child.wait()
            raise
        if received is not None or code < 0:
            _end_descendants()
        if received is not None:
            return 128 + received
        return 128 - code if code < 0 else code

    _adopt_orphans()
    try:
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[number] = signal.signal(number, forward)
        yield execute
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _restore_root(initial: str, code: int | None) -> None:
    """Give the root back as it was, verified, or say exactly how to."""
    if _root_mode() == initial:
        return
    verb = 'enable' if initial == 'enabled' else 'disable'
    for attempt in range(3):
        try:
            result = subprocess.run([READONLY_COMMAND, verb], check=False, timeout=30)
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None and result.returncode == 0 and _root_mode() == initial:
            return
        if attempt < 2:
            time.sleep(1)
    raise RuntimeError('Could not restore SteamOS read-only mode to ' + initial
                       + '; toolkit exit status: ' + str(code)
                       + '. Run: sudo steamos-readonly ' + verb
                       + ' (check it with steamos-readonly status).')


def run_preserving_root_mode(command: list[str], initial: str | None = None, *,
                             on_restored=None) -> int:
    """Leave privileged windows to upstream, then verify the original mode.

    Do not unlock the root during source downloads or long compilation. On
    completion or a Python exception, restore a changed root. ``initial`` is the
    state to give back when the caller already decided it (an interrupted earlier
    run can make the current state differ from the original). ``on_restored`` runs
    once the original state is verified back, whether the action finished or not.
    """
    if initial is None:
        initial = _root_mode()
    if initial not in {'enabled', 'disabled'}:
        raise RuntimeError('Cannot determine SteamOS read-only mode; the toolkit action was not started.')
    with _interactive_signal_relay() as execute:
        code = None
        try:
            code = execute(command)
            return code
        finally:
            _restore_root(initial, code)
            if on_restored is not None:
                on_restored()


def prepare_state_root(path: Path) -> None:
    """Create only below root-owned, non-writable, non-symlink ancestors."""
    if not path.is_absolute():
        raise ValueError('Real Toolkit storage path must be absolute')
    for directory in reversed((path, *path.parents)):
        try:
            metadata = directory.lstat()
        except FileNotFoundError:
            directory.mkdir(mode=0o755)
            metadata = directory.lstat()
        if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0
                or metadata.st_mode & 0o022):
            raise PermissionError('Real Toolkit storage must have protected root-owned ancestors: ' + str(directory))


def require_source_space(path: Path) -> None:
    if shutil.disk_usage(path).free < provider.SOURCE_SPACE_MIB * 1024**2:
        raise RuntimeError('Real Toolkit source preparation needs at least 768 MiB free on /home. '
                           'Kernel and Mesa builds require additional space.')


def cache_guard_runtime(installed: Path, destination: Path) -> None:
    """Keep guarded Decky/recovery workflows usable after app package removal.

    This directory is a sibling of the upstream workspace, so upstream build
    ownership changes cannot make the privileged checker user-writable.
    """
    for relative in ('bc250-steamos-toolkit-check', 'lib/bc250_steamos_toolkit_runtime.zip'):
        source, target = installed / relative, destination / relative
        metadata = source.lstat()
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_mode & 0o022
                or os.geteuid() == 0 and metadata.st_uid != 0):
            raise PermissionError('Installed Toolkit guard runtime is not protected: ' + str(source))
        for directory in (destination, target.parent):
            if directory.is_symlink():
                raise PermissionError('Toolkit guard runtime directory cannot be a symlink')
            directory.mkdir(mode=0o755, exist_ok=True)
            info = directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022
                    or os.geteuid() == 0 and info.st_uid != 0):
                raise PermissionError('Toolkit guard runtime directory is not protected')
        if target.is_symlink():
            raise PermissionError('Toolkit guard runtime file cannot be a symlink')
        descriptor, temporary = tempfile.mkstemp(prefix='.guard-', dir=target.parent)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(source.read_bytes())
            os.chmod(temporary, 0o755 if relative.endswith('-check') else 0o644)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)


def resolve_revision() -> str:
    """Newest commit of the tracked branch, as one full hash.

    The archive is then requested by that hash, so the bytes verified and run
    are those of the commit named here, not of a branch that moves meanwhile.
    """
    request = urllib.request.Request(provider.REVISION_API, headers={
        'Accept': 'application/vnd.github.sha', 'User-Agent': 'bc250-control-center'})
    with urllib.request.urlopen(request, timeout=20) as response:
        revision = response.read(128).decode('ascii', 'replace').strip().lower()
    if not provider.valid_revision(revision):
        raise ValueError('The upstream revision lookup did not return a commit hash')
    return revision


def _cached_revision(state_root: Path) -> str | None:
    """Most recent archive already downloaded, for use when offline."""
    candidates = [path for path in state_root.glob('*.tar.gz')
                  if provider.valid_revision(path.name[:-len('.tar.gz')]) and path.is_file()
                  and not path.is_symlink()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime).name[:-len('.tar.gz')]


def download_archive(destination: Path, revision: str) -> None:
    """Fetch the archive of exactly this commit; never execute a download.

    Content is checked structurally when the snapshot is prepared. A cached
    archive of the same commit is reused; it is immutable by construction.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and not destination.is_symlink():
        return
    handle, name = tempfile.mkstemp(prefix='.download-', dir=destination.parent)
    temporary = Path(name)
    try:
        count = 0
        with os.fdopen(handle, 'wb') as output, urllib.request.urlopen(
                provider.archive_url(revision), timeout=45) as response:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > 512 * 1024**2:
                    raise ValueError('Real Toolkit download exceeds its size limit')
                output.write(chunk)
        if count == 0:
            raise ValueError('Real Toolkit download was empty')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def clear_cache(state_root: Path | None = None) -> None:
    """Forget downloaded sources and the workspace so the next run starts clean.

    Keeps the protected guard runtime and the lock. Upstream may publish a fix
    within hours of a failure, and a half-built tree or a bad archive must not
    survive to the next attempt.
    """
    state_root = STATE_ROOT if state_root is None else state_root
    for pattern in ('*.tar.gz', '.download-*', '.verify-*', '.guard-*'):
        for path in state_root.glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
    clear_workspace(state_root)


def clear_workspace(state_root: Path | None = None) -> None:
    """Forget what an action built, keeping its logs and the downloaded archive."""
    state_root = STATE_ROOT if state_root is None else state_root
    workspace = state_root / 'workspace'
    _keep_failure_logs(workspace, state_root)
    if workspace.is_symlink():
        workspace.unlink()
    elif workspace.exists():
        shutil.rmtree(workspace, ignore_errors=True)


FAILURE_LOGS = 'last-failure'


def _keep_failure_logs(workspace: Path, state_root: Path, *, newest: int = 6) -> None:
    """Copy the toolkit's own logs out before the workspace goes.

    They are what a report needs ("what did the toolkit say") and they live in
    the tree that is about to be deleted. Only the newest few, only plain files.
    """
    logs = workspace / 'logs'
    try:
        files = sorted((path for path in logs.glob('*.log') if path.is_file() and not path.is_symlink()),
                       key=lambda path: path.stat().st_mtime, reverse=True)[:newest]
    except OSError:
        return
    if not files:
        return
    target = state_root / FAILURE_LOGS
    try:
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(mode=0o755)
        for path in files:
            shutil.copyfile(path, target / path.name)
            (target / path.name).chmod(0o644)
    except OSError:
        pass


def _prune_other_archives(state_root: Path, keep: str) -> None:
    for path in state_root.glob('*.tar.gz'):
        if path.name != keep:
            path.unlink(missing_ok=True)


def _workspace_revision(workspace: Path) -> str:
    try:
        return str(json.loads((workspace / '.bc250cc-provider.json').read_text(encoding='utf-8')).get('revision') or '')
    except (OSError, ValueError, AttributeError):
        return ''


def refresh_workspace(snapshot: Path, workspace: Path) -> None:
    """Restore provider files while retaining untracked builds and logs.

    Upstream deliberately gives its build directories to the desktop user.
    Before every explicit run replace the tracked code from a newly verified
    snapshot; never treat a previous mutable build tree as reviewed source.
    """
    if workspace.is_symlink():
        raise ValueError('Real Toolkit workspace cannot be a symlink')
    workspace.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        os.chown(workspace, 0, 0)
        workspace.chmod(0o755)
    for source in sorted(snapshot.rglob('*')):
        relative = source.relative_to(snapshot)
        target = workspace / relative
        if any((workspace / Path(*relative.parts[:n])).is_symlink()
               for n in range(1, len(relative.parts) + 1)):
            raise ValueError('Real Toolkit workspace contains a symlink at a provider path')
        if source.is_dir():
            target.mkdir(exist_ok=True)
            if os.geteuid() == 0:
                os.chown(target, 0, 0)
                target.chmod(0o755)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            handle, name = tempfile.mkstemp(prefix='.provider-', dir=target.parent)
            try:
                with os.fdopen(handle, 'wb') as output, source.open('rb') as content:
                    shutil.copyfileobj(content, output)
                os.chmod(name, source.stat().st_mode & 0o777)
                os.replace(name, target)
            finally:
                Path(name).unlink(missing_ok=True)


def _require_invoking_user() -> pwd.struct_passwd:
    """Validate the privileged SteamOS/BC-250 boundary before preparation."""
    if os.geteuid() != 0:
        raise PermissionError('Real Toolkit launcher requires sudo')
    uid = int(os.environ.get('SUDO_UID', '0'))
    if uid <= 0:
        raise PermissionError('Launch Real Toolkit from the desktop user through sudo')
    user = pwd.getpwuid(uid)
    if not Path(user.pw_dir).is_dir():
        raise ValueError('The invoking user home is unavailable')
    if platform.freedesktop_os_release().get('ID') != 'steamos':
        raise ValueError('Real Toolkit actions are available only on SteamOS')
    require_bc250_hardware()
    return user


def _preflight_root(action: str) -> None:
    """Refuse early, with the reason, and say what is about to happen to the root."""
    reading = _read_root()
    if reading.state not in guard.KNOWN:
        raise RuntimeError(guard.explain_unreadable(reading))
    initial, note = guard.initial_state(reading, guard.read_session(STATE_ROOT))
    if note:
        _say('[WARN] ' + note)
    if initial == guard.PROTECTED:
        _say('SteamOS system files: protected (read-only). The toolkit unlocks them only for the steps '
             'that need it, and Control Center locks them again when the action ends.')
    else:
        _say('SteamOS system files: already writable. They stay writable when the action ends.')
    free, level = guard.var_space()
    if level == 'critical':
        raise RuntimeError('/var has only ' + str(free) + ' MB free and package installs need room there; '
                           'the toolkit action was not started.\n' + guard.VAR_HELP)
    if level == 'low':
        _say('[WARN] /var has only ' + str(free) + ' MB free; it works now, but a package install may not fit.')
    root_free, root_level = guard.root_space()
    if root_level == 'low':
        _say('[WARN] The SteamOS system partition (/) has only ' + str(root_free) + ' MB free. Components that '
             'install packages there (kernel headers, build tools, drivers) can stop half way; a SteamOS '
             'update gives the space back.')


def _begin_root_session(action: str) -> str:
    """The state to give back, written to disk before the toolkit can change anything."""
    reading = _read_root()
    if reading.state not in guard.KNOWN:
        raise RuntimeError(guard.explain_unreadable(reading))
    initial, _note = guard.initial_state(reading, guard.read_session(STATE_ROOT))
    guard.write_session(STATE_ROOT, initial=initial, action=action)
    return initial


#: How long a second action waits for the first, and how often it looks.
LOCK_WAIT_SECONDS = 900
LOCK_POLL_SECONDS = 2


def _holder() -> str:
    """The action that holds the toolkit, as a sentence part, or ''."""
    session = guard.read_session(STATE_ROOT)
    if not guard.session_running(session):
        return ''
    name = str(session.get('action') or 'unknown')
    try:
        since = time.strftime('%H:%M', time.localtime(int(session.get('started') or 0)))
    except (TypeError, ValueError, OverflowError):
        return name
    return name + ', started at ' + since


def _wait_for_lock(lock) -> None:
    """Take the toolkit's lock, waiting for an action already running.

    Two actions pressed a minute apart are normal (R-140dc24c): the second one
    waits and says for what, instead of failing after the password.
    """
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    told = False
    while True:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError as error:
            holder = _holder()
            if time.monotonic() >= deadline:
                raise RuntimeError('Another Real Toolkit action is still running'
                                   + (' (' + holder + ')' if holder else '')
                                   + '. Finish or close its terminal, then try again.') from error
            if not told:
                _say('Waiting for another Real Toolkit action to finish'
                     + (' (' + holder + ')' if holder else '') + '. Press Ctrl+C to cancel.')
                told = True
            time.sleep(LOCK_POLL_SECONDS)


def combined_module_active(root: Path = Path('/'), kernel: str | None = None) -> bool:
    """The toolkit's own AC-3 condition: amdgpu comes from this kernel's updates folder."""
    release = kernel or os.uname().release
    folder = root / 'usr/lib/modules' / release / 'updates'
    try:
        return any(path.is_file() for path in folder.rglob('amdgpu.ko*'))
    except OSError:
        return False


def _require_prerequisites(action: str) -> None:
    """What upstream would refuse minutes later, said before anything is downloaded."""
    if action == 'ac3-install' and not combined_module_active():
        raise RuntimeError('AC-3 audio needs the combined display, audio and graphics fixes first. '
                           'Install them from Kernel and Mesa, restart, and try again.')


_KERNEL_BUILDS = frozenset({
    'combined-install', 'aic8800-install', 'aic8800-legacy-install',
    'dualsense-install', 'xbox-adapter-install',
})
_FULL_KERNEL_FALLBACK = _KERNEL_BUILDS - {'xbox-adapter-install'}
_DOWNLOAD_HOSTS = {
    'combined-install': 'steamdeck-packages.steamos.cloud',
    'acpi-install': 'raw.githubusercontent.com',
    'be200-install': 'deb.debian.org',
    'video-install': 'github.com', 'proton-install': 'github.com',
    'aic8800-install': 'steamdeck-packages.steamos.cloud',
    'aic8800-legacy-install': 'steamdeck-packages.steamos.cloud',
    'dualsense-install': 'steamdeck-packages.steamos.cloud',
    'xbox-adapter-install': 'steamdeck-packages.steamos.cloud',
    'openlinkhub-install': 'aur.archlinux.org',
}
_OPTIONAL_DOWNLOADS = {
    'ac3-install', 'dual-install', 'cec-setup', 'cec-install', 'keyring',
    'aic8800', 'be200', 'dualsense', 'xbox-adapter', 'cec',
}
_MIB = 1024**2
_GIB = 1024**3
_BOOT_TARGETS = {
    'acpi-install': ('etc/systemd/system/bc250-acpi-heal.service',
                     'etc/systemd/system/bc250-cpufreq.service', 'bin/bash'),
    'cec-install': ('etc/systemd/system/bc250-cec.service', 'usr/lib/bc250-cec/bc250-cec-daemon.sh'),
}
_CEC_BOOT_TARGETS = ('etc/systemd/system/bc250-cec-poweroff-standby.service',
                     'var/lib/bc250-control/helper/bc250-cec-poweroff-standby', 'usr/bin/true')
_BOOT_UNSAFE = 'A boot unit or helper could not be verified as root-controlled.'
_BOOT_FIX = 'Have an administrator inspect the boot unit and its helper.'


@dataclass(frozen=True)
class PreflightLine:
    label: str
    result: str
    fix: str = ''
    blocks: bool = False
    can_override: bool = False


def _reachable(host: str) -> bool:
    try:
        request = urllib.request.Request('https://' + host, method='HEAD')
        with urllib.request.urlopen(request, timeout=3):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def _preflight_space(actions: tuple[str, ...], root: Path) -> list[PreflightLine]:
    combined = 'combined-install' in actions
    lines = []
    for mount, minimum, required in (
        ('/', None, 'Required space unknown.'),
        ('/var', 99 * _MIB + 1 if combined else guard.VAR_REFUSE_MB * _MIB,
         'Upstream requires 100 MiB as reported by df.' if combined else
         'The launcher requires 40 MiB. Additional space required is unknown.'),
        ('/home', 4 * _GIB + 1 if combined else provider.SOURCE_SPACE_MIB * _MIB,
         'Upstream requires 5 GiB as reported by df.' if combined else
         'Source preparation requires 768 MiB. Additional space required is unknown.'),
    ):
        try:
            stats = os.statvfs(root / mount.lstrip('/'))
            free = stats.f_bavail * stats.f_frsize
        except OSError:
            lines.append(PreflightLine(mount, 'Free space unknown.', 'Check free space before continuing.'))
            continue
        # GNU df rounds available whole units up. Match the upstream gates.
        blocks = minimum is not None and free < minimum
        if mount == '/':
            low = free < guard.ROOT_WARN_MB * _MIB
            fix = 'Free system partition space before installing packages.'
        elif mount == '/var':
            low = free < guard.VAR_WARN_MB * _MIB
            fix = 'Use Free /var space in Preparation.'
        else:
            low = False
            fix = 'Free space on /home and try again.'
            if _FULL_KERNEL_FALLBACK.intersection(actions):
                required += ' The full kernel build fallback defaults to 40 GiB.'
                low = free < 40 * _GIB
                if not blocks:
                    fix = 'Free more space if matching headers are unavailable.'
        lines.append(PreflightLine(mount, f'{free // _MIB} MiB free. {required}', fix if blocks or low else '', blocks))
    return lines


def preflight(action: str, *, root: Path = Path('/'), home: Path | None = None,
              kernel: str | None = None, uid: int | None = None) -> tuple[PreflightLine, ...]:
    """Read prerequisites without changing the system or starting the toolkit."""
    provider.action_for(action)
    home = Path.home() if home is None else home
    kernel = platform.release() if kernel is None else kernel
    state_root = root / provider.STATE_ROOT.relative_to('/')
    actions = (action,)
    if action == provider.PUT_BACK:
        losses = _pending_restore(state_root, root, home, kernel, os.getuid() if uid is None else uid)
        actions = provider.toolkit_restore_actions(losses)
        if not actions:
            return (PreflightLine('SteamOS update', 'No recorded Toolkit components need to be restored.', blocks=True),)
    lines = []
    try:
        cached = _cached_revision(state_root) is not None
    except OSError:
        cached = False
    hosts = set()
    if not cached:
        hosts.update(('api.github.com', 'codeload.github.com'))
    for item in actions:
        if item in _DOWNLOAD_HOSTS:
            hosts.add(_DOWNLOAD_HOSTS[item])
        elif item in _OPTIONAL_DOWNLOADS:
            hosts.add('steamdeck-packages.steamos.cloud')
    if hosts:
        unreachable = [host for host in sorted(hosts) if not _reachable(host)]
        result = 'Cannot reach {hosts}.'.format(hosts=', '.join(unreachable)) if unreachable else 'Reachable.'
        lines.append(PreflightLine('Network', result,
                                  'Check your connection and try again if a download fails.' if unreachable else ''))
    lines.extend(_preflight_space(actions, root))
    if _KERNEL_BUILDS.intersection(actions):
        series = provider.kernel_series(kernel)
        unsupported = series is not None and series < (7, 2)
        lines.append(PreflightLine('Kernel', kernel,
                                  'Update SteamOS to a kernel supported by the toolkit (7.2 or newer).'
                                  if unsupported else 'Check upstream kernel support.' if series != (7, 2) else '',
                                  unsupported))
    if _KERNEL_BUILDS.intersection(actions):
        available = (root / 'usr/lib/modules' / kernel / 'build/Makefile').is_file()
        lines.append(PreflightLine('Kernel headers', 'Installed.' if available else
                                  'Not installed. Download availability is unknown.',
                                  '' if available else 'Check that matching headers are available for this SteamOS build.'))
    if 'combined-install' in actions and provider.known_combined_failure(kernel):
        lines.append(PreflightLine('Build tools', provider.COMBINED_GLIBC_REASON,
                                  provider.COMBINED_NATIVE_ROUTE, True, True))
    if 'ac3-install' in actions and 'combined-install' not in actions and not combined_module_active(root, kernel):
        lines.append(PreflightLine('Graphics module', 'The Combined Fix module is missing.',
                                  'Install the Combined Fix and restart first.', True))
    if 'proton-install' in actions:
        try:
            environment = (root / 'etc/environment').read_text(encoding='utf-8')
        except FileNotFoundError:
            environment = ''
        except (OSError, UnicodeError):
            environment = None
        if environment is not None and not ('VK_DRIVER_FILES' in environment and 'bc250-gfx1013' in environment):
            lines.append(PreflightLine('Mesa / RADV', 'The Toolkit RADV configuration is missing.',
                                      'Install Kernel and Mesa · GFX1013 first.', True))
    ownership_lines = [_preflight_ownership(item, root, home, kernel) for item in actions]
    failures = [line for line in ownership_lines if line.fix]
    lines.extend(dict.fromkeys(failures or ownership_lines[:1]))
    for recovery in dict.fromkeys(filter(None, (_recovery_block(item, root) for item in actions))):
        fix = {RECOVERY_UNSAFE: RECOVERY_REMOVE, _BOOT_UNSAFE: _BOOT_FIX}.get(
            recovery, 'Use the built-in SteamOS recovery options.')
        lines.append(PreflightLine('Boot recovery', recovery, fix, True))
    running = guard.session_running(guard.read_session(state_root))
    lines.append(PreflightLine('Toolkit session', 'Running.' if running else 'Idle.',
                              'Wait for the current session to finish.' if running else ''))
    reading = guard.read_root(attempts=1, timeout=3)
    known = reading.state in guard.KNOWN
    lines.append(PreflightLine('SteamOS read-only mode', {'enabled': 'Protected.', 'disabled': 'Writable.'}
                               .get(reading.state, 'Unknown.'),
                               '' if known else 'Check SteamOS read-only status and try again.',
                               reading.state == guard.UNAVAILABLE))
    return tuple(lines)


def _preflight_ownership(action: str, root: Path, home: Path, kernel: str) -> PreflightLine:
    component = provider.guarded_component(action)
    try:
        conflicts = (graphics_conflicts('real-toolkit', root=root, home=home, kernel=kernel,
                                        all_kernels=action == 'combined-revert') if component == 'graphics'
                     else native_conflicts(component, root, home=home) if component else ())
    except (OSError, ValueError):
        return PreflightLine('Ownership', 'Unknown.', 'Check who installed this component.')
    else:
        return PreflightLine('Ownership', ', '.join(conflicts) if conflicts else 'Clear.',
                                  'Remove the component with its original provider and restart first.' if conflicts else '',
                                  bool(conflicts))


def show_preflight(action: str) -> int:
    try:
        lines = preflight(action)
    except (OSError, ValueError):
        print('Toolkit preflight could not read system status. Check file permissions and try again.', file=sys.stderr)
        return 1
    print('SteamOS Real Toolkit preflight', flush=True)
    for line in lines:
        level = 'Blocked' if line.blocks else 'Warning' if line.fix else 'OK'
        print(f'{level} | {line.label} | {line.result}' + (f' {line.fix}' if line.fix else ''), flush=True)
    if any(line.blocks and not line.can_override for line in lines):
        return 1
    if any(line.can_override for line in lines):
        try:
            answer = input('Type "try anyway" to continue: ')
        except EOFError:
            return 1
        return provider.OVERRIDE_STATUS if answer.strip().lower() == 'try anyway' else 1
    return 0


def _recovery_block(action: str, root: Path = Path('/')) -> str:
    if action == 'recovery-install':
        return RECOVERY_REFUSAL
    if action in {'recovery', 'recovery-toggle', 'recovery-timeout'} and unsafe_recovery(root):
        return RECOVERY_UNSAFE
    if action in {'recovery-remove', 'acpi-install', 'acpi-revert', 'combined-install', 'combined-revert'}:
        if unsafe_grub_recovery(root):
            return RECOVERY_UNSAFE
    targets = _BOOT_TARGETS.get({'acpi-revert': 'acpi-install', 'cec': 'cec-install',
                                 'cec-remove': 'cec-install'}.get(action, action), ())
    if action in {'cec', 'cec-setup', 'cec-poweroff-install', 'cec-poweroff-remove'}:
        targets += _CEC_BOOT_TARGETS
    if targets and unsafe_boot_paths(root, targets):
        return _BOOT_UNSAFE
    return ''


_REMOVED_COMPONENTS = {
    'combined-revert': ('amdgpu', 'radv'),
    'acpi-revert': ('acpi',), 'video-revert': ('video',),
    'ac3-revert': ('ac3',), 'dual-revert': ('dual-audio', 'ac3'),
    'aic8800-remove': ('aic8800',), 'be200-remove': ('be200',),
    'dualsense-remove': ('dualsense',), 'xbox-adapter-remove': ('xbox-adapter',), 'cec-remove': ('cec-retrain',),
}


def _installation_evidence(root: Path, home: Path, kernel: str) -> dict:
    return provider.tracked_evidence(provider.component_evidence(root, home, kernel),
                                     provider.graphics_evidence(root, kernel))


def _pending_restore(state_root: Path, root: Path, home: Path, kernel: str, uid: int) -> list[dict[str, str]]:
    return provider.lost_after_update(provider.read_install_record(state_root), provider.build_id(root),
                                      _installation_evidence(root, home, kernel), uid)


def _put_back(user: pwd.struct_passwd, *, override: bool) -> int:
    root, home, kernel = Path('/'), Path(user.pw_dir), platform.release()
    losses = _pending_restore(STATE_ROOT, root, home, kernel, user.pw_uid)
    for action in provider.toolkit_restore_actions(losses):
        if not any(item['action'] == action
                   for item in _pending_restore(STATE_ROOT, root, home, kernel, user.pw_uid)):
            continue
        code = run_action(provider.COMBINED_OVERRIDE if action == 'combined-install' and override else action)
        if code:
            return code
        if any(item['action'] == action
               for item in _pending_restore(STATE_ROOT, root, home, kernel, user.pw_uid)):
            _say('A component is still missing. The remaining Toolkit installs were paused.', error=True)
            return 1
    return 0


def _installed_components(action: str) -> tuple[str, ...]:
    if action == 'aic8800-legacy-install':
        return ('aic8800',)
    return tuple(component for component, install in provider.RESTORE_ACTIONS.items() if install == action)


def _update_install_record(state_root: Path, action: str, build: str, uid: int,
                           before: dict, after: dict) -> None:
    record = provider.read_install_record(state_root)
    updated = record.copy()
    for component in _installed_components(action):
        if build and before.get(component) is False and after.get(component) is True:
            updated[provider.record_scope(component, uid)] = {'build': build, 'action': action}
    removed = _REMOVED_COMPONENTS.get(action, ())
    if action == 'dual-install':
        removed = ('ac3',)
    for component in removed:
        if after.get(component) is False:
            updated.pop(provider.record_scope(component, uid), None)
    if updated == record:
        return
    handle, name = tempfile.mkstemp(prefix='.installed-builds-', dir=state_root)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(updated, output)
        os.chmod(name, 0o644)
        os.replace(name, state_root / provider.INSTALL_RECORD)
    finally:
        Path(name).unlink(missing_ok=True)


def run_action(action: str) -> int:
    """Root entrypoint, invoked only after an explicit terminal action."""
    if action in {provider.PUT_BACK, provider.PUT_BACK_OVERRIDE}:
        return _put_back(_require_invoking_user(), override=action == provider.PUT_BACK_OVERRIDE)
    override = action == provider.COMBINED_OVERRIDE
    action = 'combined-install' if override else action
    provider.action_for(action)
    user = _require_invoking_user()
    if action == 'combined-install' and not override and provider.known_combined_failure(platform.release()):
        raise RuntimeError(provider.COMBINED_GLIBC_REASON + ' ' + provider.COMBINED_NATIVE_ROUTE)
    os.environ['SUDO_USER'] = user.pw_name
    os.environ['AUTO'] = '0'
    prepare_state_root(STATE_ROOT)
    lock_path = STATE_ROOT / '.lock'
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'r+') as lock:
        _wait_for_lock(lock)
        if recovery := _recovery_block(action):
            fix = {RECOVERY_UNSAFE: RECOVERY_REMOVE, _BOOT_UNSAFE: _BOOT_FIX}.get(recovery, '')
            raise RuntimeError(' '.join(filter(None, (recovery, fix))))
        _require_prerequisites(action)
        _preflight_root(action)
        require_source_space(STATE_ROOT)
        track = bool(_installed_components(action) or action in _REMOVED_COMPONENTS)
        if track:
            root, home, kernel = Path('/'), Path(user.pw_dir), platform.release()
            build = provider.build_id(root)
            before = _installation_evidence(root, home, kernel)
        cache_guard_runtime(provider.INSTALLED_RUNTIME_ROOT, STATE_ROOT / 'runtime')
        # The note is written before the download: from here on the interface
        # must know which action holds the toolkit, not only once it runs.
        initial = _begin_root_session(action)
        try:
            revision = _resolve_or_cached()
            archive = STATE_ROOT / (revision + '.tar.gz')
            print('Preparing SteamOS Real Toolkit (' + provider.BRANCH + ' ' + revision[:7] + ')', flush=True)
            download_archive(archive, revision)
            _prune_other_archives(STATE_ROOT, archive.name)
            workspace = STATE_ROOT / 'workspace'
            if _workspace_revision(workspace) != revision:
                # Files an older revision tracked and this one dropped must not linger.
                shutil.rmtree(workspace, ignore_errors=True)
            with tempfile.TemporaryDirectory(prefix='.verify-', dir=STATE_ROOT) as temporary:
                snapshot = provider.prepare_snapshot(archive, Path(temporary) / 'snapshot', revision)
                refresh_workspace(snapshot, workspace)
        except BaseException:
            # An earlier action's pending restore outlives this failed attempt.
            if _root_mode() == initial:
                guard.clear_session(STATE_ROOT)
            clear_cache()
            print('The toolkit source could not be prepared. Its cache was cleared; '
                  'the next attempt downloads the latest version again.', file=sys.stderr, flush=True)
            raise
        # Do not pre-answer menus. The toolkit owns prompts, recovery choices
        # and privileged windows; the terminal remains interactive throughout.
        code = run_preserving_root_mode(['/usr/bin/bash', str(workspace / 'start.sh'),
                                         '--bc250cc-action', action], initial,
                                        on_restored=lambda: guard.clear_session(STATE_ROOT))
        if track and code != provider.CONFLICT_STATUS:
            try:
                _update_install_record(STATE_ROOT, action, build, user.pw_uid, before,
                                       _installation_evidence(root, home, kernel))
            except OSError:
                _say('Could not save the SteamOS build for this installation.', error=True)
        if code == 0:
            if initial == guard.PROTECTED:
                _say('SteamOS read-only protection is on again. A SteamOS system update replaces what was '
                     'installed into the system files; run the action again after updating.')
        elif code == provider.CONFLICT_STATUS:
            # Control Center's own ownership check said no: not an upstream bug,
            # so a fresh 100 MB download would change nothing.
            _say('Control Center stopped the action: another provider, or Control Center itself, manages '
                 'this component (see the message above). The toolkit cache was kept; remove that '
                 'installation with the tool that made it, then try again.')
        elif code < 128:
            # A half-built tree must not survive to the next attempt, but the
            # archive is one commit's, unchanged: a new commit upstream has its
            # own. Interrupts (128 + signal) are the user's choice and keep both.
            clear_workspace()
            _say('The action failed (status ' + str(code) + '). Its build files were cleared; '
                 'trying again starts clean and checks for a newer version first.')
            if (STATE_ROOT / FAILURE_LOGS).is_dir():
                _say("The toolkit's own logs were kept in " + str(STATE_ROOT / FAILURE_LOGS) + '.')
        return code


def _resolve_or_cached() -> str:
    try:
        return resolve_revision()
    except (OSError, ValueError) as error:
        cached = _cached_revision(STATE_ROOT)
        if cached is None:
            raise RuntimeError('Cannot reach the toolkit source and no earlier copy is cached: ' + str(error)) from error
        print('Cannot check for a newer toolkit; using the copy already downloaded.', flush=True)
        return cached
