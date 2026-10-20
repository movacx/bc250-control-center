"""The Processes page's inventory: the user's applications, games and tasks.

Read-only, and only ever about the processes of the user running Control
Center. Everything comes from files that user may read without a password:

* ``/proc/<pid>/cgroup`` names the application scope the desktop started a
  process in. systemd's naming (``app[-<launcher>]-<id>[@<random>].service``
  or ``…-<random>.scope``) is shared by KDE, GNOME, uwsm and Flatpak; Snap
  uses ``snap.<package>.<app>.…``, and D-Bus activation ``dbus-:1.N-<id>``.
  Every helper, renderer and GPU process of Chrome, an Electron app or
  Spotify shares its scope, so they are one application. ``session.slice``
  holds the programs the desktop session itself depends on.
* Without application scopes (Hyprland or Sway without uwsm, OpenRC, runit,
  s6), the process tree groups an application's children under it, and
  ``$XDG_RUNTIME_DIR/.flatpak`` names each Flatpak instance's processes.
* ``.desktop`` files, found as the XDG base directory spec says, give that
  application its name in each language and its icon.
* ``/proc/<pid>/smaps_rollup`` gives PSS: shared pages divided between the
  processes that share them. Reading it holds the process's mmap lock and
  costs milliseconds per large process, so it is read every
  ``PSS_REFRESH_SECONDS`` within a time budget, and never for a game.
* ``/proc/<pid>/fdinfo`` of each open render node gives the process's GPU
  engine time and the memory it holds in VRAM and in GTT (system memory the
  GPU maps; on the BC-250, whose VRAM carve-out is small, most of it).
* ``SteamAppId`` and Steam's own app manifests and shortcuts name a Steam
  game; Lutris, Heroic and umu set their own variables and must not be taken
  for Steam.

Protection is decided by the program's own name, never by its arguments:
an Electron app started with ``--ozone-platform=wayland`` is not the
compositor, and a command that merely mentions ``dbus`` is not the bus.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from bc250cc.domain.common.proceso import Proceso

PROC = Path("/proc")

#: Programs that hold the session together: ending one logs the user out,
#: drops the display or the sound. Shown under System, never closable.
SESSION_PROGRAMS = frozenset({
    # Bus, display managers, X and audio.
    "systemd", "(sd-pam)", "dbus-daemon", "dbus-broker", "dbus-broker-launch",
    "sddm", "sddm-helper", "gdm", "gdm-wayland-session", "gdm-x-session", "lightdm", "greetd",
    "xorg", "xwayland", "pipewire", "pipewire-pulse", "wireplumber", "pulseaudio",
    "dconf-service", "ibus-daemon", "fcitx5", "at-spi-bus-launcher", "at-spi2-registryd",
    "xdg-desktop-portal", "xdg-document-portal", "xdg-permission-store",
    # KDE Plasma.
    "kwin_wayland", "kwin_x11", "kwin_wayland_wrapper", "plasmashell", "startplasma-wayland",
    "startplasma-x11", "plasma_session", "ksmserver", "kded5", "kded6", "kglobalaccel",
    "kglobalacceld", "kaccess", "kactivitymanagerd", "kwalletd5", "kwalletd6", "ksecretd",
    "powerdevil", "org_kde_powerdevil", "polkit-kde-authentication-agent-1",
    # GNOME.
    "gnome-shell", "gnome-session-binary", "gnome-session-service", "gnome-session", "mutter",
    "gnome-keyring-daemon", "polkit-gnome-authentication-agent-1",
    # XFCE.
    "xfce4-session", "xfwm4", "xfce4-panel", "xfdesktop", "xfsettingsd", "xfce4-power-manager",
    # Cinnamon.
    "cinnamon", "cinnamon-session", "cinnamon-session-binary", "muffin", "cinnamon-killer-daemon",
    # MATE.
    "mate-session", "marco", "mate-panel", "mate-settings-daemon", "mate-power-manager",
    "polkit-mate-authentication-agent-1",
    # LXQt (pcmanfm-qt draws its desktop).
    "lxqt-session", "lxqt-panel", "lxqt-policykit-agent", "lxqt-powermanagement",
    "lxqt-notificationd", "lxqt-globalkeysd", "pcmanfm-qt",
    # Budgie.
    "budgie-daemon", "budgie-panel", "budgie-desktop", "budgie-polkit-dialog", "budgie-wm",
    # COSMIC.
    "cosmic-comp", "cosmic-session", "cosmic-panel", "cosmic-bg", "cosmic-osd",
    "cosmic-notifications", "cosmic-idle", "cosmic-settings-daemon",
    # Hyprland, wlroots compositors and their companions.
    "hyprland", "start-hyprland", "hyprpaper", "hypridle", "hyprpolkitagent",
    "sway", "swaybar", "swaybg", "swayidle", "swaync", "niri", "niri-session", "river",
    "wayfire", "labwc", "waybar", "mako", "dunst", "uwsm",
    # X11 window managers.
    "i3", "i3bar", "openbox", "enlightenment", "enlightenment_start", "xss-lock",
    # Gaming mode.
    "steamos-session-select",
})
#: Name prefixes of the same kind (GNOME's and MATE's settings daemons, gvfs,
#: ibus, Cinnamon's settings daemons, COSMIC's panel applets).
SESSION_PREFIXES = ("gsd-", "msd-", "csd-", "gvfs", "ibus-", "at-spi", "xdg-desktop-portal",
                    "cosmic-applet-", "lxqt-")
#: Screen lockers. With ext-session-lock a dead locker leaves the session
#: locked for good; on X11 killing one unlocks it. Neither may be ended or
#: paused.
LOCKER_PROGRAMS = frozenset({
    "kscreenlocker_greet", "hyprlock", "swaylock", "waylock", "gtklock", "i3lock", "i3lock-color",
    "xsecurelock", "xscreensaver", "light-locker", "cinnamon-screensaver", "mate-screensaver",
    "gnome-screensaver", "xflock4", "cosmic-greeter", "slock", "physlock",
})
#: Shells and terminals: closing one ends every command typed in it.
SHELL_PROGRAMS = frozenset({
    "bash", "zsh", "fish", "sh", "dash", "tcsh", "ksh", "nu",
    "konsole", "yakuake", "ptyxis", "kgx", "gnome-terminal-server", "xterm",
    "alacritty", "kitty", "foot", "wezterm-gui", "terminator", "tilix", "xfce4-terminal",
})
#: Programs that start applications for the user and step aside. A program
#: they start is an application of its own, never part of the launcher.
LAUNCHER_PROGRAMS = frozenset({
    "rofi", "wofi", "fuzzel", "tofi", "bemenu", "bemenu-run", "dmenu", "dmenu_run", "walker",
    "anyrun", "krunner", "ulauncher", "albert", "nwg-drawer", "nwg-menu", "sirula", "yofi",
    "kickoff", "j4-dmenu-desktop", "uwsm-app", "app2unit", "xdg-open", "gio", "kioclient",
    "kioclient5", "kde-open", "setsid", "nohup", "env", "systemd-run", "flatpak-spawn",
    "dbus-launch", "dbus-run-session", "sudo", "pkexec", "lutris", "heroic",
})
#: Background services of the desktop: closable, shown under Background.
BACKGROUND_PROGRAMS = frozenset({
    "baloo_file", "baloo_file_extractor", "baloorunner", "kdeconnectd", "ssh-agent",
    "gpg-agent", "tracker-miner-fs-3", "localsearch-3", "gnome-software",
    "evolution-source-registry", "evolution-calendar-factory",
    "evolution-addressbook-factory", "goa-daemon", "goa-identity-service",
    "kiod6", "kiod5", "kioworker", "kioslave5", "obexd", "geoclue", "gvfsd",
    "xembedsniproxy", "gmenudbusmenuproxy", "kscreen_backend_launcher",
    "ksystemstats", "kded", "kwalletmanager5", "dbus-run-session",
})
#: Programs that run code named by their arguments: the app is that code.
INTERPRETERS = frozenset({
    "python", "python3", "electron", "node", "java", "mono", "dotnet", "ruby", "perl",
    "php", "qml", "qmlscene", "gjs", "lua",
})
#: Processes of a game besides the game itself: Steam's launch wrapper,
#: Proton's Wine server, the container runtime and gamescope as a wrapper.
GAME_HELPER_PROGRAMS = frozenset({
    "reaper", "pressure-vessel-wrap", "pv-bwrap", "pv-adverb", "wineserver",
    "wine", "wine64", "wine-preloader", "wine64-preloader", "proton",
    "steam-runtime-launcher-service", "srt-bwrap", "explorer.exe", "services.exe",
    "winedevice.exe", "plugplay.exe", "svchost.exe", "rpcss.exe", "tabtip.exe",
    "start.exe", "conhost.exe", "steam.exe", "gamescope", "gamescopereaper", "umu-run",
})
#: Launcher names systemd unit names carry before the application id
#: (``app-gnome-org.gnome.Nautilus-123.scope``; uwsm uses the first entry
#: of XDG_CURRENT_DESKTOP). The session's own desktop names are added.
UNIT_LAUNCHERS = frozenset({
    "gnome", "kde", "flatpak", "hyprland", "sway", "niri", "river", "wayfire", "labwc",
    "cosmic", "xfce", "lxqt", "mate", "cinnamon", "x", "budgie", "unity", "pantheon",
    "gamescope", "wlroots", "enlightenment", "i3", "openbox", "deepin", "ukui",
})
#: GPU engines that are not rendering: video decode and encode, copy and
#: DMA engines. A video playing is not GPU load the way a game is.
_NON_RENDER_ENGINES = ("dec", "enc", "jpeg", "vcn", "video", "vpe", "dma", "sdma", "copy",
                       "bcs", "vcs", "vecs", "uvd", "vce", "mmio")
_WINDOWS_EXE = re.compile(r"([^\\/:]+?\.exe)(?:\s|$)", re.IGNORECASE)
_STEAM_LAUNCH = re.compile(r"(?:SteamLaunch AppId=|steam_app_|AppId=)([0-9]{1,10})\b")
_NIX_WRAPPED = re.compile(r"\.(.+?)-wrap(?:p(?:e(?:d)?)?)?")
_DBUS_UNIT = re.compile(r"dbus-:[0-9]+\.[0-9]+-(.+?)(?:@[^/]*)?\.service")
_UNIT_ESCAPE = re.compile(r"\\x([0-9a-fA-F]{2})")
_APPIMAGE_VERSION = re.compile(
    r"[-_.]?(?:v?[0-9][0-9A-Za-z.+~]*)?(?:[-_.](?:x86[-_]64|amd64|aarch64|arm64|i686|x64))?$",
    re.IGNORECASE,
)
_UNITS = {"KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "kB": 1000, "MB": 1000 ** 2}
_DESKTOP_TTL_SECONDS = 300.0
#: How often a process's PSS is read again, and how long one sample may
#: spend refreshing it. New processes are always read at once.
PSS_REFRESH_SECONDS = 30.0
PSS_BUDGET_SECONDS = 0.06
#: Steam marks the 32-bit id of a non-Steam shortcut with its top bit.
_SHORTCUT_BIT = 1 << 31


# ---------------------------------------------------------------- identity


def program_name(name: str, cmdline: list[str]) -> str:
    """The program's own name: the executable, never an argument."""
    first = cmdline[0] if cmdline else ""
    # Wine passes Windows paths: backslashes, and spaces ("Program Files").
    windows = _WINDOWS_EXE.search(first)
    if windows:
        return windows.group(1)
    base = os.path.basename(first.split(" ", 1)[0]) if first else ""
    # Chromium-style helpers rewrite argv[0] in place; comm is truthful.
    base = (base or name or "?").strip()
    # NixOS wraps programs as .firefox-wrapped (comm cuts it to 15 bytes).
    wrapped = _NIX_WRAPPED.fullmatch(base)
    return wrapped.group(1) if wrapped else base


def session_reason(program: str) -> str:
    """Why a program must not be closed, or "" when it may."""
    low = program.lower()
    if low in LOCKER_PROGRAMS:
        return "screen locker"
    if low in SESSION_PROGRAMS or low.startswith(SESSION_PREFIXES):
        return "desktop session"
    if low in SHELL_PROGRAMS:
        return "shell or terminal"
    if low.startswith("bc250-"):
        return "BC250 Control Center"
    return ""


def _gamescope_is_session(program: str, cmdline: list[str]) -> bool:
    """gamescope as Gaming Mode's compositor, not as a game's wrapper.

    The session starts gamescope on its own and Steam beside it (or after
    ``--``); a wrapper (``gamescope -W 1920 -- %command%``) runs a game.
    """
    if "--" not in cmdline:
        return program.lower() != "gamescopereaper"
    after = cmdline[cmdline.index("--") + 1:]
    return bool(after) and os.path.basename(after[0]).lower() in {"steam", "steam.sh"}


def protection_reason(program: str, cmdline: list[str] | tuple = (), cgroup_text: str = "") -> str:
    """Why a process must not be ended or paused, or "" when it may."""
    low = program.lower()
    if low in {"gamescope", "gamescope-wl", "gamescopereaper"}:
        return "game mode session" if _gamescope_is_session(program, list(cmdline)) else ""
    if low == "steam" and "-steamos3" in cmdline:
        # Gaming Mode ends gamescope, the whole session, when Steam exits.
        return "game mode session"
    reason = session_reason(program)
    if reason:
        return reason
    if cgroup_slice(cgroup_text) == "session":
        return "desktop session"
    return ""


def _cgroup_path(cgroup_text: str) -> str:
    for line in cgroup_text.splitlines():
        # The unified hierarchy's line; on hybrid systems the systemd one.
        # hierarchy-id:controllers:path, and the path itself may hold ":"
        # (D-Bus activated units are named after the bus name, dbus-:1.2-…).
        if line.startswith("0::") or ":name=systemd:" in line:
            parts = line.split(":", 2)
            return parts[2] if len(parts) == 3 else ""
    return ""


def cgroup_slice(cgroup_text: str) -> str:
    """"session", "background", "service" or "" for a process's cgroup.

    systemd's desktop convention puts the session's own programs in
    session.slice (uwsm: session-graphical.slice), optional helpers in
    background.slice, and user services that are not applications run as
    plain ``.service`` units in app.slice.
    """
    path = _cgroup_path(cgroup_text)
    components = path.strip("/").split("/") if path else []
    if any(part in {"session.slice", "session-graphical.slice"} for part in components):
        return "session"
    if any(part in {"background.slice", "background-graphical.slice"} for part in components):
        return "background"
    if components and "app.slice" in components[:-1] and components[-1].endswith(".service") \
            and not components[-1].startswith(("app-", "dbus-", "snap.")):
        return "service"
    return ""


def _unescape(text: str) -> str:
    return _UNIT_ESCAPE.sub(lambda match: chr(int(match.group(1), 16)), text)


def _unit_candidates(unit: str, launchers: frozenset[str]) -> tuple[str, ...] | None:
    """Application ids one unit name may stand for, best first; None when
    the unit is not an application's."""
    if unit.startswith("snap."):
        parts = unit.split(".")
        # snap.<package>.<app>.<uuid>.scope or snap.<package>.<app>.service
        if len(parts) >= 4 and parts[-1] in {"scope", "service"}:
            return (f"{parts[1]}_{parts[2]}",)
        return None
    dbus = _DBUS_UNIT.fullmatch(unit)
    if dbus:
        return (_unescape(dbus.group(1)),)
    if not unit.startswith("app-"):
        return None
    body = unit[4:]
    if body.endswith(".scope"):
        head, separator, _random = body[:-6].rpartition("-")
        if not separator or not head:
            return None
        body = head
    elif body.endswith(".service"):
        body = body[:-8].split("@", 1)[0]
    else:
        return None
    # An unescaped "-" separates the launcher; one inside the id is \x2d.
    parts = body.split("-")
    full = _unescape(body)
    if len(parts) > 1 and _unescape(parts[0]).lower() in launchers:
        # A launcher that did not escape the id's dashes: try both.
        return (_unescape("-".join(parts[1:])), full)
    return (full,) if full else None


def _desktop_launchers() -> frozenset[str]:
    names = {part.lower() for part in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":") if part}
    return UNIT_LAUNCHERS | names


def scope_candidates(cgroup_text: str, launchers: frozenset[str] | None = None) -> tuple[str, ...]:
    """Application ids of the innermost application unit, best first.

    Plasma 6 nests a ``main.scope`` inside the application's unit, and
    Konsole a ``tab(<pid>).scope`` per tab: what runs in a tab belongs to
    the command typed there, never to Konsole.
    """
    launchers = launchers if launchers is not None else _desktop_launchers()
    path = _cgroup_path(cgroup_text)
    for component in reversed(path.strip("/").split("/") if path else []):
        if component.startswith("tab(") and component.endswith(".scope"):
            return ()
        candidates = _unit_candidates(component, launchers)
        if candidates:
            return candidates
    return ()


def scope_application(cgroup_text: str) -> str:
    """The desktop application id of a process's systemd unit, or ""."""
    candidates = scope_candidates(cgroup_text)
    return candidates[0] if candidates else ""


def read_cgroup(pid: int, proc: Path = PROC) -> str:
    return _read(proc / str(pid) / "cgroup", 8192)


def smaps_pss(text: str) -> int | None:
    """PSS in bytes from smaps_rollup, or None."""
    for line in text.splitlines():
        if line.startswith("Pss:"):
            try:
                return int(line.split()[1]) * 1024
            except (IndexError, ValueError):
                return None
    return None


# --------------------------------------------------------------------- GPU


@dataclass(frozen=True)
class GpuClient:
    """One DRM client of a process, from its fdinfo.

    ``engine_ns`` is the rendering engines' busy time (graphics and compute,
    each divided by its capacity); video and copy engines are left out.
    ``vram`` and ``gtt`` are the resident bytes in each region.
    """

    client_id: str
    engine_ns: int
    vram: int
    gtt: int = 0
    pdev: str = ""

    @property
    def key(self) -> str:
        return f"{self.pdev}/{self.client_id}"


def _size(value: str) -> int | None:
    number, _space, unit = value.strip().partition(" ")
    try:
        return int(number) * _UNITS.get(unit.strip(), 1)
    except ValueError:
        return None


def parse_fdinfo(text: str) -> GpuClient | None:
    """A DRM client's rendering time and resident GPU memory, or None."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, _sep, value = line.partition(":")
        values[key.strip()] = value.strip()
    if not values.get("drm-driver"):
        return None
    engine = 0
    for key, value in values.items():
        if not key.startswith("drm-engine-") or key.startswith("drm-engine-capacity-"):
            continue
        name = key.removeprefix("drm-engine-")
        if name.startswith(_NON_RENDER_ENGINES):
            continue
        try:
            busy = int(value.split()[0])
            capacity = max(1, int(values.get(f"drm-engine-capacity-{name}", "1").split()[0]))
        except (IndexError, ValueError):
            continue
        engine += busy // capacity
    # drm-resident-<region> is the standard key; amdgpu's older
    # drm-memory-<region> means the same; drm-total- is the last resort.
    regions: dict[str, int] = {}
    for prefix in ("drm-resident-", "drm-memory-", "drm-total-"):
        for key, value in values.items():
            if key.startswith(prefix):
                region = key.removeprefix(prefix)
                size = _size(value)
                if size is not None:
                    regions.setdefault(region, size)
    vram = sum(size for region, size in regions.items() if region.startswith(("vram", "local", "lmem")))
    gtt = sum(size for region, size in regions.items() if region.startswith("gtt"))
    return GpuClient(values.get("drm-client-id", ""), engine, vram, gtt, values.get("drm-pdev", ""))


def _read(path: Path, limit: int = 1 << 20) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            return stream.read(limit)
    except OSError:
        return ""


def _environ(pid: int, proc: Path = PROC) -> dict[str, str]:
    try:
        data = (proc / str(pid) / "environ").read_bytes()
    except OSError:
        return {}
    values: dict[str, str] = {}
    for item in data.split(b"\0"):
        key, separator, value = item.partition(b"=")
        if separator:
            values.setdefault(key.decode("utf-8", "replace"), value.decode("utf-8", "replace"))
    return values


def _gpu_clients(pid: int, proc: Path = PROC) -> list[GpuClient]:
    """The DRM clients a process holds open on a render or card node."""
    clients: list[GpuClient] = []
    fd_dir = proc / str(pid) / "fd"
    try:
        entries = list(os.scandir(fd_dir))
    except OSError:
        return clients
    for entry in entries:
        try:
            target = os.readlink(entry.path)
        except OSError:
            continue
        if not target.startswith("/dev/dri/"):
            continue
        client = parse_fdinfo(_read(proc / str(pid) / "fdinfo" / entry.name, 8192))
        if client is not None:
            clients.append(client)
    return clients


# ----------------------------------------------------------------- Flatpak


def flatpak_instances(runtime_dir: Path | None = None) -> dict[int, str]:
    """PIDs of running Flatpak instances and their application ids.

    Flatpak writes ``$XDG_RUNTIME_DIR/.flatpak/<instance>/`` for each run,
    with or without systemd: ``info`` names the application, ``pid`` is the
    outer bwrap and ``bwrapinfo.json`` the sandboxed child.
    """
    if runtime_dir is None:
        runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    instances: dict[int, str] = {}
    try:
        folders = list((runtime_dir / ".flatpak").iterdir())
    except OSError:
        return instances
    for folder in folders:
        app = ""
        in_application = False
        for line in _read(folder / "info", 65536).splitlines():
            line = line.strip()
            if line.startswith("["):
                in_application = line == "[Application]"
            elif in_application and line.startswith("name="):
                app = line.split("=", 1)[1].strip()
                break
        if not app:
            continue
        pids = []
        try:
            pids.append(int(_read(folder / "pid", 64).strip()))
        except ValueError:
            pass
        try:
            child = json.loads(_read(folder / "bwrapinfo.json", 65536) or "{}").get("child-pid")
            if isinstance(child, int):
                pids.append(child)
        except (ValueError, AttributeError):
            pass
        for pid in pids:
            instances[pid] = app
    return instances


# ------------------------------------------------------------ desktop files


@dataclass
class DesktopEntry:
    name: str
    icon: str
    names: dict[str, str] = field(default_factory=dict)
    visible: bool = True


def desktop_directories(environ=None, home: Path | None = None) -> tuple[Path, ...]:
    """Where .desktop files live: XDG_DATA_HOME first, then XDG_DATA_DIRS,
    then the stores a session may not have listed (Flatpak, Snap, Nix)."""
    environ = os.environ if environ is None else environ
    home = home or Path.home()
    data_home = Path(environ.get("XDG_DATA_HOME") or home / ".local/share")
    data_dirs = [Path(part) for part in (environ.get("XDG_DATA_DIRS") or "/usr/local/share/:/usr/share/").split(":")
                 if part.startswith("/")]
    user = environ.get("USER") or home.name
    extras = [
        data_home / "flatpak/exports/share", Path("/var/lib/flatpak/exports/share"),
        Path("/var/lib/snapd/desktop"), home / ".nix-profile/share",
        Path("/etc/profiles/per-user") / user / "share", Path("/run/current-system/sw/share"),
        Path("/usr/local/share"), Path("/usr/share"),
    ]
    directories: list[Path] = []
    for base in (data_home, *data_dirs, *extras):
        path = base / "applications"
        if path not in directories:
            directories.append(path)
    return tuple(directories)


class DesktopIndex:
    """Application names and icons from .desktop files, refreshed lazily."""

    def __init__(self, directories: tuple[Path, ...] | None = None) -> None:
        self._directories = directories
        self._by_id: dict[str, DesktopEntry] = {}
        self._by_program: dict[str, DesktopEntry] = {}
        self._loaded_at = -_DESKTOP_TTL_SECONDS
        self._lock = threading.Lock()

    def _dirs(self) -> tuple[Path, ...]:
        return self._directories if self._directories is not None else desktop_directories()

    def _load(self) -> None:
        by_id: dict[str, DesktopEntry] = {}
        by_program: dict[str, DesktopEntry] = {}
        seen: set[str] = set()
        for directory in self._dirs():
            try:
                files = sorted(directory.rglob("*.desktop"))
            except OSError:
                continue
            for path in files:
                # The id is the path under applications/, "/" turned to "-";
                # the first directory that has an id owns it, even to hide it.
                desktop_id = str(path.relative_to(directory)).replace("/", "-")[:-len(".desktop")].lower()
                if desktop_id in seen:
                    continue
                seen.add(desktop_id)
                values, names = _desktop_values(_read(path, 65536))
                if not values.get("Name") or values.get("Hidden", "").lower() == "true" \
                        or values.get("Type", "Application") != "Application":
                    continue
                # NoDisplay keeps an entry out of menus; its name still holds.
                entry = DesktopEntry(values["Name"], values.get("Icon", ""), names,
                                     values.get("NoDisplay", "").lower() != "true")
                by_id[desktop_id] = entry
                programs = _exec_programs(values.get("Exec", ""))
                if values.get("TryExec"):
                    programs.append(os.path.basename(values["TryExec"]))
                if values.get("StartupWMClass"):
                    programs.append(values["StartupWMClass"])
                for program in programs:
                    current = by_program.get(program.lower())
                    if current is None or (entry.visible and not current.visible):
                        by_program[program.lower()] = entry
        self._by_id, self._by_program = by_id, by_program

    def _fresh(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now - self._loaded_at >= _DESKTOP_TTL_SECONDS:
                self._load()
                self._loaded_at = now

    def by_id(self, desktop_id: str) -> DesktopEntry | None:
        self._fresh()
        key = desktop_id.lower()
        return self._by_id.get(key) or self._by_id.get(key.rsplit(".", 1)[-1])

    def by_program(self, program: str) -> DesktopEntry | None:
        self._fresh()
        return self._by_program.get(program.lower())


def _desktop_values(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """The [Desktop Entry] group's untranslated keys, and Name[<locale>]."""
    values: dict[str, str] = {}
    names: dict[str, str] = {}
    in_entry = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            in_entry = line == "[Desktop Entry]"
            continue
        if not in_entry or "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key.startswith("Name[") and key.endswith("]"):
            names.setdefault(key[5:-1], value)
        else:
            values.setdefault(key, value)
    return values, names


def localized_name(default: str, names: dict[str, str] | None, language: str) -> str:
    """The desktop entry's name for a language code such as ``es-419``.

    The spec matches lang_COUNTRY@MODIFIER, lang_COUNTRY, lang@MODIFIER,
    then lang; the page's codes have no modifier.
    """
    if not names or not language:
        return default
    code = language.replace("-", "_")
    lang = code.split("_", 1)[0]
    for candidate in (code, lang):
        if candidate in names:
            return names[candidate]
    return default


def _exec_programs(exec_line: str) -> list[str]:
    """Program names an Exec= line starts: the binary, Flatpak's --command."""
    words = [word.strip('"') for word in exec_line.split()]
    words = [word for word in words if word and not word.startswith("%")]
    while words and (words[0] == "env" or "=" in words[0]):
        words.pop(0)
    if not words:
        return []
    programs = [os.path.basename(words[0])]
    for word in words[1:]:
        if word.startswith("--command="):
            programs.append(os.path.basename(word.split("=", 1)[1]))
    return programs


def _script_name(cmdline: list[str]) -> str:
    """What an interpreter runs: the first argument that is not an option."""
    for argument in cmdline[1:]:
        if not argument or argument.startswith("-"):
            continue
        base = os.path.basename(argument.rstrip("/"))
        for suffix in (".py", ".js", ".jar", ".asar", ".exe"):
            base = base.removesuffix(suffix)
        return base
    return ""


def _pretty(name: str) -> str:
    """``gemini-desktop`` -> ``Gemini Desktop``; names with capitals stay."""
    if any(character.isupper() for character in name):
        return name
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", name) if part) or name


def appimage_name(path: str) -> str:
    """``Obsidian-1.5.12-x86_64.AppImage`` -> ``Obsidian``."""
    base = os.path.basename(path)
    if base.lower().endswith(".appimage"):
        base = base[:-len(".appimage")]
    stripped = _APPIMAGE_VERSION.sub("", base)
    return stripped or base


# ------------------------------------------------------------------ games


def _steam_id(value: str) -> int | None:
    """A Steam app or shortcut id from SteamAppId, SteamGameId or AppId=.

    0 means none (Heroic and umu set it so); a 64-bit game id carries a
    shortcut's 32-bit id in its upper half.
    """
    value = value.strip()
    if not value.isdigit():
        return None
    number = int(value)
    if number >= 1 << 32:
        number >>= 32
    return number or None


def heroic_titles(home: Path | None = None) -> dict[str, str]:
    """Heroic's game titles by app name, from its library caches."""
    home = home or Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    titles: dict[str, str] = {}

    def walk(node, depth: int = 0) -> None:
        if depth > 6:
            return
        if isinstance(node, dict):
            app, title = node.get("app_name"), node.get("title")
            if isinstance(app, str) and isinstance(title, str) and title:
                titles.setdefault(app, title)
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for value in node:
                walk(value, depth + 1)

    for root in (config / "heroic", home / ".var/app/com.heroicgameslauncher.hgl/config/heroic"):
        for path in (*sorted((root / "store_cache").glob("*.json")), root / "sideload_apps/library.json"):
            try:
                if path.stat().st_size > 64 << 20:
                    continue
                walk(json.loads(path.read_text(encoding="utf-8", errors="replace")))
            except (OSError, ValueError):
                continue
    return titles


# --------------------------------------------------------------- records


@dataclass
class ProcessRecord(Proceso):
    """One process, with what the Processes page shows about it.

    ``memoria`` is PSS when ``pss`` was measured and RSS otherwise; a page
    summing a group must not mix the two. ``vram`` and ``gtt`` are the GPU
    memory the process holds in each region.
    """

    pid: int = 0
    nombre: str = ""
    memoria: int = 0
    comando: str = ""
    protegido: bool = False
    razon: str = ""
    create_time: float | None = None
    ppid: int = 0
    program: str = ""
    rss: int = 0
    pss: int | None = None
    cpu_percent: float | None = None
    gpu_percent: float | None = None
    vram: int = 0
    gtt: int = 0
    threads: int = 0
    paused: bool = False
    app_key: str = ""
    app_name: str = ""
    app_names: dict = field(default_factory=dict)
    icon: str = ""
    kind: str = "app"
    steam_appid: str = ""

    @property
    def gpu_memory(self) -> int:
        return self.vram + self.gtt


@dataclass
class _Previous:
    cpu: float
    gpu_ns: dict[str, int] = field(default_factory=dict)
    at: float = 0.0


@dataclass
class _Pss:
    value: int | None
    at: float


class ProcessInventory:
    """Samples the user's processes; keeps one sample to compute rates."""

    def __init__(self, *, proc: Path = PROC, desktop: DesktopIndex | None = None,
                 uid: int | None = None, own_pid: int | None = None,
                 clock=time.monotonic, game_names=None, heroic=None,
                 runtime_dir: Path | None = None, timer=time.perf_counter,
                 launchers: frozenset[str] | None = None) -> None:
        self._proc = proc
        self._desktop = desktop or DesktopIndex()
        self._uid = os.getuid() if uid is None else uid
        self._own_pid = os.getpid() if own_pid is None else own_pid
        self._clock = clock
        self._timer = timer
        self._runtime_dir = runtime_dir
        self._launchers = launchers
        self._previous: dict[tuple[int, float], _Previous] = {}
        self._pss: dict[tuple[int, float], _Pss] = {}
        self._environs: dict[tuple[int, float, str], dict[str, str]] = {}
        self._game_names = game_names
        self._game_cache: dict[str, str] = {}
        self._game_cache_at = -_DESKTOP_TTL_SECONDS
        self._heroic = heroic
        self._heroic_cache: dict[str, str] = {}
        self._heroic_at = -_DESKTOP_TTL_SECONDS
        self._cpu_count = max(1, psutil.cpu_count() or 1)
        self._lock = threading.Lock()
        #: systemd-oomd runs: it may end a whole unit (Steam with its
        #: game) whose memory went to swap, a paused game's above all.
        self.oomd_active = False

    # -- game names ---------------------------------------------------------

    def _game_name(self, appid: str) -> str:
        now = self._clock()
        if appid not in self._game_cache and now - self._game_cache_at >= 30.0:
            self._game_cache_at = now
            try:
                if self._game_names is not None:
                    names = dict(self._game_names())
                else:
                    from bc250cc.infrastructure.steam_launch_options import (
                        installed_steam_games,
                        steam_shortcut_names,
                    )

                    names = {str(key): name for key, name in steam_shortcut_names().items()}
                    names.update({game["appid"]: game["name"] for game in installed_steam_games()})
            except Exception:  # a broken library file must not break the page
                names = {}
            self._game_cache.update(names)
        return self._game_cache.get(appid, "")

    def _heroic_title(self, app_name: str) -> str:
        now = self._clock()
        if app_name not in self._heroic_cache and now - self._heroic_at >= 30.0:
            self._heroic_at = now
            try:
                titles = dict(self._heroic()) if self._heroic is not None else heroic_titles()
            except Exception:  # a broken cache file must not break the page
                titles = {}
            self._heroic_cache.update(titles)
        return self._heroic_cache.get(app_name, "")

    # -- sampling -----------------------------------------------------------

    def _own_ancestors(self) -> set[int]:
        """Control Center and the processes it was started from."""
        chain: set[int] = set()
        pid = self._own_pid
        for _ in range(16):
            chain.add(pid)
            try:
                pid = psutil.Process(pid).ppid()
            except (psutil.Error, OSError):
                break
            if pid <= 1:
                break
        return chain

    def sample(self) -> list[ProcessRecord]:
        with self._lock:
            return self._sample()

    def _sample(self) -> list[ProcessRecord]:
        now = self._clock()
        records: list[ProcessRecord] = []
        seen: dict[tuple[int, float], _Previous] = {}
        claimed_clients: set[str] = set()
        own = self._own_ancestors()
        flatpak = flatpak_instances(self._runtime_dir)
        oomd = False
        attrs = ["pid", "ppid", "name", "cmdline", "memory_info", "uids", "create_time",
                 "cpu_times", "num_threads", "status"]
        for process in psutil.process_iter(attrs):
            info = process.info
            try:
                name = str(info.get("name") or "")
                if name == "systemd-oomd":
                    oomd = True
                uids = info.get("uids")
                if uids is None or uids.real != self._uid or info["pid"] in own:
                    continue
                pid = int(info["pid"])
                cmdline = list(info.get("cmdline") or [])
                program = program_name(name, cmdline)
                created = float(info.get("create_time") or 0.0)
                rss = int(info["memory_info"].rss) if info.get("memory_info") else 0
                cpu_times = info.get("cpu_times")
                cpu_total = float(cpu_times.user + cpu_times.system) if cpu_times else 0.0
            except (psutil.Error, OSError, TypeError, ValueError, KeyError):
                continue
            cgroup = read_cgroup(pid, self._proc)
            clients = _gpu_clients(pid, self._proc)
            gpu_ns: dict[str, int] = {}
            vram = gtt = 0
            for client in clients:
                key = client.key if client.client_id else f"{pid}:{len(gpu_ns)}"
                if key in claimed_clients:
                    continue  # one client shared by two fds or a forked child
                claimed_clients.add(key)
                gpu_ns[key] = client.engine_ns
                vram += client.vram
                gtt += client.gtt
            previous = self._previous.get((pid, created))
            cpu_percent = gpu_percent = None
            highs = dict(gpu_ns)
            if previous is not None and now > previous.at:
                elapsed = now - previous.at
                cpu_percent = max(0.0, (cpu_total - previous.cpu) / elapsed * 100 / self._cpu_count)
                if gpu_ns:
                    delta = 0
                    for key, value in gpu_ns.items():
                        before = previous.gpu_ns.get(key)
                        if before is None:
                            continue
                        # The counters may step back; keep the highest seen.
                        delta += max(0, value - before)
                        highs[key] = max(before, value)
                    gpu_percent = min(100.0, delta / (elapsed * 1e9) * 100)
            seen[(pid, created)] = _Previous(cpu_total, highs, now)
            reason = protection_reason(program, cmdline, cgroup)
            record = ProcessRecord(
                pid=pid,
                nombre=name or program,
                memoria=rss,
                comando=" ".join(cmdline) or name,
                protegido=bool(reason),
                razon=reason,
                create_time=created,
                ppid=int(info.get("ppid") or 0),
                program=program,
                rss=rss,
                cpu_percent=cpu_percent,
                gpu_percent=gpu_percent if clients else None,
                vram=vram,
                gtt=gtt,
                threads=int(info.get("num_threads") or 0),
                paused=str(info.get("status") or "") == psutil.STATUS_STOPPED,
            )
            self._identify(record, cgroup, cmdline, flatpak)
            records.append(record)
        self._previous = seen
        self.oomd_active = oomd
        self._group_games(records)
        self._group_tree(records)
        self._measure_pss(records)
        live = {(record.pid, record.create_time or 0.0) for record in records}
        self._environs = {key: value for key, value in self._environs.items() if key[:2] in live}
        return records

    def _measure_pss(self, records: list[ProcessRecord]) -> None:
        """PSS for every process but a game's, refreshed within a budget.

        smaps_rollup walks every mapping under the process's mmap lock, so a
        game that faults memory in while it is read can stutter; a game is
        shown by RSS instead.
        """
        start = self._timer()
        first = not self._pss
        cache: dict[tuple[int, float], _Pss] = {}
        stale: list[tuple[ProcessRecord, _Pss]] = []
        for record in records:
            key = (record.pid, record.create_time or 0.0)
            if record.kind == "game":
                continue
            cached = self._pss.get(key)
            if cached is None:
                cached = _Pss(smaps_pss(_read(self._proc / str(record.pid) / "smaps_rollup", 16384)),
                              self._timer())
            elif self._timer() - cached.at >= PSS_REFRESH_SECONDS:
                stale.append((record, cached))
            cache[key] = cached
        # The oldest readings first, as long as this sample's budget lasts.
        stale.sort(key=lambda item: item[1].at)
        for record, cached in stale:
            if not first and self._timer() - start >= PSS_BUDGET_SECONDS:
                break
            key = (record.pid, record.create_time or 0.0)
            cache[key] = _Pss(smaps_pss(_read(self._proc / str(record.pid) / "smaps_rollup", 16384)),
                              self._timer())
        self._pss = cache
        for record in records:
            measured = cache.get((record.pid, record.create_time or 0.0))
            record.pss = measured.value if measured is not None else None
            record.memoria = record.pss if record.pss is not None else record.rss

    def _environ_of(self, record: ProcessRecord, cmdline: list[str]) -> dict[str, str]:
        key = (record.pid, record.create_time or 0.0, cmdline[0] if cmdline else "")
        values = self._environs.get(key)
        if values is None:
            values = self._environs[key] = _environ(record.pid, self._proc)
        return values

    # -- identity -----------------------------------------------------------

    def _identify(self, record: ProcessRecord, cgroup: str, cmdline: list[str],
                  flatpak: dict[int, str] | None = None) -> None:
        program = record.program
        low = program.lower()
        if record.protegido:
            record.kind = "system"
            record.app_key = f"program:{low}"
            entry = self._desktop.by_program(program)
            self._name(record, entry, program)
            return
        environ = self._environ_of(record, cmdline)
        if self._identify_game(record, environ):
            return
        candidates = scope_candidates(cgroup, self._launchers)
        if not candidates and flatpak and record.pid in flatpak:
            candidates = (flatpak[record.pid],)
        entry = None
        scope = ""
        if candidates and not session_reason(candidates[0].rsplit(".", 1)[-1]):
            # The desktop started it as an application in a unit of its own.
            for candidate in candidates:
                entry = self._desktop.by_id(candidate)
                if entry is not None:
                    scope = candidate
                    break
            scope = scope or candidates[0]
            record.app_key = f"app:{scope.lower()}"
        first = cmdline[0] if cmdline else ""
        image = environ.get("APPIMAGE", "") if ("/.mount_" in first or low == "apprun") else ""
        if image and entry is None:
            # Every process of an AppImage runs from its mount, as AppRun or
            # as the bundled binary; the image file names the application.
            entry = self._desktop.by_program(os.path.basename(image))
            label = appimage_name(image)
            record.app_key = f"appimage:{image.lower()}"
            self._name(record, entry, label, icon=label.lower())
            record.kind = "app"
            return
        if low in INTERPRETERS or low.startswith(("python3.", "electron")):
            script = _script_name(record.comando.split())
            if script:
                entry = entry or self._desktop.by_program(script)
                record.app_key = record.app_key or f"program:{script.lower()}"
                self._name(record, entry, script)
        entry = entry or self._desktop.by_program(program)
        record.app_key = record.app_key or f"program:{low}"
        self._name(record, entry, program)
        # An application has a launcher entry, a desktop scope of its own or
        # GPU memory for its windows; anything else runs in the background.
        unit = cgroup_slice(cgroup)
        if low in BACKGROUND_PROGRAMS or unit == "background" or (
            entry is None and not record.app_key.startswith("app:") and not record.gpu_memory
        ) or (unit == "service" and entry is None):
            record.kind = "background"

    @staticmethod
    def _name(record: ProcessRecord, entry: DesktopEntry | None, fallback: str, *, icon: str = "") -> None:
        if record.app_name:
            return
        record.app_name = entry.name if entry else _pretty(fallback)
        record.app_names = dict(entry.names) if entry else {}
        record.icon = record.icon or (entry.icon if entry and entry.icon else icon or fallback)

    def _identify_game(self, record: ProcessRecord, environ: dict[str, str]) -> bool:
        program = record.program
        low = program.lower()
        exe = low.endswith(".exe") and low not in GAME_HELPER_PROGRAMS
        exe_name = _pretty(program[:-4]) if low.endswith(".exe") else ""
        # Lutris and Heroic start games with their own variables, and set
        # Steam's (SteamAppId=0, SteamGameId=heroic-…) for Proton: never
        # take their games for Steam apps.
        lutris = environ.get("LUTRIS_GAME_UUID") or ""
        if lutris or (environ.get("GAME_NAME") and environ.get("GAME_DIRECTORY")):
            title = environ.get("GAME_NAME") or exe_name or _pretty(program)
            self._game(record, f"lutris:{(lutris or title).lower()}", title, "lutris")
            return True
        heroic = environ.get("HEROIC_APP_NAME") or ""
        if heroic:
            title = self._heroic_title(heroic) or exe_name or _pretty(heroic)
            self._game(record, f"heroic:{heroic.lower()}", title, "heroic")
            return True
        umu = environ.get("UMU_ID") or ""
        if umu or environ.get("GAMEID", "").startswith("umu-"):
            if not (exe or low in GAME_HELPER_PROGRAMS):
                return False
            if exe:
                self._game(record, f"wine:{low}", exe_name, "wine")
            else:
                self._game(record, f"umu:{(umu or environ.get('GAMEID', '')).lower()}",
                           _pretty(umu or program), "wine")
            return True
        steam_like = low in GAME_HELPER_PROGRAMS or low.endswith(".exe") or "steam_app_" in record.comando \
            or "SteamLaunch" in record.comando
        if steam_like:
            match = _STEAM_LAUNCH.search(record.comando)
            appid = _steam_id(match.group(1)) if match else None
            appid = appid or _steam_id(environ.get("SteamAppId", "")) or _steam_id(environ.get("SteamGameId", ""))
            if appid:
                shortcut = appid >= _SHORTCUT_BIT
                name = self._game_name(str(appid))
                if shortcut:
                    self._game(record, f"game:{appid}", name or exe_name or "Non-Steam game", "steam")
                else:
                    self._game(record, f"game:{appid}", name or f"Steam app {appid}", f"steam_icon_{appid}")
                    record.steam_appid = str(appid)
                return True
        if exe:
            # A Windows program outside Steam: a prefix run by hand.
            self._game(record, f"wine:{low}", exe_name, "wine")
            return True
        return False

    @staticmethod
    def _game(record: ProcessRecord, key: str, name: str, icon: str) -> None:
        record.kind, record.app_key, record.app_name, record.icon = "game", key, name, icon

    @staticmethod
    def _group_games(records: list[ProcessRecord]) -> None:
        """A game's Wine server, reaper, container and, for a native Linux
        game, the game binary itself join the game Steam started."""
        by_pid = {record.pid: record for record in records}
        for record in records:
            if record.kind == "game" or record.protegido:
                continue
            parent = by_pid.get(record.ppid)
            for _ in range(12):
                if parent is None or parent.protegido:
                    break
                if parent.kind == "game":
                    record.kind, record.app_key = "game", parent.app_key
                    record.app_name, record.icon = parent.app_name, parent.icon
                    record.app_names = dict(parent.app_names)
                    record.steam_appid = parent.steam_appid
                    break
                parent = by_pid.get(parent.ppid)

    @staticmethod
    def _group_tree(records: list[ProcessRecord]) -> None:
        """Group by the process tree what no desktop unit groups.

        Without application scopes (a compositor's own exec, OpenRC, runit)
        every process sits in the session's cgroup. A process then belongs
        to its topmost ancestor below the compositor, a shell or a launcher:
        Firefox's content processes to Firefox, a Flatpak's children to the
        instance its bwrap was named for.
        """
        by_pid = {record.pid: record for record in records}
        roots: dict[int, ProcessRecord] = {}

        def boundary(record: ProcessRecord) -> bool:
            return record.protegido or record.kind == "game" or record.program.lower() in LAUNCHER_PROGRAMS

        def root(record: ProcessRecord) -> ProcessRecord:
            chain: list[ProcessRecord] = []
            current = top = record
            for _ in range(32):
                if current.pid in roots:
                    top = roots[current.pid]
                    break
                chain.append(current)
                parent = by_pid.get(current.ppid)
                if parent is None or parent is current or boundary(parent):
                    top = current
                    break
                current = parent
            else:
                top = current
            for member in chain:
                roots[member.pid] = top
            return top

        for record in records:
            if boundary(record) or not record.app_key.startswith("program:"):
                continue
            top = root(record)
            if top is record or top.app_key == record.app_key \
                    or not top.app_key.startswith(("program:", "app:", "appimage:")):
                continue
            record.app_key, record.app_name, record.icon = top.app_key, top.app_name, top.icon
            record.app_names, record.kind = dict(top.app_names), top.kind
