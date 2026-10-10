"""The receiver and the TV: Dolby Digital 5.1 over HDMI and HDMI-CEC.

AC-3 selects PipeWire's own AC-3 profile set for the BC-250's audio function;
CEC runs Valve's cecd, built here from one reviewed commit where the system
does not ship it. Nothing here touches real audio, udev or systemd.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bc250cc.infrastructure import accessories
from bc250cc.infrastructure.accessories import hdmi_ac3, hdmi_cec

FAMILIES = ("arch", "manjaro", "cachyos", "fedora", "bazzite", "debian", "ubuntu", "steamos")


# ------------------------------------------------------------------ AC-3


@pytest.fixture
def ac3(tmp_path, monkeypatch):
    """A BC-250 with WirePlumber 0.5 and PipeWire's AC-3 profile set."""
    monkeypatch.setattr(hdmi_ac3, "audio_function_present", lambda: True)
    monkeypatch.setattr(hdmi_ac3, "wireplumber_version", lambda output=None: (0, 5))
    monkeypatch.setattr(hdmi_ac3.shutil, "which", lambda name: f"/usr/bin/{name}")
    profile = tmp_path / "hdmi-ac3.conf"
    profile.write_text(".include default.conf\n", encoding="utf-8")
    monkeypatch.setattr(hdmi_ac3, "PROFILE_SET", profile)
    monkeypatch.setattr(hdmi_ac3, "UDEV_RULE", tmp_path / "udev" / "91-bc250-control-center-hdmi-ac3.rules")
    monkeypatch.setattr(hdmi_ac3, "FOREIGN_SYSTEM", (tmp_path / "udev" / "91-bc250-hdmi-ac3.rules",))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(hdmi_ac3, "receiver_takes_ac3", lambda: False)
    monkeypatch.setattr(hdmi_ac3, "a52_plugin_present", lambda dirs=None: True)
    monkeypatch.setattr(hdmi_ac3, "command_output", lambda argv, **kwargs: "")
    return tmp_path


def _configure(tmp_path: Path) -> None:
    rule = hdmi_ac3.UDEV_RULE
    rule.parent.mkdir(parents=True, exist_ok=True)
    rule.write_text(hdmi_ac3.UDEV_TEXT, encoding="utf-8")
    hdmi_ac3.wireplumber_path().parent.mkdir(parents=True, exist_ok=True)
    hdmi_ac3.wireplumber_path().write_text(hdmi_ac3.WIREPLUMBER_TEXT, encoding="utf-8")


def test_ac3_is_offered_only_with_the_audio_function_and_wireplumber_05():
    assert hdmi_ac3.supported("arch", version=(0, 5), audio=False)[0] is False
    ok, reason = hdmi_ac3.supported("arch", version=(0, 4), audio=True)
    assert not ok and "0.5" in reason
    assert hdmi_ac3.supported("alpine", version=(0, 5), audio=True)[0] is False


def test_the_wireplumber_version_is_read_from_its_own_banner():
    banner = "wireplumber\nCompiled with libwireplumber 0.5.17\nLinked with libwireplumber 0.5.17\n"
    assert hdmi_ac3.wireplumber_version(banner) == (0, 5)
    assert hdmi_ac3.wireplumber_version("") is None


def test_a_receiver_is_recognised_by_the_formats_its_eld_lists(tmp_path):
    card = tmp_path / "card1"
    card.mkdir()
    (card / "eld#0.0").write_text(
        "monitor_present\t\t1\neld_valid\t\t1\nsad0_coding_type\t[0x1] LPCM\n", encoding="utf-8"
    )
    assert not hdmi_ac3.receiver_takes_ac3(tmp_path)
    (card / "eld#0.1").write_text(
        "monitor_present\t\t1\nsad1_coding_type\t[0x2] AC-3\n", encoding="utf-8"
    )
    assert hdmi_ac3.receiver_takes_ac3(tmp_path)
    (card / "eld#0.1").write_text("monitor_present\t\t0\nsad1_coding_type\t[0x2] AC-3\n", encoding="utf-8")
    assert not hdmi_ac3.receiver_takes_ac3(tmp_path)


def test_ac3_states(ac3, monkeypatch):
    assert hdmi_ac3.inventory("cachyos")["state"] == "not-installed"
    _configure(ac3)
    assert hdmi_ac3.inventory("cachyos")["state"] == "installed"
    monkeypatch.setattr(
        hdmi_ac3, "command_output",
        lambda argv, **kwargs: "alsa_output.pci-0000_01_00.1.hdmi-ac3-surround" if argv[:2] == ["pactl", "get-default-sink"] else "",
    )
    assert hdmi_ac3.inventory("cachyos")["state"] == "active"
    monkeypatch.setattr(hdmi_ac3, "a52_plugin_present", lambda dirs=None: False)
    assert hdmi_ac3.inventory("bazzite")["state"] == "reboot-required"


def test_another_toolkits_ac3_setup_is_left_alone(ac3):
    foreign = hdmi_ac3.FOREIGN_SYSTEM[0]
    foreign.parent.mkdir(parents=True)
    foreign.write_text("keyboardspecialist\n", encoding="utf-8")
    assert hdmi_ac3.inventory("steamos")["state"] == "managed-elsewhere"
    assert str(foreign) in hdmi_ac3.install_command("steamos")


@pytest.mark.parametrize(("family", "expected", "absent"), [
    ("cachyos", "pacman -S --needed --noconfirm alsa-plugins ffmpeg", "rpm-ostree"),
    ("fedora", "dnf install -y alsa-plugins-a52", "pacman"),
    ("debian", "libasound2-plugins", "pacman"),
    ("bazzite", "rpm-ostree install --idempotent alsa-plugins-a52", "dnf install"),
])
def test_ac3_installs_the_distributions_own_encoder(ac3, family, expected, absent):
    command = hdmi_ac3.install_command(family)
    assert expected in command and absent not in command
    assert "/etc/alsa/conf.d/60-a52-encoder.conf" in command
    assert "ACP_PROFILE_SET" in command and "hdmi-ac3.conf" in command
    assert "api.alsa.start-delay = 1536" in command
    assert "session.suspend-timeout-seconds = 3600" in command


def test_steamos_keeps_the_rule_across_updates_and_installs_no_package(ac3):
    command = hdmi_ac3.install_command("steamos")
    assert str(hdmi_ac3.KEEP_FILE) in command
    assert "bc250_require_password" in command
    assert "not part of this SteamOS image" in command


def test_the_a52_link_is_only_taken_back_when_control_center_made_it(ac3):
    command = hdmi_ac3.remove_command("cachyos")
    record = str(hdmi_ac3.A52_LINK_RECORD)
    assert f"[ -f {record} ] && [ -L {hdmi_ac3.A52_LINK} ]" in command
    # The encoder packages stay: other programs may use them.
    assert "pacman -R" not in command and "apt-get remove" not in command


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to parse the scripts")
@pytest.mark.parametrize("family", FAMILIES)
def test_every_ac3_script_parses(ac3, family):
    for command in (hdmi_ac3.install_command(family), hdmi_ac3.remove_command(family)):
        assert subprocess.run(["bash", "-n"], input=command, text=True).returncode == 0
    for steamos in (True, False):
        assert subprocess.run(["sh", "-n"], input=hdmi_ac3._root_script(steamos), text=True).returncode == 0


_CARDS = """Card #46
\tName: alsa_card.pci-0000_01_00.1
\tProperties:
\t\tdevice.vendor.id = "0x1002"
\t\tdevice.product.id = "0x13ff"
\tProfiles:
\t\toutput:hdmi-stereo: Digital Stereo (HDMI) Output (sinks: 1, sources: 0, priority: 5900, available: no)
\t\toutput:hdmi-stereo-extra1: Digital Stereo (HDMI 2) Output (sinks: 1, sources: 0, priority: 5700, available: yes)
\t\toutput:hdmi-ac3-surround: Digital Surround 5.1 (HDMI/AC3) Output (sinks: 1, sources: 0, priority: 1, available: no)
\t\toutput:hdmi-ac3-surround-extra1: Digital Surround 5.1 (HDMI 2/AC3) Output (sinks: 1, sources: 0, priority: 1, available: yes)
\tActive Profile: @ACTIVE@
Card #47
\tName: alsa_card.usb-Generic
\tProperties:
\t\tdevice.product.id = "0x0b21"
\tActive Profile: output:analog-stereo
"""


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the selection")
@pytest.mark.parametrize(("active", "want", "chosen"), [
    ("output:hdmi-stereo-extra1", "ac3", "output:hdmi-ac3-surround-extra1"),
    ("output:hdmi-ac3-surround-extra1", "stereo", "output:hdmi-stereo-extra1"),
    # The port of the active profile is not connected: the connected one wins.
    ("output:hdmi-stereo", "ac3", "output:hdmi-ac3-surround-extra1"),
])
def test_the_ac3_profile_stays_on_the_port_the_sound_was_on(tmp_path, active, want, chosen):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "cards").write_text(_CARDS.replace("@ACTIVE@", active), encoding="utf-8")
    pactl = bin_dir / "pactl"
    pactl.write_text(
        "#!/bin/sh\n"
        f'case "$1 $2" in\n'
        f'  "list cards") cat {tmp_path / "cards"} ;;\n'
        f'  "list sinks") echo "1 alsa_output.pci-0000_01_00.1.x module RUNNING" ;;\n'
        f'  *) echo "$*" >> {tmp_path / "calls"} ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    pactl.chmod(0o755)
    script = hdmi_ac3._SELECT + f"\nbc250_select {want}\n"
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=30,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    calls = (tmp_path / "calls").read_text(encoding="utf-8").splitlines()
    assert calls[0] == f"set-card-profile alsa_card.pci-0000_01_00.1 {chosen}"
    assert calls[1] == "set-default-sink alsa_output.pci-0000_01_00.1.x"


# ------------------------------------------------------------------- CEC


@pytest.fixture
def cec(tmp_path, monkeypatch):
    monkeypatch.setattr(hdmi_cec, "kernel_support", lambda config_gz=None: True)
    monkeypatch.setattr(hdmi_cec, "system_cecd", lambda: False)
    monkeypatch.setattr(hdmi_cec, "CEC_CLASS", tmp_path / "cec")
    monkeypatch.setattr(hdmi_cec, "user_service_state", lambda unit: "missing")
    monkeypatch.setattr(hdmi_cec, "command_output", lambda argv, **kwargs: "")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    tools = tmp_path / "tools"
    tools.mkdir()
    return tools


def test_cec_needs_the_kernel_option():
    ok, reason = hdmi_cec.supported("arch", kernel=False)
    assert not ok and "CONFIG_DRM_DISPLAY_DP_AUX_CEC" in reason
    assert hdmi_cec.supported("arch", kernel=None)[0] is True
    assert hdmi_cec.supported("gentoo", kernel=True)[0] is False


def test_cec_adapters_come_from_the_kernels_cec_class(tmp_path):
    (tmp_path / "cec0").mkdir(parents=True)
    assert hdmi_cec.adapters(tmp_path) == ["cec0"]
    assert hdmi_cec.adapters(tmp_path / "missing") == []


def test_a_bundled_cecd_goes_through_its_states(cec, monkeypatch):
    assert hdmi_cec.inventory("arch", cec)["state"] == "not-installed"
    folder = cec / hdmi_cec.FOLDER
    folder.mkdir()
    (folder / "cecd").write_text("", encoding="utf-8")
    (folder / hdmi_cec.VERSION_MARKER).write_text("0.2.0\n", encoding="utf-8")
    assert hdmi_cec.inventory("arch", cec)["state"] == "update-available"
    (folder / hdmi_cec.VERSION_MARKER).write_text(hdmi_cec.VERSION + "\n", encoding="utf-8")
    monkeypatch.setattr(hdmi_cec, "user_service_state", lambda unit: "active")
    assert hdmi_cec.inventory("arch", cec)["state"] == "active"


def test_steamos_uses_its_own_cecd_and_keeps_steams_settings(cec, monkeypatch):
    info = hdmi_cec.inventory("steamos", cec)
    assert info["mode"] == "system" and info["state"] == "not-installed"
    command = hdmi_cec.install_command("steamos", cec)
    assert "cargo" not in command and "sudo" not in command
    assert 'osd_name = \\"BC-250\\"' in command or 'osd_name = "BC-250"' in command
    # Steam's own CEC settings decide when the TV follows the console.
    assert "wake_tv" not in command
    config = hdmi_cec.config_path()
    config.parent.mkdir(parents=True)
    config.write_text(hdmi_cec.config_text(follow_console=False), encoding="utf-8")
    monkeypatch.setattr(hdmi_cec, "command_output", lambda argv, **kwargs: "active")
    assert hdmi_cec.inventory("steamos", cec)["state"] == "active"


def test_cecd_is_built_from_the_reviewed_commit(cec):
    command = hdmi_cec.install_command("arch", cec)
    assert f"fetch -q --depth 1 {hdmi_cec.REPOSITORY}.git {hdmi_cec.REVIEWED_REVISION}" in command
    assert command.index("rev-parse HEAD") < command.index("cargo build --release --locked")
    assert hdmi_cec.MIN_RUST in command
    assert 'SUBSYSTEM=="cec", TAG+="uaccess"' in command
    assert "dbus-1/services" in command and hdmi_cec.SERVICE in command
    assert "wake_tv = true" in command and "suspend_tv = true" in command
    assert "LICENSE.linux-cec-sys" in command


def test_bazzite_builds_cecd_in_a_fedora_container_of_its_release(cec):
    command = hdmi_cec.install_command("bazzite", cec)
    assert "registry.fedoraproject.org/fedora:$bc250_fedora" in command
    assert "rpm-ostree" not in command and "pacman" not in command


def test_the_user_unit_runs_the_bundled_cecd(tmp_path):
    unit = hdmi_cec.unit_text(tmp_path / "cecd")
    assert f"ExecStart={tmp_path}/cecd/cecd -e" in unit
    assert f"BusName={hdmi_cec.BUS_NAME}" in unit


def test_removing_cec_takes_back_only_what_control_center_added(cec):
    command = hdmi_cec.remove_command("arch", cec)
    assert f"grep -qxF '{hdmi_cec.MARKER}'" in command
    assert "rm -rf --" in command and str(cec / hdmi_cec.FOLDER) in command
    steamos = hdmi_cec.remove_command("steamos", cec)
    assert "sudo" not in steamos and "rm -rf" not in steamos


def test_the_tv_test_asks_cecd_to_wake_the_tv(cec):
    command = hdmi_cec.test_command("arch", cec)
    assert f"{hdmi_cec.DAEMON_PATH} {hdmi_cec.BUS_NAME}.Daemon1 Wake" in command
    assert "no CEC adapter is connected" in command


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to parse the scripts")
@pytest.mark.parametrize("family", FAMILIES)
def test_every_cec_script_parses(cec, family):
    for command in (
        hdmi_cec.install_command(family, cec),
        hdmi_cec.remove_command(family, cec),
        hdmi_cec.test_command(family, cec),
    ):
        assert subprocess.run(["bash", "-n"], input=command, text=True).returncode == 0


def test_the_accessory_dispatch_reaches_both(ac3, cec):
    assert "hdmi-ac3.conf" in accessories.accessory_command("hdmi_ac3", "install", family="fedora", tool_dir=cec)
    assert "cecd" in accessories.accessory_command("hdmi_cec", "remove", family="fedora", tool_dir=cec)
    assert {"hdmi_ac3", "hdmi_cec"} <= set(accessories.ACCESSORIES)


def test_a_display_without_ac3_is_warned_about_before_anything_changes(ac3, monkeypatch):
    command = hdmi_ac3.install_command("cachyos")
    assert "plays it as silence" in command
    assert command.index("plays it as silence") < command.index("sudo sh -c")
    monkeypatch.setattr(hdmi_ac3, "receiver_takes_ac3", lambda: True)
    assert "plays it as silence" not in hdmi_ac3.install_command("cachyos")
