"""Read and set a Steam game's launch options, the way Steam stores them.

OptiScaler Client copies OptiScaler into a game as ``dxgi.dll``. Under Proton
that file only loads when Steam passes ``WINEDLLOVERRIDES="dxgi=n,b"`` to the
game, and the client leaves that one step to the user. A newcomer who missed
it saw nothing happen when pressing Insert, with no hint why.

Steam keeps launch options per user in
``userdata/<account>/config/localconfig.vdf``, under
``UserLocalConfigStore/Software/Valve/Steam/apps/<appid>/LaunchOptions``.
Steam rewrites that file when it exits, so it is only edited while Steam is
closed. The edit touches that one value -- or inserts it -- and leaves every
other byte of the file as it was; the previous file is kept beside it.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

APPS_PATH = ("userlocalconfigstore", "software", "valve", "steam", "apps")
STEAM_PROCESSES = frozenset({"steam", "steamwebhelper"})
BACKUP_SUFFIX = ".bc250-backup-"


class SteamConfigError(RuntimeError):
    """The file is not in a shape this module edits safely."""


def steam_roots(home: Path | None = None) -> list[Path]:
    """Steam installations of this user: native, Flatpak and Snap (Ubuntu)."""
    home = home or Path.home()
    candidates = (
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".steam/root",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
        home / "snap/steam/common/.local/share/Steam",
    )
    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (resolved / "userdata").is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


def localconfig_files(home: Path | None = None) -> list[Path]:
    files = []
    for root in steam_roots(home):
        files.extend(sorted((root / "userdata").glob("*/config/localconfig.vdf")))
    return files


def steam_running(proc: Path = Path("/proc")) -> bool:
    try:
        entries = list(proc.iterdir())
    except OSError:
        return False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            name = (entry / "comm").read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if name in STEAM_PROCESSES:
            return True
    return False


# ------------------------------------------------------------------ the format

def _unescape(raw: str) -> str:
    return re.sub(r"\\(.)", lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), raw)


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _tokens(text: str):
    """(kind, start, end, value) for braces and quoted strings."""
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char in " \t\r\n":
            index += 1
        elif text.startswith("//", index):
            newline = text.find("\n", index)
            index = length if newline == -1 else newline + 1
        elif char in "{}":
            yield char, index, index + 1, char
            index += 1
        elif char == '"':
            end = index + 1
            while end < length and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            if end >= length:
                raise SteamConfigError("Steam configuration is malformed: unterminated string")
            yield "str", index, end + 1, _unescape(text[index + 1:end])
            index = end + 1
        else:
            # Unquoted tokens and [$CONDITION] tags exist in some Valve files;
            # localconfig.vdf has none, and nothing here guesses at them.
            raise SteamConfigError(f"Steam configuration is malformed: unexpected {char!r} at offset {index}")


def _locate(text: str, appid: str) -> dict:
    """Where the app's LaunchOptions value, app block and apps block are."""
    app_path = (*APPS_PATH, str(appid).lower())
    found: dict = {}
    stack: list[str] = []
    key: str | None = None
    for kind, start, end, value in _tokens(text):
        if kind == "str":
            if key is None:
                key = value
                continue
            if tuple(stack) == app_path and key.lower() == "launchoptions":
                found["value"] = (start, end, value)
            key = None
        elif kind == "{":
            if key is None:
                raise SteamConfigError("Steam configuration is malformed: a block without a name")
            stack.append(key.lower())
            key = None
            if tuple(stack) == APPS_PATH:
                found["apps_open"] = end
            elif tuple(stack) == app_path:
                found["app_open"] = end
        else:
            if not stack:
                raise SteamConfigError("Steam configuration is malformed: unbalanced braces")
            if tuple(stack) == app_path:
                found["app_close"] = start
            elif tuple(stack) == APPS_PATH:
                found["apps_close"] = start
            stack.pop()
    if stack:
        raise SteamConfigError("Steam configuration is malformed: unbalanced braces")
    return found


def _indent_before(text: str, offset: int) -> str:
    line_start = text.rfind("\n", 0, offset) + 1
    prefix = text[line_start:offset]
    return prefix if not prefix.strip() else ""


def read_all_launch_options(text: str) -> dict[str, str]:
    """Every app's LaunchOptions in one pass: ``{appid: options}``."""
    options: dict[str, str] = {}
    stack: list[str] = []
    key: str | None = None
    depth = len(APPS_PATH)
    for kind, _start, _end, value in _tokens(text):
        if kind == "str":
            if key is None:
                key = value
                continue
            if (len(stack) == depth + 1 and tuple(stack[:depth]) == APPS_PATH
                    and key.lower() == "launchoptions"):
                options[stack[depth]] = value
            key = None
        elif kind == "{":
            if key is None:
                raise SteamConfigError("Steam configuration is malformed: a block without a name")
            stack.append(key.lower())
            key = None
        else:
            if not stack:
                raise SteamConfigError("Steam configuration is malformed: unbalanced braces")
            stack.pop()
    if stack:
        raise SteamConfigError("Steam configuration is malformed: unbalanced braces")
    return options


def read_launch_options(text: str, appid: str) -> str:
    value = _locate(text, appid).get("value")
    return value[2] if value else ""


def set_launch_options(text: str, appid: str, options: str) -> str:
    """The same file with only this app's LaunchOptions changed or added."""
    found = _locate(text, appid)
    if "value" in found:
        start, end, _old = found["value"]
        return text[:start] + _quote(options) + text[end:]
    if "app_open" in found:
        inner = _indent_before(text, found["app_close"]) + "\t"
        line = f"\n{inner}\"LaunchOptions\"\t\t{_quote(options)}"
        return text[:found["app_open"]] + line + text[found["app_open"]:]
    if "apps_open" in found:
        inner = _indent_before(text, found["apps_close"]) + "\t"
        block = (
            f"\n{inner}{_quote(str(appid))}\n{inner}{{\n"
            f"{inner}\t\"LaunchOptions\"\t\t{_quote(options)}\n{inner}}}"
        )
        return text[:found["apps_open"]] + block + text[found["apps_open"]:]
    raise SteamConfigError("this Steam profile has no apps section yet; start the game once from Steam")


# --------------------------------------------------------------- the override

_OVERRIDES = re.compile(r"""WINEDLLOVERRIDES=("([^"]*)"|'([^']*)'|(\S*))""")


def _override_entries(options: str) -> tuple[re.Match | None, list[str]]:
    match = _OVERRIDES.search(options)
    if not match:
        return None, []
    value = next(group for group in match.groups()[1:] if group is not None)
    return match, [part for part in value.split(";") if part.strip()]


def has_dll_override(options: str, dll: str) -> bool:
    """True when the options already load ``dll`` natively (``n`` or ``n,b``)."""
    _match, entries = _override_entries(options)
    for entry in entries:
        names, _, mode = entry.partition("=")
        if dll.lower() in {name.strip().lower() for name in names.split(",")}:
            return mode.strip().lower().startswith("n")
    return False


def merge_dll_override(options: str, dll: str) -> str:
    """Add ``dll=n,b`` and keep everything the user already had.

    ``mangohud %command%`` becomes ``WINEDLLOVERRIDES="dxgi=n,b" mangohud
    %command%``; an existing WINEDLLOVERRIDES gains the entry; game arguments
    without ``%command%`` stay after it.
    """
    options = options.strip()
    if has_dll_override(options, dll):
        return options
    entry = f"{dll}=n,b"
    match, entries = _override_entries(options)
    if match:
        kept = [
            part for part in entries
            if dll.lower() not in {name.strip().lower() for name in part.partition("=")[0].split(",")}
        ]
        merged = f'WINEDLLOVERRIDES="{";".join([*kept, entry])}"'
        return options[:match.start()] + merged + options[match.end():]
    if "%command%" in options:
        return f'WINEDLLOVERRIDES="{entry}" {options}'
    return f'WINEDLLOVERRIDES="{entry}" %command%' + (f" {options}" if options else "")


# ------------------------------------------------------------------ the files

def launch_options_for(appid: str, home: Path | None = None) -> dict[Path, str]:
    """Each Steam profile's current launch options for the app."""
    result = {}
    for path in localconfig_files(home):
        try:
            result[path] = read_launch_options(path.read_text(encoding="utf-8"), appid)
        except (OSError, UnicodeDecodeError, SteamConfigError):
            continue
    return result


def add_dll_override(appid: str, dll: str, *, home: Path | None = None,
                     proc: Path = Path("/proc")) -> dict:
    """Write the override into every Steam profile that knows this game."""
    appid = str(appid).strip()
    if not appid.isdigit():
        raise ValueError("Invalid Steam app id.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", dll):
        raise ValueError("Invalid DLL name.")
    if steam_running(proc):
        raise RuntimeError("Close Steam completely first (Steam > Exit), then try again: Steam rewrites its settings when it closes.")
    files = localconfig_files(home)
    if not files:
        raise RuntimeError("No Steam profile was found in this home folder.")
    known = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
            if "value" in _locate(text, appid) or "app_open" in _locate(text, appid):
                known.append(path)
        except (OSError, UnicodeDecodeError, SteamConfigError):
            continue
    # A game never started has no entry yet: use the profile used last.
    targets = known or [max(files, key=lambda item: item.stat().st_mtime)]
    changed = []
    for path in targets:
        text = path.read_text(encoding="utf-8")
        try:
            before = read_launch_options(text, appid)
            after = merge_dll_override(before, dll)
            if after == before and "value" in _locate(text, appid):
                continue
            updated = set_launch_options(text, appid, after)
            _locate(updated, appid)  # refuse to write anything this module cannot read back
        except SteamConfigError as error:
            raise SteamConfigError(f"{path}: {error}") from error
        backup = path.with_name(path.name + BACKUP_SUFFIX + time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(path, backup)
        temporary = path.with_name(path.name + ".bc250-tmp")
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, path)
        changed.append({"profile": path.parent.parent.name, "before": before,
                        "after": after, "backup": str(backup)})
    return {"appid": appid, "dll": dll, "changed": changed}


# ------------------------------------------------------------ the whole library
#
# Asked for on Reddit (VRRanger): one launch option for every game, so the
# OptiScaler Client only has to copy files into a new game. dxgi=n,b is safe
# where OptiScaler is absent: Proton loads the game's own dxgi.dll when there
# is one and its built-in one otherwise.

#: Steam's own tools also have manifests; launch options mean nothing to them.
_TOOL_PREFIXES = ("proton", "steam linux runtime", "steamworks common")


def _manifest_value(text: str, key: str) -> str:
    match = re.search(rf'"{key}"\s+"([^"]*)"', text, re.IGNORECASE)
    return match.group(1) if match else ""


def steam_libraries(home: Path | None = None) -> list[Path]:
    """Every Steam library of every installation: the root, then the extra
    folders libraryfolders.vdf names (a second drive, /mnt/games, ...)."""
    libraries: list[Path] = []
    for root in steam_roots(home):
        found = [root]
        try:
            folders = (root / "steamapps/libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
            found += [Path(_unescape(path)) for path in re.findall(r'"path"\s+"([^"]+)"', folders)]
        except OSError:
            pass
        for library in found:
            try:
                real = library.resolve()
            except OSError:
                continue
            if real not in libraries:
                libraries.append(real)
    return libraries


def _game_manifests(home: Path | None = None):
    """(library, manifest text) for every app manifest of every Steam library."""
    for library in steam_libraries(home):
        for manifest in sorted((library / "steamapps").glob("appmanifest_*.acf")):
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            appid, name = _manifest_value(text, "appid"), _manifest_value(text, "name")
            if appid.isdigit() and not name.lower().startswith(_TOOL_PREFIXES):
                yield library, appid, name, text


def installed_steam_games(home: Path | None = None) -> list[dict]:
    """Every installed Steam game, from each library's app manifests."""
    games: dict[str, dict] = {}
    for _library, appid, name, _text in _game_manifests(home):
        games.setdefault(appid, {"appid": appid, "name": name})
    return sorted(games.values(), key=lambda game: game["name"].lower())


def installed_steam_game_folders(home: Path | None = None) -> list[dict]:
    """``installed_steam_games`` plus each game's folder under steamapps/common."""
    games: dict[str, dict] = {}
    for library, appid, name, text in _game_manifests(home):
        folder = _unescape(_manifest_value(text, "installdir"))
        if not folder or "/" in folder or folder in {".", ".."}:
            continue
        path = library / "steamapps" / "common" / folder
        if path.is_dir():
            games.setdefault(appid, {"appid": appid, "name": name, "path": path})
    return sorted(games.values(), key=lambda game: game["name"].lower())


def _locate_apps(text: str) -> tuple[dict, dict[str, dict]]:
    """``_locate`` for every app at once: one pass over the file."""
    depth = len(APPS_PATH)
    apps: dict = {}
    per_app: dict[str, dict] = {}
    stack: list[str] = []
    key: str | None = None
    for kind, start, end, value in _tokens(text):
        if kind == "str":
            if key is None:
                key = value
                continue
            if len(stack) == depth + 1 and tuple(stack[:depth]) == APPS_PATH and key.lower() == "launchoptions":
                per_app.setdefault(stack[-1], {})["value"] = (start, end, value)
            key = None
        elif kind == "{":
            if key is None:
                raise SteamConfigError("Steam configuration is malformed: a block without a name")
            stack.append(key.lower())
            key = None
            if tuple(stack) == APPS_PATH:
                apps["open"] = end
            elif len(stack) == depth + 1 and tuple(stack[:depth]) == APPS_PATH:
                per_app.setdefault(stack[-1], {})["open"] = end
        else:
            if not stack:
                raise SteamConfigError("Steam configuration is malformed: unbalanced braces")
            if len(stack) == depth + 1 and tuple(stack[:depth]) == APPS_PATH:
                per_app.setdefault(stack[-1], {})["close"] = start
            elif tuple(stack) == APPS_PATH:
                apps["close"] = start
            stack.pop()
    if stack:
        raise SteamConfigError("Steam configuration is malformed: unbalanced braces")
    return apps, per_app


def _set_many(text: str, wanted: dict[str, str]) -> str:
    """Set several apps' LaunchOptions in one pass, edits applied back to front."""
    apps, per_app = _locate_apps(text)
    if "open" not in apps:
        raise SteamConfigError("this Steam profile has no apps section yet")
    edits: list[tuple[int, int, str]] = []
    new_blocks = []
    inner = _indent_before(text, apps["close"]) + "\t"
    for appid, options in wanted.items():
        found = per_app.get(appid.lower(), {})
        if "value" in found:
            start, end, _old = found["value"]
            edits.append((start, end, _quote(options)))
        elif "open" in found:
            app_inner = _indent_before(text, found["close"]) + "\t"
            edits.append((found["open"], found["open"], f"\n{app_inner}\"LaunchOptions\"\t\t{_quote(options)}"))
        else:
            new_blocks.append(
                f"\n{inner}{_quote(appid)}\n{inner}{{\n"
                f"{inner}\t\"LaunchOptions\"\t\t{_quote(options)}\n{inner}}}"
            )
    if new_blocks:
        edits.append((apps["open"], apps["open"], "".join(new_blocks)))
    for start, end, replacement in sorted(edits, key=lambda edit: edit[0], reverse=True):
        text = text[:start] + replacement + text[end:]
    return text


def add_dll_override_to_library(dll: str = "dxgi", *, home: Path | None = None,
                                proc: Path = Path("/proc")) -> dict:
    """Write ``dll=n,b`` into every installed game of every Steam profile.

    Each profile's file is read once, changed in one pass, read back to check
    every game got exactly what was meant, backed up once and replaced in one
    step: a failure leaves it as it was.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", dll):
        raise ValueError("Invalid DLL name.")
    if steam_running(proc):
        raise RuntimeError("Close Steam completely first (Steam > Exit), then try again: Steam rewrites its settings when it closes.")
    games = installed_steam_games(home)
    if not games:
        raise RuntimeError("No installed Steam game was found.")
    files = localconfig_files(home)
    if not files:
        raise RuntimeError("No Steam profile was found in this home folder.")
    changed_games: set[str] = set()
    already: set[str] = set()
    backups = []
    for path in files:
        try:
            original = path.read_text(encoding="utf-8")
            apps, per_app = _locate_apps(original)
        except (OSError, UnicodeDecodeError, SteamConfigError):
            continue  # a profile this module cannot read is left alone
        if "open" not in apps:
            continue  # a profile that never ran a game
        wanted = {}
        for game in games:
            before = per_app.get(game["appid"], {}).get("value", (0, 0, ""))[2]
            after = merge_dll_override(before, dll)
            if after == before and "value" in per_app.get(game["appid"], {}):
                already.add(game["appid"])
            else:
                wanted[game["appid"]] = after
        if not wanted:
            continue
        updated = _set_many(original, wanted)
        _apps, check = _locate_apps(updated)
        if any(check.get(appid, {}).get("value", (0, 0, None))[2] != options for appid, options in wanted.items()):
            raise SteamConfigError(f"{path}: the change could not be read back; nothing was written")
        backup = path.with_name(path.name + BACKUP_SUFFIX + time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(path, backup)
        temporary = path.with_name(path.name + ".bc250-tmp")
        temporary.write_text(updated, encoding="utf-8")
        os.replace(temporary, path)
        backups.append(str(backup))
        changed_games.update(wanted)
    return {
        "dll": dll,
        "games": len(games),
        "changed": len(changed_games),
        "already": len(already - changed_games),
        "backups": backups,
    }
