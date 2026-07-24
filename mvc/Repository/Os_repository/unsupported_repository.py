from .base_repository import BaseOSRepository


class UnsupportedOSRepository(BaseOSRepository):
    family = "unsupported"

    def _unsupported(self) -> RuntimeError:
        return RuntimeError(
            f"Unsupported Linux distribution: {self.info.label}. "
            "Supported families are Arch/Manjaro/CachyOS, Debian/Ubuntu, Fedora, Bazzite and SteamOS."
        )

    def prepare_dependencies_command(self, component: str = "all", *, cu_manager_script: str = "") -> str:
        raise self._unsupported()

    def install_fan_pwm_command(self, tools_dir: str) -> str:
        raise self._unsupported()
