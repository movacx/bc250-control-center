from bc250cc.application.gpu.safe_points import (
    build_safe_point_plan,
    normalize_safe_points,
)
from bc250cc.infrastructure.gpu.governor_toml import GOVERNOR_DEFAULT_VOLTAGES
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def test_safe_points_normalize_invalid_duplicate_and_unsorted_evidence():
    points = normalize_safe_points([
        {"frequency": "1850", "voltage": "930"},
        "invalid",
        {"frequency": 1000, "voltage": 800},
        {"frequency": 1850, "voltage": 930},
        {"frequency": 0, "voltage": 999},
    ])
    assert points == ((1000, 800), (1850, 930))
    assert normalize_safe_points({"frequency": 1000}) == ()


def test_safe_point_roles_have_explicit_precedence_and_voltage_evidence():
    plan = build_safe_point_plan(
        [
            {"frequency": 1000, "voltage": 800},
            {"frequency": 1500, "voltage": 850},
            {"frequency": 1850, "voltage": 900},
            {"frequency": 2000, "voltage": 990},
            {"frequency": 2230, "voltage": 1000},
            {"frequency": 2500, "voltage": 1200},
        ],
        current=1000,
        active_maximum=1500,
        packaged_voltages=GOVERNOR_DEFAULT_VOLTAGES,
    )
    rows = {row.frequency: row for row in plan.rows}
    assert rows[1000].role == "Current SCLK"
    assert rows[1500].role == "Active ceiling"
    assert rows[1850].role == "Undervolt warning"
    assert rows[2000].role == "OC safe-point"
    assert rows[2230].role == "High OC / undervolt lab"
    assert rows[2500].role == "High OC safe-point"
    assert rows[2230].stable is False
    assert rows[2500].original_voltage is None


def test_safe_point_plan_excludes_missing_voltage_from_voltage_map():
    plan = build_safe_point_plan(
        [{"frequency": 1000}, {"frequency": 1850, "voltage": 930}],
        current=0,
        active_maximum=0,
        packaged_voltages=GOVERNOR_DEFAULT_VOLTAGES,
    )
    assert plan.frequencies == (1000, 1850)
    assert plan.voltage_map == ((1850, 930),)
    assert plan.rows[0].role == "Safe-point"


def test_real_gpu_page_populates_table_and_state_from_one_plan(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.active_max = 1850
    page._populate_points(
        [
            {"frequency": 1000, "voltage": 800},
            {"frequency": 1850, "voltage": 900},
        ],
        current=1000,
    )
    assert page.safe_frequencies == [1000, 1850]
    assert page.safe_voltage_map == {1000: 800, 1850: 900}
    assert page.points_table.rowCount() == 2
    assert page.points_table.item(0, 3).text() == "Current SCLK"
    assert page.points_table.item(1, 3).text() == "Active ceiling"
