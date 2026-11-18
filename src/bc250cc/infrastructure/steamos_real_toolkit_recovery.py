"""Recovery adaptations applied only after the full upstream source is attested."""
from __future__ import annotations

import re
import shlex

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

    The caller invokes this only after attesting the full upstream source.
    Explicit propagation is necessary even with errexit: this function is
    called from conditionals that disable Bash's implicit error handling.
    """
    matches = list(re.finditer(r'^run_revert_all\(\) \{\n.*?^\}\n', text, re.MULTILINE | re.DOTALL))
    if len(matches) != 1:
        raise ValueError('Real Toolkit bulk revert function contract changed')
    match = matches[0]
    body = match.group()
    for step in REVERT_ALL_STEPS:
        original = '    ' + step + '\n'
        if body.count(original) != 1:
            raise ValueError('Real Toolkit bulk revert step contract changed: ' + step)
        body = body.replace(original, '    ' + step + ' || return $?\n', 1)
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
    bc250cc_root_state=$(LC_ALL=C steamos-readonly status 2>/dev/null) || {
        echo "Cannot verify writable root; recovery was stopped." >&2
        return 1
    }
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
