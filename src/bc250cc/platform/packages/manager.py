"""Package-manager availability, independent from feature support."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PackageManagers:
    pacman: bool = False
    apt: bool = False
    dnf: bool = False
    rpm_ostree: bool = False
    apk: bool = False
    emerge: bool = False

    @classmethod
    def detect(cls, lookup: Callable[[str], bool]) -> "PackageManagers":
        return cls(
            *(lookup(name) for name in (
                "pacman", "apt", "dnf", "rpm-ostree", "apk", "emerge"
            ))
        )
