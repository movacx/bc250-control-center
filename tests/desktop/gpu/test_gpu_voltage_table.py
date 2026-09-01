import pytest

from bc250cc.application.gpu.voltage_table import build_voltage_table_plan
from bc250cc.infrastructure.gpu.governor_toml import GOVERNOR_DEFAULT_VOLTAGES


def _plan(level, *, points=((1000, 800), (2000, 960)), **kwargs):
    return build_voltage_table_plan(
        points=points,
        selected_level=level,
        editable_frequencies=kwargs.pop("editable", (1000, 2000)),
        profile_frequencies=kwargs.pop("profile", (1000, 2000)),
        custom_values=kwargs.pop("custom", {}),
        packaged_voltages=kwargs.pop("packaged", GOVERNOR_DEFAULT_VOLTAGES),
        detected_level=kwargs.pop("detected", 0),
        is_oberon=kwargs.pop("is_oberon", False),
        **kwargs,
    )


def test_voltage_table_level_profile_has_exact_original_delta():
    plan = _plan(3)
    rows = {row.frequency: row for row in plan.rows}
    assert plan.custom_mode is False
    assert plan.active_frequencies == (1000, 2000)
    assert rows[1000].proposed == 800
    assert rows[1000].added == 0
    assert rows[2000].proposed == 990
    assert rows[2000].added == 30
    assert dict(plan.detail_values) == {
        "level": 3,
        "added": 30,
        "start": 2000,
        "count": 2,
        "detected": 0,
    }


def test_voltage_table_custom_mode_uses_pending_values_and_all_editable_points():
    plan = _plan(-1, custom={1000: 825, 2000: 1000})
    rows = {row.frequency: row for row in plan.rows}
    assert plan.custom_mode is True
    assert rows[1000].editor_value == 825
    assert rows[1000].proposed == 825
    assert rows[1000].added == 25
    assert rows[2000].editor_value == 1000
    assert dict(plan.detail_values) == {"count": 2}


def test_voltage_table_keeps_unknown_safe_point_visible_without_fake_baseline():
    plan = _plan(
        0,
        points=((1777, 915),),
        editable=(1777,),
        profile=(),
        packaged={},
    )
    row = plan.rows[0]
    assert row.current == 915
    assert row.original is None
    assert row.proposed == 915
    assert row.added is None
    assert plan.active_frequencies == ()


def test_voltage_table_oberon_clamps_profile_but_preserves_current_editor_value():
    plan = _plan(
        0,
        points=((500, 700), (1000, 800)),
        editable=(500, 1000),
        profile=(500, 1000),
        is_oberon=True,
    )
    rows = {row.frequency: row for row in plan.rows}
    assert rows[500].proposed == 920
    assert rows[500].editor_value == 700
    assert rows[1000].proposed == 920


def test_voltage_table_empty_and_invalid_level_fail_safely():
    empty = _plan(0, points=(), editable=(), profile=())
    assert empty.rows == ()
    assert empty.active_frequencies == ()
    assert empty.detail_template.startswith("No active voltage")
    with pytest.raises(ValueError, match="Unsupported GPU voltage level"):
        _plan(7)
