"""Channel board use cases: edit one channel, name it, save and apply modes.

Every change is saved to the local desktop config first; the caller then
hands the resulting policy to the root service (``policy()``), the same way
the v1 curve was synced. Nothing here writes a PWM register.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from bc250cc.domain.fan import channels as model
from bc250cc.domain.fan import engine
from bc250cc.infrastructure.system_fan_control import build_system_fan_policy


class LocalConfig(Protocol):
    def read_local_config(self) -> dict: ...
    def save_local_config(self, values: dict) -> dict: ...


@dataclass(frozen=True)
class ChannelBoard:
    """What the channel board shows, from the saved config alone."""

    channels: dict[str, dict]
    labels: dict[str, str]
    modes: list[dict]
    active_mode: str
    policy: dict | None

    @property
    def controlled(self) -> list[int]:
        return engine.controlled_channels(self.policy) if self.policy else []

    @property
    def needs_root_service(self) -> bool:
        """More than one controlled channel: the desktop fallback cannot
        follow it (debate round 2), only the root service can."""
        return len(self.controlled) > 1


class FanChannelsService:
    def __init__(self, settings: LocalConfig):
        self._settings = settings

    def _config(self) -> dict:
        config = self._settings.read_local_config()
        return config if isinstance(config, dict) else {}

    def _save(self, updates: dict) -> ChannelBoard:
        if updates:
            self._settings.save_local_config(updates)
        return self.board()

    def board(self) -> ChannelBoard:
        config = self._config()
        channels = model.normalize_fan_channels(config.get("fan_channels"))
        if not channels:
            channels = model.legacy_channels(config)
        return ChannelBoard(
            channels=channels,
            labels=model.normalize_fan_labels(config.get("fan_channel_labels")),
            modes=model.normalize_fan_modes(config.get("fan_modes")),
            active_mode=str(config.get("fan_active_mode") or ""),
            policy=build_system_fan_policy(config),
        )

    def migrate_legacy(self) -> ChannelBoard:
        return self._save(model.migrate_legacy_config(self._config()))

    def set_channel(self, pwm: int, entry: dict | None) -> ChannelBoard:
        return self._save(model.set_channel(self._config(), pwm, entry))

    def set_label(self, pwm: int, label: str) -> ChannelBoard:
        config = self._config()
        labels = model.normalize_fan_labels(config.get("fan_channel_labels"))
        cleaned = model.normalize_fan_labels({str(pwm): label})
        labels.pop(str(pwm), None)
        labels.update(cleaned)
        return self._save({"fan_channel_labels": labels})

    def save_mode(self, name: str, *, channels: dict | None = None) -> ChannelBoard:
        return self._save(model.save_mode(self._config(), name, channels=channels))

    def preview_channel(self, pwm: int, entry: dict | None) -> dict | None:
        config = self._config()
        return build_system_fan_policy({**config, **model.set_channel(config, pwm, entry)})

    def delete_mode(self, name: str) -> ChannelBoard:
        return self._save(model.delete_mode(self._config(), name))

    def apply_mode(self, name: str, targets=()) -> ChannelBoard:
        """Make mode ``name`` the active set. ``targets``: the headers a
        built-in mode drives when no channel is configured yet."""
        return self._save(self._mode_updates(name, targets))

    def preview_mode(self, name: str, targets=()) -> dict | None:
        return build_system_fan_policy({**self._config(), **self._mode_updates(name, targets)})

    def _mode_updates(self, name: str, targets=()) -> dict:
        config = self._config()
        key = name.casefold()
        builtin = {label.casefold(): ident for ident, label in model.BUILTIN_MODE_NAMES.items()}
        saved = next(
            (mode for mode in model.normalize_fan_modes(config.get("fan_modes"))
             if mode["name"].casefold() == key),
            None,
        )
        if saved is None and key in builtin:
            saved = model.builtin_mode(builtin[key], config, targets)
        if saved is None:
            raise ValueError(f"There is no fan mode called {name!r}.")
        return model.apply_mode(config, saved)
