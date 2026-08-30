from .arch_repository import ArchRepository


class SteamOSRepository(ArchRepository):
    family = "steamos"
    dependency_script = "steamos/prepare-dependencies.sh"
    fan_script = "steamos/prepare-fan-pwm.sh"
