import os
import tomllib

import pytest

from bc250cc.infrastructure.gpu.governor_toml import (
    GovernorTomlEditor,
    GovernorTomlError,
    OberonYamlEditor,
    OberonYamlError,
    validate_voltage_curve,
    voltage_profile,
)

SAMPLE = """# keep this comment
[frequency-range]
min = 1000    # MHz
max = 1850    # MHz

[temperature]
throttling = 85

[[safe-points]]
frequency = 2000
voltage = 960

# [[safe-points]]
# frequency = 2050
# voltage = 980

# [[safe-points]]
# frequency = 2400
# voltage = 1150
"""


def test_clear_frequency_range_preserves_other_content(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    result = GovernorTomlEditor(path).clear_frequency_range()
    updated = path.read_text(encoding="utf-8")
    assert result.changed is True
    assert "# [frequency-range]" in updated
    assert "# min = 1000    # MHz" in updated
    assert "# max = 1850    # MHz" in updated
    assert "[temperature]\nthrottling = 85" in updated
    assert "frequency = 2000\nvoltage = 960" in updated
    tomllib.loads(updated)

    state = GovernorTomlEditor(path).frequency_range_state()
    assert state == {
        "present": True,
        "enabled": False,
        "valid": True,
        "mode": "profile",
        "min": 1000,
        "max": 1850,
        "error": "",
    }


def test_custom_frequency_range_restores_complete_section_idempotently(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)
    editor.clear_frequency_range()

    first = editor.set_frequency_range(500, 0)
    once = path.read_text(encoding="utf-8")
    second = editor.set_frequency_range(500, 0)

    assert first.changed is True
    assert second.changed is False
    assert path.read_text(encoding="utf-8") == once
    assert "\n[frequency-range]\nmin = 500" in once
    assert "max = 0" in once
    assert editor.frequency_range_state()["mode"] == "custom"
    tomllib.loads(once)


def test_persistent_floor_preserves_active_custom_maximum(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)

    editor.set_frequency_floor(500)
    state = editor.frequency_range_state()

    assert state["min"] == 500
    assert state["max"] == 1850
    assert state["enabled"] is True


def test_persistent_floor_keeps_profile_maximum_commented_and_unchanged(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)
    editor.clear_frequency_range()

    first = editor.set_frequency_floor(500)
    once = path.read_text(encoding="utf-8")
    second = editor.set_frequency_floor(500)
    state = editor.frequency_range_state()

    assert state["min"] == 500
    assert state["max"] is None
    assert state["stored_max"] == 1850
    assert state["enabled"] is True
    assert state["mode"] == "floor"
    text = path.read_text(encoding="utf-8")
    assert "\n[frequency-range]\nmin = 500" in text
    assert "# max = 1850" in text
    assert first.changed is True
    assert second.changed is False
    assert text == once


def test_mixed_frequency_range_state_is_rejected(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE.replace("min = 1000", "# min = 1000"), encoding="utf-8")
    editor = GovernorTomlEditor(path)

    state = editor.frequency_range_state()
    assert state["valid"] is False
    assert state["mode"] == "conflict"
    with pytest.raises(GovernorTomlError, match="mix active and commented"):
        editor.set_frequency_floor(500)


def test_legacy_empty_active_range_table_migrates_to_profile_idempotently(tmp_path):
    path = tmp_path / "config.toml"
    legacy = SAMPLE.replace("min = 1000", "# min = 1000").replace(
        "max = 1850", "# max = 1850"
    )
    path.write_text(legacy, encoding="utf-8")
    editor = GovernorTomlEditor(path)

    migration = editor.legacy_frequency_range_migration()
    assert migration["needed"] is True
    assert migration["target_mode"] == "profile"
    first = editor.migrate_legacy_frequency_range()
    once = path.read_text(encoding="utf-8")
    second = editor.migrate_legacy_frequency_range()

    assert first.changed is True
    assert second.changed is False
    assert path.read_text(encoding="utf-8") == once
    assert editor.frequency_range_state()["mode"] == "profile"
    assert "[temperature]\nthrottling = 85" in once


@pytest.mark.parametrize(
    "minimum_line, maximum_line, target_mode",
    (
        ("min = 1000", "max = 1850", "custom"),
        ("min = 1000", "# max = 1850", "floor"),
    ),
)
def test_legacy_commented_header_restores_intended_mode(
    tmp_path, minimum_line, maximum_line, target_mode
):
    path = tmp_path / "config.toml"
    legacy = SAMPLE.replace("[frequency-range]", "# [frequency-range]")
    legacy = legacy.replace("min = 1000", minimum_line).replace(
        "max = 1850", maximum_line
    )
    path.write_text(legacy, encoding="utf-8")
    editor = GovernorTomlEditor(path)

    assert editor.legacy_frequency_range_migration()["target_mode"] == target_mode
    editor.migrate_legacy_frequency_range()

    state = editor.frequency_range_state()
    assert state["valid"] is True
    assert state["mode"] == target_mode
    assert state["min"] == 1000
    assert state.get("max") == (1850 if target_mode == "custom" else None)


def test_high_frequency_toggle_is_idempotent(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)

    first = editor.set_high_frequency_points(True)
    once = path.read_text(encoding="utf-8")
    second = editor.set_high_frequency_points(True)
    twice = path.read_text(encoding="utf-8")
    assert first.changed is True
    assert second.changed is False
    assert once == twice
    assert "\n[[safe-points]]\nfrequency = 2050\nvoltage = 980" in once
    assert "frequency = 2000\nvoltage = 960" in once

    disabled = editor.set_high_frequency_points(False)
    disabled_once = path.read_text(encoding="utf-8")
    disabled_again = editor.set_high_frequency_points(False)
    assert disabled.changed is True
    assert disabled_again.changed is False
    assert path.read_text(encoding="utf-8") == disabled_once
    assert "# frequency = 2050" in disabled_once
    assert "frequency = 2000\nvoltage = 960" in disabled_once
    tomllib.loads(disabled_once)


def test_enabling_high_points_from_profile_mode_keeps_safe_startup_ceiling(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)
    editor.clear_frequency_range()

    editor.set_high_frequency_points(True)

    state = editor.frequency_range_state()
    assert state["mode"] == "custom"
    # This synthetic fixture has only one active non-experimental safe point
    # (2000 MHz), so startup bounds must be derived from that actual table.
    assert state["min"] == 2000
    assert state["max"] == 2000
    assert editor.high_frequency_state()["enabled"] is True
    assert "frequency = 2400" in path.read_text(encoding="utf-8")


def test_enabling_high_points_derives_startup_range_from_real_active_table(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "# [frequency-range]\n"
        "# min = 1000\n"
        "# max = 1850\n\n"
        "[[safe-points]]\nfrequency = 1000\nvoltage = 800\n\n"
        "[[safe-points]]\nfrequency = 1500\nvoltage = 900\n\n"
        "[[safe-points]]\nfrequency = 1850\nvoltage = 930\n\n"
        "# [[safe-points]]\n# frequency = 2200\n# voltage = 1050\n",
        encoding="utf-8",
    )
    editor = GovernorTomlEditor(path)

    editor.set_high_frequency_points(True)

    state = editor.frequency_range_state()
    assert state["mode"] == "custom"
    assert state["min"] == 1000
    assert state["max"] == 1850
    assert editor.high_frequency_state()["enabled_frequencies"] == (2200,)


@pytest.mark.parametrize("method", ["busy-flag", "process", "kernel"])
def test_gpu_telemetry_accepts_all_upstream_methods_with_toml_whitespace(
    tmp_path, method
):
    path = tmp_path / "config.toml"
    path.write_text(
        "[gpu-usage]\n"
        "fix-metrics = true\n"
        "fix-freq = false\n"
        f'method    =    "{method}"   # upstream method\n'
        "flush-every = 10\n\n" + SAMPLE,
        encoding="utf-8",
    )

    state = GovernorTomlEditor(path).gpu_telemetry_state()

    assert state["method"] == method
    assert state["set_method"] == "smu"
    assert state["valid"] is True


def test_metrics_fix_can_be_disabled_without_losing_independent_frequency_fix(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[gpu-usage]\n"
        "fix-metrics = true\n"
        "fix-freq = true\n"
        'method = "busy-flag"\n\n' + SAMPLE,
        encoding="utf-8",
    )
    editor = GovernorTomlEditor(path)

    changed = editor.set_gpu_metrics_fix(False)
    after_disable = path.read_text(encoding="utf-8")
    ensured = editor.ensure_gpu_telemetry(fix_frequency=True)
    after_ensure = path.read_text(encoding="utf-8")

    assert changed.changed is True
    assert ensured.changed is False
    assert "fix-metrics = false" in after_disable
    assert "fix-freq = true" in after_disable
    assert after_ensure == after_disable
    assert editor.gpu_telemetry_state() == {
        "fix_metrics": False,
        "fix_frequency": True,
        "method": "busy-flag",
        "temp_read": "drm",
        "set_method": "smu",
        "valid": True,
    }


def test_cyan_compatibility_updates_four_independent_controls_atomically(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[gpu-usage]\n"
        "fix-metrics = true\n"
        "fix-freq = true\n"
        'method = "busy-flag"\n\n'
        "[gpu]\n"
        'set-method = "smu"  # preserve comment\n\n' + SAMPLE,
        encoding="utf-8",
    )
    editor = GovernorTomlEditor(path)

    result = editor.set_cyan_compatibility(
        set_method="kernel",
        usage_method="kernel",
        fix_metrics=False,
        fix_frequency=False,
    )

    assert result.changed is True
    state = editor.gpu_telemetry_state()
    assert state["set_method"] == "kernel"
    assert state["fix_metrics"] is False
    assert state["fix_frequency"] is False
    assert state["method"] == "kernel"
    assert 'set-method = "kernel"  # preserve comment' in path.read_text(
        encoding="utf-8"
    )
    assert (
        editor.set_cyan_compatibility(
            set_method="kernel",
            usage_method="kernel",
            fix_metrics=False,
            fix_frequency=False,
        ).changed
        is False
    )


def test_cyan_compatibility_rejects_invalid_usage_method_without_writing(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[gpu-usage]\n"
        "fix-metrics = true\n"
        "fix-freq = false\n"
        'method = "busy-flag"\n\n'
        "[gpu]\n"
        'set-method = "smu"\n\n' + SAMPLE,
        encoding="utf-8",
    )
    before = path.read_text(encoding="utf-8")

    with pytest.raises(GovernorTomlError, match="busy-flag, process or kernel"):
        GovernorTomlEditor(path).set_cyan_compatibility(
            set_method="kernel",
            usage_method="invalid",
            fix_metrics=False,
            fix_frequency=False,
        )

    assert path.read_text(encoding="utf-8") == before


def test_frequency_floor_never_rewrites_active_maximum_line(tmp_path):
    path = tmp_path / "config.toml"
    custom = SAMPLE.replace(
        "max = 1850", "max    =    1850   # keep exact ceiling formatting"
    )
    path.write_text(custom, encoding="utf-8")
    before_max = next(line for line in custom.splitlines() if line.startswith("max"))

    GovernorTomlEditor(path).set_frequency_floor(500)

    after = path.read_text(encoding="utf-8")
    after_max = next(line for line in after.splitlines() if line.startswith("max"))
    assert after_max == before_max
    assert "min = 500" in after


def test_safe_point_diagnostics_reports_missing_duplicate_and_voltage_order(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[[safe-points]]\nfrequency = 1000\nvoltage = 900\n\n"
        "[[safe-points]]\nfrequency = 1000\nvoltage = 850\n\n"
        "[[safe-points]]\nfrequency = 1500\n\n"
        "# [[safe-points]]\n# frequency = 2400\n# voltage = 1150\n",
        encoding="utf-8",
    )

    state = GovernorTomlEditor(path).safe_point_diagnostics()

    assert state["duplicate_frequencies"] == [1000]
    assert state["missing_voltage"] == [{"frequency": 1500}]
    assert state["max_frequency"] == 1500
    assert state["max_voltage"] == 900
    assert state["voltage_order_errors"] == [
        {
            "previous_frequency": 1000,
            "previous_voltage": 900,
            "frequency": 1000,
            "voltage": 850,
        }
    ]
    assert all(point["frequency"] != 2400 for point in state["points"])


def test_safe_point_diagnostics_rejects_malformed_toml_instead_of_guessing(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[[safe-points]]\nfrequency = 1850garbage\nvoltage = 930\n",
        encoding="utf-8",
    )

    with pytest.raises(GovernorTomlError, match="validation failed"):
        GovernorTomlEditor(path).safe_point_diagnostics()


def test_disabling_high_points_clamps_persisted_high_range_to_loaded_table(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)
    editor.set_high_frequency_points(True)
    editor.set_frequency_range(2200, 2400)

    editor.set_high_frequency_points(False)

    state = editor.frequency_range_state()
    assert state["valid"] is True
    assert state["min"] == 2000
    assert state["max"] == 2000
    assert editor.high_frequency_state()["enabled"] is False


def test_high_point_toggle_refuses_config_without_high_frequency_points(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "# [frequency-range]\n# min = 1000\n# max = 2000\n\n"
        "[[safe-points]]\nfrequency = 1000\nvoltage = 800\n\n"
        "[[safe-points]]\nfrequency = 2000\nvoltage = 960\n",
        encoding="utf-8",
    )
    before = path.read_text(encoding="utf-8")

    with pytest.raises(
        GovernorTomlError, match="does not contain any safe-point above 2000"
    ):
        GovernorTomlEditor(path).set_high_frequency_points(True)

    assert path.read_text(encoding="utf-8") == before


def test_high_point_toggle_rejects_duplicate_active_frequency_before_write(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[frequency-range]\nmin = 1000\nmax = 2000\n\n"
        "[[safe-points]]\nfrequency = 1000\nvoltage = 800\n\n"
        "[[safe-points]]\nfrequency = 2000\nvoltage = 960\n\n"
        "# [[safe-points]]\n# frequency = 2200\n# voltage = 1050\n\n"
        "# [[safe-points]]\n# frequency = 2200\n# voltage = 1060\n",
        encoding="utf-8",
    )
    before = path.read_text(encoding="utf-8")

    with pytest.raises(GovernorTomlError, match="duplicate high-frequency"):
        GovernorTomlEditor(path).set_high_frequency_points(True)

    assert path.read_text(encoding="utf-8") == before


def test_ensure_cyan_telemetry_preserves_valid_kernel_usage_method(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[gpu-usage]\n"
        "fix-metrics = false\n"
        "fix-freq = false\n"
        'method = "kernel"\n'
        "flush-every = 10\n\n" + SAMPLE,
        encoding="utf-8",
    )

    result = GovernorTomlEditor(path).ensure_gpu_telemetry(fix_frequency=True)
    text = path.read_text(encoding="utf-8")

    assert result.changed is True
    assert 'method = "kernel"' in text
    assert "fix-metrics = false" in text
    assert "fix-freq = true" in text


def test_ensure_cyan_telemetry_repairs_only_invalid_usage_method(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[gpu-usage]\n"
        "fix-metrics = true\n"
        "fix-freq = false\n"
        'method = "broken"\n\n' + SAMPLE,
        encoding="utf-8",
    )

    GovernorTomlEditor(path).ensure_gpu_telemetry(fix_frequency=False)

    assert 'method = "busy-flag"' in path.read_text(encoding="utf-8")


TEMP_READ_SAMPLE = (
    "[gpu-usage]\n"
    "fix-metrics = true\n"
    "fix-freq = false\n"
    'method = "busy-flag"\n'
    'temp-read = "drm" # "drm" or "sysfs"\n\n'
    "[gpu]\n"
    'set-method = "smu"\n\n' + SAMPLE
)


def test_temp_read_is_set_in_place_and_keeps_its_comment(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(TEMP_READ_SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)

    editor.set_cyan_compatibility(
        set_method="smu", usage_method="busy-flag", fix_metrics=True,
        fix_frequency=False, temp_read="sysfs",
    )

    assert 'temp-read = "sysfs" # "drm" or "sysfs"' in path.read_text(encoding="utf-8")
    assert editor.gpu_telemetry_state()["temp_read"] == "sysfs"


def test_temp_read_is_left_alone_when_not_given(tmp_path):
    """The Game Mode plugin sends only four values; the line must survive."""
    path = tmp_path / "config.toml"
    path.write_text(TEMP_READ_SAMPLE.replace('"drm" #', '"sysfs" #'), encoding="utf-8")

    GovernorTomlEditor(path).set_cyan_compatibility(
        set_method="kernel", usage_method="busy-flag", fix_metrics=False, fix_frequency=False,
    )

    assert 'temp-read = "sysfs"' in path.read_text(encoding="utf-8")


def test_temp_read_is_added_when_missing_and_defaults_to_drm(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(TEMP_READ_SAMPLE.replace('temp-read = "drm" # "drm" or "sysfs"\n', ""), encoding="utf-8")
    editor = GovernorTomlEditor(path)
    assert editor.gpu_telemetry_state()["temp_read"] == "drm"

    editor.set_cyan_compatibility(
        set_method="smu", usage_method="busy-flag", fix_metrics=True,
        fix_frequency=False, temp_read="sysfs",
    )

    parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    assert parsed["gpu-usage"]["temp-read"] == "sysfs"


def test_the_underscore_spelling_is_rewritten_not_duplicated(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(TEMP_READ_SAMPLE.replace("temp-read =", "temp_read ="), encoding="utf-8")

    GovernorTomlEditor(path).set_cyan_compatibility(
        set_method="smu", usage_method="busy-flag", fix_metrics=True,
        fix_frequency=False, temp_read="sysfs",
    )

    text = path.read_text(encoding="utf-8")
    assert 'temp-read = "sysfs"' in text
    assert "temp_read" not in text


def test_an_invalid_temp_read_writes_nothing(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(TEMP_READ_SAMPLE, encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    with pytest.raises(GovernorTomlError, match="drm or sysfs"):
        GovernorTomlEditor(path).set_cyan_compatibility(
            set_method="smu", usage_method="busy-flag", fix_metrics=True,
            fix_frequency=False, temp_read="hwmon",
        )

    assert path.read_text(encoding="utf-8") == before


def test_the_root_copy_of_the_editor_handles_temp_read_the_same_way(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    source = Path(__file__).resolve().parents[3] / "privileged/lib/governor_toml.py"
    spec = importlib.util.spec_from_file_location("bc250_root_governor_toml", source)
    module = importlib.util.module_from_spec(spec)
    # Its dataclasses resolve annotations through sys.modules.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    # It writes /etc as root; a test file is the user's own.
    monkeypatch.setattr(module, "_require_root_owned", lambda *_args: None)
    path = tmp_path / "config.toml"
    path.write_text(TEMP_READ_SAMPLE, encoding="utf-8")
    editor = module.GovernorTomlEditor(path)

    editor.set_cyan_compatibility(
        set_method="smu", usage_method="busy-flag", fix_metrics=True,
        fix_frequency=False, temp_read="sysfs",
    )
    editor.set_cyan_compatibility(
        set_method="smu", usage_method="busy-flag", fix_metrics=True, fix_frequency=False,
    )

    assert 'temp-read = "sysfs" # "drm" or "sysfs"' in path.read_text(encoding="utf-8")
    assert editor.gpu_telemetry_state()["temp_read"] == "sysfs"


def test_root_decky_gpu_writer_accepts_a_fixed_clock_profile(tmp_path, monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    source = Path(__file__).resolve().parents[3] / "privileged/lib/governor_toml.py"
    spec = importlib.util.spec_from_file_location("bc250_root_decky_writer", source)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_require_root_owned", lambda *_args: None)
    monkeypatch.setattr(module.os, "chown", lambda *_args: None)
    target = tmp_path / "decky-gpu-profiles.json"

    assert module.write_decky_gpu_profiles(
        '[{"key":"balanced","name":"Fixed","min":1500,"max":1500}]', target,
    ).changed



def test_safe_point_state_and_diagnostics_distinguish_commented_points(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)

    assert editor.safe_point_state() == (
        {"frequency": 2000, "voltage": 960, "active": True},
        {"frequency": 2050, "voltage": 980, "active": False},
        {"frequency": 2400, "voltage": 1150, "active": False},
    )
    diagnostics = editor.safe_point_diagnostics()
    assert diagnostics["points"] == [{"frequency": 2000, "voltage": 960}]
    assert diagnostics["max_frequency"] == 2000
    assert diagnostics["missing_voltage"] == []


def test_crlf_edits_preserve_line_endings_and_comments(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(SAMPLE.replace("\n", "\r\n").encode("utf-8"))
    editor = GovernorTomlEditor(path)

    editor.set_frequency_range(700, 1900)
    editor.set_high_frequency_points(True)
    updated = path.read_bytes()
    assert b"\r\n" in updated
    assert b"\n" not in updated.replace(b"\r\n", b"")
    assert b"# keep this comment\r\n" in updated
    assert b"min = 700    # MHz\r\n" in updated
    tomllib.loads(updated.decode("utf-8"))


@pytest.mark.parametrize(
    ("values", "message"),
    (
        ({0: 800}, "frequency"),
        ({1000: 0}, "voltage"),
        ({1000: 900, 1500: 850}, "decreases"),
    ),
)
def test_voltage_curve_validation_rejects_unsafe_curves(values, message):
    with pytest.raises(GovernorTomlError, match=message):
        validate_voltage_curve(values)


def test_voltage_profiles_are_complete_and_level_zero_restores_defaults():
    level_zero = voltage_profile(0)
    boosted = voltage_profile(3)
    assert level_zero
    assert level_zero[2000] < boosted[2000]
    assert level_zero[1850] == boosted[1850]
    with pytest.raises(GovernorTomlError, match="Unsupported voltage level"):
        voltage_profile(99)


def test_custom_voltages_update_only_active_points_and_reject_missing_targets(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    editor = GovernorTomlEditor(path)

    result = editor.set_custom_voltages({2000: 970})
    assert result.changed is True
    assert result.frequencies == (2000,)
    updated = path.read_text(encoding="utf-8")
    assert "voltage = 970" in updated
    assert "# voltage = 980" in updated
    with pytest.raises(GovernorTomlError, match="not present"):
        editor.set_custom_voltages({1800: 900})
    assert path.read_text(encoding="utf-8") == updated


def test_duplicate_managed_keys_are_rejected_without_writing(tmp_path):
    path = tmp_path / "config.toml"
    original = "[gpu-usage]\nfix-freq = false\nfix_freq = true\n"
    path.write_text(original, encoding="utf-8")
    with pytest.raises(GovernorTomlError, match="Duplicate gpu-usage.fix-freq"):
        GovernorTomlEditor(path).set_gpu_metrics_fix(True)
    assert path.read_text(encoding="utf-8") == original


def test_atomic_write_refusal_keeps_original_configuration(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    original = path.read_bytes()

    def refuse_replace(_source, _destination):
        raise PermissionError("filesystem refused replacement")

    monkeypatch.setattr(os, "replace", refuse_replace)
    with pytest.raises(GovernorTomlError, match="could not be updated"):
        GovernorTomlEditor(path).set_frequency_range(700, 1900)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".config.toml.*.tmp"))


def test_oberon_yaml_edit_preserves_comments_and_validates_safe_bounds(tmp_path):
    path = tmp_path / "opps.yaml"
    path.write_text(
        "# keep this comment\nfrequency:\n  min: 500\n  max: 2000 # stock\n"
        "voltage:\n  min: 850\n  max: 1150\n",
        encoding="utf-8",
    )
    editor = OberonYamlEditor(path)
    result = editor.set_operating_points(600, 1900, 930, 1200)
    assert result.changed is True
    assert editor.state() == {
        "frequency_min": 600,
        "frequency_max": 1900,
        "voltage_min": 930,
        "voltage_max": 1200,
        "safe_voltage": True,
    }
    assert "# keep this comment" in path.read_text(encoding="utf-8")
    with pytest.raises(OberonYamlError, match="minimum frequency"):
        editor.set_operating_points(400, 1900, 930, 1200)
