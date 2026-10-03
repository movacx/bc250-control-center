"""The switch for Cyan's points above 2000 MHz sits with the points it unlocks.

It is the first row of the GPU tab's "More frequencies" drawer, named "Unlock
frequencies", and is no longer in Settings.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "integrations/decky/bc250-quick-access/src/index.tsx").read_text(encoding="utf-8")
BUNDLE = (ROOT / "integrations/decky/bc250-quick-access/dist/index.js").read_text(encoding="utf-8")


def _body(name: str) -> str:
    start = SOURCE.index(f"function {name}(")
    following = SOURCE.find("\nfunction ", start + 1)
    return SOURCE[start:following if following != -1 else len(SOURCE)]


def test_the_switch_is_rendered_once_in_the_gpu_drawer_and_not_in_settings():
    assert SOURCE.count("<HighPointsSwitch ") == 1
    assert "<HighPointsSwitch " in _body("Content")
    assert "<HighPointsSwitch " not in _body("SettingsTab")
    drawer = _body("Content").split("<HighPointsSwitch ", 1)[0].rsplit("<DisclosureRow label={text.more}", 1)[1]
    assert "<Drawer>" in drawer


def test_the_switch_still_asks_before_writing_the_toml_and_only_offers_itself_on_cyan():
    switch = _body("HighPointsSwitch")
    assert "ConfirmModal" in switch and "setGpuHighFrequencyPoints" in switch
    assert "highFrequencyCyanOnly" in switch
    assert "unlockFrequencies" in switch


def test_the_drawer_is_offered_on_cyan_even_before_any_point_is_unlocked():
    assert 'points.length || state.gpu_governor === "cyan"' in SOURCE


def test_every_language_names_it():
    names = {path.stem: json.loads(path.read_text(encoding="utf-8")).get("unlockFrequencies")
             for path in (ROOT / "integrations/decky/bc250-quick-access/locales").glob("*.json")}
    assert all(names.values()), names


def test_the_shipped_bundle_was_rebuilt_from_this_source():
    assert "HighPointsSwitch" in BUNDLE
    assert "unlockFrequencies" in BUNDLE
