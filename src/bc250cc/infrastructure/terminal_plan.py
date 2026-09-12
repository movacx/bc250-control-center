"""Pure shell wrapper and graphical-terminal candidate planning.

The failure explanation is built here, in Python, and injected into the
generated script as literal text. It used to be a ``case`` statement written
inside the shell fragment, which meant the wording could never reach ``tr()``
and so existed in English only, outside all 30 locales. It also explained just
13 statuses, while the privileged helpers exit with 20-57 — every other status
printed a bare number, which is where "code 43" came from.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from bc250cc.shared import error_catalog

_CODES_WITH_MARKERS = tuple(
    entry for entry in error_catalog.all_codes()
    if entry.markers and entry.code != "BC250-PROTOCOL-001"
)


# A plain ASCII rule so it renders identically in every terminal emulator,
# including minimal consoles without box-drawing glyphs.
_RULE = "=" * 74

# Used when the workflow printed its own [ERROR] explanation: the failure is
# real and described, but no catalog rule was consulted, so claiming a
# specific rule id would be a lie.
_WORKFLOW_REPORTED_CODE = "BC250-WORKFLOW-001"


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


def active_translator():
    return _TRANSLATOR


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

    branches = []
    for status in sorted(error_catalog.known_exit_statuses()):
        entry = error_catalog.for_exit_status(status)
        if entry is None:
            continue
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
        text_rules.append(
            f'if printf "%s" "$evidence" | grep -qiE {shlex.quote(patterns)}; then '
            f'summary={shlex.quote(translate(entry.summary))}; '
            f'cause={shlex.quote(translate(entry.cause))}; '
            f'action={shlex.quote(translate(entry.action))}; '
            f'diagnostic={shlex.quote(entry.code)}; matched=1; fi; '
        )

    return (
        'if [ "$status" -ne 0 ]; then '
        'matched=0; '
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
        # workflow already explained, so fall back to the neutral identifier.
        f'diagnostic={_WORKFLOW_REPORTED_CODE}; fi; '
        'if [ -n "$error_hints" ]; then cause=""; action=$error_hints; fi; '
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


def _evidence_capture_shell(log_path: object) -> str:
    """Shell fragment that captures the tail of the workflow log as evidence.

    Captured before the explanation block starts appending to the same log,
    so it reflects only the command's own output, not the summary text.
    """
    log = shlex.quote(str(log_path))
    return f"evidence=$(tail -n 12 {log} 2>/dev/null)"


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
        'if [ "$status" -ne 0 ] && [ -n "$evidence" ]; then '
        # First ERROR/FATAL line: what happened.
        'first_error=$(printf "%s\\n" "$evidence" '
        '| grep -m1 -E "^[[:space:]]*\\[(ERROR|FATAL)\\][: ]*" '
        '| sed -E "s/^[[:space:]]*\\[(ERROR|FATAL)\\][: ]*//" || true); '
        # Remaining ERROR lines: the script's own remediation steps.
        'error_hints=$(printf "%s\\n" "$evidence" '
        '| grep -E "^[[:space:]]*\\[(ERROR|FATAL)\\][: ]*" '
        '| tail -n +2 '
        '| sed -E "s/^[[:space:]]*\\[(ERROR|FATAL)\\][: ]*/  /" || true); '
        'fi'
    )


def _evidence_render_shell(translate=None) -> str:
    """Shell fragment that prints the captured evidence tail on failure."""
    translate = translate if callable(translate) else _TRANSLATOR
    heading = translate("Last lines from the workflow output:")
    return (
        'if [ "$status" -ne 0 ] && [ -n "$evidence" ]; then '
        f'printf "\\n%s\\n" "{heading}"; '
        'printf "%s\\n" "$evidence" | sed "s/^/  /"; '
        'fi'
    )


def workflow_wrapper(
    command: object,
    status_path: Path,
    log_path: Path,
    translate=None,
    *,
    hold: bool = True,
) -> str:
    """Wrap a workflow so it logs, records its exit status, and reports it.

    ``hold`` keeps the closing "Enter to close" prompt. A terminal emulator
    launched for one command disappears the instant the command ends, taking
    the result with it, so the prompt is what makes the output readable there.
    The embedded console does not close on its own, so it passes ``hold=False``
    and leaves the panel showing the same summary without a key press.
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
    return (
        f"bash -o pipefail -c {pipeline}; "
        "status=$?; "
        f"printf '%s\\n' \"$status\" > {status}; "
        f"{_evidence_capture_shell(log_path)}; "
        "{ echo; "
        # A successful run reports success, not a number. Only a failure needs
        # a diagnosis, and the raw status stays in the technical detail below.
        f"if [ \"$status\" -eq 0 ]; then echo \"{finished_ok}\"; "
        f"else echo \"{finished_failed}\"; fi; "
        f"{_first_error_shell(translate)}; "
        f"{exit_explanation_shell(translate)}; "
        f"{_evidence_render_shell(translate)}; "
        f"echo \"{saved_log}: {log_path!s}\"; "
        f"echo \"{share_hint}\"; }} "
        f"2>&1 | tee -a {log}; "
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
