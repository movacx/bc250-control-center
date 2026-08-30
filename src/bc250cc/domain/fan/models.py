"""Hardware-agnostic fan value objects.

The domain deliberately knows nothing about hwmon paths or privileged writes.
Those concerns belong to infrastructure and platform capability probes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class FanMode(StrEnum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"


@dataclass(frozen=True)
class FanChannel:
    """A discovered PWM channel, identified by the provider rather than index."""

    identifier: str
    pwm_index: int
    writable: bool
    mode: FanMode = FanMode.AUTOMATIC

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier.strip():
            raise ValueError("Fan channel identifier cannot be empty.")
        if not isinstance(self.writable, bool):
            raise ValueError("Fan channel writable flag must be boolean.")
        if type(self.pwm_index) is not int:
            raise ValueError("Fan PWM index must be an integer.")
        if not 1 <= self.pwm_index <= 12:
            raise ValueError("Fan PWM index must be between 1 and 12.")
        if not isinstance(self.mode, FanMode):
            raise ValueError("Fan channel mode must be a FanMode.")


@dataclass(frozen=True)
class FanRequest:
    channel: FanChannel
    percent: int

    def __post_init__(self) -> None:
        if not isinstance(self.channel, FanChannel):
            raise ValueError("Fan request requires a discovered fan channel.")
        if not self.channel.writable:
            raise ValueError("Fan channel is not writable.")
        if type(self.percent) is not int:
            raise ValueError("Fan speed must be an integer percent.")
        if not 0 <= self.percent <= 100:
            raise ValueError("Fan speed must be between 0 and 100 percent.")

    @property
    def raw_pwm(self) -> int:
        return round(self.percent * 255 / 100)
