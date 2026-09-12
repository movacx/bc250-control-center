from dataclasses import replace

import pytest

from bc250cc.application.gpu.range_policy import RangeEvidence, validate_gpu_range
from bc250cc.infrastructure.gpu.governor_toml import (
    GOVERNOR_DEFAULT_SAFE_POINTS,
    GOVERNOR_DEFAULT_VOLTAGES,
    voltage_profile,
)
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr


@pytest.fixture
def evidence():
    return RangeEvidence(
        backend="cyan-skillfish-governor-smu",
        allowed_min=500,
        allowed_max=2400,
        safe_frequencies=tuple(GOVERNOR_DEFAULT_VOLTAGES),
        safe_voltages=voltage_profile(3),
        packaged_voltages=GOVERNOR_DEFAULT_VOLTAGES,
        lab_frequencies=tuple(GOVERNOR_DEFAULT_VOLTAGES),
        current_max=1850,
        actual_clock=1500,
        gpu_busy=0,
        set_method="kernel",
    )


@pytest.mark.parametrize(
    ("minimum", "maximum", "title"),
    [
        (0, 1850, "Invalid range"),
        (1850, 1000, "Invalid range"),
        (400, 1850, "Range outside allowed limits"),
        (500, 2500, "Range outside allowed limits"),
    ],
)
def test_basic_bounds_fail_before_curve_evaluation(evidence, minimum, maximum, title):
    decision = validate_gpu_range(minimum, maximum, evidence)

    assert decision.valid is False
    assert decision.notice.title == title


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        ({"config_error": "invalid TOML"}, "could not be validated"),
        ({"duplicate_frequencies": (1850,)}, "ambiguous"),
        ({"missing_voltage": (1850,)}, "must define a voltage"),
        ({"safe_frequencies": ()}, "did not expose any TOML safe-point"),
    ],
)
def test_invalid_curve_evidence_fails_closed(evidence, change, fragment):
    decision = validate_gpu_range(500, 1850, replace(evidence, **change))

    assert decision.valid is False
    assert fragment in decision.notice.message
    assert decision.notice.tone in {"orange", "red"}


def test_descending_voltage_and_missing_maximum_are_rejected(evidence):
    descending = replace(evidence, voltage_errors=({
        "previous_frequency": 1850,
        "previous_voltage": 950,
        "frequency": 2000,
        "voltage": 900,
    },))
    invalid_maximum = replace(
        evidence,
        safe_frequencies=tuple(value for value in evidence.safe_frequencies if value != 1850),
    )

    first = validate_gpu_range(500, 1850, descending)
    second = validate_gpu_range(500, 1850, invalid_maximum)

    assert first.notice.tone == "red"
    assert "1850 MHz/950 mV" in first.notice.details
    assert second.valid is True
    assert second.notice is None


def test_high_oc_voltage_guidance_warns_without_blocking(evidence):
    partial = dict(voltage_profile(3))
    partial[2230] = GOVERNOR_DEFAULT_VOLTAGES[2230]

    decision = validate_gpu_range(
        1000, 2400, replace(evidence, safe_voltages=partial)
    )

    assert decision.valid is True
    warning = next(item for item in decision.warnings if "experimental" in item.message)
    assert "2230 MHz: 1085/1115 mV" in warning.details


def test_cyan_accepts_2000_with_either_live_backend(evidence):
    smu = validate_gpu_range(1000, 2000, replace(evidence, set_method="smu"))
    kernel = validate_gpu_range(1000, 2000, replace(evidence, set_method="kernel"))

    assert smu.valid is True
    assert kernel.valid is True


def test_busy_abrupt_drop_warns_but_does_not_override_user_request(evidence):
    loaded = replace(evidence, current_max=2200, actual_clock=2000, gpu_busy=50)
    idle = replace(evidence, current_max=2200, actual_clock=2000, gpu_busy=0)

    loaded_decision = validate_gpu_range(500, 1500, loaded)
    idle_decision = validate_gpu_range(500, 1500, idle)

    assert loaded_decision.valid is True
    assert any("GPU load is" in item.message for item in loaded_decision.warnings)
    assert idle_decision.valid is True
    assert any("ceiling reduction" in item.message for item in idle_decision.warnings)


def test_undervolt_and_high_frequency_warnings_accumulate(evidence):
    undervolted = dict(GOVERNOR_DEFAULT_SAFE_POINTS)
    undervolted[1850] -= 10

    decision = validate_gpu_range(
        500, 1850, replace(evidence, safe_voltages=undervolted)
    )

    assert decision.valid is True
    assert len(decision.warnings) == 2
    assert "undervolt" in decision.warnings[0].message


def test_oberon_accepts_the_three_offered_profiles_and_nothing_else(evidence):
    """Benchmark is (1000, 2000), and used to be rejected here.

    Quick Access wrote (1000, 2000) into /etc/oberon-config.yaml while this
    validator only knew (2000, 2000), so applying Benchmark in Game Mode left
    the desktop GPU page demanding Oberon recovery for a configuration the
    project had written itself. The written shape is the one that stays.
    """
    oberon = replace(
        evidence,
        backend="oberon-governor",
        safe_frequencies=(),
        safe_voltages={},
    )

    balanced = validate_gpu_range(1000, 1500, oberon)
    gaming = validate_gpu_range(1000, 1850, oberon)
    benchmark = validate_gpu_range(1000, 2000, oberon)
    recovery = validate_gpu_range(500, 1000, oberon)
    custom = validate_gpu_range(1000, 2200, oberon)

    assert balanced.valid is True
    assert gaming.valid is True
    assert benchmark.valid is True
    assert recovery.valid is False
    assert custom.valid is False
    assert custom.notice.title == "Unsupported Oberon profile"


def test_a_desktop_that_already_applied_the_old_benchmark_is_not_stranded(evidence):
    """(2000, 2000) is no longer offered, but it is still on disk somewhere."""
    oberon = replace(
        evidence,
        backend="oberon-governor",
        safe_frequencies=(),
        safe_voltages={},
    )
    assert validate_gpu_range(2000, 2000, oberon).valid is True


def test_new_curve_rejections_are_translated_in_every_supported_language():
    messages = (
        "The Cyan TOML could not be validated. Repair the configuration or run Prepare dependencies before applying a GPU range.",
        "Duplicate safe-point frequencies make the active voltage curve ambiguous. Remove or comment the duplicate blocks before applying a GPU range.",
        "Every active safe-point must define a voltage before a GPU range can be applied.",
        "Unsupported Oberon profile",
        "Oberon supports 1000–1500, 1000–1850, or the fixed 2000 MHz benchmark profile. The benchmark profile requires an idle GPU and explicit confirmation.",
        "Review and apply Oberon profile",
    )

    for message in messages:
        for language in SUPPORTED_LANGUAGES - {"en"}:
            assert tr(message, language) != message
