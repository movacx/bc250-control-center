"""Ubuntu and Fedora draw the BC-250 desktop on the CPU until Mesa 26.1: who is told, and the way out."""

from __future__ import annotations

import subprocess

import pytest

from bc250cc.infrastructure import mesa_desktop as module
from bc250cc.infrastructure.mesa_desktop import (
    MESA_PACKAGES,
    PPA_FINGERPRINT,
    build_mesa_ppa_command,
    mesa_desktop_state,
    os_release_fields,
    ubuntu_codename,
)
from tests.distributions.test_debian_kernel_upgrade import DPKG_STUB

UBUNTU = {"ubuntu": "noble"}
NOBLE = {"ID": "ubuntu", "ID_LIKE": "debian", "VERSION_CODENAME": "noble", "UBUNTU_CODENAME": "noble"}
MINT = {"ID": "linuxmint", "ID_LIKE": "ubuntu debian", "VERSION_CODENAME": "wilma", "UBUNTU_CODENAME": "noble"}


def _state(**overrides):
    values = {
        "family": "ubuntu", "distro_id": "ubuntu", "mesa_version": "25.2.8-0ubuntu0.24.04.4", "fields": NOBLE,
    }
    return mesa_desktop_state(**{**values, **overrides})


def test_ubuntu_with_a_mesa_older_than_26_1_is_offered_the_ppa():
    state = _state()
    assert state["offered"] is True
    assert (state["route"], state["action"], state["codename"]) == ("ppa", "mesa_ppa_install", "noble")
    assert state["minimum"] == "26.1"


def test_a_derivative_takes_the_ubuntu_codename_not_its_own():
    state = _state(distro_id="linuxmint", fields=MINT)
    assert (state["route"], state["codename"]) == ("ppa", "noble")


def test_a_derivative_is_recognised_by_what_it_is_like():
    state = _state(distro_id="somespin", fields={**MINT, "ID": "somespin"})
    assert state["route"] == "ppa"


@pytest.mark.parametrize(
    ("mesa", "offered"),
    [("25.0.7-2+deb13u1", True), ("25.2.8-0ubuntu0.24.04.4", True), ("26.0.8-1ubuntu0.3", True),
     ("26.1.0-1", False), ("26.2.4~kisak1~n", False), ("", False)],
)
def test_only_a_mesa_older_than_26_1_is_replaced(mesa, offered):
    assert _state(mesa_version=mesa)["offered"] is offered


def test_fedora_is_told_to_upgrade_the_release_and_given_nothing_to_run():
    state = _state(family="fedora", distro_id="fedora", mesa_version="25.3.6", fields={"ID": "fedora"})
    assert state["offered"] is True
    assert (state["route"], state["action"]) == ("release", "")
    assert _state(family="fedora", distro_id="fedora", mesa_version="26.2.4", fields={})["offered"] is False


@pytest.mark.parametrize("kwargs", [
    {"family": "bazzite", "distro_id": "bazzite", "immutable": True},
    {"family": "arch", "distro_id": "arch", "fields": {"ID": "arch"}},
    {"family": "steamos", "distro_id": "steamos", "fields": {"ID": "steamos"}},
])
def test_other_systems_are_not_told(kwargs):
    state = _state(**kwargs)
    assert state["offered"] is False and state["reason"]


def test_debian_is_offered_the_backports_mesa_only_when_its_kernel_card_has_nothing_to_install():
    debian = {"family": "debian", "distro_id": "debian", "mesa_version": "25.0.7-2+deb13u1", "fields": {"ID": "debian"}}
    only_mesa = mesa_desktop_state(**debian, debian_upgrade={"install_mesa": True, "install_kernel": False})
    assert (only_mesa["route"], only_mesa["action"]) == ("backports", "debian_kernel_install")
    both = mesa_desktop_state(**debian, debian_upgrade={"install_mesa": True, "install_kernel": True})
    assert both["offered"] is False, "the kernel card already carries Mesa"
    assert mesa_desktop_state(**debian)["offered"] is False


def test_os_release_is_read_unquoted():
    text = 'ID=linuxmint\nID_LIKE="ubuntu debian"\nUBUNTU_CODENAME=noble\nVERSION_CODENAME=wilma\n'
    fields = os_release_fields(text)
    assert fields["ID_LIKE"] == "ubuntu debian" and ubuntu_codename(fields) == "noble"
    assert ubuntu_codename({"VERSION_CODENAME": "Resolute"}) == "resolute"


# --- the workflow -------------------------------------------------------------------------------

def test_the_command_is_valid_shell_and_never_uses_add_apt_repository():
    command = build_mesa_ppa_command("install", "noble")
    assert subprocess.run(["bash", "-n"], input=command, text=True, capture_output=True).returncode == 0
    assert "add-apt-repository" not in command


def test_the_key_is_checked_against_the_pinned_fingerprint_before_anything_is_written(tmp_path):
    source, key = tmp_path / "kisak.sources", tmp_path / "kisak.asc"
    command = build_mesa_ppa_command("install", "noble", source=source, key=key)
    assert PPA_FINGERPRINT in command
    check = command.index(f"= {PPA_FINGERPRINT} ]")
    assert check < command.index("sudo tee") and check < command.index("sudo install -D")
    assert command.index("apt-get install -s") < command.index("apt-get install -y $packages")


@pytest.mark.parametrize("action", ["", "remove", "../x"])
def test_unknown_actions_are_refused(action):
    with pytest.raises(ValueError):
        build_mesa_ppa_command(action, "noble")


@pytest.mark.parametrize("codename", ["", "no ble", "noble;reboot", "../x", "24.04"])
def test_a_codename_that_is_not_a_plain_word_is_refused(codename):
    with pytest.raises(ValueError):
        build_mesa_ppa_command("install", codename)


def _run(tmp_path, *, fingerprint=PPA_FINGERPRINT, release_published=True, installable=True, has_32=False,
         candidate="26.2.4~kisak1~n", existing_ppa=False):
    """Run the real script with stubbed sudo, curl, gpg, apt-get, apt-cache, dpkg and dpkg-query."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"
    stubs = {
        "sudo": 'echo "sudo $*" >> "$LOG"; if [ "${1:-}" = -v ]; then exit 0; fi; exec "$@"',
        "curl": (
            'case "$*" in\n'
            '  *-fsI*) [ "$PUBLISHED" = 1 ]; exit $?;;\n'
            '  *-o*) out="${@: -1}"; echo "KEY" > "$out";;\n'
            "esac"
        ),
        "gpg": 'echo "pub:-:4096:1:ABCD:::"; echo "fpr:::::::::$FPR:"',
        "apt-get": (
            'if [ "$1" = install ] && [ "$2" = -s ]; then [ "$INSTALLABLE" = 1 ]; exit $?; fi\n'
            'echo "apt-get $*" >> "$LOG"'
        ),
        "apt-cache": 'echo "  Candidate: $CANDIDATE"',
        "dpkg-query": '[ "$HAS32" = 1 ]',
    }
    for name, body in stubs.items():
        (bin_dir / name).write_text(f"#!/bin/bash\n{body}\n")
        (bin_dir / name).chmod(0o755)
    (bin_dir / "dpkg").write_text(DPKG_STUB)
    (bin_dir / "dpkg").chmod(0o755)
    source, key = tmp_path / "kisak.sources", tmp_path / "kisak.asc"
    command = build_mesa_ppa_command("install", "noble", source=source, key=key)
    # An existing source file, as add-apt-repository would have left it.
    apt = tmp_path / "apt"
    apt.mkdir(exist_ok=True)
    if existing_ppa:
        (apt / "kisak.list").write_text("deb https://ppa.launchpadcontent.net/kisak/kisak-mesa/ubuntu noble main\n")
    command = command.replace("/etc/apt/sources.list /etc/apt/sources.list.d", str(apt))
    script = tmp_path / "run.sh"
    script.write_text(command)
    log.write_text("")
    result = subprocess.run(
        ["bash", str(script)],
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin", "LOG": str(log), "FPR": fingerprint,
            "PUBLISHED": "1" if release_published else "0", "INSTALLABLE": "1" if installable else "0",
            "HAS32": "1" if has_32 else "0", "CANDIDATE": candidate,
        },
        capture_output=True, text=True,
    )
    return result, log.read_text(), source, key


def test_the_ppa_is_added_with_its_key_and_mesa_is_installed_from_it(tmp_path):
    result, calls, source, key = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    written = source.read_text()
    assert "URIs: https://ppa.launchpadcontent.net/kisak/kisak-mesa/ubuntu/" in written
    assert "Suites: noble" in written and f"Signed-By: {key}" in written
    assert key.is_file()
    installs = [line for line in calls.splitlines() if line.startswith("apt-get install -y ")]
    assert installs[-1] == "apt-get install -y " + " ".join(MESA_PACKAGES)


def test_the_way_back_names_the_ubuntu_archive_for_every_package(tmp_path):
    """-t does not lower an installed version once the source is gone; pkg/release does (checked with apt)."""
    result, *_ = _run(tmp_path, has_32=True)
    back = [line for line in result.stdout.splitlines() if "apt-get install --allow-downgrades" in line]
    assert len(back) == 1
    for name in (*MESA_PACKAGES, *(f"{name}:i386" for name in MESA_PACKAGES)):
        assert f" {name}/noble-updates" in back[0]
    assert "-t noble-updates" not in back[0]


def test_a_key_with_another_fingerprint_is_refused_and_nothing_is_written(tmp_path):
    result, calls, source, key = _run(tmp_path, fingerprint="0" * 40)
    assert result.returncode == 30
    assert "not the pinned one" in result.stdout
    assert not source.exists() and not key.exists()
    assert "apt-get install -y " + " ".join(MESA_PACKAGES) not in calls


def test_a_release_the_ppa_does_not_publish_for_stops_before_anything_is_written(tmp_path):
    result, calls, source, key = _run(tmp_path, release_published=False)
    assert result.returncode == 29
    assert "has no packages for noble" in result.stdout
    assert not source.exists()


def test_an_existing_ppa_is_reused_not_added_twice(tmp_path):
    result, calls, source, key = _run(tmp_path, existing_ppa=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not source.exists() and not key.exists()


def test_mesa_the_system_cannot_take_changes_nothing(tmp_path):
    result, calls, *_ = _run(tmp_path, installable=False)
    assert result.returncode == 29
    assert "Nothing was changed" in result.stdout
    assert "apt-get install -y " + " ".join(MESA_PACKAGES) not in calls


def test_a_candidate_older_than_26_1_is_not_installed(tmp_path):
    result, calls, *_ = _run(tmp_path, candidate="25.2.8-0ubuntu0.24.04.4")
    assert result.returncode == 29
    assert "older than 26.1" in result.stdout


def test_steams_32_bit_mesa_moves_with_the_64_bit_one(tmp_path):
    result, calls, *_ = _run(tmp_path, has_32=True)
    assert result.returncode == 0, result.stdout + result.stderr
    installs = [line for line in calls.splitlines() if line.startswith("apt-get install -y ")]
    assert f"{MESA_PACKAGES[0]}:i386" in installs[-1] and f"{MESA_PACKAGES[-1]}:i386" in installs[-1]


# --- wiring -------------------------------------------------------------------------------------

def _repository(monkeypatch, tmp_path, *, family="debian", distro_id="ubuntu", mesa="25.2.8-0ubuntu0.24.04.4"):
    from tests.infrastructure.test_upstream_preparation_routes import _repository_for

    release = tmp_path / "os-release"
    release.write_text("ID=ubuntu\nUBUNTU_CODENAME=noble\nVERSION_CODENAME=noble\n")
    monkeypatch.setattr(module, "OS_RELEASE", release)
    monkeypatch.setattr(module, "installed_mesa_version", lambda _family: mesa)
    calls: list[tuple[str, str]] = []
    return _repository_for(family, calls, distro_id=distro_id), calls


def test_the_terminal_gets_the_ppa_workflow_for_the_release_in_os_release(monkeypatch, tmp_path):
    repository, calls = _repository(monkeypatch, tmp_path)
    assert repository.gestionar_mesa_desktop("install") == "terminal"
    command, title = calls[0]
    assert "Suites: noble" in command and "Mesa" in title


def test_nothing_is_run_where_the_ppa_is_not_the_route(monkeypatch, tmp_path):
    repository, calls = _repository(monkeypatch, tmp_path, family="fedora", distro_id="fedora", mesa="25.3.6")
    with pytest.raises(RuntimeError):
        repository.gestionar_mesa_desktop("install")
    assert calls == []
