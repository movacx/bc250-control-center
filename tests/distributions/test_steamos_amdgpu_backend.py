"""Regression coverage for the protected SteamOS AMDGPU staging boundary."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import bc250cc.infrastructure.steamos_amdgpu_backend as backend
from bc250cc.infrastructure.steamos_amdgpu import (
    build_steamos_amdgpu_diagnostic_command,
)


def _git(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["/usr/bin/git", *command], cwd=cwd, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def test_stage_command_archives_the_pinned_tree_not_the_mutable_worktree(tmp_path, monkeypatch):
    source = tmp_path / "checkout"
    subtree = source / "bc250-audio-fix"
    subtree.mkdir(parents=True)
    for name in backend.BACKEND_REQUIRED_EXECUTABLES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/bash\necho committed\n", encoding="utf-8")
        path.chmod(0o755)
    for name in backend.BACKEND_REQUIRED_REGULARS:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# committed build environment\n", encoding="utf-8")
    _git(["init"], source)
    _git(["config", "user.email", "bc250-tests@example.invalid"], source)
    _git(["config", "user.name", "BC250 tests"], source)
    _git(["add", "."], source)
    _git(["commit", "-m", "reviewed"], source)
    revision = _git(["rev-parse", "HEAD"], source)
    # The source checkout is deliberately changed after the reviewed commit.
    # A root staging path must receive the Git object, not this mutable file.
    (subtree / "patch-driver.sh").write_text("#!/bin/bash\necho mutable\n", encoding="utf-8")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_sudo = fake_bin / "sudo"
    fake_sudo.write_text(
        "#!/usr/bin/bash\n"
        "if [ \"${1:-}\" = chown ]; then exit 0; fi\n"
        "if [ \"${1:-}\" = install ]; then\n"
        "  shift; kept=(); while [ $# -gt 0 ]; do\n"
        "    case \"$1\" in -o|-g) shift 2 ;; *) kept+=(\"$1\"); shift ;; esac\n"
        "  done; exec /usr/bin/install \"${kept[@]}\"\n"
        "fi\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    fake_sudo.chmod(0o755)
    root = tmp_path / "protected" / "backend"
    # This test validates archive/atomic sequencing without pretending the
    # unprivileged test process owns a root filesystem. Filesystem ownership
    # itself is covered by the generated guard contract below.
    monkeypatch.setattr(backend, "protected_backend_guard", lambda *args, **kwargs: "true")
    command = backend.stage_backend_command(source, revision, root=root)
    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )

    assert result.returncode == 0, result.stderr
    staged_patch = root / "bc250-audio-fix" / "patch-driver.sh"
    assert "committed" in staged_patch.read_text(encoding="utf-8")
    assert "mutable" not in staged_patch.read_text(encoding="utf-8")
    assert (root / "bc250-audio-fix" / "boot-config.sh").is_file()
    assert (root / "bc250-update-persistence.sh").is_file()
    assert (root / "bc250-storage.sh").is_file()
    assert (root / ".bc250-control-center-reviewed-revision").read_text(
        encoding="utf-8"
    ).strip() == revision
    assert not (root.parent / ".steamos-amdgpu-backend.previous").exists()


def test_stage_command_requires_every_full_install_member(tmp_path):
    command = backend.stage_backend_command(tmp_path, "a" * 40)

    assert "archive --format=tar" in command
    assert "bc250-audio-fix bc250-mesh-shader.sh bc250-update-persistence.sh bc250-storage.sh" in command
    for name in backend.BACKEND_REQUIRED_EXECUTABLES + backend.BACKEND_REQUIRED_REGULARS:
        assert name in command
        assert f'reviewed {name} is absent from the pinned commit' in command
    for name in backend.BACKEND_REQUIRED_EXECUTABLES:
        assert f'"$stage_tmp/{name}"' in command


def test_staged_toolkit_runs_the_nested_read_only_status_chain(tmp_path, monkeypatch):
    """Exercise archive layout plus patch-driver -> boot-config status wiring.

    The fixture never uses a host privileged path: a fake sudo process runs
    only commands below ``tmp_path``.  This guards the relationship that the
    protected source stage must preserve for the real upstream scripts.
    """
    source = tmp_path / "checkout"
    audio = source / "bc250-audio-fix"
    audio.mkdir(parents=True)
    for name in backend.BACKEND_REQUIRED_EXECUTABLES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/bash\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    for name in backend.BACKEND_REQUIRED_REGULARS:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")
    (audio / "boot-config.sh").write_text(
        "#!/usr/bin/bash\n"
        "[ \"${1:-}\" = status ] || exit 2\n"
        "echo '[bc250-amdgpu] scheduler policy: configured and active (amdgpu.sched_policy=2)'\n",
        encoding="utf-8",
    )
    (audio / "patch-driver.sh").write_text(
        "#!/usr/bin/bash\n"
        "HERE=$(cd \"$(dirname \"$0\")\" && pwd)\n"
        "[ \"${1:-}\" = status ] || exit 2\n"
        "echo '[bc250-amdgpu] 6.18.mock: installed, metrics and compute aware'\n"
        "\"$HERE/boot-config.sh\" status\n"
        "echo '[bc250-amdgpu] state: installed'\n",
        encoding="utf-8",
    )
    _git(["init"], source)
    _git(["config", "user.email", "bc250-tests@example.invalid"], source)
    _git(["config", "user.name", "BC250 tests"], source)
    _git(["add", "."], source)
    _git(["commit", "-m", "reviewed"], source)
    revision = _git(["rev-parse", "HEAD"], source)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "sudo").write_text(
        "#!/usr/bin/bash\n"
        "if [ \"${1:-}\" = chown ]; then exit 0; fi\n"
        "if [ \"${1:-}\" = install ]; then\n"
        "  shift; kept=(); while [ $# -gt 0 ]; do\n"
        "    case \"$1\" in -o|-g) shift 2 ;; *) kept+=(\"$1\"); shift ;; esac\n"
        "  done; exec /usr/bin/install \"${kept[@]}\"\n"
        "fi\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    (fake_bin / "sudo").chmod(0o755)
    (fake_bin / "uname").write_text(
        "#!/usr/bin/bash\nif [ \"${1:-}\" = -r ]; then echo 6.18.mock; else exec /usr/bin/uname \"$@\"; fi\n",
        encoding="utf-8",
    )
    (fake_bin / "uname").chmod(0o755)
    root = tmp_path / "protected" / "backend"
    monkeypatch.setattr(backend, "protected_backend_guard", lambda *args, **kwargs: "true")
    stage = backend.stage_backend_command(source, revision, root=root)
    staged = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", stage],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    assert staged.returncode == 0, staged.stderr

    cmdline = tmp_path / "cmdline"
    cmdline.write_text("quiet amdgpu.sched_policy=2\n", encoding="utf-8")
    diagnostic = build_steamos_amdgpu_diagnostic_command(
        script=root / "bc250-audio-fix" / "patch-driver.sh",
        cmdline_path=cmdline,
        backend_guard="true",
    )
    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", diagnostic],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "XDG_RUNTIME_DIR": str(tmp_path),
        },
    )

    assert result.returncode == 0, result.stderr
    assert "scheduler policy: configured and active" in result.stdout
    assert "AMDGPU module and scheduler policy are active for this boot" in result.stdout


def test_stage_builder_rejects_non_immutable_revision_and_unsafe_subtree(tmp_path):
    with pytest.raises(ValueError, match="40-character Git revision"):
        backend.stage_backend_command(tmp_path, "main")
    with pytest.raises(ValueError, match="relative toolkit subtree"):
        backend.stage_backend_command(tmp_path, "a" * 40, subtree="../outside")
    with pytest.raises(ValueError, match="reviewed bc250-audio-fix subtree"):
        backend.stage_backend_command(tmp_path, "a" * 40, subtree="other-toolkit")


def test_protected_backend_guard_requires_a_root_owned_nonwritable_complete_tree():
    guard = backend.protected_backend_guard(reviewed_revision="a" * 40)
    assert "-type l" in guard
    assert "! -uid 0" in guard
    assert "-perm /022" in guard
    assert "bc250-audio-fix/patch-driver.sh" in guard
    assert "bc250-audio-fix/boot-config.sh" in guard
    assert "bc250-audio-fix/build-env.sh" in guard
    assert "bc250-audio-fix/cleanup-other-slot.sh" in guard
    assert "bc250-update-persistence.sh" in guard
    assert "bc250-storage.sh" in guard
    assert ".bc250-control-center-reviewed-revision" in guard
    assert "a" * 40 in guard
    assert "sudo test -x" in guard
    assert "ResourceTools" not in guard


def test_diagnostic_refuses_a_staged_backend_from_an_old_reviewed_revision(tmp_path):
    root = tmp_path / "protected" / "backend"
    root.mkdir(parents=True)
    audio = root / "bc250-audio-fix"
    audio.mkdir()
    script = audio / "patch-driver.sh"
    boot = audio / "boot-config.sh"
    for path in (script, boot):
        path.write_text("#!/usr/bin/bash\necho SHOULD_NOT_RUN\n", encoding="utf-8")
        path.chmod(0o755)
    (root / ".bc250-control-center-reviewed-revision").write_text(
        "b" * 40 + "\n", encoding="utf-8"
    )
    cmdline = tmp_path / "cmdline"
    cmdline.write_text("quiet amdgpu.sched_policy=2\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "sudo").write_text(
        "#!/usr/bin/bash\n"
        "case \"${1:-}\" in stat) echo 0; exit 0 ;; find) exit 0 ;; esac\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    (fake_bin / "sudo").chmod(0o755)
    command = build_steamos_amdgpu_diagnostic_command(
        script=script,
        cmdline_path=cmdline,
        backend_guard=backend.protected_backend_guard(
            root, reviewed_revision="a" * 40
        ),
    )
    result = subprocess.run(
        ["/usr/bin/bash", "-Eeuo", "pipefail", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        env=os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}", "XDG_RUNTIME_DIR": str(tmp_path)},
    )

    assert result.returncode == 39
    assert "protected SteamOS AMDGPU backend is unavailable or untrusted" in result.stdout
    assert "SHOULD_NOT_RUN" not in result.stdout


def test_health_backend_status_requires_exact_protected_revision(tmp_path, monkeypatch):
    root = tmp_path / "protected" / "backend"
    root.mkdir(parents=True)
    audio = root / "bc250-audio-fix"
    audio.mkdir()
    for name in ("patch-driver.sh", "boot-config.sh"):
        path = audio / name
        path.write_text("#!/usr/bin/bash\n", encoding="utf-8")
        path.chmod(0o755)
    marker = root / ".bc250-control-center-reviewed-revision"
    marker.write_text("a" * 40 + "\n", encoding="ascii")
    # Temporary test files cannot be root-owned.  Isolate the ownership
    # predicate so this test still exercises marker parsing and exact revision
    # matching without inspecting a host protected path.
    monkeypatch.setattr(backend, "_protected_path", lambda *_args, **_kwargs: True)

    assert backend.protected_backend_status_ready(root, reviewed_revision="a" * 40) == (
        True, "protected staged backend matches the reviewed revision"
    )
    ready, reason = backend.protected_backend_status_ready(root, reviewed_revision="b" * 40)
    assert ready is False
    assert "does not match" in reason


def test_health_backend_status_rejects_an_unprotected_intermediate_directory(tmp_path, monkeypatch):
    root = tmp_path / "protected" / "backend"
    audio = root / "bc250-audio-fix"
    audio.mkdir(parents=True)
    for name in ("patch-driver.sh", "boot-config.sh"):
        path = audio / name
        path.write_text("#!/usr/bin/bash\n", encoding="utf-8")
        path.chmod(0o755)
    (root / ".bc250-control-center-reviewed-revision").write_text(
        "a" * 40 + "\n", encoding="ascii"
    )

    def protected(path, **_kwargs):
        return Path(path).name != "bc250-audio-fix"

    monkeypatch.setattr(backend, "_protected_path", protected)
    ready, reason = backend.protected_backend_status_ready(
        root, reviewed_revision="a" * 40
    )

    assert ready is False
    assert "directory" in reason
    assert "bc250-audio-fix" in reason


def test_health_backend_status_rejects_an_oversized_revision_marker(tmp_path, monkeypatch):
    root = tmp_path / "protected" / "backend"
    root.mkdir(parents=True)
    audio = root / "bc250-audio-fix"
    audio.mkdir()
    for name in ("patch-driver.sh", "boot-config.sh"):
        (audio / name).write_text("#!/usr/bin/bash\n", encoding="utf-8")
    (root / ".bc250-control-center-reviewed-revision").write_text(
        "a" * 200, encoding="ascii"
    )
    monkeypatch.setattr(backend, "_protected_path", lambda *_args, **_kwargs: True)

    ready, reason = backend.protected_backend_status_ready(
        root, reviewed_revision="a" * 40
    )

    assert ready is False
    assert "bounded format" in reason
