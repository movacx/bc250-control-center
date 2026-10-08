"""HelixSR: DLSS Model E reconstruction behind an FSR 3.1 DLL, per game.

HelixSR (lonewolf0622/HelixSR) is a drop-in replacement for a game's AMD
FidelityFX upscaler DLL. The game keeps talking to FSR 3.1; HelixSR runs
NVIDIA's DLSS Model E network as plain Direct3D 12 compute shaders, which
Proton/vkd3d-proton run on the BC-250 (it was developed on one).

Its licence shapes everything this module does:

* the release is never bundled: the pinned official archive is downloaded on
  the user's PC and checked against the SHA-256 recorded here, then installed
  unmodified under the user's data folder;
* the network files (``helixsr_weights.bin`` and ``helixsr_kernels.pak``)
  hold NVIDIA's network and must never leave the PC. HelixSR's own setup
  builds them locally from NVIDIA's DLSS DLL, after asking in the terminal;
  this module only copies them next to a game's DLL on the same PC;
* the setup's optional ``sudo`` package install is never reached: with numpy
  missing, the setup is told to use its portable Python instead.

Per game, HelixSR replaces the game's ``amd_fidelityfx_upscaler_dx12.dll`` or
``amd_fidelityfx_dx12.dll`` and keeps the original as ``*.original.dll``, as
upstream's README describes. Each change is recorded so it can be undone, and
removal puts the game's own file back.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shlex
import shutil
import sys
import time
from pathlib import Path

from .steam_launch_options import installed_steam_game_folders

HELIXSR_REPOSITORY = "https://github.com/lonewolf0622/HelixSR"
HELIXSR_TAG = "v1.2.0"
HELIXSR_VERSION = "1.2.0"
HELIXSR_TOP = f"HelixSR-{HELIXSR_VERSION}"
HELIXSR_ARCHIVE = f"{HELIXSR_TOP}.zip"
HELIXSR_URL = f"{HELIXSR_REPOSITORY}/releases/download/{HELIXSR_TAG}/{HELIXSR_ARCHIVE}"
#: SHA-256 of the official v1.2.0 release archive, reviewed for this release.
HELIXSR_SHA256 = "7c9aeac2e3dcd73f6e9b2dd8b04c41a828fd8e1a8fe30a2ac77787097ddbeb0e"
HELIXSR_SIZE = 2_315_352
#: SHA-256 of ``amd_fidelityfx_dx12.dll`` inside that archive. A game file
#: with this digest is HelixSR; anything else is the game's own.
HELIXSR_DLL_SHA256 = "745477ee77c5cccd2de4bd251fc950d33895387f411815e889625fbbdc12a7e4"
#: Every reviewed HelixSR DLL. A game keeps the copy it was given when the
#: release here is updated; it is still HelixSR and still removable.
HELIXSR_DLL_DIGESTS = frozenset({HELIXSR_DLL_SHA256})
HELIXSR_DLL = "amd_fidelityfx_dx12.dll"
HELIXSR_SETUP = "helixsr-setup.sh"
HELIXSR_MARKER = ".bc250-archive-sha256"
HELIXSR_NETWORK_FILES = ("helixsr_weights.bin", "helixsr_kernels.pak")
HELIXSR_LOG = "helixsr.log"
HELIXSR_LICENSE = f"{HELIXSR_REPOSITORY}/blob/main/LICENSE"
DLSS_LICENSE = "https://github.com/NVIDIA/DLSS/blob/v310.7.0/LICENSE.txt"
#: NVIDIA's nvngx_dlss.dll 310.7.0, the one HelixSR's setup builds from
#: (DLSS_SHA256 in its helixsr_setup.py). OptiScaler Client pins the same file.
DLSS_DLL_SHA256 = "be6e434a94ca32499515eb62ca0e6c274526055d568d0426e4c652dcdfb6ee6e"

#: The FSR 3.1 DLLs HelixSR stands in for. In a folder that has both, the
#: upscaler DLL is the one replaced.
UPSCALER_DLL = "amd_fidelityfx_upscaler_dx12.dll"
LOADER_DLL = "amd_fidelityfx_dx12.dll"
_FSR_DLLS = (UPSCALER_DLL, LOADER_DLL)

#: A game folder is walked this deep and this wide, no further: Unreal games
#: keep the DLL six or seven folders down, and nothing needs more.
_SCAN_DEPTH = 10
_SCAN_ENTRY_LIMIT = 200_000


def _data_home() -> Path:
    configured = os.environ.get("XDG_DATA_HOME", "").strip()
    return Path(configured) if configured else Path.home() / ".local" / "share"


def helixsr_root() -> Path:
    return _data_home() / "bc250-control-center" / "helixsr"


def helixsr_directory() -> Path:
    return helixsr_root() / HELIXSR_VERSION


def helixsr_cache() -> Path:
    """Upstream's own cache: portable Python, numpy and the shader compiler."""
    return _data_home() / "HelixSR"


def _records_path() -> Path:
    return helixsr_root() / "games.json"


def _scan_path() -> Path:
    return helixsr_root() / "scan.json"


def _folders_path() -> Path:
    """Game folders the user added by hand: games Steam does not know."""
    return helixsr_root() / "folders.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_helixsr(path: Path, digests: frozenset[str] | None = None) -> bool:
    known = HELIXSR_DLL_DIGESTS if digests is None else digests
    try:
        return path.is_file() and not path.is_symlink() and _sha256(path) in known
    except OSError:
        return False


def _backup_for(path: Path) -> Path:
    """``x.dll`` -> ``x.original.dll``, the name upstream's README uses."""
    return path.with_name(f"{path.stem}.original{path.suffix}")


def _wine_candidates(home: Path) -> list[Path]:
    """The Proton/Wine builds upstream's setup looks for, in its order."""
    found: list[Path] = []
    for pattern in (
        ".local/share/Steam/steamapps/common/Proton*/files/bin/wine",
        ".steam/steam/steamapps/common/Proton*/files/bin/wine",
        ".local/share/Steam/compatibilitytools.d/*/files/bin/wine",
        ".steam/root/compatibilitytools.d/*/files/bin/wine",
    ):
        try:
            found.extend(sorted(home.glob(pattern)))
        except OSError:
            continue
    return found


def wine_available(home: Path | None = None) -> bool:
    """Whether the setup can run its shader compiler (Proton or Wine)."""
    if any(os.access(path, os.X_OK) for path in _wine_candidates(home or Path.home())):
        return True
    return shutil.which("wine") is not None


# ---------------------------------------------------------------- records


def _read_json(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _records() -> dict[str, dict]:
    records = _read_json(_records_path(), {})
    return {
        str(appid): record for appid, record in records.items()
        if isinstance(record, dict) and isinstance(record.get("files"), list)
    }


def _record_state(record: dict) -> str:
    """``installed``: HelixSR is in place; ``restored``: the game put its own
    file back (an update or a file check), so only the backup is left."""
    files = [Path(str(entry.get("path") or "")) for entry in record.get("files") or ()]
    if files and all(_is_helixsr(path) for path in files):
        return "installed"
    return "restored"


# ---------------------------------------------------------------- scanning


def _fsr_folders(install: Path) -> list[Path]:
    """Every file HelixSR should replace in a game: one per folder.

    A folder with the FSR 3.1 upscaler DLL gets that one replaced; a folder
    with only the loader DLL gets the loader. Links are never followed.
    """
    targets: list[Path] = []
    seen = 0
    stack: list[tuple[Path, int]] = [(install, 0)]
    while stack:
        folder, depth = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        names: dict[str, Path] = {}
        for entry in entries:
            seen += 1
            if seen > _SCAN_ENTRY_LIMIT:
                return sorted(targets)
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < _SCAN_DEPTH:
                        stack.append((Path(entry.path), depth + 1))
                elif entry.name.lower() in _FSR_DLLS:
                    names[entry.name.lower()] = Path(entry.path)
            except OSError:
                continue
        for wanted in _FSR_DLLS:
            if wanted in names:
                targets.append(names[wanted])
                break
    return sorted(targets)


def scan_helixsr_games(*, home: Path | None = None) -> list[dict]:
    """Installed Steam games that ship an FSR 3.1 DLL. Read-only; cached."""
    games = []
    for game in installed_steam_game_folders(home):
        targets = _fsr_folders(Path(game["path"]))
        if targets:
            games.append({
                "appid": game["appid"],
                "name": game["name"],
                "path": str(game["path"]),
                "files": [str(path) for path in targets],
            })
    try:
        _write_json(_scan_path(), {"time": int(time.time()), "games": games})
    except OSError:
        pass
    return games


# ---------------------------------------------------------------- folders
#
# Games outside Steam (GOG, Epic through Heroic, Lutris, a folder copied by
# hand) have no app manifest to find them by. The user picks the game's
# folder instead; it is searched exactly like a Steam game's, and from then
# on the game is a row like any other, with the same install, backup and
# removal. Its id is "folder-" and a digest of the path, so it can never
# collide with a Steam app id.

FOLDER_PREFIX = "folder-"


def _folder_id(path: Path) -> str:
    return FOLDER_PREFIX + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]


def _folders() -> dict[str, dict]:
    folders = _read_json(_folders_path(), {})
    return {
        str(key): value for key, value in folders.items()
        if str(key).startswith(FOLDER_PREFIX) and isinstance(value, dict) and value.get("path")
    }


def add_helixsr_folder(path: str) -> dict:
    """Add a game folder from outside Steam, if it ships an FSR 3.1 DLL."""
    text = str(path or "").strip()
    if not text:
        raise ValueError("Choose the game's folder.")
    folder = Path(text).expanduser()
    if not folder.is_absolute() or not folder.is_dir():
        raise RuntimeError("That folder does not exist.")
    folder = folder.resolve()
    # The search stops after a fixed number of entries, so a whole drive or
    # home folder would end half searched: the game's own folder is wanted.
    if folder == Path(folder.anchor) or folder == Path.home().resolve():
        raise RuntimeError("Choose the game's own folder, not a whole drive or your home folder.")
    targets = _fsr_folders(folder)
    if not targets:
        raise RuntimeError("No FSR 3.1 DLL was found in this game. HelixSR replaces amd_fidelityfx_upscaler_dx12.dll or amd_fidelityfx_dx12.dll.")
    key = _folder_id(folder)
    folders = _folders()
    folders[key] = {"name": folder.name, "path": str(folder), "files": [str(t) for t in targets]}
    _write_json(_folders_path(), folders)
    return {"game": folder.name, "id": key, "files": [str(t) for t in targets]}


def forget_helixsr_folder(key: str) -> dict:
    """Take a folder off the list; HelixSR must not be in it any more."""
    key = str(key or "").strip()
    folders = _folders()
    if key not in folders:
        raise RuntimeError("This folder is not on the list.")
    if key in _records():
        raise RuntimeError("Remove HelixSR from this game first, so it gets its own FSR file back.")
    entry = folders.pop(key)
    _write_json(_folders_path(), folders)
    return {"game": str(entry.get("name") or key)}


def helixsr_games(*, optiscaler: bool = True) -> list[dict]:
    """One row per game: recorded installs first, then the last scan's finds.

    ``optiscaler`` also offers the games where OptiScaler is in place; the
    ones already routed to HelixSR are listed either way.
    """
    records = _records()
    rows: list[dict] = []
    for appid, record in records.items():
        rows.append({
            "appid": appid,
            "kind": "game",
            "name": str(record.get("name") or appid),
            "state": _record_state(record),
            "files": [str(entry.get("path") or "") for entry in record["files"]],
        })
    scan = _read_json(_scan_path(), {})
    for game in scan.get("games") or ():
        if not isinstance(game, dict):
            continue
        appid = str(game.get("appid") or "")
        if not appid or appid in records:
            continue
        files = [str(path) for path in game.get("files") or () if Path(str(path)).is_file()]
        if not files:
            continue
        rows.append({
            "appid": appid,
            "kind": "game",
            "name": str(game.get("name") or appid),
            "state": "available",
            "files": files,
        })
    for key, entry in _folders().items():
        if key in records:
            continue
        files = [str(path) for path in entry.get("files") or () if Path(str(path)).is_file()]
        if not files:
            continue
        rows.append({
            "appid": key,
            "kind": "game",
            "name": str(entry.get("name") or key),
            "state": "available",
            "files": files,
            "folder": str(entry.get("path") or ""),
        })
    rows.extend(optiscaler_rows(available=optiscaler))
    order = {"installed": 0, "restored": 1, "available": 2}
    return sorted(rows, key=lambda row: (order[row["state"]], row["name"].lower(), row["kind"]))


# ---------------------------------------------------------------- OptiScaler
#
# OptiScaler (installed per game by the FSR4 card's OptiScaler Client) can hand
# a game's DLSS, XeSS or FSR input to any FidelityFX upscaler DLL. Pointing it
# at HelixSR, as upstream's README describes, brings HelixSR to games that do
# not ship FSR 3.1. HelixSR goes into a folder of its own beside OptiScaler and
# OptiScaler.ini names it; nothing of OptiScaler or of the game is replaced.
#
# OptiScaler Client records the digest of every file it installed, the .ini
# included, and refuses to update or restore a game whose files changed. So
# the .ini is saved byte for byte first and put back byte for byte on removal,
# which leaves the client's records valid again.

OPTISCALER_INI = "OptiScaler.ini"
OPTISCALER_FOLDER = "HelixSR"
#: The name HelixSR's README uses for a second FidelityFX upscaler DLL.
SECOND_UPSCALER = "amd_fidelityfx_upscaler_dx12.amd.dll"
#: OptiScaler 10 calls its FidelityFX route (FSR 2.3, 3.1 and 4) "ffx"; older
#: releases, and HelixSR's README, call it "fsr31".
OPTISCALER_UPSCALER = "ffx"


def _optiscaler_path() -> Path:
    return helixsr_root() / ".optiscaler"


def _optiscaler_records() -> dict[str, dict]:
    records = _read_json(_optiscaler_path() / "games.json", {})
    return {str(key): value for key, value in records.items() if isinstance(value, dict)}


def _ini_get(text: str, section: str, key: str) -> str | None:
    current = ""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current = stripped[1:-1]
        elif (current.lower() == section.lower() and "=" in stripped
              and stripped.split("=", 1)[0].strip().lower() == key.lower()):
            return stripped.split("=", 1)[1].strip()
    return None


def _ini_set(text: str, section: str, key: str, value: str) -> str:
    """Set one key in one section, as OptiScaler Client does; nothing else moves."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    inside = found = written = False
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if inside and not written:
                lines.insert(index, f"{key}={value}")
                written = True
                index += 1
            inside = stripped[1:-1].lower() == section.lower()
            found = found or inside
        elif (inside and "=" in stripped
              and stripped.split("=", 1)[0].strip().lower() == key.lower()):
            lines[index] = f"{key}={value}"
            written = True
        index += 1
    if not found:
        lines.append(f"[{section}]")
    if not written:
        lines.append(f"{key}={value}")
    return newline.join(lines)


def _windows_path(path: Path) -> str:
    """The path Proton's Wine sees: Z: is the Linux root."""
    return "Z:" + os.path.realpath(path).replace("/", "\\")


def _optiscaler_settings(folder: Path) -> dict[tuple[str, str], str]:
    return {
        ("Upscalers", "Dx12Upscaler"): OPTISCALER_UPSCALER,
        ("Libraries", "FfxDx12Path"): _windows_path(folder / LOADER_DLL),
        ("Libraries", "FfxDx12SRPath"): _windows_path(folder / UPSCALER_DLL),
    }


def _optiscaler_upscaler(root: Path, text: str) -> Path | None:
    """The FidelityFX upscaler OptiScaler loads now (the FSR4 DLL), if any."""
    configured = (_ini_get(text, "Libraries", "FfxDx12SRPath") or "auto").strip()
    folder = (_ini_get(text, "Libraries", "OptiDllPath") or "auto").strip()
    if configured.lower() == "auto":
        relative = (Path("OptiScaler") if folder.lower() == "auto" else Path(folder.replace("\\", "/"))) / UPSCALER_DLL
    elif ":" in configured or configured.startswith("/"):
        return None
    else:
        relative = Path(configured.replace("\\", "/"))
    if ".." in relative.parts:
        return None
    candidate = root / relative
    if candidate.is_dir():
        candidate = candidate / UPSCALER_DLL
    return candidate if candidate.is_file() and not _is_helixsr(candidate) else None


def _optiscaler_games() -> list[dict]:
    """Games with OptiScaler in place, from OptiScaler Client's list."""
    from .bc250_opticlient import opticlient_games, opticlient_state

    try:
        if not opticlient_state().get("current"):
            return []
        games = opticlient_games()
    except (OSError, ValueError, RuntimeError):
        return []
    found = []
    for game in games:
        adapter = str(game.get("adapter") or "")
        if not adapter or adapter == "unknown":
            continue
        found.append(game)
    return found


def _optiscaler_root(appid: str) -> tuple[dict, Path]:
    from .bc250_opticlient import opticlient_records

    appid = str(appid or "").strip()
    game = next((g for g in _optiscaler_games() if str(g.get("appid")) == appid), None)
    if game is None:
        raise RuntimeError("OptiScaler is not installed in this game. Install it with the FSR4 OptiScaler Client first.")
    records = _read_json(opticlient_records() / "games.json", [])
    record = next(
        (r for r in records if isinstance(r, dict) and str(r.get("AppId") or "") == appid), None
    )
    install = Path(str((record or {}).get("InstallPath") or ""))
    root = install / str(game.get("location") or "")
    if not str(install) or not (root / OPTISCALER_INI).is_file():
        raise RuntimeError("OptiScaler's settings file was not found in this game.")
    return game, root


def _optiscaler_state(record: dict) -> str:
    """``installed`` while OptiScaler.ini still names the HelixSR folder."""
    root = Path(str(record.get("root") or ""))
    folder = root / OPTISCALER_FOLDER
    try:
        text = (root / OPTISCALER_INI).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "restored"
    pointed = _ini_get(text, "Libraries", "FfxDx12SRPath") == _windows_path(folder / UPSCALER_DLL)
    return "installed" if pointed and _is_helixsr(folder / UPSCALER_DLL) else "restored"


def optiscaler_rows(*, available: bool = True) -> list[dict]:
    """Games with OptiScaler: HelixSR routed through it, or ready to be."""
    records = _optiscaler_records()
    rows = [
        {
            "appid": appid,
            "kind": "optiscaler",
            "name": str(record.get("name") or appid),
            "state": _optiscaler_state(record),
            "files": [str(Path(str(record.get("root") or "")) / OPTISCALER_INI)],
            "fsr4": bool(record.get("fsr4")),
        }
        for appid, record in records.items()
    ]
    if not available:
        return rows
    for game in _optiscaler_games():
        appid = str(game.get("appid") or "")
        if not appid or appid in records:
            continue
        rows.append({
            "appid": appid,
            "kind": "optiscaler",
            "name": str(game.get("name") or appid),
            "state": "available",
            "files": [],
            "fsr4": False,
        })
    return rows


def install_helixsr_optiscaler(appid: str) -> dict:
    """Point a game's OptiScaler at HelixSR; FSR4 stays selectable beside it."""
    if not helixsr_state()["network_ready"]:
        raise RuntimeError("Install HelixSR and build its network files first.")
    appid = str(appid or "").strip()
    records = _optiscaler_records()
    if appid in records:
        raise RuntimeError("HelixSR is already recorded for this game. Remove it first, then add it again.")
    game, root = _optiscaler_root(appid)
    _refuse_running(root)
    folder = root / OPTISCALER_FOLDER
    if folder.exists() or folder.is_symlink():
        raise RuntimeError("This game already has a HelixSR folder that Control Center did not create. Remove it by hand first.")
    ini = root / OPTISCALER_INI
    original = ini.read_bytes()
    text = original.decode("utf-8", errors="surrogateescape")
    fsr4 = _optiscaler_upscaler(root, text)
    source = helixsr_directory()
    backup = _optiscaler_path() / appid / OPTISCALER_INI
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(original)
    try:
        folder.mkdir()
        for name in (LOADER_DLL, UPSCALER_DLL):
            shutil.copyfile(source / HELIXSR_DLL, folder / name)
        for name in HELIXSR_NETWORK_FILES:
            shutil.copyfile(source / name, folder / name)
        settings = (source / "helixsr.ini").read_text(encoding="utf-8")
        if fsr4 is not None:
            shutil.copyfile(fsr4, folder / SECOND_UPSCALER)
            settings = _ini_set(settings, "Forwarding", "UpscalerDll", SECOND_UPSCALER)
        (folder / "helixsr.ini").write_text(settings, encoding="utf-8")
        for (section, key), value in _optiscaler_settings(folder).items():
            text = _ini_set(text, section, key, value)
        written = text.encode("utf-8", errors="surrogateescape")
        staged = root / f".{OPTISCALER_INI}.bc250-helixsr"
        staged.write_bytes(written)
        os.replace(staged, ini)
        records[appid] = {
            "name": str(game.get("name") or appid),
            "root": str(root),
            "backup": str(backup),
            "written_sha256": hashlib.sha256(written).hexdigest(),
            "fsr4": fsr4 is not None,
            "version": HELIXSR_VERSION,
        }
        _write_json(_optiscaler_path() / "games.json", records)
    except Exception:
        if ini.read_bytes() != original:
            ini.write_bytes(original)
        shutil.rmtree(folder, ignore_errors=True)
        (root / f".{OPTISCALER_INI}.bc250-helixsr").unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
        raise
    return {"game": records[appid]["name"], "fsr4": fsr4 is not None}


def remove_helixsr_optiscaler(appid: str) -> dict:
    """Put OptiScaler.ini back exactly and remove the HelixSR folder."""
    appid = str(appid or "").strip()
    records = _optiscaler_records()
    record = records.get(appid)
    if record is None:
        raise RuntimeError("HelixSR is not recorded for this game.")
    root = Path(str(record.get("root") or ""))
    _refuse_running(root)
    ini = root / OPTISCALER_INI
    backup = Path(str(record.get("backup") or ""))
    restored = "kept"
    if ini.is_file():
        current = ini.read_bytes()
        if hashlib.sha256(current).hexdigest() == record.get("written_sha256") and backup.is_file():
            # Untouched since: the saved file goes back byte for byte, so
            # OptiScaler Client recognises it again.
            staged = root / f".{OPTISCALER_INI}.bc250-helixsr"
            shutil.copyfile(backup, staged)
            os.replace(staged, ini)
            restored = "exact"
        elif _ini_get(current.decode("utf-8", errors="replace"), "Libraries", "FfxDx12SRPath") == \
                _windows_path(root / OPTISCALER_FOLDER / UPSCALER_DLL):
            # Changed in OptiScaler's own menu since: only HelixSR's three
            # values go back, every other setting stays.
            text = current.decode("utf-8", errors="surrogateescape")
            saved = backup.read_text(encoding="utf-8", errors="surrogateescape") if backup.is_file() else ""
            for section, key in _optiscaler_settings(root / OPTISCALER_FOLDER):
                text = _ini_set(text, section, key, _ini_get(saved, section, key) or "auto")
            ini.write_bytes(text.encode("utf-8", errors="surrogateescape"))
            restored = "settings"
    folder = root / OPTISCALER_FOLDER
    if folder.is_dir() and not folder.is_symlink():
        shutil.rmtree(folder)
    shutil.rmtree(backup.parent, ignore_errors=True)
    del records[appid]
    _write_json(_optiscaler_path() / "games.json", records)
    return {"game": str(record.get("name") or appid), "restored": restored}


def _refuse_running(folder: Path, proc: Path = Path("/proc")) -> None:
    """Refuse while a process runs from the game folder (Proton paths included)."""
    spellings = {str(folder).rstrip("/") + "/", os.path.realpath(folder).rstrip("/") + "/"}
    try:
        entries = list(proc.iterdir())
    except OSError:
        return
    for entry in entries:
        if not entry.name.isdigit() or entry.name == str(os.getpid()):
            continue
        try:
            command = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        command = command.replace("\\", "/")
        if any(spelling in command for spelling in spellings):
            raise RuntimeError("Close this game before changing its files.")


# ---------------------------------------------------------------- state


def helixsr_state(*, machine: str | None = None) -> dict:
    """Read-only: the release, its network files and every game's state."""
    directory = helixsr_directory()
    try:
        marker = (directory / HELIXSR_MARKER).read_text(encoding="ascii").strip()
    except OSError:
        marker = ""
    installed = directory.exists()
    current = bool(
        marker == HELIXSR_SHA256
        and (directory / HELIXSR_SETUP).is_file()
        and _is_helixsr(directory / HELIXSR_DLL, frozenset({HELIXSR_DLL_SHA256}))
    )
    network_ready = current and all(
        _nonempty(directory / name) for name in HELIXSR_NETWORK_FILES
    )
    try:
        others = sorted(
            entry.name for entry in helixsr_root().iterdir()
            if entry.is_dir() and not entry.name.startswith(".")
            and entry.name != HELIXSR_VERSION
        )
    except OSError:
        others = []
    supported = (machine or platform.machine()) in {"x86_64", "amd64", "AMD64"}
    if network_ready:
        state = "ready"
    elif current:
        state = "needs-network"
    elif installed:
        state = "invalid"
    elif others:
        state = "update-available"
    else:
        state = "not-installed"
    # Recorded games are listed even when the release folder is gone: they
    # still carry HelixSR and must stay removable.
    games = helixsr_games(optiscaler=network_ready)
    return {
        "provider": "helixsr",
        "version": HELIXSR_VERSION,
        "repository": HELIXSR_REPOSITORY,
        "supported": supported,
        "installer_available": supported,
        "installed": installed,
        "current": current,
        "network_ready": network_ready,
        "state": state,
        "path": str(directory),
        "other_versions": others,
        "wine_available": wine_available(),
        "local_dlss": bool(local_dlss_candidates()),
        "games": games,
        "installed_games": sum(1 for game in games if game["state"] != "available"),
    }


def _nonempty(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


# ---------------------------------------------------------------- terminal

_WINE_CHECK = '''bc250_wine=""
for bc250_candidate in "$HOME"/.local/share/Steam/steamapps/common/Proton*/files/bin/wine \\
    "$HOME"/.steam/steam/steamapps/common/Proton*/files/bin/wine \\
    "$HOME"/.local/share/Steam/compatibilitytools.d/*/files/bin/wine \\
    "$HOME"/.steam/root/compatibilitytools.d/*/files/bin/wine; do
  if test -x "$bc250_candidate"; then bc250_wine="$bc250_candidate"; break; fi
done
test -n "$bc250_wine" || bc250_wine="$(command -v wine || true)"
test -n "$bc250_wine" || {
  echo "ERROR: HelixSR's setup compiles its shaders through Proton or Wine, and neither was found."
  echo "Install Proton from Steam (any game set to Proton installs it), then retry."
  exit 69
}'''


def local_dlss_candidates() -> list[Path]:
    """Copies of NVIDIA's DLSS 310.7.0 DLL already on this PC.

    OptiScaler Client downloads it from NVIDIA's GitHub, checked against the
    same SHA-256, and keeps it in its payload folder. Using that copy spares a
    second download; the terminal checks its digest again before using it,
    and HelixSR's setup downloads the DLL itself (after asking) otherwise.
    """
    from .bc250_opticlient import opticlient_records

    payload = opticlient_records() / "BC250" / "payload" / "nvngx_dlss.dll"
    return [payload] if payload.is_file() and not payload.is_symlink() else []


def _setup_block(target: str) -> str:
    """Run upstream's setup without ever reaching its ``sudo`` branch.

    With system numpy present the setup uses it. Without it the setup would
    offer ``sudo <package manager>``; HELIXSR_FORCE_PORTABLE makes it use its
    portable Python in ~/.local/share/HelixSR instead, as it does on SteamOS.
    ``--yes`` is never passed: the setup asks in this terminal before it
    downloads NVIDIA's DLSS DLL.

    A copy of that DLL already on this PC (OptiScaler Client's) is copied to a
    private folder, checked by SHA-256 there and handed over with ``--dlss``;
    the setup then downloads nothing from NVIDIA.
    """
    candidates = " ".join(shlex.quote(str(path)) for path in local_dlss_candidates())
    return f'''bc250_portable=1
if command -v python3 >/dev/null 2>&1 && python3 -c 'import numpy, sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
  bc250_portable=0
fi
bc250_dlss_dir="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-helixsr-dlss.XXXXXX")"
bc250_dlss_args=()
for bc250_candidate in {candidates}; do
  test -f "$bc250_candidate" -a ! -L "$bc250_candidate" || continue
  cp -- "$bc250_candidate" "$bc250_dlss_dir/nvngx_dlss.dll" || continue
  if printf '%s  %s\\n' {DLSS_DLL_SHA256} "$bc250_dlss_dir/nvngx_dlss.dll" | sha256sum -c --status -; then
    echo "Using the copy of NVIDIA's DLSS 310.7.0 DLL already on this PC (checked by SHA-256):"
    echo "  $bc250_candidate"
    bc250_dlss_args=(--dlss "$bc250_dlss_dir/nvngx_dlss.dll")
    break
  fi
  echo "Skipping $bc250_candidate: it is not NVIDIA's DLSS 310.7.0 DLL."
  rm -f -- "$bc250_dlss_dir/nvngx_dlss.dll"
done
echo
echo "Building HelixSR's network files on this PC."
if test "${{#bc250_dlss_args[@]}}" -eq 0; then
  echo "The setup asks before it downloads NVIDIA's DLSS 310.7.0 DLL (license: {DLSS_LICENSE})."
else
  echo "Nothing is downloaded from NVIDIA. The DLL stays under NVIDIA's license: {DLSS_LICENSE}"
fi
echo "The files it builds hold NVIDIA's network: they are for this PC only, never share or upload them."
echo
if ! HELIXSR_FORCE_PORTABLE="$bc250_portable" bash {target}/{HELIXSR_SETUP} {target} "${{bc250_dlss_args[@]}}"; then
  rm -rf -- "$bc250_dlss_dir"
  echo
  echo "The network files were not built. HelixSR is installed; use Build network files to try again."
  exit 1
fi
rm -rf -- "$bc250_dlss_dir"
for bc250_file in {" ".join(HELIXSR_NETWORK_FILES)}; do
  test -s {target}/"$bc250_file" || {{ echo "ERROR: $bc250_file was not created."; exit 1; }}
done
echo
echo "OK: HelixSR {HELIXSR_VERSION} is ready. Add it to a game from Additional settings > Compatibility."'''


def build_helixsr_install_command() -> str:
    """Download, verify and unpack the pinned release, then build the network."""
    root = shlex.quote(str(helixsr_root()))
    target = shlex.quote(str(helixsr_directory()))
    python = shlex.quote(sys.executable or "python3")
    return f'''set -Eeuo pipefail
echo "== HelixSR {HELIXSR_VERSION} · DLSS Model E for FSR 3.1 games =="
echo "Source: {HELIXSR_REPOSITORY} ({HELIXSR_TAG})"
echo "HelixSR is an independent project, not affiliated with NVIDIA or AMD."
test "$(uname -m)" = x86_64 || {{ echo "ERROR: HelixSR's setup runs on x86_64 Linux only."; exit 64; }}
for bc250_command in sha256sum mktemp; do
  command -v "$bc250_command" >/dev/null 2>&1 || {{ echo "ERROR: $bc250_command is required."; exit 69; }}
done
bc250_python="$(command -v python3 || echo {python})"
if command -v curl >/dev/null 2>&1; then
  bc250_fetch() {{ curl -fL --retry 3 --connect-timeout 20 --progress-bar -o "$1" "$2"; }}
elif command -v wget >/dev/null 2>&1; then
  bc250_fetch() {{ wget -q --show-progress -O "$1" "$2"; }}
else
  echo "ERROR: curl or wget is required to download HelixSR."; exit 69
fi
{_WINE_CHECK}
bc250_work="$(mktemp -d "${{TMPDIR:-/tmp}}/bc250-helixsr.XXXXXX")"
trap 'rm -rf -- "$bc250_work"' EXIT
bc250_archive="$bc250_work/{HELIXSR_ARCHIVE}"
echo "Downloading {HELIXSR_ARCHIVE} ({HELIXSR_SIZE / 1_000_000:.1f} MB)..."
bc250_fetch "$bc250_archive" {shlex.quote(HELIXSR_URL)}
echo "Checking the reviewed SHA-256..."
printf '%s  %s\\n' {HELIXSR_SHA256} "$bc250_archive" | sha256sum -c -
echo "Checking the archive layout and unpacking..."
"$bc250_python" -I - "$bc250_archive" "$bc250_work" {HELIXSR_TOP} <<'BC250_UNZIP'
import stat, sys, zipfile
archive, destination, top = sys.argv[1:4]
with zipfile.ZipFile(archive) as bundle:
    for item in bundle.infolist():
        name = item.filename
        parts = name.split("/")
        if parts[0] != top or ".." in parts or name.startswith("/") or "\\\\" in name:
            sys.exit(f"ERROR: unexpected archive entry: {{name}}")
        if stat.S_ISLNK(item.external_attr >> 16):
            sys.exit(f"ERROR: the archive contains a link: {{name}}")
    bundle.extractall(destination)
BC250_UNZIP
bc250_stage="$bc250_work/{HELIXSR_TOP}"
printf '%s  %s\\n' {HELIXSR_DLL_SHA256} "$bc250_stage/{HELIXSR_DLL}" | sha256sum -c - >/dev/null || {{
  echo "ERROR: the HelixSR DLL in the archive is not the reviewed one."; exit 29; }}
chmod +x "$bc250_stage/{HELIXSR_SETUP}" "$bc250_stage/setup/lib/model/launch_synth"
printf '%s\\n' {HELIXSR_SHA256} > "$bc250_stage/{HELIXSR_MARKER}"
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
  echo "Removing the older HelixSR copy $(basename "$bc250_old")."
  rm -rf -- "$bc250_old"
done
echo "OK: the HelixSR {HELIXSR_VERSION} release is installed in {helixsr_directory()}."
{_setup_block(target)}
'''


def build_helixsr_network_command() -> str:
    """Build (or rebuild) the network files of the installed release."""
    target = shlex.quote(str(helixsr_directory()))
    return f'''set -Eeuo pipefail
echo "== HelixSR {HELIXSR_VERSION} · network files =="
test -f {target}/{HELIXSR_SETUP} || {{ echo "ERROR: install HelixSR first."; exit 66; }}
{_WINE_CHECK}
{_setup_block(target)}
'''


def build_helixsr_remove_command() -> str:
    """Remove the release and upstream's cache. Games must be restored first."""
    root = shlex.quote(str(helixsr_root()))
    cache = shlex.quote(str(helixsr_cache()))
    return f'''set -Eeuo pipefail
echo "== Removing HelixSR =="
rm -rf -- {root}
if test -d {cache}; then
  echo "Removing HelixSR's setup cache (portable Python and shader compiler) in {helixsr_cache()}."
  rm -rf -- {cache}
fi
echo "OK: HelixSR was removed. Your games use their own FSR files."
'''


# ---------------------------------------------------------------- per game


def _game(appid: str) -> dict:
    appid = str(appid or "").strip()
    folder = _folders().get(appid)
    if folder is not None:
        path = Path(str(folder["path"]))
        if not path.is_dir():
            raise RuntimeError("That folder does not exist.")
        return {"appid": appid, "name": str(folder.get("name") or path.name), "path": str(path)}
    if not appid.isdigit():
        raise ValueError("Invalid Steam app id.")
    for game in installed_steam_game_folders():
        if game["appid"] == appid:
            return game
    raise RuntimeError("This game is not installed in Steam.")


def install_helixsr_game(appid: str) -> dict:
    """Put HelixSR in a game: the original DLL is kept as ``*.original.dll``.

    All or nothing: if any step fails, every file already changed is put back.
    """
    state = helixsr_state()
    if not state["network_ready"]:
        raise RuntimeError("Install HelixSR and build its network files first.")
    game = _game(appid)
    install = Path(game["path"])
    records = _records()
    if str(appid) in records:
        raise RuntimeError("HelixSR is already recorded for this game. Remove it first, then add it again.")
    _refuse_running(install)
    targets = _fsr_folders(install)
    if not targets:
        raise RuntimeError("No FSR 3.1 DLL was found in this game. HelixSR replaces amd_fidelityfx_upscaler_dx12.dll or amd_fidelityfx_dx12.dll.")
    for target in targets:
        if _is_helixsr(target):
            raise RuntimeError("HelixSR is already in this game, copied there by hand. Use Steam > Verify integrity of game files to put the game's own file back first.")
        if _backup_for(target).exists():
            raise RuntimeError("This game already has an *.original.dll backup from an earlier manual install. Remove it by hand, or keep that install as it is.")
    source = helixsr_directory()
    undo: list = []
    files: list[dict] = []
    try:
        for target in targets:
            folder = target.parent
            staged = folder / f".{target.name}.bc250-helixsr"
            shutil.copyfile(source / HELIXSR_DLL, staged)
            undo.append(lambda staged=staged: staged.unlink(missing_ok=True))
            backup = _backup_for(target)
            os.rename(target, backup)
            undo.append(lambda target=target, backup=backup: os.rename(backup, target))
            os.replace(staged, target)
            undo.append(lambda target=target: target.unlink(missing_ok=True))
            created = []
            for name in HELIXSR_NETWORK_FILES:
                destination = folder / name
                if not destination.exists():
                    created.append(name)
                shutil.copyfile(source / name, destination)
                if name in created:
                    undo.append(lambda destination=destination: destination.unlink(missing_ok=True))
            files.append({
                "path": str(target),
                "backup": str(backup),
                "created": created,
            })
        records[str(appid)] = {
            "name": game["name"], "install": str(install), "files": files, "version": HELIXSR_VERSION,
        }
        _write_json(_records_path(), records)
    except Exception:
        for step in reversed(undo):
            try:
                step()
            except OSError:
                pass
        raise
    return {"game": game["name"], "files": [entry["path"] for entry in files]}


def remove_helixsr_game(appid: str) -> dict:
    """Put the game's own DLL back and remove what HelixSR added."""
    appid = str(appid or "").strip()
    records = _records()
    record = records.get(appid)
    if record is None:
        raise RuntimeError("HelixSR is not recorded for this game.")
    files = [Path(str(entry.get("path") or "")) for entry in record["files"]]
    if record.get("install"):
        _refuse_running(Path(str(record["install"])))
    elif files:
        _refuse_running(Path(os.path.commonpath([str(path.parent) for path in files])))
    entries = []
    for entry in record["files"]:
        target = Path(str(entry.get("path") or ""))
        backup = Path(str(entry.get("backup") or _backup_for(target)))
        ours = _is_helixsr(target)
        # Checked for every folder before any is touched, so a refusal
        # leaves the game exactly as it was.
        if ours and not backup.is_file():
            raise RuntimeError("The game's original FSR file is missing. Use Steam > Verify integrity of game files instead.")
        entries.append((entry, target, backup, ours))
    kept: list[str] = []
    for entry, target, backup, ours in entries:
        if ours:
            os.replace(backup, target)
        elif backup.is_file():
            # The game already put its own file back (an update or a file
            # check); the old backup is left for the user to judge.
            kept.append(str(backup))
        for name in (*entry.get("created", ()), HELIXSR_LOG):
            if name in (*HELIXSR_NETWORK_FILES, HELIXSR_LOG):
                (target.parent / name).unlink(missing_ok=True)
    del records[appid]
    _write_json(_records_path(), records)
    return {"game": str(record.get("name") or appid), "kept": kept}
