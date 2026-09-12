"""Nothing may open a terminal emulator behind the console's back.

The console is worth having only if it is where workflows actually appear. One
module that builds its own terminal command, or one page that shells out to
``konsole`` directly, and the user is back to a stray window with a different
theme — and the console silently covers everything except that one action,
which is worse than not having it, because the exception is invisible.

So the rule is mechanical: exactly one function in the codebase may launch a
terminal emulator, it lives in ``TerminalRepository``, and it is reached only
after the embedded console has been offered the workflow and declined.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(".").resolve()
SOURCE_TREES = (Path("src"), Path("frontends"))
TERMINAL_REPOSITORY = Path("src/bc250cc/infrastructure/terminal_repository.py")
TERMINAL_PLAN = Path("src/bc250cc/infrastructure/terminal_plan.py")
# The one deliberate exception: the console's own "Open terminal" button, which
# hands the running workflow to a real window when the user asks for it.
ESCAPE_HATCH = Path("frontends/desktop/app.py")

# Every terminal emulator the planner knows how to start.
EMULATORS = (
    "konsole", "gnome-terminal", "gnome-console", "kgx", "ptyxis", "xterm",
    "alacritty", "kitty", "wezterm", "foot", "footclient", "rio", "st",
    "urxvt", "tilix", "terminator", "xfce4-terminal", "mate-terminal",
    "cinnamon-terminal", "deepin-terminal", "qterminal", "lxterminal",
    "lxqt-terminal", "cosmic-term", "blackbox", "xdg-terminal-exec",
)


def _python_files() -> list[Path]:
    files: list[Path] = []
    for tree in SOURCE_TREES:
        if not tree.is_dir():  # pragma: no cover - packaging layouts
            pytest.skip(f"{tree} is not present in this checkout")
        files.extend(
            path for path in tree.rglob("*.py") if "__pycache__" not in path.parts
        )
    return sorted(files)


# Naming a terminal is harmless on its own: the Processes page lists "Konsole"
# as a friendly name, and the service module lists it among the processes it
# must never offer to kill. Running ``subprocess.run`` is harmless too — most
# of the infrastructure reads system state that way. What is not harmless is an
# emulator name reaching a call that starts a process, so that is what is
# measured, on the syntax tree rather than on the text.
SPAWN_CALLS = {
    "Popen", "run", "call", "check_call", "check_output",
    "startDetached", "start", "execv", "execve", "execvp", "execvpe",
    "system", "spawnv", "spawnve",
}


def _literals_in(node: ast.AST) -> set[str]:
    return {
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    }


def _emulators_passed_to_a_spawn(path: Path) -> set[str]:
    """Emulator names that appear inside a process-starting call."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - the suite would fail elsewhere
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr if isinstance(node.func, ast.Attribute)
            else node.func.id if isinstance(node.func, ast.Name)
            else ""
        )
        if name not in SPAWN_CALLS:
            continue
        literals = set()
        for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
            literals |= _literals_in(argument)
        found |= {value for value in literals if value in EMULATORS}
    return found


def test_only_the_terminal_repository_can_start_an_emulator():
    offenders: dict[str, list[str]] = {}
    allowed = {TERMINAL_REPOSITORY, TERMINAL_PLAN, ESCAPE_HATCH}
    for path in _python_files():
        if path in allowed:
            continue
        found = _emulators_passed_to_a_spawn(path)
        if found:
            offenders[str(path)] = sorted(found)
    assert offenders == {}, (
        "these modules hand a terminal emulator to a process-starting call, so "
        f"they open their own window instead of using the seam: {offenders}"
    )


def test_the_two_modules_that_only_name_a_terminal_never_start_one():
    """Pins *why* the known mentions are safe, not merely that they exist."""
    for name in ("frontends/desktop/pages/processes.py",
                 "src/bc250cc/infrastructure/system_service.py"):
        path = Path(name)
        text = path.read_text(encoding="utf-8")
        assert any(
            re.search(rf"[\"']{re.escape(emulator)}[\"']", text)
            for emulator in EMULATORS
        ), f"{name} no longer mentions a terminal; drop it from this test"
        assert _emulators_passed_to_a_spawn(path) == set(), (
            f"{name} now passes a terminal emulator to a spawn call; it used to "
            "only list the name for display"
        )


def test_no_module_builds_its_own_terminal_command():
    """``terminal_candidates`` is the planner; only two callers may use it."""
    callers: list[str] = []
    for path in _python_files():
        if path in {TERMINAL_REPOSITORY, TERMINAL_PLAN}:
            continue
        text = path.read_text(encoding="utf-8")
        if "terminal_candidates(" in text or "_launch_terminal_candidates(" in text:
            callers.append(str(path))
    assert callers == [str(ESCAPE_HATCH)], callers


def test_every_workflow_goes_through_the_one_seam():
    """All visible workflows call ``_abrir_terminal``; none spawn their own."""
    seams = 0
    for path in _python_files():
        seams += path.read_text(encoding="utf-8").count("self._abrir_terminal(")
    # The number will move as features are added; what matters is that there
    # are many callers and exactly one implementation.
    assert seams >= 20, f"only {seams} workflows found; did the seam move?"
    body = TERMINAL_REPOSITORY.read_text(encoding="utf-8")
    assert body.count("def _abrir_terminal(") == 1


def test_the_console_is_offered_before_any_window_is_opened():
    body = TERMINAL_REPOSITORY.read_text(encoding="utf-8")
    tree = ast.parse(body)
    function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_abrir_terminal"
    )
    calls = [
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "_try_embedded_terminal" in calls
    assert "_launch_terminal_candidates" in calls
    assert calls.index("_try_embedded_terminal") < calls.index("_launch_terminal_candidates")


def test_the_escape_hatch_is_the_console_asking_for_a_window():
    """app.py may start an emulator only to honour the panel's own button."""
    text = ESCAPE_HATCH.read_text(encoding="utf-8")
    assert "external_terminal_requested" in text
    assert "_open_workflow_in_terminal" in text


def test_the_desktop_registers_the_console_at_start_up():
    """Without this the seam has nothing to offer the workflow to."""
    text = ESCAPE_HATCH.read_text(encoding="utf-8")
    assert "ConsoleHost(" in text
    assert "host.install()" in text


def test_the_privileged_pipe_calls_are_not_workflows():
    """A pkexec call with pipes is a background operation, not a shown workflow.

    It is listed here so the distinction stays deliberate: these never opened a
    terminal before this change either, and routing them into the console would
    show a window for work the user is not waiting to read.
    """
    fan = Path("src/bc250cc/infrastructure/fan_repository.py").read_text(encoding="utf-8")
    assert "subprocess.PIPE" in fan
    assert not any(f"'{name}'" in fan for name in EMULATORS)


def test_the_list_of_modules_that_even_mention_a_terminal_is_closed():
    """A whitelist, so a new mention anywhere has to be looked at.

    The syntax-tree check above catches an emulator handed straight to a spawn
    call. It cannot catch a module that builds the argument list in one place
    and spawns it in another, which is exactly how the planner and the
    repository are split. This closes that gap from the other side: only these
    files may name a terminal at all, and each is accounted for.
    """
    # Three files, and only one of them is about launching anything. The
    # repository that actually spawns and the window that offers the button
    # are deliberately absent: they never name a terminal, they ask the
    # planner for candidates and run what it returns.
    expected = {
        # Builds the candidate list. Starts nothing itself.
        "src/bc250cc/infrastructure/terminal_plan.py",
        # Friendly names for the process list.
        "frontends/desktop/pages/processes.py",
        # Processes that must never be offered for termination.
        "src/bc250cc/infrastructure/system_service.py",
    }
    mentions = {
        str(path)
        for path in _python_files()
        if any(
            re.search(rf"[\"']{re.escape(name)}[\"']", path.read_text(encoding="utf-8"))
            for name in EMULATORS
        )
    }
    unexpected = mentions - expected
    assert unexpected == set(), (
        "these modules name a terminal emulator and are not accounted for; "
        f"check whether they bypass the console: {sorted(unexpected)}"
    )
    vanished = expected - mentions
    assert vanished == set(), (
        f"these no longer mention a terminal; update the list: {sorted(vanished)}"
    )
