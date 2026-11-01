"""The Bazzite kernel-argument transaction, run for real against a pretend rpm-ostree.

Only the machine is pretended: the checks for Bazzite and an ostree boot are
skipped, ``rpm-ostree`` keeps its arguments in a file, and ``sudo`` runs what it
is given. The script itself is the one the app opens in the terminal.
"""
import os
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import bazzite_kargs
from bc250cc.infrastructure.bazzite_boot_messages import SPEC as BOOT_MESSAGES
from bc250cc.infrastructure.bazzite_smt import SPEC as SMT

RPM_OSTREE = r'''#!/bin/bash
store="$KARGS_FILE"
if [ $# -eq 1 ] && [ "$1" = kargs ]; then cat "$store"; exit 0; fi
[ "$1" = kargs ] || exit 2
shift
args=$(cat "$store")
for item in "$@"; do
  case "$item" in
    --delete-if-present=*) value=${item#--delete-if-present=}; args=$(printf '%s\n' $args | grep -Fxv -- "$value" | tr '\n' ' ');;
    --append-if-missing=*) value=${item#--append-if-missing=}; printf '%s\n' $args | grep -Fxq -- "$value" || args="$args $value";;
  esac
done
printf '%s\n' $args | tr '\n' ' ' > "$store"
'''


def _run(spec, action, tmp_path, kargs):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    store = tmp_path / "kargs"
    store.write_text(kargs, encoding="utf-8")
    (bin_dir / "rpm-ostree").write_text(RPM_OSTREE)
    (bin_dir / "sudo").write_text('#!/bin/bash\n[ "${1:-}" = -v ] && exit 0\nexec "$@"\n')
    # Everything here belongs to the invoking user: report root as the owner.
    (bin_dir / "stat").write_text(
        '#!/bin/bash\ncase "$*" in *"-c %u"*) echo 0;; *) exec /usr/bin/stat "$@";; esac\n'
    )
    for tool in bin_dir.iterdir():
        tool.chmod(0o755)
    state_dir = tmp_path / "state"
    command = bazzite_kargs.build_karg_command(spec, action)
    command = command.replace("/etc/bc250-control-center", str(state_dir))
    for check in ("grep -Eqi \"^ID=", "test -e /run/ostree-booted"):
        command = "\n".join("true" if line.startswith(check) else line for line in command.splitlines())
    result = subprocess.run(
        ["bash", "-c", command],
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "KARGS_FILE": str(store), "HOME": str(tmp_path)},
        capture_output=True, text=True, timeout=60,
    )
    return result, store.read_text(encoding="utf-8").split(), state_dir / Path(str(spec.state_file)).name


@pytest.mark.parametrize("spec", [SMT, BOOT_MESSAGES], ids=["nosmt", "loglevel"])
def test_the_argument_is_staged_and_the_image_gets_back_exactly_what_it_had(spec, tmp_path):
    original = "quiet rhgb nosmt=force loglevel=4" if spec is SMT else "quiet rhgb loglevel=4 nosmt=force"
    staged, kargs, state = _run(spec, spec.enable_action, tmp_path, original)
    assert staged.returncode == 0, staged.stdout + staged.stderr
    assert spec.argument in kargs
    # The other arguments, and the other family, are untouched.
    assert "quiet" in kargs and "rhgb" in kargs
    other = "loglevel=4" if spec is SMT else "nosmt=force"
    assert other in kargs
    assert state.read_text().splitlines()[0] == bazzite_kargs.STATE_MARKER

    restored, kargs, state = _run(spec, "restore", tmp_path, " ".join(kargs))
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert spec.argument not in kargs
    assert ("nosmt=force" if spec is SMT else "loglevel=4") in kargs
    assert not state.exists()
    assert "No automatic reboot was performed." in restored.stdout


@pytest.mark.parametrize("spec", [SMT, BOOT_MESSAGES], ids=["nosmt", "loglevel"])
def test_staging_twice_changes_nothing_and_keeps_the_first_snapshot(spec, tmp_path):
    first, kargs, state = _run(spec, spec.enable_action, tmp_path, "quiet")
    assert first.returncode == 0
    saved = state.read_text()
    again, kargs_again, _ = _run(spec, spec.enable_action, tmp_path, " ".join(kargs))
    assert again.returncode == 0
    assert "already configured" in again.stdout
    assert kargs_again == kargs
    assert state.read_text() == saved


@pytest.mark.parametrize("spec", [SMT, BOOT_MESSAGES], ids=["nosmt", "loglevel"])
def test_restore_without_a_snapshot_of_ours_refuses(spec, tmp_path):
    result, kargs, _ = _run(spec, "restore", tmp_path, "quiet")
    assert result.returncode == 66
    assert "no BC250-owned" in result.stdout
    assert kargs == ["quiet"]


def test_a_foreign_state_file_is_never_overwritten(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    foreign = state_dir / "nosmt-kargs.original"
    foreign.write_text("someone else's file\n")
    foreign.chmod(0o600)
    result, kargs, _ = _run(SMT, "disable", tmp_path, "quiet")
    assert result.returncode == 66
    assert "foreign" in result.stdout
    assert foreign.read_text() == "someone else's file\n"
    assert kargs == ["quiet"]
