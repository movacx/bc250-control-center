import pytest
from PyQt6.QtWidgets import QDialog

import frontends.desktop.pages.gpu_governor as gpu_page_module
from bc250cc.application.gpu.voltage_apply import plan_voltage_apply
from bc250cc.infrastructure.gpu.governor_toml import voltage_profile
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def test_voltage_apply_reports_unavailable_without_profile_points():
    plan = plan_voltage_apply(
        level=0,
        editable_frequencies=(),
        profile_frequencies=(),
        current_voltages={},
    )
    assert plan.available is False
    assert plan.active_frequencies == ()
    assert plan.violation is None


@pytest.mark.parametrize("level", tuple(range(7)))
def test_voltage_apply_builds_complete_packaged_profile(level):
    frequencies = (1000, 2000, 2400)
    plan = plan_voltage_apply(
        level=level,
        editable_frequencies=frequencies,
        profile_frequencies=frequencies,
        current_voltages={1000: 750, 2000: 950, 2400: 1100},
    )
    expected = voltage_profile(level)
    assert plan.available is True
    assert dict(plan.proposed_values) == {
        frequency: expected[frequency] for frequency in frequencies
    }
    assert plan.maximum_voltage == expected[2400]
    assert plan.custom_values == ()
    assert plan.violation is None


def test_custom_voltage_plan_contains_only_active_editor_values():
    plan = plan_voltage_apply(
        level=-1,
        editable_frequencies=(1000, 1850),
        profile_frequencies=(500, 1000, 1850, 2000),
        current_voltages={500: 700, 1000: 800, 1850: 930},
        custom_values={1000: 820, 1850: 950, 2400: 1200},
    )
    assert plan.custom_mode is True
    assert plan.active_frequencies == (1000, 1850)
    assert plan.custom_values == ((1000, 820), (1850, 950))
    assert plan.proposed_values == plan.custom_values
    assert plan.maximum_voltage == 950


def test_voltage_plan_validates_merged_curve_including_unchanged_points():
    plan = plan_voltage_apply(
        level=-1,
        editable_frequencies=(1850,),
        profile_frequencies=(),
        current_voltages={1000: 900, 1850: 880, 2000: 960},
        custom_values={1850: 880},
    )
    violation = plan.violation
    assert violation is not None
    assert (
        violation.frequency,
        violation.voltage,
        violation.previous_frequency,
        violation.previous_voltage,
    ) == (1850, 880, 1000, 900)


def test_oberon_profile_uses_the_safe_voltage_floor():
    plan = plan_voltage_apply(
        level=0,
        editable_frequencies=(500, 1000),
        profile_frequencies=(500, 1000),
        current_voltages={500: 700, 1000: 800},
        is_oberon=True,
    )
    assert dict(plan.proposed_values) == {500: 920, 1000: 920}
    assert plan.maximum_voltage == 920
    assert plan.violation is None


def test_voltage_plan_rejects_unreachable_profile_levels():
    with pytest.raises(ValueError, match="Unsupported GPU voltage level"):
        plan_voltage_apply(
            level=7,
            editable_frequencies=(1000,),
            profile_frequencies=(1000,),
            current_voltages={1000: 800},
        )


class _AcceptedDialog:
    last_summary = ()

    def __init__(self, _title, _message, *, summary=(), **_kwargs):
        type(self).last_summary = tuple(summary)

    def exec(self):
        return QDialog.DialogCode.Accepted


class _Controller:
    def __init__(self):
        self.calls = []

    def aplicar_laboratorio_voltaje_gpu(self, level):
        self.calls.append(("level", level))
        return "ok"

    def aplicar_laboratorio_voltaje_gpu_personalizado(self, values):
        self.calls.append(("custom", dict(values)))
        return "ok"


def test_voltage_apply_qt_adapter_dispatches_the_planned_profile(qtbot, monkeypatch):
    controller = _Controller()
    page = GpuGovernorPage(controller)
    qtbot.addWidget(page)
    page._sync_voltage_lab({
        "safe_points_with_voltage": [
            {"frequency": frequency, "voltage": voltage}
            for frequency, voltage in voltage_profile(0).items()
        ]
    })
    # The drawer is the only voltage surface; it carries the selected profile.
    page.voltage_lab_drawer.set_profile(3)
    captured = []
    page._run_backend_action = lambda operation, *_args, **_kwargs: captured.append(operation)
    monkeypatch.setattr(gpu_page_module, "ConfirmDialog", _AcceptedDialog)

    page._request_apply_voltage_curve_from_drawer()

    assert dict(_AcceptedDialog.last_summary)["Curve points"] == str(len(voltage_profile(0)))
    assert len(captured) == 1
    assert captured[0]() == "ok"
    assert controller.calls == [("level", 3)]


def test_voltage_apply_qt_adapter_blocks_invalid_custom_curve(qtbot, monkeypatch):
    controller = _Controller()
    page = GpuGovernorPage(controller)
    qtbot.addWidget(page)
    page._sync_voltage_lab({
        "safe_points_with_voltage": [
            {"frequency": 1000, "voltage": 900},
            {"frequency": 1850, "voltage": 930},
        ]
    })
    # Custom mode, then the same edit a person makes in the drawer's editor.
    page._select_drawer_voltage_profile(-1)
    page.voltage_lab_drawer._editors[1850].setValue(880)
    notices = []
    page._show_info = lambda *args, **kwargs: notices.append((args, kwargs))
    page._run_backend_action = lambda *_args, **_kwargs: pytest.fail("invalid curve dispatched")
    monkeypatch.setattr(gpu_page_module, "ConfirmDialog", _AcceptedDialog)

    page._request_apply_voltage_curve_from_drawer()

    assert notices[0][0][0] == "Invalid voltage curve"
    assert notices[0][1]["tone"] == "red"
    assert controller.calls == []
