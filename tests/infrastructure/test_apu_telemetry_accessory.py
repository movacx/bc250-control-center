"""BC250-Telemetry on Additional settings › Compatibility › Board sensors.

The wired I2C route works on every distribution its installer covers, so it
sits with the two kernel drivers, in the same words as their cards.
"""

from __future__ import annotations

import pytest

from bc250cc.infrastructure import apu_telemetry_service as service


@pytest.mark.parametrize(("raw", "supported", "expected"), [
    ("not-installed", True, "not-installed"),
    ("not-installed", False, "unsupported"),
    ("external", True, "managed-elsewhere"),
    ("publishing", True, "active"),
    ("installed", True, "installed"),
    ("invalid", True, "installed"),
])
def test_the_service_state_in_the_cards_words(monkeypatch, raw, supported, expected):
    monkeypatch.setattr(service, "apu_telemetry_state", lambda **_kw: {
        "state": raw, "supported": supported, "blocked_reason": "" if supported else "SteamOS resets /usr",
        "managed": raw in {"publishing", "installed", "invalid"},
    })
    info = service.accessory_state(family="fedora")
    assert info["state"] == expected and info["service_state"] == raw


def test_it_is_listed_with_the_accessories(monkeypatch, tmp_path):
    from bc250cc.infrastructure import accessories

    monkeypatch.setattr(service, "apu_telemetry_state", lambda **_kw: {"state": "not-installed", "supported": True})
    assert "apu_telemetry" in accessories.ACCESSORIES
    assert accessories.accessory_inventory("ubuntu", tmp_path)["apu_telemetry"]["state"] == "not-installed"


def test_one_failing_probe_does_not_blank_the_others(monkeypatch, tmp_path):
    """Reported 2026-11-20 on SteamOS: every board sensor card stayed on
    "Checking". One probe raising must only mark its own card."""
    from bc250cc.infrastructure import accessories

    def boom(_family):
        raise KeyError("unexpected")

    monkeypatch.setattr(accessories.vram_sensor, "inventory", boom)
    monkeypatch.setattr(service, "apu_telemetry_state", lambda **_kw: {"state": "not-installed", "supported": True})
    states = accessories.accessory_inventory("steamos", tmp_path)
    assert states["vram_sensor"]["state"] == "error" and "KeyError" in states["vram_sensor"]["error"]
    assert states["apu_telemetry"]["state"] == "not-installed"
    assert set(states) == set(accessories.ACCESSORIES)
