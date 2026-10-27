"""The core unlock runs a private copy of the reviewed script, never the checkout.

The helper used to run the checkout's own file through /proc/self/fd. The fd
pins the inode, not its bytes: the desktop user who owns the file could write
it over in place after the hash check. And Python resolved that path to put
the checkout's directory first on sys.path, so a ``struct.py`` that
``.git/info/exclude`` hid from ``git status`` was imported, as root, in place
of the standard module the upstream script imports.
"""

from __future__ import annotations

import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

HELPER = Path(__file__).resolve().parents[3] / "privileged" / "helpers" / "bc250-core-unlock-helper"
GIT = Path("/usr/bin/git")

SCRIPT = (
    b"import json, struct, sys\n"
    b"print(json.dumps({'file': __file__, 'struct': struct.__file__, 'argv': sys.argv[1:]}))\n"
    b"print('core presence mask: 0x00000077')\n"
)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        [str(GIT), "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(repository),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
        },
    ).stdout.strip()


@pytest.fixture
def unlock(tmp_path, monkeypatch):
    """main() against a real, clean clone, with nothing reaching the system."""
    if not GIT.is_file():
        pytest.skip("git is needed to build a checkout the helper accepts")
    home = (tmp_path / "home").resolve()
    repository = home / "bc250-core-unlock"
    repository.mkdir(parents=True)
    home.chmod(0o755)
    repository.chmod(0o755)
    script = repository / "bc250-unlock-cores.py"
    script.write_bytes(SCRIPT)
    script.chmod(0o644)
    _git(repository, "init", "-q")
    _git(repository, "add", "-A")
    _git(repository, "commit", "-q", "-m", "reviewed")
    _git(repository, "remote", "add", "origin", "https://github.com/rw-r-r-0644/bc250-core-unlock")
    marker = tmp_path / "root-ran-user-code"
    # Planted by the desktop user and hidden by their own exclude file: the
    # tree stays clean.
    (repository / ".git/info").mkdir(exist_ok=True)
    (repository / ".git/info/exclude").write_text("struct.py\n")
    (repository / "struct.py").write_text(f"open({str(marker)!r}, 'w').write('ran')\nfrom _struct import *\n")
    assert _git(repository, "status", "--porcelain", "--untracked-files=all") == ""

    run = tmp_path / "run"
    run.mkdir()
    helper = runpy.run_path(str(HELPER))["main"].__globals__
    reboots: list = []
    for name, value in {
        "REVIEWED_REVISION": _git(repository, "rev-parse", "HEAD"),
        "REVIEWED_SCRIPT_SHA256": hashlib.sha256(SCRIPT).hexdigest(),
        "STAGING_PARENT": str(run),
        "_trusted_self": lambda: True,
        "_bc250_identity_present": lambda: True,
        "_invoking_user": lambda: (os.getuid(), os.getgid(), home),
        "_stop_gpu_governors": lambda: (),
        "_reboot_after_core_unlock": lambda: reboots.append(True),
    }.items():
        monkeypatch.setitem(helper, name, value)
    monkeypatch.setattr(os, "geteuid", lambda: 0)

    launched = []
    real_run = subprocess.run

    def run_upstream_for_real(command, **kwargs):
        if command[0] == "/usr/bin/python3":
            launched.append((list(command), kwargs))
            command = [sys.executable, *command[1:]]
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", run_upstream_for_real)
    return helper, repository, run, marker, launched, reboots


def _report(capsys) -> dict:
    """What the script that actually ran printed about itself."""
    return next(
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    )


def test_the_script_runs_from_a_private_copy_with_the_checkout_off_sys_path(unlock, capsys):
    helper, repository, run, marker, launched, reboots = unlock
    # What the old launch did with that clean tree.
    fd = os.open(repository / "bc250-unlock-cores.py", os.O_RDONLY)
    try:
        subprocess.run(
            [sys.executable, f"/proc/self/fd/{fd}"], pass_fds=(fd,), capture_output=True, check=True
        )
    finally:
        os.close(fd)
    assert marker.exists()
    marker.unlink()

    helper["main"](["helper", "--repo", str(repository), "--reboot"])

    report = _report(capsys)
    assert Path(report["file"]).name == "bc250-unlock-cores.py"
    assert Path(report["file"]).parent.parent == run
    assert not Path(report["struct"]).is_relative_to(repository)
    assert not marker.exists()
    command, options = launched[-1]
    assert command[:2] == ["/usr/bin/python3", "-I"]
    assert "pass_fds" not in options
    assert list(run.iterdir()) == []
    assert reboots == [True]


def test_a_script_written_over_after_validation_is_never_run(unlock, capsys, monkeypatch):
    helper, repository, run, marker, _launched, _reboots = unlock
    validate = helper["_validate_repository"]

    def validate_then_tamper(*arguments):
        verified = validate(*arguments)
        # In place, same inode: what an open fd would have followed.
        (repository / "bc250-unlock-cores.py").write_text(
            f"open({str(marker)!r}, 'w').write('ran')\n"
        )
        return verified

    monkeypatch.setitem(helper, "_validate_repository", validate_then_tamper)
    helper["main"](["helper", "--repo", str(repository), "--reboot", "--ignore-core-mask"])

    report = _report(capsys)
    assert report["argv"] == ["-f"]
    assert not marker.exists()
    assert list(run.iterdir()) == []
