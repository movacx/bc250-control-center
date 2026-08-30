from .base_repository import BaseOSRepository


class AlpineRepository(BaseOSRepository):
    """apk-backed preparation strategy for Alpine Linux hosts."""

    family = "alpine"
    dependency_script = "alpine/prepare-dependencies.sh"
    fan_script = "alpine/prepare-fan-pwm.sh"
