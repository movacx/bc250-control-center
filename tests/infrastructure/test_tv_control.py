"""Driving the TV and the receiver through cecd, and the two start/stop automations.

cecd is never started: a scripted runner stands in for busctl, and the
workflows are only parsed by bash. The calls are the ones the SteamOS toolkit's
bc250-cec.sh sends, which its author verified against real devices.
"""

from __future__ import annotations

import subprocess

import pytest

from bc250cc.infrastructure import accessories
from bc250cc.infrastructure.accessories import hdmi_cec
from bc250cc.infrastructure.accessories import hdmi_cec_control as control


class Bus:
    """A scripted cecd: records every call and answers from a table keyed by method or property."""

    def __init__(self, *, daemon=True, properties=None, replies=None, fail=()):
        self.calls: list[list[str]] = []
        self.daemon, self.properties, self.replies, self.fail = daemon, properties or {}, replies or {}, set(fail)

    def __call__(self, argv):
        self.calls.append(list(argv))
        verb = argv[3]
        if verb == "call" and argv[6] == "Ping" or "Peer" in " ".join(argv):
            return (0, "") if self.daemon else (1, "")
        if verb == "get-property":
            name = argv[-1]
            return (0, self.properties[name]) if name in self.properties else (1, "")
        method = argv[7]
        if method in self.fail:
            return 1, ""
        if method == "SendReceiveRawMessage":
            key = (argv[10], argv[11])  # first byte of the request, then the target
            return (0, self.replies.get(key, "ay 2 144 0")) if key in self.replies or argv[10] == "143" else (0, "ay 1 114")
        return 0, ""

    def methods(self):
        return [call[7] for call in self.calls if call[3] == "call" and call[6] != "Ping"]


@pytest.fixture(autouse=True)
def busctl_present(monkeypatch):
    monkeypatch.setattr(control.shutil, "which", lambda name: f"/usr/bin/{name}")


def _tv(bus, adapters=("cec0",)):
    return control.TvControl(runner=bus, adapter_list=adapters)


def test_each_action_sends_the_call_the_toolkit_verified():
    bus = Bus(properties={"AudioLogicalAddress": "y 5"})
    tv = _tv(bus)
    for action in ("tv-on", "tv-off", "switch", "volume-up", "volume-down", "mute", "amp-off"):
        assert tv.run(action) == control.Result(True, "sent")
    sent = {call[7]: call[8:] for call in bus.calls if call[3] == "call" and call[6] not in {"Ping"}}
    assert sent["Wake"] == []
    assert sent["Standby"] == ["y", "5"], "the receiver's Standby came last"
    assert sent["SetActiveSource"] == ["i", "--", "-1"]
    assert sent["VolumeUp"] == ["y", "5"] and sent["VolumeDown"] == ["y", "5"] and sent["Mute"] == ["y", "5"]
    tv_off = next(call for call in bus.calls if call[7:9] == ["Standby", "y"])
    assert tv_off[9] == "0", "the TV is logical address 0"


def test_the_device_path_follows_the_adapter():
    assert control.device_path("cec0").endswith("/Devices/Cec0")
    assert control.device_path("cec1").endswith("/Devices/Cec1")
    bus = Bus()
    _tv(bus, adapters=("cec1",)).run("tv-on")
    assert any(call[5].endswith("/Devices/Cec1") for call in bus.calls if call[3] == "call" and call[6] != "Ping")


@pytest.mark.parametrize("reported, used", [("y 9", 9), ("y 255", 5), ("y 0", 5), ("", 5)])
def test_the_receiver_address_is_what_cecd_learned_else_the_specified_one(reported, used):
    bus = Bus(properties={"AudioLogicalAddress": reported} if reported else {})
    assert _tv(bus).audio_address() == used


def test_nothing_is_sent_without_an_adapter_a_daemon_or_busctl(monkeypatch):
    bus = Bus()
    assert control.TvControl(runner=bus, adapter_list=[]).run("tv-on") == control.Result(False, "no-adapter")
    assert bus.calls == []
    assert _tv(Bus(daemon=False)).run("tv-on") == control.Result(False, "no-daemon")
    monkeypatch.setattr(control.shutil, "which", lambda name: None)
    assert _tv(Bus()).run("tv-on") == control.Result(False, "no-busctl")


def test_a_refused_call_is_reported_not_hidden():
    assert _tv(Bus(fail={"Wake"})).run("tv-on") == control.Result(False, "failed")


def test_the_receiver_wakes_with_a_system_audio_mode_request_carrying_our_address():
    bus = Bus(properties={"AudioLogicalAddress": "y 5", "PhysicalAddress": "q 13312"})
    result = _tv(bus).run("amp-on")
    assert result == control.Result(True, "amp-awake", "off")
    call = next(c for c in bus.calls if c[7] == "SendReceiveRawMessage")
    # 13312 is 3.4.0.0: bytes 0x34 0x00, to logical address 5, expecting reply 114.
    assert call[8:] == ["ayyyq", "3", "112", "52", "0", "5", "114", "2000"]


def test_a_receiver_that_does_not_answer_gets_the_power_on_key():
    bus = Bus(properties={"AudioLogicalAddress": "y 5", "PhysicalAddress": "q 4096"}, fail={"SendReceiveRawMessage"})
    assert _tv(bus).run("amp-on") == control.Result(True, "sent")
    assert bus.methods()[-1] == "PressOnceUserControl"
    assert [c for c in bus.calls if c[7] == "PressOnceUserControl"][0][8:] == ["ayy", "1", "109", "5"]


def test_the_receiver_is_not_asked_before_this_adapter_has_an_address():
    bus = Bus(properties={"PhysicalAddress": "q 65535"})
    assert _tv(bus).run("amp-on") == control.Result(False, "no-address")
    assert "SendReceiveRawMessage" not in bus.methods()


def test_status_reads_power_and_the_address_in_cec_notation():
    bus = Bus(
        properties={"AudioLogicalAddress": "y 5", "PhysicalAddress": "q 4096"},
        replies={("143", "0"): "ay 2 144 1", ("143", "5"): "ay 2 144 0"},
    )
    assert _tv(bus).status() == {"adapter": "cec0", "daemon": True, "tv": "standby", "receiver": "on", "address": "1.0.0.0"}
    assert control.physical_address_text(13312) == "3.4.0.0"
    assert _tv(Bus(daemon=False)).status()["daemon"] is False
    assert control.TvControl(runner=Bus(), adapter_list=[]).status()["adapter"] == ""


def test_an_unknown_action_is_refused():
    with pytest.raises(ValueError):
        _tv(Bus()).run("tv-on; rm -rf /")


# ------------------------------------------------------------ automation


@pytest.mark.parametrize("family", ["steamos", "arch", "bazzite"])
def test_every_automation_workflow_is_valid_bash(family):
    for command in (
        hdmi_cec.wake_install_command(family), hdmi_cec.wake_install_command(family, "grab"),
        hdmi_cec.wake_remove_command(), hdmi_cec.poweroff_install_command(family),
        hdmi_cec.poweroff_remove_command(family),
    ):
        subprocess.run(["bash", "-n"], input=command, text=True, check=True)
    for script in (hdmi_cec.wake_helper_text("polite"), hdmi_cec.wake_helper_text("grab"), hdmi_cec.poweroff_helper_text()):
        subprocess.run(["bash", "-n"], input=script, text=True, check=True)


def test_the_wake_helper_is_polite_unless_asked_to_grab_and_asks_for_the_input_twice():
    polite = hdmi_cec.wake_helper_text("polite")
    assert "MODE=polite" in polite and "MODE=grab" in hdmi_cec.wake_helper_text("grab")
    assert 'SendReceiveRawMessage ayyyq 1 133 15 130 2000' in polite, "asks who holds the input"
    assert polite.index("Wake") < polite.index("SetActiveSource")
    with pytest.raises(ValueError):
        hdmi_cec.wake_install_command("arch", "steal; rm -rf /")


def test_the_wake_unit_waits_for_the_cecd_the_system_really_uses():
    assert "After=cecd.service" in hdmi_cec.wake_unit_text("%h/x", hdmi_cec.SYSTEM_SERVICE)
    command = hdmi_cec.wake_install_command("steamos")
    assert "After=cecd.service" in command and f"enable {hdmi_cec.WAKE_SERVICE}" in command


def test_power_off_standby_only_acts_on_a_real_power_off_and_only_the_tv():
    helper = hdmi_cec.poweroff_helper_text()
    assert "poweroff|halt" in helper and "reboot" in helper.split("poweroff|halt")[0].lower()
    assert "--request-active-source" in helper, "another device holding the input is left alone"
    assert "--to 0 --standby" in helper
    assert "TimeoutStopSec=10" in hdmi_cec.poweroff_unit_text()


def test_steamos_keeps_the_power_off_unit_across_updates_and_asks_for_a_password():
    command = hdmi_cec.poweroff_install_command("steamos")
    assert str(hdmi_cec.POWEROFF_KEEP) in command and str(hdmi_cec.POWEROFF_WANTS) in command
    assert "bc250_require_password" in command
    assert str(hdmi_cec.POWEROFF_KEEP) not in hdmi_cec.poweroff_install_command("arch")
    assert str(hdmi_cec.POWEROFF_KEEP) in hdmi_cec.poweroff_remove_command("steamos")


def test_the_other_toolkits_units_are_never_overwritten():
    assert hdmi_cec.FOREIGN_WAKE in hdmi_cec.wake_install_command("steamos")
    assert str(hdmi_cec.FOREIGN_POWEROFF) in hdmi_cec.poweroff_install_command("steamos")
    for command in (hdmi_cec.wake_remove_command(), hdmi_cec.poweroff_remove_command("arch")):
        assert hdmi_cec.MARKER in command, "only what Control Center wrote is removed"


def test_the_automation_state_tells_ours_from_the_other_toolkits(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(hdmi_cec, "POWEROFF_UNIT", tmp_path / "ours.service")
    monkeypatch.setattr(hdmi_cec, "FOREIGN_POWEROFF", tmp_path / "theirs.service")
    assert hdmi_cec.automation_state() == {"wake": "absent", "poweroff": "absent"}
    units = tmp_path / "systemd" / "user"
    units.mkdir(parents=True)
    (units / hdmi_cec.FOREIGN_WAKE).write_text("x")
    (tmp_path / "theirs.service").write_text("x")
    assert hdmi_cec.automation_state() == {"wake": "foreign", "poweroff": "foreign"}
    (units / hdmi_cec.WAKE_SERVICE).write_text(hdmi_cec.wake_unit_text("h", "cecd.service"))
    (tmp_path / "ours.service").write_text(hdmi_cec.poweroff_unit_text())
    assert hdmi_cec.automation_state() == {"wake": "installed", "poweroff": "installed"}


def test_the_accessory_entry_point_offers_the_automation_actions_for_tv_control_only():
    for action in ("wake-install", "wake-remove", "poweroff-install", "poweroff-remove"):
        accessories.accessory_command("hdmi_cec", action, family="steamos", tool_dir="/tmp/x")
        with pytest.raises(ValueError):
            accessories.accessory_command("corsair", action, family="steamos", tool_dir="/tmp/x")
