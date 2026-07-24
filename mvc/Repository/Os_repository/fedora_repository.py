from .base_repository import BaseOSRepository


class FedoraRepository(BaseOSRepository):
    family = "fedora"
    dependency_script = "fedora/prepare-dependencies.sh"
    fan_script = "fedora/prepare-fan-pwm.sh"
