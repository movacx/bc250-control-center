"""Adapters for hardware, persistence, external tools and privilege."""

from .init_services import OpenRCService, SystemdUserService

__all__ = ["OpenRCService", "SystemdUserService"]
