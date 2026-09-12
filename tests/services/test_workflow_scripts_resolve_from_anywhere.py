"""A generated workflow must find its scripts wherever it is started from.

``Path("")`` is ``Path(".")`` and its string form is truthy, so an unset
``BC250_CONTROL_CENTER_DIR`` produced the candidate ``packaging/common/
os-scripts`` relative to the process working directory. Every generated
command then carried a relative script path. That worked for one reason only:
the workflow ran in a terminal emulator, which inherited the directory the
application had been started from. The moment a workflow ran anywhere else,
bash reported "No such file or directory" for a script that was present.

Nothing failed while the two happened to agree, which is exactly why it needs
a test rather than a convention.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from bc250cc.platform.packages.strategies.arch_repository import ArchRepository
from bc250cc.platform.packages.strategies.base_repository import BaseOSRepository

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class _Info:
    label = "CachyOS"
    family = "arch"


class _Host:
    """The minimum a strategy asks of its host to build a command."""

    def _tool_dir(self):
        return Path("/tmp/bc250-tools")

    def _command_path(self, name):
        return f"/usr/bin/{name}"


def _repository(cls=ArchRepository):
    repository = cls.__new__(cls)
    repository.host = _Host()
    repository.info = _Info()
    return repository


@pytest.fixture
def elsewhere(tmp_path, monkeypatch):
    """Run as if the application had been started from another directory."""
    monkeypatch.delenv("BC250_CONTROL_CENTER_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_the_scripts_root_is_absolute_from_an_unrelated_directory(elsewhere):
    root = _repository().scripts_root
    assert root.is_absolute(), root
    assert root.is_dir(), root
    assert root == REPOSITORY_ROOT / "packaging" / "common" / "os-scripts"


def test_the_scripts_root_does_not_follow_the_working_directory(elsewhere):
    """A decoy tree next to the process must not win over the real one."""
    decoy = elsewhere / "packaging" / "common" / "os-scripts"
    decoy.mkdir(parents=True)
    (decoy / "arch").mkdir()
    (decoy / "arch" / "prepare-dependencies.sh").write_text("#!/bin/sh\nexit 9\n")

    root = _repository().scripts_root
    assert root != decoy
    assert root == REPOSITORY_ROOT / "packaging" / "common" / "os-scripts"


def test_the_generated_command_names_the_script_absolutely(elsewhere):
    command = _repository().prepare_dependencies_command("governor")
    scripts = [part for part in command.split() if part.endswith(".sh")]
    assert scripts, command
    for script in scripts:
        assert script.startswith("/"), f"relative script path in: {command}"
        assert Path(script).is_file(), script


def test_every_distribution_resolves_its_own_dependency_script(elsewhere):
    """One relative path in any family is one broken distribution."""
    import importlib
    import pkgutil

    from bc250cc.platform.packages import strategies

    checked = []
    for module in pkgutil.iter_modules(strategies.__path__):
        loaded = importlib.import_module(f"{strategies.__name__}.{module.name}")
        for name, candidate in vars(loaded).items():
            if not isinstance(candidate, type) or not issubclass(candidate, BaseOSRepository):
                continue
            if not getattr(candidate, "dependency_script", ""):
                continue
            repository = _repository(candidate)
            root = repository.scripts_root
            assert root.is_absolute(), (name, root)
            script = root / candidate.dependency_script
            assert script.is_file(), (name, script)
            checked.append(name)
    assert len(set(checked)) >= 5, f"only checked {sorted(set(checked))}"


def test_an_explicit_install_directory_is_still_honoured(tmp_path, monkeypatch):
    staged = tmp_path / "installed"
    scripts = staged / "packaging" / "common" / "os-scripts"
    scripts.mkdir(parents=True)
    monkeypatch.setenv("BC250_CONTROL_CENTER_DIR", str(staged))
    assert _repository().scripts_root == scripts.resolve()


def test_a_blank_install_directory_is_ignored_rather_than_read_as_the_cwd(monkeypatch, tmp_path):
    """This is the exact shape of the original defect."""
    monkeypatch.setenv("BC250_CONTROL_CENTER_DIR", "   ")
    monkeypatch.chdir(tmp_path)
    root = _repository().scripts_root
    assert root.is_absolute()
    assert root == REPOSITORY_ROOT / "packaging" / "common" / "os-scripts"


def test_the_console_does_not_move_the_workflow_to_another_directory():
    """The embedded console inherits the directory a terminal window had.

    Forcing the child into the home directory is what surfaced the relative
    path above; the two fixes are independent, and both belong here.
    """
    source = Path("frontends/desktop/console/console_panel.py").read_text(encoding="utf-8")
    assert "cwd=None" in source
    assert not re.search(r"cwd\s*=\s*os\.path\.expanduser", source)
    assert "expanduser" not in source


def test_a_workflow_started_from_anywhere_finds_its_script(elsewhere):
    """End to end: generate the command and run it as bash would see it."""
    import subprocess

    command = _repository().prepare_dependencies_command("governor", mode="plan")
    script = next(part for part in command.split() if part.endswith(".sh"))
    result = subprocess.run(
        ["bash", "-n", script], capture_output=True, text=True, check=False, cwd=os.getcwd()
    )
    assert result.returncode == 0, result.stderr
