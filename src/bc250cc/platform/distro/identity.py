"""OS metadata used for installation selection only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DistroIdentity:
    distro_id: str
    id_like: tuple[str, ...] = ()
    pretty_name: str = ""

    @property
    def family(self) -> str:
        values = {self.distro_id, *self.id_like}
        if "steamos" in values or self.distro_id in {"holo", "steamdeck"}:
            return "steamos"
        if "bazzite" in values:
            return "bazzite"
        # Artix commonly advertises ID_LIKE=arch, but its package/service
        # integration is OpenRC. Select the family from the concrete distro
        # identity before considering inherited metadata.
        if self.distro_id in {"alpine", "artix", "devuan", "gentoo", "funtoo"}:
            return "openrc"
        if "arch" in values or self.distro_id in {"manjaro", "cachyos"}:
            return "arch"
        if "alpine" in values:
            return "openrc"
        if "debian" in values or "ubuntu" in values:
            return "debian"
        if "fedora" in values or "rhel" in values:
            return "fedora"
        return "unknown"


def read_os_release(path: Path = Path("/etc/os-release")) -> DistroIdentity:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value.strip().strip('"')
    return DistroIdentity(
        values.get("ID", "unknown").lower(),
        tuple(item.lower() for item in values.get("ID_LIKE", "").split()),
        values.get("PRETTY_NAME", ""),
    )
