"""Pure fan policies shared by every frontend."""

from __future__ import annotations

from bc250cc.domain.fan.models import FanChannel, FanRequest


def validate_pwm(channel: object, value: object) -> tuple[int, int]:
    if type(channel) is not int or type(value) is not int:
        raise ValueError("PWM channel and value must be integers.")
    pwm, raw = channel, value
    if not 1 <= pwm <= 12:
        raise ValueError("Invalid PWM channel.")
    if not 0 <= raw <= 255:
        raise ValueError("PWM value must be between 0 and 255.")
    return pwm, raw


def request_from_percent(channel: FanChannel, percent: object) -> FanRequest:
    if isinstance(percent, bool) or type(percent) not in {int, str}:
        raise ValueError("Fan speed must be an integer percent.")
    try:
        value = int(percent)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Fan speed must be an integer percent.") from error
    if str(value) != str(percent):
        raise ValueError("Fan speed must be an integer percent.")
    return FanRequest(channel, value)
