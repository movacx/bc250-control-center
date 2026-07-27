from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from PyQt6.QtCore import QSettings

from mvc.config_paths import legacy_qt_config_dir, ui_settings_path

from ..i18n import normalize_language


logger = logging.getLogger(__name__)

# Kept only as migration identifiers. New settings no longer use Qt's
# organization/application-derived directory because that produced a second
# ~/.config/BC250ControlCenter tree alongside the XDG application directory.
ORGANIZATION_NAME = "BC250ControlCenter"
APPLICATION_NAME = "ControlCenter"
LEGACY_QT_SETTINGS_FILES = (
    "ControlCenter.conf",
    "ModernPreview.conf",
    "BC250ControlCenter.conf",
)


@dataclass(frozen=True)
class PreferenceMigrationState:
    missing_backend_language: bool
    missing_backend_appearance: bool


def _ini_settings(path: Path) -> QSettings:
    return QSettings(str(path), QSettings.Format.IniFormat)


def _migrate_legacy_qt_settings(destination: QSettings) -> None:
    """Merge legacy Qt preferences into the canonical XDG directory.

    ``ControlCenter.conf`` is the newest legacy source, so it receives first
    priority. Older preview/safety files only fill values that are still
    missing. Legacy files are removed only after the canonical settings file
    has synchronized successfully.
    """

    legacy_dir = legacy_qt_config_dir()
    migrated_paths: list[Path] = []
    for filename in LEGACY_QT_SETTINGS_FILES:
        source_path = legacy_dir / filename
        if not source_path.exists() or not source_path.is_file():
            continue
        if source_path.is_symlink():
            logger.warning("Skipping symlinked legacy settings file: %s", source_path)
            continue

        source = _ini_settings(source_path)
        source.sync()
        if source.status() != QSettings.Status.NoError:
            logger.warning("Could not read legacy settings file: %s", source_path)
            continue

        for key in source.allKeys():
            if not destination.contains(key):
                destination.setValue(key, source.value(key))
        migrated_paths.append(source_path)

    if not migrated_paths:
        return

    destination.sync()
    if destination.status() != QSettings.Status.NoError:
        logger.warning(
            "Legacy UI settings were read but could not be synchronized to %s",
            destination.fileName(),
        )
        return

    for source_path in migrated_paths:
        try:
            source_path.unlink()
        except OSError:
            logger.warning("Could not remove migrated settings file: %s", source_path, exc_info=True)

    try:
        legacy_dir.rmdir()
    except FileNotFoundError:
        return
    except OSError:
        # Preserve the directory if an unknown file exists. The application no
        # longer writes there, so no duplicate tree will be generated again.
        logger.debug("Legacy Qt settings directory is not empty: %s", legacy_dir)


def application_settings() -> QSettings:
    path = ui_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    settings = _ini_settings(path)
    _migrate_legacy_qt_settings(settings)
    return settings


class UiPreferences:
    """Own local presentation preferences and one-time legacy normalization."""

    THEME_VALUES = {"system", "light", "dark"}
    ACCENT_VALUES = {"blue", "violet", "cyan", "green", "orange"}
    DENSITY_VALUES = {"comfortable", "compact"}

    def __init__(self, settings: QSettings | None = None) -> None:
        self.settings = settings or application_settings()

    def initialize(self) -> PreferenceMigrationState:
        missing_language = not self.settings.contains("settings/language")
        missing_appearance = not self.settings.contains("settings/appearance")
        if missing_language:
            self.settings.setValue("settings/language", "auto")
        if missing_appearance:
            self.settings.setValue("settings/appearance", "system")

        self._migrate_legacy_safety_preferences()
        self._normalize_stored_codes()
        self.settings.sync()
        return PreferenceMigrationState(missing_language, missing_appearance)

    def bool_value(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, "true" if default else "false")
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def scale(self) -> int:
        try:
            value = int(self.settings.value("settings/scale", 100))
        except (TypeError, ValueError):
            value = 100
        return max(70, min(150, round(value / 10) * 10))

    @classmethod
    def normalize_theme(cls, value: object) -> str:
        aliases = {
            "sistema": "system", "système": "system",
            "claro": "light", "hell": "light", "светлая": "light", "світла": "light",
            "oscuro": "dark", "escuro": "dark", "dunkel": "dark", "тёмная": "dark", "темна": "dark",
        }
        normalized = aliases.get(str(value).strip().lower(), str(value).strip().lower())
        return normalized if normalized in cls.THEME_VALUES else "system"

    @classmethod
    def normalize_accent(cls, value: object) -> str:
        aliases = {
            "azul": "blue", "blau": "blue", "синий": "blue", "синій": "blue",
            "violeta": "violet", "violett": "violet", "фиолетовый": "violet", "фіолетовий": "violet",
            "cian": "cyan", "ciano": "cyan", "бирюзовый": "cyan", "бірюзовий": "cyan",
            "verde": "green", "grün": "green", "зелёный": "green", "зелений": "green",
            "naranja": "orange", "laranja": "orange", "оранжевый": "orange", "помаранчевий": "orange",
        }
        normalized = aliases.get(str(value).strip().lower(), str(value).strip().lower())
        return normalized if normalized in cls.ACCENT_VALUES else "blue"

    @classmethod
    def normalize_density(cls, value: object) -> str:
        aliases = {
            "cómoda": "comfortable", "comoda": "comfortable", "confortável": "comfortable",
            "komfortabel": "comfortable", "комфортная": "comfortable", "комфортна": "comfortable",
            "compacta": "compact", "kompakt": "compact", "компактная": "compact", "компактна": "compact",
        }
        normalized = aliases.get(str(value).strip().lower(), str(value).strip().lower())
        return normalized if normalized in cls.DENSITY_VALUES else "comfortable"

    def _migrate_legacy_safety_preferences(self) -> None:
        # Legacy root keys are copied into the canonical file by
        # _migrate_legacy_qt_settings(), so reading another QSettings instance
        # here would only recreate ~/.config/BC250ControlCenter.
        legacy = self.settings
        if not self.settings.contains("settings/scale"):
            try:
                scale = int(legacy.value("zoom_ui", 100))
            except (TypeError, ValueError):
                scale = 100
            self.settings.setValue("settings/scale", max(70, min(150, round(scale / 10) * 10)))
        if not self.settings.contains("settings/smart_alerts"):
            self.settings.setValue("settings/smart_alerts", legacy.value("alertas_activas", "false"))
        if not self.settings.contains("settings/desktop_notifications"):
            self.settings.setValue("settings/desktop_notifications", "true")
        if not self.settings.contains("settings/detailed_diagnostics"):
            discreet = str(legacy.value("modo_discreto", "true")).strip().lower() in {"1", "true", "yes", "on"}
            self.settings.setValue("settings/detailed_diagnostics", "false" if discreet else "true")
        if not self.settings.contains("settings/gamepad_navigation"):
            self.settings.setValue("settings/gamepad_navigation", "true")
        if not self.settings.contains("settings/gamepad_onscreen_keypad"):
            self.settings.setValue("settings/gamepad_onscreen_keypad", "true")
        if not self.settings.contains("settings/gamepad_keypad_auto_show"):
            self.settings.setValue("settings/gamepad_keypad_auto_show", "false")

        for legacy_key in ("zoom_ui", "alertas_activas", "modo_discreto"):
            self.settings.remove(legacy_key)

    def _normalize_stored_codes(self) -> None:
        self.settings.setValue(
            "settings/language",
            normalize_language(self.settings.value("settings/language", "auto")),
        )
        self.settings.setValue(
            "settings/appearance",
            self.normalize_theme(self.settings.value("settings/appearance", "system")),
        )
        self.settings.setValue(
            "settings/accent",
            self.normalize_accent(self.settings.value("settings/accent", "blue")),
        )
        self.settings.setValue(
            "settings/density",
            self.normalize_density(self.settings.value("settings/density", "comfortable")),
        )
