import shlex
import subprocess
import time
from pathlib import Path

import pytest

from bc250cc.infrastructure import fedora_gfx1013
from bc250cc.infrastructure.fedora_gfx1013 import (
    build_fedora_gfx1013_command,
    build_progress_functions,
)
from bc250cc.infrastructure.gfx1013_compute_policy import (
    GFX1013_REVIEWED_COMMIT,
    GFX1013_UPSTREAM,
)

# Writes the files upstream's ``install.sh build`` writes, in the same order,
# without compiling anything.
FAKE_UPSTREAM = r'''#!/usr/bin/env bash
set -euo pipefail
build="$(cd -- "$(dirname -- "$0")" && pwd)/build"
pause=${FAKE_PAUSE:-0}
[[ $1 == build ]]
mkdir -p "$build/artifacts"
echo "== kernel module: building"
: > "$build/kernel-build.log"
for n in 1 2 3; do printf '  CC [M]  file%s.o\n' "$n" >> "$build/kernel-build.log"; sleep "$pause"; done
if [[ ${FAKE_FAIL:-} == kernel ]]; then
    printf 'file3.c:12:1: error: expected declaration\n' >> "$build/kernel-build.log"
    printf 'error: kernel module build failed; see %s\n' "$build/kernel-build.log" >&2
    exit 1
fi
head -c 1024 /dev/zero > "$build/artifacts/amdgpu.ko.xz"
printf '24\n' > "$build/artifacts/cu-mode"
echo "== mesa: building"
printf 'The Meson build system\n' > "$build/mesa-setup.log"
printf '[1/2] a.c.o\n[2/2] libvulkan_radeon.so\n' > "$build/mesa-build.log"
echo "build complete"
'''


def _fake_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "gfx"
    checkout.mkdir()
    installer = checkout / "install.sh"
    installer.write_text(FAKE_UPSTREAM, encoding="utf-8")
    installer.chmod(0o755)
    return checkout


def _run_build_step(checkout: Path, **environment: str) -> subprocess.CompletedProcess:
    """The build step exactly as the install workflow runs it, output piped."""
    script = "\n".join((
        "set -Eeuo pipefail",
        "trap 'kill \"${bc250_build_watch:-}\" 2>/dev/null || true' EXIT",
        fedora_gfx1013._build_with_progress(
            shlex.quote(str(checkout)), shlex.quote(str(checkout / "build"))
        ),
        'echo "BUILD STEP OK"',
    ))
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C", **environment},
    )


def test_fedora_workflow_uses_reviewed_commit_and_installs_both_required_halves(tmp_path):
    command = build_fedora_gfx1013_command("install", tmp_path / "gfx")

    assert GFX1013_UPSTREAM in command
    assert GFX1013_REVIEWED_COMMIT in command
    assert f"fetch --depth 1 origin {GFX1013_REVIEWED_COMMIT}" in command
    assert "checkout --detach --force FETCH_HEAD" in command
    assert 'test "${ID:-}" = fedora' in command
    assert 'test "${VERSION_ID:-}" = 43' not in command
    assert "rpm-ostree" in command
    assert "1002" in command and "13fe" in command
    assert "install.sh deps" in command
    assert "install.sh build" in command
    assert "install.sh install" in command
    assert "patches/mesa/series" in command
    assert "0002" in command and "0003" in command
    assert "Fedora 44 source-RPM compatibility" in command
    assert "./linux-*.tar.xz" in command
    assert "Fedora external-module trace compatibility" in command
    assert "#define TRACE_INCLUDE_PATH ." in command
    assert "local bc250_trace_header=" in command
    assert "unsupported amdgpu trace include layout" in command
    assert "refusing an unreviewed automatic edit" in command
    assert "selected for the next boot only" in command


def test_fedora_workflow_exposes_reviewed_status_and_rollback(tmp_path):
    status = build_fedora_gfx1013_command("status", tmp_path / "gfx")
    uninstall = build_fedora_gfx1013_command("uninstall", tmp_path / "gfx")

    assert "install.sh status" in status
    assert "install.sh uninstall" in uninstall
    assert "install.sh build" not in uninstall
    assert 'test "${VERSION_ID:-}" = 43' not in uninstall
    assert "rpm-ostree" in uninstall


def test_fedora_workflow_rejects_unknown_actions(tmp_path):
    with pytest.raises(ValueError, match="Unsupported Fedora GFX1013 action"):
        build_fedora_gfx1013_command("kernel-only", Path(tmp_path) / "gfx")


def test_fedora_install_asks_for_the_password_once_and_keeps_it_for_the_install(tmp_path):
    """The build outlasts sudo's cache: the install at the end asked again."""
    command = build_fedora_gfx1013_command("install", tmp_path / "gfx")

    order = [command.index(step) for step in (
        "sudo -v", "install.sh deps", "install.sh build", "install.sh install",
    )]
    assert order == sorted(order)
    assert "sudo -n -v" in command
    assert "trap 'kill \"$bc250_sudo_keepalive\" \"${bc250_build_watch:-}\"" in command
    # An orphaned sleep that still held the output pipe kept the workflow open.
    assert "while sleep 50 </dev/null >/dev/null 2>&1" in command


def test_build_progress_watches_upstreams_build_directory(tmp_path):
    """install.sh logs under ``<checkout>/build``, its ``build_root``."""
    command = build_fedora_gfx1013_command("install", tmp_path / "gfx")

    assert f"bc250_build_root={shlex.quote(str(tmp_path / 'gfx' / 'build'))}" in command
    assert command.index("bc250_build_progress &") < command.index("install.sh build")


def test_build_progress_names_the_phase_in_progress(tmp_path):
    build = tmp_path / "build"
    qbuild = shlex.quote(str(build))
    script = "\n".join((
        "set -Eeuo pipefail",
        f"build={qbuild}",
        'mkdir -p "$build/artifacts"',
        # A cancelled attempt leaves every one of these behind.
        "printf '  CC [M]  old.o\\n' > \"$build/kernel-build.log\"",
        ": > \"$build/artifacts/amdgpu.ko.xz\"",
        "printf '24\\n' > \"$build/artifacts/cu-mode\"",
        "printf 'The Meson build system\\n' > \"$build/mesa-setup.log\"",
        "printf '[652/819] old\\n' > \"$build/mesa-build.log\"",
        "touch -d '-10 minutes' \"$build\"/*.log \"$build\"/artifacts/*",
        build_progress_functions(qbuild),
        'echo "leftovers|$(bc250_build_detail)"',
        "printf '  CC [M]  a.o\\n  CC [M]  b.o\\n' > \"$build/kernel-build.log\"",
        'echo "compiling|$(bc250_build_detail)"',
        'head -c 3145728 /dev/zero > "$build/artifacts/amdgpu.ko.xz"',
        'echo "compressing|$(bc250_build_detail)"',
        "printf '24\\n' > \"$build/artifacts/cu-mode\"",
        'echo "unpacking-mesa|$(bc250_build_detail)"',
        "printf 'The Meson build system\\n' > \"$build/mesa-setup.log\"",
        'echo "configuring|$(bc250_build_detail)"',
        "printf '[1/819] a.c.o\\n[312/819] b.c.o\\n' > \"$build/mesa-build.log\"",
        'echo "mesa|$(bc250_build_detail)"',
        "printf '[0/1] Installing files\\n' >> \"$build/mesa-build.log\"",
        'echo "staging|$(bc250_build_detail)"',
    ))
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)

    seen = dict(line.split("|", 1) for line in result.stdout.splitlines())
    assert seen == {
        "leftovers": "",
        "compiling": "kernel module: 2 files compiled",
        "compressing": "kernel module: compressing amdgpu.ko, 3 MB written",
        "unpacking-mesa": "",
        "configuring": "Mesa/RADV: configuring the build",
        "mesa": "Mesa/RADV: step 312/819 compiled",
        "staging": "Mesa/RADV: staging the finished build",
    }
    assert result.stderr == ""


def test_a_quiet_build_prints_progress_while_it_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(fedora_gfx1013, "PROGRESS_INTERVAL", 1)
    result = _run_build_step(_fake_checkout(tmp_path), FAKE_PAUSE="0.8")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "    ... kernel module: " in result.stdout
    assert " files compiled (0m0" in result.stdout
    assert result.stdout.rstrip().endswith("BUILD STEP OK")


def test_the_progress_loop_does_not_hold_the_workflow_open(tmp_path):
    """The loop sleeps half a minute at a time; the build ending ends it."""
    started = time.monotonic()
    result = _run_build_step(_fake_checkout(tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert time.monotonic() - started < fedora_gfx1013.PROGRESS_INTERVAL / 2
    assert "BUILD STEP OK" in result.stdout


def test_a_failed_build_shows_the_end_of_its_own_log(tmp_path):
    checkout = _fake_checkout(tmp_path)
    build = checkout / "build"
    build.mkdir()
    stale = build / "mesa-build.log"
    stale.write_text("[652/819] from the attempt before\n", encoding="utf-8")
    subprocess.run(["touch", "-d", "-10 minutes", str(stale)], check=True)

    result = _run_build_step(checkout, FAKE_FAIL="kernel")

    assert result.returncode == 1
    assert f"---- last lines of {build}/kernel-build.log ----" in result.stdout
    assert "file3.c:12:1: error: expected declaration" in result.stdout
    assert "from the attempt before" not in result.stdout
    assert "BUILD STEP OK" not in result.stdout


def test_install_replaces_an_installed_release_only_after_the_build(tmp_path):
    """Upstream refuses to install over a release, so Install / update failed."""
    command = build_fedora_gfx1013_command("install", tmp_path / "gfx")

    replace = command.index(f"if [ -e {fedora_gfx1013.STATE_ROOT}/active.env ]")
    assert command.index("install.sh build") < replace
    assert replace < command.index("install.sh uninstall") < command.index("sudo " + shlex.quote(str(tmp_path / "gfx")) + "/install.sh install")


def test_boot_selection_actions_call_upstreams_own_commands(tmp_path):
    boot = build_fedora_gfx1013_command("boot-patched", tmp_path / "gfx")
    activate = build_fedora_gfx1013_command("activate", tmp_path / "gfx")

    assert "install.sh boot-patched" in boot
    assert "BC250_REBOOT_REQUIRED=1" in boot
    assert "install.sh activate" in activate
    for command in (boot, activate):
        assert "install.sh build" not in command
        assert "install.sh uninstall" not in command
