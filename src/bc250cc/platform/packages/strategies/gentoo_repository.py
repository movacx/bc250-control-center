from .base_repository import BaseOSRepository


class GentooRepository(BaseOSRepository):
    """Portage-backed preparation strategy for Gentoo-compatible hosts."""

    family = "gentoo"
    dependency_script = "gentoo/prepare-dependencies.sh"
    fan_script = "gentoo/prepare-fan-pwm.sh"
