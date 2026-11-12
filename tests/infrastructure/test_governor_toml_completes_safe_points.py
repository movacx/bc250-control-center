"""A Cyan TOML that stops below the packaged curve (R-c310d1a4: hand-made,
ending at 1750 MHz) gets the missing packaged safe-points instead of every
voltage profile being refused."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from bc250cc.infrastructure.gpu import governor_toml as desktop

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("privileged_governor_toml", ROOT / "privileged/lib/governor_toml.py")
privileged = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = privileged
_spec.loader.exec_module(privileged)

REPORTED = """[timing.intervals]
sample = 250
adjust = 100_000
[gpu-usage]
fix-metrics = false
fix-freq = false
method = "busy-flag" # "busy-flag" or "process"
flush-every = 10
temp-read = "sysfs"
[gpu]
set-method = "smu"  # "smu" or "kernel"

[dbus]
enabled = true

[frequency-range]
min = 500
max = 1750
[timing.ramp-rates]
normal = 1
burst = 50
[timing]
burst-samples = 60
down-events = 5
[frequency-thresholds]
adjust = 10
[load-target]
upper = 0.65
lower = 0.50
[temperature]
throttling = 80
throttling_recovery = 75
[[safe-points]]
frequency = 500
voltage = 700
[[safe-points]]
frequency = 1000
voltage = 800
[[safe-points]]
frequency = 1175
voltage = 850
[[safe-points]]
frequency = 1500
voltage = 900
[[safe-points]]
frequency = 1600
voltage = 910
[[safe-points]]
frequency = 1700
voltage = 920
[[safe-points]]
frequency = 1750
voltage = 925
"""


@pytest.mark.parametrize("module", [desktop, privileged], ids=["desktop", "privileged"])
def test_missing_points_are_added_in_order_and_high_ones_commented(module):
    completed = module._with_packaged_safe_points(REPORTED)
    blocks = module._parsed_safe_point_blocks(completed.splitlines(keepends=True))
    frequencies = [block.frequency for block in blocks]
    assert frequencies == sorted(frequencies)
    by_frequency = {block.frequency: block for block in blocks}
    assert by_frequency[1750].voltage == 925 and by_frequency[1750].active  # the owner's own point stays
    assert by_frequency[1850].active and by_frequency[1850].voltage == 930
    assert by_frequency[2000].active and by_frequency[2000].voltage == 960
    assert not by_frequency[2050].active and not by_frequency[2400].active
    assert set(dict(module.GOVERNOR_DEFAULT_SAFE_POINTS)) <= set(by_frequency)
    assert "max = 1750" in completed  # the range is not touched
    assert module._with_packaged_safe_points(completed) == completed


# The privileged editor only writes files root owns; its completion is the same
# function, checked above.
@pytest.mark.parametrize("module", [desktop], ids=["desktop"])
def test_the_voltage_profile_applies_on_the_reported_toml(tmp_path, module):
    path = tmp_path / "config.toml"
    path.write_text(REPORTED, encoding="utf-8")
    editor = module.GovernorTomlEditor(path)
    result = editor.set_voltage_profile(0)
    assert result.changed
    text = path.read_text(encoding="utf-8")
    assert "frequency = 2000" in text and "# frequency = 2400" in text

