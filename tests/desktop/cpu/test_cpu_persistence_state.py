import pytest

from bc250cc.infrastructure.cpu_persistence_state import (
    classify_cpu_persistence_service,
)


@pytest.mark.parametrize(
    ("enabled", "properties", "status", "config_exists", "expected"),
    [
        (
            "enabled",
            {"ActiveState": "inactive", "Result": "success", "ExecMainStatus": "0", "ExecMainStartTimestamp": "today"},
            "status=0/SUCCESS",
            True,
            (True, True, "Applied / enabled"),
        ),
        (
            "enabled",
            {"ActiveState": "inactive", "Result": "success", "ExecMainStatus": "0"},
            "",
            True,
            (True, False, "Applied / enabled"),
        ),
        (
            "enabled",
            {"ActiveState": "inactive", "Result": "exit-code", "ExecMainStatus": "1"},
            "status=1/FAILURE",
            True,
            (False, False, "Failed"),
        ),
        (
            "disabled", {"ActiveState": "active", "Result": "success"}, "", True,
            (False, True, "Active"),
        ),
        (
            "enabled", {"ActiveState": "inactive"}, "", True,
            (False, False, "Ready / enabled"),
        ),
        (
            "disabled", {"ActiveState": "inactive"}, "", False,
            (False, False, "Disabled"),
        ),
    ],
)
def test_cpu_persistence_service_state_is_conservative(
    enabled, properties, status, config_exists, expected
):
    state = classify_cpu_persistence_service(
        enabled, "unknown", properties, status, config_exists
    )

    assert (state["oneshot_ok"], state["applied_this_boot"], state["ui_state"]) == expected


def test_malformed_properties_fall_back_without_claiming_current_boot_apply():
    state = classify_cpu_persistence_service("enabled", "inactive", None, None, True)

    assert state["active_state"] == "inactive"
    assert state["oneshot_ok"] is False
    assert state["applied"] is True
    assert state["applied_this_boot"] is False
    assert state["ui_state"] == "Ready / enabled"


def test_systemd_values_are_normalized_without_losing_success_evidence():
    state = classify_cpu_persistence_service(
        " Enabled ",
        "unknown",
        {"ActiveState": " Inactive ", "Result": " SUCCESS ", "ExecMainStatus": 0},
        "STATUS=0/SUCCESS",
        True,
    )

    assert state["oneshot_ok"] is True
    assert state["ui_state"] == "Applied / enabled"


def test_failed_active_state_never_claims_applied_with_existing_config():
    state = classify_cpu_persistence_service(
        "enabled",
        "failed",
        {"ActiveState": "failed", "Result": ""},
        "",
        True,
    )

    assert state["applied"] is False
    assert state["ui_state"] == "Failed"
