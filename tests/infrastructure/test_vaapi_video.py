"""The BC-250 VA-API driver: who is offered it, what is installed, what runs."""

from __future__ import annotations

import importlib.util
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


@pytest.mark.parametrize("action", ["install", "test", "uninstall", "flatpak", "flatpak-remove"])
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
    for unwanted in ("OMP_NUM_THREADS", "usroverlay", "dkms", "99-bc250.conf\n"):
        assert unwanted not in command
    assert str(vaapi.KEEP_FILE) not in command
    # ...and so is replacing the distribution's radeonsi: the only radeonsi file
    # is a link inside our own folder, made before it is moved into place.
    alias_lines = [line for line in command.splitlines() if "radeonsi_drv_video.so" in line]
    assert alias_lines == [
        f"sudo ln -sf bc250_drv_video.so {vaapi.RUNTIME}.new/radeonsi_drv_video.so"
    ]
    assert command.index(alias_lines[0]) < command.index(f"sudo mv {vaapi.RUNTIME}.new {vaapi.RUNTIME}")


def test_steamos_keeps_the_switch_across_updates_and_asks_for_a_password_first():
    command = vaapi.build_vaapi_command("install", family="steamos")
    assert str(vaapi.KEEP_FILE) in command
    assert "bc250_require_password" in command
    assert "pacman -S " not in command and "pacman -U" not in command, "SteamOS ships Podman: nothing is installed"


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


def _flatpak_script():
    spec = importlib.util.spec_from_file_location("bc250_vaapi_flatpak", vaapi.FLATPAK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNTIME = "/var/lib/bc250-control-center/vaapi"
LIBVA = "/var/lib/bc250-control-center/vaapi:/usr/lib/dri"


def test_flatpak_apps_get_the_folder_read_only_and_the_two_libva_variables():
    flatpak = _flatpak_script()
    text = flatpak.enable("", RUNTIME, LIBVA)
    assert text == (
        "[Context]\nfilesystems=/var/lib/bc250-control-center/vaapi:ro;\n\n"
        "[Environment]\nLIBVA_DRIVERS_PATH=" + LIBVA + "\nLIBVA_DRIVER_NAME=bc250\n"
    ) or all(line in text for line in (
        "filesystems=/var/lib/bc250-control-center/vaapi:ro;", "LIBVA_DRIVER_NAME=bc250", "LIBVA_DRIVERS_PATH=" + LIBVA,
    ))
    assert flatpak.status(text, RUNTIME, LIBVA) == {"filesystem": True, "driver_name": True, "driver_path": True}
    assert flatpak.enable(text, RUNTIME, LIBVA) == text, "turning it on twice changes nothing"


def test_the_flatpak_override_keeps_what_was_already_there():
    flatpak = _flatpak_script()
    before = (
        "[Context]\nsockets=wayland;\nfilesystems=~/Games;!/home;\n\n"
        "[Environment]\nMANGOHUD=1\n\n[Session Bus Policy]\norg.example.Foo=talk\n"
    )
    on = flatpak.enable(before, RUNTIME, LIBVA)
    assert "sockets=wayland;" in on and "MANGOHUD=1" in on and "org.example.Foo=talk" in on
    assert "filesystems=~/Games;!/home;/var/lib/bc250-control-center/vaapi:ro;" in on
    assert flatpak.disable(on, RUNTIME, LIBVA).strip() == before.strip()


def test_removing_it_leaves_no_file_behind_and_spares_a_driver_somebody_else_chose():
    flatpak = _flatpak_script()
    assert flatpak.disable(flatpak.enable("", RUNTIME, LIBVA), RUNTIME, LIBVA) == ""
    theirs = "[Environment]\nLIBVA_DRIVER_NAME=iHD\n"
    assert flatpak.disable(theirs, RUNTIME, LIBVA) == theirs


def test_a_denied_folder_is_replaced_not_left_beside_the_allowance():
    flatpak = _flatpak_script()
    text = flatpak.enable("[Context]\nfilesystems=!" + RUNTIME + ";\n", RUNTIME, LIBVA)
    assert text.count(RUNTIME) == 2 and "!" + RUNTIME not in text.split("filesystems=")[1].split("\n")[0]


def test_flatpak_state_reads_the_override(monkeypatch, tmp_path):
    flatpak = _flatpak_script()
    monkeypatch.setattr(vaapi, "RUNTIME", __import__("pathlib").Path(RUNTIME))
    on = flatpak.enable("", RUNTIME, vaapi.libva_driver_path())
    assert vaapi.flatpak_state(override_text=on, available=True) == {"available": True, "applied": True}
    assert vaapi.flatpak_state(override_text="", available=True)["applied"] is False
    assert vaapi.flatpak_state(override_text="", available=False)["available"] is False


def test_the_script_runs_end_to_end_on_a_home_of_its_own(tmp_path):
    env = {"XDG_DATA_HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    script = str(vaapi.FLATPAK_SCRIPT)
    run = lambda action: subprocess.run(  # noqa: E731
        ["python3", "-I", script, action, RUNTIME, LIBVA], env=env, capture_output=True, text=True, check=True,
    ).stdout
    assert '"driver_name": false' in run("status")
    run("enable")
    assert '"filesystem": true' in run("status") and (tmp_path / "flatpak/overrides/global").is_file()
    run("disable")
    assert not (tmp_path / "flatpak/overrides/global").exists()


def test_install_and_removal_carry_the_flatpak_override():
    install = vaapi.build_vaapi_command("install", family="arch")
    assert "bc250-vaapi-flatpak.py enable" in install
    assert install.index("bc250-vaapi-flatpak.py enable") > install.index(f"sudo tee {vaapi.ENV_FILE}")
    assert "bc250-vaapi-flatpak.py disable" in vaapi.build_vaapi_command("uninstall", family="arch")
    assert "flatpak" in vaapi.build_vaapi_command("test", family="arch")
    assert "enable" in vaapi.build_vaapi_command("flatpak", family="arch")
    assert "disable" in vaapi.build_vaapi_command("flatpak-remove", family="arch")


# ------------------------------------------------------------ 32-bit companion


@pytest.mark.parametrize("family", ["steamos", "arch", "cachyos", "manjaro"])
def test_the_32_bit_workflow_is_valid_bash_where_it_is_offered(family):
    subprocess.run(["bash", "-n"], input=vaapi.build_vaapi_command("install32", family=family), text=True, check=True)


@pytest.mark.parametrize("family", ["bazzite", "fedora", "debian", "ubuntu"])
def test_the_32_bit_driver_is_not_offered_without_a_32_bit_userland(family):
    assert vaapi.vaapi_supported32(family)[0] is False
    with pytest.raises(ValueError):
        vaapi.build_vaapi_command("install32", family=family)


def test_the_32_bit_build_is_checked_for_class_relocations_and_a_real_32_bit_start():
    command = vaapi.build_vaapi_command("install32", family="steamos")
    assert "-DBUILD_32BIT=ON" in command and vaapi.ARCHIVE_SHA256 in command, "the reviewed source, 32-bit"
    for check in ("Class: *ELF32", "TEXTREL", "bc250-vaapi-probe32", "gcc -m32"):
        assert check in command, check
    # Nothing is installed before the 32-bit program has started the driver on the real render node.
    assert command.index('bc250-vaapi-probe32" "$bc250_node"') < command.index('echo "== Installing =="')
    assert command.index("bc250_pacman_install") < command.index("-DBUILD_32BIT=ON")


def test_the_32_bit_driver_goes_beside_the_64_bit_one_and_shares_its_shaders():
    command = vaapi.build_vaapi_command("install32", family="steamos")
    assert f"{vaapi.RUNTIME}/dri32" in command
    assert 'ln -sf "../$(basename' in command, "the shaders stay in one place"
    assert f"LIBVA_DRIVERS_PATH={vaapi.RUNTIME}:{vaapi.RUNTIME}/dri32:" in command, "both folders, the 64-bit one first"


def test_steamos_gets_signed_packages_with_the_protection_put_back_and_room_checked():
    command = vaapi.build_vaapi_command("install32", family="steamos")
    for package in vaapi.LIB32_PACKAGES:
        assert package in command
    assert "bc250_require_var_space" in command and "steamos-readonly" in command
    assert "bc250_require_password" in command
    assert "sudo pacman -S --needed --noconfirm lib32" in vaapi.build_vaapi_command("install32", family="arch")
    assert "[multilib]" in vaapi.build_vaapi_command("install32", family="arch"), "Arch needs multilib on"


def test_a_driver_that_is_already_there_only_gets_its_libraries_back():
    command = vaapi.build_vaapi_command("install32", family="steamos")
    assert "its libraries are back" in command
    assert command.index("its libraries are back") < command.index("podman run")


def test_the_64_bit_update_says_it_drops_the_32_bit_driver_and_writes_the_path_without_it():
    command = vaapi.build_vaapi_command("install", family="steamos")
    assert "32-bit companion goes with this update" in command
    assert f"LIBVA_DRIVERS_PATH={vaapi.RUNTIME}:/usr/lib64/dri" in command


def test_the_search_path_names_the_32_bit_folder_only_when_it_is_there(paths):
    assert vaapi.libva_driver_path().startswith(f"{vaapi.RUNTIME}:/usr/lib64/dri")
    vaapi.driver32_dir().mkdir(parents=True)
    vaapi.driver32().write_bytes(b"\x7fELF")
    assert vaapi.libva_driver_path().startswith(f"{vaapi.RUNTIME}:{vaapi.RUNTIME}/dri32:/usr/lib64/dri")
    assert vaapi.libva_driver_path(include32=False).startswith(f"{vaapi.RUNTIME}:/usr/lib64/dri")


def test_the_32_bit_state_tells_a_missing_driver_from_one_whose_libraries_an_update_took(paths, tmp_path):
    libs = [tmp_path / "libva.so.2"]
    state = lambda **kwargs: _state(family="steamos", lib32_files=libs, **kwargs)["driver32"]["state"]  # noqa: E731
    assert state() == "not-installed"
    _install(paths)
    assert state() == "not-installed"
    vaapi.driver32_dir().mkdir(parents=True)
    vaapi.driver32().write_bytes(b"\x7fELF")
    assert state() == "needs-libs"
    libs[0].write_text("x")
    assert state() == "installed"
    assert _state(family="bazzite", lib32_files=libs)["driver32"]["state"] == "unsupported"


def test_the_flatpak_override_follows_the_path_with_the_32_bit_folder_and_leaves_with_it():
    flatpak = _flatpak_script()
    runtime = str(vaapi.RUNTIME)
    with_32 = f"{runtime}:{runtime}/dri32:/usr/lib/dri"
    on = flatpak.enable("", runtime, with_32)
    assert flatpak.status(on, runtime, with_32)["driver_path"] is True
    assert flatpak.status(on, runtime, f"{runtime}:/usr/lib/dri")["driver_path"] is False
    assert flatpak.disable(on, runtime, f"{runtime}:/usr/lib/dri") == "", "removed whichever path it was written with"


def test_the_state_says_whether_programs_that_clear_the_driver_name_can_find_it(paths, monkeypatch):
    """GPU Screen Recorder clears LIBVA_DRIVER_NAME, so libva asks for radeonsi's file name."""
    monkeypatch.setattr(vaapi, "ALIAS", vaapi.RUNTIME / "radeonsi_drv_video.so")
    _install(paths)
    assert _state(environ={"LIBVA_DRIVER_NAME": "bc250"})["alias"] is False
    (vaapi.RUNTIME / "radeonsi_drv_video.so").symlink_to("bc250_drv_video.so")
    assert _state(environ={"LIBVA_DRIVER_NAME": "bc250"})["alias"] is True


def test_the_32_bit_folder_gets_the_alias_beside_its_driver():
    command = vaapi.build_vaapi_command("install32", family="steamos")
    assert f"sudo ln -sf bc250_drv_video.so {vaapi.driver32_dir()}.new/radeonsi_drv_video.so" in command


def test_allowing_flatpak_adds_the_alias_to_a_driver_installed_without_it():
    command = vaapi.build_vaapi_command("flatpak", family="arch")
    alias = f"{vaapi.RUNTIME}/radeonsi_drv_video.so"
    assert f"if [ ! -e {alias} ]; then" in command
    assert f"sudo ln -sf bc250_drv_video.so {alias}" in command
    assert command.index(f"sudo ln -sf bc250_drv_video.so {alias}") < command.index("bc250-vaapi-flatpak.py enable")
    assert "radeonsi" not in vaapi.build_vaapi_command("flatpak-remove", family="arch")


def test_the_test_workflow_checks_the_driver_the_way_gpu_screen_recorder_asks_for_it():
    command = vaapi.build_vaapi_command("test", family="arch")
    assert f"env -u LIBVA_DRIVER_NAME LIBVA_DRIVERS_PATH={vaapi.RUNTIME}" in command
    assert "cannot find the driver yet" in command
