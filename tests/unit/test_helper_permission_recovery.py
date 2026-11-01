"""Exercise the canonical repair without changing any host permissions."""

from __future__ import annotations

import errno
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
REPAIR = (ROOT / "packaging/common/bc250-package-maintenance").read_text().split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]


def _run(monkeypatch, *, mode=0o777, uid=0, gid=0, symlink=False, check=False):
    opened, changed = [], []
    metadata = SimpleNamespace(st_uid=uid, st_gid=gid, st_mode=stat.S_IFDIR | mode)

    def open_directory(path, flags, *, dir_fd=None):
        opened.append(path)
        assert flags & os.O_NOFOLLOW and flags & os.O_DIRECTORY
        if path != "/":
            raise FileNotFoundError(path)
        if symlink:
            raise OSError(errno.ELOOP, "symlink")
        return 987

    def chmod_directory(fd, wanted):
        assert fd == 987
        changed.append(("/", wanted))
        metadata.st_mode = stat.S_IFDIR | wanted

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", open_directory)
        patch.setattr(os, "fstat", lambda fd: metadata)
        patch.setattr(os, "fchmod", chmod_directory)
        patch.setattr(os, "close", lambda fd: None)
        patch.setattr(os, "geteuid", lambda: 0)
        patch.setattr(sys, "argv", ["-", "check" if check else "apply"])
        if check:
            with pytest.raises(SystemExit) as result:
                exec(compile(REPAIR, "permission-repair", "exec"), {})
            exit_code = result.value.code
        else:
            exec(compile(REPAIR, "permission-repair", "exec"), {})
            exit_code = 0
    assert opened and set(opened) <= {"/", "usr", "etc", "var"}
    return changed, exit_code


@pytest.mark.parametrize("mode", [0o775, 0o777])
def test_known_root_owned_unsafe_modes_are_repaired(monkeypatch, mode):
    assert _run(monkeypatch, mode=mode)[0] == [("/", 0o755)]


@pytest.mark.parametrize("overrides", [
    {"mode": 0o1777}, {"mode": 0o2775}, {"mode": 0o755}, {"mode": 0o555},
    {"mode": 0o776}, {"uid": 1000}, {"gid": 1000}, {"symlink": True},
])
def test_user_owned_special_or_unrecognized_paths_are_never_changed(monkeypatch, overrides):
    assert _run(monkeypatch, **overrides)[0] == []


def test_detection_is_read_only_and_distinguishes_healthy_paths(monkeypatch):
    assert _run(monkeypatch, mode=0o777, check=True) == ([], 0)
    assert _run(monkeypatch, mode=0o755, check=True) == ([], 1)
