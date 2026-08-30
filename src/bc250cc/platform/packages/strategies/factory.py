from __future__ import annotations

from .alpine_repository import AlpineRepository
from .arch_repository import ArchRepository, CachyOSRepository, ManjaroRepository
from .bazzite_repository import BazziteRepository
from .debian_repository import DebianRepository, UbuntuRepository
from .detector import detect_os_info
from .fedora_repository import FedoraRepository
from .gentoo_repository import GentooRepository
from .steamos_repository import SteamOSRepository
from .unsupported_repository import UnsupportedOSRepository

_REPOSITORIES = {
    "arch": ArchRepository,
    "manjaro": ManjaroRepository,
    "cachyos": CachyOSRepository,
    "debian": DebianRepository,
    "ubuntu": UbuntuRepository,
    "fedora": FedoraRepository,
    "gentoo": GentooRepository,
    "alpine": AlpineRepository,
    "bazzite": BazziteRepository,
    "steamos": SteamOSRepository,
}


def create_os_repository(host):
    info = detect_os_info(host._os_release(), has_rpm_ostree=bool(host._command_path("rpm-ostree")))
    repository_type = _REPOSITORIES.get(info.family, UnsupportedOSRepository)
    return repository_type(host, info)
