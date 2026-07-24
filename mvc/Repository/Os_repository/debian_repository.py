from .base_repository import BaseOSRepository


class DebianRepository(BaseOSRepository):
    family = "debian"
    dependency_script = "debian/prepare-dependencies.sh"
    fan_script = "debian/prepare-fan-pwm.sh"


class UbuntuRepository(DebianRepository):
    family = "ubuntu"
