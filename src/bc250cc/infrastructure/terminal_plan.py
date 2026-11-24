"""Pure shell wrapper and graphical-terminal candidate planning.

The failure explanation is built here, in Python, and injected into the
generated script as literal text. It used to be a ``case`` statement written
inside the shell fragment, which meant the wording could never reach ``tr()``
and so existed in English only, outside all 30 locales. It also explained just
13 statuses, while the privileged helpers exit with 20-57 — every other status
printed a bare number, which is where "code 43" came from.

The helpers' numbers were then read for every workflow, and that was wrong the
other way: a workflow's status is the status of whatever ran last under
``set -e``. ``make`` exits 2, ``curl --fail`` 22, ``systemctl status`` 3 for a
unit in auto-restart, and those numbers meant "helper version mismatch", "Cyan
D-Bus" and "helper version mismatch" in the catalog (R-bb33f44b, R-530bd5f6,
R-53376560). So the wrapper now reads only the words: the catalog's text
markers, the script's own ``[ERROR]`` lines, and two statuses the shell itself
defines (127, command not found; 124, ``timeout``). Everything else is the
neutral code, with the raw status still shown by the console.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from bc250cc.shared import error_catalog
from bc250cc.shared.operation_contract import (
    POLKIT_DISMISSED_PATTERN,
    OperationExit,
)

from .terminal_transcript import LOG_SYNC_OSC, log_sync_path

# Executed with python3 by the terminal-emulator wrapper; see run_logged.
_TRANSCRIPT_RUNNER = Path(__file__).resolve().with_name("terminal_transcript.py")

_CODES_WITH_MARKERS = tuple(
    entry for entry in error_catalog.all_codes()
    if entry.markers and entry.code != "BC250-PROTOCOL-001"
)


# A plain ASCII rule so it renders identically in every terminal emulator,
# including minimal consoles without box-drawing glyphs.
_RULE = "=" * 74

_LOG_SYNC_WAIT_TICKS = 50  # of 0.1 s: only a console that is not reading waits this long


# Used when the workflow printed its own [ERROR] explanation: the failure is
# real and described, but no catalog rule was consulted, so claiming a
# specific rule id would be a lie.
_WORKFLOW_REPORTED_CODE = "BC250-WORKFLOW-001"

CANCELLED_EXIT = int(OperationExit.CANCELLED)

#: Printed instead of a diagnosis when the user declined at a prompt.
CANCELLED_MESSAGE = "Cancelled: you answered no. Steps before this question may already have changed the system."

#: The last thing a package tool leaves on screen after a "no": the answered
#: prompt itself, or what apt and dnf print after it.
_REFUSED = r"\[(Y/n|y/N)\]:?[[:space:]]+no?[[:space:]]*$|^Operation aborted( by the user)?[.]?$|^Abort[.]$"

# Scope the locale to package tools, including calls that go through sudo.
PACKAGE_LOCALE_SHELL = r"""
bc250_package_tools='apt apt-get apt-cache dpkg pacman pacman-conf dnf dnf4 dnf5 rpm rpm-ostree zypper apk emerge'
for bc250_tool in $bc250_package_tools; do
    type -P "$bc250_tool" >/dev/null || continue
    eval "$bc250_tool() { LC_ALL=C.UTF-8 LANGUAGE=C command $bc250_tool \"\$@\"; }"
    export -f "$bc250_tool"
done
sudo() {
    case " $bc250_package_tools " in
        *" ${1:-} "*) LC_ALL=C.UTF-8 LANGUAGE=C command sudo "$@" ;;
        *) command sudo "$@" ;;
    esac
}
export bc250_package_tools
if type -P sudo >/dev/null; then export -f sudo; else unset -f sudo; fi
"""

# Exit statuses defined by bash and coreutils themselves, so they mean the
# same thing whatever ran. Every other number belongs to the program that
# exited with it, and a workflow runs many programs.
_SHELL_DEFINED_STATUSES = ((124, "BC250-TIMEOUT-001"), (127, "BC250-CMD-001"))


def _identity(value: object) -> str:
    return str(value)


# The desktop frontend installs ``tr`` here at startup so the generated script
# speaks the user's language. ``src`` must not import from ``frontends``, so
# the translator is injected rather than imported; without it the wording
# stays English and nothing breaks.
_TRANSLATOR = _identity


def set_translator(translate=None) -> None:
    """Install the translator used for generated terminal text."""
    global _TRANSLATOR
    _TRANSLATOR = translate if callable(translate) else _identity


def exit_explanation_shell(translate=None) -> str:
    """Shell fragment explaining a failing status, with a traceable code.

    Nothing is printed when the workflow succeeded: a success is not a
    diagnosis, and printing "exit code 0" only made a good outcome look like a
    fault.
    """
    translate = translate if callable(translate) else _TRANSLATOR
    heading_happened = translate("What happened")
    heading_cause = translate("Likely cause")
    heading_action = translate("How to fix it")
    label_code = translate("Diagnostic code")
    # A signal is not a workflow fault with its own fix, so it reuses the
    # generic diagnosis rather than adding three more translatable sentences.
    signal_reason = translate(error_catalog.GENERAL_FAILURE.summary)
    signal_cause = translate(error_catalog.GENERAL_FAILURE.cause)
    signal_action = translate(error_catalog.GENERAL_FAILURE.action)

    # The only statuses with one meaning for every program: the shell's own
    # 127 (command not found) and coreutils' 124 (timeout). A helper's number
    # is read by the helper's caller (failure_text.describe_failure), never here.
    branches = []
    for status, code in _SHELL_DEFINED_STATUSES:
        entry = error_catalog.BY_CODE[code]
        branches.append(
            f'{status}) summary={shlex.quote(translate(entry.summary))}; '
            f'cause={shlex.quote(translate(entry.cause))}; '
            f'action={shlex.quote(translate(entry.action))}; '
            f'diagnostic={shlex.quote(entry.code)};; '
        )

    fallback = error_catalog.GENERAL_FAILURE
    generic = (
        f'summary={shlex.quote(translate(fallback.summary))}; '
        f'cause={shlex.quote(translate(fallback.cause))}; '
        f'action={shlex.quote(translate(fallback.action))}; '
        f'diagnostic={shlex.quote(fallback.code)}; '
    )
    signal = (
        f'summary={shlex.quote(signal_reason)}; '
        f'cause={shlex.quote(signal_cause)}; '
        f'action={shlex.quote(signal_action)}; '
        f'diagnostic={shlex.quote(fallback.code)}; '
    )

    # A generic status such as 1 says nothing; the tool's own wording often
    # does. Text rules are checked first so pacman's 404 is not reported as
    # "no specific rule matched".
    text_rules = []
    for entry in _CODES_WITH_MARKERS:
        patterns = "|".join(
            marker.replace("\\", "\\\\").replace("|", "\\|") for marker in entry.markers
        )
        required = (
            f' && printf "%s" "$target" | grep -qiF {shlex.quote(entry.requires)}' if entry.requires else ""
        )
        text_rules.append(
            f'if printf "%s" "$target" | grep -qiE {shlex.quote(patterns)}{required}; then '
            f'summary={shlex.quote(translate(entry.summary))}; '
            f'cause={shlex.quote(translate(entry.cause))}; '
            f'action={shlex.quote(translate(entry.action))}; '
            f'diagnostic={shlex.quote(entry.code)}; matched=1; fi; '
        )

    workflow = error_catalog.BY_CODE[_WORKFLOW_REPORTED_CODE]
    workflow_action = shlex.quote(translate(workflow.action))
    return (
        # 130: the user declined or interrupted; no diagnosis (see workflow_wrapper).
        'if [ "$status" -ne 0 ] && [ "$status" -ne 130 ]; then '
        'matched=0; '
        # When the script explained itself, its own [ERROR] lines are what a
        # rule is matched against: the tail of the log can hold an earlier,
        # unrelated step. Rules run in catalog order and a later match wins.
        'target=$evidence; '
        'if [ -n "$first_error" ]; then '
        'target=$(printf "%s\\n%s" "$first_error" "$error_hints"); fi; '
        'target=$(printf "%s\\n%s" "$target" "${root_cause:-}"); '
        + "".join(text_rules)
        + 'if [ "$matched" -eq 0 ]; then '
        'case "$status" in '
        + "".join(branches)
        + '*) if [ "$status" -gt 128 ] && [ "$status" -le 255 ]; then '
        + signal
        + 'else '
        + generic
        + 'fi;; '
        'esac; '
        'fi; '
        # The workflow's own words win. Our scripts print the exact kernel,
        # package or path involved; a rule matched from an exit status cannot,
        # and printing both invites the two to contradict each other.
        'if [ -n "$first_error" ]; then summary=$first_error; '
        # A rule matched from the exit status would misattribute a failure the
        # workflow already explained: scripts reuse numbers that mean
        # something else for a helper (22 is a Cyan D-Bus fault there), which
        # once called a fan driver failure "Cyan is stopped". Only a rule
        # matched from the script's own words keeps its code and cause.
        'if [ "$matched" -eq 0 ]; then '
        f'diagnostic={_WORKFLOW_REPORTED_CODE}; cause=""; action={workflow_action}; fi; fi; '
        'if [ -n "$error_hints" ]; then '
        'if [ "$matched" -eq 0 ]; then cause=""; fi; action=$error_hints; fi; '
        # A leftover pacman lock: the catalog's advice (wait, never delete it)
        # contradicts the one thing that helps, so it gives way to it.
        'if [ "${bc250_stale:-0}" = 1 ]; then '
        f'cause={shlex.quote(translate(STALE_PACMAN_LOCK_MESSAGE))}; error_hints=""; '
        f'action={shlex.quote(translate(STALE_PACMAN_LOCK_FIX) + chr(10) + "  sudo rm /var/lib/pacman/db.lck")}; fi; '
        # Framed block: in a long scrolling log the diagnosis has to be
        # findable at a glance, not another indistinguishable line of output.
        f'echo; echo "{_RULE}"; '
        f'echo "{heading_happened}: $summary"; '
        f'if [ -n "$cause" ]; then echo "{heading_cause}: $cause"; fi; '
        f'if [ -n "$error_hints" ]; then echo "{heading_action}:"; '
        'printf "%s\\n" "$action"; '
        f'else echo "{heading_action}: $action"; fi; '
        f'echo "{label_code}: $diagnostic"; '
        f'echo "{_RULE}"; '
        'fi'
    )


#: Lines that name the cause exactly, however many lines other jobs of a
#: parallel build print after them (R-6d239d09: 75 lines; R-12c6bac6: 450).
ROOT_CAUSE_LINES = (
    "version .(GLIBC|GLIBCXX|CXXABI)_[0-9.]+. not found .required by"
    "|unable to find library -lgcc_s|cannot find -lgcc_s"
)
ROOT_CAUSE_SCAN_LINES = 4000

#: How far back the workflow's own [ERROR] lines are looked for.
ERROR_SCAN_LINES = 120


def _evidence_capture_shell(log_path: object) -> str:
    """Shell fragment that captures the tail of the workflow log as evidence.

    Captured before the explanation block starts appending to the same log,
    so it reflects only the command's own output, not the summary text.
    """
    log = shlex.quote(str(log_path))
    # The script's own [ERROR] lines are looked for further back than the tail
    # that is shown: a script may print diagnostics after its error (the
    # SteamOS fan script prints modules, hwmon and dmesg), and with only the
    # last 12 lines the error fell out, the exit status 22 took over, and a fan
    # driver failure was reported as a Cyan D-Bus fault.
    return (
        f"evidence=$(tail -n 12 {log} 2>/dev/null); "
        f"error_scan=$(tail -n {ERROR_SCAN_LINES} {log} 2>/dev/null); "
        f"root_cause=$(tail -n {ROOT_CAUSE_SCAN_LINES} {log} 2>/dev/null "
        f"| grep -aE {shlex.quote(ROOT_CAUSE_LINES)} | head -n 2 || true)"
    )


def _first_error_shell(translate=None) -> str:
    """Capture the workflow's own error lines.

    Our scripts already print `[ERROR] what happened` followed by `[ERROR] how
    to fix it`. When they do, that is the authoritative explanation: it names
    the exact kernel, package or path involved. Guessing a rule from the exit
    status instead once answered a "headers do not match" failure with "the
    requested value is outside the supported range", which contradicted the
    script the user had just read.
    """
    translate = translate if callable(translate) else _TRANSLATOR
    return (
        "bc250_error_re='^[[:space:]]*(\\\\[(ERROR|FATAL)\\\\][: ]*|ERROR: )'; "
        'if [ "$status" -ne 0 ] && [ -n "$error_scan" ]; then '
        # The last run of ERROR/FATAL lines is the failure that stopped the
        # workflow; an earlier one may have been recovered from (the AUR build
        # failing before the official Cyan release is installed instead).
        # The ERR trap of common.sh closes every failed script with
        # "Operation failed at line N with exit code X". It says nothing the
        # exit status did not, and as the last [ERROR] line it used to replace
        # the script's own explanation, so no rule matched it.
        'error_block=$(printf "%s\\n" "$error_scan" | awk -v re="$bc250_error_re" '
        '-v generic="Operation failed at line [0-9]+ with exit code" '
        "'{ if ($0 ~ generic) next; if ($0 ~ re) { if (!run) n = 0; run = 1; sub(re, \"\"); lines[++n] = $0 } else run = 0 } "
        "END { for (i = 1; i <= n; i++) print lines[i] }' || true); "
        # Its first line: what happened.
        'first_error=$(printf "%s\\n" "$error_block" | head -n 1); '
        'if [ "$status" -eq 100 ] && [ -z "$first_error" ]; then '
        'first_error=$(printf "%s\\n" "$error_scan" | grep -E "^dpkg: error processing package " | tail -1); fi; '
        # The rest: the script's own remediation steps.
        'error_hints=$(printf "%s\\n" "$error_block" | tail -n +2 | sed "s/^/  /"); '
        'fi'
    )


def _evidence_render_shell(translate=None) -> str:
    """Shell fragment that prints the captured evidence tail on failure."""
    translate = translate if callable(translate) else _TRANSLATOR
    heading = translate("Last lines from the workflow output:")
    return (
        f'if [ "$status" -ne 0 ] && [ "$status" -ne {CANCELLED_EXIT} ] && [ -n "$evidence" ]; then '
        f'printf "\\n%s\\n" "{heading}"; '
        'if [ -n "${root_cause:-}" ]; then printf "%s\\n" "$root_cause" | sed "s/^/  /"; echo "  ..."; fi; '
        'printf "%s\\n" "$evidence" | sed "s/^/  /"; '
        'fi'
    )


#: A lock pacman left behind when an update was interrupted (power cut, closed
#: terminal). It blocks every later transaction with "unable to lock
#: database", and the catalog's advice to wait never ends (R-1bf75324 kept
#: failing a day later; R-d8d8dc3d).
STALE_PACMAN_LOCK_MESSAGE = (
    "No package manager is running, so /var/lib/pacman/db.lck was left behind by an update that was interrupted."
)
STALE_PACMAN_LOCK_FIX = "Remove it, then run the action again:"


def _stale_pacman_lock_check_shell() -> str:
    """On a pacman lock failure, set ``bc250_stale`` when the lock is a leftover.

    The same rule as ``pacman_lock.lock_state``: pacman itself must not be
    running, and either no front-end runs either or the lock is older than
    this boot. An idle PackageKit (Discover keeps ``packagekitd`` alive on
    KDE) holds nothing, yet it hid the hint from a user whose lock outlived a
    reboot and blocked them twice (R-40f0868d, R-1c81b064). Nothing is removed
    here; it is a root file.
    """
    from bc250cc.infrastructure.pacman_lock import PACKAGE_MANAGERS

    # The libalpm front-ends: running, they may hold the lock without a pacman
    # process, so only a lock older than this boot is called a leftover then.
    front_ends = "|".join(name for name in PACKAGE_MANAGERS if name != "pacman")
    return (
        'bc250_stale=0; bc250_lock="${BC250_PACMAN_LOCK:-/var/lib/pacman/db.lck}"; '
        'if [ "$status" -ne 0 ] && [ "$status" -ne 130 ] && [ -e "$bc250_lock" ] '
        '&& command -v pgrep >/dev/null 2>&1 '
        '&& printf "%s\\n" "$evidence" | grep -qiE "unable to lock database|could not lock database" '
        '&& ! pgrep -x pacman >/dev/null 2>&1; then '
        'bc250_btime="$(awk \'/^btime /{print $2}\' "${BC250_PROC_STAT:-/proc/stat}" 2>/dev/null)"; '
        'bc250_mtime="$(stat -c %Y "$bc250_lock" 2>/dev/null)"; '
        f'if ! pgrep -x "{front_ends}" >/dev/null 2>&1 '
        '|| { [ -n "$bc250_btime" ] && [ -n "$bc250_mtime" ] && [ "$bc250_mtime" -lt "$bc250_btime" ]; }; then '
        'bc250_stale=1; '
        'fi; '
        'fi'
    )


def _stale_pacman_lock_shell(translate=None) -> str:
    """The check, then the sentence and the command on their own."""
    translate = translate if callable(translate) else _TRANSLATOR
    message = shlex.quote(translate(STALE_PACMAN_LOCK_MESSAGE))
    fix = shlex.quote(translate(STALE_PACMAN_LOCK_FIX))
    return (
        _stale_pacman_lock_check_shell()
        + '; if [ "$bc250_stale" = 1 ]; then '
        + f'printf "\\n%s\\n%s\\n  sudo rm /var/lib/pacman/db.lck\\n" {message} {fix}; fi'
    )


def workflow_wrapper(
    command: object,
    status_path: Path,
    log_path: Path,
    translate=None,
    *,
    hold: bool = True,
    host_logs: bool = False,
    inherit_tty: bool = False,
) -> str:
    """Wrap a workflow so it logs, records its exit status, and reports it.

    ``hold`` keeps the closing "Enter to close" prompt. A terminal emulator
    launched for one command disappears the instant the command ends, taking
    the result with it, so the prompt is what makes the output readable there.
    The embedded console does not close on its own, so it passes ``hold=False``
    and leaves the panel showing the same summary without a key press.

    ``host_logs`` is for the embedded console, which writes the log from the
    pty itself. The workflow then runs with the terminal as its stdout instead
    of a ``tee`` pipe: behind a pipe git hides its progress, APT and cargo
    drop their progress bars and make buffers its output, so a long build sat
    on one frozen line. Before the log is read back the wrapper waits for the
    console to confirm it has written everything printed so far.

    Without it (a terminal emulator) the same holds: the workflow runs under
    ``terminal_transcript.py``, which gives it a pty and writes the log. Only
    if that runner cannot start does the wrapper fall back to ``tee``.
    """
    translate = translate if callable(translate) else _TRANSLATOR
    requested = str(command or "").strip()
    if not requested:
        raise RuntimeError("The requested terminal workflow is empty.")
    inner = shlex.quote(requested)
    status = shlex.quote(str(status_path))
    log = shlex.quote(str(log_path))
    pipeline = shlex.quote(f"bash -lc {inner} 2>&1 | tee {log}")
    finished_ok = translate("Completed")
    finished_failed = translate("The workflow did not finish successfully.")
    saved_log = translate("Full log saved to")
    share_hint = translate("You can share that .log file if something failed.")
    close_hint = translate("Enter to close...")
    closing = f'read -r -p "{close_hint}" _; ' if hold else ""
    if host_logs:
        sync = shlex.quote(str(log_sync_path(log_path)))
        run = f"bash -lc {inner}; status=$?; "
        # Wait for the console to have logged everything printed so far.
        wait_for_log = (
            f"rm -f {sync}; printf '\\033]{LOG_SYNC_OSC}\\007'; "
            f"_bc250_tick=0; while [ ! -e {sync} ] && [ $_bc250_tick -lt {_LOG_SYNC_WAIT_TICKS} ]; "
            "do sleep 0.1; _bc250_tick=$((_bc250_tick + 1)); done; "
            f"rm -f {sync}; "
        )
        summary_sink = ""
    elif inherit_tty:
        # Web actions share their session's controlling tty (and sudo's tty
        # timestamp). Record stdout without creating a second authentication
        # terminal. Sudo reads the password from /dev/tty, outside this log.
        run = f"bash -o pipefail -c {pipeline}; status=$?; "
        wait_for_log = ""
        summary_sink = f"2>&1 | tee -a {log}"
    else:
        runner = shlex.quote(str(_TRANSCRIPT_RUNNER))
        # Chosen before anything runs, so the workflow can never run twice.
        run = (
            f"if command -v python3 >/dev/null 2>&1 && [ -r {runner} ]; then "
            f"python3 {runner} {log} -- bash -lc {inner}; "
            f"else bash -o pipefail -c {pipeline}; fi; status=$?; "
        )
        wait_for_log = ""
        summary_sink = f"2>&1 | tee -a {log}"
    return (
        # Diagnosis reads the tools' own words, and a sudo or pacman speaking
        # Polish or French matched no rule (R-e1eaa882, R-8db5f5cd).
        f"{PACKAGE_LOCALE_SHELL}\nexport LANGUAGE=en; bc250_start=$SECONDS; "
        f"{run}"
        'bc250_raw_status=$status; bc250_elapsed=$((SECONDS - bc250_start)); '
        f"{wait_for_log}"
        f"{_evidence_capture_shell(log_path)}; "
        # Match the final evidence for the refusal, even after a generic ERR trap.
        'bc250_last=$(printf "%s\\n" "$error_scan" | tr "\\r" "\\n" '
        '| LC_ALL=C sed -E $\'s/\\033\\\\[[0-?]*[ -/]*[@-~]//g\' '
        '| awk \'NF && $0 !~ /^\\[ERROR\\] Operation failed at line [0-9]+ with exit code [0-9]+[.]?$/ {l=$0} END{print l}\'); '
        'if [ "$status" -eq 1 ] && printf "%s\\n" "$bc250_last" '
        f'| grep -qiE {shlex.quote(_REFUSED)}; then '
        f'status={CANCELLED_EXIT}; '
        'elif [ "$status" -eq 126 ] && printf "%s\\n" "$bc250_last" '
        f'| grep -qiE {shlex.quote(POLKIT_DISMISSED_PATTERN)}; then '
        f'status={CANCELLED_EXIT}; fi; '
        f"printf '%s\\n' \"$status\" > {status}; "
        "{ echo; "
        # A successful run reports success, not a number. Only a failure needs
        # a diagnosis, and the raw status stays in the technical detail below.
        f"if [ \"$status\" -eq 0 ]; then echo \"{finished_ok}\"; "
        f"elif [ \"$status\" -eq {CANCELLED_EXIT} ]; then printf '%s\\n' {shlex.quote(translate(CANCELLED_MESSAGE))}; "
        f"else echo \"{finished_failed}\"; fi; "
        f"{_first_error_shell(translate)}; "
        f"{_stale_pacman_lock_check_shell()}; "
        f"{exit_explanation_shell(translate)}; "
        f"{_evidence_render_shell(translate)}; "
        'printf "BC250_WORKFLOW exit_status=%d duration_seconds=%d\\n" "$bc250_raw_status" "$bc250_elapsed"; '
        f"echo \"{saved_log}: {log_path!s}\"; "
        f'if [ "$status" -ne {CANCELLED_EXIT} ]; then echo "{share_hint}"; fi; }} '
        f"{summary_sink}; "
        f"{closing}exit \"$status\""
    )


def _environment_candidates(terminal_env: str, title: str, wrapped: str) -> list[list[str]]:
    try:
        parts = shlex.split(str(terminal_env or "").strip())
    except ValueError:
        return []
    if not parts:
        return []
    name = Path(parts[0]).name
    if name in {"ptyxis", "kgx", "gnome-console", "gnome-terminal"}:
        return [parts + ["--", "bash", "-lc", wrapped]]
    if name == "konsole":
        return [parts + ["--new-tab", "-p", f"tabtitle={title}", "-e", "bash", "-lc", wrapped]]
    if name == "kitty":
        return [parts + ["--title", title, "bash", "-lc", wrapped]]
    if name in {"alacritty", "rio"}:
        return [parts + ["-T", title, "-e", "bash", "-lc", wrapped]]
    if name == "wezterm":
        return [parts + ["start", "--", "bash", "-lc", wrapped]]
    if name in {"foot", "footclient"}:
        return [parts + ["-T", title, "bash", "-lc", wrapped]]
    return [
        parts + ["-e", "bash", "-lc", wrapped],
        parts + ["bash", "-lc", wrapped],
    ]


def terminal_candidates(
    wrapped: str, title: object, *, terminal_env: str = "", home: Path,
) -> tuple[tuple[str, ...], ...]:
    """Return ordered, de-duplicated argv; never probes or launches programs."""
    heading = str(title or "BC250 Control Center")
    quoted = shlex.quote(wrapped)
    candidates = _environment_candidates(terminal_env, heading, wrapped)
    candidates.extend([
        ["xdg-terminal-exec", "bash", "-lc", wrapped],
        ["ptyxis", "--new-window", "--title", heading, "--", "bash", "-lc", wrapped],
        ["ptyxis", "--", "bash", "-lc", wrapped],
        ["kgx", "--title", heading, "--", "bash", "-lc", wrapped],
        ["kgx", "--", "bash", "-lc", wrapped],
        ["gnome-console", "--", "bash", "-lc", wrapped],
        ["gnome-terminal", "--title", heading, "--", "bash", "-lc", wrapped],
        ["gnome-terminal", "--", "bash", "-lc", wrapped],
        ["blackbox", "--working-directory", str(home), "--command", f"bash -lc {quoted}"],
        ["cosmic-term", "-e", "bash", "-lc", wrapped],
        ["konsole", "--new-tab", "-p", f"tabtitle={heading}", "-e", "bash", "-lc", wrapped],
        ["konsole", "-p", f"tabtitle={heading}", "-e", "bash", "-lc", wrapped],
        ["qterminal", "-e", "bash", "-lc", wrapped],
        ["lxqt-terminal", "-e", "bash", "-lc", wrapped],
        ["lxterminal", "-e", "bash", "-lc", wrapped],
        ["tilix", "-e", "bash", "-lc", wrapped],
        ["terminator", "-x", "bash", "-lc", wrapped],
        ["xfce4-terminal", "--title", heading, "--command", f"bash -lc {quoted}"],
        ["mate-terminal", "--title", heading, "--", "bash", "-lc", wrapped],
        ["cinnamon-terminal", "--title", heading, "--", "bash", "-lc", wrapped],
        ["deepin-terminal", "-e", f"bash -lc {quoted}"],
        ["alacritty", "-T", heading, "-e", "bash", "-lc", wrapped],
        ["kitty", "--title", heading, "bash", "-lc", wrapped],
        ["wezterm", "start", "--", "bash", "-lc", wrapped],
        ["footclient", "-T", heading, "bash", "-lc", wrapped],
        ["foot", "-T", heading, "bash", "-lc", wrapped],
        ["rio", "-T", heading, "-e", "bash", "-lc", wrapped],
        ["st", "-t", heading, "-e", "bash", "-lc", wrapped],
        ["urxvt", "-title", heading, "-e", "bash", "-lc", wrapped],
        ["xterm", "-T", heading, "-e", "bash", "-lc", wrapped],
    ])
    unique: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        argv = tuple(str(part) for part in candidate if part is not None)
        if not argv or not argv[0] or argv in seen:
            continue
        seen.add(argv)
        unique.append(argv)
    return tuple(unique)
