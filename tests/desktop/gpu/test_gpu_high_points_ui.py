from pathlib import Path

from PyQt6.QtWidgets import QDialog, QPushButton

import frontends.desktop.pages.gpu_governor as gpu_page_module
from bc250cc.infrastructure.gpu.governor_toml import voltage_profile
from frontends.desktop.i18n import translation_coverage
from frontends.desktop.pages.gpu_governor import GpuGovernorPage

ACTIVE_POINTS = [
    {"frequency": 1850, "voltage": 975},
    {"frequency": 2000, "voltage": 1000},
    {"frequency": 2050, "voltage": 1020},
    {"frequency": 2400, "voltage": 1150},
]


HIGH_POINT_FLOW_COPY = (
    "Enable advanced +2000 MHz points",
    "Disable advanced +2000 MHz points",
    "This edits only the TOML safe-point blocks above 2000 MHz and validates the complete file. These frequencies are experimental, are not guaranteed stable, and can crash the display or system. This does not reload Cyan or change the live GPU range; use Apply active range explicitly after selecting a point.",
    "This comments the TOML safe-point blocks above 2000 MHz and validates the complete file. Active 3D workloads must be stopped first. This does not reload Cyan or change the live GPU range.",
    "Safe-points",
    "Requested state",
    "Enabled",
    "Commented",
    "Validation",
    "Full TOML parse before replacement",
    "Service",
    "No restart or clock change",
    "Keep disabled; no automatic start",
    "Enable advanced points",
    "Disable advanced points",
    "Advanced safe-points",
    "Could not update advanced safe-points",
    "Apply a range at or below 2000 MHz before disabling the +2000 MHz TOML points. The live GPU range was not changed.",
)


def test_high_point_flow_has_complete_translation_coverage():
    assert translation_coverage(HIGH_POINT_FLOW_COPY) == {}


def _page(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.current_state = {
        "dbus_ok": True,
        "service_active": "active",
        "cyan_telemetry": {"set_method": "kernel"},
        "high_frequency_points": {
            "available": True,
            "frequencies": (2050, 2400),
            "enabled_frequencies": (),
            "enabled": False,
        },
        "tools": {"incompatible_gpu_governors": []},
    }
    return page


def test_high_oc_points_are_visible_without_a_separate_show_button(qtbot):
    page = _page(qtbot)
    page._populate_points(ACTIVE_POINTS, 2000)

    assert not hasattr(page, "experimental_toggle")
    assert not hasattr(page, "fixed_button")
    assert [
        page.oc_frequency.itemData(index)
        for index in range(page.oc_frequency.count())
    ] == [1850, 2000, 2050, 2400]

    button_texts = {button.text() for button in page.findChildren(QPushButton)}
    assert not any("Show high OC points" in text for text in button_texts)
    assert "Review fixed safe-point" not in button_texts


def test_reference_panels_are_hidden_and_console_uses_their_row(qtbot):
    page = _page(qtbot)

    assert page.safe_points_panel.isHidden()
    assert page.diagnostics_panel.isHidden()
    index = page.advanced_grid.indexOf(page.console_panel)
    assert page.advanced_grid.getItemPosition(index) == (1, 0, 1, 2)
    assert page.console.minimumHeight() == 330


def test_oberon_desktop_mode_replaces_cyan_profiles_with_its_fixed_profiles(qtbot):
    page = _page(qtbot)

    page._set_backend_profile_mode(True)

    visible = [button for button in page.preset_buttons if not button.isHidden()]
    # Benchmark is (1000, 2000): the shape Quick Access has always written,
    # and the one the desktop validator used to reject.
    assert [button.payload for button in visible] == [
        (1000, 1500),
        (1000, 1850),
        (1000, 2000),
    ]
    assert [button.text().splitlines()[0] for button in visible] == [
        "Balanced", "Gaming",
        "Benchmark",
    ]
    assert all(field.isHidden() for field in page.range_fields)
    assert page.use_active_button.isHidden()
    assert page.apply_range_button.text() == "Review and apply Oberon profile"

    page._set_backend_profile_mode(False)
    assert [button.payload for button in page.preset_buttons] == [
        (500, 1500),
        (1000, 1850),
        (1000, 2000),
    ]
    assert not any(button.isHidden() for button in page.preset_buttons)


def test_oberon_gaming_stays_selectable_and_action_row_has_no_ghost_column(qtbot):
    page = _page(qtbot)
    page.current_state.update({
        "governor_backend": "oberon-governor",
        # A stale old snapshot must not hide the 2000 MHz Oberon profile.
        "allowed_min": 1000,
        "allowed_max": 1500,
    })
    page._set_backend_profile_mode(True)
    page._update_profile_availability()

    gaming = [button for button in page.preset_buttons if not button.isHidden()][1]
    assert gaming.isEnabled()
    gaming.click()
    assert gaming.isChecked()
    assert (page.minimum_control.value(), page.maximum_control.value()) == (1000, 1850)
    assert page.range_actions_grid.itemAtPosition(0, 0).widget() is page.apply_range_button
    assert page.range_actions_grid.count() == 1


def test_toml_toggle_occupies_the_removed_fixed_action_position(qtbot):
    page = _page(qtbot)

    assert page.fixed_actions.itemAtPosition(1, 0).widget() is page.oc_frequency
    assert page.fixed_actions.itemAtPosition(1, 1).widget() is page.open_toml_button
    assert page.fixed_actions.itemAtPosition(2, 0).widget() is page.apply_selected_range_button
    assert page.fixed_actions.itemAtPosition(2, 1).widget() is page.high_points_button
    assert page.fixed_actions.columnStretch(0) == page.fixed_actions.columnStretch(1) == 1
    assert page.safe_point_detail.isHidden()
    assert not hasattr(page, "selected_range_detail")
    assert page.high_points_button.text() == "Enable +2000 MHz TOML points"


def test_confirmed_enable_updates_high_oc_warning_immediately(qtbot, monkeypatch):
    page = _page(qtbot)

    class AcceptedDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(gpu_page_module, "ConfirmDialog", AcceptedDialog)
    page.controller = type(
        "Controller",
        (),
        {"alternar_puntos_gpu_altos": lambda self, enabled: "TOML updated"},
    )()

    def run_now(operation, on_success, _error_title, **_kwargs):
        on_success(operation())
        return True

    monkeypatch.setattr(page, "_run_backend_action", run_now)
    page._request_high_points_toggle()

    state = page.current_state["high_frequency_points"]
    assert state["enabled"] is True
    assert state["enabled_frequencies"] == (2050, 2400)
    assert page.high_points_button.text() == "Disable +2000 MHz TOML points"
    assert page.safety_notice.title.text() == "High OC laboratory mode"
    assert "above 2000 MHz are visible by default" in page.safety_notice.body.text()
    assert page.configuration_status is None


def test_confirmed_disable_restores_safe_notice_without_waiting_for_refresh(qtbot):
    page = _page(qtbot)
    page.current_state["high_frequency_points"]["enabled"] = True
    page.current_state["high_frequency_points"]["enabled_frequencies"] = (2050, 2400)
    page.safe_frequencies = [1850, 2000, 2050, 2400]

    page._apply_high_points_toggle_feedback(False)

    state = page.current_state["high_frequency_points"]
    assert state["enabled"] is False
    assert state["enabled_frequencies"] == ()
    assert page.high_points_button.text() == "Enable +2000 MHz TOML points"
    assert page.safety_notice.title.text() == "Safe mode enabled"


def test_cancelled_toggle_does_not_change_warning_or_state(qtbot, monkeypatch):
    page = _page(qtbot)

    class RejectedDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Rejected

    monkeypatch.setattr(gpu_page_module, "ConfirmDialog", RejectedDialog)
    page._update_safety_notice(page.current_state)
    page._request_high_points_toggle()

    assert page.current_state["high_frequency_points"]["enabled"] is False
    assert page.high_points_button.text() == "Enable +2000 MHz TOML points"
    assert page.safety_notice.title.text() == "Safe mode enabled"


def test_selected_safe_point_applies_a_fixed_1000_mhz_floor(qtbot, monkeypatch):
    page = _page(qtbot)
    page.allowed_max = 2400
    complete_level_three = [
        {"frequency": frequency, "voltage": voltage}
        for frequency, voltage in voltage_profile(3).items()
    ]
    page._populate_points(complete_level_three, 2000)
    page.oc_frequency.setCurrentIndex(page.oc_frequency.findData(2400))
    requested = []

    class AcceptedDialog:
        def __init__(self, *args, **kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(gpu_page_module, "ConfirmDialog", AcceptedDialog)
    page.controller = type(
        "Controller",
        (),
        {
            "aplicar_perfil_gpu": lambda self, minimum, maximum: requested.append(
                (minimum, maximum)
            )
        },
    )()

    def run_now(operation, on_success, _error_title, **_kwargs):
        on_success(operation())
        return True

    monkeypatch.setattr(page, "_run_backend_action", run_now)
    page._request_selected_safe_point_range()

    assert requested == [(1000, 2400)]
    assert page.apply_selected_range_button.text() == (
        "Apply active range · 1000–2400 MHz"
    )
    assert "1000–2400 MHz" in page._last_operation_summary


def test_enabled_high_points_allow_a_stale_dbus_ceiling_until_apply_reloads_cyan(qtbot):
    page = _page(qtbot)
    page.allowed_max = 2000
    page.current_state["high_frequency_points"]["enabled"] = True
    page.current_state["high_frequency_points"]["enabled_frequencies"] = (2050, 2400)
    complete_level_three = [
        {"frequency": frequency, "voltage": voltage}
        for frequency, voltage in voltage_profile(3).items()
    ]
    page._populate_points(complete_level_three, 2000)

    valid, warning = page._validate_range(1000, 2200)

    assert valid is True
    assert "3D workload" in warning


def test_disabled_high_points_still_reject_a_safe_point_above_dbus_ceiling(qtbot, monkeypatch):
    page = _page(qtbot)
    page.allowed_max = 2000
    notices = []
    monkeypatch.setattr(
        page,
        "_show_info",
        lambda title, message, **_kwargs: notices.append((title, message)),
    )
    complete_level_three = [
        {"frequency": frequency, "voltage": voltage}
        for frequency, voltage in voltage_profile(3).items()
    ]
    page._populate_points(complete_level_three, 2000)

    valid, _warning = page._validate_range(1000, 2200)

    assert valid is False
    assert notices[0][0] == "Range outside allowed limits"


def test_selected_range_is_disabled_below_the_1000_mhz_floor(qtbot):
    page = _page(qtbot)
    page._populate_points(
        [{"frequency": 500, "voltage": 700}, {"frequency": 1000, "voltage": 800}],
        500,
    )

    assert page.oc_frequency.currentData() == 500
    assert page.apply_selected_range_button.isEnabled() is False


def test_passive_refresh_does_not_reset_gamepad_highlight(qtbot):
    page = _page(qtbot)
    page._populate_points(ACTIVE_POINTS, 2000)
    view = page.oc_frequency.view()
    highlighted = view.model().index(page.oc_frequency.findData(2400), 0)
    view.setCurrentIndex(highlighted)

    page._populate_points(ACTIVE_POINTS, 2000)

    assert view.currentIndex().row() == highlighted.row()
    assert page.oc_frequency.currentData() == 2000


def test_changed_safe_points_wait_until_combo_popup_closes(qtbot, monkeypatch):
    page = _page(qtbot)
    page._populate_points(ACTIVE_POINTS, 2000)
    updated = [*ACTIVE_POINTS, {"frequency": 2350, "voltage": 1130}]
    popup_visible = True
    monkeypatch.setattr(
        page,
        "_safe_point_popup_visible",
        lambda: popup_visible,
    )

    page._populate_points(updated, 2000)
    assert page.oc_frequency.findData(2350) == -1

    popup_visible = False
    page._populate_points(updated, 2000)
    assert page.oc_frequency.findData(2350) >= 0


def test_removed_safe_point_cannot_be_applied_during_deferred_refresh(
    qtbot,
    monkeypatch,
):
    page = _page(qtbot)
    page._populate_points(ACTIVE_POINTS, 2000)
    page.oc_frequency.setCurrentIndex(page.oc_frequency.findData(2400))
    monkeypatch.setattr(page, "_safe_point_popup_visible", lambda: True)

    page._populate_points(ACTIVE_POINTS[:-1], 2000)

    assert page.oc_frequency.currentData() == 2400
    assert page.apply_selected_range_button.isEnabled() is False


def test_open_toml_uses_the_exact_governor_config_path(qtbot, monkeypatch):
    page = _page(qtbot)
    received = []
    monkeypatch.setattr(Path, "is_file", lambda path: path == page.GOVERNOR_CONFIG_PATH)

    monkeypatch.setattr(
        gpu_page_module,
        "open_local_file",
        lambda path: (received.append(path) or True, ""),
    )
    page._open_governor_config()

    assert received == [page.GOVERNOR_CONFIG_PATH]


def test_open_toml_failure_is_reported_without_crashing(qtbot, monkeypatch):
    page = _page(qtbot)
    reported = []
    monkeypatch.setattr(Path, "is_file", lambda path: path == page.GOVERNOR_CONFIG_PATH)

    monkeypatch.setattr(
        gpu_page_module,
        "open_local_file",
        lambda _path: (False, "No text editor accepted the file."),
    )
    monkeypatch.setattr(
        page,
        "_show_info",
        lambda title, message, **kwargs: reported.append((title, message, kwargs)),
    )
    page._open_governor_config()

    assert reported
    assert reported[0][0] == "Governor configuration could not be opened"
    assert str(page.GOVERNOR_CONFIG_PATH) in reported[0][1]


def test_successful_hardware_action_refreshes_after_busy_state_clears(
    qtbot,
    monkeypatch,
):
    page = _page(qtbot)
    events = []

    class ImmediateBackground:
        def start(
            self,
            _key,
            operation,
            on_success,
            _on_error,
            on_finished,
        ):
            on_success(operation())
            on_finished()
            return True

    class Cache:
        def invalidate(self, *areas):
            events.append(("invalidate", areas))

    page._background = ImmediateBackground()
    page._state_cache = Cache()
    monkeypatch.setattr(
        page,
        "refresh",
        lambda: events.append(("refresh", page._action_busy)),
    )

    assert page._run_backend_action(
        lambda: "ok",
        lambda result: events.append(("success", result)),
        "failed",
        controls=(page.apply_selected_range_button,),
    )

    assert events == [
        ("success", "ok"),
        ("invalidate", ("gpu", "performance", "tools")),
        ("refresh", False),
    ]


def test_backend_failure_reconciles_state_and_restores_original_control_state(
    qtbot, monkeypatch
):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    callbacks = {}
    events = []

    class DeferredBackground:
        def start(self, _key, _operation, success, failure, finished):
            callbacks.update(success=success, failure=failure, finished=finished)
            return True

    class Cache:
        def invalidate(self, *areas):
            events.append(("invalidate", areas))

    page._background = DeferredBackground()
    page._state_cache = Cache()
    page.apply_selected_range_button.setEnabled(False)
    monkeypatch.setattr(page, "refresh", lambda: events.append(("refresh", page._action_busy)))
    monkeypatch.setattr(page, "_show_info", lambda *args, **kwargs: events.append(("error", args[0])))
    monkeypatch.setattr(page, "_append_console", lambda message: events.append(("console", message)))

    assert page._run_backend_action(
        lambda: None,
        lambda _result: events.append(("success",)),
        "GPU action failed",
        controls=(page.apply_selected_range_button,),
    )
    callbacks["failure"]("partial failure")
    callbacks["finished"]()

    assert page._action_busy is False
    assert page.apply_selected_range_button.isEnabled() is False
    assert ("invalidate", ("gpu", "performance", "tools")) in events
    assert ("refresh", False) in events


def test_late_success_and_result_handler_exceptions_cannot_leave_action_stuck(
    qtbot, monkeypatch
):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    callbacks = {}
    events = []

    class DeferredBackground:
        def start(self, _key, _operation, success, failure, finished):
            callbacks.update(success=success, failure=failure, finished=finished)
            return True

    page._background = DeferredBackground()
    page._state_cache = type("Cache", (), {"invalidate": lambda _self, *_areas: None})()
    monkeypatch.setattr(page, "refresh", lambda: events.append("refresh"))
    monkeypatch.setattr(page, "_show_info", lambda title, message, **_kwargs: events.append((title, message)))
    monkeypatch.setattr(page, "_append_console", lambda _message: None)

    def broken_handler(_result):
        raise RuntimeError("render exploded")

    assert page._run_backend_action(lambda: None, broken_handler, "GPU action failed")
    callbacks["success"]("changed")
    callbacks["finished"]()
    callbacks["success"]("late")

    assert page._action_busy is False
    assert events.count("refresh") == 1
    assert any(
        "render exploded" in item[1]
        for item in events
        if isinstance(item, tuple)
    )
