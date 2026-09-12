from bc250cc.application.gpu.voltage_lab_state import (
    build_voltage_lab_state,
    voltage_for_level,
)
from bc250cc.infrastructure.gpu.governor_toml import (
    GOVERNOR_DEFAULT_SAFE_POINTS,
    voltage_profile,
)
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def _points(values):
    return [{"frequency": frequency, "voltage": voltage} for frequency, voltage in values]


def test_voltage_lab_normalizes_sorts_and_uses_last_duplicate():
    state = build_voltage_lab_state({
        "safe_points_with_voltage": [
            {"frequency": 1850, "voltage": 920},
            "invalid",
            {"frequency": 1000, "voltage": 800},
            {"frequency": 1850, "voltage": 930},
            {"frequency": 0, "voltage": 1000},
        ],
        "current_min": "1000",
        "current_max": "1850",
    })
    assert state.points == ((1000, 800), (1850, 930))
    assert state.current_voltages == state.points
    assert state.editable_frequencies == (1000, 1850)
    assert (state.active_min, state.active_max, state.maximum_voltage) == (1000, 1850, 930)


def test_voltage_lab_detects_each_packaged_profile_level():
    for level in range(7):
        curve = voltage_profile(level)
        state = build_voltage_lab_state({"safe_points_with_voltage": _points(curve.items())})
        assert state.detected_level == level
        assert state.safety_valid is True


def test_voltage_lab_uses_curve_fallback_for_missing_voltage_and_reports_errors():
    state = build_voltage_lab_state({
        "safe_points": [{"frequency": 1000, "voltage": 0}],
        "safe_points_voltage_errors": [{"frequency": 1000}],
    })
    assert state.current_voltages == ()
    assert state.custom_defaults == ((1000, 800),)
    assert state.curve_error_count == 1
    assert state.safety_valid is False


def test_oberon_profiles_only_include_active_endpoints_and_clamp_fallback():
    state = build_voltage_lab_state({
        "governor_backend": "oberon-governor",
        "safe_points_with_voltage": [
            {"frequency": 1000, "voltage": 0},
            {"frequency": 1850, "voltage": 950},
        ],
    })
    assert state.is_oberon is True
    assert state.profile_frequencies == (1000, 1850)
    assert dict(state.custom_defaults)[1000] == 920
    assert voltage_for_level(500, 0, is_oberon=True) == 920
    assert voltage_for_level(500, 0, is_oberon=False) == 700


def test_oberon_voltage_lab_is_diagnostic_only_in_the_qt_page(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page._sync_voltage_lab({
        "governor_backend": "oberon-governor",
        "safe_points_with_voltage": [
            {"frequency": 1000, "voltage": 920},
            {"frequency": 1850, "voltage": 930},
        ],
        "current_min": 1000,
        "current_max": 1850,
    })

    # Oberon has two YAML endpoints, not a curve, so the drawer shows them and
    # offers nothing to change: no profiles, no apply footer, no editors.
    drawer = page.voltage_lab_drawer
    # isHidden, not isVisible: the drawer itself has not been shown in this
    # test, and every child of an unshown parent reports isVisible() False.
    assert drawer.profiles_card.isHidden() is True
    assert drawer.footer.isHidden() is True
    assert drawer.compatibility_note.isHidden() is False
    assert drawer.editors() == ()
    assert page._voltage_points == [(1000, 920), (1850, 930)]
    assert page._is_oberon_backend is True


def test_voltage_lab_prefers_voltage_aware_points_and_preserves_defaults():
    state = build_voltage_lab_state({
        "safe_points_with_voltage": _points(GOVERNOR_DEFAULT_SAFE_POINTS[:2]),
        "safe_points": [{"frequency": 2400, "voltage": 1210}],
        "current_min": "invalid",
        "current_max": None,
    }, active_min_default=900, active_max_default=1900)
    assert state.editable_frequencies == (500, 1000)
    assert (state.active_min, state.active_max) == (900, 1900)


def test_voltage_lab_qt_adapter_preserves_user_edits_and_applies_pure_state(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page._voltage_custom_values[1000] = 825
    page._sync_voltage_lab({
        "safe_points_with_voltage": [
            {"frequency": 1000, "voltage": 800},
            {"frequency": 1850, "voltage": 930},
        ],
        "current_min": 1000,
        "current_max": 1850,
    })
    assert page._voltage_points == [(1000, 800), (1850, 930)]
    assert page._voltage_custom_values[1000] == 825
    assert page._voltage_custom_values[1850] == 930
    assert page._voltage_editable_frequencies == {1000, 1850}
    # A named profile renders the curve read-only; custom mode is the only
    # state in which the points can be typed into.
    drawer = page.voltage_lab_drawer
    assert set(drawer._editors) <= {1000, 1850}
    assert all(not editor.isEnabled() for editor in drawer.editors())

    page._select_drawer_voltage_profile(-1)
    assert set(drawer._editors) == {1000, 1850}
    assert all(editor.isEnabled() for editor in drawer.editors())
    assert "safe points" in drawer.profile_detail.text()
