from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


@dataclass(frozen=True)
class OSInfo:
    distro_id: str
    id_like: tuple[str, ...]
    name: str
    pretty_name: str
    variant_id: str
    family: str
    immutable: bool = False

    @property
    def label(self) -> str:
        return self.pretty_name or self.name or self.distro_id or "Unknown Linux"

    def is_like(self, *values: str) -> bool:
        expected = {value.lower() for value in values}
        return self.distro_id in expected or bool(expected.intersection(self.id_like))


def read_os_release() -> dict[str, str]:
    for path in (Path("/etc/os-release"), Path("/usr/lib/os-release")):
        if not path.exists():
            continue
        data: dict[str, str] = {}
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                data[key] = value.strip().strip('"')
            return data
        except OSError:
            continue
    return {}


def detect_os_info(raw: Mapping[str, str] | None = None, *, has_rpm_ostree: bool = False) -> OSInfo:
    data = dict(raw or read_os_release())
    distro_id = data.get("ID", "").strip().lower()
    id_like = tuple(part.strip().lower() for part in data.get("ID_LIKE", "").split() if part.strip())
    name = data.get("NAME", "").strip()
    pretty_name = data.get("PRETTY_NAME", "").strip()
    variant_id = data.get("VARIANT_ID", "").strip().lower()
    searchable = " ".join((distro_id, " ".join(id_like), name.lower(), pretty_name.lower(), variant_id))

    if any(token in searchable for token in ("steamos", "steamdeck", "holo")):
        family = "steamos"
        immutable = True
    elif has_rpm_ostree and any(token in searchable for token in ("bazzite", "ublue", "silverblue", "kinoite", "atomic")):
        family = "bazzite"
        immutable = True
    elif distro_id == "manjaro":
        family = "manjaro"
        immutable = False
    elif distro_id in {"cachyos", "cachy"}:
        family = "cachyos"
        immutable = False
    elif distro_id == "arch" or "arch" in id_like:
        family = "arch"
        immutable = False
    elif distro_id == "ubuntu":
        family = "ubuntu"
        immutable = False
    elif distro_id == "debian" or "debian" in id_like:
        family = "debian"
        immutable = False
    elif distro_id in {"fedora", "nobara"} or "fedora" in id_like:
        family = "fedora"
        immutable = False
    else:
        family = "unsupported"
        immutable = has_rpm_ostree

    return OSInfo(
        distro_id=distro_id,
        id_like=id_like,
        name=name,
        pretty_name=pretty_name,
        variant_id=variant_id,
        family=family,
        immutable=immutable,
    )
