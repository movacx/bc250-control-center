"""Pure SteamOS session and privileged-helper trust policy."""

from __future__ import annotations

from dataclasses import dataclass

DESKTOP_TOKENS = ("kde", "plasma", "gnome", "cinnamon", "xfce", "mate", "lxqt")


@dataclass(frozen=True)
class SteamSessionSignals:
    is_steamos: bool
    desktop: str = ""
    direct_game_marker: bool = False
    wayland_display: str = ""
    gamescope_ancestor: bool = False
    steam_ids: bool = False
    steam_ancestor: bool = False


def has_desktop_shell(desktop: object) -> bool:
    text = str(desktop or "").lower()
    return any(token in text for token in DESKTOP_TOKENS)


def classify_steamos_game_mode(signals: SteamSessionSignals) -> bool:
    """Classify locally observed signals; ambiguous ambient state fails closed."""
    if not signals.is_steamos:
        return False
    # An actual gamescope ancestor is stronger than inherited desktop labels.
    if signals.gamescope_ancestor:
        return True
    # Desktop shells win over spoofable/inherited Steam environment variables.
    if has_desktop_shell(signals.desktop):
        return False
    wayland = signals.wayland_display.lower()
    if signals.direct_game_marker or "gamescope" in wayland or "steam" in wayland:
        return True
    return signals.steam_ids and signals.steam_ancestor


def trusted_helper_metadata(
    *, is_regular: bool, is_symlink: bool, owner_uid: int, mode: int, executable: bool
) -> bool:
    """Require a root-owned, non-writable, executable regular helper."""
    return bool(
        is_regular
        and not is_symlink
        and owner_uid == 0
        and executable
        and mode & 0o022 == 0
    )
