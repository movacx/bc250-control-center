"""The switch for Cyan's points above 2000 MHz lives in the plugin's Settings.

Requested back where it was: it is a one-time decision about what the GPU
tab offers, not a control used while playing, so it leaves the GPU section.
"""

from __future__ import annotations

from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[2] / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(
    encoding="utf-8"
)
BUNDLE = (Path(__file__).resolve().parents[2] / "integrations/decky/bc250-quick-access/dist/index.js").read_text(
    encoding="utf-8"
)


def _body(name: str) -> str:
    start = SOURCE.index(f"function {name}(")
    following = SOURCE.find("\nfunction ", start + 1)
    return SOURCE[start:following if following != -1 else len(SOURCE)]


def test_the_switch_is_rendered_in_settings_and_nowhere_else():
    assert SOURCE.count("<HighPointsSwitch ") == 1
    assert "<HighPointsSwitch " in _body("SettingsTab")
    assert "<HighPointsSwitch " not in _body("Content")


def test_settings_is_given_what_the_switch_needs_to_act():
    assert "<SettingsTab settings={settings} setSettings={setSettings} state={state} busy={busy} execute={execute} />" in SOURCE
    # The switch still asks before writing the TOML and only offers itself on Cyan.
    switch = _body("HighPointsSwitch")
    assert "ConfirmModal" in switch and "setGpuHighFrequencyPoints" in switch
    assert "highFrequencyCyanOnly" in switch


def test_the_shipped_bundle_was_rebuilt_from_this_source():
    assert "HighPointsSwitch" in BUNDLE
    settings_start = BUNDLE.index("function SettingsTab(")
    assert "HighPointsSwitch" in BUNDLE[settings_start:settings_start + 1500]
