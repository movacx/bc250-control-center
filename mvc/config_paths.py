from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path


APP_ID = "bc250-control-center"
LEGACY_QT_ORGANIZATION = "BC250ControlCenter"
UI_SETTINGS_FILENAME = "ui.conf"


def _environment(env: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if env is None else env


def _home(home: str | Path | None) -> Path:
    return Path.home() if home is None else Path(home).expanduser()


def xdg_config_home(
    *,
    env: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    value = _environment(env).get("XDG_CONFIG_HOME", "").strip()
    return Path(value).expanduser() if value else _home(home) / ".config"


def xdg_data_home(
    *,
    env: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    value = _environment(env).get("XDG_DATA_HOME", "").strip()
    return Path(value).expanduser() if value else _home(home) / ".local" / "share"


def xdg_cache_home(
    *,
    env: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    value = _environment(env).get("XDG_CACHE_HOME", "").strip()
    return Path(value).expanduser() if value else _home(home) / ".cache"


def app_config_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    return xdg_config_home(env=env, home=home) / APP_ID


def app_data_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    return xdg_data_home(env=env, home=home) / APP_ID


def app_cache_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    return xdg_cache_home(env=env, home=home) / APP_ID


def ui_settings_path(
    *,
    env: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    return app_config_dir(env=env, home=home) / UI_SETTINGS_FILENAME


def legacy_qt_config_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | Path | None = None,
) -> Path:
    return xdg_config_home(env=env, home=home) / LEGACY_QT_ORGANIZATION
