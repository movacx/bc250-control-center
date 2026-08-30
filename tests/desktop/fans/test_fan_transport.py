import pytest

from bc250cc.infrastructure.fan_repository import FanRepository
from bc250cc.infrastructure.fan_transport import (
    PWMTransport,
    PWMTransportSignals,
    select_pwm_transport,
    validate_pwm_request,
)


@pytest.mark.parametrize(
    ("signals", "expected"),
    (
        (PWMTransportSignals(daemon_helper=True, game_helper=True), PWMTransport.DAEMON_HELPER),
        (PWMTransportSignals(game_helper=True), PWMTransport.GAME_HELPER),
        (PWMTransportSignals(sensor_present=True, channel_present=True, channel_writable=True), PWMTransport.DIRECT),
        (PWMTransportSignals(sensor_present=True, channel_present=True, pkexec_present=True, python_present=True), PWMTransport.POLKIT_HELPER),
    ),
)
def test_transport_precedence_is_explicit(signals, expected):
    assert select_pwm_transport(signals) is expected


@pytest.mark.parametrize(
    ("signals", "message"),
    (
        (PWMTransportSignals(), "No NCT"),
        (PWMTransportSignals(sensor_present=True), "does not exist"),
        (PWMTransportSignals(sensor_present=True, channel_present=True), "pkexec"),
        (PWMTransportSignals(sensor_present=True, channel_present=True, pkexec_present=True), "python3"),
    ),
)
def test_missing_transport_prerequisite_fails_before_write(signals, message):
    with pytest.raises(RuntimeError, match=message):
        select_pwm_transport(signals)


@pytest.mark.parametrize(
    ("channel", "value", "message"),
    (
        (True, 100, "must be integers"),
        (2, False, "must be integers"),
        ("bad", 100, "must be integers"),
        (0, 100, "Invalid PWM channel"),
        (13, 100, "Invalid PWM channel"),
        (2, -1, "between 0 and 255"),
        (2, 256, "between 0 and 255"),
    ),
)
def test_request_validation_rejects_ambiguous_or_out_of_range_values(
    channel, value, message
):
    with pytest.raises(RuntimeError, match=message):
        validate_pwm_request(channel, value)


def test_request_validation_returns_plain_bounded_integers():
    assert validate_pwm_request("12", "255") == (12, 255)


def test_direct_writer_never_follows_a_symlink(tmp_path):
    target = tmp_path / "target"
    target.write_text("unchanged\n", encoding="utf-8")
    link = tmp_path / "pwm2"
    link.symlink_to(target)
    with pytest.raises(OSError):
        FanRepository._write_pwm_attribute(link, "170\n")
    assert target.read_text(encoding="utf-8") == "unchanged\n"


def test_direct_writer_rejects_nonregular_attribute(tmp_path):
    directory = tmp_path / "pwm2"
    directory.mkdir()
    with pytest.raises(OSError):
        FanRepository._write_pwm_attribute(directory, "170\n")


def test_direct_pwm_waits_for_manual_mode_before_verifying_duty(tmp_path, monkeypatch):
    sensor = tmp_path / "hwmon2"
    sensor.mkdir()
    (sensor / "pwm2").write_text("127\n", encoding="ascii")
    (sensor / "pwm2_enable").write_text("2\n", encoding="ascii")
    sleeps = []

    class Repository(FanRepository):
        estado_herramientas_cache = None

        def _sensor_nct_principal(self):
            return sensor

    repository = Repository()
    monkeypatch.setattr("bc250cc.infrastructure.fan_repository.time.sleep", sleeps.append)

    result = repository._apply_direct_pwm(sensor, 2, 170)

    assert result["verified"]["value"] == 170
    assert result["verified"]["enable"] == 1
    assert any(delay > 0 for delay in sleeps)


def test_direct_pwm_reports_bounded_settle_failure(tmp_path, monkeypatch):
    sensor = tmp_path / "hwmon2"
    sensor.mkdir()
    (sensor / "pwm2").write_text("127\n", encoding="ascii")
    (sensor / "pwm2_enable").write_text("1\n", encoding="ascii")

    class Repository(FanRepository):
        estado_herramientas_cache = None

        def _sensor_nct_principal(self):
            return sensor

        def leer_pwm_fan(self, pwm):
            return {
                "pwm": pwm,
                "value": 127,
                "enable": int((sensor / f"pwm{pwm}_enable").read_text(encoding="ascii")),
            }

    monkeypatch.setattr("bc250cc.infrastructure.fan_repository.time.sleep", lambda _delay: None)

    with pytest.raises(RuntimeError, match="after 16 attempts"):
        Repository()._apply_direct_pwm(sensor, 2, 170)


def test_direct_pwm_restores_automatic_after_permanently_unsettled_duty(
    tmp_path, monkeypatch
):
    sensor = tmp_path / "hwmon2"
    sensor.mkdir()
    (sensor / "pwm4").write_text("127\n", encoding="ascii")
    (sensor / "pwm4_enable").write_text("2\n", encoding="ascii")

    class Repository(FanRepository):
        estado_herramientas_cache = None

        def _sensor_nct_principal(self):
            return sensor

        def leer_pwm_fan(self, pwm):
            return {
                "pwm": pwm,
                "value": 127,
                "enable": int((sensor / f"pwm{pwm}_enable").read_text(encoding="ascii")),
            }

    monkeypatch.setattr("bc250cc.infrastructure.fan_repository.time.sleep", lambda _delay: None)

    with pytest.raises(RuntimeError, match="Previous automatic mode was restored"):
        Repository()._apply_direct_pwm(sensor, 4, 178)

    assert (sensor / "pwm4_enable").read_text(encoding="ascii").strip() == "2"


def test_helper_acknowledgement_waits_for_settled_pwm_readback(tmp_path, monkeypatch):
    """A helper's ``OK`` line is not enough while an NCT transition settles."""
    sensor = tmp_path / "hwmon2"
    sensor.mkdir()
    (sensor / "pwm2_enable").write_text("1\n", encoding="ascii")
    samples = iter((127, 127, 170))
    sleeps = []

    class Repository(FanRepository):
        estado_herramientas_cache = None

        def _sensor_nct_principal(self):
            return sensor

        def leer_pwm_fan(self, pwm):
            return {"pwm": pwm, "value": next(samples), "enable": 1}

    monkeypatch.setattr("bc250cc.infrastructure.fan_repository.time.sleep", sleeps.append)

    result = Repository()._resultado_pwm_con_lectura(2, 170, "OK PWM 2 170")

    assert result["verified"]["value"] == 170
    assert result["verified"]["enable"] == 1
    assert result["verified"]["verification_attempts"] == 3
    assert len(sleeps) == 2


def test_helper_acknowledgement_does_not_claim_success_on_stale_duty(tmp_path, monkeypatch):
    sensor = tmp_path / "hwmon2"
    sensor.mkdir()
    (sensor / "pwm2_enable").write_text("1\n", encoding="ascii")

    class Repository(FanRepository):
        estado_herramientas_cache = None

        def _sensor_nct_principal(self):
            return sensor

        def leer_pwm_fan(self, pwm):
            return {"pwm": pwm, "value": 127, "enable": 1}

    monkeypatch.setattr("bc250cc.infrastructure.fan_repository.time.sleep", lambda _delay: None)

    result = Repository()._resultado_pwm_con_lectura(2, 170, "OK PWM 2 170")

    assert result["verified"] is None
    assert "did not settle" in result["verification_error"]
