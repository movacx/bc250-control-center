"""Regression coverage for the protected SteamOS AMDGPU staging boundary."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import bc250cc.infrastructure.steamos_amdgpu_backend as backend
from bc250cc.infrastructure.steamos_amdgpu import (
    build_steamos_amdgpu_diagnostic_command,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")



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
    # Upstream v0.37+ entrypoints source this hook when it exists; it must
    # never reach the root-owned copy.
    hook = source / "scripts" / "feature-tracking.sh"
    hook.parent.mkdir()
    hook.write_text("#!/bin/bash\necho TRACKED\n", encoding="utf-8")
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
    assert (root / "bc250-mesa-patches" / "libdrm-2.4.134-wrap.patch").is_file()
    assert not (root / "scripts").exists()
    assert (root / ".bc250-control-center-reviewed-revision").read_text(
        encoding="utf-8"
    ).strip() == revision
    assert not (root.parent / ".steamos-amdgpu-backend.previous").exists()


def test_stage_command_requires_every_full_install_member(tmp_path):
    command = backend.stage_backend_command(tmp_path, "a" * 40)

    assert "archive --format=tar" in command
    assert (
        "bc250-audio-fix bc250-mesh-shader.sh bc250-update-persistence.sh bc250-storage.sh "
        "bc250-mesa-patches/libdrm-2.4.134-wrap.patch |"
    ) in command
    assert " scripts" not in command.split("archive --format=tar", 1)[1].split("|", 1)[0]
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



def test_guard_requires_the_v040_members_and_refuses_the_tracking_hook():
    guard = backend.protected_backend_guard(reviewed_revision="a" * 40)
    assert "bc250-audio-fix/fetch-build-deps.sh" in guard
    assert "bc250-mesa-patches/libdrm-2.4.134-wrap.patch" in guard
    assert f"sudo test ! -e {backend.STEAMOS_AMDGPU_BACKEND_ROOT}/scripts" in guard


def _fake_staged_tree(root: Path, revision: str, members) -> None:
    root.mkdir(parents=True)
    for name in members:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/usr/bin/bash\n", encoding="utf-8")
        path.chmod(0o755)
    (root / ".bc250-control-center-reviewed-revision").write_text(revision + "\n", encoding="utf-8")


def _guard_passes(tmp_path: Path, guard: str) -> bool:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    (fake_bin / "sudo").write_text(
        "#!/usr/bin/bash\n"
        "case \"${1:-}\" in stat) echo 0; exit 0 ;; find) exit 0 ;; esac\n"
        "exec \"$@\"\n",
        encoding="utf-8",
    )
    (fake_bin / "sudo").chmod(0o755)
    result = subprocess.run(
        ["/usr/bin/bash", "-c", guard], check=False,
        env=os.environ | {"PATH": f"{fake_bin}:{os.environ['PATH']}"},
    )
    return result.returncode == 0


@pytest.mark.parametrize(("staged", "accepted"), [
    # What Control Center 1.x staged for v0.30.0: no fetch-build-deps.sh, no Mesa patch.
    ("e1563f2051727702a000b6ff6f6c524e2792aa21", True),
    ("6aee5530a07f2c1a4fd2f23c00a87986030c5b35", True),
    ("b" * 40, False),
])
def test_stock_module_rollback_accepts_the_previous_reviewed_stage_only(tmp_path, staged, accepted):
    root = tmp_path / "backend"
    old_members = [name for name in backend.BACKEND_REQUIRED_EXECUTABLES
                   if name != "bc250-audio-fix/fetch-build-deps.sh"]
    _fake_staged_tree(root, staged, old_members)
    current = "6aee5530a07f2c1a4fd2f23c00a87986030c5b35"

    assert _guard_passes(tmp_path, backend.rollback_backend_guard(current, root)) is accepted
    # Every other action keeps requiring the complete current stage.
    assert _guard_passes(tmp_path, backend.protected_backend_guard(root, reviewed_revision=current)) is False


def test_rollback_guard_refuses_a_stage_that_carries_the_tracking_hook(tmp_path):
    root = tmp_path / "backend"
    current = "6aee5530a07f2c1a4fd2f23c00a87986030c5b35"
    _fake_staged_tree(root, current, backend.ROLLBACK_REQUIRED_EXECUTABLES)
    assert _guard_passes(tmp_path, backend.rollback_backend_guard(current, root)) is True
    (root / "scripts").mkdir()
    (root / "scripts" / "feature-tracking.sh").write_text("echo TRACKED\n", encoding="utf-8")
    assert _guard_passes(tmp_path, backend.rollback_backend_guard(current, root)) is False
