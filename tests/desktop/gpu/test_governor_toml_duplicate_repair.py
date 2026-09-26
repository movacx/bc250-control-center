"""GitHub issue #1: a key written twice made installation roll back.

Another toolkit had left ``/etc/cyan-skillfish-governor-smu/config.toml``
with ``fix-freq`` twice, the second copy indented. TOML rejects that, the
installer's normalization step failed, and the whole installation was rolled
back. The privileged editor now removes repeats that say the same thing, and
names the key and lines when the repeats disagree.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]

ISSUE_ONE = """[gpu-usage]
fix-metrics = true
fix-freq = false
 fix-freq = false
method = "busy-flag"

[frequency-range]
min = 1000
max = 1850

[[safe-points]]
frequency = 1000
voltage = 700

[[safe-points]]
frequency = 2000
voltage = 960
"""


@pytest.fixture()
def editor_module(monkeypatch):
    loader = SourceFileLoader("privileged_governor_toml", str(ROOT / "privileged/lib/governor_toml.py"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their module through sys.modules while the class
    # body runs, so the module has to be registered before it executes.
    monkeypatch.setitem(sys.modules, loader.name, module)
    loader.exec_module(module)
    # A test file is owned by the test user; the root check is not the subject.
    monkeypatch.setattr(module, "_require_root_owned", lambda *_args: None)
    return module


def test_the_issue_one_file_is_repaired_and_everything_else_is_kept(editor_module, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(ISSUE_ONE, encoding="utf-8")

    result = editor_module.GovernorTomlEditor(path).migrate_legacy_frequency_range()

    repaired = path.read_text(encoding="utf-8")
    assert result.changed is True
    assert repaired.count("fix-freq") == 1
    parsed = tomllib.loads(repaired)
    assert parsed["gpu-usage"] == {"fix-metrics": True, "fix-freq": False, "method": "busy-flag"}
    assert [point["frequency"] for point in parsed["safe-points"]] == [1000, 2000]
    assert repaired == ISSUE_ONE.replace(" fix-freq = false\n", "", 1)


def test_repeats_that_disagree_are_named_instead_of_guessed(editor_module, tmp_path):
    path = tmp_path / "config.toml"
    original = ISSUE_ONE.replace(" fix-freq = false", " fix-freq = true")
    path.write_text(original, encoding="utf-8")

    with pytest.raises(editor_module.GovernorTomlError, match=r"fix-freq twice .*lines 3 and 4"):
        editor_module.GovernorTomlEditor(path).migrate_legacy_frequency_range()
    assert path.read_text(encoding="utf-8") == original


def test_the_same_key_in_separate_array_entries_is_not_a_repeat(editor_module, tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(ISSUE_ONE.replace(" fix-freq = false\n", ""), encoding="utf-8")

    assert editor_module.GovernorTomlEditor(path).repair_identical_duplicate_keys().changed is False


def test_a_valid_file_is_never_rewritten(editor_module, tmp_path):
    path = tmp_path / "config.toml"
    valid = ISSUE_ONE.replace(" fix-freq = false\n", "")
    path.write_text(valid, encoding="utf-8")
    before = path.stat().st_mtime_ns

    assert editor_module.GovernorTomlEditor(path).repair_identical_duplicate_keys().changed is False
    assert path.stat().st_mtime_ns == before


def test_the_installer_no_longer_rolls_back_over_this_step():
    installer = (ROOT / "scripts/install-local.sh").read_text(encoding="utf-8")
    assert 'if ! "${elevate[@]}" "$SYSTEM_GOVERNOR_CONFIG_HELPER" migrate-legacy-frequency-range; then' in installer
