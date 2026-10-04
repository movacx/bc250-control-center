"""Debian 13 cannot drive the BC-250 GPU: the backports kernel is the way out."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure.debian_kernel_upgrade import (
    build_debian_kernel_command,
    debian_kernel_upgrade_state,
    os_release_codename,
)

DEBIAN_13 = {"family": "debian", "distro_id": "debian", "kernel": "6.12.111+deb13-amd64", "codename": "trixie"}


def _boot(tmp_path, *names):
    for name in names:
        (tmp_path / f"vmlinuz-{name}").write_text("")
    return tmp_path


def test_debian_13_on_the_stock_kernel_is_offered_the_backports_kernel(tmp_path):
    state = debian_kernel_upgrade_state(**DEBIAN_13, boot_dir=_boot(tmp_path, "6.12.111+deb13-amd64"))
    assert state["offered"] is True
    assert state["state"] == "available"
    assert state["codename"] == "trixie"


def test_an_installed_newer_kernel_waits_for_a_restart(tmp_path):
    boot = _boot(tmp_path, "6.12.111+deb13-amd64", "7.1.13+bpo-amd64")
    state = debian_kernel_upgrade_state(**DEBIAN_13, boot_dir=boot)
    assert state["offered"] is True
    assert state["state"] == "reboot-required"


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"kernel": "7.1.13+bpo-amd64"}, "already new enough"),
        ({"kernel": "6.14.0-1-amd64"}, "already new enough"),
        ({"codename": "bookworm"}, "no backports kernel"),
        ({"distro_id": "ubuntu", "family": "debian"}, "Only Debian"),
        ({"distro_id": "linuxmint", "family": "debian"}, "Only Debian"),
        ({"family": "fedora", "distro_id": "fedora"}, "Only Debian"),
        ({"kernel": "6.12.0-bc250"}, "BC-250 kernel"),
        ({"kernel": ""}, "could not be read"),
    ],
)
def test_other_systems_are_not_offered_it(tmp_path, overrides, reason):
    state = debian_kernel_upgrade_state(**{**DEBIAN_13, **overrides}, boot_dir=tmp_path)
    assert state["offered"] is False
    assert state["state"] == "not-offered"
    assert reason in state["reason"]


def test_image_based_systems_are_not_offered_it(tmp_path):
    state = debian_kernel_upgrade_state(**DEBIAN_13, boot_dir=tmp_path, immutable=True)
    assert state["offered"] is False


def test_codename_is_read_from_os_release():
    assert os_release_codename('ID=debian\nVERSION_CODENAME=trixie\n') == "trixie"
    assert os_release_codename('VERSION_CODENAME="Trixie"\n') == "trixie"
    assert os_release_codename("ID=debian\n") == ""


def test_the_command_adds_backports_and_installs_from_it(tmp_path):
    source = tmp_path / "bc250.sources"
    command = build_debian_kernel_command("install", "trixie", source=source)
    assert "Suites: trixie-backports" in command
    assert "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" in command
    assert 'packages="linux-image-amd64 linux-headers-amd64 firmware-amd-graphics"' in command
    # An older backports kernel must stop the run before anything is installed.
    assert command.index("dpkg --compare-versions") < command.index("apt-get install -y")
    # Nothing is removed and no kernel is purged.
    assert "remove" not in command and "purge" not in command


def test_the_command_is_valid_shell():
    command = build_debian_kernel_command("install", "trixie")
    result = subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def _run_workflow(tmp_path, *, candidate, meta_installable=True, complete=()):
    """Run the real script with a stubbed sudo, apt-get, apt-cache and keyring.

    ``complete`` lists the concrete kernel versions a simulated install accepts.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    stubs = {
        "sudo": 'echo "sudo $*" >> "$LOG"; if [ "${1:-}" = -v ]; then exit 0; fi; exec "$@"',
        "apt-get": (
            'if [ "$1" = install ] && [ "$2" = -s ]; then\n'
            '  case "$*" in *linux-image-amd64*) [ "$META" = 1 ]; exit $?;; esac\n'
            '  for v in $COMPLETE; do case "$*" in *"linux-image-$v+deb13-amd64"*) exit 0;; esac; done\n'
            "  exit 100\n"
            "fi\n"
            'echo "apt-get $*" >> "$LOG"'
        ),
        "apt-cache": (
            'case "$1" in\n'
            '  madison) echo "linux-image-amd64 | $CANDIDATE | http://deb.debian.org/debian trixie-backports/main amd64 Packages";;\n'
            '  pkgnames) for v in 7.1.13 7.1.8 6.12.111 6.19.14; do echo "linux-image-$v+deb13-amd64"; done;'
            ' echo linux-image-7.1.8+deb13-amd64-unsigned; echo linux-image-7.1.8+deb13-rt-amd64;;\n'
            "esac"
        ),
    }
    for name, body in stubs.items():
        (bin_dir / name).write_text(f"#!/bin/bash\n{body}\n")
        (bin_dir / name).chmod(0o755)
    command = build_debian_kernel_command("install", "trixie", source=tmp_path / "bc250.sources")
    # The keyring is a real system file; drop that one guard for the dry run.
    command = command.replace("test -r /usr/share/keyrings/debian-archive-keyring.gpg || ", "true || ")
    # ...and the search for an existing backports source must not see this machine's.
    command = command.replace("/etc/apt/sources.list /etc/apt/sources.list.d", str(tmp_path / "apt"))
    script = tmp_path / "run.sh"
    script.write_text(command)
    log.write_text("")
    result = subprocess.run(
        ["bash", str(script)],
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin", "LOG": str(log), "CANDIDATE": candidate,
            "META": "1" if meta_installable else "0", "COMPLETE": " ".join(complete),
        },
        capture_output=True, text=True,
    )
    return result, log.read_text()


def test_the_command_stops_when_the_backports_kernel_is_too_old(tmp_path):
    result, calls = _run_workflow(tmp_path, candidate="6.12.57-1~bpo12+1")
    assert result.returncode == 29
    assert "apt-get install" not in calls


def test_the_command_installs_the_meta_package_when_it_is_complete(tmp_path):
    result, calls = _run_workflow(tmp_path, candidate="7.1.13-1~bpo13+1")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "apt-get install -y -t trixie-backports linux-image-amd64 linux-headers-amd64 firmware-amd-graphics" in calls
    written = (tmp_path / "bc250.sources").read_text()
    assert "Suites: trixie-backports" in written
    assert "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" in written


def test_the_command_falls_back_to_the_newest_complete_kernel(tmp_path):
    """The mirror published the meta package before its dependencies (seen in real use)."""
    result, calls = _run_workflow(
        tmp_path, candidate="7.1.13-1~bpo13+1", meta_installable=False, complete=("7.1.8", "6.19.14")
    )
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [line for line in calls.splitlines() if line.startswith("apt-get install")]
    assert installs == [
        "apt-get install -y -t trixie-backports "
        "linux-image-7.1.8+deb13-amd64 linux-headers-7.1.8+deb13-amd64 firmware-amd-graphics"
    ]


def test_the_fallback_never_picks_a_kernel_older_than_the_minimum(tmp_path):
    result, calls = _run_workflow(
        tmp_path, candidate="7.1.13-1~bpo13+1", meta_installable=False, complete=("6.12.111",)
    )
    assert result.returncode == 29
    assert "apt-get install" not in calls
    assert "Try again later" in result.stdout


def test_the_command_stops_when_no_kernel_is_complete(tmp_path):
    result, calls = _run_workflow(tmp_path, candidate="7.1.13-1~bpo13+1", meta_installable=False)
    assert result.returncode == 29
    assert "apt-get install" not in calls


@pytest.mark.parametrize("action", ["", "remove", "../x"])
def test_unknown_actions_are_refused(action):
    with pytest.raises(ValueError):
        build_debian_kernel_command(action, "trixie")


def test_an_unsupported_release_is_refused():
    with pytest.raises(ValueError):
        build_debian_kernel_command("install", "bookworm")


def test_the_source_path_is_quoted():
    command = build_debian_kernel_command("install", "trixie", source=Path("/tmp/a b.sources"))
    assert "'/tmp/a b.sources'" in command
