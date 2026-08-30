from dataclasses import dataclass

from bc250cc.infrastructure.gpu.cyan_gpu_engine import (
    CyanGpuEngine,
    fixed_request_matches,
)


def test_fixed_contract_matches_upstream_v0412_semantics():
    assert fixed_request_matches((1000, 2000), 2000, True) is True
    assert fixed_request_matches((2000, 2000), 2000, True) is True
    assert fixed_request_matches((1000, 2000), 2000, False) is False
    assert fixed_request_matches((1000, 1850), 2000, True) is False


@dataclass
class FakeEvidence:
    sclk_actual: int | None
    voltage_actual: int | None
    busy: int | None


class FakeClock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value

    def sleep(self, seconds):
        self.value += float(seconds)


class FakeRepository:
    def __init__(
        self,
        *,
        current=(1000, 1000),
        allowed=(500, 2400),
        actual=1000,
        voltage=800,
        busy=0,
        temperature=None,
        throttling=85,
        recovery=75,
        follow_range=True,
    ):
        self.current = current
        self.allowed = allowed
        self.actual = actual
        self.voltage = voltage
        self.busy = busy
        self.temperature = temperature
        self.throttling = throttling
        self.recovery = recovery
        self.follow_range = follow_range
        self.performance = False
        self.commands = []
        self.restarts = 0

    def _leer_rango_governor(self, kind):
        return self.allowed if kind == "Allowed" else self.current

    def _dbus_bool_property(self, *_args):
        return self.performance

    def _dbus_uint_property(self, _object, _interface, name):
        return {
            "TemperatureThrottling": self.throttling,
            "TemperatureRecovery": self.recovery,
        }.get(name)

    def temperatura_chip(self, *_args):
        return self.temperature

    @staticmethod
    def _gpu_device_path():
        return object()

    def _gpu_device_evidence(self, _gpu):
        return FakeEvidence(self.actual, self.voltage, self.busy)

    def _restart_governor_if_active(self, _service):
        self.restarts += 1
        raise AssertionError(
            "normal Cyan runtime transitions must never restart the service"
        )

    def _ejecutar(self, command, timeout=5):
        self.commands.append((command, timeout))
        method = command[5]
        values = [int(value) for value in command[7:]]
        if method == "SetRange":
            self.current = (values[0], values[1])
            self.performance = False
            if self.follow_range and self.busy >= 80:
                self.actual = values[1]
        elif method == "SetFixedFrequency":
            frequency = values[0]
            self.current = (self.current[0], frequency)
            self.performance = True
            if self.follow_range:
                self.actual = frequency
        return 0, "", ""


def engine_for(repo):
    clock = FakeClock()
    return CyanGpuEngine(repo, monotonic=clock.monotonic, sleep=clock.sleep)


def test_apply_range_increases_without_process_restart():
    repo = FakeRepository(current=(1000, 1000), allowed=(500, 2400))
    result = engine_for(repo).apply_range(1000, 2000)

    assert repo.restarts == 0
    assert (result.current_min, result.current_max) == (1000, 2000)
    assert result.hardware_verification == "pending-load"
    assert repo.commands[-1][0][5] == "SetRange"


def test_critical_2000_1000_2000_sequence_never_restarts_cyan():
    repo = FakeRepository(
        current=(1000, 2000), allowed=(500, 2400), actual=2000, busy=99
    )
    engine = engine_for(repo)

    low = engine.apply_range(1000, 1000)
    high = engine.apply_range(1000, 2000)

    assert repo.restarts == 0
    assert low.current_max == 1000
    assert high.current_max == 2000
    assert high.observed_frequency == 2000
    assert high.hardware_verification == "confirmed"


def test_apply_fixed_accepts_upstream_range_shape_and_verifies_hardware():
    repo = FakeRepository(current=(1000, 2000), allowed=(500, 2400), actual=1000)
    result = engine_for(repo).apply_fixed(2000)

    assert repo.restarts == 0
    assert result.performance_enabled is True
    assert (result.current_min, result.current_max) == (1000, 2000)
    assert result.hardware_verification == "confirmed"
    assert result.observed_voltage == 800
    assert repo.commands[-1][0][5] == "SetFixedFrequency"


def test_adaptive_high_load_waits_for_physical_clock_and_confirms():
    repo = FakeRepository(
        current=(1000, 1000), allowed=(500, 2400), actual=1000, busy=99
    )
    result = engine_for(repo).apply_range(1000, 2000)

    assert result.hardware_verification == "confirmed"
    assert result.observed_frequency == 2000


def test_adaptive_high_load_reports_not_confirmed_when_hardware_stays_low():
    repo = FakeRepository(
        current=(1000, 2000),
        allowed=(500, 2400),
        actual=1000,
        busy=99,
        follow_range=False,
        temperature=70,
    )
    result = engine_for(repo).apply_range(1000, 2000)

    assert repo.restarts == 0
    assert result.hardware_verification == "not-confirmed-under-load"
    assert result.observed_frequency == 1000


def test_above_recovery_but_below_throttle_does_not_mask_frequency_failure():
    repo = FakeRepository(
        current=(1000, 2000),
        allowed=(500, 2400),
        actual=1000,
        busy=99,
        temperature=80,
        throttling=85,
        recovery=75,
        follow_range=False,
    )
    result = engine_for(repo).apply_range(1000, 2000)

    assert repo.restarts == 0
    assert result.hardware_verification == "not-confirmed-under-load"
    assert result.observed_temperature == 80.0
    assert result.thermal_throttling == 85
    assert result.thermal_recovery == 75


def test_apply_range_reports_thermal_throttling_without_restart():
    repo = FakeRepository(
        current=(1000, 2000),
        allowed=(500, 2400),
        actual=1200,
        busy=99,
        temperature=88,
        throttling=85,
        recovery=75,
        follow_range=False,
    )
    result = engine_for(repo).apply_range(1000, 2000)

    assert result.hardware_verification == "thermal-throttled"
    assert repo.restarts == 0


def test_adaptive_ceiling_does_not_promise_a_fixed_clock_under_load():
    from types import SimpleNamespace

    from bc250cc.infrastructure.gpu_repository import GPURepository

    result = SimpleNamespace(
        hardware_verification="not-confirmed-under-load",
        observed_frequency=1000,
        observed_busy=99,
        observed_temperature=71.0,
        requested_max=2000,
    )

    GPURepository._raise_if_cyan_hardware_rejected(result, fixed=False)
    # Keep the observation visible; acceptance must not become clock confirmation.
    assert result.hardware_verification == "not-confirmed-under-load"
    assert result.observed_frequency == 1000


def test_reselecting_adaptive_range_restores_mode_even_when_bounds_match():
    repo = FakeRepository(current=(1000, 1850), actual=1850, busy=99)
    engine = engine_for(repo)
    engine.apply_range(1000, 1850)
    assert len(repo.commands) == 1
    repo.performance = True
    result = engine.apply_range(1000, 1850)
    assert len(repo.commands) == 2
    assert result.performance_enabled is False
    assert repo.restarts == 0


def test_adaptive_clock_observation_does_not_delay_an_accepted_dbus_request():
    repo = FakeRepository(actual=1000, busy=99, follow_range=False)
    clock = FakeClock()
    result = CyanGpuEngine(repo, monotonic=clock.monotonic, sleep=clock.sleep).apply_range(1000, 1850)
    assert result.current_max == 1850
    assert result.hardware_verification == "not-confirmed-under-load"
    assert clock.value == 0


def test_live_2000_to_1850_to_1500_and_back_never_requires_idle_or_restart():
    repo = FakeRepository(current=(1000, 2000), actual=2000, busy=99)
    for maximum in (1850, 1500, 2000):
        result = engine_for(repo).apply_range(1000, maximum)
        assert result.current_max == maximum
        assert result.hardware_verification == "confirmed"
    assert repo.restarts == 0


def test_repository_rejects_known_fixed_hardware_mismatch_but_allows_pending_adaptive():
    from types import SimpleNamespace

    from bc250cc.infrastructure.gpu_repository import GPURepository

    fixed = SimpleNamespace(
        hardware_verification="not-confirmed",
        observed_frequency=1000,
        observed_busy=10,
        observed_temperature=60.0,
        requested_max=2000,
    )
    pending = SimpleNamespace(
        hardware_verification="pending-load",
        observed_frequency=1000,
        observed_busy=5,
        observed_temperature=60.0,
        requested_max=2000,
    )

    try:
        GPURepository._raise_if_cyan_hardware_rejected(fixed, fixed=True)
    except RuntimeError as error:
        assert "accepted the fixed-frequency request" in str(error)
    else:
        raise AssertionError("known fixed hardware mismatch was reported as success")

    GPURepository._raise_if_cyan_hardware_rejected(pending, fixed=False)
