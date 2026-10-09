"""The BC-250 VA-API driver: who is offered it, what is installed, what runs."""

from __future__ import annotations

import subprocess

import pytest

from bc250cc.infrastructure import vaapi_video as vaapi


@pytest.fixture
def paths(tmp_path, monkeypatch):
    runtime = tmp_path / "var/lib/bc250-control-center/vaapi"
    monkeypatch.setattr(vaapi, "RUNTIME", runtime)
    monkeypatch.setattr(vaapi, "DRIVER", runtime / "bc250_drv_video.so")
    monkeypatch.setattr(vaapi, "MANIFEST", runtime / "VERSION")
    monkeypatch.setattr(vaapi, "ENV_FILE", tmp_path / "etc/environment.d/90-bc250-control-center-vaapi.conf")
    foreign = (tmp_path / "etc/environment.d/99-bc250.conf", tmp_path / "etc/environment.d/90-bc250-video-codec.conf")
    monkeypatch.setattr(vaapi, "FOREIGN_FILES", foreign)
    return tmp_path


def _install(paths, version=vaapi.VERSION, driver=True):
    vaapi.RUNTIME.mkdir(parents=True)
    if driver:
        vaapi.DRIVER.write_bytes(b"\x7fELF")
    vaapi.MANIFEST.write_text(f"VERSION={version}\n")
    vaapi.ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    vaapi.ENV_FILE.write_text(f"{vaapi.MARKER}\nLIBVA_DRIVER_NAME=bc250\n")


def _state(**kwargs):
    defaults = {"family": "bazzite", "environ": {}, "cmdline": "quiet", "supported": (True, "")}
    return vaapi.vaapi_state(**{**defaults, **kwargs})


@pytest.mark.parametrize("family", ["steamos", "bazzite", "arch", "cachyos", "manjaro", "fedora", "debian", "ubuntu"])
def test_every_supported_family_is_offered_it(family):
    assert vaapi.vaapi_supported(family=family, machine="x86_64", glibc=(2, 41), bc250=True) == (True, "")


def test_what_is_not_offered_says_why():
    assert "BC-250" in vaapi.vaapi_supported(family="arch", machine="x86_64", glibc=(2, 41), bc250=False)[1]
    assert "x86_64" in vaapi.vaapi_supported(family="arch", machine="aarch64", glibc=(2, 41), bc250=True)[1]
    assert "Offered on" in vaapi.vaapi_supported(family="gentoo", machine="x86_64", glibc=(2, 41), bc250=True)[1]
    assert "2.38" in vaapi.vaapi_supported(family="debian", machine="x86_64", glibc=(2, 36), bc250=True)[1]


def test_states_from_files_and_the_session(paths):
    assert _state()["state"] == "not-installed"
    _install(paths)
    assert _state()["state"] == "relogin-required"
    assert _state(environ={"LIBVA_DRIVER_NAME": "bc250"})["state"] == "active"
    vaapi.MANIFEST.write_text("VERSION=0.4.0\n")
    assert _state()["state"] == "outdated"
    vaapi.DRIVER.unlink()
    assert _state()["state"] == "invalid"


def test_another_installer_or_the_hardware_block_keeps_it_away(paths):
    vaapi.FOREIGN_FILES[1].parent.mkdir(parents=True)
    vaapi.FOREIGN_FILES[1].write_text("LIBVA_DRIVER_NAME=bc250\n")
    state = _state()
    assert state["state"] == "managed-elsewhere" and state["foreign"]
    vaapi.FOREIGN_FILES[1].unlink()
    assert _state(cmdline="quiet amdgpu.bc250_vcn=1")["state"] == "hardware-vcn"


@pytest.mark.parametrize("action", ["install", "test", "uninstall"])
@pytest.mark.parametrize("family", ["steamos", "bazzite", "arch", "debian"])
def test_every_workflow_is_valid_bash(action, family):
    command = vaapi.build_vaapi_command(action, family=family)
    subprocess.run(["bash", "-n"], input=command, text=True, check=True)


def test_the_install_builds_the_reviewed_source_and_checks_it_before_switching_on():
    command = vaapi.build_vaapi_command("install", family="bazzite")
    assert vaapi.REVIEWED_COMMIT in command and vaapi.ARCHIVE_SHA256 in command
    assert "-DBC250_WITH_X264=OFF" in command
    assert "-DBC250_WITH_X265=OFF" not in command, "upstream links a broken driver without it"
    probe = command.index("bc250-vaapi-probe.py")
    assert probe < command.index('echo "== Installing =="') < command.index(f"sudo tee {vaapi.ENV_FILE}")
    # Upstream's system-wide extras stay out.
    for unwanted in ("OMP_NUM_THREADS", "usroverlay", "dkms", "radeonsi_drv_video.so", "99-bc250.conf\n"):
        assert unwanted not in command
    assert str(vaapi.KEEP_FILE) not in command


def test_steamos_keeps_the_switch_across_updates_and_asks_for_a_password_first():
    command = vaapi.build_vaapi_command("install", family="steamos")
    assert str(vaapi.KEEP_FILE) in command
    assert "bc250_require_password" in command
    assert "pacman" not in command, "SteamOS ships Podman"


def test_a_mutable_system_without_podman_gets_it_from_its_own_packages():
    assert "pacman -S --needed --noconfirm podman" in vaapi.build_vaapi_command("install", family="cachyos")
    assert "apt-get install -y podman" in vaapi.build_vaapi_command("install", family="ubuntu")
    assert "dnf install -y podman" in vaapi.build_vaapi_command("install", family="fedora")


def test_removal_only_touches_its_own_files():
    command = vaapi.build_vaapi_command("uninstall", family="steamos")
    assert vaapi.MARKER in command
    assert f"sudo rm -rf {vaapi.RUNTIME}" in command
    assert str(vaapi.KEEP_FILE) in command


def test_unknown_actions_are_refused():
    with pytest.raises(ValueError):
        vaapi.build_vaapi_command("enable; rm -rf /", family="arch")
