import pytest

from bc250cc.infrastructure.gpu.governor_toml import (
    CUSTOM_VOLTAGE_MAX_MV,
    GOVERNOR_DEFAULT_SAFE_POINTS,
    GOVERNOR_DEFAULT_VOLTAGES,
    VOLTAGE_BOOST_START_MHZ,
    GovernorTomlEditor,
    GovernorTomlError,
    _parse_custom_pairs,
    main,
    voltage_profile,
)
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def _packaged_config() -> str:
    blocks = []
    for frequency, voltage in GOVERNOR_DEFAULT_SAFE_POINTS:
        prefix = "" if frequency <= 2000 else "# "
        blocks.append(
            f"{prefix}[[safe-points]]\n"
            f"{prefix}frequency = {frequency}\n"
            f"{prefix}voltage = {voltage}\n"
        )
    return (
        "# preserve this header\n"
        "[frequency-range]\n"
        "min = 1000    # MHz\n"
        "max = 1850   # MHz\n\n"
        "[temperature]\n"
        "throttling = 85\n\n"
        + "\n".join(blocks)
    )


@pytest.mark.parametrize(
    "level,addition",
    tuple((level, level * 10) for level in range(7)),
)
def test_profiles_modify_every_point_from_2000_mhz(level, addition):
    profile = voltage_profile(level)

    assert tuple(profile) == tuple(GOVERNOR_DEFAULT_VOLTAGES)
    assert 2230 in profile
    for frequency, original in GOVERNOR_DEFAULT_SAFE_POINTS:
        expected_addition = addition if frequency >= VOLTAGE_BOOST_START_MHZ else 0
        assert profile[frequency] == original + expected_addition


def test_level_zero_restores_the_complete_original_document_idempotently(tmp_path):
    path = tmp_path / "config.toml"
    original = _packaged_config()
    path.write_text(original, encoding="utf-8")
    editor = GovernorTomlEditor(path)

    editor.set_high_frequency_points(True)
    editor.set_voltage_profile(3)
    editor.set_voltage_profile(6)
    restored = editor.set_voltage_profile(0)

    assert restored.changed is True
    assert path.read_text(encoding="utf-8") == original
    assert editor.set_voltage_profile(0).changed is False
    assert path.read_text(encoding="utf-8") == original


def test_profile_updates_commented_high_points_without_uncommenting_them(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(_packaged_config(), encoding="utf-8")

    GovernorTomlEditor(path).set_voltage_profile(3)
    updated = path.read_text(encoding="utf-8")

    assert "# frequency = 2230\n# voltage = 1115" in updated
    assert "# frequency = 2400\n# voltage = 1180" in updated
    assert "\nfrequency = 2000\nvoltage = 990" in updated


def test_missing_packaged_point_aborts_without_partial_write(tmp_path):
    path = tmp_path / "config.toml"
    original = _packaged_config().replace(
        "# [[safe-points]]\n# frequency = 2230\n# voltage = 1085\n\n",
        "",
    )
    path.write_text(original, encoding="utf-8")

    with pytest.raises(GovernorTomlError, match="2230"):
        GovernorTomlEditor(path).set_voltage_profile(3)

    assert path.read_text(encoding="utf-8") == original


def test_the_voltage_levels_follow_the_shared_profile_rules(qtbot):
    """The "Original"/"Proposed" column headers this test used to pin belonged
    to ``VoltageCurveGrid``, the table of the deleted voltage-lab page.  The
    drawer that replaced it shows one editable value per row and no such
    columns, so there is nothing left to assert about them.  What does still
    matter — which voltage each profile level maps a frequency to — is below.
    """
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)

    assert page._voltage_for_level(2200, 3) == 1080
    assert page._voltage_for_level(2230, 3) == 1115
    assert page._voltage_for_level(2400, 6) == 1210


def test_high_oc_range_requires_every_level_three_point(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.safe_voltage_map = dict(GOVERNOR_DEFAULT_SAFE_POINTS)

    gaps = page._high_oc_voltage_gaps(2200)

    assert [frequency for frequency, _required, _current in gaps] == [
        2000,
        2050,
        2100,
        2125,
        2150,
        2200,
    ]
    page.safe_voltage_map = voltage_profile(3)
    assert page._high_oc_voltage_gaps(2400) == ()


def test_high_oc_range_validation_warns_for_partial_curve_without_blocking(qtbot, monkeypatch):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.allowed_min = 500
    page.allowed_max = 2400
    page.safe_frequencies = list(GOVERNOR_DEFAULT_VOLTAGES)
    page.safe_voltage_map = voltage_profile(3)
    page.safe_voltage_map[2230] = GOVERNOR_DEFAULT_VOLTAGES[2230]
    page.current_state = {
        "safe_points_voltage_errors": [],
        "dbus_ok": True,
        "cyan_telemetry": {"set_method": "kernel"},
    }
    messages = []
    monkeypatch.setattr(
        page,
        "_show_info",
        lambda title, message, **kwargs: messages.append((title, message, kwargs)),
    )

    valid, warning = page._validate_range(1000, 2400)

    assert valid is True
    assert "experimental" in warning
    assert messages == []


def test_safe_point_state_includes_active_and_commented_points(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(_packaged_config(), encoding="utf-8")

    points = GovernorTomlEditor(path).safe_point_state()

    assert len(points) == len(GOVERNOR_DEFAULT_SAFE_POINTS)
    assert next(point for point in points if point["frequency"] == 2000)["active"] is True
    assert next(point for point in points if point["frequency"] == 2230)["active"] is False


def test_custom_voltage_edit_changes_only_requested_active_point(tmp_path):
    path = tmp_path / "config.toml"
    original = _packaged_config()
    path.write_text(original, encoding="utf-8")

    result = GovernorTomlEditor(path).set_custom_voltages({2000: 990})
    updated = path.read_text(encoding="utf-8")

    assert result.frequencies == (2000,)
    assert "\nfrequency = 2000\nvoltage = 990" in updated
    assert "# frequency = 2050\n# voltage = 980" in updated


@pytest.mark.parametrize(
    "values,match",
    (
        ({}, "No custom"),
        ({2050: 1010}, "not present"),
        ({2000: CUSTOM_VOLTAGE_MAX_MV + 1}, "outside"),
    ),
)
def test_custom_voltage_rejects_invalid_requests_without_writing(tmp_path, values, match):
    path = tmp_path / "config.toml"
    original = _packaged_config()
    path.write_text(original, encoding="utf-8")

    with pytest.raises(GovernorTomlError, match=match):
        GovernorTomlEditor(path).set_custom_voltages(values)

    assert path.read_text(encoding="utf-8") == original


def test_cli_preview_status_and_apply_use_the_same_curve(tmp_path, capsys):
    path = tmp_path / "config.toml"
    path.write_text(_packaged_config(), encoding="utf-8")

    assert main(["preview-voltage-level", "3"]) == 0
    assert "2230  1085       1115" in capsys.readouterr().out
    assert main(["status", str(path)]) == 0
    assert "2230  commented  1085" in capsys.readouterr().out
    assert main(["apply-voltage-level", str(path), "3"]) == 0
    assert "changed MHz" in capsys.readouterr().out
    assert main(["apply-custom-voltage", str(path), "2000=1000"]) == 0
    assert "changed MHz: 2000" in capsys.readouterr().out


def test_custom_pair_parser_rejects_duplicates_and_malformed_values():
    assert _parse_custom_pairs(["2000=990", "2200=1080"]) == {
        2000: 990,
        2200: 1080,
    }
    with pytest.raises(GovernorTomlError, match="Duplicate"):
        _parse_custom_pairs(["2000=990", "2000=1000"])
    with pytest.raises(GovernorTomlError, match="Invalid"):
        _parse_custom_pairs(["not-a-pair"])
    with pytest.raises(GovernorTomlError, match="Invalid"):
        _parse_custom_pairs(["2000=bad"])
