from bc250cc.application.gpu.runtime import present_gpu_runtime
from frontends.desktop.pages.gpu_governor import GpuGovernorPage


def _present(**updates):
    values = {
        "gpu": {"service_sub": "running"},
        "is_oberon": False,
        "running": True,
        "enabled_at_boot": True,
        "range_control_ok": True,
        "active": "active",
        "enabled": "enabled",
        "dbus_ok": True,
        "range_text": "1000–1850 MHz",
        "profile_name": "Gaming",
        "safe_point_count": 6,
        "refreshed_at": "12:34:56",
    }
    values.update(updates)
    return present_gpu_runtime(**values)


def test_cyan_runtime_presentation_is_consistent_across_all_cards():
    presentation = _present()
    assert [line.value.template for line in presentation.lines] == [
        "Running", "Enabled", "Connected", "1000–1850 MHz", "6", "12:34:56"
    ]
    assert presentation.lines[2].detail.template == "runtime range API"
    assert presentation.lines[4].detail.template == "active TOML entries with frequency"
    assert presentation.card_status.template == "Running"
    assert presentation.card_tone == "green"


def test_oberon_range_is_validated_without_claiming_dbus():
    presentation = _present(is_oberon=True, dbus_ok=False)
    assert presentation.lines[2].value.template == "Validated"
    assert presentation.lines[2].detail.template == "Oberon YAML + service restart"
    assert presentation.lines[4].detail.template == "Oberon endpoint OPPs"


def test_stopped_or_unavailable_range_is_never_presented_green():
    stopped = _present(
        running=False,
        enabled_at_boot=False,
        range_control_ok=False,
        dbus_ok=False,
        active="inactive",
        enabled="disabled",
    )
    assert stopped.lines[0].value.template == "Inactive"
    assert stopped.lines[1].value.template == "Disabled"
    assert stopped.lines[1].detail.template == "not persistent"
    assert stopped.lines[2].value.template == "Unavailable"
    assert stopped.card_status.template == "Inactive"
    assert stopped.card_tone == "orange"


def test_runtime_evidence_and_timestamp_remain_literal():
    presentation = _present(
        gpu={"service_sub": "exited"},
        refreshed_at="01:02:03",
    )
    assert presentation.lines[0].detail.template == "exited"
    assert presentation.lines[5].value.literal is True


def test_real_gpu_page_applies_one_runtime_plan_to_every_status_widget(qtbot):
    page = GpuGovernorPage(object())
    qtbot.addWidget(page)
    page.safe_frequencies = [1000, 1500, 1850]

    page._update_runtime_status_cards(
        {"service_sub": "running"},
        is_oberon=False,
        running=True,
        enabled_at_boot=True,
        range_control_ok=True,
        active="active",
        enabled="enabled",
        dbus_ok=True,
        range_text="1000–1850 MHz",
        profile_name="Gaming",
    )

    assert page.service_stat.value.text() == "Running"
    assert page.boot_stat.value.text() == "Enabled"
    assert page.dbus_stat.value.text() == "Connected"
    assert page.profile_stat.value.text() == "1000–1850 MHz"
    assert page.points_stat.value.text() == "3"
    assert page.runtime_card.status.text() == "Running"
    assert page.runtime_card.status._tone == "green"
