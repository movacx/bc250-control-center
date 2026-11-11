import math

from frontends.desktop.core.fan_action_policy import (
    plan_automatic_curve,
    plan_fan_action_availability,
)
from frontends.desktop.pages.fans import FansPage


def curve(**updates):
    values = {
        "busy": False,
        "curve_enabled": True,
        "control_ready": True,
        "validation_error": "",
        "temperature": 60.0,
        "now": 10.0,
        "last_apply": 0.0,
        "last_percent": 50,
        "calculated_percent": 70,
        "selected_pwm": 2,
    }
    values.update(updates)
    return plan_automatic_curve(**values)


def test_write_actions_require_idle_writable_detected_channel():
    ready = plan_fan_action_availability(
        control_ready=True, channel_count=1, curve_point_count=3, busy=False
    )
    missing = plan_fan_action_availability(
        control_ready=True, channel_count=0, curve_point_count=3, busy=False
    )

    assert ready.apply_pwm is ready.apply_curve is True
    assert missing.apply_pwm is missing.apply_curve is False
    assert missing.save_curve is True


def test_automatic_curve_never_falls_back_to_an_undetected_pwm_channel():
    decision = curve(selected_pwm=None)

    assert (decision.action, decision.reason) == ("skip", "channel-missing")


def test_nonfinite_temperature_and_rate_limit_block_dispatch():
    assert curve(temperature=math.nan).reason == "sensor-missing"
    assert curve(now=3, last_apply=0).reason == "rate-limited"


def test_unchanged_target_touches_timer_without_writing():
    decision = curve(last_percent=70)

    assert decision.action == "touch"
    assert decision.touched_at == 10


def test_changed_target_returns_exact_detected_channel_and_clamped_percent():
    decision = curve(selected_pwm="4", calculated_percent=120)

    assert decision.action == "apply"
    assert (decision.pwm, decision.percent) == (4, 100)


def test_real_page_never_auto_writes_an_undetected_fallback_channel(qtbot):
    """The redesigned page never writes on its own: a refresh with a curve
    saved and no fan detected renders the board headers and writes nothing."""
    writes = []

    class Controller:
        def aplicar_pwm_fan(self, *args):
            writes.append(args)

        def restaurar_pwm_automatico(self, *args):
            writes.append(args)

    page = FansPage(Controller())
    qtbot.addWidget(page)
    page._apply_refresh_payload({
        "fans": {"driver_control": True, "sensores": {"fans": []}},
        "performance": {"gpu_temp": 60},
        "system": {},
    })

    assert page.model.rowCount() == 5  # the five J4003 headers, none detected
    assert writes == []
