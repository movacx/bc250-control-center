"""Recovery adaptations applied to the downloaded upstream source."""
from __future__ import annotations

import re
import shlex
import stat
from collections import deque
from pathlib import Path

RECOVERY_UNIT = 'bc250-recovery-revert.service'
RECOVERY_GRUB = 'etc/grub.d/42_bc250-recovery'
RECOVERY_REFUSAL = 'Toolkit recovery installs a boot script that the desktop user can change. Installation and repair are blocked.'
RECOVERY_UNSAFE = 'An unsafe Toolkit recovery entry is installed.'
RECOVERY_REMOVE = (
    'Have an administrator disable bc250-recovery-revert.service, remove its unit and '
    '/etc/grub.d/42_bc250-recovery, then regenerate GRUB.'
)


def _protected_path(path: Path, root: Path, trusted_uid: int, *, allow_missing: bool = False) -> bool:
    """Follow links one at a time so a writable intermediate path is caught."""
    try:
        info = root.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != trusted_uid or info.st_mode & 0o022:
            return False
        remaining: deque[str | None] = deque(path.relative_to(root).parts)
        current = root
        links = 0
        resolving_link = 0
        while remaining:
            part = remaining.popleft()
            if part is None:
                resolving_link -= 1
                continue
            if part == '..':
                if current == root:
                    return False
                current = current.parent
                continue
            name = current / part
            try:
                info = name.lstat()
            except FileNotFoundError:
                return allow_missing and not resolving_link
            if info.st_uid != trusted_uid:
                return False
            if stat.S_ISLNK(info.st_mode):
                links += 1
                if links > 40:
                    return False
                target = name.readlink()
                if target.is_absolute():
                    target = target.relative_to(root)
                    current = root
                remaining.appendleft(None)
                remaining.extendleft(reversed(target.parts))
                resolving_link += 1
            elif info.st_mode & 0o022 or any(item is not None for item in remaining) and not stat.S_ISDIR(info.st_mode):
                return False
            else:
                current = name
        return stat.S_ISREG(current.lstat().st_mode)
    except (OSError, ValueError):
        return False


def unsafe_grub_recovery(root: Path = Path('/'), *, trusted_uid: int = 0) -> bool:
    path = root / RECOVERY_GRUB
    return (path.exists() or path.is_symlink()) and not _protected_path(path, root, trusted_uid)


def unsafe_boot_paths(root: Path, paths: tuple[str, ...], *, trusted_uid: int = 0) -> bool:
    """An installer may create a missing target under protected directories."""
    for relative in paths:
        path = root / relative
        if not _protected_path(path, root, trusted_uid, allow_missing=True):
            return True
        if not relative.endswith('.service') or not path.is_file():
            continue
        try:
            with path.open(encoding='utf-8') as unit:
                contents = unit.read(65537)
            commands = re.findall(r'^\s*Exec[A-Za-z]+\s*=\s*([^\s]+)', contents, re.MULTILINE)
            if len(contents) > 65536 or any(command.strip('"\'') not in {'/' + item for item in paths}
                                             for command in commands):
                return True
            if any(path.with_name(path.name + '.d').glob('*.conf')):
                return True
        except (OSError, UnicodeError):
            return True
    return False


def unsafe_recovery(root: Path = Path('/'), *, trusted_uid: int = 0) -> tuple[str, ...]:
    """Find existing recovery paths that cannot be trusted to run as root."""
    unsafe = [str(root / RECOVERY_GRUB)] if unsafe_grub_recovery(root, trusted_uid=trusted_uid) else []
    for directory in ('etc/systemd/system', 'run/systemd/system', 'usr/lib/systemd/system'):
        base = root / directory
        dropins = base / (RECOVERY_UNIT + '.d')
        for dropin in sorted(dropins.glob('*.conf')):
            # A drop-in can substitute executable commands for the ones below.
            unsafe.append(str(dropin))
        for unit in (base / RECOVERY_UNIT, base / 'multi-user.target.wants' / RECOVERY_UNIT):
            if not (unit.exists() or unit.is_symlink()):
                continue
            if not _protected_path(unit, root, trusted_uid):
                unsafe.append(str(unit))
                continue
            try:
                commands = [shlex.split(value) for key, _, value in
                            (line.strip().partition('=') for line in unit.read_text().splitlines())
                            if key.strip().startswith('Exec')]
                if (len(commands) != 1 or len(commands[0]) != 2 or commands[0][1] != 'revert'
                        or not commands[0][0].startswith('/') or '..' in Path(commands[0][0]).parts):
                    unsafe.append(str(unit))
                    continue
                target = root / commands[0][0].lstrip('/')
                if not _protected_path(target, root, trusted_uid):
                    unsafe.append(str(target))
            except (OSError, UnicodeError, ValueError):
                unsafe.append(str(unit))
    return tuple(dict.fromkeys(unsafe))


def refuse_unsafe_install(text: str) -> str:
    pattern = r'^install_recovery_entries\(\)(\s*\{)'
    text, count = re.subn(pattern, lambda match: 'install_recovery_entries()' + match[1]
                         + '\n    printf "%s\\n" ' + shlex.quote(RECOVERY_REFUSAL) + ' >&2\n'
                         + '    return 1\n', text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError('Real Toolkit recovery install contract changed')
    return text

REVERT_ALL_STEPS = (
    'run_revert_cpu_governor', 'run_revert_gpu_governor',
    'run_revert_mitigations auto', 'run_revert_swap auto',
    'run_revert_zram_zswap auto', 'run_revert_acpi_fix',
    'run_revert_ac3_surround', 'run_revert_vaapi_driver',
    'run_revert_dual_audio', 'run_revert_ds5_bridge_fix',
    'run_revert_ds5_chord_vdf', 'run_revert_core_unlock',
    'run_revert_ram_split', 'run_revert_gfx1013_fix',
    'run_revert_aic8800_wifi', 'uninstall_recovery_entries',
)

REVERT_FLAG_BODY = '    run_revert_all || true\n    exit 0\n'
CTL_PRELUDE = '''    echo "bc250.revert_all=1 detected — reverting toolkit installation"
    unlock

    local state_dir toolkit=""
    state_dir=$(dirname "$(readlink -f "$0")")
'''
CTL_HANDOFF = '        AUTO=1 bash "$toolkit" --revert-all || echo "toolkit revert-all exited non-zero — continuing cleanup"\n'


def adapt_revert_all(text: str) -> str:
    """Do not erase recovery state or report success after a component fails.

    The caller has already checked the entrypoint structurally.
    Explicit propagation is necessary even with errexit: this function is
    called from conditionals that disable Bash's implicit error handling.
    """
    matches = list(re.finditer(r'^run_revert_all\(\) \{\n.*?^\}\n', text, re.MULTILINE | re.DOTALL))
    if len(matches) != 1:
        raise ValueError('Real Toolkit bulk revert function contract changed')
    match = matches[0]
    body = match.group()
    # Upstream adds and drops revert steps between releases, so no fixed list:
    # every revert/uninstall step present gains error propagation. A body with
    # none is a shape this adapter does not understand, and is refused.
    body, steps = re.subn(r'^(    (?:run_revert_|uninstall_|revert_)\w+(?: [\w-]+)*)\n',
                          r'\1 || return $?\n', body, flags=re.MULTILINE)
    if not steps:
        raise ValueError('Real Toolkit bulk revert step contract changed')
    return text[:match.start()] + body + text[match.end():]


def adapt_recovery_flag(text: str) -> str:
    if text.count(REVERT_FLAG_BODY) != 1:
        raise ValueError('Real Toolkit recovery exit-status contract changed')
    return text.replace(REVERT_FLAG_BODY,
                        '    bc250cc_revert_rc=0\n'
                        '    run_revert_all || bc250cc_revert_rc=$?\n'
                        '    exit "$bc250cc_revert_rc"\n', 1)


def adapt_recovery_ctl(text: str, checker_command: tuple[str, ...]) -> str:
    """Check before opening root writes; stop before cleanup/reboot on failure."""
    if text.count(CTL_PRELUDE) != 1 or text.count(CTL_HANDOFF) != 1:
        raise ValueError('Real Toolkit generated recovery helper contract changed')
    prelude = '''    local state_dir toolkit="" bc250cc_owner=""
    state_dir=$(dirname "$(readlink -f "$0")")
    bc250cc_owner=$(stat -c %u "$state_dir" 2>/dev/null || true)
    if [[ "$bc250cc_owner" =~ ^[0-9]+$ ]] && (( bc250cc_owner > 0 )); then
        export SUDO_UID="$bc250cc_owner"
    fi
    ''' + shlex.join(checker_command) + ''' all || return $?
    echo "bc250.revert_all=1 detected — reverting toolkit installation"
    unlock
    local bc250cc_root_state=""
    # status exits 1 while the root is writable: read what it says, not its status.
    bc250cc_root_state=$(LC_ALL=C steamos-readonly status 2>/dev/null || true)
    if [[ -z "$bc250cc_root_state" ]]; then
        echo "Cannot verify writable root; recovery was stopped." >&2
        return 1
    fi
    if [[ ! "$bc250cc_root_state" =~ (^|[^[:alpha:]])disabled([^[:alpha:]]|$) ]]; then
        echo "Root is not confirmed writable; recovery was stopped." >&2
        return 1
    fi
'''
    handoff = '''        local bc250cc_revert_rc=0
        AUTO=1 bash "$toolkit" --revert-all || bc250cc_revert_rc=$?
        if (( bc250cc_revert_rc != 0 )); then
            echo "Toolkit recovery failed or was refused; cleanup and reboot were stopped." >&2
            return "$bc250cc_revert_rc"
        fi
'''
    return text.replace(CTL_PRELUDE, prelude, 1).replace(CTL_HANDOFF, handoff, 1)
