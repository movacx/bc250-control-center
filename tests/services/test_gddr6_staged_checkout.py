"""Root uses a private copy of the reviewed upstream checkout, never the checkout.

The clone of pan-Rijovich/bc250-memory-temperature belongs to the desktop
user. The helpers validate it (origin, pinned revision, clean tree), but a
check made there holds only until that user's next write. The reader used to
import ``bc250_smu`` from the checkout as root, and patch_smu.py imported
``unlock`` and ``bc250_smu`` and read the payload it writes into SMU RAM from
its own directory, by path. A clean tree did not even mean only reviewed code
was there: upstream ignores ``__pycache__``, and ``.git/info/exclude`` hides
anything else. Now every file root needs is read once, checked against its
pinned SHA-256 and copied into a fresh directory only root can enter, and
imported or executed from there. A file changed after validation is refused
when it changed before it was copied, and never looked at again after.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.machinery
import importlib.util
import json
import marshal
import os
import stat
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "privileged/helpers"
GIT = Path("/usr/bin/git")

PACKAGE_INIT = b"""\
from .codec import GENUINE


class Bc250Smu:
    genuine = GENUINE
    origin = __file__

    def close(self):
        pass
"""

#: Finds its files the way the real patch_smu.py does: next to its own
#: resolved ``__file__``.
PATCH_SMU = b"""\
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bc250_smu import Bc250Smu
from unlock import ORIGIN as UNLOCK_ORIGIN

print(json.dumps({
    "root": str(ROOT),
    "genuine": Bc250Smu.genuine,
    "package": Bc250Smu.origin,
    "unlock": UNLOCK_ORIGIN,
    "json": json.__file__,
    "payload": (ROOT / "SMUPayload.bin").read_bytes().hex(),
    "symbols": (ROOT / "SMUPayload.symbols").read_text(),
    "argv": sys.argv[1:],
}))
"""

UPSTREAM = {
    "bc250_smu/__init__.py": PACKAGE_INIT,
    "bc250_smu/codec.py": b"GENUINE = True\n",
    "unlock.py": b"from bc250_smu import Bc250Smu\n\nORIGIN = __file__\n\n\ndef unlock(smu):\n    pass\n",
    "patch_smu.py": PATCH_SMU,
    "SMUPayload.bin": bytes.fromhex("01020304"),
    "SMUPayload.symbols": b"umc_read_temp_packed T 0003ac34 00000120\n",
}
PACKAGE = tuple(name for name in UPSTREAM if name.startswith("bc250_smu/"))
DIGESTS = {name: hashlib.sha256(content).hexdigest() for name, content in UPSTREAM.items()}


def _load(name: str):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(HELPERS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


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


def _evil(marker: Path) -> bytes:
    """What the desktop user would like root to run instead."""
    return (
        f"open({str(marker)!r}, 'w').write('root ran the desktop user\\'s code')\n"
        "class Bc250Smu:\n"
        "    genuine = False\n"
        "    origin = __file__\n"
        "ORIGIN = __file__\n"
    ).encode()


def _forge_bytecode(source: Path, code: str) -> None:
    """A ``__pycache__`` entry Python takes for ``source``: same size, same time."""
    info = source.stat()
    target = Path(importlib.util.cache_from_source(str(source)))
    target.parent.mkdir(exist_ok=True)
    header = importlib.util.MAGIC_NUMBER + struct.pack(
        "<III", 0, int(info.st_mtime) & 0xFFFFFFFF, info.st_size & 0xFFFFFFFF
    )
    target.write_bytes(header + marshal.dumps(compile(code, str(source), "exec")))


@pytest.fixture
def checkout(tmp_path):
    """A clean clone at its own "reviewed" revision, as the helpers expect one."""
    if not GIT.is_file():
        pytest.skip("git is needed to build a checkout the helpers accept")
    home = (tmp_path / "home").resolve()
    repository = home / "bc250-memory-temperature"
    (repository / "bc250_smu").mkdir(parents=True)
    for directory in (home, repository, repository / "bc250_smu"):
        directory.chmod(0o755)
    for name, content in UPSTREAM.items():
        (repository / name).write_bytes(content)
        (repository / name).chmod(0o644)
    # Upstream's own rules: nothing under __pycache__ shows in ``git status``.
    (repository / ".gitignore").write_text("__pycache__/\n*.pyc\n")
    _git(repository, "init", "-q")
    _git(repository, "add", "-A")
    _git(repository, "commit", "-q", "-m", "reviewed")
    _git(repository, "remote", "add", "origin", "https://github.com/pan-Rijovich/bc250-memory-temperature")
    run = tmp_path / "run"
    run.mkdir()
    return SimpleNamespace(
        home=home,
        repository=repository,
        revision=_git(repository, "rev-parse", "HEAD"),
        run=run,
        marker=tmp_path / "root-ran-user-code",
    )


@pytest.fixture(autouse=True)
def _own_imports():
    """Each test imports its own ``bc250_smu``; none may leak into another."""
    def ours():
        return [name for name in sys.modules if name == "bc250_smu" or name.startswith("bc250_smu.")]

    saved = {name: sys.modules.pop(name) for name in ours()}
    yield
    for name in ours():
        del sys.modules[name]
    sys.modules.update(saved)


def _pin(module, monkeypatch, checkout):
    monkeypatch.setattr(module, "REVIEWED_REVISION", checkout.revision)
    monkeypatch.setattr(module, "STAGING_PARENT", str(checkout.run))
    if hasattr(module, "REVIEWED_PACKAGE_SHA256"):
        monkeypatch.setattr(module, "REVIEWED_PACKAGE_SHA256", {name: DIGESTS[name] for name in PACKAGE})
        return module
    monkeypatch.setattr(module, "REVIEWED_SCRIPT_SHA256", {"patch_smu.py": DIGESTS["patch_smu.py"]})
    monkeypatch.setattr(
        module, "REVIEWED_MODULE_SHA256", {name: DIGESTS[name] for name in ("unlock.py", *PACKAGE)}
    )
    monkeypatch.setattr(
        module,
        "REVIEWED_ARTIFACT_SHA256",
        {name: DIGESTS[name] for name in ("SMUPayload.bin", "SMUPayload.symbols")},
    )
    return module


@pytest.fixture
def reader(monkeypatch, checkout):
    return _pin(_load("bc250-gddr6-temp-reader"), monkeypatch, checkout)


@pytest.fixture
def helper(monkeypatch, checkout):
    return _pin(_load("bc250-gddr6-temp-helper"), monkeypatch, checkout)


def _validate(module, checkout) -> Path:
    """The helpers' real validation: origin, revision, clean tree, as the user."""
    return module._validate_repository(
        str(checkout.repository), os.getuid(), os.getgid(), checkout.home
    )


def _tamper_after_copy(module, monkeypatch, repository: Path, replacement) -> None:
    """The moment each file has been read, its owner writes it over in place."""
    original = module._read_checkout_file

    def read_then_tamper(root_fd, name, uid):
        content = original(root_fd, name, uid)
        (repository / name).write_bytes(replacement(name))
        return content

    monkeypatch.setattr(module, "_read_checkout_file", read_then_tamper)


# ------------------------------------------------------------ the reader


def test_the_reader_imports_only_its_private_copy(reader, checkout):
    repository = _validate(reader, checkout)
    smu = reader._open_smu(repository, os.getuid())

    assert smu.genuine is True
    assert Path(smu.origin).parent.parent.parent == checkout.run
    assert not any(entry.startswith(str(checkout.run)) for entry in sys.path)
    # Nothing is left behind once the import is done.
    assert list(checkout.run.iterdir()) == []


def test_a_module_changed_after_validation_is_refused_not_imported(reader, checkout):
    repository = _validate(reader, checkout)
    (repository / "bc250_smu/__init__.py").write_bytes(_evil(checkout.marker))

    with pytest.raises(RuntimeError, match="bc250_smu/__init__.py does not match"):
        reader._open_smu(repository, os.getuid())
    assert not checkout.marker.exists()
    assert "bc250_smu" not in sys.modules
    assert list(checkout.run.iterdir()) == []


def test_a_module_changed_after_it_was_copied_is_never_used(reader, checkout, monkeypatch):
    repository = _validate(reader, checkout)
    _tamper_after_copy(reader, monkeypatch, repository, lambda _name: _evil(checkout.marker))

    smu = reader._open_smu(repository, os.getuid())

    assert (repository / "bc250_smu/__init__.py").read_bytes() == _evil(checkout.marker)
    assert smu.genuine is True
    assert Path(smu.origin).is_relative_to(checkout.run)
    assert not checkout.marker.exists()


def test_bytecode_git_ignores_is_never_imported(reader, checkout):
    """No race needed: upstream ignores __pycache__, so the tree stays clean."""
    repository = checkout.repository
    _forge_bytecode(
        repository / "bc250_smu/__init__.py",
        "class Bc250Smu:\n    genuine = False\n    origin = __file__\n",
    )
    validated = _validate(reader, checkout)
    # What importing from the checkout itself, as the reader used to, picks up.
    old_way = subprocess.run(
        [
            sys.executable, "-I", "-B", "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); import bc250_smu; "
            "print(bc250_smu.Bc250Smu.genuine)",
            str(repository),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert old_way.stdout.strip() == "False"

    assert reader._open_smu(validated, os.getuid()).genuine is True


@pytest.mark.parametrize("swapped", ["bc250_smu/codec.py", "bc250_smu"])
def test_a_symbolic_link_is_refused_even_to_the_reviewed_bytes(reader, checkout, swapped):
    repository = _validate(reader, checkout)
    elsewhere = checkout.home / "elsewhere"
    (repository / swapped).rename(elsewhere)
    (repository / swapped).symlink_to(elsewhere)

    with pytest.raises(RuntimeError, match="symbolic link"):
        reader._open_smu(repository, os.getuid())
    assert list(checkout.run.iterdir()) == []


def test_a_fifo_in_a_files_place_is_refused_without_waiting(reader, checkout):
    repository = _validate(reader, checkout)
    (repository / "bc250_smu/codec.py").unlink()
    os.mkfifo(repository / "bc250_smu/codec.py", 0o644)

    with pytest.raises(RuntimeError, match="not a regular file"):
        reader._open_smu(repository, os.getuid())


# ------------------------------------------------------------ the patcher


def _patch(helper, monkeypatch, status=None):
    """Everything but the copy and the run itself is out of the way."""
    statuses = []
    monkeypatch.setattr(helper, "bios_version", lambda: "P3.00")
    monkeypatch.setattr(
        helper,
        "_patch_status",
        lambda *args, **kwargs: statuses.append(args) or dict(status or {"payload": ""}),
    )
    monkeypatch.setattr(helper, "external_collector_lock", lambda: contextlib.nullcontext(False))
    monkeypatch.setattr(helper, "smn_window_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(helper, "governor_unsettled", lambda: "")
    launched = []
    real_run = subprocess.run

    def run(command, **kwargs):
        launched.append((list(command), kwargs))
        if command[0] == "/usr/bin/python3":
            command = [sys.executable, *command[1:]]
        return real_run(command, **kwargs)

    monkeypatch.setattr(helper.subprocess, "run", run)
    return launched, statuses


def test_patch_smu_runs_imports_and_reads_only_the_private_copy(helper, checkout, monkeypatch, capsys):
    repository = checkout.repository
    # A stand-in for the standard module patch_smu.py imports first, hidden
    # from ``git status`` by the user's own exclude file.
    (repository / ".git/info").mkdir(exist_ok=True)
    (repository / ".git/info/exclude").write_text("json.py\n")
    (repository / "json.py").write_bytes(_evil(checkout.marker))
    validated = _validate(helper, checkout)

    evil = {
        "SMUPayload.bin": bytes.fromhex("deadbeef"),
        "SMUPayload.symbols": b"umc_read_temp_packed T 00000800 0000011e\n",
    }
    _tamper_after_copy(
        helper, monkeypatch, repository, lambda name: evil.get(name, _evil(checkout.marker))
    )
    launched, _statuses = _patch(helper, monkeypatch, {"payload": "legacy", "patch_active": False})

    assert helper._do_apply(validated, os.getuid(), os.getgid()) == 0

    report = json.loads(capsys.readouterr().out.splitlines()[0])
    staged = Path(report["root"])
    assert staged.parent == checkout.run.resolve()
    assert report["genuine"] is True
    assert Path(report["package"]).is_relative_to(staged)
    assert Path(report["unlock"]).is_relative_to(staged)
    assert not Path(report["json"]).is_relative_to(repository)
    # The reviewed payload and symbols, not what replaced them in the checkout.
    assert report["payload"] == "01020304"
    assert report["symbols"] == UPSTREAM["SMUPayload.symbols"].decode()
    assert report["argv"] == ["-f"]
    assert not checkout.marker.exists()

    command, options = launched[-1]
    assert command[:2] == ["/usr/bin/python3", "-I"]
    assert Path(command[2]).resolve() == staged / "patch_smu.py"
    assert Path(options["cwd"]).resolve() == staged
    assert "pass_fds" not in options
    assert not any(str(repository) in value for value in options["env"].values())
    assert list(checkout.run.iterdir()) == []


@pytest.mark.parametrize(
    "name",
    ["patch_smu.py", "unlock.py", "bc250_smu/__init__.py", "SMUPayload.bin", "SMUPayload.symbols"],
)
def test_a_file_changed_after_validation_is_never_run_or_written(
    helper, checkout, monkeypatch, name
):
    validated = _validate(helper, checkout)
    (checkout.repository / name).write_bytes(_evil(checkout.marker))
    launched, statuses = _patch(helper, monkeypatch)

    with pytest.raises(RuntimeError, match=f"{name} does not match"):
        helper._do_apply(validated, os.getuid(), os.getgid())
    # Refused before the reader is asked and before patch_smu.py could start.
    assert statuses == [] and launched == []
    assert not checkout.marker.exists()
    assert list(checkout.run.iterdir()) == []


def test_the_private_copy_is_only_roots_and_only_the_reviewed_files(helper, checkout):
    repository = checkout.repository
    (repository / "notes.txt").write_text("not reviewed\n")
    _forge_bytecode(repository / "unlock.py", "ORIGIN = 'forged'\n")

    with helper.staged_checkout(repository, os.getuid(), helper._reviewed_files()) as staging:
        assert staging.parent == checkout.run
        assert stat.S_IMODE(staging.stat().st_mode) == 0o700
        files = sorted(path for path in staging.rglob("*") if path.is_file())
        assert [path.relative_to(staging).as_posix() for path in files] == sorted(UPSTREAM)
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files)
        assert all(path.read_bytes() == UPSTREAM[path.relative_to(staging).as_posix()] for path in files)
    assert not staging.exists()

    with pytest.raises(RuntimeError, match="interrupted"):
        with helper.staged_checkout(repository, os.getuid(), helper._reviewed_files()):
            raise RuntimeError("interrupted")
    assert list(checkout.run.iterdir()) == []
