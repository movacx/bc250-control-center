"""FSR4 INT8 for BC-250 through the BC250 build of OptiScaler Client.

The project that made FSR4 usable on this board (daniel-h-0/bc250-fsr4-fork)
ships one self-contained Linux application: OptiScaler Client with a BC250
screen that installs OptiScaler plus the optimised FSR 4.1.1 INT8 DLL into each
selected game, keeps a backup of every file it replaces, and restores them on
request. It needs no custom Mesa, no kernel and no root, so the same download
works on Arch, CachyOS, Fedora, Bazzite, Debian/Ubuntu, openSUSE and SteamOS.

What was hard for a newcomer was everything around it: finding the right
archive, extracting it somewhere sensible, starting it from a path the client
could resolve (the failure Old Lamer hit on camera), and knowing the one Steam
launch option it needs. This module does exactly that and nothing more:

* downloads the pinned release and checks it against the published SHA-256,
  then checks every file inside against the archive's own SHA256SUMS;
* refuses an archive with anything outside its single top-level folder;
* installs it under the user's data directory, replacing an older copy only
  after the new one verified, and adds a desktop entry;
* starts it from its own folder, detached from Control Center;
* removes it without touching ``~/.config/OptiscalerClient-BC250``, which holds
  every game's original files and installation records.

Games are patched and restored by the client itself, under its own
transaction and backup rules; Control Center never writes into a game folder.
It does read the client's game list and each game's folder, to say per game
whether OptiScaler is in place and whether Steam still needs the one launch
option that makes Proton load it -- and can add that option for the user (see
``steam_launch_options``).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import subprocess
from pathlib import Path

from .steam_launch_options import (
    SteamConfigError,
    has_dll_override,
    localconfig_files,
    read_launch_options,
)

OPTICLIENT_REPOSITORY = "https://github.com/daniel-h-0/bc250-fsr4-fork"
OPTICLIENT_TAG = "opticlient-v1.0.7-bc250.3"
OPTICLIENT_VERSION = "1.0.7-bc250.3"
OPTICLIENT_TOP = f"bc250-opticlient-{OPTICLIENT_VERSION}-linux-x64"
OPTICLIENT_ARCHIVE = f"{OPTICLIENT_TOP}.tar.gz"
OPTICLIENT_URL = (
    f"{OPTICLIENT_REPOSITORY}/releases/download/{OPTICLIENT_TAG}/{OPTICLIENT_ARCHIVE}"
)
#: Published in the release's SHA256SUMS and in GitHub's asset digest.
OPTICLIENT_SHA256 = "79b076d4524d8ad1a318777df2ec7dbb4066bc9d6a1d276b858b9aad65b58735"
OPTICLIENT_SIZE = 118_819_860
OPTICLIENT_GUIDE = f"{OPTICLIENT_REPOSITORY}/blob/v4/docs/optiscaler-client.md"
OPTICLIENT_LAUNCHER = "Start-BC250-OptiClient.sh"
OPTICLIENT_BINARY = "OptiscalerClient"
OPTICLIENT_MARKER = ".bc250-archive-sha256"
OPTICLIENT_DESKTOP_ID = "io.github.movacx.bc250-control-center.opticlient.desktop"
#: The client's default dxgi.dll adapter. It is the one launch option a
#: Proton game needs; Heroic, Lutris and Bottles take the same value as an
#: environment variable or DLL override.
STEAM_LAUNCH_OPTION = 'WINEDLLOVERRIDES="dxgi=n,b" %command%'


def _desktop_exec(path: Path) -> str:
    """Quote a path the way the Desktop Entry spec wants, not the shell's way."""
    text = str(path)
    if not any(character in text for character in ' "\'`$\\'):
        return text
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in text)
    return f'"{escaped}"'


def _data_home() -> Path:
    configured = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".local" / "share"


def _config_home() -> Path:
    configured = os.environ.get("XDG_CONFIG_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".config"


def opticlient_root() -> Path:
    return _data_home() / "bc250-control-center" / "opticlient"


def opticlient_directory() -> Path:
    return opticlient_root() / OPTICLIENT_VERSION


def opticlient_records() -> Path:
    """The client's own data: selected DLL, per-game records and backups."""
    return _config_home() / "OptiscalerClient-BC250"


def _running() -> bool:
    try:
        result = subprocess.run(
            ("pgrep", "-x", OPTICLIENT_BINARY),
            check=False, capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


#: Names OptiScaler loads under, beside the game executable (upstream list).
OPTISCALER_ADAPTERS = (
    "dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "d3d12.dll",
    "wininet.dll", "winhttp.dll", "dinput8.dll",
)
_NOT_THE_GAME = re.compile(
    r"crash|report|launcher|unrealcef|epicwebhelper|redist|setup|unins|"
    r"easyanticheat|battleye|dxsetup|prereq",
    re.IGNORECASE,
)


def _game_executables(install: Path) -> list[Path]:
    """The real game executables, Unreal's <Project>/Binaries/Win64 first.

    Unreal games also ship a small bootstrap .exe at the top of the folder;
    OptiScaler has to sit beside the one in Binaries/Win64 instead.
    """
    found: list[Path] = []
    for pattern in ("*/Binaries/Win64/*.exe", "*/*/Binaries/Win64/*.exe", "*.exe",
                    "bin/*.exe", "bin/x64/*.exe", "Bin/Win64*/*.exe", "x64/*.exe"):
        try:
            matches = sorted(install.glob(pattern))
        except OSError:
            continue
        for exe in matches:
            if exe.is_file() and not _NOT_THE_GAME.search(exe.name) and exe not in found:
                found.append(exe)
    return found


def _adapter_in(directory: Path) -> str:
    if not (directory / "OptiScaler.ini").is_file():
        return ""
    for name in OPTISCALER_ADAPTERS:
        if (directory / name).is_file():
            return name
    return "unknown"


def opticlient_games(*, home: Path | None = None) -> list[dict]:
    """Per game from the client's list: is OptiScaler in place, and does it load?

    Read-only. ``state`` is ``not-installed`` (no OptiScaler beside any game
    executable), ``needs-launch-option`` (Steam game without the override for
    its adapter), ``ready``, ``other-launcher`` (the loading option belongs
    in Heroic/Lutris/Bottles) or ``unknown-adapter``.
    """
    try:
        records = json.loads((opticlient_records() / "games.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    configs: dict[Path, str] = {}
    for path in localconfig_files(home):
        try:
            configs[path] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    games = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or record.get("IsHidden"):
            continue
        name = str(record.get("Name") or "").strip()
        install = Path(str(record.get("InstallPath") or ""))
        if not name or not str(install) or not install.is_dir():
            continue
        appid = str(record.get("AppId") or "").strip()
        steam = appid.isdigit() and "steamapps" in install.parts
        executable = str(record.get("ExecutablePath") or "").strip()
        candidates = _game_executables(install)
        directories = [Path(executable).parent] if executable else []
        directories += [exe.parent for exe in candidates if exe.parent not in directories]
        adapter, location = "", None
        for directory in directories:
            adapter = _adapter_in(directory)
            if adapter:
                location = directory
                break
        if not adapter and not record.get("HasUpscaler", True):
            continue  # nothing for OptiScaler to take over in this game
        suggested = candidates[0] if candidates else None
        entry = {
            "name": name,
            "appid": appid,
            "steam": steam,
            "adapter": adapter,
            "location": _relative(location, install),
            "suggested_executable": _relative(suggested, install),
            "launch_options": "",
        }
        if not adapter:
            entry["state"] = "not-installed"
        elif adapter == "unknown":
            entry["state"] = "unknown-adapter"
        elif steam:
            values = []
            for text in configs.values():
                try:
                    values.append(read_launch_options(text, appid))
                except SteamConfigError:
                    continue
            dll = adapter.removesuffix(".dll")
            entry["launch_options"] = next((value for value in values if value), "")
            entry["state"] = (
                "ready" if any(has_dll_override(value, dll) for value in values)
                else "needs-launch-option"
            )
        else:
            entry["state"] = "other-launcher"
        games.append(entry)
    return games


def _relative(path: Path | None, root: Path) -> str:
    if path is None:
        return ""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def opticlient_state(*, machine: str | None = None) -> dict:
    """Read-only: what is installed, and whether it is the pinned release."""
    directory = opticlient_directory()
    launcher = directory / OPTICLIENT_LAUNCHER
    binary = directory / OPTICLIENT_BINARY
    try:
        marker = (directory / OPTICLIENT_MARKER).read_text(encoding="ascii").strip()
    except OSError:
        marker = ""
    files_present = launcher.is_file() and binary.is_file()
    installed = directory.exists()
    current = bool(files_present and marker == OPTICLIENT_SHA256)
    try:
        others = sorted(
            entry.name for entry in opticlient_root().iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
            and entry.name != OPTICLIENT_VERSION
        )
    except OSError:
        others = []
    from bc250cc.infrastructure.bc250_fsr4 import BC250_FSR4_PREFIX

    supported = (machine or platform.machine()) in {"x86_64", "amd64", "AMD64"}
    if current:
        state = "ready"
    elif installed:
        state = "invalid"
    elif others:
        state = "update-available"
    else:
        state = "not-installed"
    return {
        "provider": "opticlient",
        "version": OPTICLIENT_VERSION,
        "repository": OPTICLIENT_REPOSITORY,
        "guide": OPTICLIENT_GUIDE,
        "supported": supported,
        "installer_available": supported,
        "installed": installed,
        "current": current,
        "state": state,
        "path": str(directory),
        "launcher": str(launcher),
        "other_versions": others,
        "records": opticlient_records().is_dir(),
        "running": _running() if current else False,
        "legacy_v3_installed": BC250_FSR4_PREFIX.exists(),
        "steam_launch_option": STEAM_LAUNCH_OPTION,
        "games": opticlient_games() if current else [],
    }


def build_opticlient_install_command() -> str:
    """User-space install or update of the pinned client. No sudo anywhere."""
    root = shlex.quote(str(opticlient_root()))
    target = shlex.quote(str(opticlient_directory()))
    applications = shlex.quote(str(_data_home() / "applications"))
    desktop = shlex.quote(str(_data_home() / "applications" / OPTICLIENT_DESKTOP_ID))
    return f'''set -Eeuo pipefail
echo "== FSR4 INT8 for BC-250 · OptiScaler Client {OPTICLIENT_VERSION} =="
echo "Source: {OPTICLIENT_REPOSITORY} ({OPTICLIENT_TAG})"
test "$(uname -m)" = x86_64 || {{ echo "ERROR: the client is built for x86_64 Linux."; exit 64; }}
for bc250_command in tar sha256sum mktemp; do
  command -v "$bc250_command" >/dev/null 2>&1 || {{ echo "ERROR: $bc250_command is required."; exit 69; }}
done
if command -v curl >/dev/null 2>&1; then
  bc250_fetch() {{ curl -fL --retry 3 --connect-timeout 20 --progress-bar -o "$1" "$2"; }}
elif command -v wget >/dev/null 2>&1; then
  bc250_fetch() {{ wget -q --show-progress -O "$1" "$2"; }}
else
  echo "ERROR: curl or wget is required to download the client."; exit 69
fi
bc250_work="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-opticlient.XXXXXX")"
trap 'rm -rf -- "$bc250_work"' EXIT
bc250_archive="$bc250_work/{OPTICLIENT_ARCHIVE}"
echo "Downloading {OPTICLIENT_ARCHIVE} ({OPTICLIENT_SIZE // 1_000_000} MB)..."
bc250_fetch "$bc250_archive" {shlex.quote(OPTICLIENT_URL)}
echo "Checking the published SHA-256..."
printf '%s  %s\\n' {OPTICLIENT_SHA256} "$bc250_archive" | sha256sum -c -
echo "Checking the archive layout..."
while IFS= read -r bc250_entry; do
  case "$bc250_entry" in
    {OPTICLIENT_TOP}|{OPTICLIENT_TOP}/*) ;;
    *) echo "ERROR: unexpected archive entry: $bc250_entry"; exit 29 ;;
  esac
  case "/$bc250_entry/" in
    */../*) echo "ERROR: unsafe archive path: $bc250_entry"; exit 29 ;;
  esac
done < <(tar -tzf "$bc250_archive")
tar -xzf "$bc250_archive" -C "$bc250_work" --no-same-owner
bc250_stage="$bc250_work/{OPTICLIENT_TOP}"
echo "Checking every file against the client's own SHA256SUMS..."
( cd "$bc250_stage" && sha256sum --quiet -c SHA256SUMS )
test -x "$bc250_stage/{OPTICLIENT_BINARY}" -a -x "$bc250_stage/{OPTICLIENT_LAUNCHER}" || {{
  echo "ERROR: the client launcher is missing from the archive."; exit 29; }}
if command -v ldd >/dev/null 2>&1 && ldd "$bc250_stage/{OPTICLIENT_BINARY}" 2>/dev/null | grep -q 'not found'; then
  echo "ERROR: the client needs system libraries that are not installed:"
  ldd "$bc250_stage/{OPTICLIENT_BINARY}" | grep 'not found' || true
  echo "Install them with your package manager (usually fontconfig, libX11 and libICU), then retry."
  exit 69
fi
printf '%s\\n' {OPTICLIENT_SHA256} > "$bc250_stage/{OPTICLIENT_MARKER}"
mkdir -p {root}
if test -L {target}; then echo "ERROR: refusing to replace a symlink at {target}."; exit 29; fi
bc250_previous=""
if test -e {target}; then
  bc250_previous="$(mktemp -d {root}/.previous.XXXXXX)"
  rmdir "$bc250_previous"
  mv -- {target} "$bc250_previous"
fi
mv -- "$bc250_stage" {target}
test -z "$bc250_previous" || rm -rf -- "$bc250_previous"
for bc250_old in {root}/*; do
  test -d "$bc250_old" || continue
  test "$bc250_old" = {target} && continue
  echo "Removing the older client copy $(basename "$bc250_old")."
  rm -rf -- "$bc250_old"
done
mkdir -p {applications}
cat > {desktop} <<'BC250_DESKTOP'
[Desktop Entry]
Type=Application
Name=OptiScaler Client (BC250 FSR4)
Comment=Install FSR4 INT8 into your games with OptiScaler
Exec={_desktop_exec(opticlient_directory() / OPTICLIENT_LAUNCHER)}
Path={opticlient_directory()}
Icon=io.github.movacx.bc250-control-center
Terminal=false
Categories=Game;Utility;
BC250_DESKTOP
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database {applications} >/dev/null 2>&1 || true
echo
echo "OK: OptiScaler Client {OPTICLIENT_VERSION} is installed in {opticlient_directory()}."
echo "Next: press Open OptiScaler Client, choose Scan Games, select your games and Install / update selected."
echo "Steam launch option for each new game:"
printf '%s\\n' {shlex.quote(STEAM_LAUNCH_OPTION)}
'''


def build_opticlient_remove_command() -> str:
    """Remove the client program; never its records or the games' backups."""
    root = shlex.quote(str(opticlient_root()))
    desktop = shlex.quote(str(_data_home() / "applications" / OPTICLIENT_DESKTOP_ID))
    records = shlex.quote(str(opticlient_records()))
    return f'''set -Eeuo pipefail
echo "== Removing OptiScaler Client (BC250 FSR4) =="
if pgrep -x {OPTICLIENT_BINARY} >/dev/null 2>&1; then
  echo "ERROR: close OptiScaler Client first."; exit 75
fi
rm -rf -- {root}
rm -f -- {desktop}
echo "OK: the client program was removed."
if test -d {records}; then
  echo "Kept {opticlient_records()}: it holds the original files of every game the client patched."
  echo "Reinstalling the client later lets you Restore / recover those games."
fi
'''


def launch_opticlient() -> dict:
    """Start the verified client from its own folder, detached from this app."""
    state = opticlient_state()
    if not state["current"]:
        raise RuntimeError("Install OptiScaler Client first.")
    launcher = Path(state["launcher"])
    environment = {
        key: value for key, value in os.environ.items()
        if key not in {"PYTHONPATH", "PYTHONHOME", "QT_PLUGIN_PATH"}
    }
    subprocess.Popen(  # noqa: S603 - fixed, verified launcher path
        [str(launcher)],
        cwd=str(launcher.parent),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"launched": True, "path": str(launcher.parent)}
