"""Case accessories: a Thermalright cooler LCD and Corsair hubs.

Both install a pinned upstream release that is checked against its published
SHA-256 before anything runs, and both keep running through a user service,
so they work in Game Mode, where the desktop's autostart never runs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import accessories
from bc250cc.infrastructure.accessories import _shared, openlinkhub, thermalright


def _usb(root: Path, *ids: str) -> Path:
    for index, item in enumerate(ids):
        vendor, product = item.split(":")
        device = root / f"1-{index}"
        device.mkdir(parents=True)
        (device / "idVendor").write_text(vendor + "\n", encoding="ascii")
        (device / "idProduct").write_text(product + "\n", encoding="ascii")
    return root


@pytest.fixture
def no_usb(tmp_path, monkeypatch):
    monkeypatch.setattr(_shared, "USB_DEVICES", tmp_path / "usb")
    return tmp_path / "usb"


# ------------------------------------------------------------- detection


def test_only_the_displays_trcc_registers_count_as_detected(tmp_path):
    root = _usb(tmp_path / "usb", "0416:5302", "0416:9999", "046d:c52b")
    # 0416 is Winbond: the vendor alone would match unrelated hardware.
    assert _shared.present_usb_ids(thermalright.DEVICE_IDS, root) == ["0416:5302"]


def test_any_corsair_device_counts(tmp_path):
    assert _shared.present_usb_vendor("1b1c", _usb(tmp_path / "a", "1b1c:0c3f"))
    assert not _shared.present_usb_vendor("1b1c", _usb(tmp_path / "b", "046d:c52b"))


# ----------------------------------------------------------- thermalright


def _thermalright_state(monkeypatch, *, version="", service="missing", binary=True):
    monkeypatch.setattr(thermalright, "BINARY", Path("/bin/sh") if binary else Path("/nonexistent/trcc"))
    monkeypatch.setattr(thermalright, "_installed_version", lambda route: version)
    monkeypatch.setattr(thermalright, "user_service_state", lambda unit: service)
    monkeypatch.setattr(thermalright, "_pending_layer", lambda: False)


@pytest.mark.parametrize(
    ("version", "service", "state"),
    [
        ("", "missing", "not-installed"),
        ("9.10.3-1", "active", "update-available"),
        (f"{thermalright.VERSION}-1", "enabled", "installed"),
        (f"{thermalright.VERSION}-1", "active", "active"),
    ],
)
def test_thermalright_states(monkeypatch, no_usb, version, service, state):
    _thermalright_state(monkeypatch, version=version, service=service)
    assert thermalright.inventory("cachyos")["state"] == state


def test_steamos_is_not_offered(monkeypatch, no_usb):
    assert thermalright.inventory("steamos")["state"] == "unsupported"
    with pytest.raises(RuntimeError, match="no package"):
        thermalright.install_command("steamos")


def test_bazzite_reports_the_pending_deployment(monkeypatch, no_usb):
    _thermalright_state(monkeypatch, binary=False)
    monkeypatch.setattr(thermalright, "_pending_layer", lambda: True)
    assert thermalright.inventory("bazzite")["state"] == "reboot-required"


@pytest.mark.parametrize(
    ("family", "asset", "installer"),
    [
        ("cachyos", "trcc-linux-9.11.2-1-any.pkg.tar.zst", "sudo pacman -U --needed --noconfirm"),
        ("fedora", "trcc-linux-9.11.2-1.fc44.noarch.rpm", "sudo dnf install -y"),
        ("ubuntu", "trcc-linux_9.11.2-1_all.deb", "sudo apt-get install -y"),
        ("bazzite", "trcc-linux-9.11.2-1.fc44.noarch.rpm", "sudo rpm-ostree install"),
    ],
)
def test_the_package_is_checked_before_it_is_installed(family, asset, installer):
    command = thermalright.install_command(family)
    sha256 = dict(thermalright.ASSETS.values())[asset]
    assert f"/releases/download/{thermalright.TAG}/{asset}" in command
    assert command.index(f"printf '%s  %s\\n' {sha256}") < command.index(installer)
    assert f"systemctl --user enable {thermalright.SERVICE}" in command


def test_bazzite_restarts_first_and_starts_nothing_before_it():
    command = thermalright.install_command("bazzite")
    assert "BC250_REBOOT_REQUIRED=1" in command
    assert f"sudo rpm-ostree uninstall {thermalright.PACKAGE} --install" in command
    assert f"systemctl --user restart {thermalright.SERVICE}" not in command


def test_removing_keeps_the_owners_themes():
    command = thermalright.remove_command("cachyos")
    assert f"systemctl --user disable --now {thermalright.SERVICE}" in command
    assert "sudo pacman -R --noconfirm trcc-linux" in command
    assert ".trcc-user" not in command.replace("in ~/.trcc-user were kept", "")


def test_the_configuration_window_pauses_the_display_service(monkeypatch):
    monkeypatch.setattr(thermalright, "BINARY", Path("/bin/sh"))
    monkeypatch.setattr(thermalright, "user_service_state", lambda unit: "active")
    argv = thermalright.configure_argv()
    script = argv[-1]
    assert script.index("--user stop") < script.index(" gui") < script.index("--user start")
    monkeypatch.setattr(thermalright, "user_service_state", lambda unit: "missing")
    assert thermalright.configure_argv()[-1] == "gui"


def test_the_display_unit_plays_the_detected_panel_without_a_window(tmp_path):
    """The ExecStart line, with systemd's $$ escapes undone, run for real."""
    fake = tmp_path / "trcc"
    fake.write_text(
        "#!/bin/sh\n"
        'case "$1" in detect) echo "  0416:5302  Winbond USBDISPLAY" ;; '
        'display) echo "$2 $3" ;; esac\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    line = next(item for item in thermalright.UNIT.splitlines() if item.startswith("ExecStart="))
    script = line.split("-c '", 1)[1].rsplit("'", 1)[0].replace("$$", "$").replace(str(thermalright.BINARY), str(fake))
    ran = subprocess.run(["sh", "-c", script], capture_output=True, text=True, env={"PATH": os.environ["PATH"]})
    assert ran.stdout.strip() == "play 0416:5302"
    pinned = subprocess.run(
        ["sh", "-c", script], capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "TRCC_DEVICE": "0402:3922"},
    )
    assert pinned.stdout.strip() == "play 0402:3922"
    assert "Environment=QT_QPA_PLATFORM=offscreen" in thermalright.UNIT
    assert "WantedBy=default.target" in thermalright.UNIT


# ------------------------------------------------------------ openlinkhub


@pytest.fixture
def olh(monkeypatch, tmp_path, no_usb):
    monkeypatch.setattr(openlinkhub, "supported", lambda: True)
    monkeypatch.setattr(openlinkhub, "FOREIGN_INSTALLS", (tmp_path / "opt-OpenLinkHub",))
    monkeypatch.setattr(openlinkhub, "user_unit_path", lambda unit: tmp_path / "units" / unit)
    monkeypatch.setattr(openlinkhub, "user_service_state", lambda unit: "active")
    monkeypatch.setattr(openlinkhub, "_in_group_now", lambda: True)
    tools = tmp_path / "tools"
    tools.mkdir()
    return tools


def _installed(tools: Path, version: str = openlinkhub.VERSION) -> None:
    folder = tools / openlinkhub.FOLDER
    folder.mkdir()
    (folder / "OpenLinkHub").write_text("", encoding="utf-8")
    (folder / openlinkhub.VERSION_MARKER).write_text(version, encoding="utf-8")


def test_openlinkhub_states(olh, monkeypatch):
    assert openlinkhub.inventory(olh)["state"] == "not-installed"
    _installed(olh, "0.9.1")
    assert openlinkhub.inventory(olh)["state"] == "update-available"
    (olh / openlinkhub.FOLDER / openlinkhub.VERSION_MARKER).write_text(openlinkhub.VERSION, encoding="utf-8")
    assert openlinkhub.inventory(olh)["state"] == "active"
    monkeypatch.setattr(openlinkhub, "_in_group_now", lambda: False)
    assert openlinkhub.inventory(olh)["state"] == "relogin-required"


def test_another_install_of_openlinkhub_is_left_alone(olh, tmp_path):
    (tmp_path / "opt-OpenLinkHub").write_text("", encoding="utf-8")
    assert openlinkhub.inventory(olh)["state"] == "managed-elsewhere"
    with pytest.raises(RuntimeError, match="another way"):
        openlinkhub.install_command(olh)


def test_openlinkhub_is_verified_and_skips_upstreams_chmod(olh):
    command = openlinkhub.install_command(olh)
    assert command.index(openlinkhub.ARCHIVE_SHA256) < command.index("tar -xzf")
    assert f"/releases/download/{openlinkhub.VERSION}/{openlinkhub.ARCHIVE}" in command
    # Upstream's installer strips the execute bit from /etc/udev/rules.d; the
    # only chmod allowed is the download folder's, so apt can read it.
    assert command.replace('chmod 755 "$bc250_stage"', "").count("chmod") == 0
    assert 'GROUP=\\"openlinkhub\\"' in command or 'GROUP="openlinkhub"' in command
    assert "groupadd -r openlinkhub" in command and "usermod -aG openlinkhub" in command
    assert "BC250_RELOGIN_REQUIRED=1" in command


def test_removing_openlinkhub_keeps_the_group(olh):
    command = openlinkhub.remove_command(olh)
    assert openlinkhub.RULE_PATH in command and "groupdel" not in command


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to parse the scripts")
@pytest.mark.parametrize("family", ["cachyos", "fedora", "ubuntu", "bazzite"])
def test_every_generated_script_parses(tmp_path, olh, family):
    for command in (
        thermalright.install_command(family),
        thermalright.remove_command(family),
        openlinkhub.install_command(olh),
        openlinkhub.remove_command(olh),
    ):
        assert subprocess.run(["bash", "-n"], input=command, text=True).returncode == 0


def test_the_package_dispatch(olh):
    assert "trcc" in accessories.accessory_command("thermalright", "install", family="fedora", tool_dir=olh)
    assert "OpenLinkHub" in accessories.accessory_command("corsair", "remove", family="fedora", tool_dir=olh)
    with pytest.raises(ValueError):
        accessories.accessory_command("thermalright", "configure", family="fedora", tool_dir=olh)


def test_trcc_on_a_release_without_pyside6_takes_the_package_that_brings_its_own():
    from bc250cc.infrastructure.accessories import thermalright

    command = thermalright.install_command("ubuntu")
    legacy, legacy_sha256 = thermalright.LEGACY_DEB
    assert "apt-cache show python3-pyside6.qtcore" in command
    assert legacy in command and legacy_sha256 in command
    assert 'sudo apt-get install -y "$bc250_package"' in command


def test_trcc_says_so_when_there_is_no_systemd_user_manager():
    from bc250cc.infrastructure.accessories import thermalright

    command = thermalright.install_command("arch")
    check = command.index("systemctl --user show-environment")
    assert check < command.index("systemctl --user daemon-reload")
    assert "no systemd user manager" in command and "exit 66" in command
