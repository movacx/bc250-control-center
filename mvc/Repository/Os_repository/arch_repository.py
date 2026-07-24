from .base_repository import BaseOSRepository


class ArchRepository(BaseOSRepository):
    family = "arch"
    dependency_script = "arch/prepare-dependencies.sh"
    fan_script = "arch/prepare-fan-pwm.sh"


class ManjaroRepository(ArchRepository):
    family = "manjaro"


class CachyOSRepository(ArchRepository):
    family = "cachyos"
