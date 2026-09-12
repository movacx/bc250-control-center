"""Twelve privileged helpers, one standard — not twelve conventions.

These run as root. They were written over time and drifted: eight started the
interpreter without isolation, so a root process honoured ``PYTHONPATH`` and
the user site directory; one resolved its interpreter through ``PATH`` with
``#!/usr/bin/env python3``; and two opened for business as an ordinary user
instead of refusing, one of them announcing ``READY`` and accepting commands
on standard input before failing on each individual write.

None of that was exploitable through the application's own paths, and that is
the point: a privileged surface should not depend on the caller being polite.
The checks below are mechanical so a thirteenth helper inherits the standard
instead of inventing a new one.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HELPERS = Path("privileged/helpers")
EXPECTED_SHEBANG = "#!/usr/bin/python3 -I"


def helper_files() -> list[Path]:
    if not HELPERS.is_dir():  # pragma: no cover - packaging layouts
        pytest.skip("privileged/helpers is not present in this checkout")
    return sorted(
        path
        for path in HELPERS.iterdir()
        if path.is_file() and not path.is_symlink() and path.name != "README.md"
    )


def helper_names() -> list[str]:
    return [path.name for path in helper_files()]


@pytest.mark.parametrize("name", helper_names())
def test_every_helper_starts_an_isolated_interpreter(name):
    """``-I`` ignores PYTHONPATH, the user site directory and PYTHONSTARTUP.

    Without it a root process imports whatever the environment points at.
    """
    first = (HELPERS / name).read_text(encoding="utf-8").splitlines()[0]
    assert first == EXPECTED_SHEBANG, f"{name} starts with {first!r}"


@pytest.mark.parametrize("name", helper_names())
def test_no_helper_finds_its_interpreter_through_the_path(name):
    first = (HELPERS / name).read_text(encoding="utf-8").splitlines()[0]
    assert "/usr/bin/env" not in first, (
        f"{name} resolves its interpreter through PATH while running as root"
    )


@pytest.mark.parametrize("name", helper_names())
def test_every_helper_checks_that_it_is_root(name):
    source = (HELPERS / name).read_text(encoding="utf-8")
    assert "geteuid" in source, f"{name} never checks the user it runs as"


@pytest.mark.skipif(os.geteuid() == 0, reason="this asserts the refusal, so it needs a non-root user")
@pytest.mark.parametrize("name", helper_names())
def test_every_helper_refuses_to_work_for_an_ordinary_user(name):
    """The behaviour, not just the presence of a check.

    ``bc250-fan-pwm-helper`` had the shape of a guard nowhere and answered
    ``READY`` to anyone; nothing in a source scan would have caught that.
    """
    result = subprocess.run(
        ["/usr/bin/python3", "-I", str(HELPERS / name)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    combined = f"{result.stdout}\n{result.stderr}"
    assert "Traceback" not in combined, combined
    assert "READY" not in result.stdout, f"{name} opened a session for a non-root user"
    assert combined.strip(), f"{name} did nothing and said nothing"


@pytest.mark.parametrize("name", helper_names())
def test_no_helper_imports_anything_it_cannot_verify(name):
    """Isolation removes the script's directory from the import path.

    A helper that needs a module from ``lib`` has to load it deliberately —
    by absolute path, with its ownership checked — rather than by import.
    """
    import ast
    import sys

    source = (HELPERS / name).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    outside = sorted(
        module
        for module in imported
        if module not in sys.stdlib_module_names and module != "__future__"
    )
    if not outside:
        return
    # The one helper that does need its own modules proves the rule: it
    # verifies ownership and inserts the directory itself.
    assert "sys.path.insert" in source or "spec_from_file_location" in source, (
        f"{name} imports {outside} but never establishes where they come from"
    )
    assert "st_uid != 0" in source or "metadata.st_uid" in source, (
        f"{name} loads {outside} without checking who owns them"
    )


def test_the_standard_covers_every_helper_that_exists():
    """A guard that silently covers zero files is worse than none."""
    assert len(helper_files()) >= 10, helper_names()
