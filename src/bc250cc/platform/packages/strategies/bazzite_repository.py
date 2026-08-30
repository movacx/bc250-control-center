from .fedora_repository import FedoraRepository


class BazziteRepository(FedoraRepository):
    family = "bazzite"
    dependency_script = "bazzite/prepare-dependencies.sh"
    fan_script = "bazzite/prepare-fan-pwm.sh"
    fan_persistence_script = "bazzite/install-fan-persistence.sh"
