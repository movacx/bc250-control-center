"""BC-250 physical fan wiring, independent of generic NCT driver labels.

J4003 F1 shares its signal with CPU_FAN1. BIOS fans 1..5 map to Linux
channels 2, 3, 4, 5, 1 respectively. Header labels are hardware data.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class FanHeader:
    pwm: int
    header: str
    bios_number: int

    @property
    def label(self) -> str:
        return f"{self.header} · BIOS Fan {self.bios_number}"


BC250_FAN_HEADERS = {
    1: FanHeader(1, "J4003 Fan 5", 5),
    2: FanHeader(2, "CPU_FAN1 / J4003 Fan 1", 1),
    3: FanHeader(3, "J4003 Fan 2", 2),
    4: FanHeader(4, "J4003 Fan 3", 3),
    5: FanHeader(5, "J4003 Fan 4", 4),
}
