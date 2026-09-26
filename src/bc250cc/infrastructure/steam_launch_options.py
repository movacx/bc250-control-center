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
    """Steam installations of this user: native and Flatpak."""
    home = home or Path.home()
    candidates = (
        home / ".local/share/Steam",
        home / ".steam/steam",
        home / ".var/app/com.valvesoftware.Steam/.local/share/Steam",
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
