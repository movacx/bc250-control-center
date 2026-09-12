import pytest

from bc250cc.infrastructure.governor_config_request import (
    GOVERNOR_CONFIG_HELPER_PROTOCOL,
    GovernorConfigRequest,
    governor_config_helper_protocol,
    plan_governor_config_request,
)
from bc250cc.infrastructure.gpu_repository import GPURepository
from frontends.desktop.i18n import SUPPORTED_LANGUAGES, tr


@pytest.mark.parametrize(
    ("action", "arguments", "normalized"),
    [
        ("clear-frequency-range", (), ()),
        ("enable-high-points", (), ()),
        ("disable-high-points", (), ()),
        ("migrate-legacy-frequency-range", (), ()),
        ("set-frequency-range", ("500", 1850), ("500", "1850")),
        ("set-frequency-floor", (500,), ("500",)),
        (
            "set-oberon-operating-points",
            (500, "2200", 920, 1050),
            ("500", "2200", "920", "1050"),
        ),
        ("ensure-cyan-telemetry", (True,), ("1",)),
        ("ensure-cyan-telemetry", (False,), ("0",)),
        ("set-cyan-metrics-fix", (True,), ("1",)),
        ("set-cyan-metrics-fix", (False,), ("0",)),
        (
            "set-cyan-compatibility",
            ("kernel", "kernel", False, False),
            ("kernel", "kernel", "0", "0"),
        ),
        ("set-cyan-voltage-level", (3,), ("3",)),
        ("set-cyan-voltage-level", (5,), ("5",)),
        (
            "set-cyan-custom-voltages",
            ("1850=950", "1000=820"),
            ("1000=820", "1850=950"),
        ),
    ],
)
def test_request_planner_normalizes_supported_actions(action, arguments, normalized):
    request = plan_governor_config_request(action, arguments)

    assert request == GovernorConfigRequest(action, normalized)
    assert request.argv("/trusted/helper") == [
        "pkexec", "--disable-internal-agent", "/trusted/helper", action, *normalized
    ]


def test_governor_helper_protocol_is_explicit_and_fails_closed_when_absent():
    assert GOVERNOR_CONFIG_HELPER_PROTOCOL == 6
    assert governor_config_helper_protocol("BC250_GOVERNOR_CONFIG_PROTOCOL = 6\n") == 6
    assert governor_config_helper_protocol("BC250_GOVERNOR_CONFIG_PROTOCOL = 1\n") == 1
    assert governor_config_helper_protocol("# no protocol\n") is None
    assert governor_config_helper_protocol("BC250_GOVERNOR_CONFIG_PROTOCOL = invalid\n") is None


@pytest.mark.parametrize(
    ("action", "arguments", "message"),
    [
        ("unknown", (), "Invalid governor TOML action"),
        (None, (), "Invalid governor TOML action"),
        ("clear-frequency-range", (1,), "does not accept"),
        ("set-frequency-range", (500,), "minimum and maximum"),
        ("set-frequency-range", (500, object()), "must be integers"),
        ("set-frequency-range", (True, 1850), "must be integers"),
        ("set-frequency-range", (500.5, 1850), "must be integers"),
        ("set-frequency-floor", (), "one minimum"),
        ("set-frequency-floor", (False,), "must be an integer"),
        ("set-oberon-operating-points", (1, 2, 3), "four integer"),
        ("ensure-cyan-telemetry", (), "one boolean"),
        ("ensure-cyan-telemetry", ("false",), "must be boolean"),
        ("ensure-cyan-telemetry", (0,), "must be boolean"),
        ("set-cyan-metrics-fix", (), "one boolean"),
        ("set-cyan-metrics-fix", ("false",), "must be boolean"),
        ("set-cyan-compatibility", ("smu", "busy-flag", False), "needs set-method"),
        ("set-cyan-compatibility", ("invalid", "busy-flag", False, False), "smu or kernel"),
        ("set-cyan-compatibility", ("smu", "invalid", False, False), "busy-flag"),
        ("set-cyan-compatibility", ("smu", "busy-flag", 0, False), "must be boolean"),
        ("set-cyan-voltage-level", (7,), "0 through 6"),
        ("set-cyan-custom-voltages", (), "No custom values"),
        ("set-cyan-custom-voltages", ("1850=950", "1850=960"), "conflicting"),
        ("set-cyan-custom-voltages", ("1850=1300",), "safe editor range"),
        ("set-cyan-custom-voltages", ("1850.5=950",), "must be integers"),
        ("set-cyan-custom-voltages", ("1850=950=900",), "frequency=millivolts"),
    ],
)
def test_request_planner_rejects_ambiguous_or_malformed_input(
    action, arguments, message
):
    with pytest.raises(ValueError, match=message):
        plan_governor_config_request(action, arguments)


def test_repository_validates_before_helper_discovery_or_privilege_prompt():
    repository = object.__new__(GPURepository)
    repository._governor_config_helper_path = lambda: (_ for _ in ()).throw(
        AssertionError("invalid input must not inspect the helper")
    )
    repository._ejecutar = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("invalid input must not invoke pkexec")
    )

    with pytest.raises(ValueError, match="must be boolean"):
        repository._editar_governor_toml("ensure-cyan-telemetry", "false")


def test_repository_invokes_only_the_planned_argv_and_invalidates_cache():
    calls = []
    repository = object.__new__(GPURepository)
    repository.estado_bc250_cache = {"stale": True}
    repository._governor_config_helper_path = lambda: "/trusted/helper"
    repository._cyan_runtime_config_path = lambda **_kwargs: repository._GOVERNOR_CONFIG
    repository._ejecutar = lambda command, timeout: (
        calls.append((command, timeout)) or (0, "updated\n", "")
    )

    assert repository._editar_governor_toml(
        "set-frequency-range", "500", 1850
    ) == "updated"
    assert calls == [
        (["pkexec", "--disable-internal-agent", "/trusted/helper", "set-frequency-range", "500", "1850"], 120)
    ]
    assert repository.estado_bc250_cache is None


def test_repository_preserves_helper_failure_evidence():
    repository = object.__new__(GPURepository)
    repository._governor_config_helper_path = lambda: "/trusted/helper"
    repository._ejecutar = lambda _command, timeout: (7, "", "permission denied")

    with pytest.raises(RuntimeError, match="permission denied"):
        repository._editar_governor_toml("set-frequency-floor", 500)


def test_new_validation_message_is_translated_in_every_supported_language():
    sources = (
        "Cyan telemetry frequency fix flag must be boolean.",
        "GPU voltage level needs one value.",
        "GPU voltage level must be an integer.",
        "Custom GPU voltages must use frequency=millivolts.",
        "Custom GPU voltage values must be integers.",
        "Custom GPU voltage value is outside the safe editor range.",
        "A GPU frequency cannot have conflicting voltage values.",
        "The Cyan governor must be active before changing its voltage curve.",
        "The active governor range could not be read through D-Bus. The voltage curve was not changed.",
    )

    for source in sources:
        for language in SUPPORTED_LANGUAGES - {"en"}:
            assert tr(source, language) != source
