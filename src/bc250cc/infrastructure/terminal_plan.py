"""Pure shell wrapper and graphical-terminal candidate planning."""

from __future__ import annotations

import shlex
from pathlib import Path


def workflow_wrapper(command: object, status_path: Path, log_path: Path) -> str:
    requested = str(command or "").strip()
    if not requested:
        raise RuntimeError("The requested terminal workflow is empty.")
    inner = shlex.quote(requested)
    status = shlex.quote(str(status_path))
    log = shlex.quote(str(log_path))
    return (
        "set -o pipefail; "
        f"bash -lc {inner} 2>&1 | tee {log}; "
        "status=${PIPESTATUS[0]}; "
        f"printf '%s\\n' \"$status\" > {status}; "
        "{ echo; echo \"== Process finished with exit code $status ==\"; "
        f"echo \"Full log saved to: {log_path!s}\"; "
        "echo \"You can share that .log file if something failed.\"; } "
        f"2>&1 | tee -a {log}; "
        "read -r -p \"Enter to close...\" _; exit \"$status\""
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
