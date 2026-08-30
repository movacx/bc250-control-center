"""Passive capability detection shared by all supported Linux families."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class PlatformCapabilities:
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
            raise ValueError("platform capability flags must be booleans")

    @classmethod
    def detect(
        cls,
        *,
        os_release: Path = Path("/etc/os-release"),
        sysfs_root: Path = Path("/sys"),
        run_root: Path = Path("/run"),
        decky_root: Path | None = None,
        executable_lookup: Callable[[str], bool] | None = None,
        dbus_probe: Callable[[], bool] | None = None,
    ) -> "PlatformCapabilities":
        values: dict[str, str] = {}
        try:
            for line in os_release.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator:
                    values[key] = value.strip().strip('"')

        except OSError:
            pass

        lookup = executable_lookup or _which
        openrc = (run_root / "openrc" / "softlevel").exists()
        systemd = (run_root / "systemd" / "system").exists()
        immutable = (run_root / "ostree-booted").exists() or bool(
            os.environ.get("OSTREE_DEPLOYMENT")
        )
        decky_candidates = (
            decky_root,
            Path.home() / "homebrew" / "plugins",
            Path("/home/deck/homebrew/plugins"),
        )
        decky_present = any(
            candidate is not None and candidate.is_dir()
            for candidate in decky_candidates
        )
        if dbus_probe is not None:
            try:
                dbus = bool(dbus_probe())
            except Exception:
                # Optional capability probes must fail closed, not crash the
                # complete platform report.
                dbus = False
        elif lookup("busctl"):
            dbus = _probe_system_bus()
        else:
            dbus = False
        return cls(
            distro_id=values.get("ID", "unknown").lower(),
            init_system="openrc" if openrc else "systemd" if systemd else "unknown",
            immutable_root=immutable,
            dbus=dbus,
            sysfs=sysfs_root.is_dir(),
            umr=lookup("umr"),
            pwm=any(sysfs_root.glob("class/hwmon/hwmon*/pwm*_enable")),
            decky=decky_present,
        )


def _which(command: str) -> bool:
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(entry) / command
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return True
    return False


def _probe_system_bus() -> bool:
    """Return whether the system D-Bus answers a read-only discovery call."""

    try:
        completed = subprocess.run(
            ("busctl", "--system", "list"),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0
