"""The web Fans page edits the same per-channel settings the desktop does,
through the shared channel board and the root service policy."""
from types import SimpleNamespace

import pytest

from bc250cc.application.fan.board_actions import FanBoardError
from frontends.tui.runtime import describe_error
from frontends.web.actions import (
    Invalid,
    fan_channel,
    fan_label,
    fan_profile,
    fan_service,
)
from frontends.web.data import _fans


class Settings:
    def __init__(self, config=None):
        self.config = dict(config or {})

    def read_local_config(self):
        return self.config.copy()

    def save_local_config(self, payload):
        self.config.update(payload)
        return self.config


def fan(index, *, rpm=1200, pwm=128):
    return {"index": index, "label": f"Fan {index}", "rpm": rpm, "pwm": pwm, "pwm_path": f"/x/pwm{index}",
            "pwm_root_writable": True}


FANS = {"driver_control": True, "sensores": {"chip": "nct6687", "path": "/x", "fans": [
    fan(1, rpm=0), fan(2), fan(3, rpm=900)]}}


def context(config=None, fans=FANS, **state):
    calls = []
    system = {"available": True, "enabled": False, **state}

    def write(pwm, raw):
        calls.append(("write", pwm, raw))
        return {"verified": {"pwm": pwm, "value": raw}}

    def restore(pwm):
        calls.append(("restore", pwm))
        return {"verified": {"pwm": pwm, "enable": 2}}

    service = SimpleNamespace(
        estado_control_fan_sistema=lambda: system,
        estado_fans_bc250=lambda: fans,
        aplicar_pwm_fan=write,
        restaurar_pwm_automatico=restore,
        activar_control_fan_sistema=lambda policy: calls.append(("enable", policy)),
        sincronizar_control_fan_sistema=lambda policy: calls.append(("sync", policy)),
        desactivar_control_fan_sistema=lambda: calls.append(("disable", None)),
    )
    return SimpleNamespace(service=service, settings=Settings(config)), system, calls


CURVE = {"mode": "curve", "source": "hottest", "points": [[40, 50], [60, 75], [75, 100]]}
PUMP = {"mode": "fixed", "percent": 90, "role": "pump"}


def test_a_curve_is_saved_per_channel_and_the_others_keep_theirs():
    ctx, system, calls = context({"fan_channels": {"2": PUMP}})
    system["enabled"] = True
    level, work = fan_channel(ctx, {"pwm": 3, "entry": CURVE}, None)
    assert level == 1 and not calls
    work()
    channels = ctx.settings.config["fan_channels"]
    assert channels["2"]["role"] == "pump" and channels["3"]["mode"] == "curve"
    assert calls[-1][0] == "sync" and set(calls[-1][1]["channels"]) == {"2", "3"}
    assert "fan_curve" not in ctx.settings.config  # never the v1 keys again


def test_firmware_on_one_channel_keeps_the_pump_on_its_policy():
    ctx, system, calls = context({"fan_channels": {"2": PUMP, "3": CURVE}})
    system["enabled"] = True
    fan_channel(ctx, {"pwm": 3, "entry": None}, None)[1]()
    assert list(ctx.settings.config["fan_channels"]) == ["2"]
    assert calls[-1][0] == "sync" and list(calls[-1][1]["channels"]) == ["2"]


def test_with_the_service_off_a_fixed_duty_is_written_and_verified():
    ctx, _system, calls = context()
    level, work = fan_channel(ctx, {"pwm": 2, "entry": {"mode": "fixed", "percent": 20}}, None)
    assert level == 2  # under 30 % asks as a risk
    assert "PWM 2" in work()
    assert calls == [("write", 2, 51)]


def test_a_write_without_read_back_is_a_failure():
    ctx, _system, _calls = context()
    ctx.service.aplicar_pwm_fan = lambda pwm, raw: "ok"
    with pytest.raises(FanBoardError) as error:
        fan_channel(ctx, {"pwm": 2, "entry": {"mode": "fixed", "percent": 60}}, None)[1]()
    assert error.value.title == "Fan PWM operation failed"


def test_with_the_service_off_a_curve_is_only_saved_and_says_what_follows_it():
    ctx, _system, calls = context()
    message = fan_channel(ctx, {"pwm": 2, "entry": CURVE}, None)[1]()
    assert not calls and "log in" in message


def test_a_pump_below_its_floor_and_unknown_keys_are_refused_before_anything_runs():
    ctx, _system, calls = context()
    with pytest.raises(Invalid):
        fan_channel(ctx, {"pwm": 2, "entry": {"mode": "fixed", "percent": 20, "role": "pump"}}, None)
    with pytest.raises(Invalid):
        fan_channel(ctx, {"pwm": 2, "entry": {**CURVE, "shell": "rm"}}, None)
    with pytest.raises(Invalid):
        fan_channel(ctx, {"pwm": 13, "entry": CURVE}, None)
    with pytest.raises(Invalid):
        fan_channel(ctx, {"pwm": 2, "entry": {"mode": "curve", "points": [[40, 50]] * 2000}}, None)
    assert not calls and not ctx.settings.config


def test_a_read_only_channel_is_a_notice_not_a_write():
    fans = {"driver_control": False, "sensores": {"chip": "nct6683", "fans": [fan(2)]}}
    ctx, _system, calls = context(fans=fans)
    with pytest.raises(FanBoardError) as error:
        fan_channel(ctx, {"pwm": 2, "entry": {"mode": "fixed", "percent": 60}}, None)[1]()
    assert error.value.notice and not calls


def test_a_handed_off_fan_is_never_written():
    ctx, _system, calls = context(external=True)
    with pytest.raises(FanBoardError):
        fan_channel(ctx, {"pwm": 2, "entry": {"mode": "fixed", "percent": 60}}, None)[1]()
    assert not calls and not ctx.settings.config


def test_a_policy_an_old_helper_cannot_follow_asks_to_update_it():
    ctx, system, calls = context(policy_schemas=[1])
    system["enabled"] = True
    mix = {"mode": "mix", "mix": [{"source": "gpu", "points": [[50, 30], [80, 100]]},
                                  {"source": "vrm", "points": [[70, 30], [95, 100]]}]}
    with pytest.raises(FanBoardError) as error:
        fan_channel(ctx, {"pwm": 2, "entry": mix}, None)[1]()
    assert error.value.message == "Update fan helper" and not calls


def test_a_built_in_profile_drives_the_turning_headers_never_a_pump():
    ctx, system, calls = context()
    system["enabled"] = True
    fan_profile(ctx, {"operation": "apply", "name": "Quiet"}, None)[1]()
    channels = ctx.settings.config["fan_channels"]
    assert set(channels) == {"2", "3"}  # PWM 1 does not turn
    assert all(entry["mode"] == "curve" for entry in channels.values())
    assert ctx.settings.config["fan_active_mode"] == "Quiet" and calls[-1][0] == "sync"


def test_a_profile_with_nothing_to_drive_is_a_plain_notice():
    fans = {"driver_control": True, "sensores": {"chip": "nct6687", "fans": [fan(2, rpm=0)]}}
    ctx, _system, calls = context(fans=fans)
    with pytest.raises(FanBoardError) as error:
        fan_profile(ctx, {"operation": "apply", "name": "Balanced"}, None)[1]()
    assert error.value.notice and error.value.title == "No PWM channel"
    assert "BC250-FAN" not in describe_error(error.value)
    # With a selected writable header it goes there.
    fan_profile(ctx, {"operation": "apply", "name": "Balanced", "selected": 2}, None)[1]()
    assert list(ctx.settings.config["fan_channels"]) == ["2"] and not calls


def test_profiles_are_saved_with_a_draft_replaced_only_when_asked_and_reserved_names_refused():
    ctx, _system, _calls = context({"fan_channels": {"2": PUMP}})
    fan_profile(ctx, {"operation": "save", "name": "Night", "draft": {"pwm": 3, "entry": CURVE}}, None)[1]()
    night = ctx.settings.config["fan_modes"][0]
    assert night["name"] == "Night" and set(night["channels"]) == {"2", "3"}
    assert set(ctx.settings.config["fan_channels"]) == {"2"}  # the draft is not applied
    with pytest.raises(FanBoardError):
        fan_profile(ctx, {"operation": "save", "name": "night"}, None)[1]()
    fan_profile(ctx, {"operation": "save", "name": "Night", "replace": True}, None)[1]()
    with pytest.raises(FanBoardError):
        fan_profile(ctx, {"operation": "save", "name": "Balanced"}, None)[1]()
    fan_profile(ctx, {"operation": "delete", "name": "Night"}, None)[1]()
    assert ctx.settings.config["fan_modes"] == []


def test_renaming_a_channel_never_changes_which_one_is_driven():
    ctx, _system, calls = context({"fan_channels": {"2": PUMP}})
    level, work = fan_label(ctx, {"pwm": 2, "label": "  AIO   pump "}, None)
    assert level == 0
    work()
    assert ctx.settings.config["fan_channel_labels"] == {"2": "AIO pump"}
    assert list(ctx.settings.config["fan_channels"]) == ["2"] and not calls


@pytest.mark.parametrize("operation", ["enable", "sync", "disable"])
def test_service_operations_use_current_saved_policy(operation):
    ctx, system, calls = context({"fan_channels": {"2": CURVE}})
    system["enabled"] = True
    level, work = fan_service(ctx, {"operation": operation}, None)
    assert level == 1 and not calls
    work()
    assert calls[0][0] == operation
    if operation != "disable":
        assert calls[0][1]["channels"]["2"]["points"] == CURVE["points"]


@pytest.mark.parametrize("operation", ["enable", "sync", "disable"])
def test_handoff_is_rechecked_when_the_action_executes(operation):
    ctx, system, calls = context({"fan_channels": {"2": CURVE}})
    _, work = fan_service(ctx, {"operation": operation}, None)
    system["external"] = True
    with pytest.raises(Invalid):
        work()
    assert not calls


def test_no_policy_or_invalid_operation_cannot_start_service():
    ctx, _system, calls = context()
    with pytest.raises(Invalid):
        fan_service(ctx, {"operation": "enable"}, None)[1]()
    with pytest.raises(Invalid):
        fan_service(ctx, {"operation": "arbitrary"}, None)
    assert not calls


def test_web_state_is_the_desktop_channel_board():
    config = {"fan_channels": {"2": PUMP, "3": CURVE}, "fan_channel_labels": {"3": "Rear"},
              "fan_modes": [{"name": "Night", "channels": {"3": CURVE}}]}
    ctx, _system, _calls = context(config)
    system = {"enabled": True, "available": True, "state": "active", "status": {"controlled": [2, 3], "channels": {
        "2": {"state": "active", "percent": 90, "source": "fixed"},
        "3": {"state": "active", "percent": 64, "source": "curve", "temperature": 61.5, "fault": "stalled"}}}}
    data = _fans({"fans": FANS, "system": system, "config": config}, ctx)
    rows = {row["pwm"]: row for row in data["channels"]}
    assert [row["pwm"] for row in data["channels"]] == [2, 3, 4, 5, 1]  # BIOS order
    assert rows[2]["role"] == "pump" and rows[2]["state"] == "Active"
    assert rows[3]["label"] == "Rear" and rows[3]["state"] == "Fan stopped" and rows[3]["tone"] == "red"
    assert rows[3]["temperature"] == 61.5 and rows[3]["follows"] == "Hottest chip"
    assert rows[1]["mode"] == "firmware" and rows[1]["state"] == "BIOS"
    assert rows[4]["state"] == "Not detected"
    assert data["profiles"] == {"builtin": ["Quiet", "Balanced", "Performance"], "saved": ["Night"],
                                "active": "", "custom": True}
    assert data["needs_root_service"] and data["service"]["out_of_date"]
    assert data["service"]["summary"].startswith("The service still follows")


def test_web_state_without_a_driver_says_what_is_missing():
    ctx, _system, _calls = context()
    data = _fans({"fans": {"sensores": {"fans": []}}, "system": {}, "config": {}}, ctx)
    assert data["driver"].startswith("No NCT fan controller")
    assert all(row["state"] == "Not detected" for row in data["channels"])
