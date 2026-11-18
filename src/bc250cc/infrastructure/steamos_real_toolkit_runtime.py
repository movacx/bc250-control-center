"""Real Toolkit download, persistent workspace and explicit action launcher."""
from __future__ import annotations

import fcntl
import hashlib
import os
import platform
import pwd
import shutil
import signal
import stat
import subprocess
import tempfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from . import steamos_real_toolkit as provider
from .hardware_identity import require_bc250_hardware
from .steamos_readonly import _state_from

STATE_ROOT = provider.STATE_ROOT
READONLY_COMMAND = '/usr/bin/steamos-readonly'


def _root_mode() -> str:
    try:
        result = subprocess.run([READONLY_COMMAND, 'status'], check=False,
                                capture_output=True, text=True, timeout=3,
                                env={**os.environ, 'LANG': 'C', 'LC_ALL': 'C'})
    except (OSError, subprocess.SubprocessError):
        return 'unknown'
    return _state_from(result.stdout + '\n' + result.stderr) if result.returncode == 0 else 'unknown'


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
        if received is not None:
            return 128 + received
        return 128 - code if code < 0 else code

    try:
        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            previous[number] = signal.signal(number, forward)
        yield execute
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def run_preserving_root_mode(command: list[str]) -> int:
    """Leave privileged windows to upstream, then verify the original mode.

    Do not unlock the root during source downloads or long compilation. On
    completion or a Python exception, repair only a changed/unknown root mode.
    """
    initial = _root_mode()
    if initial not in {'enabled', 'disabled'}:
        raise RuntimeError('Cannot determine SteamOS read-only mode; the toolkit action was not started.')
    with _interactive_signal_relay() as execute:
        code = None
        try:
            code = execute(command)
            return code
        finally:
            if _root_mode() != initial:
                action = 'enable' if initial == 'enabled' else 'disable'
                message = ('Could not restore SteamOS read-only mode to ' + initial
                           + '; toolkit exit status: ' + str(code)
                           + '. Check steamos-readonly status before continuing.')
                try:
                    result = subprocess.run([READONLY_COMMAND, action], check=False, timeout=15)
                except (OSError, subprocess.SubprocessError) as error:
                    raise RuntimeError(message) from error
                if result.returncode != 0 or _root_mode() != initial:
                    raise RuntimeError(message)


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
    if shutil.disk_usage(path).free < 768 * 1024**2:
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


def download_archive(destination: Path) -> None:
    """Cache only bytes matching the reviewed digest; never execute a download."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and not destination.is_symlink():
        with destination.open('rb') as existing:
            if hashlib.file_digest(existing, 'sha256').hexdigest() == provider.ARCHIVE_SHA256:
                return
    handle, name = tempfile.mkstemp(prefix='.download-', dir=destination.parent)
    temporary = Path(name)
    try:
        digest, count = hashlib.sha256(), 0
        with os.fdopen(handle, 'wb') as output, urllib.request.urlopen(provider.ARCHIVE_URL, timeout=45) as response:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > 512 * 1024**2:
                    raise ValueError('Real Toolkit download exceeds its size limit')
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != provider.ARCHIVE_SHA256:
            raise ValueError('Real Toolkit download did not match the reviewed SHA-256')
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


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


def run_action(action: str) -> int:
    """Root entrypoint, invoked only after an explicit terminal action."""
    provider.action_for(action)
    user = _require_invoking_user()
    os.environ['SUDO_USER'] = user.pw_name
    os.environ['AUTO'] = '0'
    prepare_state_root(STATE_ROOT)
    lock_path = STATE_ROOT / '.lock'
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'r+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another Real Toolkit action is still running') from error
        require_source_space(STATE_ROOT)
        cache_guard_runtime(provider.INSTALLED_RUNTIME_ROOT, STATE_ROOT / 'runtime')
        archive = STATE_ROOT / (provider.REVISION + '.tar.gz')
        print('Preparing SteamOS Real Toolkit ' + provider.VERSION, flush=True)
        download_archive(archive)
        with tempfile.TemporaryDirectory(prefix='.verify-', dir=STATE_ROOT) as temporary:
            snapshot = provider.prepare_snapshot(archive, Path(temporary) / 'snapshot')
            workspace = STATE_ROOT / 'workspace'
            refresh_workspace(snapshot, workspace)
        # Do not pre-answer menus. The toolkit owns prompts, recovery choices
        # and privileged windows; the terminal remains interactive throughout.
        return run_preserving_root_mode(['/usr/bin/bash', str(workspace / 'start.sh'),
                                         '--bc250cc-action', action])
