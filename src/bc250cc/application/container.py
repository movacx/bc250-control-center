"""Composition root for the application runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bc250cc.application.system import SystemStatus
from bc250cc.platform import PlatformCapabilities


@dataclass(slots=True)
class ApplicationContainer:
    """Own the concrete runtime dependencies used by application adapters."""

    platform: PlatformCapabilities
    system_service: Any | None = None
    system_repository: Any | None = None
    settings_service: Any | None = None
    activity_service: Any | None = None

    @classmethod
    def empty(cls) -> "ApplicationContainer":
        return cls(platform=PlatformCapabilities.detect())

    @classmethod
    def production(cls) -> "ApplicationContainer":
        """Build the source-only runtime composition without frontend imports."""

        from bc250cc.application.system.activity_service import ActivityService
        from bc250cc.application.system.settings_service import SettingsService
        from bc250cc.infrastructure.persistence.activity_journal import (
            activity_journal,
            activity_journal_path,
        )
        from bc250cc.infrastructure.persistence.configuracion_local import (
            ConfiguracionLocal,
        )
        from bc250cc.infrastructure.persistence.profile_bundle import (
            ProfileBundleRepository,
        )
        from bc250cc.infrastructure.sistema_repository import SistemaRepository
        from bc250cc.infrastructure.system_service import SistemaService

        repository = SistemaRepository()
        configuration = ConfiguracionLocal()
        activity_service = ActivityService(lambda: activity_journal(configuration))
        settings_service = SettingsService(
            configuration,
            ProfileBundleRepository(configuration),
            history_path=lambda: activity_journal_path(configuration),
            recovery_root=repository._recovery_snapshot_root,
        )
        return cls(
            platform=PlatformCapabilities.detect(),
            system_repository=repository,
            system_service=SistemaService(
                repository,
                activity_service=activity_service,
                settings_service=settings_service,
            ),
            settings_service=settings_service,
            activity_service=activity_service,
        )

    def system_status(self) -> SystemStatus:
        """Expose the already-detected platform state without re-probing."""

        return SystemStatus.from_capabilities(self.platform)
