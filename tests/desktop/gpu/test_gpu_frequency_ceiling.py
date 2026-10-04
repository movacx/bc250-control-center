"""The SteamOS toolkit module's 2230 MHz limit, in the reader and the root-owned editor."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import tomllib
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from bc250cc.infrastructure.gpu import governor_toml as reader
from bc250cc.infrastructure.steamos_amdgpu import gpu_points_above_module_limit

ROOT = Path(__file__).resolve().parents[3]
RELEASE = "6.18.50-valve2-1-neptune-618-gc7289a96b14d"
LIMITED = (2230, reader.STEAMOS_TOOLKIT_GFXCLK_REASON)

SAMPLE = """[frequency-range]
min = 1000
max = 1850

[[safe-points]]
frequency = 2000
voltage = 960

# [[safe-points]]
# frequency = 2230
# voltage = 1085

# [[safe-points]]
# frequency = 2300
# voltage = 1110

# [[safe-points]]
# frequency = 2400
# voltage = 1150
"""

OBERON_YAML = """opps:
  - frequency:
    - min: 1000
    - max: 2000
  - voltage:
    - min: 1000
    - max: 1000
"""


@pytest.fixture()
def editor(monkeypatch):
    loader = SourceFileLoader("privileged_governor_toml_ceiling", str(ROOT / "privileged/lib/governor_toml.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, loader.name, module)
    loader.exec_module(module)
    # A test file is owned by the test user; the root check is not the subject.
    monkeypatch.setattr(module, "_require_root_owned", lambda *_args: None)
    return module


def _host(tmp_path, *, os_id="steamos", installed=False, loaded=False, overlay=None):
    root = tmp_path / "root"
    (root / "etc").mkdir(parents=True)
    (root / "etc/os-release").write_text(f'NAME="X"\nID={os_id}\n', encoding="utf-8")
    updates = root / "usr/lib/modules" / RELEASE / "updates"
    updates.mkdir(parents=True)
    module = updates / "amdgpu.ko.zst"
    module.write_bytes(b"toolkit module")
    if installed:
        (updates / ".bc250-gfx1013-fix").write_text("sha rev\n", encoding="utf-8")
    if loaded:
        parameter = root / "sys/module/amdgpu/parameters/bc250_gfx1013_fix"
        parameter.parent.mkdir(parents=True)
        parameter.write_text("d3e6dc0\n", encoding="utf-8")
    if overlay is not None:
        digest = hashlib.sha256(module.read_bytes()).hexdigest() if overlay == "match" else "0" * 64
        (updates / reader.STEAMOS_TELEMETRY_OC_MARKER).write_text(digest + "\n", encoding="ascii")
    return root


@pytest.mark.parametrize(
    ("host", "expected"),
    (
        ({"os_id": "bazzite", "installed": True, "loaded": True}, (None, "")),
        ({}, (None, "")),
        ({"installed": True}, LIMITED),
        ({"loaded": True}, LIMITED),
        ({"installed": True, "loaded": True, "overlay": "stale"}, LIMITED),
        # A module built by an earlier Control Center with its 2400 MHz overlay.
        ({"installed": True, "loaded": True, "overlay": "match"}, (None, "")),
    ),
)
def test_both_copies_agree_on_when_the_limit_applies(tmp_path, editor, host, expected):
    root = _host(tmp_path, **host)
    assert reader.gpu_frequency_ceiling(root, RELEASE) == expected
    assert editor.gpu_frequency_ceiling(root, RELEASE) == expected


def test_a_missing_os_release_means_no_limit(tmp_path):
    assert reader.gpu_frequency_ceiling(tmp_path / "nothing", RELEASE) == (None, "")


@pytest.fixture(params=("reader", "editor"))
def limited_module(request, editor, monkeypatch):
    module = reader if request.param == "reader" else editor
    monkeypatch.setattr(module, "gpu_frequency_ceiling", lambda *_args: LIMITED)
    return module


def test_enabling_high_points_stops_at_the_module_limit(tmp_path, limited_module):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    toml = limited_module.GovernorTomlEditor(path)

    toml.set_high_frequency_points(True)

    active = [point["frequency"] for point in tomllib.loads(path.read_text(encoding="utf-8"))["safe-points"]]
    assert active == [2000, 2230]
    state = toml.high_frequency_state()
    assert state["enabled_frequencies"] == (2230,)
    assert state["allowed_frequencies"] == (2230,)
    assert state["ceiling_mhz"] == 2230
    toml.set_high_frequency_points(False)
    assert toml.high_frequency_state()["enabled_frequencies"] == ()


def test_enabling_turns_off_points_above_the_limit_left_on_by_hand(tmp_path, limited_module):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE.replace("# [[safe-points]]\n# frequency = 2400\n# voltage = 1150",
                                   "[[safe-points]]\nfrequency = 2400\nvoltage = 1150"), encoding="utf-8")

    limited_module.GovernorTomlEditor(path).set_high_frequency_points(True)

    active = [point["frequency"] for point in tomllib.loads(path.read_text(encoding="utf-8"))["safe-points"]]
    assert active == [2000, 2230]


def test_enabling_refuses_a_table_with_no_point_within_the_limit(tmp_path, limited_module):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE.replace("frequency = 2230", "frequency = 2250"), encoding="utf-8")

    with pytest.raises(limited_module.GovernorTomlError, match="2230 MHz"):
        limited_module.GovernorTomlEditor(path).set_high_frequency_points(True)
    assert path.read_text(encoding="utf-8") == SAMPLE.replace("frequency = 2230", "frequency = 2250")


def test_range_floor_and_oberon_cannot_pass_the_limit(tmp_path, limited_module):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    toml = limited_module.GovernorTomlEditor(path)
    with pytest.raises(limited_module.GovernorTomlError, match="2230 MHz or lower"):
        toml.set_frequency_range(1000, 2300)
    with pytest.raises(limited_module.GovernorTomlError, match="2230 MHz or lower"):
        toml.set_frequency_floor(2300)
    assert path.read_text(encoding="utf-8") == SAMPLE
    toml.set_frequency_range(1000, 2230)

    yaml = tmp_path / "oberon-config.yaml"
    yaml.write_text(OBERON_YAML, encoding="utf-8")
    oberon = limited_module.OberonYamlEditor(yaml)
    with pytest.raises(limited_module.OberonYamlError, match="2230 MHz or lower"):
        oberon.set_operating_points(1000, 2400, 920, 1150)
    oberon.set_operating_points(1000, 2230, 920, 1085)


def test_without_the_module_the_full_table_is_enabled(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")

    reader.GovernorTomlEditor(path).set_high_frequency_points(True)

    state = reader.GovernorTomlEditor(path).high_frequency_state()
    assert state["enabled_frequencies"] == (2230, 2300, 2400)
    assert state["ceiling_mhz"] is None


def test_installing_the_module_waits_until_points_above_the_limit_are_off(tmp_path):
    cyan = tmp_path / "config.toml"
    oberon = tmp_path / "oberon-config.yaml"
    assert gpu_points_above_module_limit(cyan_config=cyan, oberon_config=oberon) == ""

    cyan.write_text(SAMPLE, encoding="utf-8")
    reader.GovernorTomlEditor(cyan).set_high_frequency_points(True)
    oberon.write_text(OBERON_YAML.replace("max: 2000", "max: 2400"), encoding="utf-8")
    blocker = gpu_points_above_module_limit(cyan_config=cyan, oberon_config=oberon)
    assert "2300, 2400 MHz" in blocker
    assert "Disable +2000 MHz TOML points" in blocker
    assert "Oberon maximum to 2230 MHz" in blocker

    reader.GovernorTomlEditor(cyan).set_high_frequency_points(False)
    oberon.write_text(OBERON_YAML, encoding="utf-8")
    assert gpu_points_above_module_limit(cyan_config=cyan, oberon_config=oberon) == ""
