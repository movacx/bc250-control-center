"""Every sensor of the board as a list: what the Performance pages read and group."""

from bc250cc.infrastructure.sensor_inventory import (
    CLOCK,
    CURRENT,
    DATA,
    FAN,
    GPU_DEVICE,
    GROUP_CPU,
    GROUP_GDDR6,
    GROUP_GPU,
    GROUP_MEMORY,
    GROUP_NETWORK,
    GROUP_STORAGE,
    GROUP_VRM,
    POWER,
    RATE,
    TEMPERATURE,
    USAGE,
    VOLTAGE,
    SensorInventory,
    SensorReading,
)

__all__ = [
    "CLOCK", "CURRENT", "DATA", "FAN", "GPU_DEVICE", "GROUP_CPU", "GROUP_GDDR6", "GROUP_GPU", "GROUP_MEMORY",
    "GROUP_NETWORK", "GROUP_STORAGE", "GROUP_VRM", "POWER", "RATE", "TEMPERATURE", "USAGE", "VOLTAGE",
    "SensorInventory", "SensorReading",
]
