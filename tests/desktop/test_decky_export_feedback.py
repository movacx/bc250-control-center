"""After an export to Decky, the pages only claim what the plugin inventory shows."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from frontends.desktop.core.decky_export_feedback import (
    export_and_check_plugin,
    export_message,
    export_tone,
    fan_export_notes,
)


@pytest.mark.parametrize(("inventory", "expected"), [
    ({"decky_detected": True, "plugin_present": True}, True),
    ({"decky_detected": True, "plugin_present": False}, False),
    ({"decky_detected": False, "plugin_present": False}, False),
    ("not a mapping", None),
])
def test_the_plugin_is_checked_after_the_export(inventory, expected):
    calls = []
    controller = SimpleNamespace(estado_quick_access_decky=lambda: calls.append("inventory") or inventory)

    assert export_and_check_plugin(controller, lambda: calls.append("export")) is expected
    assert calls == ["export", "inventory"]


def test_an_unreadable_inventory_never_turns_a_written_export_into_a_failure():
    def broken():
        raise OSError("permission denied")

    assert export_and_check_plugin(SimpleNamespace(estado_quick_access_decky=broken), lambda: None) is None
    assert export_and_check_plugin(SimpleNamespace(), lambda: None) is None


def test_a_failed_export_is_not_hidden_by_the_inventory():
    def failing():
        raise RuntimeError("helper refused")

    with pytest.raises(RuntimeError):
        export_and_check_plugin(SimpleNamespace(estado_quick_access_decky=dict), failing)


def test_the_message_and_tone_follow_the_inventory():
    assert export_message(True) == "Profiles exported to Decky Quick Access."
    assert export_message(None) == "Profiles exported to Decky Quick Access."
    assert "not installed yet" in export_message(False)
    assert (export_tone(True), export_tone(None), export_tone(False)) == ("green", "green", "blue")
    assert export_message(True, ["A.", "B."]) == "Profiles exported to Decky Quick Access. A. B."


def test_fan_notes_name_the_channels_and_every_raised_speed():
    notes = fan_export_notes([("Quiet", 10, 20)])
    assert "PWM3–PWM8" in notes[0] and "never PWM2" in notes[0]
    assert notes[1:] == ["Quiet: 10 % → 20 % in Decky."]
    assert len(fan_export_notes([])) == 1
