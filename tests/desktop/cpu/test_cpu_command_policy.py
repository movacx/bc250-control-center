import pytest

from bc250cc.infrastructure.cpu_command_policy import (
    build_detect_command,
    build_disable_command,
    build_scale_command,
    validate_detection_target,
    validate_scale_target,
)


def test_detection_target_normalizes_values_and_builds_exact_argv(tmp_path):
    target = validate_detection_target("3850", "1150", "85")

    assert build_detect_command(
        "pkexec", "/usr/libexec/bc250-cpu", target, tmp_path / "overclock.conf"
    ) == [
        "pkexec", "/usr/libexec/bc250-cpu", "detect",
        "3850", "1150", "85", str(tmp_path / "overclock.conf"),
    ]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ((3499, 1150, 85), "3500-4200"),
        ((3850, 949, 85), "950-1325"),
        ((3850, 1150, 91), "70-90"),
        (("3850; reboot", 1150, 85), "integer"),
    ],
)
def test_detection_policy_rejects_invalid_or_injected_values(values, message):
    with pytest.raises(ValueError, match=message):
        validate_detection_target(*values)


def test_scale_policy_builds_only_allowlisted_actions():
    target = validate_scale_target(3700, -30, 85)

    assert build_scale_command("pkexec", "/helper", "apply-live", target) == [
        "pkexec", "/helper", "apply-live", "3700", "-30", "85",
    ]
    assert build_scale_command("pkexec", "/helper", "install-boot", target) == [
        "pkexec", "/helper", "install-boot", "3700", "-30", "85",
    ]
    with pytest.raises(ValueError, match="Unsupported"):
        build_scale_command("pkexec", "/helper", "arbitrary-root-command", target)


def test_scale_policy_enforces_curve_ceiling_and_boundary_paths():
    with pytest.raises(ValueError, match="1325 mV"):
        validate_scale_target(4200, 0, 90)
    with pytest.raises(ValueError, match="executor"):
        build_disable_command("", "/helper")
    with pytest.raises(ValueError, match="helper"):
        build_disable_command("pkexec", "/helper\x00suffix")
    target = validate_detection_target(3850, 1150, 90)
    with pytest.raises(ValueError, match="configuration path"):
        build_detect_command("pkexec", "/helper", target, "")
