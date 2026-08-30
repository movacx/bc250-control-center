"""systemd/OpenRC capability adapters."""

from .manager import InitSystem, detect_init_system

__all__ = ["InitSystem", "detect_init_system"]
