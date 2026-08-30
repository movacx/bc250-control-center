"""Read-only system status use case built from real platform capabilities."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from bc250cc.platform import PlatformCapabilities


@dataclass(frozen=True, slots=True)
class SystemStatus:
    """Stable application payload for system diagnostics.

    This object deliberately reports capabilities, not distro-based feature
    assumptions.  Installation strategy may use distro metadata elsewhere,
    while runtime functionality is decided by these observed capabilities.
    """

    distro_id: str
    init_system: str
    immutable_root: bool
    dbus: bool
    sysfs: bool
    umr: bool
    pwm: bool
    decky: bool

    def __post_init__(self) -> None:
        if not isinstance(self.distro_id, str) or not self.distro_id.strip():
            raise ValueError("distro_id must be a non-empty string")
        if not isinstance(self.init_system, str) or not self.init_system.strip():
            raise ValueError("init_system must be a non-empty string")
        flags = (self.immutable_root, self.dbus, self.sysfs, self.umr, self.pwm, self.decky)
        if any(type(flag) is not bool for flag in flags):
            raise ValueError("system status flags must be booleans")

    @classmethod
    def from_capabilities(cls, capabilities: PlatformCapabilities) -> "SystemStatus":
        if not isinstance(capabilities, PlatformCapabilities):
            raise TypeError("system status requires PlatformCapabilities")
        return cls(
            distro_id=capabilities.distro_id,
            init_system=capabilities.init_system,
            immutable_root=capabilities.immutable_root,
            dbus=capabilities.dbus,
            sysfs=capabilities.sysfs,
            umr=capabilities.umr,
            pwm=capabilities.pwm,
            decky=capabilities.decky,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def detect_system_status() -> SystemStatus:
    """Detect system capabilities once for an explicit read-only request."""

    return SystemStatus.from_capabilities(PlatformCapabilities.detect())
