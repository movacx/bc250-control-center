"""The Processes page's inventory, against a fake /proc.

The page used to match its protected and hidden lists against the whole
command line: every Chromium or Electron app started with
``--ozone-platform=wayland`` counted as the compositor and vanished, and
Spectacle (``--dbus``) as the bus. Identity now comes from the program's own
name, the desktop's application scope and its .desktop file.
"""

from __future__ import annotations

from collections import namedtuple
from pathlib import Path
from types import SimpleNamespace

import pytest

from bc250cc.infrastructure import process_inventory as inventory
from bc250cc.infrastructure.process_inventory import (
    DesktopIndex,
    ProcessInventory,
    appimage_name,
    cgroup_slice,
    desktop_directories,
    flatpak_instances,
    localized_name,
    parse_fdinfo,
    program_name,
    protection_reason,
    scope_application,
    scope_candidates,
    session_reason,
    smaps_pss,
)

Uids = namedtuple("Uids", "real effective saved")
Times = namedtuple("Times", "user system children_user children_system")
Memory = namedtuple("Memory", "rss vms")

UID = 1000


def test_protection_comes_from_the_program_never_from_its_arguments():
    electron = ["/usr/lib/electron44/electron", "--type=renderer", "--ozone-platform=wayland",
                "--enable-features=WaylandWindowDecorations,kaccess"]
    assert program_name("electron", electron) == "electron"
    assert session_reason("electron") == ""
    assert session_reason(program_name("spectacle", ["/usr/bin/spectacle", "--dbus"])) == ""
    # Chromium rewrites argv[0] with its flags in one string.
    assert program_name("claude-desktop", ["/usr/lib/claude-desktop/claude-desktop --type=gpu-process"]) \
        == "claude-desktop"
    for program in ("kwin_wayland", "plasmashell", "Xwayland", "pipewire", "gsd-power", "Hyprland",
                    "xfwm4", "cosmic-panel", "msd-media-keys", "waybar"):
        assert session_reason(program) == "desktop session", program
    for locker in ("kscreenlocker_greet", "hyprlock", "swaylock", "i3lock", "xscreensaver"):
        assert session_reason(locker) == "screen locker", locker
    assert session_reason("zsh") == "shell or terminal"
    assert session_reason("konsole") == "shell or terminal"
    assert session_reason("python3") == "", "a Python application of the user can be closed"


@pytest.mark.parametrize(("cgroup", "expected"), [
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.kde.dolphin@3f2a.service\n",
     "org.kde.dolphin"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-flatpak-com.spotify.Client-1234.scope\n",
     "com.spotify.Client"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-steam@autostart.service\n", "steam"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-gnome-firefox-5512.scope\n", "firefox"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-gnome-org.gnome.Nautilus-4321.scope\n",
     "org.gnome.Nautilus"),
    # Plasma 6 nests main.scope inside the application's scope.
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.kde.dolphin-21641.scope/main.scope\n",
     "org.kde.dolphin"),
    # What runs in a Konsole tab belongs to the command, not to Konsole.
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-org.kde.konsole-100074.scope/"
     "tab(100086).scope\n", ""),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-dbus\\x2d:1.2\\x2dorg.kde.kdeconnect.slice/"
     "dbus-:1.2-org.kde.kdeconnect@0.service\n", "org.kde.kdeconnect"),
    # uwsm: the first XDG_CURRENT_DESKTOP entry, then an 8-hex random part.
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-graphical.slice/"
     "app-Hyprland-firefox-1a2b3c4d.scope\n", "firefox"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-graphical.slice/"
     "app-Hyprland-org.telegram.desktop@1a2b3c4d.service\n", "org.telegram.desktop"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-polychromatic\\x2dautostart@autostart.service\n",
     "polychromatic-autostart"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/snap.firefox.firefox.0c6f9b2a.scope\n",
     "firefox_firefox"),
    ("0::/user.slice/user-1000.slice/user@1000.service/session.slice/plasma-kwin_wayland.service\n", ""),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-io.github.foo\\x2dbar@x.service\n",
     "io.github.foo-bar"),
    ("0::/user.slice/user-1000.slice/session-2.scope\n", ""),
    ("", ""),
])
def test_the_application_scope_names_the_application(cgroup, expected):
    assert scope_application(cgroup) == expected


def test_an_unescaped_id_after_a_launcher_name_is_tried_whole_too():
    cgroup = "0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-gnome-terminal-77.scope\n"
    assert scope_candidates(cgroup, frozenset({"gnome"})) == ("terminal", "gnome-terminal")


@pytest.mark.parametrize(("cgroup", "expected"), [
    ("0::/user.slice/user-1000.slice/user@1000.service/session.slice/plasma-plasmashell.service\n", "session"),
    ("0::/user.slice/user-1000.slice/user@1000.service/session.slice/org.gnome.Shell@wayland.service\n", "session"),
    ("0::/user.slice/user-1000.slice/user@1000.service/session.slice/session-graphical.slice/"
     "wayland-wm@Hyprland.service\n", "session"),
    ("0::/user.slice/user-1000.slice/user@1000.service/background.slice/kde-baloo.service\n", "background"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/dconf.service\n", "service"),
    ("0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-firefox@1.service\n", ""),
    ("0::/user.slice/user-1000.slice/session-2.scope\n", ""),
    ("12:name=systemd:/user.slice/user-1000.slice/user@1000.service/session.slice/pipewire.service\n", "session"),
])
def test_the_slice_says_what_the_session_depends_on(cgroup, expected):
    assert cgroup_slice(cgroup) == expected


def test_gaming_mode_protects_steam_and_its_gamescope_but_not_a_wrapper():
    assert protection_reason("gamescope", ["gamescope", "--xwayland-count", "2", "-R", "/run/x"]) \
        == "game mode session"
    assert protection_reason("gamescope", ["gamescope", "-e", "--", "steam", "-steamos3"]) == "game mode session"
    assert protection_reason("gamescope", ["gamescope", "-W", "1920", "--", "/s/reaper", "SteamLaunch"]) == ""
    assert protection_reason("steam", ["/home/u/.steam/ubuntu12_32/steam", "-gamepadui", "-steamos3"]) \
        == "game mode session"
    assert protection_reason("steam", ["/home/u/.steam/ubuntu12_32/steam", "-gamepadui"]) == "", \
        "Big Picture on the desktop is an application like any other"
    session = "0::/user.slice/user-1000.slice/user@1000.service/session.slice/unknown-helper.service\n"
    assert protection_reason("unknown-helper", ["unknown-helper"], session) == "desktop session"


def test_nixos_wrappers_are_named_after_the_program():
    assert program_name(".firefox-wrapped", ["/nix/store/abc-firefox/bin/.firefox-wrapped"]) == "firefox"
    assert program_name(".firefox-wrappe", []) == "firefox", "comm is cut to 15 bytes"


def test_appimage_files_name_their_application():
    assert appimage_name("/home/u/Apps/Obsidian-1.5.12.AppImage") == "Obsidian"
    assert appimage_name("/opt/LM_Studio-0.3.5-x86_64.AppImage") == "LM_Studio"
    assert appimage_name("nvim.appimage") == "nvim"


def test_pss_and_amdgpu_fdinfo_are_read():
    assert smaps_pss("Rss:  2048 kB\nPss:  1024 kB\nShared_Clean: 0 kB\n") == 1024 * 1024
    assert smaps_pss("") is None
    client = parse_fdinfo(
        "pos:\t0\nflags:\t02100002\ndrm-driver:\tamdgpu\ndrm-client-id:\t42\n"
        "drm-memory-vram:\t123952 KiB\ndrm-memory-gtt: \t84496 KiB\n"
        "drm-engine-gfx:\t436855941 ns\ndrm-engine-compute:\t1000 ns\ndrm-engine-capacity-gfx:\t2\n"
    )
    assert client == inventory.GpuClient("42", 436855941 // 2 + 1000, 123952 * 1024, 84496 * 1024), \
        "each engine's time is divided by its capacity"
    newer = parse_fdinfo("drm-driver:\tamdgpu\ndrm-pdev:\t0000:01:00.0\ndrm-client-id:\t7\n"
                         "drm-resident-vram:\t2 MiB\ndrm-memory-vram:\t9 KiB\ndrm-total-gtt:\t5 MiB\n"
                         "drm-resident-gtt:\t3 MiB\ndrm-resident-cpu:\t1 MiB\n"
                         "drm-engine-gfx:\t100 ns\ndrm-engine-dec:\t5000 ns\ndrm-engine-enc:\t7000 ns\n"
                         "drm-engine-jpeg:\t1 ns\n")
    assert newer.vram == 2 * 1024 * 1024, "the resident figure wins over the legacy one"
    assert newer.gtt == 3 * 1024 * 1024 and newer.engine_ns == 100, "video engines are not rendering"
    assert newer.key == "0000:01:00.0/7", "a client id is unique per device only"
    assert parse_fdinfo("pos:\t0\nflags:\t02\n") is None, "not a DRM file"


def _desktop(tmp_path: Path) -> DesktopIndex:
    applications = tmp_path / "applications"
    applications.mkdir()
    (applications / "com.spotify.Client.desktop").write_text(
        "[Desktop Entry]\nName=Spotify\nIcon=com.spotify.Client\n"
        "Exec=/usr/bin/flatpak run --branch=stable --command=spotify com.spotify.Client\n",
        encoding="utf-8",
    )
    (applications / "org.kde.dolphin.desktop").write_text(
        "[Desktop Entry]\nName=Dolphin\nName[es]=Dolphin\nIcon=system-file-manager\nExec=dolphin %u\n"
        "[Desktop Action new]\nName=New Window\n",
        encoding="utf-8",
    )
    (applications / "gemini-desktop.desktop").write_text(
        "[Desktop Entry]\nName=Gemini\nIcon=gemini-desktop\nExec=env FOO=1 gemini-desktop %U\n",
        encoding="utf-8",
    )
    (applications / "helper.desktop").write_text(
        "[Desktop Entry]\nName=Helper\nNoDisplay=true\nExec=helper\n", encoding="utf-8",
    )
    (applications / "removed.desktop").write_text(
        "[Desktop Entry]\nName=Removed\nHidden=true\nExec=removed\n", encoding="utf-8",
    )
    return DesktopIndex((applications,))


def test_desktop_files_give_names_and_icons(tmp_path):
    index = _desktop(tmp_path)
    assert index.by_id("com.spotify.Client").name == "Spotify"
    assert index.by_program("spotify").icon == "com.spotify.Client", "Flatpak's --command counts"
    assert index.by_program("dolphin").name == "Dolphin"
    assert index.by_program("gemini-desktop").name == "Gemini", "env and variables are skipped"
    assert index.by_program("helper").name == "Helper", "NoDisplay only keeps it out of menus"
    assert index.by_program("removed") is None, "Hidden=true is a deleted entry"
    assert index.by_id("org.kde.dolphin").names == {"es": "Dolphin"}


def test_desktop_files_follow_the_xdg_base_directories(tmp_path):
    home = tmp_path / "home"
    environ = {"XDG_DATA_DIRS": f"{tmp_path}/nix/share:relative/share:/usr/share", "USER": "u"}
    directories = desktop_directories(environ, home)
    assert directories[0] == home / ".local/share/applications"
    assert directories[1] == tmp_path / "nix/share/applications"
    assert Path("relative/share/applications") not in directories, "relative entries are ignored"
    assert Path("/var/lib/snapd/desktop/applications") in directories
    assert Path("/var/lib/flatpak/exports/share/applications") in directories

    user, system = tmp_path / "user/applications", tmp_path / "system/applications"
    (system / "kde4").mkdir(parents=True)
    user.mkdir(parents=True)
    (system / "kde4/okular.desktop").write_text("[Desktop Entry]\nName=Okular\nExec=okular\n", encoding="utf-8")
    (system / "steam.desktop").write_text("[Desktop Entry]\nName=Steam\nName[es]=Steam ES\nExec=steam\n",
                                          encoding="utf-8")
    # A user's Hidden=true entry hides the system one with the same id.
    (user / "steam.desktop").write_text("[Desktop Entry]\nName=Steam\nHidden=true\n", encoding="utf-8")
    index = DesktopIndex((user, system))
    assert index.by_id("kde4-okular").name == "Okular", "the id is the path with / turned to -"
    assert index.by_id("steam") is None and index.by_program("steam") is None
    assert localized_name("Steam", {"es": "Steam ES"}, "es-419") == "Steam ES"
    assert localized_name("Steam", {"pt_BR": "Steam BR", "pt": "Steam PT"}, "pt-BR") == "Steam BR"
    assert localized_name("Steam", {}, "es") == "Steam"


# -- a fake system -------------------------------------------------------------


class FakeProcess:
    def __init__(self, pid, ppid, name, cmdline, *, rss=50 << 20, cpu=1.0, uid=UID, status="sleeping",
                 created=1000.0, threads=4):
        self.pid = pid
        self.info = {
            "pid": pid, "ppid": ppid, "name": name, "cmdline": cmdline,
            "memory_info": Memory(rss, rss * 2), "uids": Uids(uid, uid, uid),
            "create_time": created + pid, "cpu_times": Times(cpu, 0.0, 0.0, 0.0),
            "num_threads": threads, "status": status,
        }


class FakeSystem:
    """psutil.process_iter plus the /proc files the inventory reads."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.processes: list[FakeProcess] = []

    def add(self, process: FakeProcess, *, scope: str = "", pss: int | None = None,
            environ: dict | None = None, gpu: list[tuple[str, int, int]] = (), cgroup: str = "",
            gtt: int = 0) -> FakeProcess:
        base = self.root / str(process.pid)
        (base / "fd").mkdir(parents=True)
        (base / "fdinfo").mkdir()
        cgroup = cgroup or (f"0::/user.slice/user-1000.slice/user@1000.service/app.slice/{scope}\n" if scope else
                            "0::/user.slice/user-1000.slice/session-2.scope\n")
        (base / "cgroup").write_text(cgroup, encoding="utf-8")
        if pss is not None:
            (base / "smaps_rollup").write_text(f"Pss: {pss // 1024} kB\n", encoding="utf-8")
        env = b"\0".join(f"{key}={value}".encode() for key, value in (environ or {}).items())
        (base / "environ").write_bytes(env)
        for index, (client, engine, vram) in enumerate(gpu, start=3):
            (base / "fd" / str(index)).symlink_to("/dev/dri/renderD128")
            (base / "fdinfo" / str(index)).write_text(
                f"drm-driver:\tamdgpu\ndrm-client-id:\t{client}\ndrm-memory-vram:\t{vram // 1024} KiB\n"
                f"drm-memory-gtt:\t{gtt // 1024} KiB\ndrm-engine-gfx:\t{engine} ns\n", encoding="utf-8",
            )
        self.processes.append(process)
        return process

    def set_gpu(self, pid: int, engine: int) -> None:
        for info in (self.root / str(pid) / "fdinfo").iterdir():
            text = info.read_text(encoding="utf-8")
            lines = [line for line in text.splitlines() if not line.startswith("drm-engine-gfx")]
            info.write_text("\n".join(lines) + f"\ndrm-engine-gfx:\t{engine} ns\n", encoding="utf-8")


@pytest.fixture
def system(tmp_path, monkeypatch):
    fake = FakeSystem(tmp_path / "proc")
    fake.root.mkdir()
    monkeypatch.setattr(inventory.psutil, "process_iter", lambda attrs: list(fake.processes))
    monkeypatch.setattr(inventory.psutil, "cpu_count", lambda: 4)
    monkeypatch.setattr(ProcessInventory, "_own_ancestors", lambda self: {self._own_pid})
    fake.desktop = _desktop(tmp_path)
    return fake


def _inventory(system, clock, **kwargs) -> ProcessInventory:
    kwargs.setdefault("runtime_dir", system.root.parent / "run")
    kwargs.setdefault("launchers", inventory.UNIT_LAUNCHERS)
    kwargs.setdefault("heroic", lambda: {"Quail": "Hades"})
    return ProcessInventory(proc=system.root, desktop=system.desktop, uid=UID, own_pid=1, clock=clock,
                            game_names=lambda: {"1091500": "Cyberpunk 2077", str(0xA1B2C3D4): "Witcher 3 GOG"},
                            **kwargs)


def _by_key(records):
    groups: dict[str, list] = {}
    for record in records:
        groups.setdefault(record.app_key, []).append(record)
    return groups


def test_an_electron_app_is_one_application_with_every_helper(system):
    scope = "app-flatpak-com.spotify.Client-4242.scope"
    system.add(FakeProcess(10, 1, "spotify", ["/app/extra/share/spotify/spotify"], rss=180 << 20),
               scope=scope, pss=150 << 20)
    system.add(FakeProcess(11, 10, "spotify", ["/app/extra/share/spotify/spotify", "--type=renderer",
                                               "--ozone-platform=wayland"], rss=330 << 20),
               scope=scope, pss=200 << 20)
    system.add(FakeProcess(12, 10, "spotify", ["/app/extra/share/spotify/spotify", "--type=utility",
                                               "--utility-sub-type=network.mojom.NetworkService", "agent"],
                           rss=4 << 20), scope=scope)
    system.add(FakeProcess(20, 1, "kwin_wayland", ["/usr/bin/kwin_wayland", "--xwayland"]))
    system.add(FakeProcess(30, 1, "spectacle", ["/usr/bin/spectacle", "--dbus"]),
               scope="app-org.kde.spectacle@1.service")
    system.add(FakeProcess(40, 1, "root-thing", ["/usr/bin/root-thing"], uid=0))

    records = _inventory(system, iter([0.0, 3.0]).__next__).sample()
    groups = _by_key(records)

    spotify = groups["app:com.spotify.client"]
    assert [record.pid for record in spotify] == [10, 11, 12], "the small network helper is not dropped"
    assert {record.app_name for record in spotify} == {"Spotify"}
    assert all(not record.protegido and record.kind == "app" for record in spotify)
    assert sum(record.memoria for record in spotify) == (150 << 20) + (200 << 20) + (4 << 20), \
        "PSS where the kernel gives it, RSS otherwise"
    kwin = groups["program:kwin_wayland"][0]
    assert kwin.protegido and kwin.kind == "system" and kwin.razon == "desktop session"
    assert not groups["app:org.kde.spectacle"][0].protegido, "--dbus does not make it the bus"
    assert 40 not in {record.pid for record in records}, "another user's processes are never listed"


def test_cpu_gpu_and_vram_are_measured_between_two_samples(system):
    process = system.add(FakeProcess(50, 1, "game", ["/usr/bin/game"], cpu=10.0),
                         scope="app-game@1.service", gpu=[("9", 1_000_000_000, 512 << 20)])
    system.add(FakeProcess(51, 50, "game", ["/usr/bin/game", "--child"]),
               scope="app-game@1.service", gpu=[("9", 1_000_000_000, 512 << 20)])
    moments = iter([0.0, 2.0])
    sampler = _inventory(system, moments.__next__)

    first = {record.pid: record for record in sampler.sample()}
    assert first[50].cpu_percent is None and first[50].gpu_percent is None, "no rate from one sample"
    assert first[50].vram == 512 << 20 and first[51].vram == 0, "one DRM client is counted once"

    process.info["cpu_times"] = Times(14.0, 0.0, 0.0, 0.0)
    system.set_gpu(50, 2_000_000_000)
    second = {record.pid: record for record in sampler.sample()}

    assert second[50].cpu_percent == pytest.approx(4.0 / 2.0 * 100 / 4), "share of the whole CPU"
    assert second[50].gpu_percent == pytest.approx(50.0)


def test_a_steam_game_gathers_its_proton_processes_under_the_game(system):
    steam = "app-steam@autostart.service"
    system.add(FakeProcess(100, 1, "steam", ["/home/u/.local/share/Steam/ubuntu12_32/steam"]), scope=steam)
    system.add(FakeProcess(101, 100, "reaper", ["/home/u/.local/share/Steam/ubuntu12_32/reaper",
                                                "SteamLaunch", "AppId=1091500", "--", "proton"]), scope=steam)
    system.add(FakeProcess(102, 101, "pv-bwrap", ["pv-bwrap"]), scope=steam)
    system.add(FakeProcess(103, 102, "wineserver", ["wineserver"]), scope=steam)
    system.add(FakeProcess(104, 102, "Cyberpunk2077.e", ["Z:\\games\\Cyberpunk2077.exe"], rss=6 << 30),
               scope=steam, environ={"SteamAppId": "1091500"}, gpu=[("3", 10, 3 << 30)])
    system.add(FakeProcess(110, 1, "Setup.exe", ["C:\\Setup.exe"]), scope="app-lutris@1.service")

    groups = _by_key(_inventory(system, lambda: 0.0).sample())

    game = groups["game:1091500"]
    assert sorted(record.pid for record in game) == [101, 102, 103, 104]
    assert {record.app_name for record in game} == {"Cyberpunk 2077"}
    assert {record.kind for record in game} == {"game"}
    assert groups["app:steam"][0].kind == "app", "Steam itself stays an application"
    assert groups["wine:setup.exe"][0].kind == "game", "a Windows program outside Steam"


def test_the_service_pauses_and_resumes_only_what_it_may_end(monkeypatch):
    from bc250cc.infrastructure import system_service

    signals = []

    class Process:
        def __init__(self, pid):
            self.pid = pid

        def uids(self):
            return Uids(UID, UID, UID)

        def create_time(self):
            return 5.0

        def name(self):
            return {1: "spotify", 2: "kwin_wayland", 3: "electron"}[self.pid]

        def cmdline(self):
            return {1: ["spotify"], 2: ["kwin_wayland"], 3: ["electron", "--ozone-platform=wayland"]}[self.pid]

        def send_signal(self, number):
            signals.append((self.pid, number))

    monkeypatch.setattr(system_service.psutil, "Process", Process)
    service = object.__new__(system_service.SistemaService)
    service.uid, service.pid_actual = UID, 999
    targets = [SimpleNamespace(pid=pid, protegido=False, create_time=5.0) for pid in (1, 2, 3)]

    assert service.pausar_procesos(targets, True) == [1, 3]
    assert service.pausar_procesos(targets[:1], False) == [1]
    assert signals == [(1, system_service.signal.SIGSTOP), (3, system_service.signal.SIGSTOP),
                       (1, system_service.signal.SIGCONT)]
    stale = [SimpleNamespace(pid=1, protegido=False, create_time=4.0)]
    assert service.pausar_procesos(stale, True) == [], "a reused PID is never signalled"


# -- other desktops, init systems and stores ------------------------------------

SESSION = "0::/user.slice/user-1000.slice/session-2.scope\n"


def test_without_application_scopes_the_process_tree_groups_an_application(system):
    """Hyprland without uwsm, or OpenRC: every process sits in the session."""
    system.add(FakeProcess(200, 1, "Hyprland", ["Hyprland"]), cgroup=SESSION)
    system.add(FakeProcess(201, 200, "firefox", ["/usr/lib/firefox/firefox"]), cgroup=SESSION, pss=300 << 20)
    system.add(FakeProcess(202, 201, "Isolated Web Co", ["/usr/lib/firefox/firefox", "-contentproc"]),
               cgroup=SESSION, pss=200 << 20)
    system.add(FakeProcess(203, 201, "crashhelper", ["/usr/lib/firefox/crashhelper"]), cgroup=SESSION, pss=1 << 20)
    system.add(FakeProcess(210, 200, "rofi", ["rofi", "-show", "drun"]), cgroup=SESSION)
    system.add(FakeProcess(211, 210, "gimp", ["/usr/bin/gimp"]), cgroup=SESSION, pss=90 << 20)
    system.add(FakeProcess(220, 200, "kitty", ["kitty"]), cgroup=SESSION)
    system.add(FakeProcess(221, 220, "zsh", ["zsh"]), cgroup=SESSION)
    system.add(FakeProcess(222, 221, "htop", ["htop"]), cgroup=SESSION, pss=4 << 20)

    groups = _by_key(_inventory(system, lambda: 0.0).sample())

    assert sorted(record.pid for record in groups["program:firefox"]) == [201, 202, 203]
    assert [record.pid for record in groups["program:gimp"]] == [211], "a launcher's child is its own app"
    assert [record.pid for record in groups["program:htop"]] == [222], "a command typed in a shell is its own"
    assert groups["program:hyprland"][0].protegido


def test_a_flatpak_without_systemd_is_named_from_its_runtime_directory(system, tmp_path):
    instance = tmp_path / "run/.flatpak/1234567"
    instance.mkdir(parents=True)
    (instance / "info").write_text("[Application]\nname=com.spotify.Client\nruntime=runtime/x\n", encoding="utf-8")
    (instance / "pid").write_text("300\n", encoding="utf-8")
    (instance / "bwrapinfo.json").write_text('{"child-pid": 302}', encoding="utf-8")
    assert flatpak_instances(tmp_path / "run") == {300: "com.spotify.Client", 302: "com.spotify.Client"}

    system.add(FakeProcess(299, 1, "sway", ["sway"]), cgroup=SESSION)
    system.add(FakeProcess(300, 299, "bwrap", ["bwrap", "--args", "42", "spotify"]), cgroup=SESSION)
    system.add(FakeProcess(301, 300, "xdg-dbus-proxy", ["xdg-dbus-proxy"]), cgroup=SESSION)
    system.add(FakeProcess(302, 300, "bwrap", ["bwrap", "--args", "42", "spotify"]), cgroup=SESSION)
    system.add(FakeProcess(303, 302, "spotify", ["/app/extra/share/spotify/spotify"]), cgroup=SESSION)

    groups = _by_key(_inventory(system, lambda: 0.0).sample())
    spotify = groups["app:com.spotify.client"]
    assert sorted(record.pid for record in spotify) == [300, 301, 302, 303], "the outer bwrap belongs to it"
    assert {record.app_name for record in spotify} == {"Spotify"}


def test_an_appimage_is_named_after_its_image(system):
    image = {"APPIMAGE": "/home/u/Apps/Obsidian-1.5.12.AppImage", "APPDIR": "/tmp/.mount_ObsidiXyz"}
    system.add(FakeProcess(400, 1, "AppRun", ["/tmp/.mount_ObsidiXyz/AppRun"]), cgroup=SESSION, environ=image)
    system.add(FakeProcess(401, 400, "obsidian", ["/tmp/.mount_ObsidiXyz/obsidian", "--type=renderer"]),
               cgroup=SESSION, environ=image)

    groups = _by_key(_inventory(system, lambda: 0.0).sample())
    obsidian = groups["appimage:/home/u/apps/obsidian-1.5.12.appimage"]
    assert sorted(record.pid for record in obsidian) == [400, 401]
    assert {record.app_name for record in obsidian} == {"Obsidian"} and obsidian[0].kind == "app"


def test_kde_scopes_and_the_session_slice_classify_without_name_lists(system):
    base = "0::/user.slice/user-1000.slice/user@1000.service/"
    system.add(FakeProcess(500, 1, "dolphin", ["/usr/bin/dolphin"]),
               cgroup=base + "app.slice/app-org.kde.dolphin-500.scope/main.scope\n")
    system.add(FakeProcess(501, 1, "new-shell-thing", ["/usr/bin/new-shell-thing"]),
               cgroup=base + "session.slice/new-shell-thing.service\n")
    system.add(FakeProcess(502, 1, "indexer", ["/usr/bin/indexer"]),
               cgroup=base + "background.slice/indexer.service\n")
    system.add(FakeProcess(503, 1, "openrazer-daemon", ["/usr/bin/openrazer-daemon"]),
               cgroup=base + "app.slice/openrazer-daemon.service\n")

    groups = _by_key(_inventory(system, lambda: 0.0).sample())
    assert groups["app:org.kde.dolphin"][0].app_name == "Dolphin"
    session = groups["program:new-shell-thing"][0]
    assert session.protegido and session.kind == "system", "anything in session.slice is the session's"
    assert groups["program:indexer"][0].kind == "background"
    assert groups["program:openrazer-daemon"][0].kind == "background"


def test_lutris_heroic_and_umu_games_are_never_taken_for_steam(system):
    system.add(FakeProcess(600, 1, "witcher3.exe", ["Z:\\games\\witcher3.exe"]), scope="app-lutris@1.service",
               environ={"GAME_NAME": "The Witcher 3", "GAME_DIRECTORY": "/g/w3", "LUTRIS_GAME_UUID": "u-1",
                        "STORE": "gog", "SteamAppId": "292030", "UMU_ID": "umu-292030"})
    system.add(FakeProcess(610, 1, "Hades.exe", ["Z:\\games\\Hades.exe"]),
               scope="app-com.heroicgameslauncher.hgl-1.scope",
               environ={"HEROIC_APP_NAME": "Quail", "HEROIC_APP_SOURCE": "epic", "SteamAppId": "0",
                        "SteamGameId": "heroic-Quail", "GAMEID": "umu-0"})
    system.add(FakeProcess(620, 1, "Game.exe", ["Z:\\Game.exe"]), cgroup=SESSION,
               environ={"UMU_ID": "umu-1245620", "SteamAppId": "1245620", "GAMEID": "umu-1245620"})

    groups = _by_key(_inventory(system, lambda: 0.0).sample())
    assert groups["lutris:u-1"][0].app_name == "The Witcher 3"
    assert groups["heroic:quail"][0].app_name == "Hades", "Heroic's library names the title"
    assert groups["wine:game.exe"][0].kind == "game" and not groups["wine:game.exe"][0].steam_appid
    assert not any(key.startswith("game:") for key in groups), "no false Steam app"


def test_a_non_steam_shortcut_and_a_native_steam_game_are_named(system):
    steam = "app-steam@autostart.service"
    shortcut = 0xA1B2C3D4
    system.add(FakeProcess(700, 1, "steam", ["/s/ubuntu12_32/steam"]), scope=steam)
    system.add(FakeProcess(701, 700, "reaper", ["/s/reaper", "SteamLaunch", f"AppId={shortcut}", "--", "x"]),
               scope=steam)
    system.add(FakeProcess(702, 701, "witcher3.exe", ["Z:\\w3\\witcher3.exe"]), scope=steam,
               environ={"SteamGameId": str((shortcut << 32) | 0x02000000)})
    system.add(FakeProcess(710, 700, "reaper", ["/s/reaper", "SteamLaunch", "AppId=570", "--", "dota"]),
               scope=steam)
    system.add(FakeProcess(711, 710, "dota2", ["/s/steamapps/common/dota 2 beta/game/bin/linuxsteamrt64/dota2"]),
               scope=steam)

    groups = _by_key(_inventory(system, lambda: 0.0).sample())
    witcher = groups[f"game:{shortcut}"]
    assert sorted(record.pid for record in witcher) == [701, 702]
    assert {record.app_name for record in witcher} == {"Witcher 3 GOG"}
    assert {record.steam_appid for record in witcher} == {""}, "a shortcut is not a store app"
    dota = groups["game:570"]
    assert sorted(record.pid for record in dota) == [710, 711], "a native game joins its reaper"


def test_gpu_memory_counts_gtt_and_a_counter_that_steps_back_is_no_negative_load(system):
    system.add(FakeProcess(800, 1, "game", ["/usr/bin/game"]), scope="app-game@1.service",
               gpu=[("9", 2_000_000_000, 512 << 20)], gtt=3 << 30)
    moments = iter([0.0, 2.0, 4.0])
    sampler = _inventory(system, moments.__next__)
    first = sampler.sample()[0]
    assert first.vram == 512 << 20 and first.gtt == 3 << 30 and first.gpu_memory == (512 << 20) + (3 << 30)
    system.set_gpu(800, 1_000_000_000)
    assert sampler.sample()[0].gpu_percent == 0.0
    system.set_gpu(800, 2_500_000_000)
    assert sampler.sample()[0].gpu_percent == pytest.approx(25.0), "measured from the highest value seen"


def test_pss_is_cached_never_read_for_a_game_and_refreshed_within_a_budget(system, monkeypatch):
    system.add(FakeProcess(900, 1, "kate", ["/usr/bin/kate"], rss=200 << 20), scope="app-kate@1.service",
               pss=120 << 20)
    system.add(FakeProcess(901, 1, "Game.exe", ["Z:\\Game.exe"], rss=6 << 30), cgroup=SESSION, pss=5 << 30)
    system.add(FakeProcess(902, 1, "flatpak-app", ["/app/bin/app"], rss=90 << 20), scope="app-x@1.service")
    reads = []
    original = inventory._read

    def counting(path, limit=1 << 20):
        if path.name == "smaps_rollup":
            reads.append(int(path.parent.name))
        return original(path, limit)

    monkeypatch.setattr(inventory, "_read", counting)
    now = [0.0]
    sampler = _inventory(system, lambda: 0.0, timer=lambda: now[0])
    records = {record.pid: record for record in sampler.sample()}
    assert records[900].memoria == 120 << 20 and records[900].pss == 120 << 20
    assert records[901].pss is None and records[901].memoria == 6 << 30, "a game is shown by RSS"
    assert records[902].pss is None and records[902].memoria == 90 << 20, "denied PSS falls back to RSS"
    assert sorted(reads) == [900, 902]

    reads.clear()
    sampler.sample()
    assert reads == [], "read again only after PSS_REFRESH_SECONDS"
    now[0] = inventory.PSS_REFRESH_SECONDS + 1
    sampler.sample()
    assert sorted(reads) == [900, 902]


def test_systemd_oomd_is_noticed_even_though_it_is_not_the_users(system):
    system.add(FakeProcess(950, 1, "systemd-oomd", ["/usr/lib/systemd/systemd-oomd"], uid=0))
    sampler = _inventory(system, lambda: 0.0)
    assert sampler.sample() == [] and sampler.oomd_active


def test_heroic_titles_are_read_from_its_library_caches(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    cache = tmp_path / ".config/heroic/store_cache"
    cache.mkdir(parents=True)
    (cache / "legendary_library.json").write_text(
        '{"library": [{"app_name": "Quail", "title": "Hades"}, {"app_name": "x"}]}', encoding="utf-8")
    sideload = tmp_path / ".var/app/com.heroicgameslauncher.hgl/config/heroic/sideload_apps"
    sideload.mkdir(parents=True)
    (sideload / "library.json").write_text('{"games": [{"app_name": "abc", "title": "My Game"}]}', encoding="utf-8")
    assert inventory.heroic_titles(tmp_path) == {"Quail": "Hades", "abc": "My Game"}


def test_steam_shortcut_names_come_from_shortcuts_vdf(tmp_path, monkeypatch):
    from bc250cc.infrastructure import steam_launch_options

    def entry(index, appid, name, exe):
        return (b"\x00" + index + b"\x00" + b"\x02appid\x00" + appid.to_bytes(4, "little")
                + b"\x01AppName\x00" + name + b"\x00" + b"\x01Exe\x00" + exe + b"\x00" + b"\x08")

    data = b"\x00shortcuts\x00" + entry(b"0", 0xA1B2C3D4, b"Witcher 3", b'"C:\\w3.exe"') \
        + entry(b"1", 0x80000001, b"", b'"/opt/game/run.sh"') + b"\x08\x08"
    config = tmp_path / "Steam/userdata/1/config"
    config.mkdir(parents=True)
    (config / "shortcuts.vdf").write_bytes(data)
    monkeypatch.setattr(steam_launch_options, "steam_roots", lambda home=None: [tmp_path / "Steam"])
    assert steam_launch_options.steam_shortcut_names(tmp_path) == {0xA1B2C3D4: "Witcher 3", 0x80000001: "run"}


def test_ending_or_pausing_checks_the_session_slice_and_gaming_mode_again(monkeypatch):
    from bc250cc.application.system.process_termination_policy import ProcessIdentity
    from bc250cc.infrastructure import system_service

    cgroups = {
        1: "0::/user.slice/user-1000.slice/user@1000.service/session.slice/odd-shell.service\n",
        2: "0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-steam@x.service\n",
        3: "0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-steam@x.service\n",
        4: "0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-hyprlock@x.service\n",
    }
    monkeypatch.setattr(inventory, "read_cgroup", lambda pid, proc=inventory.PROC: cgroups[pid])
    critical = system_service.SistemaService._critical_identity

    def identity(pid, name, command):
        return ProcessIdentity(pid=pid, create_time=1.0, uid=UID, name=name, command=command)

    assert critical(identity(1, "odd-shell", "/usr/bin/odd-shell"))
    assert critical(identity(2, "steam", "/s/ubuntu12_32/steam -gamepadui -steamos3"))
    assert not critical(identity(3, "steam", "/s/ubuntu12_32/steam"))
    assert critical(identity(4, "hyprlock", "hyprlock")), "a screen locker is never ended or paused"
