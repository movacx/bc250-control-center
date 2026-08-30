import pytest

from bc250cc.application.gpu.safety import present_gpu_safety
from frontends.desktop.pages.gpu_governor import DynamicSafetyNotice


def _oberon(*, detected=False, active="not-found"):
    return {
        "governor_backend": "oberon-governor",
        "service_active": active,
        "tools": {
            "supported_gpu_governors": {
                "oberon-governor": {"detected": detected, "active": active == "active"}
            }
        },
    }


@pytest.mark.parametrize(
    ("state", "frequencies", "title", "tone", "status"),
    (
        (
            {"tools": {"incompatible_gpu_governors": [{"identifier": "oberon"}]}},
            (), "Incompatible GPU governor detected", "red", "Blocked",
        ),
        (
            {"safe_points_error": "bad TOML"}, (),
            "Governor configuration could not be validated", "red", "Blocked",
        ),
        (_oberon(), (), "Oberon Governor was not found", "orange", "Not installed"),
        (_oberon(detected=True, active="inactive"), (), "Oberon Governor is not active", "orange", "Offline"),
        (_oberon(detected=True, active="active"), (), "Oberon profiles ready", "blue", "Protected"),
        (
            {"safe_points_voltage_errors": [{"frequency": 1850}]}, (),
            "Governor blocked by invalid voltage curve", "orange", "Blocked",
        ),
        (
            {"telemetry_warning": "update Cyan"}, (),
            "Cyan runtime update required", "orange", "Update required",
        ),
        (
            {"dbus_ok": True, "range_control_ok": True}, (2100,),
            "High OC laboratory mode", "orange", "Lab mode",
        ),
        (
            {"dbus_ok": False, "range_control_ok": False}, (),
            "Governor D-Bus unavailable", "orange", "Offline",
        ),
        (
            {"dbus_ok": True, "range_control_ok": True}, (),
            "Safe mode enabled", "blue", "Safe mode",
        ),
    ),
)
def test_gpu_safety_states_are_deterministic(state, frequencies, title, tone, status):
    notice = present_gpu_safety(state, safe_frequencies=frequencies)
    assert (notice.title, notice.tone, notice.status) == (title, tone, status)


def test_conflict_has_precedence_over_every_lower_priority_warning():
    notice = present_gpu_safety({
        "safe_points_error": "bad TOML",
        "safe_points_voltage_errors": [{"frequency": 1850}],
        "telemetry_warning": "update",
        "high_frequency_points": {"enabled": True},
        "tools": {"incompatible_gpu_governors": [{"service": "other.service"}]},
    })
    assert notice.title == "Incompatible GPU governor detected"
    assert dict(notice.message.values)["governors"] == "other.service"


def test_high_oc_and_offline_notices_keep_translatable_suffixes():
    high = present_gpu_safety({
        "dbus_ok": False,
        "high_frequency_points": {"enabled": True},
        "safe_points_duplicate_frequencies": [2100],
    })
    assert [part.template for part in high.suffixes] == [
        "Duplicate frequencies were also detected in the TOML.",
        "The governor is currently offline; these points will take effect after the service is activated.",
    ]

    offline = present_gpu_safety({
        "range_control_ok": False,
        "safe_points_missing_voltage": [{"frequency": 1850}, 2000],
    })
    assert dict(offline.suffixes[0].values)["values"] == "1850, 2000"


def test_critical_gpu_notice_is_rendered_as_red(qtbot):
    notice = DynamicSafetyNotice("title", "message")
    qtbot.addWidget(notice)
    notice.set_notice("blocked", "danger", tone="red")
    assert notice.property("safetyNotice") == "red"
    assert notice._tone == "red"
