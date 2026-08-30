"""Pure transport policy for one bounded PWM request."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from bc250cc.application.fan.policy import validate_pwm as _validate_pwm


class PWMTransport(StrEnum):
    DAEMON_HELPER = "daemon-helper"
    GAME_HELPER = "game-helper"
    DIRECT = "direct"
    POLKIT_HELPER = "polkit-helper"


@dataclass(frozen=True)
class PWMTransportSignals:
    daemon_helper: bool = False
    game_helper: bool = False
    sensor_present: bool = False
    channel_present: bool = False
    channel_writable: bool = False
    pkexec_present: bool = False
    python_present: bool = False


def validate_pwm_request(channel: object, value: object) -> tuple[int, int]:
    def transport_integer(candidate: object) -> object:
        if type(candidate) is int:
            return candidate
        if type(candidate) is str and candidate.isascii() and candidate.isdecimal():
            return int(candidate)
        return candidate

    try:
        return _validate_pwm(transport_integer(channel), transport_integer(value))
    except ValueError as error:
        raise RuntimeError(str(error)) from error


def select_pwm_transport(signals: PWMTransportSignals) -> PWMTransport:
    """Select exactly one route; missing prerequisites fail before mutation."""
    if signals.daemon_helper:
        return PWMTransport.DAEMON_HELPER
    if signals.game_helper:
        return PWMTransport.GAME_HELPER
    if not signals.sensor_present:
        raise RuntimeError("No NCT hwmon sensor was found.")
    if not signals.channel_present:
        raise RuntimeError("The requested PWM channel does not exist.")
    if signals.channel_writable:
        return PWMTransport.DIRECT
    if not signals.pkexec_present:
        raise RuntimeError(
            "polkit/pkexec was not found. Cannot authenticate PWM write from the GUI."
        )
    if not signals.python_present:
        raise RuntimeError("python3 was not found. It is required for the PWM helper.")
    return PWMTransport.POLKIT_HELPER
