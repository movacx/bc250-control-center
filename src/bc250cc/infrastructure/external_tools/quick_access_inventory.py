"""Read-only deployment inventory for the optional Decky Quick Access plugin."""
from __future__ import annotations

import ast
import os
import stat
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from bc250cc.platform.init.services import detect_init_manager

PLUGIN_NAME = "bc250-quick-access"
HELPER_PATH = Path("/usr/libexec/bc250-control-center/bc250-quick-access-helper")
EXPECTED_HELPER_PROTOCOL = 12


@dataclass(frozen=True)
class QuickAccessInventory:
    supported: bool
    controls_supported: bool
    init_system: str
    decky_plugin_root: str
    decky_detected: bool
    decky_plugin_root_safe: bool
    plugin_path: str
    plugin_present: bool
    plugin_safe: bool
    helper_path: str
    helper_present: bool
    helper_protected: bool
    helper_protocol: int | None
    plugin_protocol: int | None
    protocol_compatible: bool
    ready: bool
    next_action: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _protected_regular(path: Path, *, executable: bool = False) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
        and metadata.st_uid == 0
        and not metadata.st_mode & 0o022
        and (not executable or bool(metadata.st_mode & stat.S_IXUSR))
    )


def _decky_plugin_file(path: Path) -> bool:
    """Check Decky plugin structure without claiming it is root-owned.

    Decky discovers plugins below the user's home directory while its loader
    is a root service.  That directory is an explicit Decky trust boundary,
    not an independently protected BC250 runtime.  The fixed helper under
    /usr/libexec is the only payload for which this inventory asserts root
    ownership.
    """
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)


def _decky_payload_present(path: Path) -> bool:
    """Report a payload's existence without letting unreadable paths escape."""
    try:
        metadata = path.stat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode)


def _decky_plugin_directory(path: Path) -> bool:
    """Require every deployed Decky payload directory to be non-symlinked.

    Decky itself owns the plugin trust boundary, but the explicit installer
    deliberately refuses symlinked deployment paths.  The read-only inventory
    must use the same rule so it never reports a layout as ready that the
    installer would refuse to create or repair.
    """
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode)


def _declared_protocol(path: Path) -> int | None:
    """Inspect a bounded Python declaration; never import or execute a plugin."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            source = handle.read(1024 * 1024 + 1)
        if len(source) > 1024 * 1024:
            return None
        tree = ast.parse(source)
        declarations = [node.value for node in tree.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "HELPER_PROTOCOL"
                                for target in node.targets)]
        if len(declarations) == 1:
            value = declarations[0]
            if isinstance(value, ast.Constant) and type(value.value) is int:
                return value.value
    except (OSError, UnicodeError, SyntaxError, RecursionError):
        pass
    return None


def quick_access_inventory(
    *,
    os_family: str,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    helper_path: Path = HELPER_PATH,
) -> QuickAccessInventory:
    """Inspect only declared Decky/plugin paths; never create or modify them."""
    home = Path.home() if home is None else Path(home)
    environ = os.environ if environ is None else environ
    plugin_root = Path(environ.get("DECKY_PLUGIN_ROOT", home / "homebrew" / "plugins"))
    plugin_path = plugin_root / PLUGIN_NAME
    manifest = plugin_path / "plugin.json"
    package = plugin_path / "package.json"
    backend = plugin_path / "main.py"
    bundle = plugin_path / "dist" / "index.js"
    policy_runtime = plugin_path / "bc250cc/domain/gpu/profiles.py"
    decky_detected = plugin_root.is_dir()
    decky_plugin_root_safe = _decky_plugin_directory(plugin_root)
    # A Decky plugin can be root-managed. Treat an unreadable payload as not
    # present/verified rather than allowing pathlib's permission error to
    # break the entire BC250 tool inventory or dashboard refresh.
    plugin_present = all(_decky_payload_present(path) for path in (manifest, package, backend, bundle))
    plugin_safe = bool(
        decky_plugin_root_safe
        and _decky_plugin_directory(plugin_path)
        and _decky_plugin_directory(plugin_path / "dist")
        and _decky_plugin_directory(plugin_path / "bc250cc")
        and _decky_plugin_directory(plugin_path / "bc250cc/domain")
        and _decky_plugin_directory(plugin_path / "bc250cc/domain/gpu")
        and all(
            _decky_plugin_file(path)
            for path in (manifest, package, backend, bundle, policy_runtime)
        )
    )
    helper_present = helper_path.is_file()
    helper_protected = _protected_regular(helper_path, executable=True)
    helper_protocol = _declared_protocol(helper_path) if helper_protected else None
    plugin_protocol = _declared_protocol(backend) if plugin_safe else None
    protocol_compatible = helper_protocol == plugin_protocol == EXPECTED_HELPER_PROTOCOL
    family = str(os_family).lower()
    init_system = detect_init_manager().kind
    # Decky is a capability boundary, not a SteamOS brand check. Bazzite Deck
    # images and CachyOS handheld sessions can host the same plugin when Decky
    # and the protected helper are present. The helper still reports each
    # unavailable hardware backend independently, so partial readiness never
    # becomes an optimistic CU/CPU write.
    known_game_mode_family = family in {"steamos", "bazzite", "cachyos"}
    # A systemd host can use the explicit, user-confirmed upstream Decky
    # bootstrap even when its distribution is not branded as a handheld OS.
    # This deliberately remains independent from package-manager detection:
    # Arch/Manjaro, Fedora and Ubuntu/Mint all reach the same capability path.
    # Non-systemd hosts keep passive detection for an existing Decky payload,
    # but are never offered an unverified service bootstrap.
    supported = bool(known_game_mode_family or init_system == "systemd" or decky_detected)
    controls_supported = bool(known_game_mode_family or init_system == "systemd")
    ready = bool(
        supported and controls_supported and decky_detected
        and plugin_present and plugin_safe and helper_protected and protocol_compatible
    )
    if not supported:
        next_action = (
            "Quick Access needs an existing Decky Loader on this distribution; "
            "upstream support outside SteamOS is not guaranteed."
        )
    elif not decky_detected:
        next_action = "Install Decky + Quick Access (Beta)"
    elif not controls_supported:
        next_action = (
            f"Decky is present, but Quick Access hardware controls are not "
            f"supported through {init_system}; use the Desktop application for live state."
        )
    elif not decky_plugin_root_safe:
        next_action = "Use a real Decky plugin directory, not a symbolic link, then reinstall BC250 Quick Access from Desktop Mode."
    elif not plugin_present or not helper_present:
        next_action = "Run the explicit BC250 Quick Access installer from Desktop Mode."
    elif not plugin_safe or not helper_protected or not protocol_compatible:
        next_action = "Reinstall BC250 Quick Access from Desktop Mode; payload verification failed."
    else:
        next_action = "Quick Access is ready. Decky remains the trusted plugin environment; reload Decky or restart Game Mode if it is not visible yet."
    return QuickAccessInventory(
        supported=supported,
        controls_supported=controls_supported,
        init_system=init_system,
        decky_plugin_root=str(plugin_root),
        decky_detected=decky_detected,
        decky_plugin_root_safe=decky_plugin_root_safe,
        plugin_path=str(plugin_path),
        plugin_present=plugin_present,
        plugin_safe=plugin_safe,
        helper_path=str(helper_path),
        helper_present=helper_present,
        helper_protected=helper_protected,
        helper_protocol=helper_protocol,
        plugin_protocol=plugin_protocol,
        protocol_compatible=protocol_compatible,
        ready=ready,
        next_action=next_action,
    )
